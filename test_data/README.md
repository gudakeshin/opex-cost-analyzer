# Test data

Sample engagements for manual testing and demos. Everything here is **synthetic or illustrative** — amounts, vendors, GSTINs/PANs, contracts and headcount splits are made up; where a pack is modelled on a real public company, its README says so.

## How to use a pack

1. In the app, open **Documents** and create an engagement (or use **Load demo engagement** on the Analysis page for the single bundled ledger).
2. Set the sector to the pack's *sector code* below and the revenue/currency stated in the pack's README.
3. Upload the pack's files (each pack maps one file per Guidebook tier/source; its README has the file map) and run the analysis.

## Sector packs (25 data files each, plus a README)

| Folder | Company | Sector code | Files | Basis |
|---|---|---|---|---|
| `bfsi_banks_pack` | Indus Apex Bank Ltd | `bfsi_banks` | 25 | fully synthetic |
| `conglomerate_pack` | Bharat Ventures Group Ltd | `conglomerate` | 25 | fully synthetic |
| `energy_utilities_pack` | Sahyadri Power & Utilities Ltd | `energy_utilities` | 25 | fully synthetic |
| `financial_services_nonbank_pack` | Vistaar Capital Partners Ltd | `financial_services_nonbank` | 25 | fully synthetic |
| `fmcg_consumer_pack` | Prakrit Consumer Brands Ltd | `fmcg_consumer` | 25 | fully synthetic |
| `gcc_capability_centers_pack` | Meridian Global Services India Pvt Ltd | `gcc_capability_centers` | 25 | fully synthetic |
| `healthcare_hospitals_pack` | Aarogya Health Network Ltd | `healthcare_hospitals` | 25 | fully synthetic |
| `hospitality_travel_pack` | Surya Hospitality & Resorts Ltd | `hospitality_travel` | 25 | fully synthetic |
| `icici_bank_pack` | ICICI Bank Limited | `bfsi_banks` | 25 | illustrative, modelled on a real public company |
| `insurance_general_pack` | Pragati General Insurance Ltd | `insurance_general` | 25 | fully synthetic |
| `it_ites_pack` | Aranya Digital Services Ltd | `it_ites` | 25 | fully synthetic |
| `kei_industries_pack` | KEI Industries Limited | `manufacturing_diversified` | 25 | illustrative, modelled on a real public company |
| `manufacturing_diversified_pack` | Uttam Industries Ltd | `manufacturing_diversified` | 25 | fully synthetic |
| `pharma_lifesciences_pack` | Zenith Pharma Ltd | `pharma_lifesciences` | 25 | fully synthetic |
| `piccadily_agro_pack` | Piccadily Agro Industries Limited | `manufacturing_diversified` | 25 | illustrative, modelled on a real public company |
| `psu_cpse_pack` | National Engineering Corporation Ltd | `psu_cpse` | 25 | fully synthetic |
| `retail_organized_pack` | Bharat Bazaar Retail Ltd | `retail_organized` | 25 | fully synthetic |
| `telecom_infra_pack` | Pragati Telecom Networks Ltd | `telecom_infra` | 25 | fully synthetic |

`manufacturing_cement` (the 16th sector pack) has no test pack yet.

## Other material

- `realistic_pack/` — a small multi-file scenario with nuanced data (its README lists the files and example prompts). It uses a retail/USD setup, unlike the India-first packs above.
- `sample_spend_for_manual_testing.csv`, `sample_context_for_manual_testing.txt` — minimal two-file smoke test.
- `../data/samples/` — the ledger and P&L samples behind the **Download sample** links and **Load demo engagement** (HUL-style ledger and P&L, a generic ledger, and a P&L workbook).

Several folders reuse company names across this repo's engagement fixtures (for example Uttam Industries, Prakrit Consumer Brands, Aranya Digital Services, Meridian Global Services), because those engagements were created from these packs.
