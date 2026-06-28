import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styles/costRoom.css';
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
import { apiGet, apiPost, apiPut, getApiErrorMessage } from '../hooks/useApi';
import {
  getBandSavings,
  isNeedsActionInitiative,
  scenarioFactorFromSensitivity,
} from '../utils/initiativeHelpers';
import { useExceptions } from '../context/ExceptionContext';
import type {
  ComplianceAuditResponse,
  ConflictSpendImpact,
  ConflictSummary,
  DataConflict,
  AuditLogEntry,
  BvaResponse,
  CostToServeResponse,
  Initiative,
  InitiativeProvenance,
  PaymentTermsResponse,
  PercentileBand,
  PipelineSummary,
  SensitivityResponse,
  TrendsResponse,
} from '../types';

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

function scenarioExecutionRate(scenario: ScenarioPreset): number | undefined {
  if (scenario === 'conservative') return 0.6;
  if (scenario === 'accelerated') return 0.9;
  return undefined;
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
          className="px-5 py-2.5 rounded-xl bg-deloitte-green text-white text-sm font-medium"
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
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState('trends');
  const [fpaOpen, setFpaOpen] = useState(!isExecutive);
  const [percentileBand, setPercentileBand] = useState<PercentileBand>('p50');
  const [scenario, setScenario] = useState<ScenarioPreset>('base');
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('split');
  const [filters, setFilters] = useState<PortfolioFilters>(() => ({
    ...defaultFilters,
    needsActionOnly: !isExecutive,
  }));
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const [summary, setSummary] = useState<PipelineSummary | null>(null);
  const [sensitivity, setSensitivity] = useState<SensitivityResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectTargetId, setRejectTargetId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [trends, setTrends] = useState<TrendsResponse | null>(null);
  const [bva, setBva] = useState<BvaResponse | null>(null);
  const [paymentTerms, setPaymentTerms] = useState<PaymentTermsResponse | null>(null);
  const [costToServe, setCostToServe] = useState<CostToServeResponse | null>(null);
  const [milestones, setMilestones] = useState<Record<string, unknown>[] | null>(null);
  const [milestonesLoading, setMilestonesLoading] = useState(false);
  const [provenance, setProvenance] = useState<InitiativeProvenance | null>(null);
  const [provenanceLoading, setProvenanceLoading] = useState(false);
  const [actualsSaving, setActualsSaving] = useState(false);
  const [businessCaseLoading, setBusinessCaseLoading] = useState(false);
  const [excelExportLoading, setExcelExportLoading] = useState(false);
  const [exportNotice, setExportNotice] = useState<string | null>(null);
  const [tabLoading, setTabLoading] = useState<string | null>(null);
  const [tabErrors, setTabErrors] = useState<Record<string, string | null>>({});
  const [lastSync, setLastSync] = useState(() => new Date().toISOString());
  const [trustOpen, setTrustOpen] = useState(false);
  const [serverAuditCount, setServerAuditCount] = useState(0);
  const [chainValid, setChainValid] = useState<boolean | undefined>(undefined);
  const [conflicts, setConflicts] = useState<ConflictSummary | null>(null);
  const [conflictsLoading, setConflictsLoading] = useState(false);
  const [conflictsError, setConflictsError] = useState<string | null>(null);
  const [actingConflictId, setActingConflictId] = useState<string | null>(null);
  const [conflictNotice, setConflictNotice] = useState<string | null>(null);
  const [highlightConflicts, setHighlightConflicts] = useState(false);
  const [inboxDismissed, setInboxDismissed] = useState(false);
  const conflictsSectionRef = useRef<HTMLDivElement>(null);
  const workSectionRef = useRef<HTMLDivElement>(null);
  const { setItems: setExceptionItems, items: exceptionItems } = useExceptions();

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

  const portfolioP50Cr = useMemo(
    () => filteredInitiatives.reduce((sum, r) => sum + getBandSavings(r, 'p50'), 0),
    [filteredInitiatives],
  );

  const baseEbitdaBps = useMemo(() => {
    const revenueCr = engagement.annual_revenue_cr ?? 25000;
    if (revenueCr <= 0) return 0;
    const portfolioCr = toCr(portfolioP50Cr, engagement.currency);
    return Math.round((portfolioCr / revenueCr) * 10000);
  }, [portfolioP50Cr, engagement.annual_revenue_cr, engagement.currency]);

  const ebitdaBps = useMemo(() => macroScenarioBps(baseEbitdaBps, scenario), [baseEbitdaBps, scenario]);

  const toast = useCallback((msg: string) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((ts) => [...ts, { id, message: msg }]);
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), 2600);
  }, []);

  const appendAudit = useCallback((message: string) => {
    setAuditLog((log) => [{ ts: new Date().toISOString(), message }, ...log.slice(0, 49)]);
  }, []);

  const normalizeInitiative = (row: Initiative): Initiative => ({
    ...row,
    aqs: row.aqs ?? row.assumption_quality_score,
    owner_name: row.owner_name ?? row.owner_role,
  });

  const loadPipeline = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ qualified_only: 'true' });
      if (engagementId) params.set('engagement_id', engagementId);
      const qs = `?${params.toString()}`;
      const [initRes, sumRes] = await Promise.all([
        apiGet<{ initiatives: Initiative[] }>(`/api/v1/initiatives${qs}`),
        apiGet<PipelineSummary>(`/api/v1/pipeline/summary${qs}`),
      ]);
      const rows = initRes.initiatives.map(normalizeInitiative);
      setInitiatives(rows);
      setSummary(sumRes);
      setLastSync(new Date().toISOString());
      setSelectedId((prev) => prev ?? rows[0]?.initiative_id ?? null);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  const loadSensitivity = useCallback(async () => {
    if (!sessionId) return;
    try {
      const execRate = scenarioExecutionRate(scenario);
      const qs = execRate != null ? `?execution_rate_pct=${execRate}` : '';
      const data = await apiGet<SensitivityResponse>(`/api/v1/sensitivity/${sessionId}${qs}`);
      setSensitivity(data);
    } catch {
      setSensitivity(null);
    }
  }, [sessionId, scenario]);

  useEffect(() => {
    ensureSession().catch(() => undefined);
    loadPipeline();
    syncEngagementFromAnalysis().catch(() => undefined);
    refreshSessionAnalysis().catch(() => undefined);
  }, [ensureSession, loadPipeline, syncEngagementFromAnalysis, refreshSessionAnalysis]);

  useEffect(() => {
    loadSensitivity();
  }, [loadSensitivity]);

  useEffect(() => {
    if (isExecutive) {
      setFilters((f) => ({ ...f, needsActionOnly: false }));
    }
  }, [isExecutive]);

  useEffect(() => {
    apiGet<ComplianceAuditResponse>('/api/v1/compliance/audit-log?limit=1')
      .then((res) => {
        setServerAuditCount(res.integrity?.records ?? res.entries?.length ?? 0);
        setChainValid(res.integrity?.chain_valid);
      })
      .catch(() => setServerAuditCount(0));
  }, [lastSync]);

  const loadConflicts = useCallback(async () => {
    if (!sessionId || isExecutive) return;
    setConflictsLoading(true);
    setConflictsError(null);
    try {
      setConflicts(await apiGet<ConflictSummary>(`/api/v1/conflicts/${sessionId}`));
    } catch (err) {
      setConflicts(null);
      setConflictsError(getApiErrorMessage(err));
    } finally {
      setConflictsLoading(false);
    }
  }, [sessionId, isExecutive]);

  useEffect(() => {
    loadConflicts();
  }, [loadConflicts]);

  useEffect(() => {
    setExceptionItems(
      mergeExceptionItems(
        buildInitiativeExceptionItems(initiatives),
        buildConflictExceptionItems(conflicts),
      ),
    );
  }, [initiatives, conflicts, setExceptionItems]);

  const loadFpaTab = useCallback(
    async (tab: string, force = false) => {
      if (!sessionId) return;
      const cached =
        tab === 'trends' ? trends
        : tab === 'bva' ? bva
        : tab === 'payment-terms' ? paymentTerms
        : tab === 'cost-to-serve' ? costToServe
        : null;
      if (cached && !force) return;
      setTabLoading(tab);
      setTabErrors((prev) => ({ ...prev, [tab]: null }));
      try {
        if (tab === 'trends') {
          setTrends(await apiGet<TrendsResponse>(`/api/v1/trends/${sessionId}`));
        } else if (tab === 'bva') {
          setBva(await apiGet<BvaResponse>(`/api/v1/bva/${sessionId}`));
        } else if (tab === 'payment-terms') {
          setPaymentTerms(await apiGet<PaymentTermsResponse>(`/api/v1/payment-terms/${sessionId}`));
        } else if (tab === 'cost-to-serve') {
          setCostToServe(
            await apiPost<CostToServeResponse>('/api/v1/cost-to-serve', { session_id: sessionId }),
          );
        }
      } catch (err) {
        setTabErrors((prev) => ({ ...prev, [tab]: getApiErrorMessage(err) }));
      } finally {
        setTabLoading((current) => (current === tab ? null : current));
      }
    },
    [sessionId, trends, bva, paymentTerms, costToServe],
  );

  useEffect(() => {
    if (!sessionId || !fpaOpen || isExecutive) return;
    loadFpaTab(activeTab);
  }, [activeTab, sessionId, fpaOpen, isExecutive, loadFpaTab]);

  useEffect(() => {
    setTrends(null);
    setBva(null);
    setPaymentTerms(null);
    setCostToServe(null);
    setTabErrors({});
  }, [sessionId]);

  const loadMilestones = useCallback(async (initiativeId: string) => {
    setMilestonesLoading(true);
    try {
      const res = await apiGet<{ milestones: unknown[] }>(
        `/api/v1/initiatives/${initiativeId}/milestones`,
      );
      setMilestones((res.milestones ?? []) as Record<string, unknown>[]);
    } catch {
      setMilestones([]);
    } finally {
      setMilestonesLoading(false);
    }
  }, []);

  const loadProvenance = useCallback(async (initiativeId: string) => {
    setProvenanceLoading(true);
    try {
      setProvenance(await apiGet<InitiativeProvenance>(`/api/v1/initiatives/${initiativeId}/provenance`));
    } catch {
      setProvenance(null);
    } finally {
      setProvenanceLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) {
      loadMilestones(selectedId);
      loadProvenance(selectedId);
    }
  }, [selectedId, loadMilestones, loadProvenance]);

  const selectInitiative = useCallback((id: string) => {
    setSelectedId(id);
    setMilestones(null);
    setProvenance(null);
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
    }
  }, [selectInitiative]);

  const acceptInit = async (initiativeId: string) => {
    try {
      await apiPut(`/api/v1/initiatives/${initiativeId}/stage`, { stage: 'committed' });
      const init = initiatives.find((x) => x.initiative_id === initiativeId);
      toast(`Committed · ${init?.lever ?? initiativeId}`);
      appendAudit(`acceptInit: ${initiativeId} → committed`);
      await loadPipeline();
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const deferInit = async (initiativeId: string) => {
    try {
      await apiPut(`/api/v1/initiatives/${initiativeId}/stage`, { stage: 'deferred' });
      const init = initiatives.find((x) => x.initiative_id === initiativeId);
      toast(`Deferred · ${init?.lever ?? initiativeId}`);
      appendAudit(`deferInit: ${initiativeId} → deferred`);
      await loadPipeline();
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  };

  const rejectInit = (initiativeId: string) => {
    setRejectTargetId(initiativeId);
    setRejectReason('');
    setRejectModalOpen(true);
  };

  const confirmReject = async () => {
    if (!rejectTargetId || !rejectReason.trim()) return;
    try {
      await apiPut(`/api/v1/initiatives/${rejectTargetId}/reject`, { reason: rejectReason.trim() });
      const init = initiatives.find((x) => x.initiative_id === rejectTargetId);
      toast(`Rejected · ${init?.lever ?? rejectTargetId}`);
      appendAudit(`rejectInit: ${rejectTargetId}`);
      setRejectModalOpen(false);
      await loadPipeline();
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
      setActualsSaving(true);
      try {
        await apiPost(`/api/v1/initiatives/${initiativeId}/actuals`, { amount_cr: amount });
        const init = initiatives.find((x) => x.initiative_id === initiativeId);
        toast(`Actuals updated · ${init?.lever ?? initiativeId}`);
        appendAudit(`actuals_recorded: ${initiativeId}`);
        await loadPipeline();
      } catch (err) {
        setError(getApiErrorMessage(err));
      } finally {
        setActualsSaving(false);
      }
    },
    [appendAudit, initiatives, loadPipeline, toast],
  );

  const actOnConflict = async (conflict: DataConflict, strategy: string, auditLabel: string) => {
    if (!sessionId || !conflict.conflict_id) return;
    setActingConflictId(conflict.conflict_id);
    setConflictNotice(null);
    try {
      const result = await apiPost<{
        resolved_count?: number;
        escalated_count?: number;
        spend_impact?: ConflictSpendImpact | null;
      }>(`/api/v1/conflicts/resolve?session_id=${sessionId}`, {
        conflict_ids: [conflict.conflict_id],
        strategy,
      });
      toast(`Conflict resolved · ${conflict.title ?? conflict.conflict_id}`);
      appendAudit(`${auditLabel}: ${conflict.conflict_id}`);
      if (result.spend_impact && (result.spend_impact.spend_delta ?? 0) !== 0) {
        await loadPipeline();
        await syncEngagementFromAnalysis();
        await refreshSessionAnalysis();
      }
      await loadConflicts();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setActingConflictId(null);
    }
  };

  const exportBusinessCase = useCallback(async () => {
    if (!sessionId) return;
    setBusinessCaseLoading(true);
    try {
      const res = await apiPost<{ export_url?: string; filename?: string }>(
        `/api/v1/board-deck/${sessionId}`,
        {},
      );
      appendAudit('board_deck_export_requested');
      if (res.export_url) {
        triggerDownload(res.export_url, res.filename);
        setExportNotice('Board deck downloaded.');
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusinessCaseLoading(false);
    }
  }, [sessionId, appendAudit]);

  const exportExcel = useCallback(async () => {
    if (!sessionId) return;
    setExcelExportLoading(true);
    try {
      const res = await apiPost<{ export_url?: string; filename?: string }>(
        `/api/v1/pmo-export/${sessionId}`,
        {},
      );
      appendAudit('export_excel_requested');
      if (res.export_url) {
        triggerDownload(res.export_url, res.filename);
        setExportNotice('Portfolio Excel export downloaded.');
      }
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setExcelExportLoading(false);
    }
  }, [sessionId, appendAudit]);

  const handleConsolidate = useCallback(async () => {
    if (!sessionId) return;
    try {
      await apiPost(`/api/v1/consolidate/${sessionId}`, {});
      toast('Entities consolidated');
      appendAudit('consolidation_run');
      await loadPipeline();
    } catch (err) {
      setError(getApiErrorMessage(err));
    }
  }, [sessionId, appendAudit, loadPipeline, toast]);

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
                <CostRoomHero
                  initiatives={filteredInitiatives}
                  percentileBand={percentileBand}
                  scenario={scenario}
                  scenarioFactor={factor}
                  ebitdaBps={ebitdaBps}
                  currency={engagement.currency}
                  revenueCr={engagement.annual_revenue_cr}
                />
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
                  onClick={() => loadFpaTab(activeTab, true)}
                  disabled={tabLoading === activeTab}
                  className="mb-4 text-xs border border-[var(--cr-line)] rounded-[var(--cr-r-sm)] px-3 py-1.5 bg-white disabled:opacity-50"
                >
                  {tabLoading === activeTab ? 'Refreshing…' : 'Refresh'}
                </button>
                {activeTab === 'trends' && (
                  <TrendsTab data={trends} loading={tabLoading === 'trends'} error={tabErrors.trends ?? null} currency={engagement.currency} />
                )}
                {activeTab === 'bva' && (
                  <BvaTab data={bva} loading={tabLoading === 'bva'} error={tabErrors.bva ?? null} currency={engagement.currency} />
                )}
                {activeTab === 'payment-terms' && (
                  <PaymentTermsTab data={paymentTerms} loading={tabLoading === 'payment-terms'} error={tabErrors['payment-terms'] ?? null} currency={engagement.currency} />
                )}
                {activeTab === 'cost-to-serve' && (
                  <CostToServeTab data={costToServe} loading={tabLoading === 'cost-to-serve'} error={tabErrors['cost-to-serve'] ?? null} currency={engagement.currency} />
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
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder="Why is this initiative rejected?"
        />
      </Modal>
    </MainLayout>
  );
}
