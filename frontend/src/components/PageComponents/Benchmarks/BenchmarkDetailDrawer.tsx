import React from 'react';
import { useDialogA11y } from '../../../hooks/useDialogA11y';
import { Loader } from '../../Common/Loader';
import { getApiErrorMessage } from '../../../hooks/useApi';
import { useBenchmarkCoverage } from '../../../api/hooks/useBenchmarksQueries';

export interface BenchmarkDatasetRow {
  dataset_id: string;
  source?: string;
  industry_code?: string | null;
  industry_name?: string;
  vintage_date?: string;
  specificity_score?: number;
  geography?: string;
  sample_size?: number;
}

interface LeverDetailRow {
  lever_id?: string;
  lever_name?: string;
  description?: string;
  category_ids?: string[];
  p10_pct?: number;
  p50_pct?: number;
  p90_pct?: number;
  implementation_weeks?: number;
  savings_type?: string;
}

export interface CoverageResponse {
  dataset_id: string;
  source?: string;
  industry_name?: string;
  specificity_score?: number;
  vintage_date?: string;
  coverage: Record<string, string[]>;
  industry_count: number;
  category_count: number;
  pack_id?: string | null;
  lever_count?: number;
  kpi_count?: number;
  peer_count?: number;
  category_detail?: Record<
    string,
    {
      P25?: number;
      P50?: number;
      P75?: number;
      P90?: number;
      unit?: string;
      confidence?: string;
      source_note?: string;
      linked_levers?: string[];
    }
  >;
  lever_detail?: LeverDetailRow[];
  category_lever_map?: Record<string, string[]>;
}

interface BenchmarkDetailDrawerProps {
  dataset: BenchmarkDatasetRow | null;
  onClose: () => void;
  onOpenSectorPack?: (packId: string) => void;
}

export function specificityBadge(score?: number): { label: string; className: string } {
  const s = score ?? 0;
  if (s > 0.85) return { label: 'Licensed / custom', className: 'bg-violet-100 text-violet-800' };
  if (s >= 0.8) return { label: 'Public disclosure', className: 'bg-emerald-100 text-emerald-800' };
  return { label: 'Illustrative', className: 'bg-amber-100 text-amber-800' };
}

