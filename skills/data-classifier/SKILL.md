---
name: data-classifier
description: "Classify every spend line and every skill-output aggregate with a B1–B4 data band. Attach inference-risk scores to aggregates. Run as Group 0 skill before any LLM context assembly."
version: "1.0"
status: active
llm_required: false
band_ceiling: "B4"
---

# Data Classifier

Assigns B1–B4 data bands to spend lines and skill-output aggregates.

## Band Definitions

| Band | Label | Typical Content | LLM Allowed |
|------|-------|-----------------|-------------|
| B1 | Public | Industry benchmarks, anonymised aggregates | All modes |
| B2 | Confidential | Company totals, category spend (no supplier) | M2, M3 |
| B3 | Restricted | Supplier names, GL codes, GSTIN | M2 only |
| B4 | PII / Regulated | Person names, email, PAN, Aadhaar, phone | Never |

## K-Anonymity Rule

Any aggregate derived from fewer than 5 source rows is promoted to **B3**, regardless of content, to prevent individual-company re-identification.

## Output Schema

```json
{
  "line_bands": [
    {"row_id": 1, "band": "B3", "reason": "supplier field non-empty"}
  ],
  "aggregate_bands": {
    "spend-profiler": {"band": "B3", "inference_risk_score": 0.62, "reason": "..."}
  },
  "worst_band": "B3",
  "b4_row_ids": [],
  "b4_count": 0,
  "summary": "24 rows classified; worst band B3; 0 B4 rows detected."
}
```

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | full  | Fully deterministic |
| M2   | full  | Same algorithm |
| M3   | full  | Same algorithm |
