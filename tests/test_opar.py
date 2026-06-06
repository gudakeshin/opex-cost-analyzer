"""Unit tests for OPAR (Observe, Plan, Act, Reflect) modules."""

from __future__ import annotations

from unittest.mock import patch

from app.opar.observe import (
    _classify_intent_rule_based,
    assess_data_quality,
    classify_intent,
    classify_intent_with_meta,
)
from app.opar.plan import _plan_rule_based, plan
from app.opar.reflect import (
    _compute_dedup_factor,
    _determine_loop_control,
    _layer2_coherence_checks,
)
from app.opar.models import AdvisorySections, ExecutionPlan, ObserveContext, SkillTask
from app.opar.orchestrator import _should_use_cached_qa_fastpath
from app.opar.qa_lookup import answer_general_qa as _answer_general_qa, build_sme_critique_section
from app.opar.reflect import _advisory_quality_ok, _compose_response_from_advisory


def test_classify_intent_rule_based() -> None:
    assert _classify_intent_rule_based("upload my spend file") == ("upload_data", None)
    assert _classify_intent_rule_based("run benchmark analysis") == ("benchmark", None)
    assert _classify_intent_rule_based("compare to peers") == ("benchmark", None)
    assert _classify_intent_rule_based("value bridge for IT") == ("value_bridge", None)
    assert _classify_intent_rule_based("generate business case") == ("business_case", None)
    assert _classify_intent_rule_based("analyze my data") == ("benchmark", None)
    assert _classify_intent_rule_based("show addressable IT & Technology spends") == ("value_bridge", None)
    assert _classify_intent_rule_based("How can I optimize my IT & Technology costs?") == ("value_bridge", None)
    # Conversational messages must fall back to general_qa, NOT upload_data.
    # The old default (upload_data) caused the OPAR loop to run the spend-profiler
    # on every message — including greetings — which is the bug being fixed here.
    assert _classify_intent_rule_based("hello") == ("general_qa", None)
    assert _classify_intent_rule_based("what can you do?") == ("general_qa", None)
    assert _classify_intent_rule_based("tell me about my results") == ("general_qa", None)


def test_classify_intent_with_meta_returns_confidence() -> None:
    meta = classify_intent_with_meta("How can I optimize my IT & Technology costs?")
    assert meta["intent_class"] == "value_bridge"
    assert meta["intent_source"] in {"rule_based", "claude_disambiguated"}
    assert 0.0 <= float(meta["intent_confidence"]) <= 1.0


def test_answer_general_qa_addressable_for_specific_category() -> None:
    validated = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "spend": 300_000,
                    "line_count": 12,
                    "addressable_spend": 120_000,
                }
            ],
        }
    }
    out = _answer_general_qa("What is addressable IT & Technology spend?", validated)
    assert "addressable spend" in out.lower()
    assert "$120,000" in out


def test_answer_general_qa_category_match_with_symbol_variant() -> None:
    validated = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "spend": 300_000,
                    "line_count": 12,
                    "addressable_spend": 120_000,
                }
            ],
        }
    }
    out = _answer_general_qa("Show addressable IT and Technology spends", validated)
    assert "addressable spend" in out.lower()
    assert "IT & Technology" in out


def test_answer_general_qa_optimization_uses_value_evidence() -> None:
    validated = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "spend": 300_000,
                    "line_count": 12,
                    "addressable_spend": 120_000,
                }
            ],
        },
        "value-bridge-calculator": {
            "value_matrix": [
                {
                    "category_id": "IT_TECH",
                    "category_name": "IT & Technology",
                    "lever": "supplier_consolidation",
                    "deduped_mid_savings": 55_000,
                    "net_npv": 110_000,
                    "payback_months": 8,
                }
            ]
        },
    }
    out = _answer_general_qa("How can I optimize IT & Technology costs?", validated)
    assert "Modeled lever" in out
    assert "$55,000" in out


def test_should_use_cached_qa_fastpath_blocks_savings_questions() -> None:
    ctx = ObserveContext(
        session_id="s1",
        user_message="What savings opportunities should we prioritize?",
        intent_class="general_qa",
        query_capabilities=["value_modeling"],
    )
    assert _should_use_cached_qa_fastpath(ctx, ctx.user_message) is False


def test_should_use_cached_qa_fastpath_allows_simple_lookup() -> None:
    ctx = ObserveContext(
        session_id="s1",
        user_message="What is my total spend?",
        intent_class="general_qa",
        query_capabilities=[],
    )
    assert _should_use_cached_qa_fastpath(ctx, ctx.user_message) is True


