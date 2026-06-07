from __future__ import annotations

from tests.session_test_utils import seed_session_upload

def _sample_spend_csv() -> bytes:
    return (
        "supplier,description,amount,business unit,country\n"
        "Amazon,aws cloud subscription,100000,Engineering,US\n"
        "McKinsey,consulting services,50000,Finance,US\n"
        "Office Depot,office supplies,10000,Operations,US\n"
    ).encode("utf-8")


def test_health(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_session_supports_audience_setting(client) -> None:
    create = client.post(
        "/api/sessions",
        json={
            "company_name": "Audience Co",
            "industry": "technology",
            "annual_revenue": 1_000_000_000,
            "audience": "board",
        },
    )
    assert create.status_code == 200
    payload = create.json()
    assert payload["audience"] == "board"


def test_end_to_end_analysis_and_exports(client) -> None:
    create = client.post(
        "/api/sessions",
        json={"company_name": "Acme Corp", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    assert create.status_code == 200
    session_id = create.json()["session_id"]

    seed_session_upload(session_id, "spend.csv", _sample_spend_csv(), "text/csv")

    schema = client.get(f"/api/schema/{session_id}")
    assert schema.status_code == 200
    payload_schema = schema.json()
    assert len(payload_schema["schemas"]) == 1
    assert payload_schema["schemas"][0]["semantic_map"]["amount"] == "amount"

    seed_session_upload(session_id, "context.txt", b"contract and compliance guardrails", "text/plain")

    analyze = client.post(
        f"/api/analyze/{session_id}",
        json={"company_name": "Acme Corp", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    assert analyze.status_code == 200
    payload = analyze.json()
    assert payload["skill_outputs"]["data-validator"]["passed"] is True
    assert payload["skill_outputs"]["value-bridge-calculator"]["confidence_bands"]["mid"] >= 0

    read_back = client.get(f"/api/sessions/{session_id}")
    assert read_back.status_code == 200
    assert read_back.json()["session_id"] == session_id

    bc = client.post(f"/api/business-case/{session_id}", data={"template": "detailed_proposal"})
    assert bc.status_code == 200
    assert "docx" in bc.json()["exports"]

    dash = client.post(f"/api/dashboard/{session_id}")
    assert dash.status_code == 200
    assert dash.json()["dashboard_url"].startswith("/api/exports/")

    sens = client.get(f"/api/sensitivity/{session_id}")
    assert sens.status_code == 200
    assert len(sens.json()["scenarios"]) == 7
    names = {s["name"] for s in sens.json()["scenarios"]}
    assert names == {"conservative", "base", "accelerated", "delayed", "partial_success", "volume_growth", "bounce_back"}


def test_skills_and_compliance_endpoints(client) -> None:
    skills = client.get("/api/skills")
    assert skills.status_code == 200
    assert len(skills.json()) >= 10

    read_skill = client.get("/api/skills/spend-profiler")
    assert read_skill.status_code == 200
    assert "Spend Profiler" in read_skill.json()["content"]

    test_skill = client.post("/api/skills/spend-profiler/test")
    assert test_skill.status_code == 200
    assert test_skill.json()["status"] == "pass"

    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["skills_discovered"] >= 10

    register = client.get("/api/compliance/risk-register")
    assert register.status_code == 200
    assert "Risk Register" in register.json()["content"]

    privacy = client.get("/api/compliance/privacy-controls")
    assert privacy.status_code == 200
    assert privacy.json()["status"] == "baseline controls implemented"


def test_memory_delete_validation(client) -> None:
    bad = client.delete("/api/memory/notvalid/somekey")
    assert bad.status_code == 400


def test_opar_v1_chat_endpoint(client) -> None:
    create = client.post(
        "/api/sessions",
        json={"company_name": "OPAR Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    seed_session_upload(session_id, "spend.csv", _sample_spend_csv(), "text/csv")

    resp = client.post(
        "/api/v1/chat",
        json={"message": "Run benchmark analysis", "session_id": session_id, "user_id": "opar_co"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "response_text" in data
    assert "advisory_sections" in data
    assert isinstance(data["advisory_sections"], dict)
    assert "quality_signals" in data
    assert "faithfulness_score" in data["quality_signals"]
    assert "relevance_score" in data["quality_signals"]
    assert "grounding_coverage" in data["quality_signals"]
    assert "used_llm_synthesis" in data
    assert "degraded_mode" in data
    assert "fallback_reasons" in data
    assert "loop_complete" in data
    assert "Spend profile" in data["response_text"] or "value bridge" in data["response_text"].lower()
    assert "Benchmarked using" in data["response_text"]
    plan_steps = [s.get("message", "") for s in data.get("progress_steps", []) if s.get("phase") == "plan"]
    selected_line = next((m for m in plan_steps if m.startswith("Selected skills: ")), "")
    assert "Selected skills:" in selected_line
    assert "value-bridge-calculator" not in selected_line
    assert "savings-modeler" not in selected_line


def test_opar_v1_chat_value_bridge_includes_modeling_without_exec_layers(client) -> None:
    create = client.post(
        "/api/sessions",
        json={"company_name": "Value Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    seed_session_upload(session_id, "spend.csv", _sample_spend_csv(), "text/csv")

    resp = client.post(
        "/api/v1/chat",
        json={"message": "Calculate value bridge matrix", "session_id": session_id, "user_id": "value_co"},
    )
    assert resp.status_code == 200
    data = resp.json()
    plan_steps = [s.get("message", "") for s in data.get("progress_steps", []) if s.get("phase") == "plan"]
    selected_line = next((m for m in plan_steps if m.startswith("Selected skills: ")), "")
    assert "value-bridge-calculator" in selected_line
    assert "savings-modeler" in selected_line
    assert "analysis-synthesizer" not in selected_line
    assert "executive-communication" not in selected_line


def test_opar_v1_chat_with_files_endpoint(client) -> None:
    create = client.post(
        "/api/sessions",
        json={"company_name": "With Files Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    payload = {
        "message": (None, "Run benchmark analysis"),
        "session_id": (None, session_id),
        "user_id": (None, "with_files_co"),
        "files": ("spend.csv", _sample_spend_csv(), "text/csv"),
    }
    resp = client.post("/api/v1/chat/with-files", files=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "response_text" in data
    assert isinstance(data.get("uploaded_files", []), list)
    assert "Spend profile" in data["response_text"]


def test_opar_v1_chat_with_txt_file_captures_document_semantics(client) -> None:
    create = client.post(
        "/api/sessions",
        json={"company_name": "Doc Context Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    txt_payload = (
        "Master services agreement includes vendor lock-in constraints.\n"
        "Compliance policy requires PO-first procurement and quarterly reviews.\n"
        "Headcount freeze applies in Q2 and Q3."
    ).encode("utf-8")
    payload = {
        "message": (None, "Give me a summary"),
        "session_id": (None, session_id),
        "user_id": (None, "doc_context_co"),
        "files": ("context.txt", txt_payload, "text/plain"),
    }
    resp = client.post("/api/v1/chat/with-files", files=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "response_text" in data
    assert "summary of uploaded document context" in data["response_text"].lower()
    uploaded = data.get("uploaded_files", [])
    assert isinstance(uploaded, list) and uploaded
    assert uploaded[0].get("file_kind") == "document"
    assert (uploaded[0].get("text_chars") or 0) > 0
    assert uploaded[0].get("rows") is None


def test_opar_v1_chat_open_spend_chart_returns_chart_link(client) -> None:
    create = client.post(
        "/api/sessions",
        json={"company_name": "Chart Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    seed_session_upload(session_id, "spend.csv", _sample_spend_csv(), "text/csv")

    resp = client.post(
        "/api/v1/chat",
        json={"message": "Open spend chart", "session_id": session_id, "user_id": "chart_co"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "response_text" in data
    assert "Open chart view" in data["response_text"]
    assert "/api/exports/" in data["response_text"]


def test_opar_v1_chat_plan_preview(client) -> None:
    """Plan preview returns user_summary without executing."""
    create = client.post(
        "/api/sessions",
        json={"company_name": "Preview Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    seed_session_upload(session_id, "spend.csv", _sample_spend_csv(), "text/csv")
    resp = client.post(
        "/api/v1/chat/plan",
        json={"message": "Run benchmark analysis", "session_id": session_id, "user_id": "preview_co"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "clarification_required" in data
    if not data["clarification_required"]:
        assert data.get("user_summary")
        assert "plan" in data
        assert data["plan"]["total_skills"] >= 1


def test_planning_agent_asks_followups_and_refines_response(client) -> None:
    """OPAR chat: may ask for clarification or suggest next steps via next_loop_trigger."""
    create = client.post(
        "/api/sessions",
        json={"company_name": "Plan Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    seed_session_upload(session_id, "spend.csv", _sample_spend_csv(), "text/csv")

    step1 = client.post(f"/api/chat/{session_id}", json={"message": "We need to reduce procurement costs quickly."})
    assert step1.status_code == 200
    data1 = step1.json()
    assert "assistant_message" in data1 or "response_text" in data1
    msg1 = (data1.get("response_text") or data1.get("assistant_message", "")).lower()
    # OPAR may return clarification (industry/revenue) or run analysis
    assert "spend" in msg1 or "industry" in msg1 or "revenue" in msg1 or "value" in msg1 or "benchmark" in msg1

    step2 = client.post(f"/api/chat/{session_id}", json={"message": "Run benchmark analysis"})
    assert step2.status_code == 200
    data2 = step2.json()
    msg2 = (data2.get("response_text") or data2.get("assistant_message", "")).lower()
    # Should complete analysis or suggest next step
    assert "spend" in msg2 or "value" in msg2 or "benchmark" in msg2 or data2.get("next_loop_trigger")


def test_pipeline_endpoints_lifecycle(client) -> None:
    create = client.post(
        "/api/sessions",
        json={"company_name": "Pipe Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    user_id = "pipe_co"

    manual = client.post(
        "/api/v1/initiatives",
        json={
            "session_id": session_id,
            "user_id": user_id,
            "category": "IT & Technology",
            "lever": "supplier_consolidation",
            "net_npv": 1_200_000,
            "committed_savings": 500_000,
        },
    )
    assert manual.status_code == 200
    initiative_id = manual.json()["initiative_id"]

    stage = client.put(f"/api/v1/initiatives/{initiative_id}/stage", json={"stage": "committed"})
    assert stage.status_code == 200
    assert stage.json()["stage"] == "committed"

    milestone = client.post(
        f"/api/v1/initiatives/{initiative_id}/milestones",
        json={"description": "RFP complete", "due_date": "2020-01-01"},
    )
    assert milestone.status_code == 200

    actual = client.post(
        f"/api/v1/initiatives/{initiative_id}/actuals",
        json={"period": "2026-01", "actual_savings": 100_000, "committed_savings": 500_000},
    )
    assert actual.status_code == 200
    assert actual.json()["variance"] < 0

    listed = client.get("/api/v1/initiatives", params={"user_id": user_id})
    assert listed.status_code == 200
    assert len(listed.json()["initiatives"]) == 1

    summary = client.get("/api/v1/pipeline/summary", params={"user_id": user_id})
    assert summary.status_code == 200
    assert summary.json()["committed"]["count"] >= 1

    at_risk = client.get("/api/v1/pipeline/at-risk", params={"user_id": user_id})
    assert at_risk.status_code == 200
    assert len(at_risk.json()["at_risk"]) >= 1

    rejected = client.put(f"/api/v1/initiatives/{initiative_id}/reject", json={"reason": "No executive sponsorship"})
    assert rejected.status_code == 200
    assert rejected.json()["stage"] == "rejected"


def test_benchmark_registry_endpoints(client) -> None:
    listed = client.get("/api/v1/benchmarks")
    assert listed.status_code == 200
    assert len(listed.json()["datasets"]) >= 1

    created = client.post(
        "/api/v1/benchmarks",
        json={
            "source": "IBISWorld",
            "industry_name": "Technology",
            "category_coverage": {"technology": ["IT", "PROF_SVCS", "MARKETING"]},
            "specificity_score": 0.9,
            "revenue_band_min": 100000000,
            "revenue_band_max": 5000000000,
            "license_expiry": "2099-12-31",
        },
    )
    assert created.status_code == 200
    dataset_id = created.json()["dataset_id"]

    coverage = client.get(f"/api/v1/benchmarks/{dataset_id}/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["dataset_id"] == dataset_id
    assert coverage.json()["industry_count"] >= 1

    selection = client.post(
        "/api/v1/benchmarks/select",
        json={"industry": "technology", "categories": ["IT", "MARKETING"], "annual_revenue": 1000000000},
    )
    assert selection.status_code == 200
    assert selection.json()["selected"] is not None
    assert selection.json()["selection_rationale"]["industry"] == "technology"


def test_analyze_auto_applies_selected_benchmark_dataset(client) -> None:
    client.post(
        "/api/v1/benchmarks",
        json={
            "source": "IBISWorld",
            "industry_name": "Technology",
            "category_coverage": {"technology": ["IT", "PROF_SVCS", "OFFICE"]},
            "specificity_score": 0.95,
            "revenue_band_min": 100000000,
            "revenue_band_max": 5000000000,
            "license_expiry": "2099-12-31",
        },
    )

    create = client.post(
        "/api/sessions",
        json={"company_name": "Bench Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    session_id = create.json()["session_id"]
    seed_session_upload(session_id, "spend.csv", _sample_spend_csv(), "text/csv")

    analyze = client.post(
        f"/api/analyze/{session_id}",
        json={"company_name": "Bench Co", "industry": "technology", "annual_revenue": 1_000_000_000},
    )
    assert analyze.status_code == 200
    payload = analyze.json()
    peer = payload["skill_outputs"]["peer-benchmarker"]
    assert peer["comparisons"]
    assert peer["comparisons"][0]["source"] == "IBISWorld"
    assert peer.get("benchmark_dataset", {}).get("source") == "IBISWorld"


def test_session_with_headcount_field(client) -> None:
    resp = client.post(
        "/api/sessions",
        json={
            "company_name": "HeadcountCo",
            "industry": "technology",
            "annual_revenue": 500_000_000,
            "headcount": 2500,
        },
    )
    assert resp.status_code == 200
    assert resp.json().get("headcount") == 2500
