export interface QualitySignals {
  faithfulness_score?: number;
  relevance_score?: number;
  grounding_coverage?: number;
}

export interface ProgressStep {
  phase?: string;
  message?: string;
  status?: string;
}

export interface ChatNextOption {
  label: string;
  message: string;
}

export interface CategoryInsightRow {
  category_id: string;
  category_name: string;
  spend: number;
  share_of_total: number;
}

export interface ChartCategoryRow {
  category_id: string;
  category_name: string;
  spend: number;
  share_of_total: number;
  addressable_spend: number;
  variable_spend: number;
  fixed_spend: number;
  semi_variable_spend: number;
}

export interface SpendChartData {
  selected_charts: Array<{ chart: string; reason: string }>;
  commentary_points: string[];
  category_rows: ChartCategoryRow[];
  period_totals: Array<{ period: string; spend: number }>;
}

export interface AnalysisInsightSnapshot {
  total_spend: number;
  reporting_currency: string;
  line_count?: number;
  company_name?: string;
  industry?: string;
  top_categories: CategoryInsightRow[];
  peer_gap_count?: number;
  peer_comparison_count?: number;
  savings_headline?: string;
  savings_headline_raw?: number;
  ingestion_note?: string;
  chart_data?: SpendChartData;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  advisory_sections?: Record<string, unknown>;
  quality_signals?: QualitySignals;
  next_options?: ChatNextOption[];
  run_id?: string;
  progress_steps?: ProgressStep[];
  degraded_mode?: boolean;
  artefacts?: Record<string, unknown> | string[];
  insight_snapshot?: AnalysisInsightSnapshot;
  show_peer_savings?: boolean;
}

export interface SessionCreatePayload {
  company_name?: string;
  industry?: string;
  annual_revenue?: number;
  currency?: string;
  audience?: string;
}

