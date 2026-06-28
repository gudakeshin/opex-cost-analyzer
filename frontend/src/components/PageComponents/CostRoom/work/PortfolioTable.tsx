import React from 'react';
import { AqsBadge } from '../AqsBadge';
import { AddressabilityDots } from '../AddressabilityDots';
import { StageTag } from '../primitives/StageTag';
import { PENDING_STAGES } from '../primitives/stageMeta';
import {
  GATE2_AQS_THRESHOLD,
  formatBandDisplay,
  getAqs,
  getBandNpv,
} from '../../../../utils/initiativeHelpers';
import { toCr } from '../../../../utils/formatInr';
import type { Initiative, PercentileBand } from '../../../../types';

function inrDisplay(amount: number, currency: string): string {
  return toCr(amount, currency).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

interface PortfolioTableProps {
  list: Initiative[];
  band: PercentileBand;
  factor: number;
  currency: string;
  executive: boolean;
  selectedId: string | null;
  expandedId: string | null;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  onDecision: (id: string, stage: string) => void;
}

export const PortfolioTable: React.FC<PortfolioTableProps> = ({
  list,
  band,
  factor,
  currency,
  executive,
  selectedId,
  expandedId,
  onSelect,
  onToggle,
  onDecision,
}) => (
  <div className="overflow-x-auto">
    <table className="cr-ptable">
      <thead>
        <tr>
          <th style={{ width: 26 }} />
          <th>#</th>
          <th>Initiative</th>
          <th>{executive ? 'Pool' : 'Category'}</th>
          {executive && <th>Owner</th>}
          <th style={{ textAlign: 'right' }}>P50 {currency === 'INR' ? '₹Cr' : ''}</th>
          <th>P10 → P90</th>
          {!executive && <th>NPV ({band})</th>}
          <th>AQS</th>
          {executive && (
            <>
              <th>Sust.</th>
              <th>D·B·O·E·R</th>
            </>
          )}
          <th>Stage</th>
          <th style={{ textAlign: 'right' }}>Decide</th>
        </tr>
      </thead>
      <tbody>
        {list.map((init, i) => {
          const id = init.initiative_id;
          const sel = id === selectedId;
          const expanded = id === expandedId;
          const aqs = getAqs(init);
          const canCommit =
            (aqs ?? 1) >= GATE2_AQS_THRESHOLD && PENDING_STAGES.has(init.stage);
          return (
            <React.Fragment key={id}>
              <tr className={sel ? 'cr-sel' : ''} onClick={() => onSelect(id)}>
                <td
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggle(id);
                  }}
                >
                  <span
                    className="inline-flex w-5 h-5 items-center justify-center text-[var(--cr-gray)]"
                    style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}
                  >
                    ›
                  </span>
                </td>
                <td className="text-[var(--cr-gray-3)] text-xs font-semibold cr-mono">
                  {String(i + 1).padStart(2, '0')}
                </td>
                <td>
                  <div className="font-bold text-[13.5px]">{init.lever || init.category}</div>
                  {(init.description || init.root_cause) && (
                    <div className="text-[11.5px] text-[var(--cr-gray-2)] mt-0.5 line-clamp-1 max-w-[280px]">
                      {String(init.description ?? init.root_cause)}
                    </div>
                  )}
                </td>
                <td className="text-xs text-[var(--cr-gray)]">{init.category}</td>
                {executive && <td className="text-xs">{init.owner_name ?? '—'}</td>}
                <td className="cr-mono text-right font-bold">
                  {formatBandDisplay(init, band, factor, currency)}
                </td>
                <td className="cr-mono text-xs text-[var(--cr-gray-2)]">
                  {formatBandDisplay(init, 'p10', factor, currency)} →{' '}
                  {formatBandDisplay(init, 'p90', factor, currency)}
                </td>
                {!executive && (
                  <td className="cr-mono text-sm">
                    {inrDisplay(getBandNpv(init, band), currency)}
                  </td>
                )}
                <td>
                  <AqsBadge score={aqs} />
                </td>
                {executive && (
                  <>
                    <td className="text-sm tabular-nums">
                      {init.sustainability_score != null
                        ? Number(init.sustainability_score).toFixed(2)
                        : 'N/A'}
                    </td>
                    <td>
                      <AddressabilityDots initiative={init} />
                    </td>
                  </>
                )}
                <td>
                  <StageTag stage={init.stage} />
                </td>
                <td>
                  <div
                    className="flex gap-1 justify-end"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <IconBtn
                      title={canCommit ? 'Commit' : 'Commit blocked'}
                      disabled={!canCommit}
                      variant="go"
                      onClick={() => canCommit && onDecision(id, 'committed')}
                    >
                      ✓
                    </IconBtn>
                    <IconBtn title="Defer" onClick={() => onDecision(id, 'deferred')}>
                      ‖
                    </IconBtn>
                    <IconBtn title="Reject" variant="no" onClick={() => onDecision(id, 'rejected')}>
                      ×
                    </IconBtn>
                  </div>
                </td>
              </tr>
              {expanded && (
                <tr>
                  <td colSpan={executive ? 12 : 11} className="!p-0">
                    <div className="px-4 py-3.5 pl-10 bg-[var(--cr-muted)] border-b border-[var(--cr-line-2)]">
                      <div className="grid md:grid-cols-2 gap-6">
                        <div>
                          <p className="text-xs text-[var(--cr-gray)] leading-relaxed">
                            {init.description ?? init.business_rationale ?? init.root_cause ?? '—'}
                          </p>
                          {init.root_cause && (
                            <p className="text-xs text-[var(--cr-gray)] mt-2 border-l-[3px] border-[var(--cr-green)] pl-3">
                              <span className="text-[var(--cr-amber)] font-bold">Root cause</span> ·{' '}
                              {init.root_cause}
                            </p>
                          )}
                        </div>
                        <div className="flex flex-col gap-2">
                          <div className="flex gap-4 text-sm">
                            <div>
                              <div className="cr-eyebrow mb-1">EBITDA</div>
                              <div className="font-extrabold">{init.ebitda_bps ?? '—'} bps</div>
                            </div>
                            <div>
                              <div className="cr-eyebrow mb-1">Bounce-back</div>
                              <div className="font-extrabold">{init.bounce_back_risk ?? 'N/A'}</div>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="self-start text-xs px-2.5 py-1.5 border border-[var(--cr-line)] rounded-[var(--cr-r-sm)] hover:bg-white"
                            onClick={() => onSelect(id)}
                          >
                            Open full detail →
                          </button>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          );
        })}
        {list.length === 0 && (
          <tr>
            <td
              colSpan={executive ? 12 : 11}
              className="text-center py-10 text-[var(--cr-gray-2)]"
            >
              No initiatives match these filters.
            </td>
          </tr>
        )}
      </tbody>
    </table>
  </div>
);

function IconBtn({
  children,
  onClick,
  disabled,
  title,
  variant,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  title: string;
  variant?: 'go' | 'no';
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`w-7 h-7 rounded-md border border-[var(--cr-line)] bg-white inline-flex items-center justify-center text-sm transition-colors ${
        disabled ? 'opacity-35 cursor-not-allowed' : 'cursor-pointer hover:bg-[var(--cr-muted)]'
      } ${variant === 'go' ? 'hover:border-[var(--cr-green)] hover:text-[var(--cr-green-dk)]' : ''} ${
        variant === 'no' ? 'hover:border-[var(--cr-red)] hover:text-[var(--cr-red)]' : ''
      }`}
    >
      {children}
    </button>
  );
}
