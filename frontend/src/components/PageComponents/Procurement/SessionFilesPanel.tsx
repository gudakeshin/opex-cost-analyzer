import React from 'react';
import { AutoCollapsibleList } from '../../Common/AutoCollapsibleList';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import {
  fileUploadStatus,
  formatFileSize,
  type ManifestFileEntry,
} from '../../../utils/sessionFiles';

interface SessionFilesPanelProps {
  files: ManifestFileEntry[];
}

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  spend: { label: 'Spend-ready', className: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
  document: { label: 'Context doc', className: 'bg-slate-50 text-slate-700 border-slate-200' },
  unsupported: { label: 'Not for analysis', className: 'bg-amber-50 text-amber-900 border-amber-200' },
};

export const SessionFilesPanel: React.FC<SessionFilesPanelProps> = ({ files }) => {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <FactVsInferenceLabel kind="fact" />
        <p className="text-xs font-semibold uppercase text-brand-muted">Session data</p>
      </div>
      {files.length === 0 ? (
        <p className="text-sm text-brand-muted">No files uploaded yet. Use Attach data to add spend files.</p>
      ) : (
        <AutoCollapsibleList
          items={files}
          getKey={(f) => f.name || 'unknown'}
          listClassName="space-y-2"
          renderItem={(f) => {
            const name = f.name || 'Unknown file';
            const status = fileUploadStatus(name);
            const chip = STATUS_STYLES[status];
            return (
              <div className="text-sm border border-brand-border rounded-lg px-3 py-2 bg-brand-surface-muted">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium text-brand-ink break-all">{name}</span>
                  <span
                    className={`shrink-0 text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded border ${chip.className}`}
                  >
                    {chip.label}
                  </span>
                </div>
                <p className="text-xs text-brand-muted mt-1">{formatFileSize(f.size_bytes)}</p>
                {status === 'unsupported' && (
                  <p className="text-xs text-amber-800 mt-1">
                    Convert to CSV or XLSX to run full spend analysis.
                  </p>
                )}
                {status === 'spend' && f.schema != null && (
                  <p className="text-xs text-brand-muted mt-0.5">
                    {(() => {
                      const wb = (f.schema as { workbook?: Record<string, unknown> })?.workbook;
                      const selected = wb?.selected_sheet as string | undefined;
                      const count = wb?.sheet_count as number | undefined;
                      if (selected && count && count > 1) {
                        return `Selected sheet: ${selected} (${count} tabs)`;
                      }
                      return 'Schema inferred';
                    })()}
                  </p>
                )}
              </div>
            );
          }}
        />
      )}
    </div>
  );
};
