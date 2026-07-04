import React, { useState } from 'react';
import { apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import { Alert } from '../../Common/Alert';
import { Loader } from '../../Common/Loader';

export interface CustomScenarioRow {
  name: string;
  target: 'portfolio' | 'lever' | 'vendor' | 'category';
  id: string;
  savings_pct_delta: string;
  timeline_factor: string;
  execution_rate: string;
}

interface SensitivityScenario {
  name: string;
  key_assumption: string;
  savings_3yr: number;
  timeline_months: number;
  npv_aftertax: number;
  execution_rate?: number;
  custom?: boolean;
}

interface SensitivityResult {
  scenarios: SensitivityScenario[];
  baseline_mid_savings: number;
  confidence_bands: { low: number; mid: number; high: number };
}

interface SensitivityPanelProps {
  sessionId: string | null;
}

const EMPTY_ROW = (): CustomScenarioRow => ({
  name: '',
  target: 'portfolio',
  id: '',
  savings_pct_delta: '0',
  timeline_factor: '1',
  execution_rate: '',
});

export const SensitivityPanel: React.FC<SensitivityPanelProps> = ({ sessionId }) => {
  const [open, setOpen] = useState(true);
  const [rows, setRows] = useState<CustomScenarioRow[]>([EMPTY_ROW()]);
  const [result, setResult] = useState<SensitivityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateRow = (idx: number, patch: Partial<CustomScenarioRow>) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const addRow = () => setRows((prev) => [...prev, EMPTY_ROW()]);

  const removeRow = (idx: number) =>
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));

  const runSensitivity = async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const scenarios = rows
        .filter((r) => r.name.trim())
        .map((r) => ({
          name: r.name.trim(),
          target: r.target,
          id: r.id.trim() || undefined,
          savings_pct_delta: Number(r.savings_pct_delta) / 100,
          timeline_factor: Number(r.timeline_factor) || 1,
          execution_rate: r.execution_rate.trim()
            ? Number(r.execution_rate) / 100
            : undefined,
        }));
      if (scenarios.length === 0) {
        setError('Add at least one named scenario.');
        return;
      }
      const data = await apiPost<SensitivityResult>('/api/v1/sensitivity/custom', {
        session_id: sessionId,
        scenarios,
      });
      setResult(data);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  if (!sessionId) {
    return <p className="text-sm text-brand-muted">Select a session to model custom what-if scenarios.</p>;
  }

  return (
    <div className="border border-brand-border rounded-lg">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-brand-ink"
      >
        <span>Custom what-if scenarios</span>
        <span className="text-brand-muted">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-3">
          <p className="text-xs text-brand-muted">
            Requires a prior value-bridge run on this session. Savings delta is entered as % (e.g. 15 = +15%).
          </p>
          {error && (
            <Alert variant="error" title="Sensitivity failed" onDismiss={() => setError(null)}>
              {error}
            </Alert>
          )}
          {rows.map((row, idx) => (
            <div
              key={idx}
              className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end border border-brand-border/60 rounded p-2"
            >
              <label className="block text-xs md:col-span-2">
                <span className="text-brand-muted">Name</span>
                <input
                  className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                  value={row.name}
                  onChange={(e) => updateRow(idx, { name: e.target.value })}
                  placeholder="Aggressive logistics"
                />
              </label>
              <label className="block text-xs">
                <span className="text-brand-muted">Target</span>
                <select
                  className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                  value={row.target}
                  onChange={(e) =>
                    updateRow(idx, { target: e.target.value as CustomScenarioRow['target'] })
                  }
                >
                  <option value="portfolio">Portfolio</option>
                  <option value="category">Category</option>
                  <option value="vendor">Vendor</option>
                  <option value="lever">Lever</option>
                </select>
              </label>
              <label className="block text-xs">
                <span className="text-brand-muted">Target ID</span>
                <input
                  className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                  value={row.id}
                  onChange={(e) => updateRow(idx, { id: e.target.value })}
                  placeholder="CAT_LOGISTICS"
                />
              </label>
              <label className="block text-xs">
                <span className="text-brand-muted">Savings Δ (%)</span>
                <input
                  type="number"
                  className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                  value={row.savings_pct_delta}
                  onChange={(e) => updateRow(idx, { savings_pct_delta: e.target.value })}
                />
              </label>
              <label className="block text-xs">
                <span className="text-brand-muted">Timeline ×</span>
                <input
                  type="number"
                  step="0.1"
                  className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                  value={row.timeline_factor}
                  onChange={(e) => updateRow(idx, { timeline_factor: e.target.value })}
                />
              </label>
              <label className="block text-xs">
                <span className="text-brand-muted">Execution (%)</span>
                <input
                  type="number"
                  className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                  value={row.execution_rate}
                  onChange={(e) => updateRow(idx, { execution_rate: e.target.value })}
                  placeholder="auto"
                />
              </label>
              <button
                type="button"
                className="text-xs text-red-600 md:col-span-6 text-left"
                onClick={() => removeRow(idx)}
              >
                Remove
              </button>
            </div>
          ))}
          <div className="flex gap-2">
            <button
              type="button"
              className="text-sm text-brand-primary"
              onClick={addRow}
            >
              + Add scenario
            </button>
            <button
              type="button"
              disabled={loading}
              className="rounded bg-brand-primary px-3 py-1.5 text-sm text-white disabled:opacity-50"
              onClick={() => void runSensitivity()}
            >
              {loading ? 'Running…' : 'Run sensitivity'}
            </button>
          </div>
          {loading && <Loader label="Computing scenarios…" />}
          {result && (
            <div className="overflow-auto max-h-80 border border-brand-border rounded">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-brand-surface-elevated text-left">
                    <th className="px-2 py-1">Scenario</th>
                    <th className="px-2 py-1">3yr savings</th>
                    <th className="px-2 py-1">NPV (after tax)</th>
                    <th className="px-2 py-1">Months</th>
                  </tr>
                </thead>
                <tbody>
                  {result.scenarios
                    .filter((s) => s.custom || rows.some((r) => r.name === s.name))
                    .map((s) => (
                      <tr key={s.name} className="border-t border-brand-border/50">
                        <td className="px-2 py-1 font-medium">{s.name}</td>
                        <td className="px-2 py-1">{s.savings_3yr.toLocaleString()}</td>
                        <td className="px-2 py-1">{s.npv_aftertax.toLocaleString()}</td>
                        <td className="px-2 py-1">{s.timeline_months}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
