import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet } from '../../hooks/useApi';
import { benchmarkKeys } from '../queryKeys';
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
