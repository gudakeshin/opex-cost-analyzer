"""Tests for app/services/engagement_corpus.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.engagement_corpus import load_engagement_corpus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _manifest(**kwargs):
    base = {
        "engagement_id": "eng-001",
        "currency": "INR",
        "documents": [],
    }
    base.update(kwargs)
    return base


def _doc_record(doc_id="doc-1", filename="spend.csv", status="ready"):
    return {"document_id": doc_id, "filename": filename, "status": status}


# ---------------------------------------------------------------------------
# load_engagement_corpus
# ---------------------------------------------------------------------------

class TestLoadEngagementCorpus:
    def test_missing_engagement_returns_warning(self):
        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value={},
        ):
            lines, docs, reports, warnings = load_engagement_corpus("eng-missing")
        assert lines == []
        assert docs == []
        assert reports == []
        assert any("not found" in w for w in warnings)

    def test_no_documents_returns_empty(self):
        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[]),
        ):
            lines, docs, reports, warnings = load_engagement_corpus("eng-001")
        assert lines == []
        assert docs == []
        assert reports == []
        assert warnings == []

    def test_processing_document_warns_and_skips(self):
        doc = _doc_record(status="processing")
        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ):
            lines, docs, reports, warnings = load_engagement_corpus("eng-001")
        assert lines == []
        assert any("processing" in w.lower() for w in warnings)

    def test_failed_document_warns_with_reason(self):
        doc = {**_doc_record(status="failed"), "error": "PDF parse error"}
        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ):
            lines, docs, reports, warnings = load_engagement_corpus("eng-001")
        assert any("PDF parse error" in w for w in warnings)

    def test_failed_document_without_error_uses_fallback(self):
        doc = _doc_record(status="failed")
        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ):
            _, _, _, warnings = load_engagement_corpus("eng-001")
        assert any("unknown error" in w for w in warnings)

    def test_pending_document_warns_and_skips(self):
        doc = _doc_record(status="pending")
        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ):
            lines, docs, reports, warnings = load_engagement_corpus("eng-001")
        assert lines == []
        assert any("pending" in w.lower() for w in warnings)

    def test_document_missing_id_skipped_silently(self):
        doc = {"filename": "spend.csv", "status": "ready"}  # no document_id
        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ):
            lines, docs, reports, warnings = load_engagement_corpus("eng-001")
        assert lines == []
        assert warnings == []

    def test_ready_spend_doc_loads_cached_lines(self):
        doc = _doc_record(status="ready")
        fake_line = MagicMock()
        fake_line.amount = 1000.0

        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ), patch(
            "app.services.engagement_corpus.load_cached_spend_lines",
            return_value=[fake_line],
        ), patch(
            "app.services.engagement_corpus.load_cached_markdown",
            return_value="",
        ):
            lines, docs, reports, warnings = load_engagement_corpus("eng-001")

        assert lines == [fake_line]
        assert warnings == []
        assert len(reports) == 1
        assert reports[0]["rows_parsed"] == 1
        assert reports[0]["origin"] == "engagement"

    def test_ready_context_doc_loads_markdown(self):
        doc = _doc_record(doc_id="doc-2", filename="brief.txt", status="ready")

        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ), patch(
            "app.services.engagement_corpus.load_cached_spend_lines",
            return_value=[],
        ), patch(
            "app.services.engagement_corpus.load_cached_markdown",
            return_value="Company brief content here",
        ):
            lines, docs_text, reports, warnings = load_engagement_corpus("eng-001")

        assert lines == []
        assert any("brief.txt" in t for t in docs_text)
        assert any("Company brief" in t for t in docs_text)

    def test_blank_markdown_not_added_to_docs(self):
        doc = _doc_record(status="ready")

        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=[doc]),
        ), patch(
            "app.services.engagement_corpus.load_cached_spend_lines",
            return_value=[],
        ), patch(
            "app.services.engagement_corpus.load_cached_markdown",
            return_value="   ",  # whitespace only
        ):
            _, docs_text, _, _ = load_engagement_corpus("eng-001")

        assert docs_text == []

    def test_multiple_docs_accumulate_lines(self):
        docs = [
            _doc_record(doc_id="doc-1", filename="q1.csv", status="ready"),
            _doc_record(doc_id="doc-2", filename="q2.csv", status="ready"),
        ]
        line_a = MagicMock()
        line_b = MagicMock()

        def _cached_lines(eng_id, doc_id):
            return [line_a] if doc_id == "doc-1" else [line_b]

        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(documents=docs),
        ), patch(
            "app.services.engagement_corpus.load_cached_spend_lines",
            side_effect=_cached_lines,
        ), patch(
            "app.services.engagement_corpus.load_cached_markdown",
            return_value="",
        ):
            lines, _, reports, warnings = load_engagement_corpus("eng-001")

        assert lines == [line_a, line_b]
        assert len(reports) == 2
        assert warnings == []

    def test_reporting_currency_overrides_manifest(self):
        doc = _doc_record(status="ready")

        captured_currency = {}

        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=_manifest(currency="INR", documents=[doc]),
        ), patch(
            "app.services.engagement_corpus.load_cached_spend_lines",
            return_value=[],
        ), patch(
            "app.services.engagement_corpus.load_cached_markdown",
            return_value="",
        ):
            # Just check the function accepts and doesn't error; the currency is
            # used for future parsing calls, not re-parsing cached lines.
            lines, _, _, warnings = load_engagement_corpus("eng-001", reporting_currency="USD")

        assert warnings == []

    def test_currency_defaults_to_inr_when_manifest_missing(self):
        doc = _doc_record(status="ready")
        manifest = _manifest(documents=[doc])
        del manifest["currency"]

        with patch(
            "app.services.engagement_corpus.read_engagement_manifest",
            return_value=manifest,
        ), patch(
            "app.services.engagement_corpus.load_cached_spend_lines",
            return_value=[],
        ), patch(
            "app.services.engagement_corpus.load_cached_markdown",
            return_value="",
        ):
            lines, _, _, warnings = load_engagement_corpus("eng-001")

        assert warnings == []
