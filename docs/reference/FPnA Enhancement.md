# OpEx Intelligence Platform — FP&A Enhancement Plan
## Addressing the Domain Gaps for CFO-Grade Output

**Author:** Pallav Chaturvedi | **Version:** 1.0 | **Date:** March 2026  
**Basis:** FP&A domain review of v1.0 PRD and OPAR Loop Specification

---

## 0. Challenge-to-Solution Map

| # | Domain Challenge | Root Cause | Solution | Priority Shift |
|---|-----------------|-----------|----------|---------------|
| 1 | Savings math is outside-in, won't survive CFO review | No phasing, no cost-to-achieve, no NPV | New `savings-modeler` skill + time-dimensioned value bridge | P2 → **P0** |
| 2 | Benchmarking identifies WHERE, not WHY | No diagnostic layer between benchmark and savings | New `root-cause-analyzer` skill inserted in skill DAG | New → **P1** |
| 3 | Spend taxonomy too high-level for actionable analysis | Missing fixed/variable split and discretionary tagging | Enhanced `spend-profiler` with cost behaviour classification | P0 enhancement |
| 4 | Savings pipeline is P2 but should be P0 | Platform tracks identified savings only, not committed or realized | New pipeline data model + `pipeline-tracker` skill | P2 → **P0** |
| 5 | Memory misses institutional decisions | No organizational decision log | New Mem0 memory schema + Observe-phase filtering | P0 enhancement |
| 6 | Benchmark data strategy is existential, not open | No data quality metadata, no source specificity scoring | Three-tier benchmark architecture + BenchmarkDataset entity | P0 blocker |

---

## 1. New Skills

### 1.1 `root-cause-analyzer`

**Position in Skill DAG:** Sits between `peer-benchmarker`/`internal-benchmarker` and `value-bridge-calculator`. Triggered automatically for any category that scores above the 60th percentile vs. peers.

**Purpose:** Converts a benchmark gap (the "where") into a ranked list of root causes (the "why"), each mapped to a specific value lever and implementation approach. Without this layer, savings recommendations have no story — and a number without a story doesn't get funded.

**Input:**
```python
{
  "category": "IT & Technology",
  "total_spend": 42_000_000,
  "peer_percentile": 73,
  "spend_line_items": [...],      # from spend-profiler output
  "supplier_list": [...],         # supplier name, spend amount, PO flag
  "headcount": 1200,              # optional — improves demand analysis
  "transaction_count": 8400       # optional — improves demand analysis
}
```

**Diagnostic Lenses Applied:**

| Lens | Metric | Signal | Recommended Lever |
|------|--------|--------|-------------------|
| Spend concentration | Herfindahl-Hirschman Index on supplier spend | HHI < 0.15 → fragmented supply base | Supplier consolidation |
| Demand analysis | Cost per transaction vs. peer norm | >20% above norm → over-consumption | Demand management / policy |
| Specification analysis | Avg. unit cost vs. peer median | >15% above median → buying above spec | Specification optimization |
| Contract compliance | % spend on PO vs. off-PO (maverick) | Maverick > 20% → contract discipline gap | Procurement process |
| Geographic premium | Cost index adjustment by location | Adjusted spend still above median → genuine excess | Cost structure redesign |

**Output:**
```python
{
  "category": "IT & Technology",
  "root_causes": [
    {
      "diagnosis": "SaaS proliferation — 47 active software vendors, HHI 0.09",
      "confidence": "high",
      "addressable_spend": 8_400_000,
      "recommended_lever": "supplier_consolidation",
      "implementation_approach": "Software rationalization program with IT governance",
      "implementation_complexity": "medium",   # low | medium | high
      "estimated_timeline_months": 12
    },
    ...
  ],
  "non_addressable_rationale": "18.2M in multi-year enterprise agreements (Microsoft EA expires 2027, AWS committed use through 2026)"
}
```

**SKILL.md Reference Data Required:**
- `hhi_benchmarks.json` — industry-typical HHI ranges by category
- `unit_cost_benchmarks.json` — cost-per-transaction, cost-per-seat norms by vertical
- `maverick_spend_thresholds.json` — typical PO compliance rates by category and industry

---

### 1.2 `savings-modeler`

