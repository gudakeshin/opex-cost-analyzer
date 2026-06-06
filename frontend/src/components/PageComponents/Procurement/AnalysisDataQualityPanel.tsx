import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import { Loader } from '../../Common/Loader';
import { apiGet, getApiErrorMessage } from '../../../hooks/useApi';
import {
  anomalyRecommendation,
  extractAnomalyFlags,
  formatSpendAmount,
} from '../../../utils/analysisInsights';
import {
  conflictSeverityBadge,
  conflictSeverityStyle,
  fallbackConflictDescription,
  fallbackConflictTitle,
  fallbackRecommendation,
} from '../../../utils/conflictGuidance';
import type { ConflictSummary, DataConflict, SessionResponse } from '../../../types';

interface AnalysisDataQualityPanelProps {
  analysis: SessionResponse | null;
  currency?: string;
}

export const AnalysisDataQualityPanel: React.FC<AnalysisDataQualityPanelProps> = ({
  analysis,
  currency = 'INR',
}) => {
  const sessionId = analysis?.session_id ?? null;
  const [conflicts, setConflicts] = useState<ConflictSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const anomalies = useMemo(
    () => extractAnomalyFlags(analysis?.skill_outputs as Record<string, unknown> | undefined, 50),
    [analysis?.skill_outputs],
  );

  useEffect(() => {
    if (!sessionId) {
      setConflicts(null);
      return;
    }
    setLoading(true);
    setError(null);
    apiGet<ConflictSummary>(`/api/v1/conflicts/${sessionId}`)
      .then(setConflicts)
      .catch((err) => {
        setConflicts(null);
        setError(getApiErrorMessage(err));
      })
      .finally(() => setLoading(false));
  }, [sessionId, analysis?.skill_outputs]);

  const openConflicts = (conflicts?.conflicts ?? []).filter((c) => !c.resolved);
  const totalItems = openConflicts.length + anomalies.length;

  if (!sessionId && anomalies.length === 0) return null;
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
            className="text-xs font-semibold text-brand-navy hover:text-deloitte-green"
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
          <li
            key={flag.category_id}
            className="rounded-lg border border-brand-border border-l-4 border-l-amber-500 bg-amber-50/40 px-3 py-2.5"
          >
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-sm font-semibold text-brand-ink">Spend anomaly · {flag.category_name}</h4>
              <span
                className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${conflictSeverityBadge('medium')}`}
              >
                heuristic
              </span>
            </div>
            <p className="text-sm text-brand-ink mt-1.5">{anomalyRecommendation(flag)}</p>
            <p className="text-xs text-brand-muted mt-1">
              Estimated opportunity if brought to norm:{' '}
              <span className="font-semibold text-brand-ink tabular-nums">
                {formatSpendAmount(flag.estimated_saving_amount, currency)}
              </span>
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
};

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
          className={`text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full ${conflictSeverityBadge(severity)}`}
        >
          {severity}
        </span>
        <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">
          cross-source
        </span>
      </div>
      <p className="text-sm text-brand-ink mt-1.5">{description}</p>
      <div className="mt-2 rounded-lg bg-white/80 border border-brand-border/60 px-2.5 py-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-brand-muted">
          Recommended action
        </p>
        <p className="text-xs text-brand-ink mt-1">{recommendation}</p>
      </div>
    </li>
  );
}
