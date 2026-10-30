import React, { useMemo } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Loader } from '../../Common/Loader';
import { formatAmount, truncationCaption } from './fpaHelpers';
import type { TrendsResponse } from '../../../types';

const CATEGORY_ROW_LIMIT = 8;

interface TrendsTabProps {
  data: TrendsResponse | null;
  loading: boolean;
  error: string | null;
  currency?: string;
}

export const TrendsTab: React.FC<TrendsTabProps> = ({ data, loading, error, currency = 'INR' }) => {
  const chartData = useMemo(
    () =>
      (data?.period_trends ?? []).map((row) => ({
        period: row.period ?? '',
        spend: Number(row.total_spend ?? row.spend ?? 0),
      })),
    [data],
  );

  const allCategoryTrends = useMemo(() => data?.category_trends ?? [], [data]);
  const categoryTrends = useMemo(
    () => allCategoryTrends.slice(0, CATEGORY_ROW_LIMIT),
    [allCategoryTrends],
  );

  if (loading) return <Loader label="Loading trends…" />;
  if (error) return <p className="text-error text-sm">{error}</p>;
  if (!data) return <p className="text-gray-500 text-sm">Run analysis with a session to view trends.</p>;

  if (!data.temporal_available) {
    return (
      <p className="text-sm text-brand-muted">
        {data.reason ?? 'Temporal analysis not available for this session.'}
      </p>
    );
  }

  return (
    <div className="space-y-6 min-w-0">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Metric label="Periods" value={String(data.period_count ?? '—')} />
        <Metric label="ARR basis" value={String(data.arr_basis ?? '—')} />
        <Metric label="Annualized run rate" value={formatAmount(data.annualized_run_rate, currency)} />
        <Metric label="CAGR" value={data.cagr_pct != null ? `${data.cagr_pct}%` : '—'} />
      </div>

      {chartData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-brand-ink mb-2">Spend over time</h3>
          <div className="h-56 w-full min-w-0 overflow-hidden">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E7E6E6" />
                <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => formatAmount(v, currency)} width={72} />
                <Tooltip formatter={(v: number) => formatAmount(v, currency)} />
                <Line type="monotone" dataKey="spend" stroke="#003F7F" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {categoryTrends.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-brand-ink mb-2">Category trends</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-brand-border text-left text-brand-muted">
                  <th className="py-2 pr-3">Category</th>
                  <th className="py-2 pr-3">Direction</th>
                  <th className="py-2 pr-3">Change</th>
                  <th className="py-2 pr-3">CAGR</th>
                  <th className="py-2">Run rate</th>
                </tr>
              </thead>
              <tbody>
                {categoryTrends.map((row) => (
                  <tr key={String(row.category_id ?? row.category_name)} className="border-b border-brand-border/60">
                    <td className="py-2 pr-3 font-medium text-brand-ink">{row.category_name ?? row.category_id}</td>
                    <td className="py-2 pr-3 capitalize">{row.trend_direction ?? '—'}</td>
                    <td className="py-2 pr-3 tabular-nums">
                      {row.change_pct != null ? `${row.change_pct}%` : formatAmount(row.total_change, currency)}
                    </td>
                    <td className="py-2 pr-3 tabular-nums">{row.cagr_pct != null ? `${row.cagr_pct}%` : '—'}</td>
                    <td className="py-2 tabular-nums">{formatAmount(row.annualized_run_rate, currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {truncationCaption(categoryTrends.length, allCategoryTrends.length) && (
            <p className="mt-1 text-xs text-brand-muted">
              {truncationCaption(categoryTrends.length, allCategoryTrends.length)}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-3 rounded-lg bg-brand-surface-muted border border-brand-border">
      <p className="text-xs text-brand-muted">{label}</p>
      <p className="text-sm font-semibold text-brand-ink tabular-nums">{value}</p>
    </div>
  );
}
