import React from 'react';
import type { ProgressStep } from '../../types';
import { NarrativeProvenanceBanner, narrativeModeFromMetadata } from './NarrativeProvenanceBanner';

interface LogicTraceProps {
  steps?: ProgressStep[];
  runId?: string;
  degradedMode?: boolean;
  fallbackReasons?: Record<string, unknown>;
  responseMetadata?: Record<string, unknown>;
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

function synthesisDegradationDetail(reasons?: Record<string, unknown>): string | null {
  const advisory = String(reasons?.llm_advisory ?? '').trim();
  if (!advisory) return null;
  if (advisory === 'provider_billing') {
    return 'LLM narrative skipped — API credits exhausted; deterministic narrative was used.';
  }
  if (advisory === 'provider_auth') {
    return 'LLM narrative skipped — API authentication failed; deterministic narrative was used.';
  }
  if (advisory === 'provider_rate_limit') {
    return 'LLM narrative skipped — rate limit; deterministic narrative was used.';
  }
  if (advisory === 'token_budget_exceeded') {
    return 'LLM narrative skipped — context too large; deterministic narrative was used.';
  }
  if (advisory === 'synthesis_quality_low') {
    return 'LLM narrative did not pass quality checks; deterministic narrative was used.';
  }
  if (advisory === 'provider_failed' || advisory === 'provider_unavailable') {
    return 'LLM narrative unavailable; deterministic narrative was used.';
  }
  return `LLM narrative skipped (${advisory.replace(/_/g, ' ')}); deterministic narrative was used.`;
}

function degradedDetail(entries: Array<[string, string]>, fallbackReasons?: Record<string, unknown>): string {
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
  responseMetadata,
}) => {
  const skillEntries = skillDegradationEntries(fallbackReasons);
  const narrativeProvenance = narrativeModeFromMetadata(responseMetadata, fallbackReasons);
  const synthesisDetail = synthesisDegradationDetail(fallbackReasons);
  const showDegraded = degradedMode || skillEntries.length > 0 || Boolean(synthesisDetail);

  return (
    <div className="space-y-3">
      {runId && (
        <p className="text-xs text-brand-muted font-mono">
          Run <span className="text-brand-ink">{runId.slice(0, 12)}…</span>
        </p>
      )}
      <NarrativeProvenanceBanner provenance={narrativeProvenance} />
      {showDegraded && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          <span className="font-semibold">Degraded mode</span>
          {' — '}
          {synthesisDetail ?? degradedDetail(skillEntries, fallbackReasons)}
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
