import React, { useEffect, useState } from 'react';
import type { ProgressStep } from '../../../types';

interface RunStatusProps {
  steps?: ProgressStep[];
  onStop: () => void;
}

function formatElapsed(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Live status for a running analysis: elapsed time, step count, latest step, and Stop. */
export const RunStatus: React.FC<RunStatusProps> = ({ steps, onStop }) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, []);

  const latest = steps && steps.length > 0 ? steps[steps.length - 1] : undefined;

  return (
    <div
      role="status"
      aria-live="polite"
      className="mb-2 flex items-center gap-3 rounded-xl border border-brand-border bg-white px-3 py-2 text-xs"
    >
      <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-brand-primary" aria-hidden />
      <span className="min-w-0 flex-1 truncate text-brand-ink">
        {latest ? latest.message : 'Working…'}
      </span>
      <span className="shrink-0 tabular-nums text-brand-muted">
        {steps && steps.length > 0 ? `Step ${steps.length} · ` : ''}
        {formatElapsed(elapsed)}
      </span>
      <button
        type="button"
        onClick={onStop}
        className="shrink-0 rounded-lg border border-brand-border px-2.5 py-1 font-medium text-brand-ink hover:bg-brand-surface-muted"
      >
        Stop
      </button>
    </div>
  );
};
