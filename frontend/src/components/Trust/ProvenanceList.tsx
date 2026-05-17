import React from 'react';
import { FactVsInferenceLabel } from '../Common/FactVsInferenceLabel';

interface ProvenanceListProps {
  sources?: Array<{ label: string; detail?: string; kind?: 'fact' | 'inference' }>;
  narrativeTag?: Record<string, unknown> | null;
}

export const ProvenanceList: React.FC<ProvenanceListProps> = ({ sources, narrativeTag }) => {
  const tagEntries = narrativeTag
    ? Object.entries(narrativeTag).filter(([, v]) => v != null && v !== '')
    : [];

  return (
    <div className="space-y-3 text-sm">
      {sources?.length ? (
        <ul className="space-y-2">
          {sources.map((s, i) => (
            <li key={i} className="flex items-start gap-2">
              <FactVsInferenceLabel kind={s.kind ?? 'inference'} />
              <div>
                <p className="font-medium text-brand-ink">{s.label}</p>
                {s.detail && <p className="text-xs text-brand-muted">{s.detail}</p>}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-brand-muted">No source attribution recorded for this view.</p>
      )}
      {tagEntries.length > 0 && (
        <div className="pt-2 border-t border-brand-border">
          <p className="text-xs font-semibold uppercase text-brand-muted mb-2">Narrative tag</p>
          <dl className="grid grid-cols-1 gap-1 text-xs font-mono">
            {tagEntries.map(([k, v]) => (
              <div key={k} className="flex gap-2">
                <dt className="text-brand-muted">{k}</dt>
                <dd className="text-brand-ink truncate">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
};
