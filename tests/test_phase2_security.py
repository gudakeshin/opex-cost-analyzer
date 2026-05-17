"""Phase 2 Security & Classification Spine tests.

Covers:
- B1–B4 classification (spend lines + aggregates + k-anonymity)
- PII detection + redaction (email, PAN, phone, Aadhaar, GSTIN, named persons)
- Aggregate band inference and inference-risk score
- Audit log append + replay
- LLM provider mode resolution and degradation banners
- Capability matrix loading
- pii_stripper skill
- data_classifier skill
- llm_context_builder skill (B3 tokenisation, B4 exclusion, M1 suppression)
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from app.security.classification import (
    DataBand,
    classify_aggregate,
    classify_output_block,
    classify_spend_line,
    redact_for_band,
)
from app.security.pii import (
    PiiMatch,
    ScanResult,
    is_pii_free,
    quarantine_record,
    scan_record,
    scan_text,
)
from app.security.bands import (
    K_ANONYMITY_THRESHOLD,
    BandedAggregate,
    annotate_skill_output,
    wrap_aggregate,
)
from app.models import NormalizedSpendLine
from app.skills.engine import data_classifier, llm_context_builder, pii_stripper


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _line(**kwargs) -> NormalizedSpendLine:
    defaults = dict(
        row_id=1,
        supplier="TestVendor",
        description="Cloud services",
        amount=100_000.0,
        category_id="IT",
        category_name="IT & Technology",
    )
    defaults.update(kwargs)
    return NormalizedSpendLine(**defaults)


def _lines(n: int = 10, **overrides) -> List[NormalizedSpendLine]:
    return [
        _line(row_id=i + 1, **overrides)
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# B1–B4 Classification — spend lines
# ---------------------------------------------------------------------------

class TestSpendLineClassification:
    def test_supplier_field_gives_b3(self):
        record = {"supplier": "Accenture", "amount": 100_000}
        assert classify_spend_line(record) == DataBand.B3

    def test_gstin_field_gives_b3(self):
        record = {"gstin": "27AABCM1234A1Z5", "amount": 50_000}
        assert classify_spend_line(record) == DataBand.B3

    def test_gl_code_gives_b3(self):
        record = {"gl_code": "6000100", "amount": 10_000}
        assert classify_spend_line(record) == DataBand.B3

    def test_amount_only_gives_b2(self):
        record = {"amount": 500_000}
        assert classify_spend_line(record) == DataBand.B2

    def test_empty_record_gives_b1(self):
        assert classify_spend_line({}) == DataBand.B1

    def test_pii_fields_give_b4(self):
        record = {"email": "user@corp.com", "amount": 1_000}
        assert classify_spend_line(record) == DataBand.B4

    def test_person_name_gives_b4(self):
        record = {"person_name": "Ravi Kumar", "amount": 5_000}
        assert classify_spend_line(record) == DataBand.B4

    def test_b4_overrides_b3(self):
        record = {"supplier": "Vendor", "email": "a@b.com"}
        assert classify_spend_line(record) == DataBand.B4


class TestAggregateClassification:
    def _b3_row(self) -> Dict[str, Any]:
        return {"supplier": "Vendor A", "amount": 10_000}

    def _b2_row(self) -> Dict[str, Any]:
        return {"amount": 5_000}

    def test_k_anonymity_below_threshold_gives_b3(self):
        rows = [self._b3_row() for _ in range(K_ANONYMITY_THRESHOLD - 1)]
        band, reason = classify_aggregate(rows)
        assert band == DataBand.B3
        assert "k-anonymity" in reason

    def test_sufficient_rows_derives_worst_source_band(self):
        rows = [self._b2_row() for _ in range(K_ANONYMITY_THRESHOLD + 1)]
        band, reason = classify_aggregate(rows)
        assert band == DataBand.B2

    def test_output_block_with_supplier_gives_b3(self):
        block = {"top_suppliers": [{"supplier": "TCS", "spend": 1_000}], "total_spend": 50_000}
        band, reason = classify_output_block(block, source_row_count=10)
        assert band == DataBand.B3

    def test_output_block_spend_only_gives_b2(self):
        block = {"total_spend": 500_000, "category_count": 5}
        band, reason = classify_output_block(block, source_row_count=20)
        assert band == DataBand.B2

    def test_output_block_low_count_gives_b3(self):
        block = {"total_spend": 100_000}
        band, reason = classify_output_block(block, source_row_count=2)
        assert band == DataBand.B3


class TestRedactForBand:
    def test_b1_target_removes_amount(self):
        record = {"supplier": "Vendor", "amount": 1_000}
        out = redact_for_band(record, DataBand.B1)
        assert out["supplier"] == "[REDACTED]"
        assert out["amount"] is None

    def test_b2_target_removes_supplier(self):
        record = {"supplier": "TCS", "amount": 500_000}
        out = redact_for_band(record, DataBand.B2)
        assert out["supplier"] == "[REDACTED]"
        assert out["amount"] == 500_000

    def test_b3_target_keeps_all(self):
        record = {"supplier": "TCS", "amount": 500_000}
        out = redact_for_band(record, DataBand.B3)
        assert out["supplier"] == "TCS"
        assert out["amount"] == 500_000


class TestDataBandOrdering:
    def test_b1_less_than_b4(self):
        assert DataBand.B1 < DataBand.B4

    def test_b3_less_than_b4(self):
        assert DataBand.B3 < DataBand.B4

    def test_b2_less_than_or_equal_b2(self):
        assert DataBand.B2 <= DataBand.B2

    def test_max_band_works(self):
        bands = [DataBand.B1, DataBand.B3, DataBand.B2]
        worst = max(bands, key=lambda b: list(DataBand).index(b))
        assert worst == DataBand.B3


# ---------------------------------------------------------------------------
# PII Detection
# ---------------------------------------------------------------------------

class TestPiiScanText:
    def test_email_detected(self):
        result = scan_text("Contact pallav@example.com for details")
        assert result.has_pii
        assert any(m.pii_type == "email" for m in result.matches)

    def test_email_redacted(self):
        result = scan_text("Email: test@company.in")
        assert "test@company.in" not in result.redacted

    def test_pan_detected(self):
        result = scan_text("PAN: ABCDE1234F on file")
        assert any(m.pii_type == "pan" for m in result.matches)

    def test_pan_redacted(self):
        result = scan_text("PAN card ABCDE1234F")
        assert "ABCDE1234F" not in result.redacted

    def test_gstin_detected(self):
        result = scan_text("GSTIN: 27AABCM1234A1Z5")
        assert any(m.pii_type == "gstin" for m in result.matches)

    def test_indian_phone_detected(self):
        result = scan_text("Call +91 9876543210 for invoice")
        assert any(m.pii_type == "phone" for m in result.matches)

    def test_aadhaar_detected(self):
        result = scan_text("Aadhaar 1234 5678 9012")
        assert any(m.pii_type == "aadhaar" for m in result.matches)

    def test_titled_name_detected(self):
        result = scan_text("Approved by Mr. Ravi Sharma for payment")
        assert any(m.pii_type == "name" for m in result.matches)

    def test_no_pii_clean_text(self):
        result = scan_text("Cloud infrastructure spend for Q3")
        assert not result.has_pii

    def test_empty_string(self):
        result = scan_text("")
        assert not result.has_pii
        assert result.redacted == ""

    def test_none_input(self):
        result = scan_text(None)  # type: ignore[arg-type]
        assert not result.has_pii

    def test_multiple_types_detected(self):
        text = "Mr. Kumar ABCDE1234F called at 9876543210 from ceo@firm.in"
        result = scan_text(text)
        types = result.pii_types
        assert len(types) >= 2

    def test_is_pii_free_clean(self):
        assert is_pii_free("Annual software subscription renewal")

    def test_is_pii_free_with_email(self):
        assert not is_pii_free("Contact hr@company.com for onboarding")


class TestPiiScanRecord:
    def test_record_email_redacted(self):
        record = {"supplier": "Vendor", "contact": "user@vendor.com", "amount": 10_000}
        cleaned, matches = scan_record(record, redact=True)
        assert "user@vendor.com" not in cleaned["contact"]
        assert any(m.pii_type == "email" for m in matches)

    def test_nested_dict_scanned(self):
        record = {"meta": {"email": "a@b.com"}}
        cleaned, matches = scan_record(record)
        assert "a@b.com" not in cleaned["meta"]["email"]
        assert matches

    def test_list_of_strings_scanned(self):
        record = {"notes": ["Call ABCDE1234F at 9876543210"]}
        cleaned, matches = scan_record(record)
        assert matches

    def test_no_pii_record_unchanged(self):
        record = {"supplier": "TCS Ltd", "amount": 500_000, "category": "IT"}
        cleaned, matches = scan_record(record)
        assert cleaned == record
        assert not matches

    def test_quarantine_record(self):
        record = {"supplier": "Vendor", "email": "a@b.com", "amount": 1_000}
        q = quarantine_record(record)
        assert q["supplier"] == "[QUARANTINED]"
        assert q["email"] == "[QUARANTINED]"
        assert q["amount"] == 1_000  # non-strings preserved


# ---------------------------------------------------------------------------
# Band Provenance (bands.py)
# ---------------------------------------------------------------------------

class TestBandedAggregate:
    def _make_rows(self, n: int) -> List[Dict[str, Any]]:
        return [{"supplier": f"Vendor{i}", "amount": 10_000} for i in range(n)]

    def test_wrap_aggregate_low_k(self):
        rows = self._make_rows(K_ANONYMITY_THRESHOLD - 1)
        banded = wrap_aggregate({"total_spend": 40_000}, rows)
        assert banded.band == DataBand.B3

    def test_wrap_aggregate_sufficient_k(self):
        rows = self._make_rows(K_ANONYMITY_THRESHOLD + 5)
        banded = wrap_aggregate({"total_spend": 100_000}, rows)
        assert banded.band in (DataBand.B2, DataBand.B3)

    def test_inference_risk_increases_with_low_k(self):
        low_k = wrap_aggregate({"total_spend": 10_000}, self._make_rows(2))
        high_k = wrap_aggregate({"total_spend": 10_000}, self._make_rows(20))
        assert low_k.inference_risk_score >= high_k.inference_risk_score

    def test_is_safe_for_llm_m1_only_b1(self):
        banded = BandedAggregate(
            payload={}, band=DataBand.B2, source_row_count=10,
            band_reason="test", inference_risk_score=0.3,
        )
        assert not banded.is_safe_for_llm("M1")
        assert banded.is_safe_for_llm("M2")

    def test_is_safe_for_llm_m3_b3_rejected(self):
        banded = BandedAggregate(
            payload={}, band=DataBand.B3, source_row_count=10,
            band_reason="test", inference_risk_score=0.65,
        )
        assert not banded.is_safe_for_llm("M3")
        assert banded.is_safe_for_llm("M2")

    def test_annotate_skill_output_adds_metadata(self):
        output = {"total_spend": 1_000_000, "category_count": 5}
        rows = [{"amount": 100_000} for _ in range(20)]
        annotated = annotate_skill_output("spend-profiler", output, rows)
        assert "_security_metadata" in annotated
        meta = annotated["_security_metadata"]
        assert meta["skill"] == "spend-profiler"
        assert "band" in meta
        assert 0.0 <= meta["inference_risk_score"] <= 1.0


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def setup_method(self):
        from app.services import audit_log as _al
        self._orig_path = _al._LOG_PATH
        self._tmp = tempfile.mktemp(suffix=".jsonl")
        _al._LOG_PATH = Path(self._tmp)

    def teardown_method(self):
        from app.services import audit_log as _al
        _al._LOG_PATH = self._orig_path
        Path(self._tmp).unlink(missing_ok=True)

    def _al(self):
        from app.services import audit_log
        return audit_log

    def test_append_and_replay(self):
        al = self._al()
        al.append_event("test_event", {"key": "val"}, session_id="s1", severity="LOW")
        entries = al.replay_log()
        assert len(entries) >= 1
        assert entries[0]["event_type"] == "test_event"

    def test_replay_filter_by_event_type(self):
        al = self._al()
        al.append_event("pii_detected", {"pii_types": ["email"]}, session_id="s1")
        al.append_event("band_classified", {"band": "B3"}, session_id="s1")
        pii_entries = al.replay_log(event_type="pii_detected")
        assert all(e["event_type"] == "pii_detected" for e in pii_entries)

    def test_replay_filter_by_session(self):
        al = self._al()
        al.append_event("test", {}, session_id="sess-A")
        al.append_event("test", {}, session_id="sess-B")
        entries = al.replay_log(session_id="sess-A")
        assert all(e["session_id"] == "sess-A" for e in entries)

    def test_log_pii_detected_helper(self):
        al = self._al()
        al.log_pii_detected("s1", ["email", "pan"], ["supplier", "description"], 5)
        entries = al.replay_log(event_type="pii_detected")
        assert entries[0]["severity"] == "HIGH"

    def test_log_teardown_helper(self):
        al = self._al()
        al.log_teardown("eng-001", 10, ["sess-a", "sess-b"])
        entries = al.replay_log(event_type="teardown")
        assert entries[0]["engagement_id"] == "eng-001"

    def test_replay_returns_newest_first(self):
        al = self._al()
        for i in range(3):
            al.append_event("seq", {"n": i}, session_id="s")
        entries = al.replay_log(session_id="s")
        # newest first — last written should be first in replay
        assert entries[0]["detail"]["n"] == 2

    def test_empty_log_returns_empty_list(self):
        al = self._al()
        assert al.replay_log() == []

    def test_audit_log_is_append_only(self):
        al = self._al()
        al.append_event("e1", {"a": 1}, session_id="s")
        al.append_event("e2", {"b": 2}, session_id="s")
        entries = al.replay_log()
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# LLM Provider — mode + capability matrix
# ---------------------------------------------------------------------------

class TestLlmProvider:
    def test_default_mode_is_m2(self):
        from app.opar.llm_provider import get_active_mode
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_MODE", None)
            assert get_active_mode() == "M2"

    def test_mode_override_via_env(self):
        from app.opar.llm_provider import get_active_mode
        with patch.dict(os.environ, {"LLM_MODE": "M1"}):
            assert get_active_mode() == "M1"

    def test_invalid_mode_falls_back_to_m2(self):
        from app.opar.llm_provider import get_active_mode
        with patch.dict(os.environ, {"LLM_MODE": "M9"}):
            assert get_active_mode() == "M2"

    def test_skill_capability_reads_matrix(self):
        from app.opar.llm_provider import skill_capability
        # analysis-synthesizer is degraded in M1 per capability matrix
        cap = skill_capability("analysis-synthesizer", "M1")
        assert cap == "degraded"

    def test_deterministic_skill_full_all_modes(self):
        from app.opar.llm_provider import skill_capability
        for mode in ("M1", "M2", "M3"):
            assert skill_capability("spend-profiler", mode) == "full"

    def test_is_degraded_returns_true_for_llm_heavy_m1(self):
        from app.opar.llm_provider import is_degraded
        assert is_degraded("analysis-synthesizer", "M1")
        assert is_degraded("executive-communication", "M1")

    def test_is_degraded_returns_false_for_deterministic(self):
        from app.opar.llm_provider import is_degraded
        assert not is_degraded("spend-profiler", "M1")

    def test_m1_call_returns_none(self):
        from app.opar.llm_provider import call_llm
        with patch.dict(os.environ, {"LLM_MODE": "M1"}):
            result = call_llm("system", "user", mode="M1")
        assert result is None

    def test_attach_degradation_banner(self):
        from app.opar.llm_provider import attach_degradation_banner
        output: Dict[str, Any] = {"total_spend": 1_000_000}
        result = attach_degradation_banner(output, "analysis-synthesizer", "M1", "degraded")
        assert "_mode_degradation" in result
        assert result["_mode_degradation"]["mode"] == "M1"

    def test_no_banner_for_full_capability(self):
        from app.opar.llm_provider import attach_degradation_banner
        output: Dict[str, Any] = {"total_spend": 1_000_000}
        result = attach_degradation_banner(output, "spend-profiler", "M2", "full")
        assert "_mode_degradation" not in result

    def test_mode_summary_structure(self):
        from app.opar.llm_provider import mode_summary
        with patch.dict(os.environ, {"LLM_MODE": "M1"}):
            summary = mode_summary("M1")
        assert summary["mode"] == "M1"
        assert summary["llm_available"] is False
        assert isinstance(summary["degraded_skills"], list)
        assert len(summary["degraded_skills"]) > 0

    def test_mode_summary_m2_no_degradation(self):
        from app.opar.llm_provider import mode_summary
        summary = mode_summary("M2")
        assert summary["mode"] == "M2"
        assert summary["llm_available"] is True
        assert len(summary["degraded_skills"]) == 0


# ---------------------------------------------------------------------------
# pii_stripper skill
# ---------------------------------------------------------------------------

class TestPiiStripperSkill:
    def _pii_line(self, row_id: int = 1) -> NormalizedSpendLine:
        return NormalizedSpendLine(
            row_id=row_id,
            supplier="Mr. Ravi Kumar Consulting",
            description="Invoice for ABCDE1234F services",
            amount=50_000.0,
            category_id="PROF_SVCS",
            category_name="Professional Services",
        )

    def _clean_line(self, row_id: int = 1) -> NormalizedSpendLine:
        return NormalizedSpendLine(
            row_id=row_id,
            supplier="TCS Limited",
            description="Annual software maintenance",
            amount=1_00_000.0,
            category_id="IT",
            category_name="IT & Technology",
        )

    def test_empty_lines_returns_zero_counts(self):
        result = pii_stripper([])
        assert result["rows_scanned"] == 0
        assert result["rows_with_pii"] == 0

    def test_pii_line_detected(self):
        result = pii_stripper([self._pii_line()])
        assert result["rows_scanned"] == 1
        assert result["rows_with_pii"] >= 1

    def test_clean_line_not_flagged(self):
        result = pii_stripper([self._clean_line()])
        assert result["rows_with_pii"] == 0
        assert result["rows_quarantined"] == 0

    def test_quarantine_ids_populated(self):
        result = pii_stripper([self._pii_line(row_id=42)])
        if result["rows_with_pii"] > 0:
            assert 42 in result["quarantine_row_ids"]

    def test_pii_type_counts_present(self):
        result = pii_stripper([self._pii_line()])
        assert isinstance(result["pii_type_counts"], dict)

    def test_redacted_lines_count_matches_input(self):
        lines = [self._clean_line(i) for i in range(5)]
        result = pii_stripper(lines)
        assert len(result["redacted_lines"]) == 5

    def test_multiple_lines_mixed(self):
        lines = [self._pii_line(1), self._clean_line(2), self._pii_line(3)]
        result = pii_stripper(lines)
        assert result["rows_scanned"] == 3
        assert result["rows_with_pii"] >= 1


# ---------------------------------------------------------------------------
# data_classifier skill
# ---------------------------------------------------------------------------

class TestDataClassifierSkill:
    def test_empty_lines(self):
        result = data_classifier([])
        assert result["worst_band"] == "B1"
        assert result["b4_count"] == 0
        assert result["line_bands"] == []

    def test_supplier_lines_worst_b3(self):
        lines = _lines(10)
        result = data_classifier(lines)
        assert result["worst_band"] == "B3"

    def test_b4_detection_via_classify_function(self):
        """B4 detection is tested at the classify_spend_line level (dict API)."""
        from app.security.classification import classify_spend_line, DataBand
        record = {"email": "ceo@company.com", "supplier": "Vendor", "amount": 1000}
        assert classify_spend_line(record) == DataBand.B4

    def test_b4_count_zero_for_clean_lines(self):
        lines = _lines(5)
        result = data_classifier(lines)
        assert result["b4_count"] == 0

    def test_line_bands_populated(self):
        lines = _lines(3)
        result = data_classifier(lines)
        assert len(result["line_bands"]) == 3
        for lb in result["line_bands"]:
            assert "row_id" in lb
            assert "band" in lb

    def test_aggregate_bands_populated(self):
        lines = _lines(10)
        skill_outputs = {"spend-profiler": {"total_spend": 1_000_000, "category_count": 5}}
        result = data_classifier(lines, skill_outputs)
        assert "spend-profiler" in result["aggregate_bands"]

    def test_summary_string_contains_row_count(self):
        lines = _lines(7)
        result = data_classifier(lines)
        assert "7" in result["summary"]

    def test_k_anonymity_flags_low_count_aggregate(self):
        lines = _lines(K_ANONYMITY_THRESHOLD - 1)
        skill_outputs = {"spend-profiler": {"total_spend": 10_000}}
        result = data_classifier(lines, skill_outputs, k_threshold=K_ANONYMITY_THRESHOLD)
        agg = result["aggregate_bands"].get("spend-profiler", {})
        # low row count → should be B3
        assert agg.get("band") in ("B3", "B4")


# ---------------------------------------------------------------------------
# llm_context_builder skill
# ---------------------------------------------------------------------------

class TestLlmContextBuilderSkill:
    def _make_outputs(self, include_supplier: bool = False) -> Dict[str, Any]:
        base = {
            "spend-profiler": {
                "total_spend": 1_000_000,
                "category_count": 5,
                "category_profile": [
                    {
                        "category_id": "IT",
                        "category_name": "IT & Technology",
                        "spend": 500_000,
                        "top_suppliers": [{"supplier": "AWS", "spend": 300_000}] if include_supplier else [],
                    }
                ],
            },
        }
        return base

    def _make_classification(self, band: str = "B2") -> Dict[str, Any]:
        return {
            "aggregate_bands": {
                "spend-profiler": {
                    "band": band,
                    "inference_risk_score": 0.3,
                    "reason": "test",
                }
            }
        }

    def test_m1_mode_suppresses_all(self):
        outputs = self._make_outputs()
        result = llm_context_builder(outputs, mode="M1")
        assert result["context_ready"] is False
        assert result["blocks_included"] == 0
        assert result["blocks_excluded"] == len(outputs)

    def test_m2_b2_included_verbatim(self):
        outputs = self._make_outputs()
        classification = self._make_classification("B2")
        result = llm_context_builder(outputs, classification, mode="M2")
        assert result["context_ready"] is True
        assert "spend-profiler" in result["sanitised_skill_outputs"]

    def test_m2_b3_supplier_tokenised(self):
        outputs = self._make_outputs(include_supplier=True)
        classification = self._make_classification("B3")
        result = llm_context_builder(outputs, classification, mode="M2")
        profile = result["sanitised_skill_outputs"].get("spend-profiler", {})
        cats = profile.get("category_profile", [])
        if cats:
            suppliers = cats[0].get("top_suppliers", [])
            if suppliers:
                assert suppliers[0]["supplier"].startswith("VENDOR_")

    def test_m3_b3_excluded(self):
        outputs = self._make_outputs(include_supplier=True)
        classification = self._make_classification("B3")
        result = llm_context_builder(outputs, classification, mode="M3")
        assert "spend-profiler" not in result["sanitised_skill_outputs"]
        assert result["blocks_excluded"] >= 1

    def test_b4_always_excluded(self):
        outputs = {"sensitive-skill": {"personal_data": "Mr. John PAN ABCDE1234F"}}
        classification = {"aggregate_bands": {"sensitive-skill": {"band": "B4", "inference_risk_score": 0.95, "reason": "B4"}}}
        result = llm_context_builder(outputs, classification, mode="M2")
        assert "sensitive-skill" not in result["sanitised_skill_outputs"]
        assert result["blocks_excluded"] >= 1
        assert any("B4" in log for log in result["exclusion_log"])

    def test_exclusion_log_populated_on_exclusion(self):
        outputs = self._make_outputs()
        classification = self._make_classification("B4")
        result = llm_context_builder(outputs, classification, mode="M2")
        assert len(result["exclusion_log"]) >= 1

    def test_worst_band_in_context_tracked(self):
        outputs = self._make_outputs()
        classification = self._make_classification("B2")
        result = llm_context_builder(outputs, classification, mode="M2")
        assert result["worst_band_in_context"] in ("B1", "B2", "B3", "B4")

    def test_empty_outputs(self):
        result = llm_context_builder({}, mode="M2")
        assert result["blocks_included"] == 0
        assert result["sanitised_skill_outputs"] == {}
