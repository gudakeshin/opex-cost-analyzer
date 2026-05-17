---
name: value-to-shareholder-bridge
description: "Translate OpEx initiative portfolio savings into shareholder-value metrics: bps EBITDA, ΔROCE, ΔEPS, ΔFCF, ΔEquity value. Uses Section 115BAA effective tax rate by default."
version: "1.0"
status: active
llm_required: false
band_ceiling: "B2"
---

# Value-to-Shareholder Bridge

Converts OpEx savings into the financial language of boards and equity analysts.

## What This Skill Does

1. Aggregates portfolio P50 savings from `assumption-register` or `savings-modeler`.
2. Computes five shareholder-value metrics using client financial parameters.
3. Produces per-initiative attribution so individual levers can be presented on slides.

## Metrics Produced

| Metric | Formula |
|--------|---------|
| ΔEBITDA | = ΔSavings (1:1 pass-through) |
| ΔEBITDA bps | = (ΔEBITDA / Revenue) × 10,000 |
| ΔROCE pp | = (New EBITDA − Old EBITDA) / Capital Employed × 100 |
| ΔEPS (₹/share) | = ΔEBITDA × (1 − 25.17%) / Diluted shares |
| ΔFCF | = ΔPAT × 90% cash conversion |
| ΔEquity value | = ΔPAT × implied P/E |

## Default Assumptions

| Parameter | Default | Override via |
|-----------|---------|--------------|
| Effective tax rate | 25.17% (115BAA) | `effective_tax_rate` arg |
| WACC | 12% | `wacc` arg |
| Cash conversion | 90% | hardcoded |
| Capital employed | 1.2× revenue | `capital_employed` arg (Phase 4) |

## Output Schema

```json
{
  "total_mid_savings": 0,
  "delta_ebitda": 0,
  "delta_ebitda_bps": 0.0,
  "delta_roce_pp": 0.0,
  "delta_eps": 0.0,
  "delta_fcf": 0,
  "delta_equity_value": 0,
  "assumptions": {},
  "per_initiative": [],
  "summary": "Portfolio mid-case savings: X; ΔEBITDA +N bps; ΔROCE +M pp; ΔEPS +P."
}
```

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | full  | Deterministic — no LLM needed |
| M2   | full  | Same algorithm |
| M3   | full  | Same algorithm |
