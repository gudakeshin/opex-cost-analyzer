import React from 'react';
import { CollapsibleDetail } from '../../Common/CollapsibleDetail';

interface ImportPreviewPanelProps {
  result: Record<string, unknown>;
}

export const ImportPreviewPanel: React.FC<ImportPreviewPanelProps> = ({ result }) => {
  const valid = Boolean(result.valid);
  const packs = (result.packs ?? {}) as Record<
    string,
    { components?: string[]; errors?: string[]; payloads?: Record<string, unknown> | null }
  >;
  const errors = (result.errors ?? []) as string[];

  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center gap-2">
        <span
          className={`text-xs px-2 py-0.5 rounded font-medium ${
            valid ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
          }`}
        >
          {valid ? 'Import valid' : 'Import has issues'}
        </span>
        {result.dry_run === true && <span className="text-xs text-brand-muted">Dry run</span>}
      </div>

      {Object.entries(packs).map(([packId, packResult]) => (
        <div key={packId} className="border border-brand-border rounded-lg p-3 space-y-2">
          <p className="font-medium text-brand-ink">{packId}</p>
          {(packResult.components?.length ?? 0) > 0 && (
            <div className="flex flex-wrap gap-1">
              {packResult.components!.map((comp) => (
                <span
                  key={comp}
                  className="text-[11px] px-1.5 py-0.5 rounded bg-brand-surface-muted text-brand-muted uppercase"
                >
                  {comp}
                </span>
              ))}
            </div>
          )}
          {(packResult.errors?.length ?? 0) > 0 && (
            <ul className="text-xs text-red-700 space-y-1">
              {packResult.errors!.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          )}
        </div>
      ))}

      {errors.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Global errors</h4>
          <ul className="text-xs text-red-700 space-y-1">
            {errors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </section>
      )}

      <RawJsonCollapse data={result} />
    </div>
  );
};

function RawJsonCollapse({ data }: { data: Record<string, unknown> }) {
  return (
    <CollapsibleDetail summary="Raw JSON" summaryClassName="text-xs text-brand-muted">
      <pre className="text-xs overflow-auto max-h-48 bg-brand-surface-muted p-2 rounded">
        {JSON.stringify(data, null, 2)}
      </pre>
    </CollapsibleDetail>
  );
}
