from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class RawUploadRecord(BaseModel):
    session_id: str
    filename: str
    content_type: str
    size_bytes: int
    stored_path: str
    uploaded_at: datetime = Field(default_factory=_utcnow)


class NormalizedSpendLine(BaseModel):
    row_id: int
    supplier: str
    description: str
    amount: float
    category_id: str
    category_name: str
    business_unit: Optional[str] = None
    geo: Optional[str] = None
    spend_date: Optional[str] = None
    # FP&A fields
    gl_code: Optional[str] = None
    cost_center_id: Optional[str] = None
    currency: str = "USD"
    fx_rate_to_reporting: float = 1.0
    amount_reporting: Optional[float] = None  # None = same as amount
    amount_type: str = "actual"  # "actual" | "budget" | "forecast" | "accrual"
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None  # e.g. "2025-Q1", "2025-01"
    payment_terms_days: Optional[int] = None
    # India-specific fields (v2.0)
    gst_treatment: Optional[str] = None   # "itc_eligible" | "ineligible" | "rcm" | "inverted_duty"
    gstin: Optional[str] = None           # vendor GSTIN for ITC reconciliation
    lease_treatment: Optional[str] = None # "operating_ind_as_116" | "finance" | "short_term"
    lease_term_months: Optional[int] = None
    related_party_flag: bool = False      # True if intra-group / related-party transaction
    legal_entity_id: Optional[str] = None # source legal entity within a group
    # Contract stickiness fields (v2.1)
    contract_expiry_date: Optional[date] = None
    contract_status: Optional[Literal["in_contract", "rolling", "expired", "at_risk"]] = None
    min_purchase_commitment_usd: Optional[float] = None
    early_exit_penalty_pct: Optional[float] = None
    auto_renewal_notice_days: Optional[int] = None
    # Source lineage (v2.2 — conflict detection requires knowing origin)
    source_system_id: Optional[str] = None      # "SAP_001", "COUPA", "ORACLE_FIN"
    source_record_id: Optional[str] = None      # Primary key in source system
    source_file_hash: Optional[str] = None      # SHA256 of ingested file for dedup
    is_intercompany: Optional[bool] = None      # Derived from related_party_flag + entity tree
    consolidation_eliminated: bool = False      # True when removed in consolidated group view
    # Vendor master enrichment (v2.2)
    vendor_gstin: Optional[str] = None          # Normalized GSTIN — canonical dedup key
    vendor_pan: Optional[str] = None            # PAN — secondary dedup key
    vendor_msme_flag: Optional[bool] = None     # MSME classification for 45-day payment rule
    vendor_category: Optional[Literal["large", "msme", "startup", "foreign"]] = None
    # Cost classification (v2.2)
    spend_type: Optional[Literal["opex", "capex", "lease", "statutory", "intercompany"]] = None
    is_addressable: Optional[bool] = None       # False for statutory/intercompany; True for opex/capex/lease
    spend_quadrant: Optional[Literal["essential", "strategic", "supportive", "discretionary"]] = None
    # Conflict tracking (v2.2)
    conflict_flag: Optional[str] = None         # "tds_mismatch" | "gst_mismatch" | "vendor_duplicate" …
    conflict_resolution: Optional[str] = None   # Applied resolution strategy
    reconciled_amount: Optional[float] = None   # Canonical amount after conflict resolution
    # Data-quality propagation (v2.3)
    data_quality_score: float = 0.0             # 0.0–1.0; fraction of key fields populated at ingestion
    is_credit_or_reversal: bool = False         # True when amount < 0 or description signals a credit/reversal

    @field_validator("fx_rate_to_reporting")
    @classmethod
    def _fx_rate_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"fx_rate_to_reporting must be > 0, got {v}")
        return v

    @property
    def reporting_amount(self) -> float:
        """Amount in the engagement reporting currency."""
        if self.amount_reporting is not None:
            return self.amount_reporting
        # fx_rate_to_reporting is guaranteed > 0 by _fx_rate_positive validator.
        return self.amount * self.fx_rate_to_reporting

    @property
    def effective_reporting_amount(self) -> float:
        """Amount included in the consolidated spend baseline after conflict resolution."""
        if self.consolidation_eliminated:
            return 0.0
        if self.reconciled_amount is not None:
            return float(self.reconciled_amount)
        return self.reporting_amount

    @property
    def in_spend_base(self) -> bool:
        return not self.consolidation_eliminated


