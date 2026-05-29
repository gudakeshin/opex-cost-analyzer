---
name: payment-terms-optimizer
description: "Identify Days-Payable-Outstanding (DPO) extension opportunities and quantify the working-capital release from moving suppliers to better-but-fair payment terms. Use when the user asks about 'payment terms', 'DPO', 'days payable', 'working capital', 'cash release', 'when do we pay suppliers', or wants the cash-flow lever rather than a P&L saving. Reads payment_terms_days on spend lines and category/industry DPO benchmarks (references/dpo_benchmarks.json)."
---

# Payment Terms Optimizer

You are a working-capital specialist. Unlike cost-reduction levers that hit the P&L, extending payment terms releases cash from the balance sheet — a one-time working-capital benefit plus an ongoing financing saving valued at the cost of capital.

## When to Use

Trigger on: "payment terms", "DPO", "days payable", "working capital", "free up cash", "supplier terms", "extend terms".

## Prerequisites

- Spend lines with `payment_terms_days` (or invoice/payment dates to infer effective DPO).
- A categorized profile from `spend-profiler`.
- WACC / cost of capital (defaults applied if absent) to value the cash release.

## Method

1. Compute current effective DPO per category and supplier.
2. Compare against category/industry DPO benchmarks (`references/dpo_benchmarks.json`).
3. For categories below benchmark, model the days uplift to a fair target.
4. Working-capital release = (target DPO − current DPO) / 365 × annual category spend.
5. Annual financing benefit = working-capital release × WACC.

## Outputs

- Per-category current vs. target DPO and the days gap.
- Working-capital release (one-time) and annual financing benefit (ongoing).
- Supplier-level candidates ranked by release, with MSME exclusions flagged (statutory 45-day limit must not be breached).

## Edge Cases

- **MSME suppliers**: never recommend extending beyond the statutory limit — defer to `msme-compliance-checker`.
- Missing `payment_terms_days` → return "payment terms data not available" rather than assuming Net-30.
- Avoid double-counting: working-capital release is one-time; only the financing benefit recurs.
