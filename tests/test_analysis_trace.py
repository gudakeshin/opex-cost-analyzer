"""Tests for structured analysis trace and live progress callbacks."""
from __future__ import annotations

import uuid

from app.models import NormalizedSpendLine
from app.services.analysis import run_core_pipeline


def _lines() -> list[NormalizedSpendLine]:
    return [
        NormalizedSpendLine(
            row_id=1,
            supplier="Infosys",
            description="IT managed services",
            amount=12_000_000,
            category_id="IT_SERVICES",
            category_name="IT Services",
        ),
        NormalizedSpendLine(
            row_id=2,
            supplier="Advisory LLP",
            description="Management consulting",
            amount=8_000_000,
            category_id="PROF_SERVICES",
            category_name="Professional Services",
        ),
    ]


def test_run_core_pipeline_emits_analysis_trace_with_sources() -> None:
    sid = str(uuid.uuid4())
    state = run_core_pipeline(
        sid,
        _lines(),
        ["The company operates GCC capability centers in India."],
        "gcc_capability_centers",
        500_000_000,
        company_name="Test Co",
        reporting_currency="INR",
        source_files={
            "spend": ["belrise_spend.csv"],
            "context": ["strategy_brief.txt"],
        },
    )
    trace = state.get("analysis_trace") or []
    assert len(trace) >= 3

    phases = [step["phase"] for step in trace]
    assert "ingest" in phases
    assert "benchmark" in phases

    ingest = next(s for s in trace if s["phase"] == "ingest")
    assert "belrise_spend.csv" in ingest["source_documents"]
    assert ingest["metrics"]["line_count"] == 2

    context_steps = [s for s in trace if s["phase"] == "context"]
    if context_steps:
        assert "strategy_brief.txt" in context_steps[0]["source_documents"]


def test_analysis_trace_includes_richer_benchmark_and_savings_detail() -> None:
    sid = str(uuid.uuid4())
    state = run_core_pipeline(
        sid,
        _lines(),
        ["IT services company with cloud and software spend. Procurement maturity is centralised."],
        "it_ites",
        500_000_000,
        reporting_currency="INR",
        source_files={"spend": ["spend.csv"], "context": ["context.txt"]},
    )
    trace = state.get("analysis_trace") or []
    benchmark = next((s for s in trace if s["phase"] == "benchmark"), None)
    assert benchmark is not None
    assert "it_ites" in benchmark["detail"].lower() or "Compared" in benchmark["detail"]
    assert benchmark.get("metrics", {}).get("selection_rationale") is not None

    savings = next((s for s in trace if s["phase"] == "savings"), None)
    assert savings is not None
    assert "initiative" in savings["detail"].lower()


def test_run_core_pipeline_invokes_progress_cb() -> None:
    sid = str(uuid.uuid4())
    messages: list[tuple[str, str]] = []

    run_core_pipeline(
        sid,
        _lines(),
        [],
        "technology",
        500_000_000,
        reporting_currency="INR",
        progress_cb=lambda phase, msg: messages.append((phase, msg)),
        source_files={"spend": ["spend.csv"], "context": []},
    )

    assert len(messages) >= 3
    assert all(phase == "act" for phase, _ in messages)
    assert any("Read spend data" in msg for _, msg in messages)
