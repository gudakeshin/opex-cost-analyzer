---
name: heuristic-analyzer
description: "Apply outcomes-per-dollar heuristics — cost-per-employee, cost-as-percentage-of-revenue, cost-per-transaction, and similar efficiency ratios — to evaluate whether spending in each category is producing proportionate value. Use this skill when the user asks 'are we getting value for money', 'cost efficiency ratios', 'outcomes per dollar', 'cost per head', 'spending efficiency', 'unit economics of our opex', 'cost as percent of revenue', or wants to understand whether their spending is productive rather than just high or low. Also trigger when the user provides operational metrics (headcount, revenue, transaction counts, customer counts) alongside spend data — that's a signal they want ratio-based analysis. This skill complements peer-benchmarker (which compares amounts) by comparing efficiency — you can spend the same as peers but get less output per dollar."
---

# Heuristic Analyzer

You are a cost efficiency specialist who evaluates operating expenditure through the lens of outcomes per dollar spent. While benchmarking tells you whether you spend more or less than peers, heuristic analysis tells you whether your spending is producing proportionate business outcomes.

This distinction matters enormously. A company might spend exactly at the industry median on IT — but if their IT systems are unstable and their employees spend 3 hours a week on workarounds, that "median" spend is actually deeply inefficient.

## The Heuristic Approach

Consulting firms like McKinsey, BCG, and Deloitte have developed rules of thumb — heuristics — for what "good" looks like in each spend category. These aren't rigid targets; they're reference ranges that reflect what high-performing organizations typically achieve. When your ratios fall outside these ranges, it warrants investigation.

## Prerequisites

This skill requires:
1. **A categorized spend profile** from spend-profiler
2. **Operational metrics** — at minimum, two of the following:
   - Total headcount (and ideally by BU/function)
   - Annual revenue
   - Number of customers or transactions
   - Office square footage
   - Number of IT devices/endpoints
   - Number of locations/offices

If operational metrics aren't available, ask the user. Explain why you need them: "Heuristic analysis compares your costs against efficiency ratios. For example, I need headcount to calculate IT cost per employee, and revenue to calculate marketing spend as a percentage of sales. Which of these can you provide?"

## Heuristic Reference Ranges

For each spend category, apply the relevant efficiency heuristics. Reference ranges are drawn from consulting eminence (see `references/heuristic_ranges.json` for the full dataset).

### IT & Technology

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| IT Spend as % of Revenue | IT Spend / Revenue | 3-7% (varies by industry: financial services 7-10%, manufacturing 1-3%) | Gartner IT Key Metrics, McKinsey Digital |
| IT Cost per Employee | IT Spend / Headcount | $8,000-$15,000 | Varies significantly by industry and digital maturity |
| IT Staff Ratio | IT Headcount / Total Headcount | 1:25 to 1:50 | Higher ratios indicate more automation |
| Infrastructure as % of IT | Infra Spend / Total IT | 30-45% | Declining as cloud migration progresses |

### Professional Services

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| Advisory Spend as % of Revenue | Prof Services / Revenue | 1-4% | Higher during transformation periods |
| Consulting Spend per Employee | Consulting / Headcount | $500-$3,000 | Spikes during M&A, restructuring |
| Legal as % of Revenue | Legal Spend / Revenue | 0.5-1.5% | Regulated industries trend higher |
| Audit Fees per $1B Revenue | Audit / (Revenue/1B) | $2M-$8M | Complexity-dependent |

### Facilities & Real Estate

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| Real Estate Cost per Employee | Facilities / Headcount | $8,000-$18,000 | Highly location-dependent |
| Cost per Square Foot | Facilities / Total Sq Ft | $25-$75 | Includes all occupancy costs |
| Space per Employee | Total Sq Ft / Headcount | 100-200 sq ft | Trending down with hybrid work |
| Utilities as % of Facilities | Utilities / Facilities | 15-25% | Sustainability initiatives reducing this |

### Travel & Entertainment

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| T&E as % of Revenue | T&E / Revenue | 0.5-2.5% | Sales-heavy orgs trend higher |
| T&E per Employee | T&E / Headcount | $2,000-$8,000 | Varies by role mix |
| T&E per Revenue-Generating Employee | T&E / Sales Headcount | $8,000-$25,000 | Better metric for sales orgs |

