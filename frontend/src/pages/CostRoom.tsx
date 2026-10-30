import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useConfirm } from '../hooks/useConfirm';
import '../styles/costRoom.css';
import { useGuardedNavigate } from '../hooks/useGuardedNavigate';
import { useUnsavedGuard } from '../hooks/useUnsavedGuard';
import { MainLayout } from '../components/Layout/MainLayout';
import { Card } from '../components/Common/Card';
import { Modal } from '../components/Common/Modal';
import { Input } from '../components/Common/Input';
import { Loader } from '../components/Common/Loader';
import { CostRoomTopbar } from '../components/PageComponents/CostRoom/CostRoomTopbar';
import { CostRoomHero } from '../components/PageComponents/CostRoom/CostRoomHero';
import { SignalStrip } from '../components/PageComponents/CostRoom/SignalStrip';
import {
  FilterBar,
  applyPortfolioFilters,
  defaultFilters,
  type LayoutMode,
} from '../components/PageComponents/CostRoom/FilterBar';
import type { PortfolioFilters } from '../components/PageComponents/CostRoom/FilterBar';
import { WorkArea } from '../components/PageComponents/CostRoom/work/WorkArea';
import { TrustFooter } from '../components/PageComponents/CostRoom/TrustFooter';
import { ConflictsPanel } from '../components/PageComponents/CostRoom/ConflictsPanel';
import { TrustRail } from '../components/Trust/TrustRail';
import { ExceptionInbox } from '../components/Trust/ExceptionInbox';
import { Alert } from '../components/Common/Alert';
import { ToastStack, type ToastItem } from '../components/PageComponents/CostRoom/primitives/ToastStack';
import { macroScenarioBps } from '../components/PageComponents/CostRoom/MacroScenariosList';
import type { ScenarioPreset } from '../components/PageComponents/CostRoom/ScenarioControls';
import { friendlyErrorMessage } from '../utils/errorMessages';
import {
  buildConflictExceptionItems,
  buildInitiativeExceptionItems,
  mergeExceptionItems,
  type ExceptionItem,
} from '../utils/exceptions';
import { toCr } from '../utils/formatInr';
import { TrendsTab } from '../components/PageComponents/CostRoom/TrendsTab';
import { BvaTab } from '../components/PageComponents/CostRoom/BvaTab';
import { PaymentTermsTab } from '../components/PageComponents/CostRoom/PaymentTermsTab';
import { CostToServeTab } from '../components/PageComponents/CostRoom/CostToServeTab';
import { useSession } from '../context/SessionContext';
import { useAudience } from '../context/AudienceContext';
import { getApiErrorMessage } from '../hooks/useApi';
import {
  useAddActualsMutation,
  useAuditLogLatestQuery,
  useConflictsQuery,
  useConsolidateMutation,
  useExportBusinessCaseMutation,
  useExportExcelMutation,
  useFpaTabQuery,
  useInitiativeRejectMutation,
  useInitiativeStageMutation,
  useInitiativesQuery,
  useMilestonesQuery,
  usePipelineSummaryQuery,
  useProvenanceQuery,
  useResolveConflictMutation,
  useSensitivityQuery,
} from '../api/hooks/useCostRoomQueries';
import {
  getBandSavings,
  isNeedsActionInitiative,
  scenarioFactorFromSensitivity,
} from '../utils/initiativeHelpers';
import { useExceptions } from '../context/ExceptionContext';
import type { AuditLogEntry, DataConflict, PercentileBand } from '../types';

function triggerDownload(exportPath: string, filename?: string) {
  const url = exportPath.startsWith('/api') ? exportPath : `/api/v1/exports/${exportPath.split('/').pop()}`;
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename ?? url.split('/').pop() ?? 'export';
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}

const FPA_TABS = [
  { id: 'trends', label: 'Trends' },
  { id: 'bva', label: 'Budget vs Actuals' },
  { id: 'payment-terms', label: 'Payment Terms' },
  { id: 'cost-to-serve', label: 'Cost to Serve' },
];

