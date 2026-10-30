import React, { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Card } from '../../Common/Card';
import { Button } from '../../Common/Button';
import { Input } from '../../Common/Input';
import { Loader } from '../../Common/Loader';
import {
  BenchmarkDetailDrawer,
  specificityBadge,
  type BenchmarkDatasetRow,
} from './BenchmarkDetailDrawer';
import type { SectorPackRow } from './SectorPackDetailDrawer';
import { apiPost, apiUpload, getApiErrorMessage } from '../../../hooks/useApi';
import { useBenchmarkDatasets } from '../../../api/hooks/useBenchmarksQueries';
import { benchmarkKeys } from '../../../api/queryKeys';

const BENCHMARK_TEMPLATE_URL = '/api/v1/template/benchmark-csv';

export interface PeerSet {
  name: string;
  industry: string;
  description?: string;
  dataset_ids: string[];
}

export interface SelectResult {
  selected: BenchmarkDatasetRow | null;
  selection_rationale?: Record<string, unknown>;
  candidates?: { dataset_id: string; source?: string; score?: number }[];
}

function datasetTitle(d: BenchmarkDatasetRow): string {
  const label = d.industry_name || d.industry_code || d.dataset_id;
  return d.source ? `${label} · ${d.source}` : label;
}

function vintageYear(d: BenchmarkDatasetRow): string | undefined {
  if (!d.vintage_date) return undefined;
  return d.vintage_date.slice(0, 4);
}

function packIdFromDataset(datasetId: string): string | null {
  if (!datasetId.startsWith('sector-pack-')) return null;
  return datasetId.slice('sector-pack-'.length);
}

function isCustomDataset(d: BenchmarkDatasetRow): boolean {
  return !d.dataset_id.startsWith('sector-pack-');
}

interface BenchmarkToolsPanelProps {
  peerSets: PeerSet[];
  sectorPacks: SectorPackRow[];
  onError: (message: string) => void;
  onNotice: (message: string) => void;
  onPeerSetsChanged: () => void;
  onDatasetsChanged: () => void;
  onOpenSectorPack: (pack: SectorPackRow) => void;
  onSetEngagementPeerSet: (name: string) => void;
}

