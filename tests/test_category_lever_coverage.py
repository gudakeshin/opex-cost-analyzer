"""Every benchmark category in a sector pack must have at least one linked lever."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import ROOT_DIR
from app.services.benchmarks import _build_category_lever_map, _lever_detail_for_pack, _sector_pack_category_detail
from app.services.benchmarks import _load_sector_pack_benchmarks


def _pack_ids() -> list[str]:
    base = ROOT_DIR / "sector_packs"
    return sorted(
        p.name
        for p in base.iterdir()
        if p.is_dir() and (p / "benchmarks_percentiles.json").exists()
    )


@pytest.mark.parametrize("pack_id", _pack_ids())
def test_every_benchmark_category_has_linked_lever(pack_id: str) -> None:
    pack_data = _load_sector_pack_benchmarks(pack_id)
    assert pack_data, f"no benchmark data for {pack_id}"
    categories = _sector_pack_category_detail(pack_id, pack_data)
    assert categories, f"no categories in benchmarks for {pack_id}"

    lever_detail = _lever_detail_for_pack(pack_id)
    category_lever_map = _build_category_lever_map(lever_detail, list(categories.keys()))

    missing = [cat for cat in categories if not category_lever_map.get(cat)]
    assert not missing, (
        f"{pack_id}: benchmark categories without linked levers: {missing}. "
        f"Add category_ids to sector_packs/{pack_id}/sector_levers.json"
    )


def test_manufacturing_category_ids_match_benchmark_keys() -> None:
    """Regression: manufacturing levers must use benchmark category keys, not legacy aliases."""
    path = ROOT_DIR / "sector_packs" / "manufacturing_diversified" / "sector_levers.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    bench_path = ROOT_DIR / "sector_packs" / "manufacturing_diversified" / "benchmarks_percentiles.json"
    bench = json.loads(bench_path.read_text(encoding="utf-8"))
    bench_cats = set(
        bench["benchmarks"]["manufacturing_diversified"]["categories"].keys()
    )
    linked: set[str] = set()
    for lev in data.get("levers", []):
        linked.update(lev.get("category_ids") or [])
    assert linked.issubset(bench_cats), f"non-benchmark category_ids: {linked - bench_cats}"


def _norm_cat_id(cat: str) -> str:
    return (cat or "").strip().lower().replace(" ", "_")


def _pack_status(pack_id: str) -> str:
    manifest = (ROOT_DIR / "sector_packs" / pack_id / "pack_manifest.yaml").read_text(encoding="utf-8")
    for line in manifest.splitlines():
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip()
    return "scaffold"


def _full_pack_ids() -> list[str]:
    return [p for p in _pack_ids() if _pack_status(p) == "full"]


@pytest.mark.parametrize("pack_id", _full_pack_ids())
def test_full_pack_taxonomy_categories_have_linked_lever(pack_id: str) -> None:
    """Every additional_categories entry in a full pack's taxonomy must have a linked lever."""
    tax_path = ROOT_DIR / "sector_packs" / pack_id / "taxonomy_extension.json"
    tax = json.loads(tax_path.read_text(encoding="utf-8"))
    taxonomy_ids = [c["category_id"] for c in tax.get("additional_categories") or []]

    lever_detail = _lever_detail_for_pack(pack_id)
    linked_norm: set[str] = set()
    for lev in lever_detail:
        for cat in lev.get("category_ids") or []:
            linked_norm.add(_norm_cat_id(str(cat)))

    missing = [tid for tid in taxonomy_ids if _norm_cat_id(tid) not in linked_norm]
    assert not missing, (
        f"{pack_id}: taxonomy categories without linked levers: {missing}. "
        f"Add category_ids to sector_packs/{pack_id}/sector_levers.json"
    )


@pytest.mark.parametrize("pack_id", _pack_ids())
def test_stub_runtime_lever_parity(pack_id: str) -> None:
    """Stub and runtime lever catalogs must carry the same lever_id set (both directions)."""
    stub_path = ROOT_DIR / "sector_packs" / pack_id / "sector_levers.json"
    runtime_path = ROOT_DIR / "skills" / "sector-packs" / pack_id / "sector_levers.json"
    stub = json.loads(stub_path.read_text(encoding="utf-8"))
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))

    stub_ids = {lev["lever_id"] for lev in stub.get("levers") or []}
    runtime_ids = {lev["lever_id"] for lev in runtime.get("sector_specific_levers") or []}

    orphan_stubs = stub_ids - runtime_ids
    missing_stubs = runtime_ids - stub_ids
    assert not orphan_stubs, (
        f"{pack_id}: stub levers missing from runtime: {sorted(orphan_stubs)}. "
        f"Run scripts/sync_category_levers_runtime.py"
    )
    assert not missing_stubs, (
        f"{pack_id}: runtime levers missing stub entries: {sorted(missing_stubs)}. "
        f"Run scripts/backfill_stub_levers.py"
    )


@pytest.mark.parametrize("pack_id", _full_pack_ids())
def test_full_pack_benchmark_category_ids_on_levers(pack_id: str) -> None:
    """Full-pack benchmark categories must each appear on at least one stub lever."""
    stub_path = ROOT_DIR / "sector_packs" / pack_id / "sector_levers.json"
    bench_path = ROOT_DIR / "sector_packs" / pack_id / "benchmarks_percentiles.json"
    stub = json.loads(stub_path.read_text(encoding="utf-8"))
    bench = json.loads(bench_path.read_text(encoding="utf-8"))
    bench_cats = set(bench["benchmarks"][pack_id]["categories"].keys())
    bench_norm = {_norm_cat_id(c): c for c in bench_cats}

    linked: set[str] = set()
    for lev in stub.get("levers") or []:
        for cat in lev.get("category_ids") or []:
            norm = _norm_cat_id(str(cat))
            if norm in bench_norm:
                linked.add(bench_norm[norm])
    assert linked == bench_cats, f"benchmark categories not linked: {bench_cats - linked}"
