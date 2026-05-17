from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SpendProfileCategoryRow(BaseModel):
    category_id: str
    category_name: str
    spend: float
    line_count: int
    share_of_total: float
    kraljic_quadrant: Optional[str] = None
    spend_quadrant: Optional[str] = None
    category_maturity_proxy: Optional[float] = None
    maturity_adjusted_addressable: Optional[float] = None


class SpendProfilerOutput(BaseModel):
    total_spend: float
    category_profile: List[SpendProfileCategoryRow]
    trend_analysis: Dict[str, Any] | None = None


class DocumentContextOutput(BaseModel):
    context_summary: str
    constraints: List[str]


class PeerComparisonRow(BaseModel):
    category_id: str
    category_name: str
    actual_pct_of_revenue: float
    benchmark_target_pct: float
    benchmark_p50_pct: float = 0.0
    percentile_band: str
    estimated_saving_amount: float
    source: str
    benchmark_metadata: Dict[str, Any] = Field(default_factory=dict)


class PeerBenchmarkerOutput(BaseModel):
    industry: str
    comparisons: List[PeerComparisonRow]
    benchmark_metadata: Dict[str, Any] = Field(default_factory=dict)


class InternalVarianceRow(BaseModel):
    category_id: str
    max_spend: float
    min_spend: float
    median_spend: float
    internal_spread: float
    flagged_gt_20pct: bool
    segments: List[Dict[str, Any]]


class InternalBenchmarkerOutput(BaseModel):
    internal_variance: List[InternalVarianceRow]


class HeuristicFindingRow(BaseModel):
    category_id: str
    actual_pct_of_revenue: float
    heuristic_target_pct: float
    estimated_saving_amount: float
    headcount_based_saving_amount: float | None = None
    actual_cost_per_employee: float | None = None
    target_cost_per_employee: float | None = None


class HeuristicAnalyzerOutput(BaseModel):
    heuristic_findings: List[HeuristicFindingRow]


class ValueBridgeCategoryRow(BaseModel):
    category_id: str
    # Legacy value-bridge shape
    peer_savings: float = 0.0
    internal_savings: float = 0.0
    heuristic_savings: float = 0.0
    # New modeled shape
    category_name: str | None = None
    lever: str | None = None
    root_cause: str | None = None
    gross_3yr: float = 0.0
    cost_to_achieve_3yr: float = 0.0
    net_npv: float = 0.0
    payback_months: int = 0
    confidence: str | None = None
    deduped_mid_savings: float


class ConfidenceBands(BaseModel):
    low: float
    mid: float
    high: float


class ValueBridgeOutput(BaseModel):
    value_matrix: List[ValueBridgeCategoryRow]
    confidence_bands: ConfidenceBands
    addressable_pct_of_total_spend: float
    total_cost_avoidance: float = 0.0


class DataValidatorOutput(BaseModel):
    checks: Dict[str, bool]
    passed: bool


class SynthesisFinancials(BaseModel):
    mid_case_savings: float
    net_npv: float
    payback_months: int


class SynthesisConfidence(BaseModel):
    level: str
    rationale: str


class SynthesisEvidenceItem(BaseModel):
    source: str
    detail: str


class SynthesisExampleItem(BaseModel):
    supplier: str
    description: str
    amount: float
    why_relevant: str


class SynthesisRecommendation(BaseModel):
    category_id: str
    category_name: str
    lever: str
    priority: int
    financials: SynthesisFinancials
    confidence: SynthesisConfidence
    evidence: List[SynthesisEvidenceItem]
    examples: List[SynthesisExampleItem] = []
    risks: List[str]
    decisions_required: List[str]


class AnalysisSynthesizerOutput(BaseModel):
    executive_takeaway: str
    recommendations: List[SynthesisRecommendation]
    assumptions: List[str]
    citations: List[str]


class ExecutiveCommunicationSections(BaseModel):
    executive_takeaway: str
    why_now: str
    recommended_actions: List[str]
    financial_view: List[str]
    risks_and_mitigations: List[str]
    decisions_required: List[str]


class ExecutiveCommunicationOutput(BaseModel):
    message: str
    sections: ExecutiveCommunicationSections


# ---------------------------------------------------------------------------
# FP&A Skill Contracts
# ---------------------------------------------------------------------------

