# OpEx Platform Feature Completeness Eval

**Eval date**: 2026-10-30  
**Platform version**: 2.0  
**Overall score**: 9.65/10  
**Status**: PASS ✓

> ⚠️ **SCORE TYPE: STRUCTURAL** — This score measures skill wiring, API route coverage,
> and OPAR completeness. It does NOT validate whether analysis content is correct.
> See `run_llm_judge_eval.py` for content-quality assessment.

---

## Domain Summary

| Domain | Score | Status |
|--------|-------|--------|
| Skill Pipeline Completeness (w=0.35) | 10.00/10 | PASS ✓ |
| Frontend-Backend API Connectivity (w=0.35) | 9.00/10 | PASS ✓ |
| OPAR Loop Completeness (w=0.20) | 10.00/10 | PASS ✓ |
| Infrastructure Completeness (w=0.10) | 10.00/10 | PASS ✓ |

---

## Top Gaps (ranked by severity)

### API_04 — FP&A Endpoint Wiring Completeness
- **Score**: 5.00/10 (threshold 9.0, gap 4.00)
- **Finding**: 3/6 FP&A endpoint check-points pass (backend+frontend per endpoint)
- **Remediation**: Wire missing FP&A endpoints: ['trends (frontend missing)', 'bva (frontend missing)', 'payment-terms (frontend missing)'].

---

## Skill Pipeline Completeness

Domain score: **10.00/10** (PASS ✓)

| Dimension | Score | Threshold | Status |
|-----------|-------|-----------|--------|
| Skill Directory-to-Dispatch Parity | 10.00 | 9.0 | ✓ |
| Dispatch Handler Implementation Depth | 10.00 | 8.0 | ✓ |
| Skill Output Contract Coverage | 10.00 | 7.0 | ✓ |
| OPAR Intent-to-Plan Mapping Coverage | 10.00 | 8.0 | ✓ |

### SP_01 — Skill Directory-to-Dispatch Parity

**Score**: 10.00/10 (threshold 9.0) — PASS ✓

**Finding**: 40/40 skills registered in dispatch.py

**Detail**: Found 40 skills/ dirs with SKILL.md. 40 are registered via @register() in dispatch.py. Unregistered (dead code): none.

**Remediation**: All skills registered. Add CI parity check to prevent future drift.

### SP_02 — Dispatch Handler Implementation Depth

**Score**: 10.00/10 (threshold 8.0) — PASS ✓

**Finding**: 41/41 handlers implemented (≥5 lines or engine delegation)

**Detail**: Checked 41 @register() handlers. 41 have substantive dispatch logic or delegate to app.skills.engine. Potential stubs: none.

**Remediation**: All handlers appear substantively implemented.

### SP_03 — Skill Output Contract Coverage

**Score**: 10.00/10 (threshold 7.0) — PASS ✓

**Finding**: 41/41 registered skills have output contracts (or intentionally use inline dict)

**Detail**: Checked contracts.py for Output class per registered skill. Skills missing a dedicated contract class: none. Skills intentionally using inline dict (no dedicated class): ['my-new-skill', 'cohort-segmenter', 'root-cause-analyzer', 'savings-modeler', 'data-validator', 'data-quality-gate', 'evidence-gatherer', 'sme-critique', 'chart-builder', 'business-case-builder', 'pii-stripper', 'data-classifier', 'llm-context-builder', 'assumption-register', 'indian-tax-optimizer', 'brsr-cobenefit-calculator', 'scenario-modeler', 'sensitivity-analyzer', 'value-to-shareholder-bridge', 'peer-disclosure-miner', 'conflict-detector', 'vendor-master-builder', 'consolidation-analyzer', 'msme-compliance-checker', 'contract-lifecycle-manager', 'gstr-reconciler', 'zbb-modeler', 'cost-to-serve-analyzer', 'dashboard-builder', 'export-formatter'].

**Remediation**: Contract coverage adequate. Consider adding classes for inline-dict skills.

### SP_04 — OPAR Intent-to-Plan Mapping Coverage

**Score**: 10.00/10 (threshold 8.0) — PASS ✓

**Finding**: 19/19 IntentClass values handled in plan.py

**Detail**: Extracted 19 IntentClass values from models.py. Searched plan.py for each as a string literal. Unhandled (fall through to generic_qa): none.

**Remediation**: All intents handled in plan.py.

---

## Frontend-Backend API Connectivity

Domain score: **9.00/10** (PASS ✓)

| Dimension | Score | Threshold | Status |
|-----------|-------|-----------|--------|
| Frontend Call Resolution Rate | 10.00 | 9.0 | ✓ |
| Backend Feature Frontend Exposure | 10.00 | 6.0 | ✓ |
| API Version Consistency | 10.00 | 6.0 | ✓ |
| FP&A Endpoint Wiring Completeness | 5.00 | 9.0 | ✗ |

### API_01 — Frontend Call Resolution Rate

**Score**: 10.00/10 (threshold 9.0) — PASS ✓

**Finding**: 73/73 unique frontend API calls resolve to a backend route

**Detail**: Scanned all .tsx/.ts files under frontend/src for apiGet/apiPost/apiPut/apiUpload calls and href=/api/... links. Found 73 unique paths. Unresolved (would 404): none.

