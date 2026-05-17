import React from 'react';
import { Button } from '../../Common/Button';
import { Card } from '../../Common/Card';
import { Loader } from '../../Common/Loader';
import type { ConflictSummary } from '../../../types';

interface ConflictsPanelProps {
  summary: ConflictSummary | null;
  loading: boolean;
  error: string | null;
  onResolve: () => void;
  resolving?: boolean;
}

export const ConflictsPanel: React.FC<ConflictsPanelProps> = ({
  summary,
  loading,
  error,
  onResolve,
  resolving,
}) => {
  if (loading) return <Loader label="Loading conflicts…" />;
  if (error) {
    return <p className="text-sm text-brand-muted">{error}</p>;
  }
  if (!summary || !summary.total) {
    return (
      <p className="text-sm text-brand-muted">No cross-source conflicts detected for this session.</p>
    );
  }

  const rows = (summary.conflicts ?? []).slice(0, 8);

  return (
    <Card className="!p-4 bg-white border-brand-border space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-brand-ink">Data conflicts</h3>
          <p className="text-xs text-brand-muted mt-1">
            {summary.unresolved ?? 0} unresolved of {summary.total} total
          </p>
        </div>
        {(summary.unresolved ?? 0) > 0 && (
          <Button type="button" variant="secondary" onClick={onResolve} disabled={resolving}>
            {resolving ? 'Resolving…' : 'Auto-resolve'}
          </Button>
        )}
      </div>
      <ul className="space-y-2 text-sm max-h-64 overflow-y-auto">
        {rows.map((c, i) => {
          const type = String(c.conflict_type ?? c.type ?? 'conflict');
          const severity = String(c.severity ?? 'medium');
          return (
            <li
              key={String(c.conflict_id ?? i)}
              className="border-l-4 border-brand-navy pl-3 py-1"
            >
              <span className="text-xs font-bold uppercase text-brand-muted">{severity}</span>
              <p className="font-medium text-brand-ink">{type.replace(/_/g, ' ')}</p>
              {c.description != null && (
                <p className="text-xs text-brand-muted">{String(c.description)}</p>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
};
