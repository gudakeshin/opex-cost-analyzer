---
name: zbb-modeler
description: "Build a driver-based zero-based / should-cost model from first principles and quantify the gap between current spend and zero-based targets by category. Use when the user asks about 'zero-based budgeting', 'ZBB', 'should-cost', 'build the budget from scratch', 'first-principles cost', or 'what should this cost'. Uses category drivers from the spend profile and (optionally) revenue/headcount. Powers the zbb intent."
---

# Zero-Based Budget Modeler

You rebuild each cost category from first principles — drivers × unit cost — rather than last year's number plus a percentage, then expose the gap between what is spent and what the activity should cost.

## When to Use

Trigger on: "zero-based", "ZBB", "should-cost", "first principles", "build budget from scratch", "what should this cost", "clean-sheet cost".

## Prerequisites

- A categorized profile from `spend-profiler` (provides category drivers).
- Optionally `annual_revenue` and `headcount` to scale driver-based targets.

## Method

1. For each category, identify the cost driver (headcount, transactions, square footage, revenue share).
2. Apply should-cost unit rates to derive a zero-based target.
3. Compare current spend to the zero-based target; compute the gap and % reduction implied.
4. Rank categories by gap and tag the realisability tier.

## Outputs

- Per-category current spend, zero-based target, gap, and implied reduction %.
- Total zero-based opportunity and the categories driving it.
- Driver assumptions stated explicitly per category.

## Edge Cases

- Missing drivers for a category → mark target as "not modellable" rather than guessing.
- ZBB targets are aspirational — apply a realisability factor before presenting as committed savings.
