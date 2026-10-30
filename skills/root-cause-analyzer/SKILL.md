---
name: root-cause-analyzer
description: "Diagnose why spend categories benchmark above peers and map each finding to an actionable lever with timeline, complexity, and addressable spend. Use when the user asks 'why are we overspending', 'root cause analysis', 'what is driving the gap', 'diagnostic findings', or after spend-profiler and peer-benchmarker have run. Required upstream input for savings-modeler and value-bridge-calculator."
kind: analysis
runtime: python
discoverable: true
weight: heavy
version: "0.1.0"
status: active
---

# Root Cause Analyzer

Applies threshold-based diagnostics to categorized spend and benchmark gaps to produce lever-mapped root-cause findings.

## Inputs

- `spend-profiler` — category spend, supplier concentration (HHI), maverick spend signals.
- `peer-benchmarker` — percentile bands and gap-to-median by category.
- Optional: headcount, transaction_count, annual_revenue from session manifest.

## Outputs

- `root_cause_findings` — per category: diagnosis, lever_id, addressable_spend, severity, evidence signals.
- `diagnostic_summary` — counts by finding type (fragmentation, maverick, peer gap, etc.).

## Methodology

1. **Load thresholds** — read `references/diagnostic_thresholds.json` (HHI fragmentation/concentration, maverick tiers, spend floors).
2. **Evaluate peer gaps** — flag categories in P50–P75, P75–P90, P90+ bands vs peer benchmarks.
3. **Supplier structure** — compute HHI per category; flag fragmentation (low HHI + min suppliers + min spend) or concentration risk.
4. **Maverick spend** — graduated severity (warning/elevated/critical) when maverick ratio exceeds tier thresholds.
5. **Map to levers** — attach addressable_rates and lever_id from threshold config for downstream savings-modeler.
6. **Emit findings** — structured list consumed by savings-modeler and value-bridge-calculator.

Implementation: `app/skills/engine/benchmarking.py:root_cause_analyzer()` via `app/skills/dispatch.py` handler.
