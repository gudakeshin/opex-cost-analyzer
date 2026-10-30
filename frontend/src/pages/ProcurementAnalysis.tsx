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
import { sectorLabel } from '../constants/sectors';
import { useSectorOptions } from '../api/hooks/useBenchmarksQueries';
import { useSession } from '../context/SessionContext';
import { useUnsavedGuard } from '../hooks/useUnsavedGuard';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { apiGet, apiPatch, apiPost, apiUpload, getApiErrorMessage, streamChatPost } from '../hooks/useApi';
import { fetchSessionManifest, fetchSessionStatus } from '../api/hooks/useSessionQueries';
import { useEngagementDocuments, useLlmModels } from '../api/hooks/useProcurementQueries';
import { procurementKeys } from '../api/queryKeys';
import { friendlyErrorMessage } from '../utils/errorMessages';
import { loadChatMessages, saveChatMessages } from '../utils/chatStorage';
import { latestAnalyzedSessionId } from '../utils/sessionResolve';
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
import { deriveProvenanceFromSession, deriveRunProvenance, type ProvenanceSource } from '../utils/provenance';
import { VerticalResizeHandle } from '../components/Common/VerticalResizeHandle';
import { EngagementConflictBanner } from '../components/PageComponents/Procurement/EngagementConflictBanner';
import { useResizableWidth } from '../hooks/useResizableWidth';
import {
  conflictDismissKey,
  conflictSummaryMessage,
  engagementSanityFromManifest,
} from '../utils/engagementConflict';
import type { EngagementSanityConflict } from '../types';
import { useConfirm } from '../hooks/useConfirm';
import { useDialogA11y } from '../hooks/useDialogA11y';
import { useEngagementsList } from '../api/hooks/useEngagementQueries';
import { RunStatus } from '../components/PageComponents/Analysis/RunStatus';
import type { ManifestFileEntry } from '../utils/sessionFiles';
import type {
  AnalysisTraceStep,
  AuditLogEntry,
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
} from '../types';

const LLM_MODEL_STORAGE_KEY = 'opex_llm_model';

const CONFLICT_DISMISS_PREFIX = 'opex_conflict_dismiss_';
const DEEP_RESEARCH_DISMISS_PREFIX = 'opex_deep_research_dismiss_';
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

function loadDeepResearchDismissed(sessionId: string | null): boolean {
  if (!sessionId) return false;
  return localStorage.getItem(`${DEEP_RESEARCH_DISMISS_PREFIX}${sessionId}`) === '1';
}

function saveDeepResearchDismissed(sessionId: string) {
  localStorage.setItem(`${DEEP_RESEARCH_DISMISS_PREFIX}${sessionId}`, '1');
}

const PRE_RUN_PROVENANCE: ProvenanceSource[] = [
  { label: 'Uploaded spend', detail: 'Session files — run analysis for skill citations', kind: 'fact' },
  { label: 'OPAR synthesis', detail: 'Awaiting first run', kind: 'inference' },
];

