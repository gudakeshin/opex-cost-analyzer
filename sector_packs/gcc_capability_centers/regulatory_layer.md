# Regulatory Layer — GCC & Capability Centers (India)

## Primary Regulators
SEBI (listed parent / India entity); MeitY; STPI; RBI (data localisation for BFSI clients); MCA (Companies Act, transfer pricing).

## In-Force Regulations with OpEx Impact

### Captive Governance & Intercompany
- **Companies Act 2013 / Ind AS 24**: Related-party transactions, arm's-length recharge rates, and board approvals for parent allocations.
- **Transfer Pricing (Income Tax Act Sec 92)**: Benchmarking of intercompany service charges; documentation and CA OpEx.

### Export & Tax Incentives
- **STPI / SEZ compliance**: Net foreign exchange earning, softex filing, and annual performance certification.
- **Section 10AA / MAT**: Tax holiday compliance for SEZ units; separate books and audit trail costs.

### Data Privacy & Security
- **DPDP Act 2023**: Processing personal data for EU/US parent systems; DPO, consent, and breach notification OpEx.
- **GDPR (EU clients) / client SOC2/ISO mandates**: Annual infosec audits, penetration testing, and certification remediation.

### Quality & Certifications
- **CMMI / ISO 9001 / ISO 27001 / SOC 2**: Client-required quality and security certifications; assessor fees and gap remediation.
- **PCI-DSS (payment processing GCCs)**: Cardholder data environment controls and quarterly scans.

### Workforce
- **Labour Codes & POSH**: Large captive headcount — contract labour, harassment prevention, and statutory registers.
- **BRSR Core (SEBI 2023)**: If India entity is listed or part of top-1000 group — ESG metrics from captive operations.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| Transfer pricing scrutiny / TP audit | parent_recharge_costs, gcc_governance_compliance | HIGH |
| STPI/SEZ NFE shortfall | gcc_governance_compliance | HIGH |
| DPDP / GDPR compliance deadline | data_privacy_security, gcc_governance_compliance | HIGH |
| SOC2/ISO certification renewal | quality_certifications, data_privacy_security | MEDIUM |
| BRSR Core filing deadline | all | HIGH |
