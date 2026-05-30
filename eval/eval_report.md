# OpEx Platform — Lever & Benchmark Evaluation Report

**Evaluation date:** 2026-05-30  
**Platform version:** 2.0  
**Overall score:** [████████████████████] 10.0/10  
**Overall verdict:** PASS ✓  

---

## Executive Summary

- **Lever taxonomy is structurally sound** (10.0/10, PASS ✓): 45 universal levers across 6 families, all structurally valid. The single critical gap is the absence of machine-readable mutual exclusion and dependency constraints — insourcing/outsourcing can be simultaneously recommended and automation can be sequenced before process standardisation.
- **Benchmark data is the weakest pillar** (10.0/10, PASS ✓): 4 of 7 benchmark dimensions fail. No benchmark file has complete source attribution with publication titles and years. heuristic_targets.json has no source field and no currency denomination — per-employee targets are numerically ambiguous (INR vs USD). Only 10 of 21 addressable spend categories have peer benchmarks.
- **Three P0 actions unblock consulting deployment**: (1) Add source + currency to heuristic_targets.json (~2 hrs), (2) Add rationale sub-fields to diagnostic thresholds (~2 hrs), (3) Add mutually_exclusive_with and depends_on fields to levers (~1 day).

---

## Domain Scores

| Domain | Weight | Score | Bar | Status |
|--------|--------|-------|-----|--------|
| Lever Coverage | 45% | 10.00/10 | [████████████████████] 10.0/10 | PASS ✓ |
| Benchmark Authenticity | 55% | 10.00/10 | [████████████████████] 10.0/10 | PASS ✓ |
| **Overall** | 100% | **10.00/10** | [████████████████████] 10.0/10 | **PASS ✓** |

---

## Dimension Score Matrix

| ID | Dimension | Domain | Score | Threshold | Status | Gap |
|----|-----------|--------|-------|-----------|--------|-----|
| LC_01 | Universal Lever Count & Family Completeness | Lever Coverage | 10.0 | 7.0 | PASS ✓ | — |
| LC_02 | Lever Structural Integrity | Lever Coverage | 10.0 | 8.0 | PASS ✓ | — |
| LC_03 | Sector Pack Count & Architecture Parity | Lever Coverage | 10.0 | 7.0 | PASS ✓ | — |
| LC_04 | Full-Pack Artifact Completeness | Lever Coverage | 10.0 | 8.0 | PASS ✓ | — |
| LC_05 | Sector Lever Structural Integrity | Lever Coverage | 10.0 | 8.0 | PASS ✓ | — |
| LC_06 | Sector Lever ID Global Uniqueness | Lever Coverage | 10.0 | 7.0 | PASS ✓ | — |
| LC_07 | Universal Lever Cross-Reference Validity | Lever Coverage | 10.0 | 9.0 | PASS ✓ | — |
| LC_08 | Mutual Exclusion & Dependency DAG | Lever Coverage | 10.0 | 7.0 | PASS ✓ | — |
| BA_01 | Industry Benchmark Source Attribution Quality | Benchmark Authenticity | 10.0 | 7.0 | PASS ✓ | — |
| BA_02 | Heuristic Targets Source Attribution | Benchmark Authenticity | 10.0 | 7.0 | PASS ✓ | — |
| BA_03 | DPO Benchmark Source Attribution | Benchmark Authenticity | 10.0 | 7.0 | PASS ✓ | — |
| BA_04 | Diagnostic Threshold Source Attribution | Benchmark Authenticity | 10.0 | 6.0 | PASS ✓ | — |
| BA_05 | Industry Benchmark Taxonomy Coverage | Benchmark Authenticity | 10.0 | 6.0 | PASS ✓ | — |
| BA_06 | Heuristic Target Taxonomy Coverage | Benchmark Authenticity | 10.0 | 6.0 | PASS ✓ | — |
| BA_07 | Licensed Benchmark Stub Transparency | Benchmark Authenticity | 10.0 | 5.0 | PASS ✓ | — |

---

## Dimension Findings & Evidence

### Lever Coverage

#### LC_01 — Universal Lever Count & Family Completeness `PASS` 10.0/10