**Position in Skill DAG:** Replaces/supersedes the savings calculation within `value-bridge-calculator`. Takes value bridge raw gaps and converts them into a phased, risk-adjusted, NPV-based savings model.

**Purpose:** The original `Savings = Addressable Spend × Savings Rate × Confidence Factor` formula produces a static savings estimate. A CFO review requires a phased savings curve with cost-to-achieve netted out and NPV calculated. This skill produces that output.

**Input:**
```python
{
  "value_bridge_raw": {...},          # output from value-bridge-calculator
  "root_cause_outputs": {...},         # output from root-cause-analyzer
  "discount_rate": 0.10,              # user-configurable, default 10%
  "planning_horizon_years": 3,
  "cost_to_achieve_inputs": {          # user-provided or defaults applied
    "IT & Technology": {
      "consulting_fees": 500_000,
      "technology_investment": 200_000,
      "internal_resource_cost": 150_000
    }
  }
}
```

**Phasing Curves by Lever Type (defaults, user-overridable):**

| Lever | Y1 Realisation | Y2 Realisation | Y3 Realisation | Rationale |
|-------|---------------|---------------|---------------|-----------|
| Peer benchmarking (contract renegotiation) | 15% | 55% | 30% | Contracts renew at different times; savings back-loaded |
| Internal benchmarking (best-practice adoption) | 30% | 45% | 25% | Process changes take hold in Y1-2 |
| Heuristic / demand management | 40% | 40% | 20% | Policy changes faster than structural changes |
| AI / automation | 10% | 35% | 55% | Technology implementation and adoption lag |
| Supplier consolidation | 20% | 50% | 30% | RFP cycles and contract transitions |

**Output:**
```python
{
  "category": "IT & Technology",
  "lever": "supplier_consolidation",
  "gross_savings": {
    "y1": 1_260_000,    # 42M addressable × 15% savings rate × 0.9 conf × 20% phasing
    "y2": 3_150_000,
    "y3": 1_890_000,
    "total_3yr": 6_300_000
  },
  "cost_to_achieve": {
    "y1": 650_000,      # consulting + tech + internal resource
    "y2": 200_000,      # ongoing programme management
    "y3": 0,
    "total_3yr": 850_000
  },
  "net_savings": {
    "y1": 610_000,
    "y2": 2_950_000,
    "y3": 1_890_000,
    "total_3yr": 5_450_000,
    "npv_10pct": 4_380_000    # NPV of 3yr net savings at 10% discount rate
  },
  "payback_months": 13
}
```

**New Value Bridge Output Format** (replaces static matrix):

| Category | Lever | Root Cause | Gross 3yr | Cost-to-Achieve | Net NPV | Payback | Confidence |
|----------|-------|-----------|-----------|----------------|---------|---------|-----------|
| IT & Technology | Supplier consolidation | SaaS proliferation (47 vendors) | $6.3M | $0.85M | $4.4M | 13 months | High |
| IT & Technology | Contract renegotiation | Microsoft EA renewal 2027 | $3.1M | $0.25M | $2.6M | 18 months | Mid |
| Professional Services | Demand management | Above-norm consulting intensity | $1.9M | $0.10M | $1.7M | 8 months | Mid |

---

### 1.3 `pipeline-tracker`

**Position in Skill DAG:** Invoked on-demand (monthly/quarterly review trigger) or when user asks about savings progress. Not part of the primary analysis DAG — operates on the SavingsInitiative data model.

**Purpose:** Generates a monthly pipeline review: what's been identified, what's been committed to budget, what's in-flight, and what's been realized vs. target. This is the mechanism by which the platform creates durable value beyond the initial analysis.

**Input:**
```python
{
  "user_id": "...",
  "reporting_period": "2026-Q1",
  "include_categories": ["all"],    # or specific categories
  "actuals_data": [...]             # optional: GL actuals if uploaded
}
```

**Output:** A structured pipeline waterfall report with:
- Identified → Committed → In-Flight → Realized waterfall (quantities and %)
- At-risk initiatives (past milestone dates, no actuals recorded)
- Variance analysis: committed vs. realized savings, with root cause of gaps
- Recommended actions for stalled initiatives

---

## 2. Enhanced Existing Skills

### 2.1 `spend-profiler` — Cost Behaviour Classification

**What's Added:** A second classification pass after the existing taxonomy mapping. Each spend line item is tagged with:

