import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { apiGet, apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import { Loader } from '../../Common/Loader';
import { Alert } from '../../Common/Alert';

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

interface QueryPanelProps {
  sessionId: string | null;
}

const DEFAULT_SQL =
  'SELECT category_name, SUM(amount) AS spend, COUNT(*) AS lines\nFROM spend\nGROUP BY category_name\nORDER BY spend DESC\nLIMIT 25';

export const QueryPanel: React.FC<QueryPanelProps> = ({ sessionId }) => {
  const [sql, setSql] = useState(DEFAULT_SQL);
  const [groupBy, setGroupBy] = useState('category_name');
  const [metric, setMetric] = useState('SUM(amount)');
  const [schema, setSchema] = useState<SpendSchema | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

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
      const data = await apiPost<QueryResult & { session_id: string }>(
        `/api/v1/query/${sessionId}`,
        { sql: text ?? sql, limit: 500 },
      );
      setResult(data);
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setLoading(false);
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

      <div className="flex gap-2">
        <button
          type="button"
          disabled={loading}
          className="rounded bg-brand-primary px-4 py-2 text-sm text-white disabled:opacity-50"
          onClick={() => void runQuery()}
        >
          {loading ? 'Running…' : 'Run query'}
        </button>
      </div>

      {result && (
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
  );
};
