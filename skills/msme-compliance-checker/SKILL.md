---
name: msme-compliance-checker
description: "Check payment compliance against the Indian MSMED Act (statutory 45-day payment limit for Micro & Small Enterprises) and quantify penal-interest exposure on overdue MSME payables. Use when the user asks about 'MSME compliance', 'MSMED Act', '45-day rule', 'MSME payment', 'penal interest', 'Section 43B(h)', or vendor payment obligations to small suppliers. Reads MSME registration flags and payment timing on spend lines."
---

# MSME Compliance Checker

You protect the company from MSMED Act exposure: payments to registered Micro & Small Enterprises must clear within the statutory window (15 days default, up to 45 with a written agreement), or penal interest and disallowance under Section 43B(h) apply.

## When to Use

Trigger on: "MSME", "MSMED Act", "45-day rule", "small enterprise payment", "penal interest", "Section 43B(h)", "vendor payment compliance".

## Prerequisites

- Spend lines with MSME registration flags (Udyam/MSME status) and invoice/payment dates or `payment_terms_days`.

## Method

1. Identify MSME-registered suppliers.
2. Compute days-to-pay vs. the statutory limit (15/45 days).
3. Flag breaches and compute penal interest exposure (3× bank rate, compounded monthly, per the Act).
4. Estimate Section 43B(h) disallowance risk for unpaid year-end balances.

## Outputs

- MSME supplier list with compliance status (compliant / at-risk / breached).
- Penal-interest exposure and 43B(h) disallowance risk totals.
- Remediation priority by exposure.

## Edge Cases

- No MSME flags present → return "MSME data not available"; never assume MSME status.
- For MSME suppliers, suppress any DPO-extension recommendation from `payment-terms-optimizer`.
