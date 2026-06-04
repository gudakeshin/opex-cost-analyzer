import { gapHeadroomCr, resolveCategoryLabel } from './categoryLabels';
import type { BenchmarkGapRow, ValueAtTableRow } from '../types';

const COMPLEXITY_LABELS: Record<string, string> = {
  low: 'Low complexity',
  medium: 'Medium complexity',
  high: 'High complexity',
};

const DEFAULT_METHODOLOGY = {
  summary:
    'Value at table estimates annual run-rate savings as sector capture rate × addressable spend pool for each eligible lever.',
  steps: [
    'Eligible levers are chosen from the sector playbook when spend signals and industry context match.',
    'Each lever applies P10 / P50 / P90 capture rates from the playbook to an addressable spend pool.',
    'Spend pool = benchmark-proxy category spend when a category matches; otherwise 10% of total implied OpEx.',
    'Top 12 levers by expected (P50) value are shown. Row totals are not deduplicated across levers.',
  ],
};

function fmtPoolCr(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const formatted = value.toLocaleString('en-IN', {
    maximumFractionDigits: value >= 100 ? 0 : 1,
    minimumFractionDigits: 0,
  });
  return `₹${formatted} Cr`;
}

export function benchmarkGapSummary(gap: BenchmarkGapRow): string | null {
  const categoryName = resolveCategoryLabel(
    String(gap.category ?? gap.category_id ?? ''),
    String(gap.category_name ?? ''),
  );
  const p50 = Number(gap.p50_pct);
  const headroom = gapHeadroomCr(gap);
  if (!Number.isFinite(p50) || p50 <= 0) return null;

  const headroomPart =
    headroom > 0 ? ` · ${fmtPoolCr(headroom)} benchmark band to P25` : '';
  return `Proxy: ${categoryName} at ${p50}% of revenue (sector median)${headroomPart}`;
}

export function benchmarkGapCommentary(gap: BenchmarkGapRow): string | null {
  const existing = String(gap.commentary ?? '').trim();
  if (existing) return existing;

  const categoryName = resolveCategoryLabel(
    String(gap.category ?? gap.category_id ?? ''),
    String(gap.category_name ?? ''),
  );
  const p50 = Number(gap.p50_pct);
  const p25 = Number(gap.p25_pct);
  const band =
    Number(gap.benchmark_p50_to_p25_band_cr ?? gap.gap_cr ?? gap.headroom_to_p25_cr ?? 0);

  if (!Number.isFinite(p50) || p50 <= 0) return null;

  const p25Text = Number.isFinite(p25) ? `${p25}%` : 'P25 best-in-class';
  const bandText = Number.isFinite(band) && band > 0 ? ` ₹${band.toLocaleString('en-IN')} Cr` : '';
  return (
    `[Benchmark proxy, not your spend] ${categoryName} is modelled at ${p50}% of revenue ` +
    `(sector median P50 applied to the revenue you entered);` +
    `${bandText ? `${bandText} illustrative band if spend moved to P25 best-in-class (${p25Text}).` : ` illustrative gap to P25 (${p25Text}).`} ` +
    'Upload actual spend for company-specific gaps.'
  );
}

export function valueAtTableRationale(row: ValueAtTableRow): string | null {
  const existing = String(row.rationale ?? '').trim();
  if (existing) return existing;

  const parts: string[] = [];
  const savings = String(row.savings_type_label ?? row.savings_type ?? '').trim();
  const complexity = COMPLEXITY_LABELS[String(row.complexity_tier ?? 'medium')] ?? 'Medium complexity';
  if (savings) {
    parts.push(`${savings} · ${complexity}.`);
  } else if (complexity) {
    parts.push(complexity + '.');
  }

  return parts.length ? parts.join(' ') : null;
}

