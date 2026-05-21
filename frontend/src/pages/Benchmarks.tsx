import React, { useEffect, useState } from 'react';
import { MainLayout } from '../components/Layout/MainLayout';
import { Card } from '../components/Common/Card';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { apiGet, getApiErrorMessage } from '../hooks/useApi';

interface BenchmarkDataset {
  dataset_id: string;
  name: string;
  industry?: string;
  year?: number;
}

interface SectorPack {
  pack_id: string;
  name: string;
  industry?: string;
  version?: string;
}

export const Benchmarks: React.FC = () => {
  const [datasets, setDatasets] = useState<BenchmarkDataset[]>([]);
  const [sectorPacks, setSectorPacks] = useState<SectorPack[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      apiGet<{ datasets: BenchmarkDataset[] } | BenchmarkDataset[]>('/api/v1/benchmarks'),
      apiGet<{ packs: SectorPack[] } | SectorPack[]>('/api/v1/sector-packs'),
    ])
      .then(([bmRes, spRes]) => {
        const bm = Array.isArray(bmRes) ? bmRes : (bmRes as { datasets: BenchmarkDataset[] }).datasets ?? [];
        const sp = Array.isArray(spRes) ? spRes : (spRes as { packs: SectorPack[] }).packs ?? [];
        setDatasets(bm);
        setSectorPacks(sp);
      })
      .catch((err) => setError(getApiErrorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <MainLayout>
      <PageHeader
        title="Benchmarks & Sector Packs"
        subtitle="Reference datasets for peer comparison and sector modelling"
      />

      {error && (
        <Alert variant="error" title="Load error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading ? (
        <div className="mt-12">
          <Loader label="Loading reference data…" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          <Card title="Benchmark Datasets" className="bg-white border-brand-border">
            {datasets.length === 0 ? (
              <p className="text-sm text-brand-muted py-4">
                No benchmark datasets loaded. Upload a benchmark file to get started.
              </p>
            ) : (
              <ul className="divide-y divide-brand-border">
                {datasets.map((d) => (
                  <li key={d.dataset_id} className="py-3">
                    <p className="text-sm font-medium text-brand-ink">{d.name}</p>
                    {(d.industry ?? d.year) && (
                      <p className="text-xs text-brand-muted mt-0.5">
                        {[d.industry, d.year].filter(Boolean).join(' · ')}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Sector Packs" className="bg-white border-brand-border">
            {sectorPacks.length === 0 ? (
              <p className="text-sm text-brand-muted py-4">
                No sector packs available. Contact your engagement manager to load a sector pack.
              </p>
            ) : (
              <ul className="divide-y divide-brand-border">
                {sectorPacks.map((p) => (
                  <li key={p.pack_id} className="py-3">
                    <p className="text-sm font-medium text-brand-ink">{p.name}</p>
                    {(p.industry ?? p.version) && (
                      <p className="text-xs text-brand-muted mt-0.5">
                        {[p.industry, p.version ? `v${p.version}` : undefined]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </MainLayout>
  );
};
