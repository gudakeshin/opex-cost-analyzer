# OpEx Platform — Document Processing Quality Eval

**Date:** 2026-06-07  |  **Platform:** v2.1  |  **Overall:** 9.91/10  |  **Status:** ✅ PASS

Fixtures: 7  |  LLM judge (DP-07): active  |  Retrieval backend: local keyword index (deterministic)

> Scores the document ingestion pipeline — parse → schema inference → sheet selection → normalization → hierarchical chunking → retrieval — against synthetic golden fixtures. DP-01..06 and DP-08 are deterministic; DP-07 uses a provider-agnostic LLM judge.

## Parse & Normalize — 10.0/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| DP-01 | Parse Success Rate | 30% | 10.0 | 9.0 | ✅ |
| DP-02 | Schema Role Accuracy | 30% | 10.0 | 7.0 | ✅ |
| DP-03 | Sheet Selection Correctness | 15% | 10.0 | 7.0 | ✅ |
| DP-04 | Normalization Fidelity | 25% | 10.0 | 7.0 | ✅ |

## Chunk & Retrieve — 9.8/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| DP-05 | Chunk Structure Integrity | 40% | 10.0 | 7.0 | ✅ |
| DP-06 | Retrieval Precision | 40% | 9.5 | 6.0 | ✅ |
| DP-07 | Parse Fidelity (LLM judge) | 20% | 0.0 | 6.0 | ⏭️ SKIP |

### DP-07: Parse Fidelity (LLM judge)

**Finding:** SKIPPED — DP-07 needs ANTHROPIC_API_KEY or GEMINI_API_KEY; not counted in pass/fail.

**Evidence:** `{"note": "skipped \u2014 no LLM provider (set ANTHROPIC_API_KEY or GEMINI_API_KEY)"}`

**Remediation:** Improve extraction fidelity (enable LlamaParse for PDF/DOCX, or fix native parse_document) so headings/numbers survive.

## Quality Signals — 10.0/10 [PASS]

| ID | Dimension | Weight | Score | Threshold | Status |
|----|-----------|--------|-------|-----------|--------|
| DP-08 | Quality-Flag Capture | 100% | 10.0 | 7.0 | ✅ |
