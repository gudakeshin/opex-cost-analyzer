import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { MainLayout } from '../components/Layout/MainLayout';
import { Button } from '../components/Common/Button';
import { Card } from '../components/Common/Card';
import { Input } from '../components/Common/Input';
import { Select } from '../components/Common/Select';
import { Loader } from '../components/Common/Loader';
import { Alert } from '../components/Common/Alert';
import { PageHeader } from '../components/Common/PageHeader';
import { FactVsInferenceLabel } from '../components/Common/FactVsInferenceLabel';
import { DiagnosticScorecard } from '../components/PageComponents/Diagnostic/DiagnosticScorecard';
import { FindingCards } from '../components/PageComponents/Diagnostic/FindingCards';
import { apiPost, getApiErrorMessage } from '../hooks/useApi';
import { friendlyErrorMessage } from '../utils/errorMessages';
import type { DiagnosticRequest, DiagnosticResponse } from '../types';

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

export const Diagnostic: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [industry, setIndustry] = useState('manufacturing_diversified');
  const [revenueCr, setRevenueCr] = useState('5000');
  const [urlsText, setUrlsText] = useState('');
  const [result, setResult] = useState<DiagnosticResponse | null>(null);

  const friendlyError = error ? friendlyErrorMessage(error) : null;

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyName.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const payload: DiagnosticRequest = {
        company_name: companyName.trim(),
        industry,
        annual_revenue_cr: parseFloat(revenueCr) || 5000,
        urls: urlsText
          .split('\n')
          .map((u) => u.trim())
          .filter((u) => u.startsWith('http')),
      };
      const res = await apiPost<DiagnosticResponse>('/api/v1/diagnostic/company-research', payload);
      setResult(res);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const sortedGaps = [...(result?.benchmark_gaps ?? [])].sort((a, b) => {
    const ha = Number(a.headroom_to_p25_cr ?? 0);
    const hb = Number(b.headroom_to_p25_cr ?? 0);
    return hb - ha;
  });

  return (
    <MainLayout hideHeader>
      <PageHeader
        title="Company Diagnostic"
        subtitle="Benchmark-backed research and value-at-table"
      />

      <div className="max-w-5xl mx-auto space-y-6">
        {friendlyError && (
          <Alert variant="error" title={friendlyError.title} recovery={friendlyError.recovery} onDismiss={() => setError(null)}>
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

            <Card title="Benchmark gaps (ranked)" className="border-brand-border bg-white">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-brand-muted border-b border-brand-border">
                      <th scope="col" className="py-2">Category</th>
                      <th scope="col" className="py-2">P50 %</th>
                      <th scope="col" className="py-2">Headroom (₹ Cr)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedGaps.slice(0, 10).map((g, i) => {
                      const headroom = Number(g.headroom_to_p25_cr ?? 0);
                      const hot = headroom > 50;
                      return (
                        <tr
                          key={i}
                          className={`border-b border-brand-border ${hot ? 'bg-amber-50/60' : ''}`}
                        >
                          <td className="py-2 font-medium text-brand-ink">
                            {String(g.category_name || g.category)}
                          </td>
                          <td className="py-2 tabular-nums">{String(g.p50_pct ?? '—')}</td>
                          <td className="py-2 tabular-nums">{String(g.headroom_to_p25_cr ?? '—')}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Value at table" className="border-brand-border bg-white">
              <div className="flex items-center gap-2 mb-4">
                <FactVsInferenceLabel kind="inference" />
                <span className="text-xs text-brand-muted">P10 / P50 / P90 bands</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-brand-muted border-b border-brand-border">
                      <th scope="col" className="py-2">Lever</th>
                      <th scope="col" className="py-2">P10</th>
                      <th scope="col" className="py-2">P50</th>
                      <th scope="col" className="py-2">P90</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.value_at_table?.map((v, i) => (
                      <tr key={i} className="border-b border-brand-border">
                        <td className="py-2">{String(v.lever_name)}</td>
                        <td className="py-2 tabular-nums">{String(v.p10_cr)}</td>
                        <td className="py-2 tabular-nums font-semibold text-brand-green">
                          {String(v.p50_cr)}
                        </td>
                        <td className="py-2 tabular-nums">{String(v.p90_cr)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            <Link
              to="/"
              className="inline-flex text-sm font-semibold text-brand-navy hover:text-brand-green"
            >
              Start procurement session from diagnostic →
            </Link>
          </>
        )}
      </div>
    </MainLayout>
  );
};