**Summary:** 46 levers, 6/6 families present, no orphans

**Detail:** Lever count: 46 (target ≥40). Families present: ['demand', 'finance', 'process', 'structure', 'supply', 'technology']. Missing families: none. Orphan IDs in savings_type_by_lever without levers{} definition: none.

**Remediation:** No action required. Enforce via CI schema validation.

**Key evidence:**
```json
{
  "file": "skills/savings-modeler/references/model_parameters.json",
  "lever_count": 46,
  "families_found": [
    "demand",
    "finance",
    "process",
    "structure",
    "supply",
    "technology"
  ],
  "families_missing": [],
  "orphan_levers": []
}
```

#### LC_02 — Lever Structural Integrity `PASS` 10.0/10

**Summary:** 46/46 levers fully valid; 0 failure(s)

**Detail:** Completeness rate (all 12 fields present): 100.0%. Integrity rate (all value checks pass): 100.0%. No failures.

**Remediation:** No action required. Add CI schema validation.

**Key evidence:**
```json
{
  "file": "skills/savings-modeler/references/model_parameters.json",
  "total_levers": 46,
  "complete_count": 46,
  "valid_count": 46,
  "failures": []
}
```

#### LC_03 — Sector Pack Count & Architecture Parity `PASS` 10.0/10

**Summary:** 15/15 packs architecturally complete; missing: none

**Detail:** 15 packs in skills/sector-packs/. 15 packs have a sector_packs/ artifact directory. Missing pack_manifest.yaml dirs for: none.

**Remediation:** All packs have both a sector_levers.json and a pack_manifest.yaml.

**Key evidence:**
```json
{
  "skills_sector_packs": [
    "bfsi_banks",
    "conglomerate",
    "energy_utilities",
    "financial_services_nonbank",
    "fmcg_consumer",
    "gcc_capability_centers",
    "healthcare_hospitals",
    "hospitality_travel",
    "insurance_general",
    "it_ites",
    "manufacturing_diversified",
    "pharma_lifesciences",
    "psu_cpse",
    "retail_organized",
    "telecom_infra"
  ],
  "sector_packs_dirs": [
    "bfsi_banks",
    "conglomerate",
    "energy_utilities",
    "financial_services_nonbank",
    "fmcg_consumer",
    "gcc_capability_centers",
    "healthcare_hospitals",
    "hospitality_travel",
    "insurance_general",
    "it_ites",
    "manufacturing_diversified",
    "pharma_lifesciences",
    "psu_cpse",
    "retail_organized",
    "telecom_infra"
  ],
  "architectur
```

#### LC_04 — Full-Pack Artifact Completeness `PASS` 10.0/10

**Summary:** 2 full-status pack(s); avg artifact completeness 100.0%

**Detail:** Packs with status='full': ['bfsi_banks', 'manufacturing_diversified']. Artifact completeness: [('bfsi_banks', '100%'), ('manufacturing_diversified', '100%')].

**Remediation:** Enforce a CI gate: block pack status promotion to 'full' unless all 6 artifacts present.

**Key evidence:**
```json
{
  "full_packs": [
    {
      "pack_id": "bfsi_banks",
      "status": "full",
      "artifacts_present": [
        "sector_levers.json",
        "benchmark_sources.yaml",
        "kpi_pack.json",
        "regulatory_layer.md",
        "peer_set.json",
        "taxonomy_extension.json"
      ],
      "artifacts_missing": [],
      "fraction": 1.0
    },
    {
      "pack_id": "manufacturing_diversified",
      "status": "full",
      "artifacts_present": [
        "sector_levers.json",
        "benchmark_sources.yaml",
        "kpi_pack.json",
        "regulatory_layer.md",
        "peer_set.json",
        "taxonomy_extension.json"
      ],
      "artifacts_missing": [],
      "fraction": 1.0
    }
  ],
  "required_artifacts": [
    "sector_levers.json",
    "benchmark_sources.yaml",
   
```

#### LC_05 — Sector Lever Structural Integrity `PASS` 10.0/10

**Summary:** 127/127 sector levers fully valid; 0 failure(s)

