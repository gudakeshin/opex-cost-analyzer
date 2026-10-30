import React, { useState } from 'react';
import { Drawer } from '../Common/Drawer';
import { Tabs } from '../Common/Tabs';
import { AuditLogPanel } from '../PageComponents/CostRoom/AuditLogPanel';
import { LogicTrace } from './LogicTrace';
import { ProvenanceList } from './ProvenanceList';
import { ConfidenceBadge } from './ConfidenceBadge';
import { useAuditLogQuery } from '../../api/hooks/useCostRoomQueries';
import type { AuditLogEntry, ProgressStep, QualitySignals } from '../../types';

const TRUST_TABS = [
  { id: 'audit', label: 'Audit' },
  { id: 'trace', label: 'Logic trace' },
  { id: 'provenance', label: 'Provenance' },
  { id: 'confidence', label: 'Confidence' },
];

interface TrustRailProps {
  open: boolean;
  onClose: () => void;
  localAudit: AuditLogEntry[];
  progressSteps?: ProgressStep[];
  runId?: string;
  degradedMode?: boolean;
  qualitySignals?: QualitySignals | null;
  provenanceSources?: Array<{ label: string; detail?: string; kind?: 'fact' | 'inference' }>;
  narrativeTag?: Record<string, unknown> | null;
}

export const TrustRail: React.FC<TrustRailProps> = ({
  open,
  onClose,
  localAudit,
  progressSteps,
  runId,
  degradedMode,
  qualitySignals,
  provenanceSources,
  narrativeTag,
}) => {
  const [tab, setTab] = useState('audit');
  const auditQuery = useAuditLogQuery(40, open);
  const integrity = auditQuery.data?.integrity ?? null;
  const serverAudit: AuditLogEntry[] = (auditQuery.data?.entries ?? []).map((e) => ({
    ts: String(e.ts ?? ''),
    message: String(e.event ?? e.message ?? JSON.stringify(e)),
    source: 'server' as const,
  }));

  const merged: AuditLogEntry[] = [
    ...localAudit.map((e) => ({ ...e, source: 'local' as const })),
    ...serverAudit,
  ].sort((a, b) => (b.ts || '').localeCompare(a.ts || ''));

  return (
    <Drawer open={open} title="Trust & observability" onClose={onClose}>
      <Tabs tabs={TRUST_TABS} activeId={tab} onChange={setTab} />
      <div className="mt-4">
        {tab === 'audit' && (
          <>
            {integrity && (
              <p className="text-xs text-brand-muted mb-3">
                Chain {integrity.chain_valid ? 'valid' : 'broken'} · {integrity.records} records
              </p>
            )}
            <AuditLogPanel auditLog={merged} />
          </>
        )}
        {tab === 'trace' && (
          <LogicTrace steps={progressSteps} runId={runId} degradedMode={degradedMode} />
        )}
        {tab === 'provenance' && (
          <ProvenanceList sources={provenanceSources} narrativeTag={narrativeTag} />
        )}
        {tab === 'confidence' && (
          <div className="space-y-4">
            <ConfidenceBadge signals={qualitySignals} />
            {qualitySignals && (
              <dl className="text-sm space-y-2">
                {qualitySignals.faithfulness_score != null && (
                  <div className="flex justify-between">
                    <dt className="text-brand-muted">Faithfulness</dt>
                    <dd className="font-mono tabular-nums">
                      {(qualitySignals.faithfulness_score * 100).toFixed(0)}%
                    </dd>
                  </div>
                )}
                {qualitySignals.relevance_score != null && (
                  <div className="flex justify-between">
                    <dt className="text-brand-muted">Relevance</dt>
                    <dd className="font-mono tabular-nums">
                      {(qualitySignals.relevance_score * 100).toFixed(0)}%
                    </dd>
                  </div>
                )}
                {qualitySignals.grounding_coverage != null && (
                  <div className="flex justify-between">
                    <dt className="text-brand-muted">Grounding</dt>
                    <dd className="font-mono tabular-nums">
                      {(qualitySignals.grounding_coverage * 100).toFixed(0)}%
                    </dd>
                  </div>
                )}
              </dl>
            )}
            {(qualitySignals?.unverified_figures?.length ?? 0) > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                <p className="font-semibold">Unverified figures in the narrative</p>
                <p className="mt-1">
                  These amounts match no value in the analysis outputs. They may be sums or ratios the model derived, or
                  they may be wrong — check them before quoting.
                </p>
                <ul className="mt-1.5 list-disc pl-4 font-mono">
                  {qualitySignals!.unverified_figures!.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-brand-muted">
              Deterministic ledger data is tagged Fact; model outputs are tagged AI inference.
            </p>
          </div>
        )}
      </div>
    </Drawer>
  );
};
