import React, { useMemo } from 'react';
import { Card } from '../../Common/Card';
import { CollapsibleDetail, CollapsiblePanel } from '../../Common/CollapsibleDetail';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import { BenchmarkProxyDisclaimer } from './BenchmarkProxyDisclaimer';
import { DiagnosticValueBridge } from './DiagnosticValueBridge';
import { isBenchmarkProxyProfile } from '../../../utils/diagnosticProxyDisclaimer';
import { formatCr } from '../../../utils/formatInr';
import { gapHeadroomCr, resolveCategoryLabel } from '../../../utils/categoryLabels';
import {
  benchmarkGapCommentary,
  benchmarkGapSummary,
  benchmarkGapsPanelSummary,
  valueAtTableMethodologyCopy,
} from '../../../utils/diagnosticRationale';
import { valueAtTableMethodologySummary } from '../../../utils/valueBridge';
import type {
  BenchmarkGapRow,
  DiagnosticResponse,
  ValueAtTableMethodology,
  ValueAtTableRow,
} from '../../../types';

const TH_CLASS =
  'py-3 px-2 text-left text-sm font-semibold uppercase tracking-wide text-brand-muted border-b border-brand-border';
const TD_CLASS = 'py-3 px-2 text-base text-brand-ink';
const NUM_CLASS = 'tabular-nums';

function formatPct(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return `${n.toLocaleString('en-IN', { maximumFractionDigits: 1, minimumFractionDigits: 0 })}%`;
}

function DetailBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-brand-muted">{label}</p>
      <p className="mt-0.5 text-sm text-brand-muted leading-relaxed">{text}</p>
    </div>
  );
}

function sortBenchmarkGaps(gaps: BenchmarkGapRow[]): BenchmarkGapRow[] {
  return [...gaps].sort((a, b) => {
    const ha = gapHeadroomCr(a);
    const hb = gapHeadroomCr(b);
    if (hb !== ha) return hb - ha;
    const ia = Number(a.implied_p50_cr ?? 0);
    const ib = Number(b.implied_p50_cr ?? 0);
    return ib - ia;
  });
}

interface BenchmarkGapsTableProps {
  gaps: BenchmarkGapRow[];
  dataNote?: string;
  profileBasis?: string;
  percentileLegend?: Record<string, string>;
}

