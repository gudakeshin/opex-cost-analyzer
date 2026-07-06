import React, { useState } from 'react';

interface StringListEditorProps {
  label?: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
}

export const StringListEditor: React.FC<StringListEditorProps> = ({
  label,
  values,
  onChange,
  placeholder = 'Add item',
}) => {
  const [draft, setDraft] = useState('');

  const addValue = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onChange([...values, trimmed]);
    setDraft('');
  };

  return (
    <div className="space-y-2">
      {label && <p className="text-xs font-medium text-brand-muted">{label}</p>}
      <div className="flex flex-wrap gap-1">
        {values.map((value, index) => (
          <span
            key={`${value}-${index}`}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-brand-surface-muted text-xs text-brand-ink"
          >
            <span className="max-w-xs truncate">{value}</span>
            <button
              type="button"
              className="text-brand-muted hover:text-red-600"
              onClick={() => onChange(values.filter((_, i) => i !== index))}
              aria-label={`Remove ${value}`}
            >
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          className="flex-1 px-2 py-1 border border-brand-border rounded text-xs"
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              addValue();
            }
          }}
        />
        <button
          type="button"
          onClick={addValue}
          className="text-xs px-2 py-1 rounded border border-brand-border text-brand-muted hover:bg-brand-surface-muted"
        >
          Add
        </button>
      </div>
    </div>
  );
};
