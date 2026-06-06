import React, { useCallback, useId, useLayoutEffect, useRef, useState } from 'react';

const DEFAULT_LINE_PX = 18;

interface CollapsibleOverflowProps {
  children: React.ReactNode;
  maxLines?: number;
  linePx?: number;
  className?: string;
  contentClassName?: string;
  expandLabel?: string;
  collapseLabel?: string;
}

export const CollapsibleOverflow: React.FC<CollapsibleOverflowProps> = ({
  children,
  maxLines = 2,
  linePx = DEFAULT_LINE_PX,
  className = '',
  contentClassName = '',
  expandLabel = 'Show more',
  collapseLabel = 'Show less',
}) => {
  const contentRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const contentId = useId();
  const collapsedMaxHeight = maxLines * linePx;

  const measure = useCallback(() => {
    const el = contentRef.current;
    if (!el) return;
    const previousMaxHeight = el.style.maxHeight;
    el.style.maxHeight = 'none';
    const fullHeight = el.scrollHeight;
    el.style.maxHeight = previousMaxHeight;
    setOverflows(fullHeight > collapsedMaxHeight + 1);
  }, [collapsedMaxHeight]);

  useLayoutEffect(() => {
    measure();
    const el = contentRef.current;
    if (!el) return undefined;

    const observer = new ResizeObserver(() => measure());
    observer.observe(el);
    return () => observer.disconnect();
  }, [measure, children]);

  return (
    <div className={className}>
      <div
        id={contentId}
        ref={contentRef}
        className={`relative ${contentClassName}`}
        style={
          !expanded && overflows
            ? { maxHeight: collapsedMaxHeight, overflow: 'hidden' }
            : undefined
        }
      >
        {children}
        {!expanded && overflows && (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-t from-white to-transparent"
          />
        )}
      </div>
      {overflows && (
        <button
          type="button"
          className="mt-1.5 text-xs font-semibold text-brand-navy hover:text-deloitte-green"
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? collapseLabel : expandLabel}
        </button>
      )}
    </div>
  );
};
