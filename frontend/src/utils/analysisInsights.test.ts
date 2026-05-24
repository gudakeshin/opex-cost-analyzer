import { describe, expect, it } from 'vitest';
import {
  buildDataRootedPrompts,
  extractInsightSnapshot,
  wantsPeerSavingsInsight,
} from './analysisInsights';
import type { SessionResponse } from '../types';

describe('analysisInsights', () => {
  it('extracts spend snapshot from skill_outputs', () => {
    const session: SessionResponse = {
      session_id: 'x',
      reporting_currency: 'USD',
      skill_outputs: {
        'spend-profiler': {
          total_spend: 1_000_000,
          category_profile: [
            {
              category_id: 'IT',
              category_name: 'IT & Technology',
              spend: 600_000,
              share_of_total: 0.6,
            },
            {
              category_id: 'OTHER',
              category_name: 'Other',
              spend: 400_000,
              share_of_total: 0.4,
            },
          ],
        },
      },
    };
    const snap = extractInsightSnapshot(session, null);
    expect(snap?.total_spend).toBe(1_000_000);
    expect(snap?.top_categories).toHaveLength(2);
    expect(snap?.top_categories[0].category_name).toBe('IT & Technology');
  });

  it('builds data-rooted prompts without peer/savings by default', () => {
    const snap = extractInsightSnapshot(
      {
        session_id: 'x',
        skill_outputs: {
          'spend-profiler': {
            total_spend: 100,
            category_profile: [
              {
                category_id: 'A',
                category_name: 'Cloud',
                spend: 100,
                share_of_total: 1,
              },
            ],
          },
        },
      },
      null,
    );
    const prompts = buildDataRootedPrompts(snap, null);
    const joined = prompts.map((p) => p.message).join(' ');
    expect(joined).not.toMatch(/peer benchmark/i);
    expect(joined).not.toMatch(/savings opportunities/i);
    expect(prompts[0].label).toContain('Cloud');
  });

  it('detects peer/savings intent', () => {
    expect(wantsPeerSavingsInsight('Where are we above peer benchmarks?')).toBe(true);
    expect(wantsPeerSavingsInsight('Break down IT spend by supplier')).toBe(false);
  });
});
