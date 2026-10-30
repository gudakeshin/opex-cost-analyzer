import React, { useMemo } from 'react';
import { Card } from '../../Common/Card';

interface RunTracePanelProps {
  output: string;
  skillName?: string;
}

export const RunTracePanel: React.FC<RunTracePanelProps> = ({ output, skillName }) => {
  const parsed = useMemo(() => {
    try {
      return JSON.parse(output) as Record<string, unknown>;
    } catch {
      return null;
    }
  }, [output]);

  const statusRaw = String(parsed?.status ?? '').toLowerCase();
  const pass =
    statusRaw === 'ok' ||
    statusRaw === 'pass' ||
    parsed?.success === true;
  const skipped = statusRaw === 'skipped';
  const hasError = parsed?.error != null;

  const outputKeys = useMemo(() => {
    const keys = parsed?.output_keys;
    if (Array.isArray(keys)) return keys.map(String);
    const out = parsed?.output;
    if (out && typeof out === 'object') return Object.keys(out as object);
    return [];
  }, [parsed]);

  const statusLabel = hasError ? 'FAIL' : pass ? 'PASS' : skipped ? 'SKIPPED' : 'COMPLETE';

  return (
    <Card title="Run trace" className="h-full flex flex-col">
      <dl className="text-sm space-y-2 mb-4 font-sans">
        <div className="flex justify-between gap-4">
          <dt className="text-brand-muted">Skill</dt>
          <dd className="text-brand-ink font-medium">{skillName || '—'}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-brand-muted">Status</dt>
          <dd
            className={
              hasError
                ? 'text-red-600 font-semibold'
                : pass
                  ? 'text-brand-green font-semibold'
                  : skipped
                    ? 'text-amber-700 font-semibold'
                    : 'text-brand-ink font-medium'
            }
          >
            {statusLabel}
          </dd>
        </div>
        {parsed?.degraded_reason != null && (
          <div className="flex justify-between gap-4">
            <dt className="text-brand-muted">Degraded</dt>
            <dd className="text-amber-700 text-right text-xs">{String(parsed.degraded_reason)}</dd>
          </div>
        )}
        {outputKeys.length > 0 && (
          <div>
            <dt className="text-brand-muted mb-1">Output keys</dt>
            <dd className="flex flex-wrap gap-1">
              {outputKeys.map((k) => (
                <span key={k} className="text-[11px] px-1.5 py-0.5 rounded bg-brand-surface-muted text-brand-ink">
                  {k}
                </span>
              ))}
            </dd>
          </div>
        )}
      </dl>
      <pre className="flex-1 p-3 bg-brand-surface-muted rounded-lg text-xs overflow-auto font-mono border border-brand-border max-h-64 text-brand-ink">
        {output || 'Run a test to see trace output.'}
      </pre>
    </Card>
  );
};
