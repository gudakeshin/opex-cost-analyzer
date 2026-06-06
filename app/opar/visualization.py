"""Dynamic chart-spec builder for chat responses.

The LLM only *selects* which chart(s) best answer the user's question (chart type +
which dataset); every number in the rendered chart comes from skill outputs, so nothing
is hallucinated. When the LLM is unavailable or times out, a deterministic keyword
heuristic picks the most relevant dataset(s) instead.

Flow:
    validated skill outputs --build_chart_catalog--> [dataset descriptors with real data]
    user question + catalog  --suggest_charts_llm--> [{dataset_id, type, title, rationale}]
    suggestions + catalog    --resolve_chart_specs--> [ChartSpec]  (returned to the chat UI)

Each ``ChartSpec`` is render-agnostic (see ``frontend .../DynamicChart.tsx``):
    {id, type, title, rationale, x_key, x_label, y_label, unit, series, data, source_skill}
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List

# Palette mirrors frontend SpendCharts.tsx so backend-chosen colors match the theme.
_GREEN = "#86BC25"
_GRAY = "#53565A"
_GRAY_LIGHT = "#BBBCBC"
_NAVY = "#2C5282"
_AMBER = "#D97706"

_ALLOWED_TYPES = {
    "bar",
    "hbar",
    "line",
    "stacked_bar",
    "grouped_bar",
    "pie",
    "waterfall",
    "scatter",
}

_MAX_CHARTS = 3
_MAX_ROWS = 10  # cap rows per chart for legibility


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _label_of(row: Dict[str, Any]) -> str:
    return str(row.get("category_name") or row.get("category_id") or "—")


# ---------------------------------------------------------------------------
# Per-skill dataset builders — each returns 0+ dataset descriptors with REAL data.
# ---------------------------------------------------------------------------

def _spend_datasets(profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    cats = profile.get("category_profile") or []
    cats = sorted(cats, key=lambda c: _num(c.get("spend")), reverse=True)[:_MAX_ROWS]
    out: List[Dict[str, Any]] = []

    if cats:
        out.append({
            "dataset_id": "spend_by_category",
            "source_skill": "spend-profiler",
            "label": "Spend by category",
            "default_type": "hbar",
            "allowed_types": ["hbar", "bar", "pie"],
            "x_key": "label", "x_label": "Category", "y_label": "Spend",
            "unit": "currency",
            "series": [{"key": "spend", "name": "Spend", "color": _GREEN}],
            "data": [{"label": _label_of(c), "spend": round(_num(c.get("spend")), 2)} for c in cats],
            "hint_keywords": [
                "spend", "category", "categories", "where", "biggest", "largest",
                "concentration", "pareto", "top", "breakdown", "split", "how much",
            ],
        })

        addr_rows = [{
            "label": _label_of(c),
            "addressable": round(_num(c.get("addressable_spend")), 2),
            "semi_variable": round(_num(c.get("semi_variable_spend")), 2),
            "fixed": round(_num(c.get("fixed_spend")), 2),
        } for c in cats]
        if any(r["addressable"] or r["semi_variable"] or r["fixed"] for r in addr_rows):
            out.append({
                "dataset_id": "addressability_split",
                "source_skill": "spend-profiler",
                "label": "Addressable vs fixed / semi-variable spend",
                "default_type": "stacked_bar",
                "allowed_types": ["stacked_bar", "grouped_bar"],
                "x_key": "label", "x_label": "Category", "y_label": "Spend",
                "unit": "currency",
                "series": [
                    {"key": "addressable", "name": "Addressable", "color": _GREEN},
                    {"key": "semi_variable", "name": "Semi-variable", "color": _GRAY},
                    {"key": "fixed", "name": "Fixed", "color": _GRAY_LIGHT},
                ],
                "data": addr_rows,
                "hint_keywords": [
                    "addressable", "fixed", "variable", "cut", "reduce", "reducible",
                    "optimi", "lever", "levers", "what can we", "flex",
                ],
            })

    trend = profile.get("trend_analysis") or {}
    period_totals = trend.get("period_totals") if isinstance(trend, dict) else None
    if isinstance(period_totals, dict) and len(period_totals) >= 2:
        rows = [{"period": str(p), "spend": round(_num(v), 2)} for p, v in sorted(period_totals.items())]
        out.append({
            "dataset_id": "spend_trend",
            "source_skill": "spend-profiler",
            "label": "Total spend over time",
            "default_type": "line",
            "allowed_types": ["line", "bar"],
            "x_key": "period", "x_label": "Period", "y_label": "Spend",
            "unit": "currency",
            "series": [{"key": "spend", "name": "Total spend", "color": _GREEN}],
            "data": rows,
            "hint_keywords": [
                "trend", "over time", "trajectory", "run rate", "run-rate",
                "month", "period", "momentum", "history", "trending",
            ],
        })
    return out


def _temporal_datasets(temporal: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not temporal.get("temporal_available"):
        return []
    out: List[Dict[str, Any]] = []

    yoy_rows = [
        {"period": str(p.get("period")), "yoy_pct": _num(p.get("yoy_pct"))}
        for p in (temporal.get("period_trends") or [])
        if p.get("yoy_pct") is not None
    ]
    if len(yoy_rows) >= 1:
        out.append({
            "dataset_id": "yoy_growth",
            "source_skill": "temporal-analyzer",
            "label": "Year-over-year spend growth",
            "default_type": "bar",
            "allowed_types": ["bar", "line"],
            "x_key": "period", "x_label": "Period", "y_label": "YoY change",
            "unit": "percent",
            "series": [{"key": "yoy_pct", "name": "YoY %", "color": _NAVY}],
            "data": yoy_rows,
            "hint_keywords": [
                "yoy", "year over year", "year-on-year", "growth", "increase",
                "vs last year", "inflation", "rising",
            ],
        })

    movers = sorted(
        temporal.get("category_trends") or [],
        key=lambda c: abs(_num(c.get("total_change"))),
        reverse=True,
    )[:_MAX_ROWS]
    mover_rows = [{"label": _label_of(c), "change": round(_num(c.get("total_change")), 2)} for c in movers]
    if any(r["change"] for r in mover_rows):
        out.append({
            "dataset_id": "category_movers",
            "source_skill": "temporal-analyzer",
            "label": "Biggest category movers (change in spend)",
            "default_type": "hbar",
            "allowed_types": ["hbar", "bar"],
            "x_key": "label", "x_label": "Category", "y_label": "Change in spend",
            "unit": "currency",
            "series": [{"key": "change", "name": "Change", "color": _AMBER}],
            "data": mover_rows,
            "hint_keywords": [
                "movers", "moving", "changed", "biggest change", "rising", "falling",
                "decline", "increase", "drivers of growth",
            ],
        })
    return out


def _bva_datasets(bva: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not bva.get("bva_available"):
        return []
    variances = sorted(
        bva.get("variances") or [],
        key=lambda v: abs(_num(v.get("total_variance"))),
        reverse=True,
    )[:_MAX_ROWS]
    if not variances:
        return []
    out: List[Dict[str, Any]] = [{
        "dataset_id": "bva_actual_vs_budget",
        "source_skill": "bva-analyzer",
        "label": "Actual vs budget by category",
        "default_type": "grouped_bar",
        "allowed_types": ["grouped_bar", "bar"],
        "x_key": "label", "x_label": "Category", "y_label": "Spend",
        "unit": "currency",
        "series": [
            {"key": "actual", "name": "Actual", "color": _GREEN},
            {"key": "budget", "name": "Budget", "color": _GRAY},
        ],
        "data": [{
            "label": _label_of(v),
            "actual": round(_num(v.get("actual_spend")), 2),
            "budget": round(_num(v.get("budget_spend")), 2),
        } for v in variances],
        "hint_keywords": [
            "budget", "actual", "variance", "plan", "vs budget", "over budget",
            "under budget", "bva", "overrun", "forecast",
        ],
    }]

    # Budget -> Actual variance bridge (waterfall): anchored totals + per-category deltas.
    bridge: List[Dict[str, Any]] = [{
        "label": "Budget", "value": round(_num(bva.get("total_budget")), 2), "is_total": True,
    }]
    bridge += [{"label": _label_of(v), "value": round(_num(v.get("total_variance")), 2)} for v in variances]
    bridge.append({
        "label": "Actual", "value": round(_num(bva.get("total_actual")), 2), "is_total": True,
    })
    out.append({
        "dataset_id": "bva_variance_bridge",
        "source_skill": "bva-analyzer",
        "label": "Budget-to-actual variance bridge",
        "default_type": "waterfall",
        "allowed_types": ["waterfall"],
        "x_key": "label", "x_label": "Category", "y_label": "Variance",
        "unit": "currency",
        "series": [{"key": "value", "name": "Variance", "color": _GREEN}],
        "data": bridge,
        "hint_keywords": ["bridge", "variance bridge", "walk", "budget to actual", "variance"],
    })
    return out


def _peer_datasets(peer: Dict[str, Any]) -> List[Dict[str, Any]]:
    comps = peer.get("comparisons") or []
    rows = [{
        "label": _label_of(c),
        "actual": round(_num(c.get("actual_pct_of_revenue")), 2),
        "benchmark": round(_num(c.get("benchmark_target_pct")), 2),
    } for c in comps if _num(c.get("actual_pct_of_revenue")) > 0]
    rows.sort(key=lambda r: r["actual"] - r["benchmark"], reverse=True)
    rows = rows[:_MAX_ROWS]
    if not rows:
        return []
    return [{
        "dataset_id": "peer_vs_benchmark",
        "source_skill": "peer-benchmarker",
        "label": "Spend vs peer benchmark (% of revenue)",
        "default_type": "grouped_bar",
        "allowed_types": ["grouped_bar", "bar"],
        "x_key": "label", "x_label": "Category", "y_label": "% of revenue",
        "unit": "percent",
        "series": [
            {"key": "actual", "name": "Actual", "color": _GREEN},
            {"key": "benchmark", "name": "Peer target (P25)", "color": _GRAY},
        ],
        "data": rows,
        "hint_keywords": [
            "peer", "peers", "benchmark", "percentile", "compare", "comparison",
            "vs peers", "above market", "best in class", "best-in-class", "quartile",
        ],
    }]


def _savings_datasets(model: Dict[str, Any]) -> List[Dict[str, Any]]:
    inits = sorted(
        model.get("initiatives") or [],
        key=lambda i: _num((i.get("net_savings") or {}).get("total_3yr")),
        reverse=True,
    )[:_MAX_ROWS]
    if not inits:
        return []

    def _name(i: Dict[str, Any]) -> str:
        return str(i.get("lever_name") or i.get("category_name") or i.get("lever") or "Initiative")

    out: List[Dict[str, Any]] = [{
        "dataset_id": "savings_waterfall",
        "source_skill": "savings-modeler",
        "label": "3-year net savings build-up by initiative",
        "default_type": "waterfall",
        "allowed_types": ["waterfall", "bar"],
        "x_key": "label", "x_label": "Initiative", "y_label": "Net savings (3-yr)",
        "unit": "currency",
        "series": [{"key": "value", "name": "Net savings", "color": _GREEN}],
        "data": [{"label": _name(i), "value": round(_num((i.get("net_savings") or {}).get("total_3yr")), 2)} for i in inits],
        "hint_keywords": [
            "save", "savings", "opportunity", "value", "prioriti", "biggest savings",
            "where can we save", "reduce cost", "initiatives", "levers",
        ],
    }, {
        "dataset_id": "savings_net_vs_cost",
        "source_skill": "savings-modeler",
        "label": "Net savings vs cost-to-achieve",
        "default_type": "grouped_bar",
        "allowed_types": ["grouped_bar", "bar"],
        "x_key": "label", "x_label": "Initiative", "y_label": "3-yr value",
        "unit": "currency",
        "series": [
            {"key": "net", "name": "Net savings (3-yr)", "color": _GREEN},
            {"key": "cost", "name": "Cost to achieve", "color": _AMBER},
        ],
        "data": [{
            "label": _name(i),
            "net": round(_num((i.get("net_savings") or {}).get("total_3yr")), 2),
            "cost": round(_num((i.get("cost_to_achieve") or {}).get("total_3yr")), 2),
        } for i in inits],
        "hint_keywords": ["cost to achieve", "investment", "net savings", "roi", "return", "payback"],
    }]

    payback_rows = [{"label": _name(i), "payback": _num(i.get("payback_months"))} for i in inits if _num(i.get("payback_months")) > 0]
    if payback_rows:
        out.append({
            "dataset_id": "savings_payback",
            "source_skill": "savings-modeler",
            "label": "Payback period by initiative",
            "default_type": "hbar",
            "allowed_types": ["hbar", "bar"],
            "x_key": "label", "x_label": "Initiative", "y_label": "Payback (months)",
            "unit": "count",
            "series": [{"key": "payback", "name": "Months to payback", "color": _NAVY}],
            "data": payback_rows,
            "hint_keywords": ["payback", "how long", "time to value", "months to recover"],
        })
    return out


def _value_bridge_datasets(vb: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    bands = vb.get("confidence_bands") or {}
    low, mid, high = _num(bands.get("low")), _num(bands.get("mid")), _num(bands.get("high"))
    if mid > 0 or high > 0:
        out.append({
            "dataset_id": "savings_confidence_bands",
            "source_skill": "value-bridge-calculator",
            "label": "Savings opportunity — confidence range",
            "default_type": "bar",
            "allowed_types": ["bar"],
            "x_key": "label", "x_label": "Scenario", "y_label": "Savings",
            "unit": "currency",
            "series": [{"key": "amount", "name": "Savings", "color": _GREEN}],
            "data": [
                {"label": "Low", "amount": round(low, 2)},
                {"label": "Mid", "amount": round(mid, 2)},
                {"label": "High", "amount": round(high, 2)},
            ],
            "hint_keywords": [
                "confidence", "range", "low high", "sensitivity", "scenario",
                "best case", "worst case", "conservative", "how confident",
            ],
        })

    matrix = sorted(
        vb.get("value_matrix") or [],
        key=lambda r: _num(r.get("deduped_mid_savings")),
        reverse=True,
    )[:_MAX_ROWS]
    rows = [{"label": _label_of(r), "savings": round(_num(r.get("deduped_mid_savings")), 2)} for r in matrix]
    if any(r["savings"] for r in rows):
        out.append({
            "dataset_id": "savings_by_category",
            "source_skill": "value-bridge-calculator",
            "label": "Modeled savings by category",
            "default_type": "hbar",
            "allowed_types": ["hbar", "bar", "pie"],
            "x_key": "label", "x_label": "Category", "y_label": "Savings",
            "unit": "currency",
            "series": [{"key": "savings", "name": "Modeled savings", "color": _GREEN}],
            "data": rows,
            "hint_keywords": ["savings by category", "where are the savings", "opportunity by category"],
        })
    return out


def _payment_terms_datasets(pt: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not pt.get("payment_terms_available"):
        return []
    opps = sorted(
        pt.get("opportunities") or [],
        key=lambda o: _num(o.get("working_capital_release")),
        reverse=True,
    )[:_MAX_ROWS]
    if not opps:
        return []
    return [{
        "dataset_id": "dpo_gap",
        "source_skill": "payment-terms-optimizer",
        "label": "Payment terms — current vs target DPO",
        "default_type": "grouped_bar",
        "allowed_types": ["grouped_bar", "bar"],
        "x_key": "label", "x_label": "Category", "y_label": "Days payable (DPO)",
        "unit": "days",
        "series": [
            {"key": "current", "name": "Current DPO", "color": _GRAY},
            {"key": "target", "name": "Target DPO", "color": _GREEN},
        ],
        "data": [{
            "label": _label_of(o),
            "current": round(_num(o.get("current_dpo_days")), 1),
            "target": round(_num(o.get("target_dpo_days")), 1),
        } for o in opps],
        "hint_keywords": [
            "dpo", "payment terms", "working capital", "cash", "days payable",
            "terms", "supplier terms", "free up cash", "liquidity",
        ],
    }]


def _root_cause_datasets(rc: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings = rc.get("root_cause_findings") or []
    rows: List[Dict[str, Any]] = []
    for f in findings:
        magnitude = sum(_num(c.get("addressable_spend")) for c in (f.get("root_causes") or []))
        rows.append({"label": _label_of(f), "magnitude": round(magnitude, 2)})
    rows.sort(key=lambda r: r["magnitude"], reverse=True)
    rows = [r for r in rows if r["magnitude"] > 0][:_MAX_ROWS]
    if not rows:
        return []
    return [{
        "dataset_id": "root_cause_ranking",
        "source_skill": "root-cause-analyzer",
        "label": "Addressable spend by root-cause category",
        "default_type": "hbar",
        "allowed_types": ["hbar", "bar"],
        "x_key": "label", "x_label": "Category", "y_label": "Addressable spend",
        "unit": "currency",
        "series": [{"key": "magnitude", "name": "Addressable spend", "color": _GREEN}],
        "data": rows,
        "hint_keywords": [
            "root cause", "why", "driver", "drivers", "cause", "reason",
            "what's driving", "what is driving", "diagnose",
        ],
    }]


_CATALOG_BUILDERS: List[tuple[str, Callable[[Dict[str, Any]], List[Dict[str, Any]]]]] = [
    ("spend-profiler", _spend_datasets),
    ("temporal-analyzer", _temporal_datasets),
    ("bva-analyzer", _bva_datasets),
    ("peer-benchmarker", _peer_datasets),
    ("savings-modeler", _savings_datasets),
    ("value-bridge-calculator", _value_bridge_datasets),
    ("payment-terms-optimizer", _payment_terms_datasets),
    ("root-cause-analyzer", _root_cause_datasets),
]


def build_chart_catalog(validated: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Enumerate render-ready datasets (with real numbers) from whichever skills ran."""
    catalog: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for skill, builder in _CATALOG_BUILDERS:
        out = (validated or {}).get(skill)
        if not isinstance(out, dict):
            continue
        try:
            datasets = builder(out)
        except Exception:
            continue
        for ds in datasets:
            if ds and ds.get("data") and ds.get("dataset_id") not in seen:
                catalog.append(ds)
                seen.add(ds["dataset_id"])
    return catalog


