import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { Select } from '../components/Common/Select';
import { RecommendedBadge } from '../components/Common/RecommendedBadge';
import { StructuredChatMessage } from '../components/PageComponents/Procurement/StructuredChatMessage';
import { ThinkingBlock } from '../components/PageComponents/Procurement/ThinkingBlock';
import { InsightCards } from '../components/PageComponents/Procurement/InsightCards';
import {
  BusinessClarificationModal,
  type ClarificationModalVariant,
} from '../components/PageComponents/Procurement/BusinessClarificationModal';
import { PlanApprovalModal } from '../components/PageComponents/Procurement/PlanApprovalModal';
import { ChatComposer } from '../components/PageComponents/Analysis/ChatComposer';
import { TrustRail } from '../components/Trust/TrustRail';
import { DeloitteLogo } from '../components/Brand/DeloitteLogo';
import { SECTOR_OPTIONS } from '../constants/sectors';
import { useSession } from '../context/SessionContext';
import { apiGet, apiPatch, apiPost, apiUpload, getApiErrorMessage } from '../hooks/useApi';
import { friendlyErrorMessage } from '../utils/errorMessages';
import { clearChatMessages, loadChatMessages, saveChatMessages } from '../utils/chatStorage';
import { effectiveAnalysisIndustry } from '../utils/engagementContext';
import {
  buildAnalyzeCompleteContent,
  buildTraceThinkingSummary,
  buildDataRootedPrompts,
  buildDeepDivePrompts,
  buildRestoredInsightMessage,
  buildWelcomePrompts,
  answeredProbeKeysFromMessages,
  collectUnansweredProbeQuestions,
  filterProbeNextOptions,
  hasUnansweredProbeQuestions,
  mergeAnsweredProbeFamilies,
  probeAnswerKey,
  probeToClarification,
  PROBE_MODAL_TRIGGER,
  saveAnsweredProbeKeys,
  chatHasInsightSnapshot,
  extractInsightSnapshot,
  mergeNextOptions,
  wantsPeerSavingsInsight,
  type TopProbeQuestion,
} from '../utils/analysisInsights';
import { VerticalResizeHandle } from '../components/Common/VerticalResizeHandle';
import { EngagementConflictBanner } from '../components/PageComponents/Procurement/EngagementConflictBanner';
import { useResizableWidth } from '../hooks/useResizableWidth';
import {
  conflictDismissKey,
  conflictSummaryMessage,
  engagementSanityFromManifest,
} from '../utils/engagementConflict';
import type { EngagementSanityConflict } from '../types';
import type { ManifestFileEntry } from '../utils/sessionFiles';
import type {
  AnalysisTraceStep,
  ChatMessage,
  ChatPlanPreview,
  ChatProgressResponse,
  EngagementMeta,
  ProgressStep,
  SessionManifest,
  SessionManifestPatch,
  SessionResponse,
  V1ChatResponse,
  AnalysisInsightSnapshot,
  BusinessClarification,
  ProbeAnswerResponse,
  LlmModelsResponse,
} from '../types';

const LLM_MODEL_STORAGE_KEY = 'opex_llm_model';

const CONFLICT_DISMISS_PREFIX = 'opex_conflict_dismiss_';
const INSIGHTS_PANEL_WIDTH_KEY = 'opex_analysis_insights_width';
const INSIGHTS_PANEL_DEFAULT_WIDTH = 320;
const INSIGHTS_PANEL_MIN_WIDTH = 260;
const INSIGHTS_PANEL_MAX_WIDTH = 560;