**Remediation**: All frontend calls resolve. No broken links.

### API_02 — Backend Feature Frontend Exposure

**Score**: 10.00/10 (threshold 6.0) — PASS ✓

**Finding**: 8/8 backend feature groups have at least one frontend page calling them

**Detail**: Checked 8 backend feature groups for at least one matching frontend API call. Groups with NO frontend exposure: none.

**Remediation**: All backend feature groups have frontend coverage.

### API_03 — API Version Consistency

**Score**: 10.00/10 (threshold 6.0) — PASS ✓

**Finding**: 73/73 unique frontend API calls use /api/v1/ prefix

**Detail**: Backend marks /api/ (unversioned) paths as deprecated (Sunset: 2027-01-01). 0 frontend calls still use the deprecated /api/ prefix: [].

**Remediation**: All frontend calls use /api/v1/ prefix.

### API_04 — FP&A Endpoint Wiring Completeness

**Score**: 5.00/10 (threshold 9.0) — FAIL ✗

**Finding**: 3/6 FP&A endpoint check-points pass (backend+frontend per endpoint)

**Detail**: Checked 3 FP&A endpoints for presence in app/routers/outputs.py (backend) and frontend/src/pages/CostRoom.tsx (frontend). Missing: ['trends (frontend missing)', 'bva (frontend missing)', 'payment-terms (frontend missing)'].

**Remediation**: Wire missing FP&A endpoints: ['trends (frontend missing)', 'bva (frontend missing)', 'payment-terms (frontend missing)'].

---

## OPAR Loop Completeness

Domain score: **10.00/10** (PASS ✓)

| Dimension | Score | Threshold | Status |
|-----------|-------|-----------|--------|
| Phase Module Non-Empty Coverage | 10.00 | 9.0 | ✓ |
| Intent Handler Coverage in Plan | 10.00 | 8.0 | ✓ |
| Quality Gate Coverage in Reflect | 10.00 | 8.0 | ✓ |

### OPAR_01 — Phase Module Non-Empty Coverage

**Score**: 10.00/10 (threshold 9.0) — PASS ✓

**Finding**: 4/4 OPAR phase modules exist with >100 lines

**Detail**: Checked app/opar/observe.py, plan.py, act.py, reflect.py for existence and line count >100. Thin/missing: none. observe: 742 lines, plan: 1031 lines, act: 362 lines, reflect: 362 lines

**Remediation**: All 4 OPAR phase modules are substantively implemented.

### OPAR_02 — Intent Handler Coverage in Plan

**Score**: 10.00/10 (threshold 8.0) — PASS ✓

**Finding**: 19/19 IntentClass values have a plan branch in plan.py

**Detail**: 19 IntentClass values in models.py. plan.py references 19 as string literals. Not referenced (fallback to generic_qa): none.

**Remediation**: Full intent coverage in plan.py.

### OPAR_03 — Quality Gate Coverage in Reflect

**Score**: 10.00/10 (threshold 8.0) — PASS ✓

**Finding**: 3/3 required quality gate symbols present across 11 reflect*.py module(s)

**Detail**: Searched 11 reflect*.py module(s) for ['validate_core_skill_outputs', 'savings', 'peer_benchmarker']. Present: ['validate_core_skill_outputs', 'savings', 'peer_benchmarker']. Missing: none.

**Remediation**: All required quality gate references present in app/opar/reflect*.py modules.

---

## Infrastructure Completeness

Domain score: **10.00/10** (PASS ✓)

| Dimension | Score | Threshold | Status |
|-----------|-------|-----------|--------|
| Connector Method Completeness | 10.00 | 8.0 | ✓ |
| Health Endpoint Coverage | 10.00 | 9.0 | ✓ |
| Rate Limit Coverage for LLM Endpoints | 10.00 | 6.0 | ✓ |

### INFRA_01 — Connector Method Completeness

**Score**: 10.00/10 (threshold 8.0) — PASS ✓

**Finding**: 6/6 connectors have at least one required entry-point method

**Detail**: Checked for def ingest/fetch/authenticate/connect in each connector. Missing: none.

**Remediation**: All connectors have entry-point methods.

### INFRA_02 — Health Endpoint Coverage

**Score**: 10.00/10 (threshold 9.0) — PASS ✓

**Finding**: /health: ✓, /health/ready: ✓

**Detail**: Searched app/main.py for @app.get('/health') and @app.get('/health/ready'). Missing: none.

**Remediation**: Both health endpoints present.

### INFRA_03 — Rate Limit Coverage for LLM Endpoints

**Score**: 10.00/10 (threshold 6.0) — PASS ✓

**Finding**: Global limiter: ✓ (+7), per-route limiter in chat: ✓ (+3)

**Detail**: Checked for a Limiter() instantiation (in main.py or app/ratelimit.py) attached via app.state.limiter in main.py, and chat.py for @limiter.limit() per-route decorators on LLM endpoints.

**Remediation**: Rate limiting fully configured.

---

## Remediation Roadmap

**1.** `api_04` — Wire missing FP&A endpoints: ['trends (frontend missing)', 'bva (frontend missing)', 'payment-terms (frontend missing)'].  
*Closes gap of 4.0 pts (severity 0.2800)*
