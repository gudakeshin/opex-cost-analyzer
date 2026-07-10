import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiDelete, apiGet, apiPost } from '../../hooks/useApi';
import { workbenchKeys } from '../queryKeys';

export interface SpendSchema {
  columns: { name: string; type: string }[];
  sample_values: Record<string, string[]>;
  line_count: number;
  total_spend: number;
  views: Record<string, string>;
}

export interface SavedQuery {
  query_id: string;
  name: string;
  sql: string;
  description: string;
  saved_at: string;
}

export interface HistoryEntry {
  history_id: string;
  sql: string;
  row_count: number;
  elapsed_ms: number;
  source: string;
  question?: string;
  executed_at: string;
}

export interface ScenarioSpec {
  name: string;
  target: 'portfolio' | 'category' | 'lever';
  id?: string;
  savings_pct_delta: number;
  timeline_factor: number;
  execution_rate?: number;
  spend_pool_delta_pct: number;
  addressable_spend_delta_pct: number;
  bounce_back_override?: string;
  cost_driver_deltas?: Record<string, number>;
}

export interface SavedScenarioSet {
  set_id: string;
  name: string;
  description: string;
  scenarios: ScenarioSpec[];
  drivers: Record<string, number>;
  saved_at: string;
}

export function useSpendSchema(sessionId: string | null) {
  return useQuery({
    queryKey: workbenchKeys.querySchema(sessionId),
    queryFn: () => apiGet<SpendSchema>(`/api/v1/query/${sessionId}/schema`),
    enabled: !!sessionId,
  });
}

export function useQueryHistory(sessionId: string | null) {
  return useQuery({
    queryKey: workbenchKeys.queryHistory(sessionId),
    queryFn: () =>
      apiGet<{ entries: HistoryEntry[] }>(`/api/v1/query/${sessionId}/history`).then(
        (d) => d.entries ?? [],
      ),
    enabled: !!sessionId,
  });
}

export function useSavedQueries(sessionId: string | null) {
  return useQuery({
    queryKey: workbenchKeys.savedQueries(sessionId),
    queryFn: () =>
      apiGet<{ queries: SavedQuery[] }>(`/api/v1/query/${sessionId}/saved`).then(
        (d) => d.queries ?? [],
      ),
    enabled: !!sessionId,
  });
}

export function useSaveQuery(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; sql: string; description?: string }) =>
      apiPost(`/api/v1/query/${sessionId}/saved`, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workbenchKeys.savedQueries(sessionId) });
    },
  });
}

export function useDeleteSavedQuery(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (queryId: string) => apiDelete(`/api/v1/query/${sessionId}/saved/${queryId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workbenchKeys.savedQueries(sessionId) });
    },
  });
}

export function useSavedScenarioSets(sessionId: string | null) {
  return useQuery({
    queryKey: workbenchKeys.savedScenarioSets(sessionId),
    queryFn: () =>
      apiGet<{ sets: SavedScenarioSet[] }>(`/api/v1/sensitivity/${sessionId}/saved`).then(
        (d) => d.sets ?? [],
      ),
    enabled: !!sessionId,
  });
}

export function useSaveScenarioSet(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      name: string;
      scenarios: ScenarioSpec[];
      drivers?: Record<string, number>;
      description?: string;
    }) => apiPost(`/api/v1/sensitivity/${sessionId}/saved`, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workbenchKeys.savedScenarioSets(sessionId) });
    },
  });
}

export function useDeleteScenarioSet(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (setId: string) =>
      apiDelete(`/api/v1/sensitivity/${sessionId}/saved/${setId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workbenchKeys.savedScenarioSets(sessionId) });
    },
  });
}
