#!/usr/bin/env python3
"""One-off static authoring: replace family-default template playbooks with lever-specific
content for the universal levers still carrying scripts/seed_lever_playbooks.py defaults
(and the one sector lever that inherited them)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
MODEL_PARAMS = ROOT / "skills" / "savings-modeler" / "references" / "model_parameters.json"
IT_ITES_LEVERS = ROOT / "skills" / "sector-packs" / "it_ites" / "sector_levers.json"


def pb(*steps):
    return [
        {"step": s, "owner_role": o, "duration_weeks": w} if d is None
        else {"step": s, "owner_role": o, "duration_weeks": w, "dependencies": d}
        for (s, o, w, d) in steps
    ]


def sig(*signals):
    return [{"signal": s, "evidence_source": e, "confirms": c} for (s, e, c) in signals]


CONTENT: Dict[str, Dict[str, Any]] = {
    "demand_management": {
        "execution_playbook": pb(
            ("Baseline consumption by category, BU, and requester; separate price from volume drivers over 24 months", "FP&A / Procurement Analytics", 2, None),
            ("Set demand policies per category (eligibility, frequency, standards) and quantify the volume reduction target", "CFO / Functional Head", 3, None),
            ("Configure catalog restrictions, approval thresholds, and budget gates in the P2P system", "IT / Shared Services", 4, None),
            ("Run BU-level demand review boards for top categories with monthly consumption scorecards", "Category Manager", 4, None),
            ("Reset budgets to the new consumption baseline so savings cannot be respent", "FP&A", 3, None),
        ),
        "diagnostic_signals": sig(
            ("Consumption volume growing faster than the business driver (headcount, revenue, output)", "spend_profile", "Volume-driven leakage, not price, is the savings pool"),
            ("Wide per-employee or per-unit consumption variance across comparable BUs", "spend_profile", "Policy and demand discipline gaps exist"),
            ("Approval exceptions and off-catalog requests rising period-on-period", "p2p_logs", "Current controls are not containing demand"),
        ),
        "required_data_fields": [
            "Transaction-level spend with requester, BU, and cost centre (24 months)",
            "Business driver series (headcount, revenue, production volume) by BU",
            "P2P approval workflow configuration and exception log",
            "Category consumption policies currently in force",
        ],
    },
    "maverick_compliance": {
        "execution_playbook": pb(
            ("Quantify off-contract spend by category and vendor; identify top maverick requesters and root causes", "Procurement Analytics", 2, None),
            ("Close catalog gaps: onboard missing items/vendors under contract and fix punch-out usability issues", "Category Manager", 4, None),
            ("Enforce no-PO-no-pay and channel blocking for categories with contracted alternatives", "P2P Process Owner", 4, None),
            ("Publish BU-level compliance scorecards with escalation to functional heads for repeat leakage", "FP&A", 3, None),
            ("Recover retro rebates and reprice trailing maverick purchases onto contract terms", "Procurement Lead", 3, None),
        ),
        "diagnostic_signals": sig(
            ("Off-contract share above 15% in categories with valid framework agreements", "spend_profile", "Contract leakage is material and addressable"),
            ("Invoices without POs or POs raised after invoice date", "p2p_logs", "Purchasing controls are bypassed routinely"),
            ("Price paid for identical items varies across BUs beyond contract tiers", "vendor_master", "Negotiated rates are not being applied"),
        ),
        "required_data_fields": [
            "PO/non-PO invoice split by category and BU (24 months)",
            "Contract coverage map: categories with active framework agreements and rates",
            "Item-level price variance for top repeat purchases",
            "P2P channel configuration (catalog, punch-out, free-text)",
        ],
    },
    "zero_based_rebaseline": {
        "execution_playbook": pb(
            ("Select ZBB pilot cost packages and build activity-level cost visibility (driver x rate) for each", "FP&A", 3, None),
            ("Challenge every activity against business need: eliminate, reduce, standardise, or automate", "CFO / BU Heads", 4, None),
            ("Rebuild budgets bottom-up from approved activities at target unit rates", "FP&A", 4, None),
            ("Lock governance: monthly variance review against the zero-based budget with reinvestment gates", "FP&A", 3, None),
            ("Roll out to remaining cost packages in waves using pilot playbook", "Transformation Office", 8, None),
        ),
        "diagnostic_signals": sig(
            ("Budgets set incrementally (prior year + x%) with no activity-level justification", "process_benchmarking", "Structural over-budgeting is likely embedded"),
            ("Cost packages growing despite flat or falling business volumes", "spend_profile", "Spend is decoupled from need"),
            ("Large favourable variances repeatedly rebadged as new spend late in the year", "operating_metrics", "Budget padding exists and can be harvested"),
        ),
        "required_data_fields": [
            "Cost-centre level budgets vs actuals (36 months)",
            "Activity/driver decomposition for target cost packages",
            "Headcount and vendor spend mapped to each activity",
            "Prior-year budget build methodology and assumptions",
        ],
    },
    "specification_optimization": {
        "execution_playbook": pb(
            ("Rank top spend items by value and margin impact; shortlist over-specified candidates with engineering", "Category Manager / Engineering", 3, None),
            ("Run tear-down/should-cost and functional analysis to separate must-have from over-engineered attributes", "Value Engineering Team", 4, None),
            ("Validate de-specified alternatives with quality, regulatory, and key customers where relevant", "Quality / R&D", 5, None),
            ("Negotiate re-specified items with incumbents and challengers; capture price delta", "Strategic Sourcing", 5, None),
            ("Embed spec review gates into new product and repeat-buy approval workflows", "Engineering Change Board", 3, None),
        ),
        "diagnostic_signals": sig(
            ("Specifications exceed functional requirements or industry norms for the use case", "benchmark", "De-speccing headroom exists without performance loss"),
            ("Single-source items whose spec locks out competition", "vendor_master", "Spec change unlocks competitive pricing"),
            ("Material or grade cost per unit above should-cost model output", "spend_profile", "Value-engineering gap is quantifiable"),
        ),
        "required_data_fields": [
            "Bill of materials / item master with specifications for top items",
            "Should-cost or benchmark cost models for shortlisted items",
            "Quality and regulatory constraints per item",
            "Supplier quotes for alternative specifications",
        ],
    },
    "benefits_cost_optimization": {
        "execution_playbook": pb(
            ("Baseline total benefits cost per employee by plan, grade, and geography against market benchmarks", "Total Rewards / HR", 3, None),
            ("Analyse utilisation and perceived value per benefit; identify low-use high-cost items", "HR Analytics", 3, None),
            ("Redesign the benefits portfolio: flex-benefit wallets, plan tier changes, and voluntary top-ups", "CHRO / CFO", 5, None),
            ("Re-broke insurance programmes (GMC/GPA/GTL) with claims-experience data and wellness credits", "Benefits Broker / Total Rewards", 5, None),
            ("Communicate changes with employee value framing and track uptake vs cost per employee", "HR Communications", 3, None),
        ),
        "diagnostic_signals": sig(
            ("Benefits cost per employee above 75th percentile of market for the talent segment", "hr_analytics", "Portfolio is over-market and can be rebalanced"),
            ("GMC claims loss ratio driving premium escalation above medical inflation", "operating_metrics", "Plan design and wellness levers can cut premium"),
            ("Benefits with <20% utilisation absorbing material spend", "hr_analytics", "Low-value benefits can be swapped or dropped"),
        ),
        "required_data_fields": [
            "Benefits cost per employee by plan, grade, location (24 months)",
            "Insurance claims experience and loss ratios by policy year",
            "Benefit utilisation / enrolment statistics",
            "Market benchmark for benefits spend in comparable employers",
        ],
    },
    "contingent_workforce_optimization": {
        "execution_playbook": pb(
            ("Census the contingent workforce: headcount, tenure, rates, and engagement mode by function and vendor", "Procurement / HR", 3, None),
            ("Define role-level sourcing rules: SOW for outcomes, T&M for defined capacity, augmentation only for true flex", "CHRO / CFO / Functional Heads", 3, None),
            ("Rationalise rates: benchmark rate cards, tenure caps, and volume discounts across staffing vendors", "Strategic Sourcing", 5, None),
            ("Convert long-tenure augmentation roles to employees or outcome-based SOWs where cheaper", "HR / Vendor Management", 8, None),
            ("Stand up a VMS/contingent tower with monthly mix and rate compliance reporting", "Vendor Management Office", 4, None),
        ),
        "diagnostic_signals": sig(
            ("Contingent workers with tenure >18 months on time-and-material terms", "hr_analytics", "Conversion or SOW restructuring saves margin"),
            ("Rate variance for identical roles across staffing vendors above 15%", "vendor_master", "Rate card discipline is missing"),
            ("Contingent share of workforce above sector norm without seasonal justification", "hr_analytics", "Mix is structurally expensive"),
        ),
        "required_data_fields": [
            "Contingent workforce census with rates, tenure, vendor, and engagement mode",
            "Staffing vendor contracts and rate cards",
            "Comparable internal fully-loaded cost per role",
            "Demand forecast by function for the next 12-24 months",
        ],
    },
    "consulting_spend_governance": {
        "execution_playbook": pb(
            ("Aggregate consulting and advisory spend by firm, project, and sponsoring executive (36 months)", "Procurement Analytics", 2, None),
            ("Institute a demand gate: business case, internal-capability check, and ROI hypothesis before engagement", "CFO / Transformation Office", 3, None),
            ("Negotiate preferred-firm panel with rate cards, value-based fees, and volume commitments", "Strategic Sourcing", 5, None),
            ("Shift repeatable work to internal teams or lower-cost providers; cap partner-heavy staffing ratios", "Functional Heads", 6, None),
            ("Track benefits realisation per engagement against the approved business case", "FP&A", 4, None),
        ),
        "diagnostic_signals": sig(
            ("Consulting spend growing faster than revenue with fragmented firm panel", "spend_profile", "Governance and consolidation savings exist"),
            ("Engagements extended repeatedly without re-approval or measured outcomes", "p2p_logs", "Demand-side controls are absent"),
            ("Rates per grade vary widely across firms for comparable work", "vendor_master", "Rate-card negotiation headroom exists"),
        ),
        "required_data_fields": [
            "Consulting/advisory spend by firm, project, and sponsor (36 months)",
            "Engagement contracts with rates, staffing mix, and deliverables",
            "Internal capability inventory for overlapping skills",
            "Benefits tracking for past engagements where available",
        ],
    },
    "legal_spend_optimization": {
        "execution_playbook": pb(
            ("Baseline outside counsel spend by firm, matter type, and billing arrangement; identify concentration", "Legal Ops", 3, None),
            ("Publish outside counsel guidelines: staffing, billing rules, budget caps, and e-billing enforcement", "General Counsel", 3, None),
            ("Tier the panel: premium firms for bet-the-company matters, mid-tier and ALSPs for routine work", "Legal Ops / Procurement", 5, None),
            ("Negotiate alternative fee arrangements (fixed, capped, success-linked) for predictable matter types", "General Counsel / Legal Ops", 4, None),
            ("Insource high-volume routine work with legal tech (contract review, compliance filings)", "Legal Ops", 6, None),
        ),
        "diagnostic_signals": sig(
            ("Hourly-rate billing dominates with no matter budgets or e-billing validation", "spend_profile", "Fee arrangement and enforcement savings available"),
            ("Premium firms handling routine, repeatable matters", "vendor_master", "Right-tiering panel cuts blended rate"),
            ("Legal spend per matter rising with invoice write-off rates near zero", "p2p_logs", "Bill review discipline is missing"),
        ),
        "required_data_fields": [
            "Outside counsel invoices by firm, matter, timekeeper grade (24-36 months)",
            "Matter census with type, complexity, and outcome",
            "Current billing guidelines and e-billing system rules",
            "In-house team capacity and utilisation",
        ],
    },
    "ld_rationalization": {
        "execution_playbook": pb(
            ("Consolidate all L&D spend: vendors, platforms, content licences, internal academy costs, and travel", "L&D / FP&A", 2, None),
            ("Map curriculum against strategic skill gaps; cut low-completion and duplicative programmes", "CHRO / L&D", 3, None),
            ("Consolidate content platforms onto one enterprise licence with usage-based tiers", "L&D / Procurement", 4, None),
            ("Shift generic training to digital/cohort formats; reserve instructor-led for high-value skills", "L&D", 4, None),
            ("Install per-learner cost and completion dashboards with quarterly portfolio reviews", "HR Analytics", 3, None),
        ),
        "diagnostic_signals": sig(
            ("Multiple overlapping content platforms with sub-40% licence activation", "hr_analytics", "Platform consolidation savings are immediate"),
            ("L&D cost per employee above benchmark with completion rates below 50%", "hr_analytics", "Portfolio is oversized relative to value delivered"),
            ("Instructor-led and travel-heavy delivery for content available digitally", "spend_profile", "Delivery mode shift cuts cost per learning hour"),
        ),
        "required_data_fields": [
            "L&D spend by vendor, platform, programme (24 months)",
            "Licence counts vs active usage per platform",
            "Completion and satisfaction metrics by programme",
            "Skill gap priorities from workforce planning",
        ],
    },
    "agency_fee_optimization": {
        "execution_playbook": pb(
            ("Disaggregate agency fees: retainers, project fees, media commissions, and pass-through costs by agency", "Marketing Procurement", 3, None),
            ("Benchmark scopes of work against rate cards and FTE-based pricing models", "Marketing Procurement", 3, None),
            ("Restructure remuneration: move eligible scopes from retainer to project or performance-based fees", "CMO / Procurement", 5, None),
            ("Consolidate agency roster and in-house high-volume production/digital execution", "CMO", 8, None),
            ("Audit media transparency: rebates, unbilled media, and principal-based buys", "Media Auditor", 4, None),
        ),
        "diagnostic_signals": sig(
            ("Retainer scopes not reconciled to delivered outputs or staffing plans", "spend_profile", "Fee-for-scope realignment saves without volume loss"),
            ("Agency roster exceeds 6-8 agencies with overlapping capabilities", "vendor_master", "Roster consolidation increases leverage"),
            ("Production and adaptation costs above in-house or offshore studio benchmarks", "benchmark", "Execution insourcing/right-shoring is cheaper"),
        ),
        "required_data_fields": [
            "Agency contracts, scopes of work, and staffing plans",
            "Fee breakdown by agency and remuneration model (24 months)",
            "Media billing detail with rebate/AVB clauses",
            "Output volume metrics (campaigns, assets, adaptations)",
        ],
    },
    "cost_avoidance": {
        "execution_playbook": pb(
            ("Build a forward price-risk register: contract renewals, indexation clauses, and announced vendor increases", "Procurement Analytics", 2, None),
            ("Prioritise renewals by increase exposure; prepare negotiation counters before notice periods lapse", "Category Managers", 3, None),
            ("Negotiate caps, multi-year locks, or indexation formula changes on top exposures", "Strategic Sourcing", 6, None),
            ("Pre-buy or hedge categories with confirmed price escalations where storage/commitment economics work", "CFO / Treasury", 4, None),
            ("Report avoided cost separately from run-rate savings with auditable baseline vs quote evidence", "FP&A", 2, None),
        ),
        "diagnostic_signals": sig(
            ("Contracts with uncapped CPI/indexation clauses approaching renewal", "contract_repository", "Avoidable escalation is negotiable before lock-in"),
            ("Vendor increase notices exceeding market inflation for the category", "p2p_logs", "Counter-negotiation evidence exists"),
            ("Historical renewals signed at first-quote price without competitive tension", "vendor_master", "Renewal discipline will avoid future increases"),
        ),
        "required_data_fields": [
            "Contract register with renewal dates and indexation clauses",
            "Vendor price-increase notices and category inflation indices",
            "Renewal negotiation history and outcomes",
            "Budgeted vs quoted price for upcoming buys",
        ],
    },
}


def apply(levers: Dict[str, Any] | list, key_field: str | None = None) -> int:
    changed = 0
    items = levers.items() if isinstance(levers, dict) else [(lv.get("lever_id"), lv) for lv in levers]
    for lid, lv in items:
        content = CONTENT.get(lid)
        if not content:
            continue
        lv["execution_playbook"] = content["execution_playbook"]
        lv["diagnostic_signals"] = content["diagnostic_signals"]
        lv["required_data_fields"] = content["required_data_fields"]
        changed += 1
    return changed


def main() -> None:
    params = json.loads(MODEL_PARAMS.read_text(encoding="utf-8"))
    n = apply(params["levers"])
    MODEL_PARAMS.write_text(json.dumps(params, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"model_parameters.json: rewrote {n} lever playbooks")

    it = json.loads(IT_ITES_LEVERS.read_text(encoding="utf-8"))
    n = apply(it.get("sector_specific_levers", []))
    IT_ITES_LEVERS.write_text(json.dumps(it, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"it_ites sector_levers.json: rewrote {n} lever playbooks")


if __name__ == "__main__":
    main()
