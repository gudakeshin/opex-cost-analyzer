"""Reflect focus routing — category matching, QA lookup, recommendations."""
from __future__ import annotations

from typing import Any, Dict, List

from app.opar.category_resolver import match_category_from_query, tokenize
from app.opar.models import ObserveContext
from app.opar.qa_lookup import is_interactive_savings_query
from app.opar.reflect_currency import format_currency

def match_focus_category(ctx: ObserveContext, validated: Dict[str, Dict[str, Any]]) -> Dict[str, Any] | None:
    """Best-effort category matcher for focused optimization responses."""
    matrix = validated.get("value-bridge-calculator", {}).get("value_matrix", [])
    if not isinstance(matrix, list) or not matrix:
        return None
    query_tokens = set(tokenize(ctx.user_message))
    if not query_tokens:
        return None
    return match_category_from_query(ctx.user_message, matrix)


def build_focus_category_section(ctx: ObserveContext, validated: Dict[str, Dict[str, Any]]) -> str:
    row = match_focus_category(ctx, validated)
    if not row:
        return ""
    cat = row.get("category_name") or row.get("category_id") or "Selected category"
    cid = str(row.get("category_id") or "")
    mid = float(row.get("deduped_mid_savings", 0.0))
    npv = float(row.get("net_npv", 0.0))
    payback = int(row.get("payback_months", 0) or 0)
    confidence = str(row.get("confidence") or "medium")
    lever = str(row.get("lever") or "optimization")
    lever_label = business_lever_label(lever)
    root = str(row.get("root_cause") or "benchmark gap above norm")

    addressable = total_cat = 0.0
    supplier_count = 0
    top_suppliers: List[Dict[str, Any]] = []
    top_geos: List[Dict[str, Any]] = []
    express_like_pct = 0.0
    for c in validated.get("spend-profiler", {}).get("category_profile", []):
        if str(c.get("category_id")) == cid:
            addressable = float(c.get("addressable_spend", 0.0) or 0.0)
            total_cat = float(c.get("spend", 0.0) or 0.0)
            supplier_count = int(c.get("supplier_count", 0) or 0)
            top_suppliers = c.get("top_suppliers", []) if isinstance(c.get("top_suppliers"), list) else []
            top_geos = c.get("top_geos", []) if isinstance(c.get("top_geos"), list) else []
            express_like_pct = float(c.get("express_like_pct", 0.0) or 0.0)
            break

    quick_wins: List[str] = []
    if total_cat > 0:
        quick_wins.append(
            f"{cat} is {format_currency(total_cat)} with {format_currency(addressable)} modeled as addressable spend."
        )
    if len(top_suppliers) >= 2:
        fast = min(
            [s for s in top_suppliers if isinstance(s.get("avg_payment_terms_days"), (int, float))],
            key=lambda x: float(x.get("avg_payment_terms_days", 999)),
            default=None,
        )
        slow = max(
            [s for s in top_suppliers if isinstance(s.get("avg_payment_terms_days"), (int, float))],
            key=lambda x: float(x.get("avg_payment_terms_days", 0)),
            default=None,
        )
        if fast and slow:
            gap = float(slow.get("avg_payment_terms_days", 0)) - float(fast.get("avg_payment_terms_days", 0))
            if gap >= 8:
                fast_spend = float(fast.get("spend", 0.0) or 0.0)
                wc_release = fast_spend * (gap / 365.0)
                quick_wins.append(
                    f"Payment terms gap detected: {fast.get('supplier')} at Net {int(round(float(fast.get('avg_payment_terms_days', 0))))} "
                    f"vs {slow.get('supplier')} at Net {int(round(float(slow.get('avg_payment_terms_days', 0))))}. "
                    f"Moving {fast.get('supplier')} to matched terms can release about {format_currency(wc_release)} in working capital."
                )
    if supplier_count >= 3 and top_suppliers:
        top2_share = sum(float(s.get("share_of_category", 0.0) or 0.0) for s in top_suppliers[:2])
        quick_wins.append(
            f"Supplier base is fragmented ({supplier_count} suppliers). Consolidating volume to 1-2 strategic carriers "
            f"can improve rate cards and service governance (current top-2 share {top2_share:.0%})."
        )
    if express_like_pct >= 0.15:
        quick_wins.append(
            f"About {express_like_pct:.0%} of spend appears express/priority-like; a lane-level mode audit can shift eligible volume to lower-cost modes."
        )
    if len(top_geos) >= 2:
        geo_names = ", ".join(str(g.get("geo")) for g in top_geos[:3])
        quick_wins.append(
            f"Spend is split across geographies ({geo_names}); harmonizing contracts and Incoterms by lane can reduce leakage."
        )

    payment_terms = validated.get("payment-terms-optimizer", {})
    if isinstance(payment_terms, dict):
        for opp in payment_terms.get("opportunities", []):
            if str(opp.get("category_id")) == cid:
                dpo_days = float(opp.get("dpo_improvement_days", 0.0) or 0.0)
                wc = float(opp.get("working_capital_release", 0.0) or 0.0)
                if dpo_days > 0 and wc > 0:
                    quick_wins.append(
                        f"Terms optimization potential: +{dpo_days:.0f} DPO days with {format_currency(wc)} one-time working-capital release."
                    )
                break

    root_causes: list = []
    for rc in validated.get("root-cause-analyzer", {}).get("root_cause_findings", []):
        if str(rc.get("category_id")) == cid:
            root_causes = rc.get("root_causes", []) if isinstance(rc.get("root_causes"), list) else []
            break
    lever_framework: List[str] = []
    for cause in root_causes[:3]:
        lever_code = str(cause.get("recommended_lever") or lever)
        lever_framework.append(
            f"{business_lever_label(lever_code).capitalize()}: {cause.get('implementation_approach', 'Apply targeted policy and process interventions.')}"
        )
    if not lever_framework:
        lever_framework.append(
            f"{lever_label.capitalize()}: reset commercial terms, tighten demand controls, and embed monthly performance governance."
        )

    lines = [f"**Focused optimization: {cat}**"]
    if ctx.intent_class == "business_case":
        lines.append(
            f"Modeled impact: mid-case {format_currency(mid)}, NPV {format_currency(npv)}, "
            f"payback {payback if payback > 0 else 'not established'} months, confidence {confidence}."
        )
    else:
        lines.append(
            f"Modeled value-release potential: mid-case {format_currency(mid)} with confidence {confidence}. "
            "Business-case economics (NPV/payback) can be generated on request."
        )
    lines.append("")
    lines.append("**From your data: quick wins**")
    for q in quick_wins[:5]:
        lines.append(f"- {q}")
    lines.append("")
    lines.append("**Business lever framework**")
    for lf in lever_framework:
        lines.append(f"- {lf}")
    lines.append(f"- Primary modeled bottleneck: {root}.")
    return "\n".join(lines)

