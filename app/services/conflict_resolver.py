"""Conflict Resolution Engine — Phase 2.

Detects and resolves data conflicts across multiple source systems.
Seven detector types, six resolution strategies, one escalation path.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.models import ConflictRecord, NormalizedSpendLine

logger = logging.getLogger("opex.conflict_resolver")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# TDS rate table: vendor_category → rate (approximate; used for gross-up estimation)
_TDS_RATES: Dict[str, float] = {
    "large": 0.10,
    "msme": 0.10,
    "foreign": 0.20,
    "startup": 0.10,
    "default": 0.10,
}

# Materiality threshold — conflicts smaller than this fraction of amount are low-severity
_MATERIALITY_THRESHOLD = 0.05  # 5%


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _delta_pct(a: float, b: float) -> float:
    """Absolute percentage difference relative to the larger value."""
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom


def _severity_from_delta(delta: float) -> str:
    if delta >= 0.20:
        return "critical"
    if delta >= 0.10:
        return "high"
    if delta >= _MATERIALITY_THRESHOLD:
        return "medium"
    return "low"


def _group_by_gstin(lines: List[NormalizedSpendLine]) -> Dict[str, List[NormalizedSpendLine]]:
    groups: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        key = line.vendor_gstin or line.gstin or ""
        if key:
            groups.setdefault(key, []).append(line)
    return groups


def _group_by_supplier_name(lines: List[NormalizedSpendLine]) -> Dict[str, List[NormalizedSpendLine]]:
    groups: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        key = (line.supplier or "").strip().lower()
        if key:
            groups.setdefault(key, []).append(line)
    return groups


def _lines_by_source(lines: List[NormalizedSpendLine]) -> Dict[str, List[NormalizedSpendLine]]:
    groups: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        src = line.source_system_id or "unknown"
        groups.setdefault(src, []).append(line)
    return groups


# ---------------------------------------------------------------------------
# 7 Conflict Detectors
# ---------------------------------------------------------------------------

def detect_tds_mismatch(lines: List[NormalizedSpendLine]) -> List[ConflictRecord]:
    """Detect AP/GL vs bank amount mismatches attributable to TDS withholding.

    Signal: two lines with the same source_record_id from different source systems
    where amount_a ≠ amount_b and the delta is consistent with a TDS rate.
    """
    conflicts: List[ConflictRecord] = []
    by_record: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        if line.source_record_id:
            by_record.setdefault(line.source_record_id, []).append(line)

    for rec_id, group in by_record.items():
        sources = {l.source_system_id for l in group if l.source_system_id}
        if len(sources) < 2:
            continue
        amounts = [(l.source_system_id or "unknown", l.amount) for l in group]
        for i in range(len(amounts)):
            for j in range(i + 1, len(amounts)):
                src_a, amt_a = amounts[i]
                src_b, amt_b = amounts[j]
                delta = _delta_pct(amt_a, amt_b)
                if delta < _MATERIALITY_THRESHOLD:
                    continue
                # Check if delta is consistent with a TDS rate (5–20%)
                tds_rate = abs(amt_a - amt_b) / max(amt_a, amt_b, 1.0)
                if 0.04 <= tds_rate <= 0.22:
                    conflicts.append(ConflictRecord(
                        conflict_type="tds_mismatch",
                        severity=_severity_from_delta(delta),
                        source_a=src_a,
                        source_b=src_b,
                        amount_a=amt_a,
                        amount_b=amt_b,
                        delta_pct=round(delta * 100, 2),
                        resolution_strategy="tds_gross_up",
                        row_ids=[l.row_id for l in group],
                    ))
    logger.info('"conflict_tds_mismatch detected=%d"', len(conflicts))
    return conflicts


def detect_gst_mismatch(lines: List[NormalizedSpendLine]) -> List[ConflictRecord]:
    """Detect vendor GSTIN → ITC amount mismatches (GSTR-2A vs AP books).

    Signal: lines tagged gst_treatment='itc_eligible' from two sources
    with the same GSTIN but different amounts (same period).
    """
    conflicts: List[ConflictRecord] = []
    eligible = [l for l in lines if l.gst_treatment in ("itc_eligible", "rcm")]
    by_gstin = _group_by_gstin(eligible)

    for gstin, group in by_gstin.items():
        sources = {l.source_system_id for l in group if l.source_system_id}
        if len(sources) < 2:
            continue
        by_src: Dict[str, float] = {}
        src_rows: Dict[str, List[int]] = {}
        for l in group:
            sid = l.source_system_id or "unknown"
            by_src[sid] = by_src.get(sid, 0.0) + l.amount
            src_rows.setdefault(sid, []).append(l.row_id)

        srcs = list(by_src.keys())
        for i in range(len(srcs)):
            for j in range(i + 1, len(srcs)):
                sa, sb = srcs[i], srcs[j]
                amt_a, amt_b = by_src[sa], by_src[sb]
                delta = _delta_pct(amt_a, amt_b)
                if delta < _MATERIALITY_THRESHOLD:
                    continue
                conflicts.append(ConflictRecord(
                    conflict_type="gst_mismatch",
                    severity=_severity_from_delta(delta),
                    source_a=sa,
                    source_b=sb,
                    amount_a=amt_a,
                    amount_b=amt_b,
                    delta_pct=round(delta * 100, 2),
                    resolution_strategy="gstr_vendor_data",
                    row_ids=src_rows[sa] + src_rows[sb],
                ))
    logger.info('"conflict_gst_mismatch detected=%d"', len(conflicts))
    return conflicts


def _normalise_vendor_name(name: str) -> str:
    """Normalise a vendor name for script-agnostic comparison.

    Steps:
    1. Strip whitespace and lower-case.
    2. If indic-transliteration is available, transliterate any Indian-script
       characters to ITRANS (Latin) so 'टाटा कंसल्टेंसी' and 'Tata Consultancy'
       can be recognised as the same entity name phonetically.
    3. Remove common legal suffixes (Pvt Ltd, Ltd, LLP, Inc, etc.) and punctuation.
    """
    if not name:
        return ""
    text = name.strip().lower()

    # Transliterate Indian scripts to Latin if available
    try:
        from app.services.ingestion import transliterate_to_latin
        for script in ("DEVANAGARI", "TAMIL", "TELUGU", "KANNADA", "BENGALI", "GUJARATI", "GURMUKHI"):
            text = transliterate_to_latin(text, script)
    except Exception:
        pass

    # Remove legal suffixes and punctuation
    _LEGAL_SUFFIXES = re.compile(
        r"\b(private limited|pvt\.?\s*ltd\.?|ltd\.?|llp|inc\.?|corp\.?|"
        r"limited|co\.?|company|enterprises|solutions|services|technologies|"
        r"pvt|and sons|& sons)\b",
        re.IGNORECASE,
    )
    text = _LEGAL_SUFFIXES.sub("", text)
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_vendor_duplicates(lines: List[NormalizedSpendLine]) -> List[ConflictRecord]:
    """Detect the same vendor appearing under multiple name strings across sources.

    Primary dedup key: GSTIN (canonical and infallible for Indian vendors).
    Secondary (name-based): script-agnostic fuzzy match after transliteration of
    Devanagari/Tamil/Telugu/etc. → ITRANS Latin, allowing detection of the same
    vendor named differently across ERP, Tally, and manual spreadsheets.
    """
    conflicts: List[ConflictRecord] = []
    by_gstin = _group_by_gstin(lines)

    # Primary path: GSTIN-keyed dedup
    for gstin, group in by_gstin.items():
        names = {(l.supplier or "").strip().lower() for l in group if l.supplier}
        sources = {l.source_system_id for l in group if l.source_system_id}
        if len(names) < 2:
            continue
        canonical = max(names, key=len)
        aliases = list(names - {canonical})
        total_amount = sum(l.amount for l in group)
        conflicts.append(ConflictRecord(
            conflict_type="vendor_duplicate",
            severity="medium",
            source_a=list(sources)[0] if sources else "unknown",
            source_b=list(sources)[1] if len(sources) > 1 else "multiple",
            amount_a=total_amount,
            amount_b=0.0,
            delta_pct=0.0,
            resolution_strategy="gstin_dedup",
            resolution_notes=f"canonical={canonical!r} aliases={aliases}",
            row_ids=[l.row_id for l in group],
        ))

    # Secondary path: name-based dedup for lines without GSTIN
    no_gstin = [l for l in lines if not (l.vendor_gstin or l.gstin)]
    if no_gstin:
        norm_groups: Dict[str, List[NormalizedSpendLine]] = {}
        for l in no_gstin:
            key = _normalise_vendor_name(l.supplier or "")
            if key and len(key) >= 3:
                norm_groups.setdefault(key, []).append(l)

        for norm_name, group in norm_groups.items():
            raw_names = {(l.supplier or "").strip().lower() for l in group}
            if len(raw_names) < 2:
                continue
            sources = {l.source_system_id for l in group if l.source_system_id}
            total_amount = sum(l.amount for l in group)
            canonical = max(raw_names, key=len)
            aliases = list(raw_names - {canonical})
            conflicts.append(ConflictRecord(
                conflict_type="vendor_duplicate",
                severity="low",
                source_a=list(sources)[0] if sources else "unknown",
                source_b=list(sources)[1] if len(sources) > 1 else "multiple",
                amount_a=total_amount,
                amount_b=0.0,
                delta_pct=0.0,
                resolution_strategy="gstin_dedup",
                resolution_notes=(
                    f"Script-agnostic name match (no GSTIN): "
                    f"canonical={canonical!r} aliases={aliases} norm_key={norm_name!r}"
                ),
                row_ids=[l.row_id for l in group],
            ))

    logger.info('"conflict_vendor_duplicates detected=%d"', len(conflicts))
    return conflicts


def detect_intercompany_inflation(
    lines: List[NormalizedSpendLine],
    entity_ids: Optional[List[str]] = None,
) -> List[ConflictRecord]:
    """Detect intercompany transactions that inflate the consolidated cost base.

    Signal: related_party_flag=True or is_intercompany=True and both buyer/seller
    are within the entity group, and consolidation_eliminated=False.
    """
    conflicts: List[ConflictRecord] = []
    ic_lines = [
        l for l in lines
        if (l.related_party_flag or l.is_intercompany) and not l.consolidation_eliminated
    ]
    if not ic_lines:
        return conflicts

    total_ic = sum(l.amount for l in ic_lines)
    row_ids = [l.row_id for l in ic_lines]
    sources = list({l.source_system_id for l in ic_lines if l.source_system_id})
    conflicts.append(ConflictRecord(
        conflict_type="intercompany_inflation",
        severity="high",
        source_a=sources[0] if sources else "unknown",
        source_b=sources[1] if len(sources) > 1 else "consolidated_view",
        amount_a=total_ic,
        amount_b=0.0,
        delta_pct=100.0,
        resolution_strategy="eliminate_intercompany",
        resolution_notes=f"ic_transaction_count={len(ic_lines)} total_ic_amount={total_ic:.2f}",
        row_ids=row_ids,
    ))
    logger.info('"conflict_intercompany_inflation ic_lines=%d total_ic=%.2f"', len(ic_lines), total_ic)
    return conflicts


def detect_fx_mismatch(lines: List[NormalizedSpendLine]) -> List[ConflictRecord]:
    """Detect FX rate inconsistencies — same vendor/period booked at different rates.

    Signal: lines with same source_record_id but different fx_rate_to_reporting values.
    """
    conflicts: List[ConflictRecord] = []
    by_record: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        if line.source_record_id and line.currency != "INR":
            by_record.setdefault(line.source_record_id, []).append(line)

    for rec_id, group in by_record.items():
        rates = [l.fx_rate_to_reporting for l in group]
        if not rates:
            continue
        min_r, max_r = min(rates), max(rates)
        delta = _delta_pct(min_r, max_r)
        if delta < _MATERIALITY_THRESHOLD:
            continue
        sources = list({l.source_system_id for l in group if l.source_system_id})
        conflicts.append(ConflictRecord(
            conflict_type="fx_mismatch",
            severity=_severity_from_delta(delta),
            source_a=sources[0] if sources else "unknown",
            source_b=sources[1] if len(sources) > 1 else "unknown",
            amount_a=min_r,
            amount_b=max_r,
            delta_pct=round(delta * 100, 2),
            resolution_strategy="escalate",
            resolution_notes=f"record_id={rec_id} currency={group[0].currency}",
            row_ids=[l.row_id for l in group],
        ))
    logger.info('"conflict_fx_mismatch detected=%d"', len(conflicts))
    return conflicts


def detect_benchmark_disagreement(
    benchmarks: List[Dict[str, Any]],
    disagreement_threshold: float = 0.20,
) -> List[ConflictRecord]:
    """Detect conflicting benchmark values across datasets for the same category.

    Each benchmark dict must have: category_id, value, source (dataset name), sample_n, vintage.
    A conflict is raised when two sources for the same category disagree by > threshold.
    """
    conflicts: List[ConflictRecord] = []
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for bm in benchmarks:
        cat = str(bm.get("category_id") or "")
        if cat:
            by_category.setdefault(cat, []).append(bm)

    for cat_id, bms in by_category.items():
        if len(bms) < 2:
            continue
        for i in range(len(bms)):
            for j in range(i + 1, len(bms)):
                a, b = bms[i], bms[j]
                val_a = float(a.get("value") or 0.0)
                val_b = float(b.get("value") or 0.0)
                delta = _delta_pct(val_a, val_b)
                if delta < disagreement_threshold:
                    continue
                conflicts.append(ConflictRecord(
                    conflict_type="benchmark_disagreement",
                    severity=_severity_from_delta(delta),
                    source_a=str(a.get("source") or "unknown"),
                    source_b=str(b.get("source") or "unknown"),
                    amount_a=val_a,
                    amount_b=val_b,
                    delta_pct=round(delta * 100, 2),
                    resolution_strategy="confidence_blend",
                    resolution_notes=f"category={cat_id}",
                    row_ids=[],
                ))
    logger.info('"conflict_benchmark_disagreement detected=%d"', len(conflicts))
    return conflicts


def detect_cost_center_lag(lines: List[NormalizedSpendLine]) -> List[ConflictRecord]:
    """Detect cost centre assignment lag — same transaction assigned differently across sources.

    Signal: lines with same source_record_id but different cost_center_id across sources.
    """
    conflicts: List[ConflictRecord] = []
    by_record: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        if line.source_record_id and line.cost_center_id:
            by_record.setdefault(line.source_record_id, []).append(line)

    for rec_id, group in by_record.items():
        cost_centers = {l.cost_center_id for l in group}
        if len(cost_centers) < 2:
            continue
        sources = list({l.source_system_id for l in group if l.source_system_id})
        amounts = [l.amount for l in group]
        conflicts.append(ConflictRecord(
            conflict_type="cost_center_lag",
            severity="medium",
            source_a=sources[0] if sources else "unknown",
            source_b=sources[1] if len(sources) > 1 else "unknown",
            amount_a=amounts[0] if amounts else 0.0,
            amount_b=amounts[1] if len(amounts) > 1 else 0.0,
            delta_pct=0.0,
            resolution_strategy="escalate",
            resolution_notes=f"record_id={rec_id} cost_centers={list(cost_centers)}",
            row_ids=[l.row_id for l in group],
        ))
    logger.info('"conflict_cost_center_lag detected=%d"', len(conflicts))
    return conflicts


# ---------------------------------------------------------------------------
# 6 Resolution Strategies
# ---------------------------------------------------------------------------

def resolve_tds_gross_up(
    lines: List[NormalizedSpendLine], conflict: ConflictRecord
) -> Tuple[List[NormalizedSpendLine], ConflictRecord]:
    """Add TDS back to bank amount; use AP/GL amount as canonical."""
    resolved_lines = []
    for line in lines:
        if line.row_id in conflict.row_ids:
            tds_rate = _TDS_RATES.get(line.vendor_category or "default", 0.10)
            reconciled = line.amount / (1 - tds_rate) if line.amount > 0 else line.amount
            line = line.model_copy(update={
                "reconciled_amount": round(reconciled, 2),
                "conflict_flag": "tds_mismatch",
                "conflict_resolution": "tds_gross_up",
            })
        resolved_lines.append(line)
    conflict = conflict.model_copy(update={"resolved": True, "resolution_strategy": "tds_gross_up"})
    return resolved_lines, conflict


def resolve_gstin_dedup(
    lines: List[NormalizedSpendLine], conflict: ConflictRecord
) -> Tuple[List[NormalizedSpendLine], ConflictRecord]:
    """Merge vendor aliases by GSTIN; set canonical supplier name on all matching rows."""
    gstin_canonical: Dict[str, str] = {}
    for line in lines:
        gstin = line.vendor_gstin or line.gstin
        if gstin and line.supplier:
            existing = gstin_canonical.get(gstin, "")
            if len(line.supplier) > len(existing):
                gstin_canonical[gstin] = line.supplier

    resolved_lines = []
    for line in lines:
        gstin = line.vendor_gstin or line.gstin
        if gstin and gstin_canonical.get(gstin) and line.row_id in conflict.row_ids:
            line = line.model_copy(update={
                "supplier": gstin_canonical[gstin],
                "conflict_flag": "vendor_duplicate",
                "conflict_resolution": "gstin_dedup",
            })
        resolved_lines.append(line)
    conflict = conflict.model_copy(update={"resolved": True, "resolution_strategy": "gstin_dedup"})
    return resolved_lines, conflict


def resolve_eliminate_intercompany(
    lines: List[NormalizedSpendLine], conflict: ConflictRecord
) -> Tuple[List[NormalizedSpendLine], ConflictRecord]:
    """Mark intercompany lines as eliminated from consolidated view."""
    resolved_lines = []
    for line in lines:
        if line.row_id in conflict.row_ids:
            line = line.model_copy(update={
                "consolidation_eliminated": True,
                "conflict_flag": "intercompany_inflation",
                "conflict_resolution": "eliminate_intercompany",
            })
        resolved_lines.append(line)
    conflict = conflict.model_copy(update={"resolved": True, "resolution_strategy": "eliminate_intercompany"})
    return resolved_lines, conflict


def resolve_confidence_blend(
    benchmarks: List[Dict[str, Any]], conflict: ConflictRecord
) -> Tuple[Dict[str, Any], ConflictRecord]:
    """Weight benchmarks by sample_n × recency_score; return blended value."""
    category = (conflict.resolution_notes or "").replace("category=", "").strip()
    relevant = [b for b in benchmarks if str(b.get("category_id")) == category]
    if not relevant:
        return {}, conflict

    total_weight = 0.0
    blended = 0.0
    for bm in relevant:
        n = float(bm.get("sample_n") or 1)
        recency = float(bm.get("recency_score") or 0.5)
        weight = n * recency
        blended += float(bm.get("value") or 0.0) * weight
        total_weight += weight

    blended_val = blended / total_weight if total_weight > 0 else 0.0
    result = {
        "category_id": category,
        "blended_value": round(blended_val, 4),
        "sources_blended": [str(b.get("source")) for b in relevant],
        "total_weight": round(total_weight, 2),
    }
    conflict = conflict.model_copy(update={
        "resolved": True,
        "resolution_strategy": "confidence_blend",
        "resolution_notes": f"{conflict.resolution_notes or ''} blended_value={blended_val:.4f}",
    })
    return result, conflict


def resolve_gstr_vendor_data(
    lines: List[NormalizedSpendLine], conflict: ConflictRecord
) -> Tuple[List[NormalizedSpendLine], ConflictRecord]:
    """Use GSTR-2A sourced amount as canonical for GST-eligible lines."""
    resolved_lines = []
    for line in lines:
        if line.row_id in conflict.row_ids and line.source_system_id == "GSTR_2A":
            line = line.model_copy(update={
                "reconciled_amount": line.amount,
                "conflict_flag": "gst_mismatch",
                "conflict_resolution": "gstr_vendor_data",
            })
        resolved_lines.append(line)
    conflict = conflict.model_copy(update={"resolved": True, "resolution_strategy": "gstr_vendor_data"})
    return resolved_lines, conflict


def escalate(conflict: ConflictRecord, reason: str = "") -> ConflictRecord:
    """Mark conflict for human review (CFO / controller sign-off required)."""
    return conflict.model_copy(update={
        "resolution_strategy": "escalate",
        "resolution_notes": f"Escalated for manual review. {reason}".strip(),
        "resolved": False,
    })


# ---------------------------------------------------------------------------
# Display guidance — human-readable conflict context for UI / chat
# ---------------------------------------------------------------------------

_CONFLICT_TYPE_LABELS: Dict[str, str] = {
    "tds_mismatch": "TDS withholding mismatch",
    "gst_mismatch": "GST / ITC amount mismatch",
    "vendor_duplicate": "Duplicate vendor records",
    "intercompany_inflation": "Intercompany spend inflation",
    "fx_mismatch": "FX rate inconsistency",
    "benchmark_disagreement": "Benchmark source disagreement",
    "amount_mismatch": "Amount mismatch across sources",
    "cost_center_lag": "Cost centre mapping lag",
}

_STRATEGY_GUIDANCE: Dict[str, Dict[str, str]] = {
    "tds_gross_up": {
        "recommendation": (
            "The difference matches tax deducted at source (TDS). Use the AP/GL invoice "
            "amount as canonical and gross up the net bank payment by the applicable TDS rate."
        ),
        "action_label": "Apply TDS gross-up",
    },
    "gstin_dedup": {
        "recommendation": (
            "The same vendor appears under multiple names across sources. Merge to a single "
            "canonical supplier name (prefer the GSTIN-linked legal name) before counting spend."
        ),
        "action_label": "Merge vendor names",
    },
    "eliminate_intercompany": {
        "recommendation": (
            "Related-party / intercompany lines inflate consolidated spend. Excluding them "
            "removes those rows from the spend baseline and re-profiles category totals. "
            "Savings initiatives are not recalculated automatically — re-run analysis if "
            "pipeline numbers should move."
        ),
        "action_label": "Exclude from spend base",
    },
    "gstr_vendor_data": {
        "recommendation": (
            "GSTR-2A (tax portal) and AP books disagree on ITC-eligible GST. Use the GSTR-2A "
            "filed amount as the authoritative vendor GST figure for reconciliation."
        ),
        "action_label": "Use GSTR-2A amount",
    },
    "confidence_blend": {
        "recommendation": (
            "Benchmark datasets disagree for this category. Blend values weighted by sample "
            "size and recency, or override with your preferred benchmark source."
        ),
        "action_label": "Blend benchmark sources",
    },
    "escalate": {
        "recommendation": (
            "Sources cannot be auto-reconciled. Review with Finance / Treasury and confirm "
            "which source should drive the savings pipeline before committing numbers."
        ),
        "action_label": "Flag for manual review",
    },
}


def _format_amount(value: Optional[float], conflict: ConflictRecord) -> str:
    if value is None:
        return "—"
    if conflict.conflict_type in ("fx_mismatch", "benchmark_disagreement"):
        return f"{value:,.4f}"
    return f"₹{value:,.2f} Cr"


def _build_conflict_description(conflict: ConflictRecord) -> str:
    ctype = conflict.conflict_type
    src_a = conflict.source_a or "source A"
    src_b = conflict.source_b or "source B"
    amt_a = _format_amount(conflict.amount_a, conflict)
    amt_b = _format_amount(conflict.amount_b, conflict)
    delta = conflict.delta_pct

    if ctype == "tds_mismatch":
        base = (
            f"{src_a} records {amt_a} while {src_b} records {amt_b}"
            + (f" ({delta:.1f}% gap)" if delta is not None else "")
            + ". The gap is consistent with TDS withholding on the payment."
        )
        return base
    if ctype == "gst_mismatch":
        return (
            f"GSTIN-linked ITC spend totals {amt_a} in {src_a} vs {amt_b} in {src_b}"
            + (f" ({delta:.1f}% gap)" if delta is not None else "")
            + " for the same filing period."
        )
    if ctype == "vendor_duplicate":
        notes = conflict.resolution_notes or ""
        if "canonical=" in notes:
            return (
                f"The same vendor is recorded under different names across {src_a} and {src_b}. "
                f"Combined spend is {amt_a}. {notes.replace('canonical=', 'Suggested canonical name: ').replace(' aliases=', '; aliases: ')}"
            )
        return (
            f"The same vendor appears under different names across {src_a} and {src_b}. "
            f"Combined spend is {amt_a}."
        )
    if ctype == "intercompany_inflation":
        notes = conflict.resolution_notes or ""
        return (
            f"Intercompany / related-party transactions totalling {amt_a} are included in "
            f"consolidated spend from {src_a}"
            + (f" and {src_b}" if src_b != "consolidated_view" else "")
            + f". {notes.replace('ic_transaction_count=', 'Transactions: ').replace(' total_ic_amount=', '; amount: ')}"
        )
    if ctype == "fx_mismatch":
        notes = conflict.resolution_notes or ""
        return (
            f"FX rates differ: {amt_a} vs {amt_b} between {src_a} and {src_b}"
            + (f" ({delta:.1f}% gap)" if delta is not None else "")
            + f". {notes}"
        )
    if ctype == "benchmark_disagreement":
        notes = conflict.resolution_notes or ""
        return (
            f"Benchmark values disagree: {src_a} reports {amt_a} vs {src_b} at {amt_b}"
            + (f" ({delta:.1f}% gap)" if delta is not None else "")
            + f". {notes.replace('category=', 'Category: ')}"
        )
    if ctype == "cost_center_lag":
        notes = conflict.resolution_notes or ""
        return (
            f"The same transaction is mapped to different cost centres in {src_a} vs {src_b}. "
            f"{notes.replace('record_id=', 'Record: ').replace(' cost_centers=', '; centres: ')}"
        )
    return (
        f"{src_a} vs {src_b}: {amt_a} vs {amt_b}"
        + (f" ({delta:.1f}% gap)" if delta is not None else "")
    )


def stable_conflict_id(conflict: ConflictRecord) -> str:
    """Deterministic id so GET and POST refer to the same conflict across re-detection."""
    parts = [
        conflict.conflict_type,
        conflict.source_a or "",
        conflict.source_b or "",
        ",".join(str(r) for r in sorted(conflict.row_ids)),
        (conflict.resolution_notes or "")[:240],
    ]
    if conflict.amount_a is not None:
        parts.append(f"a:{conflict.amount_a:.6f}")
    if conflict.amount_b is not None:
        parts.append(f"b:{conflict.amount_b:.6f}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"conf-{conflict.conflict_type}-{digest}"


def assign_stable_conflict_ids(conflicts: List[ConflictRecord]) -> List[ConflictRecord]:
    return [c.model_copy(update={"conflict_id": stable_conflict_id(c)}) for c in conflicts]


def normalize_user_actions(
    user_actions: Optional[Dict[str, Dict[str, Any]]],
    conflicts: List[ConflictRecord],
) -> Dict[str, Dict[str, Any]]:
    """Re-key persisted actions onto stable conflict ids."""
    if not user_actions:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for conflict in conflicts:
        sid = stable_conflict_id(conflict)
        if sid in user_actions:
            out[sid] = user_actions[sid]
            continue
        for _legacy_key, action in user_actions.items():
            if action.get("conflict_fingerprint") == sid:
                out[sid] = action
                break
    return out


def conflict_matches_request(conflict: ConflictRecord, requested_ids: List[str]) -> bool:
    if not requested_ids:
        return True
    sid = stable_conflict_id(conflict)
    return conflict.conflict_id in requested_ids or sid in requested_ids


def apply_user_action_overlay(
    enriched: Dict[str, Any],
    user_actions: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Merge persisted user decisions (apply / flag) into API conflict payloads."""
    if not user_actions:
        return enriched
    conflict_id = enriched.get("conflict_id")
    if not conflict_id:
        return enriched
    action = user_actions.get(conflict_id)
    if not action:
        for _key, candidate in user_actions.items():
            if candidate.get("conflict_fingerprint") == conflict_id:
                action = candidate
                break
    if not action:
        return enriched

    status = action.get("status")
    if status == "flagged_for_review":
        enriched["user_status"] = "flagged_for_review"
        enriched["resolved"] = True
        enriched["can_auto_apply"] = False
        enriched["requires_manual_review"] = False
        enriched["recommendation"] = (
            "Flagged for manual review. Confirm the correct source with Finance / "
            "Treasury before including this spend in committed savings."
        )
        enriched["action_label"] = "Flagged for review"
    elif status == "applied":
        enriched["user_status"] = "applied"
        enriched["resolved"] = True
        enriched["can_auto_apply"] = False
        enriched["requires_manual_review"] = False
        enriched["action_label"] = "Recommendation applied"
    return enriched


