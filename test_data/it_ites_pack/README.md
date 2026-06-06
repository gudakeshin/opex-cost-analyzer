# IT/ITeS Comprehensive Test Pack — Aranya Digital Services Ltd

A single, internally-consistent engagement pack that maps **one file to each Guidebook tier/source**,
so you can walk the in-app **Guidebook** page top to bottom and have a real document to upload for
every item. Exercises ingestion column-detection, multi-format parsing (CSV / hierarchical P&L / JSON),
document RAG, multi-entity + source-lineage handling, and the full OPAR value bridge.

> All data is **synthetic / illustrative** for a fictional Indian IT/ITeS company. Amounts are scaled
> from public-peer ranges, not from any real filing.

## 1. Engagement setup

Create the engagement / diagnostic with:

| Field | Value |
|------|-------|
| Company | `Aranya Digital Services Ltd` |
| Sector / industry code | `it_ites` (IT / ITeS) |
| Annual revenue | `18400` (₹ Cr) |
| Reporting currency | `INR` |
| Aggregated headcount | `~84,000` |
| WACC | `13.5%` |
| Effective tax rate | `25.17%` |

Group structure: India parent **ADSL-IN** + US sub **AETS-US** + UK sub **ADUK-UK** (ERPs: SAP, Coupa, Oracle).

## 2. Guidebook tier → file map

### Tier 1 — Minimum to run
| Guidebook source | File |
|---|---|
| Transactional spend ledger; core spend columns | `T1_01_spend_ledger_fy25.csv` |
| Industry / Annual revenue / Company name | Set in engagement setup (above) |

### Tier 2 — Deep analysis (full value bridge)
| Guidebook source | File |
|---|---|
| GL / AP line-level extract | `T2_02_gl_ap_lineitem_extract.csv` |
| Headcount (aggregated, no PII) | `T2_03_headcount_aggregate.csv` |
| Budget vs. actuals | `T2_04_budget_vs_actual_fy25.csv` |
| P&L / hierarchical expense workbook | `T2_05_pnl_expense_workbook.csv` |
| Vendor master & material contracts | `T2_06_vendor_master.csv`, `T2_07_material_contracts.txt` |
| Supporting documents | `T2_08_annual_report_excerpt.txt`, `T2_09_budget_memo.txt`, `T2_10_procurement_policy.txt` |
| Deep research context | `T2_11_deep_research_brief.txt` |
| Diagnostic URLs | `T2_12_diagnostic_urls.txt` |
| Financial modeling parameters | `T2_13_financial_model_params.json` |

### Tier 3 — Confidence & lever depth
| Guidebook source | File |
|---|---|
| Contract register | `T3_14_contract_register.csv` |
| Payment terms / AP aging | `T3_15_payment_terms_ap_aging.csv` |
| India compliance fields (GST/GSTIN/related-party/lease) | folded into `T2_02` & `T2_06` |
| Multi-entity / group structure | `T3_16_group_structure.txt` (+ `legal_entity` in `T2_02`) |
| Source system lineage | `source_system` / `source_record_id` columns in `T2_02` |
| Operational drivers | `T3_17_operational_drivers.csv` |
| Multi-period actuals | satisfied by `T2_02` & `T2_04` (8 quarters / 12 months) |
| Segment revenue & entity tree | `T3_18_segment_revenue_entity_tree.csv` |
| Prior cost programmes | `T3_19_prior_cost_programmes.txt` |
| Realised savings / calibration | `T3_20_realised_savings_calibration.json` |

### Tier 4 — External & public context
| Guidebook source | File |
|---|---|
| BRSR disclosure | `T4_21_brsr_disclosure_excerpt.txt` |
| Annual report & statutory filings | `T2_08_annual_report_excerpt.txt` |
| Capex roster | `T4_22_capex_roster.csv` |
| Treasury & FX | `T4_23_treasury_fx_summary.txt` |
| Working capital pack | `T4_24_working_capital_pack.csv` |
| Peer & market intelligence | `T2_11_deep_research_brief.txt` |

### Tier 5 — Sector-pack add-ons (IT / ITeS)
| Guidebook source | File |
|---|---|
| Offshore/onshore mix, utilisation, vendor pyramid | `T5_25_offshore_onshore_utilization.csv` |

## 3. Suggested test walkthrough

1. **Tier 1 only** — create the engagement, upload `T1_01_spend_ledger_fy25.csv`, run analysis.
   Expect: spend profile by category, currency = INR, top-vendor concentration. (Verifies the
   Tier-1 gate opens once spend + industry + revenue are present.)
2. **Add Tier 2** — upload `T2_02`, `T2_03`, `T2_04`, `T2_05`, `T2_06` and the context docs, then chat:
   - `Run benchmark analysis` → peer percentiles for an `it_ites` engagement.
   - `Run budget vs actuals` → BvA price/volume/mix from `T2_04`.
   - `Diagnose root causes for Subcontractor and Cloud` → fragmentation / off-PO signals.
   - `Generate business case` → NPV/payback using WACC 13.5%, tax 25.17% (`T2_13`).
   - `Export as document` → executive synthesis enriched by the supporting docs (RAG).
3. **Add Tier 3** — upload contract register, AP aging, operational drivers, segment revenue, and the
   calibration JSON. Expect: addressable-vs-locked carve-out, DPO/working-capital lever, higher SME
   evidence scores (fewer "hypothesis" verdicts), and BU comparisons normalised by segment revenue.
4. **Add Tier 4 / 5** — capex roster, treasury/FX, working-capital, BRSR, and the utilisation pack add
   external context and IT/ITeS-specific levers (labour arbitrage, pyramid, FinOps).

## 4. Consistency notes

- Column headers follow the variants auto-detected in `app/services/ingestion.py`
  (`amount`, `supplier`, `description`, `gl_code`, `cost_center`, `currency`, `amount_type`,
  `fiscal_period`, `payment_terms_days`, `gstin`, `msme`, `source_system`, `legal_entity`, …).
- `T2_05` uses the hierarchical P&L layout (label column + FY amount columns; blank section/subtotal
  rows are skipped) validated by `tests/test_pl_ingestion.py`.
- Category totals across the ledger, the BvA actuals, and the P&L subtotals are roughly tied out so
  cross-checks don't raise false conflict flags.
- Intercompany lines (GL `640099`, `related_party = yes`) are included on purpose — they should be
  eliminated on consolidation, not counted as addressable third-party savings.