const DeepResearchBanner: React.FC<{ companyName: string; onDismiss: () => void }> = ({
  companyName,
  onDismiss,
}) => (
  <div className="flex items-center justify-between gap-2 px-4 py-2 bg-blue-50 border-b border-blue-200 text-xs text-blue-800">
    <div className="flex items-center gap-2 min-w-0">
      <span className="font-semibold shrink-0">Deep research context loaded</span>
      <span className="text-blue-600">·</span>
      <span className="truncate">
        Google Deep Research findings for{' '}
        <span className="font-medium">{companyName}</span> are active as analysis context.
      </span>
    </div>
    <button
      type="button"
      onClick={onDismiss}
      className="shrink-0 text-blue-700 hover:text-blue-900 font-bold px-1"
      aria-label="Dismiss deep research banner"
    >
      ×
    </button>
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

function progressStepsFromTrace(trace?: AnalysisTraceStep[]): ProgressStep[] {
  if (!trace?.length) {
    return [{ phase: 'reflect', message: 'Analysis complete.' }];
  }
  const steps = trace.slice(0, 8).map((row) => ({
    phase: row.phase || 'act',
    message: row.detail ? `${row.title} — ${row.detail}` : row.title,
  }));
  if (!steps.some((s) => s.phase === 'reflect')) {
    steps.push({ phase: 'reflect', message: 'Analysis complete.' });
  }
  return steps;
}

async function pollChatProgress(
  runId: string,
  onSteps: (steps: ProgressStep[]) => void,
  onThinking: (thinking: string) => void,
  signal: AbortSignal,
  queryClient: QueryClient,
  onStall?: () => void,
): Promise<void> {
  let failures = 0;
  while (!signal.aborted) {
    try {
      const entry = await queryClient.fetchQuery({
        queryKey: procurementKeys.chatProgress(runId),
        queryFn: () => apiGet<ChatProgressResponse>(`/api/v1/chat/progress/${runId}`),
        staleTime: 0,
      });
      failures = 0;
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
      // Tolerate transient errors; only give up (and say so) after repeated failures.
      failures += 1;
      if (failures >= 5) {
        if (!signal.aborted) onStall?.();
        break;
      }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

function isDesktopViewport(): boolean {
  return typeof window === 'undefined' || !window.matchMedia || window.matchMedia('(min-width: 1024px)').matches;
}

const STOPPED_MESSAGE =
  'Stopped waiting for this run. The server may still finish it in the background — check History or re-run if results look incomplete.';

const CANCELLED_MESSAGE =
  'Analysis stopped. It ended between steps, so no partial results were saved. Run it again when ready.';

interface AnalysisRunStatus {
  run_id: string;
  status: 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled';
  error?: string | null;
}

/** Poll a background analysis run until it reaches a terminal state. */
async function waitForAnalysisRun(runId: string, signal: AbortSignal): Promise<AnalysisRunStatus> {
  let failures = 0;
  for (;;) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
    try {
      const run = await apiGet<AnalysisRunStatus>(`/api/v1/analyze/runs/${runId}`);
      failures = 0;
      if (run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled') return run;
    } catch (err) {
      failures += 1;
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 404) {
        throw new Error('The analysis run was lost (the server may have restarted). Run it again.');
      }
      if (failures >= 8) throw err;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
}

const STALL_STEP: ProgressStep = {
  phase: 'observe',
  message: 'Live progress is unavailable — still waiting on the server…',
};

export const ProcurementAnalysis: React.FC = () => {
  const queryClient = useQueryClient();
  const {
    sessionId,
    engagementId,
    setSessionId,
    ensureSession,
    ensureSessionForEngagement,
    ensureEngagement,
    createEngagement,
    setEngagementId,
    hasAnalysis,
    engagement,
    refreshEngagement,
    syncEngagementFromAnalysis,
    refreshAnalysisStatus,
    sessionAnalysis,
    refreshSessionAnalysis,
    deepResearchSummary,
  } = useSession();
  const sectorOptions = useSectorOptions();
  const engagementsQuery = useEngagementsList();
  const engagementList = engagementsQuery.data ?? [];
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  // A typed-but-unsent chat message is lost on navigation.
  useUnsavedGuard('procurement-chat-draft', input.trim().length > 0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const analysis = sessionAnalysis;
  const [manifest, setManifest] = useState<SessionManifest | null>(null);
  // On narrow screens the insights panel is a full-screen sheet; start closed there.
  const [insightsOpen, setInsightsOpen] = useState(isDesktopViewport);
  // Below 1024px the insights panel is a modal sheet: trap focus and close on Escape.
  const insightsSheetRef = useDialogA11y<HTMLDivElement>(
    insightsOpen && !isDesktopViewport(),
    () => setInsightsOpen(false),
  );
  const openInsightsOnDesktop = () => {
    if (isDesktopViewport()) setInsightsOpen(true);
  };
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
  const [provenanceSources, setProvenanceSources] = useState<ProvenanceSource[]>(PRE_RUN_PROVENANCE);
  const [narrativeTag, setNarrativeTag] = useState<Record<string, unknown> | null>(null);
  const [localAudit, setLocalAudit] = useState<AuditLogEntry[]>([]);
  const [deepResearchDismissed, setDeepResearchDismissed] = useState(() =>
    loadDeepResearchDismissed(sessionId),
  );
  const [agentSteps, setAgentSteps] = useState<ProgressStep[] | undefined>();
  const [agentDegraded, setAgentDegraded] = useState(false);
  const [agentFallbackReasons, setAgentFallbackReasons] = useState<
    Record<string, unknown> | undefined
  >();
  const [pipelineLabel, setPipelineLabel] = useState<string | undefined>();
  const [sectorUpdating, setSectorUpdating] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const [liveThinking, setLiveThinking] = useState('');
  const [recoveryNotice, setRecoveryNotice] = useState<string | null>(null);
  const [selectedLlmModel, setSelectedLlmModel] = useState('');
  const [conflictResolving, setConflictResolving] = useState(false);
  const [dismissedConflictKeys, setDismissedConflictKeys] = useState<Set<string>>(
    () => loadDismissedConflictKeys(sessionId),
  );
  const fileRef = useRef<HTMLInputElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const pollAbortRef = useRef<AbortController | null>(null);
  const runAbortRef = useRef<AbortController | null>(null);
  // The background analysis run being followed (target of the server-side cancel).
  const analysisRunIdRef = useRef<string | null>(null);
  const analysisStopRequestedRef = useRef(false);

  // Resume: if this session already has an analysis running (page reload, second tab), follow it.
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await apiGet<{ run: AnalysisRunStatus | null }>(`/api/v1/sessions/${sessionId}/analysis-run`);
        if (cancelled || !res.run || analysisRunIdRef.current) return;
        setAgentSteps([{ phase: 'observe', message: 'Resuming the analysis already in progress…' }]);
        setPipelineLabel('Core analysis pipeline');
        openInsightsOnDesktop();
        await followAnalysisRun(sessionId, res.run.run_id);
      } catch {
        /* no active run, or the check failed: nothing to resume */
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const refreshManifest = useCallback(async (sid: string) => {
    const m = await fetchSessionManifest(queryClient, sid);
    setManifest(m);
    return m;
  }, [queryClient]);

  useEffect(() => {
    setDismissedConflictKeys(loadDismissedConflictKeys(sessionId));
    setDeepResearchDismissed(loadDeepResearchDismissed(sessionId));
  }, [sessionId]);

  const applyRunProvenance = useCallback(
    (chat: V1ChatResponse, runId?: string) => {
      const prov = deriveRunProvenance({ chat, manifest, runId });
      setProvenanceSources(prov.sources.length > 0 ? prov.sources : PRE_RUN_PROVENANCE);
      setNarrativeTag(prov.narrativeTag);
      if (prov.localAudit.length > 0) {
        setLocalAudit((prev) => [...prov.localAudit, ...prev].slice(0, 40));
      }
    },
    [manifest],
  );

  const llmModelsQuery = useLlmModels();
  const llmModels = useMemo(() => llmModelsQuery.data?.models ?? [], [llmModelsQuery.data]);

  useEffect(() => {
    const res = llmModelsQuery.data;
    if (!res) return;
    const stored = localStorage.getItem(LLM_MODEL_STORAGE_KEY);
    const validStored = res.models?.some((m) => m.id === stored) ? stored : null;
    setSelectedLlmModel(validStored || res.default_model_id || res.models?.[0]?.id || '');
  }, [llmModelsQuery.data]);

  const handleLlmModelChange = (modelId: string) => {
    setSelectedLlmModel(modelId);
    if (modelId) {
      localStorage.setItem(LLM_MODEL_STORAGE_KEY, modelId);
    } else {
      localStorage.removeItem(LLM_MODEL_STORAGE_KEY);
    }
  };

  const engagementDocumentsQuery = useEngagementDocuments(engagementId);
  const engagementDocCount = engagementId
    ? engagementDocumentsQuery.data
      ? engagementDocumentsQuery.data.documents.filter((d) => d.status === 'ready').length
      : null
    : null;

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
        const status = await fetchSessionStatus(queryClient, sessionId);
        // When the active session has no analysis, prefer the engagement's most
        // recent analyzed session. An engagement can hold several sessions and
        // the active id may point at an empty sibling — without this, returning
        // to Analysis shows the blank welcome screen even though a completed
        // analysis exists for this engagement.
        if (!status.has_analysis && engagementId) {
          const analyzedId = await latestAnalyzedSessionId(engagementId);
          if (cancelled) return;
          if (analyzedId && analyzedId !== sessionId) {
            setSessionId(analyzedId);
            return; // effect re-runs with the adopted analyzed session
          }
        }
        if (!status.session_exists) {
          if (!cancelled) {
            setManifest(null);
            setMessages([]);
          }
          return;
        }

        const m = await fetchSessionManifest(queryClient, sessionId);
        if (cancelled) return;
        setManifest(m);
        setRecoveryNotice(null);

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
            const runSummary = (sess as SessionResponse).last_analysis_run;
            if (runSummary?.run_id) {
              setLastRunId(runSummary.run_id);
            }
            const advisorySections =
              sess && typeof sess.advisory_sections === 'object'
                ? (sess.advisory_sections as Record<string, unknown>)
                : undefined;
            if (advisorySections && Object.keys(advisorySections).length > 0) {
              const restoredProv = deriveProvenanceFromSession({
                manifest: m,
                advisorySections,
                runId: runSummary?.run_id ?? undefined,
              });
              setProvenanceSources(
                restoredProv.sources.length > 0 ? restoredProv.sources : PRE_RUN_PROVENANCE,
              );
              setNarrativeTag(restoredProv.narrativeTag);
            }
            const fallbackSteps = runSummary?.progress_steps;
            if ((!agentSteps || agentSteps.length === 0) && fallbackSteps?.length) {
              setAgentSteps(fallbackSteps);
              setLastSteps(fallbackSteps);
            }
            const snapshot = extractInsightSnapshot(sess, m);
            if (snapshot && snapshot.total_spend > 0) {
              setMessages((prev) => {
                if (chatHasInsightSnapshot(prev)) return prev;
                const rawTrace = (sess as { analysis_trace?: unknown }).analysis_trace;
                const trace = Array.isArray(rawTrace) ? (rawTrace as AnalysisTraceStep[]) : undefined;
                if ((!trace || trace.length === 0) && fallbackSteps?.length) {
                  setRecoveryNotice(
                    'Recovered this analysis from saved session history. Detailed step trace was unavailable, so a summary timeline is shown.',
                  );
                }
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
  }, [sessionId, engagementId, setSessionId, refreshSessionAnalysis, queryClient]);

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
    void pollChatProgress(runId, setAgentSteps, setLiveThinking, ac.signal, queryClient, () =>
      setAgentSteps((prev) => [...(prev ?? []), STALL_STEP]),
    );
  };

  const stopRun = () => {
    const analysisRunId = analysisRunIdRef.current;
    if (analysisRunId) {
      // Cooperative cancel: the server stops the run between stages (the current stage finishes first).
      analysisStopRequestedRef.current = true;
      setAgentSteps((prev) => [
        ...(prev ?? []),
        { phase: 'observe', message: 'Stopping after the current step…' },
      ]);
      void apiPost(`/api/v1/analyze/runs/${analysisRunId}/cancel`).catch(() => runAbortRef.current?.abort());
      // Safety net: if the server never confirms, stop waiting rather than hang.
      window.setTimeout(() => {
        if (analysisRunIdRef.current === analysisRunId) runAbortRef.current?.abort();
      }, 30000);
      return;
    }
    runAbortRef.current?.abort();
    stopPolling();
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
    const runController = runAbortRef.current ?? new AbortController();
    runAbortRef.current = runController;
    setLastRunId(runId);
    openInsightsOnDesktop();
    setPipelineLabel(undefined);
    setAgentSteps([{ phase: 'observe', message: 'Starting OPAR agent…' }]);
    let streamedText = '';
    setMessages((m) => [...m, { role: 'assistant', content: '', run_id: runId }]);

    try {
      const res = await streamChatPost(
        '/api/v1/chat/stream',
        {
          message: text,
          session_id: sid,
          run_id: runId,
          thinking_mode: thinkingMode ? 'extended' : 'standard',
          llm_model: selectedLlmModel || undefined,
          chat_history: chatHistoryPayload(messages),
          ...contextPayload(engagement, manifest),
        },
        (ev) => {
          if (ev.event === 'progress') {
            setAgentSteps((prev) => [
              ...(prev ?? []),
              { phase: ev.data.phase, message: ev.data.message },
            ]);
          }
          if (ev.event === 'thinking' && ev.data.chunk) {
            setMessages((m) =>
              m.map((msg) =>
                msg.run_id === runId && msg.role === 'assistant'
                  ? { ...msg, thinking: `${msg.thinking ?? ''}${ev.data.chunk}` }
                  : msg,
              ),
            );
          }
          if (ev.event === 'token' && ev.data.delta) {
            streamedText += ev.data.delta;
            setMessages((m) =>
              m.map((msg) =>
                msg.run_id === runId && msg.role === 'assistant'
                  ? { ...msg, content: streamedText }
                  : msg,
              ),
            );
          }
        },
        runController.signal,
      );
      if (!res) return;
      const chat = res as unknown as V1ChatResponse;
      if (chat.hitl_required && chat.clarification && chat.checkpoint_id) {
        setMessages((m) => m.filter((msg) => msg.run_id !== runId));
        openClarificationProbe({
          clarification: chat.clarification,
          checkpoint_id: chat.checkpoint_id,
        });
        return;
      }
      setLastSignals(chat.quality_signals);
      setLastSteps(chat.progress_steps);
      setAgentSteps(chat.progress_steps);
      setAgentDegraded(!!chat.degraded_mode);
      setAgentFallbackReasons(chat.fallback_reasons);
      applyRunProvenance(chat, chat.run_id ?? runId);
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
      const suppressCategoryInsight = chat.response_metadata?.insight_dimension === 'supplier';
      const nextOptions = buildAssistantNextOptions(
        snapshot,
        latestManifest,
        chat.next_options,
        showPeer,
        currentAnsweredProbeFamilies(),
      );
      const insightSnap =
        !suppressCategoryInsight && snapshot && (snapshot.total_spend > 0 || showPeer)
          ? snapshot
          : undefined;
      setMessages((m) =>
        m.map((msg) =>
          msg.run_id === runId && msg.role === 'assistant'
            ? {
                role: 'assistant',
                content: chat.response_text || streamedText || 'No response',
                thinking: chat.thinking,
                advisory_sections: chat.advisory_sections,
                presentation: chat.presentation,
                quality_signals: chat.quality_signals,
                next_options: nextOptions,
                run_id: chat.run_id,
                progress_steps: chat.progress_steps,
                degraded_mode: chat.degraded_mode,
                used_llm_synthesis: chat.used_llm_synthesis,
                fallback_reasons: chat.fallback_reasons,
                artefacts: chat.artefacts,
                insight_snapshot: insightSnap,
                show_peer_savings: showPeer,
                charts: chat.charts,
                suggested_outputs: chat.suggested_outputs,
                response_metadata: chat.response_metadata,
                run_delta: chat.run_delta,
              }
            : msg,
        ),
      );
      maybeAutoOpenProbeModal(insightSnap, currentAnsweredProbeFamilies(), chat.run_id);
    } catch (streamErr) {
      if (runController.signal.aborted) {
        setMessages((m) => [
          ...m.filter((msg) => msg.run_id !== runId),
          { role: 'assistant', content: STOPPED_MESSAGE },
        ]);
        return;
      }
      setMessages((m) => m.filter((msg) => msg.run_id !== runId));
      // Tell the user instead of silently re-sending: the fallback can repeat server work.
      setAgentSteps((prev) => [
        ...(prev ?? []),
        { phase: 'observe', message: 'Live streaming was interrupted — retrying without live updates…' },
      ]);
      const res = await apiPost<V1ChatResponse>(
        '/api/v1/chat',
        {
          message: text,
          session_id: sid,
          run_id: runId,
          thinking_mode: thinkingMode ? 'extended' : 'standard',
          llm_model: selectedLlmModel || undefined,
          chat_history: chatHistoryPayload(messages),
          ...contextPayload(engagement, manifest),
        },
        runController.signal,
      ).catch((err) => {
        if (runController.signal.aborted) return null;
        throw err;
      });
      if (!res) {
        setMessages((m) => [...m, { role: 'assistant', content: STOPPED_MESSAGE }]);
        return;
      }
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
      applyRunProvenance(res, res.run_id ?? runId);
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
          suggested_outputs: res.suggested_outputs,
          response_metadata: res.response_metadata,
          run_delta: res.run_delta,
        },
      ]);
      maybeAutoOpenProbeModal(insightSnap, currentAnsweredProbeFamilies(), res.run_id);
      if (streamErr instanceof Error && !res.response_text) {
        throw streamErr;
      }
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
    await uploadFiles(Array.from(e.target.files ?? []));
  };

  const uploadFiles = async (files: File[], targetEngagementId?: string) => {
    if (files.length === 0) return;
    setLoading(true);
    setError(null);
    openInsightsOnDesktop();

    let sid: string;
    let eid: string;
    try {
      eid = targetEngagementId ?? engagementId ?? (await ensureEngagement());
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

    // Keep the header's document count and the engagement switcher current.
    void queryClient.invalidateQueries({ queryKey: procurementKeys.engagementDocuments(eid) });
    void engagementsQuery.refetch();

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

  // First-run: a ready-made engagement so a new user can see a full analysis without their own data.
  const handleLoadDemo = async () => {
    setError(null);
    try {
      const res = await fetch('/api/v1/samples/spend-ledger.csv');
      if (!res.ok) throw new Error(`Sample ledger unavailable (${res.status})`);
      const file = new File([await res.blob()], 'spend_ledger_sample.csv', { type: 'text/csv' });
      const eid = await createEngagement({
        company_name: 'Demo engagement (sample ledger)',
        // The bundled ledger is IT/cloud/services-heavy, so use the matching sector pack.
        industry: 'it_ites',
        annual_revenue: 5000 * 1e7,
        currency: 'INR',
      });
      setMessages([]);
      await engagementsQuery.refetch();
      await uploadFiles([file], eid);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
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
      const plan = await apiPost<ChatPlanPreview>(
        '/api/v1/chat/plan',
        {
          message: text,
          session_id: sid,
          ...contextPayload(engagement, manifest),
        },
        runAbortRef.current?.signal,
      );
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
      if (runAbortRef.current?.signal.aborted) {
        setMessages((m) => [...m, { role: 'assistant', content: STOPPED_MESSAGE }]);
        return;
      }
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
    runAbortRef.current = new AbortController();
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
    runAbortRef.current = new AbortController();
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
    openInsightsOnDesktop();
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
      applyRunProvenance(res, res.run_id ?? runId);
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
          suggested_outputs: res.suggested_outputs,
          response_metadata: res.response_metadata,
          run_delta: res.run_delta,
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
    openInsightsOnDesktop();
    setPipelineLabel('Core analysis pipeline');
    // Real steps stream in via progress polling; seed with a single "starting"
    // line so the panel isn't empty for the first poll interval.
    setAgentSteps([{ phase: 'observe', message: 'Starting analysis…' }]);
    const runId =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `run-${Date.now()}`;
    try {
      const sid = await ensureSession();
      // Background run: returns at once with a run id, so the run survives a page reload
      // and can be cancelled server-side. If one is already running for this session we join it.
      const started = await apiPost<{ run_id: string }>(`/api/v1/analyze/${sid}`, {
        ...contextPayload(engagement, manifest),
        run_id: runId,
        background: true,
      });
      await followAnalysisRun(sid, started.run_id);
    } catch (err) {
      setError(getApiErrorMessage(err));
      setAgentSteps([{ phase: 'reflect', message: 'Analysis failed. See error above.' }]);
      setLoading(false);
    }
  };

  /** Follow a background analysis run to its end, then load and present the result. */
  const followAnalysisRun = async (sid: string, runId: string) => {
    setLoading(true);
    setLastRunId(runId);
    analysisRunIdRef.current = runId;
    analysisStopRequestedRef.current = false;
    const controller = new AbortController();
    runAbortRef.current = controller;
    const pollPromise = pollChatProgress(
      runId,
      setAgentSteps,
      setLiveThinking,
      controller.signal,
      queryClient,
      () => setAgentSteps((prev) => [...(prev ?? []), STALL_STEP]),
    );
    try {
      const run = await waitForAnalysisRun(runId, controller.signal);
      controller.abort();
      await pollPromise.catch(() => undefined);
      if (run.status === 'cancelled') {
        setAgentSteps([{ phase: 'reflect', message: 'Stopped.' }]);
        setMessages((prev) => [...prev, { role: 'assistant', content: CANCELLED_MESSAGE }]);
        return;
      }
      if (run.status === 'failed') {
        throw new Error(run.error || 'Analysis failed.');
      }
      const analysisResult = await apiGet<SessionResponse>(`/api/v1/sessions/${sid}`);
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
      const fallbackSteps = progressStepsFromTrace(trace);
      setLastSteps(fallbackSteps);
      setPipelineLabel(undefined);
      const advisorySections =
        session && typeof session.advisory_sections === 'object'
          ? (session.advisory_sections as Record<string, unknown>)
          : undefined;
      const analyzeProv = deriveProvenanceFromSession({
        manifest: m,
        advisorySections,
        runId,
      });
      setProvenanceSources(analyzeProv.sources.length > 0 ? analyzeProv.sources : PRE_RUN_PROVENANCE);
      setNarrativeTag(analyzeProv.narrativeTag);
      if (analyzeProv.localAudit.length > 0) {
        setLocalAudit((prev) => [...analyzeProv.localAudit, ...prev].slice(0, 40));
      }
      if (snapshot) {
        const sessionExtras: Partial<ChatMessage> = {};
        if (advisorySections && Object.keys(advisorySections).length > 0) {
          sessionExtras.advisory_sections = advisorySections;
        }
        if (session?.response_metadata && typeof session.response_metadata === 'object') {
          sessionExtras.response_metadata = session.response_metadata as ChatMessage['response_metadata'];
        }
        if (session?.used_llm_synthesis === false) {
          sessionExtras.used_llm_synthesis = false;
        }
        if (Array.isArray(session?.suggested_outputs) && session!.suggested_outputs!.length > 0) {
          sessionExtras.suggested_outputs = session!.suggested_outputs as ChatMessage['suggested_outputs'];
        }
        if (session?.run_delta && typeof session.run_delta === 'object') {
          sessionExtras.run_delta = session.run_delta as ChatMessage['run_delta'];
        }
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
            ...sessionExtras,
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
      const userStopped = analysisStopRequestedRef.current;
      controller.abort();
      if (userStopped) {
        setAgentSteps([{ phase: 'reflect', message: 'Stopped.' }]);
        setMessages((prev) => [...prev, { role: 'assistant', content: STOPPED_MESSAGE }]);
        return;
      }
      setError(getApiErrorMessage(err));
      setAgentSteps([{ phase: 'reflect', message: 'Analysis failed. See error above.' }]);
      setLastSteps([{ phase: 'reflect', message: 'Analysis failed. See error above.' }]);
    } finally {
      analysisRunIdRef.current = null;
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

  const [confirm, confirmDialog] = useConfirm();

  const handleNewSession = async () => {
    if (messages.length > 0) {
      const ok = await confirm({
        title: 'Start a new session?',
        message:
          'The current conversation will be cleared from this view. Your uploaded data and earlier analyses stay saved on the engagement.',
        confirmLabel: 'New session',
      });
      if (!ok) return;
    }
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
      setSessionId(res.session_id);
      setMessages([]);
      setManifest(res);
      setAgentSteps(undefined);
      setLastSteps(undefined);
      setPipelineLabel(undefined);
      setRecoveryNotice(null);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const currentIndustry = effectiveAnalysisIndustry(manifest, engagement);

  return (
    <MainLayout hideHeader>
      {confirmDialog}
      <div className="flex flex-col h-[calc(100vh-2rem)] -m-4 md:-m-6">
        <header className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-4 md:px-6 py-2 border-b border-brand-border bg-white shrink-0">
          <PageHeader
            title="Analysis"
            subtitle="Human-in-the-loop spend intelligence"
            sessionId={sessionId}
            compact
          />
          {engagementList.length > 1 && (
            <select
              aria-label="Switch engagement"
              value={engagementId ?? ''}
              disabled={loading}
              onChange={(e) => {
                if (!e.target.value || e.target.value === engagementId) return;
                setMessages([]);
                setSessionId(null);
                setEngagementId(e.target.value);
              }}
              className="text-xs border border-brand-border rounded-lg px-2 py-1 bg-white text-brand-ink max-w-[14rem]"
            >
              {engagementList.map((en) => (
                <option key={en.engagement_id} value={en.engagement_id}>
                  {en.company_name || 'Untitled'} · {en.engagement_id.slice(0, 6)}
                </option>
              ))}
            </select>
          )}
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
              <Link to="/documents" className="text-brand-primary hover:underline shrink-0">
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
                  aria-label="Sector"
                  value={currentIndustry}
                  onChange={(e) => void handleSectorChange(e.target.value)}
                  disabled={sectorUpdating || loading}
                  className="py-1.5 px-2.5 text-xs"
                  options={[
                    { value: '', label: 'Select sector…' },
                    ...sectorOptions.map((o) => ({ value: o.value, label: o.label })),
                  ]}
                />
              </div>
              {engagement.detected_industry && (
                <RecommendedBadge
                  variant="compact"
                  label={
                    engagement.detected_industry_label ||
                    sectorLabel(engagement.detected_industry) ||
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
                  aria-label="AI model"
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
                  ? 'border-deloitte-green text-brand-primary bg-deloitte-green/5'
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
        {recoveryNotice && (
          <div className="px-4 md:px-6 pt-3 shrink-0">
            <Alert
              variant="info"
              title="Recovered analysis context"
              onDismiss={() => setRecoveryNotice(null)}
            >
              {recoveryNotice}
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
            {deepResearchSummary && !deepResearchDismissed && (
              <DeepResearchBanner
                companyName={engagement.company_name}
                onDismiss={() => {
                  if (sessionId) saveDeepResearchDismissed(sessionId);
                  setDeepResearchDismissed(true);
                }}
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
                    <ol className="grid grid-cols-2 xl:grid-cols-4 gap-2 max-w-2xl mx-auto mb-6 text-left">
                      {[
                        { n: 1, title: 'Add data', body: 'Upload a spend ledger or P&L.', done: (engagementDocCount ?? 0) > 0 },
                        { n: 2, title: 'Run analysis', body: 'Classify spend, benchmark, size savings.', done: hasAnalysis },
                        { n: 3, title: 'Explore', body: 'Ask questions here or use the Workbench.', done: false },
                        { n: 4, title: 'Decide', body: 'Track initiatives in the Cost Room.', done: false },
                      ].map((step) => (
                        <li
                          key={step.n}
                          className="rounded-xl border border-brand-border bg-white px-3 py-2"
                        >
                          <span
                            className={`inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-semibold mr-2 ${
                              step.done ? 'bg-brand-primary text-white' : 'bg-brand-surface-muted text-brand-muted'
                            }`}
                            aria-hidden
                          >
                            {step.done ? '✓' : step.n}
                          </span>
                          <span className="text-sm font-medium text-brand-ink">{step.title}</span>
                          {step.done && <span className="sr-only"> (done)</span>}
                          <p className="text-xs text-brand-muted mt-1">{step.body}</p>
                        </li>
                      ))}
                    </ol>
                    <div className="flex flex-wrap justify-center gap-2 mb-6">
                      <button
                        type="button"
                        onClick={() => fileRef.current?.click()}
                        className="text-sm px-4 py-2 rounded-lg bg-deloitte-green text-black font-medium hover:opacity-90"
                      >
                        Attach your data
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleLoadDemo()}
                        className="text-sm px-4 py-2 rounded-lg border border-brand-border bg-white text-brand-ink hover:bg-brand-surface-muted"
                      >
                        Load demo engagement
                      </button>
                    </div>
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
                      className="text-xs text-brand-muted hover:text-brand-primary underline underline-offset-2 transition-colors"
                    >
                      Download spend template ↓
                    </a>
                    <span className="text-xs text-brand-muted mx-2">·</span>
                    <a
                      href="/api/v1/samples/spend-ledger.csv"
                      download="spend_ledger_sample.csv"
                      className="text-xs text-brand-muted hover:text-brand-primary underline underline-offset-2 transition-colors"
                    >
                      Sample ledger CSV ↓
                    </a>
                    <span className="text-xs text-brand-muted mx-2">·</span>
                    <a
                      href="/api/v1/samples/pnl-expense.xlsx"
                      download="pnl_expense_summary_sample.xlsx"
                      className="text-xs text-brand-muted hover:text-brand-primary underline underline-offset-2 transition-colors"
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
                        sessionId={sessionId || undefined}
                        engagementId={engagementId ?? engagement.engagement_id}
                        onExportError={(msg) => setError(msg)}
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
                      <div className="flex justify-start gap-3 max-w-[85%] w-full">
                        <span
                          className="w-8 h-8 rounded-full bg-black flex items-center justify-center shrink-0 text-[10px] font-bold text-white"
                          aria-hidden
                        >
                          AI
                        </span>
                        <div className="flex-1 min-w-0">
                          <RunStatus steps={agentSteps} onStop={stopRun} />
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
              onStop={stopRun}
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
                    onOpenProbes={
                      insightSnapshot
                        ? () => openSmeProbeModal(insightSnapshot, answeredProbeFamilies)
                        : undefined
                    }
                  />
                </div>
              </aside>
            </>
          )}
        </div>

        {insightsOpen && (
          <div
            ref={insightsSheetRef}
            tabIndex={-1}
            className="lg:hidden fixed inset-0 z-40 flex flex-col justify-end outline-none"
            role="dialog"
            aria-modal="true"
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
                  onOpenProbes={
                    insightSnapshot
                      ? () => openSmeProbeModal(insightSnapshot, answeredProbeFamilies)
                      : undefined
                  }
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
        localAudit={localAudit}
        runId={lastRunId}
        progressSteps={lastSteps}
        degradedMode={agentDegraded}
        qualitySignals={lastSignals}
        provenanceSources={provenanceSources}
        narrativeTag={narrativeTag}
      />
    </MainLayout>
  );
};
