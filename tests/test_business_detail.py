"""Layer-A deterministic initiative enrichment (app/skills/engine/business_detail.py)."""
from __future__ import annotations

import copy

from app.skills.engine.business_detail import enrich_initiatives_business_detail


def _outputs(**overrides):
    base = {
        "spend-profiler": {
            "total_spend": 1000.0,
            "category_profile": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Telecom",
                    "spend": 1000.0,
                    "concentration_flag": "high",
                    "top_suppliers": [
                        {"supplier": "Oracle", "spend": 600.0, "share_of_category": 0.6, "avg_payment_terms_days": 30},
                        {"supplier": "SAP", "spend": 300.0, "share_of_category": 0.3, "avg_payment_terms_days": 45},
                    ],
                }
            ],
        },
        "savings-modeler": {
            "initiatives": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Telecom",
                    "lever": "license_rightsizing",
                    "lever_name": "License Rightsizing",
                    "lever_family": "technology",
                    "bounce_back_risk": "high",
                    "org_change_risk": "medium",
                    "confidence": "low",
                    "root_cause": "Shelfware above peer norm",
                    "horizon": "tactical",
                    "payback_months": 6,
                    "annualized_run_rate_savings": 250000.0,
                    "ebitda_impact": {"ebitda_bps": 12.5},
                    "gross_savings": {"y1": 100.0, "y2": 150.0, "y3": 150.0, "total_3yr": 400.0},
                    "diagnostic_signals": [{"signal": "Enterprise agreement expiring within 9 months"}],
                }
            ]
        },
    }
    base.update(overrides)
    return base


def test_enrich_attaches_owner_by_family():
    so = _outputs()
    enrich_initiatives_business_detail(so)
    init = so["savings-modeler"]["initiatives"][0]
    assert init["owner_role"] == "Chief Information Officer / IT Finance Lead"
    assert init["business_sponsor"] == "CIO and CFO"
    assert init["owner"]["raci"]["accountable"] == "Chief Information Officer"


def test_enrich_joins_vendors_from_spend_profiler():
    so = _outputs()
    enrich_initiatives_business_detail(so)
    vendors = so["savings-modeler"]["initiatives"][0]["affected_vendors"]
    assert [v["supplier"] for v in vendors] == ["Oracle", "SAP"]
    assert vendors[0]["share_of_category_pct"] == 60.0
    assert vendors[0]["avg_payment_terms_days"] == 30


def test_enrich_contract_lever_surfaces_renewal_window():
    so = _outputs()
    enrich_initiatives_business_detail(so)
    levers = so["savings-modeler"]["initiatives"][0]["contract_levers"]
    assert levers, "expected contract levers"
    assert "open contract window" in levers[0]
    assert "expiring within 9 months" in levers[0]


def test_enrich_builds_risk_register_from_labels_and_concentration():
    so = _outputs()
    enrich_initiatives_business_detail(so)
    risks = so["savings-modeler"]["initiatives"][0]["risks"]
    # high bounce-back + medium org-change + low confidence + high concentration => 4 risks
    assert len(risks) == 4
    assert all("mitigation" in r and "risk" in r for r in risks)
    severities = {r["severity"] for r in risks}
    assert "high" in severities


def test_enrich_kpis_and_change_management_present():
    so = _outputs()
    enrich_initiatives_business_detail(so)
    init = so["savings-modeler"]["initiatives"][0]
    assert len(init["kpis"]) >= 3
    assert "License / seat utilization (%)" in {k["metric"] for k in init["kpis"]}
    assert init["change_management"]["stakeholders"]
    assert init["change_management"]["comms_cadence"]


def test_enrich_phasing_and_rationale():
    so = _outputs()
    enrich_initiatives_business_detail(so)
    init = so["savings-modeler"]["initiatives"][0]
    assert "Tactical initiative phased" in init["phasing_narrative"]
    assert "Payback ~6 months" in init["phasing_narrative"]
    assert "License Rightsizing addresses" in init["business_rationale"]
    assert "annualized run-rate savings" in init["business_rationale"]


def test_enrich_is_idempotent():
    so = _outputs()
    enrich_initiatives_business_detail(so)
    first = copy.deepcopy(so["savings-modeler"]["initiatives"][0])
    enrich_initiatives_business_detail(so)
    second = so["savings-modeler"]["initiatives"][0]
    assert first == second


def test_enrich_degrades_without_spend_profiler():
    so = _outputs()
    del so["spend-profiler"]
    enrich_initiatives_business_detail(so)
    init = so["savings-modeler"]["initiatives"][0]
    # Vendor join degrades to empty, but every other field is still populated.
    assert init["affected_vendors"] == []
    assert init["owner_role"]
    assert init["kpis"]
    assert init["risks"]


def test_enrich_no_initiatives_is_safe():
    so = {"savings-modeler": {"initiatives": []}}
    enrich_initiatives_business_detail(so)  # must not raise
    enrich_initiatives_business_detail({})  # must not raise
    enrich_initiatives_business_detail({"savings-modeler": {}})  # must not raise


def test_enrich_unknown_family_uses_default_owner():
    so = _outputs()
    so["savings-modeler"]["initiatives"][0]["lever_family"] = "weird_family"
    enrich_initiatives_business_detail(so)
    init = so["savings-modeler"]["initiatives"][0]
    assert init["owner_role"] == "Category / Initiative Owner"
