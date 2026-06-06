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

/** Render-agnostic chart suggested by the LLM and filled with real numbers by the backend. */
export type ChartType =
  | 'bar'
  | 'hbar'
  | 'line'
  | 'stacked_bar'
  | 'grouped_bar'
  | 'pie'
  | 'waterfall'
  | 'scatter';

export type ChartUnit = 'currency' | 'percent' | 'count' | 'days' | 'ratio';

export interface ChartSeries {
  key: string;
  name: string;
  color?: string | null;
}

export interface ChartSpec {
  id: string;
  type: ChartType;
  title: string;
  rationale?: string;
  x_key: string;
  x_label?: string;
  y_label?: string;
  unit: ChartUnit;
  series: ChartSeries[];
  data: Array<Record<string, string | number | boolean | null>>;
  source_skill?: string;
}

export interface SmeQualificationSummary {
  ready_count: number;
  probe_count: number;
  insufficient_count: number;
  savings_ready: number;
  savings_probe: number;
  savings_insufficient: number;
}

export interface EvidenceSignal {
  status: 'found' | 'partial' | 'missing' | 'not_applicable';
  source: string;
  provenance: string[];
  summary: string;
}

export interface SmeInitiativeCritique {
  initiative_id: string;
  category_id: string;
  category_name: string;
  lever: string;
  lever_name: string;
  modelled_saving_3yr: number;
  evidence_maturity: 'hypothesis' | 'indicative' | 'supported' | 'validated';
  sme_verdict: 'proceed' | 'probe_first' | 'insufficient_data';
  critical_risk: string;
  probe_questions: Array<{
    question: string;
    why_critical: string;
    saving_at_stake: number;
    data_to_request: string;
  }>;
  double_count_risk?: string | null;
  evidence_sources?: Record<string, string>;
  gaps?: string[];
  evidence_signals?: Record<string, EvidenceSignal>;
}

export interface PortfolioProbe {
  probe_family_id: string;
  question: string;
  why_critical: string;
  saving_at_stake: number;
  scope?: 'portfolio' | 'category';
  affected_categories?: string[];
  options?: string[];
  data_to_request?: string;
}

export interface ProbeAnswerRecord {
  probe_family_id: string;
  question?: string;
  answer: string;
  selected_option?: string | null;
  scope?: string;
  applies_to_categories?: string[];
  answered_at?: string;
}

export interface AnalysisInsightSnapshot {
  total_spend: number;
  reporting_currency: string;
  spend_base_revision?: number;
  line_count?: number;
  company_name?: string;
  industry?: string;
  top_categories: CategoryInsightRow[];
  peer_gap_count?: number;
  peer_comparison_count?: number;
  savings_headline?: string;
  savings_headline_raw?: number;
  modelled_savings?: string;
  modelled_savings_raw?: number;
  savings_opportunity_count?: number;
  ingestion_note?: string;
  chart_data?: SpendChartData;
  sme_qualification?: SmeQualificationSummary;
  sme_initiative_critiques?: SmeInitiativeCritique[];
  portfolio_probes?: PortfolioProbe[];
}

