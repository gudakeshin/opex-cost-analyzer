import { useQuery, type QueryClient } from '@tanstack/react-query';
import { apiGet } from '../../hooks/useApi';
import { sessionKeys, engagementKeys } from '../queryKeys';
import type {
  EngagementSummary,
  SessionManifest,
  SessionResponse,
  SessionSummary,
} from '../../types';

// Short grace window for passive page-level reads (Diagnostic, Benchmarks,
// ProcurementAnalysis) so navigating between pages shortly after
// SessionContext already fetched the manifest doesn't re-fetch it.
// SessionContext's own internal calls always bypass this via staleTime: 0 —
// they're "refresh" semantics and must never serve stale cache.
const PASSIVE_STALE_TIME_MS = 10_000;

export interface SessionStatus {
  session_exists?: boolean;
  has_manifest?: boolean;
  has_analysis?: boolean;
  file_count?: number;
}

export interface EngagementDetail {
  company_name?: string;
  industry?: string;
  currency?: string;
  annual_revenue?: number;
  detected_company_name?: string;
  detected_industry?: string;
  detected_industry_label?: string;
  detected_annual_revenue_cr?: number;
}

export type SessionManifestResult = SessionManifest & {
  deep_research_summary?: string;
  peer_set_name?: string;
};

const manifestQuery = (sessionId: string) => ({
  queryKey: sessionKeys.manifest(sessionId),
  queryFn: () => apiGet<SessionManifestResult>(`/api/v1/sessions/${sessionId}/manifest`),
});

const statusQuery = (sessionId: string) => ({
  queryKey: sessionKeys.status(sessionId),
  queryFn: () => apiGet<SessionStatus>(`/api/v1/sessions/${sessionId}/status`),
});

const analysisQuery = (sessionId: string) => ({
  queryKey: sessionKeys.analysis(sessionId),
  queryFn: () => apiGet<SessionResponse>(`/api/v1/sessions/${sessionId}`),
});

const engagementDetailQuery = (engagementId: string) => ({
  queryKey: engagementKeys.detail(engagementId),
  queryFn: () => apiGet<EngagementDetail>(`/api/v1/engagements/${engagementId}`),
});

// --- Passive hooks for page components (replace independent apiGet calls) ---

export function useSessionManifest(sessionId: string | null | undefined) {
  return useQuery({
    ...manifestQuery(sessionId ?? ''),
    enabled: !!sessionId,
    staleTime: PASSIVE_STALE_TIME_MS,
  });
}

// --- Imperative fetchers for SessionContext's own always-fresh reads ---
// staleTime: 0 forces a real network call every time (identical to today's
// apiGet behavior) while still writing the result into the shared cache so
// the passive hooks above benefit without an extra request.

export function fetchSessionManifest(queryClient: QueryClient, sessionId: string) {
  return queryClient.fetchQuery({ ...manifestQuery(sessionId), staleTime: 0 });
}

export function fetchSessionStatus(queryClient: QueryClient, sessionId: string) {
  return queryClient.fetchQuery({ ...statusQuery(sessionId), staleTime: 0 });
}

export function fetchSessionAnalysis(queryClient: QueryClient, sessionId: string) {
  return queryClient.fetchQuery({ ...analysisQuery(sessionId), staleTime: 0 });
}

export function fetchEngagementDetail(queryClient: QueryClient, engagementId: string) {
  return queryClient.fetchQuery({ ...engagementDetailQuery(engagementId), staleTime: 0 });
}

export function setSessionManifestData(
  queryClient: QueryClient,
  sessionId: string,
  data: SessionManifestResult,
) {
  queryClient.setQueryData(sessionKeys.manifest(sessionId), data);
}

export async function listEngagements(): Promise<EngagementSummary[]> {
  return apiGet<EngagementSummary[]>('/api/v1/engagements');
}

export function useSessionsList() {
  return useQuery({
    queryKey: sessionKeys.list(),
    queryFn: () => apiGet<SessionSummary[]>('/api/v1/sessions'),
  });
}
