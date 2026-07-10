import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader } from '../../Common/Loader';
import { getApiErrorMessage } from '../../../hooks/useApi';
import { specificityBadge } from './BenchmarkDetailDrawer';
import { useSectorPackDetail } from '../../../api/hooks/useBenchmarksQueries';
import type {
  CategoryBenchmark,
  KpiRow,
  LeverRow,
  PeerRow,
  SectorPackDetailResponse,
  SectorPackRow,
} from '../../../types/sectorPack';
import { peerSizeColumnHeader, peerSizeValue } from '../../../utils/peerSizeFields';

export type { SectorPackRow, SectorPackDetailResponse };

type TabId = 'overview' | 'benchmarks' | 'levers' | 'kpis' | 'peers' | 'taxonomy' | 'regulatory' | 'sources';

const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'benchmarks', label: 'Benchmarks' },
  { id: 'levers', label: 'Levers' },
  { id: 'kpis', label: 'KPIs' },
  { id: 'peers', label: 'Peers' },
  { id: 'taxonomy', label: 'Taxonomy' },
  { id: 'regulatory', label: 'Regulatory' },
  { id: 'sources', label: 'Sources' },
];

interface SectorPackDetailDrawerProps {
  pack: SectorPackRow | null;
  onClose: () => void;
}

