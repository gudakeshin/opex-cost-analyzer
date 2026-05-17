"""Phase 1 India-spine tests.

Covers:
- INR formatter (Lakh / Crore / absolute / bps / range)
- Engagement scope isolation in MemoryStore (put/get/teardown)
- GST ITC leakage detection in indian_tax_optimizer
- India column mapping in ingestion (gst_treatment, gstin, related_party_flag)
- NormalizedSpendLine India fields (defaults + INR currency default)
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from app.utils.inr_format import (
    bps_label,
    crore_to_inr,
    format_inr,
    format_inr_range,
    inr_to_crore,
    inr_to_lakh,
    lakh_to_inr,
)
from app.models import NormalizedSpendLine
from app.memory import MemoryStore
from app.skills.engine import indian_tax_optimizer


# ---------------------------------------------------------------------------
# INR Formatter
# ---------------------------------------------------------------------------

class TestInrFormat:
    def test_auto_crore(self):
        s = format_inr(5_00_00_000)  # 5 Cr
        assert "5.00" in s and "Cr" in s and "₹" in s

    def test_auto_lakh(self):
        s = format_inr(3_50_000)  # 3.5 L
        assert "3.50" in s and "L" in s

    def test_auto_absolute(self):
        s = format_inr(45_000)
        assert "Cr" not in s and "L" not in s

    def test_force_crore(self):
        s = format_inr(1_00_00_000, scale="crore", decimals=0)
        assert "1" in s and "Cr" in s

    def test_no_symbol(self):
        s = format_inr(1_00_00_000, symbol=False)
        assert "₹" not in s

    def test_international_millions(self):
        s = format_inr(5_000_000, international=True)
        assert "M" in s

    def test_international_billions(self):
        s = format_inr(2_500_000_000, international=True)
        assert "B" in s

    def test_inr_to_crore(self):
        assert inr_to_crore(1_00_00_000) == pytest.approx(1.0)

    def test_inr_to_lakh(self):
        assert inr_to_lakh(1_00_000) == pytest.approx(1.0)

    def test_crore_to_inr(self):
        assert crore_to_inr(2.5) == pytest.approx(2_50_00_000)

    def test_lakh_to_inr(self):
        assert lakh_to_inr(10) == pytest.approx(10_00_000)

    def test_bps_label_positive(self):
        assert bps_label(180) == "+180 bps"

    def test_bps_label_negative(self):
        assert bps_label(-45) == "-45 bps"

    def test_format_inr_range(self):
        s = format_inr_range(190_00_00_000, 260_00_00_000, 320_00_00_000)
        assert "190.00" in s and "260.00" in s and "320.00" in s and "Cr" in s


# ---------------------------------------------------------------------------
# Engagement Scope (MemoryStore)
# ---------------------------------------------------------------------------

class TestEngagementScope:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        from app.config import MEMORY_DIR
        # Use a temp dir to avoid polluting real data
        self.store = MemoryStore()
        self.store.base = Path(self._tmpdir)

    def _make_dirs(self, *scopes):
        for s in scopes:
            (Path(self._tmpdir) / s).mkdir(exist_ok=True)

    def test_put_and_get_engagement(self):
        self._make_dirs("engagement")
        self.store.put_engagement("eng-001", {"company": "TestCo", "week": 1})
        data = self.store.get_engagement("eng-001")
        assert data["company"] == "TestCo"
        assert data["week"] == 1

    def test_get_missing_engagement_returns_empty(self):
        self._make_dirs("engagement")
        data = self.store.get_engagement("nonexistent")
        assert data == {}

    def test_delete_engagement(self):
        self._make_dirs("engagement")
        self.store.put_engagement("eng-002", {"x": 1})
        self.store.delete_engagement("eng-002")
        assert self.store.get_engagement("eng-002") == {}

    def test_teardown_engagement_removes_record(self):
        self._make_dirs("engagement", "session")
        self.store.put_engagement("eng-003", {"company": "TearDown"})
        result = self.store.teardown_engagement("eng-003")
        assert result["engagement_record_deleted"] is True
        assert self.store.get_engagement("eng-003") == {}

    def test_teardown_removes_child_sessions(self):
        self._make_dirs("engagement", "session")
        self.store.put_engagement("eng-004", {"company": "TearDown2"})
        # Manually write a session that declares this engagement_id
        self.store.put("session", "sess-a", {"engagement_id": "eng-004", "data": "foo"})
        result = self.store.teardown_engagement("eng-004")
        assert "sess-a" in result["sessions_deleted"]
        assert self.store.get("session", "sess-a") == {}

    def test_engagement_isolation(self):
        """Two engagements do not share data."""
        self._make_dirs("engagement")
        self.store.put_engagement("eng-A", {"company": "CompanyA"})
        self.store.put_engagement("eng-B", {"company": "CompanyB"})
        assert self.store.get_engagement("eng-A")["company"] == "CompanyA"
        assert self.store.get_engagement("eng-B")["company"] == "CompanyB"
        self.store.teardown_engagement("eng-A")
        assert self.store.get_engagement("eng-A") == {}
        assert self.store.get_engagement("eng-B")["company"] == "CompanyB"


# ---------------------------------------------------------------------------
# NormalizedSpendLine India fields
# ---------------------------------------------------------------------------

class TestSpendLineIndiaFields:
    def _line(self, **kwargs):
        defaults = dict(
            row_id=1,
            supplier="TestVendor",
            description="Cloud software",
            amount=100_000.0,
            category_id="IT",
            category_name="IT & Technology",
        )
        defaults.update(kwargs)
        return NormalizedSpendLine(**defaults)

    def test_default_currency_is_inr(self):
        line = self._line()
        assert line.currency == "INR"

    def test_gst_treatment_field(self):
        line = self._line(gst_treatment="itc_eligible")
        assert line.gst_treatment == "itc_eligible"

    def test_gstin_field(self):
        line = self._line(gstin="27AABCM1234A1Z5")
        assert line.gstin == "27AABCM1234A1Z5"

    def test_related_party_flag_default_false(self):
        line = self._line()
        assert line.related_party_flag is False

    def test_related_party_flag_true(self):
        line = self._line(related_party_flag=True)
        assert line.related_party_flag is True

    def test_lease_treatment(self):
        line = self._line(lease_treatment="operating_ind_as_116", lease_term_months=60)
        assert line.lease_treatment == "operating_ind_as_116"
        assert line.lease_term_months == 60

    def test_legal_entity_id(self):
        line = self._line(legal_entity_id="INCO001")
        assert line.legal_entity_id == "INCO001"

    def test_reporting_amount_with_fx(self):
        line = self._line(amount=1000.0, currency="USD", fx_rate_to_reporting=83.5)
        assert line.reporting_amount == pytest.approx(83_500.0)


# ---------------------------------------------------------------------------
# Indian Tax Optimizer
# ---------------------------------------------------------------------------

def _make_lines(rows):
    """Build NormalizedSpendLine list from a list of dicts."""
    out = []
    for i, r in enumerate(rows):
        out.append(
            NormalizedSpendLine(
                row_id=i + 1,
                supplier=r.get("supplier", "Vendor"),
                description=r.get("description", "Service"),
                amount=r.get("amount", 10_00_000.0),
                category_id=r.get("category_id", "IT"),
                category_name=r.get("category_name", "IT & Technology"),
                currency="INR",
                fx_rate_to_reporting=1.0,
                amount_type=r.get("amount_type", "actual"),
                gst_treatment=r.get("gst_treatment"),
                gstin=r.get("gstin"),
                related_party_flag=r.get("related_party_flag", False),
            )
        )
    return out


class TestIndianTaxOptimizer:
    def test_empty_lines_returns_not_available(self):
        result = indian_tax_optimizer([])
        assert result["tax_optimization_available"] is False

    def test_itc_eligible_lines_produce_leakage_estimate(self):
        lines = _make_lines([
            {"description": "AWS cloud services", "amount": 50_00_00_000, "gst_treatment": "itc_eligible"},
            {"description": "Consulting fees", "amount": 10_00_00_000, "gst_treatment": "itc_eligible"},
        ])
        result = indian_tax_optimizer(lines)
        assert result["tax_optimization_available"] is True
        assert result["itc_leakage"]["total_spend_itc_eligible"] == pytest.approx(60_00_00_000)
        assert result["itc_leakage"]["estimated_itc_leakage"] > 0

    def test_rcm_lines_produce_exposure_estimate(self):
        lines = _make_lines([
            {"description": "Goods transport agency freight", "amount": 5_00_00_000, "gst_treatment": "rcm"},
        ])
        result = indian_tax_optimizer(lines)
        assert result["rcm_exposure"]["total_rcm_spend"] == pytest.approx(5_00_00_000)
        assert result["rcm_exposure"]["estimated_rcm_gst_liability"] > 0

    def test_keyword_inference_for_untagged_itc(self):
        """Without gst_treatment tag, keywords should still detect ITC-eligible spend."""
        lines = _make_lines([
            {"description": "software license annual", "amount": 20_00_000, "gst_treatment": None},
        ])
        result = indian_tax_optimizer(lines)
        assert result["itc_leakage"]["total_spend_itc_eligible"] > 0

    def test_keyword_inference_for_rcm(self):
        lines = _make_lines([
            {"description": "legal services individual advocate", "amount": 3_00_000, "gst_treatment": None},
        ])
        result = indian_tax_optimizer(lines)
        assert result["rcm_exposure"]["total_rcm_spend"] > 0

    def test_confidence_high_when_all_tagged(self):
        lines = _make_lines([
            {"description": "Cloud", "amount": 1_000, "gst_treatment": "itc_eligible"},
            {"description": "Canteen", "amount": 500, "gst_treatment": "ineligible"},
        ])
        result = indian_tax_optimizer(lines)
        assert result["confidence"] == "high"

    def test_confidence_low_when_untagged(self):
        lines = _make_lines([
            {"description": "Misc service", "amount": 1_000},
            {"description": "Other cost", "amount": 2_000},
        ])
        result = indian_tax_optimizer(lines)
        assert result["confidence"] == "low"

    def test_budget_lines_excluded(self):
        """Budget/forecast lines should not inflate ITC leakage estimates."""
        lines = _make_lines([
            {"description": "cloud", "amount": 10_00_00_000, "gst_treatment": "itc_eligible", "amount_type": "budget"},
        ])
        result = indian_tax_optimizer(lines)
        assert result["itc_leakage"]["total_spend_itc_eligible"] == pytest.approx(0.0)

    def test_section_115BAA_detected(self):
        lines = _make_lines([{"description": "it services", "amount": 1_000, "gst_treatment": "itc_eligible"}])
        result = indian_tax_optimizer(lines, effective_tax_rate=0.2517)
        assert result["section_115BAA"]["applicable"] is True

    def test_total_opportunity_is_sum(self):
        lines = _make_lines([
            {"description": "software", "amount": 10_00_000, "gst_treatment": "itc_eligible"},
            {"description": "transport", "amount": 5_00_000, "gst_treatment": "rcm"},
        ])
        result = indian_tax_optimizer(lines)
        expected = (
            result["itc_leakage"]["estimated_itc_leakage"]
            + result["rcm_exposure"]["estimated_rcm_gst_liability"]
        )
        assert result["total_tax_opportunity"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Ingestion — India column mapping
# ---------------------------------------------------------------------------

class TestIngestionIndiaColumns:
    def _write_csv(self, tmpdir, df: pd.DataFrame) -> Path:
        p = Path(tmpdir) / "test_india.csv"
        df.to_csv(p, index=False)
        return p

    def test_gst_treatment_column_mapped(self, tmp_path):
        from app.services.ingestion import parse_spend_file
        import json, pathlib
        taxonomy_path = pathlib.Path(
            "/Users/pallavchaturvedi/Agentic Projects/Opex Cost analyzer"
        ) / "skills" / "spend-profiler" / "references" / "spend_taxonomy.json"
        taxonomy = json.loads(taxonomy_path.read_text())

        df = pd.DataFrame({
            "supplier": ["TCS Ltd", "Freight Co"],
            "description": ["Cloud services", "Road transport"],
            "amount": [10_00_000, 5_00_000],
            "gst_treatment": ["itc_eligible", "rcm"],
            "gstin": ["27AATCS1234A1ZP", ""],
        })
        p = self._write_csv(tmp_path, df)
        lines = parse_spend_file(p, taxonomy)
        assert lines[0].gst_treatment == "itc_eligible"
        assert lines[0].gstin == "27AATCS1234A1ZP"
        assert lines[1].gst_treatment == "rcm"

    def test_related_party_column_mapped(self, tmp_path):
        from app.services.ingestion import parse_spend_file
        import json, pathlib
        taxonomy_path = pathlib.Path(
            "/Users/pallavchaturvedi/Agentic Projects/Opex Cost analyzer"
        ) / "skills" / "spend-profiler" / "references" / "spend_taxonomy.json"
        taxonomy = json.loads(taxonomy_path.read_text())

        df = pd.DataFrame({
            "supplier": ["GroupCo A", "External Vendor"],
            "description": ["Management fee", "Software license"],
            "amount": [2_00_000, 3_00_000],
            "related_party": ["yes", "no"],
        })
        p = self._write_csv(tmp_path, df)
        lines = parse_spend_file(p, taxonomy)
        assert lines[0].related_party_flag is True
        assert lines[1].related_party_flag is False

    def test_default_currency_inr(self, tmp_path):
        from app.services.ingestion import parse_spend_file
        import json, pathlib
        taxonomy_path = pathlib.Path(
            "/Users/pallavchaturvedi/Agentic Projects/Opex Cost analyzer"
        ) / "skills" / "spend-profiler" / "references" / "spend_taxonomy.json"
        taxonomy = json.loads(taxonomy_path.read_text())

        df = pd.DataFrame({
            "supplier": ["Vendor A"],
            "description": ["Service"],
            "amount": [5_00_000],
        })
        p = self._write_csv(tmp_path, df)
        lines = parse_spend_file(p, taxonomy)
        assert lines[0].currency == "INR"
