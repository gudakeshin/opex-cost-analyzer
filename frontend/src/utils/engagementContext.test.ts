import { describe, expect, it } from 'vitest';
import {
  effectiveAnalysisIndustry,
  effectiveEngagementIndustry,
  isPlaceholderIndustry,
} from './engagementContext';

describe('engagementContext', () => {
  it('prefers manifest industry over detected', () => {
    expect(
      effectiveAnalysisIndustry({ industry: 'it_ites' }, { industry: 'manufacturing_diversified', detected_industry: 'fmcg_consumer' }),
    ).toBe('it_ites');
  });

  it('uses detected industry when manifest is empty and engagement is placeholder', () => {
    expect(
      effectiveAnalysisIndustry({ industry: '' }, { industry: 'manufacturing_diversified', detected_industry: 'it_ites' }),
    ).toBe('it_ites');
  });

  it('effectiveEngagementIndustry prefers detected over placeholder default', () => {
    expect(
      effectiveEngagementIndustry({ industry: 'manufacturing_diversified', detected_industry: 'it_ites' }),
    ).toBe('it_ites');
  });

  it('does not override explicit user industry with detected', () => {
    expect(
      effectiveEngagementIndustry({ industry: 'pharma_lifesciences', detected_industry: 'it_ites' }),
    ).toBe('pharma_lifesciences');
  });

  it('identifies placeholder industry', () => {
    expect(isPlaceholderIndustry('')).toBe(true);
    expect(isPlaceholderIndustry('manufacturing_diversified')).toBe(true);
    expect(isPlaceholderIndustry('it_ites')).toBe(false);
  });
});