**Fixed / Variable / Semi-Variable:**
```python
COST_BEHAVIOUR_RULES = {
    "IT & Technology": {
        "Software licenses (enterprise)":  "fixed",        # multi-year EA
        "Software licenses (SaaS monthly)": "variable",    # cancellable
        "Cloud infrastructure":             "semi_variable", # committed + on-demand
        "IT support & helpdesk":            "semi_variable",
        "Hardware":                         "variable",
    },
    "Facilities & Real Estate": {
        "Rent / lease":                    "fixed",
        "Utilities":                       "semi_variable",
        "Maintenance & repairs":           "variable",
        "Facilities projects":             "variable",
    },
    # ... all 25 categories
}
```

**Discretionary / Non-Discretionary:**
```python
DISCRETIONARY_RULES = {
    "Travel & Entertainment":              "discretionary",
    "Training & development":              "discretionary",
    "Marketing & advertising":             "discretionary",
    "IT & Technology - enterprise licenses": "non_discretionary",
    "Facilities - rent":                   "non_discretionary",
    # Rules + user override for edge cases
}
```

**Impact on Addressable Spend Calculation:**

The addressable spend input to `value-bridge-calculator` and `savings-modeler` becomes:

```
Addressable Spend(C) = Variable Spend(C) × 1.0
                     + Semi-Variable Spend(C) × 0.6    (default, user-adjustable)
                     + Fixed Spend(C) × 0.0            (locked, not addressable)
                     + Discretionary Override(C)        (user can include/exclude)
```

This single change can cut the gross savings estimate by 40–60% for categories with high fixed cost components — which is exactly what makes the output credible rather than aspirational.

---

### 2.2 `peer-benchmarker` — Benchmark Source Metadata

**What's Added:** Every benchmark data point now carries source metadata that flows through to the Reflect confidence scoring.

```python
@dataclass
class BenchmarkDataPoint:
    value:                float
    percentile_rank:      float
    source:               str          # 'IBISWorld' | 'Hackett' | 'BLS' | 'platform_derived'
    vintage_date:         date         # data collection date
    sample_size:          int
    industry_specificity: float        # 0.0 (cross-industry) → 1.0 (exact vertical match)
    geography_match:      bool
    revenue_band_match:   bool         # company size comparable to benchmark population
```

**Reflect confidence scoring is updated** to penalise low-specificity sources:

```python
def score_benchmark_confidence(datapoint: BenchmarkDataPoint) -> ConfidenceScore:
    base = 0.9 if datapoint.industry_specificity > 0.8 else \
           0.75 if datapoint.industry_specificity > 0.5 else 0.5

    # Staleness penalty: -0.1 per year beyond 12 months
    age_months = (today - datapoint.vintage_date).days / 30
    staleness_penalty = max(0, (age_months - 12) / 12) * 0.1

    # Size mismatch penalty
    size_penalty = 0.1 if not datapoint.revenue_band_match else 0

    return ConfidenceScore(
        factor=max(0.3, base - staleness_penalty - size_penalty),
        rationale=f"Source: {datapoint.source}, vintage: {datapoint.vintage_date}, "
                  f"specificity: {datapoint.industry_specificity:.0%}"
    )
```

---

### 2.3 `value-bridge-calculator` — Double-Counting Prevention

**What's Added:** Before aggregating savings across levers, the calculator checks committed initiatives loaded from the SavingsInitiative pipeline (via Observe phase) and excludes savings already captured in committed or in-flight initiatives.

```python
def prevent_double_counting(raw_savings: dict, committed_initiatives: list) -> dict:
    committed_savings_by_category_lever = {
        (i.category, i.lever): i.committed_savings
        for i in committed_initiatives
        if i.stage in ('committed', 'in_flight', 'realized')
    }

    adjusted_savings = {}
    for (category, lever), savings in raw_savings.items():
        already_committed = committed_savings_by_category_lever.get((category, lever), 0)
        adjusted_savings[(category, lever)] = max(0, savings - already_committed)

    return adjusted_savings
```

---

## 3. Data Model Additions

### 3.1 Savings Pipeline Entities

