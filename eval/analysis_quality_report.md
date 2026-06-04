# OpEx Platform — Analysis Quality Eval

**Date:** 2026-06-04  |  **Platform:** v2.1  |  **Overall:** 9.69/10  |  **Status:** ✅ PASS

Scenarios run: 5 | Scenarios successfully executed: 5

> This eval scores the quality of skill outputs (numerical faithfulness, recommendation specificity, evidence grounding, priority ranking, coverage completeness, causal reasoning, decision memo quality, action timeframe clarity) by running the analysis pipeline against 5 golden spend scenarios. No LLM calls are made by the scorer — all checks are deterministic.

## Skill Output Integrity — 10.0/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| AQ-01 | Numerical Faithfulness | 25% | 10.0 | 7.0 | ✅ |
| AQ-02 | Recommendation Specificity | 20% | 10.0 | 7.0 | ✅ |
| AQ-03 | Evidence Grounding | 20% | 10.0 | 7.0 | ✅ |
| AQ-04 | Priority Ranking Correctness | 15% | 10.0 | 8.0 | ✅ |
| AQ-06 | Causal Reasoning Quality | 20% | 10.0 | 6.0 | ✅ |


## Signal Coverage & Composition Quality — 9.3/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| AQ-05 | Coverage Completeness | 30% | 10.0 | 7.0 | ✅ |
| AQ-07 | Decision Memo Quality | 35% | 8.0 | 7.0 | ✅ |
| AQ-08 | Action Timeframe Clarity | 35% | 10.0 | 6.0 | ✅ |


## Improvement Opportunities (Ranked by Priority)

All dimensions that are failing or within 3 points of their threshold, plus the complete improvement roadmap:

| Priority | ID | Dimension | Score | Threshold | Delta | Status |
|----------|----|-----------|-------|-----------|-------|--------|
| 1 | AQ-07 | Decision Memo Quality | 8.0 | 7.0 | +1.0 | ⚠️ AT RISK |
| 2 | AQ-04 | Priority Ranking Correctness | 10.0 | 8.0 | +2.0 | ⚠️ AT RISK |
| 3 | AQ-01 | Numerical Faithfulness | 10.0 | 7.0 | +3.0 | ✅ PASS |
| 4 | AQ-02 | Recommendation Specificity | 10.0 | 7.0 | +3.0 | ✅ PASS |
| 5 | AQ-03 | Evidence Grounding | 10.0 | 7.0 | +3.0 | ✅ PASS |
| 6 | AQ-05 | Coverage Completeness | 10.0 | 7.0 | +3.0 | ✅ PASS |
| 7 | AQ-06 | Causal Reasoning Quality | 10.0 | 6.0 | +4.0 | ✅ PASS |
| 8 | AQ-08 | Action Timeframe Clarity | 10.0 | 6.0 | +4.0 | ✅ PASS |


## Improvement Roadmap

The following improvements are recommended, ordered by priority (failing → at-risk → enhancement):

### 1. AQ-07: Decision Memo Quality — 8.0/10 [AT RISK — within threshold]

**Action:** For category-focused intents, ensure all four lenses (value bridge, peer benchmark, root cause, heuristic) compute results for the focus category. Check that heuristic_analyzer runs when headcount=0 (revenue-only targets).

### 2. AQ-04: Priority Ranking Correctness — 10.0/10 [AT RISK — within threshold]

**Action:** value_bridge_calculator already sorts by deduped_mid_savings. If this fails, check whether savings_modeler returned initiatives in a fixed ordering that overrides the sort.

### 3. AQ-01: Numerical Faithfulness — 10.0/10 [Enhancement opportunity]

**Action:** Standardize amount formatting with a shared fmt_amount() helper in reflect.py. Assert that deduped_mid_savings propagates consistently through _build_response_text.

### 4. AQ-02: Recommendation Specificity — 10.0/10 [Enhancement opportunity]

**Action:** Add supplier injection into value bridge rows: ensure each initiative inherits the top supplier from spend_profiler.category_profile. Validate lever names against the canonical lever registry.

### 5. AQ-03: Evidence Grounding — 10.0/10 [Enhancement opportunity]

**Action:** Propagate PeerComparisonRow.source into value_matrix rows so downstream response composition can cite the benchmark source. Cross-reference bridge categories to peer/internal outputs.

### 6. AQ-05: Coverage Completeness — 10.0/10 [Enhancement opportunity]

**Action:** Add BvA and MSME flags to _build_response_text deterministic path. For BvA: inject bva.variances into the response when bva_available=True. For MSME: add a compliance block when at_risk_count > 0.

### 7. AQ-06: Causal Reasoning Quality — 10.0/10 [Enhancement opportunity]

**Action:** Root-cause-analyzer only fires for categories in P50-P75/P75-P90/P90+ bands. Inject live metrics into diagnoses: include actual HHI, maverick spend %, or DPO gap in the diagnosis string.

### 8. AQ-08: Action Timeframe Clarity — 10.0/10 [Enhancement opportunity]

**Action:** Validate payback_months in savings_modeler: if computed payback > 36 months, cap it with a warning rather than silently returning an unrealistic value. Ensure cost_to_achieve.total_3yr is always populated.

## Key Findings from Evidence Analysis

These findings were extracted from the per-scenario evidence collected during the eval run:

**AQ-03 Evidence Grounding (7.0/10 — at threshold):** The `benchmark_dataset.source` is consistently `"platform_seed"` across all 5 scenarios. This means all benchmark comparisons cite an internal seed file rather than a named external dataset (Deloitte, IBISWorld, Hackett Group, etc.). Users cannot verify benchmark claims against a real external source. The category-to-benchmark grounding is perfect (all bridge categories appear in peer comparisons), so the gap is entirely in source attribution.

**AQ-02 Recommendation Specificity (9.0/10):** `savings-modeler` initiatives return `assumptions: None` across all scenarios. The lever metadata includes `condition_precedents` (execution conditions like "requires CPO sign-off" or "supplier master consolidation required") but these are never surfaced onto the initiative output. Advisory text that includes assumptions/conditions helps CFOs assign accountability.

**AQ-07 Decision Memo Quality (8.0/10):** The S03 category-focused scenario correctly scores 10/10 — all four benchmark lenses (value bridge, peer, root cause, heuristic) produce results for the IT focus category. The 8.0 average is pulled down by the 7.5 neutral scores assigned to non-category-focused scenarios. The category-focus capability itself is working correctly.

**AQ-04 Priority Ranking (10.0/10):** `value_bridge_calculator` consistently sorts by `deduped_mid_savings` descending. This guarantee holds across all 5 scenarios including multi-category (S05 with 10 rows). No inversions detected.

**AQ-05 Coverage Completeness (10.0/10):** BvA analyzer fires correctly when budget lines are present (S02), MSME compliance surfaces at-risk payments correctly (S04), and contract lifecycle alerts are triggered by upcoming expiry dates (S04). All conditional signals are correctly gated.
