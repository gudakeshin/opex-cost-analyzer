Aranya Digital Services Ltd — Group & Entity Structure (for multi-entity / lineage handling)

Legal entities
- ADSL-IN — Aranya Digital Services Ltd (India, parent; listed). SEZ delivery campuses; ERP: SAP + Coupa.
- AETS-US — Aranya Enterprise Tech Services Inc (USA; wholly owned). Onsite delivery & sales; ERP: Oracle.
- ADUK-UK — Aranya Digital UK Ltd (United Kingdom; wholly owned). Onsite delivery; ERP: Oracle.

Entity tree
  ADSL-IN (parent)
    ├── AETS-US (100%)
    └── ADUK-UK (100%)

Source systems / lineage
- India AP runs on SAP (vendor invoices) and Coupa (cloud/software procurement).
- US and UK AP run on Oracle. Merged extracts carry source_system + source_record_id for traceability.
- When the same vendor appears across SAP and Oracle (e.g. Microsoft global), reconcile by GSTIN/entity
  before computing group totals to avoid double counting.

Intercompany
- AETS-US and ADUK-UK recharge onsite delivery management and shared services to ADSL-IN.
- Intercompany lines are flagged related_party = yes (GL 640099) and must be eliminated on
  consolidation; they are NOT addressable third-party savings.

Consolidation guidance
- Benchmark and value-bridge analysis should use consolidated, intercompany-eliminated spend.
- BU comparisons should normalise by segment revenue (see T3_18_segment_revenue_entity_tree.csv).
