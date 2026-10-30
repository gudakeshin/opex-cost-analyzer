import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { apiDelete, apiPost } from '../hooks/useApi';
import {
  fetchEngagementDetail,
  fetchSessionAnalysis,
  fetchSessionManifest,
  fetchSessionStatus,
  listEngagements as listEngagementsRequest,
  setSessionManifestData,
} from '../api/hooks/useSessionQueries';
import { manifestAudienceToMode, useAudience } from './AudienceContext';
import { isPlaceholderCompanyName } from '../utils/engagement';
import { latestAnalyzedSessionId } from '../utils/sessionResolve';
import type { EngagementMeta, EngagementSummary, SessionManifest, SessionResponse } from '../types';

const STORAGE_KEY = 'opex_session_id';
const ENGAGEMENT_STORAGE_KEY = 'opex_engagement_id';

interface SessionContextValue {
  sessionId: string | null;
  engagementId: string | null;
  setSessionId: (id: string | null) => void;
  setEngagementId: (id: string | null) => void;
  resumeSession: (id: string, engagementId?: string | null) => void;
  ensureSession: () => Promise<string>;
  ensureSessionForEngagement: (targetEngagementId?: string) => Promise<string>;
  ensureEngagement: () => Promise<string>;
  listEngagements: () => Promise<EngagementSummary[]>;
  deleteEngagement: (id: string) => Promise<void>;
  createEngagement: (payload?: {
    company_name?: string;
    industry?: string;
    annual_revenue?: number;
    currency?: string;
  }) => Promise<string>;
  engagement: EngagementMeta;
  refreshEngagement: () => Promise<void>;
  loadingEngagement: boolean;
  hasAnalysis: boolean;
  refreshAnalysisStatus: () => Promise<void>;
  sessionAnalysis: SessionResponse | null;
  spendBaseRevision: number;
  refreshSessionAnalysis: () => Promise<SessionResponse | null>;
  syncEngagementFromAnalysis: () => Promise<void>;
  deepResearchSummary: string | null;
}

const defaultEngagement: EngagementMeta = {
  company_name: 'New engagement',
  industry: 'manufacturing_diversified',
  currency: 'INR',
  engagement_week: 1,
  engagement_weeks_total: 12,
  gate_label: 'Gate 1: Data & diagnostic',
  annual_revenue_cr: undefined,
};

const SessionContext = createContext<SessionContextValue | null>(null);

function engagementFromManifest(manifest: SessionManifest): EngagementMeta {
  const created = manifest.created_at ? new Date(manifest.created_at) : new Date();
  const weeksSince = Math.max(
    1,
    Math.min(12, Math.floor((Date.now() - created.getTime()) / (7 * 24 * 60 * 60 * 1000)) + 1),
  );
  const revenue = manifest.annual_revenue;
  return {
    engagement_id: manifest.engagement_id,
    company_name: manifest.company_name || defaultEngagement.company_name,
    industry: manifest.industry || defaultEngagement.industry,
    currency: manifest.currency || 'INR',
    audience: manifest.audience,
    engagement_week: manifest.engagement_week ?? weeksSince,
    engagement_weeks_total: manifest.engagement_weeks_total ?? 12,
    gate_label: manifest.gate_label ?? defaultEngagement.gate_label,
    annual_revenue_cr:
      revenue != null && revenue > 1_000_000 ? revenue / 10_000_000 : revenue,
  };
}

