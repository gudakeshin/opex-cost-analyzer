import { useQuery } from '@tanstack/react-query';
import { apiGet } from '../../hooks/useApi';
import { diagnosticKeys } from '../queryKeys';
import type { DeepResearchStatusResponse } from '../../types';

export function useDeepResearchStatus(
  interactionId: string | null | undefined,
  sessionId: string | null | undefined,
  enabled: boolean,
) {
  return useQuery({
    queryKey: diagnosticKeys.deepResearchStatus(interactionId, sessionId),
    queryFn: () => {
      const sessionParam = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
      return apiGet<DeepResearchStatusResponse>(
        `/api/v1/diagnostic/deep-research/${interactionId}${sessionParam}`,
      );
    },
    enabled: enabled && !!interactionId,
    staleTime: 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'failed') return false;
      return 30_000;
    },
  });
}
