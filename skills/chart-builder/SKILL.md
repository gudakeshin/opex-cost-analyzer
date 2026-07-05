---
name: chart-builder
description: "Build finance-grade spend visualizations from spend-profiler output using FP&A chart-selection heuristics (Pareto, addressability bridge, trend panels). Use when the user asks for 'charts', 'visualize spend', 'Pareto of categories', or a shareable chart URL alongside profiling results. Runs deterministically on categorized spend — no interactive chart authoring."
kind: output
runtime: python
discoverable: true
weight: light
version: "0.1.0"
status: active
---

# Chart Builder

Selects decision-useful chart patterns from spend profile data and renders an HTML chart export.

## Inputs

- `spend-profiler` — category_profile, trend_analysis, addressability fields (required).
- Optional: user_message for intent hints (passed to chart selection heuristics).

## Output Contract

- `selected_charts` — list of chart patterns chosen and rationale.
- `commentary_points` — 3–6 CFO-facing insights tied to chart evidence.
- `chart_url` — path/URL to rendered HTML chart file for the session.

## Methodology

1. **Load spend profile** — from prior_results or on-demand spend_profiler run.
2. **Plan charts** — `chart_builder()` applies FP&A heuristics: Pareto when top-3 concentration is high, addressability bridge when addressable spend exists, trend panel when period data exists.
3. **Render HTML** — `build_spend_profile_chart_html()` writes session-scoped HTML using platform theme.
4. **Return plan + URL** — JSON dict for dashboard-builder and export-formatter consumption.

Implementation: `app/skills/dispatch.py` → `engine.chart_builder()` + `app/services/spend_charts.py`.

## FP&A Selection Heuristics

1. If category distribution is concentrated (top-3 share is high), prefer a Pareto chart (bars + cumulative share).
2. If addressable spend is present, include an addressability bridge view (addressable vs non-addressable by category).
3. If period trend data exists, include a trend panel for recent spend direction.
4. Prioritize charts that support decision questions: concentration, addressable value, spend trajectory.
