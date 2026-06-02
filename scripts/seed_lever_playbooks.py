#!/usr/bin/env python3
"""One-off static authoring: add execution_playbook, diagnostic_signals, required_data_fields to levers."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
SECTOR_DIR = ROOT / "skills" / "sector-packs"
MODEL_PARAMS = ROOT / "skills" / "savings-modeler" / "references" / "model_parameters.json"

FAMILY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "supply": {
        "execution_playbook": [
            {"step": "Baseline spend and contract inventory for target category", "owner_role": "Category Manager", "duration_weeks": 2},
            {"step": "Run should-cost / market benchmark and build negotiation pack", "owner_role": "Strategic Sourcing", "duration_weeks": 3, "dependencies": ["Baseline spend and contract inventory for target category"]},
            {"step": "Execute RFx or renewal negotiation and capture signed savings", "owner_role": "Procurement Lead", "duration_weeks": 6, "dependencies": ["Run should-cost / market benchmark and build negotiation pack"]},
            {"step": "Embed controls in P2P and track run-rate vs plan", "owner_role": "FP&A", "duration_weeks": 4, "dependencies": ["Execute RFx or renewal negotiation and capture signed savings"]},
        ],
        "diagnostic_signals": [
            {"signal": "Category spend above peer/median", "evidence_source": "spend_profile", "confirms": "Material savings pool exists"},
            {"signal": "Supplier concentration or contract renewal within 12 months", "evidence_source": "vendor_master", "confirms": "Negotiation lever is actionable"},
        ],
        "required_data_fields": [
            "GL spend by category (36 months)",
            "Vendor master with contract end dates",
            "Peer or should-cost benchmark",
        ],
    },
    "demand": {
        "execution_playbook": [
            {"step": "Quantify consumption drivers and policy exceptions", "owner_role": "Process Owner", "duration_weeks": 2},
            {"step": "Define target operating policy and approval workflow", "owner_role": "CFO / Functional Head", "duration_weeks": 3},
            {"step": "Implement system controls and communicate standards", "owner_role": "IT / Shared Services", "duration_weeks": 4},
            {"step": "Monitor compliance and reset budgets to hold savings", "owner_role": "FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Maverick or off-catalog spend share elevated", "evidence_source": "spend_profile", "confirms": "Demand leakage is present"},
            {"signal": "Policy exceptions rising period-on-period", "evidence_source": "p2p_logs", "confirms": "Governance gap is widening"},
        ],
        "required_data_fields": ["Transaction-level spend with requester/BU", "Approval workflow configuration", "Policy exception log"],
    },
    "process": {
        "execution_playbook": [
            {"step": "Map current-state process and cost drivers", "owner_role": "Transformation Lead", "duration_weeks": 3},
            {"step": "Design target process and RACI", "owner_role": "Process Owner", "duration_weeks": 4},
            {"step": "Pilot in one BU/geo and measure effort/cost delta", "owner_role": "Operations", "duration_weeks": 6},
            {"step": "Scale rollout and update SOPs/training", "owner_role": "HR / Ops", "duration_weeks": 8},
        ],
        "diagnostic_signals": [
            {"signal": "High FTE effort or cycle time vs benchmark", "evidence_source": "operating_metrics", "confirms": "Process inefficiency is material"},
        ],
        "required_data_fields": ["Process volume metrics", "FTE effort or cost allocation by process", "Baseline cycle times"],
    },
    "technology": {
        "execution_playbook": [
            {"step": "Prioritise automatable processes by volume × effort", "owner_role": "Automation CoE", "duration_weeks": 2},
            {"step": "Build business case and secure IT/security approval", "owner_role": "CIO / CTO", "duration_weeks": 3},
            {"step": "Develop/deploy automation (RPA/API) in waves", "owner_role": "IT Delivery", "duration_weeks": 10},
            {"step": "Stabilise bots/workflows and transfer to run team", "owner_role": "IT Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Repeatable transactions above automation threshold", "evidence_source": "process_mining", "confirms": "Automation ROI is achievable"},
        ],
        "required_data_fields": ["Process inventory with volumes", "Application landscape", "Labour cost per process"],
    },
    "finance": {
        "execution_playbook": [
            {"step": "Analyse working-capital and payment-term baseline", "owner_role": "Treasury", "duration_weeks": 2},
            {"step": "Model supplier financial risk and term scenarios", "owner_role": "Treasury / Procurement", "duration_weeks": 3},
            {"step": "Negotiate term changes with top suppliers", "owner_role": "Procurement", "duration_weeks": 6},
            {"step": "Update ERP terms and monitor DPO/cash impact", "owner_role": "AP Lead", "duration_weeks": 2},
        ],
        "diagnostic_signals": [
            {"signal": "DPO below sector benchmark with low supplier risk", "evidence_source": "ap_aging", "confirms": "Term extension is feasible"},
        ],
        "required_data_fields": ["AP aging by supplier", "Payment terms master", "Supplier credit/risk ratings"],
    },
    "structure": {
        "execution_playbook": [
            {"step": "Define organisational design principles and guardrails", "owner_role": "CHRO", "duration_weeks": 3},
            {"step": "Model span/layers and target FTE envelope", "owner_role": "HR BP / FP&A", "duration_weeks": 4},
            {"step": "Execute change plan with legal/ER review", "owner_role": "HR Operations", "duration_weeks": 8},
            {"step": "Track attrition, productivity, and cost-to-serve", "owner_role": "FP&A", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Span of control or cost/employee above benchmark", "evidence_source": "hr_analytics", "confirms": "Structural opportunity exists"},
        ],
        "required_data_fields": ["Org chart and FTE roster", "Compensation bands", "Benchmark spans and layers"],
    },
}

LEVER_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "contract_renegotiation": {
        "diagnostic_signals": [
            {"signal": "Contracts expiring within 6–18 months", "evidence_source": "contract_repository", "confirms": "Renegotiation window is open"},
            {"signal": "Rate above should-cost or peer tariff", "evidence_source": "benchmark", "confirms": "Price gap is closable"},
        ],
    },
    "rpa_intelligent_automation": {
        "required_data_fields": [
            "Process inventory (volumes, exceptions, systems touched)",
            "FTE cost loaded by process",
            "IT security and architecture standards",
        ],
    },
}

# ---------------------------------------------------------------------------
# Per-lever specific content — always wins over family defaults.
# Keys are lever_id values across all sector packs.
# ---------------------------------------------------------------------------
LEVER_SPECIFIC: Dict[str, Dict[str, Any]] = {

    # ------------------------------------------------------------------ BFSI
    "branch_network_optimization": {
        "execution_playbook": [
            {"step": "Map 24-month branch P&L, footfall, and digital-adoption by branch; rank viability against break-even threshold", "owner_role": "Retail Banking Analytics", "duration_weeks": 3},
            {"step": "Cluster branches into full-service, lite-format, and digital-only; model revenue and cost impact per scenario", "owner_role": "Strategy / FP&A", "duration_weeks": 4},
            {"step": "Initiate RBI closure approvals; negotiate lease exits; redeploy ATMs/BCs to adjacent catchments", "owner_role": "Regulatory Affairs / Real Estate", "duration_weeks": 12},
            {"step": "Execute digital migration campaign for displaced customers; track balances and transaction shift to digital channels", "owner_role": "Retail Banking / Digital", "duration_weeks": 8},
            {"step": "Monitor revenue retention, occupancy cost savings, and customer NPS post-format change; rebaseline quarterly", "owner_role": "FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "FACILITIES spend >3% of revenue with ≥20% of branches showing negative unit P&L for ≥2 years", "evidence_source": "branch_pl_data", "confirms": "Over-networked footprint with structural cost drag"},
            {"signal": "Digital channel adoption >60% in clusters with overlapping full-service branches within 2 km", "evidence_source": "digital_channel_analytics", "confirms": "Format rationalisation feasible without material revenue loss"},
            {"signal": "Fixed occupancy cost >40% of total branch OPEX in bottom-quartile branches", "evidence_source": "gl_by_branch", "confirms": "Cost structure savings achievable via format or closure"},
        ],
        "required_data_fields": [
            "Branch-level P&L for ≥24 months (revenue, direct cost, allocated overhead)",
            "Monthly footfall and transaction count per branch",
            "Digital adoption by geography (mobile/internet banking penetration)",
            "Lease terms, WALE, and break-clause positions per branch",
            "RBI branch closure approval requirements and timelines",
        ],
    },

    "ops_process_digitization": {
        "execution_playbook": [
            {"step": "Run process mining on top-10 back-office processes by volume (NEFT/RTGS, account opening, trade-finance docs) to identify STP candidates", "owner_role": "Process Excellence / Automation CoE", "duration_weeks": 3},
            {"step": "Expose CBS APIs for workflow automation; design Front-to-Back STP architecture and data-flow diagram", "owner_role": "CTO / IT Architecture", "duration_weeks": 4},
            {"step": "Deploy RPA bots and API integrations in waves—Wave 1 high-volume/low-risk, Wave 2 regulatory processes, Wave 3 exception handling", "owner_role": "IT Delivery", "duration_weeks": 12},
            {"step": "Complete RBI operational-risk and cyber-security review; obtain IS Audit sign-off before production cutover", "owner_role": "CISO / Risk", "duration_weeks": 4},
            {"step": "Stabilise bots, hand over to run team, and track FTE release and error-rate reduction monthly", "owner_role": "IT Operations / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Manual touchpoints >40% in high-volume back-office processes (account opening, reconciliation, trade-finance docs)", "evidence_source": "process_mining_output", "confirms": "STP automation ROI is achievable"},
            {"signal": "Back-office headcount cost as % of OPEX above peer benchmark (OUTSOURCED/IT >8% revenue)", "evidence_source": "spend_profile", "confirms": "Digitisation opportunity is material"},
            {"signal": "Error or rework rate in back-office processes >5% of transaction volume", "evidence_source": "ops_quality_metrics", "confirms": "Quality and cost-reduction case for automation is compelling"},
        ],
        "required_data_fields": [
            "Process inventory with transaction volumes and manual vs automated step breakdown",
            "CBS API capability documentation and integration readiness",
            "FTE count and loaded labour cost per back-office process",
            "IT application landscape map",
            "RBI IT-framework compliance checklist",
        ],
    },

    "it_vendor_consolidation": {
        "execution_playbook": [
            {"step": "Complete IT application-landscape audit: map all active applications to vendor, annual cost, and usage metrics", "owner_role": "IT Procurement / SAM", "duration_weeks": 4},
            {"step": "Build rationalization roadmap—classify apps as keep/consolidate/retire; develop CBS upgrade/migration plan", "owner_role": "CTO / Enterprise Architecture", "duration_weeks": 5},
            {"step": "Run competitive RFPs for consolidated IT categories (infrastructure, middleware, testing); negotiate multi-year terms", "owner_role": "IT Procurement", "duration_weeks": 10},
            {"step": "Execute CBS migration in controlled phases with RBI IT-framework compliance assessment at each stage gate", "owner_role": "Core Banking Programme", "duration_weeks": 24},
            {"step": "Decommission retired applications; track licence spend reduction and vendor-count trend monthly", "owner_role": "IT Finance / FP&A", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "IT vendor count >50 with top-10 vendors representing <60% of IT spend", "evidence_source": "vendor_master", "confirms": "Fragmented supply base with consolidation potential"},
            {"signal": "IT spend >5% of revenue with >30% on maintenance of legacy or duplicate systems", "evidence_source": "gl_by_it_category", "confirms": "Material cost reduction available through rationalization"},
            {"signal": "Duplicate capability across ≥2 applications in same functional domain (multiple CRMs, reporting tools)", "evidence_source": "application_portfolio_assessment", "confirms": "Platform consolidation case is justified"},
        ],
        "required_data_fields": [
            "Full IT application inventory with vendor, annual cost, and active user count",
            "CBS vendor agreement terms and migration risk assessment",
            "IT spend by sub-category (infrastructure, applications, services, telecom)",
            "RBI IT framework compliance status per system",
            "Contract terms and renewal dates for top-20 IT vendors",
        ],
    },

    "kyc_aml_automation": {
        "execution_playbook": [
            {"step": "Map end-to-end KYC (onboarding + periodic refresh) and AML (transaction monitoring + alert disposition) workflows; measure FTE-hours per case", "owner_role": "Compliance / Operations", "duration_weeks": 3},
            {"step": "Select V-KYC platform and AI AML engine; validate against RBI Master Directions and PMLA requirements", "owner_role": "Compliance / Technology", "duration_weeks": 4},
            {"step": "Integrate V-KYC with CBS and document management; run AI AML model in shadow mode for parallel validation", "owner_role": "IT Delivery / Compliance", "duration_weeks": 10},
            {"step": "Complete PMLA compliance review of automated alert disposition; obtain internal-audit and external-auditor sign-off", "owner_role": "Chief Compliance Officer", "duration_weeks": 4},
            {"step": "Go live; track KYC turnaround, AML false-positive rate, and FTE release monthly", "owner_role": "Operations / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "KYC/AML operations headcount or outsourced cost >15% of total compliance budget", "evidence_source": "compliance_cost_breakdown", "confirms": "Scale of manual effort justifies automation investment"},
            {"signal": "AML alert false-positive rate >85% consuming analyst time without commensurate risk reduction", "evidence_source": "aml_operations_report", "confirms": "AI-tuned model will materially reduce alert volume and cost"},
            {"signal": "Average KYC turnaround time >5 days (individual) or >15 days (corporate)", "evidence_source": "operations_sla_tracker", "confirms": "STP opportunity exists with material customer-experience upside"},
        ],
        "required_data_fields": [
            "KYC workflow map with FTE-hours per step and monthly case volumes",
            "AML alert data: total volume, disposition rate, false-positive rate, and analyst hours",
            "CBS API readiness and V-KYC regulatory approval status",
            "PMLA/RBI Master Directions compliance checklist",
            "Current KYC/AML vendor contracts and SLA performance data",
        ],
    },

    "collections_efficiency": {
        "execution_playbook": [
            {"step": "Segment NPA portfolio by bucket (0–30, 31–60, 61–90, 90+ DPD), product, and geography; identify highest-yield recovery segments", "owner_role": "Collections Analytics", "duration_weeks": 3},
            {"step": "Deploy predictive collections scoring and AI call-routing; rationalise agency panel to performance-based empanelment", "owner_role": "Collections Head / Technology", "duration_weeks": 6},
            {"step": "Automate IBC/SARFAESI process flows for secured recovery; integrate legal case management with collections workflow", "owner_role": "Legal / IT", "duration_weeks": 8},
            {"step": "Launch digital self-cure channels (WhatsApp, net-banking EMI) for early-bucket accounts to reduce outbound cost", "owner_role": "Digital / Collections", "duration_weeks": 4},
            {"step": "Track recovery rate by segment, cost-per-recovery, and agent productivity; rebalance channel mix quarterly", "owner_role": "FP&A / Collections", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Collections cost as % of NPA book >2% indicating a manual-heavy model", "evidence_source": "collections_pl", "confirms": "Automation and agency rationalisation will reduce cost per recovery"},
            {"signal": "Collections agency panel >10 vendors with bottom-quartile agencies contributing <15% of recoveries", "evidence_source": "agency_performance_report", "confirms": "Performance-based empanelment will improve recovery yield"},
            {"signal": "Digital self-cure adoption <20% for early-bucket (0–30 DPD) accounts", "evidence_source": "collections_channel_report", "confirms": "Shift to digital channels will reduce outbound call cost"},
        ],
        "required_data_fields": [
            "NPA portfolio by bucket, product, and geography (12-month history)",
            "Collections agency performance data (recovery rate, cost per recovery, case allocation)",
            "IBC/SARFAESI case inventory and resolution timelines",
            "Digital channel adoption rates by customer segment",
            "Collections FTE count and cost breakdown by activity",
        ],
    },

    "treasury_ops_efficiency": {
        "execution_playbook": [
            {"step": "Conduct ALM gap analysis: map funding cost, liquidity buffers, and correspondent relationships; benchmark against peer banks", "owner_role": "Treasury / ALM", "duration_weeks": 3},
            {"step": "Upgrade TMS (Murex/Kondor) to automate deal capture, limit monitoring, and regulatory return generation", "owner_role": "CTO / Treasury Technology", "duration_weeks": 8},
            {"step": "Rationalise correspondent banking panel—retain key corridors, exit low-volume relationships", "owner_role": "Treasury / Compliance", "duration_weeks": 6},
            {"step": "Automate intra-day liquidity monitoring and SLR/CRR reporting; reduce manual FTE overhead", "owner_role": "Treasury Operations", "duration_weeks": 4},
            {"step": "Track ALM cost, correspondent-fee reduction, and treasury-ops FTE productivity quarterly", "owner_role": "FP&A", "duration_weeks": 3},
        ],
        "diagnostic_signals": [
            {"signal": "Treasury operations team >15 FTEs with >50% of time on manual reconciliation and regulatory reporting", "evidence_source": "treasury_ops_time_study", "confirms": "Automation will materially reduce treasury ops cost"},
            {"signal": "Correspondent banking fee spend >₹2 Cr/year with >20 active correspondents", "evidence_source": "correspondent_fees_gl", "confirms": "Panel rationalisation opportunity is material"},
            {"signal": "SLR/CRR returns prepared manually by >2 FTEs taking >3 days per period", "evidence_source": "regulatory_reporting_ops", "confirms": "Automation of regulatory returns is justified"},
        ],
        "required_data_fields": [
            "ALM gap report and liquidity buffer composition",
            "Correspondent banking fee schedule and transaction volumes by corridor",
            "Treasury ops FTE count and time allocation by activity",
            "Current TMS capability assessment and upgrade roadmap",
            "SLR/CRR and RBI regulatory reporting FTE cost and frequency",
        ],
    },

    "fraud_detection_ai_banking": {
        "execution_playbook": [
            {"step": "Label historical transaction fraud data (≥2 years, min 10,000 confirmed fraud cases); build feature-engineering pipeline", "owner_role": "Data Science / Risk", "duration_weeks": 6},
            {"step": "Develop and validate ML fraud scoring engine vs current rules engine using holdout dataset; document precision/recall tradeoffs", "owner_role": "Data Science", "duration_weeks": 6},
            {"step": "Integrate scoring engine with CBS/payment switch in real-time; complete RBI cyber-security framework compliance review", "owner_role": "IT Delivery / CISO", "duration_weeks": 8},
            {"step": "Run 60-day parallel validation: compare fraud catch rate and false-positive rate vs legacy rules engine", "owner_role": "Fraud Risk / IT", "duration_weeks": 8},
            {"step": "Decommission legacy rules engine; monitor fraud loss rate, detection rate, and model drift monthly", "owner_role": "Fraud Risk / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Fraud loss as % of disbursements >0.1% indicating inadequacy of current detection", "evidence_source": "fraud_loss_report", "confirms": "ML model will improve catch rate and reduce fraud losses"},
            {"signal": "False-positive rate on current rules engine >60% generating customer friction and analyst overhead", "evidence_source": "fraud_operations_report", "confirms": "ML will reduce false positives and investigation cost"},
            {"signal": "Manual fraud investigation team >20 FTEs with case backlog >500 outstanding", "evidence_source": "fraud_ops_tracker", "confirms": "Automation and better triage will reduce investigation cost"},
        ],
        "required_data_fields": [
            "Transaction history ≥2 years with confirmed fraud labels",
            "Current fraud rules engine architecture and detection-rate data",
            "CBS/payment-switch API capability for real-time ML scoring integration",
            "Fraud loss data by product, channel, and customer segment",
            "RBI cyber-security framework compliance checklist",
        ],
    },

    "regulatory_reporting_automation": {
        "execution_playbook": [
            {"step": "Inventory all RBI/SEBI regulatory returns: frequency, data sources, FTE-hours, and manual touchpoints per return", "owner_role": "Compliance / Regulatory Reporting", "duration_weeks": 3},
            {"step": "Align financial data dictionary with RBI XBRL/XSLT taxonomy; establish single source of truth in data warehouse", "owner_role": "Data Management / IT", "duration_weeks": 6},
            {"step": "Build automated generation for top-10 high-effort returns (SLR, CRR, CRILC, large exposure); configure validation rules", "owner_role": "IT Delivery / Compliance", "duration_weeks": 8},
            {"step": "Run two full reporting cycles in parallel (automated vs manual); reconcile and sign off with internal audit", "owner_role": "Compliance / Audit", "duration_weeks": 6},
            {"step": "Decommission manual returns; track FTE release and on-time submission rate", "owner_role": "FP&A / Compliance", "duration_weeks": 3},
        ],
        "diagnostic_signals": [
            {"signal": "Regulatory reporting team >10 FTEs spending >60% of time on data extraction and manual report preparation", "evidence_source": "compliance_ops_time_study", "confirms": "Automation will release significant FTE capacity"},
            {"signal": "Number of unique regulatory returns >30 with >5 source systems feeding each return", "evidence_source": "return_inventory", "confirms": "Data integration and automation investment is justified"},
            {"signal": "Late or restated returns ≥2 per year due to manual data aggregation errors", "evidence_source": "regulatory_submission_log", "confirms": "Quality and compliance-risk reduction from automation is material"},
        ],
        "required_data_fields": [
            "Inventory of all regulatory returns (name, regulator, frequency, source systems, FTE-hours)",
            "RBI XBRL/XSLT taxonomy mapping to chart of accounts",
            "Data warehouse/lake architecture and data-quality assessment",
            "Compliance team FTE count and time allocation per return",
            "Historical late/restated return log with root-cause analysis",
        ],
    },

    # ---------------------------------------------------------- CONGLOMERATE
    "shared_services_center": {
        "execution_playbook": [
            {"step": "Assess process maturity and standardisation readiness across F&A, HR, and IT sub-processes; identify SSC candidate scope by BU", "owner_role": "Group Transformation / FP&A", "duration_weeks": 4},
            {"step": "Design SSC operating model: location, governance charter, SLA framework, and chargeback model", "owner_role": "SSC Design Lead", "duration_weeks": 5},
            {"step": "Execute migration in waves—Wave 1 transactional F&A (AP/AR/GL), Wave 2 HR operations, Wave 3 IT service desk", "owner_role": "SSC Operations", "duration_weeks": 16},
            {"step": "Stabilise SSC with SLA monitoring dashboard; enforce chargeback to business units to drive demand discipline", "owner_role": "SSC Head / FP&A", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Duplicate F&A or HR back-office teams across >3 business units performing identical transactional processes", "evidence_source": "org_chart_and_cost_center_data", "confirms": "Consolidation will eliminate redundancy and reduce per-transaction cost"},
            {"signal": "Cost per transaction (e.g., cost per invoice processed) >2× SSC benchmark for same process", "evidence_source": "process_benchmarking", "confirms": "Scale economies from SSC are material"},
            {"signal": "Multiple ERP instances or process variants across BUs for the same transactional process", "evidence_source": "it_application_landscape", "confirms": "SSC standardisation will reduce technology and training cost"},
        ],
        "required_data_fields": [
            "F&A, HR, and IT process inventory with volume, FTE, and cost per BU",
            "Current cost-per-transaction benchmarks by process",
            "ERP/technology landscape across business units",
            "Chargeback/recharge model and inter-company billing data",
            "Location analysis for SSC hub (cost, talent, infrastructure)",
        ],
    },

    "group_procurement": {
        "execution_playbook": [
            {"step": "Aggregate spend data across all group entities; identify categories with >₹10 Cr combined spend and multiple BU buyers", "owner_role": "Group Procurement Lead", "duration_weeks": 3},
            {"step": "Establish cross-BU category councils for top-5 common categories; align specifications and demand volumes", "owner_role": "Category Council Chairs", "duration_weeks": 4},
            {"step": "Run group-level RFPs and negotiate master vendor agreements; commit total volume in exchange for tiered pricing", "owner_role": "Strategic Sourcing", "duration_weeks": 8},
            {"step": "Mandate compliance to group contracts via P2P system controls; track savings by BU monthly", "owner_role": "Group Procurement / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Same vendor supplying multiple group BUs at different unit prices—price spread >15%", "evidence_source": "consolidated_vendor_master", "confirms": "Group aggregation will capture price harmonisation savings"},
            {"signal": "Category spend above market benchmark across ≥3 BUs with no group-level contract in place", "evidence_source": "spend_profile_consolidated", "confirms": "Group RFP will yield material savings"},
            {"signal": "Tail vendor count >500 across group for categories with <10 suitable suppliers in market", "evidence_source": "group_vendor_master", "confirms": "Supplier rationalisation will reduce admin and negotiating leverage fragmentation"},
        ],
        "required_data_fields": [
            "Consolidated spend data across all group entities by category and vendor",
            "Vendor master with prices by BU for common categories",
            "Existing contracts by BU with term and pricing details",
            "Demand forecast by category for next 12 months across group",
            "Specification alignment assessment for common categories",
        ],
    },

    "corporate_overhead_right_size": {
        "execution_playbook": [
            {"step": "Build ZBB baseline for all corporate overhead cost lines; map every FTE and spend item to business-justification owner", "owner_role": "Group FP&A / CFO", "duration_weeks": 4},
            {"step": "Benchmark corporate overhead as % of group revenue against listed-peer conglomerates; identify gap to top-quartile", "owner_role": "Strategy / FP&A", "duration_weeks": 3},
            {"step": "Define elimination and reduction targets by function; model span-of-control and layer count vs benchmark", "owner_role": "CHRO / CFO", "duration_weeks": 3},
            {"step": "Execute reduction plan with HR/legal review; enforce new span and layer guardrails in org design", "owner_role": "HR Operations", "duration_weeks": 8},
            {"step": "Track overhead cost as % of revenue quarterly; gate new corporate hiring against overhead budget", "owner_role": "FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Corporate overhead as % of group revenue >3% vs peer conglomerate median of <2%", "evidence_source": "peer_benchmarking", "confirms": "Structural overhead reduction opportunity is material"},
            {"signal": "Corporate headcount growing faster than group revenue over past 3 years", "evidence_source": "hr_headcount_data", "confirms": "Overhead creep requires reset"},
            {"signal": "Management layers at group HQ >6 from CEO to first-line manager", "evidence_source": "org_chart", "confirms": "De-layering opportunity exists"},
        ],
        "required_data_fields": [
            "Full corporate overhead P&L by function and cost line",
            "Headcount by function and layer at group HQ",
            "Peer benchmark: corporate overhead % of revenue for listed conglomerates",
            "Group revenue and EBITDA trend (3 years)",
            "Org chart with span-of-control data by function",
        ],
    },

    "portfolio_rationalization": {
        "execution_playbook": [
            {"step": "Score all group businesses on two dimensions: strategic fit (core vs adjacency) and financial performance (ROCE vs WACC)", "owner_role": "Group Strategy", "duration_weeks": 4},
            {"step": "Develop divestiture/exit business cases for bottom-quartile businesses; size value at stake vs holding cost", "owner_role": "Group M&A / FP&A", "duration_weeks": 5},
            {"step": "Engage advisors and run structured M&A/divestiture process for targeted exits; manage data room and buyer due diligence", "owner_role": "Group M&A", "duration_weeks": 20},
            {"step": "Redeploy capital from exits to high-ROCE businesses; track holding cost elimination and capital reallocation", "owner_role": "Group CFO / FP&A", "duration_weeks": 8},
        ],
        "diagnostic_signals": [
            {"signal": "≥2 portfolio businesses with ROCE below WACC for ≥3 consecutive years", "evidence_source": "business_unit_pl_and_roce", "confirms": "Value destruction is ongoing and exit/restructure is economically justified"},
            {"signal": "Corporate holding cost (HQ allocation + intercompany service charges) >5% of revenue for sub-scale businesses", "evidence_source": "recharge_data", "confirms": "Holding cost drag compounds the underperformance"},
            {"signal": "Capital tied in non-core businesses restricting investment in strategic growth engines", "evidence_source": "capital_allocation_review", "confirms": "Portfolio rationalisation will free capital for redeployment"},
        ],
        "required_data_fields": [
            "Business-unit P&L, ROCE, and capital employed (3-year history)",
            "Strategic classification of each business (core / adjacency / non-core)",
            "WACC by business unit and group level",
            "Holding cost allocation (HQ charges, intercompany services) by business",
            "M&A market conditions and indicative valuation for exit candidates",
        ],
    },

    "group_insurance_pooling": {
        "execution_playbook": [
            {"step": "Consolidate insurance inventory across all group entities: policy type, sum insured, premium, insurer, and renewal date", "owner_role": "Group Risk / Finance", "duration_weeks": 3},
            {"step": "Design group master policy (Property All Risk, Group Health, D&O, Marine) with combined limits and aggregation clauses", "owner_role": "Insurance Broker / Group Risk", "duration_weeks": 4},
            {"step": "Run group tender (broker RFP); negotiate combined premium with top-3 insurers using full group exposure data", "owner_role": "Group Procurement / Risk", "duration_weeks": 6},
            {"step": "Consolidate all entities onto group master policy at renewal; track premium savings and claims ratio annually", "owner_role": "Group Finance / Risk", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Same risk class (e.g., property, group health) insured by different insurers across ≥3 group entities at different rates", "evidence_source": "insurance_inventory", "confirms": "Pooling and combined negotiation will capture volume discount"},
            {"signal": "Average group health or property insurance premium >10% above market benchmark for same risk profile", "evidence_source": "broker_benchmarking", "confirms": "Market comparison confirms over-payment"},
            {"signal": "No group-level insurance broker or procurement structure in place", "evidence_source": "insurance_contracts", "confirms": "Centralised procurement will immediately improve negotiating position"},
        ],
        "required_data_fields": [
            "Insurance policy inventory across all group entities (type, sum insured, premium, insurer, renewal)",
            "Claims history by entity and policy type (3 years)",
            "Broker arrangement and brokerage fee disclosure",
            "Benchmark premium rates for equivalent risk profiles from market survey",
            "Group risk register for key insured assets and liabilities",
        ],
    },

    "intercompany_pricing_optimization": {
        "execution_playbook": [
            {"step": "Map all intercompany transactions by BU pair: type (services, goods, IP royalty), volume, and current transfer price", "owner_role": "Group Tax / Transfer Pricing", "duration_weeks": 3},
            {"step": "Benchmark each transaction category against arm's-length range using comparable uncontrolled pricing or TNMM method", "owner_role": "Transfer Pricing Advisor", "duration_weeks": 5},
            {"step": "Redesign TP policy to comply with Ind AS 115 and OECD BEPS Action 13; update intercompany agreements", "owner_role": "Group Tax / Legal", "duration_weeks": 6},
            {"step": "Update ERP intercompany billing configuration to enforce new TP policy; file Form 3CEB and TP documentation", "owner_role": "Group Finance / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Intercompany service charges as % of BU revenue >8% for non-core shared services", "evidence_source": "intercompany_recharge_data", "confirms": "Repricing or scope reduction will reduce cost at receiving BU"},
            {"signal": "Transfer prices not reviewed for >2 years despite changes in group structure or market rates", "evidence_source": "tp_documentation", "confirms": "Benchmarking gap creates TP risk and potential over/under-charging"},
            {"signal": "Tax authority transfer-pricing adjustment or notice in past 3 years", "evidence_source": "tax_compliance_records", "confirms": "TP policy documentation and defence gap is material"},
        ],
        "required_data_fields": [
            "Intercompany transaction register by BU pair (type, volume, price, currency)",
            "Existing intercompany service agreements and royalty agreements",
            "Comparable market benchmarks for each service/IP category",
            "Group structure chart with ownership percentages and jurisdictions",
            "Prior-year Form 3CEB and TP documentation",
        ],
    },

    "real_estate_portfolio_mgmt": {
        "execution_playbook": [
            {"step": "Build group real estate inventory: location, area (sq ft), occupancy, lease terms, WALE, and annual rent/depreciation", "owner_role": "Group Real Estate / Finance", "duration_weeks": 3},
            {"step": "Run space-utilisation sensing (badge/Wi-Fi data or manual survey) to measure actual vs designed occupancy", "owner_role": "Facilities / HR", "duration_weeks": 3},
            {"step": "Prioritise lease exits, subleases, and format changes for under-utilised spaces; target WALE reduction in high-cost locations", "owner_role": "Real Estate / Legal", "duration_weeks": 8},
            {"step": "Execute exits, consolidations, and renegotiations at lease-break or expiry events; implement hybrid-work policy to reduce seat demand", "owner_role": "Group Real Estate", "duration_weeks": 12},
            {"step": "Track cost-per-seat, utilisation rate, and occupancy cost as % of revenue quarterly", "owner_role": "FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Office occupancy rate <60% of designed capacity for ≥6 months post-pandemic baseline", "evidence_source": "space_utilisation_sensing", "confirms": "Consolidation and sublease opportunity is material"},
            {"signal": "Occupancy cost (rent + depreciation) as % of group revenue >2% vs peer benchmark <1.5%", "evidence_source": "gl_by_facility", "confirms": "Real estate cost reduction will materially improve margin"},
            {"signal": "Lease WALE >4 years in locations where headcount has declined >20% over 3 years", "evidence_source": "lease_register_and_headcount_data", "confirms": "Lease-break or sublease strategy will reduce long-term commitment"},
        ],
        "required_data_fields": [
            "Group real estate inventory (location, area, occupancy rate, lease terms, WALE, annual cost)",
            "Space utilisation data by floor/building (badge, Wi-Fi, or survey-based)",
            "Headcount trend by location (3 years)",
            "Lease contracts with break-clause and expiry dates",
            "Sublease market rate benchmarks for key locations",
        ],
    },

    "group_treasury_netting": {
        "execution_playbook": [
            {"step": "Map all intra-group cash flows by currency, BU pair, and frequency; calculate gross vs net settlement requirements", "owner_role": "Group Treasury", "duration_weeks": 3},
            {"step": "Design multi-currency netting centre structure; select netting platform (bank-hosted or in-house); confirm FEMA and RBI compliance", "owner_role": "Group Treasury / Legal / Compliance", "duration_weeks": 5},
            {"step": "Rationalise banking panel—retain top-tier banks for netting hub; close low-volume subsidiary accounts", "owner_role": "Group Treasury / Banking Relations", "duration_weeks": 6},
            {"step": "Go live on netting platform; automate settlement runs (weekly/monthly); track bank fee and FX cost reduction", "owner_role": "Treasury Operations", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Gross intra-group cross-currency settlements >10× net exposure, indicating large gross-to-net compression opportunity", "evidence_source": "treasury_cash_flow_data", "confirms": "Netting will materially reduce FX conversion and bank fees"},
            {"signal": "Number of group bank accounts >50 across entities in same country with separate settlement cycles", "evidence_source": "bank_account_register", "confirms": "Account rationalisation will reduce bank fees and treasury overhead"},
            {"signal": "Bank transaction fees for intra-group transfers >₹1 Cr/year", "evidence_source": "bank_fee_statements", "confirms": "Netting will eliminate most of these fees"},
        ],
        "required_data_fields": [
            "Intra-group cash flow register by BU pair, currency, and frequency (12 months)",
            "Group bank account register with balances, fees, and transaction volumes",
            "FEMA and RBI compliance checklist for netting/pooling structures",
            "FX conversion costs by currency pair and BU",
            "Netting platform vendor options and integration requirements",
        ],
    },

    # -------------------------------------------------------- ENERGY/UTILITIES
    "predictive_maintenance": {
        "execution_playbook": [
            {"step": "Rank assets by criticality (availability impact × replacement cost); instrument top-20 critical assets with vibration, temperature, and oil sensors", "owner_role": "Asset Management / O&M", "duration_weeks": 6},
            {"step": "Build ML predictive models (anomaly detection, remaining useful life) using historian and CMMS data; validate on holdout failure events", "owner_role": "Data Science / O&M", "duration_weeks": 8},
            {"step": "Integrate PdM predictions into CMMS (SAP PM/IBM Maximo); shift maintenance triggers from calendar to condition-based", "owner_role": "CMMS Team / IT", "duration_weeks": 6},
            {"step": "Track OEE improvement, unplanned-outage reduction, and maintenance cost per MW; rebaseline after 6 months", "owner_role": "FP&A / Asset Management", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Unplanned outage rate >5% of planned generation hours for critical rotating equipment", "evidence_source": "cmms_outage_data", "confirms": "Condition-based maintenance will reduce forced outage cost"},
            {"signal": "Preventive maintenance cost >30% of total maintenance budget with >40% of PMs yielding no defect found", "evidence_source": "cmms_maintenance_records", "confirms": "Optimising PM frequency and shifting to PdM will reduce unnecessary maintenance"},
            {"signal": "Mean time between failures declining YoY for pumps, compressors, or transformers", "evidence_source": "asset_failure_history", "confirms": "Asset degradation trend justifies condition-monitoring investment"},
        ],
        "required_data_fields": [
            "Asset criticality register with replacement cost and availability impact",
            "CMMS maintenance history (work orders, failure codes, costs) ≥3 years",
            "Historian/SCADA data for instrumented assets (vibration, temperature, pressure)",
            "Current PM frequency schedule and inspection outcomes",
            "Unplanned outage log with duration and production impact",
        ],
    },

    "energy_loss_reduction": {
        "execution_playbook": [
            {"step": "Conduct AT&C loss audit by distribution zone/feeder: segregate technical (I²R, core) losses from commercial losses (theft, metering error)", "owner_role": "Distribution Engineering", "duration_weeks": 4},
            {"step": "Deploy smart meters and AMI on high-loss feeders; automate DT-level loss monitoring and tamper alerts", "owner_role": "AMI Programme / IT", "duration_weeks": 12},
            {"step": "Execute technical loss reduction projects (conductor reconductoring, capacitor banks, DT loss reduction) on top-10 loss feeders", "owner_role": "Distribution Projects", "duration_weeks": 16},
            {"step": "Enforce anti-theft drive (inspection, metering audit, legal action) for commercial loss feeders >20% loss level", "owner_role": "Vigilance / Revenue Protection", "duration_weeks": 8},
            {"step": "Track AT&C loss monthly by zone; recalibrate DISCOM targets per SERC mandate", "owner_role": "FP&A / Regulatory", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "AT&C loss >15% of energy input indicating material technical or commercial loss above SERC benchmark", "evidence_source": "energy_audit_report", "confirms": "Loss-reduction projects will yield direct cost savings and revenue recovery"},
            {"signal": "Feeder-level loss variance >10 percentage points across distribution zones for similar feeder types", "evidence_source": "feeder_loss_data", "confirms": "Targeted interventions on high-loss feeders will disproportionately reduce system losses"},
            {"signal": "Metering error or billing gap >5% of units sold on high-revenue commercial feeders", "evidence_source": "metering_audit", "confirms": "Metering and billing accuracy correction will recover commercial losses"},
        ],
        "required_data_fields": [
            "Feeder-level energy sent and billed data (12 months)",
            "DT loss audit data by distribution transformer",
            "Conductor specifications and age profile for high-loss feeders",
            "Smart meter installation status and AMI coverage by zone",
            "SERC-mandated AT&C loss reduction targets by year",
        ],
    },

    "fuel_procurement_optimization": {
        "execution_playbook": [
            {"step": "Baseline total fuel spend by type (coal, gas, HFO, diesel); split by spot vs long-term contract volumes and landed cost per unit", "owner_role": "Fuel Procurement / FP&A", "duration_weeks": 3},
            {"step": "Optimise spot vs long-term contract split per fuel type; model hedging ratios against price volatility and generation dispatch schedule", "owner_role": "Fuel Procurement / Treasury", "duration_weeks": 4},
            {"step": "Consolidate logistics (rail, road, port) to reduce handling cost per unit; negotiate long-term contracts with top-3 fuel suppliers", "owner_role": "Fuel Procurement / Logistics", "duration_weeks": 8},
            {"step": "Implement fuel management system for real-time inventory and consumption tracking; enforce GCV/quality reconciliation", "owner_role": "Plant Operations / IT", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Fuel cost per unit generated >10% above comparable plant benchmark for same technology and fuel type", "evidence_source": "plant_benchmarking", "confirms": "Procurement and logistics optimisation will reduce landed fuel cost"},
            {"signal": "Spot market fuel purchases >40% of total volume in a volatile price environment", "evidence_source": "fuel_procurement_data", "confirms": "Increasing long-term contract coverage will reduce price risk and average cost"},
            {"signal": "GCV (Gross Calorific Value) shortfall vs contracted specification >3% on coal deliveries", "evidence_source": "fuel_quality_monitoring", "confirms": "Quality enforcement and rebate recovery will reduce effective fuel cost"},
        ],
        "required_data_fields": [
            "Fuel procurement data: type, volume, price, source, and logistics cost (24 months)",
            "Spot vs long-term contract volume split and price comparison",
            "GCV measurement data by delivery consignment",
            "Generation dispatch schedule and fuel consumption plan",
            "Market price forecasts and hedging policy",
        ],
    },

    "workforce_scheduling": {
        "execution_playbook": [
            {"step": "Map plant and field maintenance outage calendar; baseline current shift patterns, overtime spend, and contractor utilisation by skill category", "owner_role": "HR / O&M Planning", "duration_weeks": 3},
            {"step": "Deploy workforce management software with skills-based scheduling and outage-linked demand forecasting", "owner_role": "HR / IT", "duration_weeks": 6},
            {"step": "Optimise shift patterns and reduce unplanned overtime by scheduling against maintenance demand windows, not calendar", "owner_role": "Operations Manager", "duration_weeks": 4},
            {"step": "Convert recurring maintenance contractor work to in-house where skill is available; track productivity per crew per shift", "owner_role": "HR / FP&A", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Overtime as % of total labour cost >15% for field and maintenance workforce", "evidence_source": "payroll_data", "confirms": "Scheduling inefficiency is driving avoidable premium pay"},
            {"signal": "Contractor utilisation in maintenance >40% for activities where in-house skills are available", "evidence_source": "contractor_spend_and_hr_skills_matrix", "confirms": "In-sourcing recurring maintenance will reduce per-unit cost"},
            {"signal": "Unplanned call-outs >20% of total maintenance work orders", "evidence_source": "cmms_work_order_data", "confirms": "Improved scheduling and PdM will reduce emergency response cost"},
        ],
        "required_data_fields": [
            "Workforce headcount by skill category and shift pattern",
            "Overtime and call-out records by team and month (12 months)",
            "Maintenance contractor spend by activity and skill category",
            "Plant outage and maintenance schedule (annual)",
            "Skills matrix for in-house workforce",
        ],
    },

    "grid_modernization": {
        "execution_playbook": [
            {"step": "Conduct grid topology audit: age profile of key assets (transformers, cables, substations) and SAIDI/SAIFI reliability metrics by zone", "owner_role": "Network Planning / Engineering", "duration_weeks": 4},
            {"step": "Develop SCADA/DMS/AMI upgrade roadmap prioritised by loss reduction and reliability impact; obtain CERC/SERC capex approval", "owner_role": "Network Planning / Regulatory", "duration_weeks": 6},
            {"step": "Execute AMI rollout on priority feeders; deploy demand-response management to shift peak load and reduce peak procurement cost", "owner_role": "AMI Programme / Smart Grid", "duration_weeks": 20},
            {"step": "Track SAIDI/SAIFI improvement, peak demand reduction, and O&M cost savings vs capex deployed; report to board", "owner_role": "FP&A / Regulatory", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "SAIDI >300 minutes/year or SAIFI >15 interruptions/year for distribution network", "evidence_source": "reliability_reports", "confirms": "Grid investment will reduce penalty exposure and improve cost of supply"},
            {"signal": "Network assets >25 years old representing >30% of transformer/cable base", "evidence_source": "asset_age_profile", "confirms": "Ageing infrastructure drives O&M cost and outage risk"},
            {"signal": "Peak demand >15% above average demand with procurement premium for peak power", "evidence_source": "load_profile_data", "confirms": "Demand response and AMI will reduce peak procurement cost"},
        ],
        "required_data_fields": [
            "Network asset register with age, condition rating, and replacement cost",
            "SAIDI/SAIFI reliability metrics by zone and feeder (3 years)",
            "Load profile data by feeder and time of day",
            "SCADA/DMS/AMI coverage and technology roadmap",
            "CERC/SERC capex approval requirements and timelines",
        ],
    },

    "renewable_energy_transition": {
        "execution_playbook": [
            {"step": "Map renewable energy capacity requirements vs RPO mandate; compare PPA vs capex route for solar/wind by site", "owner_role": "Renewable Energy / Strategy", "duration_weeks": 4},
            {"step": "Negotiate long-term solar/wind PPAs at competitive tariffs; obtain CERC/SERC approval for captive or open-access power", "owner_role": "Regulatory Affairs / Procurement", "duration_weeks": 8},
            {"step": "Execute preferred RE integration route (PPA or capex); manage grid-connection agreement with SLDC/RLDC", "owner_role": "Renewable Energy Programme", "duration_weeks": 16},
            {"step": "Track RE share of generation mix, fuel cost displaced, and RPO compliance position quarterly", "owner_role": "FP&A / Regulatory", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Thermal fuel cost per unit generated >₹4/kWh vs solar/wind LCOE <₹2.5/kWh in target region", "evidence_source": "generation_cost_data", "confirms": "RE transition will yield material reduction in variable generation cost"},
            {"signal": "RPO compliance shortfall >5 percentage points vs state mandate, creating penalty risk", "evidence_source": "rpo_compliance_report", "confirms": "RE transition is both cost and regulatory-risk driven"},
            {"signal": "Grid connectivity and land availability confirmed for ≥50 MW renewable capacity in low-cost wind/solar zones", "evidence_source": "site_feasibility_study", "confirms": "Physical constraints are manageable for RE transition"},
        ],
        "required_data_fields": [
            "Current generation mix: thermal, hydro, and RE capacity and cost",
            "RPO mandate and current compliance position",
            "Solar/wind resource maps and LCOE estimates by site",
            "Grid connectivity assessments and SLDC/RLDC requirements",
            "Existing PPA terms and renewal schedule",
        ],
    },

    "outsourced_operations": {
        "execution_playbook": [
            {"step": "Define O&M scope for outsourcing candidates (common in distribution, project O&M, renewable sites); benchmark current cost per MW", "owner_role": "O&M Head / Strategy", "duration_weeks": 3},
            {"step": "Develop performance-based SLA framework (availability, heat rate, SAIDI targets); run competitive RFP with leading O&M vendors", "owner_role": "Procurement / Engineering", "duration_weeks": 6},
            {"step": "Negotiate SLA-linked contracts with risk-sharing provisions; transition in-house team to vendor with TUPE-equivalent provisions", "owner_role": "HR / Legal / Procurement", "duration_weeks": 8},
            {"step": "Establish vendor performance review cadence; track cost per MW, availability, and SLA penalties monthly", "owner_role": "Asset Management / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "In-house O&M cost per MW >15% above comparable outsourced benchmark for similar plant type", "evidence_source": "plant_cost_benchmarking", "confirms": "Outsourcing will reduce operating cost"},
            {"signal": "In-house maintenance team utilisation <70% due to lumpy maintenance demand and seasonal plant profile", "evidence_source": "workforce_utilisation_data", "confirms": "Specialised vendor with multi-site scale will improve resource efficiency"},
            {"signal": "Plant availability below contractual requirement with current in-house model", "evidence_source": "plant_availability_log", "confirms": "Performance-based SLA with specialist vendor will improve output"},
        ],
        "required_data_fields": [
            "Plant O&M cost per MW by plant type and age",
            "Current in-house team size, skills, and utilisation",
            "Availability and heat rate performance vs design parameters",
            "Competitive landscape of O&M service providers",
            "Existing O&M contracts and SLA performance data",
        ],
    },

    "material_inventory_optimization": {
        "execution_playbook": [
            {"step": "Classify MRO/spares inventory using ABC (value) and XYZ (criticality) analysis; identify slow-moving and obsolete items", "owner_role": "Stores / Asset Management", "duration_weeks": 3},
            {"step": "Implement vendor-managed inventory for fast-moving, non-critical spares with top-5 MRO vendors", "owner_role": "Procurement / Stores", "duration_weeks": 6},
            {"step": "Redesign reorder-point and safety-stock formulas using lead-time and outage-risk data; reduce overstock for slow-moving critical items", "owner_role": "Supply Chain / Asset Management", "duration_weeks": 4},
            {"step": "Run spares rationalisation auction for obsolete inventory; reinvest proceeds into high-criticality spares buffer", "owner_role": "Stores / Finance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "MRO inventory days-on-hand >180 days vs benchmark <90 days for comparable plant type", "evidence_source": "inventory_aging_report", "confirms": "Working capital tied in excess inventory is material"},
            {"signal": "Obsolete or slow-moving spares >20% of total inventory value with no consumption in >12 months", "evidence_source": "stores_data", "confirms": "Write-down risk and storage cost reduction opportunity exists"},
            {"signal": "Emergency procurement (spot market) events >10/year for items in OEM-recommended critical spares list", "evidence_source": "procurement_records", "confirms": "Safety-stock redesign will reduce premium emergency procurement cost"},
        ],
        "required_data_fields": [
            "MRO inventory register with value, criticality, and last-consumption date",
            "OEM-recommended critical spares list by asset type",
            "Historical material consumption data (3 years)",
            "Lead times by vendor and item category",
            "Emergency procurement log with premium cost data",
        ],
    },

    # ------------------------------------------------------ FINANCIAL SVC NON-BANK
    "fund_administration_consolidation": {
        "execution_playbook": [
            {"step": "Map current fund administration footprint: administrators, scope, AUM served, fee schedule, and contract term per fund", "owner_role": "COO / Fund Operations", "duration_weeks": 3},
            {"step": "Benchmark total administration cost (bps on AUM) vs industry median; identify consolidation candidates by administrator quality and cost", "owner_role": "Finance / Operations", "duration_weeks": 3},
            {"step": "Run competitive RFP for consolidated fund administration mandate; negotiate tiered fee schedule tied to AUM growth", "owner_role": "Procurement / COO", "duration_weeks": 8},
            {"step": "Execute migration in fund-by-fund waves; validate NAV accuracy and SEBI/AMFI reporting continuity throughout transition", "owner_role": "Fund Operations / Compliance", "duration_weeks": 12},
        ],
        "diagnostic_signals": [
            {"signal": "Fund administration cost (bps on AUM) >1.5× peer median for equivalent AUM scale and fund complexity", "evidence_source": "cost_benchmarking", "confirms": "Consolidation to a lower-cost administrator will reduce ongoing cost"},
            {"signal": "Multiple fund administrators (>3) with duplicated onboarding, compliance, and reporting overhead", "evidence_source": "fund_admin_inventory", "confirms": "Consolidation will reduce fixed overhead and improve scale economics"},
            {"signal": "NAV error rate or restatement events >2 per year with current administrator", "evidence_source": "operations_quality_log", "confirms": "Quality improvement case supports migration to higher-capability administrator"},
        ],
        "required_data_fields": [
            "Fund administration cost by fund and administrator (bps and absolute ₹)",
            "AUM by fund and administrator",
            "Contract terms, SLA, and break-clause provisions",
            "NAV error/restatement history",
            "SEBI/AMFI compliance requirement mapping",
        ],
    },

    "trading_technology_optimization": {
        "execution_playbook": [
            {"step": "Audit trading technology stack: OMS, EMS, market data, connectivity, and co-location costs; map to actual usage and trading volume", "owner_role": "CTO / Head of Trading", "duration_weeks": 3},
            {"step": "Conduct broker TCA (Transaction Cost Analysis) for top-20 brokers; identify underperforming brokers vs execution cost", "owner_role": "Trading / Finance", "duration_weeks": 4},
            {"step": "Rationalise OMS/EMS platforms to single consolidated system; negotiate multi-asset market data contract vs single-feed providers", "owner_role": "CTO / Procurement", "duration_weeks": 8},
            {"step": "Optimise co-location and connectivity footprint; track commission spend per broker against execution quality metrics", "owner_role": "Head of Trading / Finance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Trading technology cost (OMS, market data, connectivity) >5 bps of AUM vs benchmark <3 bps", "evidence_source": "technology_cost_report", "confirms": "Platform rationalisation will reduce per-AUM technology cost"},
            {"signal": "Redundant OMS/EMS platforms or market-data feeds for the same asset class", "evidence_source": "technology_landscape_assessment", "confirms": "Consolidation will eliminate duplication"},
            {"signal": "Broker commission paid to bottom-5 brokers generating >20% of total commission with below-median execution quality", "evidence_source": "broker_tca_report", "confirms": "Broker panel rationalisation will improve cost and execution quality"},
        ],
        "required_data_fields": [
            "Trading technology cost inventory (OMS, EMS, market data, co-location, connectivity)",
            "Broker commission data by broker (12 months) with execution quality metrics",
            "Trading volume by asset class and broker",
            "OMS/EMS vendor contracts and SLAs",
            "TCA analysis output for top-20 brokers",
        ],
    },

    "compliance_automation": {
        "execution_playbook": [
            {"step": "Inventory all SEBI/IRDAI/RBI regulatory obligations: return frequency, data source, FTE-hours, and manual touchpoints per obligation", "owner_role": "Chief Compliance Officer", "duration_weeks": 3},
            {"step": "Select RegTech platform for compliance workflow automation; confirm SEBI technical specifications for digital filing", "owner_role": "Compliance / IT", "duration_weeks": 4},
            {"step": "Automate high-frequency returns (daily/weekly NAV, portfolio disclosure, AUM reporting) in Phase 1; quarterly filings in Phase 2", "owner_role": "IT Delivery / Compliance", "duration_weeks": 10},
            {"step": "Run parallel filing for one quarter; obtain internal-audit sign-off and submit first automated return to SEBI/IRDAI", "owner_role": "Compliance / IT", "duration_weeks": 6},
            {"step": "Decommission manual filing process; track FTE release, error rate, and on-time submission rate", "owner_role": "FP&A / Compliance", "duration_weeks": 3},
        ],
        "diagnostic_signals": [
            {"signal": "Compliance team >10 FTEs with >60% of time on data extraction and regulatory report preparation", "evidence_source": "compliance_ops_time_study", "confirms": "Automation will release FTE capacity and reduce compliance cost"},
            {"signal": "Late or restated regulatory filings ≥2 in the past year due to data or formatting errors", "evidence_source": "regulatory_submission_log", "confirms": "Automation will reduce compliance risk"},
            {"signal": "Number of SEBI/IRDAI returns >20 with data sourced from ≥5 systems requiring manual reconciliation", "evidence_source": "return_inventory", "confirms": "Integration and automation investment is justified"},
        ],
        "required_data_fields": [
            "Regulatory return inventory (name, regulator, frequency, source systems, FTE-hours)",
            "Compliance team FTE count and time allocation per return",
            "RegTech vendor landscape and integration requirements",
            "Late/restated filing history with root cause",
            "SEBI/IRDAI technical specification for digital filing",
        ],
    },

    "performance_attribution_tech": {
        "execution_playbook": [
            {"step": "Audit current performance attribution system: coverage (funds, asset classes), calculation frequency, and reporting latency", "owner_role": "Head of Performance / Operations", "duration_weeks": 3},
            {"step": "Benchmark attribution vendor options vs current system on cost, coverage, and integration capability with portfolio management system", "owner_role": "IT / Finance", "duration_weeks": 4},
            {"step": "Migrate to consolidated attribution platform; integrate with OMS and portfolio management system for automated data feed", "owner_role": "IT Delivery", "duration_weeks": 10},
            {"step": "Automate daily attribution report generation and distribution to portfolio managers and clients; decommission manual reporting", "owner_role": "Performance / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Performance attribution reporting prepared manually for >50% of funds, consuming >3 FTE-days per quarter", "evidence_source": "performance_ops_time_study", "confirms": "Automation will materially reduce performance reporting cost"},
            {"signal": "Attribution system covers <80% of AUM by asset class (e.g., fixed income or alternatives not covered)", "evidence_source": "attribution_coverage_assessment", "confirms": "Expanded platform will close coverage gaps and improve reporting quality"},
            {"signal": "Client or regulator queries on performance discrepancies >5/quarter due to attribution methodology inconsistencies", "evidence_source": "client_service_log", "confirms": "Standardised automated attribution will reduce exceptions and reputational risk"},
        ],
        "required_data_fields": [
            "AUM by fund and asset class with attribution coverage status",
            "Current attribution system cost and FTE overhead",
            "Performance attribution vendor options and pricing",
            "OMS and portfolio management system integration architecture",
            "Client reporting SLA requirements",
        ],
    },

    "research_cost_management": {
        "execution_playbook": [
            {"step": "Audit research consumption under MiFID II/SEBI framework: identify all research providers, vote allocation, and annual spend by fund", "owner_role": "Head of Research / Compliance", "duration_weeks": 3},
            {"step": "Assess research quality and utilisation per provider using portfolio manager feedback and vote data; identify low-utilisation providers", "owner_role": "Investment Team / Finance", "duration_weeks": 4},
            {"step": "Rationalise research provider panel from bottom; consolidate budget to highest-value providers; negotiate direct pricing vs CSA", "owner_role": "Procurement / Head of Research", "duration_weeks": 6},
            {"step": "Implement research management platform to track consumption vs budget; enforce per-fund research budget allocation", "owner_role": "Finance / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Research budget per AUM >3 bps vs fund industry median for equivalent strategy complexity", "evidence_source": "research_cost_report", "confirms": "Research spend rationalisation will improve cost efficiency without compromising investment quality"},
            {"signal": "Research provider panel >20 firms with bottom-5 providers receiving <5% of votes but same contract structure", "evidence_source": "broker_vote_report", "confirms": "Panel rationalisation will improve leverage and reduce admin overhead"},
            {"signal": "Research consumption not systematically tracked per fund making budget accountability difficult", "evidence_source": "research_management_review", "confirms": "Implementing research management platform will improve cost governance"},
        ],
        "required_data_fields": [
            "Research cost by provider and fund (12 months)",
            "Broker vote allocation data",
            "Portfolio manager research utilisation and feedback by provider",
            "MiFID II/SEBI compliance framework for research payments",
            "Research management platform options and integration requirements",
        ],
    },

    # --------------------------------------------------------------- FMCG
    "cogs_direct_materials": {
        "execution_playbook": [
            {"step": "Conduct BOM review for top-20 SKUs by revenue: map every material input to specification, supplier, price, and YoY cost trend", "owner_role": "Supply Chain / Procurement", "duration_weeks": 4},
            {"step": "Build should-cost models for primary material categories using commodity indices and benchmark specs; identify formulation trade-offs", "owner_role": "R&D / Strategic Sourcing", "duration_weeks": 4},
            {"step": "Qualify 1–2 alternative suppliers per key material; run competitive RFQ with incumbent vs alternative to establish negotiation tension", "owner_role": "Procurement / Supplier Quality", "duration_weeks": 8},
            {"step": "Lock 12–18 month pricing agreements with indexed reopeners; implement material cost variance reporting in monthly S&OP", "owner_role": "Procurement / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Key material cost as % of net sales >45% vs category benchmark indicating formulation or procurement gap", "evidence_source": "cogs_breakdown", "confirms": "Direct materials savings pool is material"},
            {"signal": "Single-source supply dependency for >30% of material value creating pricing leverage for supplier", "evidence_source": "supply_risk_assessment", "confirms": "Dual-sourcing will restore competitive tension and reduce cost"},
            {"signal": "Material price variance unfavourable >5% for ≥3 consecutive quarters vs plan", "evidence_source": "material_price_variance_report", "confirms": "Procurement strategy or hedging requires reset"},
        ],
        "required_data_fields": [
            "Bill of materials for top-20 revenue SKUs with quantity per unit and unit prices",
            "Material cost trend data (24 months) by input category",
            "Supplier concentration data (number of qualified sources per key material)",
            "Commodity price indices for key materials",
            "Formulation specification constraints from R&D",
        ],
    },

    "sku_rationalization": {
        "execution_playbook": [
            {"step": "Build SKU-level P&L for all active SKUs: net revenue, variable COGS, and contribution margin; flag SKUs with margin <5% or volume <5 units/day", "owner_role": "FP&A / Category Management", "duration_weeks": 3},
            {"step": "Validate rationalization candidates against consumer need (cover unique consumption occasion) and retailer requirements before delisting", "owner_role": "Category / Sales / Marketing", "duration_weeks": 4},
            {"step": "Develop delisting plan with retailer communication, inventory liquidation, and production run-out schedule", "owner_role": "Sales / Supply Chain", "duration_weeks": 6},
            {"step": "Track manufacturing complexity reduction (changeover time, run length), working capital improvement, and margin uplift post-rationalisation", "owner_role": "FP&A / Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "SKU count in category >2× nearest competitor with ≥20% of SKUs contributing <2% of category revenue", "evidence_source": "sku_revenue_report", "confirms": "Long-tail SKUs are adding complexity cost without proportionate revenue contribution"},
            {"signal": "Average production run length <50% of minimum economic run due to SKU proliferation-driven changeovers", "evidence_source": "manufacturing_schedule_data", "confirms": "SKU rationalisation will improve manufacturing efficiency"},
            {"signal": "New SKU launch success rate <40% (measured 12 months post-launch vs plan), indicating proliferation is not creating value", "evidence_source": "innovation_tracker", "confirms": "Focused portfolio strategy will improve ROII"},
        ],
        "required_data_fields": [
            "SKU-level net revenue, volume, and contribution margin (12 months)",
            "Manufacturing setup/changeover data by SKU and line",
            "Retailer ranging and space allocation by SKU",
            "Consumer research on SKU redundancy within portfolio",
            "Inventory level and days-on-hand by SKU",
        ],
    },

    "pricing_architecture": {
        "execution_playbook": [
            {"step": "Build price-value waterfall by SKU and channel: map RSP → distributor margin → trade promotion → net realisation → contribution", "owner_role": "Revenue Management / FP&A", "duration_weeks": 3},
            {"step": "Identify price-pack architecture gaps vs competition; model consumer price elasticity by segment and channel", "owner_role": "Revenue Management / Marketing", "duration_weeks": 4},
            {"step": "Redesign pricing architecture with clear price-pack ladders; eliminate value-destructive promotions with <80% efficiency", "owner_role": "Revenue Management / Sales", "duration_weeks": 6},
            {"step": "Implement pricing governance: price realisation dashboard, promotion approval threshold, and monthly price-mix bridge", "owner_role": "FP&A / Revenue Management", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Net price realisation declining despite list-price increases due to growing trade promotion as % of gross sales", "evidence_source": "revenue_waterfall", "confirms": "Promotion efficiency and architecture review will improve net price"},
            {"signal": "Promotion return on investment <80 paise per rupee of investment for >30% of trade promotions", "evidence_source": "trade_promotion_analytics", "confirms": "Eliminating/redesigning low-ROI promotions will improve contribution"},
            {"signal": "Price gaps vs key competitors narrowing in premium segments where brand premiumisation is the strategy", "evidence_source": "market_pricing_data", "confirms": "Pricing architecture adjustment will protect premiumisation strategy"},
        ],
        "required_data_fields": [
            "SKU-level gross sales, trade promotion, and net sales waterfall by channel",
            "Promotion ROI data by promotion type and channel",
            "Competitor RSP and price-pack architecture by segment",
            "Consumer price sensitivity research by segment",
            "Channel margin structure (distributor, retailer) by format",
        ],
    },

    "trade_terms_optimization": {
        "execution_playbook": [
            {"step": "Audit current trade terms by channel and distributor class: primary discount, secondary schemes, credit period, and total trade spend %", "owner_role": "Sales Finance / FP&A", "duration_weeks": 3},
            {"step": "Benchmark trade terms against category norms and key account negotiation data; build terms simplification model", "owner_role": "Key Accounts / Sales Finance", "duration_weeks": 4},
            {"step": "Redesign trade terms with fewer schemes, performance-linked payouts, and shorter credit periods; pilot with mid-tier distributors first", "owner_role": "National Sales Head / Finance", "duration_weeks": 8},
            {"step": "Roll out new terms structure; track trade spend as % of net sales, DSO, and distributor profitability quarterly", "owner_role": "FP&A / Sales Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Total trade spend (primary + secondary schemes) >12% of gross sales vs FMCG benchmark of <10%", "evidence_source": "trade_spend_report", "confirms": "Trade terms rationalisation will improve net realisation"},
            {"signal": "Number of active trade schemes >20 per quarter creating complexity and leakage", "evidence_source": "scheme_master", "confirms": "Scheme simplification will reduce administrative cost and misclassification risk"},
            {"signal": "Distributor credit period >45 days with receivables overdue >30 days representing >10% of outstanding", "evidence_source": "accounts_receivable_aging", "confirms": "Credit term tightening will improve working capital and bad-debt risk"},
        ],
        "required_data_fields": [
            "Trade spend breakdown by channel and scheme type (primary/secondary)",
            "Distributor margin structure and credit terms by class of trade",
            "Days Sales Outstanding (DSO) by channel and key account",
            "Scheme ROI data (sales lift vs scheme cost)",
            "Competitor trade terms benchmark (qualitative/channel insights)",
        ],
    },

    "warehouse_automation": {
        "execution_playbook": [
            {"step": "Map current warehouse operations: inbound, storage, pick-pack, and outbound; measure labour hours, error rate, and cost per case picked", "owner_role": "Supply Chain / Warehouse Ops", "duration_weeks": 3},
            {"step": "Build automation ROI model (ASRS, conveyor, sorting, WMS) based on volume, SKU count, and labour cost; compare against greenfield vs retrofit", "owner_role": "Supply Chain Strategy / Finance", "duration_weeks": 4},
            {"step": "Select technology vendor; execute WMS upgrade and automation equipment deployment in waves starting with highest-volume fulfilment centre", "owner_role": "Supply Chain / IT / Projects", "duration_weeks": 16},
            {"step": "Track throughput per hour, error rate (pick accuracy), and cost per case picked post-automation; rebaseline annually", "owner_role": "FP&A / Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Labour cost as % of total warehouse cost >50% with cost per case picked >₹8 vs automated benchmark <₹4", "evidence_source": "warehouse_cost_report", "confirms": "Automation ROI is positive on 3-year DCF basis"},
            {"signal": "Pick error rate >0.5% generating downstream returns and customer service cost", "evidence_source": "warehouse_quality_report", "confirms": "Automation will reduce error-related cost and improve service level"},
            {"signal": "Warehouse capacity utilisation >90% seasonally constraining fulfilment throughput", "evidence_source": "warehouse_capacity_report", "confirms": "Automation and space optimisation will extend throughput without additional sq ft"},
        ],
        "required_data_fields": [
            "Warehouse labour cost and FTE count by facility and operation type",
            "Throughput data: orders per day, cases per picker-hour, and peak vs average volume",
            "Pick error and returns rate by SKU category",
            "Warehouse footprint and lease terms by facility",
            "Automation technology vendor options and capex estimates",
        ],
    },

    "mode_shift_logistics": {
        "execution_playbook": [
            {"step": "Baseline freight spend by mode (road, rail, air, sea) and lane; calculate cost per tonne-km and transit time by mode", "owner_role": "Logistics / Procurement", "duration_weeks": 3},
            {"step": "Model modal shift feasibility by lane: rail vs road for >800 km lanes, coastal shipping for port-to-port, air-to-surface for non-urgent loads", "owner_role": "Supply Chain / Finance", "duration_weeks": 4},
            {"step": "Negotiate long-term contracts with rail (CONCOR/private) and coastal shipping operators; optimise carrier mix per lane", "owner_role": "Logistics Procurement", "duration_weeks": 8},
            {"step": "Track freight cost per tonne-km, modal split, transit time, and OTIF by lane monthly", "owner_role": "FP&A / Logistics", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Air or premium express freight >10% of total freight spend for non-time-sensitive loads", "evidence_source": "freight_spend_by_mode", "confirms": "Mode shift to surface/rail will reduce freight cost without impacting service"},
            {"signal": "Road freight on lanes >800 km where rail alternative exists and service level is acceptable", "evidence_source": "lane_analysis", "confirms": "Rail or coastal modal shift will reduce cost per tonne-km by 30-50%"},
            {"signal": "Freight cost as % of net sales trending upward for ≥3 consecutive quarters", "evidence_source": "freight_cost_trend", "confirms": "Structural review of logistics network and mode mix is required"},
        ],
        "required_data_fields": [
            "Freight spend by mode, lane, and carrier (12 months)",
            "Volume (tonnes) and transit time by lane and mode",
            "Rail/coastal shipping network connectivity to key origin-destination pairs",
            "Carrier rate cards and contract terms by mode",
            "Inventory holding cost and service-level trade-off data",
        ],
    },

    "private_label_expansion": {
        "execution_playbook": [
            {"step": "Map category white space: identify segments where private label penetration <10% and competitor PL or NBD is gaining share", "owner_role": "Category Management / Marketing", "duration_weeks": 3},
            {"step": "Qualify manufacturers for PL production: supplier audit, GMP compliance, formulation capability, and exclusivity terms", "owner_role": "Procurement / Quality", "duration_weeks": 5},
            {"step": "Launch PL range in pilot stores (>20 stores) with consumer testing panel; track consumer acceptance vs brand alternative", "owner_role": "Category / Supply Chain", "duration_weeks": 8},
            {"step": "Scale to full chain; track PL penetration, category margin uplift, and branded manufacturer response", "owner_role": "Category / FP&A", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Category gross margin <25% with private label equivalent achievable at >35% margin on same shelf", "evidence_source": "category_margin_report", "confirms": "Private label will structurally improve category margin mix"},
            {"signal": "Private label penetration in category <15% vs modern trade benchmark of >25% in comparable markets", "evidence_source": "category_benchmarking", "confirms": "PL expansion headroom is material"},
            {"signal": "Consumer willingness to trade down confirmed by market research for this category", "evidence_source": "consumer_research", "confirms": "PL launch risk is manageable"},
        ],
        "required_data_fields": [
            "Category margin data by brand and pack size",
            "Private label penetration by category and store format",
            "Consumer research on PL acceptance by category",
            "Manufacturer shortlist with capacity and compliance data",
            "Competitor PL pricing and ranging data",
        ],
    },

    "demand_planning_accuracy": {
        "execution_playbook": [
            {"step": "Measure current forecast accuracy (MAPE, bias) by SKU and channel vs benchmark; identify root causes of forecast error", "owner_role": "Supply Chain / Demand Planning", "duration_weeks": 3},
            {"step": "Implement statistical forecasting model (ARIMA/ML) for top-80% revenue SKUs; integrate sell-in and sell-out data from key retailers", "owner_role": "Supply Chain IT / Analytics", "duration_weeks": 6},
            {"step": "Redesign S&OP process: weekly demand review with commercial inputs, 13-week rolling forecast, and agreed consensus number", "owner_role": "Supply Chain / Sales / Finance", "duration_weeks": 4},
            {"step": "Track MAPE improvement, excess inventory reduction, and OTIF; reward commercial team on forecast accuracy alongside volume", "owner_role": "FP&A / Supply Chain", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Weighted MAPE >30% for top-50 SKUs indicating significant forecast error and resulting inventory/service trade-off", "evidence_source": "demand_planning_metrics", "confirms": "Improved forecasting will reduce safety stock requirement and excess inventory write-off"},
            {"signal": "Excess and obsolete inventory write-off >1% of net sales annually due to overforecasting", "evidence_source": "inventory_write_off_data", "confirms": "Forecast improvement will directly reduce write-off cost"},
            {"signal": "OTIF (On Time In Full) <95% due to demand-supply mismatch driven by poor forecast accuracy", "evidence_source": "customer_service_data", "confirms": "Better planning will improve service level without incremental inventory"},
        ],
        "required_data_fields": [
            "SKU-level forecast vs actual data (12 months) with MAPE and bias calculation",
            "Excess and obsolete inventory write-off by SKU and cause",
            "Sell-out data from key retail accounts or Nielsen/IRI",
            "S&OP meeting cadence and consensus forecast process description",
            "Safety stock policy and inventory days-on-hand by SKU",
        ],
    },

    "assortment_optimization": {
        "execution_playbook": [
            {"step": "Build planogram analysis for top-20% stores by revenue: map space allocation vs space-to-sales ratio by SKU and category", "owner_role": "Category Management / Sales", "duration_weeks": 3},
            {"step": "Identify ranging inefficiencies: under-ranged high-demand SKUs and over-spaced slow-movers; model impact of rebalancing", "owner_role": "Category / Supply Chain", "duration_weeks": 4},
            {"step": "Negotiate category captain agreements with key suppliers for planogram execution support; implement ranging decisions by store format", "owner_role": "Key Accounts / Category", "duration_weeks": 8},
            {"step": "Track sales per sq ft uplift, in-stock rate, and category profitability improvement post-range change", "owner_role": "FP&A / Category", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Sales per sq ft below category benchmark for ≥30% of floor space allocation", "evidence_source": "planogram_data_and_sales", "confirms": "Space rebalancing will improve category return per sq ft"},
            {"signal": "Out-of-stock rate >5% for top-50 SKUs while slow-movers occupy allocated space", "evidence_source": "in_stock_monitoring", "confirms": "Assortment rebalancing will improve in-stock rate and consumer basket value"},
            {"signal": "Category profitability below retailer target for ≥2 consecutive quarters despite adequate sales", "evidence_source": "category_review_data", "confirms": "Assortment mix shift to higher-margin SKUs will improve category profit"},
        ],
        "required_data_fields": [
            "SKU-level sales per sq ft by store format and location",
            "Planogram space allocation by SKU and category",
            "In-stock (OSA) monitoring data by SKU and store",
            "Category margin by SKU and pack size",
            "Consumer basket composition and cross-purchase data",
        ],
    },

    # -------------------------------------------------- GCC CAPABILITY CENTERS
    "rpa_intelligent_automation": {
        "execution_playbook": [
            {"step": "Run process discovery sessions across F&A, HR ops, and IT service desk; rank automation candidates by volume × handling time × error rate", "owner_role": "Automation CoE", "duration_weeks": 3},
            {"step": "Establish CoE governance: bot ownership model, security standards, change management, and exception-handling SLA", "owner_role": "CTO / Automation CoE", "duration_weeks": 3},
            {"step": "Build and deploy Wave 1 bots (F&A reconciliation, HR onboarding, IT ticket routing); run parallel for 2 weeks before cutover", "owner_role": "IT Delivery / Automation CoE", "duration_weeks": 10},
            {"step": "Scale to Wave 2 (invoice processing, payroll audit, report generation); decommission manual processes; track FTE release", "owner_role": "Automation CoE / FP&A", "duration_weeks": 8},
        ],
        "diagnostic_signals": [
            {"signal": "High-volume repeatable processes (>500 transactions/day) with manual touchpoints >60% and error rate >2%", "evidence_source": "process_mining_output", "confirms": "RPA automation ROI positive within 12 months"},
            {"signal": "FTE effort on rule-based tasks >30% of total FTE capacity in F&A or HR ops functions", "evidence_source": "time_and_motion_study", "confirms": "Automation will release FTE capacity for higher-value work"},
            {"signal": "Technology landscape includes ERP (SAP/Oracle) and ITSM (ServiceNow) with accessible APIs or UI layers for bot integration", "evidence_source": "it_landscape_assessment", "confirms": "Technical feasibility for RPA deployment is confirmed"},
        ],
        "required_data_fields": [
            "Process inventory with transaction volumes, FTE-hours, error rates, and system touchpoints",
            "IT application landscape with API/UI accessibility assessment",
            "CoE governance model and bot ownership framework",
            "Security and data-privacy requirements for automated processes",
            "FTE cost by function and process to calculate automation ROI",
        ],
    },

    "attrition_reduction_retention": {
        "execution_playbook": [
            {"step": "Analyse attrition data by band, function, tenure cohort, and manager to identify root causes (compensation, career, manager quality)", "owner_role": "HRBP / People Analytics", "duration_weeks": 3},
            {"step": "Benchmark total compensation (base + variable + benefits) against NASSCOM/Aon Hewitt survey data by role and experience band", "owner_role": "Rewards / HR", "duration_weeks": 3},
            {"step": "Design and implement retention interventions: compensation correction for at-risk bands, career path transparency, and manager effectiveness program", "owner_role": "CHRO / HRBP", "duration_weeks": 8},
            {"step": "Track attrition rate by band monthly; measure regression (3-year attrition cost: recruitment + training + productivity ramp)", "owner_role": "FP&A / HR", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Attrition rate >20% for mid-level (L3–L5) employees where replacement cost is 1.5× annual CTC", "evidence_source": "hr_attrition_data", "confirms": "Retention improvement will yield significant avoidable recruitment and onboarding cost"},
            {"signal": "Exit survey data: compensation or career growth cited by >40% of voluntary leavers", "evidence_source": "exit_survey_data", "confirms": "Targeted compensation and career intervention will address primary attrition drivers"},
            {"signal": "Bench and training cost >8% of total payroll due to high replacement cycle", "evidence_source": "hr_cost_breakdown", "confirms": "Reducing attrition rate will directly lower training and bench cost"},
        ],
        "required_data_fields": [
            "Attrition data by band, function, tenure cohort, and manager (24 months)",
            "Exit survey responses with departure reasons",
            "Compensation benchmarking data (NASSCOM, Aon Hewitt, or equivalent)",
            "Recruitment and onboarding cost per hire by band",
            "Productivity ramp curve by role (time to full contribution)",
        ],
    },

    "seat_utilization_optimization": {
        "execution_playbook": [
            {"step": "Instrument all facilities with occupancy sensing (badge, Wi-Fi heatmap, or manual survey); measure peak and average utilisation by floor", "owner_role": "Facilities / HR", "duration_weeks": 3},
            {"step": "Design hybrid work policy (3:2 or 4:1) aligned with parent standards; set seat-to-headcount ratio target (1 seat : 1.3 employees)", "owner_role": "CHRO / Facilities", "duration_weeks": 3},
            {"step": "Consolidate underutilised floors/buildings; sublease or return surplus space to landlord at lease break or expiry", "owner_role": "Real Estate / Legal", "duration_weeks": 10},
            {"step": "Track cost-per-seat, utilisation rate, and occupancy cost as % of total CTC quarterly", "owner_role": "FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Peak office utilisation <65% of installed seat capacity for ≥3 months", "evidence_source": "occupancy_sensing_data", "confirms": "Space rationalisation and sublease opportunity is material"},
            {"signal": "Seat-to-headcount ratio <1.0 (more seats than employees) in a hybrid work environment", "evidence_source": "facilities_and_hr_data", "confirms": "Excess seat capacity can be released"},
            {"signal": "Occupancy cost (rent, facilities, power) >10% of total payroll cost", "evidence_source": "cost_breakdown", "confirms": "Seat optimisation will materially improve cost ratio"},
        ],
        "required_data_fields": [
            "Occupancy sensing data by floor and building (peak, average, and trend)",
            "Seat count vs headcount by location and shift pattern",
            "Lease terms, WALE, and break-clause positions by facility",
            "Facilities cost breakdown (rent, power, housekeeping, security) per seat",
            "Parent hybrid work policy requirements",
        ],
    },

    "shared_services_consolidation": {
        "execution_playbook": [
            {"step": "Map F&A (AP, AR, GL, Payroll) and HR ops processes by BU; measure volume, FTE, and cost per transaction for each BU", "owner_role": "Group Transformation / FP&A", "duration_weeks": 4},
            {"step": "Design SSC operating model: process scope, location, SLA framework, governance, and pricing/chargeback model", "owner_role": "SSC Design Lead", "duration_weeks": 5},
            {"step": "Migrate Wave 1 (transactional F&A) with parallel run for one period; transition staff under TUPE-equivalent arrangement", "owner_role": "SSC Operations / HR", "duration_weeks": 12},
            {"step": "Stabilise SSC with SLA dashboard; enforce chargeback to BUs; migrate Wave 2 (HR ops, IT service desk)", "owner_role": "SSC Head / FP&A", "duration_weeks": 8},
        ],
        "diagnostic_signals": [
            {"signal": "Same transactional process (e.g., invoice processing) performed by >3 independent BU teams at different cost per transaction", "evidence_source": "process_cost_benchmarking", "confirms": "Consolidation will reduce unit cost through scale and standardisation"},
            {"signal": "Cost per invoice processed >₹150 vs SSC benchmark <₹80 for equivalent volume", "evidence_source": "process_benchmarking", "confirms": "Scale economies from SSC are material"},
            {"signal": "Multiple ERP instances or process variants across BUs for the same transactional sub-process", "evidence_source": "it_landscape", "confirms": "Standardisation opportunity exists alongside consolidation"},
        ],
        "required_data_fields": [
            "Process inventory with volume, FTE, and cost per transaction by BU",
            "ERP/technology landscape across business units",
            "Current chargeback or recharge model for shared services",
            "SLA benchmark data for comparable SSC operations",
            "Location cost analysis (talent, real estate, infrastructure) for SSC hub",
        ],
    },

    "parent_recharge_rationalization": {
        "execution_playbook": [
            {"step": "Inventory all parent-to-GCC recharges: service type, volume driver, pricing basis, and contract; validate against actual services received", "owner_role": "Finance / Transfer Pricing", "duration_weeks": 3},
            {"step": "Benchmark each recharge category against arm's-length rate using TNMM or CUP method; identify over-priced or unsupported charges", "owner_role": "Transfer Pricing Advisor", "duration_weeks": 5},
            {"step": "Renegotiate service agreements to arm's-length pricing; eliminate charges for services not demonstrably received; update Ind AS 115 revenue recognition", "owner_role": "Finance / Legal", "duration_weeks": 6},
            {"step": "Implement recharge governance dashboard; file updated Form 3CEB and TP documentation; track effective recharge rate quarterly", "owner_role": "Finance / Tax", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Parent recharges as % of GCC revenue >12% for service categories that could be sourced locally at lower cost", "evidence_source": "intercompany_recharge_data", "confirms": "Repricing or scope reduction will reduce effective cost"},
            {"signal": "Recharge rates not benchmarked for >2 years despite changes in scope or market rates", "evidence_source": "tp_documentation", "confirms": "Benchmarking gap is creating over-payment risk"},
            {"signal": "Recharge categories include 'management fee' or 'stewardship' without clear deliverables or usage metric", "evidence_source": "intercompany_agreements", "confirms": "Restructuring unsupported charges will reduce cost and TP risk"},
        ],
        "required_data_fields": [
            "Intercompany recharge schedule: service type, pricing basis, and volume driver",
            "Intercompany service agreements with scope definition",
            "Comparable market rates for each recharged service category",
            "Form 3CEB and TP documentation",
            "Ind AS 115 revenue recognition treatment for recharged services",
        ],
    },

    "vendor_managed_services_shift": {
        "execution_playbook": [
            {"step": "Identify GCC support functions (IT infrastructure, facilities management, security) with managed-services market alternatives and clear SLA definition", "owner_role": "COO / Procurement", "duration_weeks": 3},
            {"step": "Benchmark managed-service pricing vs in-house total cost (FTE + infrastructure + overhead); confirm quality and risk profile", "owner_role": "Finance / Procurement", "duration_weeks": 4},
            {"step": "Run competitive RFP for selected managed-service scope; negotiate SLA-linked contracts with performance bonds", "owner_role": "Procurement", "duration_weeks": 6},
            {"step": "Transition in-house teams to vendor under TUPE-equivalent; track cost per unit of service and SLA compliance monthly", "owner_role": "HR / Vendor Management", "duration_weeks": 8},
        ],
        "diagnostic_signals": [
            {"signal": "In-house IT infrastructure or facilities support cost >20% above managed-service benchmark for equivalent coverage", "evidence_source": "cost_benchmarking", "confirms": "Managed-service shift will reduce cost with comparable service level"},
            {"signal": "In-house support team utilisation <70% due to variable demand pattern", "evidence_source": "workforce_utilisation_data", "confirms": "Vendor with multi-client scale will improve resource efficiency"},
            {"signal": "Support function SLA compliance below 95% with current in-house model for ≥2 quarters", "evidence_source": "it_service_desk_metrics", "confirms": "Specialised vendor will improve service quality alongside cost reduction"},
        ],
        "required_data_fields": [
            "In-house support function FTE count, cost, and utilisation by service line",
            "Managed-service pricing benchmarks for IT infrastructure, facilities, and security",
            "SLA performance data (uptime, response time, resolution time)",
            "Existing vendor contracts and performance data",
            "TUPE-equivalent obligations and transfer requirements",
        ],
    },

    "cloud_infra_modernization": {
        "execution_playbook": [
            {"step": "Assess cloud maturity: map all workloads (on-prem, co-location, cloud) to cost, utilisation, and retirement risk; define migration priority", "owner_role": "CTO / Cloud CoE", "duration_weeks": 4},
            {"step": "Build cloud migration roadmap: rehost, replatform, refactor, or retire by workload; establish landing zone and FinOps governance", "owner_role": "Cloud Architecture / Finance", "duration_weeks": 5},
            {"step": "Execute migration in waves (low-risk dev/test first, then production); enforce tagging and budget alerts from day 1", "owner_role": "Cloud Engineering / IT Delivery", "duration_weeks": 16},
            {"step": "Implement FinOps: rightsizing recommendations, reserved instances, and savings plans; track cloud spend per BU monthly", "owner_role": "FinOps / IT Finance", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "On-premises infrastructure utilisation <40% average with peak demand requiring expensive burst capacity", "evidence_source": "infrastructure_utilisation_report", "confirms": "Cloud migration will reduce idle infrastructure cost and improve elasticity"},
            {"signal": "Cloud spend growing >30% YoY without corresponding workload growth, indicating waste", "evidence_source": "cloud_billing_report", "confirms": "FinOps governance will reduce cloud waste"},
            {"signal": "Infrastructure cost per FTE >₹2 L/year vs cloud-optimised GCC benchmark of <₹1.2 L/year", "evidence_source": "cost_benchmarking", "confirms": "Cloud modernisation will improve cost per FTE ratio"},
        ],
        "required_data_fields": [
            "Workload inventory (on-prem, co-location, cloud) with cost and utilisation metrics",
            "Cloud billing breakdown by service type, environment, and business unit",
            "Network connectivity and security requirements for cloud migration",
            "FinOps maturity assessment and tagging hygiene status",
            "Parent/HQ cloud strategy and vendor preference",
        ],
    },

    "bench_management_optimization": {
        "execution_playbook": [
            {"step": "Profile bench by skill, band, and bench tenure; classify as project-ramp (0–4 weeks), skill-gap (4–8 weeks), or structural bench (>8 weeks)", "owner_role": "Resource Management / HR", "duration_weeks": 2},
            {"step": "Implement internal mobility marketplace: match bench talent to open positions across BUs before external hiring", "owner_role": "Resource Management / Talent Acquisition", "duration_weeks": 4},
            {"step": "Redeploy skill-gap bench into upskilling programs (GenAI, cloud, data) with time-bound deployment commitment", "owner_role": "Learning & Development / HR", "duration_weeks": 8},
            {"step": "Exit or PIP structural bench (>8 weeks, no deployment path); track bench % of total headcount and bench cost monthly", "owner_role": "HRBP / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Bench headcount as % of total GCC headcount >8% for ≥2 consecutive quarters", "evidence_source": "resource_management_data", "confirms": "Bench reduction will directly lower payroll cost per billable FTE"},
            {"signal": "Average bench tenure >6 weeks indicating deployment process or skill-market mismatch", "evidence_source": "bench_aging_data", "confirms": "Structural bench indicates resource management process gap"},
            {"signal": "External hiring ongoing for skills that exist in the bench profile", "evidence_source": "talent_acquisition_data_vs_bench_profile", "confirms": "Internal mobility process is broken; fixing it will reduce recruitment cost"},
        ],
        "required_data_fields": [
            "Bench headcount by skill, band, and bench tenure (weekly snapshots)",
            "Open position inventory by skill and expected start date",
            "External hiring pipeline and job requisitions",
            "Training and upskilling program catalog",
            "Bench cost (CTC for undeployed FTEs) per quarter",
        ],
    },

    "parent_scope_rationalization": {
        "execution_playbook": [
            {"step": "Inventory all work scopes migrated to GCC: service line, volume, FTE assigned, and value-add classification (transactional vs strategic)", "owner_role": "GCC Leadership / COO", "duration_weeks": 3},
            {"step": "Assess each scope for value-for-money vs parent expectation: cost, quality, and strategic contribution vs local/other-vendor alternative", "owner_role": "Finance / Strategy", "duration_weeks": 4},
            {"step": "Right-size scope: return commoditised or low-value work that is cheaper locally; pitch for higher-value strategic scope", "owner_role": "GCC CEO / Business Partners", "duration_weeks": 8},
            {"step": "Track scope mix (transactional vs strategic), cost per output, and parent satisfaction score quarterly", "owner_role": "FP&A / COO", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Transactional scope >60% of total GCC work portfolio, limiting value-add perception and long-term sustainability", "evidence_source": "scope_classification_review", "confirms": "Scope upgrade towards higher-value work will improve parent ROI and GCC resilience"},
            {"signal": "Per-seat cost of GCC trending above offshore benchmark due to cost inflation without corresponding scope upgrade", "evidence_source": "cost_benchmarking", "confirms": "Scope rationalisation and value upgrade needed to justify cost premium"},
            {"signal": "Parent considering in-sourcing or alternative vendor for ≥2 GCC service lines", "evidence_source": "parent_stakeholder_feedback", "confirms": "Proactive scope and value review is urgently needed"},
        ],
        "required_data_fields": [
            "GCC scope inventory with service line, FTE, and value-add classification",
            "Cost per seat and per output by service line",
            "Parent satisfaction scores and strategic expectation documentation",
            "Competitive landscape: alternative delivery options by scope category",
            "GCC 3-year roadmap and parent alignment",
        ],
    },

    "genai_augmented_productivity": {
        "execution_playbook": [
            {"step": "Conduct GenAI use-case discovery across top-5 functions (F&A, HR, IT, analytics, software development); estimate productivity impact per use case", "owner_role": "Innovation / CoE", "duration_weeks": 3},
            {"step": "Pilot highest-impact use cases (code generation, document summarisation, RFP response, data analysis) with volunteer teams; measure time savings", "owner_role": "Pilot Teams / CoE", "duration_weeks": 6},
            {"step": "Scale proven pilots via standardised prompt libraries, tool integrations (Copilot, Claude, Gemini), and change management", "owner_role": "CoE / HR / IT", "duration_weeks": 8},
            {"step": "Track productivity metrics (output per FTE, cycle time reduction) and report FTE capacity release to parent quarterly", "owner_role": "FP&A / CoE", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Functions with >40% of FTE time on document/data processing tasks where GenAI augmentation is proven (coding, legal review, financial analysis)", "evidence_source": "time_and_motion_study", "confirms": "GenAI adoption will yield measurable productivity improvement"},
            {"signal": "Software development cycle time (story to deployment) >4 weeks vs benchmark <2 weeks in comparable GCCs with AI-assisted coding", "evidence_source": "delivery_metrics", "confirms": "AI-assisted code generation will improve engineering throughput"},
            {"signal": "Licence or subscription cost for GenAI tools already incurred but adoption <30% of eligible workforce", "evidence_source": "saas_usage_data", "confirms": "Driving adoption of existing tools will improve ROI without incremental cost"},
        ],
        "required_data_fields": [
            "Function-level time allocation by task type (creative, analytical, document, coding)",
            "Existing GenAI tool subscriptions and adoption rates",
            "Software development metrics (velocity, cycle time, defect rate)",
            "Parent GenAI policy and data-handling guidelines",
            "Pilot design framework and measurement methodology",
        ],
    },

    "tier2_location_strategy": {
        "execution_playbook": [
            {"step": "Score Tier-2 cities against criteria: talent pool depth (technical graduates), infrastructure, attrition benchmarks, real-estate cost, and SEZ/STPI availability", "owner_role": "Strategy / Real Estate", "duration_weeks": 4},
            {"step": "Assess SEZ/STPI eligibility for target city; model 5-year TCO (salaries, real estate, infrastructure, incentives) vs Tier-1 incumbent location", "owner_role": "Finance / Tax", "duration_weeks": 4},
            {"step": "Establish satellite office or CoE in selected Tier-2 city; migrate new hiring and selected existing functions over 12–18 months", "owner_role": "CHRO / Real Estate / Operations", "duration_weeks": 16},
            {"step": "Track cost per FTE (Tier-2 vs Tier-1), attrition rate, and talent quality metrics by location quarterly", "owner_role": "FP&A / HR", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "GCC cost per FTE in current Tier-1 city growing >10% CAGR for 3 years, outpacing productivity improvement", "evidence_source": "cost_per_fte_trend", "confirms": "Tier-2 location will arrest cost escalation"},
            {"signal": "Tier-2 salary benchmark for equivalent roles 25–35% below current Tier-1 location", "evidence_source": "compensation_benchmarking", "confirms": "Material cost-per-FTE reduction is achievable via geographic arbitrage"},
            {"signal": "Attrition rate in current Tier-1 location >20% driven by competition for talent from large tech employers", "evidence_source": "hr_attrition_data", "confirms": "Tier-2 talent market is less competitive, supporting retention improvement"},
        ],
        "required_data_fields": [
            "Cost per FTE comparison across Tier-1 and Tier-2 locations (salary, real estate, infrastructure)",
            "Talent pool data: NASSCOM city report or equivalent for target Tier-2 cities",
            "Attrition benchmarks by location",
            "SEZ/STPI availability and incentive structure for target city",
            "Real estate availability and cost per sq ft in Tier-2 candidate cities",
        ],
    },

    "sez_stpi_tax_optimisation": {
        "execution_playbook": [
            {"step": "Audit current SEZ/STPI status and compliance: unit approval, Softex declaration volume and coverage, and bond utilisation", "owner_role": "Finance / Tax / Compliance", "duration_weeks": 3},
            {"step": "Calculate IT/ITeS income tax exemption foregone due to non-filing or incomplete Softex declarations; quantify IEC and bond optimisation opportunity", "owner_role": "Tax / Finance", "duration_weeks": 3},
            {"step": "File backdated Softex declarations (where permissible); correct STPI/SEZ compliance gaps and implement automated Softex filing workflow", "owner_role": "Finance / Tax", "duration_weeks": 6},
            {"step": "Integrate Softex filing into monthly invoice generation workflow; track exemption utilisation and compliance calendar", "owner_role": "Finance / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Softex declaration coverage <80% of eligible software export invoices", "evidence_source": "stpi_compliance_audit", "confirms": "Filing gap recovery will immediately improve tax exemption position"},
            {"signal": "IT income tax exemption utilised <90% of eligible income under STPI/SEZ scheme", "evidence_source": "tax_return_data", "confirms": "Compliance improvement will reduce effective tax rate"},
            {"signal": "STPI/SEZ bond amount not optimised (excess bond increasing opportunity cost)", "evidence_source": "stpi_bond_register", "confirms": "Bond rightsizing will release working capital"},
        ],
        "required_data_fields": [
            "Softex declaration log vs total software export invoice value",
            "IT exemption claimed vs eligible income in tax returns",
            "STPI/SEZ unit approval documents and scope",
            "Bond register and utilisation rate",
            "Monthly software export invoice data by client and currency",
        ],
    },

    "chargeback_model_transformation": {
        "execution_playbook": [
            {"step": "Audit current recharge model: map each GCC cost pool to chargeback driver, rate, and receiving BU; identify misalignments vs actual consumption", "owner_role": "Finance / COO", "duration_weeks": 3},
            {"step": "Redesign to activity-based costing model: define unit rates per service line (cost per FTE, per transaction, per project hour) with transparent overhead allocation", "owner_role": "Finance / FP&A", "duration_weeks": 5},
            {"step": "Align new chargeback model with parent finance teams; obtain sign-off and integrate into ERP intercompany billing module", "owner_role": "Finance / IT", "duration_weeks": 4},
            {"step": "Publish monthly chargeback dashboards by BU and service line; track demand discipline and cost recovery rate", "owner_role": "FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Recharge disputes from BUs >3 per quarter due to lack of transparency in cost allocation", "evidence_source": "intercompany_dispute_log", "confirms": "Activity-based costing model will improve transparency and reduce disputes"},
            {"signal": "GCC cost recovery rate <95% of budget due to incorrect chargeback basis or BU pushback", "evidence_source": "finance_cost_recovery_report", "confirms": "Model redesign will improve cost recovery and GCC P&L accuracy"},
            {"signal": "BU decision-making on GCC scope driven by perception of value rather than actual cost data", "evidence_source": "stakeholder_interviews", "confirms": "Transparent unit-cost pricing will enable rational demand decisions"},
        ],
        "required_data_fields": [
            "Current chargeback rate card and allocation methodology by cost pool",
            "GCC P&L by service line and function",
            "BU demand data by service type and volume",
            "Intercompany billing configuration in ERP",
            "Parent finance accounting policy for intercompany services",
        ],
    },

    "org_span_control_optimisation": {
        "execution_playbook": [
            {"step": "Analyse GCC org chart: compute average span of control and management layer count by function vs NASSCOM GCC benchmark", "owner_role": "HRBP / People Analytics", "duration_weeks": 2},
            {"step": "Define target spans (IC-to-manager: 8–12 for execution roles, 5–8 for strategic roles) and maximum layer count (4 from GCC CEO to IC)", "owner_role": "CHRO / GCC Leadership", "duration_weeks": 3},
            {"step": "Redesign org structure: flatten layers, eliminate single-direct-report manager roles, and combine sub-scale teams", "owner_role": "CHRO / Function Heads", "duration_weeks": 8},
            {"step": "Implement change plan with redeployment or exit for displaced roles; track manager-to-IC ratio and cost-per-band quarterly", "owner_role": "HR Operations / FP&A", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Average span of control <5 ICs per manager for non-specialist functions, indicating over-management", "evidence_source": "org_chart_analysis", "confirms": "De-layering will reduce management overhead cost"},
            {"signal": "Management layers >5 from GCC CEO to individual contributor for delivery functions", "evidence_source": "org_chart", "confirms": "Layer reduction will improve decision speed and reduce overhead ratio"},
            {"signal": "Manager-to-IC ratio >1:4 with management cost as % of total payroll >30%", "evidence_source": "payroll_data_by_band", "confirms": "Flatter structure will improve cost efficiency"},
        ],
        "required_data_fields": [
            "Org chart with headcount and CTC by band and function",
            "Span-of-control data by manager across all levels",
            "NASSCOM or peer GCC benchmark for management structure",
            "Single-direct-report manager inventory",
            "Cost by band (manager vs IC) for overhead ratio calculation",
        ],
    },

    "shadow_it_saas_elimination": {
        "execution_playbook": [
            {"step": "Run SaaS discovery scan using browser plug-in or SSO logs; identify all active SaaS applications by BU and usage frequency", "owner_role": "IT Security / FinOps", "duration_weeks": 3},
            {"step": "Compare against approved IT catalog; classify shadow IT into: approve+consolidate, migrate to approved alternative, or decommission", "owner_role": "IT / Procurement", "duration_weeks": 3},
            {"step": "Negotiate consolidated licensing agreements for approved SaaS (Microsoft, Atlassian, Slack); enforce single-vendor SSO login to control proliferation", "owner_role": "IT Procurement / Legal", "duration_weeks": 6},
            {"step": "Track authorised vs shadow application count monthly; enforce procurement policy requiring IT review for new SaaS subscriptions", "owner_role": "IT / Finance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Shadow SaaS (unauthorised tools) representing >20% of total SaaS spend discovered through discovery scan", "evidence_source": "saas_discovery_report", "confirms": "Rationalisation and governance will reduce waste and security risk"},
            {"signal": "Duplicate SaaS tools for same function across BUs (e.g., multiple project management tools, multiple video conferencing subscriptions)", "evidence_source": "saas_inventory", "confirms": "Consolidation to single approved tool will reduce per-seat cost"},
            {"signal": "SaaS spend growing >30% YoY without corresponding headcount or output growth", "evidence_source": "saas_spend_trend", "confirms": "Governance implementation will arrest uncontrolled proliferation"},
        ],
        "required_data_fields": [
            "SaaS discovery report (SSO logs, browser plug-in scan, credit card statement analysis)",
            "Approved IT catalog with standard tooling by function",
            "SaaS contract and licence data (vendor, users, cost, renewal date)",
            "Security risk classification for shadow IT applications",
            "Procurement policy for software purchases",
        ],
    },

    # ------------------------------------------------------- HEALTHCARE/HOSPITALS
    "clinical_workforce_optimization": {
        "execution_playbook": [
            {"step": "Model clinical staffing ratios (nurse:bed, doctor:OP visit) by specialty vs NABH and peer hospital benchmarks; identify over/under-staffed departments", "owner_role": "CMO / HR", "duration_weeks": 3},
            {"step": "Redesign rosters to align staffing with patient volume patterns (peak vs off-peak hours, seasonality); reduce agency/locum dependency", "owner_role": "Nursing Director / HR", "duration_weeks": 4},
            {"step": "Implement workforce management software for demand-driven scheduling; integrate with HIS for real-time census data", "owner_role": "IT / HR", "duration_weeks": 6},
            {"step": "Track agency locum spend, overtime %, and nurse turnover monthly; set targets for reduction", "owner_role": "FP&A / HR", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Agency/locum spend >15% of total clinical payroll indicating chronic staffing-model dependency on high-cost contractors", "evidence_source": "payroll_and_agency_spend", "confirms": "Permanent staffing model and roster redesign will reduce cost per clinical FTE"},
            {"signal": "Nurse-to-bed ratio >20% above NABH requirement in general wards during off-peak hours", "evidence_source": "staffing_benchmarking", "confirms": "Demand-linked rostering will reduce excess clinical labour cost"},
            {"signal": "Clinical overtime as % of base payroll >12% for ≥3 consecutive quarters", "evidence_source": "payroll_data", "confirms": "Rostering and shift-pattern optimisation will reduce overtime premium"},
        ],
        "required_data_fields": [
            "Clinical FTE roster by specialty, shift, and employment type (permanent vs agency/locum)",
            "Patient census data (ADC, OP visits) by department and time of day",
            "Agency/locum spend by vendor and specialty (12 months)",
            "NABH staffing norm requirements by bed type",
            "Nurse turnover and tenure data",
        ],
    },

    "medical_supplies_procurement": {
        "execution_playbook": [
            {"step": "Audit formulary: map all consumables (sutures, gloves, IV fluids, implants) to category, vendor, unit price, and annual volume", "owner_role": "Procurement / Materials Management", "duration_weeks": 3},
            {"step": "Benchmark unit prices against NHA/CGHS rates and comparable hospital group purchases; identify price gaps by item", "owner_role": "Procurement / Finance", "duration_weeks": 3},
            {"step": "Consolidate vendors for top-20 spend categories; negotiate group purchasing agreements or join existing hospital GPO", "owner_role": "Procurement Lead", "duration_weeks": 8},
            {"step": "Mandate formulary compliance via HIS-linked requisition; track savings by category and vendor compliance monthly", "owner_role": "Procurement / Clinical", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Medical consumable cost as % of revenue >18% vs peer benchmark of <15% for similar case mix", "evidence_source": "cost_per_admission_data", "confirms": "Procurement rationalisation will yield material cost reduction"},
            {"signal": "Same consumable item purchased from >3 vendors at different unit prices (price spread >20%)", "evidence_source": "vendor_master", "confirms": "Consolidation will harmonise pricing and improve negotiating leverage"},
            {"signal": "Implant cost >40% of procedure revenue for high-volume specialties (orthopaedics, cardiology)", "evidence_source": "procedure_cost_data", "confirms": "Implant vendor consolidation and consignment model will reduce working capital and purchase cost"},
        ],
        "required_data_fields": [
            "Formulary with item description, vendor, unit price, and annual consumption volume",
            "NHA/CGHS benchmark prices for common consumables and implants",
            "Spend by vendor and category (12 months)",
            "HIS requisition and inventory management configuration",
            "Existing GPO or group purchasing membership details",
        ],
    },

    "pharmacy_cost_optimization": {
        "execution_playbook": [
            {"step": "Audit pharmacy formulary for therapeutic substitution opportunities: identify branded drugs with generic equivalents at >50% cost savings", "owner_role": "Chief Pharmacist / CMO", "duration_weeks": 3},
            {"step": "Evaluate empanelment with 340B/NHA tender pricing programs; renegotiate pricing with top-10 pharma vendors by spend", "owner_role": "Pharmacy / Procurement", "duration_weeks": 5},
            {"step": "Implement pharmacist-led formulary management: enforce generic substitution protocols with prescriber education", "owner_role": "Chief Pharmacist / CMO", "duration_weeks": 6},
            {"step": "Track pharmacy cost per admission, generic substitution rate, and drug wastage monthly", "owner_role": "FP&A / Pharmacy", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Pharmacy cost per admission >20% above peer benchmark for similar case mix index", "evidence_source": "pharmacy_cost_benchmarking", "confirms": "Formulary management and generic substitution will reduce cost"},
            {"signal": "Generic substitution rate <60% where bio-equivalent generics are available and clinically appropriate", "evidence_source": "formulary_analysis", "confirms": "Systematic generic substitution will reduce drug cost without clinical compromise"},
            {"signal": "Drug wastage and expiry write-off >2% of pharmacy procurement value annually", "evidence_source": "pharmacy_write_off_data", "confirms": "Formulary optimisation and demand-linked ordering will reduce waste"},
        ],
        "required_data_fields": [
            "Formulary with drug name, branded vs generic, unit cost, and annual consumption",
            "Generic availability and bioequivalence data by therapeutic category",
            "Pharmacy vendor contracts and pricing",
            "Prescribing pattern data by physician and specialty",
            "Drug expiry and wastage report (12 months)",
        ],
    },

    "revenue_cycle_automation": {
        "execution_playbook": [
            {"step": "Measure denial rate by payer, denial reason, and department; quantify revenue at risk from denials and late submissions", "owner_role": "Revenue Cycle Head / Finance", "duration_weeks": 3},
            {"step": "Implement RCM automation: eligibility verification, pre-authorisation, and coding audit tools integrated with HIS/billing system", "owner_role": "IT / Revenue Cycle", "duration_weeks": 8},
            {"step": "Automate claim submission and denial workflow with real-time payer response tracking; resolve top-3 denial reasons with system controls", "owner_role": "Revenue Cycle / IT", "duration_weeks": 6},
            {"step": "Track denial rate, days in AR, net collection rate, and bad debt by payer monthly; set improvement targets", "owner_role": "FP&A / Revenue Cycle", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Initial claim denial rate >10% of submitted claims, indicating billing or coding quality gap", "evidence_source": "revenue_cycle_report", "confirms": "RCM automation and coding improvement will recover revenue"},
            {"signal": "Days in accounts receivable >45 days for insurance payers vs benchmark <30 days", "evidence_source": "ar_aging_report", "confirms": "Process automation will accelerate cash conversion"},
            {"signal": "Revenue cycle team >15 FTEs with >60% of time on manual claim follow-up and denial management", "evidence_source": "revenue_cycle_time_study", "confirms": "Automation will release FTE capacity and reduce cost per claim processed"},
        ],
        "required_data_fields": [
            "Claim denial data by payer, denial reason, and department (12 months)",
            "Accounts receivable aging by payer and bill type",
            "Revenue cycle FTE count and time allocation by activity",
            "HIS/billing system architecture and integration capability",
            "Payer contract terms and adjudication rules by payer",
        ],
    },

    "clinical_space_utilization": {
        "execution_playbook": [
            {"step": "Measure OT and procedure-room utilisation by specialty: scheduled hours, actual cases, and turnaround time (TAT) between cases", "owner_role": "Operations / CMO", "duration_weeks": 3},
            {"step": "Redesign OT scheduling: implement block scheduling with performance guarantees, reduce TAT through standardised turnover protocol", "owner_role": "Nursing Director / OT Manager", "duration_weeks": 4},
            {"step": "Reconfigure underutilised clinical space: convert low-utilisation OTs to day-surgery or procedure rooms; expand high-demand specialty", "owner_role": "Operations / Finance / Facilities", "duration_weeks": 8},
            {"step": "Track OT utilisation rate, cases per OT per day, and revenue per OT hour monthly", "owner_role": "FP&A / Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "OT utilisation rate <70% of available hours with TAT between cases >30 minutes", "evidence_source": "ot_scheduling_data", "confirms": "Scheduling improvement and TAT reduction will increase cases per day without capital investment"},
            {"signal": "Revenue per OT hour below peer benchmark for comparable case mix", "evidence_source": "ot_revenue_report", "confirms": "Optimised scheduling will improve OT revenue intensity"},
            {"signal": "Underutilised clinical space (empty beds, unused OTs) contributing fixed cost without revenue", "evidence_source": "occupancy_and_utilisation_data", "confirms": "Reconfiguration will improve return on clinical assets"},
        ],
        "required_data_fields": [
            "OT scheduling data: planned vs actual cases, start times, TAT, and cancellations",
            "Clinical space inventory with utilisation rates by room type",
            "Revenue per procedure by OT room and specialty",
            "Staffing model for OT and procedure rooms",
            "Bed occupancy rate by ward and specialty",
        ],
    },

    "medical_equipment_rationalization": {
        "execution_playbook": [
            {"step": "Build equipment utilisation register: map every capital medical device to scheduled hours, actual usage, and age; flag equipment <40% utilised", "owner_role": "Biomedical Engineering / Finance", "duration_weeks": 3},
            {"step": "Evaluate pooling model for under-utilised equipment across departments or campuses; assess feasibility of shared scheduling", "owner_role": "Operations / Finance", "duration_weeks": 3},
            {"step": "Retire or dispose of equipment below utilisation threshold; negotiate performance-based service contracts (up-time SLA) replacing time-and-material AMCs", "owner_role": "Procurement / Biomedical", "duration_weeks": 6},
            {"step": "Track equipment utilisation, AMC cost per equipment, and unplanned downtime quarterly", "owner_role": "FP&A / Biomedical", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Capital medical equipment utilisation <50% for ≥30% of the installed base", "evidence_source": "equipment_utilisation_register", "confirms": "Pooling or disposal will reduce ownership cost"},
            {"signal": "AMC spend as % of equipment value >8% for equipment >7 years old", "evidence_source": "amc_spend_data", "confirms": "Switching to performance-based or capex-refreshed model will reduce maintenance cost"},
            {"signal": "Equipment downtime events >5/quarter causing case cancellations or delays", "evidence_source": "biomedical_maintenance_log", "confirms": "Performance-based SLA contract will improve uptime and reduce revenue loss"},
        ],
        "required_data_fields": [
            "Equipment inventory with age, capital value, utilisation rate, and AMC cost",
            "Equipment downtime and maintenance log (12 months)",
            "AMC contract terms by vendor and equipment type",
            "Sharing feasibility assessment (location proximity, scheduling compatibility)",
            "NABH and clinical requirement for dedicated vs shared equipment",
        ],
    },

    # ---------------------------------------------------- HOSPITALITY / TRAVEL
    "ota_commission_reduction": {
        "execution_playbook": [
            {"step": "Audit channel mix: map room-night volume and commission cost by OTA channel (Booking.com, Expedia, MakeMyTrip) vs direct (website, walk-in, corporate)", "owner_role": "Revenue Management / Finance", "duration_weeks": 3},
            {"step": "Design direct booking incentive program: rate parity management, loyalty rate advantage, and value-add (F&B credit, upgrade) for direct bookers", "owner_role": "Marketing / Revenue Management", "duration_weeks": 4},
            {"step": "Negotiate OTA commission rates by market segment; explore OTA preferred-partner programs that reduce commission for volume commitments", "owner_role": "Revenue Management / GM", "duration_weeks": 6},
            {"step": "Track OTA commission as % of room revenue, direct booking share, and RevPAR by channel monthly", "owner_role": "FP&A / Revenue Management", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "OTA channel contributing >40% of room revenue with average commission >18% of room rate", "evidence_source": "channel_mix_report", "confirms": "Direct booking shift will materially reduce distribution cost"},
            {"signal": "Direct booking share declining YoY while OTA acquisition cost growing faster than RevPAR", "evidence_source": "revenue_channel_trend", "confirms": "Channel rebalancing is strategically and financially necessary"},
            {"signal": "Customer loyalty program contribution to direct bookings <15% of eligible members", "evidence_source": "loyalty_program_data", "confirms": "Loyalty program activation can drive higher-value direct bookings"},
        ],
        "required_data_fields": [
            "Room revenue and commission cost by channel (OTA, direct, corporate, GDS)",
            "Commission rate agreements by OTA and market segment",
            "Direct booking conversion data (website traffic, conversion rate, booking value)",
            "Loyalty program enrolment and redemption data",
            "Competitor channel mix and rate parity compliance data",
        ],
    },

    "fnb_procurement_optimization": {
        "execution_playbook": [
            {"step": "Audit F&B raw material spend by category (proteins, dairy, dry goods, beverages); map vendor, unit price, and yield per kg for key items", "owner_role": "Executive Chef / Procurement", "duration_weeks": 3},
            {"step": "Develop recipe costing for top-50 menu items; identify food cost ratio outliers vs menu engineering benchmark", "owner_role": "Executive Chef / Finance", "duration_weeks": 3},
            {"step": "Join group purchasing organisation or negotiate direct supply agreements for high-volume commodities; audit portion control and yield standards", "owner_role": "Procurement / Operations", "duration_weeks": 6},
            {"step": "Track food cost ratio by outlet and category weekly; enforce menu engineering principles at seasonal menu review", "owner_role": "FP&A / F&B Manager", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Food cost ratio >35% for restaurant or >40% for banquet, vs benchmark of <30% for comparable segment", "evidence_source": "fb_cost_report", "confirms": "Procurement optimisation and portion control will improve F&B margin"},
            {"signal": "F&B vendor count >50 for high-volume commodities (proteins, dairy) with no volume-based contracts", "evidence_source": "vendor_master", "confirms": "Consolidation and direct supply will reduce per-unit cost"},
            {"signal": "Wastage and spoilage >5% of F&B procurement value due to overordering or poor yield management", "evidence_source": "kitchen_waste_log", "confirms": "Demand-led ordering and yield training will reduce waste cost"},
        ],
        "required_data_fields": [
            "F&B raw material spend by category and vendor (12 months)",
            "Recipe cost cards for top-50 menu items with portion specifications",
            "Food cost ratio by outlet type and menu category",
            "Vendor pricing and minimum order quantity by commodity",
            "Wastage and spoilage data by item and kitchen section",
        ],
    },

    "energy_per_key_reduction": {
        "execution_playbook": [
            {"step": "Conduct energy audit (kWh per occupied room per night) by property; benchmark against LEED/hotel association energy intensity norms", "owner_role": "Facilities / Engineering", "duration_weeks": 3},
            {"step": "Deploy BMS (Building Management System) and smart HVAC controls linked to room occupancy sensor; replace high-wattage lighting with LED", "owner_role": "Engineering / Facilities", "duration_weeks": 8},
            {"step": "Install sub-metering by department (rooms, restaurants, pool, spa) to enable targeted energy accountability and departmental KPI tracking", "owner_role": "Engineering / Finance", "duration_weeks": 4},
            {"step": "Track energy cost per occupied room per night (kWh and ₹) and total property energy intensity monthly", "owner_role": "FP&A / Engineering", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Energy cost per key >₹150/occupied room/night vs comparable hotel benchmark of <₹100", "evidence_source": "energy_cost_report", "confirms": "Energy management investment will yield positive ROI within 18 months"},
            {"signal": "HVAC representing >50% of total energy consumption without occupancy-linked control system", "evidence_source": "energy_audit", "confirms": "BMS and smart HVAC controls will reduce HVAC energy by 20-30%"},
            {"signal": "Energy cost growing faster than RevPAR over 3-year trend", "evidence_source": "property_p_and_l", "confirms": "Energy as % of revenue is structurally increasing and requires active management"},
        ],
        "required_data_fields": [
            "Energy consumption data (kWh) by fuel type and department (12 months)",
            "Energy cost per occupied room per night by property",
            "BMS and HVAC system specifications and age",
            "Occupancy rate and seasonality pattern",
            "Capital cost estimates for energy efficiency upgrades",
        ],
    },

    "housekeeping_optimization": {
        "execution_playbook": [
            {"step": "Conduct time-and-motion study for room cleaning and public-area housekeeping; establish standard room-turn time by room type", "owner_role": "Housekeeping Manager / HR", "duration_weeks": 3},
            {"step": "Design demand-linked rostering: schedule housekeeping team against occupancy forecast; reduce permanent headcount in low-season", "owner_role": "Housekeeping / HR", "duration_weeks": 4},
            {"step": "Evaluate outsourcing part of housekeeping (public areas, laundry) to specialist contractor vs in-house model; build TCO comparison", "owner_role": "GM / Procurement / HR", "duration_weeks": 4},
            {"step": "Track rooms cleaned per housekeeper per shift, overtime %, and housekeeping cost per occupied room monthly", "owner_role": "FP&A / Housekeeping", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Housekeeping cost per occupied room >₹200/night vs comparable hotel benchmark of <₹140/night", "evidence_source": "departmental_cost_report", "confirms": "Rostering and outsourcing optimisation will reduce housekeeping cost"},
            {"signal": "Permanent housekeeping headcount sized for 95% occupancy with no seasonal adjustment", "evidence_source": "hr_headcount_vs_occupancy", "confirms": "Demand-linked rostering will reduce labour cost in low-occupancy periods"},
            {"signal": "Housekeeping overtime as % of department payroll >15%", "evidence_source": "payroll_data", "confirms": "Staffing-model optimisation will reduce overtime premium cost"},
        ],
        "required_data_fields": [
            "Housekeeping FTE count and cost breakdown (permanent vs casual vs outsourced)",
            "Rooms cleaned per housekeeper per shift (current vs benchmark)",
            "Occupancy rate by month and season",
            "Housekeeping cost per occupied room by property",
            "Outsourced housekeeping pricing and SLA benchmarks",
        ],
    },

    "revenue_management_optimization": {
        "execution_playbook": [
            {"step": "Audit RevPAR gap vs compset: decompose into occupancy and ADR components; identify rate and volume levers by segment and season", "owner_role": "Revenue Management", "duration_weeks": 3},
            {"step": "Implement or upgrade RMS (Revenue Management System) with demand forecasting and dynamic pricing engine; integrate with PMS and channel manager", "owner_role": "Revenue Management / IT", "duration_weeks": 6},
            {"step": "Rebalance segment mix towards higher-value transient and corporate accounts; renegotiate corporate rate agreements using ADR data", "owner_role": "Revenue Management / Sales", "duration_weeks": 8},
            {"step": "Track RevPAR index vs compset, ADR realisation, and segment mix monthly; report to ownership", "owner_role": "GM / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "RevPAR index (RGI) <0.9 vs compset indicating under-performance relative to market", "evidence_source": "str_report", "confirms": "Revenue management improvement will capture share from compset"},
            {"signal": "OTA and wholesale channels generating >30% of revenue at ADRs 25% below best available rate", "evidence_source": "channel_mix_report", "confirms": "Channel and rate management tightening will improve ADR and RevPAR"},
            {"signal": "No revenue management system in place or RMS used for reporting only (not active pricing)", "evidence_source": "technology_landscape", "confirms": "Implementing active demand-based pricing will improve RevPAR"},
        ],
        "required_data_fields": [
            "RevPAR, occupancy, and ADR data by segment and channel (12 months)",
            "Compset performance data from STR or hotel benchmarking service",
            "PMS and channel manager integration capability",
            "Corporate account rate agreements and production data",
            "Demand forecast accuracy and pace data",
        ],
    },

    # ----------------------------------------------------- INSURANCE GENERAL
    "claims_automation": {
        "execution_playbook": [
            {"step": "Map claims journey by product line: measure FNOL-to-settlement cycle time, manual touchpoints, and STP rate by claim type and value band", "owner_role": "Claims Operations / Process Excellence", "duration_weeks": 3},
            {"step": "Design STP pathway by claim type: auto-adjudication rules for low-value/low-complexity claims; integrate with surveyor and hospital network", "owner_role": "Claims / IT", "duration_weeks": 5},
            {"step": "Deploy FNOL automation (WhatsApp/IVR), triage scoring model, and digital document collection; eliminate manual data entry at intake", "owner_role": "IT Delivery / Claims", "duration_weeks": 10},
            {"step": "Track STP rate, claims processing cost per claim, and customer satisfaction (NPS/CSAT) by product line monthly", "owner_role": "FP&A / Claims", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Claims STP rate <30% for product lines where IRDAI allows straight-through processing (motor own-damage, health cashless)", "evidence_source": "claims_ops_report", "confirms": "STP implementation will materially reduce cost per claim and settlement time"},
            {"signal": "Claims processing cost per claim >₹800 for motor or >₹1,200 for health claims vs peer benchmark", "evidence_source": "operational_cost_benchmarking", "confirms": "Automation will reduce claims processing cost"},
            {"signal": "Average claims settlement time >15 days for cashless health or >30 days for motor own-damage", "evidence_source": "claims_tat_report", "confirms": "Process automation will improve settlement speed and customer satisfaction"},
        ],
        "required_data_fields": [
            "Claims journey map with volume, STP rate, and TAT by product line and claim type",
            "Claims processing cost per claim by product (FTE cost + surveyor + system)",
            "FNOL data: channel mix (agent, digital, call centre) and data completeness at intake",
            "Policy admin system and claims management system integration architecture",
            "IRDAI compliance requirements for automated adjudication",
        ],
    },

    "underwriting_automation": {
        "execution_playbook": [
            {"step": "Map underwriting decision workflow by product line: measure time-to-quote, referral rate, and loss ratio by underwriting tier", "owner_role": "Chief Underwriting Officer / Process Excellence", "duration_weeks": 3},
            {"step": "Build rules-based auto-acceptance engine for standard risks; integrate external data (bureau, weather, geo-risk, IoT) for risk enrichment", "owner_role": "Underwriting / IT", "duration_weeks": 8},
            {"step": "Deploy AI risk scoring model for SME and commercial lines; run parallel with manual underwriting for validation", "owner_role": "Underwriting / Data Science", "duration_weeks": 8},
            {"step": "Track auto-acceptance rate, referral rate, combined ratio by segment, and underwriting team productivity monthly", "owner_role": "FP&A / Underwriting", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Underwriting referral rate >40% of new business quotes requiring senior underwriter review", "evidence_source": "underwriting_ops_data", "confirms": "Rules engine and AI scoring will reduce referral rate and speed up quote turnaround"},
            {"signal": "Time-to-quote for standard commercial lines >5 days vs competitor benchmark of <24 hours", "evidence_source": "sales_ops_data", "confirms": "Automation will improve conversion rate through faster quote turnaround"},
            {"signal": "Loss ratio variance >10 percentage points between auto-accepted and manually-underwritten risks of similar profile", "evidence_source": "portfolio_analytics", "confirms": "Data enrichment and AI scoring will improve risk selection quality"},
        ],
        "required_data_fields": [
            "Underwriting workflow data: quote volume, referral rate, TAT, and accept/decline rate",
            "Loss ratio by product line, underwriting tier, and channel",
            "External data availability for risk enrichment (bureau, geo-risk, IoT sensors)",
            "Policy admin system architecture and API capability",
            "IRDAI compliance requirements for automated underwriting",
        ],
    },

    "policy_admin_digitization": {
        "execution_playbook": [
            {"step": "Audit policy lifecycle touchpoints: issuance, endorsement, renewal, and lapse processes; measure manual effort and error rate per transaction type", "owner_role": "Policy Operations / Process Excellence", "duration_weeks": 3},
            {"step": "Consolidate PAS (Policy Administration System) to single platform where multiple systems operate; map integration with CRM, billing, and regulatory reporting", "owner_role": "CTO / IT Architecture", "duration_weeks": 5},
            {"step": "Launch digital self-service for policyholders: endorsements, premium payment, and document download via app/portal; automate renewal trigger", "owner_role": "Digital / IT Delivery", "duration_weeks": 10},
            {"step": "Track digital self-service adoption rate, policy issuance TAT, and operations cost per policy in force monthly", "owner_role": "FP&A / Policy Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Policy issuance or endorsement TAT >24 hours for standard products vs digital-first insurer benchmark of <2 hours", "evidence_source": "policy_ops_metrics", "confirms": "Digitisation will improve speed and reduce manual cost per policy"},
            {"signal": "Operations cost per policy in force >₹1,200/year vs peer benchmark <₹800, indicating manual-heavy model", "evidence_source": "operational_cost_benchmarking", "confirms": "Self-service and PAS consolidation will reduce unit cost"},
            {"signal": "Multiple PAS platforms (>2) creating data inconsistency and integration overhead", "evidence_source": "it_landscape", "confirms": "PAS consolidation will reduce IT maintenance cost and data quality issues"},
        ],
        "required_data_fields": [
            "Policy lifecycle transaction volumes and TAT by type (issuance, endorsement, renewal, lapse)",
            "Operations cost per policy by transaction type and product",
            "PAS landscape and integration architecture",
            "Digital channel adoption rate (app, web portal) by policyholder segment",
            "IRDAI compliance requirements for digital policy issuance and documentation",
        ],
    },

    "fraud_detection_ai_insurance": {
        "execution_playbook": [
            {"step": "Analyse historical claims for fraud indicators: claims made just after policy inception, late-reported high-value claims, and repeat claimants", "owner_role": "Fraud Analytics / Claims", "duration_weeks": 4},
            {"step": "Build ML fraud scoring model using claims, policy, and network data; validate precision and recall on holdout dataset", "owner_role": "Data Science / Claims", "duration_weeks": 6},
            {"step": "Integrate fraud score into claims triage workflow: flag high-risk claims for investigation before settlement; automate low-risk claims", "owner_role": "Claims / IT", "duration_weeks": 6},
            {"step": "Track fraud detected as % of claims value, false-positive investigation rate, and fraud loss reduction quarterly", "owner_role": "Fraud / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Claims fraud loss >1% of net earned premium for motor or health lines, indicating inadequate detection", "evidence_source": "fraud_loss_report", "confirms": "AI fraud detection will improve detection rate and reduce fraud loss"},
            {"signal": "Investigation team >20 FTEs investigating all flagged claims with high false-positive rate (>70%)", "evidence_source": "fraud_investigation_metrics", "confirms": "ML scoring will improve investigation efficiency and reduce false positives"},
            {"signal": "No fraud scoring model—all fraud detection relies on adjuster judgment with no systematic analytics", "evidence_source": "claims_ops_assessment", "confirms": "AI model introduction will improve detection systematically"},
        ],
        "required_data_fields": [
            "Historical claims data with confirmed fraud labels (≥2 years, ≥5,000 confirmed fraud cases)",
            "Policy, customer, and network data for feature engineering",
            "Investigation case outcomes and false-positive rate",
            "Claims management system architecture for scoring integration",
            "IRDAI compliance requirements for AI-based fraud detection",
        ],
    },

    "channel_mix_optimization": {
        "execution_playbook": [
            {"step": "Analyse distribution cost by channel (tied agents, brokers, bancassurance, digital, direct): commission, acquisition cost, and persistency by channel", "owner_role": "Distribution / FP&A", "duration_weeks": 3},
            {"step": "Build customer lifetime value model by channel: compare 13th and 25th month persistency, premium size, and claim frequency", "owner_role": "Actuarial / Analytics", "duration_weeks": 4},
            {"step": "Rebalance channel investment towards higher-CLV, lower-cost channels; renegotiate commission structures with brokers and banks", "owner_role": "Distribution Head / Finance", "duration_weeks": 8},
            {"step": "Track new business premium by channel, cost per new policy, and persistency ratio monthly", "owner_role": "FP&A / Distribution", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Distribution cost (commission + acquisition) >25% of first-year premium for retail life or >15% for general insurance", "evidence_source": "distribution_cost_report", "confirms": "Channel mix rebalancing towards lower-commission channels will improve expense ratio"},
            {"signal": "13th month persistency ratio <70% for agent-sourced policies vs >85% for digital-sourced policies", "evidence_source": "persistency_data", "confirms": "Shifting channel mix towards digital will improve LTV and reduce policy lapse cost"},
            {"signal": "Digital channel contributing <10% of new business despite comparable unit economics", "evidence_source": "channel_mix_report", "confirms": "Digital channel investment will improve acquisition cost without sacrificing quality"},
        ],
        "required_data_fields": [
            "New business premium and policy count by channel (12 months)",
            "Commission rate and acquisition cost by channel and product",
            "Persistency data (13th and 25th month) by channel",
            "Claims frequency and loss ratio by channel",
            "Digital channel funnel data (leads, conversion, policy issued)",
        ],
    },

    "reinsurance_optimization": {
        "execution_playbook": [
            {"step": "Review treaty structure vs actual loss experience: compare cedant strategy (proportional vs XL), retention levels, and RI panel performance", "owner_role": "Chief Actuary / Reinsurance", "duration_weeks": 4},
            {"step": "Benchmark RI cost (net RI premium as % of gross) vs peer insurers; model optimised retention and treaty structure using stochastic loss model", "owner_role": "Actuarial / Reinsurance", "duration_weeks": 5},
            {"step": "Run competitive RI tender with shortlisted panel; negotiate improved terms for proportional treaties and aggregate XL covers", "owner_role": "Reinsurance Head / Procurement", "duration_weeks": 8},
            {"step": "Track RI cost ratio, net combined ratio, and RI recovery rate by treaty annually; submit updated IRDAI filing", "owner_role": "Finance / Actuarial", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "RI cost as % of gross premium >25% for lines where peer average is <18%, indicating over-cession", "evidence_source": "irdai_annual_report_peer_comparison", "confirms": "Retention optimisation and treaty restructuring will reduce RI cost"},
            {"signal": "Proportional RI cession >40% for motor or fire where historical combined ratio supports higher self-retention", "evidence_source": "loss_triangle_analysis", "confirms": "Shifting to XL or higher retention will reduce cession cost on profitable lines"},
            {"signal": "RI panel not reviewed for >3 years despite changes in company risk profile or reinsurer ratings", "evidence_source": "reinsurance_contract_register", "confirms": "Panel rationalisation will improve pricing and counterparty quality"},
        ],
        "required_data_fields": [
            "RI treaty register with cession rate, premium, and recovery data by treaty",
            "Loss triangles and development factors by line of business",
            "Reinsurer credit ratings and panel review history",
            "Gross and net combined ratio by product line (3 years)",
            "IRDAI reinsurance program filing requirements",
        ],
    },

    "investment_ops_efficiency": {
        "execution_playbook": [
            {"step": "Audit investment operations: measure settlement fails, reconciliation FTE-hours, custodian fees, and OMS/TMS integration gaps", "owner_role": "CIO / Investment Operations", "duration_weeks": 3},
            {"step": "Rationalise custodian and depository relationships: consolidate to ≤2 custodians per asset class; negotiate fee schedules based on AUM volume", "owner_role": "Finance / Investment Ops", "duration_weeks": 5},
            {"step": "Implement OMS-to-custodian STP for equity and fixed income trade settlement; automate NAV reconciliation and regulatory reporting to IRDAI", "owner_role": "IT / Investment Ops", "duration_weeks": 8},
            {"step": "Track settlement fail rate, operations cost per portfolio, and regulatory reporting accuracy monthly", "owner_role": "FP&A / Investment Ops", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Trade settlement fail rate >1% of settled trades, generating penalty and manual investigation cost", "evidence_source": "settlement_data", "confirms": "STP and OMS integration will reduce settlement failures"},
            {"signal": "Investment operations FTE >20 with >50% of time on manual reconciliation and report preparation", "evidence_source": "ops_time_study", "confirms": "Automation will release FTE capacity and reduce operations cost"},
            {"signal": "Custodian and depository fee spend >15 bps of AUM vs peer benchmark <10 bps", "evidence_source": "custodian_fee_data", "confirms": "Consolidation and renegotiation will reduce custody cost"},
        ],
        "required_data_fields": [
            "Investment operations FTE count and time allocation by activity",
            "Custodian fee schedule and AUM by custodian",
            "Settlement fail rate and penalty data",
            "OMS and custodian integration architecture",
            "IRDAI investment reporting requirements",
        ],
    },

    "actuarial_automation": {
        "execution_playbook": [
            {"step": "Inventory actuarial models by type (reserving, pricing, capital modelling) and technology (Moses/Prophet/R/Excel); identify manual bottlenecks in production run", "owner_role": "Chief Actuary", "duration_weeks": 3},
            {"step": "Migrate legacy models from Excel to actuarial modelling platform (Prophet, R, Python); establish version control and model validation governance", "owner_role": "Actuarial / IT", "duration_weeks": 10},
            {"step": "Automate quarterly reserve production run and IRDAI reporting; implement parallel run for one cycle to validate output", "owner_role": "Actuarial / IT", "duration_weeks": 8},
            {"step": "Track actuarial production run time, model error rate, and FTE release from automation monthly", "owner_role": "FP&A / Actuarial", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Quarterly reserve production run takes >3 weeks of actuary time due to manual model execution and reconciliation", "evidence_source": "actuarial_time_study", "confirms": "Automation will accelerate close and free senior actuarial capacity"},
            {"signal": "Actuarial models >50% in Excel with no version control or audit trail", "evidence_source": "model_inventory", "confirms": "Platform migration will reduce model risk and improve auditability"},
            {"signal": "IRDAI actuarial filing requires manual preparation consuming >50 actuary-hours per quarter", "evidence_source": "regulatory_reporting_time_study", "confirms": "Automation will reduce compliance cost and risk of restatement"},
        ],
        "required_data_fields": [
            "Actuarial model inventory by type and technology",
            "Production run timeline and FTE-hours by model type",
            "IRDAI actuarial reporting requirements and schedule",
            "IT infrastructure for actuarial modelling platform",
            "Model validation and governance framework",
        ],
    },

    # ----------------------------------------------------------------- IT/ITES
    "license_rightsizing": {
        "execution_playbook": [
            {"step": "Deploy SAM (Software Asset Management) tool to scan all endpoints and servers; reconcile entitlements vs active usage over 90 days", "owner_role": "IT Procurement / SAM", "duration_weeks": 3},
            {"step": "Identify over-licensed users (named users with zero usage in 90 days) and tier mismatches (full licence where reader/viewer suffices)", "owner_role": "SAM / IT Finance", "duration_weeks": 3},
            {"step": "Reclaim over-licensed seats before next renewal; right-size tier mix in renewal negotiation with vendor (Microsoft, Oracle, SAP, Salesforce)", "owner_role": "IT Procurement", "duration_weeks": 4},
            {"step": "Implement continuous licence monitoring; gate new seat requests through SAM tool; track licence spend per head monthly", "owner_role": "IT Finance / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Software licence spend per employee >₹80,000/year with >30% of seats showing zero or minimal usage in past 90 days", "evidence_source": "sam_tool_report", "confirms": "Rightsizing will yield direct licence spend reduction at next renewal"},
            {"signal": "Full-access licences issued to users who only consume reports or dashboards, where cheaper viewer tier exists", "evidence_source": "licence_entitlement_vs_usage", "confirms": "Tier rationalisation will reduce per-seat cost without impacting productivity"},
            {"signal": "Multi-year licence agreements expiring within 12 months with no renegotiation underway", "evidence_source": "contract_register", "confirms": "Renewal window is open for rightsizing negotiation"},
        ],
        "required_data_fields": [
            "Licence entitlement data by software title, user, and tier",
            "Active usage data (logins, feature usage) by user over 90 days",
            "Contract renewal dates and pricing tiers by vendor",
            "Headcount forecast for planning period",
            "Vendor audit exposure and licence true-up obligations",
        ],
    },

    "cloud_finops": {
        "execution_playbook": [
            {"step": "Enable cloud cost discovery: tag all resources by BU, project, and environment; implement cost allocation dashboard by AWS/Azure/GCP billing account", "owner_role": "FinOps / Cloud Engineering", "duration_weeks": 3},
            {"step": "Identify top-5 cost drivers: idle/underutilised resources, oversized instances, unattached volumes, and unused reserved instances", "owner_role": "FinOps", "duration_weeks": 3},
            {"step": "Right-size running instances and migrate to modern SKUs; purchase reserved instances or savings plans for steady-state workloads", "owner_role": "Cloud Engineering / IT Finance", "duration_weeks": 6},
            {"step": "Implement automated shutdown for non-prod environments outside business hours; enforce budget alerts and FinOps governance monthly", "owner_role": "FinOps / IT Finance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Cloud resources with CPU/memory utilisation <20% on average representing >30% of total cloud spend", "evidence_source": "cloud_monitoring_data", "confirms": "Rightsizing will reduce cloud spend without impacting workload performance"},
            {"signal": "On-demand pricing paid for >60% of steady-state workloads (no reserved instances or savings plans)", "evidence_source": "cloud_billing_report", "confirms": "Commitment purchase will reduce on-demand premium by 30-40%"},
            {"signal": "Non-production environments running 24/7 with weekend and off-hours utilisation <10%", "evidence_source": "cloud_usage_data", "confirms": "Automated shutdown will reduce non-prod cloud spend by 40-60%"},
        ],
        "required_data_fields": [
            "Cloud billing data by account, service, and resource (3 months)",
            "Resource utilisation data (CPU, memory, storage) by instance",
            "Tagging hygiene report and resource inventory",
            "Reserved instance and savings plan coverage and utilisation",
            "Non-production environment inventory and usage pattern",
        ],
    },

    "subcontractor_optimization": {
        "execution_playbook": [
            {"step": "Classify all subcontractor spend: T&M vs fixed-price, offshore vs onshore, and vendor tier; calculate effective bill rate and margin by vendor", "owner_role": "Delivery Head / Procurement", "duration_weeks": 3},
            {"step": "Assess Statement of Work quality: identify T&M contracts that should be fixed-price given defined scope; convert and enforce milestone billing", "owner_role": "Programme Management / Legal", "duration_weeks": 5},
            {"step": "Rationalise vendor panel: concentrate volume in top-5 strategic partners for improved pricing and SLA leverage; exit tail vendors", "owner_role": "Vendor Management / Procurement", "duration_weeks": 6},
            {"step": "Track subcontractor spend as % of project cost, effective bill rate by skill category, and vendor SLA compliance monthly", "owner_role": "FP&A / Delivery", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Subcontractor spend >35% of total project cost with >60% on T&M basis for work with defined scope", "evidence_source": "subcontractor_spend_data", "confirms": "Fixed-price conversion and bill-rate renegotiation will reduce subcontractor cost"},
            {"signal": "Effective bill rate for subcontractor roles 20% above internal FTE equivalent cost for similar skills", "evidence_source": "cost_comparison_analysis", "confirms": "Renegotiation or in-house replacement will reduce cost per skilled FTE"},
            {"signal": "Vendor panel >30 subcontractors with bottom-half contributing <10% of project delivery", "evidence_source": "vendor_performance_data", "confirms": "Consolidation will improve pricing leverage and reduce vendor management overhead"},
        ],
        "required_data_fields": [
            "Subcontractor spend by vendor, project, and contract type (T&M vs fixed-price)",
            "Bill rate by vendor and skill category vs internal FTE cost equivalent",
            "Vendor performance data (SLA compliance, defect rate, on-time delivery)",
            "Statement of Work quality assessment by contract",
            "Internal bench vs subcontractor skills overlap analysis",
        ],
    },

    "tech_debt_payoff": {
        "execution_playbook": [
            {"step": "Conduct tech debt inventory: assess each system for code quality (cyclomatic complexity, test coverage), operational risk, and business cost (incident rate, manual workarounds)", "owner_role": "Engineering Leadership / Architecture", "duration_weeks": 4},
            {"step": "Prioritise debt by business impact × remediation effort matrix; build business case for top-5 debt items using incident cost and velocity impact data", "owner_role": "CTO / FP&A", "duration_weeks": 3},
            {"step": "Allocate dedicated tech debt sprint capacity (20% of engineering velocity); execute refactoring roadmap with measurable quality gates", "owner_role": "Engineering / Product", "duration_weeks": 16},
            {"step": "Track DORA metrics (deployment frequency, lead time, change failure rate, MTTR) and incident cost monthly; report velocity improvement to CTO", "owner_role": "Engineering / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Change failure rate >15% or MTTR >4 hours for production incidents on core systems indicating high tech debt", "evidence_source": "dora_metrics", "confirms": "Tech debt payoff will reduce incident frequency and recovery cost"},
            {"signal": "Engineering velocity declining or stagnating despite headcount growth due to maintenance overhead", "evidence_source": "delivery_metrics", "confirms": "Tech debt is consuming engineering capacity at the expense of new capability"},
            {"signal": "Incident cost (engineering time + business impact) >5% of total engineering budget annually", "evidence_source": "incident_management_data", "confirms": "Tech debt reduction ROI is positive on 18-month payback horizon"},
        ],
        "required_data_fields": [
            "Tech debt inventory by system with business impact and remediation effort estimates",
            "DORA metrics history (deployment frequency, lead time, change failure rate, MTTR)",
            "Incident log with engineering resolution time and business cost",
            "Engineering velocity trend (story points delivered per sprint over 12 months)",
            "System architecture assessment for highest-debt components",
        ],
    },

    "platform_consolidation": {
        "execution_playbook": [
            {"step": "Build application portfolio inventory: map all active applications to business function, technology, cost, and user base; flag functional duplicates", "owner_role": "IT Architecture / SAM", "duration_weeks": 4},
            {"step": "Apply rationalization criteria (keep, consolidate, migrate, retire) to each application; develop migration sequencing based on dependencies and risk", "owner_role": "CTO / Enterprise Architecture", "duration_weeks": 4},
            {"step": "Execute migration in waves starting with lowest-risk applications; decommission retired systems and reclaim licences", "owner_role": "IT Delivery / Programme", "duration_weeks": 16},
            {"step": "Track application count, annual maintenance cost per app, and licence spend reduction monthly", "owner_role": "IT Finance / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Application portfolio >200 applications with >30% estimated as candidates for consolidation or retirement", "evidence_source": "application_portfolio_assessment", "confirms": "Rationalization will reduce maintenance cost and complexity"},
            {"signal": "Annual maintenance and support cost for legacy applications >40% of total IT spend", "evidence_source": "it_cost_breakdown", "confirms": "Migrating off legacy will redirect spend to value-adding capability"},
            {"signal": "Functional duplicate applications in >3 business domains (e.g., multiple CRMs, 2+ ERP instances)", "evidence_source": "application_landscape_review", "confirms": "Consolidation to single platform will reduce per-function technology cost"},
        ],
        "required_data_fields": [
            "Application inventory with business owner, user count, annual cost, and age",
            "Functional overlap assessment (capability map vs application coverage)",
            "Technical debt and supportability rating by application",
            "Migration complexity and estimated effort by application",
            "Contract terms and licence obligations for applications under consideration",
        ],
    },

    "genai_productivity": {
        "execution_playbook": [
            {"step": "Identify top-5 GenAI use cases by engineering function: code generation (Copilot), test automation, documentation, code review, and incident summarisation", "owner_role": "Engineering Leadership / Innovation", "duration_weeks": 3},
            {"step": "Pilot with volunteer engineering squads; measure code acceptance rate, PR cycle time, and defect density vs non-pilot baseline", "owner_role": "Engineering / Pilot Teams", "duration_weeks": 6},
            {"step": "Scale proven use cases organisation-wide: standardise tool choice, establish prompt library, and integrate into IDE and CI/CD pipeline", "owner_role": "CTO / DevOps", "duration_weeks": 8},
            {"step": "Track engineering throughput (features delivered per sprint), time-to-merge, and GenAI tool adoption rate monthly", "owner_role": "FP&A / Engineering", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Developer time on boilerplate code, test writing, and documentation >40% of sprint capacity", "evidence_source": "engineering_time_allocation_survey", "confirms": "GenAI code assistance will free developer time for higher-value engineering work"},
            {"signal": "Engineering throughput (features per sprint) flat or declining despite headcount growth", "evidence_source": "delivery_metrics", "confirms": "Productivity augmentation tool will improve output per engineer"},
            {"signal": "Existing GenAI tool licences (Copilot, etc.) paid but active usage <40% of eligible developers", "evidence_source": "tool_usage_analytics", "confirms": "Driving adoption of existing tools will improve ROI without incremental cost"},
        ],
        "required_data_fields": [
            "Engineering time allocation by activity type (feature dev, testing, docs, review, bugs)",
            "GenAI tool adoption data (active users vs licences) by tool and team",
            "Engineering throughput metrics (velocity, PR cycle time, deployment frequency)",
            "Test coverage and defect density baseline data",
            "Cost per engineer (fully loaded) by band and location",
        ],
    },

    "remote_first_realestate": {
        "execution_playbook": [
            {"step": "Measure actual office utilisation using badge data, Wi-Fi heatmap, or booking system; establish utilisation baseline by building and floor", "owner_role": "Facilities / HR", "duration_weeks": 3},
            {"step": "Define remote-first policy aligned with engineering productivity data; set target seat-to-employee ratio (1:1.5 for hybrid, 1:2 for remote-first)", "owner_role": "CHRO / CTO", "duration_weeks": 3},
            {"step": "Identify consolidation and exit opportunities at next lease break or expiry; negotiate surrender or sublease for excess space", "owner_role": "Real Estate / Legal / Finance", "duration_weeks": 10},
            {"step": "Track cost-per-seat, utilisation rate, and real estate cost as % of payroll quarterly", "owner_role": "FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Average office utilisation <55% of peak capacity post-implementation of hybrid work policy", "evidence_source": "occupancy_sensing_data", "confirms": "Space consolidation and sublease will reduce real estate cost"},
            {"signal": "Real estate cost >8% of total operating cost vs IT/ITES peer benchmark of <5% in remote-first models", "evidence_source": "cost_breakdown", "confirms": "Real estate rationalisation will materially improve margin"},
            {"signal": "Engineering team productivity (output per developer) equal or higher for remote vs office developers in prior assessment", "evidence_source": "productivity_analysis", "confirms": "Remote-first model will not compromise engineering output while reducing facility cost"},
        ],
        "required_data_fields": [
            "Office occupancy data by floor and building (badge, Wi-Fi, booking system)",
            "Engineering team distribution (office vs remote vs hybrid) by headcount",
            "Real estate cost per sq ft and per seat by location",
            "Lease terms, break-clause dates, and sublease market rates",
            "Engineering productivity data by location and work model",
        ],
    },

    "build_vs_buy_optimization": {
        "execution_playbook": [
            {"step": "Inventory all custom-built applications: business function, cost to build, annual maintenance, and strategic differentiation assessment", "owner_role": "CTO / Product Management", "duration_weeks": 4},
            {"step": "Apply build/buy/borrow decision framework: evaluate commercial alternatives for non-differentiating capabilities; calculate TCO over 5 years", "owner_role": "Architecture / Procurement", "duration_weeks": 4},
            {"step": "Vendor market scan for shortlisted 'buy' candidates; negotiate proof-of-concept or pilot agreements before full commitment", "owner_role": "IT Procurement", "duration_weeks": 6},
            {"step": "Execute migration for validated 'buy' decisions; decommission custom build; track engineering capacity released and TCO savings", "owner_role": "IT Delivery / FP&A", "duration_weeks": 12},
        ],
        "diagnostic_signals": [
            {"signal": "Engineering teams spending >30% of capacity on maintaining non-differentiating internal tools vs building customer-facing features", "evidence_source": "engineering_capacity_allocation", "confirms": "Replacing with commercial alternatives will free engineering capacity for value-creation"},
            {"signal": "Custom-built capability available as proven SaaS at <50% of annual maintenance cost of internal equivalent", "evidence_source": "market_scan_tco_analysis", "confirms": "Buy decision will reduce cost and shift maintenance risk to vendor"},
            {"signal": "Custom application defect rate or downtime significantly above commercial equivalent benchmark", "evidence_source": "incident_and_quality_data", "confirms": "Commercial alternative will improve quality alongside cost reduction"},
        ],
        "required_data_fields": [
            "Custom application inventory with annual maintenance cost and engineering headcount",
            "Business capability map with strategic differentiation classification",
            "Commercial vendor alternatives and indicative pricing for shortlisted capabilities",
            "5-year TCO comparison model for build vs buy by application",
            "Engineering capacity allocation by application and feature type",
        ],
    },

    "devops_automation": {
        "execution_playbook": [
            {"step": "Baseline DORA metrics and SDLC process: measure lead time, deployment frequency, change failure rate, and MTTR for all production services", "owner_role": "Engineering / DevOps", "duration_weeks": 3},
            {"step": "Implement CI/CD pipeline automation for top-5 critical services: automated testing, container build, and deployment gates", "owner_role": "DevOps / Platform Engineering", "duration_weeks": 8},
            {"step": "Automate infrastructure provisioning (IaC using Terraform/Pulumi) and environment management; standardise on container orchestration (Kubernetes)", "owner_role": "Platform Engineering", "duration_weeks": 8},
            {"step": "Track DORA metrics monthly; set targets for deployment frequency (daily) and change failure rate (<5%); reward teams against metric improvement", "owner_role": "CTO / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Deployment frequency <1/week for production services where business needs faster release cycle", "evidence_source": "dora_metrics", "confirms": "CI/CD pipeline automation will dramatically increase deployment frequency"},
            {"signal": "Lead time from code commit to production >2 weeks due to manual testing and approval gates", "evidence_source": "sdlc_cycle_time_data", "confirms": "Pipeline automation will reduce lead time and engineering opportunity cost"},
            {"signal": "Infrastructure provisioning takes >2 days due to manual ticketing and configuration", "evidence_source": "infrastructure_request_log", "confirms": "IaC and automated provisioning will reduce developer waiting time and improve throughput"},
        ],
        "required_data_fields": [
            "DORA metrics baseline (deployment frequency, lead time, change failure rate, MTTR)",
            "Current CI/CD pipeline maturity assessment by service",
            "Infrastructure provisioning time and method (manual vs automated) by environment",
            "Engineering time allocation: feature work vs operational and deployment overhead",
            "Cloud and container platform capabilities and current adoption level",
        ],
    },

    # ------------------------------------------------------- MANUFACTURING DIVERSIFIED
    "mro_consolidation": {
        "execution_playbook": [
            {"step": "Aggregate MRO spend from plant stores, purchase orders, and P-cards across all sites; classify by category (mechanical, electrical, instrumentation, safety)", "owner_role": "Procurement / Plant Management", "duration_weeks": 3},
            {"step": "Identify consolidation candidates: categories with >5 vendors and fragmented spend; build RFQ for preferred vendor agreements by category", "owner_role": "Strategic Sourcing / Stores", "duration_weeks": 4},
            {"step": "Negotiate VMI (Vendor Managed Inventory) agreements for fast-moving C-class items with top MRO distributors; implement consignment for critical spares", "owner_role": "Procurement / Stores", "duration_weeks": 8},
            {"step": "Build MRO catalogue in procurement system; enforce catalogue buying; track MRO cost per site and spend under management monthly", "owner_role": "Procurement / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "MRO vendor count >100 per site with top-20 vendors representing <50% of spend, indicating fragmentation", "evidence_source": "vendor_master", "confirms": "Consolidation will improve leverage and reduce procurement overhead"},
            {"signal": "MRO spend outside purchase order (P-card or credit card) >20%, indicating maverick purchasing", "evidence_source": "spend_classification_data", "confirms": "Catalogue discipline and VMI will reduce off-contract buying"},
            {"signal": "MRO unit price variance >30% for same item across sites due to decentralised purchasing", "evidence_source": "price_analysis", "confirms": "Group contracts will harmonise pricing across plants"},
        ],
        "required_data_fields": [
            "MRO spend by site, category, and vendor (12 months)",
            "Purchase order vs credit card spend split",
            "Price data for common items across sites",
            "Current VMI and consignment arrangements",
            "Critical vs non-critical spares classification",
        ],
    },

    "energy_audit_compliance": {
        "execution_playbook": [
            {"step": "Commission BEE-certified energy audit for all facilities above PAT cycle threshold; establish SEC (Specific Energy Consumption) baseline by production unit", "owner_role": "Energy Manager / Operations", "duration_weeks": 4},
            {"step": "Prioritise energy efficiency projects by payback period (<3 years): motor replacement, variable frequency drives, compressed air, and lighting retrofit", "owner_role": "Energy Team / Engineering", "duration_weeks": 5},
            {"step": "Execute top-10 projects with investment approval; file PAT cycle designation certificate; install DECs (Designated Energy Consumers) as required", "owner_role": "Engineering / Finance", "duration_weeks": 12},
            {"step": "Track SEC monthly vs PAT cycle target; submit BEE annual report; prepare for ESCerts trading if target exceeded", "owner_role": "Energy Manager / Compliance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Specific Energy Consumption (SEC) above BEE benchmark for the sector or above PAT cycle target", "evidence_source": "energy_audit_report", "confirms": "Energy efficiency projects will reduce SEC and electricity cost, and avoid PAT penalty"},
            {"signal": "Energy cost as % of COGS >12% for electricity-intensive processes (metal, cement, chemical, glass)", "evidence_source": "cogs_breakdown", "confirms": "Energy efficiency investment will materially reduce production cost"},
            {"signal": "Motor load factor <60% for >30% of installed motor capacity indicating oversized or inefficient motors", "evidence_source": "energy_audit_motor_survey", "confirms": "Motor replacement or VFD installation will reduce electricity consumption"},
        ],
        "required_data_fields": [
            "Energy consumption data by fuel type, unit, and process (12 months)",
            "BEE PAT cycle designation status and SEC target",
            "Energy audit report with top-10 efficiency recommendations and investment estimates",
            "Electricity tariff structure and peak demand charges",
            "Motor inventory with load factor and age data",
        ],
    },

    "gst_itc_recovery": {
        "execution_playbook": [
            {"step": "Reconcile GSTR-2A/2B (supplier invoices filed) vs GSTR-3B (ITC claimed) for all returns periods; identify unclaimed ITC by GST head", "owner_role": "Tax / Accounts", "duration_weeks": 3},
            {"step": "Investigate ITC gaps: misclassified blocked credits, supplier non-filing, and wrong GST head mapping in ERP; quantify recoverable amount", "owner_role": "Indirect Tax / Finance", "duration_weeks": 4},
            {"step": "File DRC-03 or revised GSTR-3B for recoverable credits; engage with vendors who have not filed returns to resolve mismatch", "owner_role": "Tax / Procurement", "duration_weeks": 6},
            {"step": "Implement monthly auto-reconciliation in ERP/GSTN portal; update chart of accounts to correctly classify ITC-eligible expenses", "owner_role": "Finance / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "ITC claimed as % of total GST paid <80% for input-intensive sectors (manufacturing, construction, logistics) indicating under-claim", "evidence_source": "gst_returns_data", "confirms": "ITC recovery will yield direct cash refund or credit"},
            {"signal": "GSTR-2A/2B vs GSTR-3B ITC mismatch >5% of eligible ITC pool", "evidence_source": "gst_reconciliation_report", "confirms": "Reconciliation exercise will identify recoverable amount"},
            {"signal": "Blocked credit (Schedule II items) incorrectly claimed or ITC-eligible items incorrectly coded in ERP as non-ITC", "evidence_source": "gl_classification_audit", "confirms": "GL reclassification will unlock additional ITC"},
        ],
        "required_data_fields": [
            "GSTR-2A/2B data vs GSTR-3B ITC claim (all periods under review)",
            "GL coding for input costs by GST head (ITC eligible vs blocked)",
            "Vendor GSTIN compliance status and filing history",
            "ERP GST configuration and tax code mapping",
            "Prior-year tax authority ITC mismatch notices if any",
        ],
    },

    "logistics_network_redesign": {
        "execution_playbook": [
            {"step": "Build current-state logistics network model: map all origin-destination lanes, carrier rates, volumes, and transit times; calculate cost per tonne-km by lane", "owner_role": "Logistics / Supply Chain", "duration_weeks": 4},
            {"step": "Run network optimisation model (linear programming or simulation) to identify depot location, mode mix, and lane consolidation opportunities", "owner_role": "Supply Chain Analytics", "duration_weeks": 5},
            {"step": "Negotiate revised contracts with carriers based on optimised lane volumes; implement route-and-load planning software", "owner_role": "Logistics Procurement", "duration_weeks": 8},
            {"step": "Track freight cost per tonne-km, OTIF, and carrier performance monthly; reoptimise annually", "owner_role": "FP&A / Logistics", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Freight cost as % of net sales above sector benchmark with <70% truck utilisation on primary lanes", "evidence_source": "logistics_spend_report", "confirms": "Network redesign and load optimisation will reduce freight cost"},
            {"signal": "Average truck fill rate <75% on primary distribution lanes", "evidence_source": "transport_management_system_data", "confirms": "Load consolidation or route optimisation will improve cost per tonne"},
            {"signal": "Depot footprint not reviewed in >5 years despite changes in production locations or customer geography", "evidence_source": "logistics_network_assessment", "confirms": "Network optimisation will reduce depot and haul costs"},
        ],
        "required_data_fields": [
            "Freight spend by lane, carrier, and mode (12 months)",
            "Shipment volume and weight by origin-destination pair",
            "Current depot locations and lease terms",
            "Truck fill rate and load factor data by lane",
            "Customer geography and delivery frequency requirements",
        ],
    },

    "packaging_optimisation": {
        "execution_playbook": [
            {"step": "Map packaging specifications for top-50 SKUs: material type, weight per unit, supplier, unit cost, and waste generated", "owner_role": "R&D / Procurement / Sustainability", "duration_weeks": 3},
            {"step": "Identify lightweighting opportunities (reduce material per unit) and material substitution (mono-material, recycled content) without compromising shelf life", "owner_role": "R&D / Quality / Procurement", "duration_weeks": 4},
            {"step": "Qualify alternative packaging suppliers; run structural testing per ISTA/FEFCO standards; obtain retail and logistics sign-off", "owner_role": "Supplier Quality / R&D", "duration_weeks": 8},
            {"step": "Roll out optimised specifications; track packaging cost per SKU, waste % per pack, and EPR compliance status monthly", "owner_role": "FP&A / Sustainability", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Packaging cost as % of COGS >8% for categories where packaging intensity is not driven by product fragility or regulatory requirement", "evidence_source": "cogs_breakdown_by_sku", "confirms": "Lightweighting and specification review will reduce packaging cost"},
            {"signal": "Primary packaging weight per unit 15–25% above benchmarked competitors for same product category", "evidence_source": "packaging_benchmarking", "confirms": "Lightweighting to peer specification will reduce material cost"},
            {"signal": "EPR (Extended Producer Responsibility) compliance cost growing due to non-recyclable or multi-layer packaging", "evidence_source": "epr_filing_data", "confirms": "Mono-material or recyclable substitution will reduce EPR liability"},
        ],
        "required_data_fields": [
            "Packaging specification and cost per SKU (material, weight, supplier, unit cost)",
            "Packaging waste percentage and EPR filing data",
            "Competitor packaging specification benchmarks by category",
            "Structural integrity requirements by product type (fragility, shelf life)",
            "Retailer and logistics packaging requirements",
        ],
    },

    "factory_automation": {
        "execution_playbook": [
            {"step": "Conduct automation opportunity assessment: rank processes by labour intensity, repeatability, defect risk, and automation technology readiness", "owner_role": "Manufacturing Engineering / Operations", "duration_weeks": 4},
            {"step": "Build ROI model for top-5 automation investments (robotics, vision systems, AGVs, PLC automation); source vendor quotes and validate cycle-time improvement", "owner_role": "Engineering / Finance", "duration_weeks": 4},
            {"step": "Execute automation in phased deployment: pilot on one line, validate OEE improvement, then scale to remaining lines", "owner_role": "Projects / Engineering", "duration_weeks": 16},
            {"step": "Track OEE improvement, direct labour reduction per unit, defect rate, and automation ROI monthly", "owner_role": "FP&A / Manufacturing", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Direct labour cost per unit of production >15% above peer benchmark for comparable automation intensity", "evidence_source": "cost_per_unit_benchmarking", "confirms": "Automation investment will reduce direct labour cost per unit"},
            {"signal": "Process defect rate >2% on manual assembly or inspection steps vs <0.5% for equivalent automated process at competitor", "evidence_source": "quality_data", "confirms": "Automation will improve quality and reduce rework cost"},
            {"signal": "OEE <65% for key production lines due to changeover time, minor stoppages, and speed loss", "evidence_source": "oee_data", "confirms": "Automation of bottleneck steps will improve OEE and throughput"},
        ],
        "required_data_fields": [
            "Direct labour cost per unit by production line and shift",
            "OEE data (availability, performance, quality) by line (12 months)",
            "Defect rate and rework cost by process step",
            "Automation vendor options and capital cost estimates",
            "Production volume forecast for ROI model",
        ],
    },

    # --------------------------------------------------------- PHARMA / LIFE SCI
    "clinical_trial_efficiency": {
        "execution_playbook": [
            {"step": "Audit active clinical trial portfolio: assess protocol complexity, site enrolment rate, CRO performance, and cost per patient enrolled vs benchmark", "owner_role": "Clinical Operations / Finance", "duration_weeks": 4},
            {"step": "Redesign protocol for top-3 delayed studies: simplify endpoints, adopt decentralised trial (DCT) elements (eConsent, remote monitoring), and use risk-based monitoring", "owner_role": "Clinical Development / Medical Affairs", "duration_weeks": 6},
            {"step": "Renegotiate CRO contracts: shift from FTE-based to milestone-based pricing; consolidate to preferred CRO panel (2–3 vendors)", "owner_role": "Procurement / Clinical Ops", "duration_weeks": 8},
            {"step": "Track cost per patient enrolled, enrolment velocity, and protocol deviation rate by study monthly", "owner_role": "FP&A / Clinical Ops", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Cost per patient enrolled >30% above CRO industry benchmark for comparable therapeutic area and Phase", "evidence_source": "clinical_trial_cost_report", "confirms": "Protocol simplification and CRO renegotiation will reduce per-patient cost"},
            {"signal": "Average patient enrolment rate <80% of plan, extending study timelines and increasing fixed trial costs", "evidence_source": "ctms_data", "confirms": "Site optimisation and DCT elements will improve enrolment velocity"},
            {"signal": "CRO panel >5 vendors with no preferred vendor agreement or performance benchmarking", "evidence_source": "procurement_data", "confirms": "CRO consolidation will improve pricing leverage and management efficiency"},
        ],
        "required_data_fields": [
            "Active clinical trial list with status, cost to date, and estimated cost to complete",
            "Cost per patient enrolled vs industry benchmark by therapeutic area",
            "CRO performance data (enrolment rate, protocol deviations, budget adherence)",
            "CTMS data: site performance, screen fail rates, and enrolment milestones",
            "DCT technology readiness assessment",
        ],
    },

    "manufacturing_cogs": {
        "execution_playbook": [
            {"step": "Decompose COGS by component: API, excipients, packaging, manufacturing overhead, and quality cost; compare vs comparable product benchmark", "owner_role": "Manufacturing / Finance", "duration_weeks": 3},
            {"step": "Conduct yield analysis by manufacturing step: identify yield losses, batch failure rate, and OOS events for root-cause and correction", "owner_role": "Manufacturing / QA", "duration_weeks": 4},
            {"step": "Qualify alternate API/excipient suppliers under existing ANDA/NDA filings where permitted; negotiate on volume-based pricing", "owner_role": "Procurement / Regulatory Affairs", "duration_weeks": 10},
            {"step": "Track COGS per unit, batch failure rate, and API price variance monthly; rebaseline after each yield improvement project", "owner_role": "FP&A / Manufacturing", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Manufacturing COGS as % of net sales >45% for branded formulations or >35% for generics vs peer benchmark", "evidence_source": "cogs_breakdown", "confirms": "Yield improvement and material cost reduction will improve gross margin"},
            {"signal": "Batch failure or out-of-specification rate >2% for key products generating significant reprocessing and write-off cost", "evidence_source": "batch_record_data", "confirms": "Process optimisation will reduce failure cost and improve OEE"},
            {"signal": "Single API supplier dependency for >50% of product portfolio creating price and supply vulnerability", "evidence_source": "procurement_data", "confirms": "Supplier diversification will reduce risk and restore competitive tension"},
        ],
        "required_data_fields": [
            "COGS breakdown by product and component (API, excipients, packaging, overhead)",
            "Batch yield data by product and manufacturing site (12 months)",
            "API price trends and supplier concentration data",
            "ANDA/NDA site and supplier qualification status",
            "Regulatory filing requirements for alternate supplier qualification",
        ],
    },

    "sales_force_sizing": {
        "execution_playbook": [
            {"step": "Analyse prescriber data (IMS/IQVIA) by territory: map TRx volume, rep call frequency, and call coverage ratio against yield per call", "owner_role": "Sales Force Effectiveness / Commercial", "duration_weeks": 4},
            {"step": "Build territory productivity model: rank territories by revenue opportunity vs current rep cost; identify over/under-covered territories", "owner_role": "SFE / Finance", "duration_weeks": 3},
            {"step": "Resize field force: consolidate under-productive territories, reassign or exit under-performing reps, redeploy to high-growth geographies", "owner_role": "Sales Head / HR", "duration_weeks": 8},
            {"step": "Track rep productivity (TRx growth, net sales per rep), coverage index, and SFA compliance monthly", "owner_role": "FP&A / SFE", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Rep productivity (net sales per rep) >20% below peer benchmark for comparable therapeutic area and market maturity", "evidence_source": "sales_force_benchmarking", "confirms": "Rightsizing and redeployment will improve revenue per rep without losing market share"},
            {"signal": "Territory coverage index >120% for mature product with flat TRx trajectory (over-covered, diminishing returns)", "evidence_source": "iqvia_sfe_data", "confirms": "Territory consolidation will reduce field force cost without sales impact"},
            {"signal": "Field force cost as % of net sales >20% vs specialty pharma benchmark of <15%", "evidence_source": "cost_breakdown", "confirms": "Salesforce optimisation will improve commercial efficiency"},
        ],
        "required_data_fields": [
            "Territory-level TRx data (IQVIA/IMS) and rep call activity (SFA reports)",
            "Revenue per rep and per territory (12 months)",
            "Rep cost by grade and territory (salary, travel, allowances)",
            "Coverage index and call frequency benchmarks by specialty",
            "Market share data by product and territory",
        ],
    },

    "digital_rep_model": {
        "execution_playbook": [
            {"step": "Segment HCP universe by digital adoption and prescribing behaviour; identify candidates for digital-first (e-detailing, remote) vs in-person engagement model", "owner_role": "SFE / Marketing", "duration_weeks": 3},
            {"step": "Launch e-detailing platform and remote rep capability for digital-preference HCPs; develop content library for digital channels", "owner_role": "Digital / Commercial", "duration_weeks": 6},
            {"step": "Shift field rep call mix: reduce in-person call frequency for digital-responsive HCPs; reallocate rep time to high-value non-digital prescribers", "owner_role": "Sales Head / SFE", "duration_weeks": 8},
            {"step": "Track digital engagement metrics (e-detail views, content consumption), TRx impact by engagement channel, and rep cost-per-call monthly", "owner_role": "FP&A / Commercial Analytics", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "In-person call frequency >8/month for HCPs with confirmed digital adoption and high e-detail engagement", "evidence_source": "sfa_and_digital_engagement_data", "confirms": "Digital channel shift will maintain TRx with lower cost per interaction"},
            {"signal": "Cost per in-person detail call >₹800 vs e-detailing cost <₹200 for comparable reach and message delivery", "evidence_source": "commercial_cost_analysis", "confirms": "Digital model will reduce cost per interaction materially"},
            {"signal": "HCP digital adoption >40% in target specialty (measured by telemedicine usage, conference attendance online, and social media activity)", "evidence_source": "hcp_segmentation_data", "confirms": "Sufficient HCP digital readiness to support engagement model shift"},
        ],
        "required_data_fields": [
            "HCP segmentation: digital adoption score, prescribing value, and current engagement frequency",
            "E-detailing platform capability and content delivery metrics",
            "Cost per interaction by channel (in-person vs digital vs virtual)",
            "TRx correlation data by engagement channel for comparable HCP segments",
            "Rep utilisation and call frequency data from SFA system",
        ],
    },

    "market_access_rebate_mgmt": {
        "execution_playbook": [
            {"step": "Map formulary and tender position by state, insurer, and hospital segment; identify coverage gaps vs competitor access and net price impact of rebates", "owner_role": "Market Access / Finance", "duration_weeks": 3},
            {"step": "Redesign rebate model: shift from volume-based to outcomes/adherence-based rebates where payers will support; model net realisation impact", "owner_role": "Market Access / Legal", "duration_weeks": 5},
            {"step": "Implement contract management system for rebate tracking; automate rebate accrual calculation in ERP to eliminate manual reconciliation", "owner_role": "Finance / IT", "duration_weeks": 6},
            {"step": "Track gross-to-net waterfall by product, net realisation per unit, and formulary access score quarterly", "owner_role": "FP&A / Market Access", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Gross-to-net discount >30% for hospital segment, driven primarily by volume rebates with weak clinical outcomes linkage", "evidence_source": "gross_to_net_analysis", "confirms": "Rebate redesign to outcomes basis will improve net realisation"},
            {"signal": "Rebate accrual error or reversal events >3/quarter due to manual tracking without contract management system", "evidence_source": "finance_audit_log", "confirms": "Automation will reduce accrual errors and improve P&L accuracy"},
            {"signal": "Formulary access gap in key state formularies or hospital tenders vs leading competitor", "evidence_source": "formulary_coverage_map", "confirms": "Market access strategy adjustment will improve revenue opportunity"},
        ],
        "required_data_fields": [
            "Formulary and tender status by state, insurer, and hospital segment",
            "Gross-to-net waterfall by product and channel",
            "Rebate contract terms and accrual data by customer",
            "Contract management system capability assessment",
            "Competitor pricing and formulary access data",
        ],
    },

    "tech_platform_consolidation": {
        "execution_playbook": [
            {"step": "Inventory all commercial and clinical technology platforms (Veeva CRM, CTMS, QMS, PVG, LIMS, ERP); map to vendor, annual cost, and integration dependencies", "owner_role": "IT / Business Analysts", "duration_weeks": 4},
            {"step": "Identify rationalization opportunities: functional duplicates, underutilised licences, and platforms replaceable by existing modules in current stack", "owner_role": "IT Architecture / Procurement", "duration_weeks": 4},
            {"step": "Execute consolidation: migrate to single-vendor Veeva platform (CRM + Vault QMS + eTMF + PromoMats) where feasible; negotiate enterprise agreement", "owner_role": "IT Delivery / Procurement", "duration_weeks": 16},
            {"step": "Decommission retired systems; track licence spend per user and system count monthly", "owner_role": "IT Finance / FP&A", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Technology cost per employee in commercial or R&D function >₹2 L/year with >30% identified as duplicated capability", "evidence_source": "it_cost_per_head_report", "confirms": "Consolidation will reduce per-head technology cost"},
            {"signal": "Veeva CRM deployed but Veeva Vault for QMS or eTMF not adopted, despite functionality overlap", "evidence_source": "veeva_platform_assessment", "confirms": "Expanding single-vendor platform will eliminate point-solution cost"},
            {"signal": "Data integration costs high due to multiple system-to-system feeds between clinical and commercial platforms", "evidence_source": "integration_architecture_review", "confirms": "Platform consolidation will reduce integration maintenance cost"},
        ],
        "required_data_fields": [
            "Technology platform inventory with vendor, users, cost, and contract term",
            "Functional overlap assessment across current platforms",
            "Veeva or alternative enterprise platform capability map",
            "Integration architecture and cost for current system-to-system feeds",
            "Regulatory validation requirements (21 CFR Part 11, GAMP5) for platform changes",
        ],
    },

    "expiry_risk_reduction": {
        "execution_playbook": [
            {"step": "Build expiry risk dashboard: SKU-level inventory by batch, shelf-life remaining, and monthly consumption rate; flag high-risk batches (>30% risk of expiry)", "owner_role": "Supply Chain / Regulatory", "duration_weeks": 3},
            {"step": "Segment high-risk inventory: dose-form suitability for shelf-life extension, reprocessing under QA sign-off, or liquidation to institutional buyer at discount", "owner_role": "Quality / Supply Chain / Finance", "duration_weeks": 3},
            {"step": "Implement demand-driven production planning: set maximum production run length for slow-moving SKUs; reduce build-to-stock for short shelf-life products", "owner_role": "Supply Chain / Operations", "duration_weeks": 6},
            {"step": "Track write-off rate (as % of procurement value), average remaining shelf life at shipment, and expiry waste monthly", "owner_role": "FP&A / Supply Chain", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Expiry write-off >1.5% of total COGS annually, indicating structural overproduction or demand planning inaccuracy", "evidence_source": "write_off_data", "confirms": "Demand-led production planning and FEFO enforcement will reduce expiry risk"},
            {"signal": "Inventory days-on-hand >120 days for products with ≤24-month shelf life", "evidence_source": "inventory_aging_report", "confirms": "Excess inventory with limited shelf life creates material expiry risk"},
            {"signal": "Short-dated inventory (≤6 months shelf life) representing >10% of current stock value", "evidence_source": "batch_master_data", "confirms": "Proactive liquidation or shelf-life extension will recover value"},
        ],
        "required_data_fields": [
            "Batch-level inventory data: SKU, quantity, manufacture date, and expiry date",
            "Monthly consumption data by SKU (12 months)",
            "Historical write-off data by SKU and reason code",
            "Production schedule and build-to-stock vs make-to-order split",
            "Shelf-life extension regulatory feasibility by product",
        ],
    },

    "pharmacovigilance_automation": {
        "execution_playbook": [
            {"step": "Audit ICSR (Individual Case Safety Report) processing workflow: measure intake volume by source, processing time per case, and FTE-hours by activity", "owner_role": "Drug Safety / PV Operations", "duration_weeks": 3},
            {"step": "Implement E2B gateway for electronic exchange with regulators (CDSCO, EMA, FDA); automate intake from digital channels (e-commerce, social media listening)", "owner_role": "IT / Drug Safety", "duration_weeks": 8},
            {"step": "Deploy AI-assisted medical coding (MedDRA) and narrative writing tool; run parallel with manual processing for 60 days before go-live", "owner_role": "Drug Safety / IT", "duration_weeks": 8},
            {"step": "Track ICSR processing time, coding accuracy, and on-time submission rate to CDSCO monthly", "owner_role": "FP&A / Drug Safety", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "ICSR processing volume growing >20% YoY with manual processing model causing backlog and on-time submission risk", "evidence_source": "pv_operations_report", "confirms": "Automation will absorb volume growth without proportionate FTE increase"},
            {"signal": "Average ICSR processing time >3 days per case for non-serious or >8 days for serious reports vs automated benchmark", "evidence_source": "pv_kpi_dashboard", "confirms": "AI-assisted processing will reduce cycle time and regulatory risk"},
            {"signal": "No E2B electronic gateway with CDSCO requiring manual PDF submission of safety reports", "evidence_source": "regulatory_submission_method_audit", "confirms": "E2B gateway will eliminate manual submission and reduce error risk"},
        ],
        "required_data_fields": [
            "ICSR volume by source (HCP, patient, literature, post-market surveillance) and month (12 months)",
            "Processing time and FTE-hours per case by activity (intake, coding, medical review, submission)",
            "CDSCO and ICH E2B compliance requirements for electronic submission",
            "PV database (Argus/ArisG) and E2B gateway capability assessment",
            "AI medical coding tool options and validation requirements",
        ],
    },

    # ----------------------------------------------------------------- PSU/CPSE
    "ind_as_116_lease": {
        "execution_playbook": [
            {"step": "Build comprehensive lease register: identify all contracts that qualify as leases under Ind AS 116 (embedded leases in service contracts included)", "owner_role": "Finance / Accounting", "duration_weeks": 4},
            {"step": "Calculate right-of-use (ROU) asset and lease liability for each lease using incremental borrowing rate; validate against existing balance sheet", "owner_role": "Finance / Auditors", "duration_weeks": 4},
            {"step": "Configure ERP (SAP RE-FX or Oracle Lease) for automated lease amortisation, interest accrual, and disclosure schedule generation", "owner_role": "Finance / IT", "duration_weeks": 6},
            {"step": "File revised balance sheet with ROU assets; update debt covenants disclosure and DPE reporting; train finance team on ongoing Ind AS 116 accounting", "owner_role": "CFO / Finance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Lease-related disclosures incomplete or absent in financial statements for entity with >₹50 Cr annual lease payments", "evidence_source": "financial_statements", "confirms": "Ind AS 116 compliance gap creates regulatory and audit risk"},
            {"signal": "No structured lease register—lease data maintained in spreadsheets without systematic contract tracking", "evidence_source": "lease_management_assessment", "confirms": "Lease register implementation is prerequisite for compliance"},
            {"signal": "Embedded leases in service contracts not identified, creating under-disclosure risk", "evidence_source": "contract_review", "confirms": "Comprehensive contract review will ensure full compliance scope is captured"},
        ],
        "required_data_fields": [
            "All lease contracts (property, vehicles, equipment) with commencement date, term, and lease payments",
            "Service contracts requiring embedded lease assessment",
            "Incremental borrowing rate by tenure for lease liability discounting",
            "ERP lease accounting module capability",
            "DPE reporting requirements for lease disclosures",
        ],
    },

    "csr_efficiency": {
        "execution_playbook": [
            {"step": "Audit CSR spend against Companies Act mandate (2% of average 3-year net profit): classify by project type, implementing agency, and impact measurement quality", "owner_role": "CSR Head / Finance", "duration_weeks": 3},
            {"step": "Rationalise implementing agencies: reduce from >10 to <5 strategic partners with stronger impact monitoring and lower admin overhead", "owner_role": "CSR Head / Procurement", "duration_weeks": 4},
            {"step": "Standardise CSR project selection on mandate-compliant outcomes with measurable beneficiary impact (MoU-linked deliverables)", "owner_role": "CSR Committee / Finance", "duration_weeks": 4},
            {"step": "Track CSR compliance ratio, project impact metrics, and admin overhead as % of CSR spend annually", "owner_role": "Finance / CSR", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "CSR admin and overhead (implementing agency fees + internal management) >15% of total CSR spend", "evidence_source": "csr_accounts", "confirms": "Rationalising implementing agencies will increase direct beneficiary impact"},
            {"signal": "CSR spend not fully compliant with mandate—unspent amounts or spend on non-eligible activities", "evidence_source": "csr_annual_report", "confirms": "Compliance review will prevent penalty under Companies Act Section 135"},
            {"signal": "Implementing agency performance not monitored against outcome metrics for >50% of CSR projects", "evidence_source": "csr_monitoring_report", "confirms": "Strengthening monitoring will improve impact and partner accountability"},
        ],
        "required_data_fields": [
            "CSR spend by project, implementing agency, and activity type",
            "Companies Act mandate calculation (2% of average 3-year net profit)",
            "Implementing agency contracts and performance data",
            "Impact measurement reports by project",
            "CSR committee composition and decision-making process",
        ],
    },

    "public_procurement_reform": {
        "execution_playbook": [
            {"step": "Audit procurement compliance: calculate GeM portal adoption %, DPP/DAC mandates for defence/PSU, and proportion of single-vendor awards", "owner_role": "Procurement Head / Compliance", "duration_weeks": 3},
            {"step": "Develop GeM onboarding plan for categories eligible under GFR Rule 149 / GFR 2017; train procurement team on GeM ordering process", "owner_role": "Procurement / IT", "duration_weeks": 4},
            {"step": "Implement rate-contract framework for high-frequency categories (stationery, IT peripherals, fuel, security) via tender or GeM RC", "owner_role": "Procurement", "duration_weeks": 8},
            {"step": "Track GeM adoption %, single-vendor award ratio, and savings vs benchmark prices monthly; report to Board/CVC", "owner_role": "FP&A / Compliance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "GeM portal adoption <60% of eligible procurement categories despite GFR mandate for PSUs", "evidence_source": "procurement_compliance_report", "confirms": "GeM adoption will reduce procurement cycle time and ensure compliance"},
            {"signal": "Single-vendor award (limited tender or nomination) >30% of procurement value without documented justification", "evidence_source": "cvc_audit_report", "confirms": "Open tendering or rate contracts will reduce procurement cost and audit risk"},
            {"signal": "Procurement unit prices above corresponding DGS&D/GeM rate contract for same specification", "evidence_source": "price_benchmarking", "confirms": "GeM or rate contract adoption will immediately reduce unit prices"},
        ],
        "required_data_fields": [
            "Procurement spend by category with current sourcing method (GeM, tender, nomination)",
            "GeM portal eligibility assessment by category",
            "DGS&D/GeM rate contract prices for common items",
            "CVC audit observations on procurement compliance",
            "GFR 2017 requirements applicable to the entity",
        ],
    },

    "manpower_rationalisation": {
        "execution_playbook": [
            {"step": "Conduct workforce audit: map headcount by function, grade, and age profile; compare span of control and employee-to-revenue ratio vs DPE benchmark", "owner_role": "HR / DPE Nodal Officer", "duration_weeks": 4},
            {"step": "Design VRS (Voluntary Retirement Scheme) package compliant with DPE guidelines; model savings vs payoff cost over 5 years", "owner_role": "HR / Finance / Legal", "duration_weeks": 4},
            {"step": "Launch VRS with targeted eligibility criteria (age ≥50, non-critical skills); process applications with DPE approval as required", "owner_role": "HR Operations / Finance", "duration_weeks": 8},
            {"step": "Redeploy retained staff to high-priority areas; enforce hiring moratorium in areas with surplus; track payroll savings monthly", "owner_role": "FP&A / HR", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Employee cost as % of revenue >35% vs manufacturing/utility sector benchmark of <25%", "evidence_source": "p_and_l_data", "confirms": "Manpower rationalisation will materially improve operating leverage"},
            {"signal": "Average employee age >45 with >40% workforce eligible for retirement in <10 years creating transition opportunity", "evidence_source": "workforce_demographics", "confirms": "VRS and natural attrition can reduce headcount without retrenchment"},
            {"signal": "Employee-to-revenue ratio 2–3× peer PSU benchmark for similar business scale", "evidence_source": "dpe_benchmarking", "confirms": "Productivity improvement through rationalisation is significant"},
        ],
        "required_data_fields": [
            "Workforce headcount by function, grade, age, and location",
            "Payroll cost breakdown by grade and allowance type",
            "DPE benchmark: employee cost ratios for comparable CPSEs",
            "VRS eligibility rules and DPE approval requirements",
            "5-year payroll forecast with and without rationalisation",
        ],
    },

    # ---------------------------------------------------------- RETAIL ORGANIZED
    "store_labor_optimization": {
        "execution_playbook": [
            {"step": "Conduct time-and-motion study at representative stores: measure labour hours by department (cashier, replenishment, customer service) vs transaction volume", "owner_role": "Operations / HR", "duration_weeks": 3},
            {"step": "Implement workforce management software with footfall-linked demand forecasting and automated shift generation by store", "owner_role": "IT / HR", "duration_weeks": 6},
            {"step": "Convert fixed-schedule staff to flexible/part-time model in high-footfall-variance stores; negotiate new employment terms with union where applicable", "owner_role": "HR / Operations", "duration_weeks": 6},
            {"step": "Track labour cost as % of store revenue, transactions per labour hour, and overtime % monthly by store format", "owner_role": "FP&A / Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Labour cost as % of store revenue >12% vs organised retail benchmark of <9% for similar format", "evidence_source": "store_p_and_l", "confirms": "Demand-linked scheduling will reduce excess labour cost"},
            {"signal": "Labour hours in low-footfall hours (weekday mornings, late evenings) scheduled at same staffing as peak hours", "evidence_source": "workforce_management_data", "confirms": "Footfall-linked scheduling will reduce wasted labour hours"},
            {"signal": "Overtime as % of total labour cost >10% consistently, indicating demand forecasting gap", "evidence_source": "payroll_data", "confirms": "Improved scheduling will reduce overtime premium"},
        ],
        "required_data_fields": [
            "Hourly footfall data by store and day type (weekday, weekend, festival)",
            "Labour hours by department and shift pattern",
            "Labour cost per store (permanent, part-time, casual)",
            "Transactions per hour by department and store format",
            "Union contract terms and flexibility provisions",
        ],
    },

    "category_management": {
        "execution_playbook": [
            {"step": "Build category P&L for top-20 categories: map gross margin, shrinkage, markdown, and space cost; rank by profit per sq ft", "owner_role": "Category Management / Finance", "duration_weeks": 3},
            {"step": "Conduct planogram audit for top-10 revenue categories: identify space allocation misalignment vs sales velocity and margin contribution", "owner_role": "Category / Visual Merchandising", "duration_weeks": 3},
            {"step": "Negotiate category captain or co-management agreements with top-3 suppliers per category for planogram and ranging support", "owner_role": "Key Accounts / Category", "duration_weeks": 8},
            {"step": "Implement ranging decisions and planogram changes; track sales per sq ft, in-stock rate, and category margin quarterly", "owner_role": "FP&A / Category", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Profit per sq ft below company average for ≥30% of category space allocation", "evidence_source": "category_pl_data", "confirms": "Category management and space reallocation will improve profit density"},
            {"signal": "Supplier co-investment (in-store activation, planogram compliance) <50% of category leader peer benchmark", "evidence_source": "vendor_investment_data", "confirms": "Category captain engagement will increase supplier investment and reduce category cost"},
            {"signal": "Out-of-stock rate >5% for top-50 SKUs in high-velocity categories", "evidence_source": "osa_monitoring", "confirms": "Improved planogram and range clarity will reduce lost sales from stockouts"},
        ],
        "required_data_fields": [
            "Category P&L by category (gross margin, shrinkage, markdown, space cost)",
            "Space allocation (sq ft) vs sales per sq ft by category",
            "Supplier co-investment and trade terms by category",
            "In-stock (OSA) data by category and SKU",
            "Planogram compliance monitoring data",
        ],
    },

    "shrinkage_reduction": {
        "execution_playbook": [
            {"step": "Decompose total shrinkage by root cause: known theft (internal/external), unknown loss, and administrative errors; estimate % contribution by store", "owner_role": "Loss Prevention / Finance", "duration_weeks": 3},
            {"step": "Deploy EAS (Electronic Article Surveillance) and RFID for high-shrink categories; install AI-powered CCTV at self-checkout and high-risk zones", "owner_role": "Loss Prevention / IT", "duration_weeks": 8},
            {"step": "Implement exception-based reporting for POS anomalies (voids, refunds, no-sales) to surface internal theft patterns", "owner_role": "Loss Prevention / IT", "duration_weeks": 4},
            {"step": "Track shrinkage % by store and category monthly; benchmark against FICCI/retail association benchmark; reward LP performance", "owner_role": "FP&A / Loss Prevention", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Shrinkage >1.5% of net sales vs organised retail benchmark of <1.0%, indicating structural loss prevention gap", "evidence_source": "inventory_count_data", "confirms": "LP investment will yield positive ROI through shrinkage reduction"},
            {"signal": "Unknown loss (book to physical gap) >70% of total shrinkage with no root-cause visibility", "evidence_source": "shrinkage_audit_data", "confirms": "RFID and cycle counting will improve visibility and enable targeted intervention"},
            {"signal": "High-risk categories (electronics, cosmetics, apparel) contributing >50% of shrinkage without dedicated LP coverage", "evidence_source": "shrinkage_by_category", "confirms": "EAS and enhanced surveillance for high-risk categories will reduce loss"},
        ],
        "required_data_fields": [
            "Shrinkage data by store, category, and loss cause (known theft, unknown, admin error)",
            "Current loss prevention technology by store format",
            "POS exception data (voids, refunds, no-sales by cashier)",
            "RFID and EAS coverage map by store",
            "Historical LP investment vs shrinkage reduction correlation",
        ],
    },

    "omnichannel_fulfillment": {
        "execution_playbook": [
            {"step": "Map current fulfilment flow for online orders: DC-to-home, store-to-home, and click-and-collect; measure cost per order and SLA by fulfilment path", "owner_role": "Supply Chain / E-commerce", "duration_weeks": 3},
            {"step": "Model dark store feasibility for top-5 urban clusters by order density; build order routing algorithm to minimise cost per order by zone", "owner_role": "Supply Chain / Analytics", "duration_weeks": 4},
            {"step": "Deploy OMS with real-time inventory visibility across DC and store; automate order routing based on proximity, stock, and SLA", "owner_role": "IT / Supply Chain", "duration_weeks": 10},
            {"step": "Track cost per order by fulfilment path, on-time delivery rate, and returns rate monthly", "owner_role": "FP&A / E-commerce", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Online order fulfilment cost >18% of order value vs benchmark <12% for comparable basket size and geography", "evidence_source": "ecommerce_cost_report", "confirms": "Fulfilment optimisation (dark store, order routing) will reduce unit fulfilment cost"},
            {"signal": "DC-to-home fulfilment contributing >60% of orders in high-density urban areas where store-based fulfilment is cheaper", "evidence_source": "order_routing_data", "confirms": "OMS-driven smart routing will shift volume to lower-cost local fulfilment"},
            {"signal": "Returns rate >12% of orders due to late delivery or wrong-item fulfilment issues", "evidence_source": "ecommerce_returns_data", "confirms": "Fulfilment accuracy improvement will reduce reverse logistics cost"},
        ],
        "required_data_fields": [
            "Online order data by fulfilment path, cost, and SLA performance",
            "Store and DC inventory position (real-time) by SKU",
            "Customer geography and order density by pin code",
            "OMS capability assessment for real-time routing",
            "Dark store operational model and capex/opex estimate",
        ],
    },

    "markdown_optimization": {
        "execution_playbook": [
            {"step": "Analyse markdown pattern by category: measure markdown rate (% of sales at discount), depth (average discount %), and clearance velocity", "owner_role": "Category / FP&A", "duration_weeks": 3},
            {"step": "Build AI-driven markdown optimisation model: predict optimal timing and depth of markdown to maximise margin × volume vs clearance deadline", "owner_role": "Analytics / Category", "duration_weeks": 6},
            {"step": "Pilot model in 2 high-markdown categories (fashion, seasonal); measure margin improvement vs historical average; refine before scale", "owner_role": "Category / Analytics", "duration_weeks": 6},
            {"step": "Roll out to all seasonal and fashion categories; track markdown as % of sales and gross margin improvement monthly", "owner_role": "FP&A / Category", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Markdown as % of gross sales >8% for seasonal categories with unpredictable demand (fashion, festive, seasonal food)", "evidence_source": "markdown_report", "confirms": "AI-driven markdown optimisation will reduce excess clearance discount"},
            {"signal": "Average markdown depth increasing YoY (clearance discount deepening) despite similar sell-through rate", "evidence_source": "markdown_trend_data", "confirms": "Earlier and more targeted markdown will improve margin per unit cleared"},
            {"signal": "End-of-season inventory >15% of season-opening stock requiring clearance at >50% discount", "evidence_source": "end_of_season_inventory_report", "confirms": "Demand planning and markdown model improvement will reduce clearance overhang"},
        ],
        "required_data_fields": [
            "SKU-level markdown data: timing, depth, and volume cleared by discount band",
            "Season-end inventory and clearance sell-through rate",
            "Demand forecast accuracy for seasonal categories",
            "Category margin (with and without markdown) by season",
            "Clearance deadline requirements by category",
        ],
    },

    "loyalty_program_efficiency": {
        "execution_playbook": [
            {"step": "Audit loyalty program economics: measure member acquisition cost, active member rate, redemption rate, and incremental spend uplift vs non-member baseline", "owner_role": "Marketing / Finance", "duration_weeks": 3},
            {"step": "Rationalise point structure: model break-even point earn/burn ratio; eliminate no-value redemption categories; simplify tier structure", "owner_role": "Loyalty / Marketing", "duration_weeks": 4},
            {"step": "Improve personalisation: use member purchase data for targeted offers; shift from mass discount to 1:1 relevant reward to improve redemption ROI", "owner_role": "CRM / Analytics / Marketing", "duration_weeks": 8},
            {"step": "Track loyalty breakage rate, active member %, incremental basket value, and loyalty cost as % of revenue monthly", "owner_role": "FP&A / Marketing", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Loyalty program cost (points liability + admin) >3% of revenue with incremental basket uplift <2% vs non-member", "evidence_source": "loyalty_economics_report", "confirms": "Program rationalisation and personalisation will improve ROI on loyalty investment"},
            {"signal": "Active member rate <30% of enrolled members, indicating poor engagement and wasted enrolment cost", "evidence_source": "crm_data", "confirms": "Improving personalisation and offer relevance will increase active member rate"},
            {"signal": "Breakage rate <10% indicating high redemption liability relative to margin benefit", "evidence_source": "points_accounting", "confirms": "Adjusting earn/burn ratio will reduce points liability without impacting retention"},
        ],
        "required_data_fields": [
            "Loyalty program P&L: enrolment cost, points issued, redemption cost, and program administration",
            "Active member rate and purchase frequency vs non-member",
            "Points earn/burn ratio and breakage rate",
            "Member segmentation by spend tier and redemption behaviour",
            "Basket size uplift data: member vs non-member by category",
        ],
    },

    "supply_chain_direct_sourcing": {
        "execution_playbook": [
            {"step": "Map supply chain for top-5 fresh/produce categories: identify intermediaries (commission agents, wholesalers) and their margin take per unit", "owner_role": "Procurement / Supply Chain", "duration_weeks": 3},
            {"step": "Identify and qualify direct farm/manufacturer suppliers: assess volume capability, quality standards, and logistic connectivity to DC", "owner_role": "Procurement / Supplier Quality", "duration_weeks": 6},
            {"step": "Pilot direct procurement for 1–2 categories with contract farming agreements or direct manufacturer supply; track quality and cost vs current supply chain", "owner_role": "Procurement / Supply Chain", "duration_weeks": 8},
            {"step": "Scale to all shortlisted categories; track cost per unit (farm gate vs current landed cost), quality compliance, and fill rate monthly", "owner_role": "FP&A / Procurement", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Intermediary margin >25% of landed cost for categories where direct sourcing is physically and quality-feasibly achievable", "evidence_source": "supply_chain_margin_map", "confirms": "Direct sourcing will eliminate intermediary margin and improve price competitiveness"},
            {"signal": "Product quality or freshness complaints from customers >5% of category revenue, indicating supply chain length impact on quality", "evidence_source": "customer_complaint_data", "confirms": "Shorter supply chain will improve freshness and reduce quality-related returns"},
            {"signal": "Own-label or private-label strategy requiring assured supply that is not available through spot market", "evidence_source": "category_strategy_document", "confirms": "Direct supply agreement will secure volume commitment and quality consistency"},
        ],
        "required_data_fields": [
            "Current supply chain map: intermediary count, margin by tier, and landed cost by category",
            "Supplier qualification criteria and MOQ for direct sourcing",
            "Quality specifications and cold chain requirements by category",
            "DC logistics connectivity to potential direct sourcing locations",
            "Contract farming regulatory requirements and templates",
        ],
    },

    "private_label": {
        "execution_playbook": [
            {"step": "Map category white space: identify segments where retailer private label penetration <10% and competitor PL or NBD is gaining share", "owner_role": "Category Management / Merchandising", "duration_weeks": 3},
            {"step": "Qualify manufacturers for PL production: supplier audit, GMP/FSSAI compliance, formulation capability, and exclusivity terms", "owner_role": "Procurement / Quality", "duration_weeks": 5},
            {"step": "Launch PL range in pilot stores (>20 stores) with consumer testing; track consumer acceptance vs branded alternative", "owner_role": "Category / Supply Chain", "duration_weeks": 8},
            {"step": "Scale to full chain; track PL penetration, category margin uplift, and branded manufacturer response", "owner_role": "Category / FP&A", "duration_weeks": 6},
        ],
        "diagnostic_signals": [
            {"signal": "Category gross margin <25% with retailer private label equivalent achievable at >35% margin on same shelf", "evidence_source": "category_margin_report", "confirms": "Private label will structurally improve category margin mix"},
            {"signal": "Private label penetration in category <15% vs modern trade benchmark of >25% in comparable markets", "evidence_source": "category_benchmarking", "confirms": "PL expansion headroom is material"},
            {"signal": "Consumer willingness to trade down confirmed by market research for this category", "evidence_source": "consumer_research", "confirms": "PL launch risk is manageable"},
        ],
        "required_data_fields": [
            "Category margin data by brand, pack size, and store format",
            "Private label penetration by category and store format",
            "Consumer research on PL acceptance by category",
            "Manufacturer shortlist with production capacity and compliance data",
            "Competitor PL pricing and ranging data",
        ],
    },

    "store_network_optimization": {
        "execution_playbook": [
            {"step": "Build store-level unit economics: revenue per sq ft, four-wall EBITDA, and payback period by store age, format, and location tier", "owner_role": "FP&A / Real Estate", "duration_weeks": 3},
            {"step": "Conduct catchment analysis for under-performing stores: assess cannibalisation, population density, and competitive intensity to distinguish structural vs temporary underperformance", "owner_role": "Strategy / Real Estate / Analytics", "duration_weeks": 4},
            {"step": "For close/exit candidates: negotiate lease exit or surrender at break clause; for under-performing stores: implement format change or rightsizing", "owner_role": "Real Estate / Operations / Legal", "duration_weeks": 12},
            {"step": "Track four-wall EBITDA margin, revenue per sq ft, and lease-adjusted payback by store monthly; gate new store investments against updated return hurdles", "owner_role": "FP&A / Real Estate", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "≥15% of stores with negative four-wall EBITDA for ≥2 consecutive years", "evidence_source": "store_pl_data", "confirms": "Exit or format change for loss-making stores will remove P&L drag"},
            {"signal": "New store payback period >4 years for recent openings vs investment hurdle of ≤3 years", "evidence_source": "store_investment_tracker", "confirms": "Network strategy review will tighten store quality and return on capital"},
            {"signal": "Lease WALE >3 years in locations where store has not reached breakeven, creating exit cost", "evidence_source": "lease_register", "confirms": "Proactive negotiation at lease break will reduce exit cost"},
        ],
        "required_data_fields": [
            "Store P&L: revenue, four-wall EBITDA, and payback period by store",
            "Catchment analysis data: population, demographics, and competitive landscape by store",
            "Lease terms: WALE, break-clause dates, and exit cost by store",
            "Store age and format classification",
            "New store investment return hurdles and pipeline",
        ],
    },

    # ------------------------------------------------------------- TELECOM INFRA
    "network_opex_optimization": {
        "execution_playbook": [
            {"step": "Disaggregate network OPEX by cost driver: passive infrastructure (power, rent), active network (maintenance, spares), and managed services; benchmark vs revenue", "owner_role": "Network Finance / Operations", "duration_weeks": 3},
            {"step": "Identify top-5 cost reduction levers: tower power cost reduction, network equipment refresh, RAN-sharing, NOC automation, and spares pooling", "owner_role": "Network Operations / Finance", "duration_weeks": 4},
            {"step": "Execute quick wins (automated energy management, spares pooling); develop business case for medium-term investments (equipment refresh, RAN sharing)", "owner_role": "Network Operations / Projects", "duration_weeks": 12},
            {"step": "Track network OPEX as % of revenue and EBITDA, and cost per subscriber monthly", "owner_role": "FP&A / Network Finance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Network OPEX as % of service revenue >25% vs peer operator benchmark of <22%", "evidence_source": "trai_performance_indicator_report", "confirms": "Structural OPEX reduction will improve EBITDA margin"},
            {"signal": "Power cost >35% of total passive infrastructure OPEX with diesel backup >20% of power mix", "evidence_source": "network_cost_breakdown", "confirms": "Energy management and green energy transition will reduce power cost"},
            {"signal": "Managed service contract for RAN management not benchmarked for >3 years", "evidence_source": "vendor_contract_register", "confirms": "Managed service rebid will improve pricing and SLA"},
        ],
        "required_data_fields": [
            "Network OPEX breakdown by cost category and geography",
            "Power consumption data: grid vs diesel ratio per tower/BTS",
            "Network equipment age profile and maintenance cost",
            "RAN managed service contract terms and SLA performance",
            "TRAI network performance indicators (CAGR trends, EBITDA benchmarks)",
        ],
    },

    "tower_sharing": {
        "execution_playbook": [
            {"step": "Audit tower portfolio: segment by tenancy ratio, location type, and EBITDA contribution; identify low-tenancy towers for hosting commercial sharing", "owner_role": "Tower Business / Network", "duration_weeks": 3},
            {"step": "Approach alternate operators for co-location on strategic towers; negotiate standard TRAI-compliant sharing agreements with market-rate GLR (Ground Level Rent) pass-through", "owner_role": "Business Development / Legal", "duration_weeks": 8},
            {"step": "Evaluate sale-and-leaseback of non-core towers to infrastructure investor (IndiGrid, ATC, Brookfield) to unlock capital and reduce opex", "owner_role": "Corporate Finance / Tower Business", "duration_weeks": 12},
            {"step": "Track tenancy ratio, co-location revenue per tower, and passive infrastructure cost per subscriber monthly", "owner_role": "FP&A / Tower Business", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Tenancy ratio <1.3× for >50% of tower portfolio vs industry leader benchmark of >2.0×", "evidence_source": "tower_inventory_data", "confirms": "Sharing agreements will monetise underutilised tower capacity"},
            {"signal": "Passive infrastructure cost (rent, power, security, maintenance) >20% of total network OPEX", "evidence_source": "network_cost_breakdown", "confirms": "Tower sharing and potential sale-leaseback will reduce passive opex per site"},
            {"signal": "Tower rollout cost >₹25 L per new site where equivalent co-location on existing tower is available at <₹6 L/year lease", "evidence_source": "capex_vs_opex_analysis", "confirms": "Sharing preference over new build will improve return on network investment"},
        ],
        "required_data_fields": [
            "Tower inventory with tenancy ratio, location, and EBITDA per tower",
            "Co-location agreement terms with existing sharing partners",
            "Sale-leaseback valuation assumptions and market comparables",
            "TRAI sharing regulations and GLR pass-through framework",
            "Network rollout plan and new site requirements",
        ],
    },

    "spectrum_efficiency": {
        "execution_playbook": [
            {"step": "Analyse spectrum utilisation by band: measure traffic load, spectral efficiency (bps/Hz), and coverage-capacity trade-offs by geography", "owner_role": "Radio Planning / Technology", "duration_weeks": 4},
            {"step": "Optimise traffic offloading: deploy small cells and Wi-Fi offload in high-density urban areas to reduce macro spectrum congestion", "owner_role": "Network Engineering", "duration_weeks": 10},
            {"step": "Identify refarming opportunities: migrate 900 MHz/1800 MHz 2G traffic to LTE; release spectrum for higher-capacity 4G/5G use", "owner_role": "Technology / Regulatory", "duration_weeks": 12},
            {"step": "Model spectrum needs for upcoming auctions: estimate minimum auction quantity needed vs current spectral efficiency improvement trajectory", "owner_role": "Strategy / Finance", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Spectral efficiency (bps/Hz) in dense urban cells <60% of theoretical maximum for deployed equipment", "evidence_source": "network_performance_data", "confirms": "RAN optimisation and traffic offloading will improve spectrum yield"},
            {"signal": "2G traffic >15% of total voice minutes on spectrum bands (900/1800 MHz) that could serve higher-value LTE/5G traffic", "evidence_source": "traffic_analytics", "confirms": "Spectrum refarming will improve revenue per MHz by migrating to higher-value services"},
            {"signal": "Upcoming spectrum auction costs can be partially offset by improved utilisation of current holdings", "evidence_source": "spectrum_planning_report", "confirms": "Efficiency improvement will reduce incremental spectrum capex need"},
        ],
        "required_data_fields": [
            "Spectrum holding by band, geography, and operator",
            "Traffic load data by cell and band (busy hour utilisation)",
            "Spectral efficiency benchmarks by equipment vendor and technology",
            "2G/3G traffic migration timeline and customer base",
            "Spectrum auction schedule and estimated pricing by band",
        ],
    },

    "customer_service_automation": {
        "execution_playbook": [
            {"step": "Analyse contact centre data: measure contact volume by reason, IVR containment rate, and cost per resolution by contact type", "owner_role": "Customer Service / Operations", "duration_weeks": 3},
            {"step": "Design chatbot/IVR upgrade: map top-10 contact reasons to automated resolution flows; integrate with BSS for real-time account data", "owner_role": "Digital / IT / Customer Service", "duration_weeks": 6},
            {"step": "Deploy AI chatbot (WhatsApp, app, web) for high-volume, low-complexity contacts (bill queries, plan changes, balance inquiry); pilot with 20% of inbound volume", "owner_role": "IT Delivery / Customer Service", "duration_weeks": 8},
            {"step": "Track digital containment rate, cost per contact, and NPS by channel monthly; expand automation to complex contact types in Phase 2", "owner_role": "FP&A / Customer Experience", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "IVR/chatbot containment rate <30% for contacts where top-10 contact reasons are automatable (bill, plan, balance)", "evidence_source": "ivr_analytics", "confirms": "Chatbot and IVR redesign will significantly increase automation containment"},
            {"signal": "Cost per contact >₹80 via agent vs <₹10 via digital self-service for equivalent resolution", "evidence_source": "contact_centre_cost_report", "confirms": "Digital containment improvement will reduce total customer service cost"},
            {"signal": "Agent utilisation <70% due to high volume of simple contacts that could be self-served", "evidence_source": "workforce_management_data", "confirms": "Automation will free agent capacity for complex and high-value interactions"},
        ],
        "required_data_fields": [
            "Contact volume by reason code and channel (IVR, agent, digital)",
            "IVR containment rate by reason code",
            "Cost per contact by channel (agent, IVR, digital)",
            "BSS system API capability for real-time data in chatbot flows",
            "NPS and CSAT by contact reason and resolution channel",
        ],
    },

    "churn_reduction": {
        "execution_playbook": [
            {"step": "Build churn prediction model by subscriber segment: identify leading indicators (declining ARPU, reduced data usage, customer service contacts, network complaints)", "owner_role": "Data Science / Analytics", "duration_weeks": 4},
            {"step": "Design win-back and retention programs by churn risk tier: targeted offers for high-value/high-risk subscribers; network experience improvement for service-driven churn", "owner_role": "Marketing / Customer Retention", "duration_weeks": 5},
            {"step": "Activate retention programs via outbound and app push; measure response rate and 90-day retention by offer type and segment", "owner_role": "CRM / Customer Service", "duration_weeks": 8},
            {"step": "Track monthly churn rate, ARPU of retained base, and cost per retained subscriber monthly", "owner_role": "FP&A / Marketing", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Monthly churn rate >2.5% for postpaid or >5% for prepaid vs peer operator benchmark", "evidence_source": "trai_data_and_internal_churn_report", "confirms": "Churn reduction will improve LTV and reduce subscriber acquisition cost burden"},
            {"signal": "High-value subscriber (ARPU >₹500) churn rate disproportionately higher than average, indicating service quality issue for premium segment", "evidence_source": "churn_cohort_analysis", "confirms": "Targeted retention investment for high-ARPU customers will yield highest ROI"},
            {"signal": "Network-related complaints (dropped calls, data speed) are primary churn driver for >30% of churned subscribers", "evidence_source": "exit_survey_and_churn_reason_data", "confirms": "Network quality improvement is a prerequisite for churn reduction"},
        ],
        "required_data_fields": [
            "Subscriber-level usage data and ARPU trend (12 months)",
            "Churn data with reason codes and churn cohort by acquisition source",
            "Network complaint and NPS data by geography and segment",
            "Retention offer history and response rate",
            "Customer LTV model by segment",
        ],
    },

    "roaming_cost_optimization": {
        "execution_playbook": [
            {"step": "Analyse international roaming traffic: map volume by corridor, wholesale rate, and retail margin; identify corridors with below-market wholesale rates", "owner_role": "International Business / Finance", "duration_weeks": 3},
            {"step": "Renegotiate bilateral roaming agreements with top-10 traffic corridors: benchmark vs IPX (IP eXchange) hub rates; migrate to IPX for cost efficiency", "owner_role": "Roaming Team / Procurement", "duration_weeks": 8},
            {"step": "Implement real-time roaming cost control: per-session cost alerts for high-usage roamers; block inadvertent roaming on satellite or premium networks", "owner_role": "IT / Customer Service", "duration_weeks": 4},
            {"step": "Track wholesale roaming cost per MB/minute, retail vs wholesale margin, and roaming revenue contribution monthly", "owner_role": "FP&A / International", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Roaming wholesale cost >60% of roaming retail revenue for top-3 traffic corridors", "evidence_source": "roaming_p_and_l", "confirms": "IPX routing and bilateral renegotiation will improve roaming margin"},
            {"signal": "More than 5 corridors still on legacy bilateral agreements not routed through IPX hub, paying premium per-unit rates", "evidence_source": "roaming_agreement_inventory", "confirms": "IPX migration will reduce wholesale cost for high-traffic corridors"},
            {"signal": "Inadvertent roaming events (satellite, premium partner network) generating bill shock and customer complaints", "evidence_source": "customer_service_data", "confirms": "Real-time controls will reduce inadvertent roaming cost and complaint volume"},
        ],
        "required_data_fields": [
            "Roaming traffic by corridor: volume (MB, minutes, SMS), wholesale cost, and retail revenue",
            "Current bilateral agreement rates vs IPX benchmark by corridor",
            "IPX hub connectivity and migration readiness",
            "Inadvertent roaming incident log and cost",
            "TRAI roaming tariff regulations",
        ],
    },

    "it_bss_oss_modernization": {
        "execution_playbook": [
            {"step": "Assess BSS/OSS landscape: map all systems (billing, CRM, provisioning, mediation, network management) to vendor, age, and integration complexity", "owner_role": "CTO / IT Architecture", "duration_weeks": 4},
            {"step": "Develop modernisation roadmap: prioritise by business impact (revenue leakage, time-to-market, customer experience) and technical risk; select cloud-native vs SaaS replacement", "owner_role": "CTO / Strategy", "duration_weeks": 5},
            {"step": "Execute migration in phases starting with mediation and billing (revenue impact); implement API gateway for legacy integration; decompose monolith to microservices", "owner_role": "IT Delivery / Programme", "duration_weeks": 24},
            {"step": "Track IT OPEX as % of revenue, time-to-market for new plan launch, and billing accuracy rate monthly", "owner_role": "FP&A / IT", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "New product/plan time-to-market >30 days due to BSS configuration complexity vs cloud-native benchmark of <7 days", "evidence_source": "product_launch_tracker", "confirms": "BSS modernisation will improve time-to-market and commercial agility"},
            {"signal": "IT OPEX for BSS/OSS maintenance >12% of total revenue vs cloud-native operator benchmark of <7%", "evidence_source": "it_cost_breakdown", "confirms": "Modernisation will reduce IT maintenance cost through platform consolidation"},
            {"signal": "Revenue leakage from billing errors or unmediated traffic >0.5% of total revenue", "evidence_source": "revenue_assurance_report", "confirms": "BSS modernisation will close revenue assurance gaps"},
        ],
        "required_data_fields": [
            "BSS/OSS landscape: system inventory, vendor, age, and annual maintenance cost",
            "Time-to-market data for recent product launches",
            "Revenue assurance report with leakage estimate",
            "IT OPEX breakdown (BSS/OSS maintenance, licensing, managed services)",
            "Cloud-native or SaaS BSS vendor options and migration feasibility",
        ],
    },

    "energy_management": {
        "execution_playbook": [
            {"step": "Measure energy consumption per site: electricity units consumed per BTS/tower per month; calculate energy per GB traffic and trend YoY", "owner_role": "Network Energy / Operations", "duration_weeks": 3},
            {"step": "Deploy free cooling, battery energy storage systems (BESS), and solar at high-consumption sites; negotiate green energy PPA for grid supply", "owner_role": "Network Infrastructure / Procurement", "duration_weeks": 12},
            {"step": "Implement remote BTS (intelligent energy controller) and passive cooling optimisation (insulation, variable-speed fans) at all managed sites", "owner_role": "Network Operations", "duration_weeks": 8},
            {"step": "Track energy cost per GB traffic, diesel % in energy mix, and carbon intensity monthly; report against SBTi targets", "owner_role": "FP&A / Network Energy", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Diesel generator runtime >30% of total energy supply hours, indicating grid reliability issues and high diesel cost", "evidence_source": "network_energy_monitoring", "confirms": "BESS and solar will reduce diesel dependency and fuel cost"},
            {"signal": "Energy cost per GB traffic growing >10% YoY due to traffic growth without corresponding energy efficiency improvement", "evidence_source": "energy_per_gb_trend", "confirms": "Energy efficiency programme will decouple energy cost from traffic growth"},
            {"signal": "TowerCo SLA not optimised for energy efficiency (fixed rental structure with no energy pass-through incentive)", "evidence_source": "towerco_lease_agreement", "confirms": "Renegotiating energy-linked SLA will incentivise TowerCo energy management"},
        ],
        "required_data_fields": [
            "Energy consumption data by site (electricity units, diesel litres) per month",
            "TowerCo energy SLA terms and diesel reimbursement structure",
            "Solar and BESS feasibility data by site geography",
            "Grid reliability metrics by region",
            "Energy cost and carbon intensity targets",
        ],
    },

    "workforce_productivity": {
        "execution_playbook": [
            {"step": "Analyse field force utilisation: map jobs per engineer per day, travel time vs work time, and first-time fix rate by team and geography", "owner_role": "Field Operations / HR", "duration_weeks": 3},
            {"step": "Deploy FSO (Field Service Optimisation) tool with AI-based dispatch, route optimisation, and remote diagnostics integration", "owner_role": "IT / Field Operations", "duration_weeks": 8},
            {"step": "Implement performance-linked variable pay for field force: pay on first-time fix rate, jobs completed per day, and SLA compliance", "owner_role": "HR / Field Operations", "duration_weeks": 4},
            {"step": "Track jobs per engineer per day, first-time fix rate, and field force cost per resolved incident monthly", "owner_role": "FP&A / Field Operations", "duration_weeks": 4},
        ],
        "diagnostic_signals": [
            {"signal": "Jobs per field engineer per day <4 vs FSO benchmark of 6–8 for comparable urban/rural mix and job type", "evidence_source": "field_operations_data", "confirms": "Dispatch optimisation and route planning will increase jobs completed per engineer per day"},
            {"signal": "First-time fix rate <75% generating high repeat-visit cost and customer dissatisfaction", "evidence_source": "field_service_kpi_report", "confirms": "Remote diagnostics and better parts provisioning will improve fix rate and reduce revisit cost"},
            {"signal": "Travel time >40% of total field engineer productive hours due to poor territory planning or dispatch system", "evidence_source": "time_and_motion_study", "confirms": "Route optimisation will reduce travel time and increase productive work hours"},
        ],
        "required_data_fields": [
            "Field force utilisation data: jobs per engineer per day, travel time, and work time",
            "First-time fix rate and repeat-visit rate by job type and team",
            "Territory allocation and customer concentration data",
            "FSO tool options and integration with workforce management system",
            "Field engineer compensation structure and variable pay policy",
        ],
    },
}


def _ensure_fields(lever: Dict[str, Any], is_sector: bool, *, force: bool = False) -> None:
    family = lever.get("lever_family", "supply")
    defaults = FAMILY_DEFAULTS.get(family, FAMILY_DEFAULTS["supply"])
    lid = lever.get("lever_id", "")
    override = LEVER_OVERRIDES.get(lid, {})
    specific = LEVER_SPECIFIC.get(lid, {})

    for field in ("execution_playbook", "diagnostic_signals", "required_data_fields"):
        # Specific content always wins; family defaults only for unknown levers
        if specific.get(field):
            lever[field] = deepcopy(specific[field])
        elif lever.get(field) and not force:
            continue
        else:
            lever[field] = deepcopy(override.get(field) or defaults.get(field, []))

    if is_sector and lever.get("lever_name") and not specific:
        name = lever["lever_name"]
        playbook = lever.get("execution_playbook") or []
        if playbook and name not in playbook[0].get("step", ""):
            playbook[0] = {
                **playbook[0],
                "step": f"Confirm scope for {name}: validate baseline and stakeholders",
            }


def _patch_file(path: Path, sector: bool, *, force: bool = False) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for key in ("sector_specific_levers",):
        for lever in data.get(key, []):
            _ensure_fields(lever, is_sector=True, force=force)
            count += 1
    if not sector:
        pass
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return count


def main() -> None:
    import sys
    force = "--force" in sys.argv
    total = 0
    for path in sorted(SECTOR_DIR.glob("*/sector_levers.json")):
        n = _patch_file(path, sector=True, force=force)
        total += n
        print(f"Updated {path.relative_to(ROOT)} ({n} levers)")

    params = json.loads(MODEL_PARAMS.read_text(encoding="utf-8"))
    levers = params.get("levers", {})
    for lid, lever in levers.items():
        lever.setdefault("lever_id", lid)
        _ensure_fields(lever, is_sector=False, force=force)
    params["lever_family_defaults_note"] = (
        "execution_playbook/diagnostic_signals/required_data_fields on each lever; "
        "seeded via scripts/seed_lever_playbooks.py"
    )
    MODEL_PARAMS.write_text(json.dumps(params, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated model_parameters.json ({len(levers)} universal levers)")
    print(f"Total sector levers patched: {total}")


if __name__ == "__main__":
    main()
