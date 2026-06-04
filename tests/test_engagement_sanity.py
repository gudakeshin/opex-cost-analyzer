from __future__ import annotations

from app.services.engagement_sanity import (
    company_names_align,
    compute_engagement_sanity,
    extract_company_from_filename,
    is_placeholder_company,
)


def test_extract_company_from_belrise_filename() -> None:
    assert extract_company_from_filename("Belrise_Detailed_Spend_Report_FY25-v3.xlsx") == "Belrise"


def test_sample_files_do_not_extract_company() -> None:
    assert extract_company_from_filename("spend_ledger_sample.csv") is None
    assert extract_company_from_filename("pnl_expense_summary_sample.xlsx") is None


def test_company_names_align_substring_and_tokens() -> None:
    assert company_names_align("Belrise", "Belrise Industries")
    assert company_names_align("Belrise Industries Ltd", "Belrise")
    assert not company_names_align("Belrise", "Acme Corp")


def test_detect_upload_company_mismatch_against_diagnostic() -> None:
    manifest = {
        "company_name": "Belrise",
        "diagnostic_result": {"company_name": "Belrise"},
        "files": [
            {"name": "Acme_Detailed_Spend_Report_FY25.xlsx"},
        ],
    }
    sanity = compute_engagement_sanity(manifest)
    assert sanity["has_conflicts"] is True
    assert sanity["conflicts"][0]["detected_company"] == "Acme"
    assert sanity["conflicts"][0]["engagement_company"] == "Belrise"


def test_no_conflict_when_filename_matches_engagement() -> None:
    manifest = {
        "company_name": "Belrise",
        "diagnostic_result": {"company_name": "Belrise"},
        "files": [{"name": "Belrise_Detailed_Spend_Report_FY25-v3.xlsx"}],
    }
    sanity = compute_engagement_sanity(manifest)
    assert sanity["has_conflicts"] is False


def test_diagnostic_company_used_when_manifest_is_placeholder() -> None:
    manifest = {
        "company_name": "New engagement",
        "diagnostic_result": {"company_name": "Belrise"},
        "files": [{"name": "Acme_Spend_2024.xlsx"}],
    }
    sanity = compute_engagement_sanity(manifest)
    assert sanity["engagement_company"] == "Belrise"
    assert sanity["has_conflicts"] is True


def test_placeholder_company_skips_checks() -> None:
    manifest = {
        "company_name": "New engagement",
        "files": [{"name": "Belrise_Spend.xlsx"}],
    }
    sanity = compute_engagement_sanity(manifest)
    assert sanity["engagement_company"] is None
    assert sanity["has_conflicts"] is False
    assert is_placeholder_company("New engagement")
