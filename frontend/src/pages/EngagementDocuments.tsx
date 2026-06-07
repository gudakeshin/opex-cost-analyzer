import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { PageHeader } from '../components/Common/PageHeader';
import { Card } from '../components/Common/Card';
import { Alert } from '../components/Common/Alert';
import { Loader } from '../components/Common/Loader';
import { Modal } from '../components/Common/Modal';
import { Button } from '../components/Common/Button';
import { Input } from '../components/Common/Input';
import { Select } from '../components/Common/Select';
import { useSession } from '../context/SessionContext';
import { apiDelete, apiGet, apiPost, apiUpload, getApiErrorMessage } from '../hooks/useApi';
import { formatFileSize } from '../utils/sessionFiles';
import { SECTOR_OPTIONS } from '../constants/sectors';
import type { EngagementDocument, EngagementSummary } from '../types';

const ACCEPT =
  '.csv,.xlsx,.xls,.json,.pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,application/json';

const CURRENCY_OPTIONS = [
  { value: 'INR', label: 'INR (₹)' },
  { value: 'USD', label: 'USD ($)' },
  { value: 'EUR', label: 'EUR (€)' },
  { value: 'GBP', label: 'GBP (£)' },
];

const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-900 border-amber-200',
  processing: 'bg-blue-50 text-blue-900 border-blue-200',
  ready: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  failed: 'bg-red-50 text-red-800 border-red-200',
};

function truncateId(id: string): string {
  return `${id.slice(0, 8)}…`;
}

