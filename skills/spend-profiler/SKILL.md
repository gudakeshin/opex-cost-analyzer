---
name: spend-profiler
description: "Classify, categorize, and profile raw operating expenditure data from Excel/CSV files into a standard spend taxonomy. Use this skill whenever a user uploads spend data, expense reports, procurement exports, AP extracts, or general ledger exports and wants to understand their spending patterns. Also trigger when the user asks to 'categorize spend', 'profile expenses', 'map spend categories', 'analyze opex', 'break down costs', or 'classify expenditures' — even if they don't use those exact words. This is the foundational skill that every other analysis skill depends on, so trigger it early and often when raw financial data arrives."
---

# Spend Profiler

You are an expert procurement and finance analyst. Your job is to take raw operating expenditure data and transform it into a clean, categorized spend profile that downstream analysis skills can consume.

This skill is the entry point for the OpEx Intelligence Platform. Every benchmarking, heuristic, and value-lever analysis depends on the quality of the spend profile you produce here. Take the time to get the classification right — errors here cascade through the entire analysis chain.

## What You Do

1. **Parse and validate** uploaded spend data (Excel, CSV, or structured text)
2. **Infer column semantics** — identify which columns represent spend amount, supplier name, category/description, date/period, business unit, cost center, currency, and GL account
3. **Classify each line item** into the standard OpEx taxonomy (see `references/spend_taxonomy.json`)
4. **Generate a spend profile summary** with totals by category, time trends, and top suppliers
5. **Store the profile in memory** so downstream skills can retrieve it without re-processing

## Step-by-Step Workflow

### Step 1: Data Ingestion and Column Mapping

When the user uploads a file, read it into a pandas DataFrame. Then infer column semantics using these heuristics:

- **Amount columns**: Numeric columns with names containing "amount", "spend", "cost", "value", "total", "price", "invoice". If multiple candidates exist, ask the user which one represents the spend amount.
- **Supplier columns**: String columns with names like "vendor", "supplier", "payee", "merchant", "counterparty".
- **Category columns**: String columns named "category", "class", "type", "group", "GL description", "expense type", "cost category".
- **Date columns**: Datetime or string columns with "date", "period", "month", "year", "fiscal".
- **BU columns**: String columns with "business unit", "BU", "department", "division", "segment", "entity", "region", "geography".
- **Cost center**: String columns with "cost center", "CC", "profit center".

Present the inferred mapping to the user for confirmation before proceeding. If any critical column (amount, at minimum) cannot be identified, ask the user to clarify.

### Step 2: Data Cleaning

Before classification, clean the data:

- Remove rows where the spend amount is null, zero, or negative (flag negative amounts separately as credits/reversals)
- Standardize supplier names (trim whitespace, normalize case, merge obvious duplicates like "ACME Corp" / "Acme Corporation" / "ACME CORP.")
- Parse dates into a consistent format (YYYY-MM or YYYY-QQ)
- Flag and report any data quality issues: duplicate rows, missing values, outlier amounts (>3 standard deviations from category mean)

Report a data quality summary to the user before moving on.

### Step 3: Spend Category Classification

Classify each line item into the standard taxonomy. Use a two-pass approach:

**Pass 1 — Rule-based matching**: Match against the category keywords in `references/spend_taxonomy.json`. Check the supplier name, GL description, and any existing category column against the keyword lists. This should resolve 60-80% of line items.

**Pass 2 — LLM classification**: For unmatched items, use your judgment to classify based on the supplier name, description, and any contextual clues. When uncertain, assign to the closest category and flag with `confidence: "low"`.

The standard taxonomy has 15 top-level categories and ~60 subcategories. See `references/spend_taxonomy.json` for the full hierarchy.

**Standard OpEx Taxonomy (Top Level)**:

| # | Category | Typical Keywords |
|---|----------|-----------------|
| 1 | IT & Technology | software, SaaS, cloud, hardware, licenses, IT support, cybersecurity |
| 2 | Professional Services | consulting, legal, audit, advisory, accounting, tax |
| 3 | Facilities & Real Estate | rent, lease, utilities, maintenance, janitorial, security, office space |
| 4 | Travel & Entertainment | flights, hotels, meals, events, conferences, per diem |
| 5 | Marketing & Advertising | digital marketing, print, media, brand, PR, events, sponsorship |
| 6 | HR & Recruitment | staffing agencies, training, L&D, benefits admin, relocation |
| 7 | Logistics & Supply Chain | freight, shipping, warehousing, distribution, fleet, courier |
| 8 | Telecommunications | voice, data, mobile, internet, conferencing, unified comms |
| 9 | Insurance & Risk | property insurance, liability, D&O, cyber insurance, workers comp |
| 10 | Office Supplies & Equipment | furniture, supplies, printing, copiers, stationery |
| 11 | Outsourced Operations | BPO, contact center, managed services, staff augmentation |
| 12 | R&D & Engineering | lab supplies, prototyping, testing, patents, R&D tools |
| 13 | Financial Services | banking fees, payment processing, treasury, FX costs |
| 14 | Contingent Workforce | contractors, freelancers, temp labor, SOW-based services |
| 15 | Other / Unclassified | items that don't fit cleanly into the above categories |

Allow the user to override any classification. When they do, learn from the correction — if they reclassify "Salesforce" from IT to Marketing, apply that mapping to all Salesforce line items.

### Step 4: Generate Spend Profile

Produce a structured spend profile with these components:

**Summary Table** (always show this first):
- One row per top-level category
- Columns: Category, Total Spend, % of Total, # of Transactions, # of Suppliers, Avg Transaction Size
- Sorted by Total Spend descending

**Time Series** (if date data is available):
- Monthly or quarterly spend by category
- Highlight categories with >15% period-over-period growth or decline

**Top Suppliers** (per category):
- Top 5 suppliers by spend within each category
- Include supplier concentration metric: % of category spend from top 3 suppliers

**Data Quality Report**:
- Total rows processed, rows classified, rows flagged
- Classification confidence distribution (high/medium/low)
- Data issues found and actions taken

### Step 5: Store in Memory

After generating the profile, store these facts in memory for downstream skills:

```
Company/Org: [from user context or ask]
Industry: [from user context or ask]
Reporting Currency: [inferred from data or ask]
Total OpEx Analyzed: $X
Number of Categories: N
Top 3 Categories by Spend: [list]
Analysis Period: [date range]
Data Quality Score: [high/medium/low]
```

Also store the full categorized dataset reference so other skills can access it.

## Output Format

Always present results in this order:
1. Column mapping confirmation (ask user to approve before proceeding)
2. Data quality summary (brief — 3-5 bullet points)
3. Spend profile summary table
4. Time series highlights (if applicable)
5. Top supplier analysis (if applicable)
6. Offer next steps: "Your spend is profiled. I can now run peer benchmarking, internal benchmarking, heuristic analysis, or all three. What would you like to explore?"

## Edge Cases

- **Multi-currency data**: If multiple currencies detected, warn the user and ask for a reporting currency. Apply approximate conversion using the rates in the data or ask for rate table. Flag this as a data quality issue.
- **Partial data**: If only a subset of categories has data (e.g., only IT spend), proceed but note that the profile is partial and downstream benchmarks will be limited.
- **Pre-categorized data**: If the data already has a category column, use it as a starting point but validate against the standard taxonomy. Map the user's categories to the standard ones and show the mapping for approval.
- **Very large files**: For files with >100K rows, process in chunks and report progress. Prioritize the summary statistics over line-item detail.
