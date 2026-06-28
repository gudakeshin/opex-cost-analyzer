import React, { useMemo } from 'react';
import { Loader } from '../../Common/Loader';
import { formatAmount } from './fpaHelpers';
import type { PaymentTermsResponse } from '../../../types';

interface PaymentTermsTabProps {
  data: PaymentTermsResponse | null;
  loading: boolean;
  error: string | null;
  currency?: string;
}

export const PaymentTermsTab: React.FC<PaymentTermsTabProps> = ({ data, loading, error, currency = 'INR' }) => {
  const opportunities = useMemo(() => data?.opportunities ?? [], [data]);

  if (loading) return <Loader label="Loading payment terms…" />;
  if (error) return <p className="text-error text-sm">{error}</p>;
  if (!data) return <p className="text-gray-500 text-sm">No payment terms analysis for this session.</p>;

  if (!data.payment_terms_available) {
    return (
      <p className="text-sm text-brand-muted">
        {data.reason ?? 'Payment terms analysis not available — add a Payment Terms column to spend data.'}
      </p>
    );
  }

  return (
    <div className="space-y-6 min-w-0">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Metric label="WC release" value={formatAmount(data.total_working_capital_release, currency)} />
        <Metric label="Annual cash value" value={formatAmount(data.total_annual_cash_value, currency)} />
        <Metric label="Opportunities" value={String(data.opportunity_count ?? opportunities.length)} />
        <Metric label="Terms coverage" value={data.coverage_pct != null ? `${data.coverage_pct}%` : '—'} />
      </div>

      {opportunities.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-brand-border text-left text-brand-muted">
                <th className="py-2 pr-3">Category</th>
                <th className="py-2 pr-3">Current DPO</th>
                <th className="py-2 pr-3">Target DPO</th>
                <th className="py-2 pr-3">WC release</th>
                <th className="py-2">Annual value</th>
              </tr>
            </thead>
            <tbody>
              {opportunities.map((row) => (
                <tr key={String(row.category_id ?? row.category_name)} className="border-b border-brand-border/60">
                  <td className="py-2 pr-3 font-medium">{row.category_name ?? row.category_id}</td>
                  <td className="py-2 pr-3 tabular-nums">{row.current_dpo_days ?? '—'}d</td>
                  <td className="py-2 pr-3 tabular-nums">{row.target_dpo_days ?? '—'}d</td>
                  <td className="py-2 pr-3 tabular-nums">
                    {formatAmount(row.working_capital_release, currency)}
                  </td>
                  <td className="py-2 tabular-nums">
                    {formatAmount(row.annual_cash_value_at_wacc, currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-brand-muted">No DPO extension opportunities identified.</p>
      )}

      {data.note && <p className="text-xs text-brand-muted">{data.note}</p>}
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
