import React, { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Loader } from '../../Common/Loader';
import { formatAmount, truncationCaption } from './fpaHelpers';
import type { CostToServeResponse } from '../../../types';

const CHART_BAR_LIMIT = 8;

interface CostToServeTabProps {
  data: CostToServeResponse | null;
  loading: boolean;
  error: string | null;
  currency?: string;
}

export const CostToServeTab: React.FC<CostToServeTabProps> = ({ data, loading, error, currency = 'INR' }) => {
  const drivers = useMemo(() => data?.top_cost_drivers ?? [], [data]);

  const chartData = useMemo(
    () =>
      drivers.slice(0, CHART_BAR_LIMIT).map((d) => ({
        name: String(d.category_name ?? d.category_id ?? '—').slice(0, 16),
        spend: Number(d.spend ?? 0),
        pct: Number(d.pct_of_opex ?? 0),
      })),
    [drivers],
  );

  if (loading) return <Loader label="Computing cost-to-serve…" />;
  if (error) return <p className="text-error text-sm">{error}</p>;
  if (!data) return <p className="text-sm text-brand-muted">No cost-to-serve data. Run full analysis first.</p>;

  if (!data.cost_to_serve_available) {
    return (
      <p className="text-sm text-brand-muted">
        {data.reason ?? 'Cost-to-serve analysis not available.'}
      </p>
    );
  }

  const cpe = data.cost_per_employee;

  return (
    <div className="space-y-6 min-w-0">
      {data.reason && (
        <p className="text-sm text-brand-muted">{data.reason}</p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {cpe && (
          <Metric label="Cost per employee" value={formatAmount(cpe.total, currency)} />
        )}
        <Metric label="Opex allocated" value={formatAmount(data.total_opex_allocated, currency)} />
        <Metric label="Opex unallocated" value={formatAmount(data.total_opex_unallocated, currency)} />
      </div>

      {chartData.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-brand-ink mb-2">Top cost drivers</h3>
          {truncationCaption(chartData.length, drivers.length) && (
            <p className="mb-2 text-xs text-brand-muted">
              {truncationCaption(chartData.length, drivers.length)}
            </p>
          )}
          <div className="h-56 w-full min-w-0 overflow-hidden">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 16, left: 4, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E7E6E6" />
                <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-30} textAnchor="end" height={50} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => formatAmount(v, currency)} width={72} />
                <Tooltip formatter={(v: number) => formatAmount(v, currency)} />
                <Bar dataKey="spend" fill="#003F7F" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {drivers.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-brand-border text-left text-brand-muted">
                <th className="py-2 pr-3">Category</th>
                <th className="py-2 pr-3">Spend</th>
                <th className="py-2">% of OpEx</th>
              </tr>
            </thead>
            <tbody>
              {drivers.map((d) => (
                <tr key={String(d.category_id ?? d.category_name)} className="border-b border-brand-border/60">
                  <td className="py-2 pr-3 font-medium">{d.category_name ?? d.category_id}</td>
                  <td className="py-2 pr-3 tabular-nums">{formatAmount(d.spend, currency)}</td>
                  <td className="py-2 tabular-nums">{d.pct_of_opex != null ? `${d.pct_of_opex}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
