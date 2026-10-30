import React from 'react';
import type { LayoutMode } from '../FilterBar';
import { PortfolioTable } from './PortfolioTable';
import { PriorityWorklist } from './PriorityWorklist';
import { StageKanban } from './StageKanban';
import { InitiativeDetailPanel } from './InitiativeDetailPanel';
import type { Initiative, InitiativeProvenance, PercentileBand } from '../../../../types';

interface WorkAreaProps {
  list: Initiative[];
  layoutMode: LayoutMode;
  band: PercentileBand;
  factor: number;
  currency: string;
  executive: boolean;
  selectedId: string | null;
  expandedId: string | null;
  onSelect: (id: string) => void;
  onToggleExpand: (id: string) => void;
  onDecision: (id: string, stage: string) => void;
  provenance: InitiativeProvenance | null;
  provenanceLoading: boolean;
  milestones: Record<string, unknown>[] | null;
  milestonesLoading: boolean;
  onRecordActuals?: (amountCr: number) => void;
  actualsSaving?: boolean;
  onConsolidate?: () => void;
  showConsolidate?: boolean;
}

const LAYOUT_TITLES: Record<LayoutMode, { title: string; hint: string }> = {
  split: {
    title: 'Initiative portfolio',
    hint: 'Click a row to inspect · ▸ to expand',
  },
  worklist: {
    title: 'Priority worklist',
    hint: 'Ranked by value × urgency',
  },
  kanban: {
    title: 'Pipeline by stage',
    hint: 'Board view · click to inspect',
  },
};

export const WorkArea: React.FC<WorkAreaProps> = ({
  list,
  layoutMode,
  band,
  factor,
  currency,
  executive,
  selectedId,
  expandedId,
  onSelect,
  onToggleExpand,
  onDecision,
  provenance,
  provenanceLoading,
  milestones,
  milestonesLoading,
  onRecordActuals,
  actualsSaving,
  onConsolidate,
  showConsolidate,
}) => {
  const meta = LAYOUT_TITLES[layoutMode];
  const selected = list.find((x) => x.initiative_id === selectedId) ?? null;

  return (
    <div className="cr-work">
      <div className="cr-card overflow-hidden min-w-0">
        <div className="cr-card-h">
          <h2 className="text-sm font-bold">{meta.title}</h2>
          <div className="flex items-center gap-2">
            <span className="text-[11.5px] text-[var(--cr-gray-2)] hidden sm:inline">{meta.hint}</span>
            {showConsolidate && onConsolidate && (
              <button
                type="button"
                onClick={onConsolidate}
                className="text-[11px] px-2 py-1 border border-[var(--cr-line)] rounded-[var(--cr-r-sm)] hover:bg-[var(--cr-muted)]"
              >
                Consolidate
              </button>
            )}
          </div>
        </div>
        <div className={layoutMode === 'kanban' ? 'p-3.5' : ''}>
          {layoutMode === 'split' && (
            <PortfolioTable
              list={list}
              band={band}
              factor={factor}
              currency={currency}
              executive={executive}
              selectedId={selectedId}
              expandedId={expandedId}
              onSelect={onSelect}
              onToggle={onToggleExpand}
              onDecision={onDecision}
            />
          )}
          {layoutMode === 'worklist' && (
            <PriorityWorklist
              list={list}
              band={band}
              factor={factor}
              currency={currency}
              selectedId={selectedId}
              onSelect={onSelect}
              onDecision={onDecision}
            />
          )}
          {layoutMode === 'kanban' && (
            <StageKanban
              list={list}
              band={band}
              factor={factor}
              currency={currency}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          )}
        </div>
      </div>

      <div className="cr-detail-sticky">
        <InitiativeDetailPanel
          initiative={selected}
          band={band}
          factor={factor}
          currency={currency}
          provenance={provenance}
          provenanceLoading={provenanceLoading}
          milestones={milestones}
          milestonesLoading={milestonesLoading}
          onDecision={onDecision}
          onRecordActuals={onRecordActuals}
          actualsSaving={actualsSaving}
        />
      </div>
    </div>
  );
};