```sql
-- Promotes from P2 to P0

CREATE TABLE savings_initiative (
    initiative_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id         UUID REFERENCES analysis(analysis_id),
    category            VARCHAR(100) NOT NULL,
    lever               VARCHAR(100) NOT NULL,
    root_cause          TEXT,
    -- Financials
    gross_savings_y1    DECIMAL(15,2),
    gross_savings_y2    DECIMAL(15,2),
    gross_savings_y3    DECIMAL(15,2),
    cost_to_achieve     DECIMAL(15,2),
    net_npv             DECIMAL(15,2),
    -- Pipeline stage
    stage               VARCHAR(50) DEFAULT 'identified',
                        -- identified | committed | in_flight | realized | rejected
    rejection_reason    TEXT,        -- populated if stage = 'rejected'
    owner_name          VARCHAR(200),
    owner_email         VARCHAR(200),
    committed_date      DATE,
    target_realization_date DATE,
    -- Tracking
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE initiative_milestone (
    milestone_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    initiative_id       UUID REFERENCES savings_initiative(initiative_id),
    description         TEXT NOT NULL,
    due_date            DATE NOT NULL,
    status              VARCHAR(50) DEFAULT 'pending',  -- pending | complete | at_risk | missed
    evidence_doc_ref    VARCHAR(500),   -- S3 key of supporting document
    completed_at        DATE
);

CREATE TABLE initiative_actuals (
    actuals_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    initiative_id       UUID REFERENCES savings_initiative(initiative_id),
    period              VARCHAR(7) NOT NULL,    -- 'YYYY-MM'
    actual_savings      DECIMAL(15,2) NOT NULL,
    committed_savings   DECIMAL(15,2),          -- snapshot of committed target at time of entry
    variance            DECIMAL(15,2)           -- actual - committed (computed)
                        GENERATED ALWAYS AS (actual_savings - committed_savings) STORED,
    gl_reference        VARCHAR(200),           -- GL account or cost centre reference
    notes               TEXT
);
```

### 3.2 Benchmark Dataset Registry

```sql
CREATE TABLE benchmark_dataset (
    dataset_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source              VARCHAR(100) NOT NULL,  -- 'IBISWorld' | 'Hackett' | 'BLS' | 'platform'
    industry_code       VARCHAR(20),            -- NAICS or SIC code
    industry_name       VARCHAR(200),
    category_coverage   JSONB,                  -- list of categories this dataset covers
    vintage_date        DATE NOT NULL,
    sample_size         INTEGER,
    revenue_band_min    DECIMAL(15,0),
    revenue_band_max    DECIMAL(15,0),
    geography           VARCHAR(100),
    specificity_score   DECIMAL(3,2),           -- 0.00–1.00
    license_expiry      DATE,
    data_file_ref       VARCHAR(500),           -- S3 key
    ingested_at         TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.3 Additions to Existing Entities

```sql
-- SpendRecord: add cost behaviour tags (spend-profiler enhanced output)
ALTER TABLE spend_record ADD COLUMN cost_behaviour     VARCHAR(20);   -- fixed|variable|semi_variable
ALTER TABLE spend_record ADD COLUMN is_discretionary   BOOLEAN;
ALTER TABLE spend_record ADD COLUMN addressability_pct DECIMAL(5,2);  -- 0–100

-- Analysis: add link to benchmark source used
ALTER TABLE analysis ADD COLUMN benchmark_dataset_id UUID REFERENCES benchmark_dataset(dataset_id);
ALTER TABLE analysis ADD COLUMN benchmark_specificity DECIMAL(3,2);

-- ValueBridge: add phased savings and NPV columns
ALTER TABLE value_bridge ADD COLUMN savings_y1        DECIMAL(15,2);
ALTER TABLE value_bridge ADD COLUMN savings_y2        DECIMAL(15,2);
ALTER TABLE value_bridge ADD COLUMN savings_y3        DECIMAL(15,2);
ALTER TABLE value_bridge ADD COLUMN cost_to_achieve   DECIMAL(15,2);
ALTER TABLE value_bridge ADD COLUMN net_npv           DECIMAL(15,2);
ALTER TABLE value_bridge ADD COLUMN payback_months    INTEGER;
ALTER TABLE value_bridge ADD COLUMN root_cause        TEXT;
```

---

## 4. OPAR Loop Changes by Phase

### 4.1 OBSERVE — Three New Inputs

**1. Pipeline state loading**

At the start of every session, the orchestrator loads open SavingsInitiative records for the current user. These are injected into ObserveContext to prevent double-counting in Plan and Act.

```python
@dataclass
class ObserveContext:
    # ... existing fields ...

    # NEW: Pipeline context
    committed_initiatives:  list[SavingsInitiative]   # stage: committed | in_flight
    realized_initiatives:   list[SavingsInitiative]   # stage: realized
    rejected_initiatives:   list[SavingsInitiative]   # stage: rejected — excluded from Plan

    # NEW: Institutional context (from Mem0 user_memory)
    locked_categories:      list[str]     # categories declared off-limits by user
    org_decisions_pending:  list[str]     # e.g. 'return-to-office policy under review'
    budget_cycle_deadline:  date | None   # when does the next budget freeze hit?
