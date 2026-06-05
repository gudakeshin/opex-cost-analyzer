from __future__ import annotations

import csv
import io
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR, ROOT_DIR
from app.storage import read_json, write_json

BENCHMARK_STORE_PATH = DATA_DIR / "benchmarks" / "registry.json"
PEER_SETS_PATH = DATA_DIR / "benchmarks" / "peer_sets.json"
SEED_PATH = ROOT_DIR / "skills" / "peer-benchmarker" / "references" / "industry_benchmarks.json"

# Sector-pack IDs (used by industry inference, lever rules, the diagnostic UI)
# are a finer taxonomy than the benchmark registry, which is keyed by a coarser
# set of industries. This maps a sector pack to the benchmark industry whose
# category percentiles best represent it, so peer benchmarking resolves instead
# of silently returning zero comparisons (e.g. an FMCG ledger inferred as
# `fmcg_consumer` reads `retail_consumer` benchmarks).
SECTOR_PACK_TO_BENCHMARK: Dict[str, str] = {
    "it_ites": "technology",
    "gcc_capability_centers": "gcc_capability_centers",
    "bfsi_banks": "financial_services",
    "financial_services_nonbank": "financial_services",
    "insurance_general": "financial_services",
    "fmcg_consumer": "retail_consumer",
    "retail_organized": "retail_consumer",
    "hospitality_travel": "retail_consumer",
    "pharma_lifesciences": "healthcare",
    "healthcare_hospitals": "healthcare",
    "energy_utilities": "manufacturing",
    "telecom_infra": "technology",
    "manufacturing_diversified": "manufacturing",
    "psu_cpse": "manufacturing",
    "conglomerate": "manufacturing",
}


def benchmark_industry_for(industry: str) -> str:
    """Resolve a sector-pack id (or raw industry) to a benchmark-registry key."""
    key = (industry or "").strip()
    result = SECTOR_PACK_TO_BENCHMARK.get(key, key)
    if result == key and key and key not in SECTOR_PACK_TO_BENCHMARK.values():
        from app.config import logger
        logger.warning("benchmark_industry_for: no mapping for %r — passing through as-is", key)
    return result

# Lock protecting all read-modify-write operations on the benchmark store.
_LOCK = threading.Lock()


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_seed_dataset() -> Dict[str, Any]:
    seed = read_json(SEED_PATH, {})
    category_coverage = {}
    for industry, data in seed.get("benchmarks", {}).items():
        category_coverage[industry] = sorted(list((data.get("categories") or {}).keys()))
    # Derive source attribution from seed metadata — prefer named external sources over internal ones
    primary_sources = seed.get("source_metadata", {}).get("primary_sources", [])
    external = [
        s["source_name"] for s in primary_sources
        if s.get("source_name") and s.get("source_type") not in ("internal_calibration", "internal")
    ]
    source_label = " / ".join(external) + " (illustrative)" if external else "platform_seed"
    return {
        "dataset_id": "seed-industry-benchmarks",
        "source": source_label,
        "industry_code": None,
        "industry_name": "Cross-industry seed benchmarks",
        "category_coverage": category_coverage,
        "vintage_date": _today_iso(),
        "sample_size": 0,
        "revenue_band_min": 0,
        "revenue_band_max": None,
        "geography": "global",
        "specificity_score": 0.55,
        "license_expiry": "2099-12-31",
        "data_file_ref": str(SEED_PATH),
        "ingested_at": _now_iso(),
    }


def _load_store() -> Dict[str, Any]:
    store = read_json(BENCHMARK_STORE_PATH, {"datasets": []})
    datasets = store.get("datasets", [])
    if not datasets:
        store["datasets"] = [_load_seed_dataset()]
        write_json(BENCHMARK_STORE_PATH, store)
    elif any(d.get("source") == "platform_seed" for d in datasets):
        # Refresh cached seed entry that still has the old generic source label
        fresh = _load_seed_dataset()
        store["datasets"] = [fresh if d.get("source") == "platform_seed" else d for d in datasets]
        write_json(BENCHMARK_STORE_PATH, store)
    return store


def _save_store(store: Dict[str, Any]) -> None:
    write_json(BENCHMARK_STORE_PATH, store)


def list_datasets() -> List[Dict[str, Any]]:
    return _load_store().get("datasets", [])


def create_dataset(payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "dataset_id": str(uuid.uuid4()),
        "source": payload.get("source"),
        "industry_code": payload.get("industry_code"),
        "industry_name": payload.get("industry_name"),
        "category_coverage": payload.get("category_coverage") or {},
        "vintage_date": payload.get("vintage_date") or _today_iso(),
        "sample_size": int(payload.get("sample_size") or 0),
        "revenue_band_min": payload.get("revenue_band_min"),
        "revenue_band_max": payload.get("revenue_band_max"),
        "geography": payload.get("geography"),
        "specificity_score": float(payload.get("specificity_score") or 0.5),
        "license_expiry": payload.get("license_expiry") or "2099-12-31",
        "data_file_ref": payload.get("data_file_ref"),
        "ingested_at": _now_iso(),
    }
    with _LOCK:
        store = _load_store()
        store.setdefault("datasets", []).append(row)
        _save_store(store)
    return row


