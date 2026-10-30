from __future__ import annotations

import pytest

from app.services.benchmarks import (
    BENCHMARK_CSV_HEADERS,
    benchmark_csv_template,
    create_peer_set,
    ingest_benchmark_csv,
    list_datasets,
    list_peer_sets,
    resolve_benchmark_payload,
    sector_pack_benchmarks_payload,
)


def test_ingest_benchmark_csv_round_trip():
    csv_text = "industry,category_id,p25,p50,p75,p90\ntechnology,IT_SOFTWARE,2.0,3.0,4.0,5.0\n"
    ds = ingest_benchmark_csv(
        file_bytes=csv_text.encode("utf-8"),
        source="test_upload",
        industry_code="technology",
        industry_name="Technology test",
        specificity_score=0.72,
    )
    assert ds["dataset_id"]
    assert ds["industry_name"] == "Technology test"
    assert "technology" in (ds.get("category_coverage") or {})


def test_ingest_full_column_csv_round_trip(tmp_path):
    csv_text = (
        f"{BENCHMARK_CSV_HEADERS}\n"
        "bfsi_banks,BFSI Banks,IT_SOFTWARE,IT Software,large,1000,,India,"
        "% of revenue,4.0,7.0,10.0,14.0,5,public_disclosure,published_research,"
        "RBI FY25,Bank IT benchmark,2025-04-01\n"
    )
    ds = ingest_benchmark_csv(
        file_bytes=csv_text.encode("utf-8"),
        source="licensed_test",
        industry_code="bfsi_banks",
        industry_name="BFSI Banks",
        sample_size=0,
        specificity_score=0.9,
        revenue_band_min=1000.0,
        data_dir=tmp_path / "uploads",
    )
    assert ds["sample_size"] == 5
    assert ds["revenue_band_min"] == 1000.0
    from pathlib import Path
    from app.storage import read_json

    data = read_json(Path(ds["data_file_ref"]), {})
    cat = data["benchmarks"]["bfsi_banks"]["categories"]["IT_SOFTWARE"]
    assert cat["unit"] == "% of revenue"
    assert cat["confidence"] == "public_disclosure"
    assert cat["P50"] == 7.0


def test_ingest_rejects_non_monotonic_percentiles():
    csv_text = "industry,category_id,p25,p50,p75,p90\ntech,IT,5.0,3.0,4.0,6.0\n"
    with pytest.raises(ValueError, match="monotonic"):
        ingest_benchmark_csv(
            file_bytes=csv_text.encode("utf-8"),
            source="bad",
        )


def test_benchmark_csv_template_headers():
    tpl = benchmark_csv_template()
    assert BENCHMARK_CSV_HEADERS in tpl
    assert "bfsi_banks" in tpl
    assert tpl.strip().startswith("#")


def test_list_datasets_includes_sector_packs():
    datasets = list_datasets(include_sector_packs=True)
    pack_ids = [d["dataset_id"] for d in datasets if str(d.get("dataset_id", "")).startswith("sector-pack-")]
    assert len(pack_ids) >= 1
    assert any("bfsi_banks" in pid for pid in pack_ids)


def test_sector_pack_benchmarks_payload():
    payload = sector_pack_benchmarks_payload("bfsi_banks")
    assert payload is not None
    assert payload["pack_id"] == "bfsi_banks"
    assert payload["categories"]
    assert "IT_SOFTWARE" in payload["categories"]
    assert payload["categories"]["IT_SOFTWARE"].get("unit")


def test_benchmark_template_endpoint(client):
    resp = client.get("/api/v1/template/benchmark-csv")
    assert resp.status_code == 200
    assert "industry_code" in resp.text
    assert "bfsi_banks" in resp.text


def test_peer_set_create_and_resolve():
    ps = create_peer_set(
        name="test-peer-set-unit",
        industry="technology",
        dataset_ids=[],
        description="unit test",
    )
    assert ps["name"] == "test-peer-set-unit"
    names = [p["name"] for p in list_peer_sets()]
    assert "test-peer-set-unit" in names


def test_resolve_benchmark_payload_with_peer_set():
    result = resolve_benchmark_payload(
        industry="technology",
        categories=["IT_SOFTWARE"],
        peer_set_name="test-peer-set-unit",
    )
    assert "benchmark_data" in result
    assert result["benchmark_data"].get("benchmarks")
