---
name: cost-to-serve-analyzer
description: "Analyse cost-to-serve by segment, surface per-employee and per-unit cost drivers, and identify unprofitable segments where allocated OpEx exceeds segment revenue. Use when the user asks 'cost to serve', 'which segments are unprofitable', 'per-employee cost', 'cost per customer/transaction', 'segment profitability', or supplies segment revenue. Powers the cost_to_serve intent and the /api/v1/cost-to-serve endpoint."
---

# Cost-to-Serve Analyzer

You attribute operating spend to the segments it serves and reveal where the cost of serving a segment outruns the revenue it returns.

## When to Use

Trigger on: "cost to serve", "segment profitability", "per-employee cost", "cost per customer/transaction", "unprofitable segments", "where are we losing money to serve".

## Prerequisites

- A categorized profile from `spend-profiler`.
- Drivers: `annual_revenue`, `headcount`, and optionally `segment_revenue` per segment.

## Method

1. Allocate OpEx to segments using available drivers (headcount, revenue share, transaction volume).
2. Compute per-employee and per-unit cost ratios.
3. Where `segment_revenue` is provided, compute segment OpEx-to-revenue and margin.
4. Flag segments where allocated cost-to-serve exceeds segment revenue.

## Outputs

- Per-segment cost-to-serve, per-employee cost, and (if available) margin.
- Ranked list of unprofitable / high-cost-to-serve segments.
- Top per-unit cost drivers.

## Edge Cases

- No segment revenue → report cost-to-serve and ratios only; skip profitability verdicts.
- Zero headcount/revenue drivers → skip the affected ratios rather than divide by zero.
