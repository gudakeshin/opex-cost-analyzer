"""Validate band-scaled NPV against savings_modeler output."""
from __future__ import annotations

import pytest

from app.services.npv_bands import compute_band_npv, initiative_band_npv
from app.skills.engine.savings import savings_modeler


def _model_initiative(amount: float = 2_000_000.0) -> dict:
    value_bridge = {
        "raw_rows": [
            {
                "category_id": "hr_recruitment",
                "category_name": "HR & Recruitment",
                "estimated_saving_amount": amount,
                "source": "internal",
            }
        ]
    }
    result = savings_modeler(value_bridge, {"root_cause_findings": []})
    init = result["initiatives"][0]
    gross = init["gross_savings"]
    cta = init["cost_to_achieve"]
    net = init["net_savings"]
    p50 = gross["y1"]
    return {
        "gross_savings_y1": gross["y1"],
        "gross_savings_y2": gross["y2"],
        "gross_savings_y3": gross["y3"],
        "cost_to_achieve": cta["total_3yr"],
        "net_npv": net["npv_pretax"],
        "p50_savings": p50,
        "p10_savings": p50 * 0.7,
        "p90_savings": p50 * 1.3,
    }


def test_p50_npv_matches_savings_modeler() -> None:
    row = _model_initiative()
    npv = initiative_band_npv(row, "p50")
    assert npv == pytest.approx(row["net_npv"], rel=1e-6)


@pytest.mark.parametrize(
    ("band", "factor"),
    [("p10", 0.7), ("p50", 1.0), ("p90", 1.3)],
)
def test_band_npv_scales_with_savings_band(band: str, factor: float) -> None:
    row = _model_initiative()
    p50_amt = row["p50_savings"]
    band_amt = p50_amt * factor
    expected = compute_band_npv(
        gross_y1=row["gross_savings_y1"],
        gross_y2=row["gross_savings_y2"],
        gross_y3=row["gross_savings_y3"],
        cost_to_achieve_3yr=row["cost_to_achieve"],
        band_savings=band_amt,
        p50_savings=p50_amt,
        net_npv_p50=row["net_npv"],
    )
    assert initiative_band_npv(row, band) == pytest.approx(expected, rel=1e-6)


def test_p10_less_than_p50_less_than_p90() -> None:
    row = _model_initiative()
    p10 = initiative_band_npv(row, "p10")
    p50 = initiative_band_npv(row, "p50")
    p90 = initiative_band_npv(row, "p90")
    assert 0 < p10 < p50 < p90


def test_npv_less_than_gross_3yr_for_each_band() -> None:
    row = _model_initiative()
    gross_3yr = row["gross_savings_y1"] + row["gross_savings_y2"] + row["gross_savings_y3"]
    for band in ("p10", "p50", "p90"):
        factor = {"p10": 0.7, "p50": 1.0, "p90": 1.3}[band]
        npv = initiative_band_npv(row, band)
        assert npv <= gross_3yr * factor + 1.0


def test_custom_p10_p90_savings_not_default_multipliers() -> None:
    row = _model_initiative()
    row["p10_savings"] = row["p50_savings"] * 0.55
    row["p90_savings"] = row["p50_savings"] * 1.45
    p10 = initiative_band_npv(row, "p10")
    p90 = initiative_band_npv(row, "p90")
    default_p10 = initiative_band_npv({**row, "p10_savings": row["p50_savings"] * 0.7}, "p10")
    default_p90 = initiative_band_npv({**row, "p90_savings": row["p50_savings"] * 1.3}, "p90")
    assert p10 < default_p10
    assert p90 > default_p90


def test_zero_p50_returns_stored_npv() -> None:
    row = {"gross_savings_y1": 0, "gross_savings_y2": 0, "gross_savings_y3": 0, "net_npv": 42.0}
    assert initiative_band_npv(row, "p50") == 42.0
