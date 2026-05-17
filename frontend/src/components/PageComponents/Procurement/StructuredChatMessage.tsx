import React from 'react';
import { ConfidenceBadge } from '../../Trust/ConfidenceBadge';
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

export const StructuredChatMessage: React.FC<StructuredChatMessageProps> = ({
  message,
  onOptionClick,
}) => {
  const isUser = message.role === 'user';
  const sections = message.advisory_sections;
  const sectionEntries =
    sections && typeof sections === 'object'
      ? Object.entries(sections).filter(([, v]) => v != null && v !== '')
      : [];

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
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
        {!isUser && sectionEntries.length > 0 && (
          <div className="mt-3 space-y-2 border-t border-brand-border pt-2">
            {sectionEntries.map(([key, val]) => (
              <div key={key}>
                <p className="text-xs font-bold uppercase text-brand-muted">{key.replace(/_/g, ' ')}</p>
                <p className="text-xs mt-0.5 opacity-90">
                  {typeof val === 'string' ? val : JSON.stringify(val, null, 0).slice(0, 400)}
                </p>
              </div>
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
