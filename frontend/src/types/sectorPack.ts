export interface CategoryBenchmark {
  P25?: number;
  P50?: number;
  P75?: number;
  P90?: number;
  unit?: string;
  confidence?: string;
  source_note?: string;
  linked_levers?: string[];
}

export interface LeverRow {
  lever_id?: string;
  lever_name?: string;
  description?: string;
  category_ids?: string[];
  p10_pct?: number;
  p50_pct?: number;
  p90_pct?: number;
  implementation_weeks?: number;
  savings_type?: string;
  industry_sources?: string[];
  brsr_principle?: string;
  effort_weeks?: { p10?: number; p50?: number; p90?: number };
  [key: string]: unknown;
}

export interface KpiRow {
  kpi_id?: string;
  kpi_name?: string;
  unit?: string;
  formula?: string;
  target_direction?: string;
  p50_benchmark_pct?: number;
  p50_benchmark_cr?: number;
  p50_benchmark_inr?: number;
}

export interface PeerRow {
  name?: string;
  ticker?: string;
  exchange?: string;
  entity_type?: string;
  total_assets_cr?: number;
  revenue_cr?: number;
}

export interface TaxonomyCategoryRow {
  category_id?: string;
  category_name?: string;
  gl_prefix?: string;
  cost_nature?: string;
  brsr_principle?: string;
}

export interface TaxonomyOverrideRow {
  category_id?: string;
  category_name?: string;
  brsr_principle?: string;
}

export interface FreeSourceRow {
  id?: string;
  name?: string;
  url?: string;
  sample_metric?: string;
  refresh_frequency?: string;
  [key: string]: unknown;
}

export interface LicensedSourceStubRow {
  id?: string;
  name?: string;
  credential_env?: string;
  [key: string]: unknown;
}

export interface SectorPackRow {
  pack_id: string;
  sector?: string;
  version?: string;
  status?: string;
  error?: string;
  lever_count?: number;
  kpi_count?: number;
  peer_count?: number;
  category_count?: number;
}

export interface SectorPackDetailResponse {
  pack_id: string;
  sector?: string;
  version?: string;
  vintage_date?: string;
  confidence_overall?: string;
  source_metadata?: {
    methodology?: string;
    sample_size?: number;
    primary_sources?: Array<{ source_name?: string; source_type?: string; notes?: string }>;
  };
  manifest?: Record<string, unknown>;
  pack_error?: string | null;
  categories?: Record<string, CategoryBenchmark>;
  levers?: LeverRow[];
  levers_document?: Record<string, unknown>;
  benchmarks_document?: Record<string, unknown>;
  category_lever_map?: Record<string, string[]>;
  kpi_pack?: KpiRow[];
  peers?: PeerRow[];
  peer_set?: Record<string, unknown>;
  peer_benchmark_metrics?: Record<string, { p25?: number; p50?: number; p75?: number }>;
  taxonomy_extension?: {
    base_taxonomy_version?: string;
    additional_categories?: TaxonomyCategoryRow[];
    overrides?: TaxonomyOverrideRow[];
  };
  benchmark_sources?: {
    source_validation_date?: string;
    source_validation_note?: string;
    sector?: string;
    free_sources?: FreeSourceRow[];
    licensed_sources_stubs?: LicensedSourceStubRow[];
  };
  regulatory_layer?: string;
  counts?: {
    peer_count?: number;
    lever_count?: number;
    kpi_count?: number;
    category_count?: number;
  };
}

export type PackEditorTabId = 'taxonomy' | 'peers' | 'levers' | 'kpis' | 'benchmarks' | 'sources';

export interface TaxonomyDraft {
  base_taxonomy_version: string;
  additional_categories: TaxonomyCategoryRow[];
  overrides: TaxonomyOverrideRow[];
}

export interface PeerMetricDraftRow {
  key: string;
  p25?: number;
  p50?: number;
  p75?: number;
}

export interface PeersDraft {
  sector: string;
  currency: string;
  data_source: string;
  refresh_date: string;
  peers: PeerRow[];
  benchmark_metrics: PeerMetricDraftRow[];
}

export interface BenchmarkCategoryDraftRow {
  category_id: string;
  P25?: number;
  P50?: number;
  P75?: number;
  P90?: number;
  unit?: string;
  confidence?: string;
  source_note?: string;
}

export interface BenchmarksDraft {
  sector: string;
  version: string;
  vintage_date: string;
  confidence_overall: string;
  source_metadata: {
    methodology: string;
    sample_size: string;
  };
  categories: BenchmarkCategoryDraftRow[];
}

export interface SourcesDraft {
  source_validation_date: string;
  source_validation_note: string;
  sector: string;
  free_sources: FreeSourceRow[];
  licensed_sources_stubs: LicensedSourceStubRow[];
}

export interface LeversDraft {
  sector: string;
  source_type: string;
  source_verification_note: string;
  levers: LeverRow[];
}

export type PackEditorDraft =
  | TaxonomyDraft
  | PeersDraft
  | LeversDraft
  | KpiRow[]
  | BenchmarksDraft
  | SourcesDraft;

export const BENCHMARK_CONFIDENCE_OPTIONS = [
  { value: 'public_disclosure', label: 'Public disclosure' },
  { value: 'published_research', label: 'Published research' },
  { value: 'internal_calibration', label: 'Internal calibration' },
];

export const TARGET_DIRECTION_OPTIONS = [
  { value: 'lower', label: 'Lower' },
  { value: 'higher', label: 'Higher' },
];
