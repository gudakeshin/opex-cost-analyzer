"""Layer 3: Counterfactual signal injection and prioritization scoring.

Usage pattern
-------------
1. Start with a set of baseline spend lines (e.g. from a CSV fixture).
2. Call inject_signal() to embed a known high-priority overrun.
3. Run the relevant skills (bva_analyzer, spend_profiler, etc.).
4. Call score_prioritization() to verify the platform surfaced the signal.

This is fully deterministic — no LLM required for the basic scoring path.
An optional LLM prominence score is gated behind pytest.mark.llm_judge.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from app.models import NormalizedSpendLine


# ---------------------------------------------------------------------------
# Signal specification
# ---------------------------------------------------------------------------

@dataclass
class SignalSpec:
    """Describes a high-priority signal to inject into a spend dataset.

    Attributes:
        supplier:           Supplier name used for the injected lines.
        category_id:        Category that will carry the overrun.
        signal_amount:      Actual spend amount (the inflated value).
        baseline_amount:    Normal/budget amount for this supplier.
        signal_type:        "overrun" | "spike" | "new_vendor"
        spend_date:         Date string (YYYY-MM-DD) for the injected lines.
        gl_code:            Optional GL code on the injected lines.
        cost_center_id:     Optional cost-center on the injected lines.
    """
    supplier: str
    category_id: str
    signal_amount: float
    baseline_amount: float
    signal_type: str = "overrun"
    spend_date: str = "2025-01-15"
    gl_code: str = ""
    cost_center_id: str = ""


# ---------------------------------------------------------------------------
# Injection
# ---------------------------------------------------------------------------

def inject_signal(
    base_lines: List[NormalizedSpendLine],
    signal: SignalSpec,
    include_budget_line: bool = True,
) -> List[NormalizedSpendLine]:
    """Return a new list of lines with the signal injected.

    Appends:
      - One "actual" line at signal_amount
      - (Optionally) one "budget" line at baseline_amount for BvA contrast
    """
    injected = list(base_lines)

    # Derive a human-readable category name from the category_id
    category_name = signal.category_id.replace("_", " ").title()

    actual_line = NormalizedSpendLine(
        row_id=hash(f"signal_actual_{signal.supplier}") % 10_000_000,
        supplier=signal.supplier,
        description=f"{signal.supplier} {signal.signal_type} signal",
        category_id=signal.category_id,
        category_name=category_name,
        amount=signal.signal_amount,
        spend_date=signal.spend_date,
        amount_type="actual",
        gl_code=signal.gl_code or None,
        cost_center_id=signal.cost_center_id or None,
        currency="USD",
        fx_rate_to_reporting=1.0,
        amount_reporting=signal.signal_amount,
    )
    injected.append(actual_line)

    if include_budget_line:
        budget_line = NormalizedSpendLine(
            row_id=hash(f"signal_budget_{signal.supplier}") % 10_000_000,
            supplier=signal.supplier,
            description=f"{signal.supplier} budget",
            category_id=signal.category_id,
            category_name=category_name,
            amount=signal.baseline_amount,
            spend_date=signal.spend_date,
            amount_type="budget",
            gl_code=signal.gl_code or None,
            cost_center_id=signal.cost_center_id or None,
            currency="USD",
            fx_rate_to_reporting=1.0,
            amount_reporting=signal.baseline_amount,
        )
        injected.append(budget_line)

    return injected


# ---------------------------------------------------------------------------
# Prioritization scoring (deterministic)
# ---------------------------------------------------------------------------

@dataclass
class PrioritizationResult:
    signal_surfaced: bool
    mention_count: int = 0
    prominence_score: float = 0.0  # 0-1; 1 = mentioned prominently / first
    details: str = ""


def score_prioritization(
    response_text: str,
    signal: SignalSpec,
    bva_output: Optional[dict] = None,
) -> PrioritizationResult:
    """Deterministically check whether the signal was surfaced.

    Checks:
    1. Keyword presence — supplier name or category_id in response_text.
    2. BvA rank — if bva_output is provided, checks signal category ranks
       in the top-3 variances by absolute delta.

    Returns a PrioritizationResult with signal_surfaced=True if either check passes.
    """
    text_lower = response_text.lower()
    supplier_lower = signal.supplier.lower()
    category_lower = signal.category_id.lower()

    # Keyword match
    mention_count = text_lower.count(supplier_lower) + text_lower.count(category_lower)
    keyword_found = mention_count > 0

    # BvA rank check — engine uses "variances" key with "total_variance" per row
    bva_rank: Optional[int] = None
    if bva_output and bva_output.get("bva_available"):
        variances = bva_output.get("variances", bva_output.get("category_variances", []))
        sorted_vars = sorted(
            variances,
            key=lambda v: abs(v.get("total_variance", v.get("variance_amount", 0.0))),
            reverse=True,
        )
        for rank, var in enumerate(sorted_vars, start=1):
            if var.get("category_id", "").lower() == category_lower:
                bva_rank = rank
                break

    bva_top3 = bva_rank is not None and bva_rank <= 3

    signal_surfaced = keyword_found or bva_top3

    # Prominence: 1.0 if supplier appears in first 20% of text
    prominence = 0.0
    if keyword_found:
        first_pos = text_lower.find(supplier_lower)
        if first_pos == -1:
            first_pos = text_lower.find(category_lower)
        prominence = max(0.0, 1.0 - (first_pos / max(len(text_lower), 1)))

    details_parts = []
    if keyword_found:
        details_parts.append(f"keyword found {mention_count}x in response_text")
    if bva_rank is not None:
        details_parts.append(f"BvA rank #{bva_rank}")

    return PrioritizationResult(
        signal_surfaced=signal_surfaced,
        mention_count=mention_count,
        prominence_score=round(prominence, 3),
        details="; ".join(details_parts) if details_parts else "signal not found",
    )


# ---------------------------------------------------------------------------
# Convenience: build noise lines around a signal
# ---------------------------------------------------------------------------

def build_noise_lines(
    n: int = 5,
    base_amount: float = 5_000.0,
    spend_date: str = "2025-01-15",
) -> List[NormalizedSpendLine]:
    """Generate n small noise spend lines in distinct categories."""
    noise = []
    for i in range(n):
        noise.append(NormalizedSpendLine(
            row_id=9_000_000 + i,
            supplier=f"noise_vendor_{i}",
            description=f"Noise line {i}",
            category_id=f"noise_cat_{i}",
            category_name=f"Noise Category {i}",
            amount=base_amount * (0.8 + 0.4 * (i / max(n - 1, 1))),
            spend_date=spend_date,
            amount_type="actual",
            currency="USD",
            fx_rate_to_reporting=1.0,
            amount_reporting=base_amount,
        ))
    return noise
