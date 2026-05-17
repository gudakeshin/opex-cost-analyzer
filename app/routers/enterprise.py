from __future__ import annotations

import re
import urllib.request as _urllib_req
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from app.config import UPLOAD_DIR
from app.routers._shared import _memory
from app.schemas import (
    CompanyResearchRequest,
    ConflictResolveRequest,
    ConsolidateRequest,
    CostToServeRequest,
    SectorPackOverrideRequest,
)
from app.services.benchmarks import resolve_benchmark_payload
from app.services.compliance import append_audit_event
from app.services.sector_packs import (
    get_pack_override,
    list_available_packs,
    list_pack_overrides,
    load_pack,
    run_regression_test,
    set_pack_override,
)
from app.skills import engine as _engine
from app.skills.registry import discover_skills
from app.storage import read_json, write_json

router = APIRouter()


@router.get("/api/v1/conflicts/{session_id}")
def get_conflicts(session_id: str) -> Dict[str, Any]:
    from app.models import NormalizedSpendLine
    from app.services.conflict_resolver import ConflictResolver

    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    raw_lines = analysis.get("normalized_spend") or analysis.get("skill_outputs", {}).get("spend-profiler", {}).get("lines", [])
    if not raw_lines:
        raise HTTPException(status_code=404, detail="No normalized spend lines found — run analysis first")
    lines = [NormalizedSpendLine(**l) if isinstance(l, dict) else l for l in raw_lines]
    resolver = ConflictResolver()
    conflicts = resolver.run_all(lines)
    summary = resolver.summary(conflicts)
    manifest_path = UPLOAD_DIR / session_id / "manifest.json"
    manifest = read_json(manifest_path, {})
    manifest["conflict_state"] = {
        "total": summary["total"],
        "unresolved": summary["unresolved"],
        "by_type": summary["by_type"],
        "by_severity": summary["by_severity"],
        "has_intercompany": bool(summary["by_type"].get("intercompany_inflation", 0) > 0),
    }
    try:
        write_json(manifest_path, manifest)
    except Exception:
        pass
    append_audit_event(f"conflict_detection session={session_id} total={summary['total']}")
    return summary


@router.post("/api/v1/conflicts/resolve")
def resolve_conflicts(req: ConflictResolveRequest, session_id: str) -> Dict[str, Any]:
    from app.models import NormalizedSpendLine
    from app.services.conflict_resolver import (
        ConflictResolver,
        escalate,
        resolve_eliminate_intercompany,
        resolve_gstin_dedup,
        resolve_tds_gross_up,
    )

    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    raw_lines = analysis.get("normalized_spend") or analysis.get("skill_outputs", {}).get("spend-profiler", {}).get("lines", [])
    if not raw_lines:
        raise HTTPException(status_code=404, detail="No normalized spend lines — run analysis first")
    lines = [NormalizedSpendLine(**l) if isinstance(l, dict) else l for l in raw_lines]
    resolver = ConflictResolver()
    conflicts = resolver.run_all(lines)
    resolved_count = 0
    escalated_count = 0
    for conflict in conflicts:
        if req.conflict_ids and conflict.conflict_id not in req.conflict_ids:
            continue
        strategy = req.strategy or conflict.resolution_strategy
        if strategy == "tds_gross_up":
            lines, conflict = resolve_tds_gross_up(lines, conflict)
            resolved_count += 1
        elif strategy == "gstin_dedup":
            lines, conflict = resolve_gstin_dedup(lines, conflict)
            resolved_count += 1
        elif strategy == "eliminate_intercompany":
            lines, conflict = resolve_eliminate_intercompany(lines, conflict)
            resolved_count += 1
        elif strategy == "escalate" or not strategy:
            escalate(conflict)
            escalated_count += 1
    updated_analysis = dict(analysis)
    if "normalized_spend" in updated_analysis:
        updated_analysis["normalized_spend"] = [l.model_dump() for l in lines]
    _memory.put("session", session_id, updated_analysis)
    append_audit_event(f"conflicts_resolved session={session_id} resolved={resolved_count} escalated={escalated_count}")
    return {
        "resolved_count": resolved_count,
        "escalated_count": escalated_count,
        "total_conflicts": len(conflicts),
        "summary": resolver.summary(conflicts),
    }


