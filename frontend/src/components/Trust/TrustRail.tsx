import React, { useEffect, useState } from 'react';
import { Drawer } from '../Common/Drawer';
import { Tabs } from '../Common/Tabs';
import { AuditLogPanel } from '../PageComponents/CostRoom/AuditLogPanel';
import { LogicTrace } from './LogicTrace';
import { ProvenanceList } from './ProvenanceList';
import { ConfidenceBadge } from './ConfidenceBadge';
import { apiGet } from '../../hooks/useApi';
import type {
  AuditLogEntry,
  ComplianceAuditResponse,
  ProgressStep,
  QualitySignals,
} from '../../types';

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
  const [serverAudit, setServerAudit] = useState<AuditLogEntry[]>([]);
  const [integrity, setIntegrity] = useState<ComplianceAuditResponse['integrity'] | null>(null);

  useEffect(() => {
    if (!open) return;
    apiGet<ComplianceAuditResponse>('/api/compliance/audit-log?limit=40')
      .then((res) => {
        setIntegrity(res.integrity);
        setServerAudit(
          res.entries.map((e) => ({
            ts: String(e.ts ?? ''),
            message: String(e.event ?? e.message ?? JSON.stringify(e)),
            source: 'server' as const,
          })),
        );
      })
      .catch(() => setServerAudit([]));
  }, [open]);

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
            <p className="text-xs text-brand-muted">
              Deterministic ledger data is tagged Fact; model outputs are tagged AI inference.
            </p>
          </div>
        )}
      </div>
    </Drawer>
  );
};
