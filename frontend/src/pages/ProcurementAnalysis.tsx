import React, { useEffect, useRef, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { StructuredChatMessage } from '../components/PageComponents/Procurement/StructuredChatMessage';
import { InsightCards } from '../components/PageComponents/Procurement/InsightCards';
import { PlanApprovalModal } from '../components/PageComponents/Procurement/PlanApprovalModal';
import { ChatComposer } from '../components/PageComponents/Analysis/ChatComposer';
import { TrustRail } from '../components/Trust/TrustRail';
import { DeloitteLogo } from '../components/Brand/DeloitteLogo';
import { useSession } from '../context/SessionContext';
import { apiGet, apiPost, apiUpload, getApiErrorMessage } from '../hooks/useApi';
import { friendlyErrorMessage } from '../utils/errorMessages';
import type {
  ChatMessage,
  ChatPlanPreview,
  SessionResponse,
  V1ChatResponse,
} from '../types';

const SUGGESTED_PROMPTS = [
  'Summarize spend concentration by category',
  'Where are we above peer benchmarks?',
  'What savings opportunities should we prioritize?',
  'Show me the top 10 suppliers by spend',
  'Which categories have the highest cost reduction potential?',
  'Flag any compliance or conflict-of-interest risks',
];

export const ProcurementAnalysis: React.FC = () => {
  const {
    sessionId,
    setSessionId,
    ensureSession,
    syncEngagementFromAnalysis,
    refreshAnalysisStatus,
  } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<SessionResponse | null>(null);
  const [insightsOpen, setInsightsOpen] = useState(true);
  const [trustOpen, setTrustOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [planPreview, setPlanPreview] = useState<ChatPlanPreview | null>(null);
  const [pendingMessage, setPendingMessage] = useState('');
  const [lastRunId, setLastRunId] = useState<string | undefined>();
  const [lastSignals, setLastSignals] = useState<V1ChatResponse['quality_signals']>();
  const [lastSteps, setLastSteps] = useState<V1ChatResponse['progress_steps']>();
  const fileRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const friendlyError = error ? friendlyErrorMessage(error) : null;

  const runChat = async (text: string) => {
    const sid = await ensureSession();
    const res = await apiPost<V1ChatResponse>('/api/v1/chat', {
      message: text,
      session_id: sid,
    });
    setLastRunId(res.run_id);
    setLastSignals(res.quality_signals);
    setLastSteps(res.progress_steps);
    setMessages((m) => [
      ...m,
      {
        role: 'assistant',
        content: res.response_text || 'No response',
        advisory_sections: res.advisory_sections,
        quality_signals: res.quality_signals,
        next_options: res.next_options,
        run_id: res.run_id,
        progress_steps: res.progress_steps,
        degraded_mode: res.degraded_mode,
        artefacts: res.artefacts,
      },
    ]);
    try {
      const session = await apiGet<SessionResponse>(`/api/v1/sessions/${sid}`);
      setAnalysis(session);
      await refreshAnalysisStatus();
    } catch {
      /* analysis not run yet */
    }
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const sid = await ensureSession();
      const fd = new FormData();
      fd.append('file', file);
      await apiUpload(`/api/v1/upload/${sid}`, fd);
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
    try {
      const sid = await ensureSession();
      await apiPost(`/api/v1/analyze/${sid}`, {});
      await syncEngagementFromAnalysis();
      const session = await apiGet<SessionResponse>(`/api/v1/sessions/${sid}`);
      setAnalysis(session);
      setInsightsOpen(true);
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content:
            'Analysis complete. Insights are in the panel on the right — open the Cost Room when you are ready for the executive portfolio view.',
        },
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err));
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
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: 'Incremental analysis complete. New data merged into session insights.',
        },
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleNewSession = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiPost<{ session_id: string }>('/api/v1/sessions', {
        company_name: 'New engagement',
        audience: 'consultant',
      });
      setSessionId(res.session_id);
      setMessages([]);
      setAnalysis(null);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

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
                      {SUGGESTED_PROMPTS.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => sendMessage(prompt)}
                          className="text-sm px-4 py-2.5 rounded-xl border border-brand-border bg-white text-brand-ink hover:border-deloitte-green hover:shadow-sm transition-shadow text-left"
                        >
                          {prompt}
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
                <p className="text-xs text-brand-muted">Facts and model outputs</p>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {loading && !analysis ? (
                  <Loader />
                ) : (
                  <InsightCards analysis={analysis} onOpenCostRoom={syncEngagementFromAnalysis} />
                )}
              </div>
            </aside>
          )}
        </div>
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
