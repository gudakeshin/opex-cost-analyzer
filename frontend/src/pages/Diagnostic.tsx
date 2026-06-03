import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { Button } from '../components/Common/Button';
import { Card } from '../components/Common/Card';
import { Input } from '../components/Common/Input';
import { Select } from '../components/Common/Select';
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
import { DeepResearchSection } from '../components/PageComponents/Diagnostic/DeepResearchSection';
import { apiGet, apiPatch, apiPost, getApiErrorMessage } from '../hooks/useApi';
import { friendlyErrorMessage } from '../utils/errorMessages';
import { useSession } from '../context/SessionContext';
import {
  buildDiagnosticContextPatch,
  formStateFromManifest,
  isDiagnosticResponse,
  parseUrlsText,
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

const FORM_SAVE_DEBOUNCE_MS = 500;

export const Diagnostic: React.FC = () => {
  const navigate = useNavigate();
  const { sessionId, ensureSession, refreshEngagement, engagement } = useSession();
  const [activeSid, setActiveSid] = useState<string | null>(sessionId);
  const [hydrating, setHydrating] = useState(true);
  const [manifest, setManifest] = useState<SessionManifest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('manufacturing_diversified');
  const [revenueCr, setRevenueCr] = useState('5000');
  const [urlsText, setUrlsText] = useState('');
  const [result, setResult] = useState<DiagnosticResponse | null>(null);
  const [deepResearchSummary, setDeepResearchSummary] = useState<string | null>(null);
  const [handoffLoading, setHandoffLoading] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipFormSaveRef = useRef(true);

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
    let cancelled = false;

    (async () => {
      setHydrating(true);
      skipFormSaveRef.current = true;
      try {
        const sid = await ensureSession();
        if (cancelled) return;
        setActiveSid(sid);

        const m = await apiGet<SessionManifest>(`/api/v1/sessions/${sid}/manifest`);
        if (cancelled) return;
        setManifest(m);

        const form = formStateFromManifest(m, engagement);
        setCompanyName(form.companyName);
        setIndustry(form.industry);
        setRevenueCr(form.revenueCr);
        setUrlsText(form.urlsText);

        if (m.diagnostic_result && isDiagnosticResponse(m.diagnostic_result)) {
          setResult(m.diagnostic_result);
        } else {
          setResult(null);
        }

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
  }, [sessionId, ensureSession]);

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
      const sid = activeSid ?? (await ensureSession());
      const patch: DiagnosticContextPatch = {
        company_name: companyName.trim() || undefined,
        industry,
        annual_revenue_cr: parseFloat(revenueCr) || 5000,
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
    setLoading(true);
    setError(null);
    try {
      const sid = activeSid ?? (await ensureSession());
      setActiveSid(sid);

      const payload: DiagnosticRequest = {
        company_name: companyName.trim(),
        industry,
        annual_revenue_cr: parseFloat(revenueCr) || 5000,
        urls: parseUrlsText(urlsText),
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

        <Card className="border-brand-border bg-white">
          <p className="text-brand-muted mb-6">
            Enter company details for benchmark-backed diagnostic research.
          </p>
          <form onSubmit={handleAnalyze} className="space-y-4">
            <Input
              label="Company Name"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="Enter company name…"
              required
            />
            <Select
              label="Industry (sector pack)"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              options={SECTOR_OPTIONS}
            />
            <Input
              label="Annual Revenue (₹ Cr)"
              type="number"
              value={revenueCr}
              onChange={(e) => setRevenueCr(e.target.value)}
            />
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
          {loading && <Loader label="Analyzing company data…" />}
        </Card>

        {result && (
          <>
            <DiagnosticScorecard result={result} />

            <Card title="Key findings" className="border-brand-border bg-white">
              <FindingCards findings={result.key_findings ?? []} />
              {result.data_note && (
                <p className="mt-4 text-sm text-brand-muted border-l-4 border-brand-navy pl-3">
                  {result.data_note}
                </p>
              )}
            </Card>

            {showDeepResearch && (
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

            <BenchmarkGapsTable
              gaps={tableData?.benchmarkGaps ?? []}
              dataNote={result.data_note}
              percentileLegend={result.percentile_legend}
            />

            <ValueAtTableTable
              rows={tableData?.valueAtTable ?? []}
              totalP50Cr={tableData?.totalP50}
              annualRevenueCr={result.annual_revenue_cr}
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
