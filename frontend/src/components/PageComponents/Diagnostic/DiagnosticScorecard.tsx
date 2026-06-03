import React from 'react';
import { MetricTile } from '../../Common/MetricTile';
import type { DiagnosticResponse } from '../../../types';

interface DiagnosticScorecardProps {
  result: DiagnosticResponse;
}

export const DiagnosticScorecard: React.FC<DiagnosticScorecardProps> = ({ result }) => {
  const gapCount = result.benchmark_gaps?.length ?? 0;
  const valueRows = result.value_at_table?.length ?? 0;
  const totalP50 =
    result.total_p50_value_cr ??
    (result.value_at_table ?? []).reduce((sum, row) => {
      const v = Number(row.p50_cr ?? 0);
      return sum + (Number.isFinite(v) ? v : 0);
    }, 0);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <MetricTile
        label="Value at table (P50)"
        value={`₹${totalP50.toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr`}
        highlight
      />
      <MetricTile label="Benchmark gaps" value={String(gapCount)} change="Top material gaps ranked below" />
      <MetricTile
        label="Value levers"
        value={String(valueRows)}
        change={result.data_note || 'Model + benchmark backed'}
      />
    </div>
  );
};
