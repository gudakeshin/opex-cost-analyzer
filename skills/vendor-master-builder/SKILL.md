---
name: vendor-master-builder
description: "Deduplicate vendors across all data sources by GSTIN / normalized name and build a canonical vendor master with consolidated spend per supplier. Use when the user asks for a 'vendor master', 'vendor dedup', 'duplicate vendors', 'canonical supplier list', 'how many real vendors do we have', or 'consolidate suppliers'. Always useful as a precursor to negotiation and tail-spend rationalization. Powers the vendor_master intent."
---

# Vendor Master Builder

You collapse the messy reality of supplier records — the same vendor spelled five ways across three systems — into one canonical vendor master so spend-per-supplier is finally accurate.

## When to Use

Trigger on: "vendor master", "vendor dedup", "duplicate vendor", "canonical vendor", "how many suppliers", "consolidate vendors", "tail spend".

## Prerequisites

- Normalized spend lines with supplier name and, where available, GSTIN / vendor ID.

## Method

1. Cluster supplier records by GSTIN (authoritative) then by normalized name similarity.
2. Elect a canonical record per cluster and map aliases to it.
3. Aggregate spend, transaction count, and category mix per canonical vendor.
4. Surface fragmentation: vendors with many aliases, and tail vendors below a spend threshold.

## Outputs

- Canonical vendor master (canonical id/name, aliases, GSTIN, total spend, txn count).
- Dedup summary: raw vendor count → canonical count, aliases merged.
- Tail-spend and fragmentation candidates for consolidation.

## Edge Cases

- No GSTIN → fall back to fuzzy name matching at a conservative threshold; flag low-confidence merges.
- Genuinely distinct entities sharing a name → keep separate when GSTIN differs.
