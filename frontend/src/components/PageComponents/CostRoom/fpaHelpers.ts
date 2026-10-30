/** Shared helpers for FP&A tab visualizations. */

import { formatCr } from '../../../utils/formatInr';

export function formatAmount(value: unknown, currency = 'INR'): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return formatCr(n, { currency, decimals: 1 });
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function asArray<T = Record<string, unknown>>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

/** Caption for truncated lists, or null when nothing was dropped. */
export function truncationCaption(shown: number, total: number): string | null {
  return total > shown ? `Showing top ${shown} of ${total}` : null;
}
