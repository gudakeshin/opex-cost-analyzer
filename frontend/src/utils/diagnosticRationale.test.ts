import { describe, expect, it } from 'vitest';
import {
  benchmarkGapCommentary,
  benchmarkGapSummary,
  valueAtTableCalculationNote,
  valueAtTableCaptureRate,
  valueAtTableMethodologyCopy,
  valueAtTableRationale,
  valueAtTableRowSummary,
  valueAtTableSpendPoolLabel,
} from './diagnosticRationale';

describe('diagnosticRationale', () => {
  it('builds concise benchmark gap summary', () => {
    const text = benchmarkGapSummary({
      category: 'RND',
      category_name: 'R&D & Engineering',
      p50_pct: 10,
      benchmark_p50_to_p25_band_cr: 100,
    });
    expect(text).toContain('Proxy: R&D & Engineering at 10%');
    expect(text).toContain('₹100 Cr');
    expect(text!.length).toBeLessThan(120);
  });

  it('builds value-at-table one-line summary from derivation', () => {
    expect(
      valueAtTableRowSummary({
        lever_name: 'Cloud rightsizing',
        p50_cr: 25,
        value_derivation: {
          calculation_p50: 'Expected (P50) = 22% × ₹120 Cr = ₹25 Cr',
          savings_rate_p50_pct: 22,
        },
        base_spend_cr: 120,
      }),
    ).toBe('Expected (P50) = 22% × ₹120 Cr = ₹25 Cr');
  });

  it('uses API commentary when present', () => {
    expect(
      benchmarkGapCommentary({
        category: 'RND',
        commentary: 'Custom gap commentary from API.',
      }),
    ).toBe('Custom gap commentary from API.');
  });

  it('builds fallback benchmark commentary from numeric fields', () => {
    const text = benchmarkGapCommentary({
      category: 'RND',
      category_name: 'Rnd',
      p50_pct: 10,
      p25_pct: 5,
      benchmark_p50_to_p25_band_cr: 100,
    });
    expect(text).toContain('R&D & Engineering');
    expect(text).toContain('Benchmark proxy');
    expect(text).toContain('10% of revenue');
    expect(text).toContain('₹100 Cr');
  });

  it('uses API lever rationale when present', () => {
    expect(
      valueAtTableRationale({
        rationale: 'Selected because IT spend is material in the benchmark profile.',
      }),
    ).toBe('Selected because IT spend is material in the benchmark profile.');
  });

  it('uses API calculation note when present', () => {
    expect(
      valueAtTableCalculationNote({
        calculation_note:
          'Expected (P50) = 57.9% × ₹120 Cr = ₹69 Cr. Pool: ₹120 Cr — IT pool.',
      }),
    ).toContain('Expected (P50) = 57.9%');
  });

  it('builds calculation note from value_derivation', () => {
    const text = valueAtTableCalculationNote({
      value_derivation: {
        calculation_p50: 'Expected (P50) = 22% × ₹124 Cr = ₹27 Cr',
        base_spend_cr: 124,
        base_spend_note: 'IT addressable pool from benchmark proxy',
        savings_rate_p10_pct: 12,
        savings_rate_p50_pct: 22,
        savings_rate_p90_pct: 32,
      },
    });
    expect(text).toContain('Expected (P50) = 22% × ₹124 Cr');
    expect(text).toContain('IT addressable pool');
    expect(text).toContain('P50 22%');
  });

  it('exposes spend pool and capture rate helpers', () => {
    const row = {
      base_spend_cr: 120,
      base_spend_label: 'IT & Technology',
      value_derivation: { savings_rate_p50_pct: 57.9 },
    };
    expect(valueAtTableSpendPoolLabel(row)).toBe('₹120 Cr · IT & Technology');
    expect(valueAtTableCaptureRate(row, 'p50')).toBe('57.9%');
  });

  it('returns methodology copy with scope note', () => {
    const copy = valueAtTableMethodologyCopy({
      summary: 'Custom summary',
      steps: ['Step one'],
      eligible_levers_total: 20,
      shown_levers: 12,
    });
    expect(copy.summary).toBe('Custom summary');
    expect(copy.steps).toEqual(['Step one']);
    expect(copy.scopeNote).toContain('12 of 20');
  });
});
