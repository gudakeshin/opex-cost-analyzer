---
name: llm-context-builder
description: "Assemble the LLM context payload for analysis-synthesizer and executive-communication, enforcing band rules: B2 data included in full, B3 data tokenised (supplier names replaced with coded IDs), B4 data rejected. Emits a context-assembly audit event."
version: "1.0"
status: active
llm_required: false
band_ceiling: "B3"
---

# LLM Context Builder

Enforces data-band rules when assembling context for LLM calls.

## What This Skill Does

1. Receives skill outputs tagged with `_security_metadata` (from data-classifier).
2. For each block:
   - **B1 / B2** → included verbatim
   - **B3** → supplier names replaced with coded IDs (e.g. `VENDOR_001`); all other fields kept
   - **B4** → block excluded entirely; a placeholder note is inserted
3. Assembles the sanitised context dict for downstream LLM calls.
4. Emits a `llm_context_assembled` audit event with: number of blocks included, excluded, tokenised, and the worst band present.

## Tokenisation Rules for B3 Suppliers

- Deterministic hash: `VENDOR_{first4chars_of_sha256(supplier_name)}`
- Mapping is stored in session memory for cross-turn consistency
- Never logged to the SIEM or included in the context payload

## Output Schema

```json
{
  "context_ready": true,
  "blocks_included": 0,
  "blocks_tokenised": 0,
  "blocks_excluded": 0,
  "worst_band_in_context": "B2",
  "sanitised_skill_outputs": {},
  "exclusion_log": []
}
```

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | full  | Returns empty context (M1 suppresses LLM calls anyway) |
| M2   | full  | B3 tokenised, B4 excluded |
| M3   | full  | B2 only — B3 also excluded for on-prem |
