import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { Select } from '../components/Common/Select';
import { StructuredChatMessage } from '../components/PageComponents/Procurement/StructuredChatMessage';
import { InsightCards } from '../components/PageComponents/Procurement/InsightCards';
import { PlanApprovalModal } from '../components/PageComponents/Procurement/PlanApprovalModal';
import { ChatComposer } from '../components/PageComponents/Analysis/ChatComposer';
import { TrustRail } from '../components/Trust/TrustRail';
import { DeloitteLogo } from '../components/Brand/DeloitteLogo';
import { SECTOR_OPTIONS } from '../constants/sectors';
import { useSession } from '../context/SessionContext';
import { apiGet, apiPatch, apiPost, apiUpload, getApiErrorMessage } from '../hooks/useApi';
import { friendlyErrorMessage } from '../utils/errorMessages';
import { clearChatMessages, loadChatMessages, saveChatMessages } from '../utils/chatStorage';
import {
  buildAnalyzeCompleteContent,
  buildDataRootedPrompts,
  buildDeepDivePrompts,
  buildRestoredInsightMessage,
  buildWelcomePrompts,
  chatHasInsightSnapshot,
  extractInsightSnapshot,
  wantsPeerSavingsInsight,
} from '../utils/analysisInsights';
import type { ManifestFileEntry } from '../utils/sessionFiles';
import type {
  ChatMessage,
  ChatPlanPreview,
  ChatProgressResponse,
  EngagementMeta,
  ProgressStep,
  SessionManifest,
  SessionManifestPatch,
  SessionResponse,
  V1ChatResponse,
} from '../types';

const ANALYZE_PIPELINE_STEPS: ProgressStep[] = [
  { phase: 'act', message: 'Running spend-profiler…' },
  { phase: 'act', message: 'Running document-contextualizer & peer-benchmarker…' },
  { phase: 'act', message: 'Running heuristic-analyzer & root-cause-analyzer…' },
  { phase: 'act', message: 'Running savings-modeler & value-bridge-calculator…' },
  { phase: 'reflect', message: 'Validating outputs and persisting session…' },
];

function contextPayload(engagement: EngagementMeta): Record<string, unknown> {
  const body: Record<string, unknown> = {
    industry: engagement.industry || undefined,
    currency: engagement.currency,
  };
  if (engagement.company_name && engagement.company_name !== 'New engagement') {
    body.company_name = engagement.company_name;
  }
  if (engagement.annual_revenue_cr != null && engagement.annual_revenue_cr > 0) {
    body.annual_revenue = engagement.annual_revenue_cr * 10_000_000;
  }
  return body;
}

function filesToUploadMessages(files: ManifestFileEntry[]): ChatMessage[] {
  return files.map((f) => ({
    role: 'assistant' as const,
    content: `Uploaded **${f.name || 'file'}**. Ask a question or run full analysis when ready.`,
  }));
}

function progressStepsFromPoll(entry: ChatProgressResponse): ProgressStep[] {
  return (entry.steps ?? []).map((s) => ({
    phase: s.phase,
    message: s.message,
    status: entry.status,
  }));
}

