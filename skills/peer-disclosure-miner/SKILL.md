---
name: peer-disclosure-miner
description: "Mine BSE/NSE annual report filings, earnings call transcripts, BRSR disclosures, and MCA21 data for peer cost commentary and benchmarks. M1=keyword-regex (~25% recall); M2/M3=LLM-powered full extraction (~90% recall)."
version: "1.0"
status: active
llm_required: true
band_ceiling: "B2"
---

# Peer Disclosure Miner

Extracts peer cost-structure intelligence from public filings to support benchmark construction when licensed data (CMIE, Capitaline) is unavailable.

## What This Skill Does

1. Accepts a peer set (from sector pack `peer_set.json`) and a list of target cost categories.
2. In **M1 mode**: runs keyword-regex patterns against the most-recently-indexed filing text.
3. In **M2/M3 mode**: sends structured prompts to the LLM to extract quantitative disclosures + qualitative commentary.
4. Returns structured `peer_disclosures` with source attribution and confidence scores.

## Extraction Targets

| Filing Type | Source | Data Points |
|-------------|--------|-------------|
| Annual Report (MDA) | BSE/NSE PDF | OpEx breakdown, cost trends, efficiency commentary |
| Earnings Call Transcript | NSE/Screener | Management guidance on cost reduction |
| BRSR Core Disclosure | BSE/SEBI | Scope-2 intensity, water, waste, energy |
| Schedule III P&L | MCA21 XBRL | Employee expenses, other expenses, depreciation |

## M1 vs M2/M3 Capability Gap

| Capability | M1 (regex) | M2/M3 (LLM) |
|------------|-----------|-------------|
| Quantitative extraction | ~25% recall | ~90% recall |
| Qualitative commentary | 0% | 85% |
| Multi-year trend | No | Yes |
| Ambiguity resolution | No | Yes |

**Degradation banner**: in M1 mode, skill output includes `"llm_degraded": true` and `"m1_recall_note"`.

## Output Schema

```json
{
  "peer_disclosures": [
    {
      "peer_name": "HDFC Bank",
      "ticker": "HDFCBANK.NS",
      "filing_type": "annual_report",
      "fiscal_year": "FY25",
      "cost_category": "core_banking_platform",
      "disclosed_value_cr": null,
      "disclosed_pct_of_opex": 12.5,
      "commentary": "...",
      "source_page": 47,
      "confidence": 0.82
    }
  ],
  "portfolio_coverage": 0.25,
  "llm_degraded": false,
  "m1_recall_note": null,
  "extraction_mode": "M2",
  "summary": "..."
}
```

## Capability Matrix

| Mode | Level | Notes |
|------|-------|-------|
| M1   | partial | Keyword-regex; ~25% recall; llm_degraded=true in output |
| M2   | full    | LLM extraction from indexed filing text |
| M3   | full    | Same as M2 with local model |
