import { describe, expect, it } from 'vitest';
import {
  buildDiagnosticContextPatch,
  formStateFromManifest,
  isDiagnosticResponse,
  isSessionEngagementStale,
  parseUrlsText,
  sessionDiagnosticResult,
} from './diagnosticPersistence';
import type { DiagnosticResponse, SessionManifest } from '../types';

describe('diagnosticPersistence', () => {
  it('parses and serializes URLs', () => {
    const text = 'https://a.com\n  \nnot-a-url\nhttps://b.com/path';
    expect(parseUrlsText(text)).toEqual(['https://a.com', 'https://b.com/path']);
  });

  it('hydrates form from manifest with engagement fallback', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      company_name: 'Acme',
      industry: 'it_ites',
      annual_revenue: 30_000_000_000,
      diagnostic_urls: ['https://acme.com'],
    };
    const form = formStateFromManifest(manifest, {
      company_name: 'New engagement',
      industry: 'manufacturing_diversified',
    });
    expect(form.companyName).toBe('Acme');
    expect(form.industry).toBe('it_ites');
    expect(form.revenueCr).toBe('3000');
    expect(form.urlsText).toBe('https://acme.com');
  });

  it('defaults revenue to blank when not in manifest or engagement', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      company_name: 'New engagement',
      industry: '',
    };
    const form = formStateFromManifest(manifest, {
      company_name: 'New engagement',
      industry: '',
    });
    expect(form.revenueCr).toBe('');
  });

  it('falls back to detected annual revenue when unset', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      company_name: 'New engagement',
      industry: '',
    };
    const form = formStateFromManifest(manifest, {
      detected_annual_revenue_cr: 18400,
    });
    expect(form.revenueCr).toBe('18400');
  });

  it('builds patch without revenue when field is blank', () => {
    const patch = buildDiagnosticContextPatch({
      companyName: 'Acme',
      industry: 'it_ites',
      revenueCr: '',
      urlsText: '',
    });
    expect(patch.annual_revenue_cr).toBeUndefined();
  });

  it('falls back to detected values when user fields are unset', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      company_name: 'New engagement',
      industry: '',
    };
    const form = formStateFromManifest(manifest, {
      company_name: 'New engagement',
      industry: '',
      detected_company_name: 'Belrise',
      detected_industry: 'fmcg_consumer',
    });
    expect(form.companyName).toBe('Belrise');
    expect(form.industry).toBe('fmcg_consumer');
  });

  it('prefers detected industry over placeholder engagement default', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      company_name: 'New engagement',
      industry: '',
    };
    const form = formStateFromManifest(manifest, {
      company_name: 'New engagement',
      industry: 'manufacturing_diversified',
      detected_industry: 'it_ites',
    });
    expect(form.industry).toBe('it_ites');
  });

  it('does not override explicit user industry with detected value', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      company_name: 'Acme',
      industry: 'it_ites',
    };
    const form = formStateFromManifest(manifest, {
      company_name: 'Acme',
      industry: 'it_ites',
      detected_industry: 'fmcg_consumer',
    });
    expect(form.industry).toBe('it_ites');
  });

  it('builds diagnostic context patch with result', () => {
    const result: DiagnosticResponse = {
      company_name: 'Acme',
      industry_used: 'it_ites',
      annual_revenue_cr: 3000,
      key_findings: [],
      benchmark_gaps: [],
      value_at_table: [],
      company_signals: {},
    };
    const patch = buildDiagnosticContextPatch(
      { companyName: 'Acme', industry: 'it_ites', revenueCr: '3000', urlsText: '' },
      { diagnosticResult: result, markDiagnosticComplete: true },
    );
    expect(patch.diagnostic_result).toEqual(result);
    expect(patch.diagnostic_completed_at).toBeDefined();
  });

  it('validates diagnostic response shape', () => {
    expect(isDiagnosticResponse({ company_name: 'x', key_findings: [], benchmark_gaps: [] })).toBe(
      true,
    );
    expect(isDiagnosticResponse(null)).toBe(false);
  });

  it('ignores stale session company when engagement ids mismatch', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      engagement_id: 'aranya-id',
      company_name: 'Aranya Digital Services Ltd',
      industry: 'it_ites',
      annual_revenue: 18_400_000_000,
      diagnostic_urls: ['https://aranya.com'],
    };
    const form = formStateFromManifest(
      manifest,
      {
        company_name: 'Hindustan Unilever Limited',
        industry: 'fmcg_consumer',
      },
      { sessionEngagementId: 'aranya-id', activeEngagementId: 'hul-id' },
    );
    expect(form.companyName).toBe('Hindustan Unilever Limited');
    expect(form.industry).toBe('fmcg_consumer');
    expect(form.revenueCr).toBe('');
    expect(form.urlsText).toBe('');
  });

  it('returns null diagnostic result when session engagement is stale', () => {
    const manifest: SessionManifest = {
      session_id: 's1',
      engagement_id: 'aranya-id',
      company_name: 'Aranya Digital Services Ltd',
      diagnostic_result: {
        company_name: 'Aranya Digital Services Ltd',
        industry_used: 'it_ites',
        annual_revenue_cr: 18400,
        key_findings: [],
        benchmark_gaps: [],
        value_at_table: [],
        company_signals: {},
      },
    };
    expect(
      sessionDiagnosticResult(manifest, {
        sessionEngagementId: 'aranya-id',
        activeEngagementId: 'hul-id',
      }),
    ).toBeNull();
  });

  it('detects session engagement staleness', () => {
    expect(isSessionEngagementStale('a', 'b')).toBe(true);
    expect(isSessionEngagementStale('a', 'a')).toBe(false);
    expect(isSessionEngagementStale(undefined, 'a')).toBe(false);
  });
});
