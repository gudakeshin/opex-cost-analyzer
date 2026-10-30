import { describe, expect, it } from 'vitest';
import type { SectorPackDetailResponse } from '../types/sectorPack';
import { buildManifestForm, hydrateEditorDrafts } from './sectorPackStudioState';

const mockDetail: SectorPackDetailResponse = {
  pack_id: 'bfsi_banks',
  sector: 'Banking & Financial Services (India)',
  manifest: {
    description: 'Full sector pack for Indian banks.',
    effective_from: '2026-05-01',
    reporting_currency: 'INR',
    fiscal_year_end: 'March 31',
  },
  kpi_pack: [{ kpi_id: 'cost_to_income_ratio', kpi_name: 'Cost-to-Income', target_direction: 'lower' }],
  taxonomy_extension: {
    base_taxonomy_version: '1.0',
    additional_categories: [{ category_id: 'kyc_aml_ops', category_name: 'KYC / AML' }],
    overrides: [],
  },
  peers: [{ name: 'HDFC Bank', ticker: 'HDFCBANK.NS' }],
  peer_set: {
    sector: 'bfsi_banks',
    currency: 'INR',
    peers: [{ name: 'HDFC Bank', ticker: 'HDFCBANK.NS' }],
    benchmark_metrics: { cost_to_income_ratio_pct: { p25: 42, p50: 47.5, p75: 55 } },
  },
  levers: [{ lever_id: 'bank_workforce_productivity', lever_name: 'Workforce', p50_pct: 8 }],
  categories: {
    IT_SOFTWARE: { P25: 4, P50: 7, P75: 10, P90: 14, unit: '% of revenue', confidence: 'public_disclosure' },
  },
  benchmark_sources: {
    sector: 'bfsi_banks',
    free_sources: [{ id: 'rbi', name: 'RBI Annual Report' }],
    licensed_sources_stubs: [],
  },
  regulatory_layer: '| trigger | categories | severity |\n|---|---|---|',
};

describe('sectorPackStudioState', () => {
  it('buildManifestForm uses top-level sector when manifest.sector is missing', () => {
    const form = buildManifestForm(mockDetail, { pack_id: 'bfsi_banks', status: 'full' });
    expect(form.sector).toBe('Banking & Financial Services (India)');
    expect(form.status).toBe('full');
    expect(form.description).toBe('Full sector pack for Indian banks.');
    expect(form.effective_from).toBe('2026-05-01');
  });

  it('hydrateEditorDrafts preloads all editor tabs with data', () => {
    const { drafts } = hydrateEditorDrafts(mockDetail);
    expect((drafts.kpis as unknown[]).length).toBe(1);
    expect((drafts.taxonomy as { additional_categories: unknown[] }).additional_categories.length).toBe(1);
    expect((drafts.peers as { peers: unknown[] }).peers.length).toBe(1);
    expect((drafts.levers as { levers: unknown[] }).levers.length).toBe(1);
    expect((drafts.benchmarks as { categories: unknown[] }).categories.length).toBe(1);
    expect((drafts.sources as { free_sources: unknown[] }).free_sources.length).toBe(1);
  });
});
