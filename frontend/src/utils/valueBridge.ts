import {
  valueAtTableCaptureRate,
  valueAtTableRowSummary,
  valueAtTableSpendPoolLabel,
} from './diagnosticRationale';
import {
  interpolateBandValue,
  interpolateLeverValueCr,
  leverKey,
  PERCENTILE_DEFAULT,
  sumLeverValuesAtPercentiles,
} from './percentileInterpolation';
import type { ValueAtTableRow } from '../types';

export interface ValueBridgeSegment {
  leverId: string;
  leverName: string;
  shortName: string;
  p10Cr: number;
  p50Cr: number;
  p90Cr: number;
  scenarioCr: number;
  percentile: number;
  sharePct: number;
  color: string;
  insight: string | null;
  poolLabel: string | null;
  captureLabel: string | null;
  complexityTier: string | null;
  savingsTypeLabel: string | null;
  row: ValueAtTableRow;
}

export interface ValueBridgePortfolio {
  totalP10: number;
  totalP50: number;
  totalP90: number;
  totalScenario: number;
  leverCount: number;
  top3SharePct: number;
}

const BRIDGE_PALETTE = [
  '#000000',
  '#86BC25',
  '#53565A',
  '#0563C1',
  '#003F7F',
  '#2D5016',
  '#6B7280',
  '#1E3A5F',
  '#4A6741',
  '#374151',
  '#0F766E',
  '#7C3AED',
];

const COMPLEXITY_SHORT: Record<string, string> = {
  low: 'Quick win',
  medium: 'Medium effort',
  high: 'Complex',
};

function truncateLabel(value: string, max = 28): string {
  const trimmed = value.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max - 1)}…`;
}

function sumBand(rows: ValueAtTableRow[], key: 'p10_cr' | 'p50_cr' | 'p90_cr'): number {
  return rows.reduce((sum, row) => {
    const v = Number(row[key] ?? 0);
    return sum + (Number.isFinite(v) ? v : 0);
  }, 0);
}

export function buildValueBridgePortfolio(
  rows: ValueAtTableRow[],
  percentilesByLever: Record<string, number>,
  totalP50Cr?: number,
  topN = 3,
): ValueBridgePortfolio {
  const totalP10 = sumBand(rows, 'p10_cr');
  const totalP50 = totalP50Cr ?? sumBand(rows, 'p50_cr');
  const totalP90 = sumBand(rows, 'p90_cr');
  const totalScenario = sumLeverValuesAtPercentiles(rows, percentilesByLever);
  const { segments } = buildValueBridgeSegments(rows, percentilesByLever, totalP50Cr);
  const top3SharePct = segments
    .slice(0, topN)
    .reduce((sum, segment) => sum + segment.sharePct, 0);

  return {
    totalP10,
    totalP50,
    totalP90,
    totalScenario,
    leverCount: segments.length,
    top3SharePct,
  };
}

export function valueBridgeConcentrationLine(portfolio: ValueBridgePortfolio): string | null {
  if (portfolio.leverCount <= 1) return null;
  const topN = Math.min(3, portfolio.leverCount);
  return `Top ${topN} levers account for ${portfolio.top3SharePct.toFixed(0)}% of scenario value`;
}

export function complexityShortLabel(tier: string | null | undefined): string | null {
  if (!tier) return null;
  return COMPLEXITY_SHORT[String(tier).toLowerCase()] ?? null;
}

export function buildValueBridgeSegments(
  rows: ValueAtTableRow[],
  percentilesByLever: Record<string, number>,
  _totalP50Cr?: number,
): { segments: ValueBridgeSegment[]; totalScenario: number } {
  const sorted = [...rows].sort((a, b) => Number(b.p50_cr ?? 0) - Number(a.p50_cr ?? 0));
  const totalScenario = sumLeverValuesAtPercentiles(rows, percentilesByLever);

  const segments = sorted
    .map((row, index) => {
      const p50Cr = Number(row.p50_cr ?? 0);
      if (!Number.isFinite(p50Cr) || p50Cr <= 0) return null;
      const p10Cr = Number(row.p10_cr ?? 0);
      const p90Cr = Number(row.p90_cr ?? 0);
      const origIndex = rows.indexOf(row);
      const key = leverKey(row, origIndex >= 0 ? origIndex : index);
      const percentile = percentilesByLever[key] ?? PERCENTILE_DEFAULT;
      const scenarioCr = interpolateLeverValueCr(row, percentile);
      const leverName = String(row.lever_name ?? 'Lever');
      const complexityTier = String(row.complexity_tier ?? '').trim() || null;

      const capturePct = (() => {
        const d = row.value_derivation;
        if (!d) return null;
        const p10 = Number(d.savings_rate_p10_pct);
        const p50 = Number(d.savings_rate_p50_pct);
        const p90 = Number(d.savings_rate_p90_pct);
        if (!Number.isFinite(p50)) return valueAtTableCaptureRate(row, 'p50');
        if (!Number.isFinite(p10) || !Number.isFinite(p90)) {
          return `${p50}% capture (P50)`;
        }
        const rate = interpolateBandValue(p10, p50, p90, percentile);
        return `${rate.toLocaleString('en-IN', { maximumFractionDigits: 1 })}% capture (P${Math.round(percentile)})`;
      })();

      return {
        leverId: key,
        leverName,
        shortName: truncateLabel(leverName),
        p10Cr: Number.isFinite(p10Cr) ? p10Cr : 0,
        p50Cr,
        p90Cr: Number.isFinite(p90Cr) ? p90Cr : p50Cr,
        scenarioCr,
        percentile,
        sharePct: totalScenario > 0 ? (scenarioCr / totalScenario) * 100 : 0,
        color: BRIDGE_PALETTE[index % BRIDGE_PALETTE.length],
        insight: valueAtTableRowSummary(row),
        poolLabel: valueAtTableSpendPoolLabel(row),
        captureLabel: capturePct ?? valueAtTableCaptureRate(row, 'p50'),
        complexityTier,
        savingsTypeLabel: String(row.savings_type_label ?? row.savings_type ?? '').trim() || null,
        row,
      };
    })
    .filter((segment): segment is ValueBridgeSegment => segment != null);

  return { segments, totalScenario };
}

export function valueAtTableMethodologySummary(methodology?: {
  eligible_levers_total?: number;
  shown_levers?: number;
}): string {
  const eligible = methodology?.eligible_levers_total;
  const shown = methodology?.shown_levers;
  if (eligible != null && shown != null) {
    return `Top ${shown} of ${eligible} eligible levers · sector capture rates × addressable spend pools`;
  }
  return 'Sector capture rates applied to addressable spend pools · expand for methodology';
}

export function valueBridgeHowValued(segment: ValueBridgeSegment): string | null {
  const parts: string[] = [];
  if (segment.poolLabel) parts.push(segment.poolLabel);
  if (segment.captureLabel) parts.push(segment.captureLabel);
  return parts.length ? parts.join(' · ') : segment.insight;
}
