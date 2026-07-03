import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPut } from '../../hooks/useApi';
import { costRoomKeys, sessionKeys } from '../queryKeys';
import type {
  ComplianceAuditResponse,
  ConflictSpendImpact,
  ConflictSummary,
  BvaResponse,
  CostToServeResponse,
  Initiative,
  InitiativeProvenance,
  PaymentTermsResponse,
  PipelineSummary,
  SensitivityResponse,
  TrendsResponse,
} from '../../types';
import type { ScenarioPreset } from '../../components/PageComponents/CostRoom/ScenarioControls';

function normalizeInitiative(row: Initiative): Initiative {
  return {
    ...row,
    aqs: row.aqs ?? row.assumption_quality_score,
    owner_name: row.owner_name ?? row.owner_role,
  };
}

function scenarioExecutionRate(scenario: ScenarioPreset): number | undefined {
  if (scenario === 'conservative') return 0.6;
  if (scenario === 'accelerated') return 0.9;
  return undefined;
}

function pipelineQueryString(engagementId: string | null): string {
  const params = new URLSearchParams({ qualified_only: 'true' });
  if (engagementId) params.set('engagement_id', engagementId);
  return params.toString();
}

export function useInitiativesQuery(engagementId: string | null) {
  return useQuery({
    queryKey: costRoomKeys.initiatives(engagementId),
    queryFn: async () => {
      const res = await apiGet<{ initiatives: Initiative[] }>(
        `/api/v1/initiatives?${pipelineQueryString(engagementId)}`,
      );
      return res.initiatives.map(normalizeInitiative);
    },
  });
}

export function usePipelineSummaryQuery(engagementId: string | null) {
  return useQuery({
    queryKey: costRoomKeys.summary(engagementId),
    queryFn: () => apiGet<PipelineSummary>(`/api/v1/pipeline/summary?${pipelineQueryString(engagementId)}`),
  });
}

export function useSensitivityQuery(sessionId: string | null, scenario: ScenarioPreset) {
  return useQuery({
    queryKey: costRoomKeys.sensitivity(sessionId, scenario),
    queryFn: () => {
      const execRate = scenarioExecutionRate(scenario);
      const qs = execRate != null ? `?execution_rate_pct=${execRate}` : '';
      return apiGet<SensitivityResponse>(`/api/v1/sensitivity/${sessionId}${qs}`);
    },
    enabled: !!sessionId,
  });
}

export function useConflictsQuery(sessionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: costRoomKeys.conflicts(sessionId),
    queryFn: () => apiGet<ConflictSummary>(`/api/v1/conflicts/${sessionId}`),
    enabled: !!sessionId && enabled,
  });
}

const FPA_TAB_FETCHERS = {
  trends: (sid: string) => apiGet<TrendsResponse>(`/api/v1/trends/${sid}`),
  bva: (sid: string) => apiGet<BvaResponse>(`/api/v1/bva/${sid}`),
  'payment-terms': (sid: string) => apiGet<PaymentTermsResponse>(`/api/v1/payment-terms/${sid}`),
  'cost-to-serve': (sid: string) =>
    apiPost<CostToServeResponse>('/api/v1/cost-to-serve', { session_id: sid }),
} as const;

type FpaTab = keyof typeof FPA_TAB_FETCHERS;

export function useFpaTabQuery<T extends FpaTab>(tab: T, sessionId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: costRoomKeys.fpaTab(tab, sessionId),
    queryFn: () => FPA_TAB_FETCHERS[tab](sessionId as string),
    enabled: !!sessionId && enabled,
    staleTime: Infinity,
  });
}

export function useMilestonesQuery(initiativeId: string | null) {
  return useQuery({
    queryKey: costRoomKeys.milestones(initiativeId),
    queryFn: async () => {
      const res = await apiGet<{ milestones: unknown[] }>(
        `/api/v1/initiatives/${initiativeId}/milestones`,
      );
      return (res.milestones ?? []) as Record<string, unknown>[];
    },
    enabled: !!initiativeId,
  });
}

export function useProvenanceQuery(initiativeId: string | null) {
  return useQuery({
    queryKey: costRoomKeys.provenance(initiativeId),
    queryFn: () => apiGet<InitiativeProvenance>(`/api/v1/initiatives/${initiativeId}/provenance`),
    enabled: !!initiativeId,
  });
}

export function useAuditLogLatestQuery(trigger: number) {
  return useQuery({
    queryKey: costRoomKeys.auditLogLatest(trigger),
    queryFn: () => apiGet<ComplianceAuditResponse>('/api/v1/compliance/audit-log?limit=1'),
  });
}

function invalidatePipeline(queryClient: ReturnType<typeof useQueryClient>, engagementId: string | null) {
  queryClient.invalidateQueries({ queryKey: costRoomKeys.initiatives(engagementId) });
  queryClient.invalidateQueries({ queryKey: costRoomKeys.summary(engagementId) });
}

export function useInitiativeStageMutation(engagementId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ initiativeId, stage }: { initiativeId: string; stage: 'committed' | 'deferred' }) =>
      apiPut(`/api/v1/initiatives/${initiativeId}/stage`, { stage }),
    onSuccess: () => invalidatePipeline(queryClient, engagementId),
  });
}

export function useInitiativeRejectMutation(engagementId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ initiativeId, reason }: { initiativeId: string; reason: string }) =>
      apiPut(`/api/v1/initiatives/${initiativeId}/reject`, { reason }),
    onSuccess: () => invalidatePipeline(queryClient, engagementId),
  });
}

export function useAddActualsMutation(engagementId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ initiativeId, amount }: { initiativeId: string; amount: number }) =>
      apiPost(`/api/v1/initiatives/${initiativeId}/actuals`, { amount_cr: amount }),
    onSuccess: () => invalidatePipeline(queryClient, engagementId),
  });
}

export function useConsolidateMutation(engagementId: string | null, sessionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost(`/api/v1/consolidate/${sessionId}`, {}),
    onSuccess: () => invalidatePipeline(queryClient, engagementId),
  });
}

interface ResolveConflictResult {
  resolved_count?: number;
  escalated_count?: number;
  spend_impact?: ConflictSpendImpact | null;
}

export function useResolveConflictMutation(engagementId: string | null, sessionId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conflictId, strategy }: { conflictId: string; strategy: string }) =>
      apiPost<ResolveConflictResult>(`/api/v1/conflicts/resolve?session_id=${sessionId}`, {
        conflict_ids: [conflictId],
        strategy,
      }),
    onSuccess: (result) => {
      if (result.spend_impact && (result.spend_impact.spend_delta ?? 0) !== 0) {
        invalidatePipeline(queryClient, engagementId);
        queryClient.invalidateQueries({ queryKey: sessionKeys.analysis(sessionId) });
      }
      queryClient.invalidateQueries({ queryKey: costRoomKeys.conflicts(sessionId) });
    },
  });
}

export function useExportBusinessCaseMutation(sessionId: string | null) {
  return useMutation({
    mutationFn: () =>
      apiPost<{ exports?: { docx?: string; pdf_report_text?: string } }>(
        `/api/v1/business-case/${sessionId}`,
        {},
      ),
  });
}

export function useExportExcelMutation(sessionId: string | null) {
  return useMutation({
    mutationFn: () =>
      apiPost<{ export_url?: string; filename?: string }>(`/api/v1/pmo-export/${sessionId}`, {}),
  });
}