@router.post("/api/v1/consolidate/{session_id}")
def consolidate_session(session_id: str, req: ConsolidateRequest) -> Dict[str, Any]:
    from app.models import EntityTree, NormalizedSpendLine
    from app.services.consolidation import ConsolidationEngine

    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    raw_lines = analysis.get("normalized_spend") or analysis.get("skill_outputs", {}).get("spend-profiler", {}).get("lines", [])
    if not raw_lines:
        raise HTTPException(status_code=404, detail="No normalized spend lines — run analysis first")
    lines = [NormalizedSpendLine(**l) if isinstance(l, dict) else l for l in raw_lines]
    entity_tree: EntityTree | None = None
    if req.entity_tree:
        try:
            entity_tree = EntityTree(**req.entity_tree)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid entity_tree: {exc}")
    engine = ConsolidationEngine(entity_tree)
    report = engine.consolidate(lines)
    if req.include_entity_comparison:
        report["entity_comparison"] = engine.entity_comparison(lines)
    append_audit_event(f"consolidation_run session={session_id} entities={report.get('entity_count', 0)}")
    return report


@router.get("/api/metrics")
def get_metrics() -> Dict[str, Any]:
    from app.config import OUTPUT_DIR, UPLOAD_DIR
    sessions = [p for p in UPLOAD_DIR.glob("*") if p.is_dir()]
    outputs = list(OUTPUT_DIR.glob("*"))
    return {
        "sessions_count": len(sessions),
        "exports_count": len(outputs),
        "skills_discovered": len(discover_skills()),
        "upload_success_target": ">99%",
        "classification_accuracy_target": ">85%",
    }


@router.get("/api/v1/sector-packs")
def list_sector_packs() -> Dict[str, Any]:
    packs = []
    for pid in list_available_packs():
        try:
            p = load_pack(pid)
            packs.append({
                "pack_id": pid,
                "sector": p["manifest"].get("sector"),
                "version": p["version"],
                "effective_from": p.get("effective_from", ""),
                "status": p["status"],
            })
        except Exception as exc:
            packs.append({"pack_id": pid, "error": str(exc)})
    return {"packs": packs, "total": len(packs)}


@router.get("/api/v1/sector-packs/{pack_id}")
def get_sector_pack(pack_id: str) -> Dict[str, Any]:
    try:
        p = load_pack(pack_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "pack_id": pack_id,
        "manifest": p["manifest"],
        "version": p["version"],
        "effective_from": p.get("effective_from", ""),
        "status": p["status"],
        "sector_levers_count": len(p.get("sector_levers", {}).get("sector_specific_levers", [])),
        "kpi_count": len(p.get("kpi_pack", [])),
        "peer_count": len(p.get("peer_set", {}).get("peers", [])),
    }


@router.get("/api/v1/sector-packs/{pack_id}/regression-test")
def sector_pack_regression_test(pack_id: str) -> Dict[str, Any]:
    return run_regression_test(pack_id)


@router.post("/api/v1/sector-packs/override")
def sector_pack_override(req: SectorPackOverrideRequest) -> Dict[str, Any]:
    result = set_pack_override(
        req.pack_id,
        disabled_levers=req.disabled_levers,
        lever_overrides=req.lever_overrides,
        engagement_id=req.engagement_id,
    )
    append_audit_event(
        f"sector_pack_override pack_id={req.pack_id} engagement={req.engagement_id}",
        data=result,
    )
    return result


@router.get("/api/v1/sector-packs/overrides/list")
def list_sector_pack_overrides() -> Dict[str, Any]:
    return {"overrides": list_pack_overrides()}


