---
name: sensitivity-analyzer
description: "Compute NPV and savings what-if scenarios (conservative, accelerated, bounce-back, regulatory headwind, custom). Use when the user asks for sensitivity analysis, stress tests, or scenario NPV comparisons after value bridge modeling."
---

# Sensitivity Analyzer

Deterministic wrapper around `compute_sensitivity()`:

- Nine built-in scenarios plus optional custom what-if rows
- Phased NPV from savings-modeler when available
- Portfolio drivers: execution rate, headcount/revenue growth, timeline compression

Requires `value-bridge-calculator` (and benefits from `savings-modeler`).
