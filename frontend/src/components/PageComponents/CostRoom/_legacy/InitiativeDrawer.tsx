import React, { useState } from 'react';
import { Drawer } from '../../../Common/Drawer';
import { Badge } from '../../../Common/Badge';
import { Input } from '../../../Common/Input';
import { Loader } from '../../../Common/Loader';
import { AqsBadge } from '../AqsBadge';
import { formatAmount } from '../fpaHelpers';
import { formatBandRange, formatCr } from '../../../../utils/formatInr';
import { getAqs, getBandNpv, getBandSavings, stageLabel } from '../../../../utils/initiativeHelpers';
import type { Initiative, InitiativeProvenance, PercentileBand } from '../../../../types';

interface InitiativeDrawerProps {
  initiative: Initiative | null;
  open: boolean;
  onClose: () => void;
  percentileBand: PercentileBand;
  currency?: string;
  provenance?: InitiativeProvenance | null;
  provenanceLoading?: boolean;
  milestones?: Record<string, unknown>[] | null;
  milestonesLoading?: boolean;
  onRecordActuals?: (amountCr: number) => void;
  actualsSaving?: boolean;
}

export const InitiativeDrawer: React.FC<InitiativeDrawerProps> = ({
  initiative,
  open,
  onClose,
  percentileBand,
  currency = 'USD',
  provenance = null,
  provenanceLoading = false,
  milestones = null,
  milestonesLoading = false,
  onRecordActuals,
  actualsSaving = false,
}) => {
  const [actualsInput, setActualsInput] = useState('');

  if (!initiative) return null;

  const sym = currency === 'INR' ? '₹' : currency === 'EUR' ? '€' : currency === 'GBP' ? '£' : '$';
  const unit = currency === 'INR' ? 'Cr' : 'M';
  const aqs = getAqs(initiative);
  const p10 = getBandSavings(initiative, 'p10');
  const p50 = getBandSavings(initiative, 'p50');
  const p90 = getBandSavings(initiative, 'p90');
  const bandSavings = getBandSavings(initiative, percentileBand);
  const bandNpv = getBandNpv(initiative, percentileBand);
  const precedents = initiative.condition_precedents ?? [];

  const changeLog = [...(initiative.change_log ?? [])].reverse();

  const handleRecordActuals = () => {
    if (!onRecordActuals) return;
    const amount = parseFloat(actualsInput);
    if (!Number.isFinite(amount) || amount < 0) return;
    onRecordActuals(amount);
    setActualsInput('');
  };

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
          <p className="font-semibold text-brand-navy mb-3">Savings bands ({sym} {unit})</p>
          <div className="grid grid-cols-3 gap-3 tabular-nums">
            <div>
              <p className="text-xs text-brand-muted">P10</p>
              <p className="font-mono font-semibold">{formatCr(p10, { currency })}</p>
            </div>
            <div>
              <p className="text-xs text-brand-muted">P50</p>
              <p className="font-mono font-semibold text-brand-green">{formatCr(p50, { currency })}</p>
            </div>
            <div>
              <p className="text-xs text-brand-muted">P90</p>
              <p className="font-mono font-semibold">{formatCr(p90, { currency })}</p>
            </div>
          </div>
          <p className="text-xs text-brand-muted mt-2">
            Active view ({percentileBand}): {formatCr(bandSavings, { currency })} · Range{' '}
            {formatBandRange(p10, p90, { currency })}
          </p>
          <p className="text-xs text-brand-muted mt-1">
            3-yr NPV ({percentileBand}, 10% WACC):{' '}
            <span className="font-mono font-semibold text-brand-ink">{formatCr(bandNpv, { currency })}</span>
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

        {initiative.business_rationale && (
          <section>
            <p className="font-semibold text-brand-navy mb-1">Business rationale</p>
            <p className="text-brand-ink">{initiative.business_rationale}</p>
          </section>
        )}

        {initiative.root_cause && (
          <section>
            <p className="font-semibold text-brand-navy mb-1">Root cause</p>
            <p className="text-brand-ink">{initiative.root_cause}</p>
          </section>
        )}

        {(initiative.owner_role || initiative.business_sponsor) && (
          <section className="space-y-1">
            <p className="font-semibold text-brand-navy">Owner &amp; accountability</p>
            {initiative.owner_role && (
              <p><span className="text-brand-muted">Owner:</span> {initiative.owner_role}</p>
            )}
            {initiative.business_sponsor && (
              <p><span className="text-brand-muted">Sponsor:</span> {initiative.business_sponsor}</p>
            )}
          </section>
        )}

        {initiative.affected_vendors && initiative.affected_vendors.length > 0 && (
          <section>
            <p className="font-semibold text-brand-navy mb-2">Affected vendors</p>
            <ul className="space-y-1 text-brand-ink">
              {initiative.affected_vendors.map((v, i) => (
                <li key={i} className="flex justify-between gap-3">
                  <span>{v.supplier}</span>
                  <span className="text-brand-muted tabular-nums">
                    {v.share_of_category_pct != null ? `${v.share_of_category_pct}% of category` : ''}
                    {v.avg_payment_terms_days != null ? ` · ${v.avg_payment_terms_days}d terms` : ''}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {initiative.contract_levers && initiative.contract_levers.length > 0 && (
          <section>
            <p className="font-semibold text-brand-navy mb-2">Contract &amp; commercial levers</p>
            <ul className="list-disc pl-5 space-y-1 text-brand-ink">
              {initiative.contract_levers.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </section>
        )}

        {initiative.risks && initiative.risks.length > 0 && (
          <section>
            <p className="font-semibold text-brand-navy mb-2">Risks &amp; mitigations</p>
            <ul className="space-y-2 text-brand-ink">
              {initiative.risks.map((r, i) => (
                <li key={i} className="p-2 border border-brand-border rounded-lg bg-white">
                  <p className="font-medium flex items-start gap-2">
                    {r.severity && (
                      <Badge tone={r.severity === 'high' ? 'error' : r.severity === 'medium' ? 'warning' : 'default'}>
                        {r.severity}
                      </Badge>
                    )}
                    <span>{r.risk}</span>
                  </p>
                  {r.mitigation && (
                    <p className="text-xs text-brand-muted mt-1">Mitigation: {r.mitigation}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {initiative.kpis && initiative.kpis.length > 0 && (
          <section>
            <p className="font-semibold text-brand-navy mb-2">KPIs</p>
            <ul className="list-disc pl-5 space-y-1 text-brand-ink">
              {initiative.kpis.map((k, i) => (
                <li key={i}>
                  {k.metric}
                  {k.cadence && <span className="text-brand-muted"> ({k.cadence})</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {initiative.change_management?.stakeholders && initiative.change_management.stakeholders.length > 0 && (
          <section className="space-y-1">
            <p className="font-semibold text-brand-navy">Change management</p>
            <p>
              <span className="text-brand-muted">Stakeholders:</span>{' '}
              {initiative.change_management.stakeholders.join(', ')}
            </p>
            {initiative.change_management.comms_cadence && (
              <p>
                <span className="text-brand-muted">Cadence:</span>{' '}
                {initiative.change_management.comms_cadence}
              </p>
            )}
            {initiative.change_management.resistance_points && initiative.change_management.resistance_points.length > 0 && (
              <p>
                <span className="text-brand-muted">Resistance:</span>{' '}
                {initiative.change_management.resistance_points.join('; ')}
              </p>
            )}
          </section>
        )}

        {initiative.phasing_narrative && (
          <section>
            <p className="font-semibold text-brand-navy mb-1">Phasing</p>
            <p className="text-brand-ink">{initiative.phasing_narrative}</p>
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

        <section className="border-t border-brand-border pt-4">
          <p className="font-semibold text-brand-navy mb-2">Source data trace</p>
          {provenanceLoading ? (
            <Loader label="Loading provenance…" />
          ) : provenance ? (
            <div className="space-y-3 text-xs">
              <ol className="space-y-2">
                {(provenance.trace_steps ?? []).map((step) => (
                  <li key={step.step} className="flex gap-2">
                    <span className="font-mono text-brand-muted shrink-0">{step.step}.</span>
                    <span>
                      <span className="font-medium text-brand-ink">{step.label}</span>
                      {step.count != null && ` (${step.count} items)`}
                      {step.value != null && ` — ${String(step.value)}`}
                      {step.source && (
                        <span className="text-brand-muted"> · {step.source}</span>
                      )}
                    </span>
                  </li>
                ))}
              </ol>

              {(provenance.source_spend_rows ?? []).length > 0 && (
                <div>
                  <p className="font-medium text-brand-ink mb-1">Top source spend rows</p>
                  <div className="overflow-x-auto border border-brand-border rounded-lg">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-brand-surface-muted text-brand-muted text-left">
                          <th className="px-2 py-1">Row</th>
                          <th className="px-2 py-1">Supplier</th>
                          <th className="px-2 py-1">Amount</th>
                          <th className="px-2 py-1">Period</th>
                        </tr>
                      </thead>
                      <tbody>
                        {provenance.source_spend_rows!.slice(0, 8).map((row, i) => (
                          <tr key={i} className="border-t border-brand-border/60">
                            <td className="px-2 py-1 font-mono">{String(row.row_id ?? '—')}</td>
                            <td className="px-2 py-1">{String(row.supplier ?? '—')}</td>
                            <td className="px-2 py-1 tabular-nums">
                              {formatAmount(row.amount_reporting, currency)}
                            </td>
                            <td className="px-2 py-1">{String(row.fiscal_period ?? row.spend_date ?? '—')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {provenance.source_spend_rows!.length > 8 && (
                    <p className="mt-1 text-brand-muted">
                      Showing 8 of {provenance.source_spend_rows!.length} source rows
                    </p>
                  )}
                </div>
              )}

              {(provenance.source_files ?? []).length > 0 && (
                <div>
                  <p className="font-medium text-brand-ink mb-1">Source files</p>
                  <ul className="space-y-1 text-brand-muted">
                    {provenance.source_files!.map((f, i) => (
                      <li key={i}>
                        {f.filename ?? f.path ?? 'file'}
                        {f.uploaded_at && <span> · uploaded {f.uploaded_at}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <p className="text-brand-muted text-xs">No source trace available for this initiative.</p>
          )}
        </section>

        <section className="border-t border-brand-border pt-4">
          <p className="font-semibold text-brand-navy mb-2">Milestones &amp; actuals</p>
          {milestonesLoading ? (
            <Loader label="Loading milestones…" />
          ) : milestones && milestones.length > 0 ? (
            <ul className="space-y-2 mb-4">
              {milestones.map((ms, i) => (
                <li key={i} className="p-2 border border-brand-border rounded-lg text-xs">
                  <p className="font-medium">{String(ms.title ?? ms.name ?? ms.milestone ?? `Milestone ${i + 1}`)}</p>
                  {ms.due_date != null && <p className="text-brand-muted">Due: {String(ms.due_date)}</p>}
                  {ms.status != null && <p className="text-brand-muted capitalize">Status: {String(ms.status)}</p>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-brand-muted text-xs mb-4">No milestones recorded yet.</p>
          )}

          {onRecordActuals && (
            <div className="flex flex-wrap items-end gap-2">
              <div className="flex-1 min-w-[8rem]">
                <Input
                  label={`Realized savings (${unit})`}
                  type="number"
                  min="0"
                  step="0.1"
                  value={actualsInput}
                  onChange={(e) => setActualsInput(e.target.value)}
                  placeholder="e.g. 2.5"
                />
              </div>
              <button
                type="button"
                disabled={actualsSaving || !actualsInput.trim()}
                onClick={handleRecordActuals}
                className="px-3 py-2 rounded-lg bg-deloitte-green text-white text-xs font-medium hover:bg-[#6fa31e] disabled:opacity-50"
              >
                {actualsSaving ? 'Saving…' : 'Record actuals'}
              </button>
            </div>
          )}
        </section>

        {changeLog.length > 0 && (
          <section className="border-t border-brand-border pt-4">
            <p className="font-semibold text-brand-navy mb-2">Change history</p>
            <ul className="space-y-1.5 text-xs">
              {changeLog.slice(0, 10).map((entry, i) => (
                <li key={i} className="flex gap-2">
                  <span className="font-mono text-brand-muted shrink-0">
                    {entry.ts ? String(entry.ts).slice(0, 10) : '—'}
                  </span>
                  <span>
                    <span className="font-medium capitalize">
                      {(entry.action ?? 'change').replace(/_/g, ' ')}
                    </span>
                    {describeChangeDetail(entry.detail) && (
                      <span className="text-brand-muted"> · {describeChangeDetail(entry.detail)}</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
            {changeLog.length > 10 && (
              <p className="mt-1 text-xs text-brand-muted">
                Showing 10 of {changeLog.length} changes
              </p>
            )}
          </section>
        )}
      </div>
    </Drawer>
  );
};

function describeChangeDetail(detail: Record<string, unknown> | undefined): string | null {
  if (!detail) return null;
  const parts = Object.entries(detail)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${String(v)}`);
  return parts.length ? parts.join(' · ') : null;
}
