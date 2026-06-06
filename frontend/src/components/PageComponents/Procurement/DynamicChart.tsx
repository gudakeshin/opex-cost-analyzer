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
  PieChart,
  Pie,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';
import { formatSpendAmount } from '../../../utils/analysisInsights';
import type { ChartSpec, ChartSeries, ChartUnit } from '../../../types';

const GREEN = '#86BC25';
const GRAY = '#53565A';
const GRAY_LIGHT = '#BBBCBC';
const AMBER = '#D97706';
const NAVY = '#2C5282';

// Cycling palette for single-series categorical charts (bar / pie).
const PALETTE = [GREEN, NAVY, AMBER, GRAY, '#0F9D9D', '#9B59B6', '#E0792B', GRAY_LIGHT];

function truncate(s: string, max = 18): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function makeFormatter(unit: ChartUnit, currency: string) {
  return (v: number): string => {
    if (v == null || Number.isNaN(v)) return '—';
    switch (unit) {
      case 'currency':
        return formatSpendAmount(v, currency);
      case 'percent':
        return `${v.toFixed(1)}%`;
      case 'days':
        return `${Math.round(v)}d`;
      case 'ratio':
        return v.toFixed(2);
      default:
        return Math.round(v).toLocaleString();
    }
  };
}

interface DynamicChartProps {
  spec: ChartSpec;
  currency: string;
}

function CategoryTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  if (x == null || y == null || !payload) return null;
  return (
    <text x={x} y={y} dy={4} textAnchor="end" fontSize={10} fill={GRAY}>
      {truncate(String(payload.value), 16)}
    </text>
  );
}

/** Builds a Recharts waterfall from rows of { [x_key]: label, value, is_total? }. */
function buildWaterfall(spec: ChartSpec) {
  const valueKey = spec.series[0]?.key ?? 'value';
  let running = 0;
  return spec.data.map((row) => {
    const label = String(row[spec.x_key] ?? '');
    const value = Number(row[valueKey] ?? 0);
    const isTotal = Boolean(row.is_total);
    if (isTotal) {
      running = value;
      return { label, base: 0, bar: value, display: value, color: GRAY };
    }
    const start = running;
    const end = running + value;
    running = end;
    return {
      label,
      base: Math.min(start, end),
      bar: Math.abs(value),
      display: value,
      color: value >= 0 ? GREEN : AMBER,
    };
  });
}

export const DynamicChart: React.FC<DynamicChartProps> = ({ spec, currency }) => {
  const fmt = makeFormatter(spec.unit, currency);
  const { type, series, x_key: xKey, data } = spec;

  if (!data || data.length === 0) return null;

  const tooltipStyle = { fontSize: 11, borderRadius: 8, border: '1px solid #E0E0E0' };
  const axisTick = { fontSize: 9, fill: GRAY } as const;

  // ----- Waterfall -----
  if (type === 'waterfall') {
    const wf = buildWaterfall(spec);
    return (
      <ResponsiveContainer width="100%" height={Math.max(180, wf.length * 30 + 30)}>
        <BarChart data={wf} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" vertical={false} />
          <XAxis dataKey="label" tick={axisTick} interval={0} angle={-20} textAnchor="end" height={48} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={fmt} tick={axisTick} width={60} axisLine={false} tickLine={false} />
          <Tooltip formatter={(_v, _n, p) => [fmt(Number((p?.payload as { display?: number })?.display ?? 0)), spec.series[0]?.name ?? 'Value']} contentStyle={tooltipStyle} />
          <Bar dataKey="base" stackId="w" fill="transparent" />
          <Bar dataKey="bar" stackId="w" radius={[4, 4, 0, 0]} maxBarSize={48}>
            {wf.map((r, i) => (
              <Cell key={i} fill={r.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ----- Pie / Donut -----
  if (type === 'pie') {
    const valueKey = series[0]?.key ?? 'value';
    const pieData = data.map((row) => ({
      name: String(row[xKey] ?? ''),
      value: Number(row[valueKey] ?? 0),
    }));
    return (
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} innerRadius={42}>
            {pieData.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip formatter={(v: number, n: string) => [fmt(v), n]} contentStyle={tooltipStyle} />
          <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  // ----- Line -----
  if (type === 'line') {
    return (
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
          <XAxis dataKey={xKey} tick={axisTick} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={fmt} tick={axisTick} width={60} axisLine={false} tickLine={false} />
          <Tooltip formatter={(v: number, n: string) => [fmt(v), n]} contentStyle={tooltipStyle} />
          {series.length > 1 && <Legend iconSize={8} wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />}
          {series.map((s: ChartSeries, i) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color ?? PALETTE[i % PALETTE.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  }

  // ----- Horizontal bar (hbar) -----
  if (type === 'hbar') {
    const stacked = false;
    return (
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 30 + 24)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#E0E0E0" />
          <XAxis type="number" tickFormatter={fmt} tick={axisTick} axisLine={false} tickLine={false} />
          <YAxis type="category" dataKey={xKey} width={112} tick={<CategoryTick />} axisLine={false} tickLine={false} />
          <Tooltip formatter={(v: number, n: string) => [fmt(v), n]} contentStyle={tooltipStyle} />
          {series.length > 1 && <Legend iconSize={8} wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />}
          {series.map((s: ChartSeries, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.name}
              stackId={stacked ? 'a' : undefined}
              fill={s.color ?? PALETTE[i % PALETTE.length]}
              radius={[0, 4, 4, 0]}
              maxBarSize={20}
            >
              {series.length === 1 &&
                data.map((_, idx) => <Cell key={idx} fill={s.color ?? PALETTE[idx % PALETTE.length]} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  // ----- Vertical bar (bar / grouped_bar / stacked_bar) -----
  const stacked = type === 'stacked_bar';
  return (
    <ResponsiveContainer width="100%" height={210}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" vertical={false} />
        <XAxis dataKey={xKey} tick={axisTick} interval={0} angle={data.length > 5 ? -20 : 0} textAnchor={data.length > 5 ? 'end' : 'middle'} height={data.length > 5 ? 48 : 24} axisLine={false} tickLine={false} />
        <YAxis tickFormatter={fmt} tick={axisTick} width={60} axisLine={false} tickLine={false} />
        <Tooltip formatter={(v: number, n: string) => [fmt(v), n]} contentStyle={tooltipStyle} />
        {series.length > 1 && <Legend iconSize={8} wrapperStyle={{ fontSize: 10, paddingTop: 4 }} />}
        {series.map((s: ChartSeries, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.name}
            stackId={stacked ? 'a' : undefined}
            fill={s.color ?? PALETTE[i % PALETTE.length]}
            radius={stacked ? [0, 0, 0, 0] : [4, 4, 0, 0]}
            maxBarSize={36}
          >
            {series.length === 1 &&
              data.map((_, idx) => <Cell key={idx} fill={s.color ?? PALETTE[idx % PALETTE.length]} />)}
          </Bar>
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
};
