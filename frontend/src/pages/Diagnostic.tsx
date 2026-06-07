import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { Button } from '../components/Common/Button';
import { Card } from '../components/Common/Card';
import { Input } from '../components/Common/Input';
import { Select } from '../components/Common/Select';
import { RecommendedBadge } from '../components/Common/RecommendedBadge';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { DiagnosticScorecard } from '../components/PageComponents/Diagnostic/DiagnosticScorecard';
import { FindingCards } from '../components/PageComponents/Diagnostic/FindingCards';
import {
  BenchmarkGapsTable,
  ValueAtTableTable,
  diagnosticTablesFromResult,
} from '../components/PageComponents/Diagnostic/DiagnosticTables';
import { BenchmarkProxyDisclaimer } from '../components/PageComponents/Diagnostic/BenchmarkProxyDisclaimer';
import { DeepResearchSection } from '../components/PageComponents/Diagnostic/DeepResearchSection';
import { isBenchmarkProxyProfile } from '../utils/diagnosticProxyDisclaimer';
import { apiGet, apiPatch, apiPost, getApiErrorMessage } from '../hooks/useApi';
import { friendlyErrorMessage } from '../utils/errorMessages';
import { useSession } from '../context/SessionContext';
import {
  buildDiagnosticContextPatch,
  formStateFromManifest,
  isDiagnosticResponse,
  parseUrlsText,
  sessionDiagnosticResult,
} from '../utils/diagnosticPersistence';
import type {
  DiagnosticContextPatch,
  DiagnosticRequest,
  DiagnosticResponse,
  SessionManifest,
} from '../types';

const SECTOR_OPTIONS = [
  { value: 'bfsi_banks', label: 'BFSI / Banks' },
  { value: 'conglomerate', label: 'Conglomerate' },
  { value: 'energy_utilities', label: 'Energy & Utilities' },
  { value: 'financial_services_nonbank', label: 'Financial Services (Non-bank)' },
  { value: 'fmcg_consumer', label: 'FMCG / Consumer' },
  { value: 'gcc_capability_centers', label: 'GCC Capability Centers' },
  { value: 'healthcare_hospitals', label: 'Healthcare & Hospitals' },
  { value: 'hospitality_travel', label: 'Hospitality & Travel' },
  { value: 'insurance_general', label: 'Insurance (General)' },
  { value: 'it_ites', label: 'IT / ITES' },
  { value: 'manufacturing_diversified', label: 'Manufacturing (Diversified)' },
  { value: 'pharma_lifesciences', label: 'Pharma & Life Sciences' },
  { value: 'psu_cpse', label: 'PSU / CPSE' },
  { value: 'retail_organized', label: 'Retail (Organized)' },
  { value: 'telecom_infra', label: 'Telecom & Infrastructure' },
];

function sectorLabel(value: string): string {
  return SECTOR_OPTIONS.find((o) => o.value === value)?.label || value;
}

const FORM_SAVE_DEBOUNCE_MS = 500;

