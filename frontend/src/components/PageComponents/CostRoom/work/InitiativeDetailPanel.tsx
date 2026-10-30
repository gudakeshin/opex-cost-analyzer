import React, { useState } from 'react';
import { currencySymbol } from '../../../../utils/currencySymbol';
import { AqsBadge } from '../AqsBadge';
import { AddressabilityDots } from '../AddressabilityDots';
import { StageTag } from '../primitives/StageTag';
import { PENDING_STAGES } from '../primitives/stageMeta';
import { Loader } from '../../../Common/Loader';
import { Input } from '../../../Common/Input';
import {
  GATE2_AQS_THRESHOLD,
  formatBandDisplay,
  getAqs,
  getBandNpv,
} from '../../../../utils/initiativeHelpers';
import { formatCr } from '../../../../utils/formatInr';
import type { Initiative, InitiativeProvenance, PercentileBand } from '../../../../types';

interface InitiativeDetailPanelProps {
  initiative: Initiative | null;
  band: PercentileBand;
  factor: number;
  currency: string;
  provenance?: InitiativeProvenance | null;
  provenanceLoading?: boolean;
  milestones?: Record<string, unknown>[] | null;
  milestonesLoading?: boolean;
  onDecision: (id: string, stage: string) => void;
  onRecordActuals?: (amountCr: number) => void;
  actualsSaving?: boolean;
}

function MiniBand({ band }: { band: PercentileBand }) {
  const left = band === 'p10' ? 12 : band === 'p90' ? 88 : 50;
  return (
    <div className="h-1.5 rounded bg-gradient-to-r from-[var(--cr-line)] via-[#cfe39f] to-[var(--cr-green)] relative my-1.5">
      <span
        className="absolute top-1/2 w-[11px] h-[11px] rounded-full bg-white border-2 border-[var(--cr-ink)] -translate-x-1/2 -translate-y-1/2"
        style={{ left: `${left}%` }}
      />
    </div>
  );
}

