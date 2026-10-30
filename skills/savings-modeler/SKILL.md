---
name: savings-modeler
description: "Convert root-cause findings and benchmark gaps into a phased 3-year savings model with cost-to-achieve, net savings, NPV, payback, and initiative-level execution probabilities. Use when the user asks to 'model savings', 'build the value case', 'NPV of initiatives', 'phased savings', 'cost to achieve', or after root-cause-analyzer and benchmarking skills have run. Feeds value-bridge-calculator, scenario-modeler, evidence-gatherer, and sensitivity-analyzer."
kind: analysis
runtime: python
discoverable: true
weight: heavy
version: "0.1.0"
status: active
---

# Savings Modeler

Converts diagnostic and benchmark outputs into a portfolio of savings initiatives with phased gross/net savings, implementation cost, NPV, and payback.

## Inputs

- `root-cause-analyzer` — root_cause_findings with lever mappings per category.
- `peer-benchmarker`, `internal-benchmarker`, `heuristic-analyzer` — combined into raw savings rows.
- `spend-profiler` — category spend, addressability, and data-quality inputs.
- Optional: `document-contextualizer` for signal corpus; session manifest for WACC, tax rate, planning horizon.

## Outputs

- `initiatives` — per-lever savings with gross_savings (y1/y2/y3), net_savings, cost_to_achieve, NPV, payback_months, bounce_back_risk, base_execution_probability.
- `portfolio_summary` — total gross/net 3yr, NPV, payback, initiative count.
- `assumptions` — discount rate, tax rate, phasing curves applied.

## Methodology

1. **Build raw rows** — merge peer, internal, and heuristic gap rows via `build_raw_rows()`.
2. **Resolve eligible levers** — filter by industry sector pack, spend profile signals, and root-cause findings.
3. **Size initiatives** — apply lever ranges from `model_parameters.json`, sustainability haircuts, and org-change-risk adjustments.
4. **Phase savings** — apply phasing curves and implementation cost phasing (Y1/Y2/Y3 gross and net).
5. **Compute financials** — NPV at session WACC, payback months, bounce-back risk label per initiative.
6. **Emit portfolio** — structured dict consumed by value-bridge-calculator and downstream FP&A skills.

Implementation: `app/skills/engine/savings.py:savings_modeler()` via `app/skills/dispatch.py` handler.
