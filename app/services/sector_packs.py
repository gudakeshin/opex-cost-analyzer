"""
Sector Pack loader — version-locks packs at engagement start; regression-gates releases.

Layout expected at sector_packs/<pack_id>/:
  pack_manifest.yaml         version, applicable peer set, schema_version
  taxonomy_extension.json    sector categories merged into base taxonomy
  benchmark_sources.yaml     CMIE queries, MCA21 selectors, free-source refs
  sector_levers.json         levers + default P10/P50/P90 ranges
  regulatory_layer.md        in-force regulations for this sector
  kpi_pack.json              C-suite KPIs
  peer_set.json              listed peers + ticker
"""
from __future__ import annotations

import json
import logging
import re
import threading as _threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger(__name__)

_SECTOR_PACKS_ROOT = Path(__file__).resolve().parents[2] / "sector_packs"
_REQUIRED_FILES = {"pack_manifest.yaml", "taxonomy_extension.json", "peer_set.json"}
_OPTIONAL_FILES = {
    "benchmark_sources.yaml",
    "sector_levers.json",
    "regulatory_layer.md",
    "kpi_pack.json",
}


class SectorPackError(RuntimeError):
    pass


def _load_yaml(path: Path) -> Dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def pack_dir(pack_id: str) -> Path:
    return _SECTOR_PACKS_ROOT / pack_id