export const InitiativeDetailPanel: React.FC<InitiativeDetailPanelProps> = ({
  initiative,
  band,
  factor,
  currency,
  provenance,
  provenanceLoading,
  milestones,
  milestonesLoading,
  onDecision,
  onRecordActuals,
  actualsSaving,
}) => {
  const [actualsInput, setActualsInput] = useState('');
  const sym = currencySymbol(currency);

  if (!initiative) {
    return (
      <div className="cr-card flex flex-col min-h-[320px]">
        <div className="flex-1 flex flex-col items-center justify-center px-6 py-14 text-center text-[var(--cr-gray-2)]">
          <div className="w-11 h-11 rounded-xl bg-[var(--cr-muted)] flex items-center justify-center mb-3 text-xl">
            ⌂
          </div>
          <p className="font-bold text-[var(--cr-ink)] mb-1">Select an initiative</p>
          <p className="text-xs max-w-[220px]">
            Pick a row to inspect the savings band, evidence quality, milestones, and commit it.
          </p>
        </div>
      </div>
    );
  }

  const id = initiative.initiative_id;
  const aqs = getAqs(initiative);
  const canCommit = (aqs ?? 1) >= GATE2_AQS_THRESHOLD && PENDING_STAGES.has(initiative.stage);
  const isRealizable = initiative.stage === 'in_flight' || initiative.stage === 'realized';
  const bandNpv = getBandNpv(initiative, band);

  const handleRecordActuals = () => {
    if (!onRecordActuals) return;
    const amount = parseFloat(actualsInput);
    if (!Number.isFinite(amount) || amount < 0) return;
    onRecordActuals(amount);
    setActualsInput('');
  };

  return (
    <div className="cr-card flex flex-col">
      <div className="px-5 py-4 border-b border-[var(--cr-line-2)]">
        <div className="cr-eyebrow mb-1.5">
          {id.slice(0, 8)} · {initiative.category}
        </div>
        <h2 className="text-[17px] font-extrabold leading-tight tracking-tight">
          {initiative.lever || initiative.category}
        </h2>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <StageTag stage={initiative.stage} />
          {initiative.owner_name && (
            <span className="text-xs font-semibold text-[var(--cr-gray)] bg-[var(--cr-muted)] border border-[var(--cr-line)] rounded-full px-2.5 py-0.5">
              {initiative.owner_name}
            </span>
          )}
        </div>
      </div>

      <div className="px-5 py-4 flex flex-col gap-4 flex-1 overflow-y-auto max-h-[calc(100vh-280px)]">
        <div>
          <div className="flex items-baseline gap-2">
            <div className="cr-mono text-[32px] font-extrabold tracking-tight">
              {sym}
              {formatBandDisplay(initiative, band, factor, currency)}
            </div>
            <div className="text-xs text-[var(--cr-gray-2)]">Cr · {band.toUpperCase()} run-rate</div>
          </div>
          <MiniBand band={band} />
          <div className="flex justify-between text-[11px] cr-mono text-[var(--cr-gray-2)]">
            <span>
              P10 {sym}
              {formatBandDisplay(initiative, 'p10', factor, currency)}
            </span>
            <span>
              P50 {sym}
              {formatBandDisplay(initiative, 'p50', factor, currency)}
            </span>
            <span>
              P90 {sym}
              {formatBandDisplay(initiative, 'p90', factor, currency)}
            </span>
          </div>
          <p className="text-xs text-[var(--cr-gray-2)] mt-2">
            3-yr NPV ({band}, 10% WACC):{' '}
            <span className="cr-mono font-bold text-[var(--cr-ink)]">{formatCr(bandNpv, { currency })}</span>
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2.5">
          <Kv label="Assumption quality" value={<AqsBadge score={aqs} showLabel />} />
          <Kv label="EBITDA impact" value={`${initiative.ebitda_bps ?? '—'} bps`} />
          <Kv label="Bounce-back risk" value={initiative.bounce_back_risk ?? 'N/A'} />
          <Kv label="Sustainability" value={
            initiative.sustainability_score != null
              ? Number(initiative.sustainability_score).toFixed(2)
              : 'N/A'
          } />
        </div>

        <div>
          <div className="cr-eyebrow mb-2">Addressability · D·B·O·E·R</div>
          <AddressabilityDots initiative={initiative} />
        </div>

        <div>
          <div className="cr-eyebrow mb-2">Milestones</div>
          {milestonesLoading ? (
            <Loader label="Loading…" />
          ) : milestones && milestones.length > 0 ? (
            milestones.map((ms, i) => {
              const label = String(ms.label ?? ms.name ?? ms.title ?? `Milestone ${i + 1}`);
              const done = Boolean(ms.done ?? ms.completed);
              return (
                <div key={i} className="flex items-start gap-2 py-1.5 text-xs">
                  <span
                    className={`w-4 h-4 rounded-full shrink-0 flex items-center justify-center text-[11px] ${
                      done
                        ? 'bg-[var(--cr-green)] text-white'
                        : 'bg-white border border-[var(--cr-line)]'
                    }`}
                  >
                    {done ? '✓' : ''}
                  </span>
                  <span
                    className={done ? 'text-[var(--cr-gray)] line-through' : 'text-[var(--cr-ink)]'}
                  >
                    {label}
                  </span>
                </div>
              );
            })
          ) : (
            <p className="text-xs text-[var(--cr-gray-2)]">No milestones on file.</p>
          )}
        </div>

        <div className="text-xs text-[var(--cr-gray)] bg-[var(--cr-muted)] border-l-[3px] border-[var(--cr-green)] rounded-r-md px-3 py-2 leading-relaxed">
          {provenanceLoading ? (
            'Loading provenance…'
          ) : provenance?.trace_steps?.length ? (
            `${provenance.trace_steps.length} provenance steps on file.`
          ) : (
            <>
              <span className="text-[var(--cr-green-dk)] font-bold">Fact</span> GL spend cube + AP ledger ·{' '}
              <span className="text-[var(--cr-amber)] font-bold">Inference</span> savings range from sector
              pack lever + peer benchmark.
            </>
          )}
        </div>

        {isRealizable && onRecordActuals && (
          <div className="bg-[var(--cr-green-soft)] border border-[#cfe39f] rounded-lg px-3 py-2.5">
            <p className="text-xs font-bold text-[#2f6a1e] mb-2">Record actuals (Cr)</p>
            <div className="flex gap-2">
              <Input
                value={actualsInput}
                onChange={(e) => setActualsInput(e.target.value)}
                placeholder="0.0"
                className="flex-1 text-sm"
              />
              <button
                type="button"
                disabled={actualsSaving}
                onClick={handleRecordActuals}
                className="text-xs px-3 py-2 bg-[var(--cr-green)] text-white rounded-[var(--cr-r-sm)] font-semibold disabled:opacity-50"
              >
                {actualsSaving ? '…' : 'Save'}
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2 px-5 py-4 border-t border-[var(--cr-line-2)] bg-[var(--cr-muted)]">
        <button
          type="button"
          disabled={!canCommit}
          title={canCommit ? '' : 'Blocked — AQS or stage'}
          onClick={() => onDecision(id, 'committed')}
          className="flex-1 flex items-center justify-center gap-1.5 text-sm font-semibold py-2 rounded-[var(--cr-r-sm)] bg-[var(--cr-green)] text-white disabled:opacity-45"
        >
          ✓ Commit
        </button>
        <button
          type="button"
          onClick={() => onDecision(id, 'deferred')}
          className="flex-1 text-sm font-semibold py-2 rounded-[var(--cr-r-sm)] border border-[var(--cr-line)] bg-white"
        >
          ‖ Defer
        </button>
        <button
          type="button"
          onClick={() => onDecision(id, 'rejected')}
          className="flex-1 text-sm font-semibold py-2 rounded-[var(--cr-r-sm)] border border-[var(--cr-red-soft)] bg-[var(--cr-red-soft)] text-[var(--cr-red)]"
        >
          × Reject
        </button>
      </div>
    </div>
  );
};

function Kv({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] text-[var(--cr-gray-2)]">{label}</div>
      <div className="text-[15px] font-extrabold tracking-tight mt-0.5">{value}</div>
    </div>
  );
}
