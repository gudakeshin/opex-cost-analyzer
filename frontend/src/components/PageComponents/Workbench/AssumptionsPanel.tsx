import React, { useState } from 'react';
import type { WorkbenchAssumptionField } from '../../../types';

interface AssumptionsPanelProps {
  fields: WorkbenchAssumptionField[];
  values: Record<string, string>;
  relevantKeys: Set<string>;
  onChange: (key: string, value: string) => void;
}

export const AssumptionsPanel: React.FC<AssumptionsPanelProps> = ({
  fields,
  values,
  relevantKeys,
  onChange,
}) => {
  const [open, setOpen] = useState(true);
  const editedCount = fields.filter((f) => (values[f.key] ?? '').trim() !== '').length;

  return (
    <div className="border border-brand-border rounded-lg">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-brand-ink"
      >
        <span>
          Assumptions
          {editedCount > 0 && (
            <span className="ml-2 text-xs text-brand-primary">{editedCount} overridden</span>
          )}
        </span>
        <span className="text-brand-muted">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 grid grid-cols-2 gap-2">
          {fields.map((field) => {
            const relevant = relevantKeys.has(field.key);
            const suffix = field.type === 'percent' ? '%' : '';
            return (
              <label key={field.key} className="block text-xs">
                <span className={`block mb-0.5 ${relevant ? 'text-brand-ink font-medium' : 'text-brand-muted'}`}>
                  {field.label}
                  {suffix && <span className="text-brand-muted"> ({suffix})</span>}
                </span>
                <input
                  type={field.type === 'text' ? 'text' : 'number'}
                  value={values[field.key] ?? ''}
                  placeholder={field.default !== undefined ? String(field.default) : 'auto'}
                  onChange={(e) => onChange(field.key, e.target.value)}
                  className="w-full px-2 py-1 rounded border border-brand-border text-sm focus:outline-none focus:ring-1 focus:ring-deloitte-green"
                />
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
};
