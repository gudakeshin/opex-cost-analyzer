# Heuristics Improvement Plan
**Date:** June 2026 | **Linked to:** `heuristics_evaluation.md`

Organised into three phases by effort and dependency order. Each item names the exact file(s) to change, what to change, and the acceptance test.

---

## Phase 1 — Config & Data Changes (No Logic Edits Required)
*Target: 1–2 days. Pure JSON/YAML edits. Zero regression risk.*

---

### P1-A: Populate `effort_weeks` and `applicability_threshold_pct` on all sector levers

**Why it matters:** These two null fields block the effort-vs-impact matrix that opens every consulting deck.

**Files:**
```
skills/sector-packs/*/sector_levers.json   (one per sector pack)
```

**What to add to each lever entry:**
```json
"effort_weeks": { "p10": 6, "p50": 12, "p90": 20 },
"applicability_threshold_pct": 0.05
```

`effort_weeks` = implementation weeks P10/P50/P90 — use `model_parameters.json → levers.<lever_id>.implementation_weeks` as the source where it exists; populate the remaining from the table below.

`applicability_threshold_pct` = minimum category spend (as % of total OpEx) below which the lever isn't worth running. Use 2% for low-effort levers (payment_terms, maverick_compliance), 5% for standard, 10% for high-effort transformational levers (shared_services_center, geographic_arbitrage).

**Reference defaults by lever family:**

| Lever family | effort p50 (weeks) | applicability_threshold_pct |
|---|---|---|
| supply (contract renegotiation, supplier consolidation) | 14 | 0.05 |
| process (standardization, automation, P2P) | 20 | 0.05 |
| demand (demand management, maverick compliance) | 10 | 0.03 |
| structural (shared services, geographic arbitrage) | 36 | 0.10 |
| compliance (GST ITC, MSME, payment terms) | 8 | 0.02 |

**Acceptance test:** `run_regression_test(pack_id)` must pass `lever_playbook_fields` check — it already validates that `execution_playbook`, `diagnostic_signals`, and `required_data_fields` are non-empty; add `effort_weeks` and `applicability_threshold_pct` to its check list (see P2-B).

---

### P1-B: Add graduated maverick spend severity to `diagnostic_thresholds.json`

**File:** `skills/root-cause-analyzer/references/diagnostic_thresholds.json`

**Replace** the single `maverick_spend_ratio_min` entry with a tiered structure:

```json
"maverick_spend_tiers": {
  "warning":  { "value": 0.15, "label": "Elevated", "narrative": "15–25% maverick — compliance programme recommended" },
  "elevated": { "value": 0.25, "label": "Significant", "narrative": "25–40% maverick — P2P controls and approval workflow required" },
  "critical": { "value": 0.40, "label": "Critical", "narrative": ">40% maverick — spend visibility gap; baseline unreliable" },
  "best_in_class": { "value": 0.05, "label": "World-class target", "source": "Hackett Group AP Benchmarking 2024" },
  "source_type": "internal_calibration",
  "rationale": "Graduated tiers based on Hackett world-class (<5%), average (15%), and poor (>25%) thresholds. 40% critical flag = baseline integrity risk."
}
```

Keep the existing `maverick_spend_ratio_min: 0.20` in place during transition (root-cause-analyzer reads it by key).

---

### P1-C: Add minimum addressable spend gate to HHI fragmentation threshold

**File:** `skills/root-cause-analyzer/references/diagnostic_thresholds.json`

Add alongside existing `supplier_fragmentation_hhi_max`:

```json
"supplier_fragmentation_min_spend": {
  "value": 50000000,
  "currency": "reporting",
  "note": "₹5 Crore (or equivalent in reporting currency) — categories below this floor are excluded from fragmentation flagging regardless of HHI, to avoid noise initiatives in executive dashboards.",
  "source_type": "internal_calibration"
}
```

---

## Phase 2 — Logic Changes (Targeted, Contained)
*Target: 3–5 days. Each item is self-contained — no cross-item dependencies.*

---

### P2-A: Wire `bounce_back_risk` per lever into the bounce-back scenario

**File:** `app/services/sensitivity.py`

**Problem:** `bounce_back_reversion_rate` is a global scalar (0.80). Lever-level `bounce_back_risk: high/medium/low` is computed in `savings.py` and stored in each initiative dict but never read here.

**Change:** Replace the global reversion rate with a per-initiative lookup:

