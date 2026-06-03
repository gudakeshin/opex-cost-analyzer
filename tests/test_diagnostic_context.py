from __future__ import annotations

from app.routers._shared import read_manifest
from app.routers.enterprise import _category_display_name


def test_category_display_name_uses_taxonomy() -> None:
    assert _category_display_name("RND") == "R&D & Engineering"
    assert _category_display_name("IT") == "IT & Technology"
    assert _category_display_name("PROF_SVCS") == "Professional Services"
    assert _category_display_name("RELATED_PARTY") == "Related-Party & Intercompany"


def test_company_research_benchmark_gap_fields(client) -> None:
    resp = client.post(
        "/api/v1/diagnostic/company-research",
        json={
            "company_name": "Readability Test Co",
            "industry": "it_ites",
            "annual_revenue_cr": 2000.0,
            "urls": [],
            "headcount": 5000,
            "wacc": 0.12,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    gaps = body.get("benchmark_gaps", [])
    assert gaps, "expected non-empty benchmark gaps for it_ites"

    rnd = next((g for g in gaps if g.get("category") == "RND"), None)
    assert rnd is not None
    assert rnd["category_name"] == "R&D & Engineering"
    assert rnd["benchmark_p50_to_p25_band_cr"] == rnd["headroom_to_p25_cr"]
    assert rnd["benchmark_p50_to_p25_band_cr"] > 0
    assert isinstance(rnd.get("commentary"), str) and len(rnd["commentary"]) > 20

    levers = body.get("value_at_table", [])
    assert levers, "expected non-empty value_at_table for it_ites"
    lever = levers[0]
    assert isinstance(lever.get("rationale"), str) and len(lever["rationale"]) > 20
    assert isinstance(lever.get("calculation_note"), str) and "Expected (P50)" in lever["calculation_note"]
    assert isinstance(lever.get("value_derivation"), dict)
    assert lever["value_derivation"].get("base_spend_cr", 0) > 0
    assert lever["value_derivation"].get("savings_rate_p50_pct", 0) > 0

    methodology = body.get("value_at_table_methodology", {})
    assert methodology.get("steps")
    assert methodology.get("shown_levers") == len(levers)


def test_diagnostic_context_patch_round_trip(client) -> None:
    create = client.post(
        "/api/v1/sessions",
        json={
            "company_name": "Diag Co",
            "industry": "it_ites",
            "annual_revenue": 50_000_000_000,
            "currency": "INR",
            "audience": "consultant",
        },
    )
    assert create.status_code == 200
    session_id = create.json()["session_id"]

    diagnostic_result = {
        "company_name": "Diag Co",
        "industry_used": "it_ites",
        "annual_revenue_cr": 5000.0,
        "key_findings": ["Finding one"],
        "benchmark_gaps": [{"category": "it_cloud", "p50_pct": 4.2}],
        "value_at_table": [{"lever_name": "Cloud rightsizing", "p50_cr": 12.0}],
        "company_signals": {},
    }
    urls = ["https://example.com/annual-report"]

    patch = client.patch(
        f"/api/v1/sessions/{session_id}/diagnostic-context",
        json={
            "company_name": "Diag Co",
            "industry": "it_ites",
            "annual_revenue_cr": 5000.0,
            "diagnostic_urls": urls,
            "diagnostic_result": diagnostic_result,
            "diagnostic_completed_at": "2026-06-03T12:00:00+00:00",
            "deep_research_summary": "Summary text",
            "deep_research_interaction_id": "job-abc-123",
        },
    )
    assert patch.status_code == 200
    assert patch.json()["ok"] is True

    manifest_resp = client.get(f"/api/v1/sessions/{session_id}/manifest")
    assert manifest_resp.status_code == 200
    manifest = manifest_resp.json()
    assert manifest["diagnostic_urls"] == urls
    assert manifest["diagnostic_result"]["company_name"] == "Diag Co"
    assert manifest["diagnostic_completed_at"] == "2026-06-03T12:00:00+00:00"
    assert manifest["deep_research_summary"] == "Summary text"
    assert manifest["deep_research_interaction_id"] == "job-abc-123"

    on_disk = read_manifest(session_id)
    assert on_disk["diagnostic_result"]["key_findings"] == ["Finding one"]
