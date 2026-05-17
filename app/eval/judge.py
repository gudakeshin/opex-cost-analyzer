"""Layer 2: LLM-as-judge faithfulness and trace-grounding scorers.

These classes require a live Anthropic API key and are NOT run in standard CI.
Gate with:  pytest.mark.llm_judge  +  RUN_LLM_JUDGE=1 env var.

FaithfulnessJudge  — scores whether a skill's output contains unsupported claims
                     relative to its source input data.

TraceGroundedJudge — scores whether claims in the final response_text can be
                     traced back to raw data in the EvalTrace.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.opar.models import EvalTrace

# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class FaithfulnessResult:
    score: float                          # 0.0 – 1.0 (1 = fully faithful)
    unsupported_claims: List[str] = field(default_factory=list)
    rationale: str = ""
    raw_response: str = ""


@dataclass
class TraceGroundingResult:
    score: float                          # 0.0 – 1.0
    grounded_claims: int = 0
    ungrounded_claims: List[str] = field(default_factory=list)
    rationale: str = ""
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Faithfulness judge
# ---------------------------------------------------------------------------

class FaithfulnessJudge:
    """Uses Claude to identify unsupported numerical claims in a skill's output.

    Usage::

        judge = FaithfulnessJudge()
        result = judge.score(
            skill_name="bva-analyzer",
            input_data={"lines": [...]},
            output_text=json.dumps(bva_output),
        )
        assert result.score >= 0.75
    """

    MODEL = "claude-haiku-4-5"  # fast + cheap for eval runs

    _SYSTEM = (
        "You are an FP&A audit assistant. You evaluate whether a financial analysis "
        "output contains any claims that cannot be verified from the source data. "
        "Respond ONLY with valid JSON."
    )

    _PROMPT_TEMPLATE = """\
## Skill
{skill_name}

## Source Data (truncated to first 3000 chars)
{input_summary}

## Skill Output
{output_text}

## Task
Identify any numerical or factual claims in the output that are NOT directly supported
by the source data above. A claim is "unsupported" if:
- The number does not appear in or cannot be derived from the source data
- A category or supplier is mentioned that does not appear in the source

Respond with this JSON schema:
{{
  "unsupported_claims": ["<claim 1>", ...],   // empty list if all claims are supported
  "rationale": "<brief explanation>",
  "score": <float 0.0-1.0>                    // 1.0 = fully faithful, 0.0 = completely unsupported
}}"""

    def score(
        self,
        skill_name: str,
        input_data: Dict[str, Any],
        output_text: str,
    ) -> FaithfulnessResult:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package required for LLM judge. pip install anthropic")

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        input_summary = json.dumps(input_data, default=str)[:3000]
        prompt = self._PROMPT_TEMPLATE.format(
            skill_name=skill_name,
            input_summary=input_summary,
            output_text=output_text[:4000],
        )
        msg = client.messages.create(
            model=self.MODEL,
            max_tokens=512,
            system=self._SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
        try:
            parsed = json.loads(raw)
            return FaithfulnessResult(
                score=float(parsed.get("score", 0.5)),
                unsupported_claims=parsed.get("unsupported_claims", []),
                rationale=parsed.get("rationale", ""),
                raw_response=raw,
            )
        except Exception:
            # If parse fails, treat as uncertain
            return FaithfulnessResult(score=0.5, raw_response=raw)


# ---------------------------------------------------------------------------
# Trace-grounded judge
# ---------------------------------------------------------------------------

class TraceGroundedJudge:
    """Verifies that claims in a final response_text trace back to raw source data.

    For each numerical claim in response_text, asks Claude to identify which
    SkillTrace's input_snapshot (raw spend lines) supports the claim.
    """

    MODEL = "claude-haiku-4-5"

    _SYSTEM = (
        "You are a financial audit assistant verifying that an executive brief "
        "is grounded in raw source data. Respond ONLY with valid JSON."
    )

    _PROMPT_TEMPLATE = """\
## Final Executive Brief
{response_text}

## Execution Trace (skill inputs and outputs)
{trace_summary}

## Task
For each numerical or categorical claim in the brief, determine whether it can be
traced to a specific skill's input_snapshot (the raw spend data).

Respond with this JSON schema:
{{
  "grounded_claims": <int>,
  "ungrounded_claims": ["<claim 1>", ...],
  "rationale": "<explanation>",
  "score": <float 0.0-1.0>
}}"""

    def score(self, response_text: str, trace: EvalTrace) -> TraceGroundingResult:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package required for LLM judge. pip install anthropic")

        from app.eval.trace import summarize_trace

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        trace_summary = summarize_trace(trace)
        prompt = self._PROMPT_TEMPLATE.format(
            response_text=response_text[:3000],
            trace_summary=trace_summary[:4000],
        )
        msg = client.messages.create(
            model=self.MODEL,
            max_tokens=512,
            system=self._SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
        try:
            parsed = json.loads(raw)
            return TraceGroundingResult(
                score=float(parsed.get("score", 0.5)),
                grounded_claims=int(parsed.get("grounded_claims", 0)),
                ungrounded_claims=parsed.get("ungrounded_claims", []),
                rationale=parsed.get("rationale", ""),
                raw_response=raw,
            )
        except Exception:
            return TraceGroundingResult(score=0.5, raw_response=raw)
