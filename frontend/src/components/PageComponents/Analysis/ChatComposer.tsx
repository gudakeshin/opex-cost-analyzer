import React, { useRef, useEffect } from 'react';
import { Button } from '../../Common/Button';

interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  loading?: boolean;
  onUploadClick: () => void;
  onAnalyzeClick: () => void;
  onNewSessionClick: () => void;
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  value,
  onChange,
  onSubmit,
  loading,
  onUploadClick,
  onAnalyzeClick,
  onNewSessionClick,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim() && !loading) {
        onSubmit(e as unknown as React.FormEvent);
      }
    }
  };

  return (
    <div className="border-t border-brand-border bg-white/95 backdrop-blur-sm shrink-0">
      <form onSubmit={onSubmit} className="max-w-3xl mx-auto w-full px-4 py-4">
        <div className="rounded-2xl border border-brand-border bg-white shadow-sm focus-within:border-deloitte-green focus-within:ring-2 focus-within:ring-deloitte-green/20 transition-shadow">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about spend, benchmarks, or savings opportunities…"
            disabled={loading}
            className="w-full resize-none bg-transparent px-4 pt-4 pb-2 text-sm text-brand-ink placeholder:text-brand-muted focus:outline-none min-h-[52px] max-h-[160px]"
          />
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 pb-3">
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={onUploadClick}
                disabled={loading}
                className="text-xs px-2.5 py-1.5 rounded-lg text-brand-muted hover:bg-brand-surface-muted hover:text-brand-ink disabled:opacity-50"
              >
                Attach data
              </button>
              <button
                type="button"
                onClick={onAnalyzeClick}
                disabled={loading}
                className="text-xs px-2.5 py-1.5 rounded-lg text-brand-navy hover:bg-brand-surface-muted disabled:opacity-50"
              >
                Run analysis
              </button>
              <button
                type="button"
                onClick={onNewSessionClick}
                disabled={loading}
                className="text-xs px-2.5 py-1.5 rounded-lg text-brand-muted hover:bg-brand-surface-muted disabled:opacity-50"
              >
                New session
              </button>
            </div>
            <Button
              type="submit"
              disabled={loading || !value.trim()}
              className="!rounded-xl !px-5 !py-2 text-sm"
            >
              Send
            </Button>
          </div>
        </div>
        <p className="text-[11px] text-center text-brand-muted mt-2">
          Shift+Enter for new line · Human-in-the-loop OPAR with trust rail
        </p>
      </form>
    </div>
  );
};