def get_dataset(dataset_id: str) -> Dict[str, Any] | None:
    for row in _load_store().get("datasets", []):
        if row.get("dataset_id") == dataset_id:
            return row
    return None


def dataset_coverage(dataset_id: str) -> Dict[str, Any] | None:
    ds = get_dataset(dataset_id)
    if not ds:
        return None
    coverage = ds.get("category_coverage") or {}
    industry_count = len(coverage.keys()) if isinstance(coverage, dict) else 0
    category_count = 0
    if isinstance(coverage, dict):
        for cats in coverage.values():
            if isinstance(cats, list):
                category_count += len(cats)
    return {
        "dataset_id": ds.get("dataset_id"),
        "source": ds.get("source"),
        "industry_name": ds.get("industry_name"),
        "specificity_score": ds.get("specificity_score", 0.0),
        "vintage_date": ds.get("vintage_date"),
        "coverage": coverage,
        "industry_count": industry_count,
        "category_count": category_count,
    }


def select_best_dataset(industry: str, categories: List[str], annual_revenue: float | None = None) -> Dict[str, Any]:
    # Compute today once — avoids calling date.today() per dataset in the loop.
    today = _today_iso()
    candidates: List[Dict[str, Any]] = []
    for ds in _load_store().get("datasets", []):
        expiry = ds.get("license_expiry")
        if expiry and expiry < today:
            continue
        coverage = ds.get("category_coverage") or {}
        covered = set(coverage.get(industry, [])) if isinstance(coverage, dict) else set()
        match_ratio = (len(covered.intersection(set(categories))) / len(categories)) if categories else 0.0
        spec = float(ds.get("specificity_score") or 0.0)
        revenue_score = 0.1
        if annual_revenue is not None:
            min_rev = ds.get("revenue_band_min")
            max_rev = ds.get("revenue_band_max")
            if min_rev is None and max_rev is None:
                revenue_score = 0.1
            elif max_rev is None and annual_revenue >= float(min_rev or 0):
                revenue_score = 1.0
            elif min_rev is not None and max_rev is not None and float(min_rev) <= annual_revenue <= float(max_rev):
                revenue_score = 1.0
            else:
                revenue_score = 0.2
        score = (match_ratio * 0.5) + (spec * 0.35) + (revenue_score * 0.15)
        candidates.append({"dataset": ds, "score": score, "match_ratio": match_ratio, "revenue_score": revenue_score})
    if not candidates:
        return {"selected": None, "candidates": []}
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    return {
        "selected": best["dataset"],
        "selection_rationale": {
            "score": round(best["score"], 4),
            "match_ratio": round(best["match_ratio"], 4),
            "revenue_score": round(best["revenue_score"], 4),
            "industry": industry,
            "requested_categories": categories,
        },
        "candidates": [
            {
                "dataset_id": c["dataset"].get("dataset_id"),
                "source": c["dataset"].get("source"),
                "score": round(c["score"], 4),
            }
            for c in candidates[:5]
        ],
    }


