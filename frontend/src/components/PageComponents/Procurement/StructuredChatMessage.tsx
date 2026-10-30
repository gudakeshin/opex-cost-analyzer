import React, { useState } from 'react';
import { ConfidenceBadge } from '../../Trust/ConfidenceBadge';
import { NarrativeProvenanceBanner, narrativeModeFromMetadata } from '../../Trust/NarrativeProvenanceBanner';
import { ProvenanceTakeaway } from './ProvenanceTakeaway';
import { AnalysisTraceBlock } from './AnalysisTraceBlock';
import { ChatInsightBlock } from './ChatInsightBlock';
import { DynamicCharts } from './DynamicCharts';
import { ProbeQuestionsBlock } from './ProbeQuestionsBlock';
import { ThinkingBlock } from './ThinkingBlock';
import { Markdown } from '../../Common/Markdown';
import { AssistantMessageBody } from './AssistantMessageBody';
import { artefactLinks } from '../../../utils/chatMarkdown';
import { filterProbeNextOptions, mergeLiveSpendIntoSnapshot, shouldShowSpendInsightBlock } from '../../../utils/analysisInsights';
import { ADVISORY_HANDLED_KEYS } from '../../../utils/provenance';
import type { AnalysisInsightSnapshot, ChatMessage, SuggestedOutput } from '../../../types';
import { apiPost, getApiErrorMessage } from '../../../hooks/useApi';

interface StructuredChatMessageProps {
  message: ChatMessage;
  onOptionClick?: (text: string) => void;
  onOpenProbes?: () => void;
  onExportError?: (message: string) => void;
  answeredProbeFamilies?: Set<string>;
  currency?: string;
  liveSnapshot?: AnalysisInsightSnapshot | null;
  sessionId?: string;
  engagementId?: string;
}

function AssistantAvatar() {
  return (
    <span
      className="w-8 h-8 rounded-full bg-black flex items-center justify-center shrink-0 text-[11px] font-bold text-white"
      aria-hidden
    >
      AI
    </span>
  );
}

function hasSynthesisSkipReason(reasons?: Record<string, unknown>): boolean {
  const advisory = String(reasons?.llm_advisory ?? '').trim();
  const chat = String(reasons?.chat_synthesis ?? '').trim();
  return Boolean(advisory || chat);
}

function llmFallbackDetail(reasons?: Record<string, unknown>): string {
  const advisory = String(reasons?.llm_advisory ?? '').trim();
  if (advisory === 'token_budget_exceeded') {
    return 'The analysis context was too large for live LLM synthesis, so a deterministic summary was used instead.';
  }
  if (advisory === 'synthesis_quality_low') {
    return 'The LLM response did not meet quality checks, so a deterministic summary was used instead.';
  }
  if (advisory === 'provider_unavailable' || advisory === 'provider_failed') {
    return (
      'Live LLM narrative synthesis did not complete. A deterministic, data-backed narrative was used instead.'
    );
  }
  if (advisory === 'llm_budget_exceeded') {
    return "LLM narrative skipped — this engagement's LLM spend cap has been reached. Deterministic narrative composed from skill outputs.";
  }
  if (advisory === 'provider_billing') {
    return 'LLM narrative skipped — API credits exhausted. Deterministic narrative composed from skill outputs.';
  }
  if (advisory === 'provider_auth') {
    return 'LLM narrative skipped — API authentication failed. Deterministic narrative composed from skill outputs.';
  }
  const chat = String(reasons?.chat_synthesis ?? '').trim();
  if (chat === 'provider_failed') {
    return (
      'Chat LLM synthesis failed. Use Claude Sonnet 4.6 (Gemini prepay credits may be depleted) ' +
      'or retry after confirming API keys.'
    );
  }
  return 'Using deterministic answers from cached spend data. Check API keys, credits, and model selection for richer responses.';
}