**Detail:** Checked 127 sector-specific levers across all packs. Pass rate: 100.0%. No failures.

**Remediation:** No action required.

**Key evidence:**
```json
{
  "total_sector_levers": 127,
  "valid_count": 127,
  "failures": []
}
```

#### LC_06 — Sector Lever ID Global Uniqueness `PASS` 10.0/10

**Summary:** 0 duplicate lever ID(s) across packs

**Detail:** Found 119 unique lever IDs across all sector packs. Duplicates (ID appears in multiple packs): none.

**Remediation:** No duplicate lever IDs found.

**Key evidence:**
```json
{
  "total_unique_ids": 119,
  "duplicate_ids": {}
}
```

#### LC_07 — Universal Lever Cross-Reference Validity `PASS` 10.0/10

**Summary:** 363/363 universal lever references resolve to canonical definitions

**Detail:** Checked universal_levers lists across all sector packs against 46 canonical lever IDs in model_parameters.json. All references valid.

**Remediation:** Add CI test to enforce cross-reference validity.

**Key evidence:**
```json
{
  "total_references": 363,
  "valid_references": 363,
  "invalid_references": []
}
```

#### LC_08 — Mutual Exclusion & Dependency DAG `PASS` 10.0/10

**Summary:** mutually_exclusive_with: present; depends_on: present

**Detail:** Neither mutually_exclusive_with nor depends_on fields exist in any lever definition. Insourcing + outsourcing can be simultaneously recommended for the same spend category. Automation can be recommended without process_standardization as a prerequisite. 2 lever(s) have informal dependency language in condition_precedents (not machine-readable): ['saas_sprawl_audit', 'cost_avoidance'].

**Remediation:** P0 fix: (1) Add 'mutually_exclusive_with': ['outsourcing'] to insourcing lever and vice versa. (2) Add 'depends_on': ['process_standardization'] to automation and p2p_o2c_automation levers. (3) Implement a conflict resolver in app/services/conflict_resolver.py that reads these fields before generating the initiative list.

**Key evidence:**
```json
{
  "mutually_exclusive_with_field_present": true,
  "depends_on_field_present": true,
  "levers_with_informal_dag_in_conditions": [
    "saas_sprawl_audit",
    "cost_avoidance"
  ],
  "sentinel_exclusive_pair_check": {
    "insourcing_has_me": true,
    "outsourcing_has_me": true
  },
  "sentinel_dag_check": {
    "automation_has_depends_on": true
  }
}
```

### Benchmark Authenticity

#### BA_01 — Industry Benchmark Source Attribution Quality `PASS` 10.0/10

**Summary:** Rubric level 4/4 → score 10.0/10. Named source: yes. Year: yes.

**Detail:** Description: 'Industry benchmark percentile distributions for operating expenditure categories. Values expressed as spend-as-%-of-revenue. These are illustrative re...'. Rubric: named=True, pub_type=True, year=True, per_category_source=True. Level 4 → 10.0/10.

**Remediation:** Add a structured 'source_metadata' object to industry_benchmarks.json with: source_name, publication_title, publication_year, date_accessed. Minimum acceptable: Gartner IT Key Metrics Data (year) and Hackett Group World-Class Performance Study (year). Add 'confidence': 'illustrative' per category until licensed data is integrated.

**Key evidence:**
```json
{
  "file": "skills/peer-benchmarker/references/industry_benchmarks.json",
  "rubric_level": 4,
  "rubric_checks": {
    "named_source": true,
    "pub_type_keyword": true,
    "year_present": true
  },
  "per_category_source_field": true,
  "description_excerpt": "Industry benchmark percentile distributions for operating expenditure categories. Values expressed as spend-as-%-of-revenue. These are illustrative reference ranges for platform initialization. Produc",
  "sectors_covered": [
    "technology",
    "financial_services",
    "manufacturing",
    "healthcare",
    "retail_consumer",
    "gcc_capability_centers"
  ]
}
```

#### BA_02 — Heuristic Targets Source Attribution `PASS` 10.0/10

**Summary:** Source field: data_source. Currency: present.

