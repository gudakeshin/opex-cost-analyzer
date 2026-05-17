import React from 'react';
import { Drawer } from '../../Common/Drawer';
import { Badge } from '../../Common/Badge';
import { AqsBadge } from './AqsBadge';
import { formatBandRange, formatCr } from '../../../utils/formatInr';
import { getAqs, getBandSavings, stageLabel } from '../../../utils/initiativeHelpers';
import type { Initiative, PercentileBand } from '../../../types';

interface InitiativeDrawerProps {
  initiative: Initiative | null;
  open: boolean;
  onClose: () => void;
  percentileBand: PercentileBand;
}

export const InitiativeDrawer: React.FC<InitiativeDrawerProps> = ({
  initiative,
  open,
  onClose,
  percentileBand,
}) => {
  if (!initiative) return null;

  const aqs = getAqs(initiative);
  const p10 = getBandSavings(initiative, 'p10');
  const p50 = getBandSavings(initiative, 'p50');
  const p90 = getBandSavings(initiative, 'p90');
  const bandSavings = getBandSavings(initiative, percentileBand);
  const precedents = initiative.condition_precedents ?? [];

  return (
    <Drawer open={open} title={initiative.lever || initiative.category} onClose={onClose}>
      <div className="space-y-5 text-sm">
        <section>
          <p className="text-brand-muted text-xs uppercase tracking-wide mb-1">Category / pool</p>
          <p className="font-medium text-brand-ink">{initiative.category}</p>
        </section>

        <section className="flex flex-wrap gap-3">
          <div>
            <p className="text-xs text-brand-muted">Stage</p>
            <Badge>{stageLabel(initiative.stage)}</Badge>
          </div>
          <div>
            <p className="text-xs text-brand-muted">Type</p>
            <p>{initiative.savings_type ?? 'run_rate'}</p>
          </div>
          {initiative.owner_name && (
            <div>
              <p className="text-xs text-brand-muted">Owner</p>
              <p>{initiative.owner_name}</p>
            </div>
          )}
        </section>

        <section className="p-4 rounded-xl bg-brand-surface-muted border border-brand-border">
          <p className="font-semibold text-brand-navy mb-3">Savings bands (₹ Cr)</p>
          <div className="grid grid-cols-3 gap-3 tabular-nums">
            <div>
              <p className="text-xs text-brand-muted">P10</p>
              <p className="font-mono font-semibold">{formatCr(p10)}</p>
            </div>
            <div>
              <p className="text-xs text-brand-muted">P50</p>
              <p className="font-mono font-semibold text-brand-green">{formatCr(p50)}</p>
            </div>
            <div>
              <p className="text-xs text-brand-muted">P90</p>
              <p className="font-mono font-semibold">{formatCr(p90)}</p>
            </div>
          </div>
          <p className="text-xs text-brand-muted mt-2">
            Active view ({percentileBand}): {formatCr(bandSavings)} · Range {formatBandRange(p10, p90)}
          </p>
        </section>

        {(aqs != null ||
          initiative.sustainability_score != null ||
          initiative.bounce_back_risk) && (
          <section className="space-y-2">
            <p className="font-semibold text-brand-navy">Quality & risk</p>
            {aqs != null && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-brand-muted">AQS</span>
                <AqsBadge score={aqs} showLabel />
              </div>
            )}
            {initiative.sustainability_score != null && (
              <p>
                <span className="text-brand-muted">Sustainability:</span>{' '}
                {Number(initiative.sustainability_score).toFixed(2)}
              </p>
            )}
            {initiative.bounce_back_risk && (
              <p>
                <span className="text-brand-muted">Bounce-back risk:</span> {initiative.bounce_back_risk}
              </p>
            )}
          </section>
        )}

        {initiative.root_cause && (
          <section>
            <p className="font-semibold text-brand-navy mb-1">Root cause</p>
            <p className="text-brand-ink">{initiative.root_cause}</p>
          </section>
        )}

        {precedents.length > 0 && (
          <section>
            <p className="font-semibold text-brand-navy mb-2">Condition precedents</p>
            <ul className="list-disc pl-5 space-y-1 text-brand-ink">
              {precedents.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <p className="font-semibold text-brand-navy mb-2">Assumption register</p>
          {initiative.assumptions?.length ? (
            <div className="space-y-2">
              {initiative.assumptions.map((a, i) => (
                <div
                  key={i}
                  className="p-3 border border-brand-border rounded-lg bg-white text-xs overflow-x-auto"
                >
                  {typeof a === 'object' && a !== null ? (
                    <dl className="space-y-1">
                      {Object.entries(a).map(([k, v]) => (
                        <div key={k}>
                          <dt className="text-brand-muted inline">{k}: </dt>
                          <dd className="inline text-brand-ink">{String(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : (
                    <pre className="font-mono">{JSON.stringify(a, null, 2)}</pre>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-brand-muted text-xs">
              No structured assumptions on file. Values are model-derived from sector pack and spend signals.
            </p>
          )}
        </section>
      </div>
    </Drawer>
  );
};
