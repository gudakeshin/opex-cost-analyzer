from __future__ import annotations

from app.services.engagement_detection import reconcile_detection_view
from app.services.engagement_sanity import (
    company_names_align,
    compute_engagement_sanity,
    extract_company_from_context_text,
    extract_company_from_filename,
    extract_revenue_cr_from_context_text,
    infer_industry_from_company_name,
    industries_align,
    is_low_confidence_company_guess,
    is_placeholder_company,
    is_placeholder_industry,
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


def test_industries_align_conglomerate_umbrella() -> None:
    assert industries_align("fmcg_consumer", "conglomerate", strict=False)
    assert not industries_align("bfsi_banks", "fmcg_consumer", strict=True)
    assert industries_align("conglomerate", "fmcg_consumer", strict=True)


def test_industry_mismatch_when_set_sector_conflicts_with_spend() -> None:
    manifest = {
        "company_name": "Indus Apex Bank Ltd",
        "industry": "bfsi_banks",
        "detected_industry": "conglomerate",
        "detected_industry_label": "Conglomerate",
        "detection_signals": {"industry_spend": "fmcg_consumer"},
    }
    sanity = compute_engagement_sanity(manifest)
    assert sanity["has_conflicts"] is True
    industry_conflicts = [c for c in sanity["conflicts"] if c["kind"] == "industry_mismatch"]
    assert len(industry_conflicts) == 1
    assert industry_conflicts[0]["engagement_industry"] == "bfsi_banks"
    assert industry_conflicts[0]["detected_industry"] == "fmcg_consumer"
    assert industry_conflicts[0]["industry_spend"] == "fmcg_consumer"


def test_no_industry_conflict_when_detected_matches_set() -> None:
    manifest = {
        "company_name": "Prakrit Consumer Brands",
        "industry": "fmcg_consumer",
        "detected_industry": "fmcg_consumer",
        "detection_signals": {"industry_spend": "fmcg_consumer"},
    }
    sanity = compute_engagement_sanity(manifest)
    industry_conflicts = [c for c in sanity["conflicts"] if c["kind"] == "industry_mismatch"]
    assert industry_conflicts == []


def test_no_industry_conflict_for_placeholder_industry() -> None:
    manifest = {
        "industry": "manufacturing_diversified",
        "detected_industry": "fmcg_consumer",
        "detection_signals": {"industry_spend": "fmcg_consumer"},
    }
    sanity = compute_engagement_sanity(manifest)
    industry_conflicts = [c for c in sanity["conflicts"] if c["kind"] == "industry_mismatch"]
    assert industry_conflicts == []
    assert is_placeholder_industry("manufacturing_diversified")


def test_fmcg_set_with_conglomerate_detected_is_ok_without_spend_conflict() -> None:
    manifest = {
        "industry": "fmcg_consumer",
        "detected_industry": "conglomerate",
        "detection_signals": {"industry_spend": "fmcg_consumer"},
    }
    sanity = compute_engagement_sanity(manifest)
    industry_conflicts = [c for c in sanity["conflicts"] if c["kind"] == "industry_mismatch"]
    assert industry_conflicts == []


def test_infer_industry_from_bank_company_name() -> None:
    assert infer_industry_from_company_name("Indus Apex Bank Ltd") == "bfsi_banks"
    assert infer_industry_from_company_name("Aranya Digital Services Ltd") == "it_ites"


def test_reconcile_detection_view_fixes_bank_misclassified_as_it() -> None:
    manifest = {
        "company_name": "Indus Apex Bank Ltd",
        "industry": "bfsi_banks",
        "detected_industry": "it_ites",
        "detected_industry_label": "IT / ITES",
        "detection_signals": {"industry_llm": "it_ites", "industry_spend": "bfsi_banks"},
    }
    fixed = reconcile_detection_view(manifest)
    assert fixed["detected_industry"] == "bfsi_banks"
    assert fixed["detected_industry_label"] == "BFSI / Banks"
