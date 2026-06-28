#!/usr/bin/env python3
"""Sync category-gated levers from sector_packs stubs into skills/sector-packs runtime JSON."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUB_DIR = ROOT / "sector_packs"
RUNTIME_DIR = ROOT / "skills" / "sector-packs"
MODEL_PARAMS = ROOT / "skills" / "savings-modeler" / "references" / "model_parameters.json"

UNIVERSAL_CATEGORY_LEVERS = [
    "travel_policy_optimization",
    "telecom_expense_management",
    "office_supplies_consolidation",
    "brsr_reporting_efficiency",
    "intercompany_charge_benchmarking",
    "energy_procurement_optimization",
    "rnd_portfolio_rationalization",
    "insurance_premium_optimization",
    "consulting_spend_governance",
    "bank_fee_optimization",
]

FAMILY_MAP = {
    "travel_policy_optimization": "demand",
    "telecom_expense_management": "supply",
    "office_supplies_consolidation": "supply",
    "brsr_reporting_efficiency": "process",
    "intercompany_charge_benchmarking": "finance",
    "energy_procurement_optimization": "supply",
    "rnd_portfolio_rationalization": "demand",
    "insurance_premium_optimization": "finance",
    "consulting_spend_governance": "demand",
    "bank_fee_optimization": "finance",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _benchmark_categories(pack_id: str) -> set[str]:
    path = STUB_DIR / pack_id / "benchmarks_percentiles.json"
    if not path.exists():
        return set()
    data = _load_json(path)
    block = (data.get("benchmarks") or {}).get(pack_id) or {}
    return set((block.get("categories") or {}).keys())


def _stub_levers(pack_id: str) -> list[dict]:
    path = STUB_DIR / pack_id / "sector_levers.json"
    if not path.exists():
        return []
    raw = _load_json(path)
    return raw.get("levers") or raw.get("sector_specific_levers") or []


def _runtime_entry_from_stub(stub: dict, model_levers: dict) -> dict:
    lid = stub["lever_id"]
    cats = stub.get("category_ids") or []
    applicable_if = [f"category:{c} present" for c in cats if c.isupper() or "_" in c.upper()]
    if not applicable_if:
        applicable_if = [f"category:{cats[0]} present"] if cats else []

    universal_meta = model_levers.get(lid, {})
    p10 = stub.get("p10_pct")
    p50 = stub.get("p50_pct")
    p90 = stub.get("p90_pct")
    impl = stub.get("implementation_weeks", 12)

    entry = {
        "lever_id": lid,
        "lever_name": stub.get("lever_name") or universal_meta.get("lever_name", lid),
        "lever_family": universal_meta.get("lever_family") or FAMILY_MAP.get(lid, "supply"),
        "savings_range_pct": {"p10": p10, "p50": p50, "p90": p90},
        "cta_rate": universal_meta.get("cta_rate", 0.05),
        "phasing_curve": universal_meta.get("phasing_curve", [0.3, 0.5, 0.2]),
        "savings_type": stub.get("savings_type") or universal_meta.get("savings_type", "run_rate"),
        "sustainability_score": universal_meta.get("sustainability_score", 0.7),
        "bounce_back_risk": universal_meta.get("bounce_back_risk", "medium"),
        "org_change_risk": universal_meta.get("org_change_risk", "low"),
        "condition_precedents": universal_meta.get("condition_precedents")
        or [f"Baseline validated for {stub.get('lever_name', lid)}"],
        "complexity_tier": universal_meta.get("complexity_tier", "medium"),
        "base_execution_probability": universal_meta.get("base_execution_probability", 0.75),
        "implementation_weeks": universal_meta.get("implementation_weeks")
        or {"p10": max(4, impl - 4), "p50": impl, "p90": impl + 8},
        "applicable_if": applicable_if,
        "industry_sources": stub.get("industry_sources") or [],
        "execution_playbook": universal_meta.get("execution_playbook")
        or [
            {
                "step": f"Confirm scope for {stub.get('lever_name', lid)}: validate baseline",
                "owner_role": "Category Manager",
                "duration_weeks": 2,
            },
            {
                "step": "Execute initiative and capture signed savings",
                "owner_role": "Procurement Lead",
                "duration_weeks": max(4, impl // 2),
            },
            {
                "step": "Embed controls and track run-rate vs plan",
                "owner_role": "FP&A",
                "duration_weeks": 4,
            },
        ],
        "diagnostic_signals": universal_meta.get("diagnostic_signals")
        or [
            {
                "signal": f"Category spend elevated vs peer benchmark for {cats[0] if cats else 'target'}",
                "evidence_source": "spend_profile",
                "confirms": "Category-specific lever is applicable",
            }
        ],
        "required_data_fields": universal_meta.get("required_data_fields")
        or ["Category spend baseline", "Supplier and contract inventory"],
        "applicability_threshold_pct": universal_meta.get("applicability_threshold_pct", 0.03),
    }
    return entry


def sync_pack(pack_id: str, model_levers: dict) -> None:
    runtime_path = RUNTIME_DIR / pack_id / "sector_levers.json"
    if not runtime_path.exists():
        return
    runtime = _load_json(runtime_path)
    bench_cats = _benchmark_categories(pack_id)
    stubs = _stub_levers(pack_id)

    # Map stub category -> lever_ids
    cat_to_levers: dict[str, list[str]] = {}
    stub_by_id = {s["lever_id"]: s for s in stubs}
    for stub in stubs:
        for cat in stub.get("category_ids") or []:
            norm = cat.upper()
            if norm in bench_cats or cat in bench_cats:
                key = cat if cat in bench_cats else norm
                cat_to_levers.setdefault(key, []).append(stub["lever_id"])

    # Universal levers: add category universal levers if pack benchmark has matching categories
    universal = list(runtime.get("universal_levers") or [])
    cat_universal_map = {
        "TRAVEL": "travel_policy_optimization",
        "TELECOM": "telecom_expense_management",
        "OFFICE": "office_supplies_consolidation",
        "BRSR_ESG": "brsr_reporting_efficiency",
        "RELATED_PARTY": "intercompany_charge_benchmarking",
        "POWER_ENERGY": "energy_procurement_optimization",
        "RND": "rnd_portfolio_rationalization",
        "INSURANCE": "insurance_premium_optimization",
        "PROF_SVCS": "consulting_spend_governance",
        "PROF_SERVICES": "consulting_spend_governance",
        "FIN_SVCS": "bank_fee_optimization",
    }
    for cat, ulid in cat_universal_map.items():
        if cat in bench_cats and ulid not in universal:
            universal.append(ulid)
    runtime["universal_levers"] = universal

    # Sector-specific: ensure each stub lever with benchmark category mapping exists
    existing = {lv["lever_id"]: lv for lv in runtime.get("sector_specific_levers") or []}
    for stub in stubs:
        lid = stub["lever_id"]
        cats = set(stub.get("category_ids") or [])
        if not cats.intersection(bench_cats) and not any(
            c.upper() in bench_cats for c in cats
        ):
            continue
        if lid in model_levers and lid in UNIVERSAL_CATEGORY_LEVERS:
            # Add category-gated wrapper using universal metadata
            entry = _runtime_entry_from_stub(stub, model_levers)
            existing[lid] = entry
        elif lid not in existing:
            existing[lid] = _runtime_entry_from_stub(stub, model_levers)
        else:
            # Merge category_ids into applicable_if
            cur = existing[lid]
            cur_if = set(cur.get("applicable_if") or [])
            for cat in stub.get("category_ids") or []:
                if cat in bench_cats:
                    cur_if.add(f"category:{cat} present")
            cur["applicable_if"] = list(cur_if) or cur.get("applicable_if")

    runtime["sector_specific_levers"] = list(existing.values())
    runtime_path.write_text(json.dumps(runtime, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Synced {pack_id}: {len(runtime['sector_specific_levers'])} sector levers, {len(universal)} universal")


def main() -> None:
    model = _load_json(MODEL_PARAMS)
    model_levers = model.get("levers") or {}
    for pack_dir in sorted(STUB_DIR.iterdir()):
        if pack_dir.is_dir() and (RUNTIME_DIR / pack_dir.name / "sector_levers.json").exists():
            sync_pack(pack_dir.name, model_levers)


if __name__ == "__main__":
    main()
