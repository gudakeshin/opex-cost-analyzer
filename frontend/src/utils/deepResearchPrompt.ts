export function buildDefaultDeepResearchPrompt(
  companyName: string,
  industry: string,
  revenueCr: number,
): string {
  const revenue = revenueCr.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  return `Conduct comprehensive research on ${companyName}, a company operating in the ${industry} sector with approximately ₹${revenue} Cr in annual revenue. The goal is to build a deep, decision-grade understanding of the company's business and business model, the industry it operates in, and the implications for its operating cost structure and cost-optimization opportunities.

Your research should cover the following areas in depth:

1. Company business and business model
   - What the company does: core products, services, and business segments, and the relative size/contribution of each
   - Revenue model and monetization: how it makes money (product sales, subscriptions, services, licensing), pricing structure, and revenue mix
   - Customers and go-to-market: key customer segments, sales channels, distribution model, and major clients or end-markets
   - Operating model and value chain: where the company sits in its value chain, what it owns vs. outsources, its manufacturing/service-delivery footprint, and key partnerships or suppliers
   - Cost structure and primary cost drivers: major operating cost categories (COGS vs. SG&A), what drives them, and how the cost base scales with volume
   - Scale and footprint: revenue, profitability/margins, headcount, and geographic/plant/network footprint
   - Strategy and positioning: recent strategic priorities, growth initiatives, competitive positioning, and any durable advantage or moat

2. Industry deep-dive
   - Industry structure and size: market size, growth rate, segmentation, and degree of concentration or fragmentation
   - Value chain and economics: how the value chain is structured and where margins/profit pools sit
   - Demand and supply drivers: what drives demand, input/supply dynamics, and any cyclicality or seasonality
   - Competitive dynamics: intensity of rivalry, threat of substitutes, buyer and supplier bargaining power, and barriers to entry
   - Regulatory and policy environment: regulation, taxation, compliance, and policy trends shaping the sector
   - Technology and disruption: technology adoption, digitization, and disruption trends reshaping the industry
   - Cost and margin profile: typical cost structure and margin benchmarks for companies in ${industry}
   - India-specific dynamics: domestic market structure, regulation, and competitive context where relevant

3. Peer and competitive landscape
   - Identify 4–6 closest listed and private peers in India and, where relevant, globally
   - Summarize recent peer news: margin trends, cost-reduction programs, outsourcing and offshoring decisions, digital/technology transformation spend, procurement centralization, and SG&A efficiency initiatives
   - Benchmarking signals relevant to indirect spend categories: SG&A, procurement, IT, facilities, travel, and professional services
   - Any peer actions that create competitive pressure on ${companyName}'s cost base

4. Company-specific developments
   - Recent news from the last 12–24 months: earnings releases, management commentary, guidance changes, strategic initiatives, restructuring, M&A, divestitures, plant/network changes, and major contract wins or losses
   - Regulatory actions, litigation, or compliance issues that could affect operating costs
   - Workforce actions (hiring freezes, layoffs, union developments) and their OpEx implications
   - How these developments may affect operating expenditure, procurement posture, shared services, and overall cost structure

5. Macro context
   - Industry-wide trends affecting OpEx: input costs, regulation, talent and labor markets, technology adoption, supply-chain dynamics, consolidation, and pricing power
   - Relevant analyst reports, rating-agency views, and trade or industry-body publications from the last 18 months
   - Macro factors (interest rates, FX, inflation, policy) that materially affect cost structure in ${industry}

6. Implications for cost optimization
   - Connect the business model, industry economics, and market signals to plausible OpEx pressure points and savings levers for ${companyName}
   - Note risks, constraints, or tailwinds that would affect a cost-transformation or zero-based budgeting program
   - Highlight categories where external evidence suggests the company may be above or below peer norms

Use credible sources: company filings and exchange disclosures, reputable financial press, industry research, and analyst notes. Prefer India-relevant context where applicable. Write with specificity — include dates, figures, and named peers wherever available.`;
}