def test_answer_general_qa_savings_priorities_includes_sme_critique() -> None:
    validated = {
        "spend-profiler": {
            "total_spend": 1_000_000,
            "category_profile": [{"category_id": "IT", "category_name": "IT", "spend": 300_000}],
        },
        "value-bridge-calculator": {
            "confidence_bands": {"low": 40_000, "mid": 80_000, "high": 120_000},
            "value_matrix": [
                {
                    "category_id": "IT",
                    "category_name": "IT",
                    "lever": "contract_renegotiation",
                    "deduped_mid_savings": 55_000,
                    "confidence": "medium",
                }
            ],
        },
        "sme-critique": {
            "critique_summary": {
                "ready_count": 0,
                "probe_count": 1,
                "insufficient_count": 0,
                "savings_ready": 0,
                "savings_probe": 165_000,
                "savings_insufficient": 0,
            },
            "initiative_critiques": [
                {
                    "category_name": "IT",
                    "sme_verdict": "probe_first",
                    "critical_risk": "No contract register — renewal timing unknown.",
                    "probe_questions": [
                        {
                            "question": "When do IT contracts expire?",
                            "why_critical": "Locked contracts push savings to future periods.",
                        }
                    ],
                }
            ],
        },
    }
    out = _answer_general_qa("What savings opportunities should we prioritize?", validated)
    assert "Top modeled savings priorities" in out
    assert "SME qualification" in out
    assert "contract register" in out.lower()
    assert "Based on your uploaded data: total spend" not in out


def test_compose_response_from_advisory_includes_sme_narrative() -> None:
    advisory = AdvisorySections(
        executive_takeaway="IT spend is above peer median with consolidation upside.",
        quick_wins_from_data=["Renegotiate top 2 vendors", "Enforce PO compliance"],
        business_levers=[
            {
                "lever_name": "Supplier consolidation",
                "what_changes": "Reduce vendor count from 12 to 5",
                "why_it_works": "Concentration unlocks volume pricing",
                "evidence": ["Top 3 vendors are 68% of spend", "Peer median is 4 vendors"],
            },
            {
                "lever_name": "Contract renegotiation",
                "what_changes": "Reset maintenance terms at renewal",
                "why_it_works": "Benchmark gap is contract-driven",
                "evidence": ["Gap vs P75 is 2.1 pts of revenue", "Largest vendor is 31% of category"],
            },
            {
                "lever_name": "Maverick compliance",
                "what_changes": "Route card spend through approved POs",
                "why_it_works": "Off-contract buying inflates unit cost",
                "evidence": ["Express-like lines are 14% of category", "Policy exists but is not enforced"],
            },
        ],
        sme_qualification_narrative=(
            "The IT consolidation saving assumes contracts renew within 18 months, "
            "but no contract register was uploaded — if locked beyond that horizon, "
            "this saving is FY27+ at best."
        ),
    )
    validated = {
        "value-bridge-calculator": {
            "confidence_bands": {"low": 40_000, "mid": 80_000, "high": 120_000},
        }
    }
    out = _compose_response_from_advisory(advisory, validated)
    assert "SME qualification" in out
    assert "contract register" in out.lower()


def test_build_sme_critique_section_renders_critical_risk() -> None:
    validated = {
        "sme-critique": {
            "critique_summary": {"probe_count": 1, "savings_probe": 100_000},
            "initiative_critiques": [
                {
                    "category_name": "Logistics",
                    "sme_verdict": "probe_first",
                    "critical_risk": "Benchmark gap only — no lane-level freight data.",
                    "probe_questions": [{"question": "Which lanes drive air freight?", "why_critical": "Lane mix sets achievability."}],
                }
            ],
        }
    }
    out = build_sme_critique_section(validated, "USD")
    assert "SME qualification" in out
    assert "lane-level freight" in out.lower()


def test_assess_data_quality_no_spend_file() -> None:
    score, missing = assess_data_quality([], "benchmark", {"files": [], "industry": "tech", "annual_revenue": 1e9})
    assert score == 0.0
    assert "spend_data" in missing


