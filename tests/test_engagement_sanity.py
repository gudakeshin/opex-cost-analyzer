from __future__ import annotations

from app.services.engagement_sanity import (
    company_names_align,
    compute_engagement_sanity,
    extract_company_from_context_text,
    extract_company_from_filename,
    extract_revenue_cr_from_context_text,
    is_low_confidence_company_guess,
    is_placeholder_company,
    pick_best_company_guess,
    should_auto_apply_company,
)


def test_extract_company_from_belrise_filename() -> None:
    assert extract_company_from_filename("Belrise_Detailed_Spend_Report_FY25-v3.xlsx") == "Belrise"


def test_sample_files_do_not_extract_company() -> None:
    assert extract_company_from_filename("spend_ledger_sample.csv") is None
    assert extract_company_from_filename("pnl_expense_summary_sample.xlsx") is None


def test_budget_pack_filenames_do_not_extract_company() -> None:
    assert extract_company_from_filename("T2_04_budget_vs_actual_fy25.csv") is None
    assert extract_company_from_filename("T2_09_budget_memo.txt") is None


def test_extract_company_from_context_text_header() -> None:
    text = "Aranya Digital Services Ltd — FY26 Cost Optimisation Mandate (CFO memo)\n\nContext"
    assert extract_company_from_context_text(text) == "Aranya Digital Services Ltd"


def test_is_low_confidence_company_guess() -> None:
    assert is_low_confidence_company_guess("budget")
    assert is_low_confidence_company_guess("pnl")
    assert not is_low_confidence_company_guess("Aranya Digital Services Ltd")
    assert not is_low_confidence_company_guess("Belrise")


def test_pick_best_company_guess_prefers_high_confidence() -> None:
    votes = {"budget": 2.0, "aranya digital services ltd": 4.0}
    display = {
        "budget": "budget",
        "aranya digital services ltd": "Aranya Digital Services Ltd",
    }
    assert pick_best_company_guess(votes, display) == "Aranya Digital Services Ltd"


def test_pick_best_company_guess_empty_when_only_low_confidence() -> None:
    votes = {"hul": 2.0}
    display = {"hul": "hul"}
    assert pick_best_company_guess(votes, display) == ""


def test_should_auto_apply_company() -> None:
    assert not should_auto_apply_company("hul")
    assert not should_auto_apply_company("budget")
    assert should_auto_apply_company("Belrise")
    assert should_auto_apply_company("Aranya Digital Services Ltd")


def test_extract_company_from_deep_research_brief_pattern() -> None:
    text = (
        "Deep Research Brief — Indian IT/ITeS cost structure (for Aranya Digital Services Ltd)\n"
    )
    assert extract_company_from_context_text(text) == "Aranya Digital Services Ltd"


def test_extract_revenue_cr_from_annual_report_excerpt() -> None:
    text = (
        "Aranya Digital Services is an IT company. FY25 consolidated\n"
        "revenue was ₹18,400 Cr (FY24: ₹16,900 Cr), up 8.9% YoY."
    )
    assert extract_revenue_cr_from_context_text(text) == 18400.0


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