def enrich_conflict_for_display(conflict: ConflictRecord) -> Dict[str, Any]:
    """Attach human-readable title, description, and recommended action for UI."""
    data = conflict.model_dump(mode="json")
    strategy = conflict.resolution_strategy or "escalate"
    guidance = _STRATEGY_GUIDANCE.get(strategy, _STRATEGY_GUIDANCE["escalate"])

    data["title"] = _CONFLICT_TYPE_LABELS.get(
        conflict.conflict_type,
        conflict.conflict_type.replace("_", " ").title(),
    )
    data["description"] = _build_conflict_description(conflict)
    data["recommendation"] = guidance["recommendation"]
    data["action_label"] = guidance["action_label"]
    data["requires_manual_review"] = strategy == "escalate"
    data["can_auto_apply"] = bool(strategy and strategy != "escalate" and not conflict.resolved)
    if conflict.conflict_type == "intercompany_inflation" and conflict.amount_a is not None:
        data["estimated_spend_impact"] = round(float(conflict.amount_a), 2)
    return data


# ---------------------------------------------------------------------------
# ConflictResolver — orchestrates all detectors
# ---------------------------------------------------------------------------

class ConflictResolver:
    """Orchestrates all 7 conflict detectors against a set of NormalizedSpendLines."""

    def run_all(
        self,
        lines: List[NormalizedSpendLine],
        benchmarks: Optional[List[Dict[str, Any]]] = None,
        entity_ids: Optional[List[str]] = None,
    ) -> List[ConflictRecord]:
        """Run all applicable detectors and return a deduplicated conflict list."""
        all_conflicts: List[ConflictRecord] = []
        all_conflicts.extend(detect_tds_mismatch(lines))
        all_conflicts.extend(detect_gst_mismatch(lines))
        all_conflicts.extend(detect_vendor_duplicates(lines))
        all_conflicts.extend(detect_intercompany_inflation(lines, entity_ids))
        all_conflicts.extend(detect_fx_mismatch(lines))
        all_conflicts.extend(detect_cost_center_lag(lines))
        if benchmarks:
            all_conflicts.extend(detect_benchmark_disagreement(benchmarks))
        logger.info(
            '"conflict_resolver_complete total=%d critical=%d high=%d"',
            len(all_conflicts),
            sum(1 for c in all_conflicts if c.severity == "critical"),
            sum(1 for c in all_conflicts if c.severity == "high"),
        )
        return assign_stable_conflict_ids(all_conflicts)

    def summary(
        self,
        conflicts: List[ConflictRecord],
        user_actions: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Return a structured summary suitable for API responses."""
        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        for c in conflicts:
            by_type[c.conflict_type] = by_type.get(c.conflict_type, 0) + 1
            by_severity[c.severity] = by_severity.get(c.severity, 0) + 1

        enriched = [
            apply_user_action_overlay(enrich_conflict_for_display(c), user_actions)
            for c in conflicts
        ]

        return {
            "total": len(conflicts),
            "by_type": by_type,
            "by_severity": by_severity,
            "unresolved": sum(1 for c in enriched if not c.get("resolved")),
            "auto_resolvable": sum(
                1 for c in enriched
                if c.get("can_auto_apply")
            ),
            "requires_escalation": sum(
                1 for c in enriched
                if c.get("requires_manual_review") and not c.get("resolved")
            ),
            "conflicts": enriched,
        }
