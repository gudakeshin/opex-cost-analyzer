from __future__ import annotations

import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from app.config import DATA_DIR
from app.storage import read_json, write_json

PIPELINE_PATH = DATA_DIR / "pipeline" / "store.json"

ALLOWED_STAGES = {"identified", "committed", "in_flight", "realized", "rejected", "deferred"}
TRACKED_STAGES = {"committed", "in_flight", "realized"}

# Lock protecting all read-modify-write operations on the pipeline store.
_LOCK = threading.Lock()


def _load_store() -> Dict[str, Any]:
    return read_json(PIPELINE_PATH, {"initiatives": [], "milestones": [], "actuals": []})


def _save_store(store: Dict[str, Any]) -> None:
    write_json(PIPELINE_PATH, store)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None


def list_initiatives(
    user_id: str | None = None,
    session_id: str | None = None,
    stage: str | None = None,
    category: str | None = None,
    lever: str | None = None,
) -> List[Dict[str, Any]]:
    store = _load_store()
    rows = store.get("initiatives", [])
    out = []
    for row in rows:
        if user_id and row.get("user_id") != user_id:
            continue
        if session_id and row.get("session_id") != session_id:
            continue
        if stage and row.get("stage") != stage:
            continue
        if category and row.get("category") != category:
            continue
        if lever and row.get("lever") != lever:
            continue
        out.append(row)
    return out


