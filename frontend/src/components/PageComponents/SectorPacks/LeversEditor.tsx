import React from 'react';
import type { LeverRow, LeversDraft } from '../../../types/sectorPack';
import { CollapsibleDetail } from '../../Common/CollapsibleDetail';
import { EditableTable } from './EditableTable';
import { StringListEditor } from './StringListEditor';

interface LeversEditorProps {
  draft: LeversDraft;
  onChange: (draft: LeversDraft) => void;
}

export const LeversEditor: React.FC<LeversEditorProps> = ({ draft, onChange }) => {
  const updateLever = (index: number, patch: Partial<LeverRow>) => {
    const levers = draft.levers.map((row, i) => (i === index ? { ...row, ...patch } : row));
    onChange({ ...draft, levers });
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
        <label className="block">
          <span className="text-xs text-brand-muted">Sector</span>
          <input
            className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm"
            value={draft.sector}
            onChange={(e) => onChange({ ...draft, sector: e.target.value })}
          />
        </label>
        <label className="block">
          <span className="text-xs text-brand-muted">Source type</span>
          <input
            className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm"
            value={draft.source_type}
            onChange={(e) => onChange({ ...draft, source_type: e.target.value })}
          />
        </label>
        <label className="block md:col-span-2">
          <span className="text-xs text-brand-muted">Source verification note</span>
          <textarea
            className="w-full border border-brand-border rounded px-2 py-1 mt-0.5 text-sm min-h-[3rem]"
            value={draft.source_verification_note}
            onChange={(e) => onChange({ ...draft, source_verification_note: e.target.value })}
          />
        </label>
      </div>

      <section>
        <h3 className="text-xs font-semibold uppercase text-brand-muted mb-2">Levers</h3>
        <EditableTable<LeverRow>
          columns={[
            { key: 'lever_id', header: 'Lever ID', minWidth: '12rem' },
            { key: 'lever_name', header: 'Name', minWidth: '12rem' },
            { key: 'p10_pct', header: 'P10 %', type: 'number' },
            { key: 'p50_pct', header: 'P50 %', type: 'number' },
            { key: 'p90_pct', header: 'P90 %', type: 'number' },
            { key: 'implementation_weeks', header: 'Weeks', type: 'number' },
            { key: 'savings_type', header: 'Savings type' },
          ]}
          rows={draft.levers}
          onChange={(levers) => onChange({ ...draft, levers })}
          newRow={() => ({
            lever_id: '',
            lever_name: '',
            category_ids: [],
            industry_sources: [],
            savings_type: 'run_rate',
          })}
          rowKey={(row) => String(row.lever_id || Math.random())}
        />
      </section>

      {draft.levers.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase text-brand-muted">Lever details</h3>
          {draft.levers.map((lever, index) => {
            const id = String(lever.lever_id || `row-${index}`);
            const effort = (lever.effort_weeks ?? {}) as { p10?: number; p50?: number; p90?: number };
            return (
              <div key={id} className="border border-brand-border rounded-lg p-3">
                <CollapsibleDetail
                  summary={`${lever.lever_name || lever.lever_id || `Lever ${index + 1}`} — description, categories, sources`}
                  summaryClassName="text-xs font-medium"
                >
                  <div className="space-y-3 text-xs">
                    <label className="block">
                      <span className="text-brand-muted">Description</span>
                      <textarea
                        className="w-full mt-1 border border-brand-border rounded px-2 py-1 min-h-[4rem]"
                        value={lever.description ?? ''}
                        onChange={(e) => updateLever(index, { description: e.target.value })}
                      />
                    </label>
                    <StringListEditor
                      label="Category IDs"
                      values={lever.category_ids ?? []}
                      onChange={(category_ids) => updateLever(index, { category_ids })}
                      placeholder="e.g. HR"
                    />
                    <StringListEditor
                      label="Industry sources"
                      values={lever.industry_sources ?? []}
                      onChange={(industry_sources) => updateLever(index, { industry_sources })}
                      placeholder="Source citation"
                    />
                    <label className="block">
                      <span className="text-brand-muted">BRSR principle</span>
                      <input
                        className="w-full max-w-xs mt-1 border border-brand-border rounded px-2 py-1"
                        value={String(lever.brsr_principle ?? '')}
                        onChange={(e) => updateLever(index, { brsr_principle: e.target.value })}
                      />
                    </label>
                    <div>
                      <p className="text-brand-muted mb-1">Effort weeks (p10 / p50 / p90)</p>
                      <div className="flex gap-2">
                        {(['p10', 'p50', 'p90'] as const).map((band) => (
                          <input
                            key={band}
                            type="number"
                            className="w-20 border border-brand-border rounded px-2 py-1"
                            placeholder={band}
                            value={effort[band] ?? ''}
                            onChange={(e) =>
                              updateLever(index, {
                                effort_weeks: {
                                  ...effort,
                                  [band]: e.target.value === '' ? undefined : Number(e.target.value),
                                },
                              })
                            }
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                </CollapsibleDetail>
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
};
