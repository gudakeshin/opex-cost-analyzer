import { describe, expect, it } from 'vitest';
import {
  buildDiagnosticContextPatch,
  formStateFromManifest,
  isDiagnosticResponse,
  parseUrlsText,
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
});
