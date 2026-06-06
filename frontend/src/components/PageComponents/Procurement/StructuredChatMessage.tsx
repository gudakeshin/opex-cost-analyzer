import React from 'react';
import { ConfidenceBadge } from '../../Trust/ConfidenceBadge';
import { AnalysisTraceBlock } from './AnalysisTraceBlock';
import { ChatInsightBlock } from './ChatInsightBlock';
import { DynamicCharts } from './DynamicCharts';
import { ProbeQuestionsBlock } from './ProbeQuestionsBlock';
import { ThinkingBlock } from './ThinkingBlock';
import { Markdown } from '../../Common/Markdown';
import { artefactLinks, renderChatMarkdown } from '../../../utils/chatMarkdown';
import { filterProbeNextOptions, mergeLiveSpendIntoSnapshot, shouldShowSpendInsightBlock } from '../../../utils/analysisInsights';
import type { AnalysisInsightSnapshot, ChatMessage } from '../../../types';

interface StructuredChatMessageProps {
  message: ChatMessage;
  onOptionClick?: (text: string) => void;
  onOpenProbes?: () => void;
  answeredProbeFamilies?: Set<string>;
  currency?: string;
  liveSnapshot?: AnalysisInsightSnapshot | null;
}

function AssistantAvatar() {
  return (
    <span
      className="w-8 h-8 rounded-full bg-black flex items-center justify-center shrink-0 text-[10px] font-bold text-white"
      aria-hidden
    >
      AI
    </span>
  );
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function AdvisorySections({ sections }: { sections: Record<string, unknown> }) {
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
    const fallback = Object.entries(sections).filter(([, v]) => v != null && v !== '');
    if (fallback.length === 0) return null;
    return (
      <div className="mt-3 space-y-2 border-t border-brand-border pt-2">
        {fallback.map(([key, val]) => (
          <div key={key}>
            <p className="text-xs font-bold uppercase text-brand-muted">{key.replace(/_/g, ' ')}</p>
            <p className="text-xs mt-0.5 opacity-90">
              {typeof val === 'string' ? val : JSON.stringify(val, null, 0).slice(0, 400)}
            </p>
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
          <p className="text-xs mt-0.5 leading-relaxed">{renderChatMarkdown(takeaway)}</p>
        </div>
      )}
      {smeQualification && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">SME qualification</p>
          <p className="text-xs mt-0.5 leading-relaxed">{renderChatMarkdown(smeQualification)}</p>
        </div>
      )}
      {categoryFocus && (
        <div>
          <p className="text-xs font-bold uppercase text-brand-muted">Category focus</p>
          <p className="text-xs mt-0.5 leading-relaxed">{renderChatMarkdown(categoryFocus)}</p>
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
                <li key={String(row.lever_name ?? i)} className="border-l-2 border-deloitte-green pl-2">
                  <span className="font-semibold">{String(row.lever_name ?? 'Lever')}</span>
                  {row.what_changes ? (
                    <p className="text-brand-muted mt-0.5">{String(row.what_changes)}</p>
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

export const StructuredChatMessage: React.FC<StructuredChatMessageProps> = ({
  message,
  onOptionClick,
  onOpenProbes,
  answeredProbeFamilies,
  currency,
  liveSnapshot,
}) => {
  const isUser = message.role === 'user';
  const sections = message.advisory_sections;
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
              <span className="text-[10px] uppercase font-bold text-amber-700">Degraded</span>
            )}
          </div>
        )}
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
        ) : (
          <Markdown className="text-sm leading-relaxed">{message.content}</Markdown>
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

        {!isUser && sections && typeof sections === 'object' && (
          <AdvisorySections sections={sections} />
        )}

        {!isUser && urls.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {urls.map((url) => (
              <a
                key={url}
                href={url.startsWith('/') ? url : url}
                className="text-xs text-deloitte-green underline underline-offset-2"
                target="_blank"
                rel="noopener noreferrer"
              >
                {url.includes('chart') ? 'Open chart' : 'Open export'}
              </a>
            ))}
          </div>
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
