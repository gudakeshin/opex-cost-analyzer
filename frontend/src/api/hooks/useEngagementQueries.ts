import { useQuery, type QueryClient } from '@tanstack/react-query';
import { apiGet } from '../../hooks/useApi';
import { engagementKeys, procurementKeys } from '../queryKeys';
import { listEngagements } from './useSessionQueries';
import type { EngagementDocument } from '../../types';

const engagementsListQuery = () => ({
  queryKey: engagementKeys.list(),
  queryFn: listEngagements,
});

export function useEngagementsList() {
  return useQuery(engagementsListQuery());
}

export function fetchEngagementsList(queryClient: QueryClient) {
  return queryClient.fetchQuery({ ...engagementsListQuery(), staleTime: 0 });
}

export interface EngagementDocumentsFullResult {
  documents: EngagementDocument[];
  llamaparse_configured?: boolean;
}

export function useEngagementDocumentsFull(engagementId: string | null | undefined) {
  return useQuery({
    queryKey: procurementKeys.engagementDocuments(engagementId),
    queryFn: () =>
      apiGet<EngagementDocumentsFullResult>(`/api/v1/engagements/${engagementId}/documents`),
    enabled: !!engagementId,
    refetchInterval: (query) => {
      const docs = query.state.data?.documents ?? [];
      const hasPending = docs.some((d) => d.status === 'pending' || d.status === 'processing');
      return hasPending ? 2500 : false;
    },
  });
}
