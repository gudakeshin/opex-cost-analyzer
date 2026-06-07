import React from 'react';
import { DynamicChart } from './DynamicChart';
import type { ChartSpec } from '../../../types';

interface DynamicChartsProps {
  charts: ChartSpec[];
  currency: string;
}

/** Renders the LLM-suggested charts attached to an assistant message. */
export const DynamicCharts: React.FC<DynamicChartsProps> = ({ charts, currency }) => {
  const valid = charts.filter((c) => c && Array.isArray(c.data) && c.data.length > 0 && c.series?.length > 0);
  if (valid.length === 0) return null;

  return (
    <div className="mt-3 space-y-4 border-t border-brand-border pt-3">
      <p className="text-[10px] uppercase font-semibold text-brand-muted tracking-wide">Charts</p>
      {valid.map((spec) => (
        <div key={spec.id}>
          <p className="text-[11px] font-semibold text-brand-ink mb-0.5">{spec.title}</p>
          {spec.rationale && (
            <p className="text-[10px] text-brand-muted mb-2 italic">{spec.rationale}</p>
          )}
          <div className="rounded-xl bg-white border border-brand-border p-2">
            <DynamicChart spec={spec} currency={currency} />
          </div>
        </div>
      ))}
    </div>
  );
};