```python
# Add at top of compute_sensitivity():
BOUNCE_BACK_RATES = {"high": 0.80, "medium": 0.40, "low": 0.15}

# In the bounce_back scenario block, replace:
#   y3_reversion = float(gs.get("y3", 0.0)) * bounce_back_reversion_rate
# With:
for init in savings_model["initiatives"]:
    bbr = BOUNCE_BACK_RATES.get(init.get("bounce_back_risk", "medium"), 0.40)
    y3_reversion = float(gs.get("y3", 0.0)) * bbr
```

Also expose `BOUNCE_BACK_RATES` as an override-able entry in `model_parameters.json → defaults → bounce_back_rates_by_risk`.

**Acceptance test:** With an initiative portfolio containing one `bounce_back_risk: high` and one `bounce_back_risk: low`, the bounce-back scenario NPV should fall between the global-rate result and the no-reversion result — not equal to either.

---

### P2-B: Use `base_execution_probability` per lever in scenario generation

**File:** `app/services/sensitivity.py`

**Problem:** Scenarios apply a single `execution_rate_pct` global override. Each initiative in `savings_model` already carries `base_execution_probability` (computed from lever meta + org-change-risk haircut in `savings.py` lines 136–137).

**Change:** In the conservative and accelerated scenario blocks, weight savings by initiative-level probability rather than the global scalar:

```python
# New helper (add before compute_sensitivity):
def _portfolio_execution_weighted_savings(initiatives, global_exec_rate):
    """Weight each initiative's savings by its own base_execution_probability,
    then apply the global_exec_rate as a portfolio-level multiplier."""
    total = 0.0
    for init in initiatives:
        bep = float(init.get("base_execution_probability", 0.70))
        net = float(init.get("net_savings", {}).get("total_3yr", 0.0))
        total += net * bep
    return total * global_exec_rate
```

Use this in the `conservative` and `accelerated` scenario savings computation. Keep the existing simple path when `savings_model` is absent.

**Acceptance test:** Portfolio with high-confidence contract renegotiation (bep=0.85) + low-confidence demand management (bep=0.40) should produce a conservative scenario savings noticeably lower than `mid × 0.60` when the portfolio is demand-management-heavy.

---

### P2-C: Make confidence bands a function of sustainability and specificity

**File:** `app/skills/engine/savings.py`, function `value_bridge_calculator`

**Problem:** `low_factor: 0.8` and `high_factor: 1.2` are applied uniformly (lines 356–357 and 375–376). Signed contracts carry the same uncertainty as behavioural levers.

**Change:** Compute per-initiative band factors from `sustainability_score` and then apply:

```python
def _band_factors(sustainability_score: float, benchmark_specificity: float = 0.70) -> tuple[float, float]:
    """
    Lower sustainability → wider bands (less confident the saving will hold).
    Lower benchmark specificity → wider bands (less confident the baseline is right).
    
    Base: low=0.80, high=1.20 at sustainability=0.65, specificity=0.70
    Range: low narrows to 0.90 at sust=1.0; widens to 0.65 at sust=0.0
           high narrows to 1.10 at sust=1.0; widens to 1.40 at sust=0.0
    """
    sust_adj = 0.25 * (0.65 - sustainability_score)   # positive = riskier
    spec_adj = 0.15 * (0.70 - benchmark_specificity)   # positive = less specific data
    low = max(0.60, 0.80 - sust_adj - spec_adj)
    high = min(1.50, 1.20 + sust_adj + spec_adj)
    return round(low, 3), round(high, 3)
```

Fetch `benchmark_specificity` from `manifest.get("benchmark_specificity_score", 0.70)` — the benchmark selection logic already stores this. Apply per-initiative in the `savings_model` path; apply category-level average in the raw-rows fallback path.

**Acceptance test:** `contract_renegotiation` (sustainability 0.40, signed contract → specificity 0.90) should produce tighter bands than `demand_management` (sustainability 0.25, seed data → specificity 0.55).

---

### P2-D: Add EBITDA margin impact framing to initiative and pipeline outputs

**File:** `app/skills/engine/savings.py` (initiative dict construction ~line 230), `app/routers/pipeline.py` (`pipeline_summary`)

**Problem:** Annual revenue is in the session manifest. No output surfaces basis-point framing.

**Change 1 — per initiative:** Add to `initiative_dict` (after existing `net_savings` block):

```python
annual_revenue = float(manifest.get("annual_revenue") or 0.0)
ebitda_bps = round((run_rate_savings / annual_revenue) * 10000, 1) if annual_revenue else None

initiative_dict["ebitda_impact"] = {
    "run_rate_savings_annualized": round(run_rate_savings, 2),
    "ebitda_bps": ebitda_bps,
    "ebitda_bps_label": f"{ebitda_bps} bps" if ebitda_bps is not None else "N/A",
    "revenue_base_used": round(annual_revenue, 0),
}
```

