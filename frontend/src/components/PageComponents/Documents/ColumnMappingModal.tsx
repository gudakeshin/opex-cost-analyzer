import React, { useEffect, useMemo, useState } from 'react';
import { Modal } from '../../Common/Modal';
import { Loader } from '../../Common/Loader';
import { apiGet, apiPost, getApiErrorMessage } from '../../../hooks/useApi';
import type { EngagementDocument } from '../../../types';

interface MappingEntry {
  column: string;
  match: 'exact' | 'partial' | 'inferred' | 'manual';
}

interface IngestionReportResponse {
  document_id: string;
  filename?: string;
  report: {
    warnings?: string[];
    quality?: {
      column_mapping?: Record<string, MappingEntry>;
      available_columns?: string[];
      unmapped_columns?: string[];
      rows_input?: number;
      rows_dropped?: number;
    };
  };
  column_overrides: Record<string, string>;
}

// The fields that matter most come first; the rest follow alphabetically.
const FIELD_ORDER = ['amount', 'supplier', 'description', 'date', 'currency', 'gl_code', 'cost_center'];

const MATCH_LABEL: Record<MappingEntry['match'], { text: string; className: string; title: string }> = {
  exact: { text: 'Exact', className: 'bg-emerald-50 text-emerald-800 border-emerald-200', title: 'Column name matches a known header' },
  partial: { text: 'Partial', className: 'bg-amber-50 text-amber-900 border-amber-200', title: 'Matched by part of the name — please confirm' },
  inferred: { text: 'Detected', className: 'bg-slate-50 text-slate-700 border-slate-200', title: 'Chosen from the column contents' },
  manual: { text: 'Your choice', className: 'bg-blue-50 text-blue-800 border-blue-200', title: 'Set by you' },
};

const humanize = (field: string) => field.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

interface ColumnMappingModalProps {
  engagementId: string;
  document: EngagementDocument;
  onClose: () => void;
  /** Called after the document has been queued for re-processing. */
  onReprocessed: () => void;
}

export const ColumnMappingModal: React.FC<ColumnMappingModalProps> = ({
  engagementId,
  document,
  onClose,
  onReprocessed,
}) => {
  const [data, setData] = useState<IngestionReportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiGet<IngestionReportResponse>(
      `/api/v1/engagements/${engagementId}/documents/${document.document_id}/ingestion-report`,
    )
      .then((res) => !cancelled && setData(res))
      .catch((e) => !cancelled && setError(getApiErrorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [engagementId, document.document_id]);

  const quality = data?.report?.quality;
  const mapping = quality?.column_mapping;
  const columns = quality?.available_columns ?? [];

  const rows = useMemo(() => {
    const fields = Object.keys(mapping ?? {});
    return fields.sort((a, b) => {
      const ia = FIELD_ORDER.indexOf(a);
      const ib = FIELD_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    });
  }, [mapping]);

  const changed = Object.keys(choices).length > 0;

  const submit = async (overrides: Record<string, string>) => {
    setSaving(true);
    setError(null);
    try {
      await apiPost(`/api/v1/engagements/${engagementId}/documents/${document.document_id}/reprocess`, {
        column_overrides: overrides,
      });
      onReprocessed();
      onClose();
    } catch (e) {
      setError(getApiErrorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      size="xl"
      title={`Column mapping — ${document.filename}`}
      onClose={onClose}
      onConfirm={changed && !saving ? () => void submit({ ...(data?.column_overrides ?? {}), ...choices }) : undefined}
      confirmLabel={saving ? 'Re-processing…' : 'Re-process with this mapping'}
    >
      {!data && !error && <Loader label="Loading mapping…" />}
      {error && (
        <p role="alert" className="text-sm text-error mb-3">
          {error}
        </p>
      )}
      {data && !mapping && (
        <p className="text-sm text-brand-muted">
          No column mapping is recorded for this document. Re-process it to generate one.
        </p>
      )}
      {mapping && (
        <>
          <p className="text-xs text-brand-muted mb-3">
            How each source column was matched to a field. Check the amber “Partial” matches, then change any wrong
            one and re-process.
            {quality?.rows_dropped ? ` ${quality.rows_dropped} of ${quality.rows_input} rows were dropped on the last parse.` : ''}
          </p>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-brand-muted">
                <th className="py-1 pr-3 font-medium">Field</th>
                <th className="py-1 pr-3 font-medium">Source column</th>
                <th className="py-1 font-medium">Match</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((field) => {
                const entry = mapping[field];
                const value = field in choices ? choices[field] : entry.column;
                const badge = MATCH_LABEL[field in choices ? 'manual' : entry.match];
                return (
                  <tr key={field} className="border-t border-brand-border">
                    <td className="py-1.5 pr-3">
                      <label htmlFor={`map-${field}`}>{humanize(field)}</label>
                    </td>
                    <td className="py-1.5 pr-3">
                      <select
                        id={`map-${field}`}
                        value={value}
                        onChange={(e) => setChoices((prev) => ({ ...prev, [field]: e.target.value }))}
                        className="w-full max-w-xs rounded border border-brand-border bg-white px-2 py-1 text-sm"
                      >
                        <option value="">— not used —</option>
                        {columns.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-1.5">
                      <span title={badge.title} className={`text-[11px] font-semibold px-1.5 py-0.5 rounded border ${badge.className}`}>
                        {badge.text}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {(quality?.unmapped_columns?.length ?? 0) > 0 && (
            <p className="mt-3 text-xs text-brand-muted">
              Not mapped to any field: {quality!.unmapped_columns!.join(', ')}
            </p>
          )}
          {Object.keys(data?.column_overrides ?? {}).length > 0 && (
            <button
              type="button"
              onClick={() => void submit({})}
              disabled={saving}
              className="mt-3 text-xs text-brand-primary underline"
            >
              Reset to automatic matching
            </button>
          )}
        </>
      )}
    </Modal>
  );
};