def is_category_focused_request(ctx: ObserveContext | None, validated: Dict[str, Dict[str, Any]]) -> bool:
    if not ctx:
        return False
    if bool((ctx.explicit_category or "").strip()):
        return True
    return match_focus_category(ctx, validated) is not None


# Deep-analysis skills whose presence means a general_qa turn warranted the full
# advisory narrative rather than a deterministic QA lookup.
_QA_LOOKUP_DEEP_SKILLS = frozenset({
    "peer-benchmarker",
    "internal-benchmarker",
    "root-cause-analyzer",
    "savings-modeler",
    "value-bridge-calculator",
    "analysis-synthesizer",
    "executive-communication",
})


def is_qa_lookup(
    ctx: ObserveContext | None,
    validated: Dict[str, Dict[str, Any]],
    composition_validated: Dict[str, Dict[str, Any]] | None = None,
) -> bool:
    """True when a general_qa turn ran only the profiler/doc-contextualizer and
    should be answered with the deterministic QA lookup instead of the value-bridge
    template. Mirrors the condition the orchestrator used to apply post-hoc, now
    owned by reflect so there is a single response-composition path."""
    if not ctx or getattr(ctx, "intent_class", "") != "general_qa":
        return False
    if is_interactive_savings_query(ctx.user_message, getattr(ctx, "query_capabilities", None)):
        return False
    if not ("spend-profiler" in validated or "document-contextualizer" in validated):
        return False
    if any(skill in validated for skill in _QA_LOOKUP_DEEP_SKILLS):
        return False
    # Preserve chart-builder formatting when the user explicitly asked to visualize spend.
    if getattr(ctx, "wants_spend_visualization", False) and "chart-builder" in validated:
        return False
    return True

