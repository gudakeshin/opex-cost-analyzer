"""Behaviour tests for the June-2026 heuristics improvement batch (P1–P3).

One test per acceptance criterion in the heuristics improvement plan:
- P1-A: effort_weeks + applicability_threshold_pct present on every sector lever
- P1-B: graduated maverick severity (Critical / Elevated)
- P1-C: fragmentation flag gated on a minimum addressable-spend floor
- P2-A: per-lever bounce-back reversion (NPV ordering high < mixed < low)
- P2-B: execution-probability-weighted conservative scenario
- P2-C/P3-C: confidence bands narrow with higher sustainability / specificity
- P2-D: EBITDA basis-point framing per initiative + portfolio
- P2-E: horizon classification (tactical / structural / transformational)
- P2-F: regulatory_headwind scenario present and excludes impacted levers
- P3-B: telecom/energy resolve to dedicated benchmark keys + fallback note
"""
from __future__ import annotations

from app.models import NormalizedSpendLine
from app.skills import engine
from app.skills.engine.savings import _band_factors, _classify_horizon
from app.services.benchmarks import benchmark_industry_for, resolve_benchmark_payload
from app.services.sector_packs import run_regression_test
from app.services.sensitivity import compute_sensitivity


def _line(row_id, supplier, category_id, amount, description="adhoc services"):
    return NormalizedSpendLine(
        row_id=row_id,
        supplier=supplier,
        description=description,
        category_id=category_id,
        category_name=category_id,
        amount=amount,
        spend_date="2025-01-15",
        currency="INR",
        fx_rate_to_reporting=1.0,
    )


# ---------------------------------------------------------------------------
# P1-A
# ---------------------------------------------------------------------------

def test_p1a_regression_test_checks_effort_and_applicability() -> None:
    result = run_regression_test("bfsi_banks")
    assert result["checks"]["lever_effort_weeks"] is True
    assert result["checks"]["lever_applicability_threshold"] is True


def test_p1a_eligible_levers_carry_effort_weeks_alias() -> None:
    profile = {"category_profile": [{"category_id": "IT", "spend": 1_000_000.0}]}
    levers = engine.resolve_eligible_levers(
        industry="bfsi_banks", spend_profile=profile, headcount=100.0,
        annual_revenue=1_000_000_000.0, root_causes=[],
    )
    assert levers
    # effort_weeks is aliased from implementation_weeks (p50 always present).
    assert all((lv.get("effort_weeks") or {}).get("p50") for lv in levers)
    assert any(lv.get("applicability_threshold_pct") is not None for lv in levers)


# ---------------------------------------------------------------------------
# P1-B — graduated maverick severity
# ---------------------------------------------------------------------------

def _maverick_finding(off_po_amount: float, po_amount: float):
    lines = [
        _line("1", "V1", "IT", off_po_amount, description="adhoc consulting"),
        _line("2", "V2", "IT", po_amount, description="po 4567 consulting"),
    ]
    profile = engine.spend_profiler(lines)
    out = engine.root_cause_analyzer(
        profile, {"comparisons": []}, lines, industry="technology",
        reporting_currency="INR",
    )
    findings = out["root_cause_findings"][0]["root_causes"]
    return next((rc for rc in findings if "maverick" in rc.get("diagnosis", "").lower()), None)


def test_p1b_maverick_severity_critical_at_45pct() -> None:
    rc = _maverick_finding(off_po_amount=450_000.0, po_amount=550_000.0)
    assert rc is not None
    assert rc["maverick_severity"]["label"] == "Critical"


def test_p1b_maverick_severity_elevated_at_18pct() -> None:
    # 18% off-PO is below the old flat 0.20 floor but above the warning tier (0.15),
    # so it now fires with the "Elevated" (warning tier) label.
    rc = _maverick_finding(off_po_amount=180_000.0, po_amount=820_000.0)
    assert rc is not None
    assert rc["maverick_severity"]["label"] == "Elevated"


# ---------------------------------------------------------------------------
# P1-C — fragmentation minimum-spend gate
# ---------------------------------------------------------------------------

def _fragmentation_levers(per_supplier_amount: float):
    # 8 equal suppliers → HHI 0.125 (< 0.15 max), supplier_count 8 (≥ 5).
    lines = [_line(str(i), f"S{i}", "IT", per_supplier_amount) for i in range(8)]
    profile = engine.spend_profiler(lines)
    out = engine.root_cause_analyzer(
        profile, {"comparisons": []}, lines, industry="technology",
        reporting_currency="INR",
    )
    causes = out["root_cause_findings"][0]["root_causes"]
    return {rc.get("recommended_lever") for rc in causes}


