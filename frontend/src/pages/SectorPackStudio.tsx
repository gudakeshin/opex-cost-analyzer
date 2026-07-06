import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { Button } from '../components/Common/Button';
import { Card } from '../components/Common/Card';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import type { SectorPackRow } from '../components/PageComponents/Benchmarks/SectorPackDetailDrawer';
import { parse_regulatory_triggers_count } from '../utils/regulatoryTriggers';
import {
  useCreateSectorPack,
  useImportPackWorkbook,
  usePackRegressionTest,
  usePublishSectorPack,
  useSectorPackDetail,
  useSectorPacks,
  useUpdatePackComponent,
} from '../api/hooks/useBenchmarksQueries';
import { getApiErrorMessage } from '../hooks/useApi';
import { useUnsavedGuard } from '../hooks/useUnsavedGuard';

type TabId =
  | 'manifest'
  | 'taxonomy'
  | 'peers'
  | 'levers'
  | 'kpis'
  | 'benchmarks'
  | 'sources'
  | 'regulatory';

const TABS: { id: TabId; label: string; component: string }[] = [
  { id: 'manifest', label: 'Manifest', component: 'manifest' },
  { id: 'taxonomy', label: 'Taxonomy', component: 'taxonomy' },
  { id: 'peers', label: 'Peers', component: 'peers' },
  { id: 'levers', label: 'Levers', component: 'levers' },
  { id: 'kpis', label: 'KPIs', component: 'kpis' },
  { id: 'benchmarks', label: 'Benchmarks', component: 'benchmarks' },
  { id: 'sources', label: 'Sources', component: 'sources' },
  { id: 'regulatory', label: 'Regulatory', component: 'regulatory' },
];

function statusBadge(status?: string) {
  const s = (status || 'scaffold').toLowerCase();
  if (s === 'full') return 'bg-emerald-100 text-emerald-800';
  if (s === 'draft') return 'bg-amber-100 text-amber-800';
  return 'bg-slate-100 text-slate-600';
}

function payloadForTab(tab: TabId, detail: Record<string, unknown> | null): unknown {
  if (!detail) return null;
  switch (tab) {
    case 'manifest':
      return detail.manifest ?? {};
    case 'taxonomy':
      return detail.taxonomy_extension ?? { additional_categories: [], overrides: [] };
    case 'peers':
      return { sector: detail.pack_id, currency: 'INR', peers: detail.peers ?? [] };
    case 'levers':
      return { sector: detail.pack_id, source_type: 'studio', levers: detail.levers ?? [] };
    case 'kpis':
      return detail.kpi_pack ?? [];
    case 'benchmarks':
      return {
        sector: detail.pack_id,
        version: detail.version ?? '0.1',
        benchmarks: { [String(detail.pack_id)]: { categories: detail.categories ?? {} } },
      };
    case 'sources':
      return detail.benchmark_sources ?? { free_sources: [], licensed_sources_stubs: [] };
    case 'regulatory':
      return detail.regulatory_layer ?? '';
    default:
      return null;
  }
}

