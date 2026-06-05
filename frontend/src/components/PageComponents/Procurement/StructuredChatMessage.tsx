import React from 'react';
import { ConfidenceBadge } from '../../Trust/ConfidenceBadge';
import { AnalysisTraceBlock } from './AnalysisTraceBlock';
import { ChatInsightBlock } from './ChatInsightBlock';
import { ProbeQuestionsBlock } from './ProbeQuestionsBlock';
import { ThinkingBlock } from './ThinkingBlock';
import { artefactLinks, renderChatMarkdown } from '../../../utils/chatMarkdown';
import type { ChatMessage } from '../../../types';

interface StructuredChatMessageProps {
  message: ChatMessage;
  onOptionClick?: (text: string) => void;
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
}) => {
  const isUser = message.role === 'user';
  const sections = message.advisory_sections;
  const urls = artefactLinks(message.artefacts);

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
        <p className="text-sm whitespace-pre-wrap leading-relaxed">
          {isUser ? message.content : renderChatMarkdown(message.content)}
        </p>

        {!isUser && message.thinking && (
          <ThinkingBlock thinking={message.thinking} />
        )}

        {!isUser && message.analysis_trace && message.analysis_trace.length > 0 && (
          <AnalysisTraceBlock steps={message.analysis_trace} />
        )}

        {!isUser && message.insight_snapshot && (
          <ChatInsightBlock
            snapshot={message.insight_snapshot}
            showPeerSavings={message.show_peer_savings}
          />
        )}

        {!isUser &&
          message.insight_snapshot &&
          (message.insight_snapshot.sme_qualification?.probe_count ?? 0) +
            (message.insight_snapshot.sme_qualification?.insufficient_count ?? 0) >
            0 && (
            <ProbeQuestionsBlock
              snapshot={message.insight_snapshot}
              currency={message.insight_snapshot.reporting_currency}
              onAnswer={onOptionClick}
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

        {!isUser && message.next_options && message.next_options.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {message.next_options.map((opt) => (
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
        )}
      </div>
    </div>
  );
};
