import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../hooks/useApi';
import { procurementKeys } from '../queryKeys';
import type { LlmModelsResponse } from '../../types';

export interface EngagementDocumentsResult {
  documents: { status: string }[];
}

export function useEngagementDocuments(engagementId: string | null | undefined) {
  return useQuery({
    queryKey: procurementKeys.engagementDocuments(engagementId),
    queryFn: () =>
      apiGet<EngagementDocumentsResult>(`/api/v1/engagements/${engagementId}/documents`),
    enabled: !!engagementId,
  });
}

export function useLlmModels() {
  return useQuery({
    queryKey: procurementKeys.llmModels(),
    queryFn: () => apiGet<LlmModelsResponse>('/api/v1/llm/models'),
    staleTime: Infinity,
  });
}
