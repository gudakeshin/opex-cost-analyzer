import React from 'react';
import { currencySymbol } from '../../../../utils/currencySymbol';
import { AqsBadge } from '../AqsBadge';
import { STAGE_META, KANBAN_STAGES } from '../primitives/stageMeta';
import { formatBandDisplay, valForBand } from '../../../../utils/initiativeHelpers';
import { toCr } from '../../../../utils/formatInr';
import type { Initiative, PercentileBand } from '../../../../types';

interface StageKanbanProps {
  list: Initiative[];
  band: PercentileBand;
  factor: number;
  currency: string;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

export const StageKanban: React.FC<StageKanbanProps> = ({
  list,
  band,
  factor,
  currency,
  selectedId,
  onSelect,
}) => {
  const sym = currencySymbol(currency);

  return (
    <div className="grid grid-flow-col auto-cols-[minmax(220px,1fr)] gap-3 overflow-x-auto pb-2">
      {KANBAN_STAGES.map((stage) => {
        const items = list.filter((x) => x.stage === stage);
        const meta = STAGE_META[stage];
        const total = items.reduce((s, x) => s + (valForBand(x, band, factor) ?? 0), 0);
        const dotColor =
          meta.bg === '#fff' ? meta.bd : meta.fg === '#fff' ? meta.bg : meta.fg;
        return (
          <div
            key={stage}
            className="bg-[var(--cr-muted)] border border-[var(--cr-line)] rounded-[var(--cr-r)] min-h-[120px]"
          >
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-[var(--cr-line)]">
              <span className="text-xs font-bold inline-flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: dotColor }} />
                {meta.label}
              </span>
              <span className="text-[11px] font-bold text-[var(--cr-gray-2)] bg-white border border-[var(--cr-line)] rounded-full px-1.5 py-0.5 cr-mono">
                {items.length} · {sym}
                {toCr(total, currency).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
              </span>
            </div>
            <div className="p-2 flex flex-col gap-2">
              {items.map((init) => (
                <div
                  key={init.initiative_id}
                  className={`bg-white border rounded-[var(--cr-r-sm)] p-2.5 cursor-pointer shadow-sm transition-all hover:border-[var(--cr-green)] hover:-translate-y-px ${
                    init.initiative_id === selectedId
                      ? 'border-[var(--cr-green)] ring-2 ring-[var(--cr-green-soft)]'
                      : 'border-[var(--cr-line)]'
                  }`}
                  role="button"
                  tabIndex={0}
                  aria-pressed={init.initiative_id === selectedId}
                  onClick={() => onSelect(init.initiative_id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onSelect(init.initiative_id);
                    }
                  }}
                >
                  <div className="text-xs font-bold leading-snug">{init.lever || init.category}</div>
                  <div className="text-[11px] text-[var(--cr-gray-2)] mt-0.5">
                    {init.owner_name ?? '—'} · {init.category}
                  </div>
                  <div className="flex items-center justify-between mt-2">
                    <span className="cr-mono font-extrabold text-sm">
                      {sym}
                      {formatBandDisplay(init, band, factor, currency)}
                    </span>
                    <AqsBadge score={init.aqs} />
                  </div>
                </div>
              ))}
              {items.length === 0 && (
                <div className="text-[11.5px] text-[var(--cr-gray-3)] text-center py-2">—</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
