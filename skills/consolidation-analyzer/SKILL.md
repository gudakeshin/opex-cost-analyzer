---
name: consolidation-analyzer
description: "Roll up spend across multiple legal entities into a consolidated group view, eliminate intercompany transactions, and report consolidation completeness. Use when the user asks for a 'group view', 'consolidate entities', 'multi-entity rollup', 'eliminate intercompany', or uploads data spanning several legal_entity_id values (or supplies an entity tree). Powers the consolidate intent and the /api/v1/consolidate endpoint."
---

# Consolidation Analyzer

You produce a group-level spend view from multiple legal entities, removing intercompany double-counting so leadership sees true external spend.

## When to Use

Trigger on: "consolidate", "group view", "entity rollup", "multi-entity", "intercompany elimination", or when `≥2` legal entities (or an `entity_tree`) are present.

## Prerequisites

- Spend lines with `legal_entity_id` populated, or an explicit `entity_tree`.
- Markers identifying intercompany / related-party lines where available.

## Method

1. Group spend by legal entity and category.
2. Identify and eliminate intercompany transactions to avoid double-counting.
3. Produce consolidated group totals (gross, addressable, intercompany eliminated).
4. Assess completeness — which expected entities reported vs. are missing.
5. Build an entity comparison (per-entity spend, addressable %, category mix).

## Outputs

- Group total spend, addressable spend, intercompany eliminated, addressable %.
- Entity count, completeness coverage %, missing entities.
- Per-entity comparison and top consolidated categories.

## Edge Cases

- Single entity → return `consolidation_available: false` with a clear reason.
- Missing entity tree → infer entities from `legal_entity_id`; flag completeness as estimated.
