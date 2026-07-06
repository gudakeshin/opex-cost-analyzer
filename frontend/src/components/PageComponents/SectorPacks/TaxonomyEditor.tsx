import React from 'react';
import type { TaxonomyDraft, TaxonomyCategoryRow, TaxonomyOverrideRow } from '../../../types/sectorPack';
import { EditableTable } from './EditableTable';

interface TaxonomyEditorProps {
  draft: TaxonomyDraft;
  onChange: (draft: TaxonomyDraft) => void;
}

export const TaxonomyEditor: React.FC<TaxonomyEditorProps> = ({ draft, onChange }) => (
  <div className="space-y-6">
    <label className="block text-sm">
      <span className="text-xs text-brand-muted">Base taxonomy version</span>
      <input
        className="w-full max-w-xs mt-0.5 border border-brand-border rounded px-2 py-1 text-sm"
        value={draft.base_taxonomy_version}
        onChange={(e) => onChange({ ...draft, base_taxonomy_version: e.target.value })}
      />
    </label>

    <section>
      <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Additional categories</h3>
      <EditableTable<TaxonomyCategoryRow>
        columns={[
          { key: 'category_id', header: 'Category ID', minWidth: '10rem' },
          { key: 'category_name', header: 'Name', minWidth: '12rem' },
          { key: 'gl_prefix', header: 'GL prefix' },
          { key: 'cost_nature', header: 'Cost nature' },
        ]}
        rows={draft.additional_categories}
        onChange={(additional_categories) => onChange({ ...draft, additional_categories })}
        newRow={() => ({ category_id: '', category_name: '' })}
        rowKey={(row) => String(row.category_id || Math.random())}
      />
    </section>

    <section>
      <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Overrides</h3>
      <EditableTable<TaxonomyOverrideRow>
        columns={[
          { key: 'category_id', header: 'Category ID', minWidth: '10rem' },
          { key: 'category_name', header: 'Display name', minWidth: '12rem' },
          { key: 'brsr_principle', header: 'BRSR principle' },
        ]}
        rows={draft.overrides}
        onChange={(overrides) => onChange({ ...draft, overrides })}
        newRow={() => ({ category_id: '', category_name: '' })}
        rowKey={(row) => String(row.category_id || Math.random())}
      />
    </section>
  </div>
);
