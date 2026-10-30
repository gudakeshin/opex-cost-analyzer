import React, { useEffect, useMemo, useState } from 'react';
import { Input } from '../components/Common/Input';
import { Link } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { Button } from '../components/Common/Button';
import { Card } from '../components/Common/Card';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import type { SectorPackRow } from '../types/sectorPack';
import type {
  BenchmarksDraft,
  KpiRow,
  LeversDraft,
  PackEditorDraft,
  PackEditorTabId,
  PeersDraft,
  SourcesDraft,
  TaxonomyDraft,
} from '../types/sectorPack';
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
import { BenchmarksEditor } from '../components/PageComponents/SectorPacks/BenchmarksEditor';
import { ImportPreviewPanel } from '../components/PageComponents/SectorPacks/ImportPreviewPanel';
import { KpiPackEditor } from '../components/PageComponents/SectorPacks/KpiPackEditor';
import { LeversEditor } from '../components/PageComponents/SectorPacks/LeversEditor';
import { PackEditorShell } from '../components/PageComponents/SectorPacks/PackEditorShell';
import { PeersEditor } from '../components/PageComponents/SectorPacks/PeersEditor';
import { SourcesEditor } from '../components/PageComponents/SectorPacks/SourcesEditor';
import { TaxonomyEditor } from '../components/PageComponents/SectorPacks/TaxonomyEditor';
import { ValidationResultPanel } from '../components/PageComponents/SectorPacks/ValidationResultPanel';
import {
  deepEqual,
  draftToJson,
  isPackEditorTab,
  parseDetailToDraft,
  parseDraftFromJson,
  serializeDraftToPayload,
} from '../utils/sectorPackEditors';
import { buildManifestForm, hydrateEditorDrafts } from '../utils/sectorPackStudioState';
import { useConfirm } from '../hooks/useConfirm';
import { TabList } from '../components/Common/TabList';

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

function manifestDirty(
  form: Record<string, string>,
  baseline: Record<string, string>,
): boolean {
  return JSON.stringify(form) !== JSON.stringify(baseline);
}

