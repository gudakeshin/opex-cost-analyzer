import React from 'react';
import { MetricTile } from '../../Common/MetricTile';
import { formatBps, formatCr } from '../../../utils/formatInr';
import { GATE2_COMMIT_THRESHOLD_PCT } from '../../../utils/initiativeHelpers';

interface KpiStripProps {
  portfolioP50Cr: number;
  committedP50Cr: number;
  ebitdaBps: number;
  initiativeCount: number;
  gateProgressPct: number;
  currency?: string;
}

export const KpiStrip: React.FC<KpiStripProps> = ({
  portfolioP50Cr,
  committedP50Cr,
  ebitdaBps,
  initiativeCount,
  gateProgressPct,
  currency = 'USD',
}) => (
  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
    <MetricTile
      label="Portfolio P50"
      value={formatCr(portfolioP50Cr, { currency })}
      change={`${initiativeCount} initiatives`}
    />
    <MetricTile
      label="Committed (P50)"
      value={formatCr(committedP50Cr, { currency })}
      change={`${gateProgressPct}% of portfolio`}
    />
    <MetricTile label="EBITDA impact (Y3)" value={formatBps(ebitdaBps)} change="Steady-state P50" />
    <MetricTile
      label="Gate 2 progress"
      value={`${gateProgressPct}%`}
      change={`Threshold ${GATE2_COMMIT_THRESHOLD_PCT}%`}
      highlight
    />
  </div>
);
