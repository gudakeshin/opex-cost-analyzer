#!/usr/bin/env python3
"""Backfill sector_packs/<pack>/sector_levers.json stub catalogs from the runtime skills packs.

Reverse direction of scripts/sync_category_levers_runtime.py: every lever that exists in
skills/sector-packs/<pack>/sector_levers.json (runtime) but not in the version-controlled
stub catalog gets a stub row derived from the runtime record plus authored description /
BRSR metadata below. Idempotent — re-running adds nothing once parity is reached.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = ROOT / "sector_packs"
RUNTIME_DIR = ROOT / "skills" / "sector-packs"

_CATEGORY_RULE = re.compile(r"category:([A-Za-z0-9_&]+)")

# Authored one-line descriptions per lever_id (shared levers share a description).
DESCRIPTIONS: Dict[str, str] = {
    "actuarial_automation": "Automate actuarial data preparation, reserving runs, and IFRS-17/Ind AS 117 reporting pipelines to cut actuarial support cost and cycle time.",
    "assortment_optimization": "Rationalise assortment breadth by store cluster using sell-through and margin analytics; free working capital and reduce handling cost of slow movers.",
    "attrition_reduction_retention": "Reduce regrettable attrition through compensation benchmarking, career pathing, and manager quality programmes; cut replacement hiring and ramp-up costs.",
    "bench_management_optimization": "Tighten bench policies with demand-linked hiring triggers, internal redeployment marketplaces, and utilisation dashboards to shrink unbilled capacity.",
    "build_vs_buy_optimization": "Institute build-vs-buy gates for new platform investments comparing internal delivery cost against SaaS/COTS alternatives over a 5-year TCO.",
    "category_management": "Deploy category captaincy with joint business plans, planogram discipline, and margin-mix targets across grocery and general merchandise categories.",
    "channel_mix_optimization": "Shift acquisition mix toward lower-cost digital and bancassurance channels; rationalise agency incentives against persistency-adjusted economics.",
    "chargeback_model_transformation": "Move from headcount-based to consumption-based chargeback with unit-rate transparency, driving demand discipline from parent business units.",
    "churn_reduction": "Deploy churn-propensity models and save-desk playbooks to reduce gross churn and the acquisition spend needed to replace lost subscribers.",
    "claims_automation": "Automate FNOL intake, triage, and straight-through settlement for low-value claims; deploy AI-assisted estimation to compress loss-adjustment expense.",
    "clinical_space_utilization": "Raise OT, cath-lab, and bed utilisation through block scheduling, discharge-lounge conversion, and demand-smoothing across the facility network.",
    "clinical_trial_efficiency": "Optimise trial site mix, adopt decentralised/hybrid trial elements, and renegotiate CRO rate cards to lower per-patient trial cost.",
    "clinical_workforce_optimization": "Rebalance nurse-to-bed ratios, cross-train clinical support staff, and reduce agency/locum dependence through structured float pools.",
    "cloud_finops": "Stand up a FinOps practice — rightsize instances, purchase commitments/savings plans, eliminate orphaned resources, and enforce tagging-based showback.",
    "cloud_infra_modernization": "Migrate parent-mandated legacy hosting to modern cloud landing zones with autoscaling and reserved-capacity economics.",
    "cogs_direct_materials": "Attack direct-material COGS via should-cost models, alternate vendor development, and specification harmonisation across brands and plants.",
    "compliance_automation": "Automate KYC refresh, transaction monitoring tuning, and regulatory reporting workflows to cut compliance operations cost per account.",
    "corporate_overhead_right_size": "Right-size corporate centre spans, delayer management, and rebase central function budgets against benchmarked cost-to-revenue ratios.",
    "csr_efficiency": "Consolidate CSR programme administration, co-fund with government schemes, and shift to outcome-based partner contracts to raise impact per rupee.",
    "customer_service_automation": "Deflect contact volume to self-care apps, bots, and IVR containment; consolidate contact-centre vendors on outcome-based pricing.",
    "demand_planning_accuracy": "Improve forecast accuracy with ML demand sensing and S&OP discipline, cutting expedited freight, write-offs, and safety-stock carrying cost.",
    "devops_automation": "Automate build-test-deploy toolchains and environment provisioning to reduce release engineering effort and non-production infrastructure spend.",
    "digital_rep_model": "Shift field-force coverage of long-tail prescribers to digital/hybrid engagement, resizing territories around high-value accounts.",
    "energy_audit_compliance": "Execute PAT-cycle energy audits and implement identified conservation measures (VFDs, waste-heat recovery, compressed-air fixes) across plants.",
    "energy_loss_reduction": "Reduce AT&C losses through feeder metering, theft analytics, and targeted network refurbishment in high-loss zones.",
    "energy_management": "Deploy site-level energy management — RF sleep modes, lithium-ion + solar hybridisation, and diesel elimination at tower and node sites.",
    "energy_per_key_reduction": "Cut energy cost per occupied room via BMS-driven HVAC scheduling, heat-pump retrofits, and kitchen/laundry equipment upgrades.",
    "expiry_risk_reduction": "Reduce expiry write-offs with shelf-life-aware inventory deployment, FEFO discipline, and demand-linked production slotting.",
    "fnb_procurement_optimization": "Consolidate F&B vendors, implement seasonal menu engineering, and enforce yield/portioning standards to cut food cost percentage.",
    "fraud_detection_ai_insurance": "Deploy ML fraud scoring across claims intake to reduce leakage from staged, inflated, and duplicate claims while protecting genuine settlement TAT.",
    "fuel_procurement_optimization": "Optimise coal/gas linkage mix, e-auction participation, and blending strategies; renegotiate transport contracts to lower landed fuel cost.",
    "fund_administration_consolidation": "Consolidate fund accounting, transfer agency, and custody mandates to fewer providers at tiered AUM-linked fees.",
    "genai_augmented_productivity": "Deploy GenAI copilots for coding, testing, documentation, and knowledge ops with adoption tracking tied to capacity release.",
    "genai_productivity": "Roll out GenAI-assisted delivery (code generation, test automation, documentation) with productivity gain-share targets baked into account plans.",
    "grid_modernization": "Deploy smart meters, SCADA/ADMS upgrades, and self-healing feeder automation to cut outage response and manual operations cost.",
    "group_insurance_pooling": "Pool group companies' insurance programmes into master policies with captive/retention analysis to cut total premium spend.",
    "group_procurement": "Aggregate common indirect categories across group companies into master agreements with group-level pricing and compliance tracking.",
    "group_treasury_netting": "Centralise treasury with intercompany netting, cash pooling, and consolidated banking mandates to cut financing and bank fees.",
    "gst_itc_recovery": "Recover blocked input tax credit through vendor compliance remediation, GSTR-2B reconciliation, and refund claim acceleration.",
    "housekeeping_optimization": "Re-engineer housekeeping standards with workload-based staffing, task bundling, and outsourced deep-clean cycles to cut cost per occupied room.",
    "ind_as_116_lease": "Restructure lease portfolios post-Ind AS 116 — renegotiate embedded escalations, exercise break clauses, and rationalise underutilised leased assets.",
    "intercompany_pricing_optimization": "Rebase intercompany service charges and royalties on benchmarked arm's-length rates with documented cost-allocation keys.",
    "investment_ops_efficiency": "Automate investment operations — reconciliation, corporate actions, NAV oversight — and consolidate market-data terminal licenses.",
    "it_bss_oss_modernization": "Consolidate BSS/OSS stacks post-merger, decommission legacy platforms, and shift to cloud-native charging and assurance systems.",
    "license_rightsizing": "Reclaim unused software entitlements, rightsize license tiers to actual usage telemetry, and consolidate overlapping tools at renewal.",
    "loyalty_program_efficiency": "Re-engineer loyalty economics — tier thresholds, breakage assumptions, and partner-funded rewards — to cut programme cost per active member.",
    "manpower_rationalisation": "Rebalance workforce through VRS design, redeployment to growth units, and freeze-and-attrite plans aligned with DPE guidelines.",
    "manufacturing_cogs": "Drive conversion-cost productivity via OEE improvement, yield optimisation, and energy intensity reduction across API and formulation plants.",
    "markdown_optimization": "Apply ML-driven markdown timing and depth optimisation by store/SKU to recover margin from clearance activity.",
    "market_access_rebate_mgmt": "Tighten rebate and discount governance across channels with contract compliance analytics and claw-back of off-contract concessions.",
    "material_inventory_optimization": "Optimise spares and consumables inventory with criticality-based min/max norms, obsolete stock disposal, and vendor-managed inventory for fast movers.",
    "medical_equipment_rationalization": "Rationalise medical equipment fleet — utilisation-based redeployment, standardised vendors, and outcome-based maintenance contracts.",
    "medical_supplies_procurement": "Consolidate medical-surgical consumables onto formulary contracts with compliance tracking and clinical-variation reduction programmes.",
    "mode_shift_logistics": "Shift primary freight from road to rail/coastal multimodal where service levels allow; consolidate lanes and tender freight annually.",
    "mro_consolidation": "Consolidate MRO vendors under annual rate contracts with ABC-criticality stocking norms and consumption-based replenishment.",
    "omnichannel_fulfillment": "Optimise split between store-fulfilled, dark-store, and DC e-commerce fulfilment to cut cost per order without degrading promise times.",
    "org_span_control_optimisation": "Widen manager spans and delayer the organisation against benchmark spans by function, converting freed capacity to billable or cut roles.",
    "ota_commission_reduction": "Shift booking mix toward direct channels via rate parity discipline, loyalty-exclusive pricing, and metasearch investment to cut OTA commissions.",
    "outsourced_operations": "Rebid O&M and outsourced field operations with output-based SLAs and benchmarked unit rates; insource where scale justifies.",
    "packaging_optimisation": "Lightweight and right-size packaging specifications, increase recycled content, and consolidate packaging vendors across plants.",
    "parent_recharge_rationalization": "Challenge and rebase parent-company recharges (brand fees, IT allocations, management charges) against service-level evidence.",
    "parent_scope_rationalization": "Renegotiate the GCC's chartered scope with the parent — exit low-value work, expand higher-value ownership, and reprice the service catalogue.",
    "performance_attribution_tech": "Consolidate performance, attribution, and risk analytics platforms; replace bespoke builds with vendor utilities priced per portfolio.",
    "perks_benefits_rationalisation": "Rationalise benefits portfolio against utilisation data — transport, cafeteria, insurance top-ups — while protecting high-value retention perks.",
    "pharmacovigilance_automation": "Automate adverse-event case intake and processing with AI-assisted triage, cutting per-case PV cost while maintaining compliance.",
    "pharmacy_cost_optimization": "Tighten hospital pharmacy economics — generic substitution protocols, consignment stock, and pilferage controls at dispensing points.",
    "platform_consolidation": "Consolidate overlapping delivery platforms, tools, and environments after growth/M&A; decommission redundant licenses and infrastructure.",
    "policy_admin_digitization": "Digitise policy administration — issuance, endorsements, renewals — with straight-through processing to cut per-policy servicing cost.",
    "portfolio_rationalization": "Exit or divest sub-scale business lines and merge overlapping legal entities to eliminate stranded overhead and compliance cost.",
    "predictive_maintenance": "Deploy condition-based monitoring on critical rotating equipment to convert breakdown and time-based maintenance into predictive interventions.",
    "pricing_architecture": "Re-architect pack-price ladders and trade margins to protect price realisation while funding promotions from mix rather than depth.",
    "private_label": "Expand private-label penetration in high-margin categories with dedicated sourcing and quality programmes to improve blended margin.",
    "private_label_expansion": "Expand private-label / own-brand share in strategic categories, backstopped by contract manufacturing rate benchmarks.",
    "project_cost_overrun_control": "Institute stage-gate reviews, EPC contract discipline, and independent cost audits to arrest project time and cost overruns.",
    "public_procurement_reform": "Adopt GeM marketplace pricing, e-reverse auctions, and framework agreements to compress procurement rates within CVC guidelines.",
    "real_estate_portfolio_mgmt": "Consolidate group office footprint, sublet surplus space, and renegotiate leases at renewal against market benchmarks.",
    "recruitment_cost_optimisation": "Shift hiring mix to internal referrals and direct sourcing, renegotiate agency rate cards, and reduce offer-drop leakage.",
    "regulatory_submission_efficiency": "Standardise dossier authoring with structured content management and automate submission publishing across markets.",
    "reinsurance_optimization": "Restructure reinsurance programmes — retention levels, treaty vs facultative mix, and panel competition — to cut ceded cost per unit of cover.",
    "remote_first_realestate": "Adopt remote-first workplace policy with hub-and-spoke offices and hot-desking ratios, exiting surplus leases at break points.",
    "renewable_energy_transition": "Contract round-the-clock renewable PPAs and group captive solar/wind to displace costlier grid and fossil generation.",
    "research_cost_management": "Unbundle and rationalise external research spend post-MiFID economics; consolidate providers and enforce usage-based allocation.",
    "revenue_cycle_automation": "Automate charge capture, coding assistance, and payer-claims scrubbing to cut billing cost and revenue leakage.",
    "revenue_management_optimization": "Deploy dynamic pricing and channel-mix revenue management to lift RevPAR while trimming distribution and manual pricing effort.",
    "roaming_cost_optimization": "Renegotiate IOT roaming agreements, steer traffic to preferred partners, and deploy local breakout to cut wholesale roaming cost.",
    "rpa_intelligent_automation": "Industrialise RPA/IDP pipelines for rule-based back-office processes with a reusable automation factory and benefits tracking.",
    "sales_force_sizing": "Right-size field-force territories using prescriber-value analytics; redeploy or reduce coverage of low-yield segments.",
    "seat_utilization_optimization": "Raise seat-sharing ratios with hybrid scheduling and neighbourhood-based allocation, consolidating floors and exiting surplus leases.",
    "sez_stpi_tax_optimisation": "Optimise SEZ/STPI unit structure, safe-harbour elections, and state incentive claims to reduce effective tax and compliance cost.",
    "shadow_it_saas_elimination": "Discover and eliminate shadow SaaS via SSO/CASB telemetry; consolidate duplicative tools into the sanctioned stack.",
    "shared_services_center": "Consolidate finance, HR, and procurement transactional work from group companies into a shared services centre with unit-cost SLAs.",
    "shared_services_consolidation": "Consolidate fragmented support functions into the GCC's shared-services towers with standardised processes and unit-rate charging.",
    "sku_rationalization": "Prune tail SKUs below contribution thresholds and harmonise formulations/packs to cut complexity cost across the value chain.",
    "spectrum_efficiency": "Refarm legacy-band spectrum to 4G/5G, optimise carrier aggregation, and rationalise redundant legacy network layers.",
    "store_labor_optimization": "Deploy traffic-driven labour scheduling, task-time standards, and multi-skilling to cut store labour cost per transaction.",
    "store_network_optimization": "Exit persistently sub-threshold stores, renegotiate renewal leases, and rebalance formats toward higher-productivity footprints.",
    "subcontractor_optimization": "Rationalise subcontractor panel, enforce rate cards and margin floors, and convert recurring subcon roles to direct hires where cheaper.",
    "tech_debt_payoff": "Retire legacy applications and re-platform high-maintenance systems to cut run cost and release capacity from keep-the-lights-on work.",
    "tech_platform_consolidation": "Consolidate commercial and R&D technology platforms post-acquisition; decommission overlapping systems and renegotiate enterprise agreements.",
    "tier2_location_strategy": "Shift growth seats to tier-2 India locations with lower salary and real-estate cost while protecting niche-skill hubs.",
    "tower_sharing": "Increase tower tenancy ratios through co-location deals and network-sharing agreements to dilute passive infrastructure cost per tenant.",
    "trade_terms_optimization": "Restructure trade spend from unconditional margins to performance-linked terms with claims automation and audit recovery.",
    "trading_technology_optimization": "Rationalise OMS/EMS platforms, market-data entitlements, and connectivity spend against desk-level usage.",
    "underwriting_automation": "Automate rule-based underwriting with STP for standard risks and analytics-assisted triage for referrals, cutting cost per policy issued.",
    "upskilling_pyramid_rebalancing": "Rebalance the delivery pyramid via structured upskilling, fresher intake, and role-level output standards to lower blended cost per FTE.",
    "vendor_managed_services_shift": "Shift commodity IT operations from staff augmentation to outcome-based managed services with benchmarked unit pricing.",
    "warehouse_automation": "Automate high-throughput DC operations (sortation, put-to-light, WMS optimisation) to cut cost per case shipped.",
    "workforce_productivity": "Lift field and retail workforce productivity through digital work-order management, route optimisation, and span recalibration.",
    "workforce_scheduling": "Optimise field crew scheduling and dispatch with demand-based rostering and mobile workforce management tools.",
}

# category_ids fallback for levers whose applicable_if carries no category:<id> rule.
CATEGORY_FALLBACKS: Dict[str, List[str]] = {
    "shared_services_center": ["PROF_SERVICES", "HR"],
    "group_procurement": ["PROF_SERVICES", "OFFICE"],
    "corporate_overhead_right_size": ["PROF_SERVICES", "HR"],
    "portfolio_rationalization": ["PROF_SERVICES"],
    "intercompany_pricing_optimization": ["FIN_SVCS", "PROF_SERVICES"],
    "workforce_scheduling": ["HR"],
    "fund_administration_consolidation": ["PROF_SERVICES", "IT_SOFTWARE"],
    "clinical_space_utilization": ["FACILITIES"],
    "policy_admin_digitization": ["IT_SOFTWARE"],
    "fraud_detection_ai_insurance": ["IT_SOFTWARE", "PROF_SERVICES"],
    "reinsurance_optimization": ["INSURANCE", "FIN_SVCS"],
    "market_access_rebate_mgmt": ["MARKETING", "PROF_SERVICES"],
    "gst_itc_recovery": ["FIN_SVCS"],
    "public_procurement_reform": ["PROF_SERVICES"],
    "manpower_rationalisation": ["HR"],
    "real_estate_portfolio_mgmt": ["FACILITIES"],
    "group_treasury_netting": ["FIN_SVCS"],
    "group_insurance_pooling": ["INSURANCE"],
    "claims_automation": ["IT_SOFTWARE", "PROF_SERVICES"],
    "underwriting_automation": ["IT_SOFTWARE"],
    "channel_mix_optimization": ["MARKETING"],
    "actuarial_automation": ["PROF_SERVICES", "IT_SOFTWARE"],
    "investment_ops_efficiency": ["IT_SOFTWARE", "FIN_SVCS"],
    "compliance_automation": ["PROF_SERVICES", "IT_SOFTWARE"],
    "research_cost_management": ["PROF_SERVICES"],
    "performance_attribution_tech": ["IT_SOFTWARE"],
    "trading_technology_optimization": ["IT_SOFTWARE"],
    "sales_force_sizing": ["HR", "MARKETING"],
    "digital_rep_model": ["MARKETING", "HR"],
    "clinical_trial_efficiency": ["RND", "PROF_SERVICES"],
    "regulatory_submission_efficiency": ["PROF_SERVICES", "RND"],
    "pharmacovigilance_automation": ["PROF_SERVICES", "IT_SOFTWARE"],
    "expiry_risk_reduction": ["LOGISTICS"],
    "manufacturing_cogs": ["CONVERSION_COST", "RAW_MATERIALS"],
    "tech_platform_consolidation": ["IT_SOFTWARE"],
    "revenue_management_optimization": ["MARKETING", "IT_SOFTWARE"],
    "ota_commission_reduction": ["MARKETING"],
    "churn_reduction": ["MARKETING"],
    "csr_efficiency": ["BRSR_ESG"],
    "project_cost_overrun_control": ["PROF_SERVICES"],
    "ind_as_116_lease": ["FACILITIES", "FIN_SVCS"],
    "category_management": ["MARKETING"],
    "private_label": ["MARKETING", "RAW_MATERIALS"],
    "markdown_optimization": ["MARKETING"],
    "loyalty_program_efficiency": ["MARKETING"],
    "omnichannel_fulfillment": ["LOGISTICS"],
    "store_labor_optimization": ["HR"],
    "store_network_optimization": ["FACILITIES"],
    "roaming_cost_optimization": ["NETWORK_OPEX"],
    "it_bss_oss_modernization": ["IT_SOFTWARE"],
    "tower_sharing": ["TOWER_INFRA"],
    "spectrum_efficiency": ["SPECTRUM_LICENSING"],
    "energy_management": ["POWER_ENERGY"],
    "workforce_productivity": ["HR"],
    "customer_service_automation": ["PROF_SERVICES", "IT_SOFTWARE"],
}

# BRSR principle overrides; anything not listed falls back to _brsr_heuristic().
BRSR_OVERRIDES: Dict[str, str] = {
    "csr_efficiency": "P8",
    "gst_itc_recovery": "P1",
    "intercompany_pricing_optimization": "P1",
    "public_procurement_reform": "P1",
    "sez_stpi_tax_optimisation": "P1",
    "group_treasury_netting": "P1",
    "project_cost_overrun_control": "P1",
    "compliance_automation": "P1",
    "pharmacovigilance_automation": "P9",
    "fraud_detection_ai_insurance": "P9",
}

_P3_HINTS = ("workforce", "attrition", "manpower", "recruitment", "upskilling", "perks", "benefits", "bench", "span", "labor", "scheduling", "sales_force", "clinical_workforce")
_P6_HINTS = ("energy", "renewable", "packaging", "fuel", "grid", "predictive_maintenance", "mode_shift", "loss_reduction", "real_estate", "remote_first", "seat_utilization", "space", "tower", "spectrum", "expiry", "housekeeping")
_P9_HINTS = ("churn", "customer", "claims", "policy_admin", "loyalty", "revenue_cycle", "underwriting", "market_access", "pricing_architecture", "revenue_management")


def _brsr_heuristic(lever_id: str) -> str:
    lid = lever_id.lower()
    if any(h in lid for h in _P3_HINTS):
        return "P3"
    if any(h in lid for h in _P6_HINTS):
        return "P6"
    if any(h in lid for h in _P9_HINTS):
        return "P9"
    return "P2"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _derive_category_ids(runtime_lever: Dict[str, Any]) -> List[str]:
    cats: List[str] = []
    for rule in runtime_lever.get("applicable_if") or []:
        for match in _CATEGORY_RULE.finditer(str(rule)):
            cat = match.group(1)
            if cat not in cats:
                cats.append(cat)
    if cats:
        return cats
    return CATEGORY_FALLBACKS.get(runtime_lever.get("lever_id", ""), [])


def _stub_row(runtime_lever: Dict[str, Any]) -> Dict[str, Any]:
    lid = runtime_lever["lever_id"]
    if lid not in DESCRIPTIONS:
        raise SystemExit(f"No authored description for lever '{lid}' — add it to DESCRIPTIONS")
    cats = _derive_category_ids(runtime_lever)
    if not cats:
        raise SystemExit(f"No category_ids derivable for lever '{lid}' — add to CATEGORY_FALLBACKS")
    sr = runtime_lever.get("savings_range_pct") or {}
    weeks = runtime_lever.get("implementation_weeks") or {}
    p50_weeks = weeks.get("p50") if isinstance(weeks, dict) else weeks
    return {
        "lever_id": lid,
        "lever_name": runtime_lever.get("lever_name", lid),
        "description": DESCRIPTIONS[lid],
        "category_ids": cats,
        "p10_pct": float(sr.get("p10")),
        "p50_pct": float(sr.get("p50")),
        "p90_pct": float(sr.get("p90")),
        "implementation_weeks": int(p50_weeks or 0),
        "brsr_principle": BRSR_OVERRIDES.get(lid, _brsr_heuristic(lid)),
        "savings_type": runtime_lever.get("savings_type", "run_rate"),
        "industry_sources": runtime_lever.get("industry_sources") or [],
    }


def main() -> None:
    total_added = 0
    for pack_path in sorted(STUB_DIR.iterdir()):
        if not pack_path.is_dir():
            continue
        pack_id = pack_path.name
        stub_path = pack_path / "sector_levers.json"
        runtime_path = RUNTIME_DIR / pack_id / "sector_levers.json"
        if not stub_path.exists() or not runtime_path.exists():
            continue
        stub = _load_json(stub_path)
        runtime = _load_json(runtime_path)
        stub_ids = {lv["lever_id"] for lv in stub.get("levers") or []}
        missing = [
            lv for lv in runtime.get("sector_specific_levers") or []
            if lv["lever_id"] not in stub_ids
        ]
        if not missing:
            continue
        for lv in missing:
            stub["levers"].append(_stub_row(lv))
        stub_path.write_text(
            json.dumps(stub, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        total_added += len(missing)
        print(f"{pack_id}: added {len(missing)} stub levers -> {len(stub['levers'])} total")
    print(f"Done. {total_added} stub levers backfilled.")


if __name__ == "__main__":
    main()
