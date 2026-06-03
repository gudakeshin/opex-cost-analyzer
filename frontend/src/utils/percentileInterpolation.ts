import type { ValueAtTableRow } from '../types';

export const PERCENTILE_MIN = 10;
export const PERCENTILE_MAX = 90;
export const PERCENTILE_DEFAULT = 50;

/** Piecewise linear interpolation across P10 → P50 → P90 anchor points. */
export function interpolateBandValue(p10: number, p50: number, p90: number, percentile: number): number {
  const p10v = Number.isFinite(p10) ? p10 : 0;
  const p50v = Number.isFinite(p50) ? p50 : p10v;
  const p90v = Number.isFinite(p90) ? p90 : p50v;
  const p = Math.min(PERCENTILE_MAX, Math.max(PERCENTILE_MIN, percentile));

  if (p <= PERCENTILE_DEFAULT) {
    const t = (p - PERCENTILE_MIN) / (PERCENTILE_DEFAULT - PERCENTILE_MIN);
    return p10v + t * (p50v - p10v);
  }
  const t = (p - PERCENTILE_DEFAULT) / (PERCENTILE_MAX - PERCENTILE_DEFAULT);
  return p50v + t * (p90v - p50v);
}

export function interpolateLeverValueCr(row: ValueAtTableRow, percentile: number): number {
  return interpolateBandValue(
    Number(row.p10_cr ?? 0),
    Number(row.p50_cr ?? 0),
    Number(row.p90_cr ?? row.p50_cr ?? 0),
    percentile,
  );
}

export function interpolateCaptureRatePct(row: ValueAtTableRow, percentile: number): number | null {
  const d = row.value_derivation;
  if (!d) return null;
  const p10 = Number(d.savings_rate_p10_pct);
  const p50 = Number(d.savings_rate_p50_pct);
  const p90 = Number(d.savings_rate_p90_pct);
  if (!Number.isFinite(p50)) return null;
  if (!Number.isFinite(p10) || !Number.isFinite(p90)) return p50;
  return interpolateBandValue(p10, p50, p90, percentile);
}

export function percentileScenarioLabel(percentile: number): string {
  const p = Math.round(percentile);
  if (p === PERCENTILE_DEFAULT) return 'Expected (P50)';
  if (p < PERCENTILE_DEFAULT) return `Conservative (P${p})`;
  return `Stretch (P${p})`;
}

export function percentileScenarioShort(percentile: number): string {
  return `P${Math.round(percentile)}`;
}

export function sumInterpolatedLeverValues(rows: ValueAtTableRow[], percentile: number): number {
  return rows.reduce((sum, row) => {
    const v = interpolateLeverValueCr(row, percentile);
    return sum + (Number.isFinite(v) && v > 0 ? v : 0);
  }, 0);
}

export function leverKey(row: ValueAtTableRow, index = 0): string {
  return String(row.lever_id ?? row.lever_name ?? index);
}

export function buildDefaultPercentilesByLever(rows: ValueAtTableRow[]): Record<string, number> {
  const map: Record<string, number> = {};
  rows.forEach((row, index) => {
    const key = leverKey(row, index);
    map[key] = PERCENTILE_DEFAULT;
  });
  return map;
}

export function sumLeverValuesAtPercentiles(
  rows: ValueAtTableRow[],
  percentilesByLever: Record<string, number>,
): number {
  return rows.reduce((sum, row, index) => {
    const key = leverKey(row, index);
    const percentile = percentilesByLever[key] ?? PERCENTILE_DEFAULT;
    const v = interpolateLeverValueCr(row, percentile);
    return sum + (Number.isFinite(v) && v > 0 ? v : 0);
  }, 0);
}

export function mergePercentilesForRows(
  rows: ValueAtTableRow[],
  previous: Record<string, number>,
): Record<string, number> {
  const next = buildDefaultPercentilesByLever(rows);
  for (const key of Object.keys(next)) {
    if (previous[key] != null) {
      next[key] = previous[key];
    }
  }
  return next;
}
