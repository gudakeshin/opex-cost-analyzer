import React from 'react';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import { SpendCharts } from './SpendCharts';
import { formatSpendAmount } from '../../../utils/analysisInsights';
import type { AnalysisInsightSnapshot } from '../../../types';

interface ChatInsightBlockProps {
  snapshot: AnalysisInsightSnapshot;
  showPeerSavings?: boolean;
}

export const ChatInsightBlock: React.FC<ChatInsightBlockProps> = ({
  snapshot,
  showPeerSavings = false,
}) => {
  const { reporting_currency: currency, top_categories: topCategories } = snapshot;

  if (snapshot.total_spend <= 0 && topCategories.length === 0) {
    return (
      <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5 mt-2">
        Spend totals are zero — check that the amount column was mapped correctly on upload.
      </p>
    );
  }

  return (
    <div className="mt-3 space-y-3 border-t border-brand-border pt-3">
      <div className="flex items-center gap-2">
        <FactVsInferenceLabel kind="fact" />
        <p className="text-xs font-semibold uppercase text-brand-muted">Spend insights</p>
      </div>

      {snapshot.total_spend > 0 && (
        <div className="rounded-xl bg-brand-surface-muted border border-brand-border px-3 py-2.5">
          <p className="text-[10px] uppercase font-semibold text-brand-muted">Total spend (signal)</p>
          <p className="text-lg font-bold text-brand-ink tabular-nums">
            {formatSpendAmount(snapshot.total_spend, currency)}
          </p>
          {snapshot.line_count != null && snapshot.line_count > 0 && (
            <p className="text-[10px] text-brand-muted mt-0.5">
              {snapshot.line_count.toLocaleString()} transaction lines
            </p>
          )}
        </div>
      )}

      {snapshot.chart_data ? (
        <SpendCharts chartData={snapshot.chart_data} currency={currency} />
      ) : topCategories.length > 0 ? (
        <div>
          <p className="text-[10px] font-semibold uppercase text-brand-muted mb-1.5">
            Spend concentration
          </p>
          <ul className="text-xs space-y-1.5">
            {topCategories.map((cat) => {
              const share =
                cat.share_of_total > 0
                  ? `${(cat.share_of_total * 100).toFixed(1)}%`
                  : '—';
              return (
                <li key={cat.category_id} className="flex justify-between gap-2">
                  <span className="text-brand-ink truncate">{cat.category_name}</span>
                  <span className="text-brand-muted shrink-0 tabular-nums">{share}</span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {snapshot.ingestion_note && (
        <p className="text-[10px] text-brand-muted bg-brand-surface-muted rounded-lg px-2 py-1.5 border border-brand-border">
          {snapshot.ingestion_note}
        </p>
      )}

      {showPeerSavings && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {(snapshot.peer_comparison_count ?? 0) > 0 && (
            <div className="rounded-lg border border-brand-border px-2.5 py-2">
              <p className="text-[10px] uppercase font-semibold text-brand-muted">Peer gaps (P75+)</p>
              <p className="text-sm font-bold text-brand-ink">
                {snapshot.peer_gap_count ?? 0}
                <span className="text-xs font-normal text-brand-muted">
                  {' '}
                  / {snapshot.peer_comparison_count} categories
                </span>
              </p>
            </div>
          )}
          {snapshot.savings_headline && (
            <div className="rounded-lg border border-brand-border px-2.5 py-2">
              <p className="text-[10px] uppercase font-semibold text-brand-muted">Top savings signal</p>
              <p className="text-sm font-bold text-deloitte-green">{snapshot.savings_headline}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
