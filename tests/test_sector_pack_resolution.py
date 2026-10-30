from __future__ import annotations

from app.services.benchmarks import benchmark_industry_for
from app.services.sector_packs import normalize_industry_selection, resolve_sector_pack_id
from app.skills.engine._loaders import _resolve_pack_id


def test_pack_id_passthrough() -> None:
    assert resolve_sector_pack_id("fmcg_consumer") == "fmcg_consumer"
    assert resolve_sector_pack_id("bfsi_banks") == "bfsi_banks"


def test_healthcare_hospitals_not_mapped_to_pharma() -> None:
    assert _resolve_pack_id("healthcare_hospitals") == "healthcare_hospitals"
    assert resolve_sector_pack_id("healthcare_hospitals") == "healthcare_hospitals"


def test_free_text_maps_to_pack() -> None:
    assert resolve_sector_pack_id("FMCG") == "fmcg_consumer"
    assert resolve_sector_pack_id("IT Services") == "it_ites"


def test_normalize_industry_selection() -> None:
    assert normalize_industry_selection("  bfsi_banks ") == "bfsi_banks"
    assert normalize_industry_selection("banking") == "bfsi_banks"
    assert normalize_industry_selection(None) is None


def test_benchmark_industry_uses_resolved_pack() -> None:
    assert benchmark_industry_for("fmcg_consumer") == "retail_consumer"
    assert benchmark_industry_for("banking") == "financial_services"
