"""
Calibration pipeline — v2.1 §6.
At T+12m after engagement close, realised savings are ingested and compared
to the P10/P50/P90 plan.  Variances drive sector-pack lever-range update
proposals that a senior advisor reviews before version bumping the pack.
"""
from __future__ import annotations

import json
import logging
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

_CALIBRATION_ROOT = Path("data") / "calibration"
_SECTOR_PACKS_ROOT = Path(__file__).resolve().parents[2] / "sector_packs"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RealisedSavingsRecord:
    engagement_id: str
    initiative_id: str
    lever_id: str
    pack_id: str
    planned_p50_cr: float          # plan mid-case (Crore INR)
    realised_cr: float             # actual confirmed saving at T+12m
    realised_date: str             # ISO date string
    data_source: str               # "finance_sign_off" | "auditor" | "self_reported"
    confidence: str = "high"       # "high" | "medium" | "low"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RealisedSavingsRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class LeverRangeProposal:
    pack_id: str
    lever_id: str
    current_p10_pct: float
    current_p50_pct: float
    current_p90_pct: float
    proposed_p10_pct: float
    proposed_p50_pct: float
    proposed_p90_pct: float
    evidence_count: int
    realisation_rate: float        # median(realised / planned_p50)
    reviewer: Optional[str] = None
    approved: bool = False
    approval_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CalibrationReport:
    engagement_id: str
    generated_at: str
    records: List[RealisedSavingsRecord] = field(default_factory=list)
    variance_summary: Dict[str, Any] = field(default_factory=dict)
    lever_proposals: List[LeverRangeProposal] = field(default_factory=list)
    overall_realisation_rate: float = 0.0
    gate_recommendation: str = "review"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "engagement_id": self.engagement_id,
            "generated_at": self.generated_at,
            "records": [r.to_dict() for r in self.records],
            "variance_summary": self.variance_summary,
            "lever_proposals": [p.to_dict() for p in self.lever_proposals],
            "overall_realisation_rate": self.overall_realisation_rate,
            "gate_recommendation": self.gate_recommendation,
        }
        return d


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_realised_savings(
    engagement_id: str,
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Persist realised-savings records for an engagement.
    Returns {engagement_id, records_ingested, path}.
    """
    _CALIBRATION_ROOT.mkdir(parents=True, exist_ok=True)
    parsed: List[RealisedSavingsRecord] = []
    errors: List[str] = []
    for i, r in enumerate(records):
        try:
            rec = RealisedSavingsRecord.from_dict({**r, "engagement_id": engagement_id})
            parsed.append(rec)
        except Exception as exc:
            errors.append(f"Record {i}: {exc}")

    out_path = _CALIBRATION_ROOT / f"{engagement_id}_realised.json"
    existing: List[Dict] = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())
        except Exception:
            pass
    existing.extend([p.to_dict() for p in parsed])
    out_path.write_text(json.dumps(existing, indent=2))
    log.info("Ingested %d realised-savings records for %s", len(parsed), engagement_id)
    return {
        "engagement_id": engagement_id,
        "records_ingested": len(parsed),
        "errors": errors,
        "path": str(out_path),
    }


def load_realised_savings(engagement_id: str) -> List[RealisedSavingsRecord]:
    out_path = _CALIBRATION_ROOT / f"{engagement_id}_realised.json"
    if not out_path.exists():
        return []
    try:
        raw = json.loads(out_path.read_text())
        return [RealisedSavingsRecord.from_dict(r) for r in raw]
    except Exception as exc:
        log.warning("Could not load realised savings: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Variance computation
# ---------------------------------------------------------------------------

def compute_variance(engagement_id: str, initiative_id: str) -> Dict[str, Any]:
    """Return plan vs actual for a single initiative."""
    records = load_realised_savings(engagement_id)
    matched = [r for r in records if r.initiative_id == initiative_id]
    if not matched:
        return {"initiative_id": initiative_id, "found": False}

    total_planned = sum(r.planned_p50_cr for r in matched)
    total_realised = sum(r.realised_cr for r in matched)
    variance_cr = total_realised - total_planned
    realisation_rate = (total_realised / total_planned) if total_planned else 0.0
    return {
        "initiative_id": initiative_id,
        "found": True,
        "planned_p50_cr": round(total_planned, 2),
        "realised_cr": round(total_realised, 2),
        "variance_cr": round(variance_cr, 2),
        "realisation_rate": round(realisation_rate, 4),
        "records": len(matched),
    }


# ---------------------------------------------------------------------------
# Lever-range proposal
# ---------------------------------------------------------------------------

def propose_lever_range_update(
    pack_id: str,
    lever_id: str,
    realised_records: List[RealisedSavingsRecord],
) -> LeverRangeProposal:
    """
    Given realised records for a specific lever, propose new P10/P50/P90.
    Method: compute median realisation rate across records; scale current ranges.
    """
    current = _load_current_lever(pack_id, lever_id)
    cur_p10 = current.get("p10_pct", 4.0)
    cur_p50 = current.get("p50_pct", 8.0)
    cur_p90 = current.get("p90_pct", 15.0)

    lever_records = [r for r in realised_records if r.lever_id == lever_id]
    if not lever_records:
        return LeverRangeProposal(
            pack_id=pack_id,
            lever_id=lever_id,
            current_p10_pct=cur_p10,
            current_p50_pct=cur_p50,
            current_p90_pct=cur_p90,
            proposed_p10_pct=cur_p10,
            proposed_p50_pct=cur_p50,
            proposed_p90_pct=cur_p90,
            evidence_count=0,
            realisation_rate=1.0,
        )

    rates = [
        r.realised_cr / r.planned_p50_cr
        for r in lever_records
        if r.planned_p50_cr > 0
    ]
    if not rates:
        rates = [1.0]

    median_rate = statistics.median(rates)
    # Widen or narrow based on dispersion (stdev relative to median)
    if len(rates) > 1:
        stdev = statistics.stdev(rates)
        spread_factor = 1.0 + (stdev / max(median_rate, 0.01)) * 0.5
    else:
        spread_factor = 1.0

    proposed_p50 = round(cur_p50 * median_rate, 1)
    proposed_p10 = round(max(1.0, proposed_p50 * (cur_p10 / cur_p50) / spread_factor), 1)
    proposed_p90 = round(proposed_p50 * (cur_p90 / cur_p50) * spread_factor, 1)

    return LeverRangeProposal(
        pack_id=pack_id,
        lever_id=lever_id,
        current_p10_pct=cur_p10,
        current_p50_pct=cur_p50,
        current_p90_pct=cur_p90,
        proposed_p10_pct=proposed_p10,
        proposed_p50_pct=proposed_p50,
        proposed_p90_pct=proposed_p90,
        evidence_count=len(lever_records),
        realisation_rate=round(median_rate, 4),
    )


def _load_current_lever(pack_id: str, lever_id: str) -> Dict[str, Any]:
    levers_path = _SECTOR_PACKS_ROOT / pack_id / "sector_levers.json"
    if not levers_path.exists():
        return {}
    try:
        data = json.loads(levers_path.read_text())
        for lv in data.get("levers", []):
            if lv.get("lever_id") == lever_id:
                return lv
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Full calibration report
# ---------------------------------------------------------------------------

def generate_calibration_report(engagement_id: str) -> CalibrationReport:
    records = load_realised_savings(engagement_id)
    ts = datetime.now(timezone.utc).isoformat()

    if not records:
        return CalibrationReport(
            engagement_id=engagement_id,
            generated_at=ts,
            gate_recommendation="no_data",
        )

    # Variance by initiative
    initiative_ids = list({r.initiative_id for r in records})
    variances = {iid: compute_variance(engagement_id, iid) for iid in initiative_ids}

    rates = [
        v["realisation_rate"]
        for v in variances.values()
        if v.get("found") and v.get("realisation_rate") is not None
    ]
    overall_rate = round(statistics.mean(rates), 4) if rates else 0.0

    # Lever proposals per pack
    packs_levers: Dict[str, set] = {}
    for r in records:
        packs_levers.setdefault(r.pack_id, set()).add(r.lever_id)

    proposals: List[LeverRangeProposal] = []
    for pack_id, lever_ids in packs_levers.items():
        for lid in lever_ids:
            proposals.append(propose_lever_range_update(pack_id, lid, records))

    gate = (
        "auto_approve" if overall_rate >= 0.80
        else "senior_review" if overall_rate >= 0.60
        else "deep_audit"
    )

    report = CalibrationReport(
        engagement_id=engagement_id,
        generated_at=ts,
        records=records,
        variance_summary={
            "initiative_count": len(initiative_ids),
            "overall_realisation_rate": overall_rate,
            "by_initiative": variances,
        },
        lever_proposals=proposals,
        overall_realisation_rate=overall_rate,
        gate_recommendation=gate,
    )

    # Persist report
    _CALIBRATION_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = _CALIBRATION_ROOT / f"{engagement_id}_calibration_report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2))
    log.info("Calibration report written to %s", report_path)
    return report


# ---------------------------------------------------------------------------
# Version bump
# ---------------------------------------------------------------------------

def apply_version_bump(
    pack_id: str,
    proposals: List[LeverRangeProposal],
    reviewer: str,
    *,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Apply approved lever-range proposals to the sector pack and bump version.
    Returns {pack_id, old_version, new_version, levers_updated, dry_run}.
    """
    levers_path = _SECTOR_PACKS_ROOT / pack_id / "sector_levers.json"
    manifest_path = _SECTOR_PACKS_ROOT / pack_id / "pack_manifest.yaml"

    if not levers_path.exists():
        return {"error": f"sector_levers.json not found for pack '{pack_id}'"}

    import yaml  # type: ignore
    levers_data = json.loads(levers_path.read_text())
    manifest_data = yaml.safe_load(manifest_path.read_text()) or {}

    old_version = str(manifest_data.get("version", "1.0"))
    major, minor = (old_version.split(".")[:2] + ["0", "0"])[:2]
    new_version = f"{major}.{int(minor) + 1}"

    approved = [p for p in proposals if p.approved or reviewer]
    levers_updated = 0

    if not dry_run:
        lever_map = {lv["lever_id"]: lv for lv in levers_data.get("levers", [])}
        for proposal in approved:
            if proposal.lever_id in lever_map:
                lever_map[proposal.lever_id]["p10_pct"] = proposal.proposed_p10_pct
                lever_map[proposal.lever_id]["p50_pct"] = proposal.proposed_p50_pct
                lever_map[proposal.lever_id]["p90_pct"] = proposal.proposed_p90_pct
                levers_updated += 1
        levers_data["levers"] = list(lever_map.values())
        levers_path.write_text(json.dumps(levers_data, indent=2))

        manifest_data["version"] = new_version
        manifest_data["last_calibrated"] = datetime.now(timezone.utc).isoformat()
        manifest_data["calibrated_by"] = reviewer
        manifest_path.write_text(yaml.dump(manifest_data, default_flow_style=False))
        log.info(
            "Pack %s bumped %s → %s; %d levers updated by %s",
            pack_id, old_version, new_version, levers_updated, reviewer,
        )

    return {
        "pack_id": pack_id,
        "old_version": old_version,
        "new_version": new_version if not dry_run else f"{new_version} (dry_run)",
        "levers_updated": levers_updated if not dry_run else len(approved),
        "reviewer": reviewer,
        "dry_run": dry_run,
    }
