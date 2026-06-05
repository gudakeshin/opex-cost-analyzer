from __future__ import annotations

from typing import Any, Dict, List

from app.models import NormalizedSpendLine


def build_transaction_examples_from_lines(
    lines: List[NormalizedSpendLine],
    max_categories: int = 8,
    max_examples_per_category: int = 3,
) -> Dict[str, list[Dict[str, Any]]]:
    """Compact per-category spend examples for narrative grounding."""
    grouped: Dict[str, List[NormalizedSpendLine]] = {}
    for line in lines:
        grouped.setdefault(line.category_id, []).append(line)

    out: Dict[str, list[Dict[str, Any]]] = {}
    for category_id, cat_lines in grouped.items():
        top = sorted(
            cat_lines,
            key=lambda x: float(x.amount or 0.0),
            reverse=True,
        )[:max_examples_per_category]
        out[category_id] = [
            {
                "supplier": x.supplier,
                "description": x.description,
                "amount": float(x.amount or 0.0),
                "business_unit": x.business_unit,
                "geo": x.geo,
                "spend_date": x.spend_date,
            }
            for x in top
        ]

    limited = sorted(
        out.items(),
        key=lambda kv: sum(e["amount"] for e in kv[1]),
        reverse=True,
    )[:max_categories]
    return dict(limited)
