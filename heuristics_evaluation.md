# Heuristics Quality Evaluation — OpEx Cost Analyzer
**Date:** July 2026 (refreshed) | **Scope:** Analytical heuristics across `model_parameters.json`, `diagnostic_thresholds.json`, `sensitivity.py`, `savings.py`, `sector_packs/`, and `calibration.py`

---

## Executive Summary

The heuristics layer is **production-ready for consultant-driven engagements** on core diagnostic and scenario paths. Source provenance, externalized parameters, calibration governance, and sector-pack versioning remain strengths. Recent work (June–July 2026) closed the highest-impact gaps: graduated maverick severity, spend-floor fragmentation gates, sustainability/specificity-driven confidence bands, lever-family dedup overlap, per-lever bounce-back and execution-probability weighting, EBITDA bps framing, horizon classification, regulatory-headwind scenario, populated `effort_weeks`, industry-differentiated benchmark categories, industry-variant cost-per-transaction thresholds, and client-facing calibration gate explanations.

**Remaining gaps** are mostly medium/low priority: industry-variant cost-per-transaction thresholds, client-facing calibration gate explanations, and licensed benchmark feed enrichment (CMIE/Capitaline/CRISIL stubs).

---

## What's Working Well

**Source transparency** — Every threshold in `diagnostic_thresholds.json` carries `source_type`, `rationale`, and disclaimer text. Model parameters explicitly warn against citing internal calibration as external benchmarks.

**Parameters are externalized** — CFOs can override execution rates, discount rate, and bounce-back rates without code changes. Per-engagement lever suppression via `set_pack_override()` is wired.

**Calibration loop** — Realised savings feed `propose_lever_range_update` → senior review → `apply_version_bump`. Gate logic (`auto_approve` ≥ 80%, `senior_review` ≥ 60%, `deep_audit` < 60%) maps to consulting governance.

**Sector pack versioning** — `lock_pack_version` at engagement start prevents mid-programme benchmark drift.

---

## Recently Fixed (July 2026)

| Gap (original audit) | Resolution |
|---|---|
| Flat ±20% value-bridge bands | `_band_factors()` widens/narrows by `sustainability_score` + `benchmark_specificity` |
| Flat 25% dedup haircut | Lever-family `dedup_overlap_matrix` in `model_parameters.json`; `_category_deduped_mid()` |
| Binary maverick at 20% | Graduated tiers (Elevated / Significant / Critical) in `diagnostic_thresholds.json` |
| HHI fragmentation without spend floor | `supplier_fragmentation_min_spend` (₹5 Cr) gate |
| `effort_weeks` null on sector levers | Populated on all 15 root packs + loader fallback from `complexity_tier` |
| `bounce_back_risk` unused in scenarios | Per-initiative reversion rates in bounce-back scenario |
| `base_execution_probability` unused | `_portfolio_execution_weighted_savings()` for conservative/accelerated |
| No EBITDA bps framing | `ebitda_impact` per initiative + `portfolio_ebitda_impact_bps` in summary |
| No horizon classification | `quick_win` / `structural` / `transformational` on each initiative |
| No regulatory scenario | `regulatory_headwind` scenario (GST ITC, MSME payment terms, bank fees) |
| Identical benchmark categories across industries | Dedicated keys for telecom (`NETWORK_OPEX`, `TOWER_INFRA`), healthcare (`CLINICAL_*`), BFSI (`TECH_INFRA`, `TREASURY_OPS`), energy, retail, etc. |
| `telecom_infra → technology` collapse | Maps to dedicated `telecom_infra` benchmark key |
| `specificity_score` not modulating bands | Wired through `benchmark_specificity` into `_band_factors()` |

---

## Open Issues

### Licensed benchmark feeds

**CMIE/Capitaline/CRISIL connectors remain stubs** in `benchmarks_india.py`. Production deployments should enrich seed percentiles with licensed data; the platform honestly labels seed data as illustrative (`specificity_score: 0.55`).

---

## Prioritized Remaining Roadmap

**Higher effort / parallel-safe:**
1. Licensed benchmark feed ingestion (CMIE Prowess, Capitaline, CRISIL)
2. Initiative-pair overlap matrix exposed in UI (dedup is computed; transparency layer optional)

---

## Summary Table

| Heuristic | Status | Notes |
|---|---|---|
| Value bridge confidence bands | **Fixed** | Sustainability + specificity driven |
| Deduplication haircut | **Fixed** | Lever-family overlap matrix |
| Maverick spend flag | **Fixed** | Graduated severity tiers |
| effort_weeks on sector levers | **Fixed** | All packs + loader fallback |
| bounce_back_risk → scenario | **Fixed** | Per-lever reversion rates |
| base_execution_probability | **Fixed** | Portfolio-weighted scenarios |
| EBITDA margin impact | **Fixed** | bps per initiative + portfolio |
| Horizon classification | **Fixed** | quick_win / structural / transformational |
| HHI spend floor | **Fixed** | ₹5 Cr minimum addressable gate |
| Industry benchmark categories | **Improved** | Sector-specific keys; seed still illustrative |
| specificity_score → band width | **Fixed** | Via benchmark_specificity param |
| Regulatory risk scenario | **Fixed** | regulatory_headwind in sensitivity |
| Cost-per-transaction by industry | **Fixed** | Per-industry thresholds in diagnostic config |
| Calibration gate client narrative | **Fixed** | `gate_explanation` on calibration reports |
| Licensed benchmark feeds | Stubbed | Connectors exist; no live data |
