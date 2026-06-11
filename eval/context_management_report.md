# OpEx Platform — Context Management Quality Eval

**Date:** 2026-06-11  |  **Platform:** v2.1  |  **Overall:** 9.43/10  |  **Status:** ✅ PASS

Golden fixture files: 6  |  CM-13 token calibration: active  |  Retrieval backend: local keyword index (deterministic)

> Scores the machinery that decides what reaches the LLM — synthesis token budgeting and degradation, payload slimming, relevance filtering, chat-history windowing, and document-RAG context packing — against synthetic golden fixtures with all LLM calls mocked.
>
> ⚠️ **SCORE TYPE: STRUCTURAL** — Context-management *mechanics*, not answer quality. CM-03, CM-04 and CM-10 are honest-gap probes that are expected to FAIL until the underlying mechanism is improved — a failure there is the finding, not an eval bug. See `run_llm_judge_eval.py` for answer quality.

## Synthesis Token Budget — 9.4/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| CM-01 | Slimming Efficiency & Whitelist Integrity | 22% | 10.0 | 7.0 | ✅ |
| CM-02 | Budget Gate Degradation | 20% | 10.0 | 8.0 | ✅ |
| CM-03 | Core-Skill Survival Under Degradation | 12% | 10.0 | 6.0 | ✅ |
| CM-04 | Budget Estimate Completeness | 16% | 8.0 | 6.0 | ✅ |
| CM-05 | End-to-End Oversized Chain | 20% | 10.0 | 8.0 | ✅ |
| CM-13 | Token Estimate vs Real API Count | 10% | 6.8 | 6.0 | ✅ |

## Relevance Filtering — 10.0/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| CM-06 | Capability Detection Accuracy | 30% | 10.0 | 7.0 | ✅ |
| CM-07 | Relevance Selection Precision/Recall | 40% | 10.0 | 7.0 | ✅ |
| CM-08 | Manifest Completeness & Bypass Correctness | 30% | 10.0 | 8.0 | ✅ |

## Retrieval Context (RAG) — 8.6/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| CM-11 | RAG Packing, Auto-Merge & Fallback | 55% | 7.5 | 7.0 | ✅ |
| CM-12 | Retrieval Relevance | 45% | 10.0 | 6.0 | ✅ |

## Conversational Context — 10.0/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| CM-09 | Chat Window & Field Caps | 55% | 10.0 | 7.0 | ✅ |
| CM-10 | Chat Context Boundedness | 45% | 10.0 | 7.5 | ✅ |