```

**2. Institutional context from Mem0**

New memory categories read in Observe:

```python
async def load_institutional_context(user_id: str) -> dict:
    memories = await mem0.get_all(user_id=user_id)
    return {
        "locked_categories":     extract_by_tag(memories, "locked_category"),
        "rejected_initiatives":  extract_by_tag(memories, "rejected_initiative"),
        "committed_initiatives": extract_by_tag(memories, "committed_initiative"),
        "pending_decisions":     extract_by_tag(memories, "pending_org_decision"),
    }
```

**3. Budget cycle awareness**

If `budget_cycle_deadline` is within 60 days, the Observe phase sets `urgency_flag = True`, which biases the Plan toward quick-win initiatives (high Y1 realisation) rather than structural programmes.

---

### 4.2 PLAN — Updated Skill DAG

**New DAG with root-cause-analyzer inserted:**

```
Group 0:  spend-profiler
            ↓
Group 1:  peer-benchmarker (parallel) | internal-benchmarker (parallel) | heuristic-analyzer (parallel)
            ↓
Group 2:  root-cause-analyzer         ← NEW: runs on categories above 60th percentile
            ↓
Group 3:  savings-modeler             ← ENHANCED: replaces savings calc in value-bridge
            ↓
Group 4:  value-bridge-calculator     ← now aggregates modeler outputs + applies double-counting prevention
            ↓
Group 5:  business-case-builder
```

**New planning rules:**
```python
PLANNING_RULES = [
    # Existing rules...
    "root-cause-analyzer runs after benchmarkers, only for categories above 60th percentile peer rank",
    "savings-modeler runs after root-cause-analyzer; receives root cause output as primary input",
    "value-bridge-calculator receives savings-modeler output, not raw benchmark gaps",
    "Exclude levers where root cause maps to rejected_initiative in ObserveContext",
    "Exclude locked_categories from all analysis regardless of benchmark position",
    "If budget_cycle_deadline within 60 days, prioritise levers with payback_months < 12",
    "If committed_initiative exists for category+lever, set addressable_spend -= committed_savings",
]
```

**User-visible plan summary now includes:**
> *"I'll benchmark IT & Technology and Professional Services, diagnose the root causes of any gaps, then build a phased 3-year savings model with NPV. I'll exclude the Microsoft EA (locked until 2027) and the IT helpdesk outsourcing initiative already in your pipeline. This will take approximately 90 seconds."*

---

### 4.3 ACT — Pipeline Auto-Creation

After `business-case-builder` completes, the Act phase automatically creates a `SavingsInitiative` record in `identified` stage for each category × lever in the business case output. This happens before the response is returned to the user.

```python
async def post_business_case_actions(business_case: BusinessCaseOutput,
                                     session_id: str, user_id: str):
    for initiative in business_case.initiatives:
        await db.execute("""
            INSERT INTO savings_initiative
            (analysis_id, category, lever, root_cause,
             gross_savings_y1, gross_savings_y2, gross_savings_y3,
             cost_to_achieve, net_npv, stage)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'identified')
        """, session_id, initiative.category, initiative.lever,
             initiative.root_cause, initiative.y1, initiative.y2, initiative.y3,
             initiative.cost_to_achieve, initiative.npv)