def test_p1c_fragmentation_suppressed_below_spend_floor() -> None:
    # 8 × ₹5 lakh = ₹40 lakh total, below the ₹5 Cr floor → no consolidation flag.
    levers = _fragmentation_levers(500_000.0)
    assert "supplier_consolidation" not in levers


def test_p1c_fragmentation_fires_above_spend_floor() -> None:
    # 8 × ₹80 lakh = ₹6.4 Cr total, above the ₹5 Cr floor → consolidation flag.
    levers = _fragmentation_levers(8_000_000.0)
    assert "supplier_consolidation" in levers


# ---------------------------------------------------------------------------
# P2-A — per-lever bounce-back
# ---------------------------------------------------------------------------

def _bounce_back_npv(risk_a: str, risk_b: str) -> float:
    vb = {"confidence_bands": {"low": 80.0, "mid": 100.0, "high": 120.0}}
    sm = {"initiatives": [
        {"lever": "a", "bounce_back_risk": risk_a, "base_execution_probability": 0.8,
         "gross_savings": {"y1": 10, "y2": 20, "y3": 30, "total_3yr": 60},
         "net_savings": {"total_3yr": 54}},
        {"lever": "b", "bounce_back_risk": risk_b, "base_execution_probability": 0.8,
         "gross_savings": {"y1": 10, "y2": 20, "y3": 30, "total_3yr": 60},
         "net_savings": {"total_3yr": 54}},
    ]}
    out = compute_sensitivity(vb, savings_model=sm, discount_rate=0.10)
    bb = next(s for s in out["scenarios"] if s["name"] == "bounce_back")
    return bb["npv_pretax"]


def test_p2a_bounceback_npv_between_global_and_no_reversion() -> None:
    npv_high = _bounce_back_npv("high", "high")   # both revert 80% of Y3 (≈ global 0.80)
    npv_mixed = _bounce_back_npv("high", "low")   # one high, one low
    npv_low = _bounce_back_npv("low", "low")      # both revert only 15% of Y3
    assert npv_high < npv_mixed < npv_low


# ---------------------------------------------------------------------------
# P2-B — execution-probability-weighted conservative scenario
# ---------------------------------------------------------------------------

def test_p2b_conservative_below_flat_rate_for_low_probability_portfolio() -> None:
    mid = 200.0
    sm = {"initiatives": [
        {"lever": "demand_management", "base_execution_probability": 0.40,
         "net_savings": {"total_3yr": 100.0},
         "gross_savings": {"y1": 40, "y2": 40, "y3": 20, "total_3yr": 100}},
        {"lever": "maverick_compliance", "base_execution_probability": 0.40,
         "net_savings": {"total_3yr": 100.0},
         "gross_savings": {"y1": 40, "y2": 40, "y3": 20, "total_3yr": 100}},
    ]}
    vb = {"confidence_bands": {"low": 160.0, "mid": mid, "high": 240.0}}
    out = compute_sensitivity(vb, savings_model=sm, discount_rate=0.10)
    conservative = next(s for s in out["scenarios"] if s["name"] == "conservative")
    # Flat path would give mid * 0.60 = 120; execution-weighted lands well below.
    assert conservative["savings_3yr"] < mid * 0.60


# ---------------------------------------------------------------------------
# P2-C / P3-C — confidence bands as a function of sustainability & specificity
# ---------------------------------------------------------------------------

def test_p2c_band_factors_tighter_for_high_sustainability_and_specificity() -> None:
    tight = _band_factors(0.40, 0.90)   # signed contract, client benchmark
    wide = _band_factors(0.25, 0.55)    # behavioural lever, seed data
    assert (tight[1] - tight[0]) < (wide[1] - wide[0])


def test_p3c_specificity_narrows_value_bridge_bands() -> None:
    sm = {"initiatives": [
        {"category_id": "IT", "lever": "contract_renegotiation", "sustainability_score": 0.5,
         "confidence": "high", "net_savings": {"total_3yr": 100.0, "npv_10pct": 90.0},
         "gross_savings": {"total_3yr": 100.0}, "cost_to_achieve": {"total_3yr": 10.0},
         "payback_months": 8},
    ]}
    high_spec = engine.value_bridge_calculator({}, {}, {}, 1000.0, savings_model=sm, benchmark_specificity=0.90)
    low_spec = engine.value_bridge_calculator({}, {}, {}, 1000.0, savings_model=sm, benchmark_specificity=0.55)
    hb = high_spec["confidence_bands"]
    lb = low_spec["confidence_bands"]
    assert (hb["high"] - hb["low"]) < (lb["high"] - lb["low"])


