import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiGet, apiPost } from '../hooks/useApi';
import { manifestAudienceToMode, useAudience } from './AudienceContext';
import { isPlaceholderCompanyName } from '../utils/engagement';
import type { EngagementMeta, SessionManifest } from '../types';

const STORAGE_KEY = 'opex_session_id';

interface SessionContextValue {
  sessionId: string | null;
  setSessionId: (id: string | null) => void;
  ensureSession: () => Promise<string>;
  engagement: EngagementMeta;
  refreshEngagement: () => Promise<void>;
  loadingEngagement: boolean;
  hasAnalysis: boolean;
  refreshAnalysisStatus: () => Promise<void>;
  syncEngagementFromAnalysis: () => Promise<void>;
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
  const [engagement, setEngagement] = useState<EngagementMeta>(defaultEngagement);
  const [loadingEngagement, setLoadingEngagement] = useState(false);
  const [hasAnalysis, setHasAnalysis] = useState(false);

  useEffect(() => {
    if (sessionId) localStorage.setItem(STORAGE_KEY, sessionId);
    else localStorage.removeItem(STORAGE_KEY);
  }, [sessionId]);

  const refreshEngagement = useCallback(async () => {
    if (!sessionId) return;
    setLoadingEngagement(true);
    try {
      const manifest = await apiGet<SessionManifest>(`/api/sessions/${sessionId}/manifest`);
      setEngagement(engagementFromManifest(manifest));
      const mode = manifestAudienceToMode(manifest.audience);
      if (mode) setAudience(mode);
    } catch {
      /* keep defaults when manifest unavailable */
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
      await apiGet(`/api/sessions/${sessionId}`);
      setHasAnalysis(true);
    } catch {
      setHasAnalysis(false);
    }
  }, [sessionId]);

  const syncEngagementFromAnalysis = useCallback(async () => {
    if (!sessionId) return;
    try {
      const analysis = await apiGet<{
        company_name?: string;
        industry?: string;
        annual_revenue?: number;
      }>(`/api/sessions/${sessionId}`);
      setHasAnalysis(true);
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
    } catch {
      setHasAnalysis(false);
    }
  }, [sessionId, refreshEngagement]);

  useEffect(() => {
    refreshEngagement();
    refreshAnalysisStatus();
  }, [refreshEngagement, refreshAnalysisStatus]);

  const setSessionId = useCallback((id: string | null) => {
    setSessionIdState(id);
    if (!id) {
      setHasAnalysis(false);
      setEngagement(defaultEngagement);
    }
  }, []);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    const res = await apiPost<SessionManifest>('/api/sessions', {
      company_name: 'New engagement',
      industry: '',
      currency: 'INR',
      audience: 'consultant',
    });
    setSessionIdState(res.session_id);
    setEngagement(engagementFromManifest(res));
    return res.session_id;
  }, [sessionId]);

  const value = useMemo(
    () => ({
      sessionId,
      setSessionId,
      ensureSession,
      engagement,
      refreshEngagement,
      loadingEngagement,
      hasAnalysis,
      refreshAnalysisStatus,
      syncEngagementFromAnalysis,
    }),
    [
      sessionId,
      setSessionId,
      ensureSession,
      engagement,
      refreshEngagement,
      loadingEngagement,
      hasAnalysis,
      refreshAnalysisStatus,
      syncEngagementFromAnalysis,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
};

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used within SessionProvider');
  return ctx;
}
