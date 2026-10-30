import React from 'react';
import { useDialogA11y } from '../../../hooks/useDialogA11y';
import { formatCr } from '../../../utils/formatInr';
import type { WorkbenchRun } from '../../../types';

interface RunCompareViewProps {
  runs: [WorkbenchRun, WorkbenchRun];
  currency: string;
  onClose: () => void;
}

type MetricRow = { label: string; key: keyof WorkbenchRun['headline']; money: boolean };

const METRICS: MetricRow[] = [
  { label: 'Savings (mid)', key: 'savings_mid', money: true },
  { label: 'NPV', key: 'npv', money: true },
  { label: 'Spend base', key: 'total_spend', money: true },
  { label: 'Initiatives', key: 'initiative_count', money: false },
  { label: 'EBITDA bps', key: 'ebitda_bps', money: false },
];

export const RunCompareView: React.FC<RunCompareViewProps> = ({ runs, currency, onClose }) => {
  const panelRef = useDialogA11y<HTMLDivElement>(true, onClose);
  const [a, b] = runs;

  const fmt = (v: unknown, money: boolean): string => {
    if (v === undefined || v === null) return '—';
    return money ? formatCr(Number(v), { currency }) : String(v);
  };

  const overrideKeys = Array.from(
    new Set([...Object.keys(a.overrides || {}), ...Object.keys(b.overrides || {})]),
  ).sort();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-compare-title"
        tabIndex={-1}
        className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[85vh] overflow-y-auto p-5 outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 id="run-compare-title" className="text-lg font-bold text-brand-ink">Compare runs</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="text-brand-muted hover:text-brand-ink text-xl">
            ×
          </button>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-brand-border">
              <th className="text-left py-2 text-brand-muted font-medium">Metric</th>
              <th className="text-right py-2 text-brand-ink font-semibold">{a.name}</th>
              <th className="text-right py-2 text-brand-ink font-semibold">{b.name}</th>
            </tr>
          </thead>
          <tbody>
            {METRICS.map((m) => (
              <tr key={m.key} className="border-b border-brand-border/60">
                <td className="py-2 text-brand-muted">{m.label}</td>
                <td className="py-2 text-right font-medium text-brand-ink">{fmt(a.headline?.[m.key], m.money)}</td>
                <td className="py-2 text-right font-medium text-brand-ink">{fmt(b.headline?.[m.key], m.money)}</td>
              </tr>
            ))}
            {overrideKeys.length > 0 && (
              <tr>
                <td colSpan={3} className="pt-3 pb-1 text-[11px] uppercase tracking-wider text-brand-muted">
                  Assumptions
                </td>
              </tr>
            )}
            {overrideKeys.map((k) => (
              <tr key={k} className="border-b border-brand-border/60">
                <td className="py-2 text-brand-muted">{k}</td>
                <td className="py-2 text-right text-brand-ink">{String((a.overrides || {})[k] ?? '—')}</td>
                <td className="py-2 text-right text-brand-ink">{String((b.overrides || {})[k] ?? '—')}</td>
              </tr>
            ))}
            <InitiativeDiff a={a} b={b} currency={currency} />
          </tbody>
        </table>
      </div>
    </div>
  );
};

function InitiativeDiff({
  a,
  b,
  currency,
}: {
  a: WorkbenchRun;
  b: WorkbenchRun;
  currency: string;
}) {
  const initsA = ((a.skill_outputs?.['savings-modeler'] as Record<string, unknown>)?.initiatives ||
    []) as Record<string, unknown>[];
  const initsB = ((b.skill_outputs?.['savings-modeler'] as Record<string, unknown>)?.initiatives ||
    []) as Record<string, unknown>[];
  if (!initsA.length && !initsB.length) return null;

  const npv = (item: Record<string, unknown>) =>
    Number((item.net_savings as Record<string, number>)?.npv_aftertax || 0);

  return (
    <>
      <tr>
        <td colSpan={3} className="pt-3 pb-1 text-[11px] uppercase tracking-wider text-brand-muted">
          Initiative NPV (savings-modeler)
        </td>
      </tr>
      <tr className="border-b border-brand-border/60">
        <td className="py-2 text-brand-muted">Count</td>
        <td className="py-2 text-right text-brand-ink">{initsA.length}</td>
        <td className="py-2 text-right text-brand-ink">{initsB.length}</td>
      </tr>
      <tr className="border-b border-brand-border/60">
        <td className="py-2 text-brand-muted">Total NPV</td>
        <td className="py-2 text-right text-brand-ink">
          {formatCr(initsA.reduce((s, i) => s + npv(i), 0), { currency })}
        </td>
        <td className="py-2 text-right text-brand-ink">
          {formatCr(initsB.reduce((s, i) => s + npv(i), 0), { currency })}
        </td>
      </tr>
    </>
  );
}
