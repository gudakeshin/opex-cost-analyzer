"""LLM narrative for custom sensitivity / what-if scenario tables."""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List

from app.config import ANTHROPIC_ENABLED, GEMINI_ENABLED, LLM_CHAT_SYNTHESIS_ENABLED, logger
from app.utils.inr_format import format_money

SENSITIVITY_NARRATIVE_SYSTEM = """You are an FP&A advisor summarizing a what-if sensitivity table for a CFO.

Write 2–4 short paragraphs in markdown:
1. Baseline vs scenario deltas in plain language (3yr savings and NPV after tax).
2. Which scenario is most/least favorable and why (execution rate, timeline, savings delta).
3. One practical recommendation — what to validate before adopting the aggressive case.

Use the currency symbol provided. Quote scenario names exactly. Do not invent numbers not in the table."""


def _deterministic_narrative(
    sensitivity: Dict[str, Any],
    *,
    currency: str,
) -> str:
    baseline = float(sensitivity.get("baseline_mid_savings") or 0.0)
    scenarios: List[Dict[str, Any]] = list(sensitivity.get("scenarios") or [])
    custom = [s for s in scenarios if s.get("custom")]
    focus = custom or scenarios
    if not focus:
        return (
            f"Baseline mid-case 3-year savings are **{format_money(baseline, currency)}**. "
            "No scenario rows were returned — check that value-bridge has run."
        )

    lines = [
        f"Baseline mid-case 3-year savings: **{format_money(baseline, currency)}**.",
        "",
        "**Scenario comparison**",
    ]
    ranked = sorted(focus, key=lambda s: float(s.get("savings_3yr") or 0.0), reverse=True)
    for row in ranked[:6]:
        name = str(row.get("name") or "Scenario")
        sav = float(row.get("savings_3yr") or 0.0)
        npv = float(row.get("npv_aftertax") or 0.0)
        delta = sav - baseline
        sign = "+" if delta >= 0 else ""
        lines.append(
            f"- **{name}**: 3yr savings {format_money(sav, currency)} "
            f"({sign}{format_money(delta, currency)} vs baseline), "
            f"NPV after tax {format_money(npv, currency)}, "
            f"{int(row.get('timeline_months') or 0)} months"
        )

    best = ranked[0]
    worst = ranked[-1]
    lines.extend(
        [
            "",
            f"**Most favorable:** {best.get('name')} — validate execution assumptions before adopting.",
            f"**Most conservative:** {worst.get('name')} — use for board/risk reporting.",
        ]
    )
    return "\n".join(lines)


def _llm_narrative(payload: Dict[str, Any]) -> str | None:
    if os.getenv("PYTEST_CURRENT_TEST"):
        return None
    if not LLM_CHAT_SYNTHESIS_ENABLED:
        return None
    user = json.dumps(payload, ensure_ascii=False)
    try:
        if ANTHROPIC_ENABLED:
            from app.opar.claude_client import _call_anthropic_native

            text = _call_anthropic_native(
                SENSITIVITY_NARRATIVE_SYSTEM,
                user,
                max_tokens=700,
                cache_system=True,
            )
            return (text or "").strip() or None
        if GEMINI_ENABLED:
            from app.opar.gemini_client import call_gemini

            text = call_gemini(
                system=SENSITIVITY_NARRATIVE_SYSTEM,
                user_content=user,
                max_tokens=700,
            )
            return (text or "").strip() or None
    except Exception as exc:
        logger.warning('"sensitivity_narrative_llm_failed error=%s"', exc)
    return None


def synthesize_sensitivity_narrative(
    sensitivity: Dict[str, Any],
    *,
    currency: str = "INR",
    scenario_labels: List[str] | None = None,
    token_callback: Callable[[str], None] | None = None,
) -> str:
    """Narrate sensitivity results; deterministic fallback when LLM unavailable."""
    payload = {
        "currency": currency,
        "baseline_mid_savings": sensitivity.get("baseline_mid_savings"),
        "confidence_bands": sensitivity.get("confidence_bands"),
        "scenarios": [
            {
                "name": s.get("name"),
                "key_assumption": s.get("key_assumption"),
                "savings_3yr": s.get("savings_3yr"),
                "npv_aftertax": s.get("npv_aftertax"),
                "timeline_months": s.get("timeline_months"),
                "execution_rate": s.get("execution_rate"),
                "custom": s.get("custom"),
            }
            for s in (sensitivity.get("scenarios") or [])
            if not scenario_labels or str(s.get("name") or "") in scenario_labels
        ],
    }
    if token_callback and ANTHROPIC_ENABLED and not os.getenv("PYTEST_CURRENT_TEST"):
        try:
            from app.opar.claude_client import _stream_anthropic_native

            text = _stream_anthropic_native(
                SENSITIVITY_NARRATIVE_SYSTEM,
                json.dumps(payload, ensure_ascii=False),
                max_tokens=700,
                cache_system=True,
                on_token=token_callback,
            )
            if text:
                return text
        except Exception as exc:
            logger.warning('"sensitivity_narrative_stream_failed error=%s"', exc)

    llm_text = _llm_narrative(payload)
    if llm_text:
        return llm_text
    return _deterministic_narrative(sensitivity, currency=currency)
