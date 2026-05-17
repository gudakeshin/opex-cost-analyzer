# Chart Builder

Build finance-grade visualizations from skill outputs using an FP&A decision lens.

## Purpose

Generate the most decision-useful chart view for spend profiling and produce concise commentary that explains where spend concentration and optimization headroom exist.

## Inputs

- `spend-profiler` output (required)
- Optional context from user message/intent

## Output Contract

Return JSON with:

- `selected_charts`: list of selected chart patterns and why they were chosen
- `commentary_points`: 3-6 concise insights tied to chart evidence
- `chart_url`: export URL for the rendered chart view

## FP&A Selection Heuristics

1. If category distribution is concentrated (top-3 share is high), prefer a Pareto chart (bars + cumulative share).
2. If addressable spend is present, include an addressability bridge view (addressable vs non-addressable by category).
3. If period trend data exists, include a trend panel for recent spend direction.
4. Prioritize charts that support decision questions:
   - Where is spend concentrated?
   - Where is addressable value highest?
   - Is spend trajectory improving or worsening?

## Style Rules

- Use the app’s visual theme colors and typography hierarchy.
- Keep labels readable and CFO-friendly.
- Do not add decorative charts without decision value.
