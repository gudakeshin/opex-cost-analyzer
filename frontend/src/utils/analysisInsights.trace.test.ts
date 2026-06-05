import { describe, expect, it } from 'vitest';
import { buildTraceThinkingSummary } from './analysisInsights';
import type { AnalysisTraceStep } from '../types';

describe('buildTraceThinkingSummary', () => {
  it('summarizes trace steps with source documents', () => {
    const trace: AnalysisTraceStep[] = [
      {
        step: 1,
        phase: 'ingest',
        title: 'Read spend data',
        detail: 'Parsed 10 lines totalling INR 1,000,000.',
        source_documents: ['spend.csv'],
      },
      {
        step: 2,
        phase: 'benchmark',
        title: 'Benchmarked against peers',
        detail: 'Compared 5 categories to **it_ites** peers.',
        source_documents: ['spend.csv'],
      },
    ];
    const summary = buildTraceThinkingSummary(trace);
    expect(summary).toContain('Read spend data');
    expect(summary).toContain('[from: spend.csv]');
    expect(summary).not.toContain('**');
  });
});
