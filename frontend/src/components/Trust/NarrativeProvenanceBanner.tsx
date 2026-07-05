import React from 'react';

export interface NarrativeProvenance {
  mode?: string;
  llm_skip_reason?: string | null;
}

function friendlySkipReason(reason?: string | null): string {
  const r = String(reason ?? '').trim();
  if (r === 'provider_billing') return 'API credits exhausted';
  if (r === 'provider_auth') return 'API authentication failed';
  if (r === 'provider_rate_limit') return 'rate limit reached';
  if (r === 'token_budget_exceeded') return 'context too large for LLM synthesis';
  if (r === 'synthesis_quality_low') return 'LLM output did not meet quality checks';
  if (r === 'export_no_llm') return 'export uses deterministic narrative only';
  if (r) return r.replace(/_/g, ' ');
  return 'LLM unavailable';
}

interface NarrativeProvenanceBannerProps {
  provenance?: NarrativeProvenance | null;
  className?: string;
}

export const NarrativeProvenanceBanner: React.FC<NarrativeProvenanceBannerProps> = ({
  provenance,
  className = '',
}) => {
  if (!provenance || provenance.mode !== 'deterministic') return null;
  const detail = friendlySkipReason(provenance.llm_skip_reason);
  return (
    <div
      className={`rounded-lg border border-amber-300/80 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-950 ${className}`}
      role="status"
    >
      <span className="font-semibold">Deterministic narrative</span>
      {` — LLM unavailable: ${detail}.`}
    </div>
  );
};

export function narrativeModeFromMetadata(
  metadata?: Record<string, unknown> | null,
  fallbackReasons?: Record<string, unknown> | null,
): NarrativeProvenance | null {
  const mode = String(metadata?.narrative_mode ?? '').trim();
  if (mode === 'llm') return { mode: 'llm' };
  if (mode === 'deterministic') {
    return {
      mode: 'deterministic',
      llm_skip_reason: String(fallbackReasons?.llm_advisory ?? metadata?.llm_skip_reason ?? ''),
    };
  }
  const skip = String(fallbackReasons?.llm_advisory ?? '').trim();
  if (skip) return { mode: 'deterministic', llm_skip_reason: skip };
  return null;
}
