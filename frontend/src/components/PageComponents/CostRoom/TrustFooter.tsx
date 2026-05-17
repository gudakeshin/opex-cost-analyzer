import React from 'react';

interface TrustFooterProps {
  auditCount: number;
  lastSync: string;
  chainValid?: boolean;
  onOpenAudit?: () => void;
  onExportDeck?: () => void;
  onExportExcel?: () => void;
}

export const TrustFooter: React.FC<TrustFooterProps> = ({
  auditCount,
  lastSync,
  chainValid,
  onOpenAudit,
  onExportDeck,
  onExportExcel,
}) => (
  <footer className="flex flex-wrap items-center justify-between gap-4 pt-6 mt-6 border-t border-brand-border text-xs text-brand-muted">
    <p>
      Pool-scoped RBAC ·{' '}
      <button
        type="button"
        onClick={onOpenAudit}
        className="text-brand-navy font-semibold hover:text-brand-green underline-offset-2 hover:underline"
      >
        Audit log: {auditCount.toLocaleString()} events
      </button>
      {chainValid === false && (
        <span className="ml-2 text-red-600 font-semibold">Chain integrity warning</span>
      )}
      {' · '}Last sync: {lastSync}
    </p>
    <div className="flex gap-2">
      <button
        type="button"
        onClick={onExportDeck}
        className="px-3 py-1.5 rounded-lg border border-brand-border bg-white hover:bg-brand-surface-muted text-brand-ink"
      >
        Export to deck
      </button>
      <button
        type="button"
        onClick={onExportExcel}
        className="px-3 py-1.5 rounded-lg border border-brand-border bg-white hover:bg-brand-surface-muted text-brand-ink"
      >
        Export Excel
      </button>
    </div>
  </footer>
);
