import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert } from '../../Common/Alert';
import { Button } from '../../Common/Button';
import { Card } from '../../Common/Card';
import { Loader } from '../../Common/Loader';
import { apiGet, apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import type {
  DeepResearchSource,
  DeepResearchStartResponse,
  DeepResearchStatusResponse,
} from '../../../types';

type Phase = 'idle' | 'starting' | 'polling' | 'done' | 'failed';

const POLL_INTERVAL_MS = 30_000;

interface Props {
  companyName: string;
  industry: string;
  revenueCr: number;
  sessionId?: string | null;
  onSummaryReady: (summary: string) => void;
}

export const DeepResearchSection: React.FC<Props> = ({
  companyName,
  industry,
  revenueCr,
  sessionId,
  onSummaryReady,
}) => {
  const [phase, setPhase] = useState<Phase>('idle');
  const [interactionId, setInteractionId] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [fullReport, setFullReport] = useState<string | null>(null);
  const [sources, setSources] = useState<DeepResearchSource[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedToSession, setSavedToSession] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handlePollResult = useCallback(
    (data: DeepResearchStatusResponse) => {
      if (data.status === 'completed') {
        stopPolling();
        setSummary(data.summary ?? null);
        setFullReport(data.full_report ?? null);
        setSources(data.sources ?? []);
        setPhase('done');
        if (data.summary) {
          onSummaryReady(data.summary);
          setSavedToSession(!!sessionId);
        }
      } else if (data.status === 'failed') {
        stopPolling();
        setError('Deep research job failed. Please try again.');
        setPhase('failed');
      }
      // in_progress: keep polling
    },
    [stopPolling, onSummaryReady, sessionId],
  );

  const pollOnce = useCallback(
    async (id: string) => {
      try {
        const sessionParam = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
        const data = await apiGet<DeepResearchStatusResponse>(
          `/api/v1/diagnostic/deep-research/${id}${sessionParam}`,
        );
        handlePollResult(data);
      } catch (err) {
        stopPolling();
        setError(getApiErrorMessage(err));
        setPhase('failed');
      }
    },
    [sessionId, handlePollResult, stopPolling],
  );

  const startPolling = useCallback(
    (id: string) => {
      setPhase('polling');
      // Immediate first poll after a short delay to catch fast completions
      setTimeout(() => pollOnce(id), 5_000);
      pollRef.current = setInterval(() => pollOnce(id), POLL_INTERVAL_MS);
    },
    [pollOnce],
  );

  const handleStart = async () => {
    if (!companyName.trim()) return;
    setError(null);
    setPhase('starting');
    try {
      const res = await apiPost<DeepResearchStartResponse>(
        '/api/v1/diagnostic/deep-research',
        {
          company_name: companyName,
          industry,
          annual_revenue_cr: revenueCr,
          session_id: sessionId ?? null,
        },
      );
      setInteractionId(res.interaction_id);
      startPolling(res.interaction_id);
    } catch (err) {
      setError(getApiErrorMessage(err));
      setPhase('failed');
    }
  };

  const handleRetry = () => {
    setPhase('idle');
    setError(null);
    setInteractionId(null);
    setSummary(null);
    setFullReport(null);
    setSources([]);
    setSavedToSession(false);
  };

  return (
    <Card title="Deep Research (Google)" className="border-brand-border bg-white">
      {phase === 'idle' && (
        <div className="space-y-3">
          <p className="text-sm text-brand-muted">
            Run Google&apos;s agentic Deep Research on{' '}
            <span className="font-medium text-brand-ink">{companyName}</span> to surface
            independent benchmark data, cost-reduction levers, and peer comparisons. Results are
            saved to your session as analysis context.
          </p>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2.5 py-0.5 text-xs text-amber-800 font-medium">
              ~$1–3 per run
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 border border-blue-200 px-2.5 py-0.5 text-xs text-blue-800 font-medium">
              up to 20 min
            </span>
          </div>
          <Button onClick={handleStart} className="w-full sm:w-auto">
            Run Deep Research
          </Button>
        </div>
      )}

      {(phase === 'starting' || phase === 'polling') && (
        <div className="space-y-3">
          <Loader
            label={
              phase === 'starting'
                ? 'Submitting research job…'
                : 'Deep research in progress — checking every 30 s…'
            }
          />
          <p className="text-xs text-brand-muted">
            Google&apos;s agentic research API performs multi-step web research. This may take up
            to 20 minutes. You can keep this page open or come back later — the job runs in the
            background.
          </p>
          {interactionId && (
            <p className="text-xs text-brand-muted font-mono">Job ID: {interactionId}</p>
          )}
        </div>
      )}

      {phase === 'failed' && (
        <div className="space-y-3">
          <Alert variant="error" title="Deep research failed" onDismiss={handleRetry}>
            {error ?? 'An unexpected error occurred.'}
          </Alert>
          <Button onClick={handleRetry} className="w-full sm:w-auto">
            Try again
          </Button>
        </div>
      )}

      {phase === 'done' && summary && (
        <div className="space-y-4">
          {/* Summary — always visible */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-sm font-semibold text-brand-ink">Research Summary</h4>
              <div className="flex items-center gap-2">
                {savedToSession && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-green-50 border border-green-200 px-2.5 py-0.5 text-xs text-green-800 font-medium">
                    ✓ Saved to session
                  </span>
                )}
              </div>
            </div>
            <p className="text-sm text-brand-ink leading-relaxed whitespace-pre-wrap">{summary}</p>
          </div>

          {/* Full report — expandable */}
          {fullReport && (
            <div>
              <button
                onClick={() => setExpanded((v) => !v)}
                className="text-sm font-medium text-brand-navy hover:text-brand-green flex items-center gap-1"
              >
                <span>{expanded ? '▲' : '▼'}</span>
                {expanded ? 'Collapse full report' : 'Expand full report'}
              </button>
              {expanded && (
                <div className="mt-3 max-h-96 overflow-y-auto rounded-md border border-brand-border bg-gray-50 p-4">
                  <pre className="text-xs text-brand-ink whitespace-pre-wrap font-sans leading-relaxed">
                    {fullReport}
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* Sources */}
          {sources.length > 0 && (
            <div>
              <button
                onClick={() => setSourcesExpanded((v) => !v)}
                className="text-sm font-medium text-brand-navy hover:text-brand-green flex items-center gap-1"
              >
                <span>{sourcesExpanded ? '▲' : '▼'}</span>
                {sourcesExpanded ? 'Hide sources' : `Show ${sources.length} sources`}
              </button>
              {sourcesExpanded && (
                <ul className="mt-2 space-y-1">
                  {sources.map((s, i) => (
                    <li key={i} className="text-xs text-brand-muted">
                      {s.url ? (
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-navy hover:underline"
                        >
                          {s.title || s.url}
                        </a>
                      ) : (
                        s.title || '(no title)'
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </Card>
  );
};
