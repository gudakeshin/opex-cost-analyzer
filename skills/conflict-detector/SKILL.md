---
name: conflict-detector
description: "Scan spend data drawn from multiple source systems for conflicts — TDS withholding mismatches, GST discrepancies, duplicate vendors, and intercompany / related-party inflation — then propose resolution strategies. Use when the user uploads data from 2+ source systems and asks to 'find conflicts', 'reconcile mismatches', 'check for duplicates', 'TDS/GST mismatch', or 'intercompany'. Powers the conflict_review intent and the /api/v1/conflicts endpoints."
---

# Conflict Detector

You reconcile spend that arrives from more than one system of record (ERP, AP ledger, bank statements, GST portal) and surface the discrepancies that distort a clean spend picture.

## When to Use

Trigger when `≥2` source systems are present and the user asks about conflicts, mismatches, duplicates, reconciliation, TDS/GST discrepancies, or intercompany inflation.

## Prerequisites

- Normalized spend lines with `source_system_id` populated across multiple systems.
- Where available: GSTIN, TDS fields, legal-entity identifiers.

## Conflict Types Detected

- **TDS mismatch** — withholding inconsistent across the gross/net booking of the same invoice.
- **GST discrepancy** — tax treatment differs between source systems for the same transaction.
- **Duplicate vendor** — same supplier under different names/IDs (GSTIN-based clustering).
- **Intercompany inflation** — related-party transactions inflating consolidated spend.

## Outputs

- Conflict list with `conflict_id`, type, severity, affected lines, and a recommended `resolution_strategy` (e.g. `tds_gross_up`, `gstin_dedup`, `eliminate_intercompany`, `escalate`).
- Summary by type and severity; counts of auto-resolvable vs. escalation-required.

## Edge Cases

- Single source system → return zero conflicts with an explicit reason (nothing to reconcile).
- Low-confidence duplicate matches → mark for human review rather than auto-merge.
