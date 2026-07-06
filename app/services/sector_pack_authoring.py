"""Sector pack authoring — create, update components, publish, and Excel import."""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.config import ROOT_DIR
from app.services.compliance import append_audit_event
from app.services.lever_runtime_sync import RUNTIME_DIR, sync_pack
from app.services.sector_packs import (
    SectorPackError,
    _BENCHMARK_REQUIRED_FIELDS,
    _load_pack_cached,
    pack_dir,
    pack_levers_list,
    parse_regulatory_triggers,
    run_regression_test,
)

PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")

_SECTOR_PACKS_ROOT = ROOT_DIR / "sector_packs"
_PACK_LOCKS: Dict[str, threading.Lock] = {}
_LOCK_GUARD = threading.Lock()

COMPONENT_FILES: Dict[str, str] = {
    "manifest": "pack_manifest.yaml",
    "taxonomy": "taxonomy_extension.json",
    "peers": "peer_set.json",
    "levers": "sector_levers.json",
    "kpis": "kpi_pack.json",
    "benchmarks": "benchmarks_percentiles.json",
    "sources": "benchmark_sources.yaml",
    "regulatory": "regulatory_layer.md",
}

VALID_COMPONENTS = frozenset(COMPONENT_FILES.keys())
VALID_STATUSES = frozenset({"scaffold", "draft", "full"})


class SectorPackAuthoringError(ValueError):
    pass


def validate_pack_id(pack_id: str) -> str:
    slug = (pack_id or "").strip()
    if not slug or not PACK_ID_RE.match(slug):
        raise SectorPackAuthoringError("Pack id must match ^[a-z0-9][a-z0-9_-]{1,63}$")
    resolved = ( _SECTOR_PACKS_ROOT / slug).resolve()
    if not str(resolved).startswith(str(_SECTOR_PACKS_ROOT.resolve())):
        raise SectorPackAuthoringError("Invalid pack id")
    return slug


def _pack_lock(pack_id: str) -> threading.Lock:
    with _LOCK_GUARD:
        if pack_id not in _PACK_LOCKS:
            _PACK_LOCKS[pack_id] = threading.Lock()
        return _PACK_LOCKS[pack_id]


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    _atomic_write_text(path, text)


def _atomic_write_yaml(path: Path, payload: Dict[str, Any]) -> None:
    text = yaml.dump(payload, default_flow_style=False, sort_keys=False)
    _atomic_write_text(path, text)


def _invalidate_caches(pack_id: str, *, sync_runtime: bool = False) -> None:
    _load_pack_cached.cache_clear()
    from app.skills.engine._loaders import _SECTOR_LEVERS_CACHE

    _SECTOR_LEVERS_CACHE.pop(pack_id, None)
    if sync_runtime:
        sync_pack(pack_id)