function LlmOfflineBanner({ reasons }: { reasons?: Record<string, unknown> }) {
  return (
    <div
      className="mb-3 rounded-lg border border-amber-300/80 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-950"
      role="status"
    >
      <span className="font-semibold">LLM synthesis skipped</span>
      {' — '}
      {llmFallbackDetail(reasons)}
    </div>
  );
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function renderAdvisoryFallbackValue(val: unknown): React.ReactNode {
  if (typeof val === 'string') return <Markdown className="text-xs leading-relaxed">{val}</Markdown>;
  if (Array.isArray(val) && val.every((x) => typeof x === 'string')) {
    return (
      <ul className="text-xs mt-0.5 list-disc list-inside space-y-0.5">
        {(val as string[]).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    );
  }
  return <p className="text-xs text-brand-muted mt-0.5">Structured data available — see Provenance tab.</p>;
}

function AdvisorySections({
  sections,
  engagementId,
  turnId,
}: {
  sections: Record<string, unknown>;
  engagementId?: string;
  turnId?: string;
}) {
  const takeaway = String(sections.executive_takeaway ?? '').trim();
  const smeQualification = String(sections.sme_qualification_narrative ?? '').trim();
  const categoryFocus = String(sections.category_focus_section ?? '').trim();
  const quickWins = Array.isArray(sections.quick_wins_from_data)
    ? (sections.quick_wins_from_data as unknown[]).map(String).filter(Boolean)
    : [];
  const callouts = Array.isArray(sections.executive_callouts)
    ? (sections.executive_callouts as unknown[]).map(String).filter(Boolean)
    : [];
  const levers = Array.isArray(sections.business_levers) ? sections.business_levers : [];
  const actions = Array.isArray(sections.priority_actions_30_60_90)
    ? sections.priority_actions_30_60_90
    : [];

  const hasTyped =
    takeaway ||
    smeQualification ||
    categoryFocus ||
    quickWins.length > 0 ||
    callouts.length > 0 ||
    levers.length > 0 ||
    actions.length > 0;

  if (!hasTyped) {
    const fallback = Object.entries(sections).filter(
      ([key, v]) => !ADVISORY_HANDLED_KEYS.has(key) && v != null && v !== '',
    );
    if (fallback.length === 0) return null;
    return (
      <div className="mt-3 space-y-2 border-t border-brand-border pt-2">
        {fallback.map(([key, val]) => (
          <div key={key}>
            <p className="text-xs font-bold uppercase text-brand-muted">{key.replace(/_/g, ' ')}</p>
            {renderAdvisoryFallbackValue(val)}
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-3 border-t border-brand-border pt-2">
      {takeaway && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">Executive takeaway</p>
          <ProvenanceTakeaway text={takeaway} engagementId={engagementId} turnId={turnId} />
        </div>
      )}
      {smeQualification && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">SME qualification</p>
          <Markdown className="text-xs leading-relaxed">{smeQualification}</Markdown>
        </div>
      )}
      {categoryFocus && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">Category focus</p>
          <Markdown className="text-xs leading-relaxed">{categoryFocus}</Markdown>
        </div>
      )}
      {quickWins.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">Quick wins</p>
          <ul className="text-xs mt-0.5 list-disc list-inside space-y-0.5">
            {quickWins.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {callouts.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">Callouts</p>
          <ul className="text-xs mt-0.5 list-disc list-inside space-y-0.5">
            {callouts.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      {levers.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">Business levers</p>
          <ul className="text-xs mt-1 space-y-2">
            {levers.slice(0, 4).map((item, i) => {
              const row = asRecord(item);
              if (!row) return null;
              return (
                <li key={`${i}-${String(row.lever_name ?? 'lever')}`} className="border-l-2 border-deloitte-green pl-2">
                  <span className="font-semibold">{String(row.lever_name ?? 'Lever')}</span>
                  {row.what_changes ? (
                    <p className="text-brand-muted mt-0.5">{String(row.what_changes)}</p>
                  ) : null}
                  {row.so_what ? (
                    <p className="text-brand-ink mt-1 font-medium">
                      <span className="text-brand-muted font-normal">So what: </span>
                      {String(row.so_what)}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {actions.length > 0 && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">30 / 60 / 90 day actions</p>
          <ul className="text-xs mt-1 space-y-1.5">
            {actions.slice(0, 5).map((item, i) => {
              const row = asRecord(item);
              if (!row) return null;
              return (
                <li key={i}>
                  <span className="font-semibold text-brand-navy">{String(row.timeline ?? '')}</span>
                  {' — '}
                  {String(row.action ?? '')}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function SuggestedOutputButtons({
  outputs,
  sessionId,
  onExportError,
}: {
  outputs: SuggestedOutput[];
  sessionId?: string;
  onExportError?: (message: string) => void;
}) {
  const [exportState, setExportState] = useState<Record<string, 'idle' | 'pending' | 'failed'>>({});

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {outputs.map((cta) => {
        const key = `${cta.skill}-${cta.endpoint}`;
        const state = exportState[key] ?? 'idle';
        return (
          <button
            key={key}
            type="button"
            disabled={state === 'pending'}
            onClick={async () => {
              const ep = cta.endpoint.includes('{session_id}')
                ? cta.endpoint.replace('{session_id}', sessionId || '')
                : cta.endpoint;
              setExportState((s) => ({ ...s, [key]: 'pending' }));
              try {
                const res = await apiPost<{ export_url?: string; exports?: { docx?: string; pptx?: string } }>(ep, {});
                const url = String(res.export_url || res.exports?.docx || res.exports?.pptx || '');
                if (url) {
                  window.open(url.startsWith('/') ? url : url, '_blank');
                  setExportState((s) => ({ ...s, [key]: 'idle' }));
                } else {
                  setExportState((s) => ({ ...s, [key]: 'failed' }));
                  onExportError?.(`Export for "${cta.label}" returned no download URL.`);
                }
              } catch (err) {
                setExportState((s) => ({ ...s, [key]: 'failed' }));
                onExportError?.(getApiErrorMessage(err));
              }
            }}
            className={`text-xs px-3 py-1.5 rounded-full border ${
              state === 'failed'
                ? 'border-red-400 text-red-700 hover:bg-red-50'
                : 'border-deloitte-green text-brand-primary hover:bg-emerald-50'
            } disabled:opacity-60`}
          >
            {state === 'pending' ? 'Exporting…' : state === 'failed' ? `${cta.label} — retry` : cta.label}
          </button>
        );
      })}
    </div>
  );
}

export const StructuredChatMessage: React.FC<StructuredChatMessageProps> = ({
  message,
  onOptionClick,
  onOpenProbes,
  onExportError,
  answeredProbeFamilies,
  currency,
  liveSnapshot,
  sessionId,
  engagementId,
}) => {
  const isUser = message.role === 'user';
  const sections = message.advisory_sections;
  const presentation = message.presentation;
  const hasPresentationBlocks = Boolean(presentation?.blocks && presentation.blocks.length > 0);
  const urls = artefactLinks(message.artefacts);
  const spendSnapshot = mergeLiveSpendIntoSnapshot(message.insight_snapshot, liveSnapshot ?? null);
  const probeSnapshot = spendSnapshot ?? message.insight_snapshot ?? liveSnapshot;

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {!isUser && <AssistantAvatar />}
      <div
        className={`max-w-[85%] min-w-0 ${
          isUser
            ? 'rounded-2xl rounded-tr-md bg-black text-white px-4 py-3'
            : 'rounded-2xl rounded-tl-md bg-white border border-brand-border text-brand-ink px-4 py-3 shadow-sm'
        }`}
      >
        {!isUser && (
          <div className="flex items-center gap-2 mb-2">
            <ConfidenceBadge signals={message.quality_signals} compact />
            {message.degraded_mode && (
              <span className="text-[11px] uppercase font-bold text-amber-700">Degraded</span>
            )}
            {message.used_llm_synthesis === false && (
              <span className="text-[11px] uppercase font-bold text-amber-700">Offline</span>
            )}
            {message.response_metadata?.narrative_mode === 'deterministic' && (
              <span
                className="text-[11px] uppercase font-bold text-slate-600 border border-slate-300 rounded px-1.5 py-0.5"
                title="Narrative composed from skill outputs — see Sources & confidence → Provenance"
              >
                Composed from data
              </span>
            )}
          </div>
        )}
        {!isUser && message.used_llm_synthesis === false && hasSynthesisSkipReason(message.fallback_reasons) && (
          <LlmOfflineBanner reasons={message.fallback_reasons} />
        )}
        {!isUser && (
          <NarrativeProvenanceBanner
            provenance={narrativeModeFromMetadata(message.response_metadata, message.fallback_reasons)}
            className="mb-3"
          />
        )}
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : hasPresentationBlocks && presentation ? (
          <AssistantMessageBody presentation={presentation} currency={currency} />
        ) : (
          <Markdown className="text-sm leading-relaxed">{message.content}</Markdown>
        )}

        {!isUser && (message.quality_signals?.unverified_figures?.length ?? 0) > 0 && (
          <p
            className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900"
            role="note"
          >
            <span className="font-semibold">Check these figures:</span>{' '}
            {message.quality_signals!.unverified_figures!.join(', ')} could not be matched to the analysis outputs. They
            may be derived values, so verify before quoting.
          </p>
        )}

        {!isUser && message.thinking && (
          <ThinkingBlock thinking={message.thinking} />
        )}

        {!isUser && message.analysis_trace && message.analysis_trace.length > 0 && (
          <AnalysisTraceBlock steps={message.analysis_trace} />
        )}

        {!isUser && spendSnapshot && shouldShowSpendInsightBlock(spendSnapshot, message.show_peer_savings) && (
          <ChatInsightBlock
            snapshot={spendSnapshot}
            showPeerSavings={message.show_peer_savings}
            suppressCharts={!!(message.charts && message.charts.length > 0)}
          />
        )}

        {!isUser && message.charts && message.charts.length > 0 && (
          <DynamicCharts
            charts={message.charts}
            currency={spendSnapshot?.reporting_currency ?? message.insight_snapshot?.reporting_currency ?? currency ?? 'INR'}
          />
        )}

        {!isUser && probeSnapshot && (
            <ProbeQuestionsBlock
              snapshot={probeSnapshot}
              currency={probeSnapshot.reporting_currency}
              answeredProbeFamilies={answeredProbeFamilies}
              onOpenProbes={onOpenProbes}
            />
          )}

        {!isUser && !hasPresentationBlocks && sections && typeof sections === 'object' && (
          <AdvisorySections
            sections={sections}
            engagementId={engagementId}
            turnId={message.run_id ?? sessionId}
          />
        )}

        {!isUser && urls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {urls.map((url) => (
              <a
                key={url}
                href={url.startsWith('/') ? url : url}
                className="text-xs text-brand-primary underline underline-offset-2"
                target="_blank"
                rel="noopener noreferrer"
              >
                {url.includes('chart') ? 'Open chart' : 'Open export'}
              </a>
            ))}
          </div>
        )}

        {!isUser && message.suggested_outputs && message.suggested_outputs.length > 0 && (
          <SuggestedOutputButtons
            outputs={message.suggested_outputs}
            sessionId={sessionId}
            onExportError={onExportError}
          />
        )}

        {!isUser && message.next_options && message.next_options.length > 0 && (() => {
          const options = probeSnapshot
            ? filterProbeNextOptions(message.next_options, probeSnapshot, answeredProbeFamilies)
            : message.next_options;
          if (options.length === 0) return null;
          return (
          <div className="flex flex-wrap gap-2 mt-3">
            {options.map((opt) => (
              <button
                key={opt.label}
                type="button"
                onClick={() => onOptionClick?.(opt.message)}
                className="text-xs px-3 py-1.5 rounded-full border border-brand-border text-brand-navy hover:bg-brand-surface-muted"
              >
                {opt.label}
              </button>
            ))}
          </div>
          );
        })()}
      </div>
    </div>
  );
};
