"""Tests for hybrid presentation layer (structured blocks + markdown narrative)."""
from __future__ import annotations

import json
from pathlib import Path

from app.opar.models import AdvisorySections, ObserveContext
from app.opar.presentation import (
    assemble_assistant_payload,
    build_insight_blocks,
    presentation_structure_score,
)
from app.opar.reflect_advisory import normalize_advisory_sections

_GOLDEN = Path(__file__).parent / "eval" / "golden" / "presentation" / "portfolio_gap.json"


def _portfolio_validated() -> dict:
    return {
        "spend-profiler": {
            "total_spend": 12_000_000,
            "category_profile": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Technology",
                    "spend": 4_500_000,
                    "spend_pct": 3.2,
                    "addressable_spend": 900_000,
                    "hhi": 0.28,
                    "top_suppliers": [
                        {"supplier": "Microsoft", "spend": 2_000_000, "share_of_category": 0.44},
                        {"supplier": "AWS", "spend": 1_500_000, "share_of_category": 0.33},
                    ],
                },
                {
                    "category_id": "LOG",
                    "category_name": "Logistics",
                    "spend": 2_100_000,
                    "spend_pct": 1.5,
                    "addressable_spend": 420_000,
                    "hhi": 0.35,
                    "top_suppliers": [
                        {"supplier": "DHL", "spend": 1_200_000, "share_of_category": 0.57},
                    ],
                },
                {
                    "category_id": "MKT",
                    "category_name": "Marketing",
                    "spend": 1_800_000,
                    "spend_pct": 1.3,
                    "addressable_spend": 360_000,
                    "hhi": 0.22,
                    "top_suppliers": [],
                },
            ],
        },
        "peer-benchmarker": {
            "comparisons": [
                {
                    "category_id": "IT",
                    "actual_pct_of_revenue": 3.2,
                    "benchmark_p50_pct": 2.1,
                    "benchmark_gap_pct": 1.1,
                },
                {
                    "category_id": "LOG",
                    "actual_pct_of_revenue": 1.5,
                    "benchmark_p50_pct": 0.9,
                    "benchmark_gap_pct": 0.6,
                },
            ],
        },
        "savings-modeler": {
            "initiatives": [
                {
                    "category_id": "IT",
                    "lever_name": "Cloud rightsizing",
                    "net_savings": {"mid": 250_000},
                },
            ],
        },
    }


def test_build_insight_blocks_emits_multiple_category_cards_for_portfolio() -> None:
    ctx = ObserveContext(
        user_message="Where are the biggest benchmark gaps across our portfolio?",
        intent_class="value_bridge",
    )
    blocks = build_insight_blocks(ctx, _portfolio_validated())
    kinds = [b.kind for b in blocks]
    assert "metric_strip" in kinds
    category_blocks = [b for b in blocks if b.kind == "category_insight"]
    assert len(category_blocks) >= 2
    it_block = next(b for b in category_blocks if b.data["category_id"] == "IT")
    assert it_block.data["benchmark_gap"] is not None
    assert len(it_block.data["top_suppliers"]) >= 1


