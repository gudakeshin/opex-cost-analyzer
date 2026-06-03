import { describe, expect, it } from 'vitest';
import { gapHeadroomCr, resolveCategoryLabel } from './categoryLabels';

describe('categoryLabels', () => {
  it('maps auto-generated backend names to taxonomy labels', () => {
    expect(resolveCategoryLabel('RND', 'Rnd')).toBe('R&D & Engineering');
    expect(resolveCategoryLabel('IT', 'It')).toBe('IT & Technology');
    expect(resolveCategoryLabel('HR', 'Hr')).toBe('HR & Recruitment');
    expect(resolveCategoryLabel('PROF_SVCS', 'Prof Svcs')).toBe('Professional Services');
  });

  it('preserves proper category names from API', () => {
    expect(resolveCategoryLabel('IT', 'IT & Technology')).toBe('IT & Technology');
  });

  it('resolves headroom from renamed and legacy fields', () => {
    expect(gapHeadroomCr({ benchmark_p50_to_p25_band_cr: 100 })).toBe(100);
    expect(gapHeadroomCr({ gap_cr: 75 })).toBe(75);
    expect(gapHeadroomCr({ headroom_to_p25_cr: 50 })).toBe(50);
    expect(gapHeadroomCr({})).toBe(0);
  });

  it('prefers benchmark_p50_to_p25_band_cr over legacy headroom', () => {
    expect(
      gapHeadroomCr({
        benchmark_p50_to_p25_band_cr: 90,
        headroom_to_p25_cr: 50,
      }),
    ).toBe(90);
  });
});