export const SectorPackStudio: React.FC = () => {
  const packsQuery = useSectorPacks();
  const packs = useMemo(() => packsQuery.data?.packs ?? [], [packsQuery.data]);
  const [selectedId, setSelectedId] = useState('');
  const [tab, setTab] = useState<TabId>('manifest');
  const [editorText, setEditorText] = useState('');
  const [savedText, setSavedText] = useState('');
  const [manifestForm, setManifestForm] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [showPublish, setShowPublish] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newPackId, setNewPackId] = useState('');
  const [newSector, setNewSector] = useState('');
  const [importPreview, setImportPreview] = useState<Record<string, unknown> | null>(null);

  const detailQuery = useSectorPackDetail(selectedId || null);
  const detail = detailQuery.data ?? null;
  const updateMutation = useUpdatePackComponent(selectedId || null);
  const createMutation = useCreateSectorPack();
  const publishMutation = usePublishSectorPack(selectedId || null);
  const regressionMutation = usePackRegressionTest(selectedId || null);
  const importMutation = useImportPackWorkbook();

  const selectedPack = packs.find((p) => p.pack_id === selectedId);
  const activeTab = TABS.find((t) => t.id === tab)!;
  const isJsonTab = tab !== 'manifest' && tab !== 'regulatory';
  const hasDiff = editorText !== savedText;

  useUnsavedGuard('sector-pack-studio', hasDiff);

  useEffect(() => {
    if (packs.length && !selectedId) setSelectedId(packs[0].pack_id);
  }, [packs, selectedId]);

  const loadEditorFromDetail = useCallback(() => {
    if (!detail) return;
    if (tab === 'manifest') {
      const m = (detail.manifest ?? {}) as Record<string, unknown>;
      setManifestForm({
        sector: String(m.sector ?? ''),
        status: String(m.status ?? 'scaffold'),
        description: String(m.description ?? ''),
        effective_from: String(m.effective_from ?? ''),
        reporting_currency: String(m.reporting_currency ?? 'INR'),
        fiscal_year_end: String(m.fiscal_year_end ?? 'March 31'),
      });
      setEditorText('');
      setSavedText('');
    } else if (tab === 'regulatory') {
      const text = detail.regulatory_layer ?? '';
      setEditorText(text);
      setSavedText(text);
    } else {
      const payload = payloadForTab(tab, detail as unknown as Record<string, unknown>);
      const text = JSON.stringify(payload, null, 2);
      setEditorText(text);
      setSavedText(text);
    }
  }, [detail, tab]);

  useEffect(() => {
    loadEditorFromDetail();
  }, [loadEditorFromDetail, selectedId, tab]);

  const handleSave = async () => {
    if (!selectedId) return;
    setError(null);
    try {
      let payload: unknown;
      if (tab === 'manifest') {
        const m = { ...(detail?.manifest as Record<string, unknown>), ...manifestForm };
        payload = m;
      } else if (tab === 'regulatory') {
        payload = editorText;
      } else {
        payload = JSON.parse(editorText);
      }
      await updateMutation.mutateAsync({ component: activeTab.component, payload });
      if (tab !== 'manifest') {
        setSavedText(editorText);
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const handleValidate = async () => {
    if (!selectedId) return;
    setError(null);
    try {
      const res = await regressionMutation.mutateAsync();
      setValidation(res as Record<string, unknown>);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const handlePublish = async (bump: string, targetStatus?: string) => {
    if (!selectedId) return;
    setError(null);
    try {
      const res = await publishMutation.mutateAsync({ bump, target_status: targetStatus ?? null });
      setValidation(res as Record<string, unknown>);
      setShowPublish(false);
      await detailQuery.refetch();
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const handleCreate = async () => {
    if (!newPackId.trim() || !newSector.trim()) return;
    setError(null);
    try {
      await createMutation.mutateAsync({
        pack_id: newPackId.trim(),
        sector: newSector.trim(),
      });
      setSelectedId(newPackId.trim());
      setShowCreate(false);
      await packsQuery.refetch();
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const handleImport = async (file: File, dryRun: boolean) => {
    setError(null);
    try {
      const res = await importMutation.mutateAsync({ file, dryRun, packId: selectedId || undefined });
      if (dryRun) {
        setImportPreview(res);
      } else {
        setImportPreview(null);
        await packsQuery.refetch();
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const triggerCount =
    tab === 'regulatory' ? parse_regulatory_triggers_count(editorText) : 0;

  const loading = packsQuery.isLoading || detailQuery.isLoading;

  return (
    <MainLayout hideHeader>
      <PageHeader
        title="Sector Pack Studio"
        subtitle="Author benchmarks, levers, KPIs, peers, taxonomy, and regulatory layers. New packs appear in engagement sector dropdowns after publish."
      />

      {error && (
        <Alert variant="error" title="Error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mt-6">
        <Card className="lg:col-span-1 border-brand-border bg-white">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium">Packs</p>
            <Link to="/benchmarks" className="text-xs text-deloitte-green">
              Benchmarks view
            </Link>
          </div>
          <div className="max-h-72 overflow-y-auto space-y-1 border border-brand-border rounded-lg p-2">
            {packs.map((p: SectorPackRow) => (
              <button
                key={p.pack_id}
                type="button"
                onClick={() => setSelectedId(p.pack_id)}
                className={`w-full text-left px-2 py-1.5 rounded text-sm ${
                  selectedId === p.pack_id ? 'bg-brand-surface-muted font-medium' : 'hover:bg-brand-surface-muted/60'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="truncate">{p.sector || p.pack_id}</span>
                  <span className={`text-[10px] px-1 rounded ${statusBadge(p.status)}`}>
                    {p.status || 'scaffold'}
                  </span>
                </div>
                <p className="text-[10px] text-brand-muted">v{p.version || '?'} · {p.pack_id}</p>
              </button>
            ))}
          </div>
          <div className="space-y-2 pt-4">
            <Button className="w-full" variant="secondary" onClick={() => setShowCreate((v) => !v)}>
              {showCreate ? 'Cancel' : 'Create pack'}
            </Button>
          </div>
          {showCreate && (
            <div className="mt-3 space-y-2">
              <input
                className="w-full border rounded px-2 py-1 text-sm"
                placeholder="pack_id (slug)"
                value={newPackId}
                onChange={(e) => setNewPackId(e.target.value)}
              />
              <input
                className="w-full border rounded px-2 py-1 text-sm"
                placeholder="Sector label"
                value={newSector}
                onChange={(e) => setNewSector(e.target.value)}
              />
              <Button className="w-full" onClick={handleCreate} disabled={createMutation.isPending}>
                Scaffold pack
              </Button>
            </div>
          )}
        </Card>

        <div className="lg:col-span-3 space-y-4">
          {selectedPack && (
            <div className="flex flex-wrap gap-2 items-center">
              <h2 className="text-lg font-semibold">{selectedPack.sector || selectedPack.pack_id}</h2>
              <span className={`text-xs px-2 py-0.5 rounded ${statusBadge(selectedPack.status)}`}>
                {selectedPack.status || 'scaffold'}
              </span>
              <span className="text-xs text-brand-muted">v{selectedPack.version}</span>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`text-xs px-2.5 py-1 rounded border ${
                  tab === t.id ? 'bg-brand-ink text-white border-brand-ink' : 'border-brand-border text-brand-muted'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap gap-2">
            <Button onClick={handleSave} disabled={!selectedId || updateMutation.isPending}>
              Save {activeTab.label}
            </Button>
            <Button variant="secondary" onClick={handleValidate} disabled={!selectedId || regressionMutation.isPending}>
              Run validation
            </Button>
            <Button variant="ghost" onClick={() => setShowPublish(true)} disabled={!selectedId}>
              Publish
            </Button>
            <label className="text-xs border border-brand-border rounded px-3 py-2 cursor-pointer hover:bg-brand-surface-muted">
              Import Excel (preview)
              <input
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void handleImport(f, true);
                  e.target.value = '';
                }}
              />
            </label>
            {importPreview && (
              <Button
                variant="secondary"
                onClick={() => {
                  const input = document.createElement('input');
                  input.type = 'file';
                  input.accept = '.xlsx';
                  input.onchange = () => {
                    const f = input.files?.[0];
                    if (f) void handleImport(f, false);
                  };
                  input.click();
                }}
              >
                Confirm import
              </Button>
            )}
          </div>

          {hasDiff && <p className="text-xs text-amber-700">Unsaved changes on this tab.</p>}

          {loading ? (
            <Loader label="Loading pack…" />
          ) : tab === 'manifest' ? (
            <Card title="Manifest" className="border-brand-border bg-white">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                {(['sector', 'status', 'description', 'effective_from', 'reporting_currency', 'fiscal_year_end'] as const).map(
                  (key) => (
                    <label key={key} className="block">
                      <span className="text-xs text-brand-muted">{key}</span>
                      <input
                        className="w-full border rounded px-2 py-1 mt-0.5"
                        value={manifestForm[key] ?? ''}
                        onChange={(e) => setManifestForm((f) => ({ ...f, [key]: e.target.value }))}
                        disabled={key === 'status'}
                      />
                    </label>
                  ),
                )}
              </div>
              <p className="text-xs text-brand-muted mt-2">
                pack_id and version are immutable here; version bumps on Publish. Industry free-text mapping for new packs
                requires explicit pack selection in engagements.
              </p>
            </Card>
          ) : (
            <Card
              title={tab === 'regulatory' ? `Regulatory (${triggerCount} triggers parsed)` : activeTab.label}
              className="border-brand-border bg-white"
            >
              <textarea
                value={editorText}
                onChange={(e) => setEditorText(e.target.value)}
                className={`w-full px-3 py-2 border border-brand-border rounded-lg font-mono text-sm ${
                  tab === 'regulatory' ? 'h-96' : 'h-[28rem]'
                }`}
                spellCheck={false}
              />
              {isJsonTab && (
                <p className="text-xs text-brand-muted mt-2">JSON is validated server-side before write.</p>
              )}
            </Card>
          )}

          {validation && (
            <Card title="Validation / publish result" className="border-brand-border bg-white">
              <pre className="text-xs overflow-auto max-h-64">{JSON.stringify(validation, null, 2)}</pre>
            </Card>
          )}

          {importPreview && (
            <Card title="Import preview (dry run)" className="border-brand-border bg-white">
              <pre className="text-xs overflow-auto max-h-48">{JSON.stringify(importPreview, null, 2)}</pre>
            </Card>
          )}

          {showPublish && (
            <Card title="Publish pack" className="border-brand-border bg-white">
              <p className="text-sm text-brand-muted mb-3">
                Runs regression tests, bumps version, and updates effective_from. Engagements with a version lock on the
                prior version are listed in the result.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => handlePublish('minor')}>Publish minor bump</Button>
                <Button variant="secondary" onClick={() => handlePublish('major')}>
                  Publish major bump
                </Button>
                <Button variant="ghost" onClick={() => handlePublish('minor', 'draft')}>
                  Publish as draft
                </Button>
                <Button variant="ghost" onClick={() => setShowPublish(false)}>
                  Cancel
                </Button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </MainLayout>
  );
};
