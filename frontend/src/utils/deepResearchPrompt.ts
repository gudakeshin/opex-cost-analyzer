export function buildDefaultDeepResearchPrompt(
  companyName: string,
  industry: string,
  revenueCr: number,
): string {
  const revenue = revenueCr.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  return `Conduct comprehensive market and news research on ${companyName}, a company operating in the ${industry} sector with approximately ₹${revenue} Cr in annual revenue.

Your research should cover the following areas in depth:

1. Company-specific developments
   - Recent news from the last 12–24 months: earnings releases, management commentary, guidance changes, strategic initiatives, restructuring, M&A, divestitures, plant/network changes, and major contract wins or losses
   - Regulatory actions, litigation, or compliance issues that could affect operating costs
   - Workforce actions (hiring freezes, layoffs, union developments) and their OpEx implications
   - How these developments may affect operating expenditure, procurement posture, shared services, and overall cost structure

2. Peer and competitive landscape
   - Identify 4–6 closest listed and private peers in India and, where relevant, globally
   - Summarize recent peer news: margin trends, cost-reduction programs, outsourcing and offshoring decisions, digital/technology transformation spend, procurement centralization, and SG&A efficiency initiatives
   - Benchmarking signals relevant to indirect spend categories: SG&A, procurement, IT, facilities, travel, and professional services
   - Any peer actions that create competitive pressure on ${companyName}'s cost base

3. Sector and macro context
   - Industry-wide trends affecting OpEx: input costs, regulation, talent and labor markets, technology adoption, supply-chain dynamics, consolidation, and pricing power
   - Relevant analyst reports, rating-agency views, and trade or industry-body publications from the last 18 months
   - Macro factors (interest rates, FX, inflation, policy) that materially affect cost structure in ${industry}

4. Implications for cost optimization
   - Connect news and market signals to plausible OpEx pressure points and savings levers for ${companyName}
   - Note risks, constraints, or tailwinds that would affect a cost-transformation or zero-based budgeting program
   - Highlight categories where external evidence suggests the company may be above or below peer norms

Use credible sources: company filings and exchange disclosures, reputable financial press, industry research, and analyst notes. Prefer India-relevant context where applicable. Write with specificity — include dates, figures, and named peers wherever available.`;
}
