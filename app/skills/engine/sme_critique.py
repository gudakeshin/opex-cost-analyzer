"""SME Critique Analyzer — Deloitte-style evidence qualification for savings initiatives.

Deterministic rules engine: no LLM call. Evaluates each savings initiative against
data signals to score evidence maturity and generate targeted probe questions that
a senior consultant would ask before building a value case.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.skills.engine.evidence import (
    data_to_request_for_signal,
    normalize_lever_id,
    requirements_for_initiative,
    resolve_structured_indexes,
)


# ---------------------------------------------------------------------------
# Evidence maturity scoring
# Each present signal adds 1 point. Thresholds: 0-1=hypothesis, 2=indicative,
# 3=supported, 4=validated.
# ---------------------------------------------------------------------------

def _score_evidence_maturity(
    initiative: Dict[str, Any],
    contracts_by_category: Dict[str, List[Dict[str, Any]]],
    supplier_counts: Dict[str, int],
    root_cause_signals_by_category: Dict[str, int],
) -> tuple[str, int]:
    category_id = str(initiative.get("category_id") or "").lower()
    score = 0

    # Signal 1: contract expiry data for this category
    if contracts_by_category.get(category_id):
        score += 1

    # Signal 2: supplier-level granularity (>1 distinct supplier recorded)
    if supplier_counts.get(category_id, 0) > 1:
        score += 1

    # Signal 3: root-cause has ≥2 diagnostic signals (not just benchmark gap)
    if root_cause_signals_by_category.get(category_id, 0) >= 2:
        score += 1

    # Signal 4: savings-modeler assigned high confidence
    if initiative.get("confidence") == "high":
        score += 1

    if score >= 4:
        return "validated", score
    if score == 3:
        return "supported", score
    if score == 2:
        return "indicative", score
    return "hypothesis", score


# Session-wide evidence gaps → one portfolio question per family (not per category).
PORTFOLIO_PROBE_FAMILIES = frozenset({
    "transaction_volume",
    "po_coverage",
    "cost_centre_split",
    "spend_trend",
    "specification_data",
})

# Portfolio wording when the same family applies across multiple categories.
FAMILY_PORTFOLIO_QUESTIONS: Dict[str, str] = {
    "transaction_volume": (
        "What is the current invoice-approval cycle time and how many invoices per month "
        "are processed across AP?"
    ),
    "po_coverage": (
        "What percentage of spend currently flows through approved POs vs direct or card purchases?"
    ),
    "cost_centre_split": (
        "For discretionary spend categories, is spend operationally linked to headcount, revenue, "
        "or production volume — or largely discretionary?"
    ),
    "spend_trend": (
        "Has indirect spend grown faster than revenue over the last 2 years, or roughly in line?"
    ),
    "specification_data": (
        "Are specifications standardized across business units, or does each BU buy to its own spec?"
    ),
    "contract_terms": (
        "When do the top vendor contracts expire across priority categories — "
        "are they up for renewal within the planning horizon?"
    ),
    "supplier_fragmentation": (
        "How fragmented is the supplier base in priority categories — "
        "many vendors (10+) or already concentrated?"
    ),
    "benchmark_specificity": (
        "Do you have closer peer comparables (same geography, revenue band, operating model) "
        "than the broad industry benchmarks used in this model?"
    ),
}


def _make_probe(
    *,
    probe_family_id: str,
    question: str,
    why_critical: str,
    saving_at_stake: float,
    data_to_request: str,
    category: str,
    scope: str | None = None,
) -> Dict[str, Any]:
    resolved_scope = scope or (
        "portfolio" if probe_family_id in PORTFOLIO_PROBE_FAMILIES else "category"
    )
    if resolved_scope == "portfolio" and probe_family_id in FAMILY_PORTFOLIO_QUESTIONS:
        question = FAMILY_PORTFOLIO_QUESTIONS[probe_family_id]
    return {
        "probe_family_id": probe_family_id,
        "scope": resolved_scope,
        "question": question,
        "why_critical": why_critical,
        "saving_at_stake": round(saving_at_stake),
        "data_to_request": data_to_request,
        "affected_categories": [category],
    }


# ---------------------------------------------------------------------------
# Probe question registry — keyed by lever slug
# Each entry is a list of probe specs. A probe fires when its `triggered_by`
# condition is True.
# ---------------------------------------------------------------------------

def _build_probe_questions(
    initiative: Dict[str, Any],
    has_contract_data: bool,
    has_supplier_data: bool,
    benchmark_specificity: float,
    has_cost_center_split: bool,
    has_prior_year_data: bool,
    has_po_coverage: bool,
    has_transaction_volume: bool,
    has_spec_data: bool,
) -> List[Dict[str, Any]]:
    lever = normalize_lever_id(str(initiative.get("lever") or initiative.get("lever_id") or ""))
    category = str(initiative.get("category_name") or initiative.get("category_id") or "this category")
    saving = float(initiative.get("annualized_run_rate_savings") or 0)
    saving_3yr = float(
        (initiative.get("net_savings") or {}).get("total_3yr")
        or initiative.get("annualized_run_rate_savings")
        or 0
    )
    probes: List[Dict[str, Any]] = []

    if lever in ("supplier_consolidation", "renegotiation"):
        if not has_contract_data:
            probes.append(_make_probe(
                probe_family_id="contract_terms",
                question=f"When do the top vendor contracts for {category} expire — are they up for renewal within the planning horizon?",
                why_critical=(
                    "If contracts run beyond 18 months, this saving is a future-period item at best. "
                    "Without expiry dates we cannot confirm near-term addressability."
                ),
                saving_at_stake=saving_3yr * 0.80,
                data_to_request="Contract register with vendor name, category, expiry date, and auto-renewal clause",
                category=category,
            ))
        if not has_supplier_data:
            probes.append(_make_probe(
                probe_family_id="supplier_fragmentation",
                question=f"How many active vendors currently serve {category}? Is the base fragmented (10+ vendors) or already concentrated?",
                why_critical=(
                    "Consolidation from 20→5 vendors is an 18-month programme with significant sourcing effort. "
                    "Consolidation from 3→2 vendors releases minimal saving. "
                    "The starting supplier count determines both saving size and execution timeline."
                ),
                saving_at_stake=saving_3yr * 0.60,
                data_to_request="Vendor master for this category with annual spend per vendor",
                category=category,
            ))

    if lever == "strategic_sourcing":
        if not has_contract_data:
            probes.append(_make_probe(
                probe_family_id="contract_terms",
                question=f"When were {category} contracts last put to competitive tender — and were international / new-entrant suppliers included?",
                why_critical=(
                    "Suppliers calibrate pricing to when you last tested the market. "
                    "If last tender was >3 years ago, the benchmark gap is likely real and recoverable. "
                    "If recently tendered, the peer gap may reflect genuine market position, not procurement failure."
                ),
                saving_at_stake=saving_3yr * 0.70,
                data_to_request="Last tender date, shortlist size, and whether a should-cost model was used",
                category=category,
            ))
        if benchmark_specificity < 0.60:
            probes.append(_make_probe(
                probe_family_id="benchmark_specificity",
                question=f"The peer benchmark for {category} is drawn from a broad industry cut. Do you have a closer comparable — same geography, revenue band, and operating model?",
                why_critical=(
                    "A low-specificity benchmark (broad sector, mixed geographies) can overstate the gap by 30–50%. "
                    "If the comparables are mostly MNCs vs your profile as a domestic mid-cap, "
                    "the achievable saving could be half the modelled figure."
                ),
                saving_at_stake=saving_3yr * 0.40,
                data_to_request="Industry-specific benchmark from a sourced advisory database or prior engagement data",
                category=category,
            ))

    if lever == "demand_management":
        if not has_cost_center_split:
            probes.append(_make_probe(
                probe_family_id="cost_centre_split",
                question=f"Is {category} spend discretionary (can be cut without revenue impact) or operationally linked to headcount / revenue / production volume?",
                why_critical=(
                    "Demand management levers address discretionary spend only. "
                    "If most of this category is operationally driven, the addressable fraction drops from ~40% to ~15%. "
                    "Getting this wrong inflates the saving headline significantly."
                ),
                saving_at_stake=saving_3yr * 0.50,
                data_to_request="Cost-centre breakdown and approval flow — which BUs control this spend and what drives purchase decisions",
                category=category,
            ))
        if not has_prior_year_data:
            probes.append(_make_probe(
                probe_family_id="spend_trend",
                question=f"Has {category} spend grown faster than revenue over the last 2 years, or roughly in line?",
                why_critical=(
                    "If spend has tracked revenue closely, you are likely buying what the business needs. "
                    "If spend has outpaced revenue, there is true demand-side slack — this probe determines whether "
                    "demand management is the right lever or whether structural cost is the issue."
                ),
                saving_at_stake=saving_3yr * 0.30,
                data_to_request="2-year spend trend by category alongside revenue for the same periods",
                category=category,
            ))

    if lever == "maverick_buying_reduction":
        if not has_po_coverage:
            probes.append(_make_probe(
                probe_family_id="po_coverage",
                question=f"What percentage of {category} spend currently flows through approved POs vs direct / card purchases?",
                why_critical=(
                    "Maverick buying savings require PO compliance enforcement, which needs system configuration "
                    "and change management. If PO coverage is already >85%, the lever's upside is limited. "
                    "If <60%, the saving is real but the execution path is process-heavy."
                ),
                saving_at_stake=saving_3yr * 0.60,
                data_to_request="PO coverage rate by category from your ERP (AP module)",
                category=category,
            ))

    if lever == "process_automation":
        if not has_transaction_volume:
            probes.append(_make_probe(
                probe_family_id="transaction_volume",
                question=f"What is the current invoice-approval cycle time for {category}, and how many invoices per month are processed?",
                why_critical=(
                    "Automation ROI scales with transaction volume and cycle time. "
                    "At <200 invoices/month, automation rarely pays back in Year 1. "
                    "Without this data the saving is speculative."
                ),
                saving_at_stake=saving * 0.40,
                data_to_request="AP transaction log with invoice count and average days-to-pay for this category",
                category=category,
            ))

    if lever == "specification_optimization":
        if not has_spec_data:
            probes.append(_make_probe(
                probe_family_id="specification_data",
                question=f"Are {category} specifications standardized across business units, or does each BU buy to its own spec?",
                why_critical=(
                    "Specification harmonization requires engineering / operations sign-off and can take 6–12 months. "
                    "If specs are already standardized, this lever is moot. "
                    "If fragmented, the saving is real but the execution path is longer than the model assumes."
                ),
                saving_at_stake=saving_3yr * 0.70,
                data_to_request="SKU or specification master per BU for this category",
                category=category,
            ))

    # Generic fallback if no lever-specific probes fired but maturity is hypothesis/indicative
    if not probes and not has_supplier_data:
        probes.append(_make_probe(
            probe_family_id="supplier_fragmentation",
            question=f"Can you share the vendor master for {category} — supplier names, annual spend per supplier, and any known contract details?",
            why_critical=(
                "The current saving is modelled from benchmark gap alone, with no supplier-level evidence. "
                "A vendor master gives us the data needed to stress-test the assumption "
                "and move from hypothesis to an evidenced business case."
            ),
            saving_at_stake=saving_3yr * 0.50,
            data_to_request="Vendor master extract for this category",
            category=category,
        ))

    return probes[:3]  # cap at 3 probes per initiative


def _inventory_for_initiative(
    evidence_gatherer_output: Dict[str, Any],
    category_id: str,
    lever: str,
) -> Dict[str, Any] | None:
    for item in evidence_gatherer_output.get("evidence_inventory", []) or []:
        if not isinstance(item, dict):
            continue
        if (
            str(item.get("category_id") or "").lower() == category_id
            and str(item.get("lever") or "") == lever
        ):
            return item
    return None


def _has_signal(inv: Dict[str, Any] | None, signal_type: str) -> bool:
    if not inv:
        return False
    sig = (inv.get("signals") or {}).get(signal_type) or {}
    return sig.get("status") == "found"


def _build_evidence_message(
    inv: Dict[str, Any] | None,
    initiative: Dict[str, Any],
    gaps: List[str],
    searched_docs: int,
) -> str:
    if not inv:
        return ""
    signals = inv.get("signals") or {}
    used: List[str] = []
    for sig_type, sig in signals.items():
        if isinstance(sig, dict) and sig.get("status") in ("found", "partial"):
            prov = sig.get("provenance") or []
            prov_str = ", ".join(str(p) for p in prov[:2]) if prov else sig.get("source", "")
            used.append(f"{sig_type.replace('_', ' ')} ({sig.get('summary', '')}; {prov_str})".strip())

    if not gaps:
        return ""
    reqs = requirements_for_initiative(initiative)
    gap_labels = [
        data_to_request_for_signal(g, reqs) for g in gaps
    ]
    if used:
        return (
            f"Used: {' · '.join(used[:2])}. "
            f"Searched {searched_docs} document(s) — still need: {'; '.join(gap_labels[:2])}"
        )
    if searched_docs > 0:
        return (
            f"Searched {searched_docs} document(s) — no supporting evidence found. "
            f"Upload: {'; '.join(gap_labels[:2])}"
        )
    return (
        "Benchmark gap only — upload spend ledger and/or contract register. "
        f"Need: {'; '.join(gap_labels[:2])}"
    )


def _evidence_sources_from_inventory(inv: Dict[str, Any] | None) -> Dict[str, str]:
    if not inv:
        return {}
    out: Dict[str, str] = {}
    for sig_type, sig in (inv.get("signals") or {}).items():
        if isinstance(sig, dict) and sig.get("status") in ("found", "partial"):
            out[sig_type] = str(sig.get("source") or "unknown")
    return out


# ---------------------------------------------------------------------------
# Double-count detection
# ---------------------------------------------------------------------------

def _check_double_count(
    initiative: Dict[str, Any],
    all_initiatives: List[Dict[str, Any]],
) -> str | None:
    cat = str(initiative.get("category_id") or "")
    lever = str(initiative.get("lever") or "")
    overlapping = [
        i for i in all_initiatives
        if isinstance(i, dict)
        and str(i.get("category_id") or "") == cat
        and str(i.get("lever") or "") != lever
    ]
    if not overlapping:
        return None
    other_levers = [str(i.get("lever_name") or i.get("lever") or "unknown lever") for i in overlapping]
    return (
        f"Both {initiative.get('lever_name') or lever} and "
        f"{', '.join(other_levers)} claim savings from {initiative.get('category_name') or cat}. "
        "Confirm whether these are additive or competing — double-counting is common when "
        "demand management and supplier consolidation target the same category simultaneously."
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def sme_critique_analyzer(
    savings_model: Dict[str, Any],
    spend_profile: Dict[str, Any],
    benchmarks: Dict[str, Any],
    root_causes: Dict[str, Any],
    contract_lifecycle: Dict[str, Any],
    evidence_gatherer_output: Optional[Dict[str, Any]] = None,
    lines: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Evaluate each savings initiative for evidence maturity and generate probe questions.

    Pure rules engine — no LLM call. Output is stored as skill_outputs['sme-critique']
    and consumed by reflect.py to shape next_options and advisory_sections.
    """
    initiatives: List[Dict[str, Any]] = savings_model.get("initiatives", [])
    if not initiatives:
        return {
            "critique_summary": {
                "total_initiatives": 0,
                "ready_count": 0,
                "probe_count": 0,
                "insufficient_count": 0,
                "savings_ready": 0,
                "savings_probe": 0,
                "savings_insufficient": 0,
            },
            "initiative_critiques": [],
            "top_probes": [],
            "portfolio_probes": [],
        }

    # --- Index structured evidence (spend + contract lifecycle) ---
    from app.models import NormalizedSpendLine

    norm_lines: List[NormalizedSpendLine] = []
    if lines:
        for ln in lines:
            if isinstance(ln, NormalizedSpendLine):
                norm_lines.append(ln)
            elif isinstance(ln, dict):
                try:
                    norm_lines.append(NormalizedSpendLine.model_validate(ln))
                except Exception:
                    pass

    contracts_by_category, supplier_counts, root_cause_signals_by_category = resolve_structured_indexes(
        evidence_gatherer_output,
        norm_lines,
        spend_profile,
        root_causes,
        contract_lifecycle,
    )

    corpus_summary = (evidence_gatherer_output or {}).get("corpus_summary") or {}
    searched_docs = int(corpus_summary.get("searched_documents") or 0)

    # --- Benchmark specificity by category ---
    benchmark_specificity_by_category: Dict[str, float] = {}
    for comp in benchmarks.get("comparisons", []):
        if isinstance(comp, dict):
            cat_id = str(comp.get("category_id") or "").lower()
            spec = float(comp.get("specificity_score") or comp.get("dataset_specificity") or 0.5)
            benchmark_specificity_by_category[cat_id] = spec

    # --- Assess spend profile for presence of cost-centre and trend data ---
    has_cost_center_split = any(
        isinstance(e, dict) and e.get("cost_center_breakdown")
        for e in spend_profile.get("category_profile", [])
    )
    has_prior_year_data = bool(spend_profile.get("trend_analysis"))
    has_po_coverage = any(
        isinstance(e, dict) and e.get("po_coverage_rate") is not None
        for e in spend_profile.get("category_profile", [])
    )
    has_transaction_volume = any(
        isinstance(e, dict) and e.get("transaction_count") is not None
        for e in spend_profile.get("category_profile", [])
    )
    has_spec_data = bool(spend_profile.get("specification_data"))

    # --- Evaluate each initiative ---
    initiative_critiques: List[Dict[str, Any]] = []
    ready_count = probe_count = insufficient_count = 0
    savings_ready = savings_probe = savings_insufficient = 0.0

    for initiative in initiatives:
        if not isinstance(initiative, dict):
            continue
        category_id = str(initiative.get("category_id") or "").lower()
        lever = str(initiative.get("lever") or initiative.get("lever_id") or "")
        saving_3yr = float(
            (initiative.get("net_savings") or {}).get("total_3yr")
            or initiative.get("annualized_run_rate_savings")
            or 0
        )

        inv = _inventory_for_initiative(evidence_gatherer_output or {}, category_id, lever)

        maturity, maturity_score = _score_evidence_maturity(
            initiative,
            contracts_by_category,
            supplier_counts,
            root_cause_signals_by_category,
        )
        # Boost maturity when evidence gatherer found document-backed signals
        if inv:
            found_count = sum(
                1 for s in (inv.get("signals") or {}).values()
                if isinstance(s, dict) and s.get("status") == "found"
            )
            if found_count >= 2 and maturity == "hypothesis":
                maturity, maturity_score = "indicative", min(maturity_score + 1, 4)
            elif found_count >= 3 and maturity == "indicative":
                maturity, maturity_score = "supported", min(maturity_score + 1, 4)

        has_contract = (
            _has_signal(inv, "contract_terms")
            or bool(contracts_by_category.get(category_id))
        )
        has_supplier = (
            _has_signal(inv, "supplier_fragmentation")
            or supplier_counts.get(category_id, 0) > 1
        )
        has_structural = (
            _has_signal(inv, "structural_drivers")
            or root_cause_signals_by_category.get(category_id, 0) >= 2
        )
        specificity = benchmark_specificity_by_category.get(category_id, 0.5)

        probes = _build_probe_questions(
            initiative,
            has_contract_data=has_contract,
            has_supplier_data=has_supplier,
            benchmark_specificity=specificity,
            has_cost_center_split=has_cost_center_split or _has_signal(inv, "cost_centre_split"),
            has_prior_year_data=has_prior_year_data or _has_signal(inv, "spend_trend"),
            has_po_coverage=has_po_coverage or _has_signal(inv, "po_coverage"),
            has_transaction_volume=has_transaction_volume or _has_signal(inv, "transaction_volume"),
            has_spec_data=has_spec_data or _has_signal(inv, "specification_data"),
        )

        double_count_risk = _check_double_count(initiative, initiatives)
        gaps: List[str] = list(inv.get("gaps") or []) if inv else []
        evidence_sources = _evidence_sources_from_inventory(inv)
        found_or_partial = sum(
            1 for s in (inv.get("signals") or {}).values()
            if isinstance(s, dict) and s.get("status") in ("found", "partial")
        ) if inv else (int(has_contract) + int(has_supplier) + int(has_structural))

        # Determine verdict — evidence-aware
        all_required_found = inv and not gaps and found_or_partial > 0
        if (maturity in ("supported", "validated") and not probes) or all_required_found:
            sme_verdict = "proceed"
        elif found_or_partial == 0:
            sme_verdict = "insufficient_data"
        else:
            sme_verdict = "probe_first"

        # Derive critical risk narrative
        if sme_verdict == "insufficient_data":
            critical_risk = _build_evidence_message(
                inv, initiative, gaps or ["supplier_fragmentation", "contract_terms"],
                searched_docs or int(inv.get("searched_documents") or 0) if inv else searched_docs,
            )
            if not critical_risk:
                critical_risk = (
                    f"Saving is modelled from benchmark gap alone for "
                    f"{initiative.get('category_name') or category_id}. "
                    "Upload spend ledger and/or contract documents."
                )
        elif sme_verdict == "probe_first":
            gap_msg = _build_evidence_message(
                inv, initiative, gaps,
                searched_docs or int(inv.get("searched_documents") or 0) if inv else searched_docs,
            )
            critical_risk = gap_msg or (probes[0]["why_critical"] if probes else "")
        else:
            critical_risk = ""

        # Bucket
        if sme_verdict == "proceed":
            ready_count += 1
            savings_ready += saving_3yr
        elif sme_verdict == "probe_first":
            probe_count += 1
            savings_probe += saving_3yr
        else:
            insufficient_count += 1
            savings_insufficient += saving_3yr

        critique_id = (
            f"{category_id}_{initiative.get('lever') or initiative.get('lever_id') or 'unknown'}"
        )
        initiative_critiques.append({
            "initiative_id": critique_id,
            "category_id": category_id,
            "category_name": initiative.get("category_name") or category_id,
            "lever": lever,
            "lever_name": initiative.get("lever_name") or "",
            "modelled_saving_3yr": saving_3yr,
            "evidence_maturity": maturity,
            "maturity_score": maturity_score,
            "sme_verdict": sme_verdict,
            "critical_risk": critical_risk,
            "probe_questions": probes,
            "double_count_risk": double_count_risk,
            "evidence_sources": evidence_sources,
            "gaps": gaps,
            "evidence_signals": (inv or {}).get("signals") or {},
        })

    portfolio_probes = _build_portfolio_probes(initiative_critiques)
    top_probes = _portfolio_to_legacy_top_probes(portfolio_probes)

    result = {
        "critique_summary": {
            "total_initiatives": len(initiative_critiques),
            "ready_count": ready_count,
            "probe_count": probe_count,
            "insufficient_count": insufficient_count,
            "savings_ready": round(savings_ready),
            "savings_probe": round(savings_probe),
            "savings_insufficient": round(savings_insufficient),
        },
        "initiative_critiques": initiative_critiques,
        "top_probes": top_probes,
        "portfolio_probes": portfolio_probes,
    }

    try:
        from app.opar.probe_intelligence import enrich_portfolio_probes_with_gemini

        enriched = enrich_portfolio_probes_with_gemini(portfolio_probes)
        if enriched:
            result["portfolio_probes"] = enriched
            result["top_probes"] = _portfolio_to_legacy_top_probes(enriched)
    except Exception:
        pass

    try:
        from app.opar.sme_intelligence import enrich_sme_critique_with_llm

        llm_enriched = enrich_sme_critique_with_llm(result)
        if llm_enriched:
            result = llm_enriched
    except Exception:
        pass

    return result


