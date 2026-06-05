"""SME Critique Analyzer — Deloitte-style evidence qualification for savings initiatives.

Deterministic rules engine: no LLM call. Evaluates each savings initiative against
data signals to score evidence maturity and generate targeted probe questions that
a senior consultant would ask before building a value case.
"""
from __future__ import annotations

from typing import Any, Dict, List


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
    category_id = str(initiative.get("category_id") or "")
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
    lever = str(initiative.get("lever") or initiative.get("lever_id") or "")
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
            probes.append({
                "question": f"When do the top vendor contracts for {category} expire — are they up for renewal within the planning horizon?",
                "why_critical": (
                    "If contracts run beyond 18 months, this saving is a future-period item at best. "
                    "Without expiry dates we cannot confirm near-term addressability."
                ),
                "saving_at_stake": round(saving_3yr * 0.80),
                "data_to_request": "Contract register with vendor name, category, expiry date, and auto-renewal clause",
            })
        if not has_supplier_data:
            probes.append({
                "question": f"How many active vendors currently serve {category}? Is the base fragmented (10+ vendors) or already concentrated?",
                "why_critical": (
                    "Consolidation from 20→5 vendors is an 18-month programme with significant sourcing effort. "
                    "Consolidation from 3→2 vendors releases minimal saving. "
                    "The starting supplier count determines both saving size and execution timeline."
                ),
                "saving_at_stake": round(saving_3yr * 0.60),
                "data_to_request": "Vendor master for this category with annual spend per vendor",
            })

    if lever == "strategic_sourcing":
        if not has_contract_data:
            probes.append({
                "question": f"When were {category} contracts last put to competitive tender — and were international / new-entrant suppliers included?",
                "why_critical": (
                    "Suppliers calibrate pricing to when you last tested the market. "
                    "If last tender was >3 years ago, the benchmark gap is likely real and recoverable. "
                    "If recently tendered, the peer gap may reflect genuine market position, not procurement failure."
                ),
                "saving_at_stake": round(saving_3yr * 0.70),
                "data_to_request": "Last tender date, shortlist size, and whether a should-cost model was used",
            })
        if benchmark_specificity < 0.60:
            probes.append({
                "question": f"The peer benchmark for {category} is drawn from a broad industry cut. Do you have a closer comparable — same geography, revenue band, and operating model?",
                "why_critical": (
                    "A low-specificity benchmark (broad sector, mixed geographies) can overstate the gap by 30–50%. "
                    "If the comparables are mostly MNCs vs your profile as a domestic mid-cap, "
                    "the achievable saving could be half the modelled figure."
                ),
                "saving_at_stake": round(saving_3yr * 0.40),
                "data_to_request": "Industry-specific benchmark from a sourced advisory database or prior engagement data",
            })

    if lever == "demand_management":
        if not has_cost_center_split:
            probes.append({
                "question": f"Is {category} spend discretionary (can be cut without revenue impact) or operationally linked to headcount / revenue / production volume?",
                "why_critical": (
                    "Demand management levers address discretionary spend only. "
                    "If most of this category is operationally driven, the addressable fraction drops from ~40% to ~15%. "
                    "Getting this wrong inflates the saving headline significantly."
                ),
                "saving_at_stake": round(saving_3yr * 0.50),
                "data_to_request": "Cost-centre breakdown and approval flow — which BUs control this spend and what drives purchase decisions",
            })
        if not has_prior_year_data:
            probes.append({
                "question": f"Has {category} spend grown faster than revenue over the last 2 years, or roughly in line?",
                "why_critical": (
                    "If spend has tracked revenue closely, you are likely buying what the business needs. "
                    "If spend has outpaced revenue, there is true demand-side slack — this probe determines whether "
                    "demand management is the right lever or whether structural cost is the issue."
                ),
                "saving_at_stake": round(saving_3yr * 0.30),
                "data_to_request": "2-year spend trend by category alongside revenue for the same periods",
            })

    if lever == "maverick_buying_reduction":
        if not has_po_coverage:
            probes.append({
                "question": f"What percentage of {category} spend currently flows through approved POs vs direct / card purchases?",
                "why_critical": (
                    "Maverick buying savings require PO compliance enforcement, which needs system configuration "
                    "and change management. If PO coverage is already >85%, the lever's upside is limited. "
                    "If <60%, the saving is real but the execution path is process-heavy."
                ),
                "saving_at_stake": round(saving_3yr * 0.60),
                "data_to_request": "PO coverage rate by category from your ERP (AP module)",
            })

    if lever == "process_automation":
        if not has_transaction_volume:
            probes.append({
                "question": f"What is the current invoice-approval cycle time for {category}, and how many invoices per month are processed?",
                "why_critical": (
                    "Automation ROI scales with transaction volume and cycle time. "
                    "At <200 invoices/month, automation rarely pays back in Year 1. "
                    "Without this data the saving is speculative."
                ),
                "saving_at_stake": round(saving * 0.40),
                "data_to_request": "AP transaction log with invoice count and average days-to-pay for this category",
            })

    if lever == "specification_optimization":
        if not has_spec_data:
            probes.append({
                "question": f"Are {category} specifications standardized across business units, or does each BU buy to its own spec?",
                "why_critical": (
                    "Specification harmonization requires engineering / operations sign-off and can take 6–12 months. "
                    "If specs are already standardized, this lever is moot. "
                    "If fragmented, the saving is real but the execution path is longer than the model assumes."
                ),
                "saving_at_stake": round(saving_3yr * 0.70),
                "data_to_request": "SKU or specification master per BU for this category",
            })

    # Generic fallback if no lever-specific probes fired but maturity is hypothesis/indicative
    if not probes and not has_supplier_data:
        probes.append({
            "question": f"Can you share the vendor master for {category} — supplier names, annual spend per supplier, and any known contract details?",
            "why_critical": (
                "The current saving is modelled from benchmark gap alone, with no supplier-level evidence. "
                "A vendor master gives us the data needed to stress-test the assumption "
                "and move from hypothesis to an evidenced business case."
            ),
            "saving_at_stake": round(saving_3yr * 0.50),
            "data_to_request": "Vendor master extract for this category",
        })

    return probes[:3]  # cap at 3 probes per initiative


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
        }

    # --- Index contract data by category ---
    contracts = contract_lifecycle.get("contracts", []) or []
    contracts_by_category: Dict[str, List[Dict[str, Any]]] = {}
    for c in contracts:
        if isinstance(c, dict):
            cat = str(c.get("category_id") or c.get("category") or "").lower()
            contracts_by_category.setdefault(cat, []).append(c)

    # --- Index supplier counts from spend profile ---
    supplier_counts: Dict[str, int] = {}
    for cat_entry in spend_profile.get("category_profile", []):
        if isinstance(cat_entry, dict):
            cat_id = str(cat_entry.get("category_id") or "").lower()
            # Use supplier_count field if present; otherwise count unique suppliers
            if "supplier_count" in cat_entry:
                supplier_counts[cat_id] = int(cat_entry["supplier_count"] or 0)
            elif "top_suppliers" in cat_entry:
                supplier_counts[cat_id] = len(cat_entry["top_suppliers"] or [])

    # --- Index root-cause diagnostic signal counts ---
    root_cause_signals_by_category: Dict[str, int] = {}
    for finding in root_causes.get("root_cause_findings", []):
        if isinstance(finding, dict):
            cat_id = str(finding.get("category_id") or "").lower()
            signals = finding.get("root_causes") or []
            root_cause_signals_by_category[cat_id] = len(signals) if isinstance(signals, list) else 0

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
        saving_3yr = float(
            (initiative.get("net_savings") or {}).get("total_3yr")
            or initiative.get("annualized_run_rate_savings")
            or 0
        )

        maturity, maturity_score = _score_evidence_maturity(
            initiative,
            contracts_by_category,
            supplier_counts,
            root_cause_signals_by_category,
        )

        has_contract = bool(contracts_by_category.get(category_id))
        has_supplier = supplier_counts.get(category_id, 0) > 1
        specificity = benchmark_specificity_by_category.get(category_id, 0.5)

        probes = _build_probe_questions(
            initiative,
            has_contract_data=has_contract,
            has_supplier_data=has_supplier,
            benchmark_specificity=specificity,
            has_cost_center_split=has_cost_center_split,
            has_prior_year_data=has_prior_year_data,
            has_po_coverage=has_po_coverage,
            has_transaction_volume=has_transaction_volume,
            has_spec_data=has_spec_data,
        )

        double_count_risk = _check_double_count(initiative, initiatives)

        # Determine verdict
        if maturity in ("supported", "validated") and not probes:
            sme_verdict = "proceed"
        elif maturity == "hypothesis" or (not has_contract and not has_supplier):
            sme_verdict = "insufficient_data"
        else:
            sme_verdict = "probe_first"

        # Derive critical risk narrative
        if sme_verdict == "insufficient_data":
            critical_risk = (
                f"Saving is modelled from benchmark gap alone — no contract, supplier, "
                f"or structural evidence for {initiative.get('category_name') or category_id}. "
                "Treat as hypothesis until data is gathered."
            )
        elif probes:
            critical_risk = probes[0]["why_critical"]
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
            "lever": initiative.get("lever") or initiative.get("lever_id") or "",
            "lever_name": initiative.get("lever_name") or "",
            "modelled_saving_3yr": saving_3yr,
            "evidence_maturity": maturity,
            "maturity_score": maturity_score,
            "sme_verdict": sme_verdict,
            "critical_risk": critical_risk,
            "probe_questions": probes,
            "double_count_risk": double_count_risk,
        })

    # --- Build top_probes: highest-stakes probe questions across all initiatives ---
    all_probes_flat: List[Dict[str, Any]] = []
    for critique in initiative_critiques:
        for probe in critique["probe_questions"]:
            all_probes_flat.append({
                "question": probe["question"],
                "saving_at_stake": probe["saving_at_stake"],
                "category_name": critique["category_name"],
                "why_critical": probe["why_critical"],
                "data_to_request": probe["data_to_request"],
                "chat_cta": _build_cta_label(critique["category_name"], probe["question"]),
            })

    # Sort by saving at stake descending, deduplicate by question stem
    all_probes_flat.sort(key=lambda p: p["saving_at_stake"], reverse=True)
    seen_questions: set[str] = set()
    top_probes: List[Dict[str, Any]] = []
    for probe in all_probes_flat:
        stem = probe["question"][:60]
        if stem not in seen_questions:
            seen_questions.add(stem)
            top_probes.append(probe)
        if len(top_probes) >= 3:
            break

    return {
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
    }


def _build_cta_label(category_name: str, question: str) -> str:
    """Build a short, scannable chat CTA label from question text."""
    # Extract the key noun/action from the question (first 50 chars, cleaned)
    short = question.split("—")[0].split("?")[0].strip()
    # Prefix with category name for context
    cat_short = category_name[:20].strip()
    label = f"{cat_short} — {short[:45].strip()}"
    return label