def business_lever_label(lever: str) -> str:
    mapping = {
        "internal_best_practice": "process standardization and operating model redesign",
        "process_standardization": "process standardization and operating model redesign",
        "supplier_consolidation": "supplier consolidation and lane/package rebundling",
        "contract_renegotiation": "commercial renegotiation with should-cost and volume commitments",
        "maverick_compliance": "guided buying and policy compliance enforcement",
        "demand_management": "demand challenge and specification-to-need control",
        "automation": "workflow automation and touchless processing",
        "payment_terms": "payment-term harmonization and DPO optimization",
        "insourcing": "insource where structural unit economics are favorable",
        "outsourcing": "outsource to scale providers for lower delivered unit cost",
    }
    if not lever:
        return "targeted procurement optimization"
    return mapping.get(lever, lever.replace("_", " "))


def executive_callouts(validated: Dict[str, Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    bva = validated.get("bva-analyzer", {})
    if isinstance(bva, dict) and bva.get("bva_available"):
        variances = bva.get("variances", [])
        over = next((v for v in variances if v.get("flag") == "over_budget"), None)
        if over:
            pct = over.get("variance_pct")
            pct_txt = f"{pct:.1f}%" if isinstance(pct, (int, float)) else "materially"
            out.append(
                f"{over.get('category_name', over.get('category_id', 'A major category'))} is {pct_txt} over budget "
                f"({format_currency(over.get('actual_spend', 0))} actual vs {format_currency(over.get('budget_spend', 0))} budget)."
            )

    internal = validated.get("internal-benchmarker", {})
    if isinstance(internal, dict):
        totals: Dict[str, float] = {}
        for row in internal.get("internal_variance", []):
            for seg in row.get("segments", []):
                name = str(seg.get("segment") or "Unknown segment")
                totals[name] = totals.get(name, 0.0) + float(seg.get("spend", 0.0))
        if totals:
            seg, amt = max(totals.items(), key=lambda x: x[1])
            out.append(f"{seg} is currently the largest internal spend footprint at {format_currency(amt)}.")
    return out[:2]


def recommendation_rows(validated: Dict[str, Dict[str, Any]], max_items: int = 3) -> List[Dict[str, Any]]:
    bridge = validated.get("value-bridge-calculator", {})
    matrix = bridge.get("value_matrix", [])
    if not matrix:
        return []

    peer_rows = {
        r.get("category_id"): r
        for r in validated.get("peer-benchmarker", {}).get("comparisons", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    internal_rows = {
        r.get("category_id"): r
        for r in validated.get("internal-benchmarker", {}).get("internal_variance", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    heuristic_rows = {
        r.get("category_id"): r
        for r in validated.get("heuristic-analyzer", {}).get("heuristic_findings", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    root_rows = {
        r.get("category_id"): r
        for r in validated.get("root-cause-analyzer", {}).get("root_cause_findings", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    modeled_rows = {
        r.get("category_id"): r
        for r in validated.get("savings-modeler", {}).get("initiatives", [])
        if isinstance(r, dict) and r.get("category_id")
    }
    constraints = validated.get("document-contextualizer", {}).get("constraints", [])
    top_constraint = constraints[0] if constraints else ""

    def _rank_key(item: Dict[str, Any]) -> tuple[float, float]:
        lever = str(item.get("lever") or "")
        penalty = 0.6 if lever == "internal_best_practice" else 1.0
        return (
            float(item.get("deduped_mid_savings", 0.0)) * penalty,
            float(item.get("deduped_mid_savings", 0.0)),
        )

    ranked = sorted(matrix, key=_rank_key, reverse=True)[:max_items]
    out: List[Dict[str, Any]] = []
    for item in ranked:
        cid = item.get("category_id")
        category = item.get("category_name") or cid or "Unknown category"
        lever = item.get("lever") or "optimization"
        lever_label = business_lever_label(lever)
        dedup_mid = float(item.get("deduped_mid_savings", 0.0))
        npv = float(item.get("net_npv", 0.0))
        payback = int(item.get("payback_months", 0) or 0)
        confidence = item.get("confidence") or "medium"

        evidence: List[str] = []
        peer = peer_rows.get(cid, {})
        if peer:
            actual = float(peer.get("actual_pct_of_revenue", 0.0))
            p50 = float(peer.get("benchmark_p50_pct", 0.0))
            gap = max(actual - p50, 0.0)
            evidence.append(
                f"Peer gap: actual {actual:.2f}% of revenue vs P50 {p50:.2f}% (gap {gap:.2f} pts, band {peer.get('percentile_band', 'n/a')})."
            )

        internal = internal_rows.get(cid, {})
        if internal:
            spread = float(internal.get("internal_spread", 0.0)) * 100
            segments = internal.get("segments", []) if isinstance(internal.get("segments"), list) else []
            if segments:
                sorted_segments = sorted(
                    [s for s in segments if isinstance(s, dict)],
                    key=lambda x: float(x.get("spend", 0.0) or 0.0),
                    reverse=True,
                )
                best = sorted_segments[-1] if sorted_segments else {}
                worst = sorted_segments[0] if sorted_segments else {}
                evidence.append(
                    "Internal variance: "
                    f"{spread:.1f}% spread; highest spend segment "
                    f"{worst.get('segment', 'Unknown')} at {format_currency(worst.get('spend', 0.0))} "
                    f"vs lowest spend segment {best.get('segment', 'Unknown')} at {format_currency(best.get('spend', 0.0))}."
                )
            else:
                evidence.append(f"Internal variance: {spread:.1f}% spread between best and worst performing segments.")

        heur = heuristic_rows.get(cid, {})
        if heur:
            actual_h = float(heur.get("actual_pct_of_revenue", 0.0))
            target_h = float(heur.get("heuristic_target_pct", 0.0))
            gap_h = max(actual_h - target_h, 0.0)
            evidence.append(f"Heuristic gap: {actual_h:.2f}% vs target {target_h:.2f}% (gap {gap_h:.2f} pts).")

        root = root_rows.get(cid, {})
        if root.get("root_causes"):
            top_cause = root.get("root_causes", [{}])[0]
            diagnosis = top_cause.get("diagnosis", "No diagnosis available")
            addr = float(top_cause.get("addressable_spend", 0.0))
            evidence.append(f"Root-cause signal: {diagnosis}. Addressable spend estimate {format_currency(addr)}.")

        modeled = modeled_rows.get(cid, {})
        if modeled:
            gross_3yr = float(modeled.get("gross_savings", {}).get("total_3yr", 0.0))
            cta_3yr = float(modeled.get("cost_to_achieve", {}).get("total_3yr", 0.0))
            evidence.append(
                f"Modeled economics: gross 3Y {format_currency(gross_3yr)}, cost-to-achieve {format_currency(cta_3yr)}."
            )

        if top_constraint:
            evidence.append(f"Execution constraint from documents: {top_constraint}.")

        out.append(
            {
                "category": category,
                "lever": lever,
                "lever_label": lever_label,
                "dedup_mid": dedup_mid,
                "npv": npv,
                "payback_months": payback,
                "confidence": confidence,
                "evidence": evidence[:4],
            }
        )
    return out
