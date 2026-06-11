import React from 'react';
import type { ProgressStep } from '../../types';

interface LogicTraceProps {
  steps?: ProgressStep[];
  runId?: string;
  degradedMode?: boolean;
  fallbackReasons?: Record<string, unknown>;
}

const SYNTHESIS_KEYS = new Set(['llm_advisory', 'chat_synthesis']);

function skillDegradationEntries(
  reasons?: Record<string, unknown>,
): Array<[string, string]> {
  if (!reasons) return [];
  return Object.entries(reasons)
    .filter(([key]) => !SYNTHESIS_KEYS.has(key))
    .map(([key, value]) => [key, String(value ?? '').trim()] as [string, string])
    .filter(([, value]) => value.length > 0);
}

function degradedDetail(entries: Array<[string, string]>): string {
  if (entries.length === 0) {
    return 'Some analysis skills used deterministic fallback paths instead of full LLM enrichment.';
  }
  if (entries.length === 1) {
    const [skill, reason] = entries[0];
    return `${skill} used a fallback path (${reason.replace(/_/g, ' ')}).`;
  }
  const skills = entries.map(([skill]) => skill).join(', ');
  return `These skills used fallback paths: ${skills}.`;
}

export const LogicTrace: React.FC<LogicTraceProps> = ({
  steps,
  runId,
  degradedMode,
  fallbackReasons,
}) => {
  const skillEntries = skillDegradationEntries(fallbackReasons);
  const showDegraded = degradedMode || skillEntries.length > 0;

  return (
    <div className="space-y-3">
      {runId && (
        <p className="text-xs text-brand-muted font-mono">
          Run <span className="text-brand-ink">{runId.slice(0, 12)}…</span>
        </p>
      )}
      {showDegraded && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          <span className="font-semibold">Degraded mode</span>
          {' — '}
          {degradedDetail(skillEntries)}
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
};