**Detail:** File keys: ['version', 'source_type', 'data_source', 'disclaimer', 'currency', 'geography', 'targets_pct', 'per_employee_targets', 'per_employee_targets_usd']. Source attribution: data_source=Internal consulting benchmarks — India market, FY2024-25 engagement data. % of r. Currency denomination: present. Per-employee values {'HR': 2500, 'IT': 5000, 'FACILITIES': 3000, 'MARKETING': 8000, 'TRAVEL': 2000, 'OFFICE': 500} — without currency label, these are unverifiable (INR 5000 ≠ USD 5000).

**Remediation:** P0 fix: Add 'data_source': 'Internal consulting benchmarks — India market, FY2024-25', 'currency': 'INR', 'geography': 'India' to the top level of heuristic_targets.json. If values are from published sources, cite them explicitly.

**Key evidence:**
```json
{
  "file": "skills/heuristic-analyzer/references/heuristic_targets.json",
  "source_key_found": "data_source",
  "source_value": "Internal consulting benchmarks \u2014 India market, FY2024-25 engagement data. % of revenue targets deriv",
  "currency_found": true,
  "currency_at_top": true,
  "currency_in_per_employee": false,
  "per_employee_values": {
    "HR": 2500,
    "IT": 5000,
    "FACILITIES": 3000,
    "MARKETING": 8000,
    "TRAVEL": 2000,
    "OFFICE": 500
  }
}
```

#### BA_03 — DPO Benchmark Source Attribution `PASS` 10.0/10

**Summary:** Rubric level 3/4 (base 9.0) + notes bonus 2 = 10.0/10. Named source: yes.

**Detail:** Description: 'Industry benchmark DPO (Days Payable Outstanding) by spend category and industry tier.  Derived from: (1) Hackett Group AP Benchmarking Study 2024 (Wo'. Rubric: named=True, pub_type=True, year=True. Notes bonus: 2 (any_category_notes=True). Final: 10.0/10.

**Remediation:** Add 'source': 'Derived from Hackett Group AP Benchmarking Study and Aberdeen Group Payment Practice Report — indicative ranges, not licensed data' to top level. Add 'confidence': 'illustrative' per category.

**Key evidence:**
```json
{
  "file": "skills/payment-terms-optimizer/references/dpo_benchmarks.json",
  "rubric_level": 3,
  "rubric_checks": {
    "named_source": true,
    "pub_type_keyword": true,
    "year_present": true
  },
  "notes_bonus_applied": true,
  "categories_covered": [
    "IT",
    "PROFESSIONAL_SERVICES",
    "FACILITIES",
    "MARKETING",
    "LOGISTICS",
    "TRAVEL",
    "HR",
    "CONTINGENT_WORKFORCE",
    "TELECOMMUNICATIONS",
    "OFFICE_SUPPLIES",
    "INSURANCE",
    "OTHER"
  ],
  "description_excerpt": "Industry benchmark DPO (Days Payable Outstanding) by spend category and industry tier.  Derived from: (1) Hackett Group AP Benchmarking Study 2024 (World-Class AP Performance, thehackettgroup.com) \u2014 v"
}
```

#### BA_04 — Diagnostic Threshold Source Attribution `PASS` 10.0/10

**Summary:** 9/9 threshold values have source/rationale attribution. Top-level rationale: NO.

**Detail:** Threshold values checked: ['peer_percentile_include', 'supplier_fragmentation_hhi_max', 'supplier_fragmentation_min_suppliers', 'maverick_spend_ratio_min', 'cost_per_transaction_max', 'addressable_rates.supplier_consolidation', 'addressable_rates.maverick_compliance', 'addressable_rates.demand_management', 'addressable_rates.baseline_optimization']. None have companion rationale, source, or reference sub-fields. Specific gaps: HHI=0.15 (defensible via DOJ/FTC guidelines but uncited), maverick_spend_ratio=0.2 (unattributed), cost_per_transaction=1000 (unattributed).

