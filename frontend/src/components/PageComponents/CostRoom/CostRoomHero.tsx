import React, { useMemo } from 'react';
import { currencySymbol } from '../../../utils/currencySymbol';
import { ConfidenceBandTrack } from './primitives/ConfidenceBandTrack';
import { GateProgressBar } from './primitives/GateProgressBar';
import type { ScenarioPreset } from './ScenarioControls';
import { toCr } from '../../../utils/formatInr';
import {
  GATE2_COMMIT_THRESHOLD_PCT,
  valForBand,
} from '../../../utils/initiativeHelpers';
import type { Initiative, PercentileBand } from '../../../types';

const SCENARIO_LABELS: Record<string, string> = {
  base: 'Base case',
  conservative: 'Conservative · 60% exec',
  accelerated: 'Accelerated · 90% exec',
  inr_depreciation: 'INR −5% (depreciation)',
  wage_shock: 'Wage +200 bps',
  commodity: 'Commodity +15%',
  exec_slip: 'Exec slip +6 months',
};

interface CostRoomHeroProps {
  initiatives: Initiative[];
  percentileBand: PercentileBand;
  scenario: ScenarioPreset;
  scenarioFactor: number;
  ebitdaBps: number;
  currency?: string;
  revenueCr?: number;
}

function formatHeroCr(amount: number, currency: string): string {
  const cr = toCr(amount, currency);
  return cr.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

export const CostRoomHero: React.FC<CostRoomHeroProps> = ({
  initiatives,
  percentileBand,
  scenario,
  scenarioFactor,
  ebitdaBps,
  currency = 'INR',
  revenueCr = 25000,
}) => {
  const live = useMemo(
    () => initiatives.filter((x) => x.stage !== 'rejected' && x.stage !== 'deferred'),
    [initiatives],
  );

  const portfolioP = useMemo(
    () => live.reduce((s, x) => s + (valForBand(x, percentileBand, scenarioFactor) ?? 0), 0),
    [live, percentileBand, scenarioFactor],
  );
  const portfolioP50 = useMemo(
    () => live.reduce((s, x) => s + (valForBand(x, 'p50', scenarioFactor) ?? 0), 0),
    [live, scenarioFactor],
  );
  const portfolioP10 = useMemo(
    () => live.reduce((s, x) => s + (valForBand(x, 'p10', scenarioFactor) ?? 0), 0),
    [live, scenarioFactor],
  );
  const portfolioP90 = useMemo(
    () => live.reduce((s, x) => s + (valForBand(x, 'p90', scenarioFactor) ?? 0), 0),
    [live, scenarioFactor],
  );
  const committedP = useMemo(
    () =>
      live
        .filter((x) => ['committed', 'in_flight', 'realized'].includes(x.stage))
        .reduce((s, x) => s + (valForBand(x, percentileBand, scenarioFactor) ?? 0), 0),
    [live, percentileBand, scenarioFactor],
  );
  const committedPct = portfolioP > 0 ? Math.round((committedP / portfolioP) * 100) : 0;
  const portfolioP50Cr = toCr(portfolioP50, currency);
  const revenuePct = revenueCr > 0 ? ((portfolioP50Cr / revenueCr) * 100).toFixed(1) : '0';
  const roceBps = Math.round(ebitdaBps * 0.85);
  const epsUplift = (portfolioP50Cr * 0.0011).toFixed(2);
  const equityCr = Math.round(portfolioP50Cr * 0.75 * 15);
  const sym = currencySymbol(currency);

  const scenarioSuffix =
    scenario !== 'base' ? ` · ${SCENARIO_LABELS[scenario] ?? scenario}` : '';
  const gapCr = Math.max(
    0,
    Math.round(toCr(portfolioP * (GATE2_COMMIT_THRESHOLD_PCT / 100), currency) - toCr(committedP, currency)),
  );
  const gateStatus =
    committedPct >= GATE2_COMMIT_THRESHOLD_PCT
      ? 'Gate 2 commitment threshold cleared'
      : `${sym}${gapCr.toLocaleString('en-IN')} Cr more to commit to clear Gate 2 (${GATE2_COMMIT_THRESHOLD_PCT}%)`;

  return (
    <div className="cr-card overflow-hidden">
      <div className="cr-hero-grid">
        <div className="cr-hero-left p-6 border-r border-[var(--cr-line-2)]">
          <div className="cr-eyebrow">
            Value at stake · {percentileBand.toUpperCase()}
            {scenarioSuffix}
          </div>
          <div className="cr-bignum mt-2">
            <span className="text-[0.5em] font-bold text-[var(--cr-gray-2)] align-super mr-1">
              {sym}
            </span>
            {formatHeroCr(portfolioP, currency)}
            <span className="text-[22px] font-bold text-[var(--cr-gray-2)] ml-2">Cr</span>
          </div>
          <p className="text-sm text-[var(--cr-gray)] mt-1.5">
            Annual run-rate across <strong>{live.length} live initiatives</strong> · {revenuePct}%
            of {sym}
            {revenueCr.toLocaleString('en-IN')} Cr revenue
          </p>
          <ConfidenceBandTrack
            band={percentileBand}
            tipLabel={`${sym}${formatHeroCr(portfolioP, currency)} Cr`}
            p10Label={`${sym}${formatHeroCr(portfolioP10, currency)}`}
            p50Label={`${sym}${formatHeroCr(portfolioP50, currency)}`}
            p90Label={`${sym}${formatHeroCr(portfolioP90, currency)}`}
          />
          <GateProgressBar
            committedPct={committedPct}
            statusMessage={`${sym}${formatHeroCr(committedP, currency)} Cr · ${committedPct}%`}
          />
          <p
            className={`text-[11.5px] mt-3.5 font-semibold ${
              committedPct >= GATE2_COMMIT_THRESHOLD_PCT
                ? 'text-[var(--cr-green-dk)]'
                : 'text-[var(--cr-amber)]'
            }`}
          >
            {gateStatus}
          </p>
        </div>
        <div className="p-5 bg-gradient-to-b from-[#fcfcfb] to-[#f7f8f4]">
          <div className="cr-eyebrow mb-3.5">Savings → shareholder value (P50)</div>
          <div className="flex flex-col gap-2">
            <BridgeStep label="Portfolio savings" value={`${sym}${formatHeroCr(portfolioP50, currency)} Cr`} />
            <BridgeArrow />
            <BridgeStep label="EBITDA impact (Y3)" value={`+${ebitdaBps} bps`} />
            <BridgeArrow />
            <div className="flex gap-2.5">
              <BridgeStep label="ROCE" value={`+${roceBps} bps`} className="flex-1" />
              <BridgeStep label="EPS (Y3)" value={`+${sym}${epsUplift}`} className="flex-1" />
            </div>
            <BridgeArrow />
            <BridgeStep
              label="Equity value @ 15× P/E"
              value={`${sym}${equityCr.toLocaleString('en-IN')}+ Cr`}
              dark
            />
          </div>
          <p className="text-[11px] text-[var(--cr-gray-2)] mt-3 leading-snug">
            Bridge recomputes live with the percentile and scenario above. Equity uplift on net PAT
            improvement at a 15× exit multiple.
          </p>
        </div>
      </div>
    </div>
  );
};

function BridgeStep({
  label,
  value,
  dark = false,
  className = '',
}: {
  label: string;
  value: string;
  dark?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`flex items-baseline justify-between rounded-[var(--cr-r-sm)] px-3 py-2 border ${className} ${
        dark
          ? 'bg-[var(--cr-navy)] border-[var(--cr-navy)]'
          : 'bg-white border-[var(--cr-line)]'
      }`}
    >
      <span
        className={`text-[11.5px] font-semibold ${dark ? 'text-white/80' : 'text-[var(--cr-gray)]'}`}
      >
        {label}
      </span>
      <span className={`cr-mono text-base font-extrabold ${dark ? 'text-white' : ''}`}>{value}</span>
    </div>
  );
}

function BridgeArrow() {
  return (
    <div className="text-center text-[var(--cr-gray-3)] text-xs">▼</div>
  );
}