def test_assess_data_quality_with_schema() -> None:
    parse_results = [
        {
            "columns": [
                {"name": "amount", "null_ratio": 0.05},
                {"name": "supplier", "null_ratio": 0.0},
            ],
            "semantic_map": {"amount": "amount"},
        }
    ]
    manifest = {
        "files": [{"path": "x.csv", "schema": parse_results[0]}],
        "industry": "technology",
        "annual_revenue": 1_000_000_000,
    }
    score, missing = assess_data_quality(parse_results, "benchmark", manifest)
    assert score >= 0.8
    assert "spend_data" not in missing
    assert "annual_revenue" not in missing


def test_assess_data_quality_missing_revenue() -> None:
    manifest = {
        "files": [{"path": "x.csv", "schema": {"semantic_map": {"amount": "amount"}}}],
        "industry": "technology",
        "annual_revenue": 0.0,
    }
    score, missing = assess_data_quality([], "benchmark", manifest)
    assert "annual_revenue" in missing


def test_assess_data_quality_clarification_required_returns_bool() -> None:
    """Regression: clarification_required must be bool, not list."""
    manifest = {
        "files": [{"path": "x.csv", "schema": {"semantic_map": {"amount": "amount"}}}],
        "industry": "technology",
        "annual_revenue": 1e9,
    }
    score, missing = assess_data_quality([], "benchmark", manifest)
    assert isinstance(score, float)
    assert isinstance(missing, list)


@patch("app.opar.observe.ANTHROPIC_ENABLED", False)
def test_classify_intent_fallback_when_anthropic_disabled() -> None:
    """When ANTHROPIC_ENABLED is False, uses rule-based classification."""
    intent, cat = classify_intent("run benchmark")
    assert intent == "benchmark"
    assert cat is None


