# Realistic Manual Test Pack

This pack is designed for realistic end-to-end testing in the UI:

1. Create a session (example):
   - Company: `Northstar Retail Group`
   - Industry: `retail_consumer`
   - Annual revenue: `3200` million
   - Currency: `USD`
2. Upload both spend files:
   - `01_spend_transactions_us_q1_2026.csv`
   - `02_spend_transactions_eu_q1_2026.csv`
3. Upload the two context docs:
   - `03_contract_and_policy_context.txt`
   - `04_operating_model_and_budget_context.txt`
4. Run analysis and then chat with prompts like:
   - `Run benchmark analysis`
   - `Diagnose root causes for IT and Professional Services`
   - `Generate business case`
   - `Export as document`

Expected behavior this pack is tuned to trigger:
- Cross-category classification with realistic supplier names and descriptions
- Internal variance signals (US vs EU patterns, BU mix)
- Root-cause diagnostics (fragmented suppliers, higher off-PO behavior in some lines)
- Benchmark provenance text in chat response
- Pipeline creation after business case generation
