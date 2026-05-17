import React from 'react';
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatCr } from '../../../utils/formatInr';

const BRAND = {
  navy: '#003F7F',
  green: '#86BC25',
  muted: '#6B7280',
  border: '#E7E6E6',
};

interface ValueBridgeChartProps {
  portfolioP50Cr: number;
  committedP50Cr: number;
  ebitdaBps: number;
}

export const ValueBridgeChart: React.FC<ValueBridgeChartProps> = ({
  portfolioP50Cr,
  committedP50Cr,
  ebitdaBps,
}) => {
  const data = [
    { name: 'Portfolio P50', value: portfolioP50Cr, fill: BRAND.navy },
    { name: 'Committed', value: committedP50Cr, fill: BRAND.green },
    {
      name: 'EBITDA bps',
      value: Math.max(ebitdaBps / 10, 0.1),
      fill: BRAND.muted,
      display: `${ebitdaBps} bps`,
    },
  ];

  return (
    <div className="h-48 w-full" aria-label="Value bridge chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 8, top: 4, bottom: 4 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="name"
            width={100}
            tick={{ fontSize: 11, fill: BRAND.muted }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            formatter={(value: number, _name, item) => {
              const payload = item?.payload as { display?: string; name: string };
              if (payload?.display) return [payload.display, payload.name];
              return [formatCr(value), payload?.name ?? ''];
            }}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <table className="sr-only">
        <caption>Value bridge</caption>
        <tbody>
          {data.map((row) => (
            <tr key={row.name}>
              <th scope="row">{row.name}</th>
              <td>{row.display ?? formatCr(row.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