@router.post("/api/v1/cost-to-serve")
def cost_to_serve_endpoint(req: CostToServeRequest) -> Dict[str, Any]:
    from app.memory import MemoryStore
    from app.models import NormalizedSpendLine

    store = MemoryStore()
    existing = store.get("session", req.session_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")
    lines: List[NormalizedSpendLine] = [
        NormalizedSpendLine(**raw) for raw in existing.get("normalized_spend", []) if isinstance(raw, dict)
    ]
    annual_revenue = float(existing.get("annual_revenue") or 0.0)
    headcount = float(req.headcount or existing.get("headcount") or 0.0)
    result = _engine.cost_to_serve_analyzer(
        lines,
        segment_revenue=req.segment_revenue,
        annual_revenue=annual_revenue,
        headcount=headcount,
    )
    append_audit_event("cost_to_serve_analysis", session_id=req.session_id)
    return result


@router.post("/api/v1/diagnostic/company-research")
async def company_research(req: CompanyResearchRequest) -> Dict[str, Any]:
    texts: List[str] = []
    url_errors: List[Dict[str, str]] = []
    for url in (req.urls or [])[:5]:
        url = (url or "").strip()
        if not url.startswith("http"):
            continue
        try:
            request = _urllib_req.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; OpExResearcher/1.0)"})
            with _urllib_req.urlopen(request, timeout=12) as resp:
                raw = resp.read(60_000).decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()
            texts.append(text[:15_000])
        except Exception as exc:
            url_errors.append({"url": url, "error": str(exc)[:150]})

    company_signals = _engine.document_contextualizer(texts)
    inferred = company_signals.get("inferred_industry", "")
    effective_industry = inferred if inferred else req.industry

    _PACK_TO_BENCH: Dict[str, str] = {
        "it_ites": "technology",
        "bfsi_banks": "financial_services",
        "insurance_general": "financial_services",
        "fmcg_consumer": "retail_consumer",
        "pharma_lifesciences": "healthcare",
        "energy_utilities": "manufacturing",
        "retail_organized": "retail_consumer",
        "telecom_infra": "technology",
        "manufacturing_diversified": "manufacturing",
        "psu_cpse": "manufacturing",
        "conglomerate": "manufacturing",
    }
    bench_industry = _PACK_TO_BENCH.get(effective_industry, effective_industry)
    revenue_inr = req.annual_revenue_cr * 1_00_00_000
    bench_resolved = resolve_benchmark_payload(industry=bench_industry, categories=[], annual_revenue=revenue_inr)
    bench_cats = (
        bench_resolved.get("benchmark_data", {})
        .get("benchmarks", {})
        .get(bench_industry, {})
        .get("categories", {})
    )
    category_profile = []
    categories_in_pack: List[str] = []
    for cat_id, metrics in bench_cats.items():
        p50_pct = float(metrics.get("P50", 0.0))
        implied_spend = (p50_pct / 100.0) * revenue_inr
        if implied_spend > 0:
            category_profile.append({
                "category_id": cat_id,
                "category_name": cat_id.replace("_", " ").title(),
                "spend": implied_spend,
                "supplier_count": 5,
                "transaction_count": 50,
            })
            categories_in_pack.append(cat_id)
    total_implied = sum(c["spend"] for c in category_profile) or 1.0
    synthetic_profile = {"total_spend": total_implied, "category_profile": category_profile, "data_source": "benchmark_proxy"}
    bench_resolved = resolve_benchmark_payload(industry=bench_industry, categories=categories_in_pack, annual_revenue=revenue_inr)
    benchmarks = _engine.peer_benchmarker(
        synthetic_profile,
        bench_resolved["benchmark_data"],
        bench_industry,
        revenue_inr,
        selected_dataset=bench_resolved.get("selected_dataset"),
        selection_rationale=bench_resolved.get("selection_rationale"),
    )
    benchmark_gaps = []
    for row in benchmarks.get("comparisons", []):
        p50_pct = float(row.get("benchmark_p50_pct", 0.0))
        p25_pct = float(row.get("benchmark_target_pct", 0.0))
        if p50_pct <= 0:
            continue
        implied_p50_cr = round(p50_pct / 100.0 * req.annual_revenue_cr, 1)
        implied_p25_cr = round(p25_pct / 100.0 * req.annual_revenue_cr, 1)
        headroom_cr = round((p50_pct - p25_pct) / 100.0 * req.annual_revenue_cr, 1)
        benchmark_gaps.append({
            "category": row.get("category_id", ""),
            "category_name": row.get("category_name", row.get("category_id", "")),
            "p25_pct": round(p25_pct, 2),
            "p50_pct": round(p50_pct, 2),
            "actual_pct": round(p50_pct, 2),
            "gap_pct": 0.0,
            "gap_cr": 0.0,
            "implied_p50_cr": implied_p50_cr,
            "implied_p25_cr": implied_p25_cr,
            "headroom_to_p25_cr": headroom_cr,
            "percentile_band": "Reference",
        })
    benchmark_gaps.sort(key=lambda x: x["implied_p50_cr"], reverse=True)
    eligible_levers = _engine.resolve_eligible_levers(
        industry=effective_industry,
        spend_profile=synthetic_profile,
        headcount=500.0,
        annual_revenue=revenue_inr,
        root_causes=[],
    )
    cat_spend_cr = {c["category_id"]: c["spend"] / 1_00_00_000 for c in category_profile}
    total_spend_cr = sum(cat_spend_cr.values()) or 1.0
    value_at_table = []
    for lv in eligible_levers:
        rng = lv.get("savings_range_pct", {})
        if not rng:
            continue
        p10_rate = float(rng.get("p10", 0)) / 100.0
        p50_rate = float(rng.get("p50", 0)) / 100.0
        p90_rate = float(rng.get("p90", 0)) / 100.0
        primary_cat_spend_cr = 0.0
        for sig in lv.get("trigger_signals", []):
            if sig.startswith("category:") and sig.endswith("_present"):
                cid = sig.split(":")[1].replace("_present", "")
                primary_cat_spend_cr = cat_spend_cr.get(cid, 0.0)
                break
        base_spend_cr = primary_cat_spend_cr if primary_cat_spend_cr > 0 else total_spend_cr * 0.10
        p50_cr = round(p50_rate * base_spend_cr, 1)
        if p50_cr < 0.1:
            continue
        value_at_table.append({
            "lever_id": lv["lever_id"],
            "lever_name": lv["lever_name"],
            "category": "",
            "p10_cr": round(p10_rate * base_spend_cr, 1),
            "p50_cr": p50_cr,
            "p90_cr": round(p90_rate * base_spend_cr, 1),
            "npv": 0.0,
            "savings_type": lv.get("savings_type", "run_rate"),
            "complexity_tier": lv.get("complexity_tier", "medium"),
        })
    value_at_table.sort(key=lambda x: x["p50_cr"], reverse=True)
    value_at_table = value_at_table[:12]
    total_p50 = round(sum(v["p50_cr"] for v in value_at_table), 1)
    top_gap = benchmark_gaps[0] if benchmark_gaps else {}
    top_lever = value_at_table[0] if value_at_table else {}
    key_findings = []
    if top_gap:
        key_findings.append(
            f"Largest category: {top_gap.get('category_name', '')} — "
            f"₹{top_gap.get('implied_p50_cr', 0):.0f} Cr at P50 benchmark; "
            f"₹{top_gap.get('headroom_to_p25_cr', 0):.0f} Cr headroom to P25 best-in-class"
        )
    if top_lever:
        key_findings.append(
            f"Highest-value lever: {top_lever['lever_name']} with ₹{top_lever['p50_cr']:.0f} Cr P50 3-year savings"
        )
    if company_signals.get("constraints"):
        key_findings.append("Document flags: " + "; ".join(company_signals["constraints"][:2]))
    key_findings.append(
        f"Total value at table (P50, 3-year): ₹{total_p50:.0f} Cr across {len(value_at_table)} levers"
    )
    append_audit_event("diagnostic_company_research", data={"company": req.company_name, "industry": effective_industry})
    return {
        "company_name": req.company_name,
        "industry_used": effective_industry,
        "annual_revenue_cr": req.annual_revenue_cr,
        "url_count": len(texts),
        "url_errors": url_errors,
        "company_signals": company_signals,
        "benchmark_gaps": benchmark_gaps,
        "value_at_table": value_at_table,
        "total_p50_value_cr": total_p50,
        "key_findings": key_findings,
        "data_note": "Spend profile derived from benchmark P50 values — upload actual spend data for company-specific analysis.",
    }
