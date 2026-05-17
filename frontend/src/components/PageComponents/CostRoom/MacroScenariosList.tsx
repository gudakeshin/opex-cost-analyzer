import React from 'react';
import { formatBps } from '../../../utils/formatInr';

export interface MacroScenarioItem {
  id: string;
  label: string;
  ebitdaBps: number;
  illustrative?: boolean;
}

interface MacroScenariosListProps {
  scenarios: MacroScenarioItem[];
  activeId: string;
  baseBps: number;
}

export const MacroScenariosList: React.FC<MacroScenariosListProps> = ({
  scenarios,
  activeId,
  baseBps,
}) => (
  <div className="space-y-2">
    <h4 className="text-xs font-semibold uppercase tracking-wide text-brand-muted">Macro scenarios</h4>
    <ul className="space-y-1.5">
      {scenarios.map((s) => {
        const active = s.id === activeId;
        return (
          <li
            key={s.id}
            className={`flex items-center justify-between text-sm px-3 py-2 rounded-lg border ${
              active
                ? 'border-brand-green bg-brand-green/10 font-medium'
                : 'border-brand-border bg-brand-surface-muted/50'
            }`}
          >
            <span className="text-brand-ink">
              {s.label}
              {s.illustrative && (
                <span className="ml-1 text-[10px] text-brand-muted">(illustrative)</span>
              )}
            </span>
            <span className="tabular-nums text-brand-navy">{formatBps(s.ebitdaBps)}</span>
          </li>
        );
      })}
    </ul>
    <p className="text-[10px] text-brand-muted">Base scenario: {formatBps(baseBps)} EBITDA impact</p>
  </div>
);

export const DEFAULT_MACRO_SCENARIOS: Omit<MacroScenarioItem, 'ebitdaBps'>[] = [
  { id: 'base', label: 'Base (current)' },
  { id: 'inr_depreciation', label: 'INR −5% (depreciation)' },
  { id: 'wage_shock', label: 'Wage +200 bps over base' },
  { id: 'commodity', label: 'Commodity +15%' },
  { id: 'exec_slip', label: 'Exec slip +6 months' },
];

export function macroScenarioBps(baseBps: number, scenarioId: string): number {
  const factors: Record<string, number> = {
    base: 1,
    inr_depreciation: 0.87,
    wage_shock: 0.92,
    commodity: 0.9,
    exec_slip: 0.7,
    conservative: 0.75,
    accelerated: 1.05,
  };
  return Math.round(baseBps * (factors[scenarioId] ?? 1));
}
