---
name: pii-stripper
description: "Scan spend-line records for PII (email, phone, PAN, Aadhaar, named individuals) and redact before any downstream skill or LLM receives the data. Classify quarantine-worthy rows as B4. Run as Group 0 skill before any analysis."
version: "1.0"
status: active
llm_required: false
band_ceiling: "B4"
---

# PII Stripper

Probabilistic PII detector and redactor for Indian enterprise spend data.

## What This Skill Does

1. Scans every string field in every spend line for PII patterns.
2. Redacts matched spans with `█` characters.
3. Returns per-row match counts, pii_types found, and field names affected.
4. Quarantines rows where PII density exceeds the threshold — these rows are excluded from all downstream analysis and LLM context.
5. Emits a `pii_detected` audit event for every batch where PII is found.

## PII Patterns Detected (Phase 2 — regex baseline)

| Pattern | Example | Confidence |
|---------|---------|------------|
| Email | `pallav@example.com` | 0.99 |
| PAN card | `ABCDE1234F` | 0.98 |
| GSTIN | `27AABCM1234A1Z5` | 0.97 |
| Indian mobile | `+91 98765 43210` | 0.92 |
| Aadhaar | `1234 5678 9012` | 0.85 |
| Titled name | `Mr. Pallav Chaturvedi` | 0.80 |

Phase 3 will overlay Presidio + spaCy NER + Indian-name corpus to reach the ≥ 99.2% recall target.

## Output Schema

```json
{
  "rows_scanned": 0,
  "rows_with_pii": 0,
  "rows_quarantined": 0,
  "pii_type_counts": {"email": 0, "pan": 0, "phone": 0, "aadhaar": 0, "name": 0},
  "affected_fields": ["supplier", "description"],
  "quarantine_row_ids": [],
  "redacted_lines": []
}
```

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | full  | Regex-only; no LLM needed |
| M2   | full  | Same regex; Presidio can be added |
| M3   | full  | Same regex |