def ingest_benchmark_csv(
    file_bytes: bytes,
    source: str,
    industry_code: Optional[str] = None,
    industry_name: Optional[str] = None,
    vintage_date: Optional[str] = None,
    sample_size: int = 0,
    geography: str = "India",
    specificity_score: float = 0.7,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Parse a client-supplied benchmark CSV and register it as a dataset.

    Expected CSV columns (flexible, case-insensitive):
      industry, category_id, p25, p50, p75, p90  (p* are % of revenue)
    At minimum: industry + category_id + one of (p50 | benchmark_pct_of_revenue).

    Saves the parsed benchmark data as a JSON file and registers the dataset.
    Returns the created dataset registry entry.
    """
    store_dir = data_dir or (DATA_DIR / "benchmarks" / "uploads")
    store_dir.mkdir(parents=True, exist_ok=True)

    # Parse CSV bytes
    try:
        text = file_bytes.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows = [row for row in reader]

    if not rows:
        raise ValueError("Uploaded benchmark CSV is empty or has no data rows")

    # Normalize column names (lowercase, strip spaces/underscores)
    def _norm_col(name: str) -> str:
        return name.strip().lower().replace(" ", "_")

    normalized_rows = [{_norm_col(k): v for k, v in r.items()} for r in rows]

    # Build benchmark_data JSON in the same shape as industry_benchmarks.json:
    # { "benchmarks": { industry: { "categories": { cat_id: { P25, P50, P75, P90 } } } } }
    benchmarks: Dict[str, Any] = {}
    category_coverage: Dict[str, List[str]] = {}

    for row in normalized_rows:
        ind = (row.get("industry") or industry_code or "custom").strip()
        cat = (row.get("category_id") or row.get("category") or "").strip()
        if not cat:
            continue

        def _pct(key: str) -> float:
            try:
                return float(row.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0.0

        p50 = _pct("p50") or _pct("benchmark_pct_of_revenue") or _pct("median")
        p25 = _pct("p25") or round(p50 * 0.8, 4)
        p75 = _pct("p75") or round(p50 * 1.2, 4)
        p90 = _pct("p90") or round(p50 * 1.4, 4)

        benchmarks.setdefault(ind, {"categories": {}})
        benchmarks[ind]["categories"][cat] = {
            "P25": p25,
            "P50": p50,
            "P75": p75,
            "P90": p90,
        }
        category_coverage.setdefault(ind, [])
        if cat not in category_coverage[ind]:
            category_coverage[ind].append(cat)

    if not benchmarks:
        raise ValueError("No parseable benchmark rows found — check CSV column names")

    # Persist benchmark data JSON
    file_id = str(uuid.uuid4())
    data_path = store_dir / f"{file_id}.json"
    write_json(data_path, {"benchmarks": benchmarks})

    dataset = create_dataset(
        {
            "source": source,
            "industry_code": industry_code,
            "industry_name": industry_name or industry_code,
            "category_coverage": category_coverage,
            "vintage_date": vintage_date or _today_iso(),
            "sample_size": sample_size,
            "geography": geography,
            "specificity_score": specificity_score,
            "data_file_ref": str(data_path),
        }
    )
    return dataset


# ---------------------------------------------------------------------------
# Peer set management
# ---------------------------------------------------------------------------

def _load_peer_sets() -> Dict[str, Any]:
    return read_json(PEER_SETS_PATH, {"peer_sets": []})


def _save_peer_sets(store: Dict[str, Any]) -> None:
    PEER_SETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(PEER_SETS_PATH, store)


def list_peer_sets() -> List[Dict[str, Any]]:
    return _load_peer_sets().get("peer_sets", [])


def get_peer_set(name: str) -> Optional[Dict[str, Any]]:
    for ps in _load_peer_sets().get("peer_sets", []):
        if ps.get("name") == name:
            return ps
    return None


def create_peer_set(
    name: str,
    industry: str,
    dataset_ids: List[str],
    description: str = "",
    override_categories: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create or replace a named peer set combining specific benchmark datasets.

    override_categories allows clients to pin specific category benchmarks
    (e.g. {"IT": {"P50": 3.2}}) that override whatever the datasets provide.
    """
    with _LOCK:
        store = _load_peer_sets()
        # Remove existing peer set with same name (upsert semantics)
        store["peer_sets"] = [ps for ps in store.get("peer_sets", []) if ps.get("name") != name]
        row: Dict[str, Any] = {
            "name": name,
            "industry": industry,
            "description": description,
            "dataset_ids": dataset_ids,
            "override_categories": override_categories or {},
            "created_at": _now_iso(),
        }
        store["peer_sets"].append(row)
        _save_peer_sets(store)
    return row


def resolve_peer_set_payload(peer_set_name: str, categories: List[str], annual_revenue: float | None = None) -> Dict[str, Any]:
    """Resolve a named peer set into benchmark_data, honouring overrides."""
    ps = get_peer_set(peer_set_name)
    if not ps:
        raise ValueError(f"Peer set '{peer_set_name}' not found")

    industry = ps["industry"]
    dataset_ids = ps.get("dataset_ids", [])
    overrides = ps.get("override_categories", {})

    # Merge benchmark data from all referenced datasets (last wins per category).
    merged_categories: Dict[str, Any] = {}
    selected_dataset: Optional[Dict[str, Any]] = None
    all_datasets = {ds["dataset_id"]: ds for ds in list_datasets()}

    for did in dataset_ids:
        ds = all_datasets.get(did)
        if not ds:
            continue
        data_ref = ds.get("data_file_ref")
        if data_ref:
            path = Path(str(data_ref))
            if path.exists():
                loaded = read_json(path, {})
                cats = loaded.get("benchmarks", {}).get(industry, {}).get("categories", {})
                merged_categories.update(cats)
        selected_dataset = ds  # last dataset is the "primary" for metadata

    # Apply client overrides (highest priority).
    merged_categories.update(overrides)

    benchmark_data = {"benchmarks": {industry: {"categories": merged_categories}}}
    return {
        "benchmark_data": benchmark_data,
        "selected_dataset": selected_dataset or {},
        "selection_rationale": {"peer_set": peer_set_name, "dataset_ids": dataset_ids},
        "candidates": [{"dataset_id": did} for did in dataset_ids],
    }


def _load_sector_pack_benchmarks(pack_id: str) -> Dict[str, Any] | None:
    """Load sector-specific percentile benchmarks from the sector pack directory.

    Returns the parsed JSON if the file exists and is valid, otherwise None.
    Sector pack files take priority over the global seed — they carry verified
    public-disclosure data derived from actual annual reports and regulator
    publications, so specificity_score is set to 0.85 (vs seed's 0.55).
    """
    pack_file = ROOT_DIR / "sector_packs" / pack_id / "benchmarks_percentiles.json"
    if not pack_file.exists():
        return None
    data = read_json(pack_file, {})
    return data if data.get("benchmarks") else None


def _sector_pack_dataset_meta(pack_id: str, pack_data: Dict[str, Any]) -> Dict[str, Any]:
    """Synthesise a dataset registry entry for a sector-pack percentile file."""
    sources = pack_data.get("source_metadata", {}).get("primary_sources", [])
    external = [s["source_name"] for s in sources if s.get("source_type") != "internal_calibration"]
    source_label = " / ".join(external[:3]) + " (public_disclosure)" if external else f"{pack_id} sector pack"
    categories_in_pack = sorted(
        list((pack_data.get("benchmarks", {}).get(pack_id, {}).get("categories") or {}).keys())
    )
    return {
        "dataset_id": f"sector-pack-{pack_id}",
        "source": source_label,
        "industry_code": pack_id,
        "industry_name": pack_data.get("sector", pack_id),
        "category_coverage": {pack_id: categories_in_pack},
        "vintage_date": pack_data.get("vintage_date", _today_iso()),
        "sample_size": pack_data.get("source_metadata", {}).get("sample_size", 6),
        "revenue_band_min": 0,
        "revenue_band_max": None,
        "geography": "India",
        "specificity_score": 0.85,
        "license_expiry": "2099-12-31",
        "data_file_ref": str(ROOT_DIR / "sector_packs" / pack_id / "benchmarks_percentiles.json"),
        "ingested_at": _now_iso(),
    }


def resolve_benchmark_payload(
    industry: str,
    categories: List[str],
    annual_revenue: float | None = None,
) -> Dict[str, Any]:
    """
    Select the best dataset for a run and resolve the actual benchmark payload.

    Resolution order:
    1. Sector-pack-specific benchmarks_percentiles.json (highest priority — public_disclosure data)
    2. Best uploaded/registered dataset from registry
    3. Global seed (industry_benchmarks.json) — fallback

    Falls back to seed benchmarks if the selected dataset has no readable data file.
    """
    # 1. Sector-pack-specific percentile file (takes priority over registry + seed)
    if industry and industry in SECTOR_PACK_TO_BENCHMARK:
        pack_data = _load_sector_pack_benchmarks(industry)
        if pack_data:
            selected_meta = _sector_pack_dataset_meta(industry, pack_data)
            return {
                "benchmark_data": pack_data,
                "selected_dataset": selected_meta,
                "selection_rationale": {
                    "source": "sector_pack_percentiles",
                    "pack_id": industry,
                    "specificity_score": 0.85,
                    "confidence": pack_data.get("confidence_overall", "public_disclosure"),
                },
                "candidates": [{"dataset_id": selected_meta["dataset_id"], "source": selected_meta["source"], "score": 0.85}],
            }

    bench_key = benchmark_industry_for(industry)
    selection = select_best_dataset(industry=bench_key, categories=categories, annual_revenue=annual_revenue)
    selected = selection.get("selected") or _load_seed_dataset()
    payload = read_json(SEED_PATH, {})
    data_ref = selected.get("data_file_ref")
    if data_ref:
        candidate = Path(str(data_ref))
        if candidate.exists():
            loaded = read_json(candidate, {})
            if loaded.get("benchmarks"):
                payload = loaded
    # Alias the requested sector-pack id onto the resolved benchmark taxonomy so
    # callers that look up benchmarks[industry] (peer_benchmarker) resolve even
    # when the registry is keyed coarser. Copy before mutating to avoid leaking
    # the alias into a shared/cached payload.
    benchmarks = payload.get("benchmarks", {})
    if industry and industry != bench_key and industry not in benchmarks and bench_key in benchmarks:
        benchmarks = dict(benchmarks)
        benchmarks[industry] = benchmarks[bench_key]
        payload = {**payload, "benchmarks": benchmarks}
    return {
        "benchmark_data": payload,
        "selected_dataset": selected,
        "selection_rationale": selection.get("selection_rationale", {}),
        "candidates": selection.get("candidates", []),
    }
