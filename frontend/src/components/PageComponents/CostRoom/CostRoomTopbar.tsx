import React from 'react';
import { Link } from 'react-router-dom';
import { SegControl } from './primitives/SegControl';
import type { ScenarioPreset } from './ScenarioControls';
import { useSession } from '../../../context/SessionContext';
import { useAudience } from '../../../context/AudienceContext';
import { formatIndustryLabel } from '../../../utils/formatInr';
import { isClientEngagementReady } from '../../../utils/engagement';
import type { PercentileBand } from '../../../types';

const SCENARIO_OPTIONS: { value: ScenarioPreset; label: string }[] = [
  { value: 'base', label: 'Base case' },
  { value: 'conservative', label: 'Conservative · 60% exec' },
  { value: 'accelerated', label: 'Accelerated · 90% exec' },
  { value: 'inr_depreciation', label: 'INR −5% (depreciation)' },
  { value: 'wage_shock', label: 'Wage +200 bps' },
  { value: 'commodity', label: 'Commodity +15%' },
  { value: 'exec_slip', label: 'Exec slip +6 months' },
];

interface CostRoomTopbarProps {
  percentileBand: PercentileBand;
  onBandChange: (band: PercentileBand) => void;
  scenario: ScenarioPreset;
  onScenarioChange: (scenario: ScenarioPreset) => void;
}

export const CostRoomTopbar: React.FC<CostRoomTopbarProps> = ({
  percentileBand,
  onBandChange,
  scenario,
  onScenarioChange,
}) => {
  const { engagement, hasAnalysis } = useSession();
  const { isExecutive, toggleAudience } = useAudience();
  const clientReady = isClientEngagementReady(hasAnalysis, engagement.company_name);

  return (
    <header className="flex flex-wrap items-center justify-between gap-4 py-3 px-0 mb-2 border-b border-[var(--cr-line)] bg-white/80 backdrop-blur-sm -mx-4 md:-mx-6 lg:-mx-8 px-4 md:px-6 lg:px-8">
      <div className="min-w-0">
        <div className="cr-eyebrow">
          Deloitte · {isExecutive ? 'Executive Cost Room' : 'Live Cost Room'}
        </div>
        <h1 className="text-lg font-bold text-[var(--cr-ink)] tracking-tight mt-0.5">
          {clientReady ? engagement.company_name : 'Client portfolio'}
          {clientReady && (
            <span className="font-normal text-[var(--cr-gray-2)]">
              {' '}
              · {formatIndustryLabel(engagement.industry)}
            </span>
          )}
        </h1>
        {!clientReady && (
          <p className="text-sm text-[var(--cr-gray)] mt-1">
            Run analysis on the{' '}
            <Link to="/" className="text-[var(--cr-navy)] font-medium hover:text-[var(--cr-green-dk)]">
              Analysis
            </Link>{' '}
            page to load this client&apos;s Cost Room.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-2.5 text-xs text-[var(--cr-gray)] mt-1">
          <span>
            Week {engagement.engagement_week} of {engagement.engagement_weeks_total}
          </span>
          <span className="text-[11px] font-bold text-[var(--cr-green-dk)] bg-[var(--cr-green-soft)] border border-[#cfe39f] px-2 py-0.5 rounded-full">
            {engagement.gate_label}
          </span>
          <span className="text-[var(--cr-gray-3)]">Group CFO · SSO</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 shrink-0">
        <div className="text-right">
          <div className="cr-eyebrow">Percentile</div>
          <div className="mt-1">
            <SegControl
              green
              value={percentileBand}
              onChange={onBandChange}
              options={[
                { value: 'p10', label: 'P10' },
                { value: 'p50', label: 'P50' },
                { value: 'p90', label: 'P90' },
              ]}
            />
          </div>
        </div>
        <div className="text-right">
          <div className="cr-eyebrow">Scenario</div>
          <select
            value={scenario}
            onChange={(e) => onScenarioChange(e.target.value as ScenarioPreset)}
            className="mt-1 text-sm border border-[var(--cr-line)] rounded-[var(--cr-r-sm)] px-2.5 py-1.5 bg-white text-[var(--cr-ink)] min-w-[200px] cursor-pointer"
          >
            {SCENARIO_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={toggleAudience}
          className="text-xs px-3 py-1.5 rounded-[var(--cr-r-sm)] border border-[var(--cr-line)] text-[var(--cr-ink)] hover:bg-[var(--cr-muted)] self-end"
        >
          {isExecutive ? 'Consultant view' : 'Executive view'}
        </button>
      </div>
    </header>
  );
};
