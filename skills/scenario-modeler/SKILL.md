---
name: scenario-modeler
description: "Build a 6-scenario macro surface (FX stress, wage inflation, commodity spike, execution slip, base case, P90 upside) for the initiative portfolio. Extends app/services/sensitivity.py with macro-driver scenarios."
version: "1.0"
status: active
llm_required: false
band_ceiling: "B2"
---

# Scenario Modeler

Applies macro-driver shocks to the initiative portfolio to produce a range-of-outcomes surface.

## What This Skill Does

1. Takes portfolio base-case savings (from `assumption-register` P50 total or `savings-modeler`).
2. Applies six pre-defined macro scenarios with calibrated impact multipliers.
3. Computes NPV for each scenario using WACC and Section 115BAA tax rate.
4. Returns a macro-sensitivity rating (high / medium / low).

## Scenarios

| ID | Label | Impact Driver | Savings Multiplier |
|----|-------|--------------|-------------------|
| `base` | Base case | — | 1.00× |
| `fx_stress` | FX stress (INR −10%) | FX | 0.88× |
| `wage_inflation` | Wage inflation (+8% YoY) | Wage | 0.88× |
| `commodity_spike` | Commodity spike (+15%) | Commodity | 0.85× |
| `execution_slip` | Execution slip (30% slippage) | Execution | 0.70× |
| `upside` | P90 upside | — | P90 total |

## Output Schema

```json
{
  "scenarios": [
    {
      "scenario_id": "base",
      "label": "Base case",
      "description": "...",
      "savings_impact": 0,
      "npv": 0,
      "driver": null
    }
  ],
  "base_savings": 0,
  "base_npv": 0,
  "p10_savings": 0,
  "p90_savings": 0,
  "downside_floor": 0,
  "downside_floor_pct_of_base": 0.0,
  "macro_sensitivity_rating": "medium",
  "summary": "..."
}
```

## Relationship to sensitivity.py

`app/services/sensitivity.py` (FP&A enhancements) handles driver-based sensitivity
(headcount_growth, revenue_growth, execution_rate).  This skill adds the macro layer:
FX, wage, commodity shocks applied at the portfolio level.  Both can run in the same turn.

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | full  | Deterministic |
| M2   | full  | Same |
| M3   | full  | Same |