export const SessionProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const { setAudience } = useAudience();
  const [sessionId, setSessionIdState] = useState<string | null>(() =>
    localStorage.getItem(STORAGE_KEY),
  );
  const [engagementId, setEngagementIdState] = useState<string | null>(() =>
    localStorage.getItem(ENGAGEMENT_STORAGE_KEY),
  );
  const [engagement, setEngagement] = useState<EngagementMeta>(defaultEngagement);
  const [loadingEngagement, setLoadingEngagement] = useState(false);
  const [hasAnalysis, setHasAnalysis] = useState(false);
  const [sessionAnalysis, setSessionAnalysis] = useState<SessionResponse | null>(null);
  const [deepResearchSummary, setDeepResearchSummary] = useState<string | null>(null);

  const spendBaseRevision = Number(sessionAnalysis?.spend_base_revision ?? 0);

  useEffect(() => {
    if (sessionId) localStorage.setItem(STORAGE_KEY, sessionId);
    else localStorage.removeItem(STORAGE_KEY);
  }, [sessionId]);

  useEffect(() => {
    if (engagementId) localStorage.setItem(ENGAGEMENT_STORAGE_KEY, engagementId);
    else localStorage.removeItem(ENGAGEMENT_STORAGE_KEY);
  }, [engagementId]);

  // Whenever the active session changes (create/switch/delete engagement,
  // resume, or mismatch-recreate), drop results derived from the previous
  // session so one engagement never shows another's analysis/deep research.
  useEffect(() => {
    setHasAnalysis(false);
    setSessionAnalysis(null);
    setDeepResearchSummary(null);
  }, [sessionId]);

  const refreshEngagementMeta = useCallback(async (eid: string) => {
    const detail = await fetchEngagementDetail(queryClient, eid);
    const revenue = detail.annual_revenue;
    setEngagement({
      company_name: detail.company_name || defaultEngagement.company_name,
      industry: detail.industry || defaultEngagement.industry,
      currency: detail.currency || 'INR',
      engagement_week: 1,
      engagement_weeks_total: 12,
      gate_label: defaultEngagement.gate_label,
      annual_revenue_cr:
        revenue != null && revenue > 1_000_000 ? revenue / 10_000_000 : revenue,
      detected_company_name: detail.detected_company_name || undefined,
      detected_industry: detail.detected_industry || undefined,
      detected_industry_label: detail.detected_industry_label || undefined,
      detected_annual_revenue_cr:
        detail.detected_annual_revenue_cr != null && detail.detected_annual_revenue_cr > 0
          ? detail.detected_annual_revenue_cr
          : undefined,
    });
  }, [queryClient]);

  const refreshEngagement = useCallback(async () => {
    setLoadingEngagement(true);
    try {
      const activeEngagementId = engagementId;

      if (activeEngagementId) {
        await refreshEngagementMeta(activeEngagementId);
      }

      if (!sessionId) {
        return;
      }

      const status = await fetchSessionStatus(queryClient, sessionId);
      if (!status.session_exists) {
        setSessionIdState(null);
        setHasAnalysis(false);
        return;
      }
      setHasAnalysis(!!status.has_analysis);

      const manifest = await fetchSessionManifest(queryClient, sessionId);

      // Never let a stale session override the user's selected engagement.
      if (!activeEngagementId && manifest.engagement_id) {
        setEngagementIdState(manifest.engagement_id);
        await refreshEngagementMeta(manifest.engagement_id);
      } else if (!activeEngagementId) {
        setEngagement(engagementFromManifest(manifest));
      }

      const mode = manifestAudienceToMode(manifest.audience);
      if (mode) setAudience(mode);
      setDeepResearchSummary(manifest.deep_research_summary ?? null);
    } catch (err) {
      if ((err as { response?: { status?: number } })?.response?.status === 404) {
        setSessionIdState(null);
        setHasAnalysis(false);
      }
    } finally {
      setLoadingEngagement(false);
    }
  }, [sessionId, engagementId, refreshEngagementMeta, setAudience, queryClient]);

  const refreshAnalysisStatus = useCallback(async () => {
    if (!sessionId) {
      setHasAnalysis(false);
      return;
    }
    try {
      const status = await fetchSessionStatus(queryClient, sessionId);
      if (!status.session_exists) {
        setSessionIdState(null);
        setHasAnalysis(false);
        return;
      }
      setHasAnalysis(!!status.has_analysis);
    } catch {
      setHasAnalysis(false);
    }
  }, [sessionId, queryClient]);

  const refreshSessionAnalysis = useCallback(async (): Promise<SessionResponse | null> => {
    if (!sessionId) {
      setSessionAnalysis(null);
      setHasAnalysis(false);
      return null;
    }
    try {
      const status = await fetchSessionStatus(queryClient, sessionId);
      if (!status.session_exists || !status.has_analysis) {
        setSessionAnalysis(null);
        setHasAnalysis(false);
        return null;
      }
      const analysis = await fetchSessionAnalysis(queryClient, sessionId);
      setSessionAnalysis(analysis);
      setHasAnalysis(true);
      return analysis;
    } catch {
      setSessionAnalysis(null);
      setHasAnalysis(false);
      return null;
    }
  }, [sessionId, queryClient]);

  const syncEngagementFromAnalysis = useCallback(async () => {
    const analysis = await refreshSessionAnalysis();
    if (!analysis) return;
    if (analysis.company_name && !isPlaceholderCompanyName(analysis.company_name)) {
      setEngagement((prev) => ({
        ...prev,
        company_name: analysis.company_name!,
        industry: analysis.industry || prev.industry,
        gate_label: 'Gate 2: Portfolio sign-off',
        engagement_week: Math.max(prev.engagement_week, 2),
        annual_revenue_cr:
          analysis.annual_revenue != null && analysis.annual_revenue > 1_000_000
            ? analysis.annual_revenue / 10_000_000
            : analysis.annual_revenue ?? prev.annual_revenue_cr,
      }));
    }
    await refreshEngagement();
  }, [refreshSessionAnalysis, refreshEngagement]);

  useEffect(() => {
    refreshEngagement();
    refreshAnalysisStatus();
  }, [refreshEngagement, refreshAnalysisStatus]);

  useEffect(() => {
    if (engagementId) {
      refreshEngagementMeta(engagementId).catch(() => undefined);
    }
  }, [engagementId, refreshEngagementMeta]);

  const setSessionId = useCallback((id: string | null) => {
    setSessionIdState(id);
  }, []);

  const setEngagementId = useCallback(
    (id: string | null) => {
      // Re-selecting the already-active engagement must not clear the session —
      // doing so orphans the active analysis and blanks the workspace. Only a
      // genuine switch to a different engagement resets the session.
      if (id && id === engagementId) {
        refreshEngagementMeta(id).catch(() => undefined);
        return;
      }
      setSessionIdState(null);
      setEngagementIdState(id);
      if (id) {
        refreshEngagementMeta(id).catch(() => undefined);
      } else {
        setEngagement(defaultEngagement);
      }
    },
    [engagementId, refreshEngagementMeta],
  );

  const resumeSession = useCallback(
    (id: string, nextEngagementId?: string | null) => {
      // History resume must keep session + engagement aligned in one transition.
      // Using setEngagementId() here would clear session by design.
      setSessionIdState(id);
      if (nextEngagementId !== undefined) {
        setEngagementIdState(nextEngagementId);
        if (nextEngagementId) {
          refreshEngagementMeta(nextEngagementId).catch(() => undefined);
        } else {
          setEngagement(defaultEngagement);
        }
      }
    },
    [refreshEngagementMeta],
  );

  const listEngagements = useCallback(async () => {
    return listEngagementsRequest();
  }, []);

  const deleteEngagement = useCallback(
    async (id: string) => {
      await apiDelete(`/api/v1/engagement/${id}`);
      if (id === engagementId) {
        setSessionIdState(null);
        setEngagementIdState(null);
        setEngagement(defaultEngagement);
      }
    },
    [engagementId],
  );

  const createEngagement = useCallback(
    async (payload?: {
      company_name?: string;
      industry?: string;
      annual_revenue?: number;
      currency?: string;
    }) => {
      setSessionIdState(null);
      const res = await apiPost<{ engagement_id: string }>('/api/v1/engagements', {
        company_name: payload?.company_name ?? 'New engagement',
        industry: payload?.industry ?? '',
        annual_revenue: payload?.annual_revenue ?? 0,
        currency: payload?.currency ?? 'INR',
      });
      setEngagementIdState(res.engagement_id);
      await refreshEngagementMeta(res.engagement_id);
      return res.engagement_id;
    },
    [refreshEngagementMeta],
  );

  const ensureEngagement = useCallback(async (): Promise<string> => {
    if (engagementId) return engagementId;
    return createEngagement();
  }, [engagementId, createEngagement]);

  // Concurrent callers (e.g. an effect re-firing because a prior call's own
  // intermediate setSessionIdState/setEngagementIdState mutated its deps)
  // must await the same in-flight ensure rather than each independently
  // concluding "nothing exists yet" and creating their own session/engagement.
  //
  // `target` starts null and is mutated in place once the in-flight call
  // resolves which engagement it's actually operating on. A no-arg caller
  // always merges (it means "whatever's current"); an explicit-target caller
  // merges as long as the in-flight call hasn't resolved its target yet, or
  // has resolved to the same one — this matters because the in-flight call's
  // own intermediate state updates (setEngagementIdState) can cause a fresh
  // effect fire with an explicit target *before* our code resumes past the
  // await that would otherwise register that target here.
  const ensureSessionInFlightRef = useRef<{ target: string | null; promise: Promise<string> } | null>(
    null,
  );

  const ensureSessionForEngagement = useCallback(
    (targetEngagementId?: string): Promise<string> => {
      const requested = targetEngagementId ?? null;
      const inFlight = ensureSessionInFlightRef.current;
      if (
        inFlight &&
        (requested === null || inFlight.target === null || inFlight.target === requested)
      ) {
        return inFlight.promise;
      }

      const entry: { target: string | null; promise: Promise<string> } = {
        target: requested,
        promise: undefined as unknown as Promise<string>,
      };

      entry.promise = (async (): Promise<string> => {
        let target = requested ?? engagementId;
        if (!target) {
          target = await ensureEngagement();
        }
        entry.target = target;

        if (sessionId) {
          try {
            const existing = await fetchSessionManifest(queryClient, sessionId);
            if (existing.engagement_id === target) {
              return sessionId;
            }
          } catch {
            /* stale or missing session — create a new one below */
          }
          setSessionIdState(null);
        }

        // Before creating a new (empty) session, adopt the engagement's most
        // recent analyzed session if one exists — otherwise each entry point that
        // ensures a session spawns an empty sibling, and the workspace renders
        // blank despite a completed analysis for this engagement.
        const analyzedId = await latestAnalyzedSessionId(target);
        if (analyzedId) {
          setSessionIdState(analyzedId);
          setEngagementIdState(target);
          await refreshEngagementMeta(target);
          return analyzedId;
        }

        const detail = await fetchEngagementDetail(queryClient, target);

        const res = await apiPost<SessionManifest>('/api/v1/sessions', {
          company_name: detail.company_name,
          industry: detail.industry || '',
          currency: detail.currency || 'INR',
          audience: 'consultant',
          engagement_id: target,
        });
        setSessionManifestData(queryClient, res.session_id, res);
        setSessionIdState(res.session_id);
        setEngagementIdState(target);
        await refreshEngagementMeta(target);
        return res.session_id;
      })();

      ensureSessionInFlightRef.current = entry;
      entry.promise
        .catch(() => undefined)
        .finally(() => {
          if (ensureSessionInFlightRef.current === entry) {
            ensureSessionInFlightRef.current = null;
          }
        });
      return entry.promise;
    },
    [sessionId, engagementId, ensureEngagement, refreshEngagementMeta, queryClient],
  );

  const ensureSession = useCallback(async (): Promise<string> => {
    return ensureSessionForEngagement();
  }, [ensureSessionForEngagement]);

  const value = useMemo(
    () => ({
      sessionId,
      engagementId,
      setSessionId,
      setEngagementId,
      resumeSession,
      ensureSession,
      ensureSessionForEngagement,
      ensureEngagement,
      listEngagements,
      deleteEngagement,
      createEngagement,
      engagement,
      refreshEngagement,
      loadingEngagement,
      hasAnalysis,
      refreshAnalysisStatus,
      sessionAnalysis,
      spendBaseRevision,
      refreshSessionAnalysis,
      syncEngagementFromAnalysis,
      deepResearchSummary,
    }),
    [
      sessionId,
      engagementId,
      setSessionId,
      setEngagementId,
      resumeSession,
      ensureSession,
      ensureSessionForEngagement,
      ensureEngagement,
      listEngagements,
      deleteEngagement,
      createEngagement,
      engagement,
      refreshEngagement,
      loadingEngagement,
      hasAnalysis,
      refreshAnalysisStatus,
      sessionAnalysis,
      spendBaseRevision,
      refreshSessionAnalysis,
      syncEngagementFromAnalysis,
      deepResearchSummary,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
};

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
