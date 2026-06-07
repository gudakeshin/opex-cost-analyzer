from __future__ import annotations

import re
import urllib.request as _urllib_req
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, HTTPException, Query

from app.config import DEEP_RESEARCH_ENABLED, UPLOAD_DIR, logger
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
from app.services.analysis import load_taxonomy
from app.services.benchmarks import benchmark_industry_for, resolve_benchmark_payload
from app.services.compliance import append_audit_event
from app.services.sector_packs import (
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
    lines = [NormalizedSpendLine(**ln) if isinstance(ln, dict) else ln for ln in raw_lines]
    resolver = ConflictResolver()
    conflicts = resolver.run_all(lines)
    from app.services.conflict_resolver import normalize_user_actions

    user_actions = normalize_user_actions(
        dict(analysis.get("conflict_user_actions") or {}),
        conflicts,
    )
    summary = resolver.summary(conflicts, user_actions=user_actions)
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
        conflict_matches_request,
        escalate,
        normalize_user_actions,
        resolve_eliminate_intercompany,
        resolve_gstin_dedup,
        resolve_gstr_vendor_data,
        resolve_tds_gross_up,
        stable_conflict_id,
    )

    analysis = _memory.get("session", session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis for session")
    raw_lines = analysis.get("normalized_spend") or analysis.get("skill_outputs", {}).get("spend-profiler", {}).get("lines", [])
    if not raw_lines:
        raise HTTPException(status_code=404, detail="No normalized spend lines — run analysis first")
    lines = [NormalizedSpendLine(**ln) if isinstance(ln, dict) else ln for ln in raw_lines]
    resolver = ConflictResolver()
    conflicts = resolver.run_all(lines)
    user_actions = normalize_user_actions(
        dict(analysis.get("conflict_user_actions") or {}),
        conflicts,
    )
    resolved_count = 0
    escalated_count = 0
    from datetime import datetime, timezone

    targets = [c for c in conflicts if conflict_matches_request(c, req.conflict_ids)]
    if req.conflict_ids and not targets:
        raise HTTPException(
            status_code=404,
            detail="Conflict not found — refresh the page and try again.",
        )

    for conflict in targets:
        strategy = req.strategy or conflict.resolution_strategy
        fingerprint = stable_conflict_id(conflict)
        if strategy == "tds_gross_up":
            lines, conflict = resolve_tds_gross_up(lines, conflict)
            user_actions[fingerprint] = {
                "status": "applied",
                "strategy": strategy,
                "conflict_fingerprint": fingerprint,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            resolved_count += 1
        elif strategy == "gstin_dedup":
            lines, conflict = resolve_gstin_dedup(lines, conflict)
            user_actions[fingerprint] = {
                "status": "applied",
                "strategy": strategy,
                "conflict_fingerprint": fingerprint,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            resolved_count += 1
        elif strategy == "eliminate_intercompany":
            lines, conflict = resolve_eliminate_intercompany(lines, conflict)
            user_actions[fingerprint] = {
                "status": "applied",
                "strategy": strategy,
                "conflict_fingerprint": fingerprint,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            resolved_count += 1
        elif strategy == "gstr_vendor_data":
            lines, conflict = resolve_gstr_vendor_data(lines, conflict)
            user_actions[fingerprint] = {
                "status": "applied",
                "strategy": strategy,
                "conflict_fingerprint": fingerprint,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            resolved_count += 1
        elif strategy == "escalate" or not strategy:
            escalate(conflict)
            user_actions[fingerprint] = {
                "status": "flagged_for_review",
                "strategy": "escalate",
                "conflict_fingerprint": fingerprint,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            escalated_count += 1
    updated_analysis = dict(analysis)
    if "normalized_spend" in updated_analysis:
        updated_analysis["normalized_spend"] = [ln.model_dump() for ln in lines]
    updated_analysis["conflict_user_actions"] = user_actions

    spend_impact: Dict[str, Any] | None = None
    if resolved_count > 0:
        from app.services.analysis import reprofile_after_spend_correction

        spend_impact = reprofile_after_spend_correction(session_id, lines, updated_analysis)
        updated_analysis = _memory.get("session", session_id) or updated_analysis
    else:
        _memory.put("session", session_id, updated_analysis)

    append_audit_event(f"conflicts_resolved session={session_id} resolved={resolved_count} escalated={escalated_count}")
    spend_base_revision = int((updated_analysis or {}).get("spend_base_revision") or 0)
    return {
        "resolved_count": resolved_count,
        "escalated_count": escalated_count,
        "total_conflicts": len(conflicts),
        "spend_impact": spend_impact,
        "spend_base_revision": spend_base_revision,
        "summary": resolver.summary(conflicts, user_actions=user_actions),
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
    lines = [NormalizedSpendLine(**ln) if isinstance(ln, dict) else ln for ln in raw_lines]
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

# Sector-pack → benchmark-registry resolution lives in a single source of truth:
# benchmarks.SECTOR_PACK_TO_BENCHMARK (resolved via benchmark_industry_for). A
# divergent local copy previously mapped gcc_capability_centers → technology even
# though the registry ships a dedicated gcc_capability_centers dataset, silently
# mis-benchmarking GCC engagements. Always call benchmark_industry_for() instead
# of re-declaring the map here.

_TAXONOMY_NAMES: Dict[str, str] | None = None


def _category_display_name(category_id: str) -> str:
    global _TAXONOMY_NAMES
    if _TAXONOMY_NAMES is None:
        taxonomy = load_taxonomy()
        _TAXONOMY_NAMES = {
            str(cat.get("id", "")): str(cat.get("name", ""))
            for cat in taxonomy.get("categories", [])
            if cat.get("id")
        }
    return _TAXONOMY_NAMES.get(category_id) or category_id.replace("_", " ").title()


def _humanize_trigger_signal(signal: str) -> str:
    if signal == "universal_lever":
        return "applies as a standard cost lever for this sector"
    if signal == "no_restriction":
        return "no sector-specific restriction"
    if signal.startswith("category:") and signal.endswith("_present"):
        cid = signal.split(":")[1].replace("_present", "")
        return f"{_category_display_name(cid)} spend is material in the benchmark profile"
    cleaned = signal.replace("_", " ").strip()
    if "keywords detected" in cleaned.lower():
        return cleaned
    return cleaned


def _benchmark_gap_commentary(
    *,
    category_name: str,
    p25_pct: float,
    p50_pct: float,
    band_cr: float,
    source: str,
) -> str:
    parts = [
        "[Benchmark proxy, not your spend] "
        f"{category_name} is modelled at {p50_pct:g}% of revenue "
        f"(sector median P50 applied to the revenue you entered); "
        f"{_fmt_cr(band_cr)} illustrative band if spend moved to P25 best-in-class ({p25_pct:g}%).",
    ]
    if source:
        parts.append(f"Benchmark: {source}.")
    parts.append("Upload actual spend for company-specific gaps.")
    return " ".join(parts)


def _lever_rationale(lv: Dict[str, Any], matched_category_id: str) -> str:
    signals = lv.get("trigger_signals") or []
    phrases = [_humanize_trigger_signal(s) for s in signals[:4] if s != "universal_lever"]
    if not phrases and "universal_lever" in signals:
        phrases = [_humanize_trigger_signal("universal_lever")]

    parts: List[str] = []
    if phrases:
        parts.append("Selected because " + "; ".join(phrases) + ".")
    if lv.get("root_cause_match"):
        parts.append(
            "Supported by root-cause signals on the benchmark proxy spend profile "
            "(not uploaded company spend)."
        )

    complexity = _COMPLEXITY_LABELS.get(str(lv.get("complexity_tier", "medium")), "medium complexity")
    savings_key = str(lv.get("savings_type", "run_rate"))
    savings_label = _SAVINGS_TYPE_LABELS.get(savings_key, savings_key.replace("_", " ").title())
    parts.append(f"{savings_label} · {complexity.capitalize()}.")
    return " ".join(parts)


def _build_lever_value_derivation(
    *,
    base_spend_cr: float,
    matched_category_id: str,
    used_portfolio_proxy: bool,
    p10_pct: float,
    p50_pct: float,
    p90_pct: float,
    p10_cr: float,
    p50_cr: float,
    p90_cr: float,
) -> Dict[str, Any]:
    if matched_category_id and not used_portfolio_proxy:
        pool_label = _category_display_name(matched_category_id)
        pool_source = "category_benchmark_proxy"
        pool_note = (
            f"{pool_label} addressable pool from sector benchmark P50 spend profile "
            "(proxy until actual spend is uploaded)"
        )
    else:
        pool_label = "Portfolio (proxy)"
        pool_source = "portfolio_proxy_10pct"
        pool_note = (
            "No single category pool matched — 10% of total implied OpEx used as addressable proxy"
        )

    pool_fmt = _fmt_cr(base_spend_cr)
    return {
        "base_spend_cr": round(base_spend_cr, 1),
        "base_spend_label": pool_label,
        "base_spend_source": pool_source,
        "base_spend_note": pool_note,
        "savings_rate_p10_pct": round(p10_pct, 1),
        "savings_rate_p50_pct": round(p50_pct, 1),
        "savings_rate_p90_pct": round(p90_pct, 1),
        "calculation_p10": f"Conservative (P10) = {p10_pct:g}% × {pool_fmt} = {_fmt_cr(p10_cr)}",
        "calculation_p50": f"Expected (P50) = {p50_pct:g}% × {pool_fmt} = {_fmt_cr(p50_cr)}",
        "calculation_p90": f"Stretch (P90) = {p90_pct:g}% × {pool_fmt} = {_fmt_cr(p90_cr)}",
    }


def _lever_calculation_note(derivation: Dict[str, Any]) -> str:
    return (
        f"{derivation['calculation_p50']}. "
        f"Pool: {_fmt_cr(derivation['base_spend_cr'])} — {derivation['base_spend_note']}. "
        f"Capture rates from sector lever playbook "
        f"(P10 {derivation['savings_rate_p10_pct']:g}% / "
        f"P50 {derivation['savings_rate_p50_pct']:g}% / "
        f"P90 {derivation['savings_rate_p90_pct']:g}%)."
    )


_VALUE_AT_TABLE_METHODOLOGY: Dict[str, Any] = {
    "summary": (
        "Value at table estimates annual run-rate savings as "
        "sector capture rate × addressable spend pool for each eligible lever."
    ),
    "steps": [
        "Eligible levers are chosen from the sector playbook when spend signals and industry context match.",
        "Each lever applies P10 / P50 / P90 capture rates from the playbook to an addressable spend pool.",
        "Spend pool = benchmark-proxy category spend when a category matches; otherwise 10% of total implied OpEx.",
        "Top 12 levers by expected (P50) value are shown. Row totals are not deduplicated across levers.",
    ],
}

def _build_real_spend_profile(lines: List[Any]) -> Dict[str, Any]:
    """Aggregate NormalizedSpendLine objects into a spend profile for diagnostic use."""
    from collections import defaultdict

    cat_spend: Dict[str, float] = defaultdict(float)
    cat_tx: Dict[str, int] = defaultdict(int)
    cat_vendors: Dict[str, set] = defaultdict(set)
    for line in lines:
        if hasattr(line, "is_actual") and not line.is_actual():
            continue
        cat = (getattr(line, "category", None) or "uncategorized").lower().replace(" ", "_")
        amount = float(getattr(line, "reporting_amount", None) or getattr(line, "amount", 0) or 0)
        cat_spend[cat] += amount
        cat_tx[cat] += 1
        vendor = getattr(line, "vendor", None) or ""
        if vendor:
            cat_vendors[cat].add(vendor)

    category_profile = [
        {
            "category_id": cat_id,
            "category_name": _category_display_name(cat_id),
            "spend": spend,
            "supplier_count": len(cat_vendors.get(cat_id, set())),
            "transaction_count": cat_tx.get(cat_id, 0),
        }
        for cat_id, spend in sorted(cat_spend.items(), key=lambda x: -x[1])
        if spend > 0
    ]
    total = sum(cast(float, c["spend"]) for c in category_profile) or 1.0
    return {"total_spend": total, "category_profile": category_profile, "data_source": "actual_spend"}


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
    context_docs: Optional[List[str]] = None,
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

        structured = _json.dumps({
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

        if context_docs:
            doc_excerpt = "\n\n".join(context_docs)[:3000]
            user_content = f"Company document excerpts:\n{doc_excerpt}\n\n---\nDiagnostic data:\n{structured}"
        else:
            user_content = structured

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
    context_docs: Optional[List[str]] = None,
) -> str:
    """Generate 3-sentence CFO executive summary via Gemini Flash-Lite. Falls back to first key_finding."""
    try:
        import json as _json
        from app.opar.gemini_client import call_gemini

        total_pct = round(total_p50 / annual_revenue_cr * 100, 1) if annual_revenue_cr > 0 else 0
        structured = _json.dumps({
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

        if context_docs:
            doc_excerpt = "\n\n".join(context_docs)[:2000]
            user_content = f"Company document excerpts:\n{doc_excerpt}\n\n---\nDiagnostic data:\n{structured}"
        else:
            user_content = structured

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
    # ── Engagement hydration ────────────────────────────────────────────────
    engagement_docs_text: List[str] = []
    real_profile: Optional[Dict[str, Any]] = None
    if req.engagement_id:
        try:
            from app.services.engagement_corpus import load_engagement_corpus
            eng_lines, engagement_docs_text, _, _ = load_engagement_corpus(req.engagement_id)
            if eng_lines:
                real_profile = _build_real_spend_profile(eng_lines)
        except Exception as _exc:
            logger.warning("diagnostic_engagement_hydration_failed eng=%s err=%s", req.engagement_id, _exc)

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

    bench_industry = benchmark_industry_for(effective_industry)
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
                "category_name": _category_display_name(cat_id),
                "spend": implied_spend,
                "supplier_count": 5,
                "transaction_count": 50,
            })
    total_implied = sum(c["spend"] for c in category_profile) or 1.0
    synthetic_profile = {"total_spend": total_implied, "category_profile": category_profile, "data_source": "benchmark_proxy"}

    # Use real spend profile when engagement data is available; fall back to synthetic.
    active_profile = real_profile if real_profile else synthetic_profile
    profile_basis = "actual_spend" if real_profile else "benchmark_proxy"

    benchmarks = _engine.peer_benchmarker(
        active_profile,
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
        cat_name = row.get("category_name", row.get("category_id", ""))
        benchmark_gaps.append({
            "category": row.get("category_id", ""),
            "category_name": cat_name,
            "p25_pct": round(p25_pct, 2),
            "p50_pct": round(p50_pct, 2),
            "proxy_pct": round(p50_pct, 2),
            "gap_pct": round(p50_pct - p25_pct, 2),
            "gap_cr": band_cr,
            "implied_p50_cr": implied_p50_cr,
            "implied_p25_cr": implied_p25_cr,
            "benchmark_p50_to_p25_band_cr": band_cr,
            "headroom_to_p25_cr": band_cr,
            "percentile_band": "P50 industry benchmark (proxy)",
            "commentary": _benchmark_gap_commentary(
                category_name=str(cat_name),
                p25_pct=p25_pct,
                p50_pct=p50_pct,
                band_cr=band_cr,
                source=str(row.get("source") or ""),
            ),
        })
    benchmark_gaps.sort(key=lambda x: x["implied_p50_cr"], reverse=True)

    # Derive root causes from active profile before lever resolution
    from app.skills.engine.lever_rules import build_signal_corpus as _build_signal_corpus
    root_cause_output = _engine.root_cause_analyzer(
        profile=active_profile,
        peer=benchmarks,
        lines=[],
        headcount=float(req.headcount),
        annual_revenue=revenue_inr,
        industry=effective_industry,
    )
    derived_root_causes = root_cause_output.get("root_causes", [])
    signal_corpus = _build_signal_corpus(active_profile)
    diag_engagement_id = req.engagement_id or f"diag-{req.company_name[:20].strip()}-{int(revenue_inr)}"

    eligible_levers = _engine.resolve_eligible_levers(
        industry=effective_industry,
        spend_profile=active_profile,
        headcount=float(req.headcount),
        annual_revenue=revenue_inr,
        root_causes=derived_root_causes,
        signal_corpus=signal_corpus,
        line_flags={"constraints": company_signals.get("constraints", [])},
        engagement_id=diag_engagement_id,
    )
    active_cat_profile = cast(List[Dict[str, Any]], active_profile.get("category_profile", category_profile))
    cat_spend_cr = {c["category_id"]: c["spend"] / 1_00_00_000 for c in active_cat_profile}
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
        used_portfolio_proxy = primary_cat_spend_cr <= 0
        p10_cr = round(p10_rate * base_spend_cr, 1)
        p50_cr = round(p50_rate * base_spend_cr, 1)
        p90_cr = round(p90_rate * base_spend_cr, 1)
        if p50_cr < 0.1:
            continue
        npv = round(sum(p50_cr / (1.0 + req.wacc) ** t for t in range(1, 4)), 1)
        rng_p10 = float(rng.get("p10", 0))
        rng_p50 = float(rng.get("p50", 0))
        rng_p90 = float(rng.get("p90", 0))
        value_derivation = _build_lever_value_derivation(
            base_spend_cr=base_spend_cr,
            matched_category_id=matched_category_id,
            used_portfolio_proxy=used_portfolio_proxy,
            p10_pct=rng_p10,
            p50_pct=rng_p50,
            p90_pct=rng_p90,
            p10_cr=p10_cr,
            p50_cr=p50_cr,
            p90_cr=p90_cr,
        )
        value_at_table.append({
            "lever_id": lv["lever_id"],
            "lever_name": lv["lever_name"],
            "category": matched_category_id,
            "base_spend_cr": value_derivation["base_spend_cr"],
            "base_spend_label": value_derivation["base_spend_label"],
            "p10_cr": p10_cr,
            "p50_cr": p50_cr,
            "p90_cr": p90_cr,
            "npv": npv,
            "savings_type": lv.get("savings_type", "run_rate"),
            "savings_type_label": _SAVINGS_TYPE_LABELS.get(lv.get("savings_type", "run_rate"), lv.get("savings_type", "run_rate").replace("_", " ").title()),
            "complexity_tier": lv.get("complexity_tier", "medium"),
            "rationale": _lever_rationale(lv, matched_category_id),
            "calculation_note": _lever_calculation_note(value_derivation),
            "value_derivation": value_derivation,
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
    if real_profile:
        data_note = (
            f"Spend profile derived from {len(active_cat_profile)} categories of actual uploaded data. "
            f"Benchmarks compare your real spend against {bench_industry} sector peers."
        )
    elif bench_resolved.get("selected_dataset"):
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
        "profile_basis": profile_basis,
    }
    context_docs = engagement_docs_text if engagement_docs_text else None
    # LLM-1: replace template findings with Gemini Flash-Lite narrative (falls back to templates)
    key_findings = _generate_findings_llm(
        company_name=req.company_name,
        industry=effective_industry,
        annual_revenue_cr=req.annual_revenue_cr,
        benchmark_gaps=benchmark_gaps,
        value_at_table=value_at_table,
        assumptions=assumptions,
        template_fallback=key_findings,
        context_docs=context_docs,
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
        context_docs=context_docs,
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
        "value_at_table_methodology": {
            **_VALUE_AT_TABLE_METHODOLOGY,
            "eligible_levers_total": len(eligible_levers),
            "shown_levers": len(value_at_table),
        },
        "eligible_levers_total": len(eligible_levers),
        "total_p50_value_cr": total_p50,
        "key_findings": key_findings,
        "percentile_legend": _PERCENTILE_LEGEND,
        "profile_basis": profile_basis,
        "engagement_id": req.engagement_id or None,
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
    from app.services.deep_research_prompt import build_default_deep_research_prompt

    query = (req.research_prompt or "").strip() or build_default_deep_research_prompt(
        req.company_name,
        req.industry,
        req.annual_revenue_cr,
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
            if req.research_prompt:
                manifest["deep_research_prompt"] = req.research_prompt.strip()
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
