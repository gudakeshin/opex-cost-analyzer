import React, { useCallback, useEffect, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { useSession } from '../context/SessionContext';
import { SectorPackGrid } from '../components/PageComponents/Benchmarks/SectorPackGrid';
import {
  BenchmarkToolsPanel,
  type PeerSet,
} from '../components/PageComponents/Benchmarks/BenchmarkToolsPanel';
import {
  SectorPackDetailDrawer,
  type SectorPackRow,
} from '../components/PageComponents/Benchmarks/SectorPackDetailDrawer';
import { apiGet, apiPatch, getApiErrorMessage } from '../hooks/useApi';

export const Benchmarks: React.FC = () => {
  const { sessionId, ensureSession } = useSession();
  const [sectorPacks, setSectorPacks] = useState<SectorPackRow[]>([]);
  const [peerSets, setPeerSets] = useState<PeerSet[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [detailPack, setDetailPack] = useState<SectorPackRow | null>(null);
  const [activePeerSet, setActivePeerSet] = useState<string | null>(null);

  const loadPacksAndPeerSets = useCallback(async () => {
    setLoading(true);
    setError(null);
    const errors: string[] = [];
    try {
      const [spRes, psRes] = await Promise.allSettled([
        apiGet<{ packs: SectorPackRow[] }>('/api/v1/sector-packs'),
        apiGet<{ peer_sets: PeerSet[] }>('/api/v1/benchmarks/peer-sets'),
      ]);
      if (spRes.status === 'fulfilled') {
        setSectorPacks(spRes.value.packs ?? []);
      } else {
        errors.push(getApiErrorMessage(spRes.reason));
      }
      if (psRes.status === 'fulfilled') {
        setPeerSets(psRes.value.peer_sets ?? []);
      } else {
        errors.push(getApiErrorMessage(psRes.reason));
      }
      if (errors.length === 2) {
        setError(errors[0]);
      } else if (errors.length > 0) {
        setNotice(`Some reference data could not be loaded: ${errors.join('; ')}`);
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPacksAndPeerSets();
  }, [loadPacksAndPeerSets]);

  useEffect(() => {
    (async () => {
      const sid = sessionId || (await ensureSession());
      if (!sid) return;
      try {
        const manifest = await apiGet<{ peer_set_name?: string }>(`/api/v1/sessions/${sid}/manifest`);
        if (manifest.peer_set_name) setActivePeerSet(manifest.peer_set_name);
      } catch {
        /* optional */
      }
    })();
  }, [sessionId, ensureSession]);

  const setEngagementPeerSet = async (name: string | null) => {
    const sid = sessionId || (await ensureSession());
    if (!sid) return;
    try {
      await apiPatch(`/api/v1/sessions/${sid}/manifest`, { peer_set_name: name });
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
        onPeerSetsChanged={loadPacksAndPeerSets}
        onDatasetsChanged={loadPacksAndPeerSets}
        onOpenSectorPack={setDetailPack}
        onSetEngagementPeerSet={(name) => setEngagementPeerSet(name)}
      />

      <SectorPackDetailDrawer pack={detailPack} onClose={() => setDetailPack(null)} />
    </MainLayout>
  );
};
