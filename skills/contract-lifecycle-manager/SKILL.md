---
name: contract-lifecycle-manager
description: "Surface contract renewals, auto-renewal risk, exit-penalty exposure, and the share of spend locked in by current contract commitments. Use when the user asks about 'contract review', 'contract lifecycle', 'upcoming renewals', 'auto-renewal', 'exit penalty', 'lock-in', or 'what spend is contractually committed'. Reads contract fields (expiry date, status, auto-renewal, notice period) on spend lines."
---

# Contract Lifecycle Manager

You give procurement a forward view of the contract estate: what renews when, where auto-renewal could lock in unfavourable terms, and how much addressable spend is actually free to move.

## When to Use

Trigger on: "contract review", "renewals", "auto-renewal", "exit penalty", "notice period", "contract expiry", "locked-in spend".

## Prerequisites

- Spend lines carrying contract metadata: `contract_expiry_date`, `contract_status`, and where available auto-renewal flag, notice period, exit penalty.

## Method

1. Build a renewal calendar from expiry dates (next 3 / 6 / 12 months).
2. Flag auto-renewing contracts whose notice window is approaching — these need action now.
3. Quantify exit-penalty exposure for early termination.
4. Compute spend addressable vs. contractually locked-in by category.

## Outputs

- Renewal timeline with value at each window.
- Auto-renewal risk list (contract, notice deadline, value).
- Exit-penalty exposure total and by contract.
- Locked-in vs. free-to-move spend split.

## Edge Cases

- No contract fields present → return "contract data not available"; do not infer terms.
- Expired-but-active contracts → flag as evergreen/auto-renewed and prioritise.
