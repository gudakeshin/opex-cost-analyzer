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
  formatSpendAmount,
} from '../../../utils/analysisInsights';
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

  const dataValidator = analysis?.skill_outputs
    ? asRecord((analysis.skill_outputs as Record<string, unknown>)['data-validator'])
    : null;
  const validationIssues = Array.isArray(dataValidator?.issues)
    ? (dataValidator!.issues as unknown[])
    : [];

  const lineCount = Array.isArray(analysis?.normalized_spend)
    ? analysis!.normalized_spend!.length
    : undefined;

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
              change={sectorLabel(industry)}
            />
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

      {comparisonCount > 0 && analysis?.skill_outputs && (
        <div>
          <p className="text-xs font-semibold uppercase text-brand-muted mb-2">Above peer (P75+)</p>
          <ul className="text-xs space-y-1 max-h-32 overflow-y-auto">
            {(
              (asRecord((analysis.skill_outputs as Record<string, unknown>)['peer-benchmarker'])
                ?.comparisons as unknown[]) ?? []
            )
              .filter((c) => {
                const row = asRecord(c);
                const band = String(row?.percentile_band ?? '');
                return band.includes('P75') || band.includes('P90');
              })
              .slice(0, 5)
              .map((c) => {
                const row = asRecord(c)!;
                return (
                  <li key={String(row.category_id)} className="text-brand-ink">
                    {String(row.category_name ?? row.category_id)} — {String(row.percentile_band)}
                  </li>
                );
              })}
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
