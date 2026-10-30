import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../hooks/useApi';
import { workbenchKeys } from '../queryKeys';
import type { WorkbenchCatalog, WorkbenchRun } from '../../types';

export function useWorkbenchCatalog() {
  return useQuery({
    queryKey: workbenchKeys.catalog(),
    queryFn: () => apiGet<WorkbenchCatalog>('/api/v1/workbench/catalog'),
  });
}

export function useWorkbenchRuns(
  engagementId: string | null | undefined,
  sessionId: string | null | undefined,
) {
  const params = engagementId
    ? `engagement_id=${engagementId}`
    : sessionId
      ? `session_id=${sessionId}`
      : '';
  return useQuery({
    queryKey: workbenchKeys.runs(engagementId, sessionId),
    queryFn: () => apiGet<{ runs: WorkbenchRun[] }>(`/api/v1/workbench/runs?${params}`),
    enabled: !!params,
  });
}

export interface WorkbenchProgress {
  steps?: { message?: string }[];
  phase?: string;
}

export function useWorkbenchProgress(runId: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: workbenchKeys.progress(runId),
    queryFn: () => apiGet<WorkbenchProgress>(`/api/v1/workbench/progress/${runId}`),
    enabled: enabled && !!runId,
    staleTime: 0,
    refetchInterval: 800,
    retry: false,
  });
}