export interface AnalysisTraceStep {
  step: number;
  phase: string;
  title: string;
  detail: string;
  source_documents: string[];
  metrics?: Record<string, unknown>;
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
  analysis_trace?: AnalysisTraceStep[];
  show_peer_savings?: boolean;
  charts?: ChartSpec[];
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
  annual_revenue?: number;
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

export interface IngestionQuality {
  rows_parsed?: number;
  rows_with_amount?: number;
  total_amount?: number;
  zero_spend_warning?: boolean;
  column_mapping_note?: string;
}

export interface IngestionReport {
  source_file?: string;
  sheets_ingested?: Array<{ sheet?: string; rows?: number; strategy?: string }>;
  sheets_skipped?: Array<{ sheet?: string; role?: string; reason?: string }>;
  layout?: string;
  warnings?: string[];
  quality?: IngestionQuality;
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

export interface EngagementSummary {
  engagement_id: string;
  company_name: string;
  industry: string;
  currency: string;
  annual_revenue?: number;
  created_at?: string;
  updated_at?: string;
  session_count: number;
  document_count: number;
  documents_ready: number;
}

export interface EngagementDocument {
  document_id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
  role?: 'spend_tabular' | 'context_doc' | 'mixed';
  status?: 'pending' | 'processing' | 'ready' | 'failed';
  parse_backend?: string | null;
  error?: string | null;
  uploaded_at?: string;
  processed_at?: string | null;
  text_preview?: string | null;
  line_count?: number;
  warnings?: string[];
}

export interface SessionManifest {
  session_id: string;
  engagement_id?: string;
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
  diagnostic_urls?: string[];
  diagnostic_result?: DiagnosticResponse;
  diagnostic_completed_at?: string;
  deep_research_interaction_id?: string;
  deep_research_prompt?: string;
  deep_research_summary?: string;
  deep_research_full_report?: string;
  deep_research_completed_at?: string;
  engagement_sanity?: EngagementSanity;
  probe_answers?: ProbeAnswerRecord[];
}

export interface ProbeAnswerResponse {
  response_text: string;
  probe_answer?: ProbeAnswerRecord;
  answered_probe_families?: string[];
  remaining_probe_count?: number;
  loop_complete?: boolean;
}

export interface EngagementSanityConflict {
  kind: string;
  severity?: string;
  engagement_company?: string;
  detected_company?: string;
  detected_companies?: string[];
  source?: string;
  signal_source?: string;
  message?: string;
}

export interface EngagementSanity {
  engagement_company?: string | null;
  has_diagnostic_context?: boolean;
  upload_signals?: Array<{ source?: string; file?: string; company_guess?: string }>;
  conflicts?: EngagementSanityConflict[];
  has_conflicts?: boolean;
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
  engagement_id?: string;
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
  // Auto-detected recommendations from uploaded documents (override-able).
  detected_company_name?: string;
  detected_industry?: string;
  detected_industry_label?: string;
}

export interface ChatHistoryTurn {
  role: string;
  content: string;
}

export interface ChatResponseMetadata {
  insight_dimension?: string;
  focus_category?: string;
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
  audience?: string;
  thinking_mode?: 'standard' | 'extended';
  chat_history?: ChatHistoryTurn[];
}

export interface BusinessClarification {
  question: string;
  options: string[];
  reasoning: string;
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
  hitl_required?: boolean;
  checkpoint_id?: string;
  clarification?: BusinessClarification;
  response_metadata?: ChatResponseMetadata;
  charts?: ChartSpec[];
}

export interface ChatPlanPreview {
  user_summary?: string;
  planned_skills?: string[];
  requires_confirmation?: boolean;
  hitl_required?: boolean;
  checkpoint_id?: string;
  clarification?: BusinessClarification;
  clarification_required?: boolean;
  clarification_prompt?: string;
  [key: string]: unknown;
}

export interface DataConflict {
  conflict_id?: string;
  conflict_type?: string;
  severity?: string;
  source_a?: string;
  source_b?: string;
  amount_a?: number;
  amount_b?: number;
  delta_pct?: number;
  resolution_strategy?: string;
  resolved?: boolean;
  resolution_notes?: string;
  title?: string;
  description?: string;
  recommendation?: string;
  action_label?: string;
  requires_manual_review?: boolean;
  can_auto_apply?: boolean;
  user_status?: 'applied' | 'flagged_for_review';
  estimated_spend_impact?: number;
}

export interface ConflictSpendImpact {
  prior_total_spend?: number;
  new_total_spend?: number;
  spend_delta?: number;
  lines_excluded?: number;
  excluded_spend?: number;
  spend_base_revision?: number;
  initiatives_refresh_required?: boolean;
}

export interface ConflictSummary {
  total?: number;
  unresolved?: number;
  auto_resolvable?: number;
  requires_escalation?: number;
  by_type?: Record<string, number>;
  by_severity?: Record<string, number>;
  conflicts?: DataConflict[];
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
  engagement_id?: string;
}

export interface BenchmarkGapRow {
  category?: string;
  category_id?: string;
  category_name?: string;
  p25_pct?: number;
  p50_pct?: number;
  gap_cr?: number;
  implied_p50_cr?: number;
  benchmark_p50_to_p25_band_cr?: number;
  headroom_to_p25_cr?: number;
  percentile_band?: string;
  commentary?: string;
  [key: string]: unknown;
}

export interface ValueDerivation {
  base_spend_cr?: number;
  base_spend_label?: string;
  base_spend_source?: string;
  base_spend_note?: string;
  savings_rate_p10_pct?: number;
  savings_rate_p50_pct?: number;
  savings_rate_p90_pct?: number;
  calculation_p10?: string;
  calculation_p50?: string;
  calculation_p90?: string;
}

export interface ValueAtTableRow {
  lever_id?: string;
  lever_name?: string;
  category?: string;
  base_spend_cr?: number;
  base_spend_label?: string;
  p10_cr?: number;
  p50_cr?: number;
  p90_cr?: number;
  npv?: number;
  savings_type?: string;
  savings_type_label?: string;
  complexity_tier?: string;
  rationale?: string;
  calculation_note?: string;
  value_derivation?: ValueDerivation;
  [key: string]: unknown;
}

export interface ValueAtTableMethodology {
  summary?: string;
  steps?: string[];
  eligible_levers_total?: number;
  shown_levers?: number;
}

export interface DiagnosticResponse {
  company_name: string;
  industry_used: string;
  annual_revenue_cr: number;
  key_findings: string[];
  benchmark_gaps: BenchmarkGapRow[];
  value_at_table: ValueAtTableRow[];
  company_signals: Record<string, unknown>;
  data_note?: string;
  url_errors?: Array<Record<string, string>>;
  total_p50_value_cr?: number;
  percentile_legend?: Record<string, string>;
  assumptions?: Record<string, unknown>;
  executive_summary?: string;
  eligible_levers_total?: number;
  profile_basis?: string;
  value_at_table_methodology?: ValueAtTableMethodology;
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
  diagnostic_urls?: string[];
  diagnostic_result?: DiagnosticResponse;
  diagnostic_completed_at?: string;
}
