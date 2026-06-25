# Regulatory Layer — Telecom & Infrastructure (India)

## Primary Regulators
Telecom Regulatory Authority of India (TRAI); Department of Telecommunications (DoT); MeitY (data/localisation); SEBI (listed telcos).

## In-Force Regulations with OpEx Impact

### Licensing & Spectrum
- **Indian Telegraph Act / Unified Licence (DoT)**: Licence fees, spectrum usage charges (SUC), and AGR dues — statutory OpEx on revenue.
- **Spectrum Auction & Assignment (DoT/TRAI)**: Upfront payments plus ongoing SUC; compliance reporting on rollout obligations.

### Interconnect & QoS
- **TRAI QoS Regulations (wireless/wireline)**: Call-drop thresholds, billing accuracy; network monitoring and remediation OpEx.
- **Interconnect Usage Charges (IUC) / MNP regulations**: Settlement systems, porting infrastructure, and dispute resolution costs.

### Tower & Infrastructure
- **DOT EMF exposure norms**: Tower radiation audits, shielding, and community compliance programmes.
- **Right of Way (RoW) Rules 2016**: State-level fibre/tower permissions; legal and municipal fee OpEx.

### Data & Consumer Protection
- **DPDP Act 2023**: Consent management, data localisation for subscriber records, DPO appointment for large fiduciaries.
- **BRSR Core (SEBI 2023)**: Mandatory FY26 for listed telcos; tower energy, diesel genset emissions, e-waste.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| TRAI tariff / IUC revision | network_opex_access, spectrum_license_fees | HIGH |
| AGR / licence fee settlement order | spectrum_license_fees | HIGH |
| QoS penalty / call-drop breach | network_opex_access, tower_power_diesel | HIGH |
| Spectrum rollout obligation deadline | network_opex_access | MEDIUM |
| BRSR Core filing deadline | all | HIGH |
