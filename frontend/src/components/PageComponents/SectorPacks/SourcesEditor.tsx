import React from 'react';
import type { FreeSourceRow, LicensedSourceStubRow, SourcesDraft } from '../../../types/sectorPack';
import { EditableTable } from './EditableTable';

interface SourcesEditorProps {
  draft: SourcesDraft;
  onChange: (draft: SourcesDraft) => void;
}

export const SourcesEditor: React.FC<SourcesEditorProps> = ({ draft, onChange }) => (
  <div className="space-y-6">
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
      {(['source_validation_date', 'sector'] as const).map((key) => (
        <label key={key} className="block">
          <span className="text-xs text-brand-muted">{key.replace(/_/g, ' ')}</span>
          <input
            className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm"
            value={draft[key]}
            onChange={(e) => onChange({ ...draft, [key]: e.target.value })}
          />
        </label>
      ))}
      <label className="block md:col-span-2">
        <span className="text-xs text-brand-muted">Validation note</span>
        <textarea
          className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm min-h-[3rem]"
          value={draft.source_validation_note}
          onChange={(e) => onChange({ ...draft, source_validation_note: e.target.value })}
        />
      </label>
    </div>

    <section>
      <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Free / public sources</h3>
      <EditableTable<FreeSourceRow>
        columns={[
          { key: 'id', header: 'ID', minWidth: '10rem' },
          { key: 'name', header: 'Name', minWidth: '12rem' },
          { key: 'url', header: 'URL', minWidth: '14rem' },
          { key: 'sample_metric', header: 'Sample metric', type: 'textarea', minWidth: '14rem' },
          { key: 'refresh_frequency', header: 'Refresh' },
        ]}
        rows={draft.free_sources}
        onChange={(free_sources) => onChange({ ...draft, free_sources })}
        newRow={() => ({ id: '', name: '' })}
        rowKey={(row) => String(row.id || row.name || Math.random())}
      />
    </section>

    <section>
      <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Licensed source stubs</h3>
      <EditableTable<LicensedSourceStubRow>
        columns={[
          { key: 'id', header: 'ID', minWidth: '10rem' },
          { key: 'name', header: 'Name', minWidth: '12rem' },
          { key: 'credential_env', header: 'Credential env', minWidth: '12rem' },
        ]}
        rows={draft.licensed_sources_stubs}
        onChange={(licensed_sources_stubs) => onChange({ ...draft, licensed_sources_stubs })}
        newRow={() => ({ id: '', name: '' })}
        rowKey={(row) => String(row.id || row.name || Math.random())}
      />
    </section>
  </div>
);