def is_actual(line: "NormalizedSpendLine") -> bool:
    """Canonical actual-spend predicate.

    Treats an empty ``amount_type`` as actual (defensive: some sources leave the
    column blank). Use this everywhere actuals are filtered so spend_profiler,
    temporal_analyzer and payment_terms_optimizer stay consistent.
    """
    return line.amount_type in ("actual", "")


class SkillIO(BaseModel):
    session_id: str
    skill_name: str
    input: Dict[str, Any]
    output: Dict[str, Any]
    narrative: str = ""
    confidence: Dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)


class SessionAnalysisState(BaseModel):
    session_id: str
    engagement_id: Optional[str] = None  # v2.0: parent engagement scope
    company_name: Optional[str] = None
    industry: str = ""
    annual_revenue: float = 0.0
    reporting_currency: str = "USD"
    normalized_spend: List[NormalizedSpendLine] = Field(default_factory=list)
    context_summary: str = ""
    skill_outputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    # Human-readable, ordered trace of how the analysis was derived — one entry
    # per pipeline step, each carrying the source documents it drew on. Surfaced
    # as the "How this analysis was derived" collapsible in the chat.
    analysis_trace: List[Dict[str, Any]] = Field(default_factory=list)
    spend_base_revision: int = 0
    updated_at: datetime = Field(default_factory=_utcnow)


class SkillMetadata(BaseModel):
    name: str
    version: str = "0.1.0"
    status: str = "active"
    path: str
    description: str = ""


# ---------------------------------------------------------------------------
# v2.2 Enterprise models
# ---------------------------------------------------------------------------

class VendorMaster(BaseModel):
    """Canonical vendor record built by vendor_master_builder skill."""
    vendor_id: str = Field(default_factory=_new_id)
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    gstin: Optional[str] = None
    pan: Optional[str] = None
    msme_flag: Optional[bool] = None
    vendor_category: str = "large"
    contract_count: int = 0
    earliest_contract: Optional[date] = None
    latest_renewal: Optional[date] = None
    spend_ytd: float = 0.0
    source_systems: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class EntityNode(BaseModel):
    """A single legal entity within the group org chart."""
    entity_id: str
    entity_name: str
    parent_id: Optional[str] = None
    entity_type: Literal["group", "subsidiary", "division", "branch"] = "subsidiary"
    gstin: Optional[str] = None
    pan: Optional[str] = None
    country: str = "IN"


class EntityTree(BaseModel):
    """Org-chart tree for multi-entity consolidation.

    Nodes list is flat; parent_id links form the hierarchy.
    root_id must match exactly one node's entity_id.
    """
    root_id: str
    nodes: List[EntityNode] = Field(default_factory=list)

    def get_entity_ids(self) -> List[str]:
        return [n.entity_id for n in self.nodes]

    def get_children(self, parent_id: str) -> List[EntityNode]:
        return [n for n in self.nodes if n.parent_id == parent_id]

    def get_related_entity_ids(self, entity_id: str) -> List[str]:
        """All entities in the same group excluding the given one."""
        return [n.entity_id for n in self.nodes if n.entity_id != entity_id]

    def is_related_party(self, entity_a: str, entity_b: str) -> bool:
        """True when both entities belong to this group."""
        ids = self.get_entity_ids()
        return entity_a in ids and entity_b in ids


class ConflictRecord(BaseModel):
    """A detected data conflict between two sources, with optional resolution."""
    conflict_id: str = Field(default_factory=_new_id)
    conflict_type: Literal[
        "tds_mismatch",
        "gst_mismatch",
        "vendor_duplicate",
        "intercompany_inflation",
        "fx_mismatch",
        "benchmark_disagreement",
        "amount_mismatch",
        "cost_center_lag",
    ]
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    source_a: str
    source_b: str
    amount_a: Optional[float] = None
    amount_b: Optional[float] = None
    delta_pct: Optional[float] = None
    resolution_strategy: Optional[str] = None
    resolved: bool = False
    resolution_notes: Optional[str] = None
    row_ids: List[int] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=_utcnow)

