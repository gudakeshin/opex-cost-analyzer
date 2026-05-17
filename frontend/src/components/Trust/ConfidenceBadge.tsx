import React from 'react';
import type { QualitySignals } from '../../types';

interface ConfidenceBadgeProps {
  signals?: QualitySignals | null;
  aqs?: number;
  compact?: boolean;
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({ signals, aqs, compact }) => {
  const faith = signals?.faithfulness_score;
  const rel = signals?.relevance_score;
  const grounding = signals?.grounding_coverage;

  let label = 'Model output';
  let tone = 'bg-brand-green/15 text-brand-green border-brand-green/30';

  if (aqs != null) {
    if (aqs >= 0.65) {
      label = `AQS ${aqs.toFixed(2)}`;
      tone = 'bg-brand-navy/10 text-brand-navy border-brand-navy/20';
    } else {
      label = `AQS ${aqs.toFixed(2)} · review`;
      tone = 'bg-amber-50 text-amber-800 border-amber-200';
    }
  } else if (faith != null) {
    const pct = Math.round(faith * 100);
    label = compact ? `${pct}%` : `Faithfulness ${pct}%`;
    if (faith < 0.6) tone = 'bg-amber-50 text-amber-800 border-amber-200';
  } else if (rel != null) {
    label = compact ? `${Math.round(rel * 100)}%` : `Relevance ${Math.round(rel * 100)}%`;
  }

  return (
    <span
      className={`inline-flex items-center text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded border ${tone}`}
      title={
        grounding != null
          ? `Grounding coverage: ${Math.round(grounding * 100)}%`
          : 'Confidence indicator for AI-assisted content'
      }
    >
      {label}
    </span>
  );
};