```

The user sees in the chat response: *"I've added 3 initiatives to your savings pipeline. You can promote them to 'committed' once approved by your CFO."*

---

### 4.4 REFLECT — Enhanced Confidence Scoring

**Benchmark specificity now drives confidence:**

```python
def compute_confidence(category: str, lever: str,
                       benchmark_dp: BenchmarkDataPoint,
                       root_cause_confidence: str,
                       data_quality_score: float) -> ConfidenceScore:

    # Benchmark source quality
    bench_score = score_benchmark_confidence(benchmark_dp)   # uses new method from §2.2

    # Root cause confidence
    rc_score = 0.9 if root_cause_confidence == 'high' else \
               0.75 if root_cause_confidence == 'medium' else 0.5

    # Data quality
    dq_score = data_quality_score  # 0.0–1.0 from Observe phase

    # Weighted composite
    composite = (bench_score.factor * 0.40) + (rc_score * 0.35) + (dq_score * 0.25)

    level = 'high' if composite >= 0.8 else 'mid' if composite >= 0.6 else 'low'
    return ConfidenceScore(factor=composite, level=level,
                           rationale=f"Benchmark: {bench_score.factor:.0%}, "
                                     f"Root cause: {rc_score:.0%}, "
                                     f"Data quality: {dq_score:.0%}")
```

**New Reflect validation checks:**
- NPV sign: if net_npv is negative after cost-to-achieve, flag initiative as not investable (not just low confidence)
- Payback sanity: payback_months > 60 triggers a flag — surfaced to user as a questionable initiative
- Pipeline overlap: verify double-counting prevention ran correctly; flag if committed_savings > gross_savings for any cell
- Rejected initiative suppression: confirm no rejected initiative appears in the output

**Memory writes extended:**

```python
# After a user rejects or accepts an initiative recommendation:
await mem0.add(
    messages=[{'role': 'system', 'content':
        f"User rejected savings initiative: category={category}, lever={lever}, "
        f"reason={rejection_reason}, date={today}"}],
    user_id=user_id,
    metadata={'tag': 'rejected_initiative', 'category': category, 'lever': lever}
)

# After CFO/CPO commits to an initiative:
await mem0.add(
    messages=[{'role': 'system', 'content':
        f"Committed initiative: category={category}, lever={lever}, "
        f"committed_savings={committed_savings}, owner={owner_name}"}],
    user_id=user_id,
    metadata={'tag': 'committed_initiative', 'initiative_id': initiative_id}
)
```

---

## 5. New API Endpoints

### 5.1 Pipeline Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/initiatives` | GET | List all savings initiatives for user; filterable by stage, category, lever |
| `/api/v1/initiatives` | POST | Manually create an initiative (e.g., from offline analysis) |
| `/api/v1/initiatives/{id}/stage` | PUT | Advance stage: identified → committed → in_flight → realized |
| `/api/v1/initiatives/{id}/reject` | PUT | Reject initiative with mandatory reason; writes to Mem0 |
| `/api/v1/initiatives/{id}/milestones` | GET/POST | Manage initiative milestones |
| `/api/v1/initiatives/{id}/actuals` | POST | Record actual savings for a period |
| `/api/v1/pipeline/summary` | GET | Waterfall summary: identified → committed → realized with variance |
| `/api/v1/pipeline/at-risk` | GET | Initiatives past milestone dates or below actuals trajectory |

### 5.2 Benchmark Data Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/benchmarks` | GET | List available benchmark datasets with coverage and vintage |
| `/api/v1/benchmarks` | POST | Ingest a new benchmark dataset (admin only) |
| `/api/v1/benchmarks/{id}/coverage` | GET | Category coverage and specificity scores for a dataset |
| `/api/v1/benchmarks/select` | POST | Given industry + categories, return best-fit benchmark dataset |

