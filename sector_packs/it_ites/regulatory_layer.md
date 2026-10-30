# Regulatory Layer — IT & ITeS (India)

## Primary Regulators
Software Technology Parks of India (STPI); Ministry of Electronics & IT (MeitY); Department of Telecommunications (DoT); SEBI (listed IT services).

## In-Force Regulations with OpEx Impact

### Export & SEZ Compliance
- **STPI / SEZ Rules (2006, amended)**: Net foreign exchange earning (NFE) obligations; softex filing, annual performance reports.
- **FTP 2023 — Services Export from India Scheme (SEIS)**: Export documentation and DGFT compliance for eligible IT services.

### Data Protection & Cross-Border
- **Digital Personal Data Protection Act 2023**: Consent, purpose limitation, DPO for significant fiduciaries; data localisation for government data.
- **RBI / client-mandated data residency**: Offshore delivery centres serving BFSI clients — dedicated compliance and audit OpEx.

### Immigration & Delivery
- **Visa / work permit norms (MHA)**: H1B/L1 equivalents, business visa caps; immigration legal and relocation costs.
- **Labour Codes (Wages, OSH)**: Contract labour and gig-worker compliance for large delivery centres.

### Quality & Security Certifications
- **ISO 27001 / SOC 2 Type II**: Client-mandated infosec audits; annual certification and remediation OpEx.
- **BRSR Core (SEBI 2023)**: Mandatory FY26 for listed IT firms; energy from data centres, e-waste, employee diversity.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| STPI/SEZ NFE shortfall or audit | stpi_see_compliance | HIGH |
| DPDP compliance deadline / penalty | cloud_saas_infra, offshore_delivery_infra | HIGH |
| Visa / immigration policy change | visa_immigration | HIGH |
| Client-mandated SOC2/ISO renewal | cloud_saas_infra, offshore_delivery_infra | MEDIUM |
| BRSR Core filing deadline | all | HIGH |
