import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiDelete, apiGet, apiPost } from '../hooks/useApi';
import { manifestAudienceToMode, useAudience } from './AudienceContext';
import { isPlaceholderCompanyName } from '../utils/engagement';
import type { EngagementMeta, EngagementSummary, SessionManifest, SessionResponse } from '../types';

const STORAGE_KEY = 'opex_session_id';
const ENGAGEMENT_STORAGE_KEY = 'opex_engagement_id';

interface SessionContextValue {
  sessionId: string | null;
  engagementId: string | null;
  setSessionId: (id: string | null) => void;
  setEngagementId: (id: string | null) => void;
  ensureSession: () => Promise<string>;
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

  const refreshEngagementMeta = useCallback(async (eid: string) => {
    const detail = await apiGet<{
      company_name?: string;
      industry?: string;
      currency?: string;
      annual_revenue?: number;
      detected_company_name?: string;
      detected_industry?: string;
      detected_industry_label?: string;
    }>(`/api/v1/engagements/${eid}`);
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
    });
  }, []);

  const refreshEngagement = useCallback(async () => {
    if (!sessionId) return;
    setLoadingEngagement(true);
    try {
      const status = await apiGet<{
        session_exists?: boolean;
        has_analysis?: boolean;
      }>(`/api/v1/sessions/${sessionId}/status`);
      if (!status.session_exists) {
        setSessionIdState(null);
        setHasAnalysis(false);
        return;
      }
      setHasAnalysis(!!status.has_analysis);

      const manifest = await apiGet<SessionManifest & { deep_research_summary?: string }>(
        `/api/v1/sessions/${sessionId}/manifest`,
      );
      if (manifest.engagement_id) {
        setEngagementIdState(manifest.engagement_id);
      }
      setEngagement(engagementFromManifest(manifest));
      // Merge auto-detected company/industry recommendations from the engagement
      // manifest (the session manifest doesn't carry them) so the Diagnostic and
      // Analysis pages can surface the "Recommended" badge.
      if (manifest.engagement_id) {
        try {
          const detail = await apiGet<{
            detected_company_name?: string;
            detected_industry?: string;
            detected_industry_label?: string;
          }>(`/api/v1/engagements/${manifest.engagement_id}`);
          setEngagement((prev) => ({
            ...prev,
            detected_company_name: detail.detected_company_name || undefined,
            detected_industry: detail.detected_industry || undefined,
            detected_industry_label: detail.detected_industry_label || undefined,
          }));
        } catch {
          /* detection is best-effort; ignore */
        }
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
  }, [sessionId, setAudience]);

  const refreshAnalysisStatus = useCallback(async () => {
    if (!sessionId) {
      setHasAnalysis(false);
      return;
    }
    try {
      const status = await apiGet<{
        session_exists?: boolean;
        has_analysis?: boolean;
      }>(`/api/v1/sessions/${sessionId}/status`);
      if (!status.session_exists) {
        setSessionIdState(null);
        setHasAnalysis(false);
        return;
      }
      setHasAnalysis(!!status.has_analysis);
    } catch {
      setHasAnalysis(false);
    }
  }, [sessionId]);

  const refreshSessionAnalysis = useCallback(async (): Promise<SessionResponse | null> => {
    if (!sessionId) {
      setSessionAnalysis(null);
      setHasAnalysis(false);
      return null;
    }
    try {
      const status = await apiGet<{
        session_exists?: boolean;
        has_analysis?: boolean;
      }>(`/api/v1/sessions/${sessionId}/status`);
      if (!status.session_exists || !status.has_analysis) {
        setSessionAnalysis(null);
        setHasAnalysis(false);
        return null;
      }
      const analysis = await apiGet<SessionResponse>(`/api/v1/sessions/${sessionId}`);
      setSessionAnalysis(analysis);
      setHasAnalysis(true);
      return analysis;
    } catch {
      setSessionAnalysis(null);
      setHasAnalysis(false);
      return null;
    }
  }, [sessionId]);

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

  const setSessionId = useCallback((id: string | null) => {
    setSessionIdState(id);
    if (!id) {
      setHasAnalysis(false);
      setSessionAnalysis(null);
      setDeepResearchSummary(null);
    }
  }, []);

  const setEngagementId = useCallback(
    (id: string | null) => {
      setEngagementIdState(id);
      if (id) {
        refreshEngagementMeta(id).catch(() => undefined);
      } else {
        setEngagement(defaultEngagement);
      }
    },
    [refreshEngagementMeta],
  );

  const listEngagements = useCallback(async () => {
    return apiGet<EngagementSummary[]>('/api/v1/engagements');
  }, []);

  const deleteEngagement = useCallback(
    async (id: string) => {
      await apiDelete(`/api/v1/engagement/${id}`);
      if (id === engagementId) {
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

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    const eid = await ensureEngagement();
    const res = await apiPost<SessionManifest>('/api/v1/sessions', {
      company_name: engagement.company_name,
      industry: engagement.industry,
      currency: engagement.currency || 'INR',
      audience: 'consultant',
      engagement_id: eid,
    });
    setSessionIdState(res.session_id);
    if (res.engagement_id) setEngagementIdState(res.engagement_id);
    setEngagement(engagementFromManifest(res));
    return res.session_id;
  }, [sessionId, ensureEngagement, engagement.company_name, engagement.industry, engagement.currency]);

  const value = useMemo(
    () => ({
      sessionId,
      engagementId,
      setSessionId,
      setEngagementId,
      ensureSession,
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
      ensureSession,
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
