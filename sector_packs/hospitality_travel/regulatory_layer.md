# Regulatory Layer — Hospitality & Travel (India)

## Primary Regulators
Ministry of Tourism (MoT); FSSAI (food & beverage); state Excise departments; state Fire & Safety authorities; state Tourism departments.

## In-Force Regulations with OpEx Impact

### Licensing & Classification
- **Hotels & Restaurants Approval & Classification (MoT)**: Star classification, renewal inspections, and tourism promotion levy in some states.
- **State Tourism / Trade licences**: Bar licence, entertainment licence, and health permits — per-property compliance OpEx.

### Food & Beverage
- **FSSAI (central/state licence)**: Kitchen hygiene, HACCP, and periodic food safety audits for F&B operations.
- **State Excise Act**: Liquor licence fees, inventory controls, and excise duty compliance for bar operations.

### Safety & Labour
- **National Building Code / Fire Safety**: NOC renewal, sprinkler systems, and evacuation drill documentation.
- **Shops & Establishments / Contract Labour Act**: Seasonal workforce, housekeeping contractors, and statutory registers.

### Tax & Distribution
- **GST on hospitality (room tariff slabs)**: Rate changes affect pricing systems and ITC eligibility on inputs.
- **OTA / aggregator TCS (Sec 194-O)**: E-commerce operator obligations; reconciliation with OTA commission spend.

### Sustainability
- **State water conservation norms**: Large hotels — STP, rainwater harvesting, and metering compliance.
- **BRSR Core (SEBI 2023)**: Mandatory FY26 for listed hospitality groups; energy, water, and waste per property.

## Regulatory Event Triggers (mapped to reg_watcher categories)
| Trigger | Category IDs | Severity |
|---------|-------------|----------|
| FSSAI kitchen audit failure | fb_cost_of_sales, guest_amenities | HIGH |
| Liquor licence suspension / excise audit | fb_cost_of_sales, property_occupancy | HIGH |
| Fire safety NOC non-renewal | property_occupancy, utilities_energy | HIGH |
| GST rate change on room tariff | property_occupancy, ota_commission | MEDIUM |
| BRSR Core filing deadline | all | HIGH |
