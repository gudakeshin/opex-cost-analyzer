from __future__ import annotations

import asyncio
import uuid

from app.memory import MemoryStore
from app.models import NormalizedSpendLine
from app.services import workbench as wb


def _lines() -> list[NormalizedSpendLine]:
    rows = [
        ("CloudCo", "Cloud platform (actual)", 4_000_000.0, "IT_SOFTWARE", "IT Software & Licenses", "actual"),
        ("CloudCo", "Cloud platform (budget)", 3_000_000.0, "IT_SOFTWARE", "IT Software & Licenses", "budget"),
        ("Advisory LLP", "Consulting", 2_500_000.0, "PROF_SERVICES", "Professional Services", "actual"),
        ("Realty Co", "Office lease", 1_800_000.0, "FACILITIES", "Facilities & Real Estate", "actual"),
        ("TravelDesk", "Corporate travel", 900_000.0, "TRAVEL", "Travel & Entertainment", "actual"),
    ]
    return [
        NormalizedSpendLine(
            row_id=i, supplier=s, description=d, amount=amt,
            category_id=cid, category_name=cn, amount_type=at,
            business_unit="Corporate", spend_date="2025-06-15", payment_terms_days=30,
        )
        for i, (s, d, amt, cid, cn, at) in enumerate(rows, start=1)
    ]


def _seed_session(engagement_id: str | None = None) -> str:
    """Seed a session with spend + manifest so load_authoritative_spend_lines works."""
    from app.routers._shared import session_dir, write_manifest

    session_id = str(uuid.uuid4())
    session_dir(session_id).mkdir(parents=True, exist_ok=True)
    eid = engagement_id or str(uuid.uuid4())
    write_manifest(session_id, {
        "files": [],
        "industry": "technology",
        "annual_revenue": 500_000_000.0,
        "company_name": "Workbench Test Co",
        "engagement_id": eid,
        "currency": "INR",
        "headcount": 500,
    })
    MemoryStore().put("session", session_id, {
        "session_id": session_id,
        "engagement_id": eid,
        "company_name": "Workbench Test Co",
        "industry": "technology",
        "annual_revenue": 500_000_000.0,
        "reporting_currency": "INR",
        "normalized_spend": [ln.model_dump(mode="json") for ln in _lines()],
    })
    return session_id


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

def test_catalog_excludes_group0_and_has_tiers() -> None:
    cat = wb.workbench_catalog()
    names = {s["name"] for s in cat["skills"]}
    # Group-0 security skills are auto-injected, not user-selectable.
    assert {"pii-stripper", "data-classifier", "llm-context-builder"}.isdisjoint(names)
    assert "spend-profiler" in names and "value-bridge-calculator" in names
    assert cat["tiers"][0] == "Diagnostics"
    assert any(a["key"] == "wacc" for a in cat["assumptions"])
    # every skill carries tier + deps + param metadata
    s = next(x for x in cat["skills"] if x["name"] == "savings-modeler")
    assert s["tier"] == "Savings & Value"
    assert "wacc" in s["params"]


# ---------------------------------------------------------------------------
# Validator — "no hard boundaries unless logically inconsistent"
# ---------------------------------------------------------------------------

def test_validate_autoresolves_dependencies() -> None:
    r = wb.validate_workbench_run(["value-bridge-calculator"], _seed_session(), {})
    assert not r["blocked"]
    assert "savings-modeler" in r["added_deps"]
    assert "spend-profiler" in r["resolved_skills"]


def test_validate_blocks_hard_requirement_when_selected() -> None:
    r = wb.validate_workbench_run(["gstr-reconciler"], _seed_session(), {})
    assert r["blocked"]
    assert any(e["code"] == "missing_gstr_2a_data" for e in r["blocking_errors"])


def test_validate_soft_requirement_drops_autodep_keeps_selected() -> None:
    sid = _seed_session()
    # No revenue: value-bridge pulls heuristic as a dep → dropped (not blocked).
    no_rev_manifest = sid  # session manifest has revenue; override it to 0 via overrides
    r = wb.validate_workbench_run(["value-bridge-calculator"], no_rev_manifest, {"annual_revenue": 0})
    assert not r["blocked"]
    assert "heuristic-analyzer" not in r["resolved_skills"]
    assert any(w["code"] == "skipped_annual_revenue" for w in r["warnings"])
    # Explicitly selecting heuristic with no revenue keeps it but warns degraded.
    r2 = wb.validate_workbench_run(["heuristic-analyzer"], sid, {"annual_revenue": 0})
    assert not r2["blocked"]
    assert "heuristic-analyzer" in r2["resolved_skills"]
    assert any(w["code"] == "degraded_annual_revenue" for w in r2["warnings"])


# ---------------------------------------------------------------------------
# Executor — overrides flow end-to-end (savings-modeler echoes its inputs)
# ---------------------------------------------------------------------------

