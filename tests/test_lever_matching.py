"""Table-driven tests for applicable_if lever matching grammar."""
from __future__ import annotations

import pytest

from app.skills.engine.lever_rules import evaluate_lever_applicable_if
from app.skills.engine.profiler import _evaluate_lever_signals, resolve_eligible_levers


def _profile(
    categories: dict[str, float],
    *,
    total_spend: float | None = None,
    bus: int = 1,
    cc: int = 1,
) -> dict:
    total = total_spend or sum(categories.values()) or 1.0
    return {
        "total_spend": total,
        "category_profile": [
            {
                "category_id": cid,
                "category_name": cid,
                "spend": amt,
                "supplier_count": 5,
                "express_like_pct": 0.0,
            }
            for cid, amt in categories.items()
        ],
        "organizational_diversity": {
            "distinct_business_units": bus,
            "distinct_cost_centers": cc,
        },
    }


KEYWORD_FAMILIES = {
    "gcc": ["global capability center", "gcc", "captive"],
    "bfsi": ["core banking", "npa"],
}


@pytest.mark.parametrize(
    "rules,categories,revenue,expected_token",
    [
        (["category:FACILITIES present"], {"FACILITIES": 100}, 1000, "category:FACILITIES_present"),
        (["category:IT or HR present"], {"IT": 50}, 1000, "category:IT_present"),
        (["category:FACILITIES > 3% revenue"], {"FACILITIES": 40}, 1000, "category:FACILITIES_present"),
        (["category:FACILITIES > 3% revenue"], {"FACILITIES": 10}, 1000, "category:FACILITIES_present"),
        (["category:IT > 5% spend"], {"IT": 60, "HR": 40}, 1000, "category:IT_present"),
        (["headcount > 100"], {}, 0, "headcount>100"),
        (["annual_revenue > 100M"], {}, 200_000_000, "revenue>"),
    ],
)
def test_hard_gate_rules(rules, categories, revenue, expected_token):
    profile = _profile(categories)
    cats_present = set(categories)
    cat_spend = dict(categories)
    total = sum(categories.values()) or 1.0
    signals = evaluate_lever_applicable_if(
        rules,
        categories_present=cats_present,
        cat_spend=cat_spend,
        total_spend=total,
        annual_revenue=revenue,
        headcount=150 if "headcount" in rules[0] else 0,
        signal_corpus=set(),
        keyword_families=KEYWORD_FAMILIES,
        multi_bu_inferable=False,
        spend_profile=profile,
    )
    if expected_token is None:
        assert signals == []
    else:
        assert any(expected_token in s for s in signals)


def test_keyword_unconfirmed_is_permissive():
    lever = {"applicable_if": ["gcc_keywords detected"]}
    profile = _profile({"IT": 100})
    signals = _evaluate_lever_signals(
        lever,
        {"IT"},
        {"IT": 100},
        100,
        0,
        1_000_000,
        signal_corpus=None,
        spend_profile=profile,
    )
    assert "gcc_keywords detected" in signals


def test_keyword_does_not_block_category_rule():
    lever = {"applicable_if": ["gcc_keywords detected", "category:IT present"]}
    profile = _profile({"IT": 100})
    signals = _evaluate_lever_signals(
        lever,
        {"IT"},
        {"IT": 100},
        100,
        0,
        1_000_000,
        signal_corpus={"unrelated term only"},
        spend_profile=profile,
    )
    assert "category:IT_present" in signals


def test_multi_bu_does_not_block_when_category_present():
    lever = {"applicable_if": ["multi_bu_structure detected", "category:IT present"]}
    profile = _profile({"IT": 100}, bus=1, cc=1)
    signals = _evaluate_lever_signals(
        lever,
        {"IT"},
        {"IT": 100},
        100,
        0,
        1_000_000,
        spend_profile=profile,
        multi_bu_inferable=False,
    )
    assert "category:IT_present" in signals

    signals = _evaluate_lever_signals(
        lever,
        {"IT"},
        {"IT": 100},
        100,
        0,
        1_000_000,
        spend_profile=profile,
        multi_bu_inferable=True,
    )
    assert "multi_bu_inferred" in signals
    assert "category:IT_present" in signals


def test_empty_applicable_if_no_restriction():
    lever = {"lever_id": "x", "applicable_if": []}
    signals = _evaluate_lever_signals(
        lever, set(), {}, 1, 0, 0, spend_profile=_profile({})
    )
    assert signals == ["no_restriction"]


def test_facilities_revenue_via_resolve():
    from app.skills.engine._loaders import _get_sector_levers

    target_id = next(
        lv["lever_id"]
        for lv in _get_sector_levers("conglomerate").get("sector_specific_levers", [])
        if any("FACILITIES > 3% revenue" in r for r in lv.get("applicable_if", []))
    )

    profile_high = _profile({"FACILITIES": 40, "IT": 60}, bus=2, cc=2)
    high = resolve_eligible_levers(
        industry="conglomerate",
        spend_profile=profile_high,
        headcount=0,
        annual_revenue=1000,
        root_causes=[],
        sector_weights={"conglomerate": 0.6, "it_ites": 0.4},
    )
    fired = next((l for l in high if l["lever_id"] == target_id), None)
    assert fired is not None, "FACILITIES >3% revenue + multi-BU should fire target lever"
    assert "category:FACILITIES_present" in fired["trigger_signals"]

    profile_low = _profile({"FACILITIES": 10, "IT": 90}, bus=2, cc=2)
    low_rev = resolve_eligible_levers(
        industry="conglomerate",
        spend_profile=profile_low,
        headcount=0,
        annual_revenue=1000,
        root_causes=[],
        sector_weights={"conglomerate": 0.6, "it_ites": 0.4},
    )
    low_fired = next((l for l in low_rev if l["lever_id"] == target_id), None)
    assert low_fired is not None, "FACILITIES presence qualifies even below 3% revenue threshold"
    assert "category:FACILITIES_present" in low_fired["trigger_signals"]
