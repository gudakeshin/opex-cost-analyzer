import React from 'react';
import { formatSpendAmount } from '../../../utils/analysisInsights';
import type { CategoryInsightData } from '../../../types';

interface CategoryInsightCardProps {
  data: CategoryInsightData;
  currency?: string;
}

export const CategoryInsightCard: React.FC<CategoryInsightCardProps> = ({ data, currency = 'INR' }) => {
  const fmt = (v: number | null | undefined) =>
    v != null && v > 0 ? formatSpendAmount(v, currency) : '—';

  return (
    <div className="rounded-lg border border-brand-border bg-brand-surface-muted/40 p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-xs font-bold text-brand-navy">{data.category_name}</h4>
        {data.benchmark_gap && (
          <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-800 bg-amber-50 px-1.5 py-0.5 rounded">
            {data.benchmark_gap}
          </span>
        )}
      </div>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <div>
          <dt className="text-brand-muted">Spend</dt>
          <dd className="font-medium tabular-nums">{fmt(data.spend)}</dd>
        </div>
        {data.spend_pct_revenue != null && (
          <div>
            <dt className="text-brand-muted">% revenue</dt>
            <dd className="font-medium tabular-nums">{data.spend_pct_revenue.toFixed(2)}%</dd>
          </div>
        )}
        {data.addressable_gap != null && data.addressable_gap > 0 && (
          <div>
            <dt className="text-brand-muted">Addressable</dt>
            <dd className="font-medium tabular-nums">{fmt(data.addressable_gap)}</dd>
          </div>
        )}
        {data.concentration_hhi != null && (
          <div>
            <dt className="text-brand-muted">HHI</dt>
            <dd className="font-medium tabular-nums">{data.concentration_hhi.toFixed(2)}</dd>
          </div>
        )}
      </dl>
      {data.top_suppliers && data.top_suppliers.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase text-brand-muted mb-1">Top suppliers</p>
          <ul className="text-[11px] space-y-0.5">
            {data.top_suppliers.map((s) => (
              <li key={s.supplier} className="flex justify-between gap-2">
                <span className="truncate">{s.supplier}</span>
                <span className="text-brand-muted shrink-0 tabular-nums">{fmt(s.spend)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {data.suggested_actions && data.suggested_actions.length > 0 && (
        <ul className="text-[11px] list-disc list-inside text-brand-muted space-y-0.5">
          {data.suggested_actions.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
    </div>
  );
};
