import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { MetricTile } from '../../Common/MetricTile';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import type { SessionResponse } from '../../../types';

interface InsightCardsProps {
  analysis: SessionResponse | null;
  onOpenCostRoom?: () => void | Promise<void>;
}

export const InsightCards: React.FC<InsightCardsProps> = ({ analysis, onOpenCostRoom }) => {
  const [showRaw, setShowRaw] = useState(false);

  const skillNames = useMemo(() => {
    if (!analysis?.skill_outputs) return [];
    return Object.keys(analysis.skill_outputs as object);
  }, [analysis]);

  const spendProfiler = analysis?.skill_outputs
    ? (analysis.skill_outputs as Record<string, unknown>)['spend-profiler']
    : null;
  const totalSpend =
    spendProfiler && typeof spendProfiler === 'object' && 'total_spend' in spendProfiler
      ? String((spendProfiler as Record<string, unknown>).total_spend)
      : null;

  if (!analysis) {
    return (
      <p className="text-sm text-brand-muted">Results appear after upload and analysis.</p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3">
        <MetricTile
          label="Company"
          value={String(analysis.company_name || '—')}
          change={String(analysis.industry || 'Industry not set')}
        />
        {totalSpend && (
          <MetricTile label="Total spend (signal)" value={totalSpend} highlight />
        )}
        <MetricTile
          label="Skills executed"
          value={String(skillNames.length)}
          change={skillNames.length ? skillNames.slice(0, 3).join(', ') : 'Run analysis to populate'}
        />
      </div>

      {skillNames.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FactVsInferenceLabel kind="fact" />
            <p className="text-xs font-semibold uppercase text-brand-muted">Skill outputs</p>
          </div>
          <ul className="text-sm text-brand-ink space-y-1 list-disc list-inside">
            {skillNames.map((k) => (
              <li key={k}>{k}</li>
            ))}
          </ul>
        </div>
      )}

      <Link
        to="/cost-room"
        onClick={() => void onOpenCostRoom?.()}
        className="inline-flex text-sm font-semibold text-brand-navy hover:text-deloitte-green"
      >
        Open Cost Room →
      </Link>

      <button
        type="button"
        className="text-xs text-brand-muted underline"
        onClick={() => setShowRaw((v) => !v)}
      >
        {showRaw ? 'Hide' : 'Show'} developer JSON
      </button>
      {showRaw && (
        <pre className="p-3 bg-brand-surface-muted rounded text-xs overflow-auto max-h-48 font-mono border border-brand-border">
          {JSON.stringify(analysis, null, 2)}
        </pre>
      )}
    </div>
  );
};
