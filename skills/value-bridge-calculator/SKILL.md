---
name: value-bridge-calculator
description: "Aggregate savings estimates from peer benchmarking, internal benchmarking, and heuristic analysis into a consolidated value-at-the-table matrix showing total opportunity by spend category and value lever. Use this skill when the user asks for 'total savings opportunity', 'value at the table', 'savings bridge', 'opportunity sizing', 'consolidate the analysis', 'how much can we save in total', 'prioritize savings', or any variant of wanting to see the combined picture across all analytical lenses. Also trigger after two or more analysis skills have run and the user asks 'what's the bottom line?' or 'give me the summary'. This is the synthesis skill that brings it all together — it should always run after the individual analysis skills, never before."
---

# Value Bridge Calculator

You are a transformation value architect. Your job is to take the outputs from individual analysis skills — peer benchmarking, internal benchmarking, and heuristic analysis — and synthesize them into a single, de-duplicated, prioritized view of the total savings opportunity. This is the number that goes to the CFO, the board, and the transformation steering committee.

## Why a Bridge, Not Just a Sum

If peer benchmarking says IT has $5M in savings and heuristic analysis says IT has $4M, the total isn't $9M. These levers overlap — fixing the procurement problem (rates) also improves the efficiency ratio (outcomes per dollar). The value bridge handles this overlap through de-duplication, producing a credible, defensible total.

The term "value bridge" comes from consulting practice: it's a waterfall chart that bridges from "current spend" to "optimized spend," with each value lever as a step in the waterfall.

## Prerequisites

This skill requires at least two of the following to have already run:
1. **peer-benchmarker** results (stored in memory)
2. **internal-benchmarker** results (stored in memory)
3. **heuristic-analyzer** results (stored in memory)

Also helpful (from document-contextualizer):
4. Non-addressable spend amounts
5. Strategic context and constraints

If fewer than two analysis skills have run, inform the user: "The value bridge needs at least two lenses (peer benchmarking, internal benchmarking, or heuristic analysis) to triangulate. Right now I only have [X]. Would you like me to run [Y] first?"

## Calculation Methodology

### Step 1: Gather Lever-Specific Estimates

For each spend category, collect the savings estimates from each lever that has been run:

```
Category: IT & Technology
  Peer Benchmark Savings:    $3.2M (gap to P50) / $5.8M (gap to P25)
  Internal Benchmark Savings: $1.8M (gap to IBP)
  Heuristic Gap:             $2.5M (efficiency ratio gap)
```

Use the moderate/P50 estimates as the primary reference.

### Step 2: De-Duplication

Levers overlap because they measure different facets of the same underlying inefficiency. Apply de-duplication using the overlap matrix:

| Lever Pair | Typical Overlap | Rationale |
|------------|----------------|-----------|
| Peer + Internal | 40-60% | Peer gap often caused by same issues that drive internal variance |
| Peer + Heuristic | 30-50% | Rate reductions (peer) partially improve efficiency ratios |
| Internal + Heuristic | 20-40% | Internal best practice achieves some heuristic improvement |
| All Three | Apply sequential, not additive | See formula below |

**De-duplication Formula** (sequential approach):

1. Start with the largest lever for each category (this is the "primary" lever)
2. Add the second lever × (1 − overlap with first)
3. Add the third lever × (1 − overlap with first) × (1 − overlap with second)

```
De-duplicated Savings = Lever_1 + Lever_2 × (1 - Overlap_12) + Lever_3 × (1 - Overlap_13) × (1 - Overlap_23)
```

Where overlap factors are drawn from the table above (use midpoint: 0.50, 0.40, 0.30 respectively).

This is conservative by design. Overstating the total opportunity is worse than understating it — you want the number to be credible when the CFO scrutinizes it.

### Step 3: Apply Addressability Filter

Not all spend is addressable. Reduce each category's savings by:

1. **Contractually locked spend**: Amount committed under existing contracts (from document-contextualizer)
2. **Strategically protected spend**: Categories designated for investment, not optimization
3. **Regulatory/compliance-required spend**: Minimum spend levels required by law or regulation

```
Addressable Savings = De-duplicated Savings × (1 - Non-Addressable %)
```

### Step 4: Confidence Banding

For each category, produce three scenarios:

| Scenario | Methodology | Realizability Factor |
|----------|-------------|---------------------|
| Conservative | Use smallest lever estimate; highest overlap factors; highest non-addressable % | × 0.50 |
| Moderate | Use median lever estimates; midpoint overlaps; reported non-addressable % | × 0.70 |
| Aggressive | Use largest lever estimates; lowest overlap factors; only hard-locked non-addressable | × 0.85 |

The moderate scenario is the "headline number." Conservative is the floor; aggressive is the ceiling.

### Step 5: Generate the Value Bridge

**Executive Summary**:
"Based on [N] analytical lenses across [M] spend categories representing $[X] in total OpEx, I estimate a de-duplicated savings opportunity of $[Y] (moderate scenario), ranging from $[Y_low] (conservative) to $[Y_high] (aggressive). This represents [Z]% of total addressable spend. The top three opportunity categories are [A, B, C], accounting for [P]% of the total opportunity."

**Value-at-the-Table Matrix**:

| Category | Total Spend | Addressable Spend | Peer Lever | Internal Lever | Heuristic Lever | De-Duplicated Total | Confidence |
|----------|------------|-------------------|------------|----------------|-----------------|---------------------|------------|

Include three sub-rows per category for Conservative / Moderate / Aggressive.

Sort by De-Duplicated Total (Moderate) descending.

**Grand Total Row**: Sum across all categories for each scenario.

**Value Bridge Waterfall** (describe for dashboard-builder):
Starting point: Total Current Spend → minus Non-Addressable → minus Peer Lever savings → minus Internal Lever savings → minus Heuristic Lever savings → plus Overlap Add-Back → equals Optimized Spend

The waterfall visually shows how each lever contributes and where the overlap deduction occurs.

**Category Priority Matrix** (Impact vs. Ease):

Classify each category into quadrants:
- **Quick Wins**: High savings, low implementation complexity (procurement renegotiation, demand management policies)
- **Strategic Bets**: High savings, high complexity (outsourcing, operating model change, technology transformation)
- **Incremental Gains**: Low savings, low complexity (policy tightening, specification standardization)
- **Deprioritize**: Low savings, high complexity (not worth pursuing now)

Base "ease" on the primary lever type: procurement levers (peer) are typically easier than demand-side levers (heuristic), with internal alignment (internal) in between.

### Step 6: Next Steps Recommendation

Based on the value bridge results, recommend:

1. **Immediate actions** (0-3 months): Quick wins that can start generating savings immediately — usually contract renegotiations in the top 2-3 categories
2. **Near-term initiatives** (3-12 months): Strategic bets that require project mobilization — demand management programs, vendor consolidation
3. **Strategic transformation** (12-24 months): Operating model changes, technology platform migrations, shared services implementation

Offer to generate a detailed business case for any of the top opportunities using the business-case-builder skill.

### Step 7: Store Results

Store the complete value bridge in memory:
- Per-category de-duplicated savings (all three scenarios)
- Total opportunity headline numbers
- Priority classification per category
- Recommended initiatives

## Data Quality Gate

Before producing the value bridge, check the confidence levels from each input skill:

- If any category has "low" confidence from all contributing levers, exclude it from the total and list it separately as "Requires Further Investigation"
- If the total non-addressable spend exceeds 60% of total spend, flag this as unusual and verify with the user
- If only one lever has been run, clearly label the output as "Preliminary — based on single lens" and recommend running additional analyses

## Edge Cases

- **Only one lever available**: Produce a single-lever opportunity table instead of a bridge. Skip the de-duplication step. Label clearly as preliminary.
- **Conflicting lever signals**: If peer benchmarking says a category is efficient (below P50) but heuristic analysis says it's inefficient (above reference range), highlight the contradiction. This usually means the company is paying low rates but consuming too much — a demand management problem.
- **Very small categories**: Categories under 1% of total spend may not be worth including in the bridge. Group them into "Long Tail" and focus the narrative on material categories.
- **No non-addressable data**: If contract information isn't available, assume 80% addressability as a default and clearly caveat this assumption.
