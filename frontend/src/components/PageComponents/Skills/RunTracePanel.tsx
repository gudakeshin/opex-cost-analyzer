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

  const pass = parsed?.status === 'ok' || parsed?.success === true;
  const hasError = parsed?.error != null;

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
                  : 'text-brand-ink font-medium'
            }
          >
            {hasError ? 'FAIL' : pass ? 'PASS' : 'COMPLETE'}
          </dd>
        </div>
      </dl>
      <pre className="flex-1 p-3 bg-brand-surface-muted rounded-lg text-xs overflow-auto font-mono border border-brand-border max-h-64 text-brand-ink">
        {output || 'Run a test to see trace output.'}
      </pre>
    </Card>
  );
};