export const BenchmarkDetailDrawer: React.FC<BenchmarkDetailDrawerProps> = ({
  dataset,
  onClose,
  onOpenSectorPack,
}) => {
  const panelRef = useDialogA11y<HTMLDivElement>(Boolean(dataset), onClose);
  const coverageQuery = useBenchmarkCoverage(dataset?.dataset_id);
  const coverage = coverageQuery.data ?? null;
  const loading = coverageQuery.isLoading;
  const error = coverageQuery.isError ? getApiErrorMessage(coverageQuery.error) : null;

  if (!dataset) return null;

  const badge = specificityBadge(dataset.specificity_score ?? coverage?.specificity_score);
  const title = dataset.industry_name || dataset.industry_code || dataset.dataset_id;
  const packId =
    coverage?.pack_id ||
    (dataset.dataset_id.startsWith('sector-pack-') ? dataset.dataset_id.slice('sector-pack-'.length) : null);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="benchmark-drawer-title"
        tabIndex={-1}
        className="bg-white h-full w-full max-w-2xl overflow-y-auto p-5 shadow-xl outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 id="benchmark-drawer-title" className="text-lg font-bold text-brand-ink">{title}</h2>
            <p className="text-xs text-brand-muted mt-0.5">{dataset.dataset_id}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="text-brand-muted hover:text-brand-ink text-xl">
            ×
          </button>
        </div>

        <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded ${badge.className}`}>
          {badge.label}
        </span>

        {packId && onOpenSectorPack && (
          <button
            type="button"
            className="mt-3 text-sm text-brand-primary underline block"
            onClick={() => onOpenSectorPack(packId)}
          >
            Open full sector pack →
          </button>
        )}

        <dl className="mt-4 text-sm space-y-2">
          <div className="flex justify-between gap-4">
            <dt className="text-brand-muted">Source</dt>
            <dd className="text-brand-ink text-right">{dataset.source || coverage?.source || '—'}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-brand-muted">Vintage</dt>
            <dd className="text-brand-ink">{dataset.vintage_date || coverage?.vintage_date || '—'}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-brand-muted">Specificity</dt>
            <dd className="text-brand-ink">
              {((dataset.specificity_score ?? coverage?.specificity_score) || 0).toFixed(2)}
            </dd>
          </div>
          {coverage && (coverage.lever_count ?? 0) > 0 && (
            <div className="flex justify-between gap-4">
              <dt className="text-brand-muted">Sector levers</dt>
              <dd className="text-brand-ink">{coverage.lever_count}</dd>
            </div>
          )}
          {dataset.geography && (
            <div className="flex justify-between gap-4">
              <dt className="text-brand-muted">Geography</dt>
              <dd className="text-brand-ink">{dataset.geography}</dd>
            </div>
          )}
        </dl>

        {loading && <Loader label="Loading coverage…" />}
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}

        {coverage && (
          <>
            <section className="mt-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-brand-muted mb-2">
                Coverage ({coverage.industry_count} industries · {coverage.category_count} categories)
              </h3>
              {coverage.category_detail && Object.keys(coverage.category_detail).length > 0 ? (
                <div className="overflow-x-auto border border-brand-border rounded-lg max-h-64 overflow-y-auto">
                  <table className="min-w-full text-xs">
                    <thead className="bg-brand-surface-muted sticky top-0">
                      <tr>
                        <th className="text-left p-2">Category</th>
                        <th className="text-right p-2">P25</th>
                        <th className="text-right p-2">P50</th>
                        <th className="text-right p-2">P75</th>
                        <th className="text-right p-2">P90</th>
                        <th className="text-left p-2">Unit</th>
                        <th className="text-left p-2">Levers</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(coverage.category_detail).map(([catId, cat]) => (
                        <tr key={catId} className="border-t border-brand-border">
                          <td className="p-2 font-medium">{catId}</td>
                          <td className="p-2 text-right tabular-nums">{cat.P25 ?? '—'}</td>
                          <td className="p-2 text-right tabular-nums font-medium">{cat.P50 ?? '—'}</td>
                          <td className="p-2 text-right tabular-nums">{cat.P75 ?? '—'}</td>
                          <td className="p-2 text-right tabular-nums">{cat.P90 ?? '—'}</td>
                          <td className="p-2 text-brand-muted">{cat.unit || '% of revenue'}</td>
                          <td className="p-2 text-brand-muted text-[10px]">
                            {cat.linked_levers?.length ? cat.linked_levers.join(', ') : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="max-h-64 overflow-y-auto border border-brand-border rounded-lg p-2 text-xs">
                  {Object.entries(coverage.coverage || {}).map(([ind, cats]) => (
                    <div key={ind} className="mb-2">
                      <p className="font-medium text-brand-ink">{ind}</p>
                      <p className="text-brand-muted">{Array.isArray(cats) ? cats.join(', ') : ''}</p>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {coverage.lever_detail && coverage.lever_detail.length > 0 && (
              <section className="mt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-brand-muted mb-2">
                  Sector levers ({coverage.lever_detail.length})
                </h3>
                <div className="overflow-x-auto border border-brand-border rounded-lg max-h-48 overflow-y-auto">
                  <table className="min-w-full text-xs">
                    <thead className="bg-brand-surface-muted sticky top-0">
                      <tr>
                        <th className="text-left p-2">Lever</th>
                        <th className="text-right p-2">P10</th>
                        <th className="text-right p-2">P50</th>
                        <th className="text-right p-2">P90</th>
                        <th className="text-left p-2">Categories</th>
                      </tr>
                    </thead>
                    <tbody>
                      {coverage.lever_detail.map((lev) => (
                        <tr key={lev.lever_id} className="border-t border-brand-border">
                          <td className="p-2 font-medium">{lev.lever_name || lev.lever_id}</td>
                          <td className="p-2 text-right tabular-nums">{lev.p10_pct ?? '—'}%</td>
                          <td className="p-2 text-right tabular-nums">{lev.p50_pct ?? '—'}%</td>
                          <td className="p-2 text-right tabular-nums">{lev.p90_pct ?? '—'}%</td>
                          <td className="p-2 text-brand-muted">
                            {lev.category_ids?.join(', ') || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
};
