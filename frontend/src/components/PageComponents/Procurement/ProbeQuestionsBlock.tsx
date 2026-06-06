import React from 'react';
import {
  collectUnansweredProbeQuestions,
  formatSpendAmount,
} from '../../../utils/analysisInsights';
import type { AnalysisInsightSnapshot } from '../../../types';

interface ProbeQuestionsBlockProps {
  snapshot: AnalysisInsightSnapshot;
  currency: string;
  answeredProbeFamilies?: Set<string>;
  onOpenProbes?: () => void;
}

export const ProbeQuestionsBlock: React.FC<ProbeQuestionsBlockProps> = ({
  snapshot,
  currency,
  answeredProbeFamilies,
  onOpenProbes,
}) => {
  const probes = collectUnansweredProbeQuestions(snapshot, answeredProbeFamilies ?? new Set(), 5);
  if (probes.length === 0) return null;

  const stakeTotal = probes.reduce((sum, p) => sum + (p.saving_at_stake > 0 ? p.saving_at_stake : 0), 0);

  return (
    <div className="mt-3 pt-3 border-t border-brand-border">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2">
        <p className="text-xs text-amber-950 leading-snug">
          <span className="font-semibold">{probes.length} assumption probe{probes.length !== 1 ? 's' : ''}</span>
          {' need your business judgment'}
          {stakeTotal > 0 && (
            <span className="text-amber-800">
              {' '}
              ({formatSpendAmount(stakeTotal, currency)} at stake)
            </span>
          )}
          .
        </p>
        {onOpenProbes && (
          <button
            type="button"
            onClick={onOpenProbes}
            className="shrink-0 text-xs font-medium px-3 py-1.5 rounded-full border border-amber-400 bg-white text-amber-900 hover:bg-amber-100 transition-colors"
          >
            Open probe dialog
          </button>
        )}
      </div>
    </div>
  );
};
