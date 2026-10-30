"""Regulatory event watcher — surface GST/SEBI/RBI/IRDAI/CMIE events at Reflect gates.

Phase 3 implementation: lightweight in-process watcher using a static event
catalogue supplemented by a writable events store.  Phase 4 will add live HTTP
polling of public feeds (SEBI circulars RSS, RBI press releases, GST portal
notifications).  A ForcedDecision is raised at each Reflect gate when an
unacknowledged HIGH-severity event matches an active initiative category.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR

_EVENTS_PATH = DATA_DIR / "reg_events.jsonl"
_lock = threading.Lock()

# --------------------------------------------------------------------------- #
# Severity levels and sources                                                   #
# --------------------------------------------------------------------------- #

SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

SOURCES = {"GST", "SEBI", "RBI", "IRDAI", "CMIE", "MCA21", "BRSR"}

# --------------------------------------------------------------------------- #
# Built-in baseline events (representative; not exhaustive)                    #
# --------------------------------------------------------------------------- #

_BASELINE_EVENTS: List[Dict[str, Any]] = [
    {
        "event_id": "RBI_2026_01",
        "source": "RBI",
        "title": "RBI Repo Rate decision — May 2026",
        "summary": "RBI cut repo rate by 25 bps to 6.25%. Cost-of-capital assumptions in NPV models should be reviewed.",
        "effective_date": "2026-05-09",
        "severity": SEVERITY_HIGH,
        "affected_categories": ["finance", "treasury", "working_capital", "leasing"],
        "acknowledged": False,
    },
    {
        "event_id": "GST_2026_02",
        "source": "GST",
        "title": "GST Council — Rate rationalisation notification",
        "summary": "GST rates revised on select B2B services (legal, consulting, IT). Confirm ITC eligibility mapping.",
        "effective_date": "2026-04-01",
        "severity": SEVERITY_HIGH,
        "affected_categories": ["professional_services", "it_software", "legal"],
        "acknowledged": False,
    },
    {
        "event_id": "SEBI_2026_03",
        "source": "SEBI",
        "title": "SEBI BRSR Core mandatory for top-1000 listed companies FY26",
        "summary": "BRSR Core disclosures (Scope-1, Scope-2, water, waste) are now mandatory. OpEx initiatives should include BRSR co-benefit estimates.",
        "effective_date": "2026-04-01",
        "severity": SEVERITY_MEDIUM,
        "affected_categories": ["energy", "logistics", "manufacturing", "facilities"],
        "acknowledged": False,
    },
    {
        "event_id": "MCA21_2026_04",
        "source": "MCA21",
        "title": "Companies Act related-party threshold update",
        "summary": "Related-party transaction thresholds revised. Conglomerate spend with group entities must be re-classified.",
        "effective_date": "2026-03-01",
        "severity": SEVERITY_MEDIUM,
        "affected_categories": ["intercompany", "group_services", "shared_services"],
        "acknowledged": False,
    },
]


# --------------------------------------------------------------------------- #
# Event store helpers                                                            #
# --------------------------------------------------------------------------- #

def _load_stored_events() -> List[Dict[str, Any]]:
    if not _EVENTS_PATH.exists():
        return []
    events: List[Dict[str, Any]] = []
    with _lock:
        for line in _EVENTS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _save_event(event: Dict[str, Any]) -> None:
    with _lock:
        _EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _EVENTS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def add_event(
    event_id: str,
    source: str,
    title: str,
    summary: str,
    effective_date: str,
    severity: str = SEVERITY_MEDIUM,
    affected_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Persist a new regulatory event to the writable store."""
    event = {
        "event_id": event_id,
        "source": source,
        "title": title,
        "summary": summary,
        "effective_date": effective_date,
        "severity": severity,
        "affected_categories": affected_categories or [],
        "acknowledged": False,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_event(event)
    return event


def acknowledge_event(event_id: str, *, acknowledged_by: str) -> bool:
    """Mark an event as acknowledged.  Returns True if found and updated."""
    events = _load_stored_events()
    found = False
    updated: List[Dict[str, Any]] = []
    for ev in events:
        if ev.get("event_id") == event_id:
            ev = dict(ev)
            ev["acknowledged"] = True
            ev["acknowledged_by"] = acknowledged_by
            ev["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
            found = True
        updated.append(ev)
    if found:
        with _lock:
            _EVENTS_PATH.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in updated) + "\n",
                encoding="utf-8",
            )
    return found


def _live_feeds_enabled() -> bool:
    """Phase 4 live HTTP polling — off by default; sample catalogue is advisory only."""
    return os.environ.get("REG_WATCHER_LIVE", "").strip().lower() in ("1", "true", "yes")

