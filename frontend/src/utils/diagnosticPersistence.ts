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
  if (annualRevenue == null || annualRevenue <= 0) return '';
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

export function isSessionEngagementStale(
  sessionEngagementId?: string,
  activeEngagementId?: string,
): boolean {
  if (!sessionEngagementId || !activeEngagementId) return false;
  return sessionEngagementId !== activeEngagementId;
}

export function formStateFromManifest(
  manifest: SessionManifest,
  engagement?: {
    company_name?: string;
    industry?: string;
    annual_revenue_cr?: number;
    detected_company_name?: string;
    detected_industry?: string;
    detected_annual_revenue_cr?: number;
  },
  options?: {
    sessionEngagementId?: string;
    activeEngagementId?: string;
  },
): DiagnosticFormState {
  const stale = isSessionEngagementStale(
    options?.sessionEngagementId ?? manifest.engagement_id,
    options?.activeEngagementId,
  );

  const companyFromManifest = stale ? undefined : manifest.company_name;
  const companyFromEngagement = engagement?.company_name;
  const companyFromDetected = engagement?.detected_company_name;
  const companyName =
    companyFromManifest && !isPlaceholderCompanyName(companyFromManifest)
      ? companyFromManifest
      : companyFromEngagement && !isPlaceholderCompanyName(companyFromEngagement)
        ? companyFromEngagement
        : companyFromDetected && !isPlaceholderCompanyName(companyFromDetected)
          ? companyFromDetected
          : '';

  const industry = stale
    ? engagement?.detected_industry ||
      engagement?.industry ||
      'manufacturing_diversified'
    : manifest.industry ||
      engagement?.detected_industry ||
      engagement?.industry ||
      'manufacturing_diversified';

  const revenueCr = stale
    ? engagement?.annual_revenue_cr != null && engagement.annual_revenue_cr > 0
      ? String(engagement.annual_revenue_cr)
      : engagement?.detected_annual_revenue_cr != null &&
          engagement.detected_annual_revenue_cr > 0
        ? String(engagement.detected_annual_revenue_cr)
        : ''
    : manifest.annual_revenue != null && manifest.annual_revenue > 0
      ? revenueCrFromManifest(manifest.annual_revenue)
      : engagement?.annual_revenue_cr != null && engagement.annual_revenue_cr > 0
        ? String(engagement.annual_revenue_cr)
        : engagement?.detected_annual_revenue_cr != null &&
            engagement.detected_annual_revenue_cr > 0
          ? String(engagement.detected_annual_revenue_cr)
          : '';

  return {
    companyName,
    industry,
    revenueCr,
    urlsText: stale ? '' : urlsToText(manifest.diagnostic_urls),
  };
}

export function sessionDiagnosticResult(
  manifest: SessionManifest,
  options?: {
    sessionEngagementId?: string;
    activeEngagementId?: string;
  },
): DiagnosticResponse | null {
  if (
    isSessionEngagementStale(
      options?.sessionEngagementId ?? manifest.engagement_id,
      options?.activeEngagementId,
    )
  ) {
    return null;
  }
  const result = manifest.diagnostic_result;
  return result && isDiagnosticResponse(result) ? result : null;
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
    annual_revenue_cr: form.revenueCr.trim()
      ? parseFloat(form.revenueCr) || undefined
      : undefined,
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
