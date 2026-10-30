# Regulatory Layer — Energy & Utilities (India)

## Primary Regulators
Central Electricity Regulatory Commission (CERC); State Electricity Regulatory Commissions (SERCs); Ministry of Power (MoP); MoPNG / PNGRB (gas pipelines).

## In-Force Regulations with OpEx Impact

### Tariff & Revenue
- **Electricity Act 2003 / Tariff Policy**: Multi-year tariff orders; allowed O&M, wheeling, and AT&C loss norms baked into revenue recovery.
- **CERC/SERC Open Access Regulations**: Wheeling charges, cross-subsidy surcharge, and billing system compliance OpEx.

### Generation & Fuel
- **MoEFCC EC/CRZ clearances**: Environmental compliance for thermal/hydro; ash utilisation and fly-ash transport costs.
- **Coal linkage / e-auction (CIL)**: Fuel supply agreement compliance; quality sampling and logistics OpEx.

### Renewables & Carbon
- **Renewable Purchase Obligation (RPO) / REC mechanism**: REC purchase or penalty; trading and registry compliance costs.
- **PAT Scheme (BEE) — Designated Consumers**: Specific energy consumption targets; ESCert purchase if targets missed.

### Distribution & Losses
- **AT&C Loss Reduction targets (UDAY/Revamped Scheme)**: Smart metering, feeder segregation, and theft-detection programme OpEx.
- **BRSR Core (SEBI 2023)**: Mandatory FY26 for listed utilities; Scope-1 from generation, grid losses, water intensity.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| SERC/CERC tariff order revision | fuel_cost, grid_wheeling_charges, o_and_m_plant | HIGH |
| RPO/REC compliance shortfall | carbon_compliance | HIGH |
| PAT cycle end / ESCert purchase | carbon_compliance, fuel_cost | HIGH |
| AT&C loss target revision | at_and_c_losses | MEDIUM |
| BRSR Core filing deadline | all | HIGH |
