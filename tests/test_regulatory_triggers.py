from __future__ import annotations

import os

from app.services.reg_watcher import surface_at_reflect_gate, surface_pack_regulatory_events
from app.services.sector_packs import (
    get_pack_regulatory_context,
    list_available_packs,
    parse_regulatory_triggers,
)


SAMPLE_MD = """# Regulatory Layer — Test

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| GST rate change | raw_material_procurement, energy_utilities_plant | HIGH |
| BRSR filing deadline | all | HIGH |
| Minor audit | quality_testing | MEDIUM |
"""


def test_parse_regulatory_triggers_pipe_table():
    triggers = parse_regulatory_triggers(SAMPLE_MD)
    assert len(triggers) == 3
    assert triggers[0]["trigger"] == "GST rate change"
    assert triggers[0]["category_ids"] == ["raw_material_procurement", "energy_utilities_plant"]
    assert triggers[0]["severity"] == "HIGH"
    assert triggers[1]["category_ids"] == ["all"]
    assert triggers[2]["severity"] == "MEDIUM"


def test_get_pack_regulatory_context_bfsi():
    ctx = get_pack_regulatory_context("bfsi_banks")
    assert ctx["pack_id"] == "bfsi_banks"
    assert "RBI" in ctx["regulatory_layer"]
    assert len(ctx["triggers"]) >= 3
    assert "RBI" in ctx["regulatory_bodies"]


def test_surface_pack_regulatory_events_matches_categories():
    events = surface_pack_regulatory_events(
        "pharma_lifesciences",
        ["regulatory_filing_costs", "gmp_validation_costs"],
    )
    assert events
    assert any(ev.get("severity") == "HIGH" for ev in events)
    assert all(ev.get("origin") == "sector_pack_trigger" for ev in events)


def test_surface_at_reflect_gate_includes_pack_events():
    result = surface_at_reflect_gate(
        ["regulatory_filing_costs"],
        pack_id="pharma_lifesciences",
    )
    assert result["events"]
    pack_events = [ev for ev in result["events"] if ev.get("origin") == "sector_pack_trigger"]
    assert pack_events


def test_surface_at_reflect_gate_forced_with_live_and_pack_high():
    prev = os.environ.get("REG_WATCHER_LIVE")
    os.environ["REG_WATCHER_LIVE"] = "1"
    try:
        result = surface_at_reflect_gate(
            ["regulatory_filing_costs"],
            pack_id="pharma_lifesciences",
        )
        assert any(ev.get("severity") == "HIGH" for ev in result["events"])
        assert result["forced_decision"] is True
    finally:
        if prev is None:
            os.environ.pop("REG_WATCHER_LIVE", None)
        else:
            os.environ["REG_WATCHER_LIVE"] = prev


def test_all_packs_have_regulatory_layer():
    primary_regulator_hints = {
        "bfsi_banks": "RBI",
        "manufacturing_diversified": "BIS",
        "insurance_general": "IRDAI",
        "pharma_lifesciences": "CDSCO",
        "healthcare_hospitals": "NABH",
        "telecom_infra": "TRAI",
        "energy_utilities": "CERC",
        "it_ites": "STPI",
        "fmcg_consumer": "FSSAI",
        "retail_organized": "FSSAI",
        "financial_services_nonbank": "SEBI",
        "gcc_capability_centers": "DPDP",
        "hospitality_travel": "FSSAI",
        "psu_cpse": "DPE",
        "conglomerate": "SEBI",
    }
    for pack_id in list_available_packs():
        ctx = get_pack_regulatory_context(pack_id)
        assert ctx["regulatory_layer"].strip(), f"missing regulatory_layer for {pack_id}"
        hint = primary_regulator_hints.get(pack_id, "")
        if hint:
            assert hint in ctx["regulatory_layer"], f"{pack_id} should mention {hint}"
        assert len(ctx["triggers"]) >= 3, f"{pack_id} should have trigger rows"


def test_run_reg_watcher_uses_manifest_industry():
    from app.opar.models import ObserveContext
    from app.opar.reflect_validation import _run_reg_watcher

    validated = {
        "spend-profiler": {
            "category_profile": [
                {"category_id": "regulatory_filing_costs", "spend": 100.0},
            ],
        },
    }
    ctx = ObserveContext(
        user_message="test",
        intent_class="value_bridge",
        has_tabular_spend=True,
        session_id="test-session",
        engagement_week=2,
    )
    forced, events, prompt = _run_reg_watcher(
        validated,
        ctx,
        manifest={"industry": "pharma_lifesciences"},
    )
    assert events
    assert any(ev.get("origin") == "sector_pack_trigger" for ev in events)
    assert prompt


def test_persist_session_analysis_stores_regulatory_events(monkeypatch):
    from app.opar.models import ActResult, ObserveContext
    from app.opar.reflect_persistence import persist_session_analysis

    stored: dict = {}

    class _FakeMemory:
        def get(self, ns, key):
            return stored.get(key)

        def put(self, ns, key, value):
            stored[key] = value

    monkeypatch.setattr("app.opar.reflect_persistence._memory", _FakeMemory())
    ctx = ObserveContext(
        user_message="test",
        intent_class="value_bridge",
        has_tabular_spend=True,
        session_id="persist-reg-test",
        engagement_week=1,
    )
    reg_events = [{"event_id": "PACK_test", "title": "Test regulatory event"}]
    persist_session_analysis(
        ctx=ctx,
        act_result=ActResult(skill_outputs={}, errors={}, degradation_reasons={}),
        validated={"spend-profiler": {"total_spend": 1.0}},
        manifest={"industry": "pharma_lifesciences", "company_name": "TestCo"},
        reporting_currency="INR",
        advisory_sections=None,
        regulatory_events=reg_events,
    )
    snapshot = stored["persist-reg-test"]
    assert snapshot["regulatory_events"] == reg_events

