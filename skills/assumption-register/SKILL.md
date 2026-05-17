---
name: assumption-register
description: "Build a per-initiative assumption register with P10/P50/P90 ranges using five construction methods. Used by AssumptionQualityScore gate to gate Gate-2 promotion."
version: "1.0"
status: active
llm_required: false
band_ceiling: "B2"
---

# Assumption Register

Builds and maintains a structured register of savings assumptions per initiative.

## What This Skill Does

1. Receives the initiative list from `savings-modeler`.
2. Constructs P10/P50/P90 ranges for each initiative using the selected method.
3. Attaches metadata: source_class, validation_date, owner_name, owner_sign_off.
4. Returns a register queryable by `AssumptionQualityScore` in `app/opar/quality.py`.

## P10/P50/P90 Construction Methods

| Method | Description |
|--------|-------------|
| `three_point` | PERT/triangular: pessimistic (60% of mid), most likely, optimistic (150% of mid) |
| `historical` | Derived from spend coefficient of variation across GL lines |
| `peer_disp` | Uses peer distribution spread from benchmark dataset |
| `mc` | Monte Carlo — 1,000 Gaussian draws, σ = 25% of mid |
| `expert` | Point estimate provided by SME; P10/P90 = ±25% |

## AssumptionQualityScore Components

| Component | Weight | Notes |
|-----------|--------|-------|
| source_class | 25% | peer_validated=1.0 … unknown=0.25 |
| validation_age | 25% | Linear decay 0→365 days: 1.0→0.20 |
| owner_sign_off | 25% | Boolean: yes=1.0, no=0.50 |
| range_plausibility | 25% | P50 within 2 SD of peer distribution |

**Gate-2 threshold: composite ≥ 0.65**  
Below threshold → Gate-2 blocked until CFO override recorded.

## Output Schema

```json
{
  "register": [
    {
      "initiative_id": "logistics",
      "category_name": "Logistics",
      "p10": 1200000,
      "p50": 2000000,
      "p90": 3100000,
      "pert_mean": 2050000,
      "method": "three_point",
      "source_class": "expert_estimate",
      "owner_sign_off": false,
      "validation_date": null
    }
  ],
  "initiative_count": 5,
  "method": "three_point",
  "p10_total": 0,
  "p50_total": 0,
  "p90_total": 0,
  "summary": "5 initiative(s) registered using three_point method; portfolio P50 = X."
}
```

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | full  | Fully deterministic |
| M2   | full  | Same algorithm |
| M3   | full  | Same algorithm |
