"""Plain-language "basis of figures" statements for exported documents.

Exports quote savings and peer gaps to a CFO. This states what those figures assume
(full delivery vs execution-risk-adjusted) and which data caveats apply, so the document
does not look more certain than the analysis is.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.utils.inr_format import format_money


def _ingestion_warnings(analysis: Dict[str, Any]) -> List[str]:
    report = analysis.get("ingestion_report")
    if not isinstance(report, dict):
        return []
    files = report.get("files")
    reports = files if isinstance(files, list) and files else [report]
    out: List[str] = []
    for r in reports:
        if not isinstance(r, dict):
            continue
        for w in r.get("warnings") or []:
            text = str(w).strip()
            if text and text not in out:
                out.append(text)
    return out


def basis_of_figures(analysis: Dict[str, Any]) -> Dict[str, Any]:
    outputs = analysis.get("skill_outputs") or {}
    currency = str(analysis.get("reporting_currency") or "INR")
    summary = (outputs.get("savings-modeler") or {}).get("summary") or {}
    expected = float(summary.get("total_expected_net_3yr") or 0.0)
    full = float(summary.get("total_net_3yr_full_delivery") or 0.0)

    peer = outputs.get("peer-benchmarker") or {}
    caveats: List[str] = [str(w) for w in (peer.get("warnings") or []) if str(w).strip()]
    meta = peer.get("benchmark_metadata") or {}
    if meta.get("is_illustrative") and not any("illustrative" in c.lower() for c in caveats):
        caveats.append("Peer benchmarks are illustrative (no sample behind them); treat peer gaps as directional.")
    for w in _ingestion_warnings(analysis):
        if w not in caveats:
            caveats.append(w)

    return {
        "currency": currency,
        "expected_net_3yr": expected or None,
        "full_delivery_net_3yr": full or None,
        "caveats": caveats,
    }


def basis_lines(basis: Dict[str, Any]) -> List[str]:
    """Human-readable lines, in order; empty when there is nothing worth stating."""
    lines: List[str] = []
    currency = basis.get("currency") or "INR"
    expected, full = basis.get("expected_net_3yr"), basis.get("full_delivery_net_3yr")
    if expected and full:
        lines.append(
            "Headline savings assume every initiative is delivered in full. "
            f"Expected 3-year net savings after execution risk: {format_money(expected, currency)} "
            f"(vs {format_money(full, currency)} if fully delivered)."
        )
    lines.extend(basis.get("caveats") or [])
    return lines