def _build_portfolio_probes(initiative_critiques: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate per-initiative probes by probe_family_id into portfolio-scoped questions."""
    by_family: Dict[str, Dict[str, Any]] = {}
    for critique in initiative_critiques:
        cat = str(critique.get("category_name") or critique.get("category_id") or "")
        for probe in critique.get("probe_questions") or []:
            if not isinstance(probe, dict):
                continue
            fam = str(probe.get("probe_family_id") or "unknown")
            stake = float(probe.get("saving_at_stake") or 0)
            if fam not in by_family:
                entry = dict(probe)
                entry["affected_categories"] = [cat] if cat else []
                entry["_peak_stake"] = stake
                by_family[fam] = entry
            else:
                entry = by_family[fam]
                if cat and cat not in entry["affected_categories"]:
                    entry["affected_categories"].append(cat)
                entry["saving_at_stake"] = round(float(entry.get("saving_at_stake") or 0) + stake)
                if stake >= float(entry.get("_peak_stake") or 0):
                    entry["_peak_stake"] = stake
                    entry["why_critical"] = probe.get("why_critical") or entry.get("why_critical", "")

    ranked = sorted(
        by_family.values(),
        key=lambda p: float(p.get("saving_at_stake") or 0),
        reverse=True,
    )
    out: List[Dict[str, Any]] = []
    for entry in ranked[:5]:
        entry.pop("_peak_stake", None)
        cats = entry.get("affected_categories") or []
        fam = str(entry.get("probe_family_id") or "")
        if len(cats) > 1 or entry.get("scope") == "portfolio":
            entry["scope"] = "portfolio"
            if fam in FAMILY_PORTFOLIO_QUESTIONS:
                entry["question"] = FAMILY_PORTFOLIO_QUESTIONS[fam]
            entry["chat_cta"] = _build_portfolio_cta_label(fam, entry.get("question", ""), cats)
        else:
            entry["scope"] = entry.get("scope") or "category"
            entry["chat_cta"] = _build_cta_label(cats[0] if cats else "Category", entry.get("question", ""))
        entry["options"] = [
            "I need to gather this data — defer to the next review cycle",
            "This assumption does not apply to our business",
        ]
        out.append(entry)
    return out


def _portfolio_to_legacy_top_probes(portfolio_probes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map portfolio_probes to legacy top_probes shape for backward compatibility."""
    legacy: List[Dict[str, Any]] = []
    for probe in portfolio_probes[:3]:
        cats = probe.get("affected_categories") or []
        legacy.append({
            "question": probe.get("question", ""),
            "saving_at_stake": probe.get("saving_at_stake", 0),
            "category_name": cats[0] if cats else "",
            "why_critical": probe.get("why_critical", ""),
            "data_to_request": probe.get("data_to_request", ""),
            "chat_cta": probe.get("chat_cta", ""),
            "probe_family_id": probe.get("probe_family_id"),
            "scope": probe.get("scope"),
            "affected_categories": cats,
        })
    return legacy


def _build_portfolio_cta_label(family_id: str, question: str, categories: List[str]) -> str:
    short = question.split("—")[0].split("?")[0].strip()
    label = short[:40].strip() or family_id.replace("_", " ")
    n = len(categories)
    if n > 1:
        return f"{label} ({n} categories)"
    if categories:
        return f"{categories[0][:20]} — {label[:35]}"
    return label[:60]


def _build_cta_label(category_name: str, question: str) -> str:
    """Build a short, scannable chat CTA label from question text."""
    # Extract the key noun/action from the question (first 50 chars, cleaned)
    short = question.split("—")[0].split("?")[0].strip()
    # Prefix with category name for context
    cat_short = category_name[:20].strip()
    label = f"{cat_short} — {short[:45].strip()}"
    return label
