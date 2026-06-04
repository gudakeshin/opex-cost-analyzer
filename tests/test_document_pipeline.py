"""Document pipeline routing tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.document_pipeline import process_engagement_document, validate_upload_suffix
from app.services.engagements_store import (
    add_document_record,
    create_engagement_manifest,
    document_dir,
)
from app.services.analysis import load_taxonomy


def test_validate_upload_suffix_rejects_unknown():
    with pytest.raises(ValueError, match="Unsupported"):
        validate_upload_suffix("file.exe")


def test_process_txt_document(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    manifest = create_engagement_manifest(company_name="Doc Test")
    eid = manifest["engagement_id"]
    doc_id = "00000000-0000-4000-8000-000000000099"
    ddir = document_dir(eid, doc_id)
    ddir.mkdir(parents=True)
    (ddir / "raw.txt").write_text("Budget memo: reduce IT spend by 10%", encoding="utf-8")
    add_document_record(
        eid,
        document_id=doc_id,
        filename="memo.txt",
        content_type="text/plain",
        size_bytes=40,
        raw_path=str(ddir / "raw.txt"),
    )
    result = process_engagement_document(
        eid,
        doc_id,
        taxonomy=load_taxonomy(),
    )
    assert result["status"] == "ready"
    assert result["role"] == "context_doc"
    assert "IT spend" in (result.get("text_preview") or "")


def test_process_pdf_fallback_without_llamaparse(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    manifest = create_engagement_manifest()
    eid = manifest["engagement_id"]
    doc_id = "00000000-0000-4000-8000-000000000098"
    ddir = document_dir(eid, doc_id)
    ddir.mkdir(parents=True)
    (ddir / "raw.pdf").write_bytes(b"%PDF-1.4 minimal")
    add_document_record(
        eid,
        document_id=doc_id,
        filename="notes.pdf",
        content_type="application/pdf",
        size_bytes=16,
        raw_path=str(ddir / "raw.pdf"),
    )
    with patch("app.services.document_pipeline.is_llamaparse_available", return_value=False):
        with patch("app.services.document_pipeline.parse_document", return_value="fallback text"):
            result = process_engagement_document(eid, doc_id, taxonomy=load_taxonomy())
    assert result["status"] == "ready"
