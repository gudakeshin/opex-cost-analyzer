import React, { useMemo } from 'react';
import { Card } from '../../Common/Card';
import { ValueBridgeChart } from './ValueBridgeChart';
import { formatBps, formatCr } from '../../../utils/formatInr';
import { GATE2_COMMIT_THRESHOLD_PCT } from '../../../utils/initiativeHelpers';
import type { Initiative, PipelineSummary } from '../../../types';
import type { EngagementMeta } from '../../../types';

interface ValueBridgePanelProps {
  initiatives: Initiative[];
  summary: PipelineSummary | null;
  engagement: EngagementMeta;
  portfolioP50Cr: number;
  committedP50Cr: number;
  ebitdaBps: number;
}

export const ValueBridgePanel: React.FC<ValueBridgePanelProps> = ({
  initiatives,
  summary,
  engagement,
  portfolioP50Cr,
  committedP50Cr,
  ebitdaBps,
}) => {
  const committedPct = portfolioP50Cr > 0 ? Math.round((committedP50Cr / portfolioP50Cr) * 100) : 0;
  const revenueCr = engagement.annual_revenue_cr ?? 25000;
  const roceBps = Math.round(ebitdaBps * 0.85);
  const epsUplift = portfolioP50Cr > 0 ? (portfolioP50Cr * 0.0025).toFixed(2) : '—';
  const equityUpliftCr = portfolioP50Cr > 0 ? Math.round(portfolioP50Cr * revenueCr * 0.015) : 0;

  const runRateCount = useMemo(
    () => initiatives.filter((i) => i.savings_type !== 'one_time').length,
    [initiatives],
  );

  return (
    <Card className="!p-5 space-y-5 bg-white border-brand-border h-full">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-brand-muted">Value Bridge (P50)</h3>
        <p className="text-xs text-brand-muted mt-1">
          {engagement.company_name} · ₹{revenueCr.toLocaleString('en-IN')} Cr revenue
        </p>
      </div>

      <ValueBridgeChart
        portfolioP50Cr={portfolioP50Cr}
        committedP50Cr={committedP50Cr}
        ebitdaBps={ebitdaBps}
      />

      <div className="space-y-3">
        <BridgeRow label="Portfolio P50" value={formatCr(portfolioP50Cr)} highlight />
        <BridgeRow
          label="Committed"
          value={`${formatCr(committedP50Cr)} (${committedPct}%)`}
          sub={`Gate 2 threshold: ${GATE2_COMMIT_THRESHOLD_PCT}%`}
        />
        <BridgeRow label="EBITDA impact (steady-state Y3)" value={formatBps(ebitdaBps)} />
        <BridgeRow label="ROCE impact" value={formatBps(roceBps)} />
        <BridgeRow label="EPS uplift (Y3)" value={epsUplift !== '—' ? `₹${epsUplift}` : '—'} />
        <BridgeRow
          label="Equity value @ 15× P/E"
          value={equityUpliftCr > 0 ? `₹${equityUpliftCr.toLocaleString('en-IN')}+ Cr` : '—'}
        />
      </div>

      <div className="pt-3 border-t border-brand-border text-xs text-brand-muted space-y-1">
        <p>{runRateCount} run-rate initiatives in portfolio</p>
        {summary?.realization_rate_pct != null && (
          <p>Realization rate: {summary.realization_rate_pct}%</p>
        )}
      </div>
    </Card>
  );
};

function BridgeRow({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-brand-muted">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${highlight ? 'text-brand-navy' : 'text-brand-ink'}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-brand-muted">{sub}</p>}
    </div>
  );
}
