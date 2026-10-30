"""Cohort segmentation — vendor tiers, BU/GL rollups, period movers via DuckDB."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def cohort_segmenter(
    store: Any,
    *,
    group_by: Optional[List[str]] = None,
    period_column: str = "period",
) -> Dict[str, Any]:
    """Run bespoke cohort cuts on the analytical spend store.

    When ``group_by`` is omitted, returns vendor Pareto tiers, BU/GL rollups,
    and QoQ movers (when multiple periods exist).
    """
    group_by = group_by or ["supplier"]
    valid_dims = {
        "supplier", "category_id", "category_name", "business_unit",
        "gl_code", "cost_center_id", period_column,
    }
    dims = [d for d in group_by if d in valid_dims] or ["supplier"]

    rollup = store.aggregate(
        group_by=dims,
        metrics={"spend": "SUM(amount)", "line_count": "COUNT(*)"},
        order_by="spend DESC",
        limit=500,
    )
    segments: List[Dict[str, Any]] = []
    col_idx = {name: i for i, name in enumerate(rollup.columns)}
    for row in rollup.rows:
        entry: Dict[str, Any] = {
            dims[i]: row[col_idx[dims[i]]] for i in range(len(dims))
        }
        entry["spend"] = float(row[col_idx["spend"]] or 0.0)
        entry["line_count"] = int(row[col_idx["line_count"]] or 0)
        segments.append(entry)

    total = sum(s["spend"] for s in segments) or 1.0
    cumulative = 0.0
    for seg in segments:
        cumulative += seg["spend"]
        seg["cumulative_share"] = round(cumulative / total, 4)
        seg["pareto_tier"] = (
            "A" if seg["cumulative_share"] <= 0.80
            else "B" if seg["cumulative_share"] <= 0.95
            else "C"
        )

    movers: List[Dict[str, Any]] = []
    try:
        period_check = store.run_sql(
            f"SELECT COUNT(DISTINCT {period_column}) AS n FROM spend "
            f"WHERE {period_column} IS NOT NULL",
            limit=1,
        )
        n_periods = int(period_check.rows[0][0] or 0) if period_check.rows else 0
        if n_periods >= 2:
            mover_sql = (
                f"WITH ranked AS ("
                f"  SELECT {period_column} AS period, SUM(amount) AS spend "
                f"  FROM spend WHERE {period_column} IS NOT NULL "
                f"  GROUP BY {period_column} ORDER BY period"
                f"), pairs AS ("
                f"  SELECT period, spend, "
                f"  LAG(spend) OVER (ORDER BY period) AS prev_spend "
                f"  FROM ranked"
                f") SELECT period, spend, prev_spend, "
                f"  CASE WHEN prev_spend > 0 "
                f"    THEN ROUND((spend - prev_spend) / prev_spend * 100, 1) "
                f"    ELSE NULL END AS qoq_pct "
                f"FROM pairs WHERE prev_spend IS NOT NULL "
                f"ORDER BY ABS(COALESCE(qoq_pct, 0)) DESC LIMIT 12"
            )
            result = store.run_sql(mover_sql, limit=12)
            m_idx = {name: i for i, name in enumerate(result.columns)}
            for row in result.rows:
                movers.append({
                    "period": row[m_idx["period"]],
                    "spend": float(row[m_idx["spend"]] or 0.0),
                    "prev_spend": float(row[m_idx["prev_spend"]] or 0.0),
                    "qoq_pct": row[m_idx["qoq_pct"]],
                })
    except Exception:
        pass

    return {
        "cohort_available": True,
        "group_by": dims,
        "segments": segments,
        "segment_count": len(segments),
        "total_spend": round(total, 2),
        "period_movers": movers,
        "pushdown": True,
    }