### 5.3 Organizational Context

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/context/locked-categories` | GET/PUT | Declare categories as off-limits for analysis |
| `/api/v1/context/org-decisions` | GET/POST | Log pending organizational decisions that affect spend |
| `/api/v1/context/budget-calendar` | GET/PUT | Set budget cycle deadlines for urgency-aware planning |

---

## 6. Mem0 Memory Schema Additions

### New Memory Tags and What Triggers Them

| Tag | Written When | Read When | Effect in Observe |
|-----|-------------|-----------|-------------------|
| `rejected_initiative` | User explicitly rejects a recommendation | Every session start | Excluded from Plan; never re-surfaced as a recommendation |
| `committed_initiative` | Initiative promoted to 'committed' stage | Every session start | Deducted from addressable savings in value-bridge |
| `locked_category` | User declares category off-limits | Every session start | Category excluded from all benchmarking and analysis |
| `pending_org_decision` | User logs a pending decision affecting spend | Every session start | Injected as caveat into relevant analysis outputs |
| `budget_cycle_deadline` | User sets planning calendar | Every session start | Biases Plan toward short-payback initiatives if deadline < 60 days |
| `rejected_benchmark_source` | User flags a benchmark source as unreliable | Every benchmarker invocation | Excluded from peer-benchmarker reference data selection |

### Example Memory Objects

```python
# Rejected initiative
{
  "tag": "rejected_initiative",
  "category": "IT & Technology",
  "lever": "outsourcing",
  "reason": "Board decided to keep IT in-house for IP protection reasons",
  "decided_by": "CFO",
  "date": "2025-11-15"
}

# Locked category
{
  "tag": "locked_category",
  "category": "Facilities & Real Estate",
  "reason": "All leases locked until 2028; real estate team handling separately",
  "expires": "2028-01-01"    # Observe will auto-unlock after this date
}

# Pending organizational decision
{
  "tag": "pending_org_decision",
  "affects_category": "Travel & Entertainment",
  "decision": "Return-to-office policy under board review",
  "expected_resolution": "2026-Q2",
  "implication": "T&E spend benchmark comparison deferred until policy confirmed"
}
```

---

## 7. Benchmark Data Strategy (Three-Tier Architecture)

This resolves Open Question #1 from the PRD and treats it as the P0 blocker it is.

### Tier 1 — Licensed Data (Primary Source)

| Provider | Coverage | Cost | Vintage | Recommendation |
|----------|----------|------|---------|----------------|
| Hackett Group | IT, Finance, HR, Procurement | $$$$ | 12–18mo | Best for process-intensive categories |
| IBISWorld | All OpEx categories by industry | $$$ | 12–24mo | Best for manufacturing, retail, logistics |
| Gartner | IT-specific (detailed sub-categories) | $$$$ | 6–12mo | Essential for IT benchmarking credibility |

**Decision rule:** License minimum 2 providers to enable cross-validation. Start with IBISWorld (broadest category + industry coverage) + Hackett (depth on IT/Finance which are highest-value categories).

### Tier 2 — Public Proxy Sources (Supplementary)

| Source | What It Provides | Limitation |
|--------|-----------------|-----------|
| BLS Industry Data | Labor cost by industry and occupation | Only covers labor-related OpEx |
| SEC EDGAR 10-K filings | Publicly reported SG&A breakdowns | Very high-level; no category detail |
| Eurostat | EU enterprise cost structures | Geography-limited; useful for European deployments |
| Public procurement databases (USASpending.gov) | Government contract rates | Public sector only |

**Use:** Fill coverage gaps where Tier 1 licenses don't cover specific categories or verticals. Tag as low-specificity in BenchmarkDataPoint — Reflect will apply appropriate confidence penalty.

### Tier 3 — Platform-Derived (Long-Term Moat)

As the user base grows, anonymized and aggregated spend data from consenting users becomes the most valuable benchmark source — it's current, highly specific, and proprietary.

**Engineering requirements:**
- Opt-in consent mechanism at onboarding
- Anonymization pipeline: strip company identifiers, aggregate to NAICS 4-digit level, require minimum 5 companies per cell before publishing
- `platform_derived` tag in BenchmarkDataset; specificity_score based on sample_size and industry granularity
- Version each platform benchmark quarterly

**Timeline to usability:** 12–18 months of user data collection. Tier 3 augments, never replaces, Tier 1 in early product lifecycle.

### Benchmark Selection Logic in `peer-benchmarker`

```python
def select_benchmark(category: str, industry_vertical: str,
                     revenue_band: str) -> BenchmarkDataset:
    candidates = db.query("""
        SELECT * FROM benchmark_dataset
        WHERE $1 = ANY(category_coverage)
        AND ($2 IS NULL OR industry_code LIKE $2 || '%')
        AND ($3 IS NULL OR (revenue_band_min <= $3 AND revenue_band_max >= $3))
        AND license_expiry > NOW()
        ORDER BY specificity_score DESC, vintage_date DESC
        LIMIT 1
    """, category, industry_naics_code(industry_vertical), revenue_midpoint(revenue_band))

    if not candidates:
        # Fall back to Tier 2 proxy
        return get_public_proxy_benchmark(category, industry_vertical)

    return candidates[0]