class BvAVarianceRow(BaseModel):
    category_id: str
    category_name: str
    actual_spend: float
    budget_spend: float
    total_variance: float
    variance_pct: float | None = None
    # price_variance / volume_variance / mix_variance are Optional — they are
    # only populated when homogeneous per-unit quantity data is present in the
    # source (CIMA/ACCA standard). Without quantity data the spend variance
    # (`total_variance`) is the only valid decomposition.
    price_variance: float | None = None
    volume_variance: float | None = None
    mix_variance: float | None = None
    decomposition_note: str | None = None
    flag: str  # "over_budget" | "under_budget" | "on_budget"
    primary_driver: str  # "spend" | "price" | "volume" | "mix"


class BvAAnalyzerOutput(BaseModel):
    bva_available: bool
    reason: str | None = None
    total_actual: float = 0.0
    total_budget: float = 0.0
    total_variance: float = 0.0
    total_variance_pct: float | None = None
    categories_over_budget: int = 0
    categories_under_budget: int = 0
    variances: List[BvAVarianceRow]


class TemporalPeriodRow(BaseModel):
    period: str
    total_spend: float
    mom_delta: float | None = None
    mom_pct: float | None = None
    yoy_delta: float | None = None
    yoy_pct: float | None = None


class TemporalCategoryTrendRow(BaseModel):
    category_id: str
    category_name: str
    periods_available: int
    first_period: str
    last_period: str
    first_period_spend: float
    last_period_spend: float
    total_change: float
    change_pct: float | None = None
    trend_direction: str
    annualized_run_rate: float


class TemporalAnalyzerOutput(BaseModel):
    temporal_available: bool
    reason: str | None = None
    period_count: int = 0
    first_period: str | None = None
    last_period: str | None = None
    annualized_run_rate: float = 0.0
    period_trends: List[TemporalPeriodRow] = Field(default_factory=list)
    category_trends: List[TemporalCategoryTrendRow] = Field(default_factory=list)


class PaymentTermsOpportunityRow(BaseModel):
    category_id: str
    category_name: str
    annual_spend: float
    current_dpo_days: float
    target_dpo_days: float
    dpo_improvement_days: float
    working_capital_release: float
    annual_cash_value_at_wacc: float
    wacc_used: float
    benchmark_note: str = ""
    lines_with_terms: int = 0


class PaymentTermsOptimizerOutput(BaseModel):
    payment_terms_available: bool
    reason: str | None = None
    wacc: float = 0.10
    industry: str = "default"
    coverage_pct: float = 0.0
    total_working_capital_release: float = 0.0
    total_annual_cash_value: float = 0.0
    opportunity_count: int = 0
    opportunities: List[PaymentTermsOpportunityRow] = Field(default_factory=list)
    note: str = ""


class PlanningHorizon(BaseModel):
    start_period: str | None = None
    end_period: str | None = None
    period_grain: Literal["monthly", "quarterly", "annual", "unknown"] = "unknown"
    total_periods: int = 0


class ScenarioDescriptor(BaseModel):
    scenario_id: str
    label: str
    source_sheet: str | None = None
    column_index: int | None = None
    maps_to_sensitivity_scenario: str | None = None


class SheetPeriodAxis(BaseModel):
    orientation: Literal["column", "row", "unknown"] = "unknown"
    first_period_col: int | None = None
    last_period_col: int | None = None
    periods: List[str] = Field(default_factory=list)


class SheetGraphNode(BaseModel):
    sheet_name: str
    role: Literal[
        "assumptions",
        "timeseries",
        "summary",
        "scenarios",
        "sensitivity",
        "bridge",
        "cover",
        "helper",
        "transaction_ledger",
        "unknown",
    ] = "unknown"
    feeds_into: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    period_axis: SheetPeriodAxis | None = None
    driver_variables: List[str] = Field(default_factory=list)
    output_metrics: List[str] = Field(default_factory=list)
    categories_detected: List[str] = Field(default_factory=list)
    row_count: int = 0
    data_density: Literal["sparse", "medium", "dense", "unknown"] = "unknown"


class KeyDriverVariable(BaseModel):
    variable_name: str
    source_sheet: str | None = None
    cell_ref: str | None = None
    current_value: float | str | None = None
    unit: str | None = None
    maps_to_sensitivity_driver: str | None = None


