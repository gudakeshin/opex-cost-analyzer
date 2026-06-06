---
name: evidence-gatherer
description: "Gather document evidence for modeled savings initiatives using semantic RAG over engagement uploads. Use after savings-modeler when initiatives need contract, policy, or procurement document support before SME critique or business-case commitment."
---

# Evidence Gatherer

Retrieves and ranks document excerpts that support or challenge each modeled savings initiative.

## When to Use

- After `savings-modeler` produces initiatives that will be presented to leadership.
- Before `sme-critique` when document context may qualify addressability or timing.
- When the user asks whether savings are backed by contracts, policies, or vendor agreements.

## Inputs

- `savings-modeler` — initiatives to gather evidence for.
- `spend-profiler` — category and supplier context for retrieval queries.
- Optional upstream: `root-cause-analyzer`, `peer-benchmarker`, `contract-lifecycle-manager`.

## Outputs

- Evidence items per initiative with document provenance (`filename`, heading path).
- Coverage summary (supported / partial / missing evidence).
- Retrieval queries used for audit replay.

## Methodology

1. Build retrieval queries from initiative lever, category, and supplier names.
2. Semantic search via `retrieve_context(engagement_id, query)`.
3. Score relevance and attach provenance labels for downstream SME critique.