def validate_component(pack_id: str, component: str, payload: Any) -> None:
    validate_pack_id(pack_id)
    if component not in VALID_COMPONENTS:
        raise SectorPackAuthoringError(f"Unknown component: {component}")

    if component == "manifest":
        if not isinstance(payload, dict):
            raise SectorPackAuthoringError("manifest must be a YAML object")
        for key in ("pack_id", "version", "sector", "status", "effective_from"):
            if key not in payload:
                raise SectorPackAuthoringError(f"manifest missing required key: {key}")
        if str(payload.get("pack_id")) != pack_id:
            raise SectorPackAuthoringError("manifest pack_id cannot be changed")
        status = str(payload.get("status") or "scaffold")
        if status not in VALID_STATUSES:
            raise SectorPackAuthoringError(f"manifest status must be one of {sorted(VALID_STATUSES)}")
        parts = str(payload.get("version", "")).split(".")
        if len(parts) < 2 or not all(p.isdigit() for p in parts):
            raise SectorPackAuthoringError("manifest version must be 2-part semver (e.g. 1.0)")

    elif component == "taxonomy":
        if not isinstance(payload, dict):
            raise SectorPackAuthoringError("taxonomy must be a JSON object")
        cats = payload.get("additional_categories") or []
        if not isinstance(cats, list) or len(cats) < 1:
            raise SectorPackAuthoringError("taxonomy requires at least one additional_categories entry")
        seen: set[str] = set()
        for cat in cats:
            if not isinstance(cat, dict):
                raise SectorPackAuthoringError("taxonomy category must be an object")
            cid = cat.get("category_id")
            if not cid:
                raise SectorPackAuthoringError("taxonomy category missing category_id")
            if cid in seen:
                raise SectorPackAuthoringError(f"duplicate taxonomy category_id: {cid}")
            seen.add(str(cid))

    elif component == "peers":
        if not isinstance(payload, dict):
            raise SectorPackAuthoringError("peers must be a JSON object")
        peers = payload.get("peers") or []
        if not isinstance(peers, list) or len(peers) < 1:
            raise SectorPackAuthoringError("peer_set requires at least one peer")

    elif component == "levers":
        if not isinstance(payload, dict):
            raise SectorPackAuthoringError("levers must be a JSON object")
        levers = pack_levers_list(payload)
        if not levers:
            raise SectorPackAuthoringError("sector_levers requires at least one lever in levers array")
        for lv in levers:
            if not lv.get("lever_id"):
                raise SectorPackAuthoringError("each lever requires lever_id")
            if not lv.get("category_ids"):
                raise SectorPackAuthoringError(f"lever {lv.get('lever_id')} requires category_ids")
            for pct in ("p10_pct", "p50_pct", "p90_pct"):
                if lv.get(pct) is None:
                    raise SectorPackAuthoringError(f"lever {lv.get('lever_id')} missing {pct}")

    elif component == "kpis":
        if not isinstance(payload, list):
            raise SectorPackAuthoringError("kpi_pack must be a JSON array")
        for kpi in payload:
            if not isinstance(kpi, dict) or not kpi.get("kpi_id"):
                raise SectorPackAuthoringError("each KPI requires kpi_id")

    elif component == "benchmarks":
        if not isinstance(payload, dict):
            raise SectorPackAuthoringError("benchmarks must be a JSON object")
        block = (payload.get("benchmarks") or {}).get(pack_id) or {}
        cats = block.get("categories") or {}
        if not isinstance(cats, dict):
            raise SectorPackAuthoringError("benchmarks.categories must be an object")
        for cat_id, row in cats.items():
            if not isinstance(row, dict):
                raise SectorPackAuthoringError(f"benchmark category {cat_id} must be an object")
            missing = [f for f in _BENCHMARK_REQUIRED_FIELDS if f not in row]
            if missing:
                raise SectorPackAuthoringError(
                    f"benchmark category {cat_id} missing fields: {missing}"
                )

    elif component == "sources":
        if payload is not None and not isinstance(payload, dict):
            raise SectorPackAuthoringError("sources must be a YAML object")

    elif component == "regulatory":
        if not isinstance(payload, str):
            raise SectorPackAuthoringError("regulatory must be markdown text")