# ---------------------------------------------------------------------------
# LLM selection (type + dataset only) with a deterministic keyword fallback.
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a data-visualization advisor for an OpEx cost-analysis platform. "
    "Given the user's question and the datasets available from the analysis, pick the "
    "1-3 charts that best answer the question. Prefer the most decision-relevant view. "
    "Respond with JSON only — no prose, no markdown fence."
)


def _catalog_for_prompt(catalog: List[Dict[str, Any]]) -> str:
    lines = []
    for ds in catalog:
        sample = ds["data"][:2]
        lines.append(
            f"- {ds['dataset_id']}: {ds['label']} "
            f"(source={ds['source_skill']}, default_type={ds['default_type']}, "
            f"allowed_types={ds['allowed_types']}, unit={ds['unit']}, rows={len(ds['data'])}, "
            f"sample={sample})"
        )
    return "\n".join(lines)


def suggest_charts_llm(user_message: str, catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]] | None:
    """Ask Claude to choose dataset + chart type. Returns selections or None on any failure."""
    try:
        from app.opar.claude_client import ANTHROPIC_ENABLED, _call_claude, _extract_json
    except Exception:
        return None
    if not ANTHROPIC_ENABLED or not catalog:
        return None

    user_prompt = (
        f"User question: {user_message}\n\n"
        f"Available datasets:\n{_catalog_for_prompt(catalog)}\n\n"
        "Choose 1-3 charts that best answer the question. For each chart output an object "
        "{dataset_id, type, title, rationale}. The dataset_id MUST be one of the ids above and "
        "the type MUST be one of that dataset's allowed_types. 'title' is a short chart title; "
        "'rationale' is one sentence on why this chart answers the question. Order by relevance.\n"
        'Output JSON only: {"charts": [{"dataset_id": "...", "type": "...", "title": "...", "rationale": "..."}]}'
    )

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_call_claude, _SYSTEM_PROMPT, user_prompt, 600)
    try:
        raw = future.result(timeout=10)
    except Exception:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        return None
    finally:
        if not future.cancelled():
            executor.shutdown(wait=True, cancel_futures=True)

    try:
        data = _extract_json(raw)
    except Exception:
        return None
    charts = data.get("charts") if isinstance(data, dict) else None
    if not isinstance(charts, list):
        return None

    by_id = {ds["dataset_id"]: ds for ds in catalog}
    cleaned: List[Dict[str, Any]] = []
    for c in charts:
        if not isinstance(c, dict):
            continue
        ds = by_id.get(c.get("dataset_id"))
        if not ds:
            continue
        ctype = c.get("type")
        if ctype not in ds["allowed_types"] or ctype not in _ALLOWED_TYPES:
            ctype = ds["default_type"]
        cleaned.append({
            "dataset_id": ds["dataset_id"],
            "type": ctype,
            "title": str(c.get("title") or ds["label"]).strip()[:120],
            "rationale": str(c.get("rationale") or "").strip()[:240],
        })
        if len(cleaned) >= _MAX_CHARTS:
            break
    return cleaned or None


