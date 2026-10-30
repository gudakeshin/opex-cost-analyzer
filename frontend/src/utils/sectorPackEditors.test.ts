import { describe, expect, it } from 'vitest';
import type { BenchmarksDraft, LeversDraft, SectorPackDetailResponse } from '../types/sectorPack';
import {
  deepEqual,
  parseDetailToDraft,
  parseDraftFromJson,
  serializeDraftToPayload,
} from './sectorPackEditors';

const mockDetail: SectorPackDetailResponse = {
  pack_id: 'bfsi_banks',
  sector: 'BFSI Banks',
  version: '1.1',
  vintage_date: '2025-04-01',
  confidence_overall: 'public_disclosure',
  source_metadata: {
    methodology: 'Peer-derived percentiles',
    sample_size: 10,
    primary_sources: [{ source_name: 'RBI Annual Report', source_type: 'published_research' }],
  },
  categories: {
    IT_SOFTWARE: {
      P25: 4,
      P50: 7,
      P75: 10,
      P90: 14,
      unit: '% of revenue',
      confidence: 'public_disclosure',
      source_note: 'Bank IT spend',
      linked_levers: ['bank_it_optimisation'],
    },
  },
  levers: [
    {
      lever_id: 'bank_workforce_productivity',
      lever_name: 'Workforce Productivity',
      p10_pct: 4,
      p50_pct: 8,
      p90_pct: 14,
      category_ids: ['HR'],
    },
  ],
  levers_document: {
    sector: 'bfsi_banks',
    source_type: 'internal_calibration',
    source_verification_note: 'Internal estimates only',
    levers: [
      {
        lever_id: 'bank_workforce_productivity',
        lever_name: 'Workforce Productivity',
        p10_pct: 4,
        p50_pct: 8,
        p90_pct: 14,
        category_ids: ['HR'],
        brsr_principle: 'P3',
        effort_weeks: { p10: 15, p50: 20, p90: 25 },
      },
    ],
  },
  benchmarks_document: {
    sector: 'bfsi_banks',
    version: '1.1',
    vintage_date: '2025-04-01',
    confidence_overall: 'public_disclosure',
    source_metadata: {
      methodology: 'Peer-derived percentiles',
      sample_size: 10,
      primary_sources: [{ source_name: 'RBI Annual Report' }],
    },
    benchmarks: {
      bfsi_banks: {
        categories: {
          IT_SOFTWARE: {
            P25: 4,
            P50: 7,
            P75: 10,
            P90: 14,
            unit: '% of revenue',
            confidence: 'public_disclosure',
            source_note: 'Bank IT spend',
          },
        },
      },
    },
  },
  kpi_pack: [{ kpi_id: 'cost_to_income_ratio', kpi_name: 'Cost-to-Income', target_direction: 'lower' }],
  peer_set: {
    sector: 'bfsi_banks',
    currency: 'INR',
    data_source: 'BSE/NSE annual reports FY25',
    refresh_date: '2026-04-01',
    peers: [{ name: 'HDFC Bank', ticker: 'HDFCBANK.NS' }],
    benchmark_metrics: {
      cost_to_income_ratio_pct: { p25: 42, p50: 47.5, p75: 55 },
    },
  },
  peers: [{ name: 'HDFC Bank', ticker: 'HDFCBANK.NS' }],
  peer_benchmark_metrics: {
    cost_to_income_ratio_pct: { p25: 42, p50: 47.5, p75: 55 },
  },
  taxonomy_extension: {
    base_taxonomy_version: '1.0',
    additional_categories: [{ category_id: 'kyc_aml_ops', category_name: 'KYC / AML' }],
    overrides: [{ category_id: 'HR', category_name: 'Workforce Cost' }],
  },
  benchmark_sources: {
    source_validation_date: '2026-05-21',
    source_validation_note: 'URLs verified',
    sector: 'bfsi_banks',
    free_sources: [{ id: 'rbi_annual_report', name: 'RBI Annual Report', url: 'https://rbi.org.in' }],
    licensed_sources_stubs: [{ id: 'cmie', name: 'CMIE Prowess', credential_env: 'CMIE_API_KEY' }],
  },
};

describe('sectorPackEditors', () => {
  it('round-trips KPI draft unchanged', () => {
    const draft = parseDetailToDraft('kpis', mockDetail);
    const payload = serializeDraftToPayload('kpis', draft, mockDetail);
    expect(payload).toEqual(mockDetail.kpi_pack);
  });

  it('preserves hidden lever fields on save', () => {
    const draft = parseDetailToDraft('levers', mockDetail) as LeversDraft;
    const edited = {
      ...draft,
      levers: [
        {
          ...draft.levers[0],
          p50_pct: 9,
        },
      ],
    };
    const payload = serializeDraftToPayload('levers', edited, mockDetail) as {
      levers: Array<Record<string, unknown>>;
      source_verification_note?: string;
    };
    expect(payload.source_verification_note).toBe('Internal estimates only');
    expect(payload.levers[0].brsr_principle).toBe('P3');
    expect(payload.levers[0].effort_weeks).toEqual({ p10: 15, p50: 20, p90: 25 });
    expect(payload.levers[0].p50_pct).toBe(9);
  });

  it('preserves hidden benchmark metadata on save', () => {
    const draft = parseDetailToDraft('benchmarks', mockDetail) as BenchmarksDraft;
    const edited = {
      ...draft,
      categories: draft.categories.map((row) =>
        row.category_id === 'IT_SOFTWARE' ? { ...row, P50: 8 } : row,
      ),
    };
    const payload = serializeDraftToPayload('benchmarks', edited, mockDetail) as {
      source_metadata: { primary_sources?: unknown[]; methodology?: string };
      benchmarks: Record<string, { categories: Record<string, { P50?: number; linked_levers?: string[] }> }>;
    };
    expect(payload.source_metadata.primary_sources).toHaveLength(1);
    expect(payload.source_metadata.methodology).toBe('Peer-derived percentiles');
    expect(payload.benchmarks.bfsi_banks.categories.IT_SOFTWARE.P50).toBe(8);
    expect(payload.benchmarks.bfsi_banks.categories.IT_SOFTWARE.linked_levers).toBeUndefined();
  });

  it('preserves peer_set metadata on save', () => {
    const draft = parseDetailToDraft('peers', mockDetail);
    const payload = serializeDraftToPayload('peers', draft, mockDetail) as {
      data_source?: string;
      refresh_date?: string;
    };
    expect(payload.data_source).toBe('BSE/NSE annual reports FY25');
    expect(payload.refresh_date).toBe('2026-04-01');
  });

  it('parses draft JSON for structured toggle', () => {
    const draft = parseDetailToDraft('taxonomy', mockDetail);
    const parsed = parseDraftFromJson('taxonomy', JSON.stringify(draft));
    expect(deepEqual(parsed, draft)).toBe(true);
  });
});