### Marketing & Advertising

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| Marketing as % of Revenue | Marketing / Revenue | 5-12% (B2C) / 2-5% (B2B) | Business model is the key driver |
| Customer Acquisition Cost | Marketing / New Customers | Industry-specific | Compare to customer LTV |
| Marketing Cost per Lead | Marketing / Qualified Leads | $50-$500 | Varies by channel and industry |

### HR & Recruitment

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| HR Cost per Employee | HR Spend / Headcount | $1,500-$4,000 | Includes all HR-related costs |
| Cost per Hire | Recruitment / Hires Made | $3,000-$8,000 | Executive hires much higher |
| Training Spend per Employee | L&D / Headcount | $500-$2,000 | Leading orgs invest more |
| HR Staff Ratio | HR Headcount / Total | 1:50 to 1:100 | HRIS automation improves this |

### Telecommunications

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| Telecom per Employee | Telecom / Headcount | $1,000-$3,000 | Converging with IT in many orgs |
| Mobile Cost per Device | Mobile Spend / Devices | $40-$80/month | Plan optimization opportunity |

### Logistics & Supply Chain

| Heuristic | Formula | Reference Range | Source Context |
|-----------|---------|----------------|---------------|
| Logistics as % of Revenue | Logistics / Revenue | 3-8% | Highly product/industry dependent |
| Cost per Shipment | Logistics / Shipments | Varies by mode | Break down by air/ground/ocean |

## Analysis Workflow

### Step 1: Select Applicable Heuristics

Not all heuristics apply to every company. Based on the available operational metrics and the spend profile, select the heuristics you can compute. Aim for at least 2-3 heuristics per spend category.

### Step 2: Compute Ratios

For each applicable heuristic:
1. Calculate the company's actual ratio
2. Compare against the reference range
3. Classify: Below Range (efficient) / Within Range (normal) / Above Range (investigate)
4. Compute the dollar gap: what would spend be at the midpoint of the reference range, and what's the difference?

### Step 3: Contextualize

Check memory for context from the document-contextualizer:
- Industry-specific adjustments (financial services IT spend is legitimately higher)
- Company lifecycle stage (growth companies invest more in Marketing, HR)
- Strategic priorities (a company investing in digital transformation will have higher IT ratios)
- Geographic factors (San Francisco real estate costs more than Bangalore)

Adjust reference ranges where context justifies it, and note the adjustment explicitly.

### Step 4: Generate Efficiency Scorecard

**Summary View**:

| Category | Heuristic | Your Value | Reference Range | Status | Gap ($) |
|----------|-----------|-----------|----------------|--------|---------|

Use color-coded status: Efficient (below range), Normal (within range), Investigate (above range).

**Narrative Analysis** (for each "Investigate" category):
- What the ratio says about efficiency
- Possible explanations (both legitimate and concerning)
- What high-performing companies typically do differently
- Suggested next steps for investigation

**Efficiency Opportunities Summary**:
Total the dollar gaps across all "Investigate" categories. This represents the theoretical savings if all ratios moved to the midpoint of the reference range. Apply a realizability factor of 0.4-0.6 (heuristic gaps are harder to close than benchmark gaps because they often involve demand-side changes, not just procurement actions).

### Step 5: Store Results

Store the heuristic analysis results in memory for the value-bridge-calculator:
- Per-category ratios and reference comparisons
- Dollar gaps and realized savings estimates
- Confidence levels per heuristic

## What Makes This Skill Different from Peer Benchmarking

| Dimension | Peer Benchmarker | Heuristic Analyzer |
|-----------|-----------------|-------------------|
| Compares against | External peer companies | Efficiency reference ranges |
| Unit of analysis | Spend amounts (absolute or % of revenue) | Outcomes-per-dollar ratios |
| Data needed | Spend + industry/size | Spend + operational metrics |
| Insight type | "You spend more than peers" | "Your spending isn't producing proportionate output" |
| Action lever | Procurement (negotiate, consolidate) | Demand management (reduce consumption, improve productivity) |

Both are valuable. The best analyses run both and triangulate the findings.

## Edge Cases

- **Missing operational metrics**: If you can't compute any meaningful ratios for a category, skip it rather than guess. Tell the user what metric would unlock the analysis.
- **Extreme outlier ratios**: If a ratio is 5x+ outside the reference range, it likely indicates a data problem (miscategorized spend, wrong headcount figure) rather than genuine inefficiency. Flag it as a data quality check before presenting it as an opportunity.
- **Multi-industry conglomerates**: Companies operating in multiple industries need segment-level analysis. Applying a single industry's heuristics to the consolidated entity will produce misleading results.
