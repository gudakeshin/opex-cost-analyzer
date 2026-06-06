# Diagnostic Feature Eval — ❌ FAIL

**Date:** 2026-06-05  |  **Version:** v2.1  |  **Overall Score:** 8.45/10

## Summary

| Domain | Score | Weight | Status |
|--------|-------|--------|--------|
| Data Integrity | 10.0/10 | 30% | ✅ |
| Analysis Completeness | 9.9/10 | 35% | ✅ |
| Schema & Signal Integrity | 4.0/10 | 15% | ❌ |
| Input Signal Quality | 6.9/10 | 20% | ✅ |

## Dimension Detail

| ID | Dimension | Score | Threshold | Status | Gap |
|----|-----------|-------|-----------|--------|-----|
| DG-01 | Synthetic Profile Arithmetic | 10.0 | 7.0 | ✅ | 0.0 |
| DG-02 | Benchmark Gap Field Consistency | 10.0 | 8.0 | ✅ | 0.0 |
| DG-03 | Value-at-Table Arithmetic | 10.0 | 7.0 | ✅ | 0.0 |
| DG-04 | Stub Field Detection | 10.0 | 4.0 | ✅ | 0.0 |
| DG-05 | Lever Base Spend Coverage | 9.7 | 6.0 | ✅ | 0.0 |
| DG-06 | Key Findings Completeness | 10.0 | 7.0 | ✅ | 0.0 |
| DG-07 | Diagnostic Signal Schema | 10.0 | 9.0 | ✅ | 0.0 |
| DG-08 | Sector Pack Mapping Coverage | 0.0 | 8.0 | ❌ | 8.0 |
| DG-09 | Document Contextualizer Signal Quality | 6.0 | 4.0 | ✅ | 0.0 |
| DG-10 | Circular Benchmark Derivation Disclosure | 5.0 | 5.0 | ✅ | 0.0 |
| DG-11 | Silent Parameter Defaulting | 10.0 | 4.0 | ✅ | 0.0 |

## Known Stubs & Inconsistencies

| Severity | Stub | Location | Fix |
|----------|------|----------|-----|
| HIGH | NPV always 0.0 | `enterprise.py:369` | Add wacc param; compute 3-year NPV |
| HIGH | root_causes=[] always | `enterprise.py:340` | Run root_cause_analyzer on synthetic profile first |
| HIGH | document_contextualizer is bag-of-words | `profiler.py:786-811` | Word-boundary regex; remove ambiguous ≤3-char keywords; add LLM summary |
| HIGH | URL analysis dead code when urls=[] | `enterprise.py:261` + `profiler.py:787` | Return structured 'no_url_provided' signal; skip contextualizer call |
| MED | Circular benchmark derivation | `enterprise.py:289-333` | Rename headroom field; set percentile_band='synthetic_P50'; add profile_basis field |
| MED | headcount hardcoded 500 | `enterprise.py:338` | Add headcount to CompanyResearchRequest schema |
| MED | headcount missing from request schema | `schemas.py:203-207` | Add headcount field to CompanyResearchRequest |
| MED | signal_corpus / line_flags always None | `enterprise.py:335-341` | Build signal_corpus from synthetic profile; derive line_flags from constraints |
| MED | category='' always in value_at_table | `enterprise.py:365` | Populate from matched trigger_signal category ID |
| MED | gap_pct/gap_cr always 0 | `enterprise.py:326-328` | Compute vs. P25 target or rename fields |
| MED | '3-year' label without 3x multiplier | `enterprise.py:387` | Multiply p50_cr by 3 or rename to 'annual savings' |
| LOW | _PACK_TO_BENCH missing sector packs | `enterprise.py:265-277` | Add financial_services_nonbank, gcc_capability_centers, healthcare_hospitals, hospitality_travel |
| LOW | resolve_benchmark_payload called twice | `enterprise.py:280+303` | Reuse categories list from first call |
| LOW | engagement_id not passed to lever resolver | `enterprise.py:335-341` | Generate engagement_id from company+timestamp for audit trail |

## Top Gaps to Close

1. **DG-08** (gap 8.0) — Add the following to _PACK_TO_BENCH in app/routers/enterprise.py: "bfsi_banks": "<benchmark_industry

## Remediation Roadmap

1. **[DG-08] Sector Pack Mapping Coverage** — Add the following to _PACK_TO_BENCH in app/routers/enterprise.py: "bfsi_banks": "<benchmark_industry>", "conglomerate": 
