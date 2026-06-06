"""Pydantic request/response schemas for all API routers."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


class _FinancialParamsMixin(BaseModel):
    """Shared validators for financial request parameters."""

    @field_validator("annual_revenue", mode="before", check_fields=False)
    @classmethod
    def validate_annual_revenue(cls, v: float) -> float:
        v = float(v)
        if v < 0:
            raise ValueError("annual_revenue must be non-negative")
        return v

    @field_validator("wacc", mode="before", check_fields=False)
    @classmethod
    def validate_wacc(cls, v: float) -> float:
        v = float(v)
        if not (0 < v < 1):
            raise ValueError(
                f"wacc must be between 0 and 1 exclusive (e.g. 0.10 = 10%); received {v}"
            )
        return v

    @field_validator("effective_tax_rate", mode="before", check_fields=False)
    @classmethod
    def validate_effective_tax_rate(cls, v: float) -> float:
        v = float(v)
        if not (0 <= v <= 1):
            raise ValueError(
                f"effective_tax_rate must be between 0 and 1 inclusive; received {v}"
            )
        return v


class EngagementCreateRequest(_FinancialParamsMixin):
    company_name: str | None = None
    industry: str | None = None
    annual_revenue: float = 0.0
    currency: str | None = None
    headcount: float | None = None


class EngagementPatchRequest(BaseModel):
    company_name: str | None = None
    industry: str | None = None
    annual_revenue: float | None = None
    currency: str | None = None
    headcount: float | None = None


class SessionCreateRequest(_FinancialParamsMixin):
    company_name: str | None = None
    industry: str | None = None
    annual_revenue: float = 0.0
    currency: str | None = None
    audience: str | None = None
    headcount: float | None = None
    engagement_id: str | None = None
    wacc: float = 0.10
    effective_tax_rate: float = 0.0


class AnalyzeRequest(_FinancialParamsMixin):
    company_name: str | None = None
    industry: str | None = None
    annual_revenue: float = 0.0
    currency: str | None = None
    audience: str | None = None
    wacc: float = 0.10
    effective_tax_rate: float = 0.0
    # Optional client-generated run id; when present, the analysis streams live
    # progress steps to GET /api/v1/chat/progress/{run_id} as it executes.
    run_id: str | None = None


class SessionManifestPatch(BaseModel):
    company_name: str | None = None
    industry: str | None = None
    annual_revenue: float | None = None
    currency: str | None = None
    audience: str | None = None


class SkillEditRequest(BaseModel):
    content: str


class SkillCreateRequest(BaseModel):
    name: str
    content: str


class ChatRequest(BaseModel):
    message: str


class ChatHistoryTurn(BaseModel):
    role: str
    content: str


class V1ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: str | None = None
    run_id: str | None = None
    company_name: str | None = None
    industry: str | None = None
    annual_revenue: float | None = None
    currency: str | None = None
    audience: str | None = None
    headcount: float | None = None
    thinking_mode: str | None = None  # "standard" | "extended"
    chat_history: List[ChatHistoryTurn] | None = None


class ProbeAnswerRequest(BaseModel):
    session_id: str
    probe_family_id: str
    question: str | None = None
    answer: str
    selected_option: str | None = None
    scope: str | None = "portfolio"
    applies_to_categories: List[str] | None = None

    @field_validator("probe_family_id", "answer")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("field is required")
        return v


class ClarificationResumeRequest(BaseModel):
    checkpoint_id: str
    selected_option: str | None = None
    free_text: str | None = None
    run_id: str | None = None
    thinking_mode: str | None = None  # "standard" | "extended"
    company_name: str | None = None
    industry: str | None = None
    annual_revenue: float | None = None
    currency: str | None = None
    audience: str | None = None
    headcount: float | None = None
    chat_history: List[ChatHistoryTurn] | None = None

    @field_validator("checkpoint_id")
    @classmethod
    def validate_checkpoint_id(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("checkpoint_id is required")
        return v

    def has_answer(self) -> bool:
        return bool((self.selected_option or "").strip() or (self.free_text or "").strip())


class InitiativeCreateRequest(BaseModel):
    user_id: str | None = None
    session_id: str | None = None
    analysis_id: str | None = None
    category: str
    lever: str
    root_cause: str | None = None
    gross_savings_y1: float = 0.0
    gross_savings_y2: float = 0.0
    gross_savings_y3: float = 0.0
    cost_to_achieve: float = 0.0
    net_npv: float = 0.0
    committed_savings: float = 0.0
    savings_type: str = "run_rate"
    annualized_run_rate_savings: float = 0.0
    implementation_cost_schedule: list = []
    stage: str = "identified"
    owner_name: str | None = None
    owner_email: str | None = None
    committed_date: str | None = None
    target_realization_date: str | None = None


class InitiativeStageRequest(BaseModel):
    stage: str


class InitiativeRejectRequest(BaseModel):
    reason: str


class MilestoneCreateRequest(BaseModel):
    description: str
    due_date: str
    status: str = "pending"
    evidence_doc_ref: str | None = None
    completed_at: str | None = None


class ActualsCreateRequest(BaseModel):
    period: str
    actual_savings: float
    committed_savings: float | None = None
    gl_reference: str | None = None
    notes: str | None = None


class RealisedSavingsIngestRequest(BaseModel):
    """Realised-savings records feeding the calibration loop. Each record maps to
    calibration.RealisedSavingsRecord (initiative_id, lever_id, pack_id,
    planned_p50_cr, realised_cr, realised_date, data_source, ...)."""
    records: List[Dict[str, Any]]


class BenchmarkDatasetCreateRequest(BaseModel):
    source: str
    industry_code: str | None = None
    industry_name: str | None = None
    category_coverage: Dict[str, List[str]]
    vintage_date: str | None = None
    sample_size: int = 0
    revenue_band_min: float | None = None
    revenue_band_max: float | None = None
    geography: str | None = None
    specificity_score: float = 0.5
    license_expiry: str | None = None
    data_file_ref: str | None = None


class BenchmarkSelectRequest(BaseModel):
    industry: str
    categories: List[str]
    annual_revenue: float | None = None


class PeerSetCreateRequest(BaseModel):
    name: str
    industry: str
    dataset_ids: List[str]
    description: str = ""
    override_categories: Dict[str, Any] | None = None


class ConflictResolveRequest(BaseModel):
    conflict_ids: List[str] = []
    strategy: str | None = None


class ConsolidateRequest(BaseModel):
    entity_tree: Dict[str, Any] | None = None
    include_entity_comparison: bool = False


class SectorPackOverrideRequest(BaseModel):
    pack_id: str
    disabled_levers: List[str] = []
    lever_overrides: Dict[str, Any] = {}
    engagement_id: Optional[str] = None


class CostToServeRequest(BaseModel):
    session_id: str
    segment_revenue: Optional[Dict[str, float]] = None
    headcount: Optional[float] = None


class CompanyResearchRequest(BaseModel):
    company_name: str
    industry: str
    annual_revenue_cr: float = 5000.0
    urls: List[str] = []
    headcount: int = 500
    wacc: float = 0.12
    engagement_id: Optional[str] = None


class DeepResearchStartRequest(BaseModel):
    company_name: str
    industry: str
    annual_revenue_cr: float = 5000.0
    session_id: str | None = None
    research_prompt: str | None = None


class DeepResearchStartResponse(BaseModel):
    interaction_id: str
    status: str  # "in_progress"


class DeepResearchStatusResponse(BaseModel):
    status: str  # "in_progress" | "completed" | "failed"
    summary: str | None = None      # LLM-condensed ≤400 words
    full_report: str | None = None  # raw output_text
    sources: List[Any] = []


class DiagnosticContextPatch(BaseModel):
    company_name: str | None = None
    industry: str | None = None
    annual_revenue_cr: float | None = None
    deep_research_summary: str | None = None
    deep_research_interaction_id: str | None = None
    diagnostic_urls: List[str] | None = None
    diagnostic_result: Dict[str, Any] | None = None
    diagnostic_completed_at: str | None = None


class ConnectorIngestRequest(BaseModel):
    session_id: str
    source_file: str
    source_system_id: str | None = None
    credentials: Dict[str, str] = {}
    fetch_kwargs: Dict[str, Any] = {}
    run_analysis: bool = False
