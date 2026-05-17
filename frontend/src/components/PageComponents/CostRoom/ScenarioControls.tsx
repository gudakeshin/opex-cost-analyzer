import React from 'react';
import type { PercentileBand } from '../../../types';

export type ScenarioPreset =
  | 'base'
  | 'conservative'
  | 'accelerated'
  | 'inr_depreciation'
  | 'wage_shock'
  | 'commodity'
  | 'exec_slip';

interface ScenarioControlsProps {
  percentileBand: PercentileBand;
  onBandChange: (band: PercentileBand) => void;
  scenario: ScenarioPreset;
  onScenarioChange: (scenario: ScenarioPreset) => void;
}

const BANDS: PercentileBand[] = ['p10', 'p50', 'p90'];

const SCENARIO_OPTIONS: { value: ScenarioPreset; label: string }[] = [
  { value: 'base', label: 'Base' },
  { value: 'conservative', label: 'Conservative (60%)' },
  { value: 'accelerated', label: 'Accelerated (90%)' },
  { value: 'inr_depreciation', label: 'INR −5%' },
  { value: 'wage_shock', label: 'Wage +200 bps' },
  { value: 'commodity', label: 'Commodity +15%' },
  { value: 'exec_slip', label: 'Exec slip +6 mo' },
];

export const ScenarioControls: React.FC<ScenarioControlsProps> = ({
  percentileBand,
  onBandChange,
  scenario,
  onScenarioChange,
}) => (
  <div className="flex flex-wrap items-center gap-6 p-4 bg-white border border-brand-border rounded-xl">
    <div className="flex items-center gap-2">
      <span className="text-sm font-medium text-brand-muted">Percentile</span>
      <div className="flex gap-1">
        {BANDS.map((b) => (
          <button
            key={b}
            type="button"
            onClick={() => onBandChange(b)}
            className={`px-3 py-1.5 rounded-lg text-sm font-mono tabular-nums transition-colors ${
              percentileBand === b
                ? 'bg-brand-green text-white'
                : 'bg-brand-surface-muted text-brand-ink border border-brand-border hover:border-brand-green'
            }`}
          >
            {b.toUpperCase()}
          </button>
        ))}
      </div>
    </div>
    <div className="flex items-center gap-2">
      <span className="text-sm font-medium text-brand-muted">Scenario</span>
      <select
        value={scenario}
        onChange={(e) => onScenarioChange(e.target.value as ScenarioPreset)}
        className="text-sm border border-brand-border rounded-lg px-3 py-2 bg-white text-brand-ink min-w-[180px]"
      >
        {SCENARIO_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  </div>
);
