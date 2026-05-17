"""B1–B4 data band classification.

B1 — Public          : industry-level aggregates, anonymised benchmarks, published rates
B2 — Confidential    : company-level totals and category spend without supplier attribution
B3 — Restricted      : supplier names, GL codes, cost-centre IDs, GSTIN (business linkable)
B4 — PII / Regulated : person names, email, phone, PAN, Aadhaar — subject to data-protection law
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class DataBand(str, Enum):
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    B4 = "B4"

    def __lt__(self, other: "DataBand") -> bool:  # type: ignore[override]
        _ORDER = {DataBand.B1: 1, DataBand.B2: 2, DataBand.B3: 3, DataBand.B4: 4}
        return _ORDER[self] < _ORDER[other]

    def __le__(self, other: "DataBand") -> bool:  # type: ignore[override]
        return self == other or self < other


# Fields on NormalizedSpendLine that, if non-empty, push the record to at least B3
_B3_FIELDS = frozenset({
    "supplier", "gstin", "gl_code", "cost_center_id", "legal_entity_id",
})

# Fields that push a record to B4 if non-empty (PII indicators)
_B4_FIELDS = frozenset({
    "employee_id", "person_name", "email", "phone",
})


def classify_spend_line(record: Dict[str, Any]) -> DataBand:
    """Return the highest (most sensitive) band for a single spend-line dict."""
    for field in _B4_FIELDS:
        if record.get(field):
            return DataBand.B4

    for field in _B3_FIELDS:
        if record.get(field):
            return DataBand.B3

    amount = record.get("amount") or record.get("amount_reporting")
    if amount is not None:
        return DataBand.B2

    return DataBand.B1


def classify_aggregate(
    rows: List[Dict[str, Any]],
    *,
    k_threshold: int = 5,
) -> Tuple[DataBand, str]:
    """Classify an aggregate (e.g. category total) under k-anonymity rules.

    Returns (band, reason).  If the aggregate is derived from fewer than
    k_threshold source rows, individual re-identification risk is too high —
    the aggregate is promoted to B3 regardless of apparent field content.
    """
    if len(rows) < k_threshold:
        return (
            DataBand.B3,
            f"k-anonymity: only {len(rows)} source rows (threshold {k_threshold}); "
            "aggregate promoted to B3 to prevent re-identification.",
        )
    row_bands = [classify_spend_line(r) for r in rows]
    worst = max(row_bands, key=lambda b: list(DataBand).index(b))
    reason = f"Derived from {len(rows)} rows; worst source band = {worst.value}"
    return worst, reason


def classify_output_block(
    block: Dict[str, Any],
    *,
    source_row_count: Optional[int] = None,
    k_threshold: int = 5,
) -> Tuple[DataBand, str]:
    """Classify a skill-output block (e.g. a spend-profiler category row).

    The block is assumed to be an aggregate.  If source_row_count is supplied
    and is below k_threshold, the result is promoted to B3.
    """
    if source_row_count is not None and source_row_count < k_threshold:
        return (
            DataBand.B3,
            f"Aggregate has only {source_row_count} source rows (k < {k_threshold}); promoted to B3.",
        )
    # Look for supplier-level detail in the block itself
    if block.get("top_suppliers") or block.get("supplier"):
        return DataBand.B3, "Block contains supplier-level detail → B3."
    if block.get("spend") or block.get("total_spend"):
        return DataBand.B2, "Company-level spend aggregate → B2."
    return DataBand.B1, "No sensitive fields detected → B1."


def redact_for_band(record: Dict[str, Any], target_band: DataBand) -> Dict[str, Any]:
    """Return a copy of record with fields above target_band redacted to '[REDACTED]'."""
    out = dict(record)
    if target_band <= DataBand.B2:
        for f in _B3_FIELDS:
            if f in out:
                out[f] = "[REDACTED]"
    if target_band <= DataBand.B1:
        for key in ("amount", "amount_reporting", "spend"):
            if key in out:
                out[key] = None
    return out
