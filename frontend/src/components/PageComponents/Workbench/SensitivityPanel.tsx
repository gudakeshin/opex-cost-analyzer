import React, { useEffect, useMemo, useState } from 'react';
import { apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import { useSession } from '../../../context/SessionContext';
import { useToast } from '../../../context/ToastContext';
import { useWorkbenchRuns } from '../../../api/hooks/useWorkbenchQueries';
import {
  useDeleteScenarioSet,
  useSaveScenarioSet,
  useSavedScenarioSets,
  type SavedScenarioSet,
  type ScenarioSpec,
} from '../../../api/hooks/useWorkbenchPanelQueries';
import { Alert } from '../../Common/Alert';
import { Loader } from '../../Common/Loader';
import { DynamicChart } from '../Procurement/DynamicChart';
import { formatCr } from '../../../utils/formatInr';
import { copyText, downloadTextFile, toCsv, toTsv } from '../../../utils/exportTable';
import type { ChartSpec } from '../../../types';
import { useConfirm } from '../../../hooks/useConfirm';

export interface CustomScenarioRow {
  name: string;
  target: 'portfolio' | 'category' | 'lever';
  id: string;
  savings_pct_delta: string;
  timeline_factor: string;
  execution_rate: string;
  spend_pool_delta_pct: string;
  addressable_spend_delta_pct: string;
  bounce_back_override: '' | 'high' | 'medium' | 'low';
  cost_driver_deltas: string; // "supplier_price_inflation_pct=0.05, fx=0.02"
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
  narrative?: string;
}

interface ParsedScenario {
  name: string;
  target: string;
  id: string | null;
  savings_pct_delta: number;
  timeline_factor: number;
  execution_rate: number | null;
  addressable_spend_delta_pct: number;
  spend_pool_delta_pct: number;
  bounce_back_override: string | null;
  cost_driver_deltas: Record<string, number>;
}

interface ParseResponse {
  question: string;
  drivers: Record<string, number>;
  scenarios: ParsedScenario[];
  validation_errors: string[];
  known_categories: { category_id: string; category_name: string }[];
  known_levers: { lever_id: string; lever_name: string }[];
  parse_source: 'llm' | 'regex';
}

interface SensitivityPanelProps {
  sessionId: string | null;
  currency: string;
  onRequestValueBridge?: () => void;
}

const EMPTY_ROW = (): CustomScenarioRow => ({
  name: '',
  target: 'portfolio',
  id: '',
  savings_pct_delta: '0',
  timeline_factor: '1',
  execution_rate: '',
  spend_pool_delta_pct: '0',
  addressable_spend_delta_pct: '0',
  bounce_back_override: '',
  cost_driver_deltas: '',
});

const rowFromParsed = (s: ParsedScenario, idx: number): CustomScenarioRow => ({
  name: s.name || `scenario_${idx + 1}`,
  target: (['portfolio', 'category', 'lever'].includes(s.target) ? s.target : 'portfolio') as
    | 'portfolio'
    | 'category'
    | 'lever',
  id: s.id ?? '',
  savings_pct_delta: String(Math.round(s.savings_pct_delta * 10000) / 100),
  timeline_factor: String(s.timeline_factor ?? 1),
  execution_rate:
    s.execution_rate == null ? '' : String(Math.round(s.execution_rate * 10000) / 100),
  spend_pool_delta_pct: String(Math.round((s.spend_pool_delta_pct ?? 0) * 10000) / 100),
  addressable_spend_delta_pct: String(
    Math.round((s.addressable_spend_delta_pct ?? 0) * 10000) / 100,
  ),
  bounce_back_override: (s.bounce_back_override ?? '') as CustomScenarioRow['bounce_back_override'],
  cost_driver_deltas: Object.entries(s.cost_driver_deltas ?? {})
    .map(([k, v]) => `${k}=${v}`)
    .join(', '),
});

const rowFromSpec = (s: ScenarioSpec, idx: number): CustomScenarioRow =>
  rowFromParsed(
    {
      name: s.name,
      target: s.target,
      id: s.id ?? null,
      savings_pct_delta: s.savings_pct_delta,
      timeline_factor: s.timeline_factor,
      execution_rate: s.execution_rate ?? null,
      addressable_spend_delta_pct: s.addressable_spend_delta_pct,
      spend_pool_delta_pct: s.spend_pool_delta_pct,
      bounce_back_override: s.bounce_back_override ?? null,
      cost_driver_deltas: s.cost_driver_deltas ?? {},
    },
    idx,
  );

const parseDriverDeltas = (text: string): Record<string, number> | undefined => {
  const out: Record<string, number> = {};
  for (const pair of text.split(',')) {
    const [k, v] = pair.split('=').map((s) => s.trim());
    if (k && v && !Number.isNaN(Number(v))) out[k] = Number(v);
  }
  return Object.keys(out).length ? out : undefined;
};

const buildScenarioSpecs = (rows: CustomScenarioRow[]): ScenarioSpec[] =>
  rows
    .filter((r) => r.name.trim())
    .map((r) => ({
      name: r.name.trim(),
      target: r.target,
      id: r.id.trim() || undefined,
      savings_pct_delta: Number(r.savings_pct_delta) / 100,
      timeline_factor: Number(r.timeline_factor) || 1,
      execution_rate: r.execution_rate.trim() ? Number(r.execution_rate) / 100 : undefined,
      spend_pool_delta_pct: Number(r.spend_pool_delta_pct || 0) / 100,
      addressable_spend_delta_pct: Number(r.addressable_spend_delta_pct || 0) / 100,
      bounce_back_override: r.bounce_back_override || undefined,
      cost_driver_deltas: parseDriverDeltas(r.cost_driver_deltas),
    }));

const mentionsValueBridge = (msg: string): boolean =>
  /value-bridge|value bridge|value_bridge/i.test(msg);

export const SensitivityPanel: React.FC<SensitivityPanelProps> = ({
  sessionId,
  currency,
  onRequestValueBridge,
}) => {
  const { sessionAnalysis, refreshSessionAnalysis, engagementId } = useSession();
  const { toast } = useToast();
  const runsQuery = useWorkbenchRuns(engagementId, sessionId);
  const savedSetsQuery = useSavedScenarioSets(sessionId);
  const saveSetMutation = useSaveScenarioSet(sessionId);
  const deleteSetMutation = useDeleteScenarioSet(sessionId);
  const savedSets = savedSetsQuery.data ?? [];
  const [open, setOpen] = useState(true);
  const [rows, setRows] = useState<CustomScenarioRow[]>([EMPTY_ROW()]);
  const [result, setResult] = useState<SensitivityResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bridgeMissing, setBridgeMissing] = useState(false);

  const [question, setQuestion] = useState('');
  const [parsing, setParsing] = useState(false);
  const [parseSource, setParseSource] = useState<'llm' | 'regex' | null>(null);
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [drivers, setDrivers] = useState<{ key: string; value: string }[]>([]);
  const [advancedOpen, setAdvancedOpen] = useState<Record<number, boolean>>({});
  const [knownCategories, setKnownCategories] = useState<
    { category_id: string; category_name: string }[]
  >([]);
  const [knownLevers, setKnownLevers] = useState<
    { lever_id: string; lever_name: string }[]
  >([]);
  const [view, setView] = useState<'table' | 'chart'>('table');
  const [saveName, setSaveName] = useState('');
  const [copyStatus, setCopyStatus] = useState<string | null>(null);

  const hasBridge = Boolean(
    sessionAnalysis?.skill_outputs?.['value-bridge-calculator'] ||
      (runsQuery.data?.runs ?? []).some(
        (r) => r.skill_outputs && r.skill_outputs['value-bridge-calculator'],
      ),
  );

  useEffect(() => {
    void refreshSessionAnalysis();
  }, [refreshSessionAnalysis]);

  useEffect(() => {
    const inits =
      (sessionAnalysis?.skill_outputs?.['savings-modeler'] as { initiatives?: Record<string, unknown>[] } | undefined)
        ?.initiatives ?? [];
    const seen = new Map<string, { lever_id: string; lever_name: string }>();
    for (const i of inits) {
      const lid = String(i.lever || i.lever_id || '');
      if (lid && !seen.has(lid)) {
        seen.set(lid, { lever_id: lid, lever_name: String(i.lever_name || lid) });
      }
    }
    if (seen.size) setKnownLevers(Array.from(seen.values()));
  }, [sessionAnalysis]);

  useEffect(() => {
    setBridgeMissing(!hasBridge);
  }, [hasBridge]);

  const updateRow = (idx: number, patch: Partial<CustomScenarioRow>) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const addRow = () => setRows((prev) => [...prev, EMPTY_ROW()]);

  const removeRow = (idx: number) =>
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));

  const driverMap = () =>
    Object.fromEntries(
      drivers
        .filter((d) => d.key.trim() && !Number.isNaN(Number(d.value)))
        .map((d) => [d.key.trim(), Number(d.value)]),
    );

  const parseQuestion = async () => {
    if (!sessionId || !question.trim()) return;
    setParsing(true);
    setError(null);
    setParseWarnings([]);
    try {
      const data = await apiPost<ParseResponse>('/api/v1/sensitivity/parse', {
        session_id: sessionId,
        question: question.trim(),
      });
      setParseSource(data.parse_source);
      setParseWarnings(data.validation_errors ?? []);
      setKnownCategories(data.known_categories ?? []);
      setKnownLevers(data.known_levers ?? []);
      if (data.scenarios.length > 0) {
        setRows(data.scenarios.map(rowFromParsed));
        setAdvancedOpen(
          Object.fromEntries(
            data.scenarios.map((s, i) => [
              i,
              Boolean(
                s.spend_pool_delta_pct ||
                  s.addressable_spend_delta_pct ||
                  s.bounce_back_override ||
                  Object.keys(s.cost_driver_deltas ?? {}).length,
              ),
            ]),
          ),
        );
      } else if ((data.validation_errors ?? []).length === 0) {
        setParseWarnings([
          'Nothing recognizable in that description — no LLM provider configured, or the phrasing is too open-ended. Fill the rows manually.',
        ]);
      }
      setDrivers(
        Object.entries(data.drivers ?? {}).map(([key, value]) => ({
          key,
          value: String(value),
        })),
      );
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setParsing(false);
    }
  };

  const runSensitivity = async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const scenarios = buildScenarioSpecs(rows);
      if (scenarios.length === 0) {
        setError('Add at least one named scenario.');
        return;
      }
      const dm = driverMap();
      const data = await apiPost<SensitivityResult>('/api/v1/sensitivity/custom', {
        session_id: sessionId,
        scenarios,
        ...(Object.keys(dm).length ? { drivers: dm } : {}),
      });
      setResult(data);
      setBridgeMissing(false);
      toast('Sensitivity scenarios computed');
    } catch (e) {
      const msg = getApiErrorMessage(e);
      if (mentionsValueBridge(msg)) {
        setBridgeMissing(true);
        setError(null);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const saveSet = async () => {
    if (!sessionId || !saveName.trim()) return;
    const scenarios = buildScenarioSpecs(rows);
    if (scenarios.length === 0) {
      setError('Add at least one named scenario before saving.');
      return;
    }
    try {
      const dm = driverMap();
      await saveSetMutation.mutateAsync({
        name: saveName.trim(),
        scenarios,
        ...(Object.keys(dm).length ? { drivers: dm } : {}),
      });
      setSaveName('');
      toast('Scenario set saved');
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  };

  const loadSet = (set: SavedScenarioSet) => {
    setRows(set.scenarios.map(rowFromSpec));
    setDrivers(
      Object.entries(set.drivers ?? {}).map(([key, value]) => ({
        key,
        value: String(value),
      })),
    );
    toast(`Loaded “${set.name}”`, 'info');
  };

  const [confirm, confirmDialog] = useConfirm();

  const deleteSet = async (setId: string) => {
    if (!sessionId) return;
    const ok = await confirm({
      title: 'Delete scenario set?',
      message: 'This saved scenario set will be permanently deleted.',
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteSetMutation.mutateAsync(setId);
      toast('Scenario set deleted', 'info');
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  };

  const baseScenario = result?.scenarios.find((s) => s.name === 'base') ?? null;
  const visibleScenarios = result
    ? result.scenarios.filter(
        (s) => s.name === 'base' || s.custom || rows.some((r) => r.name === s.name),
      )
    : [];

  const comparisonChart: ChartSpec | null = useMemo(() => {
    if (!result || !baseScenario) return null;
    const nonBase = visibleScenarios.filter((s) => s.name !== 'base');
    if (nonBase.length === 0) return null;
    return {
      id: 'whatif-comparison',
      type: 'bar',
      title: 'Scenario deltas vs base',
      x_key: 'scenario',
      unit: 'currency',
      series: [
        { key: 'delta_savings', name: 'Δ 3yr savings' },
        { key: 'delta_npv', name: 'Δ NPV after tax' },
      ],
      data: nonBase.map((s) => ({
        scenario: s.name,
        delta_savings: s.savings_3yr - baseScenario.savings_3yr,
        delta_npv: s.npv_aftertax - baseScenario.npv_aftertax,
      })),
    };
  }, [result, baseScenario, visibleScenarios]);

  const fmtDelta = (value: number, base: number) => {
    const d = value - base;
    const sign = d >= 0 ? '+' : '';
    return `${sign}${formatCr(d, { currency })}`;
  };

  const exportColumns = [
    'scenario',
    'savings_3yr',
    'delta_savings',
    'npv_aftertax',
    'delta_npv',
    'timeline_months',
  ];

  const exportRows = (): unknown[][] =>
    visibleScenarios.map((s) => {
      const isBase = s.name === 'base';
      return [
        s.name,
        s.savings_3yr,
        baseScenario && !isBase ? s.savings_3yr - baseScenario.savings_3yr : null,
        s.npv_aftertax,
        baseScenario && !isBase ? s.npv_aftertax - baseScenario.npv_aftertax : null,
        s.timeline_months,
      ];
    });

  const handleCopy = async () => {
    try {
      await copyText(toTsv(exportColumns, exportRows()));
      setCopyStatus('Copied');
      setTimeout(() => setCopyStatus(null), 1500);
    } catch {
      setCopyStatus('Copy failed');
      setTimeout(() => setCopyStatus(null), 1500);
    }
  };

  if (!sessionId) {
    return (
      <p className="text-sm text-brand-muted">Select a session to model custom what-if scenarios.</p>
    );
  }

  const showBridgeCta = bridgeMissing || !hasBridge;

  return (
    <div className="border border-brand-border rounded-lg">
      {confirmDialog}
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
            Requires a prior value-bridge run on this session. Savings delta is entered as %
            (e.g. 15 = +15%).
          </p>

          {showBridgeCta && (
            <Alert variant="info" title="Value bridge required">
              <p className="mb-2">
                Run the value-bridge calculator on this session before modeling what-if scenarios.
              </p>
              {onRequestValueBridge && (
                <button
                  type="button"
                  className="rounded bg-brand-primary px-3 py-1.5 text-sm text-white"
                  onClick={onRequestValueBridge}
                >
                  Run value bridge
                </button>
              )}
            </Alert>
          )}

          <div className="rounded border border-brand-border p-2 space-y-2">
            <label className="block text-xs font-medium text-brand-muted">
              Describe your scenario in plain language
              <div className="mt-1 flex gap-2">
                <input
                  className="flex-1 rounded border border-brand-border bg-brand-surface px-2 py-1.5 text-sm"
                  placeholder="e.g. logistics savings drop 20%, timeline slips 1.5x, high bounce-back"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void parseQuestion();
                  }}
                />
                <button
                  type="button"
                  disabled={parsing || !question.trim()}
                  className="rounded bg-brand-primary px-3 py-1.5 text-sm text-white disabled:opacity-50"
                  onClick={() => void parseQuestion()}
                >
                  {parsing ? 'Parsing…' : 'Parse'}
                </button>
              </div>
            </label>
            {parseSource && (
              <span
                className={`inline-block rounded border px-2 py-0.5 text-xs ${
                  parseSource === 'llm'
                    ? 'bg-amber-100 text-amber-800 border-amber-300'
                    : 'bg-emerald-100 text-emerald-800 border-emerald-300'
                }`}
              >
                {parseSource === 'llm'
                  ? 'Parsed by LLM — review before running'
                  : 'Rule-based parse — review carefully'}
              </span>
            )}
            {parseWarnings.length > 0 && (
              <Alert variant="warning" title="Parse notes" onDismiss={() => setParseWarnings([])}>
                <ul className="list-disc pl-4">
                  {parseWarnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </Alert>
            )}
            {drivers.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs text-brand-muted">
                  Portfolio driver overrides (fractional, e.g. 0.6 = 60% execution):
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {drivers.map((d, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 rounded border border-brand-border bg-brand-surface px-1.5 py-0.5 text-xs"
                    >
                      <code>{d.key}</code>
                      <input
                        className="w-14 rounded border border-brand-border px-1 text-xs"
                        value={d.value}
                        onChange={(e) =>
                          setDrivers((prev) =>
                            prev.map((p, j) => (j === i ? { ...p, value: e.target.value } : p)),
                          )
                        }
                      />
                      <button
                        type="button"
                        className="text-red-600"
                        onClick={() => setDrivers((prev) => prev.filter((_, j) => j !== i))}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

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
                  list={row.target === 'lever' ? 'whatif-known-levers' : 'whatif-known-categories'}
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
              <div className="md:col-span-6 space-y-2">
                <button
                  type="button"
                  className="text-xs text-brand-primary"
                  onClick={() =>
                    setAdvancedOpen((prev) => ({ ...prev, [idx]: !prev[idx] }))
                  }
                >
                  {advancedOpen[idx] ? '▾ Advanced' : '▸ Advanced'}
                </button>
                {advancedOpen[idx] && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <label className="block text-xs">
                      <span className="text-brand-muted">Spend pool Δ (%)</span>
                      <input
                        type="number"
                        className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                        value={row.spend_pool_delta_pct}
                        onChange={(e) =>
                          updateRow(idx, { spend_pool_delta_pct: e.target.value })
                        }
                      />
                    </label>
                    <label className="block text-xs">
                      <span className="text-brand-muted">Addressable Δ (%)</span>
                      <input
                        type="number"
                        className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                        value={row.addressable_spend_delta_pct}
                        onChange={(e) =>
                          updateRow(idx, { addressable_spend_delta_pct: e.target.value })
                        }
                      />
                    </label>
                    <label className="block text-xs">
                      <span className="text-brand-muted">Bounce-back</span>
                      <select
                        className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm"
                        value={row.bounce_back_override}
                        onChange={(e) =>
                          updateRow(idx, {
                            bounce_back_override: e.target
                              .value as CustomScenarioRow['bounce_back_override'],
                          })
                        }
                      >
                        <option value="">auto</option>
                        <option value="high">high</option>
                        <option value="medium">medium</option>
                        <option value="low">low</option>
                      </select>
                    </label>
                    <label className="block text-xs">
                      <span className="text-brand-muted">Cost drivers (k=v, fractional)</span>
                      <input
                        className="mt-0.5 w-full px-2 py-1 rounded border border-brand-border text-sm font-mono"
                        value={row.cost_driver_deltas}
                        onChange={(e) =>
                          updateRow(idx, { cost_driver_deltas: e.target.value })
                        }
                        placeholder="supplier_price_inflation_pct=0.05"
                      />
                    </label>
                  </div>
                )}
              </div>
              <button
                type="button"
                className="text-xs text-red-600 md:col-span-6 text-left"
                onClick={() => removeRow(idx)}
              >
                Remove
              </button>
            </div>
          ))}
          <datalist id="whatif-known-categories">
            {knownCategories.map((c) => (
              <option key={c.category_id} value={c.category_id}>
                {c.category_name}
              </option>
            ))}
          </datalist>
          <datalist id="whatif-known-levers">
            {knownLevers.map((l) => (
              <option key={l.lever_id} value={l.lever_id}>
                {l.lever_name}
              </option>
            ))}
          </datalist>
          <div className="flex flex-wrap gap-2 items-center">
            <button type="button" className="text-sm text-brand-primary" onClick={addRow}>
              + Add scenario
            </button>
            <button
              type="button"
              disabled={loading || showBridgeCta}
              className="rounded bg-brand-primary px-3 py-1.5 text-sm text-white disabled:opacity-50"
              onClick={() => void runSensitivity()}
            >
              {loading ? 'Running…' : 'Run sensitivity'}
            </button>
            <input
              className="rounded border border-brand-border bg-brand-surface px-2 py-1.5 text-sm"
              placeholder="Save set as…"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
            />
            <button
              type="button"
              disabled={!saveName.trim()}
              className="rounded border border-brand-border px-3 py-1.5 text-sm disabled:opacity-50"
              onClick={() => void saveSet()}
            >
              Save set
            </button>
          </div>

          {savedSets.length > 0 && (
            <details className="text-xs" open>
              <summary className="cursor-pointer font-medium text-brand-muted">
                Saved scenario sets ({savedSets.length})
              </summary>
              <ul className="mt-1 divide-y divide-brand-border/50 rounded border border-brand-border">
                {savedSets.map((s) => (
                  <li key={s.set_id} className="flex items-center gap-2 px-2 py-1.5">
                    <button
                      type="button"
                      className="flex-1 text-left hover:underline"
                      title={s.description || `${s.scenarios.length} scenarios`}
                      onClick={() => loadSet(s)}
                    >
                      {s.name}
                    </button>
                    <button
                      type="button"
                      className="text-brand-primary hover:underline"
                      onClick={() => loadSet(s)}
                    >
                      Load
                    </button>
                    <button
                      type="button"
                      className="text-red-600 hover:underline"
                      onClick={() => void deleteSet(s.set_id)}
                    >
                      delete
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {loading && <Loader label="Computing scenarios…" />}
          {result && (
            <>
              {result.narrative && (
                <div className="text-xs text-brand-ink border border-brand-border rounded p-2 whitespace-pre-wrap prose prose-sm max-w-none">
                  {result.narrative}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {comparisonChart && (
                  <div className="flex gap-1">
                    {(['table', 'chart'] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        className={`rounded px-2 py-1 border ${
                          view === v
                            ? 'bg-brand-primary text-white border-brand-primary'
                            : 'border-brand-border text-brand-muted'
                        }`}
                        onClick={() => setView(v)}
                      >
                        {v === 'table' ? 'Table' : 'Chart'}
                      </button>
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  className="rounded border border-brand-border px-2 py-0.5"
                  onClick={() => void handleCopy()}
                >
                  {copyStatus ?? 'Copy TSV'}
                </button>
                <button
                  type="button"
                  className="rounded border border-brand-border px-2 py-0.5"
                  onClick={() =>
                    downloadTextFile('whatif_results.csv', toCsv(exportColumns, exportRows()))
                  }
                >
                  Download CSV
                </button>
              </div>
              {comparisonChart && view === 'chart' ? (
                <div className="rounded border border-brand-border p-2">
                  <DynamicChart spec={comparisonChart} currency={currency} />
                </div>
              ) : (
                <div className="overflow-auto max-h-80 border border-brand-border rounded">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-brand-surface-elevated text-left">
                        <th className="px-2 py-1">Scenario</th>
                        <th className="px-2 py-1">3yr savings</th>
                        <th className="px-2 py-1">Δ vs base</th>
                        <th className="px-2 py-1">NPV (after tax)</th>
                        <th className="px-2 py-1">Δ NPV vs base</th>
                        <th className="px-2 py-1">Months</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleScenarios.map((s) => {
                        const isBase = s.name === 'base';
                        return (
                          <tr
                            key={s.name}
                            className={`border-t border-brand-border/50 ${
                              isBase ? 'text-brand-muted italic' : ''
                            }`}
                          >
                            <td className="px-2 py-1 font-medium">
                              {s.name}
                              {isBase ? ' (reference)' : ''}
                            </td>
                            <td className="px-2 py-1">
                              {formatCr(s.savings_3yr, { currency })}
                            </td>
                            <td className="px-2 py-1">
                              {baseScenario && !isBase
                                ? fmtDelta(s.savings_3yr, baseScenario.savings_3yr)
                                : '—'}
                            </td>
                            <td className="px-2 py-1">
                              {formatCr(s.npv_aftertax, { currency })}
                            </td>
                            <td className="px-2 py-1">
                              {baseScenario && !isBase
                                ? fmtDelta(s.npv_aftertax, baseScenario.npv_aftertax)
                                : '—'}
                            </td>
                            <td className="px-2 py-1">{s.timeline_months}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};
