# Regulatory Layer — Manufacturing Diversified (India)

## Primary Regulators
Ministry of Commerce & Industry (DPIIT), MoEFCC, BIS, State Pollution Control Boards.

## In-Force Regulations with OpEx Impact

### Indirect Tax
- **GST** (CGST Act 2017): ITC eligibility per Sec 17(5); RCM on GTA, import of services; inverted duty on inputs — key lever for cost recovery.
- **Customs** (Customs Act 1962): BCD + IGST on imports; advance licence / EPCG scheme for zero-duty imports vs. export obligation tracking.

### Labour & Compliance
- **Factories Act 1948**: Safety inspections, welfare fund, overtime limits — embedded in HR & facilities cost.
- **EPFO/ESIC**: Employer contributions (EPF 12%, ESI 3.25%) on applicable wage base.
- **POSH / CLRA**: Contract labour management compliance costs.

### Environmental
- **Environment Protection Act 1986 + EIA Notification**: ETP operations, stack monitoring, annual environmental audit.
- **Plastic Waste Management Rules 2016 (amended 2022)**: EPR compliance + buyback costs for plastic packaging manufacturers.
- **Energy Conservation Act 2001 (BEE)**: PAT scheme — Designated Consumers ≥ 1,000 MTOE must meet SEC targets or purchase ESCerts.
- **BRSR Core (SEBI 2023)**: Mandatory FY26; Scope-1/2 intensity, water intensity, waste generated — all from manufacturing data.

### PLI Schemes
- **PLI Scheme (various MoCI notifications)**: Incremental production thresholds; baseline year locked; annual compliance certification.
- Key sectors: Auto (MHI), White Goods (DPIIT), Specialty Chemicals (MoCI), Pharma (DoP).

### Quality & Standards
- **BIS Act 2016**: Mandatory BIS certification for ~400+ product categories; testing & hallmarking costs.
- **Legal Metrology Act 2009**: Packaging weight/measure compliance.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| GST rate change | raw_material_procurement, energy_utilities_plant | HIGH |
| BEE PAT cycle end | energy_utilities_plant | HIGH |
| PLI compliance deadline | pli_scheme_costs | HIGH |
| MoEFCC EIA amendment | ehs_environment | MEDIUM |
| Customs duty revision (Union Budget) | inbound_logistics | HIGH |
