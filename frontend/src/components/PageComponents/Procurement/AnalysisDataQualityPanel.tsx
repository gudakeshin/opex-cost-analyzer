import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import { Loader } from '../../Common/Loader';
import { getApiErrorMessage } from '../../../hooks/useApi';
import { useConflictsQuery } from '../../../api/hooks/useCostRoomQueries';
import { costRoomKeys } from '../../../api/queryKeys';
import {
  anomalyRecommendation,
  extractAnomalyFlags,
  type AnomalyFlag,
} from '../../../utils/analysisInsights';
import {
  conflictSeverityBadge,
  conflictSeverityStyle,
  fallbackConflictDescription,
  fallbackConflictTitle,
  fallbackRecommendation,
} from '../../../utils/conflictGuidance';
import type { DataConflict, SessionResponse } from '../../../types';

interface AnalysisDataQualityPanelProps {
  analysis: SessionResponse | null;
  currency?: string;
}

export const AnalysisDataQualityPanel: React.FC<AnalysisDataQualityPanelProps> = ({
  analysis,
  currency = 'INR',
}) => {
  const queryClient = useQueryClient();
  const sessionId = analysis?.session_id ?? null;
  const conflictsQuery = useConflictsQuery(sessionId, true);
  const conflicts = conflictsQuery.data ?? null;
  const loading = conflictsQuery.isLoading;
  const error = conflictsQuery.isError ? getApiErrorMessage(conflictsQuery.error) : null;
  const [showAllAnomalies, setShowAllAnomalies] = useState(false);

  const allAnomalies = useMemo(
    () => extractAnomalyFlags(analysis?.skill_outputs as Record<string, unknown> | undefined, 50),
    [analysis?.skill_outputs],
  );
  const anomalies = showAllAnomalies ? allAnomalies : allAnomalies.slice(0, 5);

  useEffect(() => {
    if (sessionId && analysis?.skill_outputs) {
      queryClient.invalidateQueries({ queryKey: costRoomKeys.conflicts(sessionId) });
    }
  }, [sessionId, analysis?.skill_outputs, queryClient]);

  const openConflicts = (conflicts?.conflicts ?? []).filter((c) => !c.resolved);
  const totalItems = openConflicts.length + allAnomalies.length;

  if (!sessionId && allAnomalies.length === 0) return null;
  if (loading && totalItems === 0) return <Loader label="Checking data quality…" />;
  if (!loading && totalItems === 0 && !error) return null;

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <FactVsInferenceLabel kind="inference" />
          <p className="text-xs font-semibold uppercase text-brand-muted">
            Data quality ({totalItems})
          </p>
        </div>
        {openConflicts.length > 0 && (
          <Link
            to="/cost-room"
            className="text-xs font-semibold text-brand-navy hover:text-brand-primary"
          >
            Resolve in Cost Room →
          </Link>
        )}
      </div>

      {error && (
        <p className="text-xs text-brand-muted mb-2">
          Cross-source conflicts unavailable ({error}). Anomaly flags below are still shown.
        </p>
      )}

      <ul className="space-y-3">
        {openConflicts.map((conflict, index) => (
          <ConflictQualityCard key={String(conflict.conflict_id ?? index)} conflict={conflict} />
        ))}
        {anomalies.map((flag) => (
          <AnomalyQualityCard key={flag.category_id} flag={flag} currency={currency} />
        ))}
      </ul>
      {allAnomalies.length > 5 && (
        <button
          type="button"
          className="mt-2 text-xs font-semibold text-brand-navy hover:text-brand-primary"
          onClick={() => setShowAllAnomalies((v) => !v)}
        >
          {showAllAnomalies ? 'Show top 5' : `Show all ${allAnomalies.length} anomalies`}
        </button>
      )}
    </div>
  );
};

function AnomalyQualityCard({ flag, currency }: { flag: AnomalyFlag; currency: string }) {
  const borderColor =
    flag.severity === 'high' ? 'border-l-red-500' : flag.severity === 'medium' ? 'border-l-amber-500' : 'border-l-slate-400';
  return (
    <li
      className={`rounded-lg border border-brand-border border-l-4 ${borderColor} bg-amber-50/40 px-3 py-2.5`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-brand-ink">Spend anomaly · {flag.category_name}</h4>
        <span
          className={`text-[11px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${conflictSeverityBadge(flag.severity)}`}
        >
          {flag.severity}
        </span>
      </div>
      <p className="text-sm text-brand-ink mt-1.5">{anomalyRecommendation(flag, currency)}</p>
    </li>
  );
}

function ConflictQualityCard({ conflict }: { conflict: DataConflict }) {
  const severity = String(conflict.severity ?? 'medium');
  const title = conflict.title ?? fallbackConflictTitle(conflict);
  const description = conflict.description ?? fallbackConflictDescription(conflict);
  const recommendation = conflict.recommendation ?? fallbackRecommendation(conflict);

  return (
    <li
      className={`rounded-lg border border-brand-border border-l-4 px-3 py-2.5 ${conflictSeverityStyle(severity)}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-semibold text-brand-ink">{title}</h4>
        <span
          className={`text-[11px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${conflictSeverityBadge(severity)}`}
        >
          {severity}
        </span>
        <span className="text-[11px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
          cross-source
        </span>
      </div>
      <p className="text-sm text-brand-ink mt-1.5">{description}</p>
      <div className="mt-2 rounded-lg bg-white/80 border border-brand-border/60 px-2.5 py-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-muted">
          Recommended action
        </p>
        <p className="text-xs text-brand-ink mt-1">{recommendation}</p>
      </div>
    </li>
  );
}
