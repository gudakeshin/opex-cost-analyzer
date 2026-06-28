import React from 'react';

interface TrustFooterProps {
  auditCount: number;
  lastSync: string;
  chainValid?: boolean;
  onOpenAudit?: () => void;
  onExportDeck?: () => void;
  onExportExcel?: () => void;
  deckLoading?: boolean;
  excelLoading?: boolean;
}

export const TrustFooter: React.FC<TrustFooterProps> = ({
  auditCount,
  lastSync,
  chainValid,
  onOpenAudit,
  onExportDeck,
  onExportExcel,
  deckLoading = false,
  excelLoading = false,
}) => (
  <footer className="cr-footer">
    <span className="inline-flex items-center gap-1.5 flex-wrap">
      <span aria-hidden>🛡</span>
      Pool-scoped RBAC ·{' '}
      <button type="button" onClick={onOpenAudit} className="text-[var(--cr-navy)] font-bold hover:underline">
        Audit log: {auditCount.toLocaleString('en-IN')} events
      </button>
      {chainValid !== false && ' · chain verified'}
      {chainValid === false && (
        <span className="text-[var(--cr-red)] font-semibold"> · chain warning</span>
      )}
      {' · '}Last sync: {lastSync}
    </span>
    <div className="flex gap-2">
      <button
        type="button"
        onClick={onExportDeck}
        disabled={deckLoading}
        className="text-xs px-2.5 py-1.5 rounded-[var(--cr-r-sm)] border border-[var(--cr-line)] bg-white hover:bg-[var(--cr-muted)] disabled:opacity-50"
      >
        {deckLoading ? 'Exporting…' : '↓ Export to deck'}
      </button>
      <button
        type="button"
        onClick={onExportExcel}
        disabled={excelLoading}
        className="text-xs px-2.5 py-1.5 rounded-[var(--cr-r-sm)] border border-[var(--cr-line)] bg-white hover:bg-[var(--cr-muted)] disabled:opacity-50"
      >
        {excelLoading ? 'Exporting…' : '↓ Export Excel'}
      </button>
    </div>
  </footer>
);
