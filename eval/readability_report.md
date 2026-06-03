# Diagnostic Readability Eval — ✅ PASS

**Date:** 2026-06-03  |  **Version:** v2.1  |  **Overall Score:** 10.0/10  |  **Pass threshold:** 7.0/10

## Summary

| Domain | Score | Weight | Status |
|--------|-------|--------|--------|
| Financial Number Formatting | 10.0/10 | 25% | ✅ |
| Label Accuracy & Terminology | 10.0/10 | 25% | ✅ |
| Key Findings Narrative Quality | 10.0/10 | 30% | ✅ |
| Context Completeness | 10.0/10 | 20% | ✅ |

## Dimension Detail

| ID | Dimension | Score | Threshold | Status | Gap |
|----|-----------|-------|-----------|--------|-----|
| RD-01 | Comma Separators in Findings | 10.0 | 8.0 | ✅ | 0.0 |
| RD-02 | NPV Time Horizon Disclosure | 10.0 | 7.0 | ✅ | 0.0 |
| RD-03 | WACC / Discount Rate Visible | 10.0 | 7.0 | ✅ | 0.0 |
| RD-04 | actual_pct Misnomer Detection | 10.0 | 7.0 | ✅ | 0.0 |
| RD-05 | percentile_band Jargon Removal | 10.0 | 7.0 | ✅ | 0.0 |
| RD-06 | savings_type Display Format | 10.0 | 7.0 | ✅ | 0.0 |
| RD-07 | Debug Fields Nested (not top-level) | 10.0 | 6.0 | ✅ | 0.0 |
| RD-08 | Revenue-% Framing in Findings | 10.0 | 7.0 | ✅ | 0.0 |
| RD-09 | Actionability Signal in Findings | 10.0 | 6.0 | ✅ | 0.0 |
| RD-10 | Savings Confidence Range Surfaced | 10.0 | 6.0 | ✅ | 0.0 |
| RD-11 | Assumption Disclosure (WACC, headcount, horizon) | 10.0 | 7.0 | ✅ | 0.0 |
| RD-12 | Document Flags Interpretability | 10.0 | 6.0 | ✅ | 0.0 |
| RD-13 | data_note Specificity | 10.0 | 6.0 | ✅ | 0.0 |
| RD-14 | Eligible Levers Total Disclosed | 10.0 | 6.0 | ✅ | 0.0 |
| RD-15 | Percentile Legend (P25/P50 definitions) | 10.0 | 5.0 | ✅ | 0.0 |

## Findings by Dimension

### RD-01 — Comma Separators in Findings [PASS]

**Score:** 10.0/8.0  |  **Domain:** financial_formatting

PASS — all large monetary figures use comma formatting

**Remediation:** In enterprise.py key_findings assembly, replace :.0f with a helper: def _fmt_cr(n): return f'₹{n:,.0f} Cr'. Apply to all findings strings (top-gap, top-lever, total-value findings).

### RD-02 — NPV Time Horizon Disclosure [PASS]

**Score:** 10.0/7.0  |  **Domain:** financial_formatting

PASS — '3-year' or equivalent appears in findings/data_note

**Remediation:** In enterprise.py top-lever finding, append '3-year NPV' label: f'{lever_name} — {_fmt_cr(p50_cr)} annual savings; {_fmt_cr(npv)} 3-year NPV (P50 estimate)'. Alternatively add to assumptions dict: {npv_horizon_years: 3}.

### RD-03 — WACC / Discount Rate Visible [PASS]

**Score:** 10.0/7.0  |  **Domain:** financial_formatting

PASS — WACC or discount rate disclosed in response

**Remediation:** Add 'assumptions' object to enterprise.py return dict: {'wacc_pct': round(req.wacc * 100, 1), 'headcount': req.headcount, 'npv_horizon_years': 3, 'profile_basis': 'benchmark_proxy'}.

### RD-04 — actual_pct Misnomer Detection [PASS]

**Score:** 10.0/7.0  |  **Domain:** label_accuracy

PASS — actual_pct renamed or proxy disclaimer present

**Remediation:** In enterprise.py benchmark_gaps assembly (line ~328), rename 'actual_pct' → 'proxy_pct'. Or add profile_note field per row: 'profile_note': 'derived from benchmark P50 — not actual spend'.

### RD-05 — percentile_band Jargon Removal [PASS]

**Score:** 10.0/7.0  |  **Domain:** label_accuracy

PASS — percentile_band uses FP&A-readable label

**Remediation:** In enterprise.py line ~334, change: 'percentile_band': 'synthetic_P50' → 'percentile_band': 'P50 industry benchmark (proxy)'

### RD-06 — savings_type Display Format [PASS]

**Score:** 10.0/7.0  |  **Domain:** label_accuracy

PASS — savings_type uses readable labels or savings_type_label field present

**Remediation:** In enterprise.py value_at_table assembly (line ~393), add: _SAVINGS_LABELS = {'run_rate': 'Run Rate', 'one_time': 'One-Time', 'mixed': 'Mixed'} then 'savings_type_label': _SAVINGS_LABELS.get(savings_type, savings_type.replace('_', ' ').title())

### RD-07 — Debug Fields Nested (not top-level) [PASS]

**Score:** 10.0/6.0  |  **Domain:** label_accuracy

PASS — debug fields nested under _meta or absent from FP&A payload

**Remediation:** In enterprise.py return dict, replace top-level url_count/url_errors with: '_meta': {'url_count': len(texts), 'url_errors': url_errors, 'bench_industry': bench_industry}

