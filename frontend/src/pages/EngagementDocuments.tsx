import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { PageHeader } from '../components/Common/PageHeader';
import { Card } from '../components/Common/Card';
import { Alert } from '../components/Common/Alert';
import { Loader } from '../components/Common/Loader';
import { Button } from '../components/Common/Button';
import { useSession } from '../context/SessionContext';
import { apiDelete, apiGet, apiPost, apiUpload, getApiErrorMessage } from '../hooks/useApi';
import { formatFileSize } from '../utils/sessionFiles';
import type { EngagementDocument, EngagementSummary } from '../types';

const ACCEPT =
  '.csv,.xlsx,.xls,.json,.pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,application/json';

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
  const {
    engagementId,
    setEngagementId,
    ensureEngagement,
    listEngagements,
    createEngagement,
    engagement,
  } = useSession();
  const [engagements, setEngagements] = useState<EngagementSummary[]>([]);
  const [documents, setDocuments] = useState<EngagementDocument[]>([]);
  const [llamaparseConfigured, setLlamaparseConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    const pending = documents.some(
      (d) => d.status === 'pending' || d.status === 'processing',
    );
    if (!engagementId || !pending) return;
    pollRef.current = setInterval(() => {
      loadDocuments(engagementId).catch(() => undefined);
    }, 2500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [documents, engagementId, loadDocuments]);

  const handleSelectEngagement = async (eid: string) => {
    setEngagementId(eid);
    setLoading(true);
    try {
      await loadDocuments(eid);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const handleNewEngagement = async () => {
    setLoading(true);
    try {
      const eid = await createEngagement({
        company_name: 'New engagement',
        industry: engagement.industry,
        currency: engagement.currency || 'INR',
      });
      await loadEngagements();
      await loadDocuments(eid);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
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

  const handleReprocess = async (docId: string) => {
    if (!engagementId) return;
    try {
      await apiPost(`/api/v1/engagements/${engagementId}/documents/${docId}/reprocess`, {});
      await loadDocuments(engagementId);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
        <Card title="Engagement" className="bg-white border-brand-border lg:col-span-1">
          <p className="text-xs text-brand-muted mb-3">
            One engagement can have multiple analysis sessions. Documents apply to all sessions
            under this engagement.
          </p>
          {engagementId && (
            <p className="text-xs font-mono text-brand-ink mb-3">
              ID: {engagementId}
            </p>
          )}
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {engagements.map((e) => (
              <button
                key={e.engagement_id}
                type="button"
                onClick={() => handleSelectEngagement(e.engagement_id)}
                className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                  e.engagement_id === engagementId
                    ? 'border-deloitte-green bg-emerald-50/50'
                    : 'border-brand-border hover:bg-brand-surface-muted'
                }`}
              >
                <p className="font-medium text-brand-ink">{e.company_name}</p>
                <p className="text-xs text-brand-muted mt-0.5">
                  {e.document_count} docs · {e.session_count} sessions
                </p>
              </button>
            ))}
          </div>
          <Button type="button" variant="secondary" className="mt-4 w-full" onClick={handleNewEngagement}>
            New engagement
          </Button>
        </Card>

        <Card title="Upload files" className="bg-white border-brand-border lg:col-span-2">
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
        to run the pipeline — it uses documents from this engagement plus any session attachments.
      </p>
    </MainLayout>
  );
};
