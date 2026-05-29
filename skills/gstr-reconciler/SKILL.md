---
name: gstr-reconciler
description: "Reconcile accounts-payable books against GSTR-2A / 2B data to identify Input Tax Credit (ITC) at risk and quantify the GST recovery opportunity. Use when the user asks about 'GSTR reconciliation', 'GST reconcile', 'GSTR-2A/2B', 'ITC reconciliation', 'input tax credit', or 'GST recovery'. Reads GST fields on spend lines plus supplied gstr_2a_data. Powers the gstr_reconcile intent."
---

# GSTR Reconciler

You match a company's purchase register against the GST portal's auto-populated GSTR-2A/2B to find input tax credit that is unclaimed, mismatched, or at risk of denial.

## When to Use

Trigger on: "GSTR reconcile", "GST reconciliation", "GSTR-2A", "GSTR-2B", "ITC reconciliation", "input tax credit", "GST recovery".

## Prerequisites

- Spend lines with GST fields (GSTIN, invoice number, taxable value, tax amount).
- `gstr_2a_data` supplied via the manifest (the portal-side records to match against).

## Method

1. Match AP invoices to GSTR-2A/2B records by GSTIN + invoice number + value.
2. Classify each line: **matched**, **mismatched** (value/tax differs), **in books not in portal** (ITC at risk), **in portal not in books** (unrecorded).
3. Quantify ITC at risk and the recoverable opportunity.

## Outputs

- Reconciliation summary by status with counts and tax value.
- ITC at risk total and recoverable opportunity.
- Exception list of mismatches needing vendor follow-up.

## Edge Cases

- No `gstr_2a_data` → return "portal data not provided; cannot reconcile" rather than guessing.
- Missing GSTIN on a line → route to exceptions, not to a match.
