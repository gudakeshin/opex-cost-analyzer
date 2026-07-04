import React, { useEffect, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { useSession } from '../context/SessionContext';
import { SectorPackGrid } from '../components/PageComponents/Benchmarks/SectorPackGrid';
import { BenchmarkToolsPanel } from '../components/PageComponents/Benchmarks/BenchmarkToolsPanel';
import {
  SectorPackDetailDrawer,
  type SectorPackRow,
} from '../components/PageComponents/Benchmarks/SectorPackDetailDrawer';
import { useQueryClient } from '@tanstack/react-query';
import { apiPatch, getApiErrorMessage } from '../hooks/useApi';
import {
  fetchSessionManifest,
  setSessionManifestData,
  type SessionManifestResult,
} from '../api/hooks/useSessionQueries';
import {
  useInvalidateBenchmarkReferenceData,
  usePeerSets,
  useSectorPacks,
} from '../api/hooks/useBenchmarksQueries';

export const Benchmarks: React.FC = () => {
  const queryClient = useQueryClient();
  const { sessionId, ensureSession } = useSession();
  const sectorPacksQuery = useSectorPacks();
  const peerSetsQuery = usePeerSets();
  const invalidateReferenceData = useInvalidateBenchmarkReferenceData();
  const sectorPacks = sectorPacksQuery.data?.packs ?? [];
  const peerSets = peerSetsQuery.data?.peer_sets ?? [];
  const loading = sectorPacksQuery.isLoading || peerSetsQuery.isLoading;
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [detailPack, setDetailPack] = useState<SectorPackRow | null>(null);
  const [activePeerSet, setActivePeerSet] = useState<string | null>(null);

  useEffect(() => {
    const spFailed = sectorPacksQuery.isError;
    const psFailed = peerSetsQuery.isError;
    if (spFailed && psFailed) {
      setError(getApiErrorMessage(sectorPacksQuery.error));
    } else if (spFailed || psFailed) {
      const message = getApiErrorMessage(spFailed ? sectorPacksQuery.error : peerSetsQuery.error);
      setNotice(`Some reference data could not be loaded: ${message}`);
    }
  }, [sectorPacksQuery.isError, sectorPacksQuery.error, peerSetsQuery.isError, peerSetsQuery.error]);

  useEffect(() => {
    (async () => {
      const sid = sessionId || (await ensureSession());
      if (!sid) return;
      try {
        const manifest = await fetchSessionManifest(queryClient, sid);
        if (manifest.peer_set_name) setActivePeerSet(manifest.peer_set_name);
      } catch {
        /* optional */
      }
    })();
  }, [sessionId, ensureSession, queryClient]);

  const setEngagementPeerSet = async (name: string | null) => {
    const sid = sessionId || (await ensureSession());
    if (!sid) return;
    try {
      const updated = await apiPatch<SessionManifestResult>(`/api/v1/sessions/${sid}/manifest`, {
        peer_set_name: name,
      });
      setSessionManifestData(queryClient, sid, updated);
      setActivePeerSet(name);
      setNotice(name ? `Peer set “${name}” set as session default.` : 'Peer set default cleared.');
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  return (
    <MainLayout>
      <PageHeader
        title="Sector Packs"
        subtitle="Sector reference data for peer comparison, lever modelling, and diagnostics"
      />

      {error && (
        <Alert variant="error" title="Error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}
      {notice && (
        <Alert variant="success" title="Done" onDismiss={() => setNotice(null)}>
          {notice}
        </Alert>
      )}

      <SectorPackGrid
        packs={sectorPacks}
        loading={loading}
        activePeerSet={activePeerSet}
        onSelectPack={setDetailPack}
        onClearPeerSet={() => setEngagementPeerSet(null)}
      />

      <BenchmarkToolsPanel
        peerSets={peerSets}
        sectorPacks={sectorPacks}
        onError={setError}
        onNotice={setNotice}
        onPeerSetsChanged={invalidateReferenceData}
        onDatasetsChanged={invalidateReferenceData}
        onOpenSectorPack={setDetailPack}
        onSetEngagementPeerSet={(name) => setEngagementPeerSet(name)}
      />

      <SectorPackDetailDrawer pack={detailPack} onClose={() => setDetailPack(null)} />
    </MainLayout>
  );
};
