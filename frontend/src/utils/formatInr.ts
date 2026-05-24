/** Currency-aware formatting for executive Cost Room. INR uses Cr scale; others use M scale. */

export function formatCr(
  value: number,
  opts?: { perYear?: boolean; decimals?: number; currency?: string },
): string {
  const currency = (opts?.currency ?? 'INR').toUpperCase();
  const sym = currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '₹';
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const decimals = opts?.decimals ?? (Math.abs(n) >= 100 ? 0 : 1);
  const suffix = opts?.perYear ? '/yr' : '';
  if (currency === 'INR') {
    const formatted = n.toLocaleString('en-IN', { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
    return `${sym}${formatted} Cr${suffix}`;
  }
  const formatted = n.toLocaleString('en-US', { maximumFractionDigits: decimals, minimumFractionDigits: 0 });
  return `${sym}${formatted} M${suffix}`;
}

export function formatBps(value: number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${Math.round(n)} bps`;
}

export function formatBandRange(p10: number, p90: number): string {
  const a = Number(p10);
  const b = Number(p90);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return '—';
  const fmt = (x: number) =>
    x.toLocaleString('en-IN', { maximumFractionDigits: 0, minimumFractionDigits: 0 });
  return `${fmt(a)} – ${fmt(b)}`;
}

export function formatIndustryLabel(industry?: string): string {
  if (!industry) return 'General';
  return industry
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
