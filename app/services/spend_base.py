"""Authoritative spend-base loading, refresh, and consistency for session memory."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.memory import MemoryStore
from app.models import NormalizedSpendLine
from app.opar.pipeline_profile import PipelineProfile, run_profile
from app.services.spend_line_merge import merge_persisted_line_adjustments, prior_lines_from_session
from app.skills.contracts import validate_msme_output, validate_vendor_master_output
from app.skills.dispatch import SkillContext
from app.skills.engine.profiler import spend_profiler

_memory = MemoryStore()

INCREMENTAL_SKILLS = (
    "spend-profiler",
    "internal-benchmarker",
    "vendor-master-builder",
    "msme-compliance-checker",
)


def session_has_line_adjustments(lines: List[NormalizedSpendLine]) -> bool:
    """True when any line carries conflict-resolution or consolidation flags."""
    return any(
        line.consolidation_eliminated
        or line.reconciled_amount is not None
        or bool(line.conflict_resolution)
        for line in lines
    )


def compute_spend_profile(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    return spend_profiler(lines)


def assert_spend_base_consistent(session: Dict[str, Any]) -> None:
    """Raise when skill_outputs spend-profiler total diverges from normalized_spend."""
    lines = prior_lines_from_session(session)
    if not lines:
        return
    profile = (session.get("skill_outputs") or {}).get("spend-profiler") or {}
    if not profile:
        return
    expected = float(compute_spend_profile(lines).get("total_spend", 0.0) or 0.0)
    actual = float(profile.get("total_spend", 0.0) or 0.0)
    if abs(expected - actual) >= 0.01:
        raise AssertionError(
            f"spend base inconsistent: profiler total={actual}, lines total={expected}"
        )


def load_authoritative_spend_lines(
    session_id: str,
) -> Tuple[List[NormalizedSpendLine], List[str], Dict[str, Any]]:
    """Load spend lines with persisted conflict adjustments applied."""
    from app.services.engagement_corpus import load_analysis_corpus

    existing = _memory.get("session", session_id)
    prior_lines = prior_lines_from_session(existing) if existing else []

    corpus_lines, docs_text, _reports, _warnings, manifest = load_analysis_corpus(session_id)

    if prior_lines and session_has_line_adjustments(prior_lines):
        lines = prior_lines
    elif prior_lines:
        lines = merge_persisted_line_adjustments(corpus_lines, prior_lines)
    else:
        lines = corpus_lines

    if existing:
        conflict_actions = existing.get("conflict_user_actions")
        if conflict_actions:
            manifest = dict(manifest)
            manifest["conflict_user_actions"] = conflict_actions

    return lines, docs_text, manifest


def _apply_incremental_outputs(
    updated_state: Dict[str, Any],
    lines: List[NormalizedSpendLine],
    inc_outputs: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    profile = inc_outputs["spend-profiler"]
    validate_vendor_master_output(inc_outputs["vendor-master-builder"])
    validate_msme_output(inc_outputs["msme-compliance-checker"])

    updated_state["normalized_spend"] = [ln.model_dump(mode="json") for ln in lines]
    updated_state.setdefault("skill_outputs", {})
    updated_state["skill_outputs"]["spend-profiler"] = profile
    updated_state["skill_outputs"]["internal-benchmarker"] = inc_outputs["internal-benchmarker"]
    updated_state["skill_outputs"]["vendor-master-builder"] = inc_outputs["vendor-master-builder"]
    updated_state["skill_outputs"]["msme-compliance-checker"] = inc_outputs["msme-compliance-checker"]
    return updated_state


def refresh_spend_base(
    session_id: str,
    *,
    reason: str,
    lines: List[NormalizedSpendLine] | None = None,
    existing: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Recompute spend-profiler + incremental dependents and persist atomically."""
    existing = dict(existing or _memory.get("session", session_id) or {})
    if lines is None:
        lines, _, _ = load_authoritative_spend_lines(session_id)

    prior_total = float(
        existing.get("skill_outputs", {}).get("spend-profiler", {}).get("total_spend", 0.0) or 0.0
    )
    prior_revision = int(existing.get("spend_base_revision") or 0)
    excluded_lines = sum(1 for line in lines if line.consolidation_eliminated)
    excluded_spend = sum(line.reporting_amount for line in lines if line.consolidation_eliminated)

    manifest: Dict[str, Any] = {"session_id": session_id, "spend_base_reason": reason}
    conflict_actions = existing.get("conflict_user_actions")
    if conflict_actions:
        manifest["conflict_user_actions"] = conflict_actions

    inc_ctx = SkillContext(
        lines=lines,
        docs_text=[],
        manifest=manifest,
        prior_results=dict(existing.get("skill_outputs") or {}),
    )
    inc_outputs, _ = run_profile(PipelineProfile.INCREMENTAL, inc_ctx, gating=False)

    updated_state = dict(existing)
    updated_state["session_id"] = session_id
    _apply_incremental_outputs(updated_state, lines, inc_outputs)
    updated_state["spend_base_revision"] = prior_revision + 1
    updated_state["updated_at"] = datetime.now(timezone.utc).isoformat()

    assert_spend_base_consistent(updated_state)
    _memory.put("session", session_id, updated_state)

    profile = inc_outputs["spend-profiler"]
    new_total = float(profile.get("total_spend", 0.0) or 0.0)
    return {
        "prior_total_spend": round(prior_total, 2),
        "new_total_spend": round(new_total, 2),
        "spend_delta": round(new_total - prior_total, 2),
        "lines_excluded": excluded_lines,
        "excluded_spend": round(excluded_spend, 2),
        "spend_base_revision": updated_state["spend_base_revision"],
        "updated_skills": list(INCREMENTAL_SKILLS),
        "initiatives_refresh_required": abs(new_total - prior_total) > 0.01,
        "reason": reason,
    }


def bump_spend_base_revision(session: Dict[str, Any]) -> Dict[str, Any]:
    """Increment revision on a session dict about to be persisted (full pipeline path)."""
    session = dict(session)
    session["spend_base_revision"] = int(session.get("spend_base_revision") or 0) + 1
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    assert_spend_base_consistent(session)
    return session


def repair_spend_base_if_needed(session_id: str, session: Dict[str, Any]) -> Dict[str, Any]:
    """Re-sync spend-profiler from normalized_spend when a partial write caused drift."""
    try:
        assert_spend_base_consistent(session)
        return session
    except AssertionError:
        refresh_spend_base(session_id, reason="consistency_repair", existing=session)
        repaired = _memory.get("session", session_id)
        return dict(repaired) if isinstance(repaired, dict) else session
