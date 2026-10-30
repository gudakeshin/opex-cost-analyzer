import React, { useMemo } from 'react';
import { currencySymbol } from '../../../../utils/currencySymbol';
import { AqsBadge } from '../AqsBadge';
import { StageTag } from '../primitives/StageTag';
import { PENDING_STAGES } from '../primitives/stageMeta';
import {
  GATE2_AQS_THRESHOLD,
  actionReason,
  formatBandDisplay,
  getAqs,
  priorityScore,
} from '../../../../utils/initiativeHelpers';
import type { Initiative, PercentileBand } from '../../../../types';

interface PriorityWorklistProps {
  list: Initiative[];
  band: PercentileBand;
  factor: number;
  currency: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDecision: (id: string, stage: string) => void;
}

export const PriorityWorklist: React.FC<PriorityWorklistProps> = ({
  list,
  band,
  factor,
  currency,
  selectedId,
  onSelect,
  onDecision,
}) => {
  const ranked = useMemo(
    () => [...list].sort((a, b) => priorityScore(b) - priorityScore(a)),
    [list],
  );
  const sym = currencySymbol(currency);

  return (
    <div className="flex flex-col">
      {ranked.map((init, i) => {
        const id = init.initiative_id;
        const reason = actionReason(init);
        const aqs = getAqs(init);
        const canCommit =
          (aqs ?? 1) >= GATE2_AQS_THRESHOLD && PENDING_STAGES.has(init.stage);
        const toneColor =
          reason.tone === 'block'
            ? 'var(--cr-red)'
            : reason.tone === 'go'
              ? 'var(--cr-green-dk)'
              : 'var(--cr-amber)';
        return (
          <div
            key={id}
            className={`grid grid-cols-[30px_1fr_auto] gap-3.5 items-center px-4 py-3.5 border-b border-[var(--cr-line-2)] cursor-pointer transition-colors ${
              id === selectedId ? 'bg-[var(--cr-green-soft)]' : 'hover:bg-[var(--cr-muted)]'
            }`}
            onClick={() => onSelect(id)}
          >
            <div className="text-lg font-extrabold text-[var(--cr-gray-3)] tabular-nums">{i + 1}</div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-bold text-sm">{init.lever || init.category}</span>
                <StageTag stage={init.stage} />
                <AqsBadge score={aqs} />
              </div>
              <div className="text-[11.5px] font-semibold mt-0.5" style={{ color: toneColor }}>
                {reason.txt} · {init.owner_name ?? '—'} · {init.category}
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="cr-mono font-extrabold text-base">
                  {sym}
                  {formatBandDisplay(init, band, factor, currency)}
                </div>
                <div className="cr-mono text-[11px] text-[var(--cr-gray-2)]">
                  {formatBandDisplay(init, 'p10', factor, currency)}–
                  {formatBandDisplay(init, 'p90', factor, currency)}
                </div>
              </div>
              <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                <ActionBtn
                  disabled={!canCommit}
                  onClick={() => canCommit && onDecision(id, 'committed')}
                  label="Commit"
                >
                  ✓
                </ActionBtn>
                <ActionBtn onClick={() => onDecision(id, 'deferred')} label="Defer">
                  ‖
                </ActionBtn>
                <ActionBtn onClick={() => onDecision(id, 'rejected')} label="Reject" danger>
                  ×
                </ActionBtn>
              </div>
            </div>
          </div>
        );
      })}
      {list.length === 0 && (
        <div className="text-center py-10 text-[var(--cr-gray-2)]">No initiatives match these filters.</div>
      )}
    </div>
  );
};

function ActionBtn({
  children,
  onClick,
  disabled,
  label,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  label: string;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`w-7 h-7 rounded-md border border-[var(--cr-line)] bg-white text-sm ${
        disabled ? 'opacity-35' : 'hover:bg-[var(--cr-muted)]'
      } ${danger ? 'hover:border-[var(--cr-red)] hover:text-[var(--cr-red)]' : 'hover:border-[var(--cr-green)]'}`}
    >
      {children}
    </button>
  );
}
