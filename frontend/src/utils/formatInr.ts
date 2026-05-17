/** INR-native formatting for executive Cost Room (₹ Cr). */

export function formatCr(value: number, opts?: { perYear?: boolean; decimals?: number }): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const decimals = opts?.decimals ?? (Math.abs(n) >= 100 ? 0 : 1);
  const formatted = n.toLocaleString('en-IN', {
    maximumFractionDigits: decimals,
    minimumFractionDigits: 0,
  });
  const suffix = opts?.perYear ? '/yr' : '';
  return `₹${formatted} Cr${suffix}`;
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
