import React from 'react';
import { Badge } from './Badge';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  sessionId?: string | null;
  phase?: string;
  extra?: React.ReactNode;
  /** Tighter layout for in-toolbar use (e.g. Analysis chat header). */
  compact?: boolean;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  sessionId,
  phase,
  extra,
  compact = false,
}) => {
  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 min-w-0 shrink-0">
        <h1 className="text-lg font-bold font-sans text-brand-ink tracking-tight">{title}</h1>
        {subtitle && (
          <span className="hidden lg:inline text-xs font-sans text-brand-muted border-l border-brand-border pl-2.5">
            {subtitle}
          </span>
        )}
        {sessionId && <Badge tone="success">Session {sessionId.slice(0, 8)}…</Badge>}
        {phase && (
          <span className="text-[10px] uppercase tracking-wider font-semibold text-brand-navy bg-brand-surface-muted px-1.5 py-0.5 rounded">
            {phase}
          </span>
        )}
        {extra}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-bold font-sans text-brand-ink tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm font-sans text-brand-muted mt-1">{subtitle}</p>}
        {(sessionId || phase) && (
          <div className="flex flex-wrap items-center gap-2 mt-2">
            {sessionId && (
              <Badge tone="success">Session {sessionId.slice(0, 8)}…</Badge>
            )}
            {phase && (
              <span className="text-xs uppercase tracking-wider font-semibold text-brand-navy bg-brand-surface-muted px-2 py-1 rounded">
                {phase}
              </span>
            )}
          </div>
        )}
      </div>
      {extra}
    </div>
  );
};
