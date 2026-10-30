"""Check that money figures quoted in a narrative trace back to skill outputs.

Informational only: a figure that matches nothing may be a legitimate derived value
(a sum, a ratio) or an LLM invention, so callers should surface it as "unverified",
not as an error.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from typing import Any, Dict, List

_SCALES = {
    "crore": 1e7, "cr": 1e7,
    "lakh": 1e5, "lac": 1e5, "l": 1e5,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "million": 1e6, "mn": 1e6, "m": 1e6,
    "k": 1e3,
}

# Amounts introduced by a currency symbol (any unit), or a number with an unambiguous unit word.
_FIGURE_RE = re.compile(
    r"""
    (?:(?P<sym>[₹$€£])\s?(?P<n1>\d[\d,]*(?:\.\d+)?)\s?(?P<u1>crore|cr|lakh|lac|billion|bn|million|mn|[lkmb])?(?![A-Za-z]))
    |
    (?:(?<![\w.])(?P<n2>\d[\d,]*(?:\.\d+)?)\s?(?P<u2>crore|cr|lakh|lacs?|billion|bn|million|mn)(?![A-Za-z]))
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _numbers(obj: Any, out: List[float], depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if obj == obj and abs(obj) >= 1:
            out.append(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numbers(v, out, depth + 1)


def _parse(match: "re.Match[str]") -> tuple[float, float] | None:
    """Return (absolute value, rounding tolerance) for one matched figure."""
    raw = match.group("n1") or match.group("n2")
    unit = (match.group("u1") or match.group("u2") or "").lower()
    scale = _SCALES.get(unit, 1.0)
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    half_unit = 0.5 * (10 ** -decimals) * scale
    return value * scale, max(half_unit * 1.01, value * scale * 0.005)


def find_unverified_figures(text: str, skill_outputs: Dict[str, Any], limit: int = 10) -> List[str]:
    """Money figures in ``text`` that match no number in ``skill_outputs`` (within display rounding)."""
    if not text or not skill_outputs:
        return []
    pool: List[float] = []
    _numbers(skill_outputs, pool)
    if not pool:
        return []
    pool.sort()

    unverified: List[str] = []
    seen: set[str] = set()
    for m in _FIGURE_RE.finditer(text):
        parsed = _parse(m)
        if parsed is None:
            continue
        value, tol = parsed
        if value < 1000:  # small standalone numbers are ordinary counts, not money claims
            continue
        i = bisect_left(pool, value - tol)
        if i < len(pool) and pool[i] <= value + tol:
            continue
        shown = m.group(0).strip()
        if shown not in seen:
            seen.add(shown)
            unverified.append(shown)
            if len(unverified) >= limit:
                break
    return unverified
