import React, { useState } from 'react';
import { renderChatMarkdown } from '../../../utils/chatMarkdown';
import type { AnalysisTraceStep } from '../../../types';

interface AnalysisTraceBlockProps {
  steps: AnalysisTraceStep[];
}

const PHASE_LABELS: Record<string, string> = {
  ingest: 'Read data',
  profile: 'Profile',
  context: 'Context',
  benchmark: 'Benchmark',
  root_cause: 'Root cause',
  savings: 'Savings',
  synthesis: 'Synthesis',
};

function phaseLabel(phase: string): string {
  return PHASE_LABELS[phase] || phase.replace(/_/g, ' ');
}

/**
 * Collapsible, readable record of how an analysis was derived — one numbered
 * step per pipeline stage, each citing the source documents it drew on. Backs the
 * "How this analysis was derived" disclosure inside an assistant chat message.
 */
export const AnalysisTraceBlock: React.FC<AnalysisTraceBlockProps> = ({ steps }) => {
  const [open, setOpen] = useState(false);
  if (!steps || steps.length === 0) return null;

  return (
    <div className="mt-3 rounded-lg border border-brand-border bg-brand-surface-muted/60">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <span
          aria-hidden
          className="shrink-0 text-brand-muted transition-transform duration-200"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▸
        </span>
        <span className="text-xs font-semibold uppercase tracking-wide text-brand-muted">
          How this analysis was derived
        </span>
        <span className="ml-auto text-[10px] text-brand-muted">
          {steps.length} step{steps.length === 1 ? '' : 's'}
        </span>
      </button>

      {open && (
        <ol className="space-y-3 px-3 pb-3 pt-1">
          {steps.map((step) => (
            <li
              key={step.step}
              className="border-l-2 border-brand-navy pl-3"
            >
              <div className="flex items-baseline gap-2">
                <span className="text-[10px] font-bold text-brand-navy">
                  {String(step.step).padStart(2, '0')}
                </span>
                <span className="text-[10px] font-semibold uppercase tracking-wide text-brand-muted">
                  {phaseLabel(step.phase)}
                </span>
              </div>
              <p className="mt-0.5 text-sm font-semibold text-brand-ink leading-snug">
                {step.title}
              </p>
              <p className="mt-0.5 text-xs text-brand-muted leading-relaxed">
                {renderChatMarkdown(step.detail)}
              </p>
              {step.source_documents.length > 0 && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1">
                  <span className="text-[10px] uppercase tracking-wide text-brand-muted">
                    Source:
                  </span>
                  {step.source_documents.map((doc) => (
                    <span
                      key={doc}
                      className="rounded bg-white border border-brand-border px-1.5 py-0.5 text-[10px] font-mono text-brand-ink"
                      title={doc}
                    >
                      {doc}
                    </span>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
};
