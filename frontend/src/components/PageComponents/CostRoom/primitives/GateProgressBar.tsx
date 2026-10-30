import React from 'react';
import { GATE2_COMMIT_THRESHOLD_PCT } from '../../../../utils/initiativeHelpers';

interface GateProgressBarProps {
  committedPct: number;
  statusMessage: string;
}

export const GateProgressBar: React.FC<GateProgressBarProps> = ({
  committedPct,
  statusMessage,
}) => (
  <div className="mt-6">
    <div className="flex justify-between items-baseline mb-4">
      <span className="text-xs font-semibold text-[var(--cr-gray)]">Committed to Gate 2</span>
      <span className="cr-mono font-extrabold text-sm">{statusMessage}</span>
    </div>
    <div className="relative h-[9px] bg-[var(--cr-muted-2)] rounded-md overflow-visible">
      <div
        className="h-full rounded-md bg-[var(--cr-navy)] transition-[width] duration-300"
        style={{ width: `${Math.min(100, committedPct)}%` }}
      />
      <div
        className="absolute top-[-4px] bottom-[-4px] w-0.5 bg-[var(--cr-ink)]"
        style={{ left: `${GATE2_COMMIT_THRESHOLD_PCT}%` }}
      >
        <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9.5px] font-bold text-[var(--cr-gray)] whitespace-nowrap">
          Gate 2 · {GATE2_COMMIT_THRESHOLD_PCT}%
        </span>
      </div>
    </div>
  </div>
);
