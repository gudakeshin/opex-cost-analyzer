import { describe, expect, it } from 'vitest';
import { formatBandRange, formatCr, INR_PER_CR, toCr } from './formatInr';

describe('formatInr', () => {
  it('scales raw INR pipeline amounts to crore display', () => {
    expect(formatCr(2_720_783_853)).toBe('₹272 Cr');
    expect(formatCr(INR_PER_CR)).toBe('₹1 Cr');
  });

  it('leaves pre-scaled diagnostic crore values unchanged', () => {
    expect(formatCr(25, { alreadyInCr: true })).toBe('₹25 Cr');
    expect(formatCr(6800, { alreadyInCr: true })).toBe('₹6,800 Cr');
  });

  it('computes EBITDA bps from raw savings and crore revenue', () => {
    const savingsCr = toCr(2_720_783_853, 'INR');
    const revenueCr = 6800;
    const bps = Math.round((savingsCr / revenueCr) * 10000);
    expect(bps).toBeGreaterThan(0);
    expect(bps).toBeLessThan(500);
  });

  it('formats band ranges from raw amounts', () => {
    expect(formatBandRange(INR_PER_CR * 2, INR_PER_CR * 3)).toBe('2 – 3');
  });

  it('formats USD amounts in millions', () => {
    expect(formatCr(5_000_000, { currency: 'USD' })).toBe('$5 M');
  });
});
