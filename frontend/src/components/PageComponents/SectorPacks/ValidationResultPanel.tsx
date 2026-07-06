import React from 'react';
import { CollapsibleDetail } from '../../Common/CollapsibleDetail';

interface ValidationResultPanelProps {
  result: Record<string, unknown>;
}

function formatCheckName(name: string): string {
  return name.replace(/_/g, ' ');
}

export const ValidationResultPanel: React.FC<ValidationResultPanelProps> = ({ result }) => {
  const passed = Boolean(result.passed ?? result.valid);
  const checks = (result.checks ?? {}) as Record<string, boolean>;
  const errors = (result.errors ?? []) as string[];
  const regression = (result.regression ?? null) as Record<string, unknown> | null;

  const checkEntries = Object.entries(checks);
  const regressionChecks = regression?.checks ? (regression.checks as Record<string, boolean>) : null;
  const regressionErrors = regression?.errors ? (regression.errors as string[]) : null;

  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center gap-2">
        <span
          className={`text-xs px-2 py-0.5 rounded font-medium ${
            passed ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'
          }`}
        >
          {passed ? 'Passed' : 'Failed'}
        </span>
        {typeof result.pack_id === 'string' && (
          <span className="text-xs text-brand-muted">Pack: {result.pack_id}</span>
        )}
        {typeof result.new_version === 'string' && (
          <span className="text-xs text-brand-muted">New version: {result.new_version}</span>
        )}
      </div>

      {checkEntries.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Checks</h4>
          <ul className="space-y-1 text-xs">
            {checkEntries.map(([name, ok]) => (
              <li key={name} className="flex items-center gap-2">
                <span className={ok ? 'text-emerald-700' : 'text-red-600'}>{ok ? '✓' : '✗'}</span>
                <span className="capitalize">{formatCheckName(name)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {regressionChecks && Object.keys(regressionChecks).length > 0 && (
        <section>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Regression checks</h4>
          <ul className="space-y-1 text-xs">
            {Object.entries(regressionChecks).map(([name, ok]) => (
              <li key={name} className="flex items-center gap-2">
                <span className={ok ? 'text-emerald-700' : 'text-red-600'}>{ok ? '✓' : '✗'}</span>
                <span className="capitalize">{formatCheckName(name)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(errors.length > 0 || (regressionErrors && regressionErrors.length > 0)) && (
        <section>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Errors</h4>
          <ul className="space-y-1 text-xs text-red-700">
            {[...errors, ...(regressionErrors ?? [])].map((err, i) => (
              <li key={i} className="border-l-2 border-red-200 pl-2">
                {err}
              </li>
            ))}
          </ul>
        </section>
      )}

      {Array.isArray(result.locked_engagements) && result.locked_engagements.length > 0 && (
        <section>
          <h4 className="text-xs font-semibold uppercase text-brand-muted mb-2">Locked engagements</h4>
          <p className="text-xs text-brand-muted">
            {(result.locked_engagements as string[]).join(', ')}
          </p>
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
