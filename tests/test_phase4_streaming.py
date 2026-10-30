"""Phase 4 tests: streaming hooks, sensitivity narrative, golden-set evals."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("duckdb")
pytest.importorskip("pyarrow")


def test_synthesize_chat_response_claude_accepts_token_callback() -> None:
    from app.opar.claude_client import synthesize_chat_response_claude

    tokens: list[str] = []

    with patch("app.opar.claude_client.ANTHROPIC_ENABLED", True), patch(
        "app.opar.claude_client.ANTHROPIC_API_KEY", "test-key"
    ), patch("app.opar.claude_client.os.getenv", return_value=None), patch(
        "app.opar.claude_client.submit_with_context"
    ) as submit:
        future = MagicMock()
        future.result.return_value = "Hello **world**"
        submit.return_value = future
        text, thinking = synthesize_chat_response_claude(
            {"user_message": "hi", "qa_context": {}},
            token_callback=tokens.append,
        )
    assert text == "Hello **world**"
    assert thinking is None
    assert submit.call_args[0][1].__name__ == "_stream_anthropic_native"


def test_sensitivity_narrative_deterministic_fallback() -> None:
    from app.opar.sensitivity_narrative import synthesize_sensitivity_narrative

    payload = {
        "baseline_mid_savings": 10_000_000,
        "scenarios": [
            {
                "name": "Aggressive",
                "savings_3yr": 12_000_000,
                "npv_aftertax": 9_000_000,
                "timeline_months": 24,
                "custom": True,
            },
            {
                "name": "Conservative",
                "savings_3yr": 8_000_000,
                "npv_aftertax": 6_000_000,
                "timeline_months": 36,
                "custom": True,
            },
        ],
    }
    with patch("app.opar.sensitivity_narrative._llm_narrative", return_value=None):
        text = synthesize_sensitivity_narrative(payload, currency="INR")
    assert "Aggressive" in text
    assert "Conservative" in text
    assert "Cr" in text


def test_chat_stream_format_sse() -> None:
    from app.routers.chat import _format_sse

    line = _format_sse("token", {"delta": "Hi"})
    assert line.startswith("event: token\n")
    assert json.loads(line.split("data: ", 1)[1].strip()) == {"delta": "Hi"}


def test_llm_golden_eval_passes() -> None:
    import json
    import subprocess
    import sys
    from pathlib import Path

    import os

    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "eval" / "run_llm_golden_eval.py"), "--json-only"],
        cwd=str(root),
        env={**os.environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    scores_path = root / "eval" / "llm_golden_scores.json"
    payload = json.loads(scores_path.read_text(encoding="utf-8"))
    assert payload["total_cases"] >= 45
    assert payload["passed"], payload


def test_stream_callbacks_emit_progress() -> None:
    import asyncio

    from app.routers.chat import _stream_callbacks

    async def _run() -> None:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        progress_cb, thinking_cb, token_cb = _stream_callbacks("run-1", queue, loop)
        progress_cb("observe", "Starting")
        thinking_cb("reasoning")
        token_cb("tok")
        await asyncio.sleep(0.05)
        events = []
        while not queue.empty():
            events.append(await queue.get())
        assert ("progress", {"phase": "observe", "message": "Starting"}) in events
        assert ("thinking", {"chunk": "reasoning"}) in events
        assert ("token", {"delta": "tok"}) in events

    asyncio.run(_run())
