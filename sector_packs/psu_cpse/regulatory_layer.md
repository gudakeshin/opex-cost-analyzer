# Regulatory Layer — PSU / CPSE (India)

## Primary Regulators
Department of Public Enterprises (DPE); Comptroller & Auditor General (CAG); Department of Investment and Public Asset Management (DIPAM); Central Vigilance Commission (CVC); sectoral ministries.

## In-Force Regulations with OpEx Impact

### DPE Guidelines & Governance
- **DPE Guidelines on Corporate Governance (2010, updated)**: Board composition, audit committee, and performance MoU targets — governance OpEx.
- **DPE guidelines on pay / perquisites**: CTC caps, executive perks, and HR policy compliance for CPSEs.

### Statutory Audit & Dividend
- **CAG audit (Companies Act / CAG DPC Act)**: Statutory and supplementary audit; para compliance and remediation costs.
- **DIPAM dividend policy**: Minimum dividend payout for profit-making CPSEs; cash flow and capex planning constraints.

### CSR & Social Obligations
- **Companies Act Sec 135 (CSR)**: 2% of average net profit on eligible activities; monitoring and impact assessment OpEx.
- **Township & welfare obligations**: Hospital, school, and housing for CPSE townships — embedded in township_welfare_ops.

### Vigilance & Procurement
- **CVC guidelines / Integrity Pact**: Tender scrutiny, vigilance clearance, and e-procurement compliance OpEx.
- **GeM / CPPP mandates**: Central procurement portal usage; cataloguing and vendor onboarding costs.

### Sectoral Levies
- **Government levies, cess & special dividends**: Coal cess, NMDC royalty pass-through, and sector-specific statutory payments.
- **BRSR Core (SEBI 2023)**: Listed CPSEs in top-1000 — mandatory sustainability disclosures.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| CAG audit para / compliance deadline | cag_audit_costs, govt_levy_dividends | HIGH |
| DPE MoU target revision | dpe_hr_perquisites, township_welfare_ops | MEDIUM |
| CSR spending shortfall (Sec 135) | csr_mandatory_spend | HIGH |
| DIPAM dividend policy change | govt_levy_dividends | HIGH |
| CVC vigilance / procurement enquiry | cag_audit_costs | MEDIUM |