def test_run_applies_overrides_end_to_end() -> None:
    sid = _seed_session()
    draft = wb.create_draft(
        session_id=sid, name="Base case",
        selected_skills=["savings-modeler"],
        overrides={"wacc": 0.20, "effective_tax_rate": 0.30},
    )
    run = asyncio.run(wb.run_workbench_run(draft))
    assert run["status"] == "complete", run.get("errors")
    outputs = run["skill_outputs"]
    assert "spend-profiler" in outputs  # auto-resolved dependency executed
    sm = outputs["savings-modeler"]
    # The override reached the engine: savings-modeler echoes its discount/tax inputs.
    assert sm["discount_rate"] == 0.20
    assert sm["effective_tax_rate"] == 0.30
    assert "total_spend" in run["headline"]


# ---------------------------------------------------------------------------
# Branch + board persistence
# ---------------------------------------------------------------------------

def test_branch_produces_independent_run_on_same_board() -> None:
    eid = str(uuid.uuid4())
    sid = _seed_session(engagement_id=eid)
    base = asyncio.run(wb.run_workbench_run(wb.create_draft(
        session_id=sid, name="Base", selected_skills=["savings-modeler"],
        overrides={"wacc": 0.10},
    )))
    branch = wb.branch_run(base["run_id"], name="High WACC")
    assert branch is not None
    assert branch["parent_run_id"] == base["run_id"]
    branch["overrides"]["wacc"] = 0.25
    branched = asyncio.run(wb.run_workbench_run(branch))

    assert branched["skill_outputs"]["savings-modeler"]["discount_rate"] == 0.25
    assert base["skill_outputs"]["savings-modeler"]["discount_rate"] == 0.10

    runs = wb.list_runs(engagement_id=eid)
    ids = {r["run_id"] for r in runs}
    assert {base["run_id"], branch["run_id"]}.issubset(ids)


def test_chain_seeds_prior_outputs() -> None:
    sid = _seed_session()
    base = asyncio.run(wb.run_workbench_run(wb.create_draft(
        session_id=sid, name="Seed run", selected_skills=["spend-profiler"],
    )))
    assert base["status"] == "complete"
    chained = asyncio.run(wb.run_workbench_run(wb.create_draft(
        session_id=sid,
        name="Chained",
        selected_skills=["savings-modeler"],
        seed_from_run_id=base["run_id"],
    )))
    assert chained["status"] == "complete"
    assert "spend-profiler" in chained["skill_outputs"]


def test_quality_gates_option_attaches_sme() -> None:
    sid = _seed_session()
    draft = wb.create_draft(
        session_id=sid,
        name="With gates",
        selected_skills=["value-bridge-calculator"],
    )
    run = asyncio.run(wb.run_workbench_run(draft, include_quality_gates=True))
    assert run["status"] == "complete"
    assert "sme-critique" in run["resolved_skills"] or "data-quality-gate" in run["resolved_skills"]


def test_workbench_merges_outputs_into_session_analysis() -> None:
    sid = _seed_session()
    draft = wb.create_draft(
        session_id=sid,
        name="merge-test",
        selected_skills=["spend-profiler"],
        engagement_id="eng-merge",
    )
    draft["skill_outputs"] = {
        "value-bridge-calculator": {"confidence_bands": {"low": 1, "mid": 2, "high": 3}},
        "savings-modeler": {"initiatives": []},
    }
    wb._merge_outputs_into_session_analysis(sid, draft["skill_outputs"], draft)
    blob = MemoryStore().get("session", sid)
    assert blob["skill_outputs"]["value-bridge-calculator"]["confidence_bands"]["mid"] == 2
    assert blob["last_workbench_run_id"] == draft["run_id"]

    bridge, savings = wb.latest_bridge_from_workbench(sid)
    assert bridge is None  # run not saved yet
    wb.save_run({**draft, "status": "complete", "created_at": "2026-01-01T00:00:00Z"})
    bridge, savings = wb.latest_bridge_from_workbench(sid)
    assert bridge and bridge["confidence_bands"]["mid"] == 2
    assert savings == {"initiatives": []}


def test_promote_run_initiatives() -> None:
    sid = _seed_session()
    run = asyncio.run(wb.run_workbench_run(wb.create_draft(
        session_id=sid, name="Promote me", selected_skills=["savings-modeler"],
    )))
    assert run["status"] == "complete"
    sm = run["skill_outputs"].get("savings-modeler") or {}
    if not sm.get("initiatives"):
        sm = {
            **sm,
            "initiatives": [
                {
                    "category": "IT Software & Licenses",
                    "lever": "contract_renegotiation",
                    "net_savings": {"npv_aftertax": 500_000.0, "year1": 200_000.0},
                }
            ],
        }
        run["skill_outputs"]["savings-modeler"] = sm
        wb.save_run(run)
    result = wb.promote_run_initiatives(run["run_id"])
    assert result["count"] >= 1
    assert result["promoted"][0].get("initiative_id")