def suggest_charts_fallback(user_message: str, catalog: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic keyword heuristic used when the LLM is unavailable."""
    msg = (user_message or "").lower()
    scored = []
    for idx, ds in enumerate(catalog):
        score = sum(1 for kw in ds.get("hint_keywords", []) if kw in msg)
        scored.append((score, -idx, ds))  # -idx keeps catalog priority order on ties
    scored.sort(reverse=True)

    if not scored:
        return []
    top_score = scored[0][0]
    if top_score == 0:
        # Nothing matched — show the single most universally relevant view.
        chosen = [scored[0][2]]
    else:
        chosen = [ds for sc, _, ds in scored if sc > 0][:_MAX_CHARTS]

    return [{
        "dataset_id": ds["dataset_id"],
        "type": ds["default_type"],
        "title": ds["label"],
        "rationale": "",
    } for ds in chosen]


def resolve_chart_specs(
    suggestions: List[Dict[str, Any]],
    catalog: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Join each selection to its dataset's real data, producing render-ready ChartSpecs."""
    by_id = {ds["dataset_id"]: ds for ds in catalog}
    specs: List[Dict[str, Any]] = []
    for s in suggestions:
        ds = by_id.get(s.get("dataset_id"))
        if not ds:
            continue
        specs.append({
            "id": ds["dataset_id"],
            "type": s.get("type") or ds["default_type"],
            "title": s.get("title") or ds["label"],
            "rationale": s.get("rationale") or "",
            "x_key": ds["x_key"],
            "x_label": ds["x_label"],
            "y_label": ds["y_label"],
            "unit": ds["unit"],
            "series": ds["series"],
            "data": ds["data"],
            "source_skill": ds["source_skill"],
        })
    return specs


def build_chart_specs(user_message: str, validated: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Entry point: produce LLM-suggested, data-backed ChartSpecs for a chat answer.

    Fully guarded — returns ``[]`` rather than raising if anything goes wrong.
    """
    try:
        catalog = build_chart_catalog(validated or {})
    except Exception:
        return []
    if not catalog:
        return []

    suggestions = None
    try:
        suggestions = suggest_charts_llm(user_message, catalog)
    except Exception:
        suggestions = None
    if not suggestions:
        suggestions = suggest_charts_fallback(user_message, catalog)

    try:
        return resolve_chart_specs(suggestions, catalog)
    except Exception:
        return []
