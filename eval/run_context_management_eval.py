#!/usr/bin/env python3
"""
eval/run_context_management_eval.py — OpEx Platform Context-Management Quality Evaluator

Scores the machinery that decides *what reaches the LLM*: synthesis token
budgeting and degradation (reflect_advisory), payload slimming (claude_client),
relevance filtering (select_relevant_outputs), chat-history windowing and field
caps (build_chat_context), and document-RAG context packing (document_index).

13 dimensions across 4 domains. All dimensions except CM-13 are deterministic
(real app functions called in-process against golden fixtures; LLM calls are
mock-patched). CM-13 calibrates the chars/4 token estimator against the real
Anthropic count_tokens API and is gracefully skipped when no Anthropic provider
is configured.

Three dimensions are honest-gap probes expected to FAIL until the underlying
mechanism improves:
  CM-03 — _drop_largest_to_budget drops purely by size; core synthesis skills
          are not protected.
  CM-04 — the budget gate's estimate omits payload sections the synthesizer
          actually sends (model_manifest, sme_critique_data,
          deep_research_context, system prompt, hints).
  CM-10 — build_chat_context has no overall budget; several fields are
          unbounded passthroughs.

Complements:
  eval/run_document_processing_eval.py — ingestion pipeline quality
  eval/run_analysis_quality_eval.py    — analysis output quality
  eval/run_llm_judge_eval.py           — LLM-judged content plausibility

Usage:
    PYTHONPATH=. python eval/run_context_management_eval.py
    PYTHONPATH=. python eval/run_context_management_eval.py --json-only --no-judge

Exit codes:
    0 — all (non-skipped) dimensions pass their threshold
    1 — one or more dimensions fail
    2 — critical error (fixture build / import failure)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load the sibling fixtures module by file path rather than `from eval...`. Under
# pytest, tests/ is prepended to sys.path and tests/eval/ (the golden-fixtures
# package) shadows the top-level eval/ package, so `import eval.<x>` resolves to
# the wrong package. Importing by path sidesteps the collision in both contexts.
import importlib.util as _ilu  # noqa: E402


def _load_fixtures_module() -> Any:
    path = Path(__file__).resolve().parent / "_fixtures_context_management.py"
    spec = _ilu.spec_from_file_location("cm_fixtures", path)
    module = _ilu.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["cm_fixtures"] = module
    spec.loader.exec_module(module)
    return module


_FIX = _load_fixtures_module()
ensure_fixtures = _FIX.ensure_fixtures
FIXTURES_DIR = _FIX.FIXTURES_DIR
PRESLIM_TOKEN_BAND = _FIX.PRESLIM_TOKEN_BAND

CRITERIA_PATH = ROOT / "eval" / "context_management_criteria.json"
DEFAULT_OUTPUT_MD = ROOT / "eval" / "context_management_report.md"
DEFAULT_OUTPUT_JSON = ROOT / "eval" / "context_management_scores.json"

# Fields whose presence in a slimmed initiative/lever means UI-only enrichment
# leaked into the LLM payload.
_FORBIDDEN_SYNTHESIS_KEYS = frozenset({
    "execution_playbook", "change_management", "kpis", "owner", "provenance",
    "affected_vendors", "contract_levers", "condition_precedents",
    "required_data_fields", "bulk_field",
})


# ---------------------------------------------------------------------------
# Data models (mirrors run_document_processing_eval.py)
# ---------------------------------------------------------------------------

@dataclass
class DimensionResult:
    dimension_id: str
    name: str
    domain: str
    weight: float
    threshold_pass: float
    raw_score: float
    passed: bool
    evidence: Dict[str, Any]
    finding_summary: str
    finding_detail: str
    remediation: str
    skipped: bool = False

    @property
    def gap(self) -> float:
        return max(0.0, self.threshold_pass - self.raw_score)


@dataclass
class DomainResult:
    domain_name: str
    domain_display: str
    domain_weight: float
    dimension_results: List[DimensionResult]
    domain_score: float
    passed: bool


@dataclass
class EvalReport:
    platform_version: str
    eval_date: str
    overall_score: float
    domain_results: List[DomainResult]
    top_gaps: List[Dict]
    remediation_roadmap: List[Dict]
    passed: bool
    fixture_count: int
    judge_active: bool


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def _json_chars(obj: Any) -> int:
    try:
        return len(json.dumps(obj, default=str))
    except Exception:  # noqa: BLE001
        return 0


def _regex_token_count(payload: Any) -> int:
    """Deterministic reference tokenizer for chars÷4 calibration checks."""
    try:
        text = json.dumps(payload, default=str)
    except Exception:  # noqa: BLE001
        text = str(payload)
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def _scan_forbidden_keys(node: Any, found: set) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _FORBIDDEN_SYNTHESIS_KEYS:
                found.add(k)
            _scan_forbidden_keys(v, found)
    elif isinstance(node, list):
        for item in node:
            _scan_forbidden_keys(item, found)


def _judge_available() -> bool:
    # Anthropic specifically — CM-13 uses messages.count_tokens, a Claude-side API.
    from app.config import ANTHROPIC_ENABLED

    return bool(ANTHROPIC_ENABLED) and not os.getenv("PYTEST_CURRENT_TEST")


# ---------------------------------------------------------------------------
# Domain A — synthesis budget
# ---------------------------------------------------------------------------

def score_cm01_slimming(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    """Slimming efficiency, whitelist integrity, skip-skill removal, caps, idempotency."""
    from app.opar.claude_client import _SKIP_SKILLS, _slim_skill_outputs, _slim_sme_critique

    raw_payload = fx["full_payload"]
    slimmed = _slim_skill_outputs(raw_payload)
    score = 0.0
    ev: Dict[str, Any] = {}

    # 2.0 — size reduction: full credit at ratio ≤ 0.40, zero at ≥ 0.80.
    raw_chars = _json_chars(raw_payload)
    slim_chars = _json_chars(slimmed)
    ratio = slim_chars / raw_chars if raw_chars else 1.0
    size_pts = 2.0 * _clamp01((0.80 - ratio) / 0.40)
    score += size_pts
    ev["size_reduction"] = {"raw_chars": raw_chars, "slim_chars": slim_chars,
                            "ratio": round(ratio, 3), "points": round(size_pts, 2)}

    # 2.0 — no forbidden UI-only keys leak into initiatives/levers/critiques.
    found: set = set()
    _scan_forbidden_keys(slimmed.get("savings-modeler", {}), found)
    _scan_forbidden_keys(slimmed.get("root-cause-analyzer", {}), found)
    _scan_forbidden_keys(slimmed.get("sme-critique", {}), found)
    score += 2.0 if not found else 0.0
    ev["forbidden_keys_leaked"] = sorted(found)

    # 2.0 — _SKIP_SKILLS fully absent from the slimmed payload.
    leaked_skips = sorted(s for s in _SKIP_SKILLS if s in slimmed)
    score += 2.0 if not leaked_skips else 0.0
    ev["skip_skills_leaked"] = leaked_skips

    # 2.0 — top-N caps hold.
    caps = {
        "categories<=8": len(slimmed.get("spend-profiler", {}).get("category_profile", [])) <= 8,
        "initiatives<=12": len(slimmed.get("savings-modeler", {}).get("initiatives", [])) <= 12,
        "sm_levers<=8": len(slimmed.get("savings-modeler", {}).get("eligible_levers", [])) <= 8,
        "rc_levers<=8": len(slimmed.get("root-cause-analyzer", {}).get("eligible_levers_summary", [])) <= 8,
        "period_trends<=6": len(slimmed.get("temporal-analyzer", {}).get("period_trends", [])) <= 6,
        "pt_opps<=5": len(slimmed.get("payment-terms-optimizer", {}).get("opportunities", [])) <= 5,
        "critiques<=5": len(slimmed.get("sme-critique", {}).get("initiative_critiques", [])) <= 5,
        "top_suppliers<=2": all(
            len(c.get("top_suppliers", [])) <= 2
            for c in slimmed.get("spend-profiler", {}).get("category_profile", [])
        ),
    }
    score += 2.0 * (sum(caps.values()) / len(caps))
    ev["top_n_caps"] = caps

    # 2.0 — idempotency: re-slimming is a no-op, and the dedicated
    # sme_critique_data view resolves identically from raw or slimmed input.
    idem = _slim_skill_outputs(slimmed) == slimmed
    sme_stable = _slim_sme_critique(raw_payload["sme-critique"]) == _slim_sme_critique(slimmed["sme-critique"])
    score += 1.0 if idem else 0.0
    score += 1.0 if sme_stable else 0.0
    ev["idempotent"] = idem
    ev["sme_view_stable"] = sme_stable
    return round(score, 2), ev


def score_cm02_budget_gate(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    """Over-budget degrades (drop largest) instead of skipping; irreducible hard-skips."""
    from app.opar.models import ObserveContext
    from app.opar.reflect_advisory import _drop_largest_to_budget, generate_llm_advisory_sections

    score = 0.0
    ev: Dict[str, Any] = {}

    # (a+b) over-budget payload degrades: synthesizer still called, biggest skill gone.
    captured: Dict[str, Any] = {}

    def fake_synthesize(user_message, **kwargs):
        captured["skill_outputs"] = kwargs.get("skill_outputs")
        return None, None

    ctx = ObserveContext(user_message="calculate value at the table", intent_class="value_bridge")
    validated = {
        "spend-profiler": {"category_profile": [], "total_spend": 1_000_000},
        "internal-benchmarker": {"blob": "x" * 400_000},  # ~100k tokens alone
    }
    with patch("app.opar.reflect_advisory.ANTHROPIC_ENABLED", True), patch(
        "app.opar.reflect_advisory._iter_analysis_synthesizers", return_value=[fake_synthesize]
    ):
        _adv, _think, skip = generate_llm_advisory_sections(ctx, {}, validated)
    degraded_ok = skip != "token_budget_exceeded" and "skill_outputs" in captured
    score += 3.0 if degraded_ok else 0.0
    kept = captured.get("skill_outputs") or {}
    drop_ok = "internal-benchmarker" not in kept and "spend-profiler" in kept
    score += 2.0 if drop_ok else 0.0
    ev["degrade_over_budget"] = {"skip_reason": skip, "synthesizer_called": "skill_outputs" in captured,
                                 "kept_skills": sorted(kept)}

    # (c) drop-largest ordering + accurate dropped names (direct calls).
    outputs = {"big": {"blob": "x" * 40_000}, "medium": {"blob": "y" * 8_000}, "small": {"value": 1}}
    kept1, dropped1 = _drop_largest_to_budget(outputs, overshoot_tokens=5_000)
    kept2, dropped2 = _drop_largest_to_budget(outputs, overshoot_tokens=11_000)
    order1 = dropped1 == ["big"] and set(kept1) == {"medium", "small"}
    order2 = dropped2 == ["big", "medium"] and set(kept2) == {"small"}
    score += 1.0 if order1 else 0.0
    score += 1.0 if order2 else 0.0
    ev["drop_largest_ordering"] = {"overshoot_5k": dropped1, "overshoot_11k": dropped2}

    # (d) irreducible payload hard-skips and never calls the synthesizer.
    calls: List[str] = []

    def fake_synthesize2(user_message, **kwargs):
        calls.append(user_message)
        return None, None

    ctx2 = ObserveContext(user_message="x" * 400_000, intent_class="value_bridge")
    validated2 = {"spend-profiler": {"category_profile": [], "total_spend": 1_000_000}}
    with patch("app.opar.reflect_advisory.ANTHROPIC_ENABLED", True), patch(
        "app.opar.reflect_advisory._iter_analysis_synthesizers", return_value=[fake_synthesize2]
    ):
        _adv2, _t2, skip2 = generate_llm_advisory_sections(ctx2, {}, validated2)
    hard_skip_ok = skip2 == "token_budget_exceeded" and not calls
    score += 3.0 if hard_skip_ok else 0.0
    ev["irreducible_hard_skip"] = {"skip_reason": skip2, "synthesizer_calls": len(calls)}
    return round(score, 2), ev


def score_cm03_core_survival(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    """Honest-gap probe: degradation should drop non-core skills before core ones."""
    from app.opar.reflect_advisory import _CORE_SYNTHESIS_SKILLS, _drop_largest_to_budget

    def blob(tokens: int) -> Dict[str, Any]:
        return {"blob": "x" * (tokens * 4)}

    # In each scenario the largest skill is core but dropping the second-largest
    # (non-core) alone would reclaim the overshoot.
    scenarios = [
        {"name": "savings_modeler_vs_internal_benchmarker",
         "outputs": {"savings-modeler": blob(12_000), "internal-benchmarker": blob(10_000),
                     "bva-analyzer": blob(2_000)},
         "overshoot": 8_000},
        {"name": "spend_profiler_vs_peer_benchmarker",
         "outputs": {"spend-profiler": blob(9_000), "peer-benchmarker": blob(8_000),
                     "temporal-analyzer": blob(2_000)},
         "overshoot": 7_000},
        {"name": "value_bridge_vs_temporal",
         "outputs": {"value-bridge-calculator": blob(11_000), "temporal-analyzer": blob(10_000),
                     "vendor-master-builder": blob(3_000)},
         "overshoot": 9_000},
    ]
    score = 0.0
    ev: Dict[str, Any] = {"core_protection": [], "core_skills": sorted(_CORE_SYNTHESIS_SKILLS)}
    protected = 0
    completeness_ok = True
    for sc in scenarios:
        kept, dropped = _drop_largest_to_budget(dict(sc["outputs"]), sc["overshoot"])
        core_dropped = sorted(set(dropped) & _CORE_SYNTHESIS_SKILLS)
        reclaimed_ok = sum(len(json.dumps(sc["outputs"][s], default=str)) // 4 for s in dropped) >= sc["overshoot"]
        ok = not core_dropped and reclaimed_ok
        protected += 1 if ok else 0
        completeness_ok &= set(sc["outputs"]) - set(kept) == set(dropped)
        ev["core_protection"].append({"scenario": sc["name"], "dropped": dropped,
                                      "core_dropped": core_dropped, "protected": ok})
    score += 5.0 * (protected / len(scenarios))

    # 3.0 — when only core skills exist, the drop must still leave a non-empty,
    # budget-respecting set (core sacrifice is acceptable only here).
    all_core = {"spend-profiler": blob(10_000), "savings-modeler": blob(8_000), "sme-critique": blob(6_000)}
    kept, dropped = _drop_largest_to_budget(dict(all_core), overshoot_tokens=12_000)
    reclaimed = sum(len(json.dumps(all_core[s], default=str)) // 4 for s in dropped)
    must_drop_ok = bool(kept) and reclaimed >= 12_000
    completeness_ok &= set(all_core) - set(kept) == set(dropped)
    score += 3.0 if must_drop_ok else 0.0
    ev["must_drop_core_case"] = {"kept": sorted(kept), "dropped": dropped, "viable": must_drop_ok}

    # 2.0 — dropped list reported completely in every scenario.
    score += 2.0 if completeness_ok else 0.0
    ev["dropped_list_complete"] = completeness_ok
    return round(score, 2), ev


def score_cm04_estimate_completeness(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    """Honest-gap probe: gate estimate vs the prompt actually sent + estimator robustness."""
    from app.opar import claude_client
    from app.opar.models import ObserveContext
    from app.opar.reflect_advisory import _estimate_tokens, generate_llm_advisory_sections

    score = 0.0
    ev: Dict[str, Any] = {}

    # --- Completeness (6.0): capture both the gate's logged estimate and the
    # real (system + user) prompt the synthesizer would send.
    captured: Dict[str, Any] = {}

    def fake_call_claude(system, user_content, max_tokens=None, *args, **kwargs):
        if "user" not in captured:
            captured["system"] = system
            captured["user"] = user_content
        return "{}"

    class _BudgetLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if isinstance(record.msg, str) and record.msg.startswith("llm_token_budget estimated_tokens"):
                captured["estimated"] = int(record.args[0])

    full = fx["full_payload"]
    validated = {
        "spend-profiler": full["spend-profiler"],
        "savings-modeler": full["savings-modeler"],
        "peer-benchmarker": full["peer-benchmarker"],
        "sme-critique": full["sme-critique"],
    }
    ctx = ObserveContext(
        user_message="give me a benchmark readout on IT spend",
        intent_class="benchmark",
        model_manifest={"business_model": _FIX._fill("B2B services with managed infrastructure delivery.", 4_000)},
        deep_research_summary=_FIX._fill(
            "Deep research: industry rate cards, peer disclosures, and regulatory context for the sector.", 16_000
        ),
    )
    manifest = {"company_name": "Aranya Digital", "industry": "it_services",
                "annual_revenue": 4_000_000_000, "currency": "INR"}

    opex_logger = logging.getLogger("opex")
    handler = _BudgetLogHandler(level=logging.INFO)
    prior_level = opex_logger.level
    opex_logger.addHandler(handler)
    if opex_logger.level > logging.INFO or opex_logger.level == logging.NOTSET:
        opex_logger.setLevel(logging.INFO)
    try:
        with patch("app.opar.reflect_advisory.ANTHROPIC_ENABLED", True), patch(
            "app.opar.reflect_advisory._iter_analysis_synthesizers",
            return_value=[claude_client.synthesize_analysis_claude],
        ), patch("app.opar.claude_client.ANTHROPIC_ENABLED", True), patch(
            "app.opar.claude_client.GEMINI_ENABLED", False
        ), patch("app.opar.claude_client._call_claude", fake_call_claude):
            generate_llm_advisory_sections(ctx, manifest, validated)
    finally:
        opex_logger.removeHandler(handler)
        opex_logger.setLevel(prior_level)

    estimated = captured.get("estimated")
    if estimated and captured.get("user"):
        actual = (len(captured["system"]) + len(captured["user"])) // 4
        overhead = (actual - estimated) / estimated
        # Full 4.0 at ≤10% unbudgeted overhead, zero at ≥50%.
        completeness_pts = 4.0 * _clamp01((0.50 - overhead) / 0.40)
        score += completeness_pts
        ev["estimate_vs_actual"] = {
            "gate_estimated_tokens": estimated,
            "actual_prompt_tokens_chars4": actual,
            "unbudgeted_overhead_pct": round(overhead * 100, 1),
            "points": round(completeness_pts, 2),
            "note": "overhead = system prompt + model_manifest + deep_research_context "
                    "+ sme_critique_data + strict/advisory hints, none of which the gate estimates",
        }
    else:
        ev["estimate_vs_actual"] = {"error": "could not capture estimate or prompt", "captured": sorted(captured)}

    # --- chars÷4 vs regex-tokenizer reference on 3 golden payloads (2.0).
    calibration_cases = [
        {"name": "full_payload", "payload": fx["full_payload"]},
        {"name": "small_dense", "payload": {"a": "x" * 400}},
        {"name": "large_dense", "payload": {"a": "x" * 40_000}},
    ]
    cal_hits = 0
    cal_detail: Dict[str, Any] = {}
    for case in calibration_cases:
        est = _estimate_tokens(case["payload"])
        ref = _regex_token_count(case["payload"])
        drift = abs(est - ref) / ref if ref else 1.0
        within = drift <= 0.15
        cal_hits += 1 if within else 0
        cal_detail[case["name"]] = {
            "chars4_estimate": est,
            "regex_reference": ref,
            "drift_pct": round(drift * 100, 1),
            "within_15pct": within,
        }
    cal_pts = 2.0 * (cal_hits / len(calibration_cases))
    score += cal_pts
    ev["chars4_vs_regex"] = {"cases": cal_detail, "hits": cal_hits, "points": round(cal_pts, 2)}

    # --- Estimator robustness (4.0).
    small = _estimate_tokens({"a": "x" * 400})
    large = _estimate_tokens({"a": "x" * 40_000})
    monotonic = 0 < small < large
    score += 1.0 if monotonic else 0.0

    circular: Dict[str, Any] = {}
    circular["self"] = circular
    circ_est = _estimate_tokens(circular)
    # A conservative estimator must not report an unserializable payload as
    # zero tokens — that silently passes the budget gate.
    conservative = circ_est > 0
    score += 2.0 if conservative else 0.0

    nonzero = _estimate_tokens(fx["full_payload"]) > 0
    score += 1.0 if nonzero else 0.0
    ev["estimator_robustness"] = {
        "monotonic": monotonic,
        "circular_payload_estimate": circ_est,
        "circular_conservative": conservative,
        "real_payload_nonzero": nonzero,
    }
    return round(score, 2), ev


def score_cm05_end_to_end_chain(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    """Oversized 26-skill payload through slim → relevance-filter → budget gate."""
    from app.opar.models import ObserveContext
    from app.opar.reflect_advisory import _LLM_TOKEN_LIMIT, _estimate_tokens, generate_llm_advisory_sections

    score = 0.0
    ev: Dict[str, Any] = {}
    full = fx["full_payload"]
    preslim = _estimate_tokens(full)
    ev["preslim_estimated_tokens"] = preslim
    ev["limit"] = _LLM_TOKEN_LIMIT
    lo, hi = PRESLIM_TOKEN_BAND
    if not (lo <= preslim and preslim > _LLM_TOKEN_LIMIT):
        return 0.0, {**ev, "error": f"fixture out of band [{lo},{hi}] or under limit — fixture bug, not an app finding"}

    captured: Dict[str, Any] = {}

    def fake_synthesize(user_message, **kwargs):
        captured["skill_outputs"] = kwargs.get("skill_outputs")
        captured["available_analyses"] = kwargs.get("available_analyses")
        captured["docs"] = kwargs.get("docs_text")
        return None, None

    ctx = ObserveContext(
        user_message="benchmark my IT spend vs peers",
        intent_class="benchmark",
        query_capabilities=["benchmarking"],
    )
    with patch("app.opar.reflect_advisory.ANTHROPIC_ENABLED", True), patch(
        "app.opar.reflect_advisory._iter_analysis_synthesizers", return_value=[fake_synthesize]
    ):
        _adv, _think, skip = generate_llm_advisory_sections(ctx, {}, dict(full))

    # 4.0 — no hard skip; synthesizer called.
    called = "skill_outputs" in captured
    no_hard_skip = skip != "token_budget_exceeded" and called
    score += 4.0 if no_hard_skip else 0.0
    ev["skip_reason"] = skip
    ev["synthesizer_called"] = called

    kept = captured.get("skill_outputs") or {}
    aa = captured.get("available_analyses") or []

    # 3.0 — what reached the synthesizer fits the budget.
    sent_estimate = _estimate_tokens({
        "user_message": ctx.user_message,
        "skill_outputs": kept,
        "available_analyses": aa,
    })
    under_budget = called and sent_estimate <= _LLM_TOKEN_LIMIT
    score += 3.0 if under_budget else 0.0
    ev["sent_estimated_tokens"] = sent_estimate

    # 2.0 — excluded skills surfaced in available_analyses, disjoint from selected.
    aa_skills = {e.get("skill") for e in aa if isinstance(e, dict)}
    manifest_ok = bool(aa_skills) and not (aa_skills & set(kept))
    score += 2.0 if manifest_ok else 0.0
    ev["available_analyses_count"] = len(aa)
    ev["manifest_disjoint"] = not (aa_skills & set(kept))

    # 1.0 — core skill present in what was sent.
    core_present = "spend-profiler" in kept
    score += 1.0 if core_present else 0.0
    ev["kept_skills"] = sorted(kept)
    return round(score, 2), ev


def score_cm13_token_calibration(fx: Dict[str, Any], judge_active: bool) -> Tuple[float, Dict, bool]:
    """chars/4 estimate vs the real Anthropic count_tokens API. Skipped offline."""
    if not judge_active:
        return 0.0, {"note": "skipped — needs ANTHROPIC_API_KEY (count_tokens is Claude-side)"}, True
    try:
        import anthropic

        from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
        from app.opar.claude_client import _slim_skill_outputs
        from app.opar.reflect_advisory import _estimate_tokens

        slimmed = _slim_skill_outputs(fx["full_payload"])
        user_prompt = (
            "Synthesize recommendations from this JSON context:\n"
            f"{json.dumps(slimmed, ensure_ascii=False)}"
        )
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        real = client.messages.count_tokens(
            model=ANTHROPIC_MODEL,
            messages=[{"role": "user", "content": user_prompt}],
        ).input_tokens
        est = _estimate_tokens(slimmed)
        drift = abs(real - est) / real if real else 1.0
        # Full marks at ≤10% drift, zero at ≥50%.
        score = 10.0 * _clamp01((0.50 - drift) / 0.40)
        ev = {
            "real_input_tokens": real,
            "chars4_estimate": est,
            "drift_pct": round(drift * 100, 1),
            "direction": "underestimates" if est < real else "overestimates",
            "model": ANTHROPIC_MODEL,
        }
        return round(score, 2), ev, False
    except Exception as exc:  # noqa: BLE001
        return 0.0, {"note": f"skipped — count_tokens unavailable ({type(exc).__name__}: {exc})"}, True


# ---------------------------------------------------------------------------
# Domain B — relevance filtering
# ---------------------------------------------------------------------------

def score_cm06_capability_detection(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    from app.opar.observe import _detect_query_capabilities

    per: Dict[str, Any] = {}
    scores: List[float] = []
    for case in fx["relevance"]["detection_cases"]:
        detected = set(_detect_query_capabilities(case["query"]))
        expected = set(case["expected"])
        if not detected and not expected:
            jaccard = 1.0
        else:
            jaccard = len(detected & expected) / len(detected | expected)
        scores.append(jaccard * 10.0)
        per[case["query"]] = {"detected": sorted(detected), "expected": sorted(expected),
                              "jaccard": round(jaccard, 2)}
    return round(_avg(scores), 2), {"per_query": per, "cases": len(scores)}


def _selection_for_case(case: Dict[str, Any], validated: Dict[str, Any]):
    from app.opar.models import ObserveContext
    from app.opar.reflect_advisory import select_relevant_outputs

    ctx = ObserveContext(
        user_message=case["query"],
        intent_class=case["intent_class"],
        query_capabilities=case.get("capabilities") or [],
        explicit_category=case.get("explicit_category"),
    )
    return select_relevant_outputs(ctx, validated, agent_path=case.get("agent_path", False))


def score_cm07_selection_pr(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    validated = fx["relevance"]["validated_outputs"]
    per: Dict[str, Any] = {}
    scores: List[float] = []
    for case in fx["relevance"]["selection_cases"]:
        selected, _excluded = _selection_for_case(case, validated)
        got = set(selected)
        want = set(case["expected_selected"])
        precision = len(got & want) / len(got) if got else 0.0
        recall = len(got & want) / len(want) if want else 0.0
        sc = (precision + recall) / 2 * 10.0
        scores.append(sc)
        per[case["name"]] = {"selected": sorted(got), "expected": sorted(want),
                             "precision": round(precision, 2), "recall": round(recall, 2),
                             "score": round(sc, 1)}
    return round(_avg(scores), 2), {"per_case": per}


def score_cm08_manifest_bypass(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    from app.opar.claude_client import _SKIP_SKILLS
    from app.opar.reflect_advisory import _manifest_headline

    validated = fx["relevance"]["validated_outputs"]
    score = 0.0
    ev: Dict[str, Any] = {}

    # 4.0 — set identity + disjointness on every filtered case.
    identity_ok = True
    per_identity: Dict[str, Any] = {}
    for case in fx["relevance"]["selection_cases"]:
        selected, excluded = _selection_for_case(case, validated)
        excluded_skills = {e["skill"] for e in excluded}
        union = set(selected) | excluded_skills | (set(validated) & _SKIP_SKILLS)
        ok = union == set(validated) and not (set(selected) & excluded_skills)
        identity_ok &= ok
        per_identity[case["name"]] = ok
    score += 4.0 if identity_ok else 0.0
    ev["set_identity"] = per_identity

    # 2.0 — headlines non-empty everywhere; count-bearing skills embed real counts.
    _selected, excluded = _selection_for_case(fx["relevance"]["selection_cases"][0], validated)
    nonempty = all((e.get("headline") or "").strip() for e in excluded)
    headline_checks = {}
    headline_ok = nonempty
    for chk in fx["relevance"]["headline_checks"]:
        got = _manifest_headline(chk["skill"], validated[chk["skill"]])
        match = got == chk["expected_headline"]
        headline_ok &= match
        headline_checks[chk["skill"]] = {"got": got, "expected": chk["expected_headline"], "match": match}
    score += 2.0 if headline_ok else 0.0
    ev["headlines"] = {"all_nonempty": nonempty, "count_checks": headline_checks}

    # 4.0 — bypasses (1.0 each): deliverable intents, agent path, no/unknown capabilities,
    # determinism.
    def is_full_passthrough(case: Dict[str, Any]) -> bool:
        selected, excluded = _selection_for_case(case, validated)
        return selected == validated and excluded == []

    base = {"query": "benchmark spend", "capabilities": ["benchmarking"], "explicit_category": None}
    bypasses = {
        "deliverable_intents": (
            is_full_passthrough({**base, "intent_class": "business_case"})
            and is_full_passthrough({**base, "intent_class": "export_business_case"})
        ),
        "agent_path": is_full_passthrough({**base, "intent_class": "benchmark", "agent_path": True}),
        "no_or_unknown_capabilities": (
            is_full_passthrough({**base, "intent_class": "benchmark", "capabilities": []})
            and is_full_passthrough({**base, "intent_class": "benchmark", "capabilities": ["unknown_cap"]})
        ),
    }
    case0 = fx["relevance"]["selection_cases"][0]
    sel_a, exc_a = _selection_for_case(case0, validated)
    sel_b, exc_b = _selection_for_case(case0, validated)
    bypasses["deterministic"] = sel_a == sel_b and exc_a == exc_b
    score += 1.0 * sum(bypasses.values())
    ev["bypasses"] = bypasses
    return round(score, 2), ev


# ---------------------------------------------------------------------------
# Domain C — conversational context
# ---------------------------------------------------------------------------

def _expand_chat_history(spec: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    hist: List[Dict[str, Any]] = []
    h = spec["history"]
    for i in range(h["well_formed_turns"]):
        hist.append({"role": ("user", "assistant")[i % 2],
                     "content": f"t{i} " + "x" * h["turn_char_len"]})
    for entry in h["tail"]:
        kind, label = entry["kind"], entry["label"]
        if kind in ("valid", "valid_long"):
            hist.append({"role": "user", "content": f"{label} " + "y" * entry["content_chars"]})
        elif kind == "missing_role":
            hist.append({"content": f"{label} orphan content"})
        elif kind == "none_content":
            hist.append({"role": "user", "content": None})
        elif kind == "empty_content":
            hist.append({"role": "user", "content": ""})
    return hist, h["expected_window_labels"]


def _chat_base_inputs(spec: Dict[str, Any]):
    """Manifest + skill_outputs sized to probe every slice cap."""
    caps = spec["slice_caps"]
    skill_outputs = {
        "spend-profiler": {
            "total_spend": 100_000_000,
            "category_profile": [
                {"category_id": f"C{i:02d}", "category_name": f"Cat {i}", "spend": 1_000_000 * (20 - i),
                 "top_suppliers": [{"supplier": f"S{i}-{j}", "spend": 100_000} for j in range(3)]}
                for i in range(caps["categories_in"])
            ],
        },
        "payment-terms-optimizer": {
            "opportunities": [{"supplier": f"PT{i}", "annual_cash_value": 100_000 * i}
                              for i in range(caps["pt_opportunities_in"])],
        },
        "savings-modeler": {
            "initiatives": [{"category_name": f"Cat {i}", "lever": f"l{i}"}
                            for i in range(caps["initiatives_in"])],
        },
        "value-bridge-calculator": {
            "value_matrix": [{"category_id": f"C{i:02d}", "lever": f"l{i}"}
                             for i in range(caps["value_matrix_in"])],
            "confidence_bands": {"base": 10.0},
        },
        "root-cause-analyzer": {
            "root_cause_findings": [{"finding": f"f{i}"} for i in range(caps["root_findings_in"])],
        },
        "contract-lifecycle-manager": {
            "renewal_alerts": [{"supplier": f"R{i}"} for i in range(caps["renewals_in"])],
        },
        "document-contextualizer": {
            "context_summary": "s" * caps["context_summary_chars_in"],
            "constraints": [f"constraint {i}" for i in range(12)],
        },
        "sme-critique": {"portfolio_probes": [{"question": f"q{i}"} for i in range(8)]},
    }
    manifest = {"company_name": "Aranya", "industry": "it_services", "currency": "INR",
                "probe_answers": [{"answer": f"a{i}"} for i in range(12)]}
    return manifest, skill_outputs


def score_cm09_chat_window(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    from app.opar import chat_synthesis
    from app.opar.models import ObserveContext

    spec = fx["chat_spec"]
    score = 0.0
    ev: Dict[str, Any] = {}
    manifest, skill_outputs = _chat_base_inputs(spec)
    history, expected_labels = _expand_chat_history(spec)
    ctx = ObserveContext(user_message="how much do we spend overall", intent_class="drill_down")

    try:
        context = chat_synthesis.build_chat_context(
            ctx, manifest, skill_outputs, chat_history=history
        )
        no_exception = True
    except Exception as exc:  # noqa: BLE001
        return 0.0, {"error": f"build_chat_context raised {type(exc).__name__}: {exc}"}

    turns = context.get("recent_turns") or []
    labels = [t.get("content", "").split(" ")[0] for t in turns]

    # 2.0 — window ≤ 6 turns, original order preserved.
    window_ok = len(turns) <= 6 and labels == expected_labels
    score += 2.0 if window_ok else 0.0
    ev["window"] = {"turn_count": len(turns), "labels": labels, "expected_labels": expected_labels}

    # 2.0 — every turn content capped at 800 chars.
    content_ok = all(len(t.get("content", "")) <= 800 for t in turns)
    score += 2.0 if content_ok else 0.0
    ev["content_caps"] = {"max_turn_chars": max((len(t.get("content", "")) for t in turns), default=0)}

    # 1.5 — malformed turns skipped silently (no exception, no empty entries).
    malformed_ok = no_exception and all(t.get("role") and t.get("content") for t in turns)
    score += 1.5 if malformed_ok else 0.0
    ev["malformed_turns_skipped"] = malformed_ok

    # 1.5 — slice caps hold across context fields.
    caps = spec["slice_caps"]
    slice_checks = {
        "categories": len(context["spend_data"]["categories"]) <= caps["categories_max"],
        "pt_opportunities": len(context["spend_data"]["payment_terms_opportunities"]) <= caps["pt_opportunities_max"],
        "initiatives": len(context["modeled_initiatives"]) <= caps["initiatives_max"],
        "value_matrix": len(context["value_matrix_rows"]) <= caps["value_matrix_max"],
        "root_findings": len(context["root_cause_findings"]) <= caps["root_findings_max"],
        "renewals": len(context["contract_renewals"]) <= caps["renewals_max"],
        "context_summary": len(context["document_context"].get("context_summary", "")) <= caps["context_summary_max"],
    }
    score += 1.5 * (sum(slice_checks.values()) / len(slice_checks))
    ev["slice_caps"] = slice_checks

    # 1.5 — non-dict skill outputs never crash and yield empty slices.
    garbage_outputs = {"spend-profiler": "garbage", "savings-modeler": None,
                       "value-bridge-calculator": 42, "sme-critique": ["x"],
                       "payment-terms-optimizer": "g", "root-cause-analyzer": 3.14,
                       "document-contextualizer": "g", "contract-lifecycle-manager": []}
    try:
        g = chat_synthesis.build_chat_context(ctx, {}, garbage_outputs, chat_history=None)
        garbage_ok = (g["spend_data"]["categories"] == [] and g["modeled_initiatives"] == []
                      and g["root_cause_findings"] == [])
    except Exception as exc:  # noqa: BLE001
        garbage_ok = False
        ev["garbage_error"] = f"{type(exc).__name__}: {exc}"
    score += 1.5 if garbage_ok else 0.0
    ev["non_dict_outputs_safe"] = garbage_ok

    # 1.5 — document-excerpt limit follows the question (contract → 4, default → 2).
    limits: List[int] = []

    def capture_fetch(engagement_id, query, limit=2):
        limits.append(limit)
        return []

    ctx_doc = ObserveContext(user_message="what do our contracts say", intent_class="drill_down",
                             engagement_id="e-doc")
    ctx_plain = ObserveContext(user_message="total spend please", intent_class="drill_down",
                               engagement_id="e-doc")
    with patch("app.opar.chat_synthesis._fetch_document_excerpts", capture_fetch):
        chat_synthesis.build_chat_context(ctx_doc, {}, skill_outputs, chat_history=None)
        chat_synthesis.build_chat_context(ctx_plain, {}, skill_outputs, chat_history=None)
    doc_limit_ok = limits == [4, 2]
    score += 1.5 if doc_limit_ok else 0.0
    ev["doc_excerpt_limits"] = limits
    return round(score, 2), ev


def score_cm10_chat_boundedness(fx: Dict[str, Any]) -> Tuple[float, Dict]:
    """Honest-gap probe: per-field contribution caps under oversized inputs."""
    from app.opar import chat_synthesis
    from app.opar.models import ObserveContext

    spec = fx["chat_spec"]["boundedness"]
    fat = "v" * spec["fat_chars"]
    many = spec["many_items"]
    bound = spec["bounded_contribution_chars"]
    ctx = ObserveContext(user_message="summarize our spend", intent_class="drill_down")

    def contribution(context: Dict[str, Any], *path: str) -> int:
        node: Any = context
        for p in path:
            node = node.get(p) if isinstance(node, dict) else None
        return _json_chars(node) if node is not None else 0

    def build(manifest=None, outputs=None, history=None):
        with patch("app.opar.chat_synthesis._fetch_document_excerpts", lambda *a, **k: []):
            return chat_synthesis.build_chat_context(ctx, manifest or {}, outputs or {}, chat_history=history)

    per: Dict[str, Any] = {}
    credits: List[float] = []

    def probe(field: str, many_probe, fat_probe) -> None:
        """credit 1.0 both probes bounded, 0.5 rows capped but fat content leaks, 0 both leak."""
        results = {}
        if many_probe is not None:
            results["many_items_bounded"] = many_probe() <= bound
        if fat_probe is not None:
            results["fat_content_bounded"] = fat_probe() <= bound
        vals = list(results.values())
        credit = sum(vals) / len(vals) if vals else 0.0
        credits.append(credit)
        per[field] = {**results, "credit": credit}

    probe("recent_turns",
          lambda: contribution(build(history=[{"role": "user", "content": f"t{i} x"} for i in range(many)]),
                               "recent_turns"),
          lambda: contribution(build(history=[{"role": "user", "content": fat}] * 6), "recent_turns"))

    cat_rows = [{"category_id": f"C{i}", "category_name": f"Cat {i}", "spend": 100.0} for i in range(many)]
    fat_cat = [{"category_id": "C0", "category_name": fat, "spend": 100.0}]
    probe("categories",
          lambda: contribution(build(outputs={"spend-profiler": {"category_profile": cat_rows, "total_spend": 1}}),
                               "spend_data", "categories"),
          lambda: contribution(build(outputs={"spend-profiler": {"category_profile": fat_cat, "total_spend": 1}}),
                               "spend_data", "categories"))

    pt_rows = [{"supplier": f"S{i}", "annual_cash_value": i} for i in range(many)]
    fat_pt = [{"supplier": "S0", "annual_cash_value": 1, "note": fat}]
    probe("payment_terms_opportunities",
          lambda: contribution(build(outputs={"payment-terms-optimizer": {"opportunities": pt_rows}}),
                               "spend_data", "payment_terms_opportunities"),
          lambda: contribution(build(outputs={"payment-terms-optimizer": {"opportunities": fat_pt}}),
                               "spend_data", "payment_terms_opportunities"))

    many_constraints = {"document-contextualizer": {"context_summary": "s",
                                                    "constraints": [f"c{i}" for i in range(many)]}}
    fat_doc = {"document-contextualizer": {"context_summary": fat, "constraints": [fat]}}
    probe("document_context",
          lambda: contribution(build(outputs=many_constraints), "document_context"),
          lambda: contribution(build(outputs=fat_doc), "document_context"))

    probe("deep_research_summary", None,
          lambda: contribution(build(manifest={"deep_research_summary": fat}), "deep_research_summary"))

    probe("business_override_note", None,
          lambda: contribution(build(manifest={"business_override_note": fat}), "business_override_note"))

    probe("probe_answers",
          lambda: contribution(build(manifest={"probe_answers": [{"answer": f"a{i}"} for i in range(many)]}),
                               "probe_context", "probe_answers"),
          lambda: contribution(build(manifest={"probe_answers": [{"answer": fat}]}),
                               "probe_context", "probe_answers"))

    probe("portfolio_probes",
          lambda: contribution(build(outputs={"sme-critique": {"portfolio_probes":
                                                               [{"question": f"q{i}"} for i in range(many)]}}),
                               "probe_context", "portfolio_probes"),
          lambda: contribution(build(outputs={"sme-critique": {"portfolio_probes": [{"question": fat}]}}),
                               "probe_context", "portfolio_probes"))

    score = 10.0 * sum(credits) / len(credits)
    unbounded = sorted(f for f, r in per.items() if r["credit"] < 1.0)
    return round(score, 2), {"per_field": per, "unbounded_fields": unbounded,
                             "bounded_contribution_chars": bound,
                             "note": "no overall token gate exists in build_chat_context"}


# ---------------------------------------------------------------------------
# Domain D — retrieval context
# ---------------------------------------------------------------------------

def _rag_observations(fx: Dict[str, Any]) -> Dict[str, Any]:
    """Index the corpus into a throwaway engagement; collect everything CM-11/12 need."""
    from app.services.chunking import split_markdown_hierarchical
    from app.services.document_index import LocalDocumentIndex, retrieve_context
    from app.services.engagements_store import (
        add_document_record,
        create_engagement_manifest,
        delete_engagement,
        write_parent_nodes,
    )

    corpus = fx["rag_corpus"]
    cases = fx["rag_cases"]
    obs: Dict[str, Any] = {}
    eid, eid_empty, did = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    idx = LocalDocumentIndex()
    try:
        create_engagement_manifest(engagement_id=eid, company_name="CtxEvalRAG")
        create_engagement_manifest(engagement_id=eid_empty, company_name="CtxEvalEmpty")
        add_document_record(eid, document_id=did, filename="rag_corpus.md",
                            content_type="text/markdown", size_bytes=len(corpus), raw_path="x")
        parents, children = split_markdown_hierarchical(
            corpus, doc_id=did, engagement_id=eid, filename="rag_corpus.md"
        )
        write_parent_nodes(eid, did, parents)
        idx.index_document(eid, did, children)
        obs["parent_count"] = len(parents)
        obs["child_count"] = len(children)

        obs["merge_blocks"] = idx.retrieve(eid, cases["merge_query"])
        obs["broad_blocks_default"] = idx.retrieve(eid, cases["broad_query"])
        obs["broad_blocks_1500"] = idx.retrieve(eid, cases["broad_query"], char_budget=1500)

        with patch("app.services.document_index.get_document_index", return_value=idx):
            obs["formatted_blocks"] = retrieve_context(eid, cases["format_query"])
            obs["empty_engagement_id"] = retrieve_context("", "anything")
            obs["empty_query"] = retrieve_context(eid, "   ")
            obs["no_docs_engagement"] = retrieve_context(eid_empty, "anything")

        retrieval = []
        for pair in cases["pairs"]:
            blocks = idx.retrieve(eid, pair["query"])
            texts = [b.get("text", "") for b in blocks]
            rank = next((i + 1 for i, t in enumerate(texts) if pair["expect_contains"] in t), None)
            retrieval.append({"query": pair["query"], "expect": pair["expect_contains"],
                              "hit": rank is not None, "rank": rank})
        obs["retrieval"] = retrieval
    finally:
        delete_engagement(eid)
        delete_engagement(eid_empty)
    return obs


def score_cm11_rag_packing(fx: Dict[str, Any], rag_obs: Dict[str, Any]) -> Tuple[float, Dict]:
    from app.config import DOC_CONTEXT_CHAR_BUDGET
    from app.opar.claude_client import _truncate_doc_chunks

    score = 0.0
    ev: Dict[str, Any] = {"parents": rag_obs["parent_count"], "children": rag_obs["child_count"]}

    # 2.5 — sibling hits auto-merge into their parent.
    merged = [b for b in rag_obs["merge_blocks"]
              if b.get("level") == "parent" and b.get("merged_children", 0) >= 2]
    score += 2.5 if merged else 0.0
    ev["auto_merge"] = {
        "merged_parent_blocks": len(merged),
        "block_levels": [(b.get("level"), b.get("merged_children")) for b in rag_obs["merge_blocks"]],
    }

    # 2.5 — char-budget invariant (sum ≤ budget, or a single first block) at the
    # default budget and at a custom budget of 1500.
    def budget_ok(blocks: List[Dict[str, Any]], budget: int) -> bool:
        total = sum(len(b.get("text", "")) for b in blocks)
        return len(blocks) <= 1 or total <= budget

    default_ok = budget_ok(rag_obs["broad_blocks_default"], DOC_CONTEXT_CHAR_BUDGET)
    custom_ok = budget_ok(rag_obs["broad_blocks_1500"], 1500)
    score += 1.25 if default_ok else 0.0
    score += 1.25 if custom_ok else 0.0
    ev["char_budget"] = {
        "default_total": sum(len(b.get("text", "")) for b in rag_obs["broad_blocks_default"]),
        "default_budget": DOC_CONTEXT_CHAR_BUDGET, "default_ok": default_ok,
        "custom_total": sum(len(b.get("text", "")) for b in rag_obs["broad_blocks_1500"]),
        "custom_ok": custom_ok,
    }

    # 2.0 — retrieve_context labels every block with [filename › heading].
    fmt = rag_obs["formatted_blocks"]
    fmt_ok = bool(fmt) and all(b.startswith("[rag_corpus.md") and "]" in b.split("\n", 1)[0] for b in fmt)
    score += 2.0 if fmt_ok else 0.0
    ev["formatting"] = {"blocks": len(fmt), "first_label": (fmt[0].split("\n", 1)[0] if fmt else None)}

    # 1.5 — graceful empties: no engagement / blank query / no docs → [] without raising.
    graceful = (rag_obs["empty_engagement_id"] == [] and rag_obs["empty_query"] == []
                and rag_obs["no_docs_engagement"] == [])
    score += 1.5 if graceful else 0.0
    ev["graceful_empties"] = graceful

    # 1.5 — deterministic fallback truncation respects chunk/char caps.
    chunks = _truncate_doc_chunks(["z" * 5_000], max_chunks=2)
    trunc_ok = 0 < len(chunks) <= 2 and all(0 < len(c) <= 1_200 for c in chunks)
    score += 1.5 if trunc_ok else 0.0
    ev["fallback_truncation"] = {"chunks": len(chunks), "max_len": max((len(c) for c in chunks), default=0)}
    return round(score, 2), ev


def score_cm12_retrieval_relevance(fx: Dict[str, Any], rag_obs: Dict[str, Any]) -> Tuple[float, Dict]:
    results = rag_obs["retrieval"]
    if not results:
        return 0.0, {"note": "no retrieval pairs"}
    hits = sum(1 for r in results if r["hit"])
    rr = [1.0 / r["rank"] if r["hit"] else 0.0 for r in results]
    hit_rate = hits / len(results)
    mrr = _avg(rr)
    score = (0.6 * hit_rate + 0.4 * mrr) * 10.0
    return round(score, 2), {"hit_rate": round(hit_rate, 2), "mrr": round(mrr, 2),
                             "hits": hits, "total": len(results), "per_query": results}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

_DIMENSION_META = {
    "CM-01": ("Slimming Efficiency & Whitelist Integrity", "synthesis_budget", 0.22, 7.0),
    "CM-02": ("Budget Gate Degradation", "synthesis_budget", 0.20, 8.0),
    "CM-03": ("Core-Skill Survival Under Degradation", "synthesis_budget", 0.12, 6.0),
    "CM-04": ("Budget Estimate Completeness", "synthesis_budget", 0.16, 6.0),
    "CM-05": ("End-to-End Oversized Chain", "synthesis_budget", 0.20, 8.0),
    "CM-13": ("Token Estimate vs Real API Count", "synthesis_budget", 0.10, 6.0),
    "CM-06": ("Capability Detection Accuracy", "relevance_filtering", 0.30, 7.0),
    "CM-07": ("Relevance Selection Precision/Recall", "relevance_filtering", 0.40, 7.0),
    "CM-08": ("Manifest Completeness & Bypass Correctness", "relevance_filtering", 0.30, 8.0),
    "CM-09": ("Chat Window & Field Caps", "conversational_context", 0.55, 7.0),
    "CM-10": ("Chat Context Boundedness", "conversational_context", 0.45, 7.5),
    "CM-11": ("RAG Packing, Auto-Merge & Fallback", "retrieval_context", 0.55, 7.0),
    "CM-12": ("Retrieval Relevance", "retrieval_context", 0.45, 6.0),
}

_DOMAIN_META = {
    "synthesis_budget": ("Synthesis Token Budget", 0.35),
    "relevance_filtering": ("Relevance Filtering", 0.25),
    "retrieval_context": ("Retrieval Context (RAG)", 0.25),
    "conversational_context": ("Conversational Context", 0.15),
}

_REMEDIATION = {
    "CM-01": "Tighten _slim_skill_outputs / whitelists in app/opar/claude_client.py; keep new "
             "initiative/lever fields out of the payload unless added to _INITIATIVE_SYNTHESIS_KEYS.",
    "CM-02": "Fix the gate in reflect_advisory.generate_llm_advisory_sections: degrade via "
             "_drop_largest_to_budget before skipping; hard-skip only when irreducible.",
    "CM-03": "Make _drop_largest_to_budget (app/opar/reflect_advisory.py) sort non-core skills first "
             "and touch _CORE_SYNTHESIS_SKILLS only when the overshoot is otherwise unreclaimable.",
    "CM-04": "Extend _payload_estimate in generate_llm_advisory_sections to cover model_manifest, "
             "sme_critique_data, deep_research_context and a system-prompt allowance; make "
             "_estimate_tokens conservative (non-zero) on unserializable payloads.",
    "CM-05": "Keep select_relevant_outputs + _slim_skill_outputs + the budget gate composing so a "
             "full 26-skill payload never hard-skips; check whitelist coverage when adding skills.",
    "CM-06": "Extend the token lists in observe._detect_query_capabilities for the missed phrasing.",
    "CM-07": "Update _CAPABILITY_SKILL_MAP / _CORE_SYNTHESIS_SKILLS in reflect_advisory.py so the "
             "capability maps to the skills the synthesis prompt needs.",
    "CM-08": "Preserve the select_relevant_outputs contract: selected ∪ excluded ∪ skip-skills == "
             "validated, full passthrough for deliverables/agent path/unknown capabilities.",
    "CM-09": "Keep build_chat_context windowing (last 6 turns × 800 chars) and per-field slices; "
             "guard non-dict skill outputs.",
    "CM-10": "Add per-field char caps in build_chat_context for deep_research_summary, "
             "business_override_note, probe answer/probe item contents and slimmed-row string fields, "
             "plus an overall _estimate_tokens gate analogous to reflect_advisory's.",
    "CM-11": "Check _auto_merge thresholds/char budget and retrieve_context formatting in "
             "app/services/document_index.py; keep empty-input short-circuits.",
    "CM-12": "Improve retrieval recall — chunk granularity, keyword/embedding scoring, or "
             "auto-merge thresholds in document_index.",
    "CM-13": "Calibrate _CHARS_PER_TOKEN (or switch to the count_tokens API pre-flight) so the "
             "budget gate's estimate tracks real input tokens.",
}


def _aggregate(raw: Dict[str, Tuple], skipped_ids: set) -> Dict[str, DimensionResult]:
    results: Dict[str, DimensionResult] = {}
    for dim_id, (name, domain, weight, threshold) in _DIMENSION_META.items():
        score, evidence = raw[dim_id][0], raw[dim_id][1]
        skipped = dim_id in skipped_ids
        passed = True if skipped else (score >= threshold)
        if skipped:
            summary = "Skipped (no Anthropic provider)"
            detail = "SKIPPED — CM-13 needs ANTHROPIC_API_KEY; not counted in pass/fail."
        else:
            summary = f"{score:.1f}/10 (threshold {threshold})"
            detail = ("PASS" if passed else "FAIL") + f" — {score:.1f} vs {threshold}"
        results[dim_id] = DimensionResult(
            dimension_id=dim_id, name=name, domain=domain, weight=weight,
            threshold_pass=threshold, raw_score=score, passed=passed,
            evidence=evidence, finding_summary=summary, finding_detail=detail,
            remediation=_REMEDIATION.get(dim_id, ""), skipped=skipped,
        )
    return results


def _build_report(dim_results: Dict[str, DimensionResult], fixture_count: int, judge_active: bool) -> EvalReport:
    domain_results: List[DomainResult] = []
    for domain_key, (domain_display, domain_weight) in _DOMAIN_META.items():
        dims = [d for d in dim_results.values() if d.domain == domain_key and not d.skipped]
        if not dims:
            dims = [d for d in dim_results.values() if d.domain == domain_key]
        total_weight = sum(d.weight for d in dims)
        domain_score = sum(d.raw_score * d.weight for d in dims) / total_weight if total_weight else 0.0
        domain_results.append(DomainResult(
            domain_name=domain_key, domain_display=domain_display, domain_weight=domain_weight,
            dimension_results=[d for d in dim_results.values() if d.domain == domain_key],
            domain_score=domain_score,
            passed=all(d.passed for d in dim_results.values() if d.domain == domain_key),
        ))
    overall = sum(dr.domain_score * dr.domain_weight for dr in domain_results)
    top_gaps = sorted(
        [
            {"dimension_id": d.dimension_id, "name": d.name, "score": round(d.raw_score, 2),
             "threshold": d.threshold_pass, "gap": round(d.gap, 2), "remediation": d.remediation}
            for d in dim_results.values() if not d.passed
        ],
        key=lambda x: x["gap"], reverse=True,
    )
    roadmap = [
        {"priority": i + 1, "dimension": g["name"], "gap": g["gap"], "action": g["remediation"]}
        for i, g in enumerate(top_gaps)
    ]
    return EvalReport(
        platform_version="v2.1", eval_date=date.today().isoformat(), overall_score=overall,
        domain_results=domain_results, top_gaps=top_gaps, remediation_roadmap=roadmap,
        passed=all(d.passed for d in dim_results.values()),
        fixture_count=fixture_count, judge_active=judge_active,
    )


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

_KNOWN_GAP_DIMS = ("CM-03", "CM-04", "CM-10")


def _write_json(report: EvalReport, dim_results: Dict[str, DimensionResult], path: Path) -> None:
    payload = {
        "eval_date": report.eval_date,
        "score_type": "structural",
        "scope": (
            "Context-management mechanics: synthesis token budgeting/degradation, payload "
            "slimming, relevance filtering, chat-history windowing, RAG context packing. "
            "Does NOT validate answer quality. CM-03/CM-04/CM-10 are honest-gap probes."
        ),
        "platform_version": report.platform_version,
        "overall_score": round(report.overall_score, 3),
        "passed": report.passed,
        "fixture_count": report.fixture_count,
        "llm_judge_active": report.judge_active,
        "known_gap_dimensions": list(_KNOWN_GAP_DIMS),
        "domains": [
            {
                "name": dr.domain_name, "display": dr.domain_display, "weight": dr.domain_weight,
                "score": round(dr.domain_score, 3), "passed": dr.passed,
                "dimensions": [
                    {"id": d.dimension_id, "name": d.name, "weight": d.weight,
                     "threshold": d.threshold_pass, "score": round(d.raw_score, 3),
                     "passed": d.passed, "skipped": d.skipped, "gap": round(d.gap, 3),
                     "evidence": d.evidence, "remediation": d.remediation}
                    for d in dr.dimension_results
                ],
            }
            for dr in report.domain_results
        ],
        "top_gaps": report.top_gaps,
        "remediation_roadmap": report.remediation_roadmap,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_criteria(path: Path) -> None:
    payload = {
        "dimensions": [
            {"id": dim_id, "name": name, "domain": domain, "weight": weight,
             "threshold": threshold, "scoring": "deterministic rule-based against golden fixtures"
             if dim_id != "CM-13" else "real Anthropic count_tokens vs chars/4 estimate; skipped offline",
             "known_gap_probe": dim_id in _KNOWN_GAP_DIMS}
            for dim_id, (name, domain, weight, threshold) in _DIMENSION_META.items()
        ],
        "domains": [
            {"name": k, "display": disp, "weight": w} for k, (disp, w) in _DOMAIN_META.items()
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markdown(report: EvalReport, path: Path) -> None:
    status = "✅ PASS" if report.passed else "❌ FAIL"
    judge = "active" if report.judge_active else "skipped (no Anthropic provider)"
    lines = [
        "# OpEx Platform — Context Management Quality Eval",
        "",
        f"**Date:** {report.eval_date}  |  **Platform:** {report.platform_version}  |  "
        f"**Overall:** {report.overall_score:.2f}/10  |  **Status:** {status}",
        "",
        f"Golden fixture files: {report.fixture_count}  |  CM-13 token calibration: {judge}  |  "
        f"Retrieval backend: local keyword index (deterministic)",
        "",
        "> Scores the machinery that decides what reaches the LLM — synthesis token budgeting "
        "and degradation, payload slimming, relevance filtering, chat-history windowing, and "
        "document-RAG context packing — against synthetic golden fixtures with all LLM calls mocked.",
        ">",
        "> ⚠️ **SCORE TYPE: STRUCTURAL** — Context-management *mechanics*, not answer quality. "
        "CM-03, CM-04 and CM-10 are honest-gap probes that are expected to FAIL until the "
        "underlying mechanism is improved — a failure there is the finding, not an eval bug. "
        "See `run_llm_judge_eval.py` for answer quality.",
        "",
    ]
    for dr in report.domain_results:
        sd = "PASS" if dr.passed else "FAIL"
        lines += [
            f"## {dr.domain_display} — {dr.domain_score:.1f}/10 [{sd}]",
            "",
            "| ID | Dimension | Weight | Score | Threshold | Status |",
            "|----|-----------|--------|-------|-----------|--------|",
        ]
        for d in dr.dimension_results:
            ds = "⏭️ SKIP" if d.skipped else ("✅" if d.passed else "❌")
            if d.dimension_id in _KNOWN_GAP_DIMS and not d.passed:
                ds = "❌ (known gap)"
            lines.append(
                f"| {d.dimension_id} | {d.name} | {d.weight:.0%} | {d.raw_score:.1f} | {d.threshold_pass} | {ds} |"
            )
        lines.append("")
        for d in dr.dimension_results:
            if not d.passed or d.skipped:
                lines += [
                    f"### {d.dimension_id}: {d.name}",
                    "",
                    f"**Finding:** {d.finding_detail}",
                    "",
                    f"**Evidence:** `{json.dumps(d.evidence, default=str)[:500]}`",
                    "",
                    f"**Remediation:** {d.remediation}",
                    "",
                ]
    if report.remediation_roadmap:
        lines += ["## Improvement Roadmap", ""]
        for item in report.remediation_roadmap:
            lines.append(f"{item['priority']}. **{item['dimension']}** (gap {item['gap']}): {item['action']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_scorers(fx: Dict[str, Any], judge_active: bool) -> Tuple[Dict[str, Tuple], set]:
    """Run every dimension scorer; returns (raw scores, skipped dimension ids)."""
    rag_obs = _rag_observations(fx)
    raw: Dict[str, Tuple] = {
        "CM-01": score_cm01_slimming(fx),
        "CM-02": score_cm02_budget_gate(fx),
        "CM-03": score_cm03_core_survival(fx),
        "CM-04": score_cm04_estimate_completeness(fx),
        "CM-05": score_cm05_end_to_end_chain(fx),
        "CM-06": score_cm06_capability_detection(fx),
        "CM-07": score_cm07_selection_pr(fx),
        "CM-08": score_cm08_manifest_bypass(fx),
        "CM-09": score_cm09_chat_window(fx),
        "CM-10": score_cm10_chat_boundedness(fx),
        "CM-11": score_cm11_rag_packing(fx, rag_obs),
        "CM-12": score_cm12_retrieval_relevance(fx, rag_obs),
    }
    cm13_score, cm13_ev, cm13_skipped = score_cm13_token_calibration(fx, judge_active)
    raw["CM-13"] = (cm13_score, cm13_ev)
    return raw, ({"CM-13"} if cm13_skipped else set())


def main() -> int:
    parser = argparse.ArgumentParser(description="OpEx Context Management Quality Evaluator")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--no-judge", action="store_true",
                        help="Disable the CM-13 count_tokens calibration even if Anthropic is configured.")
    args = parser.parse_args()

    try:
        fx = ensure_fixtures()
    except Exception as exc:  # noqa: BLE001
        print(f"[CRITICAL] Fixture build failed: {exc}", file=sys.stderr)
        return 2

    judge_active = _judge_available() and not args.no_judge
    print(f"Loaded fixtures from {FIXTURES_DIR.relative_to(ROOT)}. "
          f"CM-13 calibration: {'active' if judge_active else 'skipped'}. Running scorers...")

    try:
        raw, skipped_ids = run_all_scorers(fx, judge_active)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"[CRITICAL] Scoring failed: {exc}", file=sys.stderr)
        return 2

    dim_results = _aggregate(raw, skipped_ids)
    report = _build_report(dim_results, fixture_count=6, judge_active=judge_active and "CM-13" not in skipped_ids)

    _write_json(report, dim_results, DEFAULT_OUTPUT_JSON)
    _write_criteria(CRITERIA_PATH)
    if not args.json_only:
        _write_markdown(report, args.output)

    print(f"\n{'=' * 60}")
    print(f"CONTEXT MANAGEMENT EVAL — {report.eval_date}")
    print(f"{'=' * 60}")
    print(f"Overall: {report.overall_score:.2f}/10  ({'PASS' if report.passed else 'FAIL'})")
    for dr in report.domain_results:
        print(f"  {dr.domain_display}: {dr.domain_score:.1f}/10")
        for d in dr.dimension_results:
            mark = "⏭" if d.skipped else ("✓" if d.passed else "✗")
            gap_note = "  [known gap]" if d.dimension_id in _KNOWN_GAP_DIMS and not d.passed else ""
            print(f"    [{mark}] {d.dimension_id}: {d.name:44s} {d.raw_score:.1f}/{d.threshold_pass}{gap_note}")
    if report.top_gaps:
        print("\nTop gaps:")
        for g in report.top_gaps[:4]:
            print(f"  {g['dimension_id']} {g['name']}: {g['score']:.1f} (gap {g['gap']:.1f})")
    if not args.json_only:
        print(f"\nReport: {args.output}\nScores: {DEFAULT_OUTPUT_JSON}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