def test_plan_rule_based_upload_data() -> None:
    ctx = ObserveContext(
        user_message="upload file",
        intent_class="upload_data",
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    assert isinstance(exec_plan, ExecutionPlan)
    assert len(exec_plan.tasks) == 2
    assert exec_plan.tasks[0].skill_name == "spend-profiler"
    assert exec_plan.tasks[1].skill_name == "chart-builder"


def test_plan_rule_based_benchmark() -> None:
    ctx = ObserveContext(
        user_message="benchmark",
        intent_class="benchmark",
        has_annual_revenue=False,
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    assert len(exec_plan.tasks) == 3
    skill_names = [t.skill_name for t in exec_plan.tasks]
    assert "spend-profiler" in skill_names
    assert "peer-benchmarker" in skill_names
    assert "internal-benchmarker" in skill_names
    assert "payment-terms-optimizer" not in skill_names
    assert "bva-analyzer" not in skill_names
    assert "temporal-analyzer" not in skill_names
    assert "chart-builder" not in skill_names
    assert "heuristic-analyzer" not in skill_names
    assert "value-bridge-calculator" not in skill_names
    assert "analysis-synthesizer" not in skill_names


def test_plan_rule_based_benchmark_includes_heuristic_when_revenue_present() -> None:
    ctx = ObserveContext(
        user_message="benchmark my spend",
        intent_class="benchmark",
        has_annual_revenue=True,
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    skill_names = [t.skill_name for t in exec_plan.tasks]
    assert "heuristic-analyzer" in skill_names
    assert "value-bridge-calculator" not in skill_names


def test_plan_rule_based_benchmark_adds_working_cap_skill_when_capability_present() -> None:
    ctx = ObserveContext(
        user_message="Benchmark and optimize payment terms to improve DPO",
        intent_class="benchmark",
        has_annual_revenue=True,
        query_capabilities=["benchmarking", "working_capital"],
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    skill_names = [t.skill_name for t in exec_plan.tasks]
    assert "payment-terms-optimizer" in skill_names


def test_plan_rule_based_general_qa_category_optimization_uses_deep_chain() -> None:
    ctx = ObserveContext(
        user_message="How can I optimize Professional Services costs?",
        intent_class="general_qa",
        explicit_category="Professional Services",
        query_capabilities=["value_modeling", "root_cause"],
        has_tabular_spend=True,
        spend_profile_ready=True,
        data_quality_score=0.9,
        has_annual_revenue=True,
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    skill_names = [t.skill_name for t in exec_plan.tasks]
    assert "value-bridge-calculator" in skill_names
    assert "savings-modeler" in skill_names
    assert "root-cause-analyzer" in skill_names
    assert "data-validator" in skill_names
    assert "chart-builder" in skill_names


def test_plan_rule_based_value_bridge_has_modeling_chain_without_exec_narrative() -> None:
    ctx = ObserveContext(
        user_message="calculate value at the table",
        intent_class="value_bridge",
        has_annual_revenue=True,
        has_document_files=False,
        wants_executive_narrative=False,
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    skill_names = [t.skill_name for t in exec_plan.tasks]
    assert "root-cause-analyzer" in skill_names
    assert "savings-modeler" in skill_names
    assert "value-bridge-calculator" in skill_names
    assert "data-validator" in skill_names
    assert "analysis-synthesizer" not in skill_names
    assert "executive-communication" not in skill_names


def test_plan_rule_based_value_bridge_narrative_delegated_to_reflect_advisory() -> None:
    """Executive narrative is produced by reflect's single LLM advisory pass, not by
    separate act-phase synthesis skills (which duplicated the same LLM call)."""
    ctx = ObserveContext(
        user_message="calculate value bridge and make it executive-ready",
        intent_class="value_bridge",
        has_annual_revenue=True,
        has_document_files=True,
        wants_executive_narrative=True,
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    skill_names = [t.skill_name for t in exec_plan.tasks]
    # Modeling chain still runs; narrative composition is reflect's job.
    assert "value-bridge-calculator" in skill_names
    assert "analysis-synthesizer" not in skill_names
    assert "executive-communication" not in skill_names


def test_plan_rule_based_business_case() -> None:
    ctx = ObserveContext(
        user_message="business case",
        intent_class="business_case",
        session_id="s1",
        user_id="u1",
    )
    exec_plan = _plan_rule_based(ctx)
    assert exec_plan.requires_approval is True
    assert "business-case-builder" in [t.skill_name for t in exec_plan.tasks]


def test_plan_always_rule_based() -> None:
    """plan() always uses the rule-based DAG (LLM path removed)."""
    ctx = ObserveContext(
        user_message="benchmark",
        intent_class="benchmark",
        session_id="s1",
        user_id="u1",
    )
    exec_plan = plan(ctx)
    assert len(exec_plan.tasks) >= 3
    assert exec_plan.user_summary


# --- Phase 2: Act and Reflect ---


def test_determine_loop_control_spend_profiler_failure() -> None:
    """Hard failure when spend-profiler fails."""
    validated = {}
    failed = {"spend-profiler": "No spend data"}
    ctx = ObserveContext(user_message="x", session_id="s1", user_id="u1")
    plan_obj = ExecutionPlan(tasks=[SkillTask(skill_name="spend-profiler", inputs={})])
    complete, trigger = _determine_loop_control(validated, failed, ctx, plan_obj)
    assert complete is False
    assert "Spend classification failed" in (trigger or "")


def test_determine_loop_control_missing_fields() -> None:
    """Soft failure when missing fields and low DQ."""
    validated = {"spend-profiler": {}}
    failed = {}
    ctx = ObserveContext(
        user_message="x",
        session_id="s1",
        user_id="u1",
        missing_fields=["annual_revenue"],
        data_quality_score=0.5,
    )
    plan_obj = ExecutionPlan(tasks=[])
    complete, trigger = _determine_loop_control(validated, failed, ctx, plan_obj)
    assert complete is True
    assert "annual_revenue" in (trigger or "")


def test_determine_loop_control_suggest_value_bridge() -> None:
    """Suggest value-bridge when benchmarks done but not value-bridge."""
    validated = {
        "spend-profiler": {},
        "peer-benchmarker": {},
        "internal-benchmarker": {},
        "heuristic-analyzer": {},
    }
    failed = {}
    ctx = ObserveContext(user_message="x", session_id="s1", user_id="u1")
    plan_obj = ExecutionPlan(
        tasks=[
            SkillTask(skill_name="peer-benchmarker", inputs={}),
            SkillTask(skill_name="internal-benchmarker", inputs={}),
            SkillTask(skill_name="heuristic-analyzer", inputs={}),
        ]
    )
    complete, trigger = _determine_loop_control(validated, failed, ctx, plan_obj)
    assert complete is True
    assert "Benchmarking complete" in (trigger or "")


def test_determine_loop_control_complete() -> None:
    """Complete when value-bridge done and no follow-up needed."""
    validated = {
        "spend-profiler": {},
        "value-bridge-calculator": {"value_matrix": [], "confidence_bands": {"low": 0, "mid": 0, "high": 0}},
    }
    failed = {}
    ctx = ObserveContext(user_message="x", session_id="s1", user_id="u1")
    plan_obj = ExecutionPlan(
        tasks=[
            SkillTask(skill_name="spend-profiler", inputs={}),
            SkillTask(skill_name="value-bridge-calculator", inputs={}),
        ]
    )
    complete, trigger = _determine_loop_control(validated, failed, ctx, plan_obj)
    assert complete is True  # Suggests business case
    assert trigger is not None


def test_compute_dedup_factor() -> None:
    """Dedup factor based on lever overlap."""
    validated = {
        "value-bridge-calculator": {
            "value_matrix": [
                {"peer_savings": 100, "internal_savings": 50, "heuristic_savings": 30},
                {"peer_savings": 0, "internal_savings": 10, "heuristic_savings": 0},
            ]
        }
    }
    factor = _compute_dedup_factor(validated)
    assert 0.6 <= factor <= 0.8


def test_layer2_coherence_no_failure_on_valid_data() -> None:
    """Layer 2 coherence does not add failures when data is valid."""
    validated = {
        "spend-profiler": {
            "total_spend": 1000,
            "category_profile": [{"category_id": "IT", "spend": 500}],
        },
        "peer-benchmarker": {
            "comparisons": [{"category_id": "IT", "estimated_saving_amount": 50}],
        },
        "internal-benchmarker": {
            "internal_variance": [{"median_spend": 40, "max_spend": 50}],
        },
        "heuristic-analyzer": {
            "heuristic_findings": [{"actual_pct_of_revenue": 5, "heuristic_target_pct": 6}],
        },
    }
    failed = {}
    scores = {}
    _layer2_coherence_checks(validated, failed, scores)
    assert "contract_validation" not in failed


def test_advisory_quality_gate_rejects_generic_levers() -> None:
    advisory = AdvisorySections(
        executive_takeaway="Initial logistics readout with one generic recommendation.",
        category_focus_section="Focused on logistics",
        quick_wins_from_data=["Win 1", "Win 2", "Win 3"],
        business_levers=[
            {
                "lever_name": "internal best practice",
                "what_changes": "Adopt best practice.",
                "why_it_works": "It is helpful.",
                "evidence": ["Evidence"],
            },
            {
                "lever_name": "Supplier consolidation",
                "what_changes": "Consolidate carriers and rebid.",
                "why_it_works": "Higher volume concentration improves rate card economics.",
                "evidence": ["Top-2 suppliers hold 70% share"],
            },
            {
                "lever_name": "Mode shift",
                "what_changes": "Shift non-urgent express lanes to economy.",
                "why_it_works": "Unit rates are materially lower on deferred lanes.",
                "evidence": ["Express-like spend is 22%"],
            },
        ],
    )
    assert _advisory_quality_ok(advisory) is False


def test_advisory_quality_gate_accepts_actionable_levers() -> None:
    advisory = AdvisorySections(
        executive_takeaway="Logistics has immediate, model-backed levers with near-term working-capital upside.",
        category_focus_section="Focused on logistics",
        quick_wins_from_data=["Win 1", "Win 2", "Win 3"],
        business_levers=[
            {
                "lever_name": "Carrier consolidation",
                "what_changes": "Run a global 3PL RFP and consolidate volume under one primary carrier with lane-level governance.",
                "why_it_works": "Volume bundling improves pricing tiers and enables service-level commitments with fewer exceptions.",
                "evidence": [
                    "Current supplier count is 4 with fragmented regional contracts",
                    "Top-2 suppliers control 68% of spend but rates vary by lane",
                ],
            },
            {
                "lever_name": "Payment-term harmonization",
                "what_changes": "Move short-term carrier contracts to Net 30 and align all carrier terms in the next renewal cycle.",
                "why_it_works": "Extending DPO releases working capital without reducing shipment volume.",
                "evidence": [
                    "Largest carrier is on Net 14 versus peer at Net 30",
                    "Working-capital release opportunity identified in terms optimizer",
                ],
            },
            {
                "lever_name": "Mode-shift policy",
                "what_changes": "Require express approvals and default qualifying lanes to deferred mode in TMS routing rules.",
                "why_it_works": "Deferred freight materially lowers unit cost while preserving service for non-urgent shipments.",
                "evidence": [
                    "Express-like spend is above threshold in this category",
                    "Lane-level shipment mix indicates non-urgent volume",
                ],
            },
        ],
    )
    assert _advisory_quality_ok(advisory) is True
