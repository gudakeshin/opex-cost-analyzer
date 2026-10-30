# OpEx Platform — Spend Categorization Eval

**Date:** 2026-10-30  |  **Micro-F1:** 0.935  |  **Macro-F1:** 0.944  |  **Status:** ✅ PASS

> **SCOPE:** This eval measures **keyword-classifier accuracy** — whether
> `ingestion.py::_classify` maps spend descriptions to the correct taxonomy
> category. It does NOT validate savings recommendations, benchmark accuracy,
> or analytical quality. A score of 1.0 here means the classifier works;
> it says nothing about whether the savings opportunities are correct.

**Golden set:** 77 labeled lines  |  **Correct:** 72 (93.5%)  |  **Pass threshold:** micro-F1 ≥ 0.8

## Per-Category Results

| Category | Precision | Recall | F1 | Support | TP | FP | FN |
|----------|-----------|--------|----|---------|----|----|----|
| PROF_SVCS | 1.00 | 1.00 | 1.00 | 6 | 6 | 0 | 0 |
| FACILITIES | 1.00 | 1.00 | 1.00 | 6 | 6 | 0 | 0 |
| TRAVEL | 1.00 | 1.00 | 1.00 | 5 | 5 | 0 | 0 |
| LOGISTICS | 1.00 | 1.00 | 1.00 | 5 | 5 | 0 | 0 |
| INSURANCE | 1.00 | 1.00 | 1.00 | 4 | 4 | 0 | 0 |
| OFFICE | 1.00 | 1.00 | 1.00 | 5 | 5 | 0 | 0 |
| POWER_ENERGY | 1.00 | 1.00 | 1.00 | 4 | 4 | 0 | 0 |
| OUTSOURCED | 1.00 | 1.00 | 1.00 | 3 | 3 | 0 | 0 |
| OTHER | 1.00 | 1.00 | 1.00 | 2 | 2 | 0 | 0 |
| TELECOM | 0.83 | 1.00 | 0.91 | 5 | 5 | 1 | 0 |
| IT | 0.90 | 0.90 | 0.90 | 10 | 9 | 1 | 1 |
| RND | 0.80 | 1.00 | 0.89 | 4 | 4 | 1 | 0 |
| MARKETING | 1.00 | 0.78 | 0.88 | 9 | 7 | 0 | 2 |
| CONTINGENT | 1.00 | 0.75 | 0.86 | 4 | 3 | 0 | 1 |
| HR | 0.67 | 0.80 | 0.73 | 5 | 4 | 2 | 1 |

**Micro-F1:** 0.935  |  **Macro-F1:** 0.944  |  **Edge-case accuracy:** 62.5% (3 wrong of 8 edge cases)

## Misclassifications

| Description | Supplier | Expected | Predicted | Note |
|-------------|----------|----------|-----------|------|
| LinkedIn Recruiter license | LinkedIn India | HR | IT | clear |
| Temporary staffing — peak season | Manpower India | CONTINGENT | HR | clear |
| Voice of customer research study | Kantar India | MARKETING | TELECOM | false+ |
| Mobile application development | ThoughtWorks India | IT | HR | false+ |
| Consumer market research report | Nielsen India | MARKETING | RND | false+ |
