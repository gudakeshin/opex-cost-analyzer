from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class IntentClass(str, Enum):
    """T2-3: Typed intent classifications used throughout the OPAR loop.

    Using ``str, Enum`` makes JSON serialisation transparent (values are plain
    strings) while mypy / Pydantic catch silent typos at parse time rather than
    at runtime inside a 200-line orchestrator function.

    ``ObserveContext.intent_class`` remains ``str`` for graceful handling of
    LLM-returned values that are not yet in this enum.  New code should use
    ``IntentClass.BENCHMARK`` rather than the bare string ``"benchmark"``
    so that typos are caught by type checkers rather than silently failing
    at runtime.
    """

    UPLOAD_DATA = "upload_data"
    BENCHMARK = "benchmark"
    VALUE_BRIDGE = "value_bridge"
    BUSINESS_CASE = "business_case"
    EXPORT_BUSINESS_CASE = "export_business_case"
    DRILL_DOWN = "drill_down"
    SAVINGS_PLAN = "savings_plan"
    SENSITIVITY = "sensitivity"
    TEMPORAL = "temporal"
    BVA = "bva"
    PAYMENT_TERMS = "payment_terms"
    GENERAL_QA = "general_qa"
    # Phase 2 — conflict management and enterprise data intents
    CONFLICT_REVIEW = "conflict_review"
    CONSOLIDATE = "consolidate"
    VENDOR_MASTER = "vendor_master"
    CONTRACT_REVIEW = "contract_review"
    ZBB = "zbb"
    COST_TO_SERVE = "cost_to_serve"
    GSTR_RECONCILE = "gstr_reconcile"


class ObserveContext(BaseModel):
    user_message: str
    # Keep as ``str`` to gracefully accept unknown values from LLM output.
    # Use IntentClass constants when *comparing* (e.g. ctx.intent_class == IntentClass.BENCHMARK).
    intent_class: str = IntentClass.UPLOAD_DATA
    explicit_category: str | None = None
    intent_source: str = "rule_based"
    intent_confidence: float = 0.0
    category_confidence: float = 0.0
    query_capabilities: List[str] = Field(default_factory=list)

    uploaded_file_ids: List[str] = Field(default_factory=list)
    headcount: float | None = None
    spend_profile_ready: bool = False
    benchmark_results_ready: bool = False
    has_tabular_spend: bool = False
    has_document_files: bool = False
    has_annual_revenue: bool = False
    has_headcount: bool = False
    wants_executive_narrative: bool = False
    wants_document_context: bool = False
    wants_spend_visualization: bool = False
    model_manifest: Dict[str, Any] = Field(default_factory=dict)
    model_manifest_confidence: float = 0.0
    schema_confirmation_required: bool = False
    schema_confirmation_note: str | None = None

    user_memory: List[Dict[str, Any]] = Field(default_factory=list)
    session_memory: List[Dict[str, Any]] = Field(default_factory=list)
    agent_memories: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)

    file_parse_status: Dict[str, str] = Field(default_factory=dict)  # file_id -> ok|partial|failed
    missing_fields: List[str] = Field(default_factory=list)
    data_quality_score: float = 0.0
    clarification_required: bool = False
    clarification_prompt: str | None = None

    session_id: str = ""
    user_id: str = ""
    turn_id: str = ""

    # Phase 3: engagement-week + decision-gate context
    engagement_week: int = 1          # 1–12; inferred from session metadata
    decision_gate: str = ""           # e.g. "Gate-1", "Gate-2", "Gate-3"
    engagement_id: str = ""           # engagement scope (outermost session boundary)

    # Phase 2: conflict detection signals
    multi_source_upload: bool = False          # True when 2+ source systems detected in session files
    conflict_count: int = 0                    # Number of conflicts detected across sources
    unresolved_conflict_count: int = 0         # Conflicts requiring action
    has_intercompany_lines: bool = False        # True when related_party/intercompany lines found
    conflict_summary: Dict[str, Any] = Field(default_factory=dict)


