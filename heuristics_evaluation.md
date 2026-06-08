# Heuristics Quality Evaluation — OpEx Cost Analyzer
**Date:** June 2026 | **Scope:** All analytical heuristics across `model_parameters.json`, `diagnostic_thresholds.json`, `sensitivity.py`, `bands.py`, `sector_packs/`, and `calibration.py`

---

## Executive Summary

The app has a **structurally sound** heuristics layer — source provenance is tracked, parameters are externalized to config files, a calibration loop exists, and sensitivity analysis covers 7 scenarios. However, for a **consultant-driven, executive-ready** product, four categories of gaps limit usability: (1) blunt thresholds that can't survive executive scrutiny, (2) parameter fields that exist in the schema but are unpopulated, (3) missing business-language outputs that executives actually use, and (4) a sensitivity model that flattens lever-specific risk into global scalars.

---

## What's Working Well

**Source transparency is a genuine strength.** Every threshold in `diagnostic_thresholds.json` carries `source_type`, `rationale`, `source`, and `disclaimer`. The model_parameters.json disclaimer ("do not cite as externally-validated benchmarks in client deliverables") is exactly the kind of guardrail that prevents consultants from mis-citing AI-generated figures. This is production-grade intellectual honesty.

**Parameters are externalized.** CFOs can override `conservative_execution_rate`, `discount_rate`, and `bounce_back_reversion_rate` without touching code. The `set_pack_override()` pattern for lever suppression per engagement is similarly well-designed.

**The calibration loop is architecturally correct.** Realised savings feed back to lever range proposals (`propose_lever_range_update`) → senior reviewer approves → `apply_version_bump` updates the pack. The gate logic (`auto_approve` ≥ 80%, `senior_review` ≥ 60%, `deep_audit` < 60%) maps cleanly to consulting governance.

**Sector pack versioning at engagement start** (`lock_pack_version`) prevents mid-engagement benchmark drift — a real operational problem in 12-week programmes.

---

## Issues by Category

### 1. Thresholds That Won't Survive a CFO Challenge

**The ±20% value bridge confidence band is symmetric and context-free.**
`low_factor: 0.8, high_factor: 1.2` is applied to every lever identically. A signed contract renegotiation (execution probability 0.85, data-backed benchmark) carries the same uncertainty band as a demand management initiative (sustainability score 0.25, highly behavioural). An executive will immediately ask: "Why does your model treat a signed contract the same as a culture-change programme?" The band should widen with lower sustainability scores and narrower data quality.

**The 25% deduplication haircut is flat regardless of initiative overlap.**
`dedup_mid_factor: 0.75` applies a uniform 25% cut to the portfolio mid-case for overlap between initiatives. In practice, a procurement consolidation and a contract renegotiation in the same category have near-100% overlap; a facilities rationalization and a cloud FinOps initiative have 0% overlap. A flat 25% haircut overstates savings in concentrated portfolios and understates them in diverse ones.

**Maverick spend flag triggers at 20% — but best-in-class is <5%.**
The threshold is documented as "median-to-poor boundary," but the app surfaces it as a single binary flag. A company at 22% maverick spend and one at 45% maverick spend both get the same signal. Graduated thresholds (warning: 15–25%, significant: 25–40%, critical: >40%) would allow the diagnostic narrative to be calibrated to the client's actual maturity gap.

**The HHI fragmentation threshold (0.15) has no minimum-spend filter.**
A ₹10 Lakh category with 6 suppliers and HHI 0.12 gets flagged identically to a ₹100 Crore category in the same state. The existing `supplier_fragmentation_min_suppliers: 5` helps on supplier count but doesn't gate on addressable spend size — resulting in noise initiatives in executive dashboards.

**Cost-per-transaction threshold (₹1,000) has no industry variant.**
A bank processing high-value treasury invoices at ₹1,200/transaction is not comparable to a manufacturer processing high-volume commodity invoices at the same rate. The field exists without differentiation, and an executive in financial services will correctly push back.

---

### 2. Populated Schema Fields That Aren't Wired Up

**`effort_weeks` and `applicability_threshold_pct` are null on all sector levers.**
Reading the IT/ITES sector pack, `license_rightsizing`, `cloud_finops`, `subcontractor_optimization`, and `tech_debt_payoff` all show `effort_weeks: null` and `applicability_threshold_pct: null`. These fields are the inputs to the effort-vs-impact prioritization matrix — the 2×2 that every consulting executive presentation leads with. Without them, the app cannot distinguish "quick win" from "multi-year transformation." The data model is ready; the values need to be populated.

**`bounce_back_risk` field on levers (high/medium/low) is not connected to the bounce-back scenario.**
`sensitivity.py` uses a global `bounce_back_reversion_rate: 0.80` regardless of the lever's `bounce_back_risk` field. `contract_renegotiation` is tagged `bounce_back_risk: high` and `automation` would carry `low` — but the scenario treats them identically. The bounce-back scenario's NPV output could be materially more credible if it used the lever-level flag.

**`base_execution_probability` on levers is not used in scenario generation.**
Each lever has `base_execution_probability` (e.g., contract_renegotiation = 0.85). The sensitivity scenarios apply a single global `execution_rate_pct` override across all initiatives rather than composing from lever-level probabilities. A portfolio of levers with probabilities [0.85, 0.70, 0.55, 0.40] has a materially different risk profile than the global 60%/85% scalar suggests.