export const BenchmarkToolsPanel: React.FC<BenchmarkToolsPanelProps> = ({
  peerSets,
  sectorPacks,
  onError,
  onNotice,
  onPeerSetsChanged,
  onDatasetsChanged,
  onOpenSectorPack,
  onSetEngagementPeerSet,
}) => {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const datasetsQuery = useBenchmarkDatasets(expanded);
  const datasets = datasetsQuery.data?.datasets ?? [];
  const datasetsLoading = datasetsQuery.isLoading;
  const datasetsLoaded = datasetsQuery.isSuccess;
  const [detailDataset, setDetailDataset] = useState<BenchmarkDatasetRow | null>(null);

  const [uploading, setUploading] = useState(false);
  const [source, setSource] = useState('platform_upload');
  const [industryCode, setIndustryCode] = useState('');
  const [industryName, setIndustryName] = useState('');
  const [vintageDate, setVintageDate] = useState('');
  const [geography, setGeography] = useState('India');
  const [specificityScore, setSpecificityScore] = useState('0.7');
  const [sampleSize, setSampleSize] = useState('');
  const [revenueBandMin, setRevenueBandMin] = useState('');
  const [revenueBandMax, setRevenueBandMax] = useState('');
  const [licenseExpiry, setLicenseExpiry] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  const [previewIndustry, setPreviewIndustry] = useState('it_ites');
  const [previewCategories, setPreviewCategories] = useState('IT_SOFTWARE,PROF_SERVICES,TRAVEL');
  const [previewResult, setPreviewResult] = useState<SelectResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [psName, setPsName] = useState('');
  const [psIndustry, setPsIndustry] = useState('');
  const [psDatasetIds, setPsDatasetIds] = useState('');
  const [psDescription, setPsDescription] = useState('');

  useEffect(() => {
    if (datasetsQuery.isError) onError(getApiErrorMessage(datasetsQuery.error));
  }, [datasetsQuery.isError, datasetsQuery.error, onError]);

  const customDatasets = datasets.filter(isCustomDataset);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      onError('Choose a CSV benchmark file to upload.');
      return;
    }
    setUploading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('source', source.trim() || 'platform_upload');
      if (industryCode.trim()) form.append('industry_code', industryCode.trim());
      if (industryName.trim()) form.append('industry_name', industryName.trim());
      if (vintageDate.trim()) form.append('vintage_date', vintageDate.trim());
      form.append('geography', geography.trim() || 'India');
      const spec = Number(specificityScore);
      if (Number.isFinite(spec)) form.append('specificity_score', String(spec));
      const n = Number(sampleSize);
      if (Number.isFinite(n) && n > 0) form.append('sample_size', String(n));
      const rmin = Number(revenueBandMin);
      if (Number.isFinite(rmin) && rmin >= 0) form.append('revenue_band_min', String(rmin));
      const rmax = Number(revenueBandMax);
      if (Number.isFinite(rmax) && rmax > 0) form.append('revenue_band_max', String(rmax));
      if (licenseExpiry.trim()) form.append('license_expiry', licenseExpiry.trim());
      const res = await apiUpload<BenchmarkDatasetRow>('/api/v1/benchmarks/upload', form);
      onNotice(`Uploaded “${datasetTitle(res)}”.`);
      if (fileRef.current) fileRef.current.value = '';
      await queryClient.invalidateQueries({ queryKey: benchmarkKeys.datasets() });
      onDatasetsChanged();
    } catch (err) {
      onError(getApiErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    try {
      const cats = previewCategories.split(/[,\s]+/).map((c) => c.trim()).filter(Boolean);
      const res = await apiPost<SelectResult>('/api/v1/benchmarks/select', {
        industry: previewIndustry.trim(),
        categories: cats,
      });
      setPreviewResult(res);
    } catch (err) {
      onError(getApiErrorMessage(err));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleOpenPreviewResult = () => {
    const selected = previewResult?.selected;
    if (!selected) return;
    const packId = packIdFromDataset(selected.dataset_id);
    if (packId) {
      const pack = sectorPacks.find((sp) => sp.pack_id === packId) ?? { pack_id: packId };
      onOpenSectorPack(pack);
      return;
    }
    setDetailDataset(selected);
  };

  const handleCreatePeerSet = async () => {
    if (!psName.trim() || !psIndustry.trim()) {
      onError('Peer set name and industry are required.');
      return;
    }
    try {
      await apiPost('/api/v1/benchmarks/peer-sets', {
        name: psName.trim(),
        industry: psIndustry.trim(),
        description: psDescription.trim(),
        dataset_ids: psDatasetIds.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean),
      });
      onNotice(`Peer set “${psName.trim()}” saved.`);
      setPsName('');
      setPsDatasetIds('');
      onPeerSetsChanged();
    } catch (err) {
      onError(getApiErrorMessage(err));
    }
  };

  const downloadTemplate = () => {
    const a = document.createElement('a');
    a.href = BENCHMARK_TEMPLATE_URL;
    a.download = 'benchmark_template.csv';
    a.click();
  };

  return (
    <>
      <div className="mt-10 border border-brand-border rounded-lg bg-white overflow-hidden">
        <button
          type="button"
          className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left hover:bg-brand-surface-muted/40"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          <div>
            <p className="text-sm font-semibold text-brand-ink">Reference data tools</p>
            <p className="text-xs text-brand-muted mt-0.5">
              Upload CSV, preview selection, manage peer sets
            </p>
          </div>
          <span className="text-brand-muted text-lg leading-none">{expanded ? '−' : '+'}</span>
        </button>

        {expanded && (
          <div className="border-t border-brand-border p-5 space-y-6">
            {datasetsLoading && <Loader label="Loading datasets…" />}

            <Card title="Upload benchmark CSV" className="!shadow-none border-brand-border">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Input label="Source label" value={source} onChange={(e) => setSource(e.target.value)} />
                <Input
                  label="Industry code"
                  value={industryCode}
                  onChange={(e) => setIndustryCode(e.target.value)}
                  placeholder="e.g. manufacturing_diversified"
                />
                <Input label="Industry name" value={industryName} onChange={(e) => setIndustryName(e.target.value)} />
                <Input label="Vintage date" value={vintageDate} onChange={(e) => setVintageDate(e.target.value)} placeholder="YYYY-MM-DD" />
                <Input label="Geography" value={geography} onChange={(e) => setGeography(e.target.value)} />
                <Input
                  label="Specificity score (0–1)"
                  value={specificityScore}
                  onChange={(e) => setSpecificityScore(e.target.value)}
                />
                <Input
                  label="Sample size (n)"
                  value={sampleSize}
                  onChange={(e) => setSampleSize(e.target.value)}
                  placeholder="Peer count in study"
                />
                <Input
                  label="Revenue band min (Cr)"
                  value={revenueBandMin}
                  onChange={(e) => setRevenueBandMin(e.target.value)}
                  placeholder="e.g. 500"
                />
                <Input
                  label="Revenue band max (Cr)"
                  value={revenueBandMax}
                  onChange={(e) => setRevenueBandMax(e.target.value)}
                  placeholder="Blank = open-ended"
                />
                <Input
                  label="License expiry"
                  value={licenseExpiry}
                  onChange={(e) => setLicenseExpiry(e.target.value)}
                  placeholder="YYYY-MM-DD"
                />
              </div>
              <div className="mt-4 flex flex-wrap items-end gap-3">
                <div>
                  <label className="block text-xs font-semibold text-brand-muted mb-1">CSV file</label>
                  <input ref={fileRef} type="file" accept=".csv,text/csv" className="text-sm" />
                </div>
                <Button variant="primary" onClick={handleUpload} disabled={uploading}>
                  {uploading ? 'Uploading…' : 'Upload'}
                </Button>
                <Button variant="ghost" onClick={downloadTemplate}>
                  Download template
                </Button>
                <a
                  href={BENCHMARK_TEMPLATE_URL}
                  download="benchmark_template.csv"
                  className="text-sm text-brand-primary underline self-center"
                >
                  Or open template URL
                </a>
              </div>
              <p className="text-xs text-brand-muted mt-3">
                Template columns: industry_code, category_id, size_band, geography, unit, p25–p90,
                sample_size, confidence (illustrative / public_disclosure / licensed), source_type,
                source_citation, methodology_notes, vintage_date. Licensed uploads with specificity &gt; 0.85
                override sector-pack defaults.
              </p>
            </Card>

            <Card title="Preview dataset selection" className="!shadow-none border-brand-border">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input label="Industry / sector pack" value={previewIndustry} onChange={(e) => setPreviewIndustry(e.target.value)} />
                <Input
                  label="Categories (comma-separated)"
                  value={previewCategories}
                  onChange={(e) => setPreviewCategories(e.target.value)}
                />
              </div>
              <Button className="mt-3" variant="secondary" onClick={handlePreview} disabled={previewLoading}>
                {previewLoading ? 'Ranking…' : 'Preview selection'}
              </Button>
              {previewResult?.selected && (
                <div className="mt-3 text-sm border border-brand-border rounded-lg p-3">
                  <p className="font-medium text-brand-ink">{datasetTitle(previewResult.selected)}</p>
                  {previewResult.selection_rationale?.benchmark_confidence_note != null && (
                    <p className="text-xs text-amber-700 mt-1">
                      {String(previewResult.selection_rationale.benchmark_confidence_note)}
                    </p>
                  )}
                  {previewResult.candidates && previewResult.candidates.length > 1 && (
                    <p className="text-xs text-brand-muted mt-2">
                      Alternatives: {previewResult.candidates.slice(1, 4).map((c) => c.dataset_id).join(', ')}
                    </p>
                  )}
                  <Button className="mt-3" variant="ghost" onClick={handleOpenPreviewResult}>
                    {packIdFromDataset(previewResult.selected.dataset_id)
                      ? 'Open sector pack →'
                      : 'View dataset details →'}
                  </Button>
                </div>
              )}
            </Card>

            <Card title="Peer sets" className="!shadow-none border-brand-border">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input label="Name" value={psName} onChange={(e) => setPsName(e.target.value)} placeholder="my-bank-peers" />
                <Input label="Industry key" value={psIndustry} onChange={(e) => setPsIndustry(e.target.value)} placeholder="bfsi_banks" />
                <Input
                  label="Dataset IDs (comma-separated)"
                  value={psDatasetIds}
                  onChange={(e) => setPsDatasetIds(e.target.value)}
                  className="md:col-span-2"
                />
                <Input label="Description" value={psDescription} onChange={(e) => setPsDescription(e.target.value)} className="md:col-span-2" />
              </div>
              <Button className="mt-3" onClick={handleCreatePeerSet}>
                Save peer set
              </Button>
              {peerSets.length > 0 && (
                <ul className="mt-4 divide-y divide-brand-border">
                  {peerSets.map((ps) => (
                    <li key={ps.name} className="py-2 flex items-center justify-between gap-2 text-sm">
                      <div>
                        <span className="font-medium text-brand-ink">{ps.name}</span>
                        <span className="text-brand-muted ml-2">{ps.industry}</span>
                        <p className="text-xs text-brand-muted">{ps.dataset_ids?.join(', ')}</p>
                      </div>
                      <Button variant="ghost" onClick={() => onSetEngagementPeerSet(ps.name)}>
                        Set as default
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            {datasetsLoaded && (
              <Card title="Custom & seed datasets" className="!shadow-none border-brand-border">
                {customDatasets.length === 0 ? (
                  <p className="text-sm text-brand-muted">No custom or seed datasets beyond sector packs.</p>
                ) : (
                  <ul className="divide-y divide-brand-border">
                    {customDatasets.map((d) => {
                      const badge = specificityBadge(d.specificity_score);
                      return (
                        <li key={d.dataset_id} className="py-3">
                          <button
                            type="button"
                            className="text-left w-full hover:bg-brand-surface-muted/50 rounded px-1 -mx-1"
                            onClick={() => setDetailDataset(d)}
                          >
                            <div className="flex items-center gap-2 flex-wrap">
                              <p className="text-sm font-medium text-brand-ink">{datasetTitle(d)}</p>
                              <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${badge.className}`}>
                                {badge.label}
                              </span>
                            </div>
                            <p className="text-xs text-brand-muted mt-0.5">
                              {[d.industry_code, vintageYear(d), d.geography].filter(Boolean).join(' · ')}
                            </p>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Card>
            )}
          </div>
        )}
      </div>

      <BenchmarkDetailDrawer
        dataset={detailDataset}
        onClose={() => setDetailDataset(null)}
        onOpenSectorPack={(packId) => {
          setDetailDataset(null);
          const pack = sectorPacks.find((sp) => sp.pack_id === packId) ?? { pack_id: packId };
          onOpenSectorPack(pack);
        }}
      />
    </>
  );
};
