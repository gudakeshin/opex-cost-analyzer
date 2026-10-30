---
name: cohort-segmenter
description: "Segment spend into vendor Pareto tiers (A/B/C), business-unit and GL rollups, and QoQ/YoY movers. Use when the user asks for cohort analysis, vendor tiers, spend segmentation, BU rollups, cost-center cuts, or period-over-period movers on large spend corpora."
---

# Cohort Segmenter

Runs DuckDB aggregations over the analytical spend store for bespoke FDE cuts:

1. **Vendor Pareto tiers** — cumulative spend share buckets (A ≤80%, B ≤95%, C remainder)
2. **Custom rollups** — group by supplier, category, BU, GL, or cost center
3. **Period movers** — QoQ % change when multiple periods exist in the data

Requires the Parquet/DuckDB spend store (large-cap engagements). Set `cohort_group_by` in manifest overrides to customize dimensions.