**Change 2 — pipeline summary:** In `app/services/pipeline.py`, `pipeline_summary()`, add:

```python
total_run_rate = sum(i.get("annualized_run_rate_savings", 0.0) for i in initiatives)
annual_revenue = ...   # pull from session or engagement store
summary["portfolio_ebitda_impact_bps"] = round((total_run_rate / annual_revenue) * 10000, 1) if annual_revenue else None
```

**Acceptance test:** For a company with ₹2,000 Cr revenue and a ₹50 Cr initiative, `ebitda_bps` = 250.0.

---

### P2-E: Add horizon classification to each initiative

**File:** `app/skills/engine/savings.py` (initiative dict construction)

**Problem:** `phasing_curves` in `model_parameters.json` implicitly encode delivery speed. `payment_terms: [1.0, 0.0, 0.0]` = Year 1 fully captured; `shared_services_center: [0.05, 0.35, 0.60]` = multi-year. Nothing classifies these as quick-win vs transformation.

**Change:** Add a `horizon` classifier derived from phasing curve and payback months:

```python
def _classify_horizon(phasing_curve: list, payback_months: int, effort_weeks_p50: int | None) -> str:
    """
    tactical:        ≥60% savings in Y1 OR payback < 6 months
    structural:      20–60% in Y1, payback 6–18 months  
    transformational:<20% savings in Y1 OR payback > 18 months
    """
    y1_pct = phasing_curve[0] if phasing_curve else 0.25
    if y1_pct >= 0.60 or payback_months < 6:
        return "tactical"
    elif y1_pct >= 0.20 and payback_months <= 18:
        return "structural"
    else:
        return "transformational"

initiative_dict["horizon"] = _classify_horizon(curve, payback_months, lv_meta.get("effort_weeks", {}).get("p50"))
```

Also expose `horizon_summary` in `pipeline_summary()`:
```python
from collections import Counter
horizon_counts = Counter(i.get("horizon", "structural") for i in initiatives)
summary["horizon_summary"] = dict(horizon_counts)
```

**Acceptance test:** `payment_terms` initiatives → `tactical`. `shared_services_center` initiatives → `transformational`. `contract_renegotiation` → `structural`.

---

### P2-F: Add regulatory risk scenario to sensitivity analysis

**File:** `app/services/sensitivity.py`, function `compute_sensitivity`

**Problem:** India-specific regulatory changes (GST ITC disallowance, MSME payment mandate, TDS rate changes) can eliminate or delay entire initiative categories. No scenario models this.

**Change:** Add an 8th scenario after the bounce-back entry:

```python
# Regulatory risk: India-specific. GST ITC levers (gst_itc_recovery) and MSME
# payment levers are zeroed. Remaining categories take a 10% reduction for
# compliance overhead on negotiations.
regulatory_impacted_levers = {"gst_itc_recovery", "msme_payment_compliance", "bank_fee_optimization"}
if savings_model and savings_model.get("initiatives"):
    reg_savings = sum(
        float(i.get("net_savings", {}).get("total_3yr", 0.0))
        for i in savings_model["initiatives"]
        if i.get("lever") not in regulatory_impacted_levers
    ) * 0.90   # 10% compliance overhead haircut on remainder
else:
    reg_savings = mid * 0.82  # fallback: ~18% portfolio at risk from regulatory exposure

scenarios.append({
    "name": "regulatory_headwind",
    "key_assumption": (
        "GST ITC rule change or MSME payment mandate enforcement eliminates compliance-linked levers; "
        "remaining categories take 10% overhead haircut for regulatory compliance cost."
    ),
    "savings_3yr": round(reg_savings, 2),
    "timeline_months": int(36 * timeline_factor),
    "npv_pretax": round(_simple_npv(reg_savings, 3.0 * timeline_factor, 0.0), 2),
    "npv_aftertax": round(_simple_npv(reg_savings, 3.0 * timeline_factor, effective_tax_rate), 2),
    "execution_rate": base_exec,
    "driver_adjusted": False,
    "regulatory_warning": True,
})
```

---

## Phase 3 — Benchmark Depth (Higher Effort, Parallel-Safe)
*Target: 5–10 days. Independent of Phases 1–2.*

---

### P3-A: Add industry-differentiated benchmark categories

**File:** `skills/peer-benchmarker/references/industry_benchmarks.json`

