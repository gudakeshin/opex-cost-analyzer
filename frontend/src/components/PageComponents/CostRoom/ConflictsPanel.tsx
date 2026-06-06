import React from 'react';
import { Button } from '../../Common/Button';
import { Card } from '../../Common/Card';
import { Loader } from '../../Common/Loader';
import type { ConflictSummary, DataConflict } from '../../../types';
import {
  conflictSeverityBadge,
  conflictSeverityStyle,
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
  actingConflictId?: string | null;
}

function ConflictCard({
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
  const flagged = conflict.user_status === 'flagged_for_review';
  const applied = conflict.user_status === 'applied';
  const canApply = Boolean(conflict.can_auto_apply) && !resolved;
  const needsReview = Boolean(conflict.requires_manual_review) && !resolved;

  return (
    <li
      className={`rounded-lg border border-brand-border border-l-4 px-4 py-3 ${conflictSeverityStyle(severity)}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="font-semibold text-sm text-brand-ink">{title}</h4>
            <span
              className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${conflictSeverityBadge(severity)}`}
            >
              {severity}
            </span>
            {applied && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-green-100 text-green-800">
                Applied
              </span>
            )}
            {flagged && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-200 text-slate-800">
                Flagged for review
              </span>
            )}
            {resolved && !applied && !flagged && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-green-100 text-green-800">
                Resolved
              </span>
            )}
          </div>
          <p className="text-sm text-brand-ink mt-1.5">{description}</p>
        </div>
      </div>

      <div className="mt-3 rounded-lg bg-white/80 border border-brand-border/60 px-3 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
          Recommended action
        </p>
        <p className="text-sm text-brand-ink mt-1">{recommendation}</p>
        {conflict.estimated_spend_impact != null && conflict.estimated_spend_impact > 0 && (
          <p className="text-xs text-brand-muted mt-2">
            Estimated spend base reduction if applied: ₹
            {conflict.estimated_spend_impact.toLocaleString('en-IN', { maximumFractionDigits: 1 })} Cr
          </p>
        )}
      </div>

      {!resolved && (
        <div className="mt-3 flex flex-wrap gap-2">
          {canApply && (
            <Button
              type="button"
              variant="primary"
              className="!text-xs !px-3 !py-1.5"
              loading={acting}
              disabled={acting}
              onClick={() => onApplyRecommendation(conflict)}
            >
              {conflict.action_label ?? 'Apply recommendation'}
            </Button>
          )}
          <Button
            type="button"
            variant={needsReview && !canApply ? 'secondary' : 'ghost'}
            className="!text-xs !px-3 !py-1.5"
            loading={acting}
            disabled={acting}
            onClick={() => onFlagForReview(conflict)}
          >
            Flag for manual review
          </Button>
        </div>
      )}
    </li>
  );
}

export const ConflictsPanel: React.FC<ConflictsPanelProps> = ({
  summary,
  loading,
  error,
  onApplyRecommendation,
  onFlagForReview,
  actingConflictId,
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

  const rows = summary.conflicts ?? [];
  const unresolved = summary.unresolved ?? 0;
  const needsReview = summary.requires_escalation ?? 0;

  return (
    <Card className="!p-4 bg-white border-brand-border space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-brand-ink">Data conflicts</h3>
        <p className="text-xs text-brand-muted mt-1">
          {unresolved} unresolved of {summary.total} total
          {needsReview > 0 ? ` · ${needsReview} need manual review` : ''}
        </p>
        <p className="text-xs text-brand-muted mt-2">
          Each item explains what disagrees across sources and what we recommend. Applying a
          recommendation updates the underlying spend lines and re-profiles the spend base.
          Flagging for review records your decision without changing spend.
        </p>
      </div>

      <ul className="space-y-3">
        {rows.map((conflict, i) => (
          <ConflictCard
            key={String(conflict.conflict_id ?? i)}
            conflict={conflict}
            acting={actingConflictId === conflict.conflict_id}
            onApplyRecommendation={onApplyRecommendation}
            onFlagForReview={onFlagForReview}
          />
        ))}
      </ul>

      {rows.length === 0 && (
        <p className="text-sm text-brand-muted">Conflict details are not available for this session.</p>
      )}
    </Card>
  );
};
