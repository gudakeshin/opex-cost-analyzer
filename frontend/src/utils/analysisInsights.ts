import { sectorLabel } from '../constants/sectors';
import type {
  AnalysisInsightSnapshot,
  CategoryInsightRow,
  ChartCategoryRow,
  ChatNextOption,
  SessionManifest,
  SessionResponse,
  SpendChartData,
} from '../types';

const PEER_SAVINGS_KEYWORDS =
  /\b(peer|benchmark|p75|p90|percentile|savings|opportunit|addressable|value bridge|value-at-the-table)\b/i;

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : null;
}

function currencySymbol(code: string): string {
  const c = code.toUpperCase();
  if (c === 'INR') return '₹';
  if (c === 'USD') return '$';
  if (c === 'EUR') return '€';
  if (c === 'GBP') return '£';
  return `${c} `;
}

export function formatSpendAmount(n: number, currency = 'INR'): string {
  const sym = currencySymbol(currency);
  if (currency.toUpperCase() === 'INR') {
    if (n >= 10_000_000) return `${sym}${(n / 10_000_000).toFixed(1)} Cr`;
    if (n >= 100_000) return `${sym}${(n / 100_000).toFixed(1)} L`;
    return `${sym}${n.toLocaleString('en-IN')}`;
  }
  if (n >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${sym}${(n / 1_000).toFixed(1)}K`;
  return `${sym}${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

function savingsHeadlineFromOutputs(
  skillOutputs: Record<string, unknown> | undefined,
  currency: string,
): { label: string; raw: number } | null {
  if (!skillOutputs) return null;
  const savingsModel = asRecord(skillOutputs['savings-modeler']);
  const topOpps = savingsModel?.top_opportunities;
  if (Array.isArray(topOpps) && topOpps.length > 0) {
    const first = asRecord(topOpps[0]);
    const amt = first?.estimated_savings ?? first?.savings_amount;
    if (typeof amt === 'number' && amt > 0) {
      return { label: formatSpendAmount(amt, currency), raw: amt };
    }
  }
  const valueBridge = asRecord(skillOutputs['value-bridge-calculator']);
  const tav = valueBridge?.total_addressable_value;
  if (typeof tav === 'number' && tav > 0) {
    return { label: formatSpendAmount(tav, currency), raw: tav };
  }
  return null;
}

function peerStatsFromOutputs(skillOutputs: Record<string, unknown> | undefined): {
  abovePeerCount: number;
  comparisonCount: number;
} {
  const peerBench = asRecord(skillOutputs?.['peer-benchmarker']);
  const comparisons = Array.isArray(peerBench?.comparisons) ? peerBench.comparisons : [];
  const abovePeerCount = comparisons.filter((c) => {
    const row = asRecord(c);
    const band = String(row?.percentile_band ?? '');
    return band.includes('P75') || band.includes('P90');
  }).length;
  return { abovePeerCount, comparisonCount: comparisons.length };
}

function ingestionNoteFromManifest(manifest: SessionManifest | null | undefined): string | undefined {
  const report = manifest?.ingestion_report;
  if (!report) return undefined;
  const ingested = report.sheets_ingested ?? [];
  if (ingested.length === 0) return undefined;
  const parts = ingested.map((s) => {
    const sheet = s.sheet ?? 'sheet';
    const rows = s.rows ?? 0;
    return `${sheet} (${rows} rows)`;
  });
  const conf = manifest?.model_manifest?.confidence;
  const confPct =
    typeof conf === 'number' && conf > 0 ? ` · structure confidence ${Math.round(conf * 100)}%` : '';
  return `Ingested ${parts.join(', ')}${confPct}.`;
}

export function extractInsightSnapshot(
  session: SessionResponse | null,
  manifest?: SessionManifest | null,
): AnalysisInsightSnapshot | null {
  if (!session?.skill_outputs) return null;
  const skillOutputs = session.skill_outputs as Record<string, unknown>;
  const spendProfiler = asRecord(skillOutputs['spend-profiler']);
  if (!spendProfiler) return null;

  const totalSpend = Number(spendProfiler.total_spend ?? 0);
  const reportingCurrency = String(
    session.reporting_currency ?? manifest?.currency ?? 'INR',
  );

  const categories = Array.isArray(spendProfiler.category_profile)
    ? (spendProfiler.category_profile as Array<Record<string, unknown>>)
    : [];
  const topCategories: CategoryInsightRow[] = categories
    .slice()
    .sort((a, b) => Number(b.spend ?? 0) - Number(a.spend ?? 0))
    .slice(0, 5)
    .map((cat) => ({
      category_id: String(cat.category_id ?? ''),
      category_name: String(cat.category_name ?? cat.category_id ?? 'Unknown'),
      spend: Number(cat.spend ?? 0),
      share_of_total: Number(cat.share_of_total ?? 0),
    }));

  const lineCount = Array.isArray(session.normalized_spend)
    ? session.normalized_spend.length
    : undefined;

  const peer = peerStatsFromOutputs(skillOutputs);
  const savings = savingsHeadlineFromOutputs(skillOutputs, reportingCurrency);

  const chartData = extractChartData(spendProfiler);

  return {
    total_spend: totalSpend,
    reporting_currency: reportingCurrency,
    line_count: lineCount,
    company_name: session.company_name ?? manifest?.company_name,
    industry: session.industry ?? manifest?.industry,
    top_categories: topCategories,
    peer_gap_count: peer.abovePeerCount,
    peer_comparison_count: peer.comparisonCount,
    savings_headline: savings?.label,
    savings_headline_raw: savings?.raw,
    ingestion_note: ingestionNoteFromManifest(manifest ?? null),
    chart_data: chartData ?? undefined,
  };
}

function extractChartData(spendProfiler: Record<string, unknown>): SpendChartData | null {
  const chartBuilder = asRecord(spendProfiler.chart_builder);
  const selectedCharts = Array.isArray(chartBuilder?.selected_charts)
    ? (chartBuilder!.selected_charts as Array<{ chart: string; reason: string }>)
    : [];
  const commentaryPoints = Array.isArray(chartBuilder?.commentary_points)
    ? (chartBuilder!.commentary_points as string[])
    : [];

  const rawCategories = Array.isArray(spendProfiler.category_profile)
    ? (spendProfiler.category_profile as Array<Record<string, unknown>>)
    : [];
  const categoryRows: ChartCategoryRow[] = rawCategories
    .slice()
    .sort((a, b) => Number(b.spend ?? 0) - Number(a.spend ?? 0))
    .slice(0, 8)
    .map((cat) => ({
      category_id: String(cat.category_id ?? ''),
      category_name: String(cat.category_name ?? cat.category_id ?? 'Unknown'),
      spend: Number(cat.spend ?? 0),
      share_of_total: Number(cat.share_of_total ?? 0),
      addressable_spend: Number(cat.addressable_spend ?? 0),
      variable_spend: Number(cat.variable_spend ?? 0),
      fixed_spend: Number(cat.fixed_spend ?? 0),
      semi_variable_spend: Number(cat.semi_variable_spend ?? 0),
    }));

  const rawPeriodTotals = asRecord(
    (asRecord(spendProfiler.trend_analysis))?.period_totals ?? null,
  );
  const periodTotals = rawPeriodTotals
    ? Object.entries(rawPeriodTotals)
        .map(([period, spend]) => ({ period, spend: Number(spend) }))
        .sort((a, b) => a.period.localeCompare(b.period))
    : [];

  if (selectedCharts.length === 0 && categoryRows.length === 0) return null;

  return { selected_charts: selectedCharts, commentary_points: commentaryPoints, category_rows: categoryRows, period_totals: periodTotals };
}

export function wantsPeerSavingsInsight(userMessage: string): boolean {
  return PEER_SAVINGS_KEYWORDS.test(userMessage);
}

export function buildDataRootedPrompts(
  snapshot: AnalysisInsightSnapshot | null,
  manifest?: SessionManifest | null,
): ChatNextOption[] {
  if (!snapshot || snapshot.total_spend <= 0) {
    return [
      { label: 'Run full analysis', message: 'Run full analysis on uploaded spend data' },
      { label: 'File format guide', message: 'What columns does my spend file need?' },
    ];
  }

  const opts: ChatNextOption[] = [];
  const cats = snapshot.top_categories;

  if (cats[0]) {
    opts.push({
      label: `Suppliers in ${cats[0].category_name}`,
      message: `Break down ${cats[0].category_name} spend by supplier`,
    });
  }
  if (cats[1]) {
    opts.push({
      label: `Drivers: ${cats[1].category_name}`,
      message: `What drives spend in ${cats[1].category_name}?`,
    });
  }
  if (cats[2]) {
    opts.push({
      label: `Trend: ${cats[2].category_name}`,
      message: `Summarize spend patterns in ${cats[2].category_name}`,
    });
  }

  if (manifest?.ingestion_report?.sheets_ingested?.length) {
    opts.push({
      label: 'Ingestion notes',
      message: 'Explain workbook ingestion results and any warnings',
    });
  }

  if (snapshot.line_count && snapshot.line_count > 0) {
    opts.push({
      label: 'Top suppliers',
      message: 'Show me the top 10 suppliers by spend',
    });
  }

  return opts.slice(0, 5);
}

export function buildDeepDivePrompts(snapshot: AnalysisInsightSnapshot | null): ChatNextOption[] {
  if (!snapshot || snapshot.total_spend <= 0) return [];
  const top = snapshot.top_categories[0];
  const opts: ChatNextOption[] = [
    {
      label: 'Peer benchmark gaps',
      message: 'Where are we above peer benchmarks?',
    },
    {
      label: 'Savings priorities',
      message: 'What savings opportunities should we prioritize?',
    },
  ];
  if (top) {
    opts.push({
      label: `Peer: ${top.category_name}`,
      message: `How does ${top.category_name} compare to industry peers?`,
    });
  }
  return opts.slice(0, 3);
}

export function buildWelcomePrompts(
  snapshot: AnalysisInsightSnapshot | null,
  manifest?: SessionManifest | null,
): ChatNextOption[] {
  const rooted = buildDataRootedPrompts(snapshot, manifest);
  if (rooted.length > 0 && snapshot && snapshot.total_spend > 0) return rooted;
  return [
    { label: 'Summarize spend', message: 'Summarize spend concentration by category' },
    { label: 'Top suppliers', message: 'Show me the top 10 suppliers by spend' },
    { label: 'Run analysis', message: 'Run full analysis on uploaded spend data' },
  ];
}

export function buildAnalyzeCompleteContent(snapshot: AnalysisInsightSnapshot): string {
  const company = snapshot.company_name && snapshot.company_name !== 'New engagement'
    ? snapshot.company_name
    : 'your engagement';
  const sector = sectorLabel(snapshot.industry);
  const spend = formatSpendAmount(snapshot.total_spend, snapshot.reporting_currency);
  const lines = snapshot.line_count ? ` · ${snapshot.line_count.toLocaleString()} lines` : '';
  return `Analysis complete for **${company}** (${sector}). Total spend signal: **${spend}**${lines}.`;
}

export function chatHasInsightSnapshot(messages: { insight_snapshot?: AnalysisInsightSnapshot }[]): boolean {
  return messages.some((m) => m.insight_snapshot != null && m.insight_snapshot.total_spend > 0);
}

export function buildRestoredInsightMessage(
  snapshot: AnalysisInsightSnapshot,
  manifest?: SessionManifest | null,
): {
  role: 'assistant';
  content: string;
  insight_snapshot: AnalysisInsightSnapshot;
  next_options: ChatNextOption[];
} {
  return {
    role: 'assistant',
    content: buildAnalyzeCompleteContent(snapshot),
    insight_snapshot: snapshot,
    next_options: buildDataRootedPrompts(snapshot, manifest),
  };
}
