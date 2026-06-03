import { describe, expect, it } from 'vitest';
import { buildDefaultPercentilesByLever } from './percentileInterpolation';
import {
  buildValueBridgePortfolio,
  buildValueBridgeSegments,
  valueBridgeHowValued,
} from './valueBridge';

describe('valueBridge', () => {
  const sampleRows = [
    {
      lever_id: 'a',
      lever_name: 'Lever A',
      p10_cr: 5,
      p50_cr: 10,
      p90_cr: 15,
      base_spend_cr: 80,
      base_spend_label: 'IT pool',
      complexity_tier: 'low',
      value_derivation: {
        savings_rate_p10_pct: 8,
        savings_rate_p50_pct: 12,
        savings_rate_p90_pct: 18,
      },
    },
    {
      lever_id: 'b',
      lever_name: 'Lever B',
      p10_cr: 20,
      p50_cr: 30,
      p90_cr: 45,
      complexity_tier: 'high',
    },
  ];

  it('builds segments sorted by P50 descending with share percentages', () => {
    const percentiles = buildDefaultPercentilesByLever([
      { lever_id: 'a', lever_name: 'Lever A', p10_cr: 5, p50_cr: 10, p90_cr: 15 },
      { lever_id: 'b', lever_name: 'Lever B', p10_cr: 20, p50_cr: 30, p90_cr: 45 },
    ]);
    const { segments, totalScenario } = buildValueBridgeSegments(
      [
        { lever_id: 'a', lever_name: 'Lever A', p10_cr: 5, p50_cr: 10, p90_cr: 15 },
        { lever_id: 'b', lever_name: 'Lever B', p10_cr: 20, p50_cr: 30, p90_cr: 45 },
      ],
      percentiles,
    );

    expect(totalScenario).toBe(40);
    expect(segments).toHaveLength(2);
    expect(segments[0].leverName).toBe('Lever B');
    expect(segments[0].sharePct).toBeCloseTo(75, 1);
    expect(segments[1].sharePct).toBeCloseTo(25, 1);
  });

  it('enriches segments with pool, capture, and band values', () => {
    const percentiles = buildDefaultPercentilesByLever(sampleRows);
    const { segments } = buildValueBridgeSegments(sampleRows, percentiles);
    expect(segments[0].p10Cr).toBe(20);
    expect(segments[0].p90Cr).toBe(45);
    expect(segments[1].poolLabel).toContain('IT pool');
    expect(segments[1].captureLabel).toContain('12%');
    expect(segments[1].complexityTier).toBe('low');
  });

  it('recalculates scenario values when a lever percentile changes', () => {
    const percentiles = buildDefaultPercentilesByLever(sampleRows);
    const atP50 = buildValueBridgeSegments(sampleRows, percentiles);
    const atMixed = buildValueBridgeSegments(sampleRows, { ...percentiles, a: 10, b: 90 });
    expect(atMixed.totalScenario).toBeCloseTo(50);
    expect(atP50.totalScenario).toBeCloseTo(40);
    expect(atMixed.totalScenario).not.toBeCloseTo(atP50.totalScenario);
  });

  it('builds portfolio totals and concentration insight', () => {
    const percentiles = buildDefaultPercentilesByLever(sampleRows);
    const portfolio = buildValueBridgePortfolio(sampleRows, percentiles);
    expect(portfolio.totalP10).toBe(25);
    expect(portfolio.totalP50).toBe(40);
    expect(portfolio.totalP90).toBe(60);
    expect(portfolio.leverCount).toBe(2);
  });

  it('combines pool and capture for how-valued copy', () => {
    const percentiles = buildDefaultPercentilesByLever(sampleRows);
    const { segments } = buildValueBridgeSegments(sampleRows, percentiles);
    const how = valueBridgeHowValued(segments[1]);
    expect(how).toContain('IT pool');
    expect(how).toContain('12%');
  });
});
