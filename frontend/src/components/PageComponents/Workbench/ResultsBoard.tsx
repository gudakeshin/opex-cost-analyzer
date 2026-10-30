import React from 'react';
import { formatCr } from '../../../utils/formatInr';
import type { WorkbenchRun } from '../../../types';

interface ResultsBoardProps {
  runs: WorkbenchRun[];
  currency: string;
  compareIds: string[];
  onOpen: (run: WorkbenchRun) => void;
  onBranch: (run: WorkbenchRun) => void;
  onChain: (run: WorkbenchRun) => void;
  onDelete: (run: WorkbenchRun) => void;
  onToggleCompare: (runId: string) => void;
}

const STATUS_STYLES: Record<string, string> = {
  complete: 'bg-green-100 text-green-800',
  running: 'bg-blue-100 text-blue-800',
  failed: 'bg-red-100 text-red-800',
  draft: 'bg-gray-100 text-gray-700',
};

export const ResultsBoard: React.FC<ResultsBoardProps> = ({
  runs,
  currency,
  compareIds,
  onOpen,
  onBranch,
  onChain,
  onDelete,
  onToggleCompare,
}) => {
  if (runs.length === 0) {
    return (
      <p className="text-sm text-brand-muted py-8 text-center border border-dashed border-brand-border rounded-lg">
        No runs yet. Compose a run on the left and click <strong>Run analysis</strong> — each run lands here.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      {runs.map((run) => {
        const h = run.headline || {};
        const inCompare = compareIds.includes(run.run_id);
        return (
          <div
            key={run.run_id}
            className={`rounded-lg border p-3 bg-white flex flex-col gap-2 ${
              inCompare ? 'border-deloitte-green ring-1 ring-deloitte-green' : 'border-brand-border'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <button
                type="button"
                onClick={() => onOpen(run)}
                className="text-left font-semibold text-brand-ink text-sm hover:text-brand-primary truncate"
                title={run.name}
              >
                {run.name}
              </button>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${STATUS_STYLES[run.status] || ''}`}>
                {run.status}
              </span>
            </div>

            {run.parent_run_id && (
              <span className="text-[10px] text-brand-muted">↳ branched</span>
            )}

            <dl className="grid grid-cols-2 gap-1.5 text-xs">
              {h.savings_mid !== undefined && (
                <div>
                  <dt className="text-brand-muted">Savings (mid)</dt>
                  <dd className="font-semibold text-brand-ink">{formatCr(Number(h.savings_mid), { currency })}</dd>
                </div>
              )}
              {h.npv !== undefined && (
                <div>
                  <dt className="text-brand-muted">NPV</dt>
                  <dd className="font-semibold text-brand-ink">{formatCr(Number(h.npv), { currency })}</dd>
                </div>
              )}
              {h.initiative_count !== undefined && (
                <div>
                  <dt className="text-brand-muted">Initiatives</dt>
                  <dd className="font-semibold text-brand-ink">{h.initiative_count}</dd>
                </div>
              )}
              {h.total_spend !== undefined && (
                <div>
                  <dt className="text-brand-muted">Spend base</dt>
                  <dd className="font-semibold text-brand-ink">{formatCr(Number(h.total_spend), { currency })}</dd>
                </div>
              )}
            </dl>

            {run.status === 'failed' && (
              <p className="text-[11px] text-red-700">
                {Object.values(run.errors || {})[0] ||
                  (run.validation as { blocking_errors?: { message: string }[] })?.blocking_errors?.[0]?.message ||
                  'Run failed.'}
              </p>
            )}

            <div className="flex items-center gap-1.5 mt-auto pt-1 text-xs">
              <button
                type="button"
                onClick={() => onOpen(run)}
                className="px-2 py-1 rounded hover:bg-brand-surface-muted text-brand-ink"
              >
                Open
              </button>
              <button
                type="button"
                onClick={() => onBranch(run)}
                className="px-2 py-1 rounded hover:bg-brand-surface-muted text-brand-ink"
              >
                Branch
              </button>
              <button
                type="button"
                onClick={() => onChain(run)}
                className="px-2 py-1 rounded hover:bg-brand-surface-muted text-brand-ink"
              >
                Chain
              </button>
              <button
                type="button"
                onClick={() => onToggleCompare(run.run_id)}
                className={`px-2 py-1 rounded ${inCompare ? 'bg-green-50 text-brand-primary' : 'hover:bg-brand-surface-muted text-brand-ink'}`}
              >
                {inCompare ? 'Comparing' : 'Compare'}
              </button>
              <button
                type="button"
                onClick={() => onDelete(run)}
                className="px-2 py-1 rounded hover:bg-red-50 text-error ml-auto"
              >
                Delete
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
};
