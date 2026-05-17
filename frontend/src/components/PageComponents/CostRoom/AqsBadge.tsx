import React from 'react';
import { GATE2_AQS_THRESHOLD } from '../../../utils/initiativeHelpers';

interface AqsBadgeProps {
  score?: number;
  showLabel?: boolean;
}

export const AqsBadge: React.FC<AqsBadgeProps> = ({ score, showLabel }) => {
  if (score == null || !Number.isFinite(score)) {
    return <span className="text-brand-muted text-sm">—</span>;
  }
  const pct = score <= 1 ? score * 100 : score;
  const normalized = pct / 100;
  let tone = 'bg-amber-50 text-amber-900 border-amber-300';
  let label = 'Gate pass';
  if (normalized >= 0.8) {
    tone = 'bg-green-50 text-green-900 border-green-300';
    label = 'Strong';
  } else if (normalized < GATE2_AQS_THRESHOLD) {
    tone = 'bg-red-50 text-red-900 border-red-300';
    label = 'Blocked';
  }
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-mono tabular-nums ${tone}`}
      title={`Assumption Quality Score. Gate-2 requires ≥${(GATE2_AQS_THRESHOLD * 100).toFixed(0)}%.`}
    >
      {pct.toFixed(0)}%
      {showLabel && <span className="font-sans font-normal opacity-80">· {label}</span>}
    </span>
  );
};
