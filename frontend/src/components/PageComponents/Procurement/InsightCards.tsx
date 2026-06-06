import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { MetricTile } from '../../Common/MetricTile';
import { FactVsInferenceLabel } from '../../Common/FactVsInferenceLabel';
import { SessionFilesPanel } from './SessionFilesPanel';
import { AgentActivityPanel } from './AgentActivityPanel';
import { WorkbookIngestionPanel } from './WorkbookIngestionPanel';
import { MiniCategoryBar } from './SpendCharts';
import { sectorLabel } from '../../../constants/sectors';
import {
  extractInsightSnapshot,
  extractTopSavingsInitiatives,
  extractRootCauseFindings,
  extractAnomalyFlags,
  extractPeerGapDetails,
  formatEvidenceUsedLine,
  formatSpendAmount,
} from '../../../utils/analysisInsights';
import { CollapsibleDetail } from '../../Common/CollapsibleDetail';
import { Badge } from '../../Common/Badge';
import {
  showZeroSpendIngestionWarning,
} from '../../../utils/ingestionWarnings';
import type { ManifestFileEntry } from '../../../utils/sessionFiles';
import type { ProgressStep, SessionManifest, SessionResponse } from '../../../types';

interface InsightCardsProps {
  analysis: SessionResponse | null;
  manifest: SessionManifest | null;
  agentSteps?: ProgressStep[];
  agentRunId?: string;
  agentLoading?: boolean;
  agentDegraded?: boolean;
  pipelineLabel?: string;
  onOpenCostRoom?: () => void | Promise<void>;
}

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : null;
}

