"""Sector-pack → benchmark registry mapping must have a single source of truth."""
from __future__ import annotations

from app.services.benchmarks import SECTOR_PACK_TO_BENCHMARK, benchmark_industry_for


def test_gcc_capability_centers_maps_to_self() -> None:
    assert SECTOR_PACK_TO_BENCHMARK["gcc_capability_centers"] == "gcc_capability_centers"
    assert benchmark_industry_for("gcc_capability_centers") == "gcc_capability_centers"


def test_fmcg_consumer_maps_to_retail_consumer() -> None:
    assert SECTOR_PACK_TO_BENCHMARK["fmcg_consumer"] == "retail_consumer"
    assert benchmark_industry_for("fmcg_consumer") == "retail_consumer"


def test_benchmark_industry_for_passthrough_for_registry_keys() -> None:
    assert benchmark_industry_for("technology") == "technology"
    assert benchmark_industry_for("manufacturing") == "manufacturing"
