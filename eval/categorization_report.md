# OpEx Platform — Spend Categorization Eval

**Date:** 2026-06-10  |  **Micro-F1:** 0.896  |  **Macro-F1:** 0.907  |  **Status:** ✅ PASS

> **SCOPE:** This eval measures **keyword-classifier accuracy** — whether
> `ingestion.py::_classify` maps spend descriptions to the correct taxonomy
> category. It does NOT validate savings recommendations, benchmark accuracy,
> or analytical quality. A score of 1.0 here means the classifier works;
> it says nothing about whether the savings opportunities are correct.

**Golden set:** 77 labeled lines  |  **Correct:** 69 (89.6%)  |  **Pass threshold:** micro-F1 ≥ 0.8

## Per-Category Results

| Category | Precision | Recall | F1 | Support | TP | FP | FN |
|----------|-----------|--------|----|---------|----|----|----|
| LOGISTICS | 1.00 | 1.00 | 1.00 | 5 | 5 | 0 | 0 |
| INSURANCE | 1.00 | 1.00 | 1.00 | 4 | 4 | 0 | 0 |
| OFFICE | 1.00 | 1.00 | 1.00 | 5 | 5 | 0 | 0 |
| POWER_ENERGY | 1.00 | 1.00 | 1.00 | 4 | 4 | 0 | 0 |
| OUTSOURCED | 1.00 | 1.00 | 1.00 | 3 | 3 | 0 | 0 |
| OTHER | 1.00 | 1.00 | 1.00 | 2 | 2 | 0 | 0 |
| PROF_SVCS | 0.86 | 1.00 | 0.92 | 6 | 6 | 1 | 0 |
| IT | 0.90 | 0.90 | 0.90 | 10 | 9 | 1 | 1 |
| TRAVEL | 1.00 | 0.80 | 0.89 | 5 | 4 | 0 | 1 |
| RND | 0.80 | 1.00 | 0.89 | 4 | 4 | 1 | 0 |
| FACILITIES | 0.75 | 1.00 | 0.86 | 6 | 6 | 2 | 0 |
| CONTINGENT | 1.00 | 0.75 | 0.86 | 4 | 3 | 0 | 1 |
| MARKETING | 0.88 | 0.78 | 0.82 | 9 | 7 | 1 | 2 |
| TELECOM | 0.80 | 0.80 | 0.80 | 5 | 4 | 1 | 1 |
| HR | 0.75 | 0.60 | 0.67 ⚠️ | 5 | 3 | 1 | 2 |

**Micro-F1:** 0.896  |  **Macro-F1:** 0.907  |  **Edge-case accuracy:** 62.5% (3 wrong of 8 edge cases)

## Misclassifications

| Description | Supplier | Expected | Predicted | Note |
|-------------|----------|----------|-----------|------|
| Cab and taxi reimbursements | Ola Corporate | TRAVEL | PROF_SVCS | clear |
| LinkedIn Recruiter license | LinkedIn India | HR | IT | clear |
| Payroll processing services | ADP India | HR | MARKETING | clear |
| MPLS leased line | Tata Communications | TELECOM | FACILITIES | clear |
| Contract worker placement | TeamLease Services | CONTINGENT | FACILITIES | clear |
| Voice of customer research study | Kantar India | MARKETING | TELECOM | false+ |
| Mobile application development | ThoughtWorks India | IT | HR | false+ |
| Consumer market research report | Nielsen India | MARKETING | RND | false+ |

## Categories Below 0.70 F1

These categories have low classification accuracy and may produce incorrect savings analysis.

### HR — F1 0.67 (P=0.75, R=0.60)

**Missed (FN):** "LinkedIn Recruiter license"; "Payroll processing services"

**Wrong prediction (FP):** "Mobile application development" → predicted HR