def test_assemble_assistant_payload_merges_advisory_structured_sections() -> None:
    ctx = ObserveContext(user_message="portfolio gaps", intent_class="value_bridge")
    advisory = AdvisorySections(
        executive_takeaway="IT and logistics drive most of the peer gap.",
        category_focus_section=(
            "## Why the gap exists\n\n"
            "IT spend runs above peer median because cloud and application vendors were onboarded "
            "on overlapping enterprise agreements without a portfolio rationalization pass — "
            "duplicate capacity and uncapped consumption tiers inflate run-rate.\n\n"
            "## What should change\n\n"
            "Consolidate overlapping Microsoft and AWS commitments at renewal and enforce "
            "rightsizing on idle instances before the next EA cycle.\n\n"
            "## Leadership decision\n\n"
            "CFO must sponsor a 90-day vendor consolidation workstream with procurement and IT "
            "jointly accountable for renewal gates."
        ),
        quick_wins_from_data=["Renegotiate Azure EA", "Consolidate freight lanes"],
        business_levers=[
            {
                "lever_name": "Supplier consolidation",
                "what_changes": "Reduce vendor count",
                "why_it_works": "Volume pricing",
                "evidence": ["Top 3 are 68% of spend"],
            },
            {
                "lever_name": "Contract reset",
                "what_changes": "Reset maintenance terms",
                "why_it_works": "Benchmark gap is contract-driven",
                "evidence": ["Gap vs P75 is 2.1 pts"],
            },
            {
                "lever_name": "Maverick compliance",
                "what_changes": "Route spend through POs",
                "why_it_works": "Off-contract buying inflates unit cost",
                "evidence": ["14% off-contract"],
            },
        ],
        priority_actions_30_60_90=[
            {
                "timeline": "30 days",
                "action": "Launch RFP for top IT vendors",
                "expected_impact": "5-8% rate reduction",
            },
            {
                "timeline": "60 days",
                "action": "Negotiate freight indexation",
                "expected_impact": "Lane cost stabilization",
            },
        ],
    )
    payload = assemble_assistant_payload(advisory, _portfolio_validated(), ctx)
    kinds = [b.kind for b in payload.blocks]
    assert "category_insight" in kinds
    assert "quick_wins" in kinds
    assert "lever_list" in kinds
    assert "action_timeline" in kinds
    assert payload.narrative_markdown == "IT and logistics drive most of the peer gap."
    causal = [
        b for b in payload.blocks
        if b.kind == "markdown_narrative" and b.data.get("variant") == "causal_prose"
    ]
    assert len(causal) == 1
    assert "## Why the gap exists" in causal[0].data["markdown"]
    assert "portfolio rationalization" in causal[0].data["markdown"]
    cat_idx = next(i for i, b in enumerate(payload.blocks) if b.kind == "category_insight")
    causal_idx = next(i for i, b in enumerate(payload.blocks) if b.data.get("variant") == "causal_prose")
    assert cat_idx < causal_idx


def test_normalize_advisory_sections_preserves_recommendations() -> None:
    raw = {
        "executive_takeaway": "Focus on IT consolidation.",
        "quick_wins_from_data": ["Win A", "Win B"],
        "business_levers": [
            {"lever_name": "A", "what_changes": "x", "why_it_works": "y", "evidence": ["z"]},
            {"lever_name": "B", "what_changes": "x", "why_it_works": "y", "evidence": ["z"]},
            {"lever_name": "C", "what_changes": "x", "why_it_works": "y", "evidence": ["z"]},
        ],
        "recommendations": [
            {
                "category_id": "IT",
                "category_name": "IT & Technology",
                "lever": "Cloud rightsizing",
                "financials": {"mid_case_savings": 250_000},
            }
        ],
    }
    advisory = normalize_advisory_sections(raw)
    assert advisory is not None
    assert len(advisory.recommendations) == 1
    assert advisory.recommendations[0].category_id == "IT"


def test_presentation_structure_score_penalizes_wall_of_text() -> None:
    ctx = ObserveContext(user_message="gaps", intent_class="value_bridge")
    payload = assemble_assistant_payload(None, _portfolio_validated(), ctx)
    good_score, good_ev = presentation_structure_score(payload)
    assert good_score >= 7.0
    assert good_ev.get("category_insight_count", 0) >= 2

    payload.narrative_markdown = "x" * 800
    bad_score, bad_ev = presentation_structure_score(payload)
    assert bad_score < good_score
    assert bad_ev.get("narrative_wall_of_text") is True


def test_golden_portfolio_fixture_expects_multiple_category_blocks() -> None:
    assert _GOLDEN.is_file(), f"missing golden fixture: {_GOLDEN}"
    fx = json.loads(_GOLDEN.read_text())
    ctx = ObserveContext(**fx["observe_context"])
    payload = assemble_assistant_payload(None, fx["validated"], ctx)
    category_blocks = [b for b in payload.blocks if b.kind == "category_insight"]
    assert len(category_blocks) >= fx["expected_min_category_blocks"]
