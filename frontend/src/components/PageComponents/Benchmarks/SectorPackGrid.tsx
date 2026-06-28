import React, { useMemo, useState } from 'react';
import { Loader } from '../../Common/Loader';
import { Input } from '../../Common/Input';
import type { SectorPackRow } from './SectorPackDetailDrawer';

type StatusFilter = 'all' | 'full' | 'incomplete' | 'error';

const STATUS_BADGE: Record<string, string> = {
  full: 'bg-emerald-100 text-emerald-800',
  partial: 'bg-amber-100 text-amber-800',
  stub: 'bg-slate-100 text-slate-700',
};

function packStatus(pack: SectorPackRow): 'error' | 'full' | 'incomplete' {
  if (pack.error) return 'error';
  if (pack.status === 'full') return 'full';
  return 'incomplete';
}

function statusLabel(pack: SectorPackRow): string {
  if (pack.error) return 'Error';
  return pack.status || 'unknown';
}

interface SectorPackGridProps {
  packs: SectorPackRow[];
  loading: boolean;
  activePeerSet: string | null;
  onSelectPack: (pack: SectorPackRow) => void;
  onClearPeerSet: () => void;
}

export const SectorPackGrid: React.FC<SectorPackGridProps> = ({
  packs,
  loading,
  activePeerSet,
  onSelectPack,
  onClearPeerSet,
}) => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  const errorCount = useMemo(() => packs.filter((p) => p.error).length, [packs]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return packs.filter((p) => {
      const status = packStatus(p);
      if (statusFilter === 'full' && status !== 'full') return false;
      if (statusFilter === 'incomplete' && status !== 'incomplete') return false;
      if (statusFilter === 'error' && status !== 'error') return false;
      if (!q) return true;
      const haystack = [p.sector, p.pack_id, p.status, p.version].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(q);
    });
  }, [packs, search, statusFilter]);

  if (loading) {
    return (
      <div className="mt-8">
        <Loader label="Loading sector packs…" />
      </div>
    );
  }

  return (
    <div className="mt-6 space-y-4">
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-brand-border bg-brand-surface-muted/40 px-4 py-3">
        <div className="flex flex-wrap gap-4 text-sm">
          <span className="text-brand-ink">
            <strong>{packs.length}</strong> sector packs
          </span>
          {errorCount > 0 && (
            <span className="text-amber-700">
              <strong>{errorCount}</strong> with issues
            </span>
          )}
        </div>
        {activePeerSet && (
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span className="rounded-full bg-white border border-brand-border px-2.5 py-1 text-brand-ink">
              Session peer set: <strong>{activePeerSet}</strong>
            </span>
            <button
              type="button"
              className="text-deloitte-green underline"
              onClick={onClearPeerSet}
            >
              Clear
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <Input
            label="Search packs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Sector name or pack ID…"
          />
        </div>
        <div className="sm:w-44">
          <label className="block text-xs font-semibold text-brand-muted mb-1">Status</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="w-full rounded-md border border-brand-border bg-white px-3 py-2 text-sm text-brand-ink"
          >
            <option value="all">All</option>
            <option value="full">Full</option>
            <option value="incomplete">Incomplete</option>
            <option value="error">With errors</option>
          </select>
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-brand-muted py-8 text-center border border-dashed border-brand-border rounded-lg">
          {packs.length === 0
            ? 'No sector packs available.'
            : 'No packs match your search or filter.'}
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((p) => (
            <SectorPackCard key={p.pack_id} pack={p} onClick={() => onSelectPack(p)} />
          ))}
        </div>
      )}
    </div>
  );
};

function StatChip({ label }: { label: string }) {
  return (
    <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-brand-surface-muted text-brand-muted">
      {label}
    </span>
  );
}

function SectorPackCard({ pack, onClick }: { pack: SectorPackRow; onClick: () => void }) {
  const status = packStatus(pack);
  const badgeClass =
    status === 'error'
      ? 'bg-rose-100 text-rose-800'
      : STATUS_BADGE[pack.status || ''] || 'bg-slate-100 text-slate-700';

  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left rounded-lg border border-brand-border bg-white p-4 shadow-sm hover:border-deloitte-green/40 hover:shadow-md transition-shadow"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-brand-ink truncate">{pack.sector || pack.pack_id}</p>
          <p className="text-xs text-brand-muted mt-0.5 font-mono truncate">{pack.pack_id}</p>
        </div>
        <span className={`shrink-0 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${badgeClass}`}>
          {statusLabel(pack)}
        </span>
      </div>

      {pack.version && (
        <p className="text-xs text-brand-muted mt-2">Version {pack.version}</p>
      )}

      <div className="flex flex-wrap gap-1.5 mt-3">
        {pack.lever_count != null && pack.lever_count > 0 && (
          <StatChip label={`${pack.lever_count} levers`} />
        )}
        {pack.kpi_count != null && pack.kpi_count > 0 && (
          <StatChip label={`${pack.kpi_count} KPIs`} />
        )}
        {pack.peer_count != null && pack.peer_count > 0 && (
          <StatChip label={`${pack.peer_count} peers`} />
        )}
        {pack.category_count != null && pack.category_count > 0 && (
          <StatChip label={`${pack.category_count} categories`} />
        )}
      </div>

      {pack.error && (
        <p className="text-xs text-amber-700 mt-2 line-clamp-2">Incomplete pack: {pack.error}</p>
      )}
    </button>
  );
}
