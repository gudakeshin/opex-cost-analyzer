import React from 'react';
import { Link } from 'react-router-dom';
import type { ExceptionItem } from '../../utils/exceptions';

interface ExceptionInboxProps {
  items: ExceptionItem[];
  onDismiss?: () => void;
  onItemAction?: (item: ExceptionItem) => void;
  compact?: boolean;
}

const severityStyles = {
  critical: 'border-l-red-500 bg-red-50/50',
  high: 'border-l-amber-500 bg-amber-50/50',
  medium: 'border-l-brand-navy bg-brand-surface-muted',
};

const actionLinkClass =
  'inline-block mt-2 text-xs font-semibold text-brand-navy hover:text-brand-green';

export const ExceptionInbox: React.FC<ExceptionInboxProps> = ({
  items,
  onDismiss,
  onItemAction,
  compact,
}) => {
  if (!items.length) return null;

  return (
    <section
      className={`rounded-xl border border-brand-border bg-white overflow-hidden ${
        compact ? '' : 'shadow-sm'
      }`}
      aria-label="Items needing attention"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-brand-border bg-brand-surface-muted">
        <h2 className="text-sm font-semibold text-brand-ink">
          Needs attention
          <span className="ml-2 inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 rounded-full bg-brand-green text-white text-xs">
            {items.length}
          </span>
        </h2>
        {onDismiss && (
          <button type="button" className="text-xs text-brand-muted hover:text-brand-ink" onClick={onDismiss}>
            Dismiss
          </button>
        )}
      </div>
      <ul className={`divide-y divide-brand-border ${compact ? 'max-h-48 overflow-y-auto' : ''}`}>
        {items.slice(0, compact ? 5 : 12).map((item) => (
          <li
            key={item.id}
            className={`px-4 py-3 border-l-4 ${severityStyles[item.severity]}`}
          >
            <p className="font-medium text-sm text-brand-ink">{item.title}</p>
            <p className="text-xs text-brand-muted mt-0.5">{item.detail}</p>
            {item.action && onItemAction ? (
              <button
                type="button"
                className={actionLinkClass}
                onClick={() => onItemAction(item)}
              >
                {item.actionLabel ?? 'Open'} →
              </button>
            ) : item.href ? (
              <Link to={item.href} className={actionLinkClass}>
                {item.actionLabel ?? 'Open'} →
              </Link>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
};
