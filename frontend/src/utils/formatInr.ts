/** Currency-aware formatting for executive views. INR uses Cr scale; others use M scale.

Backend skill outputs and pipeline initiative amounts are stored in **absolute currency
units** (e.g. INR rupees). Diagnostic ``*_cr`` fields and ``annual_revenue_cr`` are already
in crore units. ``formatCr`` scales raw amounts by default; pass ``alreadyInCr: true`` when
the value is pre-scaled.
*/

export const INR_PER_CR = 10_000_000;
export const USD_PER_M = 1_000_000;

export type FormatCrOptions = {
  perYear?: boolean;
  decimals?: number;
  currency?: string;
  bare?: boolean;
  /** When true, ``value`` is already in Cr/M display units (diagnostic *_cr fields). */
  alreadyInCr?: boolean;
};

export function toCr(value: number, currency = 'INR', alreadyInCr = false): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  if (alreadyInCr) return n;
  const c = currency.toUpperCase();
  if (c === 'INR') return n / INR_PER_CR;
  return n / USD_PER_M;
}

export function formatCr(value: number, opts?: FormatCrOptions): string {
  const currency = (opts?.currency ?? 'INR').toUpperCase();
  const sym = currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '₹';
  const scaled = toCr(value, currency, opts?.alreadyInCr ?? false);
  if (!Number.isFinite(scaled)) return '—';
  const decimals = opts?.decimals ?? (Math.abs(scaled) >= 100 ? 0 : 1);
  const suffix = opts?.perYear ? '/yr' : '';
  const unit = currency === 'INR' ? 'Cr' : 'M';
  const locale = currency === 'INR' ? 'en-IN' : 'en-US';
  const formatted = scaled.toLocaleString(locale, {
    maximumFractionDigits: decimals,
    minimumFractionDigits: 0,
  });
  if (opts?.bare) return `${sym}${formatted}`;
  return `${sym}${formatted} ${unit}${suffix}`;
}

export function currencySymbol(currency = 'INR'): string {
  const c = currency.toUpperCase();
  return c === 'USD' ? '$' : c === 'EUR' ? '€' : c === 'GBP' ? '£' : '₹';
}

/** Adaptive amount formatting: Cr/M units when the scaled value is readable
 * (≥ 0.05 Cr / 0.05 M), otherwise the raw amount — invoice-level lines would
 * all collapse to "₹0 Cr" under the fixed Cr scale. */
export function formatAmount(value: number, currency = 'INR'): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const scaled = toCr(n, currency);
  if (n === 0 || Math.abs(scaled) >= 0.05) {
    const decimals = Math.abs(scaled) >= 100 ? 0 : Math.abs(scaled) >= 1 ? 1 : 2;
    return formatCr(n, { currency, decimals });
  }
  const locale = currency.toUpperCase() === 'INR' ? 'en-IN' : 'en-US';
  return `${currencySymbol(currency)}${n.toLocaleString(locale, { maximumFractionDigits: 0 })}`;
}

export function formatBps(value: number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${Math.round(n)} bps`;
}

export function formatBandRange(
  p10: number,
  p90: number,
  opts?: Pick<FormatCrOptions, 'currency' | 'alreadyInCr'>,
): string {
  const currency = opts?.currency ?? 'INR';
  const a = toCr(p10, currency, opts?.alreadyInCr ?? false);
  const b = toCr(p90, currency, opts?.alreadyInCr ?? false);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return '—';
  const locale = currency.toUpperCase() === 'INR' ? 'en-IN' : 'en-US';
  const fmt = (x: number) =>
    x.toLocaleString(locale, { maximumFractionDigits: 1, minimumFractionDigits: 0 });
  return `${fmt(a)} – ${fmt(b)}`;
}

export function formatIndustryLabel(industry?: string): string {
  if (!industry) return 'General';
  return industry
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
