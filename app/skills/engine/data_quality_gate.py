"""Lightweight data-quality gate — runs after spend-profiler on every analysis."""
from __future__ import annotations

from typing import Any, Dict, List

from app.models import NormalizedSpendLine, is_actual


def data_quality_gate(
    lines: List[NormalizedSpendLine],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Check coverage, period completeness, outliers, and category mapping."""
    actual = [x for x in lines if is_actual(x) and x.in_spend_base]
    if not actual:
        actual = [x for x in lines if x.in_spend_base]

    total_lines = len(actual)
    if total_lines == 0:
        return {
            "confidence": "low",
            "passed": False,
            "checks": {"has_data": False},
            "caveats": ["No spend lines available for quality assessment."],
            "coverage_score": 0.0,
        }

    key_fields = ("supplier", "category_id", "category_name", "amount")
    populated = sum(
        1
        for line in actual
        if all(getattr(line, f, None) for f in key_fields)
    )
    coverage_score = round(populated / total_lines, 4)

    with_period = sum(
        1 for line in actual if line.fiscal_period or line.spend_date
    )
    period_coverage = round(with_period / total_lines, 4)
    distinct_periods = (
        profile.get("trend_analysis", {}).get("distinct_periods", [])
        if isinstance(profile.get("trend_analysis"), dict)
        else []
    )

    amounts = [abs(line.effective_reporting_amount) for line in actual if line.effective_reporting_amount]
    outlier_count = 0
    if amounts:
        mean_amt = sum(amounts) / len(amounts)
        threshold = mean_amt * 5 if mean_amt > 0 else 0.0
        if threshold > 0:
            outlier_count = sum(1 for a in amounts if a > threshold)

    unmapped = sum(
        1
        for line in actual
        if not (line.category_id and line.category_name)
        or str(line.category_id).upper() in ("UNKNOWN", "UNMAPPED", "")
    )
    mapping_score = round(1.0 - (unmapped / total_lines), 4)

    checks = {
        "has_data": total_lines > 0,
        "coverage_ok": coverage_score >= 0.85,
        "period_coverage_ok": period_coverage >= 0.5 or len(distinct_periods) >= 2,
        "mapping_ok": mapping_score >= 0.9,
        "outliers_bounded": outlier_count <= max(3, int(total_lines * 0.02)),
    }
    passed = all(checks.values())

    caveats: List[str] = []
    if coverage_score < 0.85:
        caveats.append(
            f"Field coverage is {coverage_score:.0%} — some supplier/category fields are missing."
        )
    if period_coverage < 0.5 and len(distinct_periods) < 2:
        caveats.append(
            "Period coverage is thin — trend and BvA analyses may be unreliable."
        )
    if mapping_score < 0.9:
        caveats.append(
            f"{unmapped} line(s) lack reliable category mapping."
        )
    if outlier_count > max(3, int(total_lines * 0.02)):
        caveats.append(
            f"{outlier_count} outlier transaction(s) detected — review before committing savings."
        )

    if passed:
        confidence = "high" if coverage_score >= 0.95 else "mid"
    elif coverage_score >= 0.7:
        confidence = "mid"
    else:
        confidence = "low"

    return {
        "confidence": confidence,
        "passed": passed,
        "checks": checks,
        "caveats": caveats,
        "coverage_score": coverage_score,
        "period_coverage": period_coverage,
        "mapping_score": mapping_score,
        "outlier_count": outlier_count,
        "line_count": total_lines,
    }
