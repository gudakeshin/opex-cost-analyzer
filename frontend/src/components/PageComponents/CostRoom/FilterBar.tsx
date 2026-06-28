import React, { useMemo } from 'react';
import type { Initiative } from '../../../types';
import { isNeedsActionInitiative, stageLabel } from '../../../utils/initiativeHelpers';
import { SegControl } from './primitives/SegControl';

export type LayoutMode = 'split' | 'worklist' | 'kanban';

export interface PortfolioFilters {
  pool: string;
  owner: string;
  status: string;
  needsActionOnly: boolean;
}

export const defaultFilters: PortfolioFilters = {
  pool: '',
  owner: '',
  status: '',
  needsActionOnly: true,
};

// Re-export for backward compatibility
export { isNeedsActionInitiative };

interface FilterBarProps {
  initiatives: Initiative[];
  filters: PortfolioFilters;
  onChange: (next: PortfolioFilters) => void;
  filteredCount: number;
  needsActionCount?: number;
  layoutMode: LayoutMode;
  onLayoutModeChange: (mode: LayoutMode) => void;
  executive?: boolean;
}

function uniqueOptions(rows: Initiative[], key: keyof Initiative): string[] {
  const set = new Set<string>();
  for (const row of rows) {
    const v = String(row[key] ?? '').trim();
    if (v && v !== '—') set.add(v);
  }
  return Array.from(set).sort();
}

export const FilterBar: React.FC<FilterBarProps> = ({
  initiatives,
  filters,
  onChange,
  filteredCount,
  needsActionCount = 0,
  layoutMode,
  onLayoutModeChange,
  executive = false,
}) => {
  const pools = useMemo(() => uniqueOptions(initiatives, 'category'), [initiatives]);
  const owners = useMemo(() => uniqueOptions(initiatives, 'owner_name'), [initiatives]);
  const statuses = useMemo(() => uniqueOptions(initiatives, 'stage'), [initiatives]);

  const selectClass =
    'text-sm border border-[var(--cr-line)] rounded-[var(--cr-r-sm)] px-2.5 py-1.5 bg-white text-[var(--cr-ink)] cursor-pointer';

  return (
    <div className="cr-card flex flex-wrap items-center gap-3.5 px-4 py-3">
      <SegControl
        green
        value={filters.needsActionOnly ? 'needs' : 'all'}
        onChange={(v) => onChange({ ...filters, needsActionOnly: v === 'needs' })}
        options={[
          {
            value: 'needs',
            label: `Needs action${needsActionCount ? ` · ${needsActionCount}` : ''}`,
          },
          { value: 'all', label: 'All initiatives' },
        ]}
      />
      <div className="w-px h-6 bg-[var(--cr-line)] hidden sm:block" />
      <select
        className={selectClass}
        value={filters.pool}
        onChange={(e) => onChange({ ...filters, pool: e.target.value })}
      >
        <option value="">All pools</option>
        {pools.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
      <select
        className={selectClass}
        value={filters.owner}
        onChange={(e) => onChange({ ...filters, owner: e.target.value })}
      >
        <option value="">All owners</option>
        {owners.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <select
        className={selectClass}
        value={filters.status}
        onChange={(e) => onChange({ ...filters, status: e.target.value })}
      >
        <option value="">All stages</option>
        {statuses.map((s) => (
          <option key={s} value={s}>
            {stageLabel(s)}
          </option>
        ))}
      </select>
      <div className="ml-auto flex items-center gap-3 flex-wrap">
        <span className="text-xs text-[var(--cr-gray-2)]">
          Showing <strong className="text-[var(--cr-ink)]">{filteredCount}</strong> of{' '}
          {initiatives.length}
        </span>
        {!executive && (
          <>
            <div className="w-px h-6 bg-[var(--cr-line)] hidden sm:block" />
            <SegControl
              value={layoutMode}
              onChange={onLayoutModeChange}
              options={[
                { value: 'split', label: 'Table' },
                { value: 'worklist', label: 'Worklist' },
                { value: 'kanban', label: 'Board' },
              ]}
            />
          </>
        )}
      </div>
    </div>
  );
};

export function applyPortfolioFilters(
  rows: Initiative[],
  filters: PortfolioFilters,
): Initiative[] {
  return rows.filter((row) => {
    if (filters.needsActionOnly && !isNeedsActionInitiative(row)) return false;
    if (filters.pool && row.category !== filters.pool) return false;
    if (filters.owner && row.owner_name !== filters.owner) return false;
    if (filters.status && row.stage !== filters.status) return false;
    return true;
  });
}