def create_initiative(payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "initiative_id": str(uuid.uuid4()),
        "analysis_id": payload.get("analysis_id"),
        "user_id": payload.get("user_id"),
        "session_id": payload.get("session_id"),
        "category": payload.get("category"),
        "lever": payload.get("lever"),
        "root_cause": payload.get("root_cause"),
        "gross_savings_y1": float(payload.get("gross_savings_y1") or 0.0),
        "gross_savings_y2": float(payload.get("gross_savings_y2") or 0.0),
        "gross_savings_y3": float(payload.get("gross_savings_y3") or 0.0),
        "cost_to_achieve": float(payload.get("cost_to_achieve") or 0.0),
        "net_npv": float(payload.get("net_npv") or 0.0),
        "committed_savings": float(payload.get("committed_savings") or 0.0),
        # FP&A fields
        "savings_type": payload.get("savings_type", "run_rate"),  # "run_rate" | "one_time" | "mixed"
        "annualized_run_rate_savings": float(payload.get("annualized_run_rate_savings") or 0.0),
        "implementation_cost_schedule": payload.get("implementation_cost_schedule", []),  # [{period, amount}]
        "forecast_to_complete": payload.get("forecast_to_complete"),  # computed from actuals pace
        "stage": payload.get("stage", "identified"),
        "rejection_reason": payload.get("rejection_reason"),
        "owner_name": payload.get("owner_name"),
        "owner_email": payload.get("owner_email"),
        "committed_date": payload.get("committed_date"),
        "target_realization_date": payload.get("target_realization_date"),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    if row["stage"] not in ALLOWED_STAGES:
        row["stage"] = "identified"
    with _LOCK:
        store = _load_store()
        store.setdefault("initiatives", []).append(row)
        _save_store(store)
    return row


def update_initiative_stage(initiative_id: str, stage: str) -> Dict[str, Any] | None:
    if stage not in ALLOWED_STAGES:
        return None
    with _LOCK:
        store = _load_store()
        for row in store.get("initiatives", []):
            if row.get("initiative_id") != initiative_id:
                continue
            row["stage"] = stage
            if stage == "committed" and not row.get("committed_date"):
                row["committed_date"] = date.today().isoformat()
            row["updated_at"] = _now_iso()
            _save_store(store)
            return row
    return None


def reject_initiative(initiative_id: str, reason: str) -> Dict[str, Any] | None:
    with _LOCK:
        store = _load_store()
        for row in store.get("initiatives", []):
            if row.get("initiative_id") != initiative_id:
                continue
            row["stage"] = "rejected"
            row["rejection_reason"] = reason
            row["updated_at"] = _now_iso()
            _save_store(store)
            return row
    return None


def get_milestones(initiative_id: str) -> List[Dict[str, Any]]:
    store = _load_store()
    return [m for m in store.get("milestones", []) if m.get("initiative_id") == initiative_id]


def add_milestone(initiative_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    row = {
        "milestone_id": str(uuid.uuid4()),
        "initiative_id": initiative_id,
        "description": payload.get("description", ""),
        "due_date": payload.get("due_date"),
        "status": payload.get("status", "pending"),
        "evidence_doc_ref": payload.get("evidence_doc_ref"),
        "completed_at": payload.get("completed_at"),
        "created_at": _now_iso(),
    }
    with _LOCK:
        store = _load_store()
        store.setdefault("milestones", []).append(row)
        _save_store(store)
    return row


def add_actual(initiative_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        store = _load_store()
        committed = payload.get("committed_savings")
        if committed is None:
            match = next((i for i in store.get("initiatives", []) if i.get("initiative_id") == initiative_id), {})
            committed = float(match.get("committed_savings") or 0.0)
        row = {
            "actuals_id": str(uuid.uuid4()),
            "initiative_id": initiative_id,
            "period": payload.get("period"),
            "actual_savings": float(payload.get("actual_savings") or 0.0),
            "committed_savings": float(committed or 0.0),
            "variance": float(payload.get("actual_savings") or 0.0) - float(committed or 0.0),
            "gl_reference": payload.get("gl_reference"),
            "notes": payload.get("notes"),
            "created_at": _now_iso(),
        }
        store.setdefault("actuals", []).append(row)
        _save_store(store)
    return row


def pipeline_summary(user_id: str | None = None) -> Dict[str, Any]:
    # Load store once; derive both initiatives and actuals from the same snapshot.
    store = _load_store()
    all_initiatives = store.get("initiatives", [])
    actuals = store.get("actuals", [])

    stage_totals: Dict[str, Dict[str, float]] = {
        s: {"count": 0.0, "net_npv": 0.0} for s in ("identified", "committed", "in_flight", "realized", "rejected")
    }
    # FP&A: run-rate vs one-time breakdown
    run_rate_committed = 0.0
    one_time_committed = 0.0
    ids: set[str] = set()
    for row in all_initiatives:
        if user_id and row.get("user_id") != user_id:
            continue
        stage = row.get("stage", "identified")
        if stage not in stage_totals:
            continue
        stage_totals[stage]["count"] += 1
        stage_totals[stage]["net_npv"] += float(row.get("net_npv") or 0.0)
        ids.add(row.get("initiative_id", ""))
        # Accumulate run-rate vs one-time for committed+ stages
        if stage in ("committed", "in_flight", "realized"):
            savings_type = row.get("savings_type", "run_rate")
            arr = float(row.get("annualized_run_rate_savings") or 0.0)
            if savings_type in ("run_rate", "mixed"):
                run_rate_committed += arr
            else:
                one_time_committed += float(row.get("gross_savings_y1") or 0.0)

    scoped_actuals = [a for a in actuals if a.get("initiative_id") in ids]
    variance_total = sum(float(a.get("variance") or 0.0) for a in scoped_actuals)
    return {
        "identified": stage_totals["identified"],
        "committed": stage_totals["committed"],
        "in_flight": stage_totals["in_flight"],
        "realized": stage_totals["realized"],
        "rejected": stage_totals["rejected"],
        "variance_total": variance_total,
        # FP&A additions
        "run_rate_committed_savings": round(run_rate_committed, 2),
        "one_time_committed_savings": round(one_time_committed, 2),
    }


def at_risk_initiatives(user_id: str | None = None) -> List[Dict[str, Any]]:
    # Load store once; derive initiatives, milestones, and actuals from the same snapshot.
    today = date.today()
    store = _load_store()
    all_initiatives = store.get("initiatives", [])
    milestones = store.get("milestones", [])
    actuals = store.get("actuals", [])

    # Index milestones and actuals by initiative_id for O(1) lookup.
    milestones_by_iid: Dict[str, List[Dict[str, Any]]] = {}
    for m in milestones:
        milestones_by_iid.setdefault(m.get("initiative_id", ""), []).append(m)
    actuals_by_iid: Dict[str, List[Dict[str, Any]]] = {}
    for a in actuals:
        actuals_by_iid.setdefault(a.get("initiative_id", ""), []).append(a)

    out = []
    for row in all_initiatives:
        if user_id and row.get("user_id") != user_id:
            continue
        stage = row.get("stage")
        if stage not in TRACKED_STAGES:
            continue
        iid = row.get("initiative_id", "")
        reasons: List[str] = []
        target = _safe_date(row.get("target_realization_date"))
        if target and target < today and stage != "realized":
            reasons.append("Past target realization date")
        for m in milestones_by_iid.get(iid, []):
            due = _safe_date(m.get("due_date"))
            status = m.get("status", "pending")
            if due and due < today and status not in ("complete",):
                reasons.append("Overdue milestone")
                break
        relevant_actuals = actuals_by_iid.get(iid, [])
        if relevant_actuals and any(float(a.get("variance") or 0.0) < 0 for a in relevant_actuals):
            reasons.append("Negative savings variance")

        # Forecast to Complete (FTC): extrapolate from actuals run rate
        committed = float(row.get("committed_savings") or 0.0)
        ftc = None
        if relevant_actuals and committed > 0:
            total_realized = sum(float(a.get("actual_savings") or 0.0) for a in relevant_actuals)
            period_count = len(relevant_actuals)
            monthly_run_rate = total_realized / period_count if period_count > 0 else 0.0
            # Estimate remaining months to target date
            if target and target > today:
                remaining_months = max(1, (target.year - today.year) * 12 + (target.month - today.month))
            else:
                remaining_months = 6  # default 6-month horizon
            ftc = total_realized + monthly_run_rate * remaining_months
            ftc_gap = ftc - committed
            if ftc < committed * 0.90:
                reasons.append(
                    f"Forecast to Complete (${ftc:,.0f}) is {abs(ftc_gap / committed):.0%} below committed (${committed:,.0f})"
                )

        if reasons:
            entry = {
                "initiative_id": iid,
                "category": row.get("category"),
                "lever": row.get("lever"),
                "savings_type": row.get("savings_type", "run_rate"),
                "committed_savings": committed,
                "reasons": reasons,
            }
            if ftc is not None:
                entry["forecast_to_complete"] = round(ftc, 2)
            out.append(entry)
    return out