---

### 3. Missing Business-Language Outputs for Executive Audiences

**No EBITDA margin impact framing.** The app outputs absolute ₹ savings and NPV. Executives and boards think in EBITDA margin points. A ₹50 Crore saving on ₹2,000 Crore revenue is 250 bps of EBITDA uplift — that is the number that appears in investor presentations. The app has `annual_revenue` in the session state but doesn't surface revenue-scaled impact.

**No "quick win vs structural transformation" classification.** Consultants always segment the initiative pipeline into a 3-horizon view: (1) tactical quick wins <3 months, (2) structural 3–12 months, (3) transformational >12 months. The `phasing_curves` data in `model_parameters.json` implicitly contains this (payment terms = [1.0, 0.0, 0.0] = instant; shared_services_center = [0.05, 0.35, 0.60] = long tail), but no API surface or output field exposes a "horizon" classification.

**No regulatory risk scenario.** The 7 sensitivity scenarios cover execution risk, timeline risk, bounce-back, and volume growth — but not regulatory/compliance risk. In India, GST rate changes, ITC rule amendments, and MSME payment mandate changes directly affect opex savings realizability. For a CFO audience, a "regulatory headwind" scenario is expected.

**The calibration gate thresholds (60%, 80%) have no client-facing explanation.** The `gate_recommendation` field returns `auto_approve` / `senior_review` / `deep_audit` without surfacing *why* those thresholds matter in terms of model credibility. Consultants need to explain this in a client steering committee.

---

### 4. Benchmark Coverage Gaps

**Industry benchmark categories are identical across all 6 industries.** Every industry (technology, financial_services, manufacturing, healthcare, retail_consumer, gcc_capability_centers) maps to the same 5 categories: IT, PROF_SVCS, FACILITIES, TRAVEL, MARKETING. A hospital's facilities spend has completely different cost drivers than a software company's. The cross-industry seed dataset (`specificity_score: 0.55`, `sample_size: 0`) is directionally useful but cannot support category-level percentile positioning without industry-differentiated benchmarks.

**SECTOR_PACK_TO_BENCHMARK collapses materially different sectors.** `energy_utilities → manufacturing`, `telecom_infra → technology`, `fmcg_consumer → retail_consumer`. Telecom OpEx is dominated by network maintenance, tower leases, and spectrum costs — nothing like a SaaS company's IT/PROF_SVCS profile. These mappings produce plausible-looking but potentially misleading benchmark comparisons at the category level.

**`specificity_score` exists but doesn't modulate the value bridge bands.** A dataset with specificity 0.55 and one with 0.90 produce identical confidence bands in the output. The score should mechanically widen/narrow the ±20% band — specificity 0.55 → ±30%, specificity 0.90 → ±12%.

---

## Prioritized Improvement Roadmap

**High impact, low effort** (config file changes, no new logic):
1. Populate `effort_weeks` (p10/p50/p90) and `applicability_threshold_pct` on all sector levers — enables effort-vs-impact matrix
2. Add graduated maverick spend thresholds (warning/significant/critical) to `diagnostic_thresholds.json`
3. Add a spend-minimum filter (e.g., >₹5 Crore) to the HHI fragmentation flag

**High impact, medium effort** (new computation in existing services):
4. Wire `bounce_back_risk` (high/medium/low) on levers to drive lever-specific reversion rates in the bounce-back scenario (high→80%, medium→40%, low→15%)
5. Compute `base_execution_probability` portfolio roll-up to replace the global scalar in scenario generation
6. Add EBITDA margin impact field to pipeline summary and initiative outputs
7. Make the value bridge confidence band a function of `sustainability_score` and benchmark `specificity_score` — replace flat ±20% with a formula

**Medium impact, higher effort** (new output surfaces):
8. Add horizon classification (tactical/structural/transformational) to initiative outputs derived from `phasing_curves`
9. Add a regulatory risk scenario to the sensitivity analysis (India-specific: GST rate/ITC amendment, MSME payment mandate)
10. Expose initiative-pair overlap matrix for deduplication haircut calculation rather than the flat 25%

---

## Summary Table

| Heuristic | Current State | Gap for Executive Use | Priority |
|---|---|---|---|
| Value bridge confidence bands | Flat ±20% | Should vary by sustainability + data quality | High |
| Deduplication haircut | Flat 25% | Should be initiative-pair-specific | High |
| Maverick spend flag | Binary at 20% | Needs graduated severity tiers | High |
| effort_weeks on sector levers | null | Blocks effort-vs-impact matrix | High |
| bounce_back_risk → scenario linkage | Not connected | Scenario uses global rate only | Medium |
| base_execution_probability | Not used in scenarios | Scenarios lose lever-level granularity | Medium |
| EBITDA margin impact | Not computed | Executives need basis point framing | Medium |
| Horizon classification | Not surfaced | Core consulting deliverable missing | Medium |
| HHI flag: spend floor | No minimum spend gate | Noise in executive pipeline view | Medium |
| Industry benchmark categories | Identical across all sectors | Sector differentiation missing | Medium |
| specificity_score → band width | Not wired up | Score exists but has no downstream effect | Low |
| Regulatory risk scenario | Not in sensitivity | India-specific CFO expectation | Low |
