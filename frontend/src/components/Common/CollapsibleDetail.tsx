import React, { useId, useState } from 'react';

interface CollapsibleDetailProps {
  summary: string;
  children: React.ReactNode;
  className?: string;
  summaryClassName?: string;
  detailClassName?: string;
}

export const CollapsibleDetail: React.FC<CollapsibleDetailProps> = ({
  summary,
  children,
  className = '',
  summaryClassName = '',
  detailClassName = '',
}) => {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <div className={className}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={contentId}
        className={`group flex w-full items-start gap-2 text-left ${summaryClassName}`}
      >
        <span
          aria-hidden
          className="mt-0.5 shrink-0 text-brand-muted transition-transform duration-200 group-hover:text-brand-ink"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▸
        </span>
        <span className="text-sm text-brand-ink leading-snug">{summary}</span>
      </button>
      {open && (
        <div
          id={contentId}
          className={`mt-2 ml-5 space-y-2 border-l-2 border-brand-border pl-3 ${detailClassName}`}
        >
          {children}
        </div>
      )}
    </div>
  );
};

interface CollapsiblePanelProps {
  title: string;
  summary: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

export const CollapsiblePanel: React.FC<CollapsiblePanelProps> = ({
  title,
  summary,
  children,
  defaultOpen = false,
}) => {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className="mb-4 rounded-lg border border-brand-border bg-brand-surface-muted/70">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={contentId}
        className="flex w-full items-start gap-3 p-4 text-left"
      >
        <span
          aria-hidden
          className="mt-0.5 shrink-0 text-brand-muted"
          style={{ transform: open ? 'rotate(90deg)' : 'rotate(0deg)' }}
        >
          ▸
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-brand-ink">{title}</p>
          {!open && (
            <p className="mt-1 text-sm text-brand-muted leading-relaxed line-clamp-2">{summary}</p>
          )}
        </div>
        <span className="shrink-0 text-xs text-brand-muted pt-0.5">{open ? 'Hide' : 'Details'}</span>
      </button>
      {open && (
        <div id={contentId} className="px-4 pb-4 pt-0 ml-7 space-y-3 border-t border-brand-border/60">
          {children}
        </div>
      )}
    </div>
  );
};