class OutputMetric(BaseModel):
    metric_name: str
    source_sheet: str | None = None
    cell_ref: str | None = None
    value: float | str | None = None
    currency: str | None = None
    scenario_label: str | None = None
    pre_populated: bool = False


class WorkbookManifest(BaseModel):
    manifest_version: str = "1.0"
    workbook_name: str = ""
    model_type: Literal["planning", "budget", "scenario", "forecast", "hybrid", "unknown"] = "unknown"
    planning_horizon: PlanningHorizon = Field(default_factory=PlanningHorizon)
    scenarios: List[ScenarioDescriptor] = Field(default_factory=list)
    sheet_graph: List[SheetGraphNode] = Field(default_factory=list)
    key_driver_variables: List[KeyDriverVariable] = Field(default_factory=list)
    output_metrics: List[OutputMetric] = Field(default_factory=list)
    spend_category_coverage: List[str] = Field(default_factory=list)
    ingestion_strategy: Literal["timeseries_flatten", "scenario_pivot", "assumptions_extract", "hybrid", "standard"] = "standard"
    ingestion_notes: str = ""
    confidence: float = 0.0


def validate_core_skill_outputs(
    profile: Dict[str, Any],
    context: Dict[str, Any],
    peer: Dict[str, Any],
    internal: Dict[str, Any],
    heuristic: Dict[str, Any],
    bridge: Dict[str, Any],
    validator: Dict[str, Any],
) -> None:
    SpendProfilerOutput.model_validate(profile)
    DocumentContextOutput.model_validate(context)
    PeerBenchmarkerOutput.model_validate(peer)
    InternalBenchmarkerOutput.model_validate(internal)
    HeuristicAnalyzerOutput.model_validate(heuristic)
    ValueBridgeOutput.model_validate(bridge)
    DataValidatorOutput.model_validate(validator)


def validate_bva_output(bva: Dict[str, Any]) -> None:
    BvAAnalyzerOutput.model_validate(bva)


def validate_temporal_output(temporal: Dict[str, Any]) -> None:
    TemporalAnalyzerOutput.model_validate(temporal)


def validate_payment_terms_output(pt: Dict[str, Any]) -> None:
    PaymentTermsOptimizerOutput.model_validate(pt)


def validate_analysis_synthesizer_output(synthesis: Dict[str, Any]) -> None:
    AnalysisSynthesizerOutput.model_validate(synthesis)


def validate_executive_communication_output(comm: Dict[str, Any]) -> None:
    ExecutiveCommunicationOutput.model_validate(comm)


def validate_workbook_manifest(manifest: Dict[str, Any]) -> WorkbookManifest:
    parsed = WorkbookManifest.model_validate(manifest)
    if not (0.0 <= float(parsed.confidence) <= 1.0):
        raise ValueError("WorkbookManifest confidence must be between 0.0 and 1.0")
    if not parsed.sheet_graph:
        raise ValueError("WorkbookManifest sheet_graph must include at least one sheet")
    if not any(node.role != "unknown" for node in parsed.sheet_graph):
        raise ValueError("WorkbookManifest must include at least one non-unknown sheet role")
    return parsed


# ---------------------------------------------------------------------------
# Phase 3: Enterprise Skills Contracts
# ---------------------------------------------------------------------------

class VendorMasterEntry(BaseModel):
    vendor_id: str
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    gstin: str | None = None
    total_spend: float
    line_count: int
    source_systems: List[str] = Field(default_factory=list)
    msme_flag: bool | None = None
    top_category: str | None = None


class VendorMasterOutput(BaseModel):
    vendor_count: int
    total_spend_covered: float
    coverage_pct_with_gstin: float
    duplicate_aliases_removed: int
    estimated_dedup_savings: float
    vendors: List[VendorMasterEntry] = Field(default_factory=list)


class EntitySpendRow(BaseModel):
    entity_id: str
    entity_name: str
    total_spend: float
    addressable_spend: float
    intercompany_spend: float
    line_count: int


class ConsolidationAnalyzerOutput(BaseModel):
    consolidation_available: bool
    reason: str | None = None
    group_total_spend: float = 0.0
    group_addressable_spend: float = 0.0
    intercompany_eliminated: float = 0.0
    addressable_pct: float = 0.0
    entity_count: int = 0
    completeness_coverage_pct: float = 100.0
    missing_entities: List[str] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    top_categories: List[Dict[str, Any]] = Field(default_factory=list)


