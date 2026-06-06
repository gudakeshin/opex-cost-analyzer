"""Shared spend/benchmark context lines for reflect response composition."""
from __future__ import annotations

from typing import Any, Dict, List

from app.opar.reflect_currency import format_currency


def format_spend_profile_line(validated: Dict[str, Dict[str, Any]]) -> str | None:
    profile = validated.get("spend-profiler", {})
    if not profile:
        return None
    return (
        f"Spend profile: {len(profile.get('category_profile', []))} categories, "
        f"total {format_currency(profile.get('total_spend', 0))}."
    )


def format_value_bridge_line(validated: Dict[str, Dict[str, Any]]) -> str | None:
    bridge = validated.get("value-bridge-calculator", {})
    if not isinstance(bridge, dict):
        return None
    bands = bridge.get("confidence_bands", {})
    if not bands:
        return None
    return (
        f"Value bridge: mid-case savings {format_currency(bands.get('mid', 0))} "
        f"(low: {format_currency(bands.get('low', 0))}, high: {format_currency(bands.get('high', 0))})."
    )


def format_benchmark_attribution_line(validated: Dict[str, Dict[str, Any]]) -> str | None:
    peer = validated.get("peer-benchmarker", {})
    if not isinstance(peer, dict):
        return None
    dataset = peer.get("benchmark_dataset", {})
    if not isinstance(dataset, dict) or not dataset:
        return None
    source = dataset.get("source") or "unknown"
    vintage = dataset.get("vintage_date") or "unknown"
    specificity = dataset.get("specificity_score")
    if specificity is None:
        return f"Benchmarked using {source} (vintage {vintage})."
    try:
        spec_pct = f"{float(specificity):.0%}"
    except Exception:
        spec_pct = str(specificity)
    return f"Benchmarked using {source} (vintage {vintage}, specificity {spec_pct})."


def build_analysis_context_lines(validated: Dict[str, Dict[str, Any]]) -> List[str]:
    """Spend profile, value bridge, and benchmark attribution — shared response header."""
    lines: List[str] = []
    for formatter in (format_spend_profile_line, format_value_bridge_line, format_benchmark_attribution_line):
        line = formatter(validated)
        if line:
            lines.append(line)
    return lines
