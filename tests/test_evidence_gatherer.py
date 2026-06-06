"""Tests for document-aware evidence gathering."""
from datetime import date

import pytest

from app.models import NormalizedSpendLine
from app.skills.engine.evidence import (
    build_contracts_by_category,
    evidence_gatherer,
    requirements_for_initiative,
)
from app.skills.engine.sme_critique import sme_critique_analyzer


def _line(**kwargs) -> NormalizedSpendLine:
    base = {
        "row_id": 1,
        "category_id": "it_software",
        "category_name": "IT Software",
        "supplier": "Acme Corp",
        "description": "IT services",
        "amount": 100_000.0,
        "currency": "INR",
    }
    base.update(kwargs)
    return NormalizedSpendLine(**base)


def test_requirements_for_supplier_consolidation():
    reqs = requirements_for_initiative({"lever": "supplier_consolidation"})
    types = {r.signal_type for r in reqs}
    assert "contract_terms" in types
    assert "supplier_fragmentation" in types


def test_build_contracts_from_spend_lines():
    lines = [
        _line(supplier="Vendor A", contract_expiry_date=date(2027, 6, 1), contract_status="in_contract"),
        _line(supplier="Vendor B", contract_expiry_date=date(2026, 1, 1)),
    ]
    lifecycle = {
        "renewal_alerts": [
            {
                "supplier": "Vendor B",
                "contract_expiry_date": "2026-01-01",
                "contract_status": "at_risk",
                "alert_type": "at_risk",
            }
        ]
    }
    by_cat = build_contracts_by_category(lines, lifecycle)
    assert "it_software" in by_cat
    assert len(by_cat["it_software"]) >= 2


def test_evidence_gatherer_finds_supplier_signal():
    initiative = {
        "category_id": "it_software",
        "category_name": "IT Software",
        "lever": "supplier_consolidation",
        "net_savings": {"total_3yr": 300},
    }
    spend_profile = {
        "category_profile": [
            {
                "category_id": "it_software",
                "category_name": "IT Software",
                "supplier_count": 15,
                "hhi": 0.68,
            }
        ]
    }
    lines = [_line(row_id=i + 1, supplier=f"Vendor {i}") for i in range(15)]
    result = evidence_gatherer(
        {"initiatives": [initiative]},
        spend_profile,
        {"root_cause_findings": []},
        {"renewal_alerts": []},
        {"comparisons": []},
        lines,
        engagement_id="",
    )
    inv = result["evidence_inventory"][0]
    supplier_sig = inv["signals"].get("supplier_fragmentation")
    assert supplier_sig is not None
    assert supplier_sig["status"] == "found"
    assert "15 suppliers" in supplier_sig["summary"]


def test_sme_critique_does_not_claim_no_supplier_when_found():
    initiative = {
        "category_id": "it_software",
        "category_name": "IT Software",
        "lever": "supplier_consolidation",
        "confidence": "medium",
        "net_savings": {"total_3yr": 300},
    }
    spend_profile = {
        "category_profile": [
            {"category_id": "it_software", "supplier_count": 10},
        ]
    }
    lines = [_line(row_id=i + 1, supplier=f"V{i}") for i in range(10)]
    evidence_output = evidence_gatherer(
        {"initiatives": [initiative]},
        spend_profile,
        {"root_cause_findings": []},
        {"renewal_alerts": []},
        {"comparisons": []},
        lines,
        engagement_id="",
    )
    result = sme_critique_analyzer(
        {"initiatives": [initiative]},
        spend_profile,
        {"comparisons": []},
        {"root_cause_findings": []},
        {"renewal_alerts": []},
        evidence_gatherer_output=evidence_output,
        lines=lines,
    )
    critique = result["initiative_critiques"][0]
    assert critique["sme_verdict"] != "insufficient_data" or "no supplier" not in critique["critical_risk"].lower()
    assert "supplier_fragmentation" in (critique.get("evidence_sources") or {})


def test_sme_insufficient_data_only_when_zero_evidence():
    initiative = {
        "category_id": "hr",
        "category_name": "HR",
        "lever": "supplier_consolidation",
        "net_savings": {"total_3yr": 100},
    }
    result = sme_critique_analyzer(
        {"initiatives": [initiative]},
        {"category_profile": []},
        {"comparisons": []},
        {"root_cause_findings": []},
        {"renewal_alerts": []},
        evidence_gatherer_output=evidence_gatherer(
            {"initiatives": [initiative]},
            {"category_profile": []},
            {"root_cause_findings": []},
            {"renewal_alerts": []},
            {"comparisons": []},
            [],
            engagement_id="",
        ),
        lines=[],
    )
    critique = result["initiative_critiques"][0]
    assert critique["sme_verdict"] == "insufficient_data"
    assert "Benchmark gap only" in critique["critical_risk"] or "Upload" in critique["critical_risk"]