function loadDismissedConflictKeys(sessionId: string | null): Set<string> {
  if (!sessionId) return new Set();
  try {
    const raw = localStorage.getItem(`${CONFLICT_DISMISS_PREFIX}${sessionId}`);
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveDismissedConflictKeys(sessionId: string | null, keys: Set<string>): void {
  if (!sessionId) return;
  localStorage.setItem(`${CONFLICT_DISMISS_PREFIX}${sessionId}`, JSON.stringify([...keys]));
}

const DeepResearchBanner: React.FC<{ companyName: string; onDismiss: () => void }> = ({
  companyName,
}) => (
  <div className="flex items-center gap-2 px-4 py-2 bg-blue-50 border-b border-blue-200 text-xs text-blue-800">
    <span className="font-semibold">Deep research context loaded</span>
    <span className="text-blue-600">·</span>
    <span>
      Google Deep Research findings for{' '}
      <span className="font-medium">{companyName}</span> are active as analysis context.
    </span>
  </div>
);

function contextPayload(
  engagement: EngagementMeta,
  manifest?: SessionManifest | null,
): Record<string, unknown> {
  const industry = effectiveAnalysisIndustry(manifest, engagement);
  const body: Record<string, unknown> = {
    industry: industry || undefined,
    currency: engagement.currency || 'INR',
    audience: manifest?.audience || engagement.audience || undefined,
  };
  if (engagement.company_name && engagement.company_name !== 'New engagement') {
    body.company_name = engagement.company_name;
  }
  if (engagement.annual_revenue_cr != null && engagement.annual_revenue_cr > 0) {
    body.annual_revenue = engagement.annual_revenue_cr * 10_000_000;
  }
  return body;
}

function chatHistoryPayload(messages: ChatMessage[]): { role: string; content: string }[] {
  return messages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .slice(-6)
    .map((m) => ({ role: m.role, content: m.content }));
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
  onThinking: (thinking: string) => void,
  signal: AbortSignal,
): Promise<void> {
  while (!signal.aborted) {
    try {
      const entry = await apiGet<ChatProgressResponse>(`/api/v1/chat/progress/${runId}`);
      if (entry.steps?.length) onSteps(progressStepsFromPoll(entry));
      const thinking = String(entry.thinking_text ?? '').trim();
      if (thinking) onThinking(thinking);
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
    engagementId,
    setSessionId,
    ensureSession,
    ensureSessionForEngagement,
    ensureEngagement,
    engagement,
    refreshEngagement,
    syncEngagementFromAnalysis,
    refreshAnalysisStatus,
    sessionAnalysis,
    refreshSessionAnalysis,
    deepResearchSummary,
  } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const analysis = sessionAnalysis;
  const [manifest, setManifest] = useState<SessionManifest | null>(null);
  const [engagementDocCount, setEngagementDocCount] = useState<number | null>(null);
  const [insightsOpen, setInsightsOpen] = useState(true);
  const {
    width: insightsPanelWidth,
    isDragging: insightsResizing,
    onHandlePointerDown: onInsightsResizePointerDown,
    onHandleKeyDown: onInsightsResizeKeyDown,
  } = useResizableWidth({
    storageKey: INSIGHTS_PANEL_WIDTH_KEY,
    defaultWidth: INSIGHTS_PANEL_DEFAULT_WIDTH,
    minWidth: INSIGHTS_PANEL_MIN_WIDTH,
    maxWidth: INSIGHTS_PANEL_MAX_WIDTH,
  });
  const [trustOpen, setTrustOpen] = useState(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [planPreview, setPlanPreview] = useState<ChatPlanPreview | null>(null);
  const [pendingMessage, setPendingMessage] = useState('');
  const [clarificationOpen, setClarificationOpen] = useState(false);
  const [clarification, setClarification] = useState<BusinessClarification | null>(null);
  const [clarificationVariant, setClarificationVariant] = useState<ClarificationModalVariant>('observe');
  const [smeProbeQueue, setSmeProbeQueue] = useState<TopProbeQuestion[]>([]);
  const [smeProbeSnapshot, setSmeProbeSnapshot] = useState<AnalysisInsightSnapshot | null>(null);
  const [smeProbeIndex, setSmeProbeIndex] = useState(0);
  const [smeProbeCurrency, setSmeProbeCurrency] = useState('INR');
  const [checkpointId, setCheckpointId] = useState<string | null>(null);
  const [answeredProbeFamilies, setAnsweredProbeFamilies] = useState<Set<string>>(() => new Set());
  const answeredProbeFamiliesRef = useRef<Set<string>>(new Set());
  const probeModalShownForRun = useRef<Set<string>>(new Set());
  const skipNextProbeAutoOpen = useRef(false);
  const [lastRunId, setLastRunId] = useState<string | undefined>();
  const [lastSignals, setLastSignals] = useState<V1ChatResponse['quality_signals']>();
  const [lastSteps, setLastSteps] = useState<V1ChatResponse['progress_steps']>();
  const [agentSteps, setAgentSteps] = useState<ProgressStep[] | undefined>();
  const [agentDegraded, setAgentDegraded] = useState(false);
  const [agentFallbackReasons, setAgentFallbackReasons] = useState<
    Record<string, unknown> | undefined
  >();
  const [pipelineLabel, setPipelineLabel] = useState<string | undefined>();
  const [sectorUpdating, setSectorUpdating] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const [liveThinking, setLiveThinking] = useState('');
  const [llmModels, setLlmModels] = useState<LlmModelsResponse['models']>([]);
  const [selectedLlmModel, setSelectedLlmModel] = useState('');
  const [conflictResolving, setConflictResolving] = useState(false);
  const [dismissedConflictKeys, setDismissedConflictKeys] = useState<Set<string>>(
    () => loadDismissedConflictKeys(sessionId),
  );
  const fileRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollAbortRef = useRef<AbortController | null>(null);

  const refreshManifest = useCallback(async (sid: string) => {
    const m = await apiGet<SessionManifest>(`/api/v1/sessions/${sid}/manifest`);
    setManifest(m);
    return m;
  }, []);

  useEffect(() => {
    setDismissedConflictKeys(loadDismissedConflictKeys(sessionId));
  }, [sessionId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiGet<LlmModelsResponse>('/api/v1/llm/models');
        if (cancelled) return;
        setLlmModels(res.models ?? []);
        const stored = localStorage.getItem(LLM_MODEL_STORAGE_KEY);
        const validStored = res.models?.some((m) => m.id === stored) ? stored : null;
        setSelectedLlmModel(validStored || res.default_model_id || res.models?.[0]?.id || '');
      } catch {
        if (!cancelled) setLlmModels([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLlmModelChange = (modelId: string) => {
    setSelectedLlmModel(modelId);
    if (modelId) {
      localStorage.setItem(LLM_MODEL_STORAGE_KEY, modelId);
    } else {
      localStorage.removeItem(LLM_MODEL_STORAGE_KEY);
    }
  };

  useEffect(() => {
    if (!engagementId) { setEngagementDocCount(null); return; }
    apiGet<{ documents: { status: string }[] }>(`/api/v1/engagements/${engagementId}/documents`)
      .then((res) => {
        const ready = (res.documents ?? []).filter((d) => d.status === 'ready').length;
        setEngagementDocCount(ready);
      })
      .catch(() => setEngagementDocCount(null));
  }, [engagementId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    if (!sessionId) {
      setManifest(null);
      setMessages([]);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const status = await apiGet<{
          session_exists?: boolean;
          has_analysis?: boolean;
        }>(`/api/v1/sessions/${sessionId}/status`);
        if (!status.session_exists) {
          if (!cancelled) {
            setManifest(null);
            setMessages([]);
          }
          return;
        }

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
          if (!status.has_analysis) {
            return;
          }
          const sess = await refreshSessionAnalysis();
          if (!cancelled && sess) {
            const snapshot = extractInsightSnapshot(sess, m);
            if (snapshot && snapshot.total_spend > 0) {
              setMessages((prev) => {
                if (chatHasInsightSnapshot(prev)) return prev;
                const rawTrace = (sess as { analysis_trace?: unknown }).analysis_trace;
                const trace = Array.isArray(rawTrace) ? (rawTrace as AnalysisTraceStep[]) : undefined;
                const restored = buildRestoredInsightMessage(snapshot, m, trace);
                return prev.length > 0 ? [restored, ...prev] : [restored];
              });
            }
          }
        } catch {
          /* analysis optional on load */
        }
      } catch {
        if (!cancelled) {
          setManifest(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, refreshSessionAnalysis]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible' && sessionId) {
        refreshSessionAnalysis().catch(() => undefined);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [sessionId, refreshSessionAnalysis]);

  useEffect(() => {
    if (sessionId && messages.length > 0) {
      saveChatMessages(sessionId, messages);
    }
  }, [sessionId, messages]);

  useEffect(() => {
    if (!sessionId) {
      setAnsweredProbeFamilies(new Set());
      return;
    }
    const merged = mergeAnsweredProbeFamilies(
      manifest,
      sessionId,
      answeredProbeKeysFromMessages(messages),
    );
    answeredProbeFamiliesRef.current = merged;
    setAnsweredProbeFamilies(merged);
  }, [sessionId, messages, manifest]);

  const markProbeFamilyAnswered = useCallback(
    (familyId: string) => {
      setAnsweredProbeFamilies((prev) => {
        const next = new Set(prev);
        next.add(familyId);
        answeredProbeFamiliesRef.current = next;
        if (sessionId) saveAnsweredProbeKeys(sessionId, next);
        return next;
      });
    },
    [sessionId],
  );

  const currentAnsweredProbeFamilies = () => answeredProbeFamiliesRef.current;

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
    setLiveThinking('');
    const ac = new AbortController();
    pollAbortRef.current = ac;
    void pollChatProgress(runId, setAgentSteps, setLiveThinking, ac.signal);
  };

  const resetSmeProbeState = () => {
    setSmeProbeQueue([]);
    setSmeProbeSnapshot(null);
    setSmeProbeIndex(0);
    setClarificationVariant('observe');
  };

  const openSmeProbeModal = useCallback(
    (snapshot: AnalysisInsightSnapshot, answered: Set<string>) => {
      const probes = collectUnansweredProbeQuestions(snapshot, answered, 5);
      if (probes.length === 0) return;
      const currency = snapshot.reporting_currency || 'INR';
      setSmeProbeSnapshot(snapshot);
      setSmeProbeQueue(probes);
      setSmeProbeIndex(0);
      setSmeProbeCurrency(currency);
      setClarification(probeToClarification(probes[0], currency));
      setClarificationVariant('sme_probe');
      setCheckpointId(null);
      setPendingMessage('');
      setClarificationOpen(true);
    },
    [],
  );

  const maybeAutoOpenProbeModal = useCallback(
    (
      snapshot: AnalysisInsightSnapshot | null | undefined,
      answered: Set<string>,
      runId?: string,
    ) => {
      if (skipNextProbeAutoOpen.current) {
        skipNextProbeAutoOpen.current = false;
        return;
      }
      if (!snapshot || !hasUnansweredProbeQuestions(snapshot, answered)) return;
      const unanswered = collectUnansweredProbeQuestions(snapshot, answered, 5);
      const key =
        runId ||
        `probe-${snapshot.total_spend}-${unanswered.map((p) => p.probe_family_id || probeAnswerKey(p.question)).join('|')}`;
      if (probeModalShownForRun.current.has(key)) return;
      probeModalShownForRun.current.add(key);
      openSmeProbeModal(snapshot, answered);
    },
    [openSmeProbeModal],
  );

  const buildAssistantNextOptions = (
    snapshot: AnalysisInsightSnapshot | null,
    manifest: SessionManifest | null,
    resOptions: V1ChatResponse['next_options'],
    showPeer: boolean,
    answered: Set<string>,
  ) => {
    const base = mergeNextOptions(resOptions, buildDataRootedPrompts(snapshot, manifest));
    const merged = showPeer ? mergeNextOptions(base, buildDeepDivePrompts(snapshot)) : base;
    return filterProbeNextOptions(merged, snapshot, answered);
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
        llm_model: selectedLlmModel || undefined,
        chat_history: chatHistoryPayload(messages),
        ...contextPayload(engagement, manifest),
      });
      if (res.hitl_required && res.clarification && res.checkpoint_id) {
        openClarificationProbe({
          clarification: res.clarification,
          checkpoint_id: res.checkpoint_id,
        });
        return;
      }
      setLastSignals(res.quality_signals);
      setLastSteps(res.progress_steps);
      setAgentSteps(res.progress_steps);
      setAgentDegraded(!!res.degraded_mode);
      setAgentFallbackReasons(res.fallback_reasons);
      let session: SessionResponse | null = null;
      let latestManifest = manifest;
      try {
        session = await refreshSessionAnalysis();
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
      const suppressCategoryInsight = res.response_metadata?.insight_dimension === 'supplier';
      const nextOptions = buildAssistantNextOptions(
        snapshot,
        latestManifest,
        res.next_options,
        showPeer,
        currentAnsweredProbeFamilies(),
      );
      const insightSnap =
        !suppressCategoryInsight && snapshot && (snapshot.total_spend > 0 || showPeer)
          ? snapshot
          : undefined;
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.response_text || 'No response',
          thinking: res.thinking,
          advisory_sections: res.advisory_sections,
          presentation: res.presentation,
          quality_signals: res.quality_signals,
          next_options: nextOptions,
          run_id: res.run_id,
          progress_steps: res.progress_steps,
          degraded_mode: res.degraded_mode,
          used_llm_synthesis: res.used_llm_synthesis,
          fallback_reasons: res.fallback_reasons,
          artefacts: res.artefacts,
          insight_snapshot: insightSnap,
          show_peer_savings: showPeer,
          charts: res.charts,
        },
      ]);
      maybeAutoOpenProbeModal(insightSnap, currentAnsweredProbeFamilies(), res.run_id);
    } finally {
      stopPolling();
    }
  };

  const handleDismissConflict = (conflict: EngagementSanityConflict) => {
    const key = conflictDismissKey(sessionId, conflict);
    setDismissedConflictKeys((prev) => {
      const next = new Set(prev);
      next.add(key);
      saveDismissedConflictKeys(sessionId, next);
      return next;
    });
  };

  const handleUseDetectedCompany = async (company: string) => {
    setConflictResolving(true);
    setError(null);
    try {
      const sid = await ensureSession();
      const patch: SessionManifestPatch = { company_name: company };
      const updated = await apiPatch<SessionManifest>(
        `/api/v1/sessions/${sid}/manifest`,
        patch,
      );
      setManifest(updated);
      await refreshEngagement();
      setDismissedConflictKeys(new Set());
      saveDismissedConflictKeys(sid, new Set());
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setConflictResolving(false);
    }
  };

  const handleApplySector = async (industry: string) => {
    setConflictResolving(true);
    setError(null);
    try {
      const sid = await ensureSession();
      const patch: SessionManifestPatch = { industry };
      const updated = await apiPatch<SessionManifest>(
        `/api/v1/sessions/${sid}/manifest`,
        patch,
      );
      setManifest(updated);
      const eid = engagementId ?? engagement.engagement_id;
      if (eid && industry) {
        await apiPatch(`/api/v1/engagements/${eid}`, { industry });
      }
      await refreshEngagement();
      setDismissedConflictKeys(new Set());
      saveDismissedConflictKeys(sid, new Set());
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setConflictResolving(false);
    }
  };

  const handleKeepEngagementCompany = () => {
    const sanity = engagementSanityFromManifest(manifest);
    sanity?.conflicts?.forEach((c) => handleDismissConflict(c));
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;
    setLoading(true);
    setError(null);
    setInsightsOpen(true);

    let sid: string;
    let eid: string;
    try {
      eid = engagementId ?? (await ensureEngagement());
      sid = await ensureSessionForEngagement(eid);
    } catch (err) {
      setError(getApiErrorMessage(err));
      setLoading(false);
      return;
    }

    const succeeded: string[] = [];
    const failed: string[] = [];
    const SENTINEL = '__upload_progress__';

    setMessages((prev) => [
      ...prev,
      {
        role: 'assistant' as const,
        content: `Uploading ${files.length} file${files.length > 1 ? 's' : ''}…`,
        run_id: SENTINEL,
      },
    ]);

    let latestSanity: SessionManifest['engagement_sanity'] | undefined;
    for (let i = 0; i < files.length; i++) {
      setMessages((prev) =>
        prev.map((m) =>
          m.run_id === SENTINEL
            ? {
                ...m,
                content: `Uploading ${files.length} file${files.length > 1 ? 's' : ''}… ${i} of ${files.length} done`,
              }
            : m,
        ),
      );
      try {
        const fd = new FormData();
        fd.append('file', files[i]);
        await apiUpload(`/api/v1/engagements/${eid}/documents`, fd);
        succeeded.push(files[i].name);
      } catch {
        failed.push(files[i].name);
      }
    }

    try {
      const m = await refreshManifest(sid);
      latestSanity = latestSanity ?? m.engagement_sanity;
    } catch {
      /* non-fatal */
    }

    const conflictNote =
      latestSanity?.has_conflicts && latestSanity.conflicts?.length
        ? `\n\n⚠️ ${conflictSummaryMessage(latestSanity.conflicts).replace(/\*\*/g, '')}`
        : '';
    if (latestSanity?.has_conflicts) {
      setDismissedConflictKeys(new Set());
      saveDismissedConflictKeys(sid, new Set());
    }

    let summary: string;
    if (succeeded.length > 0 && failed.length === 0) {
      summary = `Uploaded ${succeeded.length} file${succeeded.length > 1 ? 's' : ''}: ${succeeded.map((n) => `**${n}**`).join(', ')}. Ask a question or run full analysis when ready.${conflictNote}`;
    } else if (succeeded.length > 0) {
      summary = `Uploaded ${succeeded.map((n) => `**${n}**`).join(', ')}. Failed: ${failed.map((n) => `**${n}**`).join(', ')}.${conflictNote}`;
      setError(`${failed.length} file(s) failed to upload: ${failed.join(', ')}`);
    } else {
      summary = `All uploads failed: ${failed.map((n) => `**${n}**`).join(', ')}`;
      setError(`All ${failed.length} file(s) failed to upload.`);
    }

    setMessages((prev) =>
      prev.map((m) =>
        m.run_id === SENTINEL ? { ...m, run_id: undefined, content: summary } : m,
      ),
    );
    setLoading(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const openClarificationProbe = (probe: {
    clarification: BusinessClarification;
    checkpoint_id: string;
  }) => {
    resetSmeProbeState();
    setClarification(probe.clarification);
    setCheckpointId(probe.checkpoint_id);
    setClarificationVariant('observe');
    setClarificationOpen(true);
  };

  const requestPlanThenChat = async (text: string) => {
    const sid = await ensureSession();
    setPendingMessage(text);
    try {
      const plan = await apiPost<ChatPlanPreview>('/api/v1/chat/plan', {
        message: text,
        session_id: sid,
        ...contextPayload(engagement, manifest),
      });
      if (plan.hitl_required && plan.clarification && plan.checkpoint_id) {
        openClarificationProbe({
          clarification: plan.clarification,
          checkpoint_id: plan.checkpoint_id,
        });
        return;
      }
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
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    if (trimmed === PROBE_MODAL_TRIGGER) {
      const lastWithSnapshot = [...messages].reverse().find((m) => m.insight_snapshot);
      if (lastWithSnapshot?.insight_snapshot) {
        openSmeProbeModal(lastWithSnapshot.insight_snapshot, answeredProbeFamilies);
      }
      return;
    }
    setMessages((m) => [...m, { role: 'user', content: trimmed }]);
    setLoading(true);
    setError(null);
    try {
      await requestPlanThenChat(trimmed);
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

  const confirmSmeProbe = async (selectedOption: string | null, freeText: string) => {
    const probe = smeProbeQueue[smeProbeIndex];
    if (!probe) return;
    const answer = freeText.trim() || selectedOption || '';
    if (!answer) return;
    const familyId = probe.probe_family_id || probeAnswerKey(probe.question);

    setLoading(true);
    setError(null);
    skipNextProbeAutoOpen.current = true;
    try {
      const sid = await ensureSession();
      const res = await apiPost<ProbeAnswerResponse>('/api/v1/chat/probe-answer', {
        session_id: sid,
        probe_family_id: familyId,
        question: probe.question,
        answer,
        selected_option: selectedOption ?? undefined,
        scope: probe.scope ?? 'portfolio',
        applies_to_categories:
          probe.affected_categories?.length
            ? probe.affected_categories
            : probe.category_name
              ? [probe.category_name]
              : [],
      });

      markProbeFamilyAnswered(familyId);
      const updatedManifest = await refreshManifest(sid);

      let freshAnalysis = analysis;
      try {
        freshAnalysis = (await refreshSessionAnalysis()) ?? analysis;
      } catch {
        /* session refresh optional */
      }

      const freshSnap = extractInsightSnapshot(freshAnalysis, updatedManifest);
      const answered = mergeAnsweredProbeFamilies(
        updatedManifest,
        sid,
        currentAnsweredProbeFamilies(),
      );
      const remaining = freshSnap
        ? collectUnansweredProbeQuestions(freshSnap, answered, 5)
        : [];

      if (remaining.length > 0) {
        setSmeProbeSnapshot(freshSnap);
        setSmeProbeQueue(remaining);
        setSmeProbeIndex(0);
        setClarification(probeToClarification(remaining[0], smeProbeCurrency));
      } else {
        setClarificationOpen(false);
        resetSmeProbeState();
      }

      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.response_text,
          insight_snapshot: freshSnap ?? smeProbeSnapshot ?? undefined,
        },
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const confirmClarification = async (
    selectedOption: string | null,
    freeText: string,
  ) => {
    if (clarificationVariant === 'sme_probe') {
      await confirmSmeProbe(selectedOption, freeText);
      return;
    }
    if (!checkpointId) return;
    setClarificationOpen(false);
    setLoading(true);
    setError(null);
    setInsightsOpen(true);
    setPipelineLabel(undefined);
    const runId = crypto.randomUUID();
    setLastRunId(runId);
    setAgentSteps([{ phase: 'observe', message: 'Resuming analysis with your guidance…' }]);
    startPolling(runId);

    try {
      const res = await apiPost<V1ChatResponse>('/api/v1/chat/resume', {
        checkpoint_id: checkpointId,
        selected_option: selectedOption ?? undefined,
        free_text: freeText || undefined,
        run_id: runId,
        thinking_mode: thinkingMode ? 'extended' : 'standard',
        llm_model: selectedLlmModel || undefined,
        chat_history: chatHistoryPayload(messages),
        ...contextPayload(engagement, manifest),
      });
      if (res.hitl_required && res.clarification && res.checkpoint_id) {
        openClarificationProbe({
          clarification: res.clarification,
          checkpoint_id: res.checkpoint_id,
        });
        return;
      }
      setLastSignals(res.quality_signals);
      setLastSteps(res.progress_steps);
      setAgentSteps(res.progress_steps);
      setAgentDegraded(!!res.degraded_mode);
      setAgentFallbackReasons(res.fallback_reasons);
      const sid = await ensureSession();
      let session: SessionResponse | null = null;
      let latestManifest = manifest;
      try {
        session = await refreshSessionAnalysis();
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
      const showPeer = pendingMessage ? wantsPeerSavingsInsight(pendingMessage) : false;
      const suppressCategoryInsight = res.response_metadata?.insight_dimension === 'supplier';
      const nextOptions = buildAssistantNextOptions(
        snapshot,
        latestManifest,
        res.next_options,
        showPeer,
        answeredProbeFamilies,
      );
      const insightSnap =
        !suppressCategoryInsight && snapshot && (snapshot.total_spend > 0 || showPeer)
          ? snapshot
          : undefined;
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: res.response_text || 'No response',
          thinking: res.thinking,
          advisory_sections: res.advisory_sections,
          presentation: res.presentation,
          quality_signals: res.quality_signals,
          next_options: nextOptions,
          run_id: res.run_id,
          progress_steps: res.progress_steps,
          degraded_mode: res.degraded_mode,
          used_llm_synthesis: res.used_llm_synthesis,
          fallback_reasons: res.fallback_reasons,
          artefacts: res.artefacts,
          insight_snapshot: insightSnap,
          show_peer_savings: showPeer,
          charts: res.charts,
        },
      ]);
      maybeAutoOpenProbeModal(insightSnap, answeredProbeFamilies, res.run_id);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      stopPolling();
      setLoading(false);
      setPendingMessage('');
      setCheckpointId(null);
      setClarification(null);
      resetSmeProbeState();
    }
  };

  const handleAnalyze = async () => {
    setLoading(true);
    setError(null);
    setInsightsOpen(true);
    setPipelineLabel('Core analysis pipeline');
    // Real steps stream in via progress polling; seed with a single "starting"
    // line so the panel isn't empty for the first poll interval.
    setAgentSteps([{ phase: 'observe', message: 'Starting analysis…' }]);
    const runId =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `run-${Date.now()}`;
    setLastRunId(runId);
    const controller = new AbortController();
    const pollPromise = pollChatProgress(runId, setAgentSteps, setLiveThinking, controller.signal);
    try {
      const sid = await ensureSession();
      const analysisResult = await apiPost<SessionResponse>(`/api/v1/analyze/${sid}`, {
        ...contextPayload(engagement, manifest),
        run_id: runId,
      });
      controller.abort();
      await pollPromise.catch(() => undefined);
      const rawTrace = (analysisResult as { analysis_trace?: unknown }).analysis_trace;
      const trace = Array.isArray(rawTrace) ? (rawTrace as AnalysisTraceStep[]) : undefined;
      await syncEngagementFromAnalysis();
      const session = await refreshSessionAnalysis();
      const m = await refreshManifest(sid);
      const snapshot = extractInsightSnapshot(session, m);
      setAgentSteps((prev) => [
        ...(prev ?? []),
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
            analysis_trace: trace,
            thinking: thinkingMode && trace?.length ? buildTraceThinkingSummary(trace) : undefined,
            run_id: runId,
            show_peer_savings: true,
            next_options: filterProbeNextOptions(
              buildDataRootedPrompts(snapshot, m),
              snapshot,
              answeredProbeFamilies,
            ),
          },
        ]);
        maybeAutoOpenProbeModal(snapshot, answeredProbeFamilies, runId);
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content:
              'Analysis finished but spend totals are empty. Re-upload your file or check column mapping, then run analysis again.',
            analysis_trace: trace,
            thinking: thinkingMode && trace?.length ? buildTraceThinkingSummary(trace) : undefined,
            run_id: runId,
            next_options: buildDataRootedPrompts(null, m),
          },
        ]);
      }
    } catch (err) {
      controller.abort();
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
      const session = await refreshSessionAnalysis();
      const m = await refreshManifest(sid);
      const snapshot = extractInsightSnapshot(session, m);
      setMessages((prev) => [
        ...prev,
        snapshot
          ? {
              role: 'assistant',
              content: 'Incremental analysis complete. Updated spend signals below.',
              insight_snapshot: snapshot,
              next_options: filterProbeNextOptions(
                buildDataRootedPrompts(snapshot, m),
                snapshot,
                answeredProbeFamilies,
              ),
            }
          : {
              role: 'assistant',
              content: 'Incremental analysis complete. New data merged into session.',
            },
      ]);
      if (snapshot) {
        maybeAutoOpenProbeModal(snapshot, answeredProbeFamilies);
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleSectorChange = async (industry: string) => {
    if (!industry) return;
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
      const eid = engagementId ?? engagement.engagement_id;
      if (eid) {
        await apiPatch(`/api/v1/engagements/${eid}`, { industry });
      }
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
      const eid = await ensureEngagement();
      const res = await apiPost<SessionManifest>('/api/v1/sessions', {
        company_name: engagement.company_name || 'New engagement',
        industry: engagement.industry || '',
        currency: engagement.currency || 'INR',
        audience: 'consultant',
        engagement_id: eid,
      });
      if (sessionId) clearChatMessages(sessionId);
      setSessionId(res.session_id);
      setMessages([]);
      setManifest(res);
      setAgentSteps(undefined);
      setPipelineLabel(undefined);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const currentIndustry = effectiveAnalysisIndustry(manifest, engagement);

  return (
    <MainLayout hideHeader>
      <div className="flex flex-col h-[calc(100vh-2rem)] -m-4 md:-m-6">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 md:px-6 py-2 border-b border-brand-border bg-white shrink-0">
          <PageHeader
            title="Analysis"
            subtitle="Human-in-the-loop spend intelligence"
            sessionId={sessionId}
            compact
          />
          {engagementId && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-brand-muted min-w-0">
              {engagement.company_name && engagement.company_name !== 'New engagement' ? (
                <span className="font-medium text-brand-ink truncate max-w-[12rem]">
                  {engagement.company_name}
                </span>
              ) : (
                <span className="font-mono text-brand-ink">{engagementId.slice(0, 8)}…</span>
              )}
              {engagementDocCount !== null && (
                <span className={engagementDocCount > 0 ? 'text-emerald-700' : 'text-amber-700'}>
                  · {engagementDocCount > 0 ? `${engagementDocCount} doc${engagementDocCount !== 1 ? 's' : ''}` : 'no docs'}
                </span>
              )}
              <Link to="/documents" className="text-deloitte-green hover:underline shrink-0">
                Manage docs
              </Link>
              {engagement.detected_company_name && (
                <RecommendedBadge
                  variant="compact"
                  label={engagement.detected_company_name}
                  matches={
                    (engagement.company_name || '').trim().toLowerCase() ===
                    engagement.detected_company_name.toLowerCase()
                  }
                  changeLink="/diagnostic"
                />
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 shrink-0 ml-auto">
            <div className="flex items-center gap-1.5">
              <div className="w-36 min-w-[8.5rem]">
                <Select
                  label=""
                  value={currentIndustry}
                  onChange={(e) => void handleSectorChange(e.target.value)}
                  disabled={sectorUpdating || loading}
                  className="py-1.5 px-2.5 text-xs"
                  options={[
                    { value: '', label: 'Select sector…' },
                    ...SECTOR_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
                  ]}
                />
              </div>
              {engagement.detected_industry && (
                <RecommendedBadge
                  variant="compact"
                  label={
                    engagement.detected_industry_label ||
                    SECTOR_OPTIONS.find((o) => o.value === engagement.detected_industry)?.label ||
                    engagement.detected_industry
                  }
                  matches={currentIndustry === engagement.detected_industry}
                  onApply={() => void handleSectorChange(engagement.detected_industry as string)}
                  changeLink="/diagnostic"
                />
              )}
            </div>
            <button
              type="button"
              onClick={() => setInsightsOpen((v) => !v)}
              className="text-xs px-2 py-1 rounded-md border border-brand-border hover:bg-brand-surface-muted lg:hidden"
            >
              {insightsOpen ? 'Hide insights' : 'Insights'}
            </button>
            <button
              type="button"
              onClick={handleIncrementalAnalyze}
              disabled={loading}
              className="text-xs px-2 py-1 rounded-md border border-brand-border hover:bg-brand-surface-muted disabled:opacity-50"
            >
              Incremental update
            </button>
            <button
              type="button"
              onClick={() => setTrustOpen(true)}
              className="text-xs px-2 py-1 rounded-md border border-brand-border hover:bg-brand-surface-muted"
            >
              Trust rail
            </button>
            {llmModels.length > 0 && (
              <div className="w-44 min-w-[10rem]">
                <Select
                  label=""
                  value={selectedLlmModel}
                  onChange={(e) => handleLlmModelChange(e.target.value)}
                  disabled={loading}
                  className="py-1.5 px-2.5 text-xs"
                  options={llmModels.map((m) => ({
                    value: m.id,
                    label: m.label,
                  }))}
                />
              </div>
            )}
            <button
              type="button"
              onClick={() => setThinkingMode((v) => !v)}
              className={`text-xs px-2 py-1 rounded-md border transition-colors ${
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

        <EngagementConflictBanner
          manifest={manifest}
          engagement={engagement}
          sessionId={sessionId}
          dismissedKeys={dismissedConflictKeys}
          onDismiss={handleDismissConflict}
          onUseDetectedCompany={handleUseDetectedCompany}
          onApplySector={handleApplySector}
          onKeepEngagementCompany={handleKeepEngagementCompany}
          resolving={conflictResolving}
        />

        <div className="flex flex-1 min-h-0 overflow-hidden">
          <section className="flex flex-col flex-1 min-w-0 bg-brand-surface">
            {deepResearchSummary && (
              <DeepResearchBanner
                companyName={engagement.company_name}
                onDismiss={() => {/* banner is informational — no dismiss needed for now */}}
              />
            )}
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
                    <span className="text-xs text-brand-muted mx-2">·</span>
                    <a
                      href="/api/v1/samples/spend-ledger.csv"
                      download="spend_ledger_sample.csv"
                      className="text-xs text-brand-muted hover:text-deloitte-green underline underline-offset-2 transition-colors"
                    >
                      Sample ledger CSV ↓
                    </a>
                    <span className="text-xs text-brand-muted mx-2">·</span>
                    <a
                      href="/api/v1/samples/pnl-expense.xlsx"
                      download="pnl_expense_summary_sample.xlsx"
                      className="text-xs text-brand-muted hover:text-deloitte-green underline underline-offset-2 transition-colors"
                    >
                      Sample P&L workbook ↓
                    </a>
                  </div>
                ) : (
                  <>
                    {messages.map((msg, idx) => (
                      <StructuredChatMessage
                        key={idx}
                        message={msg}
                        liveSnapshot={insightSnapshot}
                        currency={engagement.currency || 'INR'}
                        onOptionClick={(text) => sendMessage(text)}
                        answeredProbeFamilies={answeredProbeFamilies}
                        onOpenProbes={
                          msg.insight_snapshot
                            ? () => openSmeProbeModal(msg.insight_snapshot!, answeredProbeFamilies)
                            : undefined
                        }
                      />
                    ))}
                    {loading && (
                      <div className="flex justify-start gap-3 max-w-[85%]">
                        <span
                          className="w-8 h-8 rounded-full bg-black flex items-center justify-center shrink-0 text-[10px] font-bold text-white"
                          aria-hidden
                        >
                          AI
                        </span>
                        <div className="flex-1 min-w-0">
                          <ThinkingBlock thinking={liveThinking} live />
                        </div>
                      </div>
                    )}
                  </>
                )}
                <div ref={chatEndRef} />
              </div>
            </div>

            <input ref={fileRef} type="file" multiple accept=".csv,.xlsx,.xls" className="hidden" onChange={handleUpload} />
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
            <>
              <VerticalResizeHandle
                onPointerDown={onInsightsResizePointerDown}
                onKeyDown={onInsightsResizeKeyDown}
                isDragging={insightsResizing}
                ariaValueNow={insightsPanelWidth}
                ariaValueMin={INSIGHTS_PANEL_MIN_WIDTH}
                ariaValueMax={INSIGHTS_PANEL_MAX_WIDTH}
              />
              <aside
                style={{ width: insightsPanelWidth }}
                className="hidden lg:flex flex-col bg-white shrink-0 min-w-0"
              >
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
                    agentFallbackReasons={agentFallbackReasons}
                    pipelineLabel={pipelineLabel}
                    onOpenCostRoom={syncEngagementFromAnalysis}
                  />
                </div>
              </aside>
            </>
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
                  agentFallbackReasons={agentFallbackReasons}
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

      <BusinessClarificationModal
        open={clarificationOpen}
        clarification={clarification}
        loading={loading}
        variant={clarificationVariant}
        probeMeta={
          clarificationVariant === 'sme_probe' && smeProbeQueue[smeProbeIndex]
            ? {
                category_name: smeProbeQueue[smeProbeIndex].category_name,
                affected_categories: smeProbeQueue[smeProbeIndex].affected_categories,
                scope: smeProbeQueue[smeProbeIndex].scope,
                saving_at_stake: smeProbeQueue[smeProbeIndex].saving_at_stake,
                index: smeProbeIndex,
                total: smeProbeQueue.length,
                currency: smeProbeCurrency,
              }
            : null
        }
        onConfirm={confirmClarification}
        onCancel={() => {
          setClarificationOpen(false);
          if (clarificationVariant === 'observe') {
            setCheckpointId(null);
            setClarification(null);
            setPendingMessage('');
            setError('Analysis paused — provide the requested data or resend your question when ready.');
          } else {
            resetSmeProbeState();
            setClarification(null);
          }
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