export const EngagementDocuments: React.FC = () => {
  const navigate = useNavigate();
  const {
    engagementId,
    setEngagementId,
    setSessionId,
    ensureEngagement,
    listEngagements,
    deleteEngagement,
    createEngagement,
    engagement,
  } = useSession();
  const [engagements, setEngagements] = useState<EngagementSummary[]>([]);
  const [engagementSearch, setEngagementSearch] = useState('');
  const [noDocsOnly, setNoDocsOnly] = useState(false);
  const [selectedEngagementIds, setSelectedEngagementIds] = useState<Set<string>>(new Set());
  const [pendingDelete, setPendingDelete] = useState<EngagementSummary[]>([]);
  const [deletingEngagement, setDeletingEngagement] = useState(false);
  const [documents, setDocuments] = useState<EngagementDocument[]>([]);
  const [llamaparseConfigured, setLlamaparseConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const uploadSectionRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // New engagement modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newIndustry, setNewIndustry] = useState('manufacturing_diversified');
  const [newRevenueCr, setNewRevenueCr] = useState('5000');
  const [newCurrency, setNewCurrency] = useState('INR');
  const [creating, setCreating] = useState(false);
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null);

  const loadEngagements = useCallback(async () => {
    const list = await listEngagements();
    setEngagements(list);
    return list;
  }, [listEngagements]);

  const loadDocuments = useCallback(async (eid: string) => {
    const res = await apiGet<{
      documents: EngagementDocument[];
      llamaparse_configured?: boolean;
    }>(`/api/v1/engagements/${eid}/documents`);
    setDocuments(res.documents ?? []);
    setLlamaparseConfigured(!!res.llamaparse_configured);
  }, []);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const list = await loadEngagements();
      let eid = engagementId;
      if (!eid && list.length > 0) {
        eid = list[0].engagement_id;
        setEngagementId(eid);
      }
      if (!eid) {
        eid = await ensureEngagement();
      }
      if (eid) await loadDocuments(eid);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [engagementId, ensureEngagement, loadDocuments, loadEngagements, setEngagementId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const hasPending = documents.some(
    (d) => d.status === 'pending' || d.status === 'processing',
  );

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (!engagementId || !hasPending) return;
    pollRef.current = setInterval(() => {
      loadDocuments(engagementId).catch(() => undefined);
    }, 2500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [hasPending, engagementId, loadDocuments]);

  const handleSelectEngagement = async (eid: string) => {
    setSessionId(null);
    setEngagementId(eid);
    setJustCreatedId(null);
    setLoading(true);
    try {
      await loadDocuments(eid);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const openCreateModal = () => {
    setNewName('');
    setNewIndustry(engagement.industry || 'manufacturing_diversified');
    setNewRevenueCr(engagement.annual_revenue_cr ? String(engagement.annual_revenue_cr) : '5000');
    setNewCurrency(engagement.currency || 'INR');
    setShowCreateModal(true);
  };

  const handleCreateEngagement = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const eid = await createEngagement({
        company_name: newName.trim(),
        industry: newIndustry,
        annual_revenue: parseFloat(newRevenueCr) * 1e7,
        currency: newCurrency,
      });
      await loadEngagements();
      await loadDocuments(eid);
      setJustCreatedId(eid);
      setShowCreateModal(false);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setCreating(false);
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length || !engagementId) return;
    setUploading(true);
    setError(null);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const fd = new FormData();
        fd.append('file', file);
        await apiUpload(`/api/v1/engagements/${engagementId}/documents`, fd);
      }
      await loadDocuments(engagementId);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleDelete = async (docId: string) => {
    if (!engagementId) return;
    try {
      await apiDelete(`/api/v1/engagements/${engagementId}/documents/${docId}`);
      await loadDocuments(engagementId);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const toggleEngagementSelection = (eid: string) => {
    setSelectedEngagementIds((prev) => {
      const next = new Set(prev);
      if (next.has(eid)) next.delete(eid);
      else next.add(eid);
      return next;
    });
  };

  const handleConfirmDeleteEngagement = async () => {
    if (pendingDelete.length === 0) return;
    setDeletingEngagement(true);
    try {
      const targetIds = pendingDelete.map((e) => e.engagement_id);
      const wasActiveDeleted = !!engagementId && targetIds.includes(engagementId);
      const failures: string[] = [];
      for (const target of pendingDelete) {
        try {
          await deleteEngagement(target.engagement_id);
        } catch (err) {
          failures.push(`${target.company_name}: ${getApiErrorMessage(err)}`);
        }
      }
      setPendingDelete([]);
      setSelectedEngagementIds((prev) => {
        const next = new Set(prev);
        targetIds.forEach((id) => next.delete(id));
        return next;
      });
      const list = await loadEngagements();
      if (wasActiveDeleted) {
        const next = list[0]?.engagement_id ?? null;
        setEngagementId(next);
        if (next) await loadDocuments(next);
        else setDocuments([]);
      }
      if (failures.length > 0) {
        setError(`Some engagements could not be deleted — ${failures.join('; ')}`);
      }
    } finally {
      setDeletingEngagement(false);
    }
  };

  const handleReprocess = async (docId: string) => {
    if (!engagementId) return;
    try {
      await apiPost(`/api/v1/engagements/${engagementId}/documents/${docId}/reprocess`, {});
      await loadDocuments(engagementId);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const activeEngagement = engagements.find((e) => e.engagement_id === engagementId);
  const readyDocCount = documents.filter((d) => d.status === 'ready').length;
  const filteredEngagements = engagements.filter((e) =>
    e.company_name.toLowerCase().includes(engagementSearch.trim().toLowerCase())
    && (!noDocsOnly || e.document_count === 0),
  );
  const noDocEngagements = engagements.filter((e) => e.document_count === 0);

  return (
    <MainLayout>
      <PageHeader
        title="Documents"
        subtitle="Upload and manage engagement data sources — shared across all analysis sessions"
        extra={
          <Link
            to="/guidebook"
            className="text-xs font-medium text-deloitte-green hover:underline"
          >
            Data guidebook
          </Link>
        }
      />

      {error && (
        <Alert variant="error" title="Error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {!llamaparseConfigured && (
        <Alert variant="warning" title="LlamaParse not configured" className="mt-4">
          PDF and DOCX will use legacy text extraction until LLAMA_CLOUD_API_KEY is set in the
          server environment.
        </Alert>
      )}

      {/* Post-creation success banner */}
      {justCreatedId && justCreatedId === engagementId && (
        <div className="mt-4 p-4 bg-emerald-50 border border-emerald-200 rounded-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-emerald-800">
              Engagement created — {activeEngagement?.company_name}
            </p>
            <p className="text-xs text-emerald-700 mt-0.5">
              Upload your spend files below, then run Analysis or Diagnostic.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              type="button"
              className="px-3 py-1.5 rounded-lg bg-white border border-emerald-300 text-xs font-medium text-emerald-800 hover:bg-emerald-50 transition-colors"
              onClick={() => uploadSectionRef.current?.scrollIntoView({ behavior: 'smooth' })}
            >
              Upload files ↓
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded-lg bg-white border border-brand-border text-xs font-medium text-brand-ink hover:bg-brand-surface-muted transition-colors"
              onClick={() => navigate('/')}
            >
              Analysis →
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded-lg bg-deloitte-green text-white text-xs font-medium hover:bg-[#6fa31e] transition-colors"
              onClick={() => navigate('/diagnostic')}
            >
              Diagnostic →
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <Card title="Engagement" className="bg-white border-brand-border lg:col-span-1">
          <p className="text-xs text-brand-muted mb-3">
            One engagement can have multiple analysis sessions. Documents apply to all sessions
            under this engagement.
          </p>
          {activeEngagement && (
            <div className="mb-3 p-2.5 bg-brand-surface-muted rounded-lg border border-brand-border">
              <p className="text-xs font-semibold text-brand-ink">{activeEngagement.company_name}</p>
              <p className="text-[10px] font-mono text-brand-muted mt-0.5">{engagementId}</p>
              {readyDocCount > 0 && (
                <p className="text-[10px] text-emerald-700 mt-1 font-medium">
                  {readyDocCount} document{readyDocCount !== 1 ? 's' : ''} ready
                </p>
              )}
            </div>
          )}
          {engagements.length > 0 && (
            <>
              <Input
                placeholder="Search engagements…"
                value={engagementSearch}
                onChange={(e) => setEngagementSearch(e.target.value)}
                className="mb-2"
              />
              <div className="mb-3 flex items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-xs text-brand-muted cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={noDocsOnly}
                    onChange={(e) => setNoDocsOnly(e.target.checked)}
                  />
                  Show only engagements with no documents
                </label>
                {noDocEngagements.length > 0 && (
                  <button
                    type="button"
                    className="text-xs font-medium text-red-700 hover:underline shrink-0"
                    onClick={() => setPendingDelete(noDocEngagements)}
                  >
                    Delete all with no documents ({noDocEngagements.length})
                  </button>
                )}
              </div>
            </>
          )}
          {selectedEngagementIds.size > 0 && (
            <div className="mb-2 flex items-center justify-between gap-2 px-1">
              <span className="text-xs text-brand-muted">
                {selectedEngagementIds.size} selected
              </span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className="text-xs text-brand-muted hover:text-brand-ink hover:underline"
                  onClick={() => setSelectedEngagementIds(new Set())}
                >
                  Clear
                </button>
                <button
                  type="button"
                  className="text-xs font-medium text-red-700 hover:underline"
                  onClick={() => setPendingDelete(
                    engagements.filter((eng) => selectedEngagementIds.has(eng.engagement_id)),
                  )}
                >
                  Delete selected ({selectedEngagementIds.size})
                </button>
              </div>
            </div>
          )}
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {filteredEngagements.length === 0 && engagements.length > 0 && (
              <p className="text-xs text-brand-muted text-center py-3">
                {noDocsOnly && !engagementSearch.trim()
                  ? 'No engagements without documents.'
                  : 'No engagements match your filters.'}
              </p>
            )}
            {filteredEngagements.map((e) => (
              <div
                key={e.engagement_id}
                className={`w-full flex items-start gap-2 px-3 py-2 rounded-lg border text-sm transition-colors ${
                  e.engagement_id === engagementId
                    ? 'border-deloitte-green bg-emerald-50/50'
                    : 'border-brand-border hover:bg-brand-surface-muted'
                }`}
              >
                <input
                  type="checkbox"
                  className="mt-1.5 shrink-0"
                  checked={selectedEngagementIds.has(e.engagement_id)}
                  onChange={() => toggleEngagementSelection(e.engagement_id)}
                  aria-label={`Select ${e.company_name}`}
                />
                <button
                  type="button"
                  onClick={() => handleSelectEngagement(e.engagement_id)}
                  className="flex-1 text-left"
                >
                  <p className="font-medium text-brand-ink">{e.company_name}</p>
                  <p className="text-xs text-brand-muted mt-0.5">
                    {e.document_count} docs · {e.session_count} sessions
                  </p>
                </button>
                <button
                  type="button"
                  className="text-xs text-red-700 hover:underline shrink-0 mt-0.5"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    setPendingDelete([e]);
                  }}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
          <Button type="button" variant="secondary" className="mt-4 w-full" onClick={openCreateModal}>
            + New engagement
          </Button>

          {/* Navigation shortcuts */}
          {engagementId && (
            <div className="mt-3 flex gap-2">
              <Link
                to="/"
                className="flex-1 text-center px-2 py-1.5 rounded-lg border border-brand-border text-xs font-medium text-brand-ink hover:bg-brand-surface-muted transition-colors"
              >
                Analysis →
              </Link>
              <Link
                to="/diagnostic"
                className="flex-1 text-center px-2 py-1.5 rounded-lg border border-brand-border text-xs font-medium text-brand-ink hover:bg-brand-surface-muted transition-colors"
              >
                Diagnostic →
              </Link>
            </div>
          )}
        </Card>

        <div ref={uploadSectionRef} className="lg:col-span-2">
          <Card title="Upload files" className="bg-white border-brand-border h-full">
            <p className="text-sm text-brand-muted mb-4">
              Supported: CSV, Excel (.xlsx, .xls), JSON, PDF, DOCX, TXT. Tabular files feed spend
              analysis; documents enrich context via LlamaParse when configured.
            </p>
            <div
              className="border-2 border-dashed border-brand-border rounded-xl p-8 text-center hover:border-deloitte-green/50 transition-colors"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                void handleUpload(e.dataTransfer.files);
              }}
            >
              <input
                ref={fileRef}
                type="file"
                multiple
                accept={ACCEPT}
                className="hidden"
                onChange={(e) => void handleUpload(e.target.files)}
              />
              <p className="text-sm text-brand-ink mb-3">Drag and drop files here, or</p>
              <Button
                type="button"
                disabled={uploading || !engagementId}
                onClick={() => fileRef.current?.click()}
              >
                {uploading ? 'Uploading…' : 'Choose files'}
              </Button>
            </div>
          </Card>
        </div>
      </div>

      <Card title="Document library" className="bg-white border-brand-border mt-6">
        {loading ? (
          <Loader label="Loading documents…" />
        ) : documents.length === 0 ? (
          <p className="text-sm text-brand-muted py-6 text-center">
            No documents yet. Upload spend ledgers and supporting files to run analysis.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-brand-border text-left">
                  <th className="py-2 pr-4 font-semibold text-brand-ink">File</th>
                  <th className="py-2 pr-4 font-semibold text-brand-ink">Role</th>
                  <th className="py-2 pr-4 font-semibold text-brand-ink">Status</th>
                  <th className="py-2 pr-4 font-semibold text-brand-ink">Size</th>
                  <th className="py-2 pr-4 font-semibold text-brand-ink">Lines</th>
                  <th className="py-2 font-semibold text-brand-ink">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-brand-border">
                {documents.map((doc) => (
                  <tr key={doc.document_id}>
                    <td className="py-3 pr-4 align-top">
                      <p className="font-medium text-brand-ink break-all">{doc.filename}</p>
                      <p className="text-xs font-mono text-brand-muted mt-0.5">
                        {truncateId(doc.document_id)}
                        {doc.parse_backend ? ` · ${doc.parse_backend}` : ''}
                      </p>
                      {doc.text_preview && (
                        <p className="text-xs text-brand-muted mt-1 line-clamp-2">
                          {doc.text_preview}
                        </p>
                      )}
                      {doc.error && (
                        <p className="text-xs text-red-700 mt-1">{doc.error}</p>
                      )}
                    </td>
                    <td className="py-3 pr-4 align-top text-brand-muted capitalize">
                      {(doc.role || '—').replace('_', ' ')}
                    </td>
                    <td className="py-3 pr-4 align-top">
                      <span
                        className={`text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border ${
                          STATUS_STYLES[doc.status || 'pending'] ?? STATUS_STYLES.pending
                        }`}
                      >
                        {doc.status || 'pending'}
                      </span>
                    </td>
                    <td className="py-3 pr-4 align-top text-brand-muted">
                      {formatFileSize(doc.size_bytes)}
                    </td>
                    <td className="py-3 pr-4 align-top text-brand-muted">
                      {doc.line_count ? doc.line_count.toLocaleString() : '—'}
                    </td>
                    <td className="py-3 align-top">
                      <div className="flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="text-xs text-brand-muted hover:text-brand-ink"
                          onClick={() => void handleReprocess(doc.document_id)}
                        >
                          Reprocess
                        </button>
                        <button
                          type="button"
                          className="text-xs text-red-700 hover:underline"
                          onClick={() => void handleDelete(doc.document_id)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="text-xs text-brand-muted mt-4">
        Open{' '}
        <Link to="/" className="text-deloitte-green hover:underline">
          Analysis
        </Link>{' '}
        or{' '}
        <Link to="/diagnostic" className="text-deloitte-green hover:underline">
          Diagnostic
        </Link>{' '}
        — both use documents from this engagement.
      </p>

      {/* New engagement modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={(e) => { if (e.target === e.currentTarget) setShowCreateModal(false); }}
        >
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-brand-ink mb-1">New engagement</h2>
            <p className="text-xs text-brand-muted mb-5">
              Enter company details. You can upload documents once the engagement is created.
            </p>
            <form onSubmit={handleCreateEngagement} className="space-y-4">
              <Input
                label="Company name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="e.g. Acme Corp"
                required
              />
              <Select
                label="Industry"
                value={newIndustry}
                onChange={(e) => setNewIndustry(e.target.value)}
                options={SECTOR_OPTIONS as unknown as { value: string; label: string }[]}
              />
              <Input
                label="Annual Revenue (₹ Cr)"
                type="number"
                value={newRevenueCr}
                onChange={(e) => setNewRevenueCr(e.target.value)}
                placeholder="5000"
              />
              <Select
                label="Reporting Currency"
                value={newCurrency}
                onChange={(e) => setNewCurrency(e.target.value)}
                options={CURRENCY_OPTIONS}
              />
              <div className="flex gap-3 pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  className="flex-1"
                  onClick={() => setShowCreateModal(false)}
                  disabled={creating}
                >
                  Cancel
                </Button>
                <Button type="submit" className="flex-1" disabled={creating || !newName.trim()} loading={creating}>
                  Create engagement
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      <Modal
        open={pendingDelete.length > 0}
        title={pendingDelete.length > 1 ? `Delete ${pendingDelete.length} engagements` : 'Delete engagement'}
        onClose={() => { if (!deletingEngagement) setPendingDelete([]); }}
        onConfirm={handleConfirmDeleteEngagement}
        confirmLabel={
          deletingEngagement
            ? 'Deleting…'
            : pendingDelete.length > 1
              ? `Delete ${pendingDelete.length} engagements`
              : 'Delete engagement'
        }
        confirmVariant="danger"
      >
        {pendingDelete.length > 1 ? (
          <div className="text-sm text-brand-ink">
            <p className="mb-2">
              This permanently deletes the following {pendingDelete.length} engagements, along with
              all of their documents and analysis sessions. This action cannot be undone.
            </p>
            <ul className="list-disc list-inside text-xs text-brand-muted max-h-32 overflow-y-auto space-y-0.5">
              {pendingDelete.map((e) => (
                <li key={e.engagement_id}>{e.company_name}</li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-brand-ink">
            This permanently deletes{' '}
            <span className="font-semibold">{pendingDelete[0]?.company_name}</span>, along with all
            of its documents and analysis sessions. This action cannot be undone.
          </p>
        )}
      </Modal>
    </MainLayout>
  );
};
