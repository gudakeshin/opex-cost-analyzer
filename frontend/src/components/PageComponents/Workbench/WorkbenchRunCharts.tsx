import React from 'react';
import { formatCr } from '../../../utils/formatInr';
import { ValueBridgeChart } from '../CostRoom/ValueBridgeChart';
import type { WorkbenchRun } from '../../../types';

interface WorkbenchRunChartsProps {
  run: WorkbenchRun;
  currency: string;
}

export const WorkbenchRunCharts: React.FC<WorkbenchRunChartsProps> = ({ run, currency }) => {
  const outputs = run.skill_outputs || {};
  const bridge = outputs['value-bridge-calculator'] as Record<string, unknown> | undefined;
  const bench = outputs['peer-benchmarker'] as Record<string, unknown> | undefined;
  const savings = outputs['savings-modeler'] as Record<string, unknown> | undefined;
  const gaps = (bench?.benchmark_gaps || bench?.gaps) as Record<string, unknown>[] | undefined;
  const inits = savings?.initiatives as Record<string, unknown>[] | undefined;

  const bands = bridge?.confidence_bands as Record<string, number> | undefined;
  const summary = savings?.summary as Record<string, number> | undefined;

  return (
    <div className="space-y-4">
      {bench?.benchmark_source != null && (
        <p className="text-xs text-brand-muted">
          Benchmark source: <span className="text-brand-ink">{String(bench.benchmark_source)}</span>
        </p>
      )}

      {bands && (
        <div>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Value bridge</h4>
          <ValueBridgeChart
            portfolioP50Cr={Number(bands.mid || 0)}
            committedP50Cr={Number(bands.low || 0)}
            ebitdaBps={Number(summary?.portfolio_ebitda_impact_bps || run.headline?.ebitda_bps || 0)}
            currency={currency}
          />
        </div>
      )}

      {Array.isArray(gaps) && gaps.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Benchmark gaps</h4>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-brand-border text-brand-muted">
                <th className="text-left py-1">Category</th>
                <th className="text-right py-1">Gap to P50</th>
              </tr>
            </thead>
            <tbody>
              {gaps.slice(0, 8).map((g, i) => (
                <tr key={i} className="border-b border-brand-border/50">
                  <td className="py-1 text-brand-ink">{String(g.category_name || g.category_id || '—')}</td>
                  <td className="py-1 text-right tabular-nums">
                    {g.gap_to_p50_cr != null
                      ? formatCr(Number(g.gap_to_p50_cr), { currency })
                      : g.gap_pct != null
                        ? `${Number(g.gap_pct).toFixed(1)}%`
                        : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Array.isArray(inits) && inits.length > 0 && (
        <div>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Initiatives</h4>
          <ul className="text-xs space-y-1">
            {inits.slice(0, 6).map((item, i) => (
              <li key={i} className="flex justify-between gap-2">
                <span className="text-brand-ink truncate">{String(item.category || item.lever || `Initiative ${i + 1}`)}</span>
                <span className="text-brand-muted shrink-0 tabular-nums">
                  {formatCr(Number((item.net_savings as Record<string, number>)?.npv_aftertax || 0), { currency })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {!bands && !gaps?.length && !inits?.length && (
        <p className="text-sm text-brand-muted">No chartable outputs in this run. Try including peer-benchmarker, savings-modeler, or value-bridge-calculator.</p>
      )}
    </div>
  );
};
