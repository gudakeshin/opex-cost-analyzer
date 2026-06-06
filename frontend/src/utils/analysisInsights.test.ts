import { describe, expect, it } from 'vitest';
import {
  answeredProbeKeysFromMessages,
  buildDataRootedPrompts,
  collectUnansweredProbeQuestions,
  extractInsightSnapshot,
  probeAnswerKey,
  wantsPeerSavingsInsight,
} from './analysisInsights';
import type { AnalysisInsightSnapshot } from '../types';
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

  it('excludes answered probe questions from the unanswered list', () => {
    const snapshot: AnalysisInsightSnapshot = {
      total_spend: 1_000_000,
      reporting_currency: 'INR',
      top_categories: [],
      sme_qualification: { ready_count: 0, probe_count: 2, insufficient_count: 0, savings_ready: 0, savings_probe: 1, savings_insufficient: 0 },
      sme_initiative_critiques: [
        {
          initiative_id: '1',
          category_id: 'HR',
          category_name: 'HR',
          lever: 'demand_management',
          lever_name: 'Demand management',
          modelled_saving_3yr: 100,
          evidence_maturity: 'hypothesis',
          sme_verdict: 'probe_first',
          critical_risk: 'discretionary mix unknown',
          probe_questions: [
            {
              question: 'Is HR spend discretionary?',
              why_critical: 'Addressability depends on mix',
              saving_at_stake: 100,
              data_to_request: 'cost center split',
            },
          ],
        },
        {
          initiative_id: '2',
          category_id: 'TRAVEL',
          category_name: 'TRAVEL',
          lever: 'policy',
          lever_name: 'Policy',
          modelled_saving_3yr: 50,
          evidence_maturity: 'hypothesis',
          sme_verdict: 'probe_first',
          critical_risk: 'policy unknown',
          probe_questions: [
            {
              question: 'What share of travel is policy-compliant?',
              why_critical: 'Policy lever needs baseline',
              saving_at_stake: 50,
              data_to_request: 'travel policy audit',
            },
          ],
        },
      ],
    };
    const answered = new Set([probeAnswerKey('Is HR spend discretionary?')]);
    const remaining = collectUnansweredProbeQuestions(snapshot, answered, 5);
    expect(remaining).toHaveLength(1);
    expect(remaining[0].category_name).toBe('TRAVEL');
  });

  it('parses answered probes from chat messages', () => {
    const keys = answeredProbeKeysFromMessages([
      {
        role: 'user',
        content:
          '**HR** assumption probe answer: Mostly operational\n\nProbe: Is HR spend discretionary?',
      },
    ]);
    expect(keys.has(probeAnswerKey('Is HR spend discretionary?'))).toBe(true);
  });

  it('filters portfolio probes answered in manifest', () => {
    const session: SessionResponse = {
      session_id: 'x',
      skill_outputs: {
        'sme-critique': {
          portfolio_probes: [
            {
              probe_family_id: 'transaction_volume',
              question: 'Invoice cycle time across AP?',
              why_critical: 'Volume drives ROI',
              saving_at_stake: 300,
              scope: 'portfolio',
              affected_categories: ['HR', 'Travel', 'Other'],
            },
            {
              probe_family_id: 'po_coverage',
              question: 'PO coverage rate?',
              why_critical: 'Maverick buying',
              saving_at_stake: 100,
              scope: 'portfolio',
              affected_categories: ['HR'],
            },
          ],
        },
      },
    };
    const manifest = {
      session_id: 'x',
      probe_answers: [
        {
          probe_family_id: 'transaction_volume',
          answer: '12 days, 800/month',
          applies_to_categories: ['HR', 'Travel', 'Other'],
        },
      ],
    };
    const snap = extractInsightSnapshot(session, manifest);
    expect(snap?.portfolio_probes).toHaveLength(1);
    expect(snap?.portfolio_probes?.[0].probe_family_id).toBe('po_coverage');
  });

  it('dedupes unanswered probes by probe_family_id', () => {
    const snapshot: AnalysisInsightSnapshot = {
      total_spend: 1_000_000,
      reporting_currency: 'INR',
      top_categories: [],
      portfolio_probes: [
        {
          probe_family_id: 'transaction_volume',
          question: 'Invoice cycle time across AP?',
          why_critical: 'Volume',
          saving_at_stake: 300,
          scope: 'portfolio',
          affected_categories: ['HR', 'Travel', 'Other'],
        },
      ],
    };
    const answered = new Set(['transaction_volume']);
    expect(collectUnansweredProbeQuestions(snapshot, answered, 5)).toHaveLength(0);
  });
});
