import { describe, expect, it } from 'vitest';
import { buildDefaultDeepResearchPrompt } from './deepResearchPrompt';

describe('buildDefaultDeepResearchPrompt', () => {
  it('includes company, industry, revenue, and market-news focus areas', () => {
    const prompt = buildDefaultDeepResearchPrompt('Infosys Ltd', 'it_ites', 150000);

    expect(prompt).toContain('Infosys Ltd');
    expect(prompt).toContain('it_ites');
    expect(prompt).toContain('₹1,50,000 Cr');
    expect(prompt).toContain('Company-specific developments');
    expect(prompt).toContain('Peer and competitive landscape');
    expect(prompt).toContain('Macro context');
    expect(prompt).toContain('Industry deep-dive');
    expect(prompt).toContain('Implications for cost optimization');
  });
});
