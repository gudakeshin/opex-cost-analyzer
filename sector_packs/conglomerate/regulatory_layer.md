# Regulatory Layer — Conglomerate / Diversified Group (India)

## Primary Regulators
Securities and Exchange Board of India (SEBI); Ministry of Corporate Affairs (MCA21); Competition Commission of India (CCI); RBI (NBFC/finance arms); sectoral regulators per business line.

## In-Force Regulations with OpEx Impact

### Listing & Disclosure
- **SEBI LODR Regulations 2015**: Quarterly results, material events, and governance disclosures for listed parent/holding companies.
- **BRSR Core (SEBI 2023)**: Mandatory FY26 for top-1000 listed groups; consolidated ESG metrics across subsidiaries.

### Related Party & Consolidation
- **Ind AS 24 (Related Party Disclosures)**: Identification, approval, and arm's-length pricing for intra-group transactions.
- **Companies Act Sec 188**: Board/shareholder approval thresholds for RPTs; compliance and legal OpEx.

### Competition & M&A
- **CCI (Competition Act 2002)**: Combination notifications above asset/turnover thresholds; filing fees and legal costs.
- **CCI vertical agreements / abuse of dominance**: Group procurement, exclusive supply — competition law review OpEx.

### Group Treasury & Shared Services
- **RBI external commercial borrowing (ECB) norms**: Where group treasury centralises foreign borrowing — compliance and hedging OpEx.
- **Transfer pricing (Sec 92)**: Cross-border and domestic related-party service charges; documentation and benchmarking costs.

### Multi-Sector Compliance
- **Sectoral regulators per subsidiary**: RBI (bank/NBFC), IRDAI (insurance), TRAI (telecom) — group compliance office and shared audit OpEx.
- **MCA21 annual filing / XBRL**: Consolidated financial statements, director KYC, and beneficial ownership reporting.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| SEBI LODR / RPT disclosure breach | related_party_transactions, holding_co_overhead | HIGH |
| CCI combination filing deadline | group_shared_services, holding_co_overhead | HIGH |
| BRSR Core filing deadline | all | HIGH |
| MCA21 beneficial ownership / director KYC | holding_co_overhead, group_treasury_funding | MEDIUM |
| Group treasury / ECB covenant breach | group_treasury_funding, intercompany_eliminations | HIGH |
