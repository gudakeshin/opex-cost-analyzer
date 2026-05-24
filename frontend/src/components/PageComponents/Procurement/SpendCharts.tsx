import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  LineChart,
  Line,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';
import { formatSpendAmount } from '../../../utils/analysisInsights';
import type { SpendChartData } from '../../../types';

const GREEN = '#86BC25';
const GRAY = '#53565A';
const GRAY_LIGHT = '#BBBCBC';
const SURFACE = '#F7F7F5';

function truncate(s: string, max = 20): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

interface ChartProps {
  data: SpendChartData;
  currency: string;
}

function SpendTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  if (x == null || y == null || !payload) return null;
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={10} fill={GRAY}>
      {truncate(payload.value, 18)}
    </text>
  );
}

function CategorySpendChart({ data, currency }: ChartProps) {
  const rows = data.category_rows.slice(0, 7).reverse();
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, rows.length * 28 + 20)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E0E0E0" />
        <XAxis
          type="number"
          tickFormatter={(v: number) => formatSpendAmount(v, currency)}
          tick={{ fontSize: 9, fill: GRAY }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="category_name"
          width={110}
          tick={<SpendTick />}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          formatter={(value: number) => [formatSpendAmount(value, currency), 'Spend']}
          contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #E0E0E0' }}
        />
        <Bar dataKey="spend" radius={[0, 4, 4, 0]} maxBarSize={18}>
          {rows.map((_, i) => (
            <Cell key={i} fill={i === rows.length - 1 ? GREEN : `${GREEN}${Math.round(180 - i * 18).toString(16).padStart(2, '0')}`} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function AddressabilityChart({ data, currency }: ChartProps) {
  const rows = data.category_rows.slice(0, 6).reverse();
  const chartRows = rows.map((r) => ({
    category_name: r.category_name,
    Addressable: r.addressable_spend,
    'Semi-variable': r.semi_variable_spend,
    Fixed: r.fixed_spend,
  }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, rows.length * 30 + 36)}>
      <BarChart data={chartRows} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E0E0E0" />
        <XAxis
          type="number"
          tickFormatter={(v: number) => formatSpendAmount(v, currency)}
          tick={{ fontSize: 9, fill: GRAY }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="category_name"
          width={110}
          tick={<SpendTick />}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          formatter={(value: number, name: string) => [formatSpendAmount(value, currency), name]}
          contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #E0E0E0' }}
        />
        <Legend iconSize={8} wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />
        <Bar dataKey="Addressable" stackId="a" fill={GREEN} radius={[0, 0, 0, 0]} maxBarSize={16} />
        <Bar dataKey="Semi-variable" stackId="a" fill={GRAY} maxBarSize={16} />
        <Bar dataKey="Fixed" stackId="a" fill={GRAY_LIGHT} radius={[0, 4, 4, 0]} maxBarSize={16} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function SpendTrendChart({ data, currency }: ChartProps) {
  if (data.period_totals.length < 2) return null;
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data.period_totals} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
        <XAxis
          dataKey="period"
          tick={{ fontSize: 9, fill: GRAY }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tickFormatter={(v: number) => formatSpendAmount(v, currency)}
          tick={{ fontSize: 9, fill: GRAY }}
          axisLine={false}
          tickLine={false}
          width={60}
        />
        <Tooltip
          formatter={(value: number) => [formatSpendAmount(value, currency), 'Total spend']}
          contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #E0E0E0' }}
        />
        <Line
          type="monotone"
          dataKey="spend"
          stroke={GREEN}
          strokeWidth={2}
          dot={{ fill: GREEN, r: 3 }}
          activeDot={{ r: 5 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

interface SpendChartsProps {
  chartData: SpendChartData;
  currency: string;
}

const CHART_LABELS: Record<string, string> = {
  pareto_spend: 'Spend concentration (Pareto)',
  ranked_bar_spend: 'Spend by category',
  stacked_addressability: 'Addressability breakdown',
  trend_line_total_spend: 'Spend trend over time',
};

export const SpendCharts: React.FC<SpendChartsProps> = ({ chartData, currency }) => {
  const charts = chartData.selected_charts.length > 0
    ? chartData.selected_charts
    : chartData.category_rows.length > 0
      ? [{ chart: 'ranked_bar_spend', reason: '' }]
      : [];

  return (
    <div className="mt-3 space-y-4 border-t border-brand-border pt-3">
      {charts.map(({ chart, reason }) => {
        let chartEl: React.ReactNode = null;

        if (chart === 'pareto_spend' || chart === 'ranked_bar_spend') {
          if (chartData.category_rows.length === 0) return null;
          chartEl = <CategorySpendChart data={chartData} currency={currency} />;
        } else if (chart === 'stacked_addressability') {
          if (chartData.category_rows.length === 0) return null;
          chartEl = <AddressabilityChart data={chartData} currency={currency} />;
        } else if (chart === 'trend_line_total_spend') {
          if (chartData.period_totals.length < 2) return null;
          chartEl = <SpendTrendChart data={chartData} currency={currency} />;
        }

        if (!chartEl) return null;

        return (
          <div key={chart}>
            <p className="text-[10px] uppercase font-semibold text-brand-muted mb-1">
              {CHART_LABELS[chart] ?? chart.replace(/_/g, ' ')}
            </p>
            {reason && (
              <p className="text-[10px] text-brand-muted mb-2 italic">{reason}</p>
            )}
            <div className="rounded-xl bg-white border border-brand-border p-2">
              {chartEl}
            </div>
          </div>
        );
      })}

      {chartData.commentary_points.length > 0 && (
        <div className="rounded-xl bg-brand-surface-muted border border-brand-border px-3 py-2.5">
          <p className="text-[10px] uppercase font-semibold text-brand-muted mb-1.5">AI analysis</p>
          <ul className="space-y-1">
            {chartData.commentary_points.map((point, i) => (
              <li key={i} className="text-xs text-brand-ink leading-relaxed flex gap-1.5">
                <span className="text-deloitte-green shrink-0 mt-0.5">›</span>
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

interface MiniCategoryBarProps {
  chartData: SpendChartData;
  currency: string;
}

export const MiniCategoryBar: React.FC<MiniCategoryBarProps> = ({ chartData, currency }) => {
  const rows = chartData.category_rows.slice(0, 5).reverse();
  if (rows.length === 0) return null;
  return (
    <div className="rounded-lg border border-brand-border bg-white p-2">
      <ResponsiveContainer width="100%" height={Math.max(100, rows.length * 22)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 2, right: 8, left: 2, bottom: 2 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="category_name"
            width={90}
            tick={<SpendTick />}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            formatter={(value: number) => [formatSpendAmount(value, currency), 'Spend']}
            contentStyle={{ fontSize: 10, borderRadius: 6, border: '1px solid #E0E0E0', background: SURFACE }}
          />
          <Bar dataKey="spend" fill={GREEN} radius={[0, 3, 3, 0]} maxBarSize={14} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};