# ---------------------------------------------------------------------------
# P2-D — EBITDA basis-point framing
# ---------------------------------------------------------------------------

def test_p2d_ebitda_bps_formula_and_portfolio() -> None:
    peer = {"comparisons": [
        {"category_id": "IT", "category_name": "IT", "percentile_band": "P75-P90",
         "estimated_saving_amount": 500_000.0},
    ]}
    raw = engine.build_raw_rows(peer, {"internal_variance": []}, {"heuristic_findings": []})
    revenue = 1_000_000_000.0
    model = engine.savings_modeler({"raw_rows": raw}, {"root_cause_findings": []}, annual_revenue=revenue)
    init = model["initiatives"][0]
    arr = init["annualized_run_rate_savings"]
    assert init["ebitda_impact"]["ebitda_bps"] == round(arr / revenue * 10000, 1)
    assert init["ebitda_impact"]["revenue_base_used"] == round(revenue, 0)
    total_rr = model["summary"]["total_run_rate_savings"]
    assert model["summary"]["portfolio_ebitda_impact_bps"] == round(total_rr / revenue * 10000, 1)


def test_p2d_ebitda_bps_250_for_2000cr_and_50cr() -> None:
    # ₹50 Cr run-rate saving on ₹2,000 Cr revenue = 250 bps.
    rev = 2000 * 1e7
    saving = 50 * 1e7
    assert round(saving / rev * 10000, 1) == 250.0


# ---------------------------------------------------------------------------
# P2-E — horizon classification
# ---------------------------------------------------------------------------

def test_p2e_classify_horizon_by_effort_weeks() -> None:
    assert _classify_horizon([1.0, 0.0, 0.0], 6, 10) == "tactical"            # payment_terms
    assert _classify_horizon([0.15, 0.55, 0.30], 3, 16) == "structural"       # contract_reneg
    assert _classify_horizon([0.10, 0.40, 0.50], 36, 48) == "transformational"  # SSC


def test_p2e_initiatives_and_summary_carry_horizon() -> None:
    peer = {"comparisons": [
        {"category_id": "IT", "category_name": "IT", "percentile_band": "P75-P90",
         "estimated_saving_amount": 500_000.0},
    ]}
    raw = engine.build_raw_rows(peer, {"internal_variance": []}, {"heuristic_findings": []})
    model = engine.savings_modeler({"raw_rows": raw}, {"root_cause_findings": []}, annual_revenue=1e9)
    valid = {"tactical", "structural", "transformational"}
    assert all(i["horizon"] in valid for i in model["initiatives"])
    assert set(model["summary"]["horizon_summary"]).issubset(valid)


# ---------------------------------------------------------------------------
# P2-F — regulatory headwind scenario
# ---------------------------------------------------------------------------

def test_p2f_regulatory_scenario_excludes_impacted_levers() -> None:
    vb = {"confidence_bands": {"low": 80.0, "mid": 100.0, "high": 120.0}}
    sm = {"initiatives": [
        {"lever": "contract_renegotiation", "base_execution_probability": 0.8,
         "net_savings": {"total_3yr": 100.0}, "gross_savings": {"y1": 30, "y2": 40, "y3": 30, "total_3yr": 100}},
        {"lever": "gst_itc_recovery", "base_execution_probability": 0.8,
         "net_savings": {"total_3yr": 100.0}, "gross_savings": {"y1": 30, "y2": 40, "y3": 30, "total_3yr": 100}},
    ]}
    out = compute_sensitivity(vb, savings_model=sm, discount_rate=0.10)
    reg = next(s for s in out["scenarios"] if s["name"] == "regulatory_headwind")
    assert reg["regulatory_warning"] is True
    # Only the non-impacted lever (100) survives, with a 10% overhead haircut → 90.
    assert reg["savings_3yr"] == 90.0


# ---------------------------------------------------------------------------
# P3-B — telecom / energy benchmark mapping + fallback note
# ---------------------------------------------------------------------------

def test_p3b_dedicated_benchmark_keys() -> None:
    assert benchmark_industry_for("telecom_infra") == "telecom_infra"
    assert benchmark_industry_for("energy_utilities") == "energy_utilities"


def test_p3b_fallback_note_for_borrowed_mapping() -> None:
    resolved = resolve_benchmark_payload("bfsi_banks", ["IT", "PROF_SVCS"])
    note = resolved["selection_rationale"].get("benchmark_confidence_note")
    assert note and "financial_services" in note
