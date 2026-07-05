import React from 'react';
import { Loader } from '../../Common/Loader';
import type { ConflictSummary, DataConflict } from '../../../types';
import {
  conflictSeverityBadge,
  fallbackConflictDescription,
  fallbackConflictTitle,
  fallbackRecommendation,
} from '../../../utils/conflictGuidance';

interface ConflictsPanelProps {
  summary: ConflictSummary | null;
  loading: boolean;
  error: string | null;
  onApplyRecommendation: (conflict: DataConflict) => void;
  onFlagForReview: (conflict: DataConflict) => void;
  onRetry?: () => void;
  actingConflictId?: string | null;
}

function friendlyConflictLoadError(raw: string | null): string {
  const msg = String(raw ?? '').trim();
  if (!msg) return 'The conflicts service is temporarily unavailable.';
  if (/404|not found/i.test(msg)) return 'No conflict data exists for this session yet.';
  if (/401|403|forbidden|unauthorized/i.test(msg)) return 'You do not have access to load conflict data for this session.';
  if (/500|502|503|504|network|fetch/i.test(msg)) return 'The server could not load conflicts. Try again in a moment.';
  if (msg.length > 120) return 'Could not load cross-source conflicts for this session.';
  return msg;
}

function severityRail(severity: string): string {
  if (severity === 'high') return 'bg-[var(--cr-red)]';
  if (severity === 'low') return 'bg-[var(--cr-gray-3)]';
  return 'bg-[var(--cr-amber)]';
}

function ConflictRow({
  conflict,
  acting,
  onApplyRecommendation,
  onFlagForReview,
}: {
  conflict: DataConflict;
  acting: boolean;
  onApplyRecommendation: (conflict: DataConflict) => void;
  onFlagForReview: (conflict: DataConflict) => void;
}) {
  const severity = String(conflict.severity ?? 'medium');
  const title = conflict.title ?? fallbackConflictTitle(conflict);
  const description = conflict.description ?? fallbackConflictDescription(conflict);
  const recommendation = conflict.recommendation ?? fallbackRecommendation(conflict);
  const resolved = Boolean(conflict.resolved);
  const canApply = Boolean(conflict.can_auto_apply) && !resolved;

  return (
    <div className="flex gap-3 px-5 py-3.5 border-b border-[var(--cr-line-2)] last:border-b-0">
      <div className={`w-1 rounded-sm shrink-0 ${severityRail(severity)}`} />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-bold text-sm">{title}</span>
          <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${conflictSeverityBadge(severity)}`}>
            {severity}
          </span>
        </div>
        <p className="text-xs text-[var(--cr-gray)] mt-1">{description}</p>
        <p className="text-xs text-[var(--cr-gray-2)] mt-1">
          <strong className="text-[var(--cr-ink)]">Recommended:</strong> {recommendation}
        </p>
        {!resolved && (
          <div className="flex flex-wrap gap-2 mt-2">
            {canApply && (
              <button
                type="button"
                disabled={acting}
                onClick={() => onApplyRecommendation(conflict)}
                className="text-xs px-2.5 py-1.5 rounded-[var(--cr-r-sm)] bg-[var(--cr-green)] text-white font-semibold disabled:opacity-50"
              >
                {acting ? '…' : conflict.action_label ?? 'Apply recommendation'}
              </button>
            )}
            <button
              type="button"
              disabled={acting}
              onClick={() => onFlagForReview(conflict)}
              className="text-xs px-2.5 py-1.5 rounded-[var(--cr-r-sm)] border border-[var(--cr-line)] bg-white font-semibold disabled:opacity-50"
            >
              Flag for review
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export const ConflictsPanel: React.FC<ConflictsPanelProps> = ({
  summary,
  loading,
  error,
  onApplyRecommendation,
  onFlagForReview,
  onRetry,
  actingConflictId,
}) => {
  if (loading) return <Loader label="Loading conflicts…" />;
  if (error) {
    return (
      <div className="cr-card p-5 border border-amber-200 bg-amber-50/60">
        <p className="text-sm font-semibold text-[var(--cr-ink)]">Could not load data conflicts</p>
        <p className="text-xs text-[var(--cr-gray)] mt-1">{friendlyConflictLoadError(error)}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 text-xs px-3 py-1.5 rounded-[var(--cr-r-sm)] border border-[var(--cr-line)] bg-white font-semibold hover:bg-gray-50"
          >
            Try again
          </button>
        )}
      </div>
    );
  }
  if (!summary || !summary.total) {
    return (
      <div className="cr-card p-5">
        <p className="text-sm text-[var(--cr-gray-2)]">No cross-source conflicts detected for this session.</p>
      </div>
    );
  }

  const rows = summary.conflicts ?? [];
  const unresolved = summary.unresolved ?? 0;

  return (
    <div className="cr-card overflow-hidden">
      <div className="cr-card-h">
        <h2 className="text-sm font-bold inline-flex items-center gap-2">
          Data conflicts
          {unresolved > 0 && (
            <span className="text-[11px] font-bold text-[var(--cr-amber)] bg-[var(--cr-amber-soft)] border border-[#f0dcb0] px-2 py-0.5 rounded-md">
              {unresolved} unresolved
            </span>
          )}
        </h2>
        <span className="text-[11.5px] text-[var(--cr-gray-2)]">Resolve before committing affected pools</span>
      </div>
      <div>
        {rows.map((conflict, i) => (
          <ConflictRow
            key={String(conflict.conflict_id ?? i)}
            conflict={conflict}
            acting={actingConflictId === conflict.conflict_id}
            onApplyRecommendation={onApplyRecommendation}
            onFlagForReview={onFlagForReview}
          />
        ))}
      </div>
    </div>
  );
};