export const BenchmarkGapsTable: React.FC<BenchmarkGapsTableProps> = ({
  gaps,
  dataNote,
  profileBasis,
  percentileLegend,
}) => {
  const allSorted = useMemo(() => sortBenchmarkGaps(gaps), [gaps]);
  const sorted = useMemo(() => allSorted.slice(0, 10), [allSorted]);
  const panelSummary = benchmarkGapsPanelSummary(sorted);
  const legend = percentileLegend?.p25
    ? `P25 = ${percentileLegend.p25} · P50 = ${percentileLegend.p50 ?? 'industry median'}`
    : 'P25 = best-in-class quartile · P50 = industry median';

  const showProxyDisclaimer = isBenchmarkProxyProfile(profileBasis);

  return (
    <Card title="Benchmark gaps" className="border-brand-border bg-white">
      {showProxyDisclaimer && (
        <BenchmarkProxyDisclaimer dataNote={dataNote} compact className="mb-4" />
      )}
      <CollapsiblePanel title="Ranked category gaps" summary={panelSummary}>
        {legend && (
          <p className="mb-4 text-xs text-brand-muted">{legend}</p>
        )}
        <div className="overflow-x-auto executive-shell">
          <table className="w-full">
            <thead>
              <tr>
                <th scope="col" className={`${TH_CLASS} w-10`}>
                  #
                </th>
                <th scope="col" className={TH_CLASS}>
                  Category
                </th>
                <th scope="col" className={`${TH_CLASS} text-right`}>
                  Median spend (% of revenue)
                </th>
                <th scope="col" className={`${TH_CLASS} text-right`}>
                  Savings to best-in-class (₹ Cr)
                </th>
                <th scope="col" className={TH_CLASS}>
                  Benchmark narrative (proxy)
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((g, i) => {
                const headroom = gapHeadroomCr(g);
                const categoryKey = String(g.category ?? g.category_id ?? i);
                const commentary = benchmarkGapCommentary(g);
                const summary = benchmarkGapSummary(g);
                return (
                  <tr
                    key={categoryKey}
                    className={`border-b border-brand-border ${i < 3 ? 'bg-brand-surface-muted/80' : ''}`}
                  >
                    <td className={`${TD_CLASS} ${NUM_CLASS} text-brand-muted text-sm align-top`}>
                      {String(i + 1).padStart(2, '0')}
                    </td>
                    <td className={`${TD_CLASS} font-medium align-top`}>
                      {resolveCategoryLabel(
                        String(g.category ?? g.category_id ?? ''),
                        String(g.category_name ?? ''),
                      )}
                    </td>
                    <td className={`${TD_CLASS} ${NUM_CLASS} text-right align-top`}>
                      {formatPct(g.p50_pct)}
                    </td>
                    <td className={`${TD_CLASS} ${NUM_CLASS} text-right font-medium align-top`}>
                      {headroom > 0 ? formatCr(headroom) : '—'}
                    </td>
                    <td className={`${TD_CLASS} max-w-md align-top`}>
                      {commentary && summary ? (
                        <CollapsibleDetail summary={summary}>
                          <DetailBlock label="Full rationale" text={commentary} />
                        </CollapsibleDetail>
                      ) : (
                        <span className="text-sm text-brand-muted">{summary ?? commentary ?? '—'}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {allSorted.length > 10 && (
          <p className="mt-2 text-xs text-brand-muted">
            Showing top 10 of {allSorted.length} categories by savings gap.
          </p>
        )}
      </CollapsiblePanel>
    </Card>
  );
};

interface ValueAtTableTableProps {
  rows: ValueAtTableRow[];
  totalP50Cr?: number;
  annualRevenueCr?: number;
  dataNote?: string;
  profileBasis?: string;
  percentileLegend?: Record<string, string>;
  methodology?: ValueAtTableMethodology;
}

function percentileLegendLine(legend?: Record<string, string>): string {
  if (!legend) {
    return 'P10 = conservative · P50 = expected · P90 = stretch';
  }
  const p10 = legend.p10 ? 'conservative' : 'P10';
  const p50 = legend.p50 ? 'expected' : 'P50';
  const p90 = legend.p90 ? 'stretch' : 'P90';
  return `P10 = ${p10} · P50 = ${p50} · P90 = ${p90}`;
}

export const ValueAtTableTable: React.FC<ValueAtTableTableProps> = ({
  rows,
  totalP50Cr,
  annualRevenueCr,
  dataNote,
  profileBasis,
  percentileLegend,
  methodology,
}) => {
  const legendLine = percentileLegendLine(percentileLegend);
  const { summary, steps, scopeNote } = valueAtTableMethodologyCopy(methodology);
  const methodologyPanelSummary = valueAtTableMethodologySummary(methodology);

  const showProxyDisclaimer = isBenchmarkProxyProfile(profileBasis);

  return (
    <Card title="Value at table" className="border-brand-border bg-white">
      {showProxyDisclaimer && (
        <BenchmarkProxyDisclaimer dataNote={dataNote} compact className="mb-4" />
      )}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <FactVsInferenceLabel kind="benchmark_proxy" />
        <span className="text-sm text-brand-muted">
          Sector lever model on synthetic spend pools · {legendLine}
        </span>
      </div>

      <DiagnosticValueBridge
        rows={rows}
        totalP50Cr={totalP50Cr}
        annualRevenueCr={annualRevenueCr}
        showProxyDisclaimer={showProxyDisclaimer}
      />

      <CollapsiblePanel title="How value at table is calculated" summary={methodologyPanelSummary}>
        <p className="text-sm text-brand-muted leading-relaxed">{summary}</p>
        <ol className="text-sm text-brand-muted space-y-1.5 list-decimal list-inside leading-relaxed mt-3">
          {steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
        {scopeNote && <p className="text-xs text-brand-muted mt-3">{scopeNote}</p>}
      </CollapsiblePanel>
    </Card>
  );
};

export function diagnosticTablesFromResult(result: DiagnosticResponse) {
  return {
    benchmarkGaps: (result.benchmark_gaps ?? []) as BenchmarkGapRow[],
    valueAtTable: (result.value_at_table ?? []) as ValueAtTableRow[],
    totalP50:
      result.total_p50_value_cr ??
      (result.value_at_table ?? []).reduce((sum, row) => {
        const v = Number(row.p50_cr ?? 0);
        return sum + (Number.isFinite(v) ? v : 0);
      }, 0),
  };
}