def get_active_events(
    *,
    categories: Optional[List[str]] = None,
    severity_filter: Optional[str] = None,
    since_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return unacknowledged regulatory events, optionally filtered.

    Args:
        categories: Only return events that mention at least one of these.
        severity_filter: Only return events at this severity or higher.
        since_date: ISO date string — only return events effective on or after.

    Returns list of event dicts, ordered newest-first.
    """
    _severity_order = {SEVERITY_HIGH: 3, SEVERITY_MEDIUM: 2, SEVERITY_LOW: 1}
    min_severity = _severity_order.get(severity_filter or SEVERITY_LOW, 1)

    all_events = _BASELINE_EVENTS + _load_stored_events()

    results: List[Dict[str, Any]] = []
    for ev in all_events:
        if ev.get("acknowledged"):
            continue
        sev_val = _severity_order.get(ev.get("severity", SEVERITY_LOW), 1)
        if sev_val < min_severity:
            continue
        if since_date:
            if ev.get("effective_date", "") < since_date:
                continue
        if categories:
            cat_lower = {c.lower() for c in categories}
            ev_cats = {c.lower() for c in (ev.get("affected_categories") or [])}
            if not cat_lower.intersection(ev_cats):
                continue
        results.append(ev)

    results.sort(key=lambda e: e.get("effective_date", ""), reverse=True)
    return results


def _trigger_matches_categories(trigger: Dict[str, Any], active_category_ids: List[str]) -> bool:
    """Return True when a pack trigger applies to at least one active category."""
    trigger_cats = [c.lower() for c in (trigger.get("category_ids") or [])]
    active = [c.lower() for c in active_category_ids if c]
    if not active:
        return False
    if "all" in trigger_cats:
        return True
    return bool(set(trigger_cats).intersection(active))


def surface_pack_regulatory_events(
    pack_id: str,
    active_category_ids: List[str],
) -> List[Dict[str, Any]]:
    """Convert sector-pack regulatory triggers into event-like dicts for active categories."""
    from app.services.sector_packs import get_pack_regulatory_context

    if not pack_id or not active_category_ids:
        return []
    ctx = get_pack_regulatory_context(pack_id)
    bodies = ctx.get("regulatory_bodies") or []
    source = str(bodies[0]) if bodies else "SECTOR_PACK"
    events: List[Dict[str, Any]] = []
    for idx, trigger in enumerate(ctx.get("triggers") or []):
        if not _trigger_matches_categories(trigger, active_category_ids):
            continue
        severity = str(trigger.get("severity") or SEVERITY_MEDIUM).upper()
        events.append({
            "event_id": f"PACK_{ctx.get('pack_id', pack_id)}_{idx}",
            "source": source,
            "title": str(trigger.get("trigger") or "Sector regulatory trigger"),
            "summary": (
                f"Sector-pack regulatory watch item for {ctx.get('pack_id', pack_id)}: "
                f"{trigger.get('trigger', '')}. Review initiative addressability and compliance assumptions."
            ),
            "effective_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "severity": severity,
            "affected_categories": list(trigger.get("category_ids") or []),
            "acknowledged": False,
            "origin": "sector_pack_trigger",
            "pack_id": ctx.get("pack_id", pack_id),
        })
    return events


def surface_at_reflect_gate(
    active_category_ids: List[str],
    *,
    engagement_week: int = 1,
    pack_id: str | None = None,
) -> Dict[str, Any]:
    """Determine whether a forced decision is required at this Reflect gate.

    Returns a dict with:
      forced_decision (bool) — True if any HIGH event matches active categories
      events            — list of matching events
      decision_prompt   — human-readable prompt to surface in the UI
      gate_week         — current engagement week
    """
    baseline_high = get_active_events(categories=active_category_ids, severity_filter=SEVERITY_HIGH)
    pack_events = surface_pack_regulatory_events(pack_id, active_category_ids) if pack_id else []
    pack_high = [ev for ev in pack_events if ev.get("severity") == SEVERITY_HIGH]
    matching: List[Dict[str, Any]] = list(baseline_high)
    seen_ids = {ev.get("event_id") for ev in matching}
    for ev in pack_events:
        if ev.get("event_id") not in seen_ids:
            matching.append(ev)
            seen_ids.add(ev.get("event_id"))
    live = _live_feeds_enabled()
    # Sample catalogue events are visible for awareness but do not force HITL until live feeds are on.
    forced = live and (len(baseline_high) > 0 or len(pack_high) > 0)
    catalogue_note = (
        "Live regulatory feeds enabled — unacknowledged HIGH events can block the gate."
        if live
        else "Sample catalogue only (set REG_WATCHER_LIVE=1 for live feed gating)."
    )
    if matching:
        prompt = (
            f"Week {engagement_week} gate — {len(matching)} regulatory event(s) match active categories "
            f"({catalogue_note}):\n"
            + "\n".join(
                f"• [{ev['source']}] {ev['title']}: {ev['summary']}"
                for ev in matching[:3]
            )
            + (
                "\nAcknowledge each event or adjust initiative assumptions before Gate-2."
                if forced
                else "\nReview for awareness — gate is not blocked in sample-catalogue mode."
            )
        )
    else:
        prompt = f"Week {engagement_week} gate — no unacknowledged HIGH-severity regulatory events affecting active categories."

    return {
        "forced_decision": forced,
        "events": matching,
        "decision_prompt": prompt,
        "gate_week": engagement_week,
        "event_source_mode": "live_feeds" if live else "sample_catalogue",
        "catalogue_note": catalogue_note,
    }
