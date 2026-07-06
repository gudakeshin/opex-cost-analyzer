import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { apiDelete, apiGet, apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import { Loader } from '../../Common/Loader';
import { Alert } from '../../Common/Alert';
import { DynamicChart } from '../Procurement/DynamicChart';
import type { ChartSpec } from '../../../types';

interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}

interface SpendSchema {
  columns: { name: string; type: string }[];
  sample_values: Record<string, string[]>;
  line_count: number;
  total_spend: number;
  views: Record<string, string>;
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

interface SavedQuery {
  query_id: string;
  name: string;
  sql: string;
  description: string;
  saved_at: string;
}

interface QueryPanelProps {
  sessionId: string | null;
}

const DEFAULT_SQL =
  'SELECT category_name, SUM(amount) AS spend, COUNT(*) AS lines\nFROM spend\nGROUP BY category_name\nORDER BY spend DESC\nLIMIT 25';

const AUTORUN_KEY = 'opex.nl2sql.autorun';

const SOURCE_BADGES: Record<Nl2SqlResponse['source'], { label: string; className: string }> = {
  llm: {
    label: 'LLM-generated — review before running',
    className: 'bg-amber-100 text-amber-800 border-amber-300',
  },
  rules: {
    label: 'Rule-based (deterministic)',
    className: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  },
  unavailable: { label: 'Unavailable', className: 'bg-brand-surface text-brand-muted border-brand-border' },
};

export const QueryPanel: React.FC<QueryPanelProps> = ({ sessionId }) => {
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [groupBy, setGroupBy] = useState('category_name');
  const [metric, setMetric] = useState('SUM(amount)');
  const [schema, setSchema] = useState<SpendSchema | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [chart, setChart] = useState<ChartSpec | null>(null);
  const [view, setView] = useState<'table' | 'chart'>('table');
  const [loading, setLoading] = useState(false);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [question, setQuestion] = useState('');
  const [nlLoading, setNlLoading] = useState(false);
  const [nlSource, setNlSource] = useState<Nl2SqlResponse['source'] | null>(null);
  const [nlUnavailable, setNlUnavailable] = useState(false);
  const [repairTrace, setRepairTrace] = useState<{ sql: string; error: string }[]>([]);
  const [autoRun, setAutoRun] = useState(() => localStorage.getItem(AUTORUN_KEY) !== 'off');

  const [saved, setSaved] = useState<SavedQuery[]>([]);
  const [saveName, setSaveName] = useState('');

  const loadSaved = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await apiGet<{ queries: SavedQuery[] }>(`/api/v1/query/${sessionId}/saved`);
      setSaved(data.queries ?? []);
    } catch {
      // saved queries are a convenience — never block the panel on them
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      setSchemaLoading(true);
      try {
        const data = await apiGet<SpendSchema>(`/api/v1/query/${sessionId}/schema`);
        if (!cancelled) setSchema(data);
      } catch (e) {
        if (!cancelled) setError(getApiErrorMessage(e));
      } finally {
        if (!cancelled) setSchemaLoading(false);
      }
    })();
    void loadSaved();
    return () => {
      cancelled = true;
    };
  }, [sessionId, loadSaved]);

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
      await apiPost(`/api/v1/query/${sessionId}/saved`, {
        name: saveName.trim(),
        sql,
        description: question.trim() || undefined,
      });
      setSaveName('');
      void loadSaved();
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  };

  const deleteSaved = async (queryId: string) => {
    if (!sessionId) return;
    try {
      await apiDelete(`/api/v1/query/${sessionId}/saved/${queryId}`);
      void loadSaved();
    } catch (e) {
      setError(getApiErrorMessage(e));
    }
  };

  const dimensionOptions = useMemo(
    () => [
      'category_name',
      'supplier',
      'business_unit',
      'gl_code',
      'cost_center_id',
      'period',
    ],
    [],
  );

  if (!sessionId) {
    return <p className="text-sm text-brand-muted">Select a session to run queries.</p>;
  }

  return (
    <div className="space-y-4">
      {schemaLoading && <Loader label="Loading schema…" />}
      {schema && (
        <p className="text-xs text-brand-muted">
          {schema.line_count.toLocaleString()} lines · total spend{' '}
          {schema.total_spend.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </p>
      )}
      {error && (
        <Alert variant="error" title="Query failed" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

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
            <span className={`rounded border px-2 py-0.5 ${SOURCE_BADGES[nlSource].className}`}>
              {SOURCE_BADGES[nlSource].label}
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
              Repair trace ({repairTrace.length} failed attempt{repairTrace.length > 1 ? 's' : ''})
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
      </div>

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
              <DynamicChart spec={chart} currency="INR" />
            </div>
          ) : (
            <div className="overflow-auto max-h-[420px] border border-brand-border rounded">
              <p className="text-xs text-brand-muted px-2 py-1 border-b border-brand-border">
                {result.row_count} rows · {result.elapsed_ms.toFixed(0)} ms
                {result.truncated ? ' · truncated' : ''}
              </p>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-brand-surface-elevated text-left">
                    {result.columns.map((c) => (
                      <th key={c} className="px-2 py-1 font-medium whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <tr key={i} className="border-t border-brand-border/50">
                      {row.map((cell, j) => (
                        <td key={j} className="px-2 py-1 whitespace-nowrap font-mono text-xs">
                          {cell === null || cell === undefined ? '' : String(cell)}
                        </td>
                      ))}
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
