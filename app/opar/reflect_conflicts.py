"""Reflect conflict formatting — cross-source TDS/GST/vendor conflict responses."""
from __future__ import annotations

from typing import Any, Dict

from app.opar.reflect_currency import format_currency

_CONFLICT_TYPE_LABELS: Dict[str, str] = {
    "tds_mismatch": "TDS mismatch",
    "gst_mismatch": "GST mismatch",
    "vendor_duplicate": "Duplicate vendor (GSTIN/name)",
    "intercompany_inflation": "Intercompany inflation",
    "fx_mismatch": "FX rate mismatch",
    "benchmark_disagreement": "Benchmark disagreement",
    "amount_mismatch": "Amount mismatch across sources",
    "cost_center_lag": "Cost centre mapping lag",
}

def format_conflict_line(conflict: Dict[str, Any]) -> str:
    ctype = str(conflict.get("conflict_type") or "unknown")
    label = _CONFLICT_TYPE_LABELS.get(ctype, ctype.replace("_", " ").title())
    severity = str(conflict.get("severity") or "medium")
    source_a = conflict.get("source_a") or "source A"
    source_b = conflict.get("source_b") or "source B"
    parts = [f"**{label}** ({severity}): {source_a} vs {source_b}"]
    amount_a = conflict.get("amount_a")
    amount_b = conflict.get("amount_b")
    if amount_a is not None and amount_b is not None:
        parts.append(
            f"amounts {format_currency(float(amount_a))} vs {format_currency(float(amount_b))}"
        )
    delta = conflict.get("delta_pct")
    if delta is not None:
        try:
            parts.append(f"delta {float(delta):+.1f}%")
        except (TypeError, ValueError):
            pass
    notes = conflict.get("resolution_notes")
    if notes:
        parts.append(str(notes))
    return "- " + " — ".join(parts)


def format_conflict_detection_response(conflict_data: Dict[str, Any]) -> str:
    total = int(conflict_data.get("conflict_count") or conflict_data.get("total") or 0)
    unresolved = int(conflict_data.get("unresolved") or 0)
    by_type = conflict_data.get("by_type") or {}
    conflicts = conflict_data.get("conflicts") or []

    if total <= 0:
        return (
            "**Cross-source check complete** — no TDS, GST, or vendor conflicts detected "
            "across the uploaded sources in this session."
        )

    lines = [
        f"**Cross-source conflicts: {total} found**"
        + (f" ({unresolved} unresolved)" if unresolved else ""),
    ]
    if by_type:
        type_bits = [
            f"{_CONFLICT_TYPE_LABELS.get(k, k.replace('_', ' '))}: {v}"
            for k, v in sorted(by_type.items(), key=lambda x: -x[1])
        ]
        lines.append("By type: " + "; ".join(type_bits) + ".")
    lines.append("")
    lines.append("**Findings**")
    for conflict in conflicts[:12]:
        if isinstance(conflict, dict):
            lines.append(format_conflict_line(conflict))
    if len(conflicts) > 12:
        lines.append(f"- …and {len(conflicts) - 12} more (open Cost Room or ask to resolve).")
    auto = int(conflict_data.get("auto_resolvable") or 0)
    escalate = int(conflict_data.get("requires_escalation") or 0)
    if auto or escalate:
        lines.append("")
        lines.append(
            f"Resolution: {auto} auto-resolvable, {escalate} need controller/CFO review."
        )
    return "\n".join(lines)
