"""Merge persisted spend-line adjustments when analysis is re-run from source files."""
from __future__ import annotations

from typing import Dict, List, Tuple

from app.models import NormalizedSpendLine

LineKey = Tuple[str, ...]

_PERSISTED_FIELDS = (
    "consolidation_eliminated",
    "reconciled_amount",
    "conflict_flag",
    "conflict_resolution",
)


def spend_line_key(line: NormalizedSpendLine) -> LineKey:
    if line.source_record_id and line.source_file_hash:
        return ("record", line.source_record_id, line.source_file_hash)
    if line.source_record_id:
        return ("record", line.source_record_id, line.source_system_id or "")
    return (
        "fallback",
        str(line.supplier or "").strip().lower(),
        str(line.description or "").strip().lower(),
        f"{line.amount:.6f}",
        str(line.category_id or ""),
        str(line.spend_date or ""),
        str(line.source_system_id or ""),
    )


def _has_persisted_adjustments(line: NormalizedSpendLine) -> bool:
    if line.consolidation_eliminated:
        return True
    if line.reconciled_amount is not None:
        return True
    return bool(line.conflict_resolution)


def _apply_persisted_fields(
    new_line: NormalizedSpendLine,
    prior_line: NormalizedSpendLine,
) -> NormalizedSpendLine:
    updates: Dict[str, object] = {
        field: getattr(prior_line, field)
        for field in _PERSISTED_FIELDS
        if getattr(prior_line, field) not in (None, False, "")
    }
    if prior_line.conflict_resolution == "gstin_dedup" and prior_line.supplier:
        updates["supplier"] = prior_line.supplier
    if not updates:
        return new_line
    return new_line.model_copy(update=updates)


def merge_persisted_line_adjustments(
    new_lines: List[NormalizedSpendLine],
    prior_lines: List[NormalizedSpendLine],
) -> List[NormalizedSpendLine]:
    """Carry conflict-resolution flags from a prior session onto freshly ingested lines."""
    prior_by_key: Dict[LineKey, NormalizedSpendLine] = {}
    for prior in prior_lines:
        if _has_persisted_adjustments(prior):
            prior_by_key[spend_line_key(prior)] = prior

    if not prior_by_key:
        return new_lines

    merged: List[NormalizedSpendLine] = []
    for line in new_lines:
        prior = prior_by_key.get(spend_line_key(line))
        merged.append(_apply_persisted_fields(line, prior) if prior else line)
    return merged


def prior_lines_from_session(existing: Dict[str, object]) -> List[NormalizedSpendLine]:
    rows: List[NormalizedSpendLine] = []
    for raw in existing.get("normalized_spend") or []:
        if isinstance(raw, dict):
            rows.append(NormalizedSpendLine(**raw))
        elif isinstance(raw, NormalizedSpendLine):
            rows.append(raw)
    return rows
