"""Deterministic spend fixture for LLM golden-set evals (no live LLM)."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.models import NormalizedSpendLine
from app.services.spend_store import SpendStore, write_document_spend_lines

GOLDEN_ENGAGEMENT_ID = "eval-golden-llm"
GOLDEN_SESSION_ID = "00000000-0000-4000-8000-000000000001"


def golden_spend_lines() -> List[NormalizedSpendLine]:
    """Fixed 30-line corpus: 3 suppliers × 2 categories × 5 periods."""
    lines: List[NormalizedSpendLine] = []
    row = 1
    suppliers = ["Acme Corp", "Beta LLC", "Gamma Inc"]
    categories = [
        ("CAT_IT", "IT & Technology"),
        ("CAT_FAC", "Facilities"),
    ]
    periods = ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4", "2025-Q1"]
    for si, supplier in enumerate(suppliers):
        for ci, (cat_id, cat_name) in enumerate(categories):
            for pi, period in enumerate(periods):
                amount = 1000.0 * (si + 1) + 100.0 * ci + 10.0 * pi
                lines.append(
                    NormalizedSpendLine(
                        row_id=row,
                        supplier=supplier,
                        description=f"{cat_name} services",
                        amount=amount,
                        category_id=cat_id,
                        category_name=cat_name,
                        business_unit="BU_EAST" if si % 2 == 0 else "BU_WEST",
                        fiscal_period=period,
                        fiscal_year=int(period[:4]),
                        source_record_id=f"r{row}",
                        source_file_hash="golden",
                    )
                )
                row += 1
    return lines


def build_golden_store(tmp_path) -> SpendStore:
    from app.services import spend_store as ss

    ss.ENGAGEMENTS_DIR = tmp_path
    write_document_spend_lines(GOLDEN_ENGAGEMENT_ID, "golden.csv", golden_spend_lines())
    return SpendStore(GOLDEN_ENGAGEMENT_ID)


def rows_fingerprint(rows: List[Dict[str, Any]], keys: List[str] | None = None) -> str:
    """Stable hash of result rows for golden comparison."""
    import hashlib
    import json

    if not rows:
        return "empty"
    if keys is None:
        keys = sorted({k for r in rows for k in r.keys()})
    normalized = []
    for row in rows:
        normalized.append(tuple(str(row.get(k, "")) for k in keys))
    normalized.sort()
    blob = json.dumps(normalized, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def golden_categories() -> List[Dict[str, str]]:
    return [
        {"category_id": "CAT_IT", "category_name": "IT & Technology"},
        {"category_id": "CAT_FAC", "category_name": "Facilities"},
    ]


def minimal_bridge_output() -> Dict[str, Any]:
    return {
        "confidence_bands": {"low": 8_000_000, "mid": 10_000_000, "high": 12_000_000},
        "value_matrix": [],
    }
