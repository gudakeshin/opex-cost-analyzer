/** Copy and helpers for diagnostic runs that use a synthetic benchmark spend profile. */

export const BENCHMARK_PROXY_DISCLAIMER_TITLE =
  'Not based on your company’s spend data';

export const BENCHMARK_PROXY_DISCLAIMER_BODY =
  'Benchmark gaps and value-at-table figures use a synthetic spend profile built from sector benchmark medians and the revenue you entered. They are directional estimates—not an analysis of uploaded invoices, GL, or actual category spend.';

export const BENCHMARK_PROXY_DISCLAIMER_RECOVERY =
  'Upload actual spend in a procurement session for company-specific gaps and lever sizing.';

export function isBenchmarkProxyProfile(profileBasis?: string): boolean {
  if (!profileBasis) return true;
  return profileBasis === 'benchmark_proxy';
}

export function benchmarkProxyDisclaimerDetail(dataNote?: string): string {
  const note = String(dataNote ?? '').trim();
  if (note) return `${BENCHMARK_PROXY_DISCLAIMER_BODY} ${note}`;
  return BENCHMARK_PROXY_DISCLAIMER_BODY;
}
