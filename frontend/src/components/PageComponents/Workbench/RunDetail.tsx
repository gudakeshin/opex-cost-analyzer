import React, { useState } from 'react';
import { useDialogA11y } from '../../../hooks/useDialogA11y';
import { Button } from '../../Common/Button';
import { formatCr } from '../../../utils/formatInr';
import { WorkbenchRunCharts } from './WorkbenchRunCharts';
import type { WorkbenchRun } from '../../../types';

interface RunDetailProps {
  run: WorkbenchRun;
  currency: string;
  onClose: () => void;
  onBranch: (run: WorkbenchRun) => void;
  onChain: (run: WorkbenchRun) => void;
  onPromote?: (run: WorkbenchRun) => void;
  promoting?: boolean;
}

function prettyName(name: string): string {
  return name
    .split('-')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

type Tab = 'summary' | 'charts' | 'raw';

export const RunDetail: React.FC<RunDetailProps> = ({
  run,
  currency,
  onClose,
  onBranch,
  onChain,
  onPromote,
  promoting,
}) => {
  const panelRef = useDialogA11y<HTMLDivElement>(true, onClose);
  const [tab, setTab] = useState<Tab>('summary');
  const h = run.headline || {};
  const outputs = Object.keys(run.skill_outputs || {});
  const errored = Object.keys(run.errors || {});

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-detail-title"
        tabIndex={-1}
        className="bg-white h-full w-full max-w-lg overflow-y-auto p-5 shadow-xl outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 id="run-detail-title" className="text-lg font-bold text-brand-ink">{run.name}</h2>
            <p className="text-xs text-brand-muted">
              {run.status} · {run.resolved_skills.length} analyses
              {run.parent_run_id ? ' · branched' : ''}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="text-brand-muted hover:text-brand-ink text-xl">
            ×
          </button>
        </div>

        <div className="flex gap-1 mb-4 border-b border-brand-border">
          {(['summary', 'charts', 'raw'] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-xs font-medium capitalize ${
                tab === t ? 'border-b-2 border-deloitte-green text-brand-ink' : 'text-brand-muted'
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === 'summary' && (
          <>
            <dl className="grid grid-cols-2 gap-2 mb-4">
              {h.savings_mid !== undefined && (
                <Metric label="Savings (mid)" value={formatCr(Number(h.savings_mid), { currency })} />
              )}
              {h.npv !== undefined && <Metric label="NPV" value={formatCr(Number(h.npv), { currency })} />}
              {h.initiative_count !== undefined && <Metric label="Initiatives" value={String(h.initiative_count)} />}
              {h.total_spend !== undefined && (
                <Metric label="Spend base" value={formatCr(Number(h.total_spend), { currency })} />
              )}
            </dl>

            {run.reflect_summary && (
              <p className="text-sm text-brand-muted mb-4 border-l-2 border-deloitte-green pl-3">{run.reflect_summary}</p>
            )}

            {Object.keys(run.overrides || {}).length > 0 && (
              <section className="mb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-brand-muted mb-1">Assumptions</h3>
                <ul className="text-sm text-brand-ink space-y-0.5">
                  {Object.entries(run.overrides).map(([k, v]) => (
                    <li key={k}>
                      <span className="text-brand-muted">{k}:</span> {String(v)}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="mb-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-brand-muted mb-1">
                Analyses ({outputs.length})
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {run.resolved_skills.map((s) => {
                  const ok = outputs.includes(s);
                  const failed = errored.includes(s);
                  return (
                    <span
                      key={s}
                      className={`text-[11px] px-2 py-0.5 rounded-full border ${
                        failed
                          ? 'border-red-200 bg-red-50 text-red-700'
                          : ok
                            ? 'border-green-200 bg-green-50 text-green-800'
                            : 'border-brand-border text-brand-muted'
                      }`}
                    >
                      {prettyName(s)}
                    </span>
                  );
                })}
              </div>
            </section>

            {errored.length > 0 && (
              <section className="mb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-red-700 mb-1">Errors</h3>
                <ul className="text-xs text-red-700 space-y-0.5">
                  {Object.entries(run.errors).map(([k, v]) => (
                    <li key={k}>
                      <span className="font-medium">{prettyName(k)}:</span> {v}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}

        {tab === 'charts' && <WorkbenchRunCharts run={run} currency={currency} />}

        {tab === 'raw' && (
          <pre className="text-[10px] font-mono bg-brand-surface-muted p-2 rounded overflow-auto max-h-96">
            {JSON.stringify(run.skill_outputs, null, 2)}
          </pre>
        )}

        <div className="flex flex-col gap-2 mt-4">
          {run.status === 'complete' &&
            onPromote &&
            Array.isArray((run.skill_outputs?.['savings-modeler'] as Record<string, unknown>)?.initiatives) && (
            <Button variant="primary" onClick={() => onPromote(run)} loading={promoting} className="w-full">
              Promote initiatives to pipeline
            </Button>
          )}
          <Button variant="secondary" onClick={() => onBranch(run)} className="w-full">
            Branch this run
          </Button>
          <Button variant="secondary" onClick={() => onChain(run)} className="w-full">
            Chain downstream analyses
          </Button>
        </div>
      </div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <dt className="text-xs text-brand-muted">{label}</dt>
    <dd className="text-sm font-semibold text-brand-ink">{value}</dd>
  </div>
);