export const InsightCards: React.FC<InsightCardsProps> = ({
  analysis,
  manifest,
  agentSteps,
  agentRunId,
  agentLoading,
  agentDegraded,
  pipelineLabel,
  onOpenCostRoom,
}) => {
  const [showRaw, setShowRaw] = useState(false);

  const files = useMemo(
    () => (manifest?.files ?? []) as ManifestFileEntry[],
    [manifest?.files],
  );

  const industry = analysis?.industry || manifest?.industry || '';
  const company = analysis?.company_name || manifest?.company_name || '—';
  const engagementConflict = manifest?.engagement_sanity?.has_conflicts ?? false;

  const snapshot = useMemo(
    () => extractInsightSnapshot(analysis, manifest),
    [analysis, manifest],
  );

  const totalSpend =
    snapshot && snapshot.total_spend > 0
      ? formatSpendAmount(snapshot.total_spend, snapshot.reporting_currency)
      : null;

  const savingsHeadline = snapshot?.savings_headline ?? null;
  const abovePeerCount = snapshot?.peer_gap_count ?? 0;
  const comparisonCount = snapshot?.peer_comparison_count ?? 0;
  const topCategories = snapshot?.top_categories ?? [];

  const skillOutputs = analysis?.skill_outputs as Record<string, unknown> | undefined;
  const currency = snapshot?.reporting_currency ?? 'INR';
  const topSavings = useMemo(() => extractTopSavingsInitiatives(skillOutputs), [skillOutputs]);
  const rootCauseFindings = useMemo(() => extractRootCauseFindings(skillOutputs), [skillOutputs]);
  const anomalyFlags = useMemo(() => extractAnomalyFlags(skillOutputs), [skillOutputs]);
  const peerGapDetails = useMemo(() => extractPeerGapDetails(skillOutputs), [skillOutputs]);

  // SME critique data — keyed by "category_id|lever" for O(1) lookup
  const smeInitiativeCritiqueMap = useMemo(() => {
    const map = new Map<
      string,
      {
        maturity: string;
        verdict: string;
        criticalRisk: string;
        evidenceUsed: string | null;
        gaps: string[];
      }
    >();
    (snapshot?.sme_initiative_critiques ?? []).forEach((c) => {
      map.set(`${c.category_id}|${c.lever}`, {
        maturity: c.evidence_maturity,
        verdict: c.sme_verdict,
        criticalRisk: c.critical_risk,
        evidenceUsed: formatEvidenceUsedLine(c.evidence_signals),
        gaps: c.gaps ?? [],
      });
    });
    return map;
  }, [snapshot?.sme_initiative_critiques]);

  const dataValidator = analysis?.skill_outputs
    ? asRecord((analysis.skill_outputs as Record<string, unknown>)['data-validator'])
    : null;
  const validationIssues = Array.isArray(dataValidator?.issues)
    ? (dataValidator!.issues as unknown[])
    : [];

  const lineCount = Array.isArray(analysis?.normalized_spend)
    ? analysis!.normalized_spend!.length
    : undefined;

  const zeroSpendWarning = showZeroSpendIngestionWarning(manifest, analysis);

  const hasContent = analysis || files.length > 0 || agentSteps?.length || agentLoading;

  if (!hasContent) {
    return (
      <p className="text-sm text-brand-muted">
        Upload spend data to see session files and run analysis for insights.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <SessionFilesPanel files={files} />

      <WorkbookIngestionPanel
        modelManifest={manifest?.model_manifest ?? undefined}
        ingestionReport={manifest?.ingestion_report ?? undefined}
        industry={industry}
        lineCount={lineCount}
      />

      {zeroSpendWarning && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5">
          Uploaded data did not produce spend totals. Use <span className="font-medium">Run analysis</span>{' '}
          after upload, and check the sample files in <span className="font-mono">data/samples/</span> for
          supported layouts.
        </p>
      )}

      {(analysis || industry) && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FactVsInferenceLabel kind="fact" />
            <p className="text-xs font-semibold uppercase text-brand-muted">Engagement</p>
          </div>
          <div className="grid grid-cols-1 gap-3">
            <MetricTile
              label="Company"
              value={String(company)}
              change={
                engagementConflict
                  ? `${sectorLabel(industry)} · context mismatch`
                  : sectorLabel(industry)
              }
            />
            {engagementConflict && (
              <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5">
                Spend files may belong to a different company than this diagnostic session. See the
                banner above to align context.
              </p>
            )}
            {totalSpend && (
              <MetricTile label="Total spend (signal)" value={totalSpend} highlight />
            )}
            {comparisonCount > 0 && (
              <MetricTile
                label="Peer benchmark gaps"
                value={String(abovePeerCount)}
                change={`${comparisonCount} categories compared`}
              />
            )}
            {savingsHeadline && (
              <MetricTile
                label="Top savings signal"
                value={savingsHeadline}
                change="From savings model / value bridge"
              />
            )}
          </div>
        </div>
      )}

      {topCategories.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FactVsInferenceLabel kind="fact" />
            <p className="text-xs font-semibold uppercase text-brand-muted">Spend concentration</p>
          </div>
          {snapshot?.chart_data ? (
            <MiniCategoryBar
              chartData={snapshot.chart_data}
              currency={snapshot.reporting_currency}
            />
          ) : (
            <ul className="text-xs space-y-1.5">
              {topCategories.map((cat) => {
                const share =
                  cat.share_of_total != null
                    ? `${(Number(cat.share_of_total) * 100).toFixed(1)}%`
                    : '—';
                return (
                  <li key={String(cat.category_id)} className="flex justify-between gap-2">
                    <span className="text-brand-ink truncate">
                      {String(cat.category_name ?? cat.category_id)}
                    </span>
                    <span className="text-brand-muted shrink-0">{share}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {peerGapDetails.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FactVsInferenceLabel kind="benchmark_proxy" />
            <p className="text-xs font-semibold uppercase text-brand-muted">Above peer (P75+)</p>
          </div>
          <div className="grid grid-cols-1 gap-2">
            {peerGapDetails.map((gap) => (
              <MetricTile
                key={gap.category_id}
                label={gap.category_name}
                value={formatSpendAmount(gap.estimated_saving_amount, currency)}
                change={`${gap.percentile_band} · target ${gap.benchmark_target_pct.toFixed(1)}% of rev`}
              />
            ))}
          </div>
        </div>
      )}

      {topSavings.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FactVsInferenceLabel kind="inference" />
            <p className="text-xs font-semibold uppercase text-brand-muted">Savings opportunities</p>
          </div>
          <ul className="space-y-2">
            {topSavings.map((initiative, idx) => {
              const smeCritique = smeInitiativeCritiqueMap.get(
                `${initiative.category_id ?? initiative.category_name?.toLowerCase().replace(/\s+/g, '_')}|${initiative.lever}`,
              );
              const maturityTone = smeCritique
                ? smeCritique.maturity === 'validated'
                  ? 'success'
                  : smeCritique.maturity === 'supported'
                  ? 'success'
                  : smeCritique.maturity === 'indicative'
                  ? 'warning'
                  : 'error'
                : null;
              const hasMissingGaps = (smeCritique?.gaps?.length ?? 0) > 0;
              const maturityLabel = smeCritique
                ? smeCritique.maturity === 'validated'
                  ? 'Validated'
                  : smeCritique.maturity === 'supported'
                  ? 'Supported'
                  : smeCritique.maturity === 'indicative'
                  ? 'Indicative'
                  : hasMissingGaps && smeCritique.verdict !== 'proceed'
                  ? 'Needs probing'
                  : smeCritique.maturity === 'hypothesis'
                  ? 'Hypothesis'
                  : null
                : null;
              return (
                <li key={idx} className="space-y-0.5 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-medium text-brand-ink break-words">{initiative.category_name}</p>
                      <p className="text-[11px] text-brand-muted break-words">{initiative.lever_name}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-xs font-semibold text-brand-navy tabular-nums">
                        {formatSpendAmount(initiative.net_savings_3yr, currency)}
                      </p>
                      <div className="flex gap-1 justify-end mt-0.5">
                        <Badge
                          tone={
                            initiative.confidence === 'high'
                              ? 'success'
                              : initiative.confidence === 'low'
                              ? 'warning'
                              : 'default'
                          }
                        >
                          {initiative.confidence}
                        </Badge>
                        {maturityLabel && maturityTone && (
                          <Badge tone={maturityTone as 'success' | 'warning' | 'error' | 'default'}>
                            {maturityLabel}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                  {smeCritique?.evidenceUsed && (
                    <p className="text-[10px] text-emerald-700 leading-snug break-words">
                      Evidence used: {smeCritique.evidenceUsed}
                    </p>
                  )}
                  {smeCritique?.criticalRisk && smeCritique.verdict !== 'proceed' && (
                    <p className="text-[10px] text-amber-700 leading-snug break-words">
                      {smeCritique.gaps?.length ? 'Still needed: ' : ''}
                      {smeCritique.criticalRisk}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {rootCauseFindings.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FactVsInferenceLabel kind="inference" />
            <p className="text-xs font-semibold uppercase text-brand-muted">Root cause insights</p>
          </div>
          <CollapsibleDetail
            summary={`${rootCauseFindings[0].category_name}: ${rootCauseFindings[0].diagnosis}`}
            summaryClassName="text-xs"
          >
            <ul className="space-y-2">
              {rootCauseFindings.slice(1).map((f, idx) => (
                <li key={idx} className="text-xs">
                  <span className="font-medium text-brand-ink">{f.category_name}:</span>{' '}
                  <span className="text-brand-muted">{f.diagnosis}</span>
                </li>
              ))}
            </ul>
          </CollapsibleDetail>
        </div>
      )}

      {anomalyFlags.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FactVsInferenceLabel kind="inference" />
            <p className="text-xs font-semibold uppercase text-brand-muted">
              Anomaly flags ({anomalyFlags.length})
            </p>
          </div>
          <ul className="text-xs space-y-1.5">
            {anomalyFlags.map((flag) => (
              <li key={flag.category_id} className="flex items-start justify-between gap-2">
                <span className="text-brand-ink truncate">{flag.category_name}</span>
                <span className="text-amber-700 shrink-0 tabular-nums font-medium">
                  {formatSpendAmount(flag.estimated_saving_amount, currency)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {validationIssues.length > 0 && (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5">
          Data quality: {validationIssues.length} validation note(s) — review spend classification.
        </p>
      )}

      <AgentActivityPanel
        steps={agentSteps}
        runId={agentRunId}
        loading={agentLoading}
        degradedMode={agentDegraded}
        pipelineLabel={pipelineLabel}
      />

      {analysis && (
        <Link
          to="/cost-room"
          onClick={() => void onOpenCostRoom?.()}
          className="inline-flex text-sm font-semibold text-brand-navy hover:text-deloitte-green"
        >
          Open Cost Room →
        </Link>
      )}

      {analysis && (
        <>
          <button
            type="button"
            className="text-xs text-brand-muted underline"
            onClick={() => setShowRaw((v) => !v)}
          >
            {showRaw ? 'Hide' : 'Show'} developer JSON
          </button>
          {showRaw && (
            <pre className="p-3 bg-brand-surface-muted rounded text-xs overflow-auto max-h-48 font-mono border border-brand-border">
              {JSON.stringify(analysis, null, 2)}
            </pre>
          )}
        </>
      )}
    </div>
  );
};
