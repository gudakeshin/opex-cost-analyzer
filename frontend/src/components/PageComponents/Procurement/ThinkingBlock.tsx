import React, { useEffect, useState } from 'react';

interface ThinkingBlockProps {
  thinking: string;
  /** When true, expand automatically and keep open while reasoning streams in. */
  live?: boolean;
}

const LIVE_PLACEHOLDER =
  'Analyzing your question and gathering evidence…';

export const ThinkingBlock: React.FC<ThinkingBlockProps> = ({ thinking, live = false }) => {
  const [open, setOpen] = useState(live);
  const hasContent = thinking.trim().length > 0;
  const displayText = hasContent ? thinking : live ? LIVE_PLACEHOLDER : thinking;

  useEffect(() => {
    if (live) setOpen(true);
  }, [live, thinking]);

  return (
    <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-100 transition-colors"
      >
        <span className="text-slate-400 text-xs select-none">◈</span>
        <span className="text-[10px] uppercase font-semibold text-slate-500 flex-1 tracking-wide">
          Model reasoning
        </span>
        <span className="text-[10px] text-slate-400 select-none">
          {open ? 'Hide ▲' : 'Show ▼'}
        </span>
      </button>
      {open && (
        <div className="border-t border-slate-200 px-3 py-2 max-h-96 overflow-y-auto">
          <pre
            className={`text-[11px] font-mono whitespace-pre-wrap leading-relaxed break-words ${
              live && !hasContent ? 'text-slate-400 animate-pulse' : 'text-slate-600'
            }`}
          >
            {displayText}
            {live && hasContent && (
              <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-slate-400 animate-pulse align-middle" aria-hidden />
            )}
          </pre>
        </div>
      )}
    </div>
  );
};
