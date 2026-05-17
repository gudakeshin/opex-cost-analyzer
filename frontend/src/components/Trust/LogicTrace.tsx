import React from 'react';
import type { ProgressStep } from '../../types';

interface LogicTraceProps {
  steps?: ProgressStep[];
  runId?: string;
  degradedMode?: boolean;
}

export const LogicTrace: React.FC<LogicTraceProps> = ({ steps, runId, degradedMode }) => (
  <div className="space-y-3">
    {runId && (
      <p className="text-xs text-brand-muted font-mono">
        Run <span className="text-brand-ink">{runId.slice(0, 12)}…</span>
      </p>
    )}
    {degradedMode && (
      <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
        Degraded mode — some skills used fallback heuristics.
      </p>
    )}
    {!steps?.length ? (
      <p className="text-sm text-brand-muted">No execution trace for this turn yet.</p>
    ) : (
      <ol className="space-y-2">
        {steps.map((step, i) => (
          <li
            key={`${step.phase}-${i}`}
            className="text-sm border-l-4 border-brand-navy pl-3 py-1"
          >
            <span className="text-xs font-bold uppercase text-brand-navy">{step.phase}</span>
            <p className="text-brand-ink mt-0.5">{step.message || step.status}</p>
          </li>
        ))}
      </ol>
    )}
  </div>
);
