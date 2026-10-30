import React, { useCallback, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import { useSession } from '../../../context/SessionContext';
import { useToast } from '../../../context/ToastContext';
import { workbenchKeys } from '../../../api/queryKeys';
import {
  useDeleteSavedQuery,
  useQueryHistory,
  useSaveQuery,
  useSavedQueries,
  useSpendSchema,
} from '../../../api/hooks/useWorkbenchPanelQueries';
import { Loader } from '../../Common/Loader';
import { Alert } from '../../Common/Alert';
import { DynamicChart } from '../Procurement/DynamicChart';
import { SchemaExplorer } from './SchemaExplorer';
import { ResultsTable } from './ResultsTable';
import type { ChartSpec } from '../../../types';
import { useConfirm } from '../../../hooks/useConfirm';

interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

interface Nl2SqlResponse {
  question: string;
  sql: string | null;
  source: 'rules' | 'llm' | 'unavailable';
  result: QueryResult | null;
  repair_trace: { sql: string; error: string }[];
  sql_attempts: number;
  chart: ChartSpec | null;
  error?: string;
}

interface QueryPanelProps {
  sessionId: string | null;
  currency: string;
}

const DEFAULT_SQL =
  'SELECT category_name, SUM(amount) AS spend, COUNT(*) AS lines\nFROM spend\nGROUP BY category_name\nORDER BY spend DESC\nLIMIT 25';

const FALLBACK_DIMENSIONS = [
  'category_name',
  'supplier',
  'business_unit',
  'gl_code',
  'cost_center_id',
  'period',
];

const AUTORUN_KEY = 'opex.nl2sql.autorun';

const SOURCE_BADGES: Record<string, { label: string; className: string }> = {
  llm: {
    label: 'LLM',
    className: 'bg-amber-100 text-amber-800 border-amber-300',
  },
  rules: {
    label: 'Rules',
    className: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  },
  unavailable: {
    label: 'Unavailable',
    className: 'bg-brand-surface text-brand-muted border-brand-border',
  },
  manual: {
    label: 'Manual',
    className: 'bg-brand-surface text-brand-muted border-brand-border',
  },
};

const TEXTUAL_TYPES = /varchar|string|text|char|enum|category/i;

function relativeTime(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return iso;
  const sec = Math.round((Date.now() - t) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function triggerDownload(url: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export const QueryPanel: React.FC<QueryPanelProps> = ({ sessionId, currency }) => {
  const { engagementId } = useSession();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const sqlRef = useRef<HTMLTextAreaElement>(null);

  const schemaQuery = useSpendSchema(sessionId);
  const historyQuery = useQueryHistory(sessionId);
  const savedQuery = useSavedQueries(sessionId);
  const saveMutation = useSaveQuery(sessionId);
  const deleteMutation = useDeleteSavedQuery(sessionId);

  const schema = schemaQuery.data ?? null;
  const saved = savedQuery.data ?? [];
  const history = historyQuery.data ?? [];

  const [sql, setSql] = useState(DEFAULT_SQL);
  const [groupBy, setGroupBy] = useState('category_name');
  const [metric, setMetric] = useState('SUM(amount)');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [chart, setChart] = useState<ChartSpec | null>(null);
  const [view, setView] = useState<'table' | 'chart'>('table');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [question, setQuestion] = useState('');
  const [nlLoading, setNlLoading] = useState(false);
  const [nlSource, setNlSource] = useState<Nl2SqlResponse['source'] | null>(null);
  const [nlUnavailable, setNlUnavailable] = useState(false);
  const [repairTrace, setRepairTrace] = useState<{ sql: string; error: string }[]>([]);
  const [autoRun, setAutoRun] = useState(() => localStorage.getItem(AUTORUN_KEY) !== 'off');
  const [saveName, setSaveName] = useState('');

  const refreshHistory = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: workbenchKeys.queryHistory(sessionId) });
  }, [queryClient, sessionId]);

  const insertAtCursor = useCallback((text: string) => {
    const el = sqlRef.current;
    if (!el) {
      setSql((prev) => (prev ? `${prev}\n${text}` : text));
      return;
    }
    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? start;
    const next = el.value.slice(0, start) + text + el.value.slice(end);
    setSql(next);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + text.length;
      el.setSelectionRange(pos, pos);
    });
  }, []);

  const buildGroupSql = useCallback(() => {
    const dim = groupBy.trim() || 'category_name';
    const agg = metric.trim() || 'SUM(amount)';
    return `SELECT ${dim}, ${agg} AS value\nFROM spend\nGROUP BY ${dim}\nORDER BY value DESC\nLIMIT 50`;
  }, [groupBy, metric]);

  const runQuery = async (text?: string) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await apiPost<QueryResult & { session_id: string; chart: ChartSpec | null }>(
        `/api/v1/query/${sessionId}?chart=true`,
        { sql: text ?? sql, limit: 500 },
      );
      setResult(data);
      setChart(data.chart ?? null);
      if (!data.chart) setView('table');
      refreshHistory();
      toast(`Query returned ${data.row_count} rows`);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const generateFromQuestion = async () => {
    if (!sessionId || !question.trim()) return;
    setNlLoading(true);
    setError(null);
    setNlUnavailable(false);
    setRepairTrace([]);
    try {
      const data = await apiPost<Nl2SqlResponse>(`/api/v1/query/${sessionId}/nl2sql`, {
        question: question.trim(),
        execute: autoRun,
      });
      setNlSource(data.source);
      if (data.source === 'unavailable' || !data.sql) {
        setNlUnavailable(true);
        return;
      }
      setSql(data.sql);
      setRepairTrace(data.repair_trace ?? []);
      if (data.result) {
        setResult(data.result);
        setChart(data.chart ?? null);
        if (!data.chart) setView('table');
        refreshHistory();
        toast('NL→SQL executed');
      } else {
        toast('SQL generated — review before running', 'info');
      }
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setNlLoading(false);
    }
  };

  const saveCurrentQuery = async () => {
    if (!sessionId || !saveName.trim()) return;
    try {
      await saveMutation.mutateAsync({
        name: saveName.trim(),
        sql,
        description: question.trim() || undefined,
      });
      setSaveName('');
      toast('Query saved');
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  };

  const [confirm, confirmDialog] = useConfirm();

  const deleteSaved = async (queryId: string) => {
    if (!sessionId) return;
    const ok = await confirm({
      title: 'Delete saved query?',
      message: 'This saved query will be permanently deleted.',
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteMutation.mutateAsync(queryId);
      toast('Saved query deleted', 'info');
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  };

  const dimensionOptions = useMemo(() => {
    if (!schema?.columns?.length) return FALLBACK_DIMENSIONS;
    const fromSchema = schema.columns
      .filter(
        (c) =>
          TEXTUAL_TYPES.test(c.type) ||
          (schema.sample_values[c.name] && schema.sample_values[c.name].length > 0),
      )
      .map((c) => c.name);
    return fromSchema.length > 0 ? fromSchema : FALLBACK_DIMENSIONS;
  }, [schema]);

  const exportFullDataset = (
    mode: 'all' | 'sql',
    fmt: 'csv' | 'xlsx' | 'parquet' = 'csv',
  ) => {
    if (!engagementId || !sessionId) return;
    const params = new URLSearchParams({
      session_id: sessionId,
      fmt,
    });
    if (mode === 'sql' && sql.trim()) {
      params.set('sql', sql.trim());
    }
    triggerDownload(`/api/v1/engagements/${engagementId}/export?${params.toString()}`);
    toast(`Export started (${fmt.toUpperCase()})`, 'info');
  };

  if (!sessionId) {
    return <p className="text-sm text-brand-muted">Select a session to run queries.</p>;
  }

  return (
    <div className="space-y-4">
      {confirmDialog}
      {schemaQuery.isLoading && <Loader label="Loading schema…" />}
      {schema && (
        <p className="text-xs text-brand-muted">
          {schema.line_count.toLocaleString()} lines · total spend{' '}
          {schema.total_spend.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </p>
      )}
      {(error || schemaQuery.isError) && (
        <Alert variant="error" title="Query failed" onDismiss={() => setError(null)}>
          {error || getApiErrorMessage(schemaQuery.error)}
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-4">
        <aside className="rounded border border-brand-border p-2 max-h-[640px] overflow-auto">
          {schema ? (
            <SchemaExplorer schema={schema} onInsert={insertAtCursor} />
          ) : (
            <p className="text-xs text-brand-muted">Schema loads with the session.</p>
          )}
        </aside>

        <div className="space-y-4 min-w-0">
          <div className="rounded border border-brand-border p-3 space-y-2">
            <label className="block text-xs font-medium text-brand-muted">
              Ask in plain language
              <div className="mt-1 flex gap-2">
                <input
                  className="flex-1 rounded border border-brand-border bg-brand-surface px-3 py-1.5 text-sm"
                  placeholder="e.g. top 10 suppliers by spend in Facilities"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void generateFromQuestion();
                  }}
                />
                <button
                  type="button"
                  disabled={nlLoading || !question.trim()}
                  className="rounded bg-brand-primary px-3 py-1.5 text-sm text-white disabled:opacity-50"
                  onClick={() => void generateFromQuestion()}
                >
                  {nlLoading ? 'Generating…' : 'Generate SQL'}
                </button>
              </div>
            </label>
            <div className="flex items-center gap-3 text-xs">
              <label className="flex items-center gap-1.5 text-brand-muted">
                <input
                  type="checkbox"
                  checked={autoRun}
                  onChange={(e) => {
                    setAutoRun(e.target.checked);
                    localStorage.setItem(AUTORUN_KEY, e.target.checked ? 'on' : 'off');
                  }}
                />
                Auto-run generated SQL
              </label>
              {nlSource && !nlUnavailable && (
                <span
                  className={`rounded border px-2 py-0.5 ${
                    SOURCE_BADGES[nlSource]?.className ?? SOURCE_BADGES.manual.className
                  }`}
                >
                  {SOURCE_BADGES[nlSource]?.label ?? nlSource}
                </span>
              )}
            </div>
            {nlUnavailable && (
              <Alert variant="info" title="Natural-language SQL needs an LLM provider">
                No LLM is configured (or the question is too complex for the rule-based
                translator). Use the builder or write SQL below.
              </Alert>
            )}
            {repairTrace.length > 0 && (
              <details className="text-xs text-brand-muted">
                <summary className="cursor-pointer">
                  Repair trace ({repairTrace.length} failed attempt
                  {repairTrace.length > 1 ? 's' : ''})
                </summary>
                <ul className="mt-1 space-y-1">
                  {repairTrace.map((t, i) => (
                    <li key={i} className="rounded bg-brand-surface p-2">
                      <code className="block whitespace-pre-wrap">{t.sql}</code>
                      <span className="text-red-600">{t.error}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
            <label className="text-xs text-brand-muted block">
              Group by
              <select
                className="mt-1 w-full rounded border border-brand-border bg-brand-surface px-2 py-1.5 text-sm"
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value)}
              >
                {dimensionOptions.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-brand-muted block md:col-span-2">
              Metric
              <input
                className="mt-1 w-full rounded border border-brand-border bg-brand-surface px-2 py-1.5 text-sm font-mono"
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="rounded bg-brand-primary px-3 py-1.5 text-sm text-white"
              onClick={() => {
                const built = buildGroupSql();
                setSql(built);
                void runQuery(built);
              }}
            >
              Build &amp; run
            </button>
          </div>

          <label className="block text-xs font-medium text-brand-muted">
            SQL (read-only SELECT on view <code className="text-brand-text">spend</code>)
            <textarea
              ref={sqlRef}
              className="mt-1 w-full min-h-[120px] rounded border border-brand-border bg-brand-surface px-3 py-2 font-mono text-sm"
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              spellCheck={false}
            />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={loading}
              className="rounded bg-brand-primary px-4 py-2 text-sm text-white disabled:opacity-50"
              onClick={() => void runQuery()}
            >
              {loading ? 'Running…' : 'Run query'}
            </button>
            <input
              className="rounded border border-brand-border bg-brand-surface px-2 py-1.5 text-sm"
              placeholder="Save as…"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
            />
            <button
              type="button"
              disabled={!saveName.trim()}
              className="rounded border border-brand-border px-3 py-1.5 text-sm disabled:opacity-50"
              onClick={() => void saveCurrentQuery()}
            >
              Save query
            </button>
            {engagementId && (
              <>
                <button
                  type="button"
                  className="rounded border border-brand-border px-3 py-1.5 text-sm"
                  title="Export all spend lines as CSV"
                  onClick={() => exportFullDataset('all', 'csv')}
                >
                  Export CSV
                </button>
                <button
                  type="button"
                  className="rounded border border-brand-border px-3 py-1.5 text-sm"
                  title="Export all spend lines as Excel"
                  onClick={() => exportFullDataset('all', 'xlsx')}
                >
                  Export XLSX
                </button>
                <button
                  type="button"
                  className="rounded border border-brand-border px-3 py-1.5 text-sm"
                  title="Export all spend lines as Parquet"
                  onClick={() => exportFullDataset('all', 'parquet')}
                >
                  Export Parquet
                </button>
                <button
                  type="button"
                  className="rounded border border-brand-border px-3 py-1.5 text-sm"
                  title="Export current SQL result set (full, not capped)"
                  onClick={() => exportFullDataset('sql', 'csv')}
                >
                  Export current SQL
                </button>
              </>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {saved.length > 0 && (
              <details className="text-xs" open>
                <summary className="cursor-pointer font-medium text-brand-muted">
                  Saved queries ({saved.length})
                </summary>
                <ul className="mt-1 divide-y divide-brand-border/50 rounded border border-brand-border">
                  {saved.map((q) => (
                    <li key={q.query_id} className="flex items-center gap-2 px-2 py-1.5">
                      <button
                        type="button"
                        className="flex-1 text-left hover:underline"
                        title={q.description || q.sql}
                        onClick={() => setSql(q.sql)}
                      >
                        {q.name}
                      </button>
                      <button
                        type="button"
                        className="text-red-600 hover:underline"
                        onClick={() => void deleteSaved(q.query_id)}
                      >
                        delete
                      </button>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {history.length > 0 && (
              <details className="text-xs" open>
                <summary className="cursor-pointer font-medium text-brand-muted">
                  History ({history.length})
                </summary>
                <ul className="mt-1 divide-y divide-brand-border/50 rounded border border-brand-border max-h-48 overflow-auto">
                  {history.map((h) => {
                    const badge =
                      SOURCE_BADGES[h.source] ?? SOURCE_BADGES.manual;
                    return (
                      <li key={h.history_id} className="px-2 py-1.5 space-y-1">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`rounded border px-1.5 py-0.5 text-[10px] ${badge.className}`}
                          >
                            {badge.label}
                          </span>
                          <span className="text-brand-muted">
                            {h.row_count} rows · {h.elapsed_ms.toFixed(0)} ms ·{' '}
                            {relativeTime(h.executed_at)}
                          </span>
                        </div>
                        <p
                          className="font-mono truncate"
                          title={h.question ? `${h.question}\n\n${h.sql}` : h.sql}
                        >
                          {h.sql}
                        </p>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            className="text-brand-primary hover:underline"
                            onClick={() => setSql(h.sql)}
                          >
                            Load
                          </button>
                          <button
                            type="button"
                            className="text-brand-primary hover:underline"
                            onClick={() => {
                              setSql(h.sql);
                              void runQuery(h.sql);
                            }}
                          >
                            Re-run
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </details>
            )}
          </div>

          {result && (
            <div className="space-y-2">
              {chart && (
                <div className="flex gap-1 text-xs">
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
              {chart && view === 'chart' ? (
                <div className="rounded border border-brand-border p-2">
                  <DynamicChart spec={chart} currency={currency} />
                </div>
              ) : (
                <ResultsTable result={result} currency={currency} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