def pack_levers_list(sector_levers: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    """Return lever rows from either ``levers`` or ``sector_specific_levers`` key."""
    if not sector_levers:
        return []
    for key in ("levers", "sector_specific_levers"):
        rows = sector_levers.get(key)
        if isinstance(rows, list) and rows:
            return [r for r in rows if isinstance(r, dict)]
    return []


def pack_file_counts(pack_id: str) -> Dict[str, int]:
    """Lightweight asset counts without requiring a complete pack load."""
    d = pack_dir(pack_id)
    counts = {
        "peer_count": 0,
        "lever_count": 0,
        "kpi_count": 0,
        "category_count": 0,
        "taxonomy_count": 0,
    }
    if not d.is_dir():
        return counts
    peer_path = d / "peer_set.json"
    if peer_path.exists():
        counts["peer_count"] = len(_load_json(peer_path).get("peers", []))
    lev_path = d / "sector_levers.json"
    if lev_path.exists():
        counts["lever_count"] = len(pack_levers_list(_load_json(lev_path)))
    kpi_path = d / "kpi_pack.json"
    if kpi_path.exists():
        kpis = _load_json(kpi_path)
        counts["kpi_count"] = len(kpis) if isinstance(kpis, list) else 0
    bench_path = d / "benchmarks_percentiles.json"
    if bench_path.exists():
        bench = _load_json(bench_path)
        cats = (bench.get("benchmarks", {}).get(pack_id, {}).get("categories") or {})
        counts["category_count"] = len(cats)
    tax_path = d / "taxonomy_extension.json"
    if tax_path.exists():
        tax = _load_json(tax_path)
        counts["taxonomy_count"] = len(tax.get("additional_categories", [])) + len(
            tax.get("overrides", [])
        )
    return counts


def list_available_packs() -> List[str]:
    """Return pack IDs for all directories that contain pack_manifest.yaml."""
    if not _SECTOR_PACKS_ROOT.exists():
        return []
    return sorted(
        d.name
        for d in _SECTOR_PACKS_ROOT.iterdir()
        if d.is_dir() and (d / "pack_manifest.yaml").exists()
    )


def resolve_sector_pack_id(industry: str) -> str:
    """Map a user-selected or detected industry label to a sector pack id."""
    from app.skills.engine._loaders import _resolve_pack_id

    return _resolve_pack_id((industry or "").strip())


def normalize_industry_selection(industry: str | None) -> str | None:
    """Normalize a user industry choice to a sector pack id for storage and analysis."""
    if industry is None:
        return None
    stripped = industry.strip()
    if not stripped:
        return None
    return resolve_sector_pack_id(stripped) or stripped


_TRIGGER_TABLE_ROW = re.compile(
    r"^\|\s*(?P<trigger>[^|]+?)\s*\|\s*(?P<categories>[^|]+?)\s*\|\s*(?P<severity>[^|]+?)\s*\|\s*$"
)


def parse_regulatory_triggers(regulatory_md: str) -> List[Dict[str, Any]]:
    """Parse the Regulatory Event Triggers markdown table from regulatory_layer.md."""
    if not regulatory_md:
        return []
    triggers: List[Dict[str, Any]] = []
    in_table = False
    for line in regulatory_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("| Trigger"):
            in_table = True
            continue
        if not in_table:
            continue
        if stripped.startswith("|---"):
            continue
        if not stripped.startswith("|"):
            break
        match = _TRIGGER_TABLE_ROW.match(stripped)
        if not match:
            continue
        trigger = match.group("trigger").strip()
        categories_raw = match.group("categories").strip()
        severity = match.group("severity").strip().upper()
        if categories_raw.lower() == "all":
            category_ids: List[str] = ["all"]
        else:
            category_ids = [c.strip() for c in categories_raw.split(",") if c.strip()]
        triggers.append({
            "trigger": trigger,
            "category_ids": category_ids,
            "severity": severity,
        })
    return triggers


def get_pack_regulatory_context(pack_id: str) -> Dict[str, Any]:
    """Return regulatory layer text, parsed triggers, and manifest regulatory bodies."""
    resolved = resolve_sector_pack_id(pack_id) or pack_id
    if not resolved or not (pack_dir(resolved) / "pack_manifest.yaml").exists():
        return {"pack_id": pack_id, "regulatory_layer": "", "triggers": [], "regulatory_bodies": []}
    pack = load_pack(resolved)
    regulatory_layer = pack.get("regulatory_layer") or ""
    manifest = pack.get("manifest") or {}
    bodies = manifest.get("regulatory_bodies") or []
    if not isinstance(bodies, list):
        bodies = [bodies]
    return {
        "pack_id": resolved,
        "regulatory_layer": regulatory_layer,
        "triggers": parse_regulatory_triggers(regulatory_layer),
        "regulatory_bodies": bodies,
    }


@lru_cache(maxsize=32)
def _load_pack_cached(pack_id: str) -> Dict[str, Any]:
    pack_dir = _SECTOR_PACKS_ROOT / pack_id
    if not pack_dir.exists():
        raise SectorPackError(f"Sector pack not found: {pack_id}")

    missing = _REQUIRED_FILES - {f.name for f in pack_dir.iterdir() if f.is_file()}
    if missing:
        raise SectorPackError(f"Pack '{pack_id}' missing required files: {missing}")

    manifest = _load_yaml(pack_dir / "pack_manifest.yaml")
    taxonomy = _load_json(pack_dir / "taxonomy_extension.json")
    peer_set = _load_json(pack_dir / "peer_set.json")

    levers = {}
    if (pack_dir / "sector_levers.json").exists():
        levers = _load_json(pack_dir / "sector_levers.json")

    benchmarks: Dict = {}
    if (pack_dir / "benchmark_sources.yaml").exists():
        benchmarks = _load_yaml(pack_dir / "benchmark_sources.yaml") or {}

    kpis: List = []
    if (pack_dir / "kpi_pack.json").exists():
        kpis = _load_json(pack_dir / "kpi_pack.json")

    regulatory = ""
    if (pack_dir / "regulatory_layer.md").exists():
        regulatory = (pack_dir / "regulatory_layer.md").read_text(encoding="utf-8")

    return {
        "pack_id": pack_id,
        "manifest": manifest,
        "taxonomy_extension": taxonomy,
        "peer_set": peer_set,
        "sector_levers": levers,
        "benchmark_sources": benchmarks,
        "kpi_pack": kpis,
        "regulatory_layer": regulatory,
        "version": manifest.get("version", "0.0"),
        "effective_from": manifest.get("effective_from", manifest.get("created_at", "")),
        "status": manifest.get("status", "scaffold"),
    }


def load_pack(pack_id: str) -> Dict[str, Any]:
    """Load and return a sector pack (cached per process)."""
    return _load_pack_cached(pack_id)


def lock_pack_version(pack_id: str, engagement_id: str) -> Dict[str, str]:
    """
    Record the pack version at engagement start so the same pack version
    is used throughout the 12-week engagement even if the pack is updated.
    Returns {pack_id, version, engagement_id, locked_at}.
    """
    from datetime import datetime, timezone

    pack = load_pack(pack_id)
    record = {
        "pack_id": pack_id,
        "version": pack["version"],
        "engagement_id": engagement_id,
        "locked_at": datetime.now(timezone.utc).isoformat(),
    }
    lock_dir = Path("data") / "pack_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / f"{engagement_id}_{pack_id}.json"
    lock_file.write_text(json.dumps(record, indent=2))
    log.info("Locked pack %s@%s for engagement %s", pack_id, pack["version"], engagement_id)
    return record


def get_locked_version(pack_id: str, engagement_id: str) -> Optional[str]:
    lock_file = Path("data") / "pack_locks" / f"{engagement_id}_{pack_id}.json"
    if lock_file.exists():
        return json.loads(lock_file.read_text()).get("version")
    return None


def merge_taxonomy(base_categories: List[Dict], pack_id: str) -> List[Dict]:
    """Merge sector pack taxonomy extensions into the base category list."""
    pack = load_pack(pack_id)
    ext = pack.get("taxonomy_extension", {})
    extra = ext.get("additional_categories", [])
    overrides = {o["category_id"]: o for o in ext.get("overrides", [])}

    merged = []
    for cat in base_categories:
        cid = cat.get("category_id", "")
        merged.append({**cat, **overrides.get(cid, {})})

    existing_ids = {c.get("category_id") for c in merged}
    for cat in extra:
        if cat.get("category_id") not in existing_ids:
            merged.append(cat)

    return merged


# Minimum content depth a pack must carry before it may declare status=full.
# Derived from the bfsi_banks / manufacturing_diversified gold standard.
FULL_PACK_MIN_TAXONOMY = 10
FULL_PACK_MIN_PEERS = 8
FULL_PACK_MIN_BENCHMARK_CATEGORIES = 15
FULL_PACK_MIN_KPIS = 8
FULL_PACK_MIN_TRIGGERS = 5
_BENCHMARK_REQUIRED_FIELDS = ("P25", "P50", "P75", "P90", "unit", "confidence", "source_note")


def _full_pack_depth_checks(
    pack_id: str, pack: Dict[str, Any], runtime_levers: List[Dict[str, Any]]
) -> tuple[Dict[str, bool], List[str]]:
    """Content-depth gate for status=full packs; scaffolds/drafts are exempt."""
    checks: Dict[str, bool] = {}
    errors: List[str] = []

    tax_cats = pack["taxonomy_extension"].get("additional_categories", [])
    checks["full_taxonomy_depth"] = len(tax_cats) >= FULL_PACK_MIN_TAXONOMY
    if not checks["full_taxonomy_depth"]:
        errors.append(
            f"status=full requires >= {FULL_PACK_MIN_TAXONOMY} taxonomy categories, found {len(tax_cats)}"
        )

    peers = pack["peer_set"].get("peers", [])
    checks["full_peer_depth"] = len(peers) >= FULL_PACK_MIN_PEERS
    if not checks["full_peer_depth"]:
        errors.append(f"status=full requires >= {FULL_PACK_MIN_PEERS} peers, found {len(peers)}")

    bench_path = pack_dir(pack_id) / "benchmarks_percentiles.json"
    bench_cats: Dict[str, Any] = {}
    if bench_path.exists():
        bench_cats = (
            _load_json(bench_path).get("benchmarks", {}).get(pack_id, {}).get("categories") or {}
        )
    checks["full_benchmark_depth"] = len(bench_cats) >= FULL_PACK_MIN_BENCHMARK_CATEGORIES
    if not checks["full_benchmark_depth"]:
        errors.append(
            f"status=full requires >= {FULL_PACK_MIN_BENCHMARK_CATEGORIES} benchmark categories, "
            f"found {len(bench_cats)}"
        )
    bad_bench = [
        cat_id
        for cat_id, row in bench_cats.items()
        if not all(field in row for field in _BENCHMARK_REQUIRED_FIELDS)
    ]
    checks["full_benchmark_fields"] = len(bad_bench) == 0
    if bad_bench:
        errors.append(f"Benchmark categories missing P25/P50/P75/P90/unit/confidence/source_note: {bad_bench[:10]}")

    kpis = pack.get("kpi_pack") or []
    n_kpis = len(kpis) if isinstance(kpis, list) else 0
    checks["full_kpi_depth"] = n_kpis >= FULL_PACK_MIN_KPIS
    if not checks["full_kpi_depth"]:
        errors.append(f"status=full requires >= {FULL_PACK_MIN_KPIS} KPIs, found {n_kpis}")

    triggers = parse_regulatory_triggers(pack.get("regulatory_layer") or "")
    checks["full_regulatory_triggers"] = len(triggers) >= FULL_PACK_MIN_TRIGGERS
    if not checks["full_regulatory_triggers"]:
        errors.append(
            f"status=full requires >= {FULL_PACK_MIN_TRIGGERS} parsed regulatory triggers, found {len(triggers)}"
        )

    major = str(pack["version"]).split(".")[0]
    checks["full_version_ge_1"] = major.isdigit() and int(major) >= 1
    if not checks["full_version_ge_1"]:
        errors.append(f"status=full requires version >= 1.0, found {pack['version']}")

    stub_ids = {lv.get("lever_id") for lv in pack_levers_list(pack.get("sector_levers"))}
    runtime_ids = {lv.get("lever_id") for lv in runtime_levers}
    missing_stub = sorted(runtime_ids - stub_ids)
    orphan_stub = sorted(stub_ids - runtime_ids)
    checks["full_lever_parity"] = not missing_stub and not orphan_stub
    if missing_stub:
        errors.append(f"Runtime levers missing stub entries in sector_packs/{pack_id}: {missing_stub[:10]}")
    if orphan_stub:
        errors.append(f"Stub levers absent from runtime skills pack for {pack_id}: {orphan_stub[:10]}")

    return checks, errors


def run_regression_test(pack_id: str) -> Dict[str, Any]:
    """
    Validate pack integrity before a version bump can be released.
    Returns {passed: bool, checks: {name: bool}, errors: [str]}.
    """
    errors: List[str] = []
    checks: Dict[str, bool] = {}

    try:
        _load_pack_cached.cache_clear()
        pack = _load_pack_cached(pack_id)
    except Exception as exc:
        return {"passed": False, "checks": {}, "errors": [str(exc)]}

    # 1. Required manifest keys
    required_manifest = {"pack_id", "version", "sector", "status", "effective_from"}
    missing_keys = required_manifest - set(pack["manifest"].keys())
    checks["manifest_keys"] = len(missing_keys) == 0
    if missing_keys:
        errors.append(f"Manifest missing keys: {missing_keys}")

    # 2. Taxonomy has at least 1 category
    tax_cats = pack["taxonomy_extension"].get("additional_categories", [])
    checks["taxonomy_non_empty"] = len(tax_cats) >= 1
    if not checks["taxonomy_non_empty"]:
        errors.append("taxonomy_extension has no additional_categories")

    # 3. Peer set has at least 1 peer
    peers = pack["peer_set"].get("peers", [])
    checks["peer_set_non_empty"] = len(peers) >= 1
    if not checks["peer_set_non_empty"]:
        errors.append("peer_set has no peers")

    # 4. Version is semver-like
    version = pack["version"]
    parts = str(version).split(".")
    checks["version_semver"] = len(parts) >= 2 and all(p.isdigit() for p in parts)
    if not checks["version_semver"]:
        errors.append(f"Version '{version}' is not semver-like")

    # 5. Skills-pack levers: savings_range_pct.p50 + playbook fields
    skills_levers_path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "sector-packs"
        / pack_id
        / "sector_levers.json"
    )
    sector_levers: List[Dict[str, Any]] = []
    if skills_levers_path.exists():
        sector_levers = _load_json(skills_levers_path).get("sector_specific_levers", [])
    bad_p50: List[str] = []
    bad_playbook: List[str] = []
    bad_effort: List[str] = []
    bad_applicability: List[str] = []
    for lv in sector_levers:
        lid = lv.get("lever_id", "?")
        sr = lv.get("savings_range_pct") or {}
        if sr.get("p50") is None:
            bad_p50.append(lid)
        for field in ("execution_playbook", "diagnostic_signals", "required_data_fields"):
            if not lv.get(field):
                bad_playbook.append(f"{lid}.{field}")
        # effort_weeks is aliased over implementation_weeks in code — accept either.
        ew = lv.get("effort_weeks") or lv.get("implementation_weeks") or {}
        if not ew.get("p50"):
            bad_effort.append(lid)
        if lv.get("applicability_threshold_pct") is None:
            bad_applicability.append(lid)
    checks["lever_p50_present"] = len(bad_p50) == 0
    checks["lever_playbook_fields"] = len(bad_playbook) == 0
    checks["lever_effort_weeks"] = len(bad_effort) == 0
    checks["lever_applicability_threshold"] = len(bad_applicability) == 0
    if bad_p50:
        errors.append(f"Sector levers missing savings_range_pct.p50: {bad_p50}")
    if bad_playbook:
        errors.append(f"Sector levers missing playbook fields: {bad_playbook[:10]}")
    if bad_effort:
        errors.append(f"Sector levers missing effort_weeks/implementation_weeks.p50: {bad_effort}")
    if bad_applicability:
        errors.append(f"Sector levers missing applicability_threshold_pct: {bad_applicability}")

    status = str(pack.get("status") or pack["manifest"].get("status") or "scaffold")
    has_regulatory = bool((pack.get("regulatory_layer") or "").strip())
    checks["regulatory_layer_present"] = has_regulatory
    if status == "full" and not has_regulatory:
        errors.append("regulatory_layer.md is required for status=full packs")

    # 6. Depth checks — only gate packs that claim status=full
    if status == "full":
        depth_checks, depth_errors = _full_pack_depth_checks(pack_id, pack, sector_levers)
        checks.update(depth_checks)
        errors.extend(depth_errors)

    passed = all(checks.values())
    return {"passed": passed, "pack_id": pack_id, "version": pack["version"], "checks": checks, "errors": errors}


