import React, { useState } from 'react';

interface SchemaColumn {
  name: string;
  type: string;
}

interface SchemaExplorerProps {
  schema: {
    columns: SchemaColumn[];
    sample_values: Record<string, string[]>;
    views: Record<string, string>;
  };
  onInsert: (text: string) => void;
}

export const SchemaExplorer: React.FC<SchemaExplorerProps> = ({ schema, onInsert }) => {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  return (
    <div className="space-y-3 text-xs">
      <p className="font-medium text-brand-muted">Schema</p>
      <ul className="space-y-1">
        {schema.columns.map((col) => {
          const samples = schema.sample_values[col.name] ?? [];
          const isOpen = Boolean(expanded[col.name]);
          return (
            <li key={col.name} className="rounded border border-brand-border/60">
              <div className="flex items-center gap-1 px-1.5 py-1">
                <button
                  type="button"
                  className="flex-1 text-left font-mono text-brand-ink hover:underline"
                  title={`Insert ${col.name}`}
                  onClick={() => onInsert(col.name)}
                >
                  {col.name}
                </button>
                <span className="rounded bg-brand-surface-elevated px-1 py-0.5 text-[11px] text-brand-muted">
                  {col.type}
                </span>
                {samples.length > 0 && (
                  <button
                    type="button"
                    className="text-brand-muted px-0.5"
                    aria-label={isOpen ? 'Collapse samples' : 'Expand samples'}
                    onClick={() =>
                      setExpanded((prev) => ({ ...prev, [col.name]: !prev[col.name] }))
                    }
                  >
                    {isOpen ? '▾' : '▸'}
                  </button>
                )}
              </div>
              {isOpen && samples.length > 0 && (
                <div className="flex flex-wrap gap-1 border-t border-brand-border/50 px-1.5 py-1.5">
                  {samples.slice(0, 12).map((v) => (
                    <button
                      key={v}
                      type="button"
                      className="rounded border border-brand-border bg-brand-surface px-1.5 py-0.5 font-mono text-[11px] hover:border-brand-primary"
                      title={`Insert ${col.name} = '${v}'`}
                      onClick={() => onInsert(`${col.name} = '${v.replace(/'/g, "''")}'`)}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {Object.keys(schema.views).length > 0 && (
        <div>
          <p className="mb-1 font-medium text-brand-muted">Views</p>
          <ul className="space-y-0.5 font-mono text-brand-ink">
            {Object.keys(schema.views).map((v) => (
              <li key={v}>
                <button
                  type="button"
                  className="hover:underline"
                  onClick={() => onInsert(v)}
                >
                  {v}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