**Problem:** All 6 industries share the same 5 category keys (IT, PROF_SVCS, FACILITIES, TRAVEL, MARKETING). A telecom company's cost structure is 60%+ network opex; a hospital's is 40%+ clinical supplies.

**What to add:** Extend each industry entry with sector-specific categories. Priority order:

| Industry | Add categories |
|---|---|
| `manufacturing` | LOGISTICS, ENERGY, RAW_MATERIALS, MAINTENANCE |
| `healthcare` | CLINICAL_SUPPLIES, MEDICAL_DEVICES, CLINICAL_STAFFING |
| `financial_services` | TECH_INFRA, REGULATORY_COMPLIANCE, TREASURY_OPS |
| `retail_consumer` | LOGISTICS, STORE_OPERATIONS, TRADE_SPEND |
| `technology` | CLOUD_INFRA, R&D_TOOLS, CUSTOMER_SUCCESS |
| `gcc_capability_centers` | TALENT_ACQUISITION, SEAT_COST, TELECOM_INFRA |

Each category needs: `p25`, `p50`, `p75`, `p90` percentile spend-as-%-of-revenue, `source_type`, `rationale`. Use `internal_calibration` with the same disclaimer pattern as `diagnostic_thresholds.json`.

---

### P3-B: Fix sector-pack-to-benchmark collapse for telco and energy

**File:** `app/services/benchmarks.py`, `SECTOR_PACK_TO_BENCHMARK` dict

**Problem:** `telecom_infra → technology` and `energy_utilities → manufacturing` produce misleading peer comparisons.

**Immediate fix:** Create dedicated benchmark industry keys in `industry_benchmarks.json` for `telecom_infra` and `energy_utilities`, even with thin data, and point the mapping to them:

```python
SECTOR_PACK_TO_BENCHMARK: Dict[str, str] = {
    ...
    "telecom_infra": "telecom_infra",       # was: "technology"
    "energy_utilities": "energy_utilities", # was: "manufacturing"
    ...
}
```

For the interim period before P3-A completes, add a `benchmark_confidence_note` to the benchmark resolution output when a fallback mapping is in use:

```python
def benchmark_industry_for(industry: str) -> tuple[str, str | None]:
    """Returns (resolved_key, fallback_note)."""
    FALLBACK_MAPPINGS = {"fmcg_consumer": "retail_consumer", ...}
    ...
```

---

### P3-C: Wire `specificity_score` to confidence band width

**File:** `app/skills/engine/savings.py`, `value_bridge_calculator` (also used in P2-C)

**Problem:** `specificity_score` is stored on benchmark datasets (e.g., 0.55 for seed) but never flows into band calculation.

**Change:** Pass `specificity_score` from the resolved benchmark dataset into `value_bridge_calculator` via its call site in `savings_modeler`. Use it in the `_band_factors()` function defined in P2-C. The call chain is:

```
savings_modeler → resolve_benchmark_payload() [returns specificity_score]
               → value_bridge_calculator(specificity_score=...)
               → _band_factors(sustainability, specificity_score)
```

---

## Regression Test Additions

Add to `sector_packs.py → run_regression_test()`:

```python
# Check effort_weeks and applicability_threshold_pct are populated on sector levers
for lv in sector_levers:
    lid = lv.get("lever_id", "?")
    ew = lv.get("effort_weeks") or {}
    if not ew.get("p50"):
        errors.append(f"{lid}: effort_weeks.p50 missing")
    if lv.get("applicability_threshold_pct") is None:
        errors.append(f"{lid}: applicability_threshold_pct missing")
checks["lever_effort_weeks"] = not any("effort_weeks" in e for e in errors)
checks["lever_applicability_threshold"] = not any("applicability_threshold_pct" in e for e in errors)
```

---

## Summary

| Phase | Items | Effort | Risk |
|---|---|---|---|
| P1: Config/data | P1-A, P1-B, P1-C | 1–2 days | Zero |
| P2: Logic changes | P2-A through P2-F | 3–5 days | Low — each is contained |
| P3: Benchmark depth | P3-A, P3-B, P3-C | 5–10 days | Low — additive only |

**Recommended sequence:** P1-A → P2-E (horizon) → P2-D (EBITDA) → P2-A (bounce-back) → P2-B (execution prob) → P2-C (band factors) → P2-F (regulatory scenario) → P3-B (mapping fix) → P3-A (category depth) → P3-C (specificity wire-up).

Start with P1-A and P2-E because they unblock the effort-vs-impact matrix and horizon waterfall — the two deliverables consultants reach for first in an executive readout.
