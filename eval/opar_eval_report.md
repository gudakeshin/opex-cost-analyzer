# OPAR Loop Eval Report

**Eval date:** 2026-05-24  
**Overall score:** 10.000 / 10  
**Status:** PASS

## Summary

| ID | Dimension | Domain | Score | Threshold | Status | Cases |
|----|-----------|--------|-------|-----------|--------|-------|
| OB_01 | Intent Classification Accuracy | observe | 10.00 | 8.5 | PASS | 20/20 |
| OB_02 | Clarification Gate Correctness | observe | 10.00 | 9.0 | PASS | 8/8 |
| OB_03 | Query Capability Detection | observe | 10.00 | 8.0 | PASS | 10/10 |
| OB_04 | Context Assembly Correctness | observe | 10.00 | 8.0 | PASS | 10/10 |
| PL_01 | Skill DAG Correctness | plan | 10.00 | 8.5 | PASS | 12/12 |
| PL_02 | Group 0 Security Skill Injection | plan | 10.00 | 9.0 | PASS | 6/6 |
| PL_03 | DAG Dependency Group Ordering | plan | 10.00 | 10.0 | PASS | 6/6 |
| PL_04 | Replanner Branch Logic | plan | 10.00 | 7.5 | PASS | 7/7 |
| OR_01 | No-Data Orchestrator Routing | orchestrator | 10.00 | 8.5 | PASS | 15/15 |
| OR_02 | General QA Answer Quality | orchestrator | 10.00 | 7.5 | PASS | 8/8 |

---

## Dimension Details

### Observe (score: 10.00)

#### OB_01: Intent Classification Accuracy
- **Score:** 10.000 / 8.5 (weight 0.15) — **PASS**
- **Cases:** 20/20
- **Finding:** 20/20 cases correct

#### OB_02: Clarification Gate Correctness
- **Score:** 10.000 / 9.0 (weight 0.12) — **PASS**
- **Cases:** 8/8
- **Finding:** 8/8 cases correct

#### OB_03: Query Capability Detection
- **Score:** 10.000 / 8.0 (weight 0.08) — **PASS**
- **Cases:** 10/10
- **Finding:** 10/10 cases correct

#### OB_04: Context Assembly Correctness
- **Score:** 10.000 / 8.0 (weight 0.10) — **PASS**
- **Cases:** 10/10
- **Finding:** 10/10 cases correct

### Plan (score: 10.00)

#### PL_01: Skill DAG Correctness
- **Score:** 10.000 / 8.5 (weight 0.18) — **PASS**
- **Cases:** 12/12
- **Finding:** 12/12 cases correct

#### PL_02: Group 0 Security Skill Injection
- **Score:** 10.000 / 9.0 (weight 0.10) — **PASS**
- **Cases:** 6/6
- **Finding:** 6/6 cases correct

#### PL_03: DAG Dependency Group Ordering
- **Score:** 10.000 / 10.0 (weight 0.08) — **PASS**
- **Cases:** 6/6
- **Finding:** 6/6 cases correct

#### PL_04: Replanner Branch Logic
- **Score:** 10.000 / 7.5 (weight 0.09) — **PASS**
- **Cases:** 7/7
- **Finding:** 7/7 cases correct

### Orchestrator (score: 10.00)

#### OR_01: No-Data Orchestrator Routing
- **Score:** 10.000 / 8.5 (weight 0.10) — **PASS**
- **Cases:** 15/15
- **Finding:** 15/15 cases correct

#### OR_02: General QA Answer Quality
- **Score:** 10.000 / 7.5 (weight 0.10) — **PASS**
- **Cases:** 8/8
- **Finding:** 8/8 cases correct
