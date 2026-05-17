# Regulatory Layer — BFSI Banks (India)

## Primary Regulator
Reserve Bank of India (RBI) — Banking Regulation Act 1949; RBI Act 1934.

## In-Force Regulations with OpEx Impact

### Capital & Provisioning (affects cost base)
- **Basel III Capital Framework** (RBI Master Circular RBI/2015-16/58): Minimum CET1 8%, Tier-1 9.5%. Capital allocation cost embedded in OpEx via internal funds transfer pricing.
- **IRACP Norms / NPA Provisioning** (RBI/2021-22/125): ECL-aligned provisioning from FY26; increases provision costs by estimated 15–20% for weaker portfolios.
- **CRR/SLR** (current CRR 4.5%, SLR 18%): Opportunity cost captured as regulatory cost.

### Compliance & Reporting
- **KYC Master Direction 2016** (updated 2023): Video KYC, periodic re-KYC; non-compliance → ₹1 Cr fine per instance.
- **AML / CFT** (PMLA 2002; RBI guidelines): Transaction monitoring system mandatory; SAR filing < 7 days.
- **CRILC Reporting** (RBI/DBOD.No.BP.BC.15/21.04.048/2014-15): Monthly large-borrower credit reporting.
- **BRSR Core** (SEBI SEBI/HO/CFD/CMD-2/P/CIR/2023/122): Mandatory FY26 for top-1000 listed; Scope-2, water intensity, waste disclosure.

### Technology & Data
- **RBI Cloud Guidelines** (RBI/2023-24/73): Data localisation; DSCI audit; no offshore storage of KYC/financial data.
- **PCI-DSS**: Mandatory for card-acquiring and issuing.
- **RBI IT Framework** (RBI/2011-12/494): Business continuity, DR, cyber security; annual CISO review.
- **Account Aggregator Framework** (RBI/2021-22/91): API-first financial data sharing; FIP/FIU compliance costs.

### Priority Sector & Inclusion
- **PSL Targets**: 40% of ANBC; sub-targets for agriculture (18%), weaker sections (12%). PSLC trading costs apply.
- **Financial Inclusion**: BCA network maintenance costs eligible for partial subsidy.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| RBI rate decision | treasury_ops | MEDIUM |
| NPA classification change | npa_provisioning_cost | HIGH |
| KYC deadline | kyc_aml_ops | HIGH |
| BRSR filing deadline | all | HIGH |
| Basel-III phase-in | cre_credit_risk_infra | MEDIUM |
