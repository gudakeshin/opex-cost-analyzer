"""Shared spend-store schema metadata for query tools and agent context."""
from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

from app.models import NormalizedSpendLine
from app.services.spend_store import _EXTRA_COLUMNS

if TYPE_CHECKING:
    from app.services.spend_store import SpendStore

# Dimensions surfaced in GET /schema sample_values — keep in sync with query router.
SAMPLE_DIMENSIONS = (
    "category_name",
    "supplier",
    "business_unit",
    "gl_code",
    "cost_center_id",
    "fiscal_period",
    "fiscal_year",
)

QUERYABLE_VIEWS: Dict[str, str] = {
    "spend": "Effective spend lines (reconciled amounts applied, eliminated lines excluded)",
    "spend_raw": "As-ingested lines, including eliminated ones",
    "adjustments": "Line-level conflict/consolidation adjustments",
}

# Columns most often used in NL queries — full list available via schema endpoint.
COMMON_QUERY_COLUMNS = (
    "supplier",
    "category_id",
    "category_name",
    "amount",
    "amount_reporting",
    "fiscal_period",
    "fiscal_year",
    "business_unit",
    "geo",
    "gl_code",
    "cost_center_id",
    "currency",
    "description",
    "spend_type",
    "is_addressable",
    "document_id",
    "line_key",
)


def all_spend_column_names() -> List[str]:
    """Column names in spend_raw / spend views (model fields + store extras)."""
    return list(NormalizedSpendLine.model_fields.keys()) + list(_EXTRA_COLUMNS)


def spend_schema_description() -> str:
    """One-line column summary for agent tool descriptions."""
    cols = ", ".join(COMMON_QUERY_COLUMNS)
    return (
        f"Queryable DuckDB view `spend`. Key columns: {cols}. "
        f"Use fiscal_period (not period) for time bucketing. "
        f"Views: {', '.join(QUERYABLE_VIEWS)}."
    )


def load_spend_schema(store: "SpendStore") -> Dict[str, Any]:
    """Build schema payload matching GET /api/v1/query/{session_id}/schema."""
    with store.connect_readonly() as con:
        columns = [
            {"name": r[0], "type": r[1]}
            for r in con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'spend_raw' ORDER BY ordinal_position"
            ).fetchall()
        ]
        samples: Dict[str, list] = {}
        valid = {c["name"] for c in columns}
        for dim in SAMPLE_DIMENSIONS:
            if dim not in valid:
                continue
            rows = con.execute(
                f"SELECT {dim}, COUNT(*) AS n FROM spend WHERE {dim} IS NOT NULL "
                f"GROUP BY {dim} ORDER BY n DESC LIMIT 15"
            ).fetchall()
            samples[dim] = [r[0] for r in rows]
        total = con.execute("SELECT COUNT(*), SUM(amount) FROM spend").fetchone()
    return {
        "views": dict(QUERYABLE_VIEWS),
        "columns": columns,
        "sample_values": samples,
        "line_count": int(total[0] or 0),
        "total_spend": float(total[1] or 0.0),
    }


def compact_schema_for_agent(schema: Dict[str, Any]) -> str:
    """Compact schema block for agent system prompt injection."""
    col_names = [c["name"] for c in schema.get("columns", [])]
    lines = [
        "Spend store schema (DuckDB view `spend`):",
        f"  line_count={schema.get('line_count', 0)}, total_spend={schema.get('total_spend', 0):.2f}",
        f"  columns ({len(col_names)}): {', '.join(col_names[:40])}"
        + (" …" if len(col_names) > 40 else ""),
    ]
    samples = schema.get("sample_values") or {}
    for dim, values in list(samples.items())[:6]:
        preview = ", ".join(str(v) for v in values[:8])
        lines.append(f"  sample {dim}: {preview}")
    lines.append(
        "  Note: use fiscal_period / fiscal_year for periods; reconciled amounts are in view `spend`."
    )
    return "\n".join(lines)


NL_QUERY_ROUTING_EXAMPLES = """
NL query routing examples (prefer natural_language_query over raw SQL):
- "How does IT spend compare to peers?" → tier skill (get_benchmarks / peer-benchmarker)
- "Profile spend concentration" → tier skill (spend-profiler)
- "Vendor Pareto tiers" → tier skill (cohort-segmenter)
- "Top 10 suppliers in Facilities by business unit" → tier aggregate
- "QoQ movers where spend grew more than 20%" → tier sql (or cohort-segmenter)
""".strip()
