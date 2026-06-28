import { describe, expect, it } from 'vitest';
import type { Initiative } from '../types';
import {
  actionReason,
  getBandNpv,
  getBandSavings,
  priorityScore,
} from './initiativeHelpers';

/** Reference row from savings_modeler (₹2M addressable gap, contract renegotiation phasing). */
const MODELED_ROW: Initiative = {
  initiative_id: 'ref',
  category: 'HR',
  lever: 'contract_renegotiation',
  stage: 'identified',
  gross_savings_y1: 500_000,
  gross_savings_y2: 1_000_000,
  gross_savings_y3: 500_000,
  cost_to_achieve: 160_000,
  net_npv: 1_514_500.38,
  p50_savings: 500_000,
  p10_savings: 350_000,
  p90_savings: 650_000,
};

describe('getBandNpv', () => {
  it('matches savings_modeler NPV at P50', () => {
    expect(getBandNpv(MODELED_ROW, 'p50')).toBeCloseTo(1_514_500.38, 0);
  });

  it('orders P10 < P50 < P90', () => {
    const p10 = getBandNpv(MODELED_ROW, 'p10');
    const p50 = getBandNpv(MODELED_ROW, 'p50');
    const p90 = getBandNpv(MODELED_ROW, 'p90');
    expect(p10).toBeLessThan(p50);
    expect(p50).toBeLessThan(p90);
  });

  it('scales NPV with explicit band savings', () => {
    const custom: Initiative = {
      ...MODELED_ROW,
      p10_savings: MODELED_ROW.p50_savings! * 0.55,
      p90_savings: MODELED_ROW.p50_savings! * 1.45,
    };
    expect(getBandNpv(custom, 'p10')).toBeLessThan(getBandNpv(MODELED_ROW, 'p10'));
    expect(getBandNpv(custom, 'p90')).toBeGreaterThan(getBandNpv(MODELED_ROW, 'p90'));
  });

  it('does not equate NPV to band savings', () => {
    expect(getBandNpv(MODELED_ROW, 'p50')).not.toBeCloseTo(getBandSavings(MODELED_ROW, 'p50'), -2);
  });

  it('NPV is discounted below gross 3-year savings for each band', () => {
    const gross3 = 500_000 + 1_000_000 + 500_000;
    for (const band of ['p10', 'p50', 'p90'] as const) {
      const factor = band === 'p10' ? 0.7 : band === 'p90' ? 1.3 : 1;
      expect(getBandNpv(MODELED_ROW, band)).toBeLessThanOrEqual(gross3 * factor + 1);
    }
  });
});

describe('priorityScore and actionReason', () => {
  it('ranks low AQS higher urgency', () => {
    const lowAqs: Initiative = { ...MODELED_ROW, aqs: 0.5, stage: 'proposed' };
    const highAqs: Initiative = { ...MODELED_ROW, aqs: 0.85, stage: 'proposed' };
    expect(priorityScore(lowAqs)).toBeGreaterThan(priorityScore(highAqs));
  });

  it('actionReason flags blocked AQS', () => {
    const blocked: Initiative = { ...MODELED_ROW, aqs: 0.5 };
    expect(actionReason(blocked).tone).toBe('block');
  });
});
