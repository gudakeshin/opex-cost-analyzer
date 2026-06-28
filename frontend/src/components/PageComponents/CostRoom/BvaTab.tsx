import React, { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Loader } from '../../Common/Loader';
import { formatAmount, truncationCaption } from './fpaHelpers';
import type { BvaResponse } from '../../../types';

const CHART_BAR_LIMIT = 10;

interface BvaTabProps {
  data: BvaResponse | null;
  loading: boolean;
  error: string | null;
  currency?: string;
}

export const BvaTab: React.FC<BvaTabProps> = ({ data, loading, error, currency = 'INR' }) => {
  const variances = useMemo(() => data?.variances ?? [], [data]);

  const chartData = useMemo(
    () =>
      variances.slice(0, CHART_BAR_LIMIT).map((v) => ({
        name: String(v.category_name ?? v.category_id ?? '—').slice(0, 18),
        variance: Number(v.total_variance ?? 0),
        flag: v.flag ?? '',
      })),
    [variances],
  );

  if (loading) return <Loader label="Loading budget vs actuals…" />;
  if (error) return <p className="text-error text-sm">{error}</p>;
  if (!data) return <p className="text-gray-500 text-sm">No BvA data for this session.</p>;

  if (!data.bva_available) {
    return (
      <p className="text-sm text-brand-muted">
        {data.reason ?? 'Budget vs actuals not available — upload budget lines in your spend file.'}
      </p>
    );
  }

  return (
    <div className="space-y-6 min-w-0">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Metric label="Total actual" value={formatAmount(data.total_actual, currency)} />
        <Metric label="Total budget" value={formatAmount(data.total_budget, currency)} />
        <Metric label="Variance" value={formatAmount(data.total_variance, currency)} />
        <Metric
          label="Over budget"
          value={String(data.categories_over_budget ?? 0)}
        />
      </div>

      {chartData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-brand-ink mb-2">Top variances by category</h3>
          {truncationCaption(chartData.length, variances.length) && (
            <p className="mb-2 text-xs text-brand-muted">
              {truncationCaption(chartData.length, variances.length)}
            </p>
          )}
          <div className="h-56 w-full min-w-0 overflow-hidden">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E7E6E6" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={(v) => formatAmount(v, currency)} />
                <YAxis type="category" dataKey="name" width={100} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v: number) => formatAmount(v, currency)} />
                <Bar dataKey="variance" radius={[0, 4, 4, 0]} barSize={16}>
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={entry.variance > 0 ? '#DC2626' : entry.variance < 0 ? '#86BC25' : '#6B7280'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {variances.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-brand-border text-left text-brand-muted">
                <th className="py-2 pr-3">Category</th>
                <th className="py-2 pr-3">Actual</th>
                <th className="py-2 pr-3">Budget</th>
                <th className="py-2 pr-3">Variance</th>
                <th className="py-2">Flag</th>
              </tr>
            </thead>
            <tbody>
              {variances.map((v) => (
                <tr key={String(v.category_id ?? v.category_name)} className="border-b border-brand-border/60">
                  <td className="py-2 pr-3 font-medium">{v.category_name ?? v.category_id}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatAmount(v.actual_spend, currency)}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatAmount(v.budget_spend, currency)}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatAmount(v.total_variance, currency)}</td>
                  <td className="py-2 capitalize">{(v.flag ?? '—').replace(/_/g, ' ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.decomposition_note && (
        <p className="text-xs text-brand-muted">{data.decomposition_note}</p>
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
