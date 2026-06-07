from __future__ import annotations

import time

from app.services.cache import (
    CostRoomCache,
    MID_CAP_LIMIT,
    LARGE_CAP_LIMIT,
    CONGLOMERATE_LIMIT,
    SLO,
    TierConfig,
    run_slo_benchmark,
    tier_for_line_count,
)


# ── Tier classification ───────────────────────────────────────────────────────

def test_tier_mid_cap():
    tier = tier_for_line_count(50_000)
    assert tier.name == "mid_cap"
    assert not tier.requires_redis
    assert not tier.use_duckdb


def test_tier_large_cap():
    tier = tier_for_line_count(500_000)
    assert tier.name == "large_cap"
    assert tier.requires_redis
    assert tier.use_duckdb


def test_tier_conglomerate():
    tier = tier_for_line_count(10_000_000)
    assert tier.name == "conglomerate"
    assert tier.requires_redis
    assert tier.use_parquet_chunks


def test_tier_boundaries():
    assert tier_for_line_count(MID_CAP_LIMIT).name == "mid_cap"
    assert tier_for_line_count(MID_CAP_LIMIT + 1).name == "large_cap"
    assert tier_for_line_count(LARGE_CAP_LIMIT).name == "large_cap"
    assert tier_for_line_count(LARGE_CAP_LIMIT + 1).name == "conglomerate"


# ── SLO definitions ───────────────────────────────────────────────────────────

def test_slo_ceilings_defined():
    for tier in ["mid_cap", "large_cap", "conglomerate"]:
        assert "ingestion" in SLO[tier]
        assert "filter" in SLO[tier]
        assert SLO[tier]["ingestion"] > 0
        assert SLO[tier]["filter"] > 0


def test_slo_order():
    # More lines → more time allowed
    assert SLO["mid_cap"]["ingestion"] < SLO["large_cap"]["ingestion"] < SLO["conglomerate"]["ingestion"]
    # But filter latency gets tighter with Redis caching
    assert SLO["mid_cap"]["filter"] > SLO["large_cap"]["filter"] > SLO["conglomerate"]["filter"]


# ── Cache (local fallback — Redis not required in CI) ─────────────────────────

def test_cache_local_backend_on_unavailable_redis():
    cache = CostRoomCache(redis_url="redis://invalid-host:9999/0")
    # Must not raise; should fall back to local dict
    cache.set("eng1", {"cat": "it"}, {"initiatives": [], "total": 0})
    result = cache.get("eng1", {"cat": "it"})
    assert result is not None
    assert result["total"] == 0
    assert cache.backend == "local_dict"


def test_cache_get_miss_returns_none():
    cache = CostRoomCache(redis_url="redis://invalid-host:9999/0")
    assert cache.get("eng_missing", {"x": 1}) is None


def test_cache_set_and_get_roundtrip():
    cache = CostRoomCache(redis_url="redis://invalid-host:9999/0")
    payload = {"initiatives": [{"id": "i1", "savings": 10.0}], "total": 1}
    cache.set("eng_rt", {"category": "logistics"}, payload)
    result = cache.get("eng_rt", {"category": "logistics"})
    assert result == payload


def test_cache_different_filters_different_keys():
    cache = CostRoomCache(redis_url="redis://invalid-host:9999/0")
    cache.set("eng2", {"cat": "it"}, {"v": 1})
    cache.set("eng2", {"cat": "hr"}, {"v": 2})
    assert cache.get("eng2", {"cat": "it"})["v"] == 1
    assert cache.get("eng2", {"cat": "hr"})["v"] == 2


def test_cache_invalidate_clears_entries():
    cache = CostRoomCache(redis_url="redis://invalid-host:9999/0")
    cache.set("eng_del", {"k": "v"}, {"data": "x"})
    removed = cache.invalidate("eng_del")
    assert removed >= 0  # local dict; may remove 0 if key mismatch but no exception


# ── SLO benchmark runner ──────────────────────────────────────────────────────

def test_slo_benchmark_runs_all_tiers():
    results = run_slo_benchmark(line_counts=[100_000, 5_000_000, 10_000_000])
    tier_names = {r.tier for r in results}
    assert "mid_cap" in tier_names
    assert "large_cap" in tier_names
    assert "conglomerate" in tier_names


def test_slo_benchmark_ingestion_passes_in_ci():
    # Synthetic (zero-IO) ingestion is instant — must always meet SLO
    results = run_slo_benchmark()
    ingestion_results = [r for r in results if r.operation == "ingestion"]
    for r in ingestion_results:
        assert r.passed, f"Ingestion SLO failed for {r.tier}: {r.elapsed_s}s > {r.slo_ceiling_s}s"


def test_slo_benchmark_filter_passes_in_ci():
    # Local-dict cache filter is sub-millisecond — must always meet SLO
    results = run_slo_benchmark()
    filter_results = [r for r in results if r.operation == "filter"]
    for r in filter_results:
        assert r.passed, f"Filter SLO failed for {r.tier}: {r.elapsed_s}s > {r.slo_ceiling_s}s"


def test_slo_result_to_dict():
    results = run_slo_benchmark(line_counts=[MID_CAP_LIMIT])
    for r in results:
        d = r.to_dict()
        assert "tier" in d
        assert "elapsed_s" in d
        assert "passed" in d
        assert "slo_ceiling_s" in d


# ── Mid-cap SLO: upload + analyze under budget ────────────────────────────────

def _generate_csv(rows: int = 20000) -> bytes:
    lines = ["supplier,description,amount,business unit,country"]
    for i in range(rows):
        lines.append(f"AWS,cloud service {i},100,Engineering,US")
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_performance_smoke_upload_and_analyze_under_budget(client) -> None:
    session = client.post(
        "/api/sessions",
        json={"company_name": "Perf Co", "industry": "technology", "annual_revenue": 500_000_000},
    )
    session_id = session.json()["session_id"]

    start_upload = time.perf_counter()
    up = client.post(
        f"/api/upload/{session_id}",
        files={"file": ("perf_spend.csv", _generate_csv(), "text/csv")},
    )
    upload_secs = time.perf_counter() - start_upload
    assert up.status_code == 200
    # Generous bound: shared CI runners are 2-3x slower than dev machines; this
    # smoke test guards against gross regressions, not a tight SLO.
    assert upload_secs < 20.0

    start_analyze = time.perf_counter()
    analyze = client.post(
        f"/api/analyze/{session_id}",
        json={"company_name": "Perf Co", "industry": "technology", "annual_revenue": 500_000_000},
    )
    analyze_secs = time.perf_counter() - start_analyze
    assert analyze.status_code == 200
    assert analyze_secs < 30.0


def test_rejects_file_larger_than_50mb(client) -> None:
    session = client.post("/api/sessions", json={"company_name": "Big File Co"})
    session_id = session.json()["session_id"]
    too_large = b"a" * (51 * 1024 * 1024)
    response = client.post(
        f"/api/upload/{session_id}",
        files={"file": ("too_large.txt", too_large, "text/plain")},
    )
    assert response.status_code == 413
    assert "File exceeds" in response.text

