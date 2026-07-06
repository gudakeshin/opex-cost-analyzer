import React, { useEffect, useState } from 'react';
import { apiGet, apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import { useWorkbenchProgress } from '../../../api/hooks/useWorkbenchQueries';
import { Alert } from '../../Common/Alert';
import { Markdown } from '../../Common/Markdown';
import { AgentActivityPanel } from '../Procurement/AgentActivityPanel';
import { ThinkingBlock } from '../Procurement/ThinkingBlock';
import { DynamicChart } from '../Procurement/DynamicChart';
import type { ChartSpec } from '../../../types';

interface AgentTraceStep {
  tool: string;
  arguments?: Record<string, unknown>;
  ok?: boolean;
}

interface AnalystTurn {
  run_id: string;
  question: string;
  answer: string;
  available: boolean;
  agent_trace: AgentTraceStep[];
  charts: ChartSpec[];
  provenance: { prompt_hash: string; model_version: string; data_slice: string[] } | null;
  ts: string;
}

interface AnalystRunResponse extends Omit<AnalystTurn, 'ts'> {
  thinking: string | null;
  skills_run: string[];
  queries_run: { sql: string }[];
  fallback: {
    reason: string;
    nl_query_result: Record<string, unknown> | null;
  } | null;
}

interface AnalystPanelProps {
  sessionId: string | null;
}

export const AnalystPanel: React.FC<AnalystPanelProps> = ({ sessionId }) => {
  const [history, setHistory] = useState<AnalystTurn[]>([]);
  const [question, setQuestion] = useState('');
  const [runningRunId, setRunningRunId] = useState<string | null>(null);
  const [thinking, setThinking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFallback, setLastFallback] = useState<AnalystRunResponse['fallback']>(null);

  const progressQuery = useWorkbenchProgress(runningRunId, !!runningRunId);
  const steps = progressQuery.data?.steps as
    | { phase?: string; message?: string; status?: string }[]
    | undefined;

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await apiGet<{ turns: AnalystTurn[] }>(
          `/api/v1/analyst/${sessionId}/history`,
        );
        if (!cancelled) setHistory(data.turns ?? []);
      } catch {
        // history is a convenience — never block the panel on it
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const ask = async () => {
    if (!sessionId || !question.trim()) return;
    const runId = crypto.randomUUID();
    setRunningRunId(runId);
    setThinking(null);
    setError(null);
    setLastFallback(null);
    const q = question.trim();
    try {
      const data = await apiPost<AnalystRunResponse>(`/api/v1/analyst/${sessionId}/run`, {
        run_id: runId,
        question: q,
      });
      setThinking(data.thinking ?? null);
      setLastFallback(data.fallback);
      setHistory((prev) => [
        ...prev,
        {
          run_id: data.run_id,
          question: q,
          answer: data.answer,
          available: data.available,
          agent_trace: data.agent_trace,
          charts: data.charts,
          provenance: data.provenance,
          ts: new Date().toISOString(),
        },
      ]);
      setQuestion('');
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setRunningRunId(null);
    }
  };

  if (!sessionId) {
    return <p className="text-sm text-brand-muted">Select a session to ask the analyst.</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-brand-muted">
        Ask an open-ended question. The analyst investigates using spend queries, skills, and
        sensitivity modeling, and shows its work below each answer.
      </p>

      {error && (
        <Alert variant="error" title="Analyst run failed" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <div className="space-y-4 max-h-[520px] overflow-y-auto">
        {history.map((turn) => (
          <div key={turn.run_id} className="rounded border border-brand-border p-3 space-y-2">
            <p className="text-sm font-medium text-brand-ink">{turn.question}</p>
            {turn.available ? (
              <>
                <Markdown className="text-sm text-brand-ink">{turn.answer}</Markdown>
                {turn.charts?.map((c) => (
                  <div key={c.id} className="rounded border border-brand-border p-2">
                    <DynamicChart spec={c} currency="INR" />
                  </div>
                ))}
                {turn.agent_trace?.length > 0 && (
                  <details className="text-xs text-brand-muted">
                    <summary className="cursor-pointer">
                      How I got this ({turn.agent_trace.length} step
                      {turn.agent_trace.length > 1 ? 's' : ''})
                    </summary>
                    <ul className="mt-1 space-y-1">
                      {turn.agent_trace.map((t, i) => (
                        <li key={i} className="rounded bg-brand-surface p-2">
                          <code>{t.tool}</code>
                          {t.arguments && Object.keys(t.arguments).length > 0 && (
                            <pre className="mt-0.5 whitespace-pre-wrap text-[11px]">
                              {JSON.stringify(t.arguments)}
                            </pre>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {turn.provenance && (
                  <p className="text-[10px] text-brand-muted">
                    {turn.provenance.model_version} · hash {turn.provenance.prompt_hash}
                  </p>
                )}
              </>
            ) : (
              <Alert variant="info" title="Analyst agent unavailable">
                No LLM provider is configured for the agent loop — showing a deterministic
                query fallback instead of an investigated answer.
              </Alert>
            )}
          </div>
        ))}
      </div>

      {runningRunId && (
        <div className="rounded border border-brand-border p-3 space-y-2">
          <AgentActivityPanel steps={steps} runId={runningRunId} loading />
          {thinking && <ThinkingBlock thinking={thinking} live />}
        </div>
      )}

      {lastFallback && (
        <Alert variant="info" title={`Fallback: ${lastFallback.reason}`}>
          {lastFallback.nl_query_result ? (
            <pre className="text-[11px] whitespace-pre-wrap">
              {JSON.stringify(lastFallback.nl_query_result, null, 2)}
            </pre>
          ) : (
            'No deterministic fallback result available for this question.'
          )}
        </Alert>
      )}

      <div className="flex gap-2">
        <input
          className="flex-1 rounded border border-brand-border bg-brand-surface px-3 py-1.5 text-sm"
          placeholder="e.g. which suppliers are driving the facilities overrun, and what's the NPV if we consolidate?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !runningRunId) void ask();
          }}
        />
        <button
          type="button"
          disabled={!!runningRunId || !question.trim()}
          className="rounded bg-brand-primary px-4 py-2 text-sm text-white disabled:opacity-50"
          onClick={() => void ask()}
        >
          {runningRunId ? 'Investigating…' : 'Ask'}
        </button>
      </div>
    </div>
  );
};