```

---

## 8. Revised Phasing

### What Moves and Why

| Item | Original Phase | New Phase | Reason |
|------|---------------|-----------|--------|
| Savings pipeline tracking (SavingsInitiative entity + API) | P2 | **P0** | Without it, identified savings are stranded — no path to realized savings |
| Cost behaviour classification in spend-profiler | P0 (not in scope) | **P0** | Addressable spend calculation is wrong without fixed/variable split |
| Root-cause-analyzer skill | Not in PRD | **P1** | Required to make business cases credible and defensible |
| Savings-modeler skill (phased NPV) | Not in PRD | **P1** | Required for CFO-grade output; replaces static savings formula |
| Benchmark source metadata + specificity scoring | Not in PRD | **P1** | Required for honest confidence scoring |
| Benchmark data strategy decision | Open question | **P0 blocker** | Phase 1 cannot build peer-benchmarker without a benchmark data source |
| Institutional context memory schema | Not in PRD | **P0** | Prevents the system from re-recommending rejected initiatives from session 1 |
| Pipeline tracker skill | Not in PRD | **P2** | Valuable but not blocking; pipeline UI comes first |

### Revised Build Sequence

**Phase 0 (Weeks 1–4): Foundation + Domain Corrections**
- FastAPI scaffold, Claude SDK integration, Mem0 setup, chat UI, file upload pipeline
- Benchmark data licensing decision finalized (blocking gate — do not proceed to Phase 1 without this)
- `spend-profiler` with fixed/variable classification and discretionary tagging
- `SavingsInitiative`, `Milestone`, `ActualsEntry` tables created (schema only, no UI)
- New Mem0 memory schema: rejected_initiative, locked_category, pending_org_decision tags
- Updated ObserveContext with pipeline state and institutional context loading

**Phase 1 (Weeks 5–10): Core Analysis with Domain Depth**
- `peer-benchmarker` with BenchmarkDataset source selection and specificity metadata
- `internal-benchmarker` with BU variance detection
- `heuristic-analyzer` (if headcount/revenue data available)
- `root-cause-analyzer` with 5 diagnostic lenses and reference data
- `savings-modeler` with phased savings curves and NPV calculation
- `value-bridge-calculator` with double-counting prevention
- Updated Reflect confidence scoring (3-factor weighted composite)
- Pipeline auto-creation after business-case-builder

**Phase 2 (Weeks 11–14): Business Case and Pipeline Management**
- `business-case-builder` with NPV-based financial projections
- Pipeline management UI: stage advancement, owner assignment, milestone tracking
- Skills management UI
- `/api/v1/pipeline` endpoints
- Organizational context settings panel (locked categories, pending decisions)
- Export to .docx / .pdf / .pptx

**Phase 3 (Weeks 15–18): Tracking, Visualization, and Platform Benchmark**
- `pipeline-tracker` skill for monthly review output
- Actuals entry and variance analysis
- Chart.js dashboard: pipeline waterfall, savings trajectory, category heat map
- Platform-derived benchmark data collection pipeline (opt-in, anonymized)
- Redis caching for Mem0 user_memory fetches

---

## 9. Key Design Principles Reinforced

**Credibility over coverage.** It is better to surface 3 high-confidence savings opportunities with transparent assumptions than 10 opportunities with opaque confidence. Every number the platform shows should be defensible in a CFO review.

**The pipeline is the product.** A one-time analysis generates a report. An active savings pipeline creates a reason to return to the platform every month. Design every feature with the question: does this help the user move savings from identified to realized?

**Institutional memory is a moat.** A platform that knows which initiatives were rejected and why, which categories are strategically locked, and what organizational decisions are pending is one that a senior FP&A professional cannot easily replace with a spreadsheet or a consulting engagement. Invest in the memory schema accordingly.

**Benchmarks are not gospel.** Every benchmark output must be accompanied by its source, vintage, and specificity score. The platform should never present a benchmark-based number as objective fact — it is always a data-informed hypothesis that requires organizational validation.

---

*OpEx Intelligence Platform — FP&A Enhancement Plan | v1.0 | Pallav Chaturvedi*
