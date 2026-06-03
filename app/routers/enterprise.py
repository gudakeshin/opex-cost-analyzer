from __future__ import annotations

import re
import urllib.request as _urllib_req
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.config import DEEP_RESEARCH_ENABLED, GEMINI_API_KEY, UPLOAD_DIR, logger
from app.routers._shared import _memory, read_manifest, write_manifest
from app.schemas import (
    CompanyResearchRequest,
    ConflictResolveRequest,
    ConsolidateRequest,
    CostToServeRequest,
    DeepResearchStartRequest,
    DeepResearchStartResponse,
    DeepResearchStatusResponse,
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


def _fmt_cr(n: float) -> str:
    """Format a Crore value for FP&A display: ₹1,234 Cr."""
    return f"₹{n:,.0f} Cr"


_SAVINGS_TYPE_LABELS: Dict[str, str] = {
    "run_rate": "Run Rate",
    "one_time": "One-Time",
    "mixed": "Mixed",
}

_COMPLEXITY_LABELS: Dict[str, str] = {
    "low": "low complexity",
    "medium": "medium complexity",
    "high": "high complexity",
}

_PERCENTILE_LEGEND: Dict[str, str] = {
    "p10": "top-decile benchmark (stretch target)",
    "p25": "best-in-class quartile",
    "p50": "industry median",
    "p90": "lagging quartile",
}

_FINDINGS_SYSTEM_PROMPT = """You are a senior FP&A analyst writing a diagnostic findings summary for a CFO audience.
You will receive structured diagnostic data about a company's OpEx benchmark profile.

Output exactly 5–7 bullet points as a JSON array of strings. No keys, no markdown — just a JSON array.

Rules for each bullet:
- Lead with the insight or implication, not just the number
- Include % of revenue context for any monetary figure ≥ ₹1 Cr
- Reference complexity tier or time-to-value for the top lever
- Disclose key modelling assumptions (WACC, NPV horizon) in at least one bullet
- Use ₹X,XXX Cr format for Indian rupee amounts (comma-separated thousands)
- Be concise (≤ 25 words per bullet)
- Do NOT repeat the same number in two bullets

Example format:
["HR Outsourcing spend of ₹240 Cr (12% of revenue) is 1.4× industry median — ₹46 Cr addressable gap to P25.",
 "Top lever: Vendor Consolidation (low complexity) — ₹45 Cr annual run-rate savings; ₹112 Cr 3-year NPV at 12% WACC."]
"""

_EXECUTIVE_SUMMARY_SYSTEM_PROMPT = """You are a senior FP&A analyst writing a 3-sentence executive summary for a CFO.
Output only the 3 sentences as plain text (no bullets, no markdown).

Sentence 1: Company context + headline OpEx opportunity (₹ amount and % of revenue).
Sentence 2: Top recommended lever with complexity, savings estimate, and 3-year NPV.
Sentence 3: Key caveat or most important next step.

Use ₹X,XXX Cr format. Be direct and decision-oriented. ≤ 60 words total.
"""


def _generate_findings_llm(
    company_name: str,
    industry: str,
    annual_revenue_cr: float,
    benchmark_gaps: List[Dict],
    value_at_table: List[Dict],
    assumptions: Dict,
    template_fallback: List[str],
) -> List[str]:
    """Generate FP&A-grade key findings via Gemini Flash-Lite. Falls back to template_fallback on any error."""
    try:
        import json as _json
        from app.opar.gemini_client import call_gemini

        top_gaps = [
            {
                "category_name": g["category_name"],
                "implied_p50_cr": g["implied_p50_cr"],
                "gap_cr": g.get("benchmark_p50_to_p25_band_cr", 0),
                "revenue_pct": round(g["implied_p50_cr"] / annual_revenue_cr * 100, 1) if annual_revenue_cr > 0 else 0,
            }
            for g in benchmark_gaps[:3]
        ]
        top_levers = [
            {
                "lever_name": lv["lever_name"],
                "p50_cr": lv["p50_cr"],
                "npv": lv["npv"],
                "complexity_tier": lv.get("complexity_tier", "medium"),
                "savings_type_label": lv.get("savings_type_label", "Run Rate"),
            }
            for lv in value_at_table[:4]
        ]
        total_p50 = sum(lv["p50_cr"] for lv in value_at_table)
        total_p10 = sum(lv.get("p10_cr", 0) for lv in value_at_table)
        total_p90 = sum(lv.get("p90_cr", 0) for lv in value_at_table)
        total_pct = round(total_p50 / annual_revenue_cr * 100, 1) if annual_revenue_cr > 0 else 0

        user_content = _json.dumps({
            "company_name": company_name,
            "industry": industry,
            "annual_revenue_cr": annual_revenue_cr,
            "top_benchmark_gaps": top_gaps,
            "top_levers": top_levers,
            "total_p50_cr": round(total_p50, 1),
            "total_p10_cr": round(total_p10, 1),
            "total_p90_cr": round(total_p90, 1),
            "total_pct_of_revenue": total_pct,
            "assumptions": assumptions,
        }, ensure_ascii=False)

        raw = call_gemini(
            system=_FINDINGS_SYSTEM_PROMPT,
            user_content=user_content,
            max_tokens=800,
        )
        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        findings = _json.loads(raw)
        if isinstance(findings, list) and all(isinstance(f, str) for f in findings) and findings:
            return findings
    except Exception:
        pass
    return template_fallback


def _generate_executive_summary_llm(
    company_name: str,
    industry: str,
    annual_revenue_cr: float,
    key_findings: List[str],
    total_p50: float,
    top_lever_name: str,
    top_lever_npv: float,
    top_lever_complexity: str,
    assumptions: Dict,
) -> str:
    """Generate 3-sentence CFO executive summary via Gemini Flash-Lite. Falls back to first key_finding."""
    try:
        import json as _json
        from app.opar.gemini_client import call_gemini

        total_pct = round(total_p50 / annual_revenue_cr * 100, 1) if annual_revenue_cr > 0 else 0
        user_content = _json.dumps({
            "company_name": company_name,
            "industry": industry,
            "annual_revenue_cr": annual_revenue_cr,
            "total_value_at_table_cr": round(total_p50, 1),
            "total_pct_of_revenue": total_pct,
            "top_lever_name": top_lever_name,
            "top_lever_npv_3yr_cr": top_lever_npv,
            "top_lever_complexity": top_lever_complexity,
            "wacc_pct": assumptions.get("wacc_pct", 12.0),
            "key_findings_preview": key_findings[:3],
        }, ensure_ascii=False)

        summary = call_gemini(
            system=_EXECUTIVE_SUMMARY_SYSTEM_PROMPT,
            user_content=user_content,
            max_tokens=200,
        )
        if summary and len(summary) > 20:
            return summary
    except Exception:
        pass
    return key_findings[0] if key_findings else ""


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
        "financial_services_nonbank": "financial_services",
        "gcc_capability_centers": "technology",
        "healthcare_hospitals": "healthcare",
        "hospitality_travel": "retail_consumer",
    }
    bench_industry = _PACK_TO_BENCH.get(effective_industry, effective_industry)
    revenue_inr = req.annual_revenue_cr * 1_00_00_000
    # Single benchmark fetch — categories param used for dataset selection; payload always covers all categories
    bench_resolved = resolve_benchmark_payload(industry=bench_industry, categories=[], annual_revenue=revenue_inr)
    bench_cats = (
        bench_resolved.get("benchmark_data", {})
        .get("benchmarks", {})
        .get(bench_industry, {})
        .get("categories", {})
    )
    category_profile = []
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
    total_implied = sum(c["spend"] for c in category_profile) or 1.0
    synthetic_profile = {"total_spend": total_implied, "category_profile": category_profile, "data_source": "benchmark_proxy"}
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
        band_cr = round((p50_pct - p25_pct) / 100.0 * req.annual_revenue_cr, 1)
        benchmark_gaps.append({
            "category": row.get("category_id", ""),
            "category_name": row.get("category_name", row.get("category_id", "")),
            "p25_pct": round(p25_pct, 2),
            "p50_pct": round(p50_pct, 2),
            "proxy_pct": round(p50_pct, 2),
            "gap_pct": round(p50_pct - p25_pct, 2),
            "gap_cr": band_cr,
            "implied_p50_cr": implied_p50_cr,
            "implied_p25_cr": implied_p25_cr,
            "benchmark_p50_to_p25_band_cr": band_cr,
            "percentile_band": "P50 industry benchmark (proxy)",
        })
    benchmark_gaps.sort(key=lambda x: x["implied_p50_cr"], reverse=True)

    # Derive root causes from synthetic profile before lever resolution
    from app.skills.engine.lever_rules import build_signal_corpus as _build_signal_corpus
    root_cause_output = _engine.root_cause_analyzer(
        profile=synthetic_profile,
        peer=benchmarks,
        lines=[],
        headcount=float(req.headcount),
        annual_revenue=revenue_inr,
        industry=effective_industry,
    )
    derived_root_causes = root_cause_output.get("root_causes", [])
    signal_corpus = _build_signal_corpus(synthetic_profile)
    engagement_id = f"diag-{req.company_name[:20].strip()}-{int(revenue_inr)}"

    eligible_levers = _engine.resolve_eligible_levers(
        industry=effective_industry,
        spend_profile=synthetic_profile,
        headcount=float(req.headcount),
        annual_revenue=revenue_inr,
        root_causes=derived_root_causes,
        signal_corpus=signal_corpus,
        line_flags={"constraints": company_signals.get("constraints", [])},
        engagement_id=engagement_id,
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
        matched_category_id = ""
        for sig in lv.get("trigger_signals", []):
            if sig.startswith("category:") and sig.endswith("_present"):
                cid = sig.split(":")[1].replace("_present", "")
                primary_cat_spend_cr = cat_spend_cr.get(cid, 0.0)
                matched_category_id = cid
                break
        base_spend_cr = primary_cat_spend_cr if primary_cat_spend_cr > 0 else total_spend_cr * 0.10
        p50_cr = round(p50_rate * base_spend_cr, 1)
        if p50_cr < 0.1:
            continue
        npv = round(sum(p50_cr / (1.0 + req.wacc) ** t for t in range(1, 4)), 1)
        value_at_table.append({
            "lever_id": lv["lever_id"],
            "lever_name": lv["lever_name"],
            "category": matched_category_id,
            "p10_cr": round(p10_rate * base_spend_cr, 1),
            "p50_cr": p50_cr,
            "p90_cr": round(p90_rate * base_spend_cr, 1),
            "npv": npv,
            "savings_type": lv.get("savings_type", "run_rate"),
            "savings_type_label": _SAVINGS_TYPE_LABELS.get(lv.get("savings_type", "run_rate"), lv.get("savings_type", "run_rate").replace("_", " ").title()),
            "complexity_tier": lv.get("complexity_tier", "medium"),
        })
    value_at_table.sort(key=lambda x: x["p50_cr"], reverse=True)
    value_at_table = value_at_table[:12]
    total_p50 = round(sum(v["p50_cr"] for v in value_at_table), 1)
    top_gap = benchmark_gaps[0] if benchmark_gaps else {}
    top_lever = value_at_table[0] if value_at_table else {}
    key_findings = []
    if top_gap:
        implied_p50_cr = top_gap.get("implied_p50_cr", 0)
        band_cr = top_gap.get("benchmark_p50_to_p25_band_cr", 0)
        revenue_pct = round(implied_p50_cr / req.annual_revenue_cr * 100, 1) if req.annual_revenue_cr > 0 else 0.0
        key_findings.append(
            f"Largest category: {top_gap.get('category_name', '')} — "
            f"{_fmt_cr(implied_p50_cr)} ({revenue_pct}% of revenue) at P50 benchmark; "
            f"{_fmt_cr(band_cr)} headroom to P25 best-in-class"
        )
    if top_lever:
        complexity = _COMPLEXITY_LABELS.get(top_lever.get("complexity_tier", "medium"), "medium complexity")
        key_findings.append(
            f"Highest-value lever: {top_lever['lever_name']} ({complexity}) — "
            f"{_fmt_cr(top_lever['p50_cr'])} annual savings; "
            f"{_fmt_cr(top_lever['npv'])} 3-year NPV (P50 estimate)"
        )
    if value_at_table:
        total_p10 = round(sum(v["p10_cr"] for v in value_at_table), 1)
        total_p90 = round(sum(v["p90_cr"] for v in value_at_table), 1)
        key_findings.append(
            f"Savings range (P10–P90): {_fmt_cr(total_p10)} to {_fmt_cr(total_p90)} across {len(value_at_table)} levers"
        )
    if company_signals.get("constraints"):
        key_findings.append(
            "Identified constraints (may affect lever eligibility): "
            + "; ".join(company_signals["constraints"][:2])
        )
    total_pct = round(total_p50 / req.annual_revenue_cr * 100, 1) if req.annual_revenue_cr > 0 else 0.0
    key_findings.append(
        f"Total value at table (P50 annual): {_fmt_cr(total_p50)} ({total_pct}% of revenue) across {len(value_at_table)} levers"
    )
    if bench_resolved.get("selected_dataset"):
        data_note = (
            f"Spend profile derived from {bench_industry} benchmark P50 values — "
            f"upload actual spend data for company-specific analysis."
        )
    else:
        data_note = (
            f"No benchmark data found for sector '{effective_industry}'; nearest-proxy estimates used. "
            f"Results should be treated as directional only. "
            f"Upload actual spend data for precise analysis."
        )
    assumptions = {
        "wacc_pct": round(req.wacc * 100, 1),
        "headcount": req.headcount,
        "npv_horizon_years": 3,
        "profile_basis": "benchmark_proxy",
    }
    # LLM-1: replace template findings with Gemini Flash-Lite narrative (falls back to templates)
    key_findings = _generate_findings_llm(
        company_name=req.company_name,
        industry=effective_industry,
        annual_revenue_cr=req.annual_revenue_cr,
        benchmark_gaps=benchmark_gaps,
        value_at_table=value_at_table,
        assumptions=assumptions,
        template_fallback=key_findings,
    )
    # LLM-3: 3-sentence executive summary (falls back to first finding)
    executive_summary = _generate_executive_summary_llm(
        company_name=req.company_name,
        industry=effective_industry,
        annual_revenue_cr=req.annual_revenue_cr,
        key_findings=key_findings,
        total_p50=total_p50,
        top_lever_name=top_lever.get("lever_name", "") if top_lever else "",
        top_lever_npv=top_lever.get("npv", 0.0) if top_lever else 0.0,
        top_lever_complexity=top_lever.get("complexity_tier", "medium") if top_lever else "medium",
        assumptions=assumptions,
    )
    append_audit_event("diagnostic_company_research", data={"company": req.company_name, "industry": effective_industry})
    return {
        "company_name": req.company_name,
        "industry_used": effective_industry,
        "annual_revenue_cr": req.annual_revenue_cr,
        "assumptions": assumptions,
        "executive_summary": executive_summary,
        "company_signals": company_signals,
        "benchmark_gaps": benchmark_gaps,
        "value_at_table": value_at_table,
        "eligible_levers_total": len(eligible_levers),
        "total_p50_value_cr": total_p50,
        "key_findings": key_findings,
        "percentile_legend": _PERCENTILE_LEGEND,
        "profile_basis": "benchmark_proxy",
        "data_note": data_note,
        "_meta": {"url_count": len(texts), "url_errors": url_errors, "bench_industry": bench_industry},
    }


# ---------------------------------------------------------------------------
# Deep Research endpoints
# ---------------------------------------------------------------------------

def _summarize_deep_research_llm(full_text: str) -> str:
    """Condense deep research output to a CFO-grade summary ≤400 words."""
    from app.opar.gemini_client import call_gemini

    system = (
        "You are an FP&A advisor. Condense the research below into a ≤400-word summary "
        "focused on: cost structure, benchmark gaps, top savings levers, and key risks. "
        "Write in prose paragraphs — no bullet lists."
    )
    try:
        return call_gemini(system, full_text[:20_000], max_tokens=600)
    except Exception:
        return full_text[:1_200]


@router.post("/api/v1/diagnostic/deep-research", response_model=DeepResearchStartResponse)
def start_deep_research_endpoint(req: DeepResearchStartRequest) -> Dict[str, Any]:
    """Kick off a Google Deep Research background job for a company."""
    if not DEEP_RESEARCH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Deep Research is not configured — set GEMINI_API_KEY",
        )
    from app.opar.deep_research_client import start_deep_research

    query = (
        f"OpEx cost benchmarks, procurement maturity, and savings opportunities for "
        f"{req.company_name} in the {req.industry} sector. "
        f"Annual revenue approximately ₹{req.annual_revenue_cr} Cr. "
        f"Focus on: top cost categories, industry peer benchmarks, typical cost-reduction "
        f"levers, and key risk factors."
    )
    try:
        interaction_id = start_deep_research(query)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # If a session is linked, persist the interaction_id for later correlation.
    if req.session_id:
        try:
            manifest = read_manifest(req.session_id)
            manifest["deep_research_interaction_id"] = interaction_id
            write_manifest(req.session_id, manifest)
        except Exception:
            pass  # Non-fatal — main job is already started

    append_audit_event(
        "deep_research_started",
        data={"company": req.company_name, "interaction_id": interaction_id},
    )
    return {"interaction_id": interaction_id, "status": "in_progress"}


