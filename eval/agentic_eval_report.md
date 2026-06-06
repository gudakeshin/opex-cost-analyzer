# Agentic Intelligence Eval

**Eval date**: 2026-06-06  
**Overall score**: 9.96/10  
**Status**: PASS ✓

---

## Domain Summary

| Domain | Score | Status |
|--------|-------|--------|
| Controller & Routing (w=0.35) | 10.00/10 | PASS ✓ |
| Intelligence & Discovery (w=0.40) | 9.90/10 | PASS ✓ |
| Safety & Provenance (w=0.25) | 10.00/10 | PASS ✓ |
---

## Controller & Routing

Domain score: **10.00/10** (PASS ✓)

| Dimension | Score | Threshold | Status |
|-----------|-------|-----------|--------|
| Agent Controller Wiring in Orchestrator | 10.00 | 9.0 | ✓ |
| Tool Catalog Completeness | 10.00 | 9.0 | ✓ |
| Deterministic Fallback Gate | 10.00 | 9.0 | ✓ |

### AG_01 — Agent Controller Wiring in Orchestrator [PASS ✓]
**Score**: 10.00/10  **Threshold**: 9.0
**Finding**: 8/8 controller-wiring checks pass
**Detail**: Missing: none
**Remediation**: Controller fully wired.

### AG_02 — Tool Catalog Completeness [PASS ✓]
**Score**: 10.00/10  **Threshold**: 9.0
**Finding**: 8/8 required tools present in catalog
**Detail**: Missing tools: none
**Remediation**: All 8 tools present.

### AG_03 — Deterministic Fallback Gate [PASS ✓]
**Score**: 10.00/10  **Threshold**: 9.0
**Finding**: 5/5 fallback gate checks pass
**Detail**: Missing: none
**Remediation**: Fallback gate fully implemented.

---

## Intelligence & Discovery

Domain score: **9.90/10** (PASS ✓)

| Dimension | Score | Threshold | Status |
|-----------|-------|-----------|--------|
| Semantic Skill Discovery Wired | 10.00 | 9.0 | ✓ |
| _DEP_MAP Covers All Registered Skills | 9.71 | 9.0 | ✓ |
| SME Critique LLM Enrichment Wired | 10.00 | 8.0 | ✓ |
| Root-Cause LLM Enrichment Wired | 10.00 | 8.0 | ✓ |

### AG_04 — Semantic Skill Discovery Wired [PASS ✓]
**Score**: 10.00/10  **Threshold**: 9.0
**Finding**: 9/9 skill discovery checks pass
**Detail**: Missing: none
**Remediation**: Skill discovery fully implemented.

### AG_05 — _DEP_MAP Covers All Registered Skills [PASS ✓]
**Score**: 9.71/10  **Threshold**: 9.0
**Finding**: 34/35 analysis skills in _DEP_MAP
**Detail**: Missing from _DEP_MAP: ['my-new-skill']
**Remediation**: Add to _DEP_MAP with correct deps: ['my-new-skill']

### AG_06 — SME Critique LLM Enrichment Wired [PASS ✓]
**Score**: 10.00/10  **Threshold**: 8.0
**Finding**: 6/6 SME enrichment checks pass
**Detail**: Missing: none
**Remediation**: SME critique LLM enrichment fully wired.

### AG_07 — Root-Cause LLM Enrichment Wired [PASS ✓]
**Score**: 10.00/10  **Threshold**: 8.0
**Finding**: 5/5 root-cause enrichment checks pass
**Detail**: Missing: none
**Remediation**: Root-cause LLM enrichment fully wired.

---

## Safety & Provenance

Domain score: **10.00/10** (PASS ✓)

| Dimension | Score | Threshold | Status |
|-----------|-------|-----------|--------|
| Offline Guard and Injectable Transport | 10.00 | 9.0 | ✓ |
| Numeric Provenance on Opportunity Assessment | 10.00 | 9.0 | ✓ |
| Audit Trail for LLM Numeric Adjustments | 10.00 | 8.0 | ✓ |

### AG_08 — Offline Guard and Injectable Transport [PASS ✓]
**Score**: 10.00/10  **Threshold**: 9.0
**Finding**: 7/7 offline guard / transport checks pass
**Detail**: Missing: none
**Remediation**: Offline guard and injectable transport fully implemented.

### AG_09 — Numeric Provenance on Opportunity Assessment [PASS ✓]
**Score**: 10.00/10  **Threshold**: 9.0
**Finding**: 8/8 provenance checks pass
**Detail**: Missing: none
**Remediation**: Numeric provenance fully implemented.

### AG_10 — Audit Trail for LLM Numeric Adjustments [PASS ✓]
**Score**: 10.00/10  **Threshold**: 8.0
**Finding**: 7/7 audit trail checks pass
**Detail**: Missing: none
**Remediation**: Audit trail fully implemented.
