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


def list_available_packs() -> List[str]:
    """Return pack IDs for all directories that contain pack_manifest.yaml."""
    if not _SECTOR_PACKS_ROOT.exists():
        return []
    return sorted(
        d.name
        for d in _SECTOR_PACKS_ROOT.iterdir()
        if d.is_dir() and (d / "pack_manifest.yaml").exists()
    )


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
