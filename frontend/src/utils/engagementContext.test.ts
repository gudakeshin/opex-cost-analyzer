import { describe, expect, it } from 'vitest';
import {
  effectiveAnalysisIndustry,
  effectiveEngagementIndustry,
  isPlaceholderIndustry,
} from './engagementContext';

describe('engagementContext', () => {
  it('prefers manifest industry over detected', () => {
    expect(
      effectiveAnalysisIndustry({ session_id: '', industry: 'it_ites' }, { industry: 'manufacturing_diversified', detected_industry: 'fmcg_consumer' }),
    ).toBe('it_ites');
  });

  it('prefers engagement industry over detected when manifest is empty', () => {
    expect(
      effectiveAnalysisIndustry(
        { session_id: '', industry: '' },
        { industry: 'bfsi_banks', detected_industry: 'it_ites' },
      ),
    ).toBe('bfsi_banks');
  });

  it('uses detected industry when manifest and engagement are empty/placeholder', () => {
    expect(
      effectiveAnalysisIndustry({ session_id: '', industry: '' }, { industry: 'manufacturing_diversified', detected_industry: 'it_ites' }),
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