class ConflictDetectorOutput(BaseModel):
    conflict_count: int = 0
    by_type: Dict[str, int] = Field(default_factory=dict)
    by_severity: Dict[str, int] = Field(default_factory=dict)
    unresolved: int = 0
    auto_resolvable: int = 0
    requires_escalation: int = 0
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)


class ContractRenewalAlert(BaseModel):
    supplier: str
    vendor_gstin: str | None = None
    contract_expiry_date: str | None = None
    contract_status: str | None = None
    annual_spend: float
    estimated_exit_penalty: float
    days_to_expiry: int | None = None
    alert_type: str  # "renewal_due" | "auto_renewal_risk" | "expired" | "at_risk"


class ContractLifecycleOutput(BaseModel):
    contracts_analyzed: int
    renewal_alerts: List[ContractRenewalAlert] = Field(default_factory=list)
    exit_penalty_exposure: float = 0.0
    savings_blocked_by_contract: float = 0.0
    at_risk_spend: float = 0.0
    expired_contracts_spend: float = 0.0


class GSTRLineMatch(BaseModel):
    invoice_ref: str
    supplier_gstin: str
    ap_amount: float
    gstr_amount: float | None = None
    status: str  # "matched" | "unmatched_in_ap" | "unmatched_in_gstr" | "amount_mismatch"
    itc_at_risk: float = 0.0


class GSTRReconcilerOutput(BaseModel):
    gstr_available: bool
    reason: str | None = None
    total_ap_lines: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    amount_mismatch_count: int = 0
    itc_at_risk: float = 0.0
    recovery_opportunity: float = 0.0
    coverage_pct: float = 0.0
    line_matches: List[GSTRLineMatch] = Field(default_factory=list)


class MSMEAtRiskPayment(BaseModel):
    supplier: str
    vendor_gstin: str | None = None
    msme_flag: bool | None = None
    annual_spend: float
    payment_terms_days: int | None = None
    days_over_limit: int | None = None
    penalty_interest_exposure: float
    alert: str


class MSMEComplianceOutput(BaseModel):
    msme_data_available: bool
    reason: str | None = None
    total_msme_spend: float = 0.0
    at_risk_spend: float = 0.0
    compliant_spend: float = 0.0
    compliance_score: float = 1.0
    penalty_exposure: float = 0.0
    at_risk_count: int = 0
    at_risk_payments: List[MSMEAtRiskPayment] = Field(default_factory=list)


class ZBBCategoryGap(BaseModel):
    category_id: str
    category_name: str
    actual_spend: float
    should_cost: float
    gap: float
    gap_pct: float | None = None
    driver: str | None = None
    driver_value: float | None = None
    driver_unit: str | None = None


class ZBBModelerOutput(BaseModel):
    zbb_available: bool
    reason: str | None = None
    total_actual_spend: float = 0.0
    total_should_cost: float = 0.0
    total_gap: float = 0.0
    realization_rate: float = 0.0
    category_gaps: List[ZBBCategoryGap] = Field(default_factory=list)
    top_redesign_opportunities: List[str] = Field(default_factory=list)


def validate_vendor_master_output(vm: Dict[str, Any]) -> None:
    VendorMasterOutput.model_validate(vm)


def validate_consolidation_output(con: Dict[str, Any]) -> None:
    ConsolidationAnalyzerOutput.model_validate(con)


def validate_msme_output(msme: Dict[str, Any]) -> None:
    MSMEComplianceOutput.model_validate(msme)


def validate_contract_lifecycle_output(cl: Dict[str, Any]) -> None:
    ContractLifecycleOutput.model_validate(cl)


class CostToServeOutput(BaseModel):
    cost_to_serve_available: bool
    segments: List[Dict[str, Any]]
    cost_per_employee: Optional[Dict[str, Any]]
    top_cost_drivers: List[Dict[str, Any]]
    unprofitable_segments: List[str]
    total_opex_allocated: float
    total_opex_unallocated: float


def validate_cost_to_serve_output(cts: Dict[str, Any]) -> None:
    CostToServeOutput.model_validate(cts)

