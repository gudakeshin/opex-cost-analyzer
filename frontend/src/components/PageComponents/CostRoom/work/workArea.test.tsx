import { describe, expect, it } from 'vitest';
import { priorityScore } from '../../../../utils/initiativeHelpers';
import type { Initiative } from '../../../../types';

const base: Initiative = {
  initiative_id: 'a',
  category: 'IT',
  lever: 'Cloud',
  stage: 'identified',
  gross_savings_y1: 100,
  p50_savings: 100,
  aqs: 0.55,
};

describe('worklist ranking', () => {
  it('sorts by priorityScore descending', () => {
    const low: Initiative = { ...base, initiative_id: 'low', aqs: 0.8, p50_savings: 50 };
    const high: Initiative = { ...base, initiative_id: 'high', aqs: 0.55, p50_savings: 200 };
    const ranked = [low, high].sort((a, b) => priorityScore(b) - priorityScore(a));
    expect(ranked[0].initiative_id).toBe('high');
  });
});
