"""Shared helpers for incremental connector fetches."""
from __future__ import annotations

from typing import List

from app.models import NormalizedSpendLine


def filter_lines_since(lines: List[NormalizedSpendLine], since: str | None) -> List[NormalizedSpendLine]:
    """Keep lines on or after *since* (ISO date prefix). If no line has dates, return all."""
    if not since:
        return lines
    cutoff = since[:10]
    dated = [ln for ln in lines if (ln.spend_date or "")[:10] >= cutoff]
    return dated if dated else lines