# ---------------------------------------------------------------------------
# Sector pack overrides — per-engagement lever suppression / customisation
# ---------------------------------------------------------------------------

_OVERRIDE_LOCK = _threading.Lock()
_OVERRIDES_PATH = Path("data") / "sector_pack_overrides.json"


def _load_overrides() -> Dict[str, Any]:
    if _OVERRIDES_PATH.exists():
        try:
            return json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_overrides(data: Dict[str, Any]) -> None:
    _OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def set_pack_override(
    pack_id: str,
    *,
    disabled_levers: Optional[List[str]] = None,
    lever_overrides: Optional[Dict[str, Any]] = None,
    engagement_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Store per-pack lever suppression / customisation.

    disabled_levers — list of lever_ids to exclude from analysis for this pack.
    lever_overrides — {lever_id: {p50_pct: ..., savings_range_pct: [lo, hi]}} patches
                      applied on top of the pack's sector_levers.json.

    Overrides are keyed by pack_id (and optionally engagement_id for scoping).
    """
    key = f"{pack_id}:{engagement_id}" if engagement_id else pack_id
    record: Dict[str, Any] = {
        "pack_id": pack_id,
        "engagement_id": engagement_id,
        "disabled_levers": disabled_levers or [],
        "lever_overrides": lever_overrides or {},
    }
    with _OVERRIDE_LOCK:
        data = _load_overrides()
        data[key] = record
        _save_overrides(data)
    log.info("Pack override set: pack=%s engagement=%s disabled=%s", pack_id, engagement_id, disabled_levers)
    return record


def get_pack_override(pack_id: str, engagement_id: Optional[str] = None) -> Dict[str, Any]:
    """Return override record for a pack, falling back to pack-level override if engagement-scoped not found."""
    data = _load_overrides()
    if engagement_id:
        record = data.get(f"{pack_id}:{engagement_id}")
        if record:
            return record
    return data.get(pack_id, {})


def list_pack_overrides() -> List[Dict[str, Any]]:
    return list(_load_overrides().values())