@router.get(
    "/api/v1/diagnostic/deep-research/{interaction_id}",
    response_model=DeepResearchStatusResponse,
)
def poll_deep_research_endpoint(
    interaction_id: str,
    session_id: str = Query(default=None),
) -> Dict[str, Any]:
    """Poll the status of a deep research job. Pass ?session_id=... to auto-save on completion."""
    if not DEEP_RESEARCH_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Deep Research is not configured — set GEMINI_API_KEY",
        )
    from app.opar.deep_research_client import poll_deep_research

    try:
        result = poll_deep_research(interaction_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    status = result["status"]
    if status != "completed":
        return {"status": status, "summary": None, "full_report": None, "sources": []}

    full_report = result.get("output_text") or ""
    summary = _summarize_deep_research_llm(full_report)

    # Persist to session manifest when a session is linked.
    if session_id:
        try:
            from datetime import datetime, timezone

            manifest = read_manifest(session_id)
            manifest["deep_research_summary"] = summary
            manifest["deep_research_full_report"] = full_report[:50_000]
            manifest["deep_research_completed_at"] = datetime.now(timezone.utc).isoformat()
            write_manifest(session_id, manifest)
            logger.info(
                '"deep_research_saved_to_manifest","session_id":"%s"', session_id
            )
        except Exception as exc:
            logger.warning('"deep_research_manifest_save_failed","error":"%s"', exc)

    append_audit_event(
        "deep_research_completed",
        data={"interaction_id": interaction_id, "session_id": session_id or ""},
    )
    return {
        "status": "completed",
        "summary": summary,
        "full_report": full_report,
        "sources": result.get("sources") or [],
    }