export interface SessionResponse {
  session_id: string;
  company_name?: string;
  industry?: string;
  files?: unknown[];
  skill_outputs?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ManifestFileEntry {
  name?: string;
  content_type?: string;
  size_bytes?: number;
  path?: string;
  schema?: unknown;
}

export interface IngestionReport {
  source_file?: string;
  sheets_ingested?: Array<{ sheet?: string; rows?: number; strategy?: string }>;
  sheets_skipped?: Array<{ sheet?: string; role?: string; reason?: string }>;
  files?: IngestionReport[];
}

export interface ModelManifest {
  confidence?: number;
  ingestion_strategy?: string;
  ingestion_notes?: string;
  sheet_graph?: Array<{ sheet_name?: string; role?: string }>;
  model_type?: string;
  [key: string]: unknown;
}

export interface SessionManifest {
  session_id: string;
  company_name?: string;
  industry?: string;
  annual_revenue?: number;
  currency?: string;
  audience?: string;
  engagement_week?: number;
  engagement_weeks_total?: number;
  gate_label?: string;
  created_at?: string;
  files?: ManifestFileEntry[];
  model_manifest?: ModelManifest;
  ingestion_report?: IngestionReport;
}

export interface ChatProgressResponse {
  run_id: string;
  status: string;
  steps?: Array<{ phase?: string; message?: string; timestamp?: string }>;
  error?: string | null;
}

export interface SessionManifestPatch {
  industry?: string;
  company_name?: string;
  annual_revenue?: number;
  currency?: string;
}

export interface SessionSummary {
  session_id: string;
  company_name: string;
  industry: string;
  currency: string;
  annual_revenue?: number;
  created_at?: string;
  file_count: number;
  has_analysis: boolean;
  top_savings_estimate?: number;
}

export interface EngagementMeta {
  company_name: string;
  industry: string;
  currency: string;
  audience?: string;
  engagement_week: number;
  engagement_weeks_total: number;
  gate_label: string;
  annual_revenue_cr?: number;
}

export interface V1ChatPayload {
  message: string;
  session_id: string;
  user_id?: string;
  run_id?: string;
  company_name?: string;
  industry?: string;
  annual_revenue?: number;
  currency?: string;
  thinking_mode?: 'standard' | 'extended';
}

export interface V1ChatResponse {
  response_text: string;
  thinking?: string;
  artefacts?: Record<string, unknown>;
  advisory_sections?: Record<string, unknown>;
  quality_signals?: QualitySignals;
  degraded_mode?: boolean;
  fallback_reasons?: Record<string, unknown>;
  loop_complete?: boolean;
  next_loop_trigger?: string;
  progress_steps?: ProgressStep[];
  next_options?: ChatNextOption[];
  ingestion_summary?: string;
  run_id?: string;
}

export interface ChatPlanPreview {
  user_summary?: string;
  planned_skills?: string[];
  requires_confirmation?: boolean;
  [key: string]: unknown;
}

export interface ConflictSummary {
  total?: number;
  unresolved?: number;
  by_type?: Record<string, number>;
  by_severity?: Record<string, number>;
  conflicts?: Array<Record<string, unknown>>;
}

export interface ComplianceAuditResponse {
  entries: Array<Record<string, unknown>>;
  integrity: {
    status?: string;
    records?: number;
    chain_valid?: boolean;
    legacy_records?: number;
  };
}

export interface DiagnosticRequest {
  company_name: string;
  industry: string;
  annual_revenue_cr: number;
  urls: string[];
}

export interface DiagnosticResponse {
  company_name: string;
  industry_used: string;
  annual_revenue_cr: number;
  key_findings: string[];
  benchmark_gaps: Array<Record<string, unknown>>;
  value_at_table: Array<Record<string, unknown>>;
  company_signals: Record<string, unknown>;
  data_note?: string;
  url_errors?: Array<Record<string, string>>;
  total_p50_value_cr?: number;
}

export interface SkillMeta {
  name: string;
  path?: string;
  description?: string;
}

export interface SkillDetail {
  name: string;
  path: string;
  content: string;
}

export interface Initiative {
  initiative_id: string;
  category: string;
  lever: string;
  stage: string;
  net_npv?: number;
  committed_savings?: number;
  gross_savings_y1?: number;
  p10_savings?: number;
  p50_savings?: number;
  p90_savings?: number;
  ebitda_bps?: number;
  session_id?: string;
  root_cause?: string;
  description?: string;
  owner_name?: string;
  assumption_quality_score?: number;
  aqs?: number;
  sustainability_score?: number;
  bounce_back_risk?: string;
  savings_type?: string;
  addressability?: Record<string, number>;
  regulatory_override?: number;
  contract_window?: number;
  switching_cost?: number;
  cost_behaviour?: number;
  condition_precedents?: string[];
  assumptions?: Array<Record<string, unknown>>;
  [key: string]: unknown;
}

export interface SensitivityScenario {
  name: string;
  key_assumption?: string;
  savings_3yr?: number;
  ebitda_bps?: number;
  npv_aftertax?: number;
}

export interface SensitivityResponse {
  scenarios?: SensitivityScenario[];
  confidence_bands?: { low?: number; mid?: number; high?: number };
}

export interface PipelineSummary {
  stage_totals?: Record<string, { count: number; net_npv: number }>;
  total_committed_net_npv?: number;
  realization_rate_pct?: number;
  active_initiatives?: number;
  [key: string]: unknown;
}

export type PercentileBand = 'p10' | 'p50' | 'p90';

export interface AuditLogEntry {
  ts: string;
  message: string;
  source?: 'local' | 'server';
}

export interface DeepResearchStartResponse {
  interaction_id: string;
  status: string;
}

export interface DeepResearchSource {
  title?: string;
  url?: string;
}

export interface DeepResearchStatusResponse {
  status: 'in_progress' | 'completed' | 'failed';
  summary?: string;
  full_report?: string;
  sources?: DeepResearchSource[];
}

export interface DiagnosticContextPatch {
  company_name?: string;
  industry?: string;
  annual_revenue_cr?: number;
  deep_research_summary?: string;
  deep_research_interaction_id?: string;
}