export function valueAtTableCalculationNote(row: ValueAtTableRow): string | null {
  const existing = String(row.calculation_note ?? '').trim();
  if (existing) return existing;

  const d = row.value_derivation;
  if (d?.calculation_p50) {
    const pool = d.base_spend_cr != null ? fmtPoolCr(Number(d.base_spend_cr)) : '—';
    const poolNote = d.base_spend_note ?? d.base_spend_label ?? 'addressable spend pool';
    const rates =
      d.savings_rate_p10_pct != null && d.savings_rate_p50_pct != null && d.savings_rate_p90_pct != null
        ? `(P10 ${d.savings_rate_p10_pct}% / P50 ${d.savings_rate_p50_pct}% / P90 ${d.savings_rate_p90_pct}%)`
        : '';
    return `${d.calculation_p50}. Pool: ${pool} — ${poolNote}. Capture rates from sector lever playbook ${rates}.`.trim();
  }

  const baseSpend = Number(row.base_spend_cr);
  const p50Rate = Number(row.value_derivation?.savings_rate_p50_pct);
  const p50Cr = Number(row.p50_cr);
  if (Number.isFinite(baseSpend) && baseSpend > 0 && Number.isFinite(p50Cr)) {
    const poolLabel = row.base_spend_label ?? resolveCategoryLabel(String(row.category ?? ''));
    const rateText = Number.isFinite(p50Rate) ? `${p50Rate}% × ` : '';
    return `Expected (P50) = ${rateText}${fmtPoolCr(baseSpend)} ${poolLabel} pool ≈ ${fmtPoolCr(p50Cr)} annual run-rate.`;
  }

  return null;
}

export function valueAtTableRowSummary(row: ValueAtTableRow): string | null {
  const d = row.value_derivation;
  if (d?.calculation_p50) {
    return String(d.calculation_p50);
  }

  const capture = valueAtTableCaptureRate(row, 'p50');
  const pool = Number(row.base_spend_cr ?? d?.base_spend_cr);
  const p50Cr = Number(row.p50_cr);
  if (capture && Number.isFinite(pool) && pool > 0 && Number.isFinite(p50Cr)) {
    return `${capture} capture × ${fmtPoolCr(pool)} pool → ${fmtPoolCr(p50Cr)} expected`;
  }

  const name = String(row.lever_name ?? '').trim();
  if (Number.isFinite(p50Cr) && p50Cr > 0) {
    return `${name || 'Lever'} · ${fmtPoolCr(p50Cr)} expected (P50)`;
  }

  return name || null;
}

export function valueAtTableMethodologyCopy(methodology?: {
  summary?: string;
  steps?: string[];
  eligible_levers_total?: number;
  shown_levers?: number;
}) {
  const summary = methodology?.summary ?? DEFAULT_METHODOLOGY.summary;
  const steps = methodology?.steps?.length ? methodology.steps : DEFAULT_METHODOLOGY.steps;
  const eligible = methodology?.eligible_levers_total;
  const shown = methodology?.shown_levers;
  const scopeNote =
    eligible != null && shown != null
      ? `Showing top ${shown} of ${eligible} eligible levers by expected (P50) value.`
      : null;
  return { summary, steps, scopeNote };
}

export function valueAtTableSpendPoolLabel(row: ValueAtTableRow): string | null {
  const label = String(row.base_spend_label ?? row.value_derivation?.base_spend_label ?? '').trim();
  const pool = Number(row.base_spend_cr ?? row.value_derivation?.base_spend_cr);
  if (!label && !Number.isFinite(pool)) return null;
  if (Number.isFinite(pool) && pool > 0) {
    return `${fmtPoolCr(pool)} · ${label || resolveCategoryLabel(String(row.category ?? ''))}`;
  }
  return label || null;
}

export function valueAtTableCaptureRate(row: ValueAtTableRow, band: 'p10' | 'p50' | 'p90'): string | null {
  const key =
    band === 'p10'
      ? 'savings_rate_p10_pct'
      : band === 'p90'
        ? 'savings_rate_p90_pct'
        : 'savings_rate_p50_pct';
  const rate = Number(row.value_derivation?.[key]);
  if (!Number.isFinite(rate)) return null;
  return `${rate}%`;
}

export function benchmarkGapsPanelSummary(gaps: BenchmarkGapRow[]): string {
  if (!gaps.length) return 'No benchmark gaps';
  const totalHeadroom = gaps.reduce((sum, gap) => {
    const band = Number(
      gap.benchmark_p50_to_p25_band_cr ?? gap.gap_cr ?? gap.headroom_to_p25_cr ?? 0,
    );
    return sum + (Number.isFinite(band) && band > 0 ? band : 0);
  }, 0);
  const headroomLabel = totalHeadroom.toLocaleString('en-IN', {
    maximumFractionDigits: totalHeadroom >= 100 ? 0 : 1,
  });
  return `${gaps.length} categor${gaps.length === 1 ? 'y' : 'ies'} · ₹${headroomLabel} Cr headroom to best-in-class`;
}
