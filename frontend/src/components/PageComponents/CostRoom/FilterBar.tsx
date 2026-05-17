import React, { useMemo } from 'react';
import type { Initiative } from '../../../types';
import { GATE2_AQS_THRESHOLD, getAqs } from '../../../utils/initiativeHelpers';

export interface PortfolioFilters {
  lever: string;
  businessUnit: string;
  owner: string;
  status: string;
  minP50: number;
  needsActionOnly: boolean;
}

export const defaultFilters: PortfolioFilters = {
  lever: '',
  businessUnit: '',
  owner: '',
  status: '',
  minP50: 0,
  needsActionOnly: true,
};

const PENDING_STAGES = new Set(['identified', 'proposed', 'validated']);

export function isNeedsActionInitiative(row: Initiative): boolean {
  const stage = row.stage ?? '';
  if (!PENDING_STAGES.has(stage)) return false;
  const aqs = getAqs(row);
  if (aqs != null && aqs < GATE2_AQS_THRESHOLD) return true;
  return stage === 'identified' || stage === 'proposed';
}

interface FilterBarProps {
  initiatives: Initiative[];
  filters: PortfolioFilters;
  onChange: (next: PortfolioFilters) => void;
  filteredCount: number;
  exceptionCount?: number;
}

function uniqueOptions(rows: Initiative[], key: keyof Initiative): string[] {
  const set = new Set<string>();
  for (const row of rows) {
    const v = String(row[key] ?? '').trim();
    if (v) set.add(v);
  }
  return Array.from(set).sort();
}

export const FilterBar: React.FC<FilterBarProps> = ({
  initiatives,
  filters,
  onChange,
  filteredCount,
  exceptionCount = 0,
}) => {
  const levers = useMemo(() => uniqueOptions(initiatives, 'lever'), [initiatives]);
  const categories = useMemo(() => uniqueOptions(initiatives, 'category'), [initiatives]);
  const owners = useMemo(() => uniqueOptions(initiatives, 'owner_name'), [initiatives]);
  const statuses = useMemo(() => uniqueOptions(initiatives, 'stage'), [initiatives]);

  const selectClass =
    'text-sm border border-brand-border rounded-lg px-3 py-2 bg-white text-brand-ink min-w-[120px]';

  return (
    <div className="flex flex-wrap items-end gap-4 p-4 bg-white border border-brand-border rounded-xl">
      <div className="flex flex-col gap-2 w-full sm:w-auto">
        <span className="text-xs font-semibold uppercase tracking-wide text-brand-muted">View</span>
        <div className="flex rounded-lg border border-brand-border overflow-hidden">
          <button
            type="button"
            className={`px-3 py-2 text-sm font-medium ${
              filters.needsActionOnly
                ? 'bg-brand-green text-white'
                : 'bg-white text-brand-ink hover:bg-brand-surface-muted'
            }`}
            onClick={() => onChange({ ...filters, needsActionOnly: true })}
          >
            Needs action
            {exceptionCount > 0 && (
              <span className="ml-1.5 inline-flex min-w-[1.1rem] justify-center rounded-full bg-white/25 px-1 text-xs">
                {exceptionCount}
              </span>
            )}
          </button>
          <button
            type="button"
            className={`px-3 py-2 text-sm font-medium border-l border-brand-border ${
              !filters.needsActionOnly
                ? 'bg-brand-navy text-white'
                : 'bg-white text-brand-ink hover:bg-brand-surface-muted'
            }`}
            onClick={() => onChange({ ...filters, needsActionOnly: false })}
          >
            All initiatives
          </button>
        </div>
      </div>
      <FilterField label="Lever">
        <select
          className={selectClass}
          value={filters.lever}
          onChange={(e) => onChange({ ...filters, lever: e.target.value })}
        >
          <option value="">All</option>
          {levers.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </FilterField>
      <FilterField label="Business unit">
        <select
          className={selectClass}
          value={filters.businessUnit}
          onChange={(e) => onChange({ ...filters, businessUnit: e.target.value })}
        >
          <option value="">All</option>
          {categories.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </FilterField>
      <FilterField label="Owner">
        <select
          className={selectClass}
          value={filters.owner}
          onChange={(e) => onChange({ ...filters, owner: e.target.value })}
        >
          <option value="">All</option>
          {owners.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </FilterField>
      <FilterField label="Status">
        <select
          className={selectClass}
          value={filters.status}
          onChange={(e) => onChange({ ...filters, status: e.target.value })}
        >
          <option value="">All</option>
          {statuses.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </FilterField>
      <FilterField label="Min P50 (₹ Cr)">
        <input
          type="number"
          min={0}
          className={`${selectClass} w-24`}
          value={filters.minP50 || ''}
          onChange={(e) => onChange({ ...filters, minP50: Number(e.target.value) || 0 })}
        />
      </FilterField>
      <p className="text-sm text-brand-muted ml-auto pb-2">
        Showing <strong className="text-brand-ink">{filteredCount}</strong> of {initiatives.length}
      </p>
    </div>
  );
};

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-semibold uppercase tracking-wide text-brand-muted">{label}</span>
      {children}
    </label>
  );
}

export function applyPortfolioFilters(
  rows: Initiative[],
  filters: PortfolioFilters,
  p50For: (row: Initiative) => number,
): Initiative[] {
  return rows.filter((row) => {
    if (filters.needsActionOnly && !isNeedsActionInitiative(row)) return false;
    if (filters.lever && row.lever !== filters.lever) return false;
    if (filters.businessUnit && row.category !== filters.businessUnit) return false;
    if (filters.owner && row.owner_name !== filters.owner) return false;
    if (filters.status && row.stage !== filters.status) return false;
    if (filters.minP50 > 0 && p50For(row) < filters.minP50) return false;
    return true;
  });
}
