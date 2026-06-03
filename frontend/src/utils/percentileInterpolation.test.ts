import { describe, expect, it } from 'vitest';
import {
  buildDefaultPercentilesByLever,
  interpolateBandValue,
  interpolateLeverValueCr,
  percentileScenarioLabel,
  sumLeverValuesAtPercentiles,
} from './percentileInterpolation';

describe('percentileInterpolation', () => {
  it('returns anchor values at P10, P50, and P90', () => {
    expect(interpolateBandValue(10, 25, 40, 10)).toBeCloseTo(10);
    expect(interpolateBandValue(10, 25, 40, 50)).toBeCloseTo(25);
    expect(interpolateBandValue(10, 25, 40, 90)).toBeCloseTo(40);
  });

  it('interpolates between P10 and P50', () => {
    expect(interpolateBandValue(10, 30, 50, 30)).toBeCloseTo(20);
  });

  it('interpolates lever values from row bands', () => {
    const value = interpolateLeverValueCr({ p10_cr: 10, p50_cr: 25, p90_cr: 40 }, 50);
    expect(value).toBeCloseTo(25);
  });

  it('labels scenarios for executives', () => {
    expect(percentileScenarioLabel(50)).toBe('Expected (P50)');
    expect(percentileScenarioLabel(20)).toBe('Conservative (P20)');
    expect(percentileScenarioLabel(75)).toBe('Stretch (P75)');
  });

  it('sums lever values using individual percentiles', () => {
    const rows = [
      { lever_id: 'a', p10_cr: 10, p50_cr: 20, p90_cr: 30 },
      { lever_id: 'b', p10_cr: 10, p50_cr: 20, p90_cr: 30 },
    ];
    const allP50 = sumLeverValuesAtPercentiles(rows, buildDefaultPercentilesByLever(rows));
    expect(allP50).toBeCloseTo(40);

    const mixed = sumLeverValuesAtPercentiles(rows, { a: 10, b: 90 });
    expect(mixed).toBeCloseTo(40);
  });
});