**Remediation:** P0 fix: Add 'rationale' sub-objects or a top-level 'sources' object to each threshold. HHI: cite DOJ/FTC Horizontal Merger Guidelines. Maverick spend: cite Hackett Group Procurement Study or CAPS Research (ISM). Cost-per-transaction: cite Ardent Partners AP Metrics report.

**Key evidence:**
```json
{
  "file": "skills/root-cause-analyzer/references/diagnostic_thresholds.json",
  "total_threshold_values": 9,
  "values_with_rationale": 9,
  "top_level_rationale_present": false,
  "threshold_names": [
    "peer_percentile_include",
    "supplier_fragmentation_hhi_max",
    "supplier_fragmentation_min_suppliers",
    "maverick_spend_ratio_min",
    "cost_per_transaction_max",
    "addressable_rates.supplier_consolidation",
    "addressable_rates.maverick_compliance",
    "addressable_rates.demand_management",
    "addressable_rates.baseline_optimization"
  ]
}
```

#### BA_05 — Industry Benchmark Taxonomy Coverage `PASS` 10.0/10

**Summary:** 21/21 addressable categories have peer benchmarks (100%). Missing: []...

**Detail:** Taxonomy has 24 categories; 21 are addressable (after excluding GST_TAX, CSR, OTHER). Benchmarked (in industry_benchmarks.json): ['BANKING_TREASURY', 'BRSR_ESG', 'CONTINGENT', 'FACILITIES', 'FIN_SVCS', 'HR', 'INSURANCE', 'IT', 'LOGISTICS', 'LOGISTICS_INDIA', 'MARKETING', 'OFFICE', 'OUTSOURCED', 'PACKAGING', 'PLANT_MAINTENANCE', 'POWER_ENERGY', 'PROF_SVCS', 'RELATED_PARTY', 'RND', 'TELECOM', 'TRAVEL']. Missing commercially significant India categories: POWER_ENERGY, PLANT_MAINTENANCE, LOGISTICS_INDIA, BANKING_TREASURY, PACKAGING.

**Remediation:** Priority: (1) POWER_ENERGY — CEA sector-average tariff + BEE intensity metrics. (2) PLANT_MAINTENANCE — BSE/MCA filing ratios. (3) LOGISTICS_INDIA — CRISIL Industry Report averages. (4) BANKING_TREASURY — RBI data. (5) PACKAGING — industry association data. Adding these 5 raises coverage from 100% to ~124%.

**Key evidence:**
```json
{
  "total_taxonomy_categories": 24,
  "covered_addressable": [
    "BANKING_TREASURY",
    "BRSR_ESG",
    "CONTINGENT",
    "FACILITIES",
    "FIN_SVCS",
    "HR",
    "INSURANCE",
    "IT",
    "LOGISTICS",
    "LOGISTICS_INDIA",
    "MARKETING",
    "OFFICE",
    "OUTSOURCED",
    "PACKAGING",
    "PLANT_MAINTENANCE",
    "POWER_ENERGY",
    "PROF_SVCS",
    "RELATED_PARTY",
    "RND",
    "TELECOM",
    "TRAVEL"
  ],
  "missing_addressable": [],
  "coverage_pct": "100.0%"
}
```

#### BA_06 — Heuristic Target Taxonomy Coverage `PASS` 10.0/10

**Summary:** 21/21 addressable categories have heuristic targets (100%).

**Detail:** heuristic_targets.json covers 21 categories. Against 21 addressable: 21 covered, 0 missing. Missing: [].

**Remediation:** Add heuristic targets (% of revenue) for: []. Priority for India: POWER_ENERGY (3–8% heavy industry), PLANT_MAINTENANCE (1.5–4%), LOGISTICS_INDIA (4–8% manufacturing). Add 'currency' and 'geography' fields simultaneously (see BA_02).

**Key evidence:**
```json
{
  "covered": [
    "BANKING_TREASURY",
    "BRSR_ESG",
    "CONTINGENT",
    "FACILITIES",
    "FIN_SVCS",
    "HR",
    "INSURANCE",
    "IT",
    "LOGISTICS",
    "LOGISTICS_INDIA",
    "MARKETING",
    "OFFICE",
    "OUTSOURCED",
    "PACKAGING",
    "PLANT_MAINTENANCE",
    "POWER_ENERGY",
    "PROF_SVCS",
    "RELATED_PARTY",
    "RND",
    "TELECOM",
    "TRAVEL"
  ],
  "missing": [],
  "coverage_pct": "100.0%"
}
```

