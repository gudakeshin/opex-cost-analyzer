# Diagnostic Feature Eval — ✅ PASS

**Date:** 2026-10-30  |  **Version:** v2.1  |  **Overall Score:** 9.29/10

> ⚠️ **SCORE TYPE: STRUCTURAL** — Measures diagnostic skill wiring and output schema completeness. Does NOT validate analytical accuracy. See `run_llm_judge_eval.py`.

## Summary

| Domain | Score | Weight | Status |
|--------|-------|--------|--------|
| Data Integrity | 10.0/10 | 30% | ✅ |
| Analysis Completeness | 9.8/10 | 35% | ✅ |
| Schema & Signal Integrity | 10.0/10 | 15% | ✅ |
| Input Signal Quality | 6.9/10 | 20% | ✅ |

## Dimension Detail

| ID | Dimension | Score | Threshold | Status | Gap |
|----|-----------|-------|-----------|--------|-----|
| DG-01 | Synthetic Profile Arithmetic | 10.0 | 7.0 | ✅ | 0.0 |
| DG-02 | Benchmark Gap Field Consistency | 10.0 | 8.0 | ✅ | 0.0 |
| DG-03 | Value-at-Table Arithmetic | 10.0 | 7.0 | ✅ | 0.0 |
| DG-04 | Stub Field Detection | 10.0 | 4.0 | ✅ | 0.0 |
| DG-05 | Lever Base Spend Coverage | 9.2 | 6.0 | ✅ | 0.0 |
| DG-06 | Key Findings Completeness | 10.0 | 7.0 | ✅ | 0.0 |
| DG-07 | Diagnostic Signal Schema | 10.0 | 9.0 | ✅ | 0.0 |
| DG-08 | Sector Pack Mapping Coverage | 10.0 | 8.0 | ✅ | 0.0 |
| DG-09 | Document Contextualizer Signal Quality | 6.0 | 4.0 | ✅ | 0.0 |
| DG-10 | Circular Benchmark Derivation Disclosure | 5.0 | 5.0 | ✅ | 0.0 |
| DG-11 | Silent Parameter Defaulting | 10.0 | 4.0 | ✅ | 0.0 |

## Known Stubs & Inconsistencies

| Severity | Stub | Location | Fix |
|----------|------|----------|-----|
| HIGH | document_contextualizer is bag-of-words | `profiler.py:786-811` | Word-boundary regex; remove ambiguous ≤3-char keywords; add LLM summary |
| HIGH | URL analysis dead code when urls=[] | `enterprise.py:261` + `profiler.py:787` | Return structured 'no_url_provided' signal; skip contextualizer call |
| MED | peer_disclosure_miner null shells (M1) | `strategic.py:peer_disclosure_miner` | Integrate filing fetch or downgrade skill visibility |
| MED | reg_watcher sample catalogue (default) | `reg_watcher.py` | Set REG_WATCHER_LIVE=1 when Phase 4 HTTP feeds are wired |
| LOW | Licensed benchmark HTTP (env-gated) | `benchmarks_india.py` | Provision CMIE/Capitaline/CRISIL keys; verify API base URLs |

## Remediation Roadmap

