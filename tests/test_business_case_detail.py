"""Business-case depth: LLM advisory wiring (Layer B), deterministic fallback,
per-initiative detail, persistence and document rendering."""
from __future__ import annotations

from unittest.mock import patch

from app.opar.models import AdvisoryActionItem, AdvisoryBusinessLever, AdvisorySections
from app.services import business_case as bc_mod
from app.services.business_case import (
    build_business_case,
    build_initiative_details,
    export_docx,
    export_pdf_like_text,
)
from app.skills.engine.business_detail import enrich_initiatives_business_detail


def _analysis():
    outputs = {
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
                    "confidence": "medium",
                    "root_cause": "Shelfware above peer norm",
                    "horizon": "tactical",
                    "payback_months": 6,
                    "annualized_run_rate_savings": 250000.0,
                    "ebitda_impact": {"ebitda_bps": 12.5},
                    "gross_savings": {"y1": 100.0, "y2": 150.0, "y3": 150.0, "total_3yr": 400.0},
                    "cost_to_achieve": {"total_3yr": 40.0},
                    "net_savings": {"npv_10pct": 320.0, "total_3yr": 360.0},
                    "irr_pct": 45.0,
                    "diagnostic_signals": [{"signal": "Enterprise agreement expiring within 9 months"}],
                }
            ]
        },
        "value-bridge-calculator": {
            "confidence_bands": {"low": 300.0, "mid": 360.0, "high": 420.0},
            "value_matrix": [
                {
                    "category_id": "IT",
                    "category_name": "IT & Telecom",
                    "lever": "license_rightsizing",
                    "root_cause": "Shelfware",
                    "gross_3yr": 400.0,
                    "cost_to_achieve_3yr": 40.0,
                    "net_npv": 320.0,
                    "payback_months": 6,
                    "confidence": "medium",
                    "deduped_mid_savings": 360.0,
                }
            ],
        },
    }
    enrich_initiatives_business_detail(outputs)
    return {
        "company_name": "Acme",
        "industry": "it services",
        "annual_revenue": 50000.0,
        "reporting_currency": "INR",
        "skill_outputs": outputs,
    }


def _advisory():
    return AdvisorySections(
        executive_takeaway="Acme can release a material run-rate by retiring shelfware now.",
        category_focus_section="Paragraph one names Oracle and the spend gap. Paragraph two sets out the renegotiation. " * 3,
        quick_wins_from_data=["Retire unused Oracle seats", "Lock the renewal-window discount"],
        business_levers=[
            AdvisoryBusinessLever(
                lever_name="License Rightsizing",
                what_changes="Remove shelfware and renegotiate the Oracle enterprise agreement at renewal.",
                why_it_works="Seat utilization is below 60% versus the peer norm of 85%.",
                evidence=["Oracle holds 60% of category spend", "EA expires within 9 months"],
            )
        ],
        executive_callouts=["~₹250k of annual run-rate is at risk without action."],
        priority_actions_30_60_90=[
            AdvisoryActionItem(timeline="30", action="Baseline license utilization", expected_impact="Confirm shelfware"),
            AdvisoryActionItem(timeline="60", action="Open EA renegotiation", expected_impact="Lock discount"),
        ],
    )


# --- LLM path (mocked advisory) ------------------------------------------------

def test_business_case_includes_llm_sections():
    with patch.object(bc_mod, "_llm_advisory_sections", return_value=_advisory()):
        bc = build_business_case(_analysis())
    secs = bc["sections"]
    assert secs["business_levers"][0]["lever_name"] == "License Rightsizing"
    assert secs["priority_actions_30_60_90"][0]["timeline"] == "30"
    assert secs["quick_wins"]
    assert secs["executive_callouts"]
    assert "release a material run-rate" in secs["executive_summary"]
    assert "Oracle" in secs["strategic_context"]


def test_llm_business_lever_sharpens_initiative_rationale():
    with patch.object(bc_mod, "_llm_advisory_sections", return_value=_advisory()):
        bc = build_business_case(_analysis())
    detail = bc["sections"]["initiative_details"][0]
    assert "renegotiate the Oracle enterprise agreement" in detail["business_rationale"]
    assert "EA expires within 9 months" in detail["evidence"]


# --- Offline / deterministic fallback -----------------------------------------

def test_business_case_offline_keeps_depth():
    with patch.object(bc_mod, "_llm_advisory_sections", return_value=None):
        bc = build_business_case(_analysis())
    secs = bc["sections"]
    # No LLM levers, but deterministic detail + a 30/60/90 fallback are present.
    assert secs["business_levers"] == []
    assert secs["priority_actions_30_60_90"], "deterministic 30/60/90 fallback expected"
    assert secs["strategic_context"], "deterministic strategic context expected"
    detail = secs["initiative_details"][0]
    assert detail["owner_role"]
    assert detail["affected_vendors"]
    assert detail["risks"]
    assert detail["kpis"]
    # Deterministic rationale survives.
    assert "License Rightsizing addresses" in detail["business_rationale"]


def test_initiative_details_carry_financials():
    details = build_initiative_details(_analysis()["skill_outputs"])
    d = details[0]
    assert d["gross_savings_y1"] == 100.0
    assert d["net_npv"] == 320.0
    assert d["p50_savings"] == 360.0
    assert d["payback_months"] == 6


# --- Persistence through the endpoint -----------------------------------------

def test_business_case_persists_business_detail(client):
    # Seed a session whose skill_outputs already carry modeled (and enriched)
    # initiatives, then exercise the real business-case endpoint → persistence
    # wiring (outputs.py loop + create_initiative).
    from app.routers._shared import _memory

    create = client.post(
        "/api/sessions",
        json={"company_name": "Acme Corp", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    analysis = _analysis()
    analysis["session_id"] = session_id
    _memory.put("session", session_id, analysis)

    bc = client.post(f"/api/business-case/{session_id}", data={"template": "detailed_proposal"})
    assert bc.status_code == 200
    secs = bc.json()["business_case"]["sections"]
    assert secs["initiative_details"], "expected per-initiative detail"

    inits = client.get("/api/v1/initiatives").json()["initiatives"]
    assert inits, "expected persisted initiatives"
    enriched = [i for i in inits if i.get("owner_role") or i.get("kpis") or i.get("affected_vendors")]
    assert enriched, "persisted initiatives should carry business detail"
    sample = enriched[0]
    assert sample["owner_role"] == "Chief Information Officer / IT Finance Lead"
    assert sample["affected_vendors"][0]["supplier"] == "Oracle"
    assert sample["risks"]
    assert sample["change_management"]["stakeholders"]
    assert sample["kpis"]


# --- Document rendering --------------------------------------------------------

def test_docx_and_text_render_business_detail(tmp_path):
    with patch.object(bc_mod, "_llm_advisory_sections", return_value=_advisory()):
        bc = build_business_case(_analysis())
    with patch.object(bc_mod, "OUTPUT_DIR", tmp_path):
        docx_path = export_docx(bc, "bc.docx")
        txt_path = export_pdf_like_text(bc, "bc.txt")
    assert docx_path.exists()
    text = txt_path.read_text(encoding="utf-8")
    assert "Oracle" in text                      # affected vendor
    assert "Chief Information Officer" in text    # owner
    assert "KPI:" in text                         # kpis
    assert "Risk [" in text                       # risk register
