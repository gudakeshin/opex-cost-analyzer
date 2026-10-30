"""Tests for Cost Room plan improvements: seeding, provenance, PMO export."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.initiative_provenance import build_initiative_provenance
from app.services.pipeline_seed import seed_initiatives_from_analysis


def test_seed_initiatives_from_analysis_creates_rows(tmp_path, monkeypatch):
    store = tmp_path / "store.json"
    monkeypatch.setattr("app.services.pipeline.PIPELINE_PATH", store)

    analysis = {
        "company_name": "Acme Corp",
        "skill_outputs": {
            "value-bridge-calculator": {
                "value_matrix": [
                    {
                        "category_id": "cloud",
                        "category_name": "Cloud",
                        "lever": "optimization",
                        "gross_savings_y1": 100.0,
                        "gross_savings_y2": 120.0,
                        "gross_savings_y3": 140.0,
                        "net_npv": 250.0,
                    }
                ]
            },
            "savings-modeler": {"modeled_initiatives": []},
        },
    }

    with patch("app.services.business_case.build_business_case") as mock_bc:
        mock_bc.return_value = {
            "sections": {
                "initiative_details": [
                    {
                        "category_name": "Cloud",
                        "lever": "optimization",
                        "gross_savings_y1": 100.0,
                        "p50_savings": 100.0,
                    }
                ]
            }
        }
        created = seed_initiatives_from_analysis(analysis, "sess-1", user_id="acme_corp")

    assert created == 1
    created_again = seed_initiatives_from_analysis(analysis, "sess-1", user_id="acme_corp")
    assert created_again == 0


def test_build_initiative_provenance_traces_spend_rows(monkeypatch):
    initiative = {
        "initiative_id": "ini-1",
        "category": "Cloud",
        "lever": "optimization",
        "session_id": "sess-1",
        "p50_savings": 50.0,
    }
    analysis = {
        "revision": 2,
        "normalized_spend": [
            {
                "row_id": 10,
                "supplier": "AWS",
                "category_name": "Cloud",
                "category_id": "cloud",
                "amount_reporting": 1_000_000.0,
                "fiscal_period": "2024-01",
            },
            {
                "row_id": 11,
                "supplier": "Other",
                "category_name": "Marketing",
                "amount_reporting": 500_000.0,
            },
        ],
        "skill_outputs": {},
    }

    monkeypatch.setattr(
        "app.services.initiative_provenance.read_manifest",
        lambda _sid: {
            "files": [{"original_name": "spend.csv", "path": "uploads/sess-1/spend.csv"}],
            "ingestion_summary": "12 months parsed",
        },
    )

    prov = build_initiative_provenance(initiative, analysis, "sess-1")
    assert prov["initiative_id"] == "ini-1"
    assert len(prov["source_spend_rows"]) == 1
    assert prov["source_spend_rows"][0]["supplier"] == "AWS"
    assert len(prov["source_files"]) == 1
    assert prov["trace_steps"][0]["step"] == 1


def test_pmo_export_endpoint_requires_analysis(client, monkeypatch):
    import uuid

    session_id = str(uuid.uuid4())
    monkeypatch.setattr(
        "app.routers.outputs._memory",
        type("M", (), {"get": staticmethod(lambda _k, _s: None)})(),
    )
    resp = client.post(f"/api/v1/pmo-export/{session_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# FP&A endpoint contract: 200 + {*_available: False, reason} when skill missing
# ---------------------------------------------------------------------------

_FPA_ENDPOINTS = [
    ("/api/v1/trends/{sid}", "temporal_available", "period_trends"),
    ("/api/v1/bva/{sid}", "bva_available", "variances"),
    ("/api/v1/payment-terms/{sid}", "payment_terms_available", "opportunities"),
]


def _stub_memory(monkeypatch, analysis):
    monkeypatch.setattr(
        "app.routers.outputs._memory",
        type("M", (), {"get": staticmethod(lambda _k, _s: analysis)})(),
    )


@pytest.mark.parametrize("path_tpl,flag_key,list_key", _FPA_ENDPOINTS)
def test_fpa_endpoint_404_without_analysis(client, monkeypatch, path_tpl, flag_key, list_key):
    import uuid

    _stub_memory(monkeypatch, None)
    resp = client.get(path_tpl.format(sid=str(uuid.uuid4())))
    assert resp.status_code == 404


@pytest.mark.parametrize("path_tpl,flag_key,list_key", _FPA_ENDPOINTS)
def test_fpa_endpoint_unavailable_shape_when_skill_missing(
    client, monkeypatch, path_tpl, flag_key, list_key
):
    import uuid

    _stub_memory(monkeypatch, {"skill_outputs": {}})
    resp = client.get(path_tpl.format(sid=str(uuid.uuid4())))
    assert resp.status_code == 200
    body = resp.json()
    assert body[flag_key] is False
    assert body["reason"]
    assert body[list_key] == []


def test_fpa_endpoint_passthrough_when_skill_present(client, monkeypatch):
    import uuid

    temporal = {"temporal_available": True, "period_count": 12, "period_trends": []}
    _stub_memory(monkeypatch, {"skill_outputs": {"temporal-analyzer": temporal}})
    resp = client.get(f"/api/v1/trends/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json()["period_count"] == 12


# ---------------------------------------------------------------------------
# Sensitivity endpoint: query parameter bounds
# ---------------------------------------------------------------------------

def test_sensitivity_rejects_out_of_bounds_params(client, monkeypatch):
    import uuid

    sid = str(uuid.uuid4())
    _stub_memory(monkeypatch, {"skill_outputs": {}})
    assert client.get(f"/api/v1/sensitivity/{sid}?discount_rate=0.9").status_code == 422
    assert client.get(f"/api/v1/sensitivity/{sid}?execution_rate_pct=5").status_code == 422
    assert client.get(f"/api/v1/sensitivity/{sid}?effective_tax_rate=0.95").status_code == 422


def test_sensitivity_accepts_in_bounds_params(client, monkeypatch):
    import uuid

    bridge = {"confidence_bands": {"low": 80.0, "mid": 100.0, "high": 120.0}}
    _stub_memory(
        monkeypatch,
        {"skill_outputs": {"value-bridge-calculator": bridge, "savings-modeler": {}}},
    )
    resp = client.get(f"/api/v1/sensitivity/{uuid.uuid4()}?execution_rate_pct=0.6")
    assert resp.status_code == 200
    assert "scenarios" in resp.json()


# ---------------------------------------------------------------------------
# PMO export: milestone gates scale with engagement length
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "weeks,expected",
    [(8, [2, 4, 6, 8]), (12, [3, 6, 9, 12]), (24, [6, 12, 18, 24])],
)
def test_pmo_gate_weeks_scale_with_engagement_weeks(weeks, expected):
    from app.services.pmo_export import build_pmo_data

    pmo = build_pmo_data({}, [], engagement_weeks=weeks)
    calendar = pmo["milestone_calendar"]
    assert [m["week"] for m in calendar] == expected
    assert calendar[0]["milestone"].startswith("Gate-1")
    assert calendar[0]["deliverable"] == "CFO brief"
    assert calendar[-1]["milestone"].startswith("Gate-4")
    assert calendar[-1]["deliverable"] == "MOR pack + tear-down"


# ---------------------------------------------------------------------------
# Cost-to-serve: fuzzy segment matching + allocation method
# ---------------------------------------------------------------------------

def _spend_line(row_id, supplier, description, amount, cost_center=None):
    from app.models import NormalizedSpendLine

    return NormalizedSpendLine(
        row_id=row_id,
        supplier=supplier,
        description=description,
        amount=amount,
        category_id="general",
        category_name="General",
        cost_center_id=cost_center,
    )


def test_cost_to_serve_matches_punctuated_and_fuzzy_segments():
    from app.skills.engine.strategic import cost_to_serve_analyzer

    lines = [
        _spend_line(1, "TechVendor", "I.T. Services retainer", 100.0),
        _spend_line(2, "RetailCo", "Enterprize support contract", 50.0),  # typo
        _spend_line(3, "Misc", "Stationery purchase", 25.0),
    ]
    out = cost_to_serve_analyzer(lines, segment_revenue={"IT": 1000.0, "Enterprise": 500.0})
    seg = {s["segment"]: s for s in out["segments"]}
    assert seg["IT"]["direct_cost"] == 100.0
    assert seg["Enterprise"]["direct_cost"] == 50.0
    quality = out["attribution_quality"]
    assert quality["direct_pct"] > 0
    assert quality["fuzzy_matched_pct"] > 0
    assert quality["unattributed_pct"] > 0


def test_cost_to_serve_matches_cost_center_id():
    from app.skills.engine.strategic import cost_to_serve_analyzer

    lines = [_spend_line(1, "Acme", "Misc services", 80.0, cost_center="CC-RETAIL-01")]
    out = cost_to_serve_analyzer(
        lines, segment_revenue={"Retail": 500.0, "Wholesale": 500.0},
    )
    seg = {s["segment"]: s for s in out["segments"]}
    assert seg["Retail"]["direct_cost"] == 80.0
    assert seg["Wholesale"]["direct_cost"] == 0.0


def test_cost_to_serve_allocation_methods():
    from app.skills.engine.strategic import cost_to_serve_analyzer

    lines = [_spend_line(1, "Misc", "Unmatched spend", 100.0)]
    segs = {"North": 900.0, "South": 100.0}

    by_revenue = cost_to_serve_analyzer(lines, segment_revenue=segs)
    rev = {s["segment"]: s for s in by_revenue["segments"]}
    assert rev["North"]["indirect_cost_allocated"] == 90.0
    assert rev["South"]["indirect_cost_allocated"] == 10.0
    assert by_revenue["attribution_quality"]["allocation_method"] == "revenue"

    equal = cost_to_serve_analyzer(lines, segment_revenue=segs, allocation_method="equal")
    eq = {s["segment"]: s for s in equal["segments"]}
    assert eq["North"]["indirect_cost_allocated"] == 50.0
    assert eq["South"]["indirect_cost_allocated"] == 50.0
    assert equal["attribution_quality"]["allocation_method"] == "equal"


def test_cost_to_serve_exact_match_behavior_unchanged():
    from app.skills.engine.strategic import cost_to_serve_analyzer

    lines = [_spend_line(1, "AWS", "Cloud hosting fees", 200.0)]
    out = cost_to_serve_analyzer(lines, segment_revenue={"Cloud": 1000.0})
    seg = {s["segment"]: s for s in out["segments"]}
    assert seg["Cloud"]["direct_cost"] == 200.0


# ---------------------------------------------------------------------------
# Engagement-scoped pipeline + qualification gate
# ---------------------------------------------------------------------------

def test_list_initiatives_engagement_filter(tmp_path, monkeypatch):
    from app.services import pipeline

    monkeypatch.setattr("app.services.pipeline.PIPELINE_PATH", tmp_path / "store.json")

    monkeypatch.setattr(
        "app.services.pipeline._engagement_session_ids",
        lambda eid: {"sess-a", "sess-b"} if eid == "eng-1" else set(),
    )

    pipeline.create_initiative(
        {
            "category": "Cloud",
            "lever": "optimization",
            "session_id": "sess-a",
            "engagement_id": "eng-1",
            "p50_savings": 100.0,
        },
    )
    pipeline.create_initiative(
        {
            "category": "Travel",
            "lever": "policy",
            "session_id": "sess-other",
            "p50_savings": 50.0,
        },
    )
    pipeline.create_initiative(
        {
            "category": "Facilities",
            "lever": "consolidation",
            "session_id": "sess-b",
            "engagement_id": "eng-1",
            "gross_savings_y1": 0.0,
            "net_npv": 0.0,
            "p50_savings": 0.0,
        },
    )

    all_rows = pipeline.list_initiatives()
    assert len(all_rows) == 3

    eng_rows = pipeline.list_initiatives(engagement_id="eng-1")
    assert len(eng_rows) == 2

    qualified = pipeline.list_initiatives(engagement_id="eng-1", qualified_only=True)
    assert len(qualified) == 1
    assert qualified[0]["category"] == "Cloud"


def test_seed_skips_zero_value_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.pipeline.PIPELINE_PATH", tmp_path / "store.json")

    analysis = {"company_name": "Acme Corp", "engagement_id": "eng-seed"}
    with patch("app.services.pipeline_seed.build_business_case") as mock_bc:
        mock_bc.return_value = {
            "sections": {
                "initiative_details": [
                    {"category_name": "Empty", "lever": "optimization", "gross_savings_y1": 0.0},
                    {"category_name": "Real", "lever": "optimization", "p50_savings": 80.0},
                ]
            }
        }
        created = seed_initiatives_from_analysis(analysis, "sess-seed-zero", user_id="acme_corp")

    assert created == 1
    from app.services.pipeline import list_initiatives

    rows = list_initiatives(session_id="sess-seed-zero")
    assert len(rows) == 1
    assert rows[0]["category"] == "Real"
    assert rows[0].get("engagement_id") == "eng-seed"


def test_analyze_persists_last_analysis_run_summary(client, monkeypatch):
    from app.models import NormalizedSpendLine
    from app.routers import sessions as sessions_router

    created = client.post(
        "/api/v1/sessions",
        json={"company_name": "Acme Corp", "industry": "technology", "currency": "INR"},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    fake_line = NormalizedSpendLine(
        row_id=1,
        supplier="Supplier A",
        description="Cloud service",
        amount=100.0,
        category_id="cloud",
        category_name="Cloud",
    )

    def _fake_load_analysis_corpus(_sid: str):
        manifest = sessions_router.read_manifest(session_id)
        return [fake_line], [], [], [], manifest

    def _fake_run_core_pipeline(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "reporting_currency": "INR",
            "analysis_trace": [
                {
                    "step": 1,
                    "phase": "act",
                    "title": "Profiled spend",
                    "detail": "Profiled one category.",
                    "source_documents": [],
                }
            ],
            "skill_outputs": {
                "spend-profiler": {"total_spend": 100.0},
                "savings-modeler": {"initiatives": [{"category_name": "Cloud"}]},
            },
        }

    monkeypatch.setattr("app.routers.sessions.load_analysis_corpus", _fake_load_analysis_corpus)
    monkeypatch.setattr("app.routers.sessions.run_core_pipeline", _fake_run_core_pipeline)
    monkeypatch.setattr("app.routers.sessions.seed_initiatives_from_analysis", lambda *_a, **_k: 1)

    resp = client.post(f"/api/v1/analyze/{session_id}", json={"run_id": "run-test-123"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    summary = body.get("last_analysis_run") or {}
    assert summary.get("run_id") == "run-test-123"
    assert summary.get("status") == "completed"
    assert summary.get("pipeline_seeded") == 1
    assert summary.get("trace_step_count") == 1
    assert summary.get("total_spend") == pytest.approx(100.0)
    assert summary.get("modelled_initiatives") == 1
    assert summary.get("progress_steps")

    persisted = sessions_router._memory.get("session", session_id) or {}
    assert persisted.get("last_analysis_run", {}).get("run_id") == "run-test-123"



def test_initiative_change_log_records_mutations(tmp_path, monkeypatch):
    from app.services import pipeline

    monkeypatch.setattr("app.services.pipeline.PIPELINE_PATH", tmp_path / "store.json")

    created = pipeline.create_initiative(
        {"category": "Cloud", "lever": "optimization", "session_id": "sess-1"},
    )
    initiative_id = created["initiative_id"]
    assert [e["action"] for e in created["change_log"]] == ["created"]

    pipeline.update_initiative_stage(initiative_id, "committed")
    pipeline.add_milestone(initiative_id, {"description": "Kickoff", "due_date": "2026-07-01"})
    pipeline.add_actual(initiative_id, {"period": "2026-07", "actual_savings": 5.0})

    # Log survives the store round-trip via a fresh read.
    row = pipeline.list_initiatives(session_id="sess-1")[0]
    actions = [e["action"] for e in row["change_log"]]
    assert actions == ["created", "stage_change", "milestone_added", "actuals_recorded"]
    stage_entry = row["change_log"][1]
    assert stage_entry["detail"] == {"from": "identified", "to": "committed"}
    actuals_entry = row["change_log"][3]
    assert actuals_entry["detail"]["actual_savings"] == 5.0
    assert all(e.get("ts") for e in row["change_log"])

    pipeline.reject_initiative(initiative_id, "duplicate of other initiative")
    row = pipeline.list_initiatives(session_id="sess-1")[0]
    assert row["change_log"][-1]["action"] == "rejected"
    assert row["change_log"][-1]["detail"]["reason"] == "duplicate of other initiative"


def test_initiative_change_log_capped(tmp_path, monkeypatch):
    from app.services import pipeline

    monkeypatch.setattr("app.services.pipeline.PIPELINE_PATH", tmp_path / "store.json")

    created = pipeline.create_initiative({"category": "Cloud", "lever": "optimization"})
    initiative_id = created["initiative_id"]
    for i in range(105):
        stage = "committed" if i % 2 == 0 else "in_flight"
        pipeline.update_initiative_stage(initiative_id, stage)

    row = pipeline.list_initiatives()[0]
    assert len(row["change_log"]) == 100
    # The newest entry is retained.
    assert row["change_log"][-1]["action"] == "stage_change"
