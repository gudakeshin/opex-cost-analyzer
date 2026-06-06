"""Expert review bundle generator.

Produces a structured markdown report combining:
  - Final response_text (from ReflectOutput if available)
  - EvalTrace summary table
  - Per-skill faithfulness scores (LLM judge, optional)
  - Counterfactual prioritization score (if a signal was embedded)

Usage (CLI)::

    python -m app.eval.review <session_id>

Or programmatically::

    from app.eval.review import generate_review_bundle
    bundle = generate_review_bundle(session_id="abc123")
    print(bundle.markdown)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import UPLOAD_DIR
from app.eval.counterfactual import SignalSpec, score_prioritization
from app.eval.trace import load_trace, summarize_trace


# ---------------------------------------------------------------------------
# Bundle data class
# ---------------------------------------------------------------------------

@dataclass
class ReviewBundle:
    session_id: str
    trace_summary: str = ""
    faithfulness_section: str = ""
    counterfactual_section: str = ""
    response_text_section: str = ""
    markdown: str = ""
    output_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_review_bundle(
    session_id: str,
    run_faithfulness_judge: bool = False,
    counterfactual_signal: Optional[SignalSpec] = None,
) -> ReviewBundle:
    """Build a ReviewBundle for the given session.

    Args:
        session_id:               The session to review.
        run_faithfulness_judge:   If True, call FaithfulnessJudge for each skill
                                  (requires ANTHROPIC_API_KEY).
        counterfactual_signal:    If provided, score whether this injected signal
                                  (supplier/category) was surfaced in the response,
                                  using the deterministic score_prioritization check.
    """
    bundle = ReviewBundle(session_id=session_id)

    # --- Load trace --------------------------------------------------------
    trace = load_trace(session_id)
    if trace is None:
        bundle.markdown = (
            f"# Review Bundle — session `{session_id}`\n\n"
            f"> No eval_trace.json found. Re-run with `enable_tracing=True`.\n"
        )
        return bundle

    bundle.trace_summary = summarize_trace(trace)

    # --- Response text (best-effort from memory) ---------------------------
    response_file = UPLOAD_DIR / session_id / "response_text.txt"
    response_text = ""
    if response_file.exists():
        response_text = response_file.read_text()[:4000]
    bundle.response_text_section = (
        f"## Final Response Text\n\n{response_text}\n" if response_text
        else "## Final Response Text\n\n*Not available — response_text.txt not found.*\n"
    )

    # --- Faithfulness section ---------------------------------------------
    faithfulness_lines = ["## Layer 1: Faithfulness Scores\n"]
    if run_faithfulness_judge:
        try:
            from app.eval.judge import FaithfulnessJudge
            import json
            judge = FaithfulnessJudge()
            for st in trace.skill_traces:
                if st.output is None:
                    faithfulness_lines.append(f"- **{st.skill_name}**: skipped (no output)\n")
                    continue
                result = judge.score(
                    skill_name=st.skill_name,
                    input_data=st.input_snapshot,
                    output_text=json.dumps(st.output, default=str)[:3000],
                )
                icon = "✅" if result.score >= 0.75 else "⚠️"
                faithfulness_lines.append(
                    f"- {icon} **{st.skill_name}**: score={result.score:.2f} "
                    f"| unsupported={len(result.unsupported_claims)}\n"
                )
                if result.unsupported_claims:
                    for claim in result.unsupported_claims:
                        faithfulness_lines.append(f"  - {claim}\n")
        except Exception as exc:
            faithfulness_lines.append(f"> LLM judge failed: {exc}\n")
    else:
        faithfulness_lines.append(
            "> Faithfulness judge not run. Re-generate with `run_faithfulness_judge=True` "
            "or set `RUN_LLM_JUDGE=1`.\n"
        )
    bundle.faithfulness_section = "".join(faithfulness_lines)

    # --- Counterfactual section -------------------------------------------
    cf_lines = ["## Layer 3: Counterfactual Score\n\n"]
    if counterfactual_signal is not None:
        try:
            bva_output = next(
                (st.output for st in trace.skill_traces
                 if st.output and "bva" in st.skill_name.lower()),
                None,
            )
            prio_result = score_prioritization(
                response_text=response_text,
                signal=counterfactual_signal,
                bva_output=bva_output,
            )
            icon = "✅" if prio_result.signal_surfaced else "⚠️"
            cf_lines.append(
                f"- {icon} **signal_surfaced={prio_result.signal_surfaced}** "
                f"| mentions={prio_result.mention_count} "
                f"| prominence={prio_result.prominence_score:.2f}\n"
                f"  - {prio_result.details}\n"
            )
        except Exception as exc:
            cf_lines.append(f"> Counterfactual scoring failed: {exc}\n")
    else:
        cf_lines.append(
            "> No counterfactual signal supplied. Pass `counterfactual_signal=SignalSpec(...)` "
            "(see `app/eval/counterfactual.py`) to score whether an injected anomaly was "
            "surfaced in the response.\n"
        )
    bundle.counterfactual_section = "".join(cf_lines)

    # --- Assemble markdown ------------------------------------------------
    parts = [
        f"# Review Bundle — session `{session_id}`\n",
        f"> Generated at: `{trace.created_at}`  |  "
        f"Total duration: {trace.total_duration_ms:.0f} ms\n\n",
        "## Layer 2: Execution Trace\n\n",
        bundle.trace_summary,
        "\n\n",
        bundle.response_text_section,
        "\n",
        bundle.faithfulness_section,
        "\n",
        bundle.counterfactual_section,
    ]
    bundle.markdown = "".join(parts)

    # --- Persist to disk --------------------------------------------------
    out_path = UPLOAD_DIR / session_id / "review_bundle.md"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(bundle.markdown)
        bundle.output_path = out_path
    except Exception:
        pass

    return bundle


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m app.eval.review <session_id> [--with-judge]")
        sys.exit(1)

    session_id = sys.argv[1]
    run_judge = "--with-judge" in sys.argv or os.environ.get("RUN_LLM_JUDGE") == "1"

    bundle = generate_review_bundle(session_id, run_faithfulness_judge=run_judge)

    if bundle.output_path:
        print(f"Review bundle written to: {bundle.output_path}")
    else:
        print(bundle.markdown)


if __name__ == "__main__":
    main()