### RD-08 — Revenue-% Framing in Findings [PASS]

**Score:** 10.0/7.0  |  **Domain:** findings_narrative

PASS — findings include % of revenue framing

**Remediation:** In enterprise.py top-gap finding, add revenue_pct: revenue_pct = round(implied_p50_cr / req.annual_revenue_cr * 100, 1); f'Largest category: {name} — {_fmt_cr(implied_p50_cr)} ({revenue_pct}% of revenue); ...' Similarly for total-value finding: total_pct = round(total_p50 / req.annual_revenue_cr * 100, 1)

### RD-09 — Actionability Signal in Findings [PASS]

**Score:** 10.0/6.0  |  **Domain:** findings_narrative

PASS — findings reference complexity tier or implementation horizon

**Remediation:** In enterprise.py top-lever finding, include complexity_tier: _COMPLEXITY = {'low': 'low complexity', 'medium': 'medium complexity', 'high': 'high complexity'}; f'{lever_name} ({_COMPLEXITY.get(top_lever["complexity_tier"], "medium complexity")}) — ...'

### RD-10 — Savings Confidence Range Surfaced [PASS]

**Score:** 10.0/6.0  |  **Domain:** findings_narrative

PASS — P10/P90 range disclosed in findings

**Remediation:** In enterprise.py key_findings assembly, add: total_p10 = sum(v['p10_cr'] for v in value_at_table); total_p90 = sum(v['p90_cr'] for v in value_at_table); key_findings.append(f'Savings range (P10–P90): {_fmt_cr(total_p10)} to {_fmt_cr(total_p90)}')

### RD-11 — Assumption Disclosure (WACC, headcount, horizon) [PASS]

**Score:** 10.0/7.0  |  **Domain:** findings_narrative

PASS — WACC, headcount, and NPV horizon disclosed

**Remediation:** Add 'assumptions' object to enterprise.py return dict: {'wacc_pct': round(req.wacc * 100, 1), 'headcount': req.headcount, 'npv_horizon_years': 3, 'profile_basis': 'benchmark_proxy'}. This one change resolves RD-03, RD-11, and partially RD-02.

### RD-12 — Document Flags Interpretability [PASS]

**Score:** 10.0/6.0  |  **Domain:** findings_narrative

PASS — constraint findings use descriptive language

**Remediation:** In enterprise.py key_findings assembly (line ~414), replace: 'Document flags: ' + ... with: 'Identified constraints (may affect lever eligibility): ' + ...

### RD-13 — data_note Specificity [PASS]

**Score:** 10.0/6.0  |  **Domain:** context_completeness

PASS — data_note is scenario-specific

**Remediation:** In enterprise.py return dict (line ~431), make data_note conditional: if bench_resolved.get('selected_dataset'): data_note = 'Spend profile derived from ...' else: data_note = f'No benchmark data found for sector {effective_industry!r}; nearest-proxy estimates used. Treat as directional only.'

### RD-14 — Eligible Levers Total Disclosed [PASS]

**Score:** 10.0/6.0  |  **Domain:** context_completeness

PASS — eligible_levers_total field present

**Remediation:** In enterprise.py return dict, add: 'eligible_levers_total': len(eligible_levers). This is already tracked internally as _eligible_levers_total — just expose it.

### RD-15 — Percentile Legend (P25/P50 definitions) [PASS]

**Score:** 10.0/5.0  |  **Domain:** context_completeness

PASS — percentile legend present

**Remediation:** In enterprise.py return dict, add: 'percentile_legend': {'p10': 'top-decile benchmark (stretch target)', 'p25': 'best-in-class quartile', 'p50': 'industry median', 'p90': 'lagging quartile'}

## LLM Enhancement Opportunities

| Priority | Enhancement | Location | Description |
|----------|-------------|----------|-------------|
| LLM-1 (Highest Value) | key_findings narrative via Claude | `app/routers/enterprise.py:401-417` | Replace 4 template strings with claude-haiku-4-5 call. System prompt cached. Generates 5-7 FP&A-grade bullets with %-of-revenue, complexity framing, and assumption disclosure. Fallback: existing templates on LLM failure. |
| LLM-2 (High Value) | Semantic document_contextualizer | `app/skills/engine/profiler.py:document_contextualizer()` | Replace bag-of-words with claude-haiku-4-5 structured extraction: inferred_industry, growth_phase, financial_stress_signals, procurement_maturity, constraints, positive_signals. Guard: skip LLM when texts=[]. Eliminates false positives from short keywords. |
| LLM-3 (Medium Value) | executive_summary field | `app/routers/enterprise.py (new field in return dict)` | 3-sentence CFO paragraph generated post-assembly. Sentence 1: headline opportunity (₹ + % of revenue). Sentence 2: top lever with complexity + payback. Sentence 3: caveat or next step. |
| LLM-4 (Medium Value) | Per-gap benchmark commentary | `app/routers/enterprise.py benchmark_gaps assembly` | Add commentary field to each benchmark_gap entry. Single batch LLM call for all gaps. System prompt cached. e.g. 'Your HR spend at 12.3% is 1.35x median; ₹46 Cr to P25 best-in-class.' |
| LLM-5 (Lower Value) | Lever rationale per value-at-table entry | `app/routers/enterprise.py value_at_table assembly` | Add rationale field explaining why each lever was flagged: 'Applicable based on IT concentration above P50 and vendor fragmentation signals.' trigger_signals already captures this structurally — LLM adds narrative. |

## Remediation Roadmap

