import React from 'react';
import { Card } from '../../Common/Card';
import type { AuditLogEntry } from '../../../types';

interface AuditLogPanelProps {
  auditLog: AuditLogEntry[];
  compact?: boolean;
}

export const AuditLogPanel: React.FC<AuditLogPanelProps> = ({ auditLog, compact }) => (
  <Card title={compact ? undefined : 'Audit log'} className="!p-0 border-0 shadow-none bg-transparent">
    {auditLog.length === 0 ? (
      <p className="text-sm text-brand-muted">No audit events yet.</p>
    ) : (
      <ul
        className={`space-y-2 font-mono text-xs ${compact ? 'max-h-64' : 'max-h-96'} overflow-y-auto`}
        aria-live="polite"
      >
        {auditLog.map((e, i) => (
          <li
            key={`${e.ts}-${i}`}
            className="text-brand-ink border-b border-brand-border pb-2 flex gap-2"
          >
            <span className="text-brand-muted shrink-0 w-36 truncate" title={e.ts}>
              {e.ts ? new Date(e.ts).toLocaleString('en-IN') : '—'}
            </span>
            <span className="flex-1">{e.message}</span>
            {e.source && (
              <span className="text-[10px] uppercase text-brand-muted">{e.source}</span>
            )}
          </li>
        ))}
      </ul>
    )}
  </Card>
);