def write_component(pack_id: str, component: str, payload: Any) -> Dict[str, str]:
    pack_id = validate_pack_id(pack_id)
    if component not in VALID_COMPONENTS:
        raise SectorPackAuthoringError(f"Unknown component: {component}")
    if not pack_dir(pack_id).is_dir():
        raise SectorPackAuthoringError(f"Pack not found: {pack_id}")

    if component == "manifest":
        existing = yaml.safe_load((pack_dir(pack_id) / "pack_manifest.yaml").read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise SectorPackAuthoringError("manifest must be a YAML object")
        merged = {**existing, **payload}
        merged["pack_id"] = pack_id
        merged["version"] = existing.get("version")
        if str(payload.get("pack_id", pack_id)) != pack_id:
            raise SectorPackAuthoringError("manifest pack_id cannot be changed")
        if str(payload.get("version", existing.get("version"))) != str(existing.get("version")):
            raise SectorPackAuthoringError("manifest version can only change via publish")
        payload = merged

    validate_component(pack_id, component, payload)

    filename = COMPONENT_FILES[component]
    target = pack_dir(pack_id) / filename

    with _pack_lock(pack_id):
        if component == "manifest":
            _atomic_write_yaml(target, payload)
        elif component == "regulatory":
            _atomic_write_text(target, payload)
        elif component == "sources":
            _atomic_write_yaml(target, payload or {})
        elif component in ("taxonomy", "peers", "levers", "kpis", "benchmarks"):
            _atomic_write_json(target, payload)
        else:
            raise SectorPackAuthoringError(f"Unhandled component: {component}")

    sync_runtime = component in ("levers", "benchmarks")
    _invalidate_caches(pack_id, sync_runtime=sync_runtime)

    append_audit_event(
        "sector_pack_component_updated",
        data={"pack_id": pack_id, "component": component},
    )
    return {"pack_id": pack_id, "component": component, "status": "saved"}


def create_pack(
    pack_id: str,
    *,
    sector: str,
    description: str = "",
) -> Dict[str, Any]:
    pack_id = validate_pack_id(pack_id)
    target = pack_dir(pack_id)
    if target.exists():
        raise SectorPackAuthoringError(f"Pack already exists: {pack_id}")

    today = date.today().isoformat()
    manifest = {
        "pack_id": pack_id,
        "sector": sector,
        "version": "0.1",
        "schema_version": "1",
        "status": "scaffold",
        "description": description or f"Scaffold sector pack for {sector}.",
        "applicable_entity_types": [],
        "regulatory_bodies": [],
        "fiscal_year_end": "March 31",
        "reporting_currency": "INR",
        "created_at": today,
        "effective_from": today,
        "maintained_by": "sector_pack_studio",
    }
    taxonomy = {
        "base_taxonomy_version": "1.0",
        "additional_categories": [
            {
                "category_id": f"{pack_id}_core",
                "category_name": f"{sector} Core Spend",
                "gl_prefix": "SEC",
                "cost_nature": "operating",
            }
        ],
        "overrides": [],
    }
    peers = {
        "sector": pack_id,
        "currency": "INR",
        "peers": [
            {
                "name": f"{sector} — placeholder peer",
                "ticker": "PLACE.NS",
                "exchange": "NSE",
                "entity_type": "listed_company",
                "revenue_cr": 1000,
            }
        ],
        "benchmark_metrics": {},
        "data_source": "scaffold",
        "refresh_date": today,
    }
    runtime_levers = {
        "pack_id": pack_id,
        "sector": sector,
        "version": "0.1",
        "universal_levers": [],
        "sector_specific_levers": [],
    }

    with _pack_lock(pack_id):
        target.mkdir(parents=True)
        _atomic_write_yaml(target / "pack_manifest.yaml", manifest)
        _atomic_write_json(target / "taxonomy_extension.json", taxonomy)
        _atomic_write_json(target / "peer_set.json", peers)
        _atomic_write_text(
            target / "regulatory_layer.md",
            "# Regulatory layer\n\n| Trigger | Categories | Severity |\n|---|---|---|\n| Scaffold placeholder | all | LOW |\n",
        )
        runtime_path = RUNTIME_DIR / pack_id / "sector_levers.json"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(runtime_path, runtime_levers)

    _invalidate_caches(pack_id)
    append_audit_event("sector_pack_created", data={"pack_id": pack_id, "sector": sector})
    return {"pack_id": pack_id, "status": "scaffold", "version": "0.1"}


def _bump_version(version: str, bump: str) -> str:
    parts = str(version).split(".")
    if len(parts) < 2:
        parts = [parts[0] if parts else "0", "0"]
    major, minor = int(parts[0]), int(parts[1])
    if bump == "major":
        return f"{major + 1}.0"
    return f"{major}.{minor + 1}"


def _engagements_on_version(pack_id: str, version: str) -> List[Dict[str, Any]]:
    lock_dir = Path("data") / "pack_locks"
    if not lock_dir.is_dir():
        return []
    results: List[Dict[str, Any]] = []
    for lock_file in lock_dir.glob(f"*_{pack_id}.json"):
        try:
            rec = json.loads(lock_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(rec.get("version")) == version:
            results.append(rec)
    return results


def publish_pack(
    pack_id: str,
    *,
    bump: str = "minor",
    target_status: Optional[str] = None,
) -> Dict[str, Any]:
    pack_id = validate_pack_id(pack_id)
    if not pack_dir(pack_id).is_dir():
        raise SectorPackAuthoringError(f"Pack not found: {pack_id}")
    if bump not in ("minor", "major"):
        raise SectorPackAuthoringError("bump must be 'minor' or 'major'")
    if target_status is not None and target_status not in VALID_STATUSES:
        raise SectorPackAuthoringError(f"target_status must be one of {sorted(VALID_STATUSES)}")

    regression = run_regression_test(pack_id)
    if not regression.get("passed"):
        raise SectorPackAuthoringError(
            f"Regression test failed: {'; '.join(regression.get('errors') or [])}"
        )

    manifest_path = pack_dir(pack_id) / "pack_manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    prior_version = str(manifest.get("version") or "0.1")
    new_version = _bump_version(prior_version, bump)
    today = date.today().isoformat()

    manifest["version"] = new_version
    manifest["effective_from"] = today
    if target_status:
        manifest["status"] = target_status

    locked_engagements = _engagements_on_version(pack_id, prior_version)

    with _pack_lock(pack_id):
        _atomic_write_yaml(manifest_path, manifest)
        runtime_path = RUNTIME_DIR / pack_id / "sector_levers.json"
        if runtime_path.exists():
            runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
            runtime["version"] = new_version
            _atomic_write_json(runtime_path, runtime)

    _invalidate_caches(pack_id)
    append_audit_event(
        "sector_pack_published",
        data={
            "pack_id": pack_id,
            "prior_version": prior_version,
            "version": new_version,
            "target_status": target_status or manifest.get("status"),
        },
    )
    return {
        "pack_id": pack_id,
        "prior_version": prior_version,
        "version": new_version,
        "status": manifest.get("status"),
        "regression": regression,
        "locked_engagements": locked_engagements,
    }


# ---------------------------------------------------------------------------
# Excel import (Sector_Packs_Documentation workbook layout)
# ---------------------------------------------------------------------------

_SHEET_LEVERS = re.compile(r"sector\s*levers?", re.I)
_SHEET_KPIS = re.compile(r"kpi", re.I)
_SHEET_PEERS = re.compile(r"peer", re.I)
_SHEET_SOURCES = re.compile(r"benchmark\s*sources?", re.I)
_SHEET_TAXONOMY = re.compile(r"taxonomy", re.I)
_SHEET_BENCHMARKS = re.compile(r"benchmarks?\s*by\s*sector", re.I)
_SHEET_OVERVIEW = re.compile(r"overview", re.I)


def _sheet_kind(name: str) -> Optional[str]:
    n = name.strip()
    if _SHEET_OVERVIEW.search(n):
        return "overview"
    if _SHEET_LEVERS.search(n):
        return "levers"
    if _SHEET_KPIS.search(n):
        return "kpis"
    if _SHEET_PEERS.search(n):
        return "peers"
    if _SHEET_SOURCES.search(n):
        return "sources"
    if _SHEET_TAXONOMY.search(n):
        return "taxonomy"
    if _SHEET_BENCHMARKS.search(n):
        return "benchmarks"
    return None


def _parse_workbook_sheets(wb: Any) -> Dict[str, Any]:
    """Parse workbook rows into per-pack component payloads."""
    import openpyxl

    packs: Dict[str, Dict[str, Any]] = {}

    def ensure(pid: str) -> Dict[str, Any]:
        return packs.setdefault(
            pid,
            {
                "manifest": None,
                "levers": {"sector": pid, "source_type": "import", "levers": []},
                "kpis": [],
                "peers": {"sector": pid, "currency": "INR", "peers": []},
                "sources": {"free_sources": [], "licensed_sources_stubs": []},
                "taxonomy": {"base_taxonomy_version": "1.0", "additional_categories": [], "overrides": []},
                "benchmarks": None,
            },
        )

    for ws in wb.worksheets:
        kind = _sheet_kind(ws.title)
        if not kind:
            continue
        rows = list(ws.iter_rows(min_row=4, values_only=True))
        for row in rows:
            if not row or not row[0]:
                continue
            pid = str(row[0]).strip()
            if not pid:
                continue
            bucket = ensure(pid)

            if kind == "overview":
                bucket["manifest"] = {
                    "pack_id": pid,
                    "sector": str(row[1] or pid),
                    "version": str(row[2] or "0.1").strip('"'),
                    "status": str(row[3] or "draft").lower(),
                    "effective_from": str(row[10] or date.today().isoformat()),
                    "schema_version": "1",
                    "description": f"Imported pack for {row[1] or pid}",
                    "applicable_entity_types": [
                        x.strip() for x in str(row[4] or "").split(",") if x.strip()
                    ],
                    "regulatory_bodies": [
                        x.strip() for x in str(row[5] or "").split(",") if x.strip()
                    ],
                    "default_wacc_pct": row[6],
                    "default_tax_rate_pct": row[7],
                    "fiscal_year_end": row[8],
                    "reporting_currency": row[9] or "INR",
                    "created_at": str(row[10] or date.today().isoformat()),
                    "maintained_by": "import",
                }

            elif kind == "levers" and row[1]:
                bucket["levers"]["levers"].append({
                    "lever_id": str(row[1]),
                    "lever_name": str(row[2] or row[1]),
                    "category_ids": [c.strip() for c in str(row[3] or "").split(",") if c.strip()],
                    "p10_pct": _num(row[4]),
                    "p50_pct": _num(row[5]),
                    "p90_pct": _num(row[6]),
                    "savings_type": str(row[7] or "run_rate"),
                    "implementation_weeks": _num(row[8]) or 12,
                    "description": str(row[12] or ""),
                    "industry_sources": [s.strip() for s in str(row[11] or "").split(";") if s.strip()],
                })

            elif kind == "kpis" and row[1]:
                bucket["kpis"].append({
                    "kpi_id": str(row[1]),
                    "kpi_name": str(row[2] or row[1]),
                    "unit": str(row[3] or "%"),
                    "formula": str(row[4] or ""),
                    "target_direction": str(row[5] or "lower").lower(),
                    "p50_benchmark_pct": _num(row[6]),
                    "source": str(row[8] or ""),
                })

            elif kind == "peers" and row[1]:
                bucket["peers"]["peers"].append({
                    "name": str(row[1]),
                    "ticker": str(row[2] or ""),
                    "exchange": str(row[3] or "NSE"),
                    "entity_type": str(row[4] or "listed_company"),
                    "revenue_cr": _num(row[5]),
                })

            elif kind == "sources" and row[1]:
                entry = {
                    "source_name": str(row[2] or row[1]),
                    "url": str(row[3] or ""),
                    "data_available": str(row[4] or ""),
                    "refresh_frequency": str(row[5] or ""),
                }
                tier = str(row[1] or "").lower()
                if "licensed" in tier:
                    bucket["sources"]["licensed_sources_stubs"].append(entry)
                else:
                    bucket["sources"]["free_sources"].append(entry)

            elif kind == "taxonomy" and row[2]:
                cat = {
                    "category_id": str(row[2]),
                    "category_name": str(row[3] or row[2]),
                    "gl_prefix": str(row[4] or ""),
                    "cost_nature": str(row[5] or "operating"),
                }
                if str(row[1] or "").lower().startswith("override"):
                    bucket["taxonomy"]["overrides"].append(cat)
                else:
                    bucket["taxonomy"]["additional_categories"].append(cat)

            elif kind == "benchmarks" and row[2]:
                bench = bucket["benchmarks"] or {
                    "sector": pid,
                    "version": "0.1",
                    "vintage_date": date.today().isoformat(),
                    "confidence_overall": "medium",
                    "source_metadata": {},
                    "benchmarks": {pid: {"categories": {}}},
                }
                bucket["benchmarks"] = bench
                bench["benchmarks"][pid]["categories"][str(row[2])] = {
                    "P25": _num(row[4]),
                    "P50": _num(row[5]),
                    "P75": _num(row[6]),
                    "P90": _num(row[7]),
                    "unit": "% of revenue",
                    "confidence": "medium",
                    "source_note": "imported",
                }

    return packs


def _num(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def import_pack_from_workbook(
    data: bytes,
    *,
    dry_run: bool = True,
    pack_id: Optional[str] = None,
) -> Dict[str, Any]:
    import openpyxl

    wb = openpyxl.load_workbook(BytesIO(data), read_only=True, data_only=True)
    parsed = _parse_workbook_sheets(wb)
    if pack_id:
        pack_id = validate_pack_id(pack_id)
        if pack_id not in parsed:
            raise SectorPackAuthoringError(f"No rows found for pack_id {pack_id} in workbook")
        parsed = {pack_id: parsed[pack_id]}

    results: Dict[str, Any] = {"dry_run": dry_run, "packs": {}}
    all_errors: List[str] = []

    for pid, components in parsed.items():
        pack_errors: List[str] = []
        payloads: Dict[str, Any] = {}

        manifest = components.get("manifest")
        if manifest:
            try:
                validate_component(pid, "manifest", manifest)
                payloads["manifest"] = manifest
            except SectorPackAuthoringError as exc:
                pack_errors.append(f"manifest: {exc}")

        for comp in ("taxonomy", "peers", "levers", "kpis", "benchmarks", "sources"):
            payload = components.get(comp)
            if payload is None:
                continue
            if comp == "levers" and not payload.get("levers"):
                continue
            if comp == "kpis" and not payload:
                continue
            if comp == "peers" and not payload.get("peers"):
                continue
            if comp == "benchmarks" and not payload:
                continue
            try:
                validate_component(pid, comp, payload)
                payloads[comp] = payload
            except SectorPackAuthoringError as exc:
                pack_errors.append(f"{comp}: {exc}")

        if not dry_run and not pack_errors:
            if not pack_dir(pid).is_dir():
                sector = (manifest or {}).get("sector") or pid
                create_pack(pid, sector=str(sector))
            for comp, payload in payloads.items():
                write_component(pid, comp, payload)

        results["packs"][pid] = {
            "components": list(payloads.keys()),
            "payloads": payloads if dry_run else None,
            "errors": pack_errors,
        }
        all_errors.extend(pack_errors)

    results["errors"] = all_errors
    results["valid"] = len(all_errors) == 0
    return results