async function pollChatProgress(
  runId: string,
  onSteps: (steps: ProgressStep[]) => void,
  signal: AbortSignal,
): Promise<void> {
  while (!signal.aborted) {
    try {
      const entry = await apiGet<ChatProgressResponse>(`/api/v1/chat/progress/${runId}`);
      if (entry.steps?.length) onSteps(progressStepsFromPoll(entry));
      if (
        entry.status === 'completed' ||
        entry.status === 'failed' ||
        entry.status === 'not_found'
      ) {
        break;
      }
    } catch {
      break;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

export const ProcurementAnalysis: React.FC = () => {
  const {
    sessionId,
    setSessionId,
    ensureSession,
    engagement,
    refreshEngagement,
    syncEngagementFromAnalysis,
    refreshAnalysisStatus,
  } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<SessionResponse | null>(null);
  const [manifest, setManifest] = useState<SessionManifest | null>(null);
  const [insightsOpen, setInsightsOpen] = useState(true);
  const [trustOpen, setTrustOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [planPreview, setPlanPreview] = useState<ChatPlanPreview | null>(null);
  const [pendingMessage, setPendingMessage] = useState('');
  const [lastRunId, setLastRunId] = useState<string | undefined>();
  const [lastSignals, setLastSignals] = useState<V1ChatResponse['quality_signals']>();
  const [lastSteps, setLastSteps] = useState<V1ChatResponse['progress_steps']>();
  const [agentSteps, setAgentSteps] = useState<ProgressStep[] | undefined>();
  const [agentDegraded, setAgentDegraded] = useState(false);
  const [pipelineLabel, setPipelineLabel] = useState<string | undefined>();
  const [sectorUpdating, setSectorUpdating] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollAbortRef = useRef<AbortController | null>(null);

  const refreshManifest = useCallback(async (sid: string) => {
    const m = await apiGet<SessionManifest>(`/api/v1/sessions/${sid}/manifest`);
    setManifest(m);
    return m;
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    if (!sessionId) {
      setManifest(null);
      setAnalysis(null);
      setMessages([]);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const m = await apiGet<SessionManifest>(`/api/v1/sessions/${sessionId}/manifest`);
        if (cancelled) return;
        setManifest(m);

        const stored = loadChatMessages(sessionId);
        if (stored.length > 0) {
          setMessages(stored);
        } else if (m.files?.length) {
          setMessages(filesToUploadMessages(m.files as ManifestFileEntry[]));
        } else {
          setMessages([]);
        }

        try {
          const sess = await apiGet<SessionResponse>(`/api/v1/sessions/${sessionId}`);
          if (!cancelled) {
            setAnalysis(sess);
            const snapshot = extractInsightSnapshot(sess, m);
            if (snapshot && snapshot.total_spend > 0) {
              setMessages((prev) => {
                if (chatHasInsightSnapshot(prev)) return prev;
                const restored = buildRestoredInsightMessage(snapshot, m);
                return prev.length > 0 ? [restored, ...prev] : [restored];
              });
            }
          }
        } catch {
          if (!cancelled) setAnalysis(null);
        }
      } catch {
        if (!cancelled) {
          setManifest(null);
          setAnalysis(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    if (sessionId && messages.length > 0) {
      saveChatMessages(sessionId, messages);
    }
  }, [sessionId, messages]);

  const friendlyError = error ? friendlyErrorMessage(error) : null;

  const insightSnapshot = useMemo(
    () => extractInsightSnapshot(analysis, manifest),
    [analysis, manifest],
  );

  const welcomePrompts = useMemo(
    () => buildWelcomePrompts(insightSnapshot, manifest),
    [insightSnapshot, manifest],
  );

  const stopPolling = () => {
    pollAbortRef.current?.abort();
    pollAbortRef.current = null;
  };

  const startPolling = (runId: string) => {
    stopPolling();
    const ac = new AbortController();
    pollAbortRef.current = ac;
    void pollChatProgress(runId, setAgentSteps, ac.signal);
  };

  const runChat = async (text: string) => {
    const sid = await ensureSession();
    const runId = crypto.randomUUID();
    setLastRunId(runId);
    setInsightsOpen(true);
    setPipelineLabel(undefined);
    setAgentSteps([{ phase: 'observe', message: 'Starting OPAR agent…' }]);
    startPolling(runId);

    try {
      const res = await apiPost<V1ChatResponse>('/api/v1/chat', {
        message: text,
        session_id: sid,
        run_id: runId,
        thinking_mode: thinkingMode ? 'extended' : 'standard',
        ...contextPayload(engagement),
      });
      setLastSignals(res.quality_signals);
      setLastSteps(res.progress_steps);
      setAgentSteps(res.progress_steps);
      setAgentDegraded(!!res.degraded_mode);
      let session: SessionResponse | null = null;
      let latestManifest = manifest;
      try {
        session = await apiGet<SessionResponse>(`/api/v1/sessions/${sid}`);
        setAnalysis(session);
        await refreshAnalysisStatus();
      } catch {
        /* analysis not run yet */
      }
      try {
        latestManifest = await refreshManifest(sid);
      } catch {
        /* manifest optional */
      }
      const snapshot = extractInsightSnapshot(session, latestManifest);
      const showPeer = wantsPeerSavingsInsight(text);
      const baseOptions = res.next_options?.length
        ? res.next_options
        : buildDataRootedPrompts(snapshot, latestManifest);
      const nextOptions = showPeer
        ? [...baseOptions, ...buildDeepDivePrompts(snapshot)]
        : baseOptions;
      const thinResponse = (res.response_text || '').length < 80;
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.response_text || 'No response',
          thinking: res.thinking,
          advisory_sections: res.advisory_sections,
          quality_signals: res.quality_signals,
          next_options: nextOptions,
          run_id: res.run_id,
          progress_steps: res.progress_steps,
          degraded_mode: res.degraded_mode,
          artefacts: res.artefacts,
          insight_snapshot: snapshot && (snapshot.total_spend > 0 || showPeer) ? snapshot : undefined,
          show_peer_savings: showPeer,
        },
      ]);
      if (thinResponse && snapshot && snapshot.total_spend > 0 && !showPeer) {
        setMessages((m) => {
          const last = m[m.length - 1];
          if (!last || last.role !== 'assistant') return m;
          return [
            ...m.slice(0, -1),
            {
              ...last,
              content: buildAnalyzeCompleteContent(snapshot),
              insight_snapshot: snapshot,
            },
          ];
        });
      }
    } finally {
      stopPolling();
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    setInsightsOpen(true);
    try {
      const sid = await ensureSession();
      const fd = new FormData();
      fd.append('file', file);
      await apiUpload(`/api/v1/upload/${sid}`, fd);
      await refreshManifest(sid);
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: `Uploaded **${file.name}**. Ask a question or run full analysis when ready.`,
        },
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const requestPlanThenChat = async (text: string) => {
    const sid = await ensureSession();
    setPendingMessage(text);
    try {
      const plan = await apiPost<ChatPlanPreview>('/api/v1/chat/plan', {
        message: text,
        session_id: sid,
        ...contextPayload(engagement),
      });
      if (plan.requires_confirmation !== false && plan.user_summary) {
        setPlanPreview(plan);
        setPlanOpen(true);
        return;
      }
    } catch {
      /* fall through */
    }
    await runChat(text);
  };

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;
    setMessages((m) => [...m, { role: 'user', content: text.trim() }]);
    setLoading(true);
    setError(null);
    try {
      await requestPlanThenChat(text.trim());
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput('');
    await sendMessage(text);
  };

  const confirmPlan = async () => {
    setPlanOpen(false);
    if (!pendingMessage) return;
    setLoading(true);
    setError(null);
    try {
      await runChat(pendingMessage);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
      setPendingMessage('');
    }
  };

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setInsightsOpen(true);
    setPipelineLabel('Core analysis pipeline');
    setAgentSteps(ANALYZE_PIPELINE_STEPS);
    try {
      const sid = await ensureSession();
      await apiPost(`/api/v1/analyze/${sid}`, contextPayload(engagement));
      await syncEngagementFromAnalysis();
      const session = await apiGet<SessionResponse>(`/api/v1/sessions/${sid}`);
      setAnalysis(session);
      const m = await refreshManifest(sid);
      const snapshot = extractInsightSnapshot(session, m);
      setAgentSteps([
        ...ANALYZE_PIPELINE_STEPS,
        { phase: 'reflect', message: 'Analysis complete.' },
      ]);
      setPipelineLabel(undefined);
      if (snapshot) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: buildAnalyzeCompleteContent(snapshot),
            insight_snapshot: snapshot,
            next_options: buildDataRootedPrompts(snapshot, m),
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content:
              'Analysis finished but spend totals are empty. Re-upload your file or check column mapping, then run analysis again.',
            next_options: buildDataRootedPrompts(null, m),
          },
        ]);
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
      setAgentSteps([{ phase: 'reflect', message: 'Analysis failed. See error above.' }]);
    } finally {
      setLoading(false);
    }
  };

  const handleIncrementalAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const sid = await ensureSession();
      await apiPost(`/api/v1/analyze/${sid}/incremental`, {});
      const session = await apiGet<SessionResponse>(`/api/v1/sessions/${sid}`);
      setAnalysis(session);
      const m = await refreshManifest(sid);
      const snapshot = extractInsightSnapshot(session, m);
      setMessages((prev) => [
        ...prev,
        snapshot
          ? {
              role: 'assistant',
              content: 'Incremental analysis complete. Updated spend signals below.',
              insight_snapshot: snapshot,
              next_options: buildDataRootedPrompts(snapshot, m),
            }
          : {
              role: 'assistant',
              content: 'Incremental analysis complete. New data merged into session.',
            },
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSectorChange = async (industry: string) => {
    setSectorUpdating(true);
    setError(null);
    try {
      const sid = await ensureSession();
      const patch: SessionManifestPatch = { industry };
      const updated = await apiPatch<SessionManifest>(
        `/api/v1/sessions/${sid}/manifest`,
        patch,
      );
      setManifest(updated);
      await refreshEngagement();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setSectorUpdating(false);
    }
  };

  const handleNewSession = async () => {
    setLoading(true);
    setError(null);
    stopPolling();
    try {
      const res = await apiPost<SessionManifest>('/api/v1/sessions', {
        company_name: 'New engagement',
        industry: engagement.industry || '',
        currency: engagement.currency || 'USD',
        audience: 'consultant',
      });
      if (sessionId) clearChatMessages(sessionId);
      setSessionId(res.session_id);
      setMessages([]);
      setAnalysis(null);
      setManifest(res);
      setAgentSteps(undefined);
      setPipelineLabel(undefined);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const currentIndustry = manifest?.industry || engagement.industry || '';

  return (
    <MainLayout hideHeader>
      <div className="flex flex-col h-[calc(100vh-2rem)] -m-4 md:-m-6">
        <header className="flex flex-wrap items-center justify-between gap-3 px-4 md:px-6 py-3 border-b border-brand-border bg-white shrink-0">
          <PageHeader
            title="Analysis"
            subtitle="Human-in-the-loop spend intelligence"
            sessionId={sessionId}
            compact
          />
          <div className="flex flex-wrap items-center gap-2 shrink-0">
            <div className="w-44 min-w-[10rem]">
              <Select
                label=""
                value={currentIndustry}
                onChange={(e) => void handleSectorChange(e.target.value)}
                disabled={sectorUpdating || loading}
                options={[
                  { value: '', label: 'Select sector…' },
                  ...SECTOR_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
                ]}
              />
            </div>
            <button
              type="button"
              onClick={() => setInsightsOpen((v) => !v)}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-brand-border hover:bg-brand-surface-muted lg:hidden"
            >
              {insightsOpen ? 'Hide insights' : 'Insights'}
            </button>
            <button
              type="button"
              onClick={handleIncrementalAnalyze}
              disabled={loading}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-brand-border hover:bg-brand-surface-muted disabled:opacity-50"
            >
              Incremental update
            </button>
            <button
              type="button"
              onClick={() => setTrustOpen(true)}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-brand-border hover:bg-brand-surface-muted"
            >
              Trust rail
            </button>
            <button
              type="button"
              onClick={() => setThinkingMode((v) => !v)}
              className={`text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                thinkingMode
                  ? 'border-deloitte-green text-deloitte-green bg-deloitte-green/5'
                  : 'border-brand-border hover:bg-brand-surface-muted'
              }`}
              title="Enable extended chain-of-thought reasoning for deeper analysis"
            >
              {thinkingMode ? 'Thinking: on' : 'Thinking: off'}
            </button>
          </div>
        </header>

        {friendlyError && (
          <div className="px-4 md:px-6 pt-3 shrink-0">
            <Alert
              variant="error"
              title={friendlyError.title}
              recovery={friendlyError.recovery}
              onDismiss={() => setError(null)}
            >
              {friendlyError.detail}
            </Alert>
          </div>
        )}

        <div className="flex flex-1 min-h-0 overflow-hidden">
          <section className="flex flex-col flex-1 min-w-0 bg-brand-surface">
            <div className="flex-1 overflow-y-auto">
              <div className="max-w-3xl mx-auto w-full px-4 py-8 space-y-6">
                {messages.length === 0 && !loading ? (
                  <div className="text-center py-8 md:py-16">
                    <DeloitteLogo className="justify-center mb-6" />
                    <h2 className="text-xl font-semibold font-sans text-brand-ink mb-2">
                      How can I help with your spend analysis?
                    </h2>
                    <p className="text-sm text-brand-muted max-w-md mx-auto mb-6">
                      Attach spend data, ask questions in natural language, or run the full OPAR
                      analysis pipeline.
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg mx-auto mb-6">
                      {welcomePrompts.map((opt) => (
                        <button
                          key={opt.label}
                          type="button"
                          onClick={() => sendMessage(opt.message)}
                          className="text-sm px-4 py-2.5 rounded-xl border border-brand-border bg-white text-brand-ink hover:border-deloitte-green hover:shadow-sm transition-shadow text-left"
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                    <a
                      href="/api/v1/template/spend-csv"
                      download="opex_spend_template.csv"
                      className="text-xs text-brand-muted hover:text-deloitte-green underline underline-offset-2 transition-colors"
                    >
                      Download spend template ↓
                    </a>
                  </div>
                ) : (
                  <>
                    {messages.map((msg, idx) => (
                      <StructuredChatMessage
                        key={idx}
                        message={msg}
                        onOptionClick={(text) => sendMessage(text)}
                      />
                    ))}
                    {loading && (
                      <div className="flex justify-start">
                        <div className="px-4 py-3 rounded-2xl bg-white border border-brand-border shadow-sm">
                          <Loader label="Thinking…" />
                        </div>
                      </div>
                    )}
                  </>
                )}
                <div ref={chatEndRef} />
              </div>
            </div>

            <input ref={fileRef} type="file" className="hidden" onChange={handleUpload} />
            <ChatComposer
              value={input}
              onChange={setInput}
              onSubmit={handleSendMessage}
              loading={loading}
              onUploadClick={() => fileRef.current?.click()}
              onAnalyzeClick={handleAnalyze}
              onNewSessionClick={handleNewSession}
            />
          </section>

          {insightsOpen && (
            <aside className="hidden lg:flex w-80 xl:w-96 flex-col border-l border-brand-border bg-white shrink-0">
              <div className="px-4 py-3 border-b border-brand-border">
                <h2 className="text-sm font-semibold font-sans text-brand-ink">Insights</h2>
                <p className="text-xs text-brand-muted">Session data, metrics & agent activity</p>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                <InsightCards
                  analysis={analysis}
                  manifest={manifest}
                  agentSteps={agentSteps ?? lastSteps}
                  agentRunId={lastRunId}
                  agentLoading={loading}
                  agentDegraded={agentDegraded}
                  pipelineLabel={pipelineLabel}
                  onOpenCostRoom={syncEngagementFromAnalysis}
                />
              </div>
            </aside>
          )}
        </div>

        {insightsOpen && (
          <div
            className="lg:hidden fixed inset-0 z-40 flex flex-col justify-end"
            role="dialog"
            aria-label="Session insights"
          >
            <button
              type="button"
              className="absolute inset-0 bg-black/40"
              aria-label="Close insights"
              onClick={() => setInsightsOpen(false)}
            />
            <div className="relative max-h-[85vh] flex flex-col bg-white border-t border-brand-border rounded-t-2xl shadow-xl">
              <div className="flex items-center justify-between px-4 py-3 border-b border-brand-border shrink-0">
                <div>
                  <h2 className="text-sm font-semibold font-sans text-brand-ink">Insights</h2>
                  <p className="text-xs text-brand-muted">Files, ingestion & agent activity</p>
                </div>
                <button
                  type="button"
                  onClick={() => setInsightsOpen(false)}
                  className="text-xs px-2.5 py-1.5 rounded-lg border border-brand-border hover:bg-brand-surface-muted"
                >
                  Close
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 min-h-0">
                <InsightCards
                  analysis={analysis}
                  manifest={manifest}
                  agentSteps={agentSteps ?? lastSteps}
                  agentRunId={lastRunId}
                  agentLoading={loading}
                  agentDegraded={agentDegraded}
                  pipelineLabel={pipelineLabel}
                  onOpenCostRoom={syncEngagementFromAnalysis}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      <PlanApprovalModal
        open={planOpen}
        plan={planPreview}
        loading={loading}
        onConfirm={confirmPlan}
        onCancel={() => {
          setPlanOpen(false);
          setPendingMessage('');
        }}
      />

      <TrustRail
        open={trustOpen}
        onClose={() => setTrustOpen(false)}
        localAudit={[]}
        runId={lastRunId}
        progressSteps={lastSteps}
        qualitySignals={lastSignals}
        provenanceSources={[
          { label: 'Uploaded spend', detail: 'Session files', kind: 'fact' },
          { label: 'OPAR synthesis', detail: 'Model-assisted narrative', kind: 'inference' },
        ]}
      />
    </MainLayout>
  );
};
