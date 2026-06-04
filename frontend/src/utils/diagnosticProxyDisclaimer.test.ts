import { describe, expect, it } from 'vitest';
import { benchmarkProxyDisclaimerDetail, isBenchmarkProxyProfile } from './diagnosticProxyDisclaimer';

describe('diagnosticProxyDisclaimer', () => {
  it('treats missing profile_basis as benchmark proxy', () => {
    expect(isBenchmarkProxyProfile(undefined)).toBe(true);
    expect(isBenchmarkProxyProfile('benchmark_proxy')).toBe(true);
    expect(isBenchmarkProxyProfile('actual_spend')).toBe(false);
  });

  it('appends API data_note to disclaimer detail', () => {
    const detail = benchmarkProxyDisclaimerDetail('Upload spend for precision.');
    expect(detail).toContain('synthetic spend profile');
    expect(detail).toContain('Upload spend for precision.');
  });
});