export const SectorPackDetailDrawer: React.FC<SectorPackDetailDrawerProps> = ({ pack, onClose }) => {
  const [tab, setTab] = useState<TabId>('overview');

  useEffect(() => {
    if (pack) setTab('overview');
  }, [pack]);

  const detailQuery = useSectorPackDetail(pack?.pack_id);
  const detail = detailQuery.data ?? null;
  const loading = detailQuery.isLoading;
  const error = detailQuery.isError ? getApiErrorMessage(detailQuery.error) : null;

  if (!pack) return null;

  const title = pack.sector || detail?.sector || pack.pack_id;
  const badge = specificityBadge(0.85);
  const manifest = detail?.manifest as Record<string, unknown> | undefined;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="bg-white h-full w-full max-w-3xl overflow-y-auto p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-brand-ink">{title}</h2>
            <p className="text-xs text-brand-muted mt-0.5">{pack.pack_id}</p>
            <Link
              to="/sector-packs"
              className="text-xs text-deloitte-green hover:underline mt-1 inline-block"
              onClick={onClose}
            >
              Edit pack in Studio →
            </Link>
          </div>
          <button type="button" onClick={onClose} className="text-brand-muted hover:text-brand-ink text-xl">
            ×
          </button>
        </div>

        <span className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded ${badge.className}`}>
          {badge.label}
        </span>

        {(pack.error || detail?.pack_error) && (
          <p className="mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
            {pack.error || detail?.pack_error}
          </p>
        )}

        <div className="flex flex-wrap gap-1 mt-4 border-b border-brand-border pb-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`text-xs px-2.5 py-1 rounded ${
                tab === t.id
                  ? 'bg-brand-ink text-white'
                  : 'text-brand-muted hover:bg-brand-surface-muted'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {loading && <Loader label="Loading sector pack…" />}
        {error && <p className="text-sm text-red-600 mt-3">{error}</p>}

        {detail && !loading && (
          <div className="mt-4">
            {tab === 'overview' && (
              <div className="space-y-4 text-sm">
                <dl className="space-y-2">
                  <div className="flex justify-between gap-4">
                    <dt className="text-brand-muted">Version</dt>
                    <dd>{detail.version || pack.version || '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-brand-muted">Status</dt>
                    <dd>{String(manifest?.status || pack.status || '—')}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-brand-muted">Effective from</dt>
                    <dd>{String(manifest?.effective_from || '—')}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-brand-muted">Vintage</dt>
                    <dd>{detail.vintage_date || '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt className="text-brand-muted">Confidence</dt>
                    <dd>{detail.confidence_overall || '—'}</dd>
                  </div>
                </dl>
                {typeof manifest?.description === 'string' && (
                  <p className="text-brand-ink">{manifest.description}</p>
                )}
                {detail.source_metadata?.methodology && (
                  <section>
                    <h3 className="text-xs font-semibold uppercase text-brand-muted mb-1">Methodology</h3>
                    <p>{detail.source_metadata.methodology}</p>
                  </section>
                )}
                {detail.source_metadata?.primary_sources && detail.source_metadata.primary_sources.length > 0 && (
                  <section>
                    <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Sources</h3>
                    <ul className="text-xs space-y-2">
                      {detail.source_metadata.primary_sources.map((src, i) => (
                        <li key={i} className="border-l-2 border-brand-border pl-2">
                          <p className="font-medium">{src.source_name}</p>
                          {src.notes && <p className="text-brand-muted mt-0.5">{src.notes}</p>}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
            )}

            {tab === 'benchmarks' && detail.categories && (
              <BenchmarkTable categories={detail.categories} />
            )}

            {tab === 'levers' && (
              <LeverTable levers={detail.levers || []} />
            )}

            {tab === 'kpis' && (
              <KpiTable kpis={detail.kpi_pack || []} />
            )}

            {tab === 'peers' && (
              <PeersPanel
                peers={detail.peers || []}
                metrics={detail.peer_benchmark_metrics || {}}
              />
            )}

            {tab === 'taxonomy' && (
              <TaxonomyPanel taxonomy={detail.taxonomy_extension} />
            )}

            {tab === 'regulatory' && (
              <pre className="text-xs whitespace-pre-wrap font-sans text-brand-ink bg-brand-surface-muted p-3 rounded-lg max-h-[70vh] overflow-y-auto">
                {detail.regulatory_layer || 'No regulatory layer documented for this pack.'}
              </pre>
            )}

            {tab === 'sources' && (
              <SourcesPanel sources={detail.benchmark_sources} />
            )}
          </div>
        )}
      </div>
    </div>
  );
};

function BenchmarkTable({ categories }: { categories: Record<string, CategoryBenchmark> }) {
  return (
    <div className="overflow-x-auto border border-brand-border rounded-lg">
      <table className="min-w-full text-xs">
        <thead className="bg-brand-surface-muted">
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
          {Object.entries(categories).map(([catId, cat]) => (
            <tr key={catId} className="border-t border-brand-border">
              <td className="p-2">
                <p className="font-medium text-brand-ink">{catId}</p>
                {cat.source_note && <p className="text-brand-muted mt-0.5 max-w-xs">{cat.source_note}</p>}
              </td>
              <td className="p-2 text-right tabular-nums">{cat.P25 ?? '—'}</td>
              <td className="p-2 text-right tabular-nums font-medium">{cat.P50 ?? '—'}</td>
              <td className="p-2 text-right tabular-nums">{cat.P75 ?? '—'}</td>
              <td className="p-2 text-right tabular-nums">{cat.P90 ?? '—'}</td>
              <td className="p-2 text-brand-muted">{cat.unit || '% of revenue'}</td>
              <td className="p-2 text-brand-muted">
                {cat.linked_levers?.length ? cat.linked_levers.join(', ') : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LeverTable({ levers }: { levers: LeverRow[] }) {
  if (!levers.length) return <p className="text-sm text-brand-muted">No sector levers defined.</p>;
  return (
    <div className="space-y-3">
      {levers.map((lev) => (
        <div key={lev.lever_id} className="border border-brand-border rounded-lg p-3 text-xs">
          <p className="font-semibold text-brand-ink">{lev.lever_name || lev.lever_id}</p>
          {lev.description && <p className="text-brand-muted mt-1">{lev.description}</p>}
          <div className="flex flex-wrap gap-3 mt-2 text-brand-ink">
            <span>P10 {lev.p10_pct ?? '—'}%</span>
            <span className="font-medium">P50 {lev.p50_pct ?? '—'}%</span>
            <span>P90 {lev.p90_pct ?? '—'}%</span>
            {lev.implementation_weeks != null && <span>{lev.implementation_weeks} wks</span>}
            {lev.savings_type && <span className="capitalize">{lev.savings_type}</span>}
          </div>
          {lev.category_ids && lev.category_ids.length > 0 && (
            <p className="mt-2 text-brand-muted">Categories: {lev.category_ids.join(', ')}</p>
          )}
          {lev.industry_sources && lev.industry_sources.length > 0 && (
            <ul className="mt-2 space-y-1 text-brand-muted">
              {lev.industry_sources.map((s, i) => (
                <li key={i} className="border-l-2 border-brand-border pl-2">{s}</li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function KpiTable({ kpis }: { kpis: KpiRow[] }) {
  if (!kpis.length) return <p className="text-sm text-brand-muted">No KPI pack defined.</p>;
  return (
    <div className="overflow-x-auto border border-brand-border rounded-lg">
      <table className="min-w-full text-xs">
        <thead className="bg-brand-surface-muted">
          <tr>
            <th className="text-left p-2">KPI</th>
            <th className="text-left p-2">Formula</th>
            <th className="text-left p-2">Target</th>
            <th className="text-right p-2">P50 benchmark</th>
          </tr>
        </thead>
        <tbody>
          {kpis.map((k) => (
            <tr key={k.kpi_id} className="border-t border-brand-border">
              <td className="p-2 font-medium">{k.kpi_name || k.kpi_id}</td>
              <td className="p-2 text-brand-muted">{k.formula || '—'}</td>
              <td className="p-2 capitalize">{k.target_direction || '—'}</td>
              <td className="p-2 text-right tabular-nums">
                {k.p50_benchmark_pct != null
                  ? `${k.p50_benchmark_pct}%`
                  : k.p50_benchmark_cr != null
                    ? `₹${k.p50_benchmark_cr} Cr`
                    : k.p50_benchmark_inr != null
                      ? `₹${k.p50_benchmark_inr}`
                      : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PeersPanel({
  peers,
  metrics,
}: {
  peers: PeerRow[];
  metrics: Record<string, { p25?: number; p50?: number; p75?: number }>;
}) {
  const sizeHeader = peerSizeColumnHeader(peers);

  return (
    <div className="space-y-4">
      {peers.length > 0 ? (
        <div className="overflow-x-auto border border-brand-border rounded-lg">
          <table className="min-w-full text-xs">
            <thead className="bg-brand-surface-muted">
              <tr>
                <th className="text-left p-2">Peer</th>
                <th className="text-left p-2">Ticker</th>
                <th className="text-right p-2">{sizeHeader}</th>
              </tr>
            </thead>
            <tbody>
              {peers.map((p) => {
                const size = peerSizeValue(p);
                return (
                <tr key={p.ticker || p.name} className="border-t border-brand-border">
                  <td className="p-2">{p.name}</td>
                  <td className="p-2 text-brand-muted">{p.ticker || '—'}</td>
                  <td className="p-2 text-right tabular-nums">
                    {size != null ? size.toLocaleString('en-IN') : '—'}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-brand-muted">No peers listed.</p>
      )}
      {Object.keys(metrics).length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Peer benchmark metrics</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            {Object.entries(metrics).map(([key, vals]) => (
              <div key={key} className="border border-brand-border rounded p-2">
                <p className="font-medium">{key.replace(/_/g, ' ')}</p>
                <p className="text-brand-muted mt-0.5">
                  P25 {vals.p25 ?? '—'} · P50 {vals.p50 ?? '—'} · P75 {vals.p75 ?? '—'}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function TaxonomyPanel({
  taxonomy,
}: {
  taxonomy?: SectorPackDetailResponse['taxonomy_extension'];
}) {
  if (!taxonomy) return <p className="text-sm text-brand-muted">No taxonomy extension.</p>;
  return (
    <div className="space-y-4 text-xs">
      {(taxonomy.additional_categories?.length ?? 0) > 0 && (
        <section>
          <h3 className="font-semibold uppercase text-brand-muted mb-2">Additional categories</h3>
          <ul className="space-y-1">
            {taxonomy.additional_categories!.map((c) => (
              <li key={c.category_id} className="border-l-2 border-brand-border pl-2">
                <span className="font-medium">{c.category_id}</span>
                {c.category_name && <span className="text-brand-muted"> — {c.category_name}</span>}
                {c.gl_prefix && <span className="text-brand-muted"> (GL {c.gl_prefix})</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {(taxonomy.overrides?.length ?? 0) > 0 && (
        <section>
          <h3 className="font-semibold uppercase text-brand-muted mb-2">Overrides</h3>
          <ul className="space-y-1">
            {taxonomy.overrides!.map((c) => (
              <li key={c.category_id} className="border-l-2 border-brand-border pl-2">
                <span className="font-medium">{c.category_id}</span>
                {c.category_name && <span className="text-brand-muted"> → {c.category_name}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function SourcesPanel({ sources }: { sources?: SectorPackDetailResponse['benchmark_sources'] }) {
  if (!sources) return <p className="text-sm text-brand-muted">No benchmark sources catalogued.</p>;
  return (
    <div className="space-y-4 text-xs">
      {(sources.free_sources?.length ?? 0) > 0 && (
        <section>
          <h3 className="font-semibold uppercase text-brand-muted mb-2">Free / public sources</h3>
          <ul className="space-y-2">
            {sources.free_sources!.map((s) => (
              <li key={s.id || s.name} className="border border-brand-border rounded p-2">
                <p className="font-medium">{s.name}</p>
                {s.sample_metric && <p className="text-brand-muted mt-0.5">{s.sample_metric}</p>}
                {s.url && (
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-deloitte-green underline mt-1 inline-block">
                    Source link
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {(sources.licensed_sources_stubs?.length ?? 0) > 0 && (
        <section>
          <h3 className="font-semibold uppercase text-brand-muted mb-2">Licensed source stubs</h3>
          <ul className="space-y-1">
            {sources.licensed_sources_stubs!.map((s) => (
              <li key={s.id || s.name}>{s.name || s.id}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
