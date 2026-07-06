import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPut, apiUpload } from '../../hooks/useApi';
import { benchmarkKeys } from '../queryKeys';
import { SECTOR_OPTIONS } from '../../constants/sectors';
import type {
  BenchmarkDatasetRow,
  CoverageResponse,
} from '../../components/PageComponents/Benchmarks/BenchmarkDetailDrawer';
import type { PeerSet } from '../../components/PageComponents/Benchmarks/BenchmarkToolsPanel';
import type {
  SectorPackDetailResponse,
  SectorPackRow,
} from '../../components/PageComponents/Benchmarks/SectorPackDetailDrawer';

export function useSectorPacks() {
  return useQuery({
    queryKey: benchmarkKeys.sectorPacks(),
    queryFn: () => apiGet<{ packs: SectorPackRow[] }>('/api/v1/sector-packs'),
  });
}

export function useSectorOptions() {
  const packsQuery = useSectorPacks();
  return useMemo(() => {
    const packs = packsQuery.data?.packs ?? [];
    if (!packs.length) {
      return SECTOR_OPTIONS.map((o) => ({ value: o.value, label: o.label }));
    }
    return packs.map((p) => ({
      value: p.pack_id,
      label: p.sector || p.pack_id.replace(/_/g, ' '),
    }));
  }, [packsQuery.data]);
}

export function usePeerSets() {
  return useQuery({
    queryKey: benchmarkKeys.peerSets(),
    queryFn: () => apiGet<{ peer_sets: PeerSet[] }>('/api/v1/benchmarks/peer-sets'),
  });
}

export function useBenchmarkDatasets(enabled: boolean) {
  return useQuery({
    queryKey: benchmarkKeys.datasets(),
    queryFn: () => apiGet<{ datasets: BenchmarkDatasetRow[] }>('/api/v1/benchmarks'),
    enabled,
  });
}

export function useBenchmarkCoverage(datasetId: string | null | undefined) {
  return useQuery({
    queryKey: benchmarkKeys.coverage(datasetId),
    queryFn: () => apiGet<CoverageResponse>(`/api/v1/benchmarks/${datasetId}/coverage`),
    enabled: !!datasetId,
  });
}

export function useSectorPackDetail(packId: string | null | undefined) {
  return useQuery({
    queryKey: benchmarkKeys.packDetail(packId),
    queryFn: () => apiGet<SectorPackDetailResponse>(`/api/v1/sector-packs/${packId}/detail`),
    enabled: !!packId,
  });
}

export function useInvalidateBenchmarkReferenceData() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: benchmarkKeys.sectorPacks() });
    queryClient.invalidateQueries({ queryKey: benchmarkKeys.peerSets() });
  };
}

export function useUpdatePackComponent(packId: string | null) {
  const invalidate = useInvalidateBenchmarkReferenceData();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ component, payload }: { component: string; payload: unknown }) =>
      apiPut(`/api/v1/sector-packs/${packId}/components/${component}`, { payload }),
    onSuccess: () => {
      invalidate();
      if (packId) queryClient.invalidateQueries({ queryKey: benchmarkKeys.packDetail(packId) });
    },
  });
}

export function useCreateSectorPack() {
  const invalidate = useInvalidateBenchmarkReferenceData();
  return useMutation({
    mutationFn: (body: { pack_id: string; sector: string; description?: string }) =>
      apiPost('/api/v1/sector-packs', body),
    onSuccess: () => invalidate(),
  });
}

export function usePublishSectorPack(packId: string | null) {
  const invalidate = useInvalidateBenchmarkReferenceData();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { bump: string; target_status?: string | null }) =>
      apiPost(`/api/v1/sector-packs/${packId}/publish`, body),
    onSuccess: () => {
      invalidate();
      if (packId) queryClient.invalidateQueries({ queryKey: benchmarkKeys.packDetail(packId) });
    },
  });
}

export function usePackRegressionTest(packId: string | null) {
  return useMutation({
    mutationFn: () =>
      apiGet<{ passed: boolean; checks: Record<string, boolean>; errors: string[] }>(
        `/api/v1/sector-packs/${packId}/regression-test`,
      ),
  });
}

export function useImportPackWorkbook() {
  const invalidate = useInvalidateBenchmarkReferenceData();
  return useMutation({
    mutationFn: ({ file, dryRun, packId }: { file: File; dryRun: boolean; packId?: string }) => {
      const fd = new FormData();
      fd.append('file', file);
      const qs = new URLSearchParams({ dry_run: String(dryRun) });
      if (packId) qs.set('pack_id', packId);
      return apiUpload<Record<string, unknown>>(`/api/v1/sector-packs/import?${qs}`, fd);
    },
    onSuccess: () => invalidate(),
  });
}
