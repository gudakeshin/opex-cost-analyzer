import React, { useState } from 'react';

interface ThinkingBlockProps {
  thinking: string;
}

export const ThinkingBlock: React.FC<ThinkingBlockProps> = ({ thinking }) => {
  const [open, setOpen] = useState(false);

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
          <pre className="text-[11px] text-slate-600 font-mono whitespace-pre-wrap leading-relaxed break-words">
            {thinking}
          </pre>
        </div>
      )}
    </div>
  );
};
