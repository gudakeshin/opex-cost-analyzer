import React from 'react';
import { CollapsibleOverflow } from './CollapsibleOverflow';

export interface StatStripItem {
  id: string;
  label: string;
  value: string;
  detail?: string;
  highlight?: boolean;
  warning?: boolean;
}

interface CompactStatStripProps {
  items: StatStripItem[];
  className?: string;
}

export const CompactStatStrip: React.FC<CompactStatStripProps> = ({ items, className = '' }) => {
  if (!items.length) return null;

  return (
    <CollapsibleOverflow maxLines={2} className={className}>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className={`inline-flex min-w-[7rem] max-w-full flex-col rounded-lg border px-2.5 py-1.5 ${
              item.warning
                ? 'border-amber-300 bg-amber-50/60'
                : item.highlight
                  ? 'border-deloitte-green/35 bg-emerald-50/40'
                  : 'border-brand-border bg-brand-surface-muted/80'
            }`}
          >
            <span className="text-[10px] font-semibold uppercase tracking-wide text-brand-muted">
              {item.label}
            </span>
            <span
              className={`text-sm font-semibold tabular-nums leading-tight truncate ${
                item.highlight ? 'text-brand-navy' : 'text-brand-ink'
              }`}
              title={item.value}
            >
              {item.value}
            </span>
            {item.detail && (
              <span className="text-[10px] text-brand-muted leading-snug truncate" title={item.detail}>
                {item.detail}
              </span>
            )}
          </div>
        ))}
      </div>
    </CollapsibleOverflow>
  );
};