function EmptyPipeline({ onGoToAnalysis }: { onGoToAnalysis: () => void }) {
  return (
    <Card className="!p-12 text-center bg-white border-brand-border">
      <div className="max-w-md mx-auto">
        <h3 className="text-lg font-semibold text-brand-ink mb-2">No initiatives yet</h3>
        <p className="text-sm text-brand-muted mb-6">
          Upload spend data in the Analysis tab and run OPAR analysis. Initiatives are seeded
          automatically when analysis completes.
        </p>
        <button
          type="button"
          onClick={onGoToAnalysis}
          className="px-5 py-2.5 rounded-xl bg-deloitte-green text-black text-sm font-medium"
        >
          Go to Analysis →
        </button>
      </div>
    </Card>
  );
}

export default function CostRoom() {
  const { sessionId, engagementId, engagement, ensureSession, syncEngagementFromAnalysis, refreshSessionAnalysis, sessionAnalysis } =
    useSession();
  const { isExecutive } = useAudience();
  const navigate = useGuardedNavigate();

  const [activeTab, setActiveTab] = useState('trends');
  const [fpaOpen, setFpaOpen] = useState(!isExecutive);
  const [percentileBand, setPercentileBand] = useState<PercentileBand>('p50');
  const [scenario, setScenario] = useState<ScenarioPreset>('base');
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('split');
  const [filters, setFilters] = useState<PortfolioFilters>(() => ({
    ...defaultFilters,
    needsActionOnly: !isExecutive,
  }));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirm, confirmDialog] = useConfirm();

  // The Cost Room has its own light colour system (--cr-* tokens); the generic dark layer would clash
  // with it, so it stays light here and the user's theme choice is restored on leaving.
  useEffect(() => {
    const root = document.documentElement;
    const wasDark = root.classList.contains('dark');
    root.classList.remove('dark');
    return () => {
      if (wasDark) root.classList.add('dark');
    };
  }, []);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectTargetId, setRejectTargetId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectReasonMissing, setRejectReasonMissing] = useState(false);
  useUnsavedGuard('cost-room-reject', rejectModalOpen && rejectReason.trim().length > 0);
  const [exportNotice, setExportNotice] = useState<string | null>(null);
  const [trustOpen, setTrustOpen] = useState(false);
  const [conflictNotice, setConflictNotice] = useState<string | null>(null);
  const [highlightConflicts, setHighlightConflicts] = useState(false);
  const [inboxDismissed, setInboxDismissed] = useState(false);
  const conflictsSectionRef = useRef<HTMLDivElement>(null);
  const workSectionRef = useRef<HTMLDivElement>(null);
  const { setItems: setExceptionItems, items: exceptionItems } = useExceptions();

  const initiativesQuery = useInitiativesQuery(engagementId);
  const summaryQuery = usePipelineSummaryQuery(engagementId);
  const sensitivityQuery = useSensitivityQuery(sessionId, scenario);
  const conflictsQuery = useConflictsQuery(sessionId, !isExecutive);
  const trendsQuery = useFpaTabQuery('trends', sessionId, fpaOpen && !isExecutive && activeTab === 'trends');
  const bvaQuery = useFpaTabQuery('bva', sessionId, fpaOpen && !isExecutive && activeTab === 'bva');
  const paymentTermsQuery = useFpaTabQuery(
    'payment-terms',
    sessionId,
    fpaOpen && !isExecutive && activeTab === 'payment-terms',
  );
  const costToServeQuery = useFpaTabQuery(
    'cost-to-serve',
    sessionId,
    fpaOpen && !isExecutive && activeTab === 'cost-to-serve',
  );
  const fpaTabQueries: Record<string, { isFetching: boolean; refetch: () => unknown }> = {
    trends: trendsQuery,
    bva: bvaQuery,
    'payment-terms': paymentTermsQuery,
    'cost-to-serve': costToServeQuery,
  };
  const activeFpaQuery = fpaTabQueries[activeTab];
  const milestonesQuery = useMilestonesQuery(selectedId);
  const provenanceQuery = useProvenanceQuery(selectedId);
  const auditLogQuery = useAuditLogLatestQuery(initiativesQuery.dataUpdatedAt);

  const initiativeStageMutation = useInitiativeStageMutation(engagementId);
  const initiativeRejectMutation = useInitiativeRejectMutation(engagementId);
  const addActualsMutation = useAddActualsMutation(engagementId);
  const consolidateMutation = useConsolidateMutation(engagementId, sessionId);
  const resolveConflictMutation = useResolveConflictMutation(engagementId, sessionId);
  const exportBusinessCaseMutation = useExportBusinessCaseMutation(sessionId);
  const exportExcelMutation = useExportExcelMutation(sessionId);

  const initiatives = useMemo(() => initiativesQuery.data ?? [], [initiativesQuery.data]);
  const summary = summaryQuery.data ?? null;
  const sensitivity = sensitivityQuery.data ?? null;
  const loading = initiativesQuery.isFetching || summaryQuery.isFetching;
  const milestones = milestonesQuery.data ?? null;
  const milestonesLoading = milestonesQuery.isFetching;
  const provenance = provenanceQuery.data ?? null;
  const provenanceLoading = provenanceQuery.isFetching;
  const conflicts = conflictsQuery.data ?? null;
  const conflictsLoading = conflictsQuery.isFetching;
  const conflictsError = conflictsQuery.error ? getApiErrorMessage(conflictsQuery.error) : null;
  const actualsSaving = addActualsMutation.isPending;
  const businessCaseLoading = exportBusinessCaseMutation.isPending;
  const excelExportLoading = exportExcelMutation.isPending;
  const tabLoading = activeFpaQuery?.isFetching ? activeTab : null;
  const tabErrors: Record<string, string | null> = {
    trends: trendsQuery.error ? getApiErrorMessage(trendsQuery.error) : null,
    bva: bvaQuery.error ? getApiErrorMessage(bvaQuery.error) : null,
    'payment-terms': paymentTermsQuery.error ? getApiErrorMessage(paymentTermsQuery.error) : null,
    'cost-to-serve': costToServeQuery.error ? getApiErrorMessage(costToServeQuery.error) : null,
  };
  const serverAuditCount = auditLogQuery.data
    ? auditLogQuery.data.integrity?.records ?? auditLogQuery.data.entries?.length ?? 0
    : 0;
  const chainValid = auditLogQuery.data?.integrity?.chain_valid;
  const actingConflictId = resolveConflictMutation.isPending
    ? resolveConflictMutation.variables?.conflictId ?? null
    : null;
  const lastSync = initiativesQuery.dataUpdatedAt
    ? new Date(initiativesQuery.dataUpdatedAt).toISOString()
    : new Date().toISOString();

  const factor = useMemo(
    () => scenarioFactorFromSensitivity(scenario, sensitivity),
    [scenario, sensitivity],
  );

  const filteredInitiatives = useMemo(
    () => applyPortfolioFilters(initiatives, filters),
    [initiatives, filters],
  );

  const liveInitiatives = useMemo(
    () => initiatives.filter((x) => x.stage !== 'rejected' && x.stage !== 'deferred'),
    [initiatives],
  );

  const needsActionCount = useMemo(
    () => liveInitiatives.filter(isNeedsActionInitiative).length,
    [liveInitiatives],
  );

  // Tracks the topbar P10/P50/P90 toggle so the hero EBITDA-bps metric stays
  // consistent with the per-initiative figures shown elsewhere on the page.
  const portfolioBandCr = useMemo(
    () => filteredInitiatives.reduce((sum, r) => sum + getBandSavings(r, percentileBand), 0),
    [filteredInitiatives, percentileBand],
  );

  const baseEbitdaBps = useMemo(() => {
    const revenueCr = engagement.annual_revenue_cr ?? 25000;
    if (revenueCr <= 0) return 0;
    const portfolioCr = toCr(portfolioBandCr, engagement.currency);
    return Math.round((portfolioCr / revenueCr) * 10000);
  }, [portfolioBandCr, engagement.annual_revenue_cr, engagement.currency]);

  const ebitdaBps = useMemo(() => macroScenarioBps(baseEbitdaBps, scenario), [baseEbitdaBps, scenario]);

  const toast = useCallback((msg: string) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((ts) => [...ts, { id, message: msg }]);
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 2600);
  }, []);

  const appendAudit = useCallback((message: string) => {
    setAuditLog((log) => [{ ts: new Date().toISOString(), message }, ...log.slice(0, 49)]);
  }, []);

  useEffect(() => {
    ensureSession().catch(() => undefined);
    syncEngagementFromAnalysis().catch(() => undefined);
    refreshSessionAnalysis().catch(() => undefined);
  }, [ensureSession, syncEngagementFromAnalysis, refreshSessionAnalysis]);

  useEffect(() => {
    setSelectedId((prev) => prev ?? initiatives[0]?.initiative_id ?? null);
  }, [initiatives]);

  useEffect(() => {
    const err = initiativesQuery.error ?? summaryQuery.error;
    if (err) setError(getApiErrorMessage(err));
  }, [initiativesQuery.error, summaryQuery.error]);

  useEffect(() => {
    if (isExecutive) {
      setFilters((f) => ({ ...f, needsActionOnly: false }));
    }
  }, [isExecutive]);

  useEffect(() => {
    setExceptionItems(
      mergeExceptionItems(
        buildInitiativeExceptionItems(initiatives),
        buildConflictExceptionItems(conflicts),
      ),
    );
  }, [initiatives, conflicts, setExceptionItems]);

  const selectInitiative = useCallback((id: string) => {
    setSelectedId(id);
  }, []);

  const handleExceptionAction = useCallback((item: ExceptionItem) => {
    setInboxDismissed(false);
    if (item.action === 'conflicts') {
      setHighlightConflicts(true);
      conflictsSectionRef.current?.scrollIntoView({ behavior: 'smooth' });
      window.setTimeout(() => setHighlightConflicts(false), 4000);
    } else if (item.action === 'portfolio') {
      workSectionRef.current?.scrollIntoView({ behavior: 'smooth' });
      if (item.id) selectInitiative(item.id);
      // Drill-through from the exception inbox into an initiative's detail panel
      // (which surfaces its AqsBadge) — record it like every other page action
      // so a low-AQS review is traceable in the audit log.
      appendAudit(`exception_drill_through: ${item.title} — ${item.detail}`);
    }
  }, [selectInitiative, appendAudit]);

  const acceptInit = async (initiativeId: string) => {
    const target = initiatives.find((x) => x.initiative_id === initiativeId);
    const ok = await confirm({
      title: 'Commit this initiative?',
      message: `“${target?.lever ?? initiativeId}” will count toward committed savings and be tracked against actuals. You can move it back to another stage later.`,
      confirmLabel: 'Commit',
    });
    if (!ok) return;
    try {
      await initiativeStageMutation.mutateAsync({ initiativeId, stage: 'committed' });
      const init = initiatives.find((x) => x.initiative_id === initiativeId);
      toast(`Committed · ${init?.lever ?? initiativeId}`);
      appendAudit(`acceptInit: ${initiativeId} → committed`);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const deferInit = async (initiativeId: string) => {
    const target = initiatives.find((x) => x.initiative_id === initiativeId);
    const ok = await confirm({
      title: 'Defer this initiative?',
      message: `“${target?.lever ?? initiativeId}” will leave the active pipeline until you bring it back.`,
      confirmLabel: 'Defer',
    });
    if (!ok) return;
    try {
      await initiativeStageMutation.mutateAsync({ initiativeId, stage: 'deferred' });
      const init = initiatives.find((x) => x.initiative_id === initiativeId);
      toast(`Deferred · ${init?.lever ?? initiativeId}`);
      appendAudit(`deferInit: ${initiativeId} → deferred`);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const rejectInit = (initiativeId: string) => {
    setRejectTargetId(initiativeId);
    setRejectReason('');
    setRejectReasonMissing(false);
    setRejectModalOpen(true);
  };

  const confirmReject = async () => {
    if (!rejectTargetId) return;
    if (!rejectReason.trim()) {
      setRejectReasonMissing(true);
      return;
    }
    try {
      await initiativeRejectMutation.mutateAsync({
        initiativeId: rejectTargetId,
        reason: rejectReason.trim(),
      });
      const init = initiatives.find((x) => x.initiative_id === rejectTargetId);
      toast(`Rejected · ${init?.lever ?? rejectTargetId}`);
      appendAudit(`rejectInit: ${rejectTargetId}`);
      setRejectModalOpen(false);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const handleDecision = (id: string, stage: string) => {
    if (stage === 'committed') void acceptInit(id);
    else if (stage === 'deferred') void deferInit(id);
    else if (stage === 'rejected') rejectInit(id);
  };

  const addActuals = useCallback(
    async (initiativeId: string, amount: number) => {
      try {
        await addActualsMutation.mutateAsync({ initiativeId, amount });
        const init = initiatives.find((x) => x.initiative_id === initiativeId);
        toast(`Actuals updated · ${init?.lever ?? initiativeId}`);
        appendAudit(`actuals_recorded: ${initiativeId}`);
      } catch (err) {
        setError(getApiErrorMessage(err));
      }
    },
    [appendAudit, initiatives, addActualsMutation, toast],
  );

  const actOnConflict = async (conflict: DataConflict, strategy: string, auditLabel: string) => {
    if (!sessionId || !conflict.conflict_id) return;
    setConflictNotice(null);
    try {
      await resolveConflictMutation.mutateAsync({ conflictId: conflict.conflict_id, strategy });
      toast(`Conflict resolved · ${conflict.title ?? conflict.conflict_id}`);
      appendAudit(`${auditLabel}: ${conflict.conflict_id}`);
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const exportBusinessCase = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await exportBusinessCaseMutation.mutateAsync();
      appendAudit('business_case_export_requested');
      if (res.exports?.docx) {
        triggerDownload(res.exports.docx, `${sessionId}_business_case.docx`);
        setExportNotice('Business case downloaded.');
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }, [sessionId, appendAudit, exportBusinessCaseMutation]);

  const exportExcel = useCallback(async () => {
    if (!sessionId) return;
    try {
      const res = await exportExcelMutation.mutateAsync();
      appendAudit('export_excel_requested');
      if (res.export_url) {
        triggerDownload(res.export_url, res.filename);
        setExportNotice('Portfolio Excel export downloaded.');
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }, [sessionId, appendAudit, exportExcelMutation]);

  const handleConsolidate = useCallback(async () => {
    if (!sessionId) return;
    try {
      await consolidateMutation.mutateAsync();
      toast('Entities consolidated');
      appendAudit('consolidation_run');
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }, [sessionId, appendAudit, consolidateMutation, toast]);

  const auditCountTotal = serverAuditCount + auditLog.length;
  const friendlyError = error ? friendlyErrorMessage(error) : null;
  const lastSyncLabel = new Date(lastSync).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  const realizedCr = summary?.stage_totals?.realized?.net_npv
    ? toCr(summary.stage_totals.realized.net_npv, engagement.currency)
    : undefined;

  const trustProgressSteps = useMemo(() => {
    const outputs = sessionAnalysis?.skill_outputs;
    if (!outputs || typeof outputs !== 'object') return undefined;
    return Object.keys(outputs).map((skill) => ({
      phase: 'skill',
      message: skill,
      status: 'complete',
    }));
  }, [sessionAnalysis]);

  const trustQualitySignals = useMemo(() => {
    const synth = sessionAnalysis?.skill_outputs?.['analysis-synthesizer'] as
      | { quality_signals?: import('../types').QualitySignals }
      | undefined;
    return synth?.quality_signals ?? null;
  }, [sessionAnalysis]);

  const trustDegraded = useMemo(() => {
    const outputs = sessionAnalysis?.skill_outputs;
    if (!outputs || typeof outputs !== 'object') return false;
    return Object.values(outputs).some(
      (o) =>
        o &&
        typeof o === 'object' &&
        (o as { degraded_reason?: string }).degraded_reason === 'provider_unavailable',
    );
  }, [sessionAnalysis]);

  const trustProvenance = useMemo(
    () => [
      { label: engagement.company_name, detail: 'Engagement manifest', kind: 'fact' as const },
      {
        label: 'Spend & pipeline',
        detail: sessionAnalysis ? 'OPAR analysis + initiative model' : 'Awaiting analysis',
        kind: 'inference' as const,
      },
      ...(sensitivity?.methodology_note
        ? [{ label: 'Sensitivity model', detail: String(sensitivity.methodology_note).slice(0, 120), kind: 'inference' as const }]
        : []),
    ],
    [engagement.company_name, sessionAnalysis, sensitivity],
  );

  return (
    <MainLayout variant={isExecutive ? 'executive' : 'default'} hideHeader>
      {confirmDialog}
      <div className="cost-room-page space-y-[var(--cr-gap)] min-w-0">
        <CostRoomTopbar
          percentileBand={percentileBand}
          onBandChange={setPercentileBand}
          scenario={scenario}
          onScenarioChange={setScenario}
        />

        {friendlyError && (
          <Alert variant="error" title={friendlyError.title} onDismiss={() => setError(null)}>
            {friendlyError.detail}
          </Alert>
        )}
        {conflictNotice && (
          <Alert variant="success" title="Conflict action recorded" onDismiss={() => setConflictNotice(null)}>
            {conflictNotice}
          </Alert>
        )}
        {exportNotice && (
          <Alert variant="success" title="Export ready" onDismiss={() => setExportNotice(null)}>
            {exportNotice}
          </Alert>
        )}

        {!loading && initiatives.length === 0 ? (
          <EmptyPipeline onGoToAnalysis={() => navigate('/')} />
        ) : (
          <>
            {loading ? (
              <Loader label="Loading pipeline…" />
            ) : (
              <>
                <div
                  title="Percentile band: p10 = conservative case, p50 = base case, p90 = stretch case. Toggle in the topbar changes the hero metrics and per-initiative figures together."
                >
                  <CostRoomHero
                    initiatives={filteredInitiatives}
                    percentileBand={percentileBand}
                    scenario={scenario}
                    scenarioFactor={factor}
                    ebitdaBps={ebitdaBps}
                    currency={engagement.currency}
                    revenueCr={engagement.annual_revenue_cr}
                  />
                </div>
                <SignalStrip
                  initiatives={initiatives}
                  currency={engagement.currency}
                  realizedCr={realizedCr}
                  onNeedsActionClick={() => {
                    setFilters((f) => ({ ...f, needsActionOnly: true }));
                    workSectionRef.current?.scrollIntoView({ behavior: 'smooth' });
                  }}
                />
              </>
            )}

            <FilterBar
              initiatives={initiatives}
              filters={filters}
              onChange={setFilters}
              filteredCount={filteredInitiatives.length}
              needsActionCount={needsActionCount}
              layoutMode={layoutMode}
              onLayoutModeChange={setLayoutMode}
              executive={isExecutive}
            />

            {!isExecutive && !inboxDismissed && exceptionItems.length > 0 && (
              <ExceptionInbox
                items={exceptionItems}
                onDismiss={() => setInboxDismissed(true)}
                onItemAction={handleExceptionAction}
                compact
              />
            )}

            <div ref={workSectionRef} id="initiative-portfolio" className="scroll-mt-24 min-w-0">
              {!loading && (
                <WorkArea
                  list={filteredInitiatives}
                  layoutMode={isExecutive ? 'split' : layoutMode}
                  band={percentileBand}
                  factor={factor}
                  currency={engagement.currency}
                  executive={isExecutive}
                  selectedId={selectedId}
                  expandedId={expandedId}
                  onSelect={selectInitiative}
                  onToggleExpand={(id) => setExpandedId((e) => (e === id ? null : id))}
                  onDecision={handleDecision}
                  provenance={provenance}
                  provenanceLoading={provenanceLoading}
                  milestones={milestones}
                  milestonesLoading={milestonesLoading}
                  onRecordActuals={
                    selectedId ? (amount) => addActuals(selectedId, amount) : undefined
                  }
                  actualsSaving={actualsSaving}
                  onConsolidate={handleConsolidate}
                  showConsolidate={!isExecutive && Boolean(sessionId)}
                />
              )}
            </div>
          </>
        )}

        {!isExecutive && sessionId && (
          <div
            ref={conflictsSectionRef}
            id="data-conflicts"
            className={`scroll-mt-24 transition-shadow duration-500 ${
              highlightConflicts ? 'ring-2 ring-amber-400 ring-offset-2 rounded-[var(--cr-r)]' : ''
            }`}
          >
            <ConflictsPanel
              summary={conflicts}
              loading={conflictsLoading}
              error={conflictsError}
              onRetry={() => void conflictsQuery.refetch()}
              onApplyRecommendation={(c) =>
                c.resolution_strategy &&
                c.resolution_strategy !== 'escalate' &&
                void actOnConflict(c, c.resolution_strategy, 'conflict_apply')
              }
              onFlagForReview={(c) => void actOnConflict(c, 'escalate', 'conflict_flag')}
              actingConflictId={actingConflictId}
            />
          </div>
        )}

        {!isExecutive && (
          <div className="cr-card overflow-hidden min-w-0">
            <div className="cr-card-h">
              <h2 className="text-sm font-bold">FP&amp;A detail</h2>
              <button
                type="button"
                className="text-xs text-[var(--cr-gray)] hover:text-[var(--cr-ink)]"
                onClick={() => {
                  setFpaOpen((o) => {
                    if (!o) setActiveTab('trends');
                    return !o;
                  });
                }}
              >
                {fpaOpen ? 'Hide' : 'Show'}
              </button>
            </div>
            {fpaOpen && (
              <div className="p-5 min-w-0">
                <div className="cr-fpa-tabs mb-4">
                  {FPA_TABS.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      className={activeTab === t.id ? 'cr-on' : ''}
                      onClick={() => setActiveTab(t.id)}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => activeFpaQuery?.refetch()}
                  disabled={tabLoading === activeTab}
                  className="mb-4 text-xs border border-[var(--cr-line)] rounded-[var(--cr-r-sm)] px-3 py-1.5 bg-white disabled:opacity-50"
                >
                  {tabLoading === activeTab ? 'Refreshing…' : 'Refresh'}
                </button>
                {activeTab === 'trends' && (
                  <TrendsTab data={trendsQuery.data ?? null} loading={tabLoading === 'trends'} error={tabErrors.trends ?? null} currency={engagement.currency} />
                )}
                {activeTab === 'bva' && (
                  <BvaTab data={bvaQuery.data ?? null} loading={tabLoading === 'bva'} error={tabErrors.bva ?? null} currency={engagement.currency} />
                )}
                {activeTab === 'payment-terms' && (
                  <PaymentTermsTab data={paymentTermsQuery.data ?? null} loading={tabLoading === 'payment-terms'} error={tabErrors['payment-terms'] ?? null} currency={engagement.currency} />
                )}
                {activeTab === 'cost-to-serve' && (
                  <CostToServeTab data={costToServeQuery.data ?? null} loading={tabLoading === 'cost-to-serve'} error={tabErrors['cost-to-serve'] ?? null} currency={engagement.currency} />
                )}
              </div>
            )}
          </div>
        )}

        <TrustFooter
          auditCount={auditCountTotal}
          lastSync={lastSyncLabel}
          chainValid={chainValid}
          onOpenAudit={() => setTrustOpen(true)}
          onExportDeck={exportBusinessCase}
          onExportExcel={exportExcel}
          deckLoading={businessCaseLoading}
          excelLoading={excelExportLoading}
        />
      </div>

      <ToastStack toasts={toasts} />

      <TrustRail
        open={trustOpen}
        onClose={() => setTrustOpen(false)}
        localAudit={auditLog}
        progressSteps={trustProgressSteps}
        runId={sessionId ?? undefined}
        degradedMode={trustDegraded}
        qualitySignals={trustQualitySignals}
        provenanceSources={trustProvenance}
      />

      <Modal
        open={rejectModalOpen}
        title="Reject initiative"
        onClose={() => setRejectModalOpen(false)}
        onConfirm={confirmReject}
        confirmLabel="Reject"
        confirmVariant="danger"
      >
        <Input
          label="Reason (required)"
          value={rejectReason}
          onChange={(e) => {
            setRejectReason(e.target.value);
            setRejectReasonMissing(false);
          }}
          placeholder="Why is this initiative rejected?"
        />
        {rejectReasonMissing && (
          <p role="alert" className="mt-2 text-sm text-error">
            Enter a reason to reject this initiative.
          </p>
        )}
      </Modal>
    </MainLayout>
  );
}
