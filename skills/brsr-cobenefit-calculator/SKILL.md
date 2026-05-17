---
name: brsr-cobenefit-calculator
description: "Map every OpEx initiative to a BRSR principle (P1–P9) and estimate ΔScope-2, ΔScope-3, Δwater, Δwaste co-benefits. Required for SEBI BRSR Core disclosures (mandatory FY26 for top-1000 listed companies)."
version: "1.0"
status: active
llm_required: false
band_ceiling: "B2"
---

# BRSR Co-Benefit Calculator

Links OpEx savings to SEBI Business Responsibility and Sustainability Report (BRSR) principles.

## What This Skill Does

1. Maps each initiative category to the most relevant BRSR principle.
2. Applies default emission/resource-intensity factors to compute environmental co-benefits.
3. Aggregates portfolio-level ΔScope-2, ΔScope-3, Δwater, Δwaste.
4. Returns line-item attribution for inclusion in the BRSR Core disclosure.

## BRSR Principles Mapped

| Principle | Theme | OpEx Categories |
|-----------|-------|----------------|
| P1 | Ethics & Transparency | Professional services, IT, Legal |
| P6 | Environment | Energy, Logistics, Facilities, Manufacturing, Travel |
| P8 | Inclusive growth | HR, Training, Community |

## Emission Intensity Defaults (generic — replace with client actuals)

| Factor | Value | Unit |
|--------|-------|------|
| Scope-2 (energy/utilities) | 0.45 | tCO₂e / ₹ Cr saved |
| Scope-3 (logistics/travel) | 0.28 | tCO₂e / ₹ Cr saved |
| Water (facilities) | 18.0 | kL / ₹ Cr saved |
| Waste (manufacturing) | 0.12 | tonnes / ₹ Cr saved |

## Output Schema

```json
{
  "cobenefit_items": [
    {
      "initiative_id": "logistics",
      "category_name": "Logistics",
      "brsr_principle": "P6",
      "delta_scope2_tco2e": 0.0,
      "delta_scope3_tco2e": 12.5,
      "delta_water_kl": 0.0,
      "delta_waste_tonnes": 0.0,
      "cobenefit_note": "..."
    }
  ],
  "portfolio_totals": {
    "delta_scope2_tco2e": 0,
    "delta_scope3_tco2e": 0,
    "delta_water_kl": 0,
    "delta_waste_tonnes": 0
  },
  "brsr_principles_addressed": ["P1", "P6"],
  "emission_factors": {},
  "summary": "..."
}
```

## Regulatory Context

SEBI Circular SEBI/HO/CFD/CMD-2/P/CIR/2023/122 mandates BRSR Core for top-1000 listed
companies from FY2024-25. Co-benefit estimates from this skill feed directly into the
Principle 6 disclosures (Scope-2 intensity, Scope-3, water intensity, waste generated).

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | full  | Deterministic |
| M2   | full  | Same |
| M3   | full  | Same |
