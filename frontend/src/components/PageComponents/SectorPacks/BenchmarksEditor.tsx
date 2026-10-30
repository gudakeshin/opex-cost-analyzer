import React from 'react';
import type { BenchmarkCategoryDraftRow, BenchmarksDraft } from '../../../types/sectorPack';
import { BENCHMARK_CONFIDENCE_OPTIONS } from '../../../types/sectorPack';
import { CollapsiblePanel } from '../../Common/CollapsibleDetail';
import { EditableTable } from './EditableTable';

interface BenchmarksEditorProps {
  draft: BenchmarksDraft;
  onChange: (draft: BenchmarksDraft) => void;
}

export const BenchmarksEditor: React.FC<BenchmarksEditorProps> = ({ draft, onChange }) => (
  <div className="space-y-6">
    <CollapsiblePanel
      title="Pack metadata"
      summary={`${draft.sector} · v${draft.version} · ${draft.confidence_overall || 'no confidence label'}`}
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
        {(['sector', 'version', 'vintage_date', 'confidence_overall'] as const).map((key) => (
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
          <span className="text-xs text-brand-muted">Methodology</span>
          <textarea
            className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm min-h-[4rem]"
            value={draft.source_metadata.methodology}
            onChange={(e) =>
              onChange({
                ...draft,
                source_metadata: { ...draft.source_metadata, methodology: e.target.value },
              })
            }
          />
        </label>
        <label className="block">
          <span className="text-xs text-brand-muted">Sample size</span>
          <input
            className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm"
            value={draft.source_metadata.sample_size}
            onChange={(e) =>
              onChange({
                ...draft,
                source_metadata: { ...draft.source_metadata, sample_size: e.target.value },
              })
            }
          />
        </label>
      </div>
    </CollapsiblePanel>

    <section>
      <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Category benchmarks</h3>
      <EditableTable<BenchmarkCategoryDraftRow>
        columns={[
          { key: 'category_id', header: 'Category', minWidth: '10rem' },
          { key: 'P25', header: 'P25', type: 'number' },
          { key: 'P50', header: 'P50', type: 'number' },
          { key: 'P75', header: 'P75', type: 'number' },
          { key: 'P90', header: 'P90', type: 'number' },
          { key: 'unit', header: 'Unit', minWidth: '8rem' },
          {
            key: 'confidence',
            header: 'Confidence',
            type: 'select',
            options: BENCHMARK_CONFIDENCE_OPTIONS,
            minWidth: '10rem',
          },
          { key: 'source_note', header: 'Source note', type: 'textarea', minWidth: '14rem' },
        ]}
        rows={draft.categories}
        onChange={(categories) => onChange({ ...draft, categories })}
        newRow={() => ({
          category_id: '',
          unit: '% of revenue',
          confidence: 'public_disclosure',
        })}
        rowKey={(row) => row.category_id || String(Math.random())}
      />
    </section>
  </div>
);