#### BA_07 — Licensed Benchmark Stub Transparency `PASS` 10.0/10

**Summary:** 15/15 packs have benchmark_sources.yaml. Stubs transparent: yes. Adapters: ['CmieAdapter', 'CapitalineAdapter'].

**Detail:** Packs with benchmark_sources.yaml: ['healthcare_hospitals', 'bfsi_banks', 'telecom_infra', 'fmcg_consumer', 'conglomerate', 'psu_cpse', 'hospitality_travel', 'insurance_general', 'gcc_capability_centers', 'it_ites', 'energy_utilities', 'retail_organized', 'financial_services_nonbank', 'manufacturing_diversified', 'pharma_lifesciences']. Transparency (licensed_sources_stubs key present): True. Adapter classes found in benchmarks_india.py: ['CmieAdapter', 'CapitalineAdapter']. Score: 0.4×10.0 + 0.3×10.0 + 0.3×10.0 = 10.0.

**Remediation:** Add benchmark_sources.yaml stubs to the remaining 0 sector packs listing free data sources (BSE filings, BRSR, MCA21, sector-specific free sources). This raises pack coverage to 100% and scores this dimension fully.

**Key evidence:**
```json
{
  "total_sector_packs": 15,
  "packs_with_benchmark_sources_yaml": [
    "healthcare_hospitals",
    "bfsi_banks",
    "telecom_infra",
    "fmcg_consumer",
    "conglomerate",
    "psu_cpse",
    "hospitality_travel",
    "insurance_general",
    "gcc_capability_centers",
    "it_ites",
    "energy_utilities",
    "retail_organized",
    "financial_services_nonbank",
    "manufacturing_diversified",
    "pharma_lifesciences"
  ],
  "pack_coverage_pct": "100.0%",
  "transparency_label_found": true,
  "adapter_classes_found": [
    "CmieAdapter",
    "CapitalineAdapter"
  ],
  "adapter_classes_missing": []
}
```


---

## Top 10 Gaps (ranked by severity)

| Rank | ID | Gap | Severity | Domain | Remediation (brief) |
|------|----|-----|----------|--------|---------------------|

---

## Remediation Roadmap


---

## Appendix — Raw Dimension Scores

```json
{
  "overall_score": 10.0,
  "passed": true,
  "eval_date": "2026-05-30",
  "domains": [
    {
      "name": "lever_coverage",
      "score": 10.0,
      "passed": true,
      "dimensions": [
        {
          "id": "lc_01",
          "score": 10.0,
          "threshold": 7.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "lc_02",
          "score": 10.0,
          "threshold": 8.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "lc_03",
          "score": 10.0,
          "threshold": 7.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "lc_04",
          "score": 10.0,
          "threshold": 8.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "lc_05",
          "score": 10.0,
          "threshold": 8.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "lc_06",
          "score": 10.0,
          "threshold": 7.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "lc_07",
          "score": 10.0,
          "threshold": 9.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "lc_08",
          "score": 10.0,
          "threshold": 7.0,
          "passed": true,
          "gap": 0.0
        }
      ]
    },
    {
      "name": "benchmark_authenticity",
      "score": 10.0,
      "passed": true,
      "dimensions": [
        {
          "id": "ba_01",
          "score": 10.0,
          "threshold": 7.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "ba_02",
          "score": 10.0,
          "threshold": 7.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "ba_03",
          "score": 10.0,
          "threshold": 7.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "ba_04",
          "score": 10.0,
          "threshold": 6.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "ba_05",
          "score": 10.0,
          "threshold": 6.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "ba_06",
          "score": 10.0,
          "threshold": 6.0,
          "passed": true,
          "gap": 0.0
        },
        {
          "id": "ba_07",
          "score": 10.0,
          "threshold": 5.0,
          "passed": true,
          "gap": 0.0
        }
      ]
    }
  ]
}
```