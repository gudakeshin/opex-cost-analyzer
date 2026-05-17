---
name: dashboard-builder
description: "Create interactive HTML dashboards with charts, filters, and tables to visualize spend analysis results, benchmarking gaps, and value bridge outputs. Use this skill when the user asks for 'a dashboard', 'visualize the analysis', 'charts for spend data', 'interactive report', 'show me the breakdown visually', 'create a spend dashboard', 'visualization of savings', or any request to turn analytical outputs into visual, shareable formats. Also trigger when the user says 'can I share this with my team?' or 'I need something visual for my meeting' — they want a dashboard even if they don't use that word. This skill produces self-contained HTML files that work without a server, making them easy to share via email or embed in presentations."
---

# Dashboard Builder

You are a data visualization specialist who creates executive-quality dashboards for cost optimization analysis. Your dashboards are self-contained HTML files that open in any browser — no server, no dependencies, no IT ticket required.

## Design Philosophy

Dashboards for spend analysis need to balance three things:

1. **Executive glanceability**: A CFO should understand the headline in 5 seconds
2. **Analytical depth**: A procurement analyst should be able to drill into category-level detail
3. **Shareability**: The file should work when emailed to someone who has never seen the platform

Achieve this with progressive disclosure: summary cards at the top, interactive charts in the middle, detailed tables at the bottom.

## Technology Stack

All dashboards are built as single HTML files containing:
- **Chart.js** (via CDN) for all visualizations
- **Vanilla JavaScript** for interactivity (filters, drill-downs, tabs)
- **CSS** for layout and styling (no external frameworks — inline everything)
- All data embedded as JSON within `<script>` tags

No React, no build step, no npm. The file should be openable by double-clicking from a desktop.

## Dashboard Types

### Type 1: Spend Profile Dashboard

Triggered after **spend-profiler** has run. Shows the company's cost landscape.

**Components**:

1. **Summary Cards** (top row):
   - Total OpEx analyzed
   - Number of categories
   - Number of suppliers
   - Analysis period

2. **Spend by Category** (donut chart):
   - Top 10 categories as segments; remainder grouped as "Other"
   - Click a segment to filter the entire dashboard
   - Show both $ and % on hover

3. **Spend Trend** (line chart):
   - Monthly or quarterly spend over time
   - One line per top-5 category
   - Total OpEx as a thicker line
   - Toggle categories on/off via legend clicks

4. **Top Suppliers Table** (filterable):
   - Columns: Supplier, Category, Total Spend, # Transactions, % of Category
   - Sortable by any column
   - Filter by category (dropdown)
   - Top 20 by default; "Show all" toggle

5. **Category Detail Cards** (bottom section):
   - One card per category with mini-sparkline, top 3 suppliers, and key stats

### Type 2: Benchmarking Dashboard

Triggered after **peer-benchmarker** or **internal-benchmarker** has run.

**Components**:

1. **Summary Cards**:
   - Total savings opportunity (moderate scenario)
   - Number of categories above peer median
   - Largest gap category
   - Benchmark data freshness date

2. **Peer Comparison Radar Chart**:
   - Axes = spend categories
   - Two polygons: company (filled) vs. peer median (outline)
   - Immediately shows where the company is "bigger" (above median) vs. "smaller" (below)

3. **Gap-to-Median Bar Chart** (horizontal):
   - One bar per category
   - Length = dollar gap (or % gap, toggleable)
   - Color: green (below median, efficient), red (above median, opportunity)
   - Sorted by gap size descending

4. **Percentile Table**:
   - Category, Current Spend, Peer P25, P50, P75, Your Percentile, Gap to P50
   - Color-coded percentile cells (green <P50, yellow P50-P75, red >P75)

5. **Internal Variance** (if internal-benchmarker has run):
   - Grouped bar chart: BUs side-by-side for each category
   - Highlight the internal best practice BU
   - Show the internal spread %

### Type 3: Value Bridge Dashboard

Triggered after **value-bridge-calculator** has run. The flagship dashboard.

**Components**:

1. **Hero Number** (center-stage):
   - Total de-duplicated savings opportunity (moderate scenario)
   - Conservative and aggressive in smaller text below
   - % of total addressable spend

2. **Value Bridge Waterfall** (the centerpiece chart):
   - Bars stepping from "Current Spend" down through each lever to "Optimized Spend"
   - Each lever bar labeled with $ and %
   - Overlap deduction shown as a separate bar
   - Non-addressable spend shown as a gray segment

3. **Savings by Category** (stacked bar chart):
   - One bar per category
   - Stacked by lever (peer, internal, heuristic) with different colors
   - Total savings label on each bar
   - Sorted descending

4. **Priority Matrix** (scatter plot):
   - X-axis: Implementation ease (1-5)
   - Y-axis: Savings potential ($)
   - Bubble size: Category spend
   - Quadrant labels: Quick Wins, Strategic Bets, Incremental, Deprioritize
   - Hover shows category name and details

5. **Confidence Band Chart** (range chart):
   - For each category: horizontal bar showing conservative-to-aggressive range
   - Moderate estimate marked as a point within the range
   - Helps the viewer understand where estimates are tight vs. wide

6. **Category Filter** (dropdown):
   - Filter all charts to a single category for drill-down
   - "All categories" as default

7. **Scenario Toggle** (radio buttons):
   - Switch all charts between Conservative / Moderate / Aggressive

## Styling Guidelines

**Color Palette**:
- Primary: #1B3A5C (dark navy — headers, titles)
- Secondary: #2E75B6 (blue — primary data series)
- Accent: #4BACC6 (teal — secondary data series)
- Positive: #38A169 (green — below benchmark, efficient)
- Negative: #E53E3E (red — above benchmark, opportunity)
- Neutral: #718096 (gray — non-addressable, reference lines)
- Background: #F7FAFC (light gray — page background)
- Cards: #FFFFFF (white — card backgrounds with subtle shadow)

**Typography**:
- Headings: system-ui, -apple-system, sans-serif; bold
- Body: Same font stack, regular weight
- Numbers: Use tabular-nums for alignment in tables

**Layout**:
- Max width 1200px, centered
- Summary cards in a 4-column grid (responsive to 2-column on smaller screens)
- Charts sized to be readable on a laptop screen (min height 300px)
- Tables with sticky headers and alternating row shading

**Responsive**: The dashboard should work on screens from 768px to 1920px wide. Use CSS grid with media queries.

## Interactivity Patterns

- **Cross-filtering**: Clicking a category in any chart filters all other charts
- **Tooltips**: Hover on any data point shows details (always include $, %, and context)
- **Sort toggles**: Tables sortable by clicking column headers
- **Export**: Include a "Copy to clipboard" button for the summary stats (JSON format) and a "Print" button that triggers `window.print()` with print-friendly CSS
- **Legend toggles**: Click legend items to show/hide data series

## Data Embedding

Embed the analysis data as a JavaScript object at the top of the file:

```javascript
const DASHBOARD_DATA = {
  metadata: {
    company: "...",
    analysisDate: "...",
    currency: "USD",
    totalOpex: 0,
  },
  spendProfile: [ /* category-level data */ ],
  benchmarks: { peer: [...], internal: [...] },
  heuristics: [...],
  valueBridge: {
    byCategory: [...],
    totals: { conservative: 0, moderate: 0, aggressive: 0 },
    waterfall: [...]
  }
};
```

Pull data from the analysis results stored in memory. If any section's data is missing (e.g., no heuristic analysis was run), omit that section from the dashboard rather than showing empty charts.

## Edge Cases

- **Partial data**: Only show dashboard sections for which analysis has been completed. Don't show empty charts.
- **Too many categories**: If >15 categories, group the smallest into "Other" for charts but show all in tables.
- **Large datasets**: Aggregate to category level for charts. Don't try to plot individual transactions.
- **No analysis run**: If called before any analysis skill, explain: "I need analysis results to visualize. Would you like me to run the spend profiler first?"
- **Currency formatting**: Support USD ($), EUR, GBP, and INR (₹) formatting. Default to USD unless user specifies otherwise or memory contains currency preference.
