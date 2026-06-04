# Sample spend files

Use these files to test upload and analysis on the **Analysis** tab.

## Quick start

1. Open **Analysis** → **Attach data** → pick a sample file below.
2. Click **Run analysis** (upload alone does not populate spend metrics).
3. Check the **Insights** panel for total spend and category concentration.

## Files

| File | Purpose |
|------|---------|
| `spend_ledger_sample.csv` | **Recommended** — transactional ledger with `supplier`, `description`, `amount`. Works out of the box. |
| `pnl_expense_summary_sample.csv` | Hierarchical P&L-style expense table (line items + FY amount columns). Tests P&L ingestion. |
| `pnl_expense_summary_sample.xlsx` | Same layout as CSV but in Excel with a header row offset (like real management reports). |
| `hul_india_spend_ledger_fy25.csv` | **HUL India test pack** — FMCG transactional ledger (A&P, trade promo, logistics, contract mfg, IT). Use with sector **FMCG / Consumer**. |
| `hul_india_pnl_expense_fy25.csv` | **HUL India test pack** — hierarchical P&L-style OpEx extract (lakhs); pairs with the ledger for P&L ingestion tests. |

### Hindustan Unilever (HUL) test data

Synthetic FY25 spend files for **Hindustan Unilever Ltd** (India FMCG). Amounts and line items are illustrative — scaled from public peer benchmarks, not from actual HUL filings.

**Diagnostic / session setup**

- Company: `Hindustan Unilever Ltd` or `HUL`
- Sector: `fmcg_consumer` (FMCG / Consumer)
- Revenue (Cr): `59200` (approx. FY24 reported revenue)

**Upload**

1. **Analysis** → **Attach data** → `hul_india_spend_ledger_fy25.csv` (recommended first)
2. **Run analysis** after upload

## Download via API

While the backend is running:

- `GET /api/v1/samples/spend-ledger.csv`
- `GET /api/v1/samples/pnl-expense.csv`
- `GET /api/v1/samples/pnl-expense.xlsx`
- `GET /api/v1/samples/hul-spend-ledger.csv`
- `GET /api/v1/samples/hul-pnl-expense.csv`
- `GET /api/v1/samples` — JSON list of available samples

## Layout notes

**Transactional ledger** (best for supplier/category analysis):

- Required: numeric **amount** column, **description** (or supplier).
- Optional: supplier, business unit, country, GL code.

**P&L / hierarchical expense** (category totals from line items):

- Line-item labels in one column (e.g. "Power & Fuel").
- Amounts in adjacent numeric period columns (even if Excel names them `Unnamed: 2`).
- Section headers and subtotal rows with blank amounts are skipped automatically.

## Your Belrise-style workbook

If you upload `Belrise_Detailed_Spend_Report_FY25-v3.xlsx` (or similar), re-upload and **Run analysis** after updating the app — amounts should map from the FY period column and descriptions from the line-item column.
