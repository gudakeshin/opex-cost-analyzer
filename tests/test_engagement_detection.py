"""Tests for auto-detected company/industry on engagement manifests."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.models import NormalizedSpendLine
from app.services.engagement_detection import detect_engagement_profile
from app.services.engagements_store import (
    create_engagement_manifest,
    update_engagement_detection,
    write_engagement_manifest,
)


def _patch_engagements_dir(monkeypatch, tmp_path: Path) -> Path:
    eng_dir = tmp_path / "engagements"
    eng_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.config.ENGAGEMENTS_DIR", eng_dir)
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", eng_dir)
    return eng_dir


def _write_spend_cache(engagement_id: str, document_id: str, lines: list[NormalizedSpendLine]) -> None:
    from app.services.engagements_store import document_dir

    parsed = document_dir(engagement_id, document_id) / "parsed"
    parsed.mkdir(parents=True, exist_ok=True)
    payload = [line.model_dump(mode="json") for line in lines]
    (parsed / "spend_lines.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_markdown_cache(engagement_id: str, document_id: str, text: str) -> None:
    from app.services.engagements_store import document_dir

    parsed = document_dir(engagement_id, document_id) / "parsed"
    parsed.mkdir(parents=True, exist_ok=True)
    (parsed / "markdown.md").write_text(text, encoding="utf-8")


def _ready_doc(
    *,
    document_id: str,
    filename: str,
    role: str,
) -> dict:
    return {
        "document_id": document_id,
        "filename": filename,
        "role": role,
        "status": "ready",
        "line_count": 1,
    }


def test_detect_company_from_filename(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    manifest = create_engagement_manifest(engagement_id=eid)
    manifest["documents"] = [
        _ready_doc(
            document_id="d1",
            filename="Belrise_Detailed_Spend_Report_FY25.xlsx",
            role="spend_tabular",
        ),
    ]
    write_engagement_manifest(eid, manifest)

    result = detect_engagement_profile(eid)
    assert result["detected_company_name"] == "Belrise"


def test_detect_industry_from_spend_heuristic(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    doc_id = "d-spend"
    create_engagement_manifest(engagement_id=eid)
    lines = [
        NormalizedSpendLine(
            row_id=1,
            supplier="Logistics Co",
            description="Primary freight and distribution",
            amount=10_000_000,
            category_id="LOGISTICS",
            category_name="Logistics",
        ),
        NormalizedSpendLine(
            row_id=2,
            supplier="Pack Co",
            description="Consumer packaging materials",
            amount=6_000_000,
            category_id="PACKAGING",
            category_name="Packaging",
        ),
    ]
    _write_spend_cache(eid, doc_id, lines)
    manifest = create_engagement_manifest(engagement_id=eid)
    manifest["documents"] = [
        _ready_doc(document_id=doc_id, filename="spend.csv", role="spend_tabular"),
    ]
    write_engagement_manifest(eid, manifest)

    result = detect_engagement_profile(eid)
    assert result["industry_spend"] == "fmcg_consumer"
    assert result["detected_industry"] == "fmcg_consumer"
    assert result["industry_source"] == "spend"


def test_llm_industry_takes_precedence_over_spend(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    spend_id, ctx_id = "d-spend", "d-ctx"
    create_engagement_manifest(engagement_id=eid)

    lines = [
        NormalizedSpendLine(
            row_id=1,
            supplier="IT Co",
            description="ERP license",
            amount=1_000_000,
            category_id="IT_SOFTWARE",
            category_name="IT Software",
        ),
    ]
    _write_spend_cache(eid, spend_id, lines)
    _write_markdown_cache(eid, ctx_id, "HUL is a leading FMCG company in India.")

    manifest = create_engagement_manifest(engagement_id=eid)
    manifest["documents"] = [
        _ready_doc(document_id=spend_id, filename="spend.csv", role="spend_tabular"),
        _ready_doc(document_id=ctx_id, filename="strategy.txt", role="context_doc"),
    ]
    write_engagement_manifest(eid, manifest)

    monkeypatch.setattr(
        "app.services.engagement_detection.profiler.document_contextualizer",
        lambda texts: {"inferred_industry": "fmcg_consumer"},
    )

    result = detect_engagement_profile(eid)
    assert result["detected_industry"] == "fmcg_consumer"
    assert result["industry_source"] == "llm"
    assert "strategy.txt" in result["source_documents"]["industry"]


def test_llm_result_cached_by_context_hash(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    ctx_id = "d-ctx"
    create_engagement_manifest(engagement_id=eid)
    _write_markdown_cache(eid, ctx_id, "Stable context about a GCC capability center.")

    manifest = create_engagement_manifest(engagement_id=eid)
    manifest["documents"] = [
        _ready_doc(document_id=ctx_id, filename="context.txt", role="context_doc"),
    ]
    write_engagement_manifest(eid, manifest)

    calls: list[int] = []

    def _fake_contextualizer(texts: list[str]) -> dict:
        calls.append(1)
        return {"inferred_industry": "gcc_capability_centers"}

    monkeypatch.setattr(
        "app.services.engagement_detection.profiler.document_contextualizer",
        _fake_contextualizer,
    )

    first = detect_engagement_profile(eid)
    assert first["detected_industry"] == "gcc_capability_centers"
    assert len(calls) == 1

    # Persist hash + cached LLM on manifest (as update_engagement_detection would).
    update_engagement_detection(eid, first)

    second = detect_engagement_profile(eid)
    assert second["detected_industry"] == "gcc_capability_centers"
    assert len(calls) == 1, "LLM should not be called again when context hash is unchanged"


def test_update_engagement_detection_auto_applies_only_when_unset(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    create_engagement_manifest(engagement_id=eid, company_name="New engagement", industry="")

    updated = update_engagement_detection(
        eid,
        {
            "detected_company_name": "Belrise",
            "detected_industry": "manufacturing_diversified",
            "detected_industry_label": "Manufacturing (Diversified)",
            "industry_source": "spend",
            "industry_llm": "",
            "industry_spend": "manufacturing_diversified",
            "context_text_hash": "",
            "source_documents": {},
        },
    )
    assert updated["company_name"] == "Belrise"
    assert updated["industry"] == "manufacturing_diversified"
    assert updated["detected_company_name"] == "Belrise"

    # Explicit user choice must not be overwritten.
    update_engagement_detection(
        eid,
        {
            "detected_company_name": "Acme",
            "detected_industry": "it_ites",
            "detected_industry_label": "IT / ITES",
            "industry_source": "llm",
            "industry_llm": "it_ites",
            "industry_spend": "",
            "context_text_hash": "abc",
            "source_documents": {},
        },
    )
    manifest = update_engagement_detection(
        eid,
        {
            "detected_company_name": "Acme",
            "detected_industry": "it_ites",
            "detected_industry_label": "IT / ITES",
            "industry_source": "llm",
            "industry_llm": "it_ites",
            "industry_spend": "",
            "context_text_hash": "abc",
            "source_documents": {},
        },
    )
    assert manifest["company_name"] == "Belrise"
    assert manifest["industry"] == "manufacturing_diversified"
    assert manifest["detected_company_name"] == "Acme"
    assert manifest["detected_industry"] == "it_ites"


def test_context_doc_company_overrides_budget_filename(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    spend_id, ctx_id = "d-spend", "d-ctx"
    create_engagement_manifest(engagement_id=eid)

    _write_markdown_cache(
        eid,
        ctx_id,
        "Aranya Digital Services Ltd — FY26 Cost Optimisation Mandate (CFO memo)\n",
    )

    manifest = create_engagement_manifest(engagement_id=eid)
    manifest["documents"] = [
        _ready_doc(
            document_id=spend_id,
            filename="T2_04_budget_vs_actual_fy25.csv",
            role="spend_tabular",
        ),
        _ready_doc(
            document_id=ctx_id,
            filename="T2_09_budget_memo.txt",
            role="context_doc",
        ),
    ]
    write_engagement_manifest(eid, manifest)

    monkeypatch.setattr(
        "app.services.engagement_detection.profiler.document_contextualizer",
        lambda texts: {
            "inferred_industry": "it_ites",
            "inferred_company_name": "Aranya Digital Services Ltd",
        },
    )

    result = detect_engagement_profile(eid)
    assert result["detected_company_name"] == "Aranya Digital Services Ltd"
    assert "T2_09_budget_memo.txt" in result["source_documents"]["company"]
    assert result["company_llm"] == "Aranya Digital Services Ltd"


def test_hul_spend_only_does_not_recommend_abbreviation(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    create_engagement_manifest(engagement_id=eid, company_name="New engagement")

    manifest = create_engagement_manifest(engagement_id=eid)
    manifest["documents"] = [
        _ready_doc(
            document_id="d1",
            filename="hul_india_pnl_expense_fy25.csv",
            role="spend_tabular",
        ),
        _ready_doc(
            document_id="d2",
            filename="hul_india_spend_ledger_fy25.csv",
            role="spend_tabular",
        ),
    ]
    write_engagement_manifest(eid, manifest)

    result = detect_engagement_profile(eid)
    assert result["detected_company_name"] == ""


def test_update_engagement_detection_does_not_auto_apply_hul(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    create_engagement_manifest(engagement_id=eid, company_name="New engagement", industry="")

    updated = update_engagement_detection(
        eid,
        {
            "detected_company_name": "hul",
            "detected_industry": "fmcg_consumer",
            "detected_industry_label": "FMCG / Consumer",
            "industry_source": "spend",
            "industry_llm": "",
            "industry_spend": "fmcg_consumer",
            "context_text_hash": "",
            "source_documents": {},
        },
    )
    assert updated["detected_company_name"] == "hul"
    assert updated["company_name"] == "New engagement"


def test_revenue_detected_from_annual_report_context(monkeypatch, tmp_path) -> None:
    _patch_engagements_dir(monkeypatch, tmp_path)
    eid = str(uuid.uuid4())
    ctx_id = "d-ctx"
    create_engagement_manifest(engagement_id=eid)

    _write_markdown_cache(
        eid,
        ctx_id,
        "Aranya Digital Services Ltd — Annual Report FY25\n\n"
        "FY25 consolidated revenue was ₹18,400 Cr (FY24: ₹16,900 Cr).\n",
    )

    manifest = create_engagement_manifest(engagement_id=eid)
    manifest["documents"] = [
        _ready_doc(document_id=ctx_id, filename="annual_report.txt", role="context_doc"),
    ]
    write_engagement_manifest(eid, manifest)

    monkeypatch.setattr(
        "app.services.engagement_detection.profiler.document_contextualizer",
        lambda texts: {
            "inferred_industry": "it_ites",
            "inferred_company_name": "Aranya Digital Services Ltd",
            "inferred_annual_revenue_cr": 18400,
        },
    )

    result = detect_engagement_profile(eid)
    assert result["detected_annual_revenue_cr"] == 18400.0
    assert "annual_report.txt" in result["source_documents"]["revenue"]

    updated = update_engagement_detection(eid, result)
    assert updated["detected_annual_revenue_cr"] == 18400.0
    assert updated["annual_revenue"] == 18400.0 * 10_000_000


@pytest.mark.parametrize(
    "engagement_id,expected_company,expected_revenue",
    [
        (
            "96c43951-61ee-4a02-be96-97da04836f55",
            "Aranya Digital Services Ltd",
            18400.0,
        ),
        (
            "931ef522-703e-417b-bdff-358ece84b7e2",
            "",
            None,
        ),
    ],
)
def test_real_engagement_regression_fixtures(engagement_id, expected_company, expected_revenue) -> None:
    from pathlib import Path

    if not Path(f"data/engagements/{engagement_id}/manifest.json").exists():
        pytest.skip("fixture engagement not present")
    result = detect_engagement_profile(engagement_id)
    assert result["detected_company_name"] == expected_company
    assert result.get("detected_annual_revenue_cr") == expected_revenue