export const Diagnostic: React.FC = () => {
  const navigate = useNavigate();
  const { sessionId, engagementId, ensureSessionForEngagement, refreshEngagement, engagement } =
    useSession();
  const [activeSid, setActiveSid] = useState<string | null>(sessionId);
  const [hydrating, setHydrating] = useState(true);
  const [manifest, setManifest] = useState<SessionManifest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('manufacturing_diversified');
  const [revenueCr, setRevenueCr] = useState('');
  const [urlsText, setUrlsText] = useState('');
  const [result, setResult] = useState<DiagnosticResponse | null>(null);
  const [deepResearchSummary, setDeepResearchSummary] = useState<string | null>(null);
  const [handoffLoading, setHandoffLoading] = useState(false);
  const [engagementDocCount, setEngagementDocCount] = useState(0);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipFormSaveRef = useRef(true);
  const engagementHydratedRef = useRef(false);

  const formState = useCallback(
    () => ({ companyName, industry, revenueCr, urlsText }),
    [companyName, industry, revenueCr, urlsText],
  );

  const persistContext = useCallback(
    async (
      sid: string,
      options?: {
        diagnosticResult?: DiagnosticResponse | null;
        markDiagnosticComplete?: boolean;
        includeDeepResearch?: boolean;
      },
    ) => {
      const patch = buildDiagnosticContextPatch(formState(), {
        diagnosticResult: options?.diagnosticResult,
        markDiagnosticComplete: options?.markDiagnosticComplete,
        deepResearchSummary:
          options?.includeDeepResearch ? deepResearchSummary : undefined,
      });
      await apiPatch(`/api/v1/sessions/${sid}/diagnostic-context`, patch);
    },
    [formState, deepResearchSummary],
  );

  useEffect(() => {
    engagementHydratedRef.current = false;
  }, [engagementId]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      setHydrating(true);
      skipFormSaveRef.current = true;
      try {
        const sid = await ensureSessionForEngagement(engagementId ?? undefined);
        if (cancelled) return;
        setActiveSid(sid);

        const m = await apiGet<SessionManifest>(`/api/v1/sessions/${sid}/manifest`);
        if (cancelled) return;
        setManifest(m);

        const staleOpts = {
          sessionEngagementId: m.engagement_id,
          activeEngagementId: engagementId ?? undefined,
        };
        const form = formStateFromManifest(
          m,
          {
            company_name: engagement.company_name,
            industry: engagement.industry,
            annual_revenue_cr: engagement.annual_revenue_cr,
            detected_company_name: engagement.detected_company_name,
            detected_industry: engagement.detected_industry,
            detected_annual_revenue_cr: engagement.detected_annual_revenue_cr,
          },
          staleOpts,
        );
        setCompanyName(form.companyName);
        setIndustry(form.industry);
        setRevenueCr(form.revenueCr);
        setUrlsText(form.urlsText);

        setResult(sessionDiagnosticResult(m, staleOpts));
        setDeepResearchSummary(m.deep_research_summary ?? null);
      } catch {
        if (!cancelled) {
          setManifest(null);
        }
      } finally {
        if (!cancelled) {
          setHydrating(false);
          skipFormSaveRef.current = false;
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sessionId, engagementId, ensureSessionForEngagement, engagement]);

  // Pre-fill form from engagement metadata (once, after hydration, only if form is empty)
  useEffect(() => {
    if (hydrating || engagementHydratedRef.current) return;
    const effectiveCompany =
      engagement.company_name && engagement.company_name !== 'New engagement'
        ? engagement.company_name
        : engagement.detected_company_name || '';
    const effectiveIndustry =
      engagement.detected_industry &&
      (!engagement.industry || engagement.industry === 'manufacturing_diversified')
        ? engagement.detected_industry
        : engagement.industry || engagement.detected_industry || '';
    if (!effectiveCompany && !effectiveIndustry) return;
    engagementHydratedRef.current = true;
    if (!companyName && effectiveCompany) setCompanyName(effectiveCompany);
    if (!industry && effectiveIndustry) setIndustry(effectiveIndustry);
    if (engagement.annual_revenue_cr && engagement.annual_revenue_cr > 0) {
      setRevenueCr(String(engagement.annual_revenue_cr));
    } else if (
      engagement.detected_annual_revenue_cr &&
      engagement.detected_annual_revenue_cr > 0 &&
      !revenueCr
    ) {
      setRevenueCr(String(engagement.detected_annual_revenue_cr));
    }
  }, [
    hydrating,
    engagement.company_name,
    engagement.detected_company_name,
    engagement.industry,
    engagement.detected_industry,
    engagement.annual_revenue_cr,
    engagement.detected_annual_revenue_cr,
    companyName,
    industry,
    revenueCr,
  ]);

  // Fetch engagement document count for the context banner
  useEffect(() => {
    if (!engagementId) return;
    apiGet<{ documents: { status: string }[] }>(`/api/v1/engagements/${engagementId}/documents`)
      .then((res) => {
        const ready = (res.documents ?? []).filter((d) => d.status === 'ready').length;
        setEngagementDocCount(ready);
      })
      .catch(() => setEngagementDocCount(0));
  }, [engagementId]);

  useEffect(() => {
    if (!activeSid || hydrating || skipFormSaveRef.current) return;

    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      persistContext(activeSid).catch(() => {});
    }, FORM_SAVE_DEBOUNCE_MS);

    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [activeSid, hydrating, companyName, industry, revenueCr, urlsText, persistContext]);

  useEffect(() => {
    return () => {
      if (!activeSid || skipFormSaveRef.current) return;
      const patch = buildDiagnosticContextPatch(formState());
      apiPatch(`/api/v1/sessions/${activeSid}/diagnostic-context`, patch).catch(() => {});
    };
  }, [activeSid, formState]);

  const friendlyError = error ? friendlyErrorMessage(error) : null;

  const handleDeepResearchReady = (summary: string) => {
    setDeepResearchSummary(summary);
    if (activeSid) {
      const patch: DiagnosticContextPatch = { deep_research_summary: summary };
      apiPatch(`/api/v1/sessions/${activeSid}/diagnostic-context`, patch).catch(() => {});
    }
  };

  const handleStartSession = async () => {
    setHandoffLoading(true);
    try {
      const sid = activeSid ?? (await ensureSessionForEngagement(engagementId ?? undefined));
      const patch: DiagnosticContextPatch = {
        company_name: companyName.trim() || undefined,
        industry,
        annual_revenue_cr: revenueCr.trim()
          ? parseFloat(revenueCr) || undefined
          : undefined,
        diagnostic_urls: parseUrlsText(urlsText),
      };
      if (result) {
        patch.diagnostic_result = result;
        patch.diagnostic_completed_at = manifest?.diagnostic_completed_at ?? new Date().toISOString();
      }
      if (deepResearchSummary) {
        patch.deep_research_summary = deepResearchSummary;
      }
      await apiPatch(`/api/v1/sessions/${sid}/diagnostic-context`, patch);
      await refreshEngagement();
      navigate('/');
    } catch {
      navigate('/');
    } finally {
      setHandoffLoading(false);
    }
  };

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyName.trim()) return;
    const parsedRevenue = parseFloat(revenueCr);
    if (!revenueCr.trim() || Number.isNaN(parsedRevenue) || parsedRevenue <= 0) {
      setError('Enter annual revenue (₹ Cr) before running the diagnostic.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const sid = activeSid ?? (await ensureSessionForEngagement(engagementId ?? undefined));
      setActiveSid(sid);

      const payload: DiagnosticRequest = {
        company_name: companyName.trim(),
        industry,
        annual_revenue_cr: parsedRevenue,
        urls: parseUrlsText(urlsText),
        ...(engagementId ? { engagement_id: engagementId } : {}),
      };
      const res = await apiPost<DiagnosticResponse>(
        '/api/v1/diagnostic/company-research',
        payload,
      );
      setResult(res);
      skipFormSaveRef.current = true;
      await persistContext(sid, {
        diagnosticResult: res,
        markDiagnosticComplete: true,
      });
      const updated = await apiGet<SessionManifest>(`/api/v1/sessions/${sid}/manifest`);
      setManifest(updated);
      await refreshEngagement();
      skipFormSaveRef.current = false;
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const tableData = result ? diagnosticTablesFromResult(result) : null;

  const showDeepResearch =
    !!result ||
    !!manifest?.deep_research_interaction_id ||
    !!manifest?.deep_research_summary;

  if (hydrating) {
    return (
      <MainLayout hideHeader>
        <PageHeader
          title="Company Diagnostic"
          subtitle="Benchmark-backed research and value-at-table"
        />
        <div className="max-w-5xl mx-auto py-12">
          <Loader label="Loading diagnostic session…" />
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout hideHeader>
      <PageHeader
        title="Company Diagnostic"
        subtitle="Benchmark-backed research and value-at-table"
      />

      <div className="max-w-5xl mx-auto space-y-6">
        {friendlyError && (
          <Alert
            variant="error"
            title={friendlyError.title}
            recovery={friendlyError.recovery}
            onDismiss={() => setError(null)}
          >
            {friendlyError.detail}
          </Alert>
        )}

        {/* Engagement context banner */}
        {engagementId && engagementDocCount > 0 && (
          <div className="flex items-start gap-3 px-4 py-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-800">
            <svg className="w-4 h-4 mt-0.5 shrink-0 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <div>
              <span className="font-semibold">{engagementDocCount} document{engagementDocCount !== 1 ? 's' : ''} loaded</span>
              {' from '}
              <span className="font-semibold">{engagement.company_name}</span>
              {' — diagnostic will use actual spend data where available.'}
              {' '}
              <a href="/ui/documents" className="underline hover:text-blue-900">Manage documents</a>
            </div>
          </div>
        )}
        {engagementId && engagementDocCount === 0 && (
          <div className="flex items-start gap-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800">
            <svg className="w-4 h-4 mt-0.5 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              No documents uploaded for <span className="font-semibold">{engagement.company_name}</span> — diagnostic will use benchmark proxies.{' '}
              <a href="/ui/documents" className="underline hover:text-amber-900">Upload documents</a> for actual-spend analysis.
            </div>
          </div>
        )}

        <Card className="border-brand-border bg-white">
          <p className="text-brand-muted mb-6">
            Enter company details for benchmark-backed diagnostic research.
          </p>
          <form onSubmit={handleAnalyze} className="space-y-4">
            <div>
              <Input
                label="Company Name"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                placeholder="Enter company name…"
                required
              />
              {engagement.detected_company_name && (
                <RecommendedBadge
                  className="mt-1"
                  label={engagement.detected_company_name}
                  matches={
                    companyName.trim().toLowerCase() ===
                    engagement.detected_company_name.toLowerCase()
                  }
                  onApply={() => setCompanyName(engagement.detected_company_name as string)}
                />
              )}
            </div>
            <div>
              <Select
                label="Industry (sector pack)"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                options={SECTOR_OPTIONS}
              />
              {engagement.detected_industry && (
                <RecommendedBadge
                  className="mt-1"
                  label={
                    engagement.detected_industry_label ||
                    sectorLabel(engagement.detected_industry)
                  }
                  matches={industry === engagement.detected_industry}
                  onApply={() => setIndustry(engagement.detected_industry as string)}
                />
              )}
            </div>
            <div>
              <Input
                label="Annual Revenue (₹ Cr)"
                type="number"
                value={revenueCr}
                onChange={(e) => setRevenueCr(e.target.value)}
                placeholder="Enter annual revenue…"
                required
              />
              {engagement.detected_annual_revenue_cr != null &&
                engagement.detected_annual_revenue_cr > 0 && (
                  <RecommendedBadge
                    className="mt-1"
                    label={`${engagement.detected_annual_revenue_cr.toLocaleString('en-IN')} Cr`}
                    matches={
                      revenueCr.trim() !== '' &&
                      parseFloat(revenueCr) === engagement.detected_annual_revenue_cr
                    }
                    onApply={() =>
                      setRevenueCr(String(engagement.detected_annual_revenue_cr))
                    }
                  />
                )}
            </div>
            <div>
              <label className="block text-sm font-medium text-brand-ink mb-2">
                Source URLs (one per line, optional)
              </label>
              <textarea
                value={urlsText}
                onChange={(e) => setUrlsText(e.target.value)}
                rows={3}
                className="w-full px-4 py-2 border border-brand-border rounded-lg font-mono text-sm bg-white text-brand-ink"
                placeholder="https://…"
              />
            </div>
            <Button type="submit" disabled={loading} loading={loading} className="w-full">
              Run Diagnostic
            </Button>
          </form>
          {loading && <Loader label="Building sector benchmark estimate…" />}
        </Card>

        {result && (
          <>
            <DiagnosticScorecard result={result} />

            {isBenchmarkProxyProfile(result.profile_basis) && (
              <BenchmarkProxyDisclaimer dataNote={result.data_note} />
            )}

            <Card title="Key findings" className="border-brand-border bg-white">
              <FindingCards findings={result.key_findings ?? []} />
              {isBenchmarkProxyProfile(result.profile_basis) && (
                <p className="mt-4 text-sm text-brand-muted border-l-4 border-amber-400 pl-3">
                  Findings below are illustrative from sector benchmarks and the revenue you entered—not
                  from company-specific spend uploads.
                </p>
              )}
            </Card>

            {showDeepResearch && (
              <DeepResearchSection
                key={`${activeSid ?? ''}-${manifest?.deep_research_interaction_id ?? 'none'}`}
                companyName={companyName}
                industry={industry}
                revenueCr={parseFloat(revenueCr) || 0}
                sessionId={activeSid}
                onSummaryReady={handleDeepResearchReady}
                initialInteractionId={manifest?.deep_research_interaction_id}
                initialSummary={manifest?.deep_research_summary ?? deepResearchSummary}
                initialFullReport={manifest?.deep_research_full_report}
                initialPrompt={manifest?.deep_research_prompt}
                hydrateReady={!hydrating}
              />
            )}

            <BenchmarkGapsTable
              gaps={tableData?.benchmarkGaps ?? []}
              dataNote={result.data_note}
              profileBasis={result.profile_basis}
              percentileLegend={result.percentile_legend}
            />

            <ValueAtTableTable
              rows={tableData?.valueAtTable ?? []}
              totalP50Cr={tableData?.totalP50}
              annualRevenueCr={result.annual_revenue_cr}
              dataNote={result.data_note}
              profileBasis={result.profile_basis}
              percentileLegend={result.percentile_legend}
              methodology={result.value_at_table_methodology}
            />

            <Button
              onClick={handleStartSession}
              loading={handoffLoading}
              disabled={handoffLoading}
              className="text-sm font-semibold"
            >
              Start procurement session from diagnostic →
              {deepResearchSummary && (
                <span className="ml-2 inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800 font-medium">
                  + deep research context
                </span>
              )}
            </Button>
          </>
        )}

        {!result && showDeepResearch && (
          <DeepResearchSection
            key={`${activeSid ?? ''}-${manifest?.deep_research_interaction_id ?? 'none'}`}
            companyName={companyName}
            industry={industry}
            revenueCr={parseFloat(revenueCr) || 5000}
            sessionId={activeSid}
            onSummaryReady={handleDeepResearchReady}
            initialInteractionId={manifest?.deep_research_interaction_id}
            initialSummary={manifest?.deep_research_summary ?? deepResearchSummary}
            initialFullReport={manifest?.deep_research_full_report}
            initialPrompt={manifest?.deep_research_prompt}
            hydrateReady={!hydrating}
          />
        )}
      </div>
    </MainLayout>
  );
};
