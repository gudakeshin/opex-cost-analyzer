import { sectorLabel } from '../constants/sectors';
import type {
  AnalysisInsightSnapshot,
  CategoryInsightRow,
  ChartCategoryRow,
  ChatNextOption,
  SessionManifest,
  SessionResponse,
  SmeInitiativeCritique,
  SmeQualificationSummary,
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

function smeQualificationFromOutputs(skillOutputs: Record<string, unknown> | undefined): {
  summary: SmeQualificationSummary | null;
  critiques: SmeInitiativeCritique[];
} {
  const sme = asRecord(skillOutputs?.['sme-critique']);
  if (!sme) return { summary: null, critiques: [] };

  const summary = asRecord(sme.critique_summary);
  const parsed: SmeQualificationSummary | null = summary
    ? {
        ready_count: Number(summary.ready_count ?? 0),
        probe_count: Number(summary.probe_count ?? 0),
        insufficient_count: Number(summary.insufficient_count ?? 0),
        savings_ready: Number(summary.savings_ready ?? 0),
        savings_probe: Number(summary.savings_probe ?? 0),
        savings_insufficient: Number(summary.savings_insufficient ?? 0),
      }
    : null;

  const raw = Array.isArray(sme.initiative_critiques) ? (sme.initiative_critiques as unknown[]) : [];
  const critiques: SmeInitiativeCritique[] = raw
    .map((c) => {
      const r = asRecord(c);
      if (!r) return null;
      return {
        initiative_id: String(r.initiative_id ?? ''),
        category_id: String(r.category_id ?? ''),
        category_name: String(r.category_name ?? ''),
        lever: String(r.lever ?? ''),
        lever_name: String(r.lever_name ?? ''),
        modelled_saving_3yr: Number(r.modelled_saving_3yr ?? 0),
        evidence_maturity: (r.evidence_maturity ?? 'hypothesis') as SmeInitiativeCritique['evidence_maturity'],
        sme_verdict: (r.sme_verdict ?? 'insufficient_data') as SmeInitiativeCritique['sme_verdict'],
        critical_risk: String(r.critical_risk ?? ''),
        probe_questions: Array.isArray(r.probe_questions)
          ? (r.probe_questions as unknown[]).map((q) => {
              const pq = asRecord(q) ?? {};
              return {
                question: String(pq.question ?? ''),
                why_critical: String(pq.why_critical ?? ''),
                saving_at_stake: Number(pq.saving_at_stake ?? 0),
                data_to_request: String(pq.data_to_request ?? ''),
              };
            })
          : [],
        double_count_risk: r.double_count_risk != null ? String(r.double_count_risk) : null,
      } satisfies SmeInitiativeCritique;
    })
    .filter(Boolean) as SmeInitiativeCritique[];

  return { summary: parsed, critiques };
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
  const mapping = report.quality?.column_mapping_note;
  const mappingNote = mapping ? ` ${mapping}` : '';
  return `Ingested ${parts.join(', ')}${confPct}.${mappingNote}`;
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

  // Modelled savings total (value bridge mid-case) + number of distinct
  // initiatives, so the post-analysis brief can quantify the opportunity even
  // when peer benchmarks are unavailable (e.g. no revenue supplied).
  const bridge = asRecord(skillOutputs['value-bridge-calculator']);
  const midRaw = Number(asRecord(bridge?.confidence_bands)?.mid ?? 0);
  const savingsModel = asRecord(skillOutputs['savings-modeler']);
  const initiativesArr = Array.isArray(savingsModel?.initiatives)
    ? (savingsModel!.initiatives as Array<Record<string, unknown>>)
    : [];
  const oppCount = initiativesArr.filter(
    (i) => Number(asRecord(i.net_savings)?.total_3yr ?? 0) > 0,
  ).length;

  const chartData = extractChartData(spendProfiler);
  const smeData = smeQualificationFromOutputs(skillOutputs);

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
    modelled_savings: midRaw > 0 ? formatSpendAmount(midRaw, reportingCurrency) : undefined,
    modelled_savings_raw: midRaw > 0 ? midRaw : undefined,
    savings_opportunity_count: oppCount > 0 ? oppCount : undefined,
    ingestion_note: ingestionNoteFromManifest(manifest ?? null),
    chart_data: chartData ?? undefined,
    sme_qualification: smeData.summary ?? undefined,
    sme_initiative_critiques: smeData.critiques.length > 0 ? smeData.critiques : undefined,
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

const CONFLICT_QUERY_PATTERN =
  /\b(tds|gst|gstr|vendor conflict|vendor duplicate|cross-?source|conflict|mismatch)\b/i;

export function isComplianceOrConflictQuery(userMessage: string): boolean {
  return CONFLICT_QUERY_PATTERN.test(userMessage);
}

export interface TopProbeQuestion {
  question: string;
  category_name: string;
  why_critical: string;
  saving_at_stake: number;
}

export function collectTopProbeQuestions(
  snapshot: AnalysisInsightSnapshot | null,
  limit = 5,
): TopProbeQuestion[] {
  const critiques = snapshot?.sme_initiative_critiques ?? [];
  const flat: TopProbeQuestion[] = [];
  for (const c of critiques) {
    for (const pq of c.probe_questions ?? []) {
      if (!pq.question?.trim()) continue;
      flat.push({
        question: pq.question.trim(),
        category_name: c.category_name,
        why_critical: pq.why_critical,
        saving_at_stake: pq.saving_at_stake > 0 ? pq.saving_at_stake : c.modelled_saving_3yr,
      });
    }
  }
  flat.sort((a, b) => b.saving_at_stake - a.saving_at_stake);
  const seen = new Set<string>();
  const out: TopProbeQuestion[] = [];
  for (const p of flat) {
    const stem = p.question.slice(0, 80);
    if (seen.has(stem)) continue;
    seen.add(stem);
    out.push(p);
    if (out.length >= limit) break;
  }
  return out;
}

export function buildProbePrompts(snapshot: AnalysisInsightSnapshot | null): ChatNextOption[] {
  return collectTopProbeQuestions(snapshot, 3).map((p) => {
    const shortQ = p.question.length > 52 ? `${p.question.slice(0, 49)}…` : p.question;
    return {
      label: `${p.category_name}: ${shortQ}`,
      message: p.question,
    };
  });
}

export function mergeNextOptions(...groups: Array<ChatNextOption[] | undefined>): ChatNextOption[] {
  const seen = new Set<string>();
  const out: ChatNextOption[] = [];
  for (const group of groups) {
    for (const opt of group ?? []) {
      if (!opt.message || seen.has(opt.message)) continue;
      seen.add(opt.message);
      out.push(opt);
    }
  }
  return out.slice(0, 8);
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
  const ccy = snapshot.reporting_currency;
  const spend = formatSpendAmount(snapshot.total_spend, ccy);
  const cats = snapshot.top_categories ?? [];
  const lines: string[] = [];

  lines.push(`**Analysis complete — ${company}** (${sector})`);
  const lineNote = snapshot.line_count ? ` across ${snapshot.line_count.toLocaleString()} lines` : '';
  lines.push(`Total spend signal: **${spend}**${lineNote}.`);

  if (cats.length > 0) {
    lines.push('');
    lines.push('**Where the money goes**');
    cats.slice(0, 3).forEach((c) => {
      const share = c.share_of_total > 0 ? `${(c.share_of_total * 100).toFixed(1)}%` : '—';
      lines.push(`• ${c.category_name} — ${formatSpendAmount(c.spend, ccy)} (${share})`);
    });
    const top = cats[0];
    if (top.share_of_total >= 0.4) {
      lines.push(
        `Spend is concentrated — **${top.category_name}** alone is ${(top.share_of_total * 100).toFixed(0)}% of the base, the highest-leverage place to start.`,
      );
    }
  }

  if (snapshot.modelled_savings && snapshot.savings_opportunity_count) {
    const n = snapshot.savings_opportunity_count;
    lines.push('');
    lines.push(
      `**Modelled savings: ${snapshot.modelled_savings}** (mid-case, 3-yr net) across ${n} initiative${n > 1 ? 's' : ''}.`,
    );
  } else if (snapshot.savings_headline) {
    lines.push('');
    lines.push(`**Top savings signal:** ${snapshot.savings_headline}`);
  }

  if ((snapshot.peer_comparison_count ?? 0) > 0) {
    const gaps = snapshot.peer_gap_count ?? 0;
    lines.push(
      gaps > 0
        ? `Benchmarked ${snapshot.peer_comparison_count} categories — **${gaps} above peer P75**.`
        : `Benchmarked ${snapshot.peer_comparison_count} categories against peers.`,
    );
  } else if (snapshot.total_spend > 0) {
    lines.push('');
    lines.push('Tip: add annual revenue on the Diagnostic tab to unlock peer-benchmark gaps.');
  }

  // SME qualification block — only shown when there are initiatives to probe
  const sme = snapshot.sme_qualification;
  if (sme && (sme.probe_count > 0 || sme.insufficient_count > 0)) {
    lines.push('');
    lines.push('**Before we call this a value case — SME read:**');
    if (sme.ready_count > 0 && sme.savings_ready > 0) {
      lines.push(
        `✓ Ready for business case: **${formatSpendAmount(sme.savings_ready, ccy)}** (${sme.ready_count} initiative${sme.ready_count !== 1 ? 's' : ''})`,
      );
    }
    if (sme.probe_count > 0 && sme.savings_probe > 0) {
      lines.push(
        `⚑ Needs probing first: **${formatSpendAmount(sme.savings_probe, ccy)}** (${sme.probe_count} initiative${sme.probe_count !== 1 ? 's' : ''})`,
      );
    }
    if (sme.insufficient_count > 0 && sme.savings_insufficient > 0) {
      lines.push(
        `✗ Insufficient data to model: **${formatSpendAmount(sme.savings_insufficient, ccy)}** (${sme.insufficient_count} initiative${sme.insufficient_count !== 1 ? 's' : ''})`,
      );
    }
    const probeTotal = sme.savings_probe + sme.savings_insufficient;
    const topProbes = collectTopProbeQuestions(snapshot, 5);
    if (probeTotal > 0) {
      lines.push(
        `Answer the probe questions below to move **${formatSpendAmount(probeTotal, ccy)}** from hypothesis to evidenced case.`,
      );
    }
    if (topProbes.length > 0) {
      lines.push('');
      lines.push('**Probe questions**');
      topProbes.forEach((p, idx) => {
        lines.push(`${idx + 1}. **${p.category_name}** — ${p.question}`);
      });
    } else if (probeTotal > 0) {
      lines.push('');
      lines.push(
        '_Probe questions are not available in this session export — re-run analysis or open Insights for initiative-level detail._',
      );
    }
  }

  return lines.join('\n');
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
  show_peer_savings: boolean;
  next_options: ChatNextOption[];
} {
  return {
    role: 'assistant',
    content: buildAnalyzeCompleteContent(snapshot),
    insight_snapshot: snapshot,
    show_peer_savings: true,
    next_options: mergeNextOptions(buildProbePrompts(snapshot), buildDataRootedPrompts(snapshot, manifest)),
  };
}

export interface SavingsInitiativeSummary {
  category_id: string;
  category_name: string;
  lever: string;
  lever_name: string;
  net_savings_3yr: number;
  confidence: string;
}

export interface RootCauseFinding {
  category_name: string;
  diagnosis: string;
  recommended_lever: string;
  confidence: string;
}

export interface AnomalyFlag {
  category_id: string;
  category_name: string;
  actual_pct_of_revenue: number;
  heuristic_target_pct: number;
  estimated_saving_amount: number;
}

export interface PeerGapDetail {
  category_id: string;
  category_name: string;
  percentile_band: string;
  actual_pct_of_revenue: number;
  benchmark_target_pct: number;
  estimated_saving_amount: number;
}

export function extractTopSavingsInitiatives(
  skillOutputs: Record<string, unknown> | undefined,
  topN = 3,
): SavingsInitiativeSummary[] {
  if (!skillOutputs) return [];
  const sm = asRecord(skillOutputs['savings-modeler']);
  return (Array.isArray(sm?.initiatives) ? (sm!.initiatives as Array<Record<string, unknown>>) : [])
    .map((i) => ({
      category_id: String(i.category_id ?? '').toLowerCase(),
      category_name: String(i.category_name ?? i.category_id ?? 'Unknown'),
      lever: String(i.lever ?? ''),
      lever_name: String(i.lever_name ?? i.lever ?? 'Unknown lever'),
      net_savings_3yr: Number(asRecord(i.net_savings)?.total_3yr ?? 0),
      confidence: String(i.confidence ?? 'medium'),
    }))
    .filter((i) => i.net_savings_3yr > 0)
    .sort((a, b) => b.net_savings_3yr - a.net_savings_3yr)
    .slice(0, topN);
}

export function extractRootCauseFindings(
  skillOutputs: Record<string, unknown> | undefined,
  topN = 4,
): RootCauseFinding[] {
  if (!skillOutputs) return [];
  const rc = asRecord(skillOutputs['root-cause-analyzer']);
  return (Array.isArray(rc?.root_cause_findings) ? (rc!.root_cause_findings as Array<Record<string, unknown>>) : [])
    .slice(0, topN)
    .map((f) => {
      const causes = Array.isArray(f.root_causes) ? (f.root_causes as Array<Record<string, unknown>>) : [];
      const top = causes[0] ?? {};
      return {
        category_name: String(f.category_name ?? f.category_id ?? 'Unknown'),
        diagnosis: String(top.diagnosis ?? 'No diagnosis available'),
        recommended_lever: String(top.recommended_lever ?? ''),
        confidence: String(top.confidence ?? 'low'),
      };
    });
}

export function extractAnomalyFlags(
  skillOutputs: Record<string, unknown> | undefined,
  topN = 5,
): AnomalyFlag[] {
  if (!skillOutputs) return [];
  const ha = asRecord(skillOutputs['heuristic-analyzer']);
  return (Array.isArray(ha?.heuristic_findings) ? (ha!.heuristic_findings as Array<Record<string, unknown>>) : [])
    .filter((f) => Number(f.estimated_saving_amount ?? 0) > 0)
    .slice(0, topN)
    .map((f) => ({
      category_id: String(f.category_id ?? ''),
      category_name: String(f.category_name ?? f.category_id ?? 'Unknown'),
      actual_pct_of_revenue: Number(f.actual_pct_of_revenue ?? 0),
      heuristic_target_pct: Number(f.heuristic_target_pct ?? 0),
      estimated_saving_amount: Number(f.estimated_saving_amount ?? 0),
    }));
}

export function extractPeerGapDetails(
  skillOutputs: Record<string, unknown> | undefined,
  topN = 3,
): PeerGapDetail[] {
  if (!skillOutputs) return [];
  const pb = asRecord(skillOutputs['peer-benchmarker']);
  return (Array.isArray(pb?.comparisons) ? (pb!.comparisons as Array<Record<string, unknown>>) : [])
    .filter((c) => { const b = String(c.percentile_band ?? ''); return b.includes('P75') || b.includes('P90'); })
    .sort((a, b) => Number(b.estimated_saving_amount ?? 0) - Number(a.estimated_saving_amount ?? 0))
    .slice(0, topN)
    .map((c) => ({
      category_id: String(c.category_id ?? ''),
      category_name: String(c.category_name ?? c.category_id ?? 'Unknown'),
      percentile_band: String(c.percentile_band ?? ''),
      actual_pct_of_revenue: Number(c.actual_pct_of_revenue ?? 0),
      benchmark_target_pct: Number(c.benchmark_target_pct ?? 0),
      estimated_saving_amount: Number(c.estimated_saving_amount ?? 0),
    }));
}