class SkillTask(BaseModel):
    skill_name: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    parallel_group: int = 0
    expected_schema: Dict[str, Any] = Field(default_factory=dict)
    estimated_tokens: int = 0


class ExecutionPlan(BaseModel):
    tasks: List[SkillTask] = Field(default_factory=list)
    total_skills: int = 0
    parallel_groups: int = 0
    user_summary: str = ""
    estimated_duration: str = ""
    requires_approval: bool = False


class SkillTrace(BaseModel):
    """Per-skill execution trace for evaluation and grounding."""
    skill_name: str
    parallel_group: int = 0
    input_snapshot: Dict[str, Any] = Field(default_factory=dict)  # resolved deps fed into skill
    output: Optional[Dict[str, Any]] = None                        # full output, not truncated
    error: Optional[str] = None
    duration_ms: float = 0.0                                       # per-skill wall-clock time


class EvalTrace(BaseModel):
    """Full execution trace for one act() call — persisted to eval_trace.json."""
    session_id: str = ""
    turn_id: str = ""
    created_at: str = ""                                           # ISO-8601 timestamp
    skill_traces: List[SkillTrace] = Field(default_factory=list)
    total_duration_ms: float = 0.0


class ActResult(BaseModel):
    skill_outputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    errors: Dict[str, str] = Field(default_factory=dict)
    degradation_reasons: Dict[str, str] = Field(default_factory=dict)
    duration_ms: float = 0.0
    eval_trace: Optional[EvalTrace] = None  # populated when enable_tracing=True


class ConfidenceScore(BaseModel):
    level: Literal["low", "mid", "high"] = "mid"
    factor: float = 0.75
    rationale: str = ""


class MemoryUpdate(BaseModel):
    scope: str  # user | session | agent
    key: str
    content: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AdvisoryBusinessLever(BaseModel):
    lever_name: str
    what_changes: str
    why_it_works: str
    evidence: List[str] = Field(default_factory=list)


class AdvisoryActionItem(BaseModel):
    timeline: str
    action: str
    expected_impact: str


class AdvisorySections(BaseModel):
    executive_takeaway: str = ""
    category_focus_section: str = ""
    quick_wins_from_data: List[str] = Field(default_factory=list)
    business_levers: List[AdvisoryBusinessLever] = Field(default_factory=list)
    executive_callouts: List[str] = Field(default_factory=list)
    priority_actions_30_60_90: List[AdvisoryActionItem] = Field(default_factory=list)


class ReflectOutput(BaseModel):
    validated_outputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    failed_validations: Dict[str, str] = Field(default_factory=dict)
    confidence_scores: Dict[str, ConfidenceScore] = Field(default_factory=dict)
    value_bridge_matrix: Any = None  # DataFrame | None
    dedup_factor: float = 0.75

    user_memory_updates: List[MemoryUpdate] = Field(default_factory=list)
    agent_memory_updates: Dict[str, List[MemoryUpdate]] = Field(default_factory=dict)

    loop_complete: bool = True
    next_loop_trigger: str | None = None

    response_text: str = ""
    response_artefacts: List[str] = Field(default_factory=list)
    advisory_sections: AdvisorySections | None = None
    quality_signals: Dict[str, Any] = Field(default_factory=dict)
    used_llm_synthesis: bool = False
    thinking_text: str | None = None
    degraded_mode: bool = False
    fallback_reasons: Dict[str, str] = Field(default_factory=dict)

    # UX: thinking process and interactive options
    progress_steps: List[Dict[str, str]] = Field(default_factory=list)  # [{phase, message}]
    next_options: List[Dict[str, str]] = Field(default_factory=list)  # [{label, message}]

    # Phase 3: replanner + quality gate + regulatory events
    replanner_log: List[Dict[str, Any]] = Field(default_factory=list)  # decisions made by replanner
    gate2_blocked: bool = False
    gate2_narrative: str = ""
    regulatory_events: List[Dict[str, Any]] = Field(default_factory=list)
    forced_regulatory_decision: bool = False
    narrative_provenance_tag: Optional[Dict[str, Any]] = None
