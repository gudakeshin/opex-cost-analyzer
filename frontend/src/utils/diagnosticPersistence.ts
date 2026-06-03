import { isPlaceholderCompanyName } from './engagement';
import type { DiagnosticContextPatch, DiagnosticResponse, SessionManifest } from '../types';

export function parseUrlsText(urlsText: string): string[] {
  return urlsText
    .split('\n')
    .map((u) => u.trim())
    .filter((u) => u.startsWith('http'));
}

export function urlsToText(urls?: string[]): string {
  return (urls ?? []).join('\n');
}

export function revenueCrFromManifest(annualRevenue?: number): string {
  if (annualRevenue == null) return '5000';
  const cr =
    annualRevenue > 1_000_000 ? annualRevenue / 10_000_000 : annualRevenue;
  return String(cr);
}

export interface DiagnosticFormState {
  companyName: string;
  industry: string;
  revenueCr: string;
  urlsText: string;
}

export function formStateFromManifest(
  manifest: SessionManifest,
  engagement?: { company_name?: string; industry?: string; annual_revenue_cr?: number },
): DiagnosticFormState {
  const companyFromManifest = manifest.company_name;
  const companyFromEngagement = engagement?.company_name;
  const companyName =
    companyFromManifest && !isPlaceholderCompanyName(companyFromManifest)
      ? companyFromManifest
      : companyFromEngagement && !isPlaceholderCompanyName(companyFromEngagement)
        ? companyFromEngagement
        : '';

  const industry =
    manifest.industry ||
    engagement?.industry ||
    'manufacturing_diversified';

  const revenueCr =
    manifest.annual_revenue != null
      ? revenueCrFromManifest(manifest.annual_revenue)
      : engagement?.annual_revenue_cr != null
        ? String(engagement.annual_revenue_cr)
        : '5000';

  return {
    companyName,
    industry,
    revenueCr,
    urlsText: urlsToText(manifest.diagnostic_urls),
  };
}

export function buildDiagnosticContextPatch(
  form: DiagnosticFormState,
  options?: {
    diagnosticResult?: DiagnosticResponse | null;
    deepResearchSummary?: string | null;
    markDiagnosticComplete?: boolean;
  },
): DiagnosticContextPatch {
  const patch: DiagnosticContextPatch = {
    company_name: form.companyName.trim() || undefined,
    industry: form.industry,
    annual_revenue_cr: parseFloat(form.revenueCr) || 5000,
    diagnostic_urls: parseUrlsText(form.urlsText),
  };
  if (options?.diagnosticResult) {
    patch.diagnostic_result = options.diagnosticResult;
    if (options.markDiagnosticComplete) {
      patch.diagnostic_completed_at = new Date().toISOString();
    }
  }
  if (options?.deepResearchSummary) {
    patch.deep_research_summary = options.deepResearchSummary;
  }
  return patch;
}

export function isDiagnosticResponse(value: unknown): value is DiagnosticResponse {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.company_name === 'string' &&
    Array.isArray(v.key_findings) &&
    Array.isArray(v.benchmark_gaps)
  );
}
