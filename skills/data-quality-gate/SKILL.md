---
name: data-quality-gate
description: "Lightweight data-quality gate after spend profiling — checks field coverage, period completeness, category mapping, and outlier concentration."
kind: quality_gate
version: 0.1.0
status: active
---

# Data Quality Gate

Runs on every analysis that includes spend profiling. Surfaces confidence level and caveats before downstream skills commit to savings or benchmark conclusions.

## Inputs

- `spend-profiler`

## Outputs

- `confidence` — low | mid | high
- `passed` — whether all quality checks passed
- `checks` — per-dimension boolean flags
- `caveats` — human-readable warnings for the advisory layer