export const SectorPackStudio: React.FC = () => {
  const packsQuery = useSectorPacks();
  const packs = useMemo(() => packsQuery.data?.packs ?? [], [packsQuery.data]);
  const [selectedId, setSelectedId] = useState('');
  const [tab, setTab] = useState<TabId>('manifest');
  const [draftByTab, setDraftByTab] = useState<Partial<Record<PackEditorTabId, PackEditorDraft>>>({});
  const [baselineByTab, setBaselineByTab] = useState<Partial<Record<PackEditorTabId, PackEditorDraft>>>({});
  const [viewModeByTab, setViewModeByTab] = useState<Partial<Record<PackEditorTabId, 'structured' | 'json'>>>({});
  const [jsonTextByTab, setJsonTextByTab] = useState<Partial<Record<PackEditorTabId, string>>>({});
  const [jsonErrorByTab, setJsonErrorByTab] = useState<Partial<Record<PackEditorTabId, string | null>>>({});
  const [regulatoryText, setRegulatoryText] = useState('');
  const [regulatoryBaseline, setRegulatoryBaseline] = useState('');
  const [manifestForm, setManifestForm] = useState<Record<string, string>>({});
  const [manifestBaseline, setManifestBaseline] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [showPublish, setShowPublish] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newPackId, setNewPackId] = useState('');
  // Mirrors the server rule (app/services/sector_pack_authoring.py) so mistakes show before submitting.
  const packIdError =
    newPackId.trim() && !/^[a-z0-9][a-z0-9_-]{1,63}$/.test(newPackId.trim())
      ? 'Use lowercase letters, numbers, _ or -, starting with a letter or number (2–64 characters).'
      : undefined;
  const [newSector, setNewSector] = useState('');
  const [importPreview, setImportPreview] = useState<Record<string, unknown> | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);

  const detailQuery = useSectorPackDetail(selectedId || null);
  const detail = detailQuery.data ?? null;
  const updateMutation = useUpdatePackComponent(selectedId || null);
  const createMutation = useCreateSectorPack();
  const publishMutation = usePublishSectorPack(selectedId || null);
  const regressionMutation = usePackRegressionTest(selectedId || null);
  const importMutation = useImportPackWorkbook();

  const selectedPack = packs.find((p) => p.pack_id === selectedId);
  const activeTab = TABS.find((t) => t.id === tab)!;

  const packSelected = Boolean(selectedId);
  const detailPending = packSelected && (detailQuery.isPending || detailQuery.isFetching);
  const detailReady = packSelected && Boolean(detail);
  const packsLoading = packsQuery.isLoading;
  const showPackLoader = packsLoading || detailPending;

  // Unsaved edits on ANY tab, not just the visible one: switching tabs keeps drafts in
  // state, but switching packs (or leaving the page) discards them.
  const dirtyTabIds = useMemo(() => {
    const dirty = new Set<TabId>();
    if (!detail) return dirty;
    for (const t of TABS) {
      if (!isPackEditorTab(t.id)) continue;
      const draft = draftByTab[t.id];
      const baseline = baselineByTab[t.id];
      if (!draft || !baseline) continue;
      if (viewModeByTab[t.id] === 'json') {
        const jsonText = jsonTextByTab[t.id];
        if (!jsonText) continue;
        try {
          const parsed = parseDraftFromJson(t.id, jsonText);
          if (
            !deepEqual(
              serializeDraftToPayload(t.id, parsed, detail),
              serializeDraftToPayload(t.id, baseline, detail),
            )
          ) {
            dirty.add(t.id);
          }
        } catch {
          dirty.add(t.id);
        }
      } else if (!deepEqual(draft, baseline)) {
        dirty.add(t.id);
      }
    }
    if (manifestDirty(manifestForm, manifestBaseline)) dirty.add('manifest');
    if (regulatoryText !== regulatoryBaseline) dirty.add('regulatory');
    return dirty;
  }, [
    detail,
    draftByTab,
    baselineByTab,
    viewModeByTab,
    jsonTextByTab,
    manifestForm,
    manifestBaseline,
    regulatoryText,
    regulatoryBaseline,
  ]);

  const anyDiff = dirtyTabIds.size > 0;
  const dirtyTabLabels = TABS.filter((t) => dirtyTabIds.has(t.id)).map((t) => t.label);
  const [confirm, confirmDialog] = useConfirm();

  useUnsavedGuard('sector-pack-studio', anyDiff);

  useEffect(() => {
    if (packs.length && !selectedId) setSelectedId(packs[0].pack_id);
  }, [packs, selectedId]);

  useEffect(() => {
    if (!detail || !selectedId) {
      setDraftByTab({});
      setBaselineByTab({});
      setJsonTextByTab({});
      setJsonErrorByTab({});
      setManifestForm({});
      setManifestBaseline({});
      setRegulatoryText('');
      setRegulatoryBaseline('');
      return;
    }

    const { drafts, jsonText } = hydrateEditorDrafts(detail);
    setDraftByTab(drafts);
    setBaselineByTab(JSON.parse(JSON.stringify(drafts)));
    setJsonTextByTab(jsonText);
    setJsonErrorByTab({});

    const pack = packs.find((p) => p.pack_id === selectedId);
    const form = buildManifestForm(detail, pack);
    setManifestForm(form);
    setManifestBaseline(form);

    const regulatory = detail.regulatory_layer ?? '';
    setRegulatoryText(regulatory);
    setRegulatoryBaseline(regulatory);
  }, [detail, selectedId, packs]);

  const resolveEditorDraft = (editorTab: PackEditorTabId): PackEditorDraft => {
    if (viewModeByTab[editorTab] === 'json') {
      const jsonText = jsonTextByTab[editorTab] ?? '';
      return parseDraftFromJson(editorTab, jsonText);
    }
    const draft = draftByTab[editorTab] ?? (detail ? parseDetailToDraft(editorTab, detail) : undefined);
    if (!draft) {
      throw new Error(`No draft available for ${editorTab}`);
    }
    return draft;
  };

  const handleSave = async () => {
    if (!selectedId || !detail) return;
    setError(null);
    try {
      let payload: unknown;
      if (tab === 'manifest') {
        payload = { ...(detail.manifest as Record<string, unknown>), ...manifestForm };
      } else if (tab === 'regulatory') {
        payload = regulatoryText;
      } else if (isPackEditorTab(tab)) {
        const draft = resolveEditorDraft(tab);
        payload = serializeDraftToPayload(tab, draft, detail);
      } else {
        return;
      }

      await updateMutation.mutateAsync({ component: activeTab.component, payload });

      if (tab === 'manifest') {
        setManifestBaseline({ ...manifestForm });
      } else if (tab === 'regulatory') {
        setRegulatoryBaseline(regulatoryText);
      } else if (isPackEditorTab(tab)) {
        const draft = resolveEditorDraft(tab);
        setDraftByTab((prev) => ({ ...prev, [tab]: draft }));
        setBaselineByTab((prev) => ({ ...prev, [tab]: JSON.parse(JSON.stringify(draft)) }));
        setJsonTextByTab((prev) => ({ ...prev, [tab]: draftToJson(draft) }));
        await detailQuery.refetch();
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
    const isMajor = bump === 'major' && !targetStatus;
    const ok = await confirm({
      title: targetStatus === 'draft' ? 'Publish as draft?' : `Publish ${bump} version?`,
      message: (
        <>
          <p>
            This runs regression tests, bumps the {bump} version of <strong>{selectedId}</strong> and updates
            effective_from.{isMajor ? ' A major bump cannot be undone.' : ''}
          </p>
          {anyDiff && (
            <p className="mt-2 text-amber-700">
              You have unsaved edits ({dirtyTabLabels.join(', ')}). Publishing uses the last saved version, so these
              edits will not be included.
            </p>
          )}
        </>
      ),
      confirmLabel: 'Publish',
      danger: isMajor,
    });
    if (!ok) return;
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
        setImportFile(file);
      } else {
        setImportPreview(null);
        setImportFile(null);
        await packsQuery.refetch();
        await detailQuery.refetch();
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const renderPackEditor = (editorTab: PackEditorTabId) => {
    const draft =
      draftByTab[editorTab] ?? (detail ? parseDetailToDraft(editorTab, detail) : undefined);
    if (!draft) {
      return <p className="text-sm text-brand-muted">Loading editor…</p>;
    }

    const shellProps = {
      tab: editorTab,
      draft,
      onDraftChange: (next: PackEditorDraft) =>
        setDraftByTab((prev) => ({ ...prev, [editorTab]: next })),
      viewMode: viewModeByTab[editorTab] ?? 'structured',
      onViewModeChange: (mode: 'structured' | 'json') =>
        setViewModeByTab((prev) => ({ ...prev, [editorTab]: mode })),
      jsonText: jsonTextByTab[editorTab] ?? draftToJson(draft),
      onJsonTextChange: (text: string) =>
        setJsonTextByTab((prev) => ({ ...prev, [editorTab]: text })),
      jsonError: jsonErrorByTab[editorTab] ?? null,
      onJsonError: (err: string | null) =>
        setJsonErrorByTab((prev) => ({ ...prev, [editorTab]: err })),
    };

    return (
      <PackEditorShell {...shellProps}>
        {editorTab === 'kpis' && (
          <KpiPackEditor draft={draft as KpiRow[]} onChange={shellProps.onDraftChange} />
        )}
        {editorTab === 'taxonomy' && (
          <TaxonomyEditor draft={draft as TaxonomyDraft} onChange={shellProps.onDraftChange} />
        )}
        {editorTab === 'peers' && (
          <PeersEditor draft={draft as PeersDraft} onChange={shellProps.onDraftChange} />
        )}
        {editorTab === 'benchmarks' && (
          <BenchmarksEditor draft={draft as BenchmarksDraft} onChange={shellProps.onDraftChange} />
        )}
        {editorTab === 'sources' && (
          <SourcesEditor draft={draft as SourcesDraft} onChange={shellProps.onDraftChange} />
        )}
        {editorTab === 'levers' && (
          <LeversEditor draft={draft as LeversDraft} onChange={shellProps.onDraftChange} />
        )}
      </PackEditorShell>
    );
  };

  const triggerCount = tab === 'regulatory' ? parse_regulatory_triggers_count(regulatoryText) : 0;
  const detailFetchError = detailQuery.isError ? getApiErrorMessage(detailQuery.error) : null;

  const renderTabContent = () => {
    if (showPackLoader) {
      return <Loader label="Loading pack…" />;
    }

    if (!packs.length && !packsLoading) {
      return (
        <Card className="border-brand-border bg-white">
          <p className="text-sm text-brand-muted">No sector packs found. Create a pack to get started.</p>
        </Card>
      );
    }

    if (detailFetchError) {
      return (
        <div className="space-y-3">
          <Alert variant="error" title="Could not load pack detail">
            {detailFetchError}
          </Alert>
          <Button variant="secondary" onClick={() => void detailQuery.refetch()}>
            Retry
          </Button>
        </div>
      );
    }

    if (!detailReady) {
      return (
        <Card className="border-brand-border bg-white">
          <p className="text-sm text-brand-muted">Select a pack from the list to edit its components.</p>
        </Card>
      );
    }

    return (
      <>
        {detail?.pack_error && (
          <Alert variant="warning" title="Pack validation warning">
            {detail.pack_error}
          </Alert>
        )}

        {tab === 'manifest' ? (
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
        ) : tab === 'regulatory' ? (
          <Card
            title={`Regulatory (${triggerCount} triggers parsed)`}
            className="border-brand-border bg-white"
          >
            <textarea
              value={regulatoryText}
              onChange={(e) => setRegulatoryText(e.target.value)}
              className="w-full px-3 py-2 border border-brand-border rounded-lg font-mono text-sm h-96"
              spellCheck={false}
            />
          </Card>
        ) : isPackEditorTab(tab) ? (
          <Card title={activeTab.label} className="border-brand-border bg-white">
            {renderPackEditor(tab)}
            <p className="text-xs text-brand-muted mt-2">Changes are validated server-side before write.</p>
          </Card>
        ) : null}
      </>
    );
  };

  return (
    <MainLayout hideHeader>
      {confirmDialog}
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
            <Link to="/benchmarks" className="text-xs text-brand-primary">
              Benchmarks view
            </Link>
          </div>
          <div className="max-h-72 overflow-y-auto space-y-1 border border-brand-border rounded-lg p-2">
            {packs.map((p: SectorPackRow) => (
              <button
                key={p.pack_id}
                type="button"
                onClick={async () => {
                  if (p.pack_id === selectedId) return;
                  if (anyDiff) {
                    const ok = await confirm({
                      title: 'Discard unsaved changes?',
                      message: `You have unsaved edits on ${dirtyTabLabels.join(', ')}. Switching packs will discard them.`,
                      confirmLabel: 'Discard and switch',
                      danger: true,
                    });
                    if (!ok) return;
                  }
                  setSelectedId(p.pack_id);
                }}
                className={`w-full text-left px-2 py-1.5 rounded text-sm ${
                  selectedId === p.pack_id ? 'bg-brand-surface-muted font-medium' : 'hover:bg-brand-surface-muted/60'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="truncate">{p.sector || p.pack_id}</span>
                  <span className={`text-[11px] px-1 rounded ${statusBadge(p.status)}`}>
                    {p.status || 'scaffold'}
                  </span>
                </div>
                <p className="text-[11px] text-brand-muted">v{p.version || '?'} · {p.pack_id}</p>
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
              <Input
                aria-label="Pack id"
                className="!px-2 !py-1"
                placeholder="pack_id (slug)"
                value={newPackId}
                onChange={(e) => setNewPackId(e.target.value)}
                hint="Lowercase letters, numbers, _ or -; 2–64 characters; cannot be changed later."
                error={packIdError}
              />
              <input
                aria-label="Sector label"
                className="w-full border rounded px-2 py-1 text-sm"
                placeholder="Sector label"
                value={newSector}
                onChange={(e) => setNewSector(e.target.value)}
              />
              <Button
                className="w-full"
                onClick={handleCreate}
                disabled={createMutation.isPending || !newPackId.trim() || !newSector.trim() || Boolean(packIdError)}
              >
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

          <TabList
            label="Pack sections"
            tabs={TABS.map((t) => ({ id: t.id, label: t.label }))}
            activeId={tab}
            onChange={(id) => setTab(id as TabId)}
            className="flex flex-wrap gap-2"
            tabClassName={(active) =>
              `text-xs px-2.5 py-1 rounded border ${
                active ? 'bg-brand-ink text-white border-brand-ink' : 'border-brand-border text-brand-muted'
              }`
            }
          />

          <div className="flex flex-wrap gap-2">
            <Button
              onClick={handleSave}
              disabled={!detailReady || updateMutation.isPending}
            >
              Save {activeTab.label}
            </Button>
            <Button
              variant="secondary"
              onClick={handleValidate}
              disabled={!detailReady || regressionMutation.isPending}
            >
              Run validation
            </Button>
            <Button variant="ghost" onClick={() => setShowPublish(true)} disabled={!detailReady}>
              Publish
            </Button>
            <label className="text-xs border border-brand-border rounded px-3 py-2 cursor-pointer hover:bg-brand-surface-muted focus-within:ring-2 focus-within:ring-brand-primary">
              Import Excel (preview)
              <input
                type="file"
                accept=".xlsx"
                className="sr-only"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void handleImport(f, true);
                  e.target.value = '';
                }}
              />
            </label>
            {importPreview && importFile && (
              <Button
                variant="secondary"
                onClick={async () => {
                  const ok = await confirm({
                    title: 'Apply import?',
                    message: `Apply “${importFile.name}” to ${selectedId || 'the selected pack'} exactly as shown in the preview. This overwrites existing pack content.`,
                    confirmLabel: 'Apply import',
                    danger: true,
                  });
                  if (ok) void handleImport(importFile, false);
                }}
              >
                Confirm import
              </Button>
            )}
          </div>

          {anyDiff && (
            <p className="text-xs text-amber-700">
              Unsaved changes on: {dirtyTabLabels.join(', ')}.
            </p>
          )}

          {renderTabContent()}

          {validation && (
            <Card title="Validation / publish result" className="border-brand-border bg-white">
              <ValidationResultPanel result={validation} />
            </Card>
          )}

          {importPreview && (
            <Card title="Import preview (dry run)" className="border-brand-border bg-white">
              <ImportPreviewPanel result={importPreview} />
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
