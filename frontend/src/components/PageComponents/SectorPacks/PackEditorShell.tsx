import React from 'react';
import type { PackEditorDraft, PackEditorTabId } from '../../../types/sectorPack';
import { draftToJson, parseDraftFromJson } from '../../../utils/sectorPackEditors';

interface PackEditorShellProps {
  tab: PackEditorTabId;
  draft: PackEditorDraft;
  onDraftChange: (draft: PackEditorDraft) => void;
  viewMode: 'structured' | 'json';
  onViewModeChange: (mode: 'structured' | 'json') => void;
  jsonText: string;
  onJsonTextChange: (text: string) => void;
  jsonError: string | null;
  onJsonError: (error: string | null) => void;
  children: React.ReactNode;
}

export const PackEditorShell: React.FC<PackEditorShellProps> = ({
  tab,
  draft,
  onDraftChange,
  viewMode,
  onViewModeChange,
  jsonText,
  onJsonTextChange,
  jsonError,
  onJsonError,
  children,
}) => {
  const switchToStructured = () => {
    try {
      const parsed = parseDraftFromJson(tab, jsonText);
      onDraftChange(parsed);
      onJsonError(null);
      onViewModeChange('structured');
    } catch (err) {
      onJsonError(err instanceof Error ? err.message : 'Invalid JSON');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-brand-muted">Edit cells in the table below, or switch to raw JSON.</p>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => onViewModeChange('structured')}
            className={`text-xs px-2 py-1 rounded border ${
              viewMode === 'structured'
                ? 'bg-brand-ink text-white border-brand-ink'
                : 'border-brand-border text-brand-muted'
            }`}
          >
            Table view
          </button>
          <button
            type="button"
            onClick={() => {
              onJsonTextChange(draftToJson(draft));
              onJsonError(null);
              onViewModeChange('json');
            }}
            className={`text-xs px-2 py-1 rounded border ${
              viewMode === 'json'
                ? 'bg-brand-ink text-white border-brand-ink'
                : 'border-brand-border text-brand-muted'
            }`}
          >
            Raw JSON
          </button>
        </div>
      </div>

      {viewMode === 'structured' ? (
        children
      ) : (
        <div className="space-y-2">
          <textarea
            value={jsonText}
            onChange={(e) => {
              onJsonTextChange(e.target.value);
              onJsonError(null);
            }}
            onBlur={() => {
              try {
                parseDraftFromJson(tab, jsonText);
                onJsonError(null);
              } catch (err) {
                onJsonError(err instanceof Error ? err.message : 'Invalid JSON');
              }
            }}
            className="w-full h-[28rem] px-3 py-2 border border-brand-border rounded-lg font-mono text-sm"
            spellCheck={false}
          />
          {jsonError && <p className="text-xs text-red-600">{jsonError}</p>}
          <button
            type="button"
            onClick={switchToStructured}
            className="text-xs px-2.5 py-1 rounded border border-brand-border text-brand-muted hover:bg-brand-surface-muted"
          >
            Apply JSON to table
          </button>
        </div>
      )}
    </div>
  );
};
