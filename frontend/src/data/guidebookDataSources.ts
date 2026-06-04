export type GuidebookTierId =
  | 'tier1'
  | 'tier2'
  | 'tier3'
  | 'tier4'
  | 'tier5';

export interface GuidebookDataSource {
  id: string;
  name: string;
  whatToProvide: string;
  whyRequired: string;
  valueAdded: string;
  platformSignals?: string[];
}

export interface GuidebookTier {
  id: GuidebookTierId;
  title: string;
  subtitle: string;
  badge: string;
  badgeTone: 'required' | 'deep' | 'enrichment' | 'external' | 'sector';
  overview: string;
  sources: GuidebookDataSource[];
}

export const GUIDEBOOK_TIERS: GuidebookTier[] = [
  {
    id: 'tier1',
    title: 'Tier 1 — Minimum to run analysis',
    subtitle: 'Platform gates benchmark, value bridge, and business case intents without these.',
    badge: 'Required',
    badgeTone: 'required',
    overview:
      'These inputs are enforced during the Observe phase. Missing spend data, industry, or annual revenue triggers clarification and blocks deep analysis until resolved.',
    sources: [
      {
        id: 't1-spend-ledger',
        name: 'Transactional spend ledger',
        whatToProvide:
          'CSV or Excel (.csv, .xlsx, .xls) with supplier-level or line-item spend, ideally 12–36 months of history.',
        whyRequired:
          'Spend lines are the primary fact base. Without a tabular upload, the pipeline cannot profile categories, benchmark peers, or model savings.',
        valueAdded:
          'Powers spend-profiler, peer-benchmarker, internal-benchmarker, root-cause-analyzer, and all downstream value-bridge skills.',
        platformSignals: ['has_tabular_spend', 'spend_data in missing_fields if absent'],
      },
      {
        id: 't1-industry',
        name: 'Industry / sector',
        whatToProvide:
          'Sector code (e.g. fmcg_consumer, it_ites) in session or Diagnostic settings, or strong sector signals in uploaded documents.',
        whyRequired:
          'Peer percentiles and sector levers are loaded from sector packs; wrong sector misstates every gap and savings estimate.',
        valueAdded:
          'Selects the correct benchmark dataset, KPI pack, and sector-specific initiative playbooks.',
        platformSignals: ['industry in missing_fields for analysis intents'],
      },
      {
        id: 't1-revenue',
        name: 'Annual revenue',
        whatToProvide: 'Annual revenue in ₹ Cr entered in engagement or Diagnostic context.',
        whyRequired:
          'Benchmarks are expressed as % of revenue; savings and implied spend bands scale from this anchor.',
        valueAdded:
          'Normalizes category spend to peer P25/P50 bands and sizes addressable opportunity in Cr.',
        platformSignals: ['annual_revenue in missing_fields', 'data_quality_score'],
      },
      {
        id: 't1-company-name',
        name: 'Company name',
        whatToProvide: 'Legal or trading name used consistently across uploads and Diagnostic.',
        whyRequired:
          'Aligns diagnostic handoff, deep research briefs, and engagement sanity checks with the correct entity.',
        valueAdded:
          'Enables company-specific research, executive narrative, and multi-session continuity.',
      },
      {
        id: 't1-spend-columns',
        name: 'Core spend columns',
        whatToProvide:
          'Supplier (or description), amount, category or GL code, and spend date on every material row.',
        whyRequired:
          'Ingestion maps columns to NormalizedSpendLine; missing amount or description yields zero parsed spend.',
        valueAdded:
          'Reliable taxonomy mapping, supplier examples in recommendations, and temporal views.',
        platformSignals: ['semantic_map.amount', 'ingestion quality warnings'],
      },
    ],
  },
  {
    id: 'tier2',
    title: 'Tier 2 — Deep analysis (full value bridge)',
    subtitle: 'Unlocks modeling, validation, and executive-grade recommendations.',
    badge: 'Deep analysis',
    badgeTone: 'deep',
    overview:
      'Tier 2 feeds the full OPAR chain: root-cause → savings-modeler → value-bridge-calculator → data-validator → analysis-synthesizer. Without it, you get profiling and benchmarks only.',
    sources: [
      {
        id: 't2-gl-extract',
        name: 'GL / AP line-level extract',
        whatToProvide:
          '24–36 months: gl_code, cost_center, vendor, description, amount, currency, period, business_unit, geo.',
        whyRequired:
          'Line-level detail separates true category drivers from rolled-up P&L noise and supports supplier-level examples.',
        valueAdded:
          'Richer internal benchmarks, fragmentation signals, and named suppliers in synthesis output.',
      },
      {
        id: 't2-headcount',
        name: 'Headcount (aggregated)',
        whatToProvide:
          'Counts by BU, function, location, and band — no individual PII.',
        whyRequired:
          'Planning excludes heuristic-analyzer when headcount is missing; per-employee ratios cannot be computed.',
        valueAdded:
          'Cost-per-FTE heuristics, IT and HR efficiency ratios, and ZBB driver-based targets.',
        platformSignals: ['has_headcount', 'heuristic-analyzer in plan'],
      },
      {
        id: 't2-bva',
        name: 'Budget vs. actuals',
        whatToProvide:
          '24 months monthly; same taxonomy with amount_type budget and actual (forecast optional).',
        whyRequired:
          'BvA explains variance vs plan; peer benchmarks alone cannot answer “why are we over budget?”',
        valueAdded:
          'bva-analyzer price/volume/mix decomposition and leadership-ready variance narrative.',
      },
      {
        id: 't2-pnl',
        name: 'P&L / hierarchical expense workbook',
        whatToProvide:
          'Management P&L with line items and FY period columns; can complement a thin transactional ledger.',
        whyRequired:
          'Some clients only export summary expense tables; multi-sheet ingestion recovers category totals.',
        valueAdded:
          'Category coverage when ledger is incomplete; validates concentration vs P&L subtotals.',
        platformSignals: ['model_manifest.ingestion_strategy', 'sheet_graph roles'],
      },
      {
        id: 't2-vendor-master',
        name: 'Vendor master & material contracts',
        whatToProvide:
          'Full vendor list with category mapping; contracts above ₹1 Cr with key commercial terms.',
        whyRequired:
          'Consolidation and renegotiation levers need supplier identity and contract materiality thresholds.',
        valueAdded:
          'Supplier fragmentation, MSME checks, and credible consolidation / renegotiation initiatives.',
      },
      {
        id: 't2-documents',
        name: 'Supporting documents',
        whatToProvide:
          'PDF/DOCX/TXT: annual report, budget memo, procurement policy, org context, prior cost programmes (up to ~20 per session).',
        whyRequired:
          'Numbers alone miss locked contracts, strategic mandates, and non-addressable spend.',
        valueAdded:
          'document-contextualizer enriches synthesis; flags non-addressable and leadership priorities.',
      },
      {
        id: 't2-deep-research',
        name: 'Deep research context',
        whatToProvide:
          'Completed deep-research brief, or company + industry + revenue to run platform research.',
        whyRequired:
          'External evidence strengthens peer positioning and category narratives beyond uploaded spend.',
        valueAdded:
          'deep_research_context in analysis-synthesizer; credible citations and market constraints.',
      },
      {
        id: 't2-diagnostic-urls',
        name: 'Diagnostic URLs',
        whatToProvide: '1–5 public URLs: IR pages, exchange filings, credible news.',
        whyRequired:
          'Pre-spend diagnostic can infer industry signals and proxy benchmark gaps before ledger upload.',
        valueAdded:
          'Faster Week-0 positioning; document-contextualizer signals from public sources.',
      },
      {
        id: 't2-session-params',
        name: 'Financial modeling parameters',
        whatToProvide: 'WACC, effective tax rate, reporting currency in engagement settings.',
        whyRequired:
          'NPV, payback, and tax-affected savings require consistent finance assumptions.',
        valueAdded:
          'Value-bridge NPV bands and business-case-ready financials.',
      },
    ],
  },
  {
    id: 'tier3',
    title: 'Tier 3 — Confidence & lever-specific depth',
    subtitle: 'Optional fields that materially improve addressability and SME qualification.',
    badge: 'Enrichment',
    badgeTone: 'enrichment',
    overview:
      'Tier 3 does not always block analysis, but missing data lowers evidence maturity and triggers probe-first verdicts from the SME critique engine.',
    sources: [
      {
        id: 't3-contracts',
        name: 'Contract register',
        whatToProvide:
          'Expiry, status, auto-renewal notice, exit penalty, minimum commitment by supplier/category.',
        whyRequired:
          'Savings without contract evidence are scored as hypothesis; locked spend must be excluded from addressable totals.',
        valueAdded:
          'contract-lifecycle-manager; separates addressable vs locked-in spend; higher SME evidence score.',
        platformSignals: ['contract_expiry_date on NormalizedSpendLine', 'SME probe if missing'],
      },
      {
        id: 't3-payment-terms',
        name: 'Payment terms / AP aging',
        whatToProvide: 'payment_terms_days on spend lines, or invoice/payment dates to infer DPO.',
        whyRequired:
          'Payment-terms optimizer will not assume Net-30 without data.',
        valueAdded:
          'Working-capital release and cash-flow lever distinct from P&L savings.',
      },
      {
        id: 't3-india-compliance',
        name: 'India compliance fields',
        whatToProvide:
          'GST treatment, GSTIN, related-party flag, lease treatment (Ind AS 116) where applicable.',
        whyRequired:
          'India engagements need ITC, RCM, and related-party treatment for accurate addressability.',
        valueAdded:
          'MSME payment compliance, GSTR alignment, and intercompany elimination context.',
      },
      {
        id: 't3-multi-entity',
        name: 'Multi-entity / group structure',
        whatToProvide: 'Legal entity ID, intercompany flags, consolidation view preferences.',
        whyRequired:
          'Group uploads from multiple ERPs create conflicts without entity lineage.',
        valueAdded:
          'conflict-detector, consolidated benchmarks, and fair BU comparisons.',
        platformSignals: ['multi_source_upload', 'has_intercompany_lines'],
      },
      {
        id: 't3-source-lineage',
        name: 'Source system lineage',
        whatToProvide: 'source_system_id when merging SAP, Coupa, Oracle, or manual files.',
        whyRequired:
          'Duplicate or conflicting rows across systems need traceable provenance.',
        valueAdded:
          'Reconciliation across uploads; higher trust in merged spend totals.',
      },
      {
        id: 't3-operational-drivers',
        name: 'Operational drivers',
        whatToProvide:
          'Transaction volumes, customers, sq ft, plants — sector-dependent unit economics inputs.',
        whyRequired:
          'Heuristic analysis compares outcomes per dollar, not just spend level vs peers.',
        valueAdded:
          'Efficiency ratios and ZBB should-cost models grounded in operational reality.',
      },
      {
        id: 't3-temporal',
        name: 'Multi-period actuals',
        whatToProvide: 'fiscal_period and consistent actual rows across 12+ months.',
        whyRequired:
          'Single-period snapshots hide seasonality and one-off spikes.',
        valueAdded:
          'temporal-analyzer trend diagnostics alongside peer and BvA views.',
      },
      {
        id: 't3-segment-revenue',
        name: 'Segment revenue & entity tree',
        whatToProvide: 'BU revenue splits and group legal entity tree.',
        whyRequired:
          'Internal benchmarks across BUs need fair normalization by segment size.',
        valueAdded:
          'internal-benchmarker and conglomerate-normalized comparisons.',
      },
      {
        id: 't3-prior-programmes',
        name: 'Prior cost programmes',
        whatToProvide:
          'Consultant reports and internal audit of savings programmes from the last 3 years.',
        whyRequired:
          'Avoids double-counting initiatives already in flight or completed.',
        valueAdded:
          'Credible initiative pipeline and realistic execution assumptions.',
      },
      {
        id: 't3-calibration',
        name: 'Realised savings / calibration',
        whatToProvide: 'Post-engagement actuals vs modeled initiative outcomes.',
        whyRequired:
          'Models improve only when prior predictions are compared to realised results.',
        valueAdded:
          'Calibration reports and tightened confidence bands on future engagements.',
      },
    ],
  },
  {
    id: 'tier4',
    title: 'Tier 4 — External & public context',
    subtitle: 'Filings, capital structure, and market intelligence — often links rather than uploads.',
    badge: 'External',
    badgeTone: 'external',
    overview:
      'Tier 4 supports Diagnostic and deep research before full spend ingestion. It contextualizes constraints that never appear in a GL extract.',
    sources: [
      {
        id: 't4-brsr',
        name: 'BRSR disclosure',
        whatToProvide: 'Most recent filed Business Responsibility and Sustainability Report.',
        whyRequired:
          'ESG and disclosed spend patterns inform sector positioning and stakeholder-sensitive categories.',
        valueAdded:
          'Alignment with published commitments; avoids recommendations that contradict disclosed targets.',
      },
      {
        id: 't4-annual-report',
        name: 'Annual report & statutory filings',
        whatToProvide: 'Annual report and AOC-4 equivalents — 3 years for material entities.',
        whyRequired:
          'Revenue mix, capex commentary, and strategic narrative are not in transactional spend.',
        valueAdded:
          'Revenue-normalized benchmarks and context for growth vs cost-out mandates.',
      },
      {
        id: 't4-capex',
        name: 'Capex roster',
        whatToProvide: '36 months of capex history plus current-year commitment view.',
        whyRequired:
          'Capex and opex trade-offs must be separated; misclassification inflates addressable opex.',
        valueAdded:
          'Cleaner opex addressability and initiative scoping.',
      },
      {
        id: 't4-treasury',
        name: 'Treasury & FX',
        whatToProvide: 'Treasury policies and hedge book summary for FX-exposed categories.',
        whyRequired:
          'FX-driven cost moves can look like operational inefficiency in spend data alone.',
        valueAdded:
          'Correct interpretation of imported and hedged cost categories.',
      },
      {
        id: 't4-working-capital',
        name: 'Working capital pack',
        whatToProvide: 'DPO, DSO, DIO trends; debtors and creditors aging.',
        whyRequired:
          'Cross-validates payment-terms recommendations and cash-release claims.',
        valueAdded:
          'Consistent WC narrative alongside payment-terms-optimizer outputs.',
      },
      {
        id: 't4-market-intel',
        name: 'Peer & market intelligence',
        whatToProvide:
          'News, exchange disclosures, analyst notes from the last 12–24 months (or platform deep research).',
        whyRequired:
          'Explains why a category gap may or may not be actionable given market and regulatory context.',
        valueAdded:
          'Deep research brief: peer programs, margin pressure, and transformation constraints.',
      },
    ],
  },
  {
    id: 'tier5',
    title: 'Tier 5 — Sector-pack add-ons',
    subtitle: 'Customize the data request to the engagement industry code.',
    badge: 'Sector-specific',
    badgeTone: 'sector',
    overview:
      'Each sector pack under sector_packs/ includes KPI definitions and levers that expect industry-specific operational data beyond generic GL fields.',
    sources: [
      {
        id: 't5-manufacturing',
        name: 'Manufacturing',
        whatToProvide: 'Power consumption per plant, OEE, maintenance spend by asset class.',
        whyRequired:
          'Energy and maintenance levers are plant-driven; revenue % benchmarks alone are insufficient.',
        valueAdded:
          'Should-cost and utility optimization initiatives with operational proof points.',
      },
      {
        id: 't5-bfsi',
        name: 'Financial services (non-bank)',
        whatToProvide: 'Branch P&L, channel mix, processing volumes.',
        whyRequired:
          'Distribution cost structure varies by channel; peer SG&A % hides branch inefficiency.',
        valueAdded:
          'Channel-specific cost-to-serve and branch consolidation levers.',
      },
      {
        id: 't5-pharma',
        name: 'Pharma & life sciences',
        whatToProvide: 'USFDA/regulatory filings, plant compliance status, R&D vs commercial split.',
        whyRequired:
          'Compliance spend is often non-discretionary; must be carved out of addressable pools.',
        valueAdded:
          'Regulatory-aware savings sizing and realistic implementation timelines.',
      },
      {
        id: 't5-fmcg',
        name: 'FMCG / consumer',
        whatToProvide: 'Trade promotion, A&P allocation, logistics lane mix.',
        whyRequired:
          'Highest spend volatility is in promo and logistics — not visible in generic IT/Facilities taxonomy.',
        valueAdded:
          'Category-specific promo and logistics levers (see data/samples HUL test pack).',
      },
      {
        id: 't5-it-ites',
        name: 'IT / ITeS',
        whatToProvide: 'Offshore/onshore mix, utilization, vendor pyramid by skill band.',
        whyRequired:
          'Labor arbitrage and pyramid shape drive addressability more than peer % of revenue.',
        valueAdded:
          'Delivery-model and vendor-mix initiatives with FTE-linked savings.',
      },
      {
        id: 't5-energy',
        name: 'Energy & utilities',
        whatToProvide: 'Regulated vs merchant revenue split, fuel mix, network opex drivers.',
        whyRequired:
          'Regulated returns cap addressability on many cost lines.',
        valueAdded:
          'Regulatory-aware initiative filtering and realistic run-rate claims.',
      },
      {
        id: 't5-retail',
        name: 'Organized retail',
        whatToProvide: 'Store count, rent roll, shrinkage, category margin by format.',
        whyRequired:
          'Store footprint drives rent and labor; benchmarks need store-normalized metrics.',
        valueAdded:
          'Format-level levers (store productivity, rent renegotiation, logistics).',
      },
      {
        id: 't5-healthcare',
        name: 'Healthcare / hospitals',
        whatToProvide: 'Bed count, case mix, consumables per procedure, doctor payout model.',
        whyRequired:
          'Clinical cost drivers dominate addressability vs generic admin benchmarks.',
        valueAdded:
          'Clinical supply and workforce model initiatives with patient-volume context.',
      },
    ],
  },
];

export const GUIDEBOOK_MISSING_IMPACT: { missing: string; effect: string }[] = [
  { missing: 'Spend file', effect: 'Analysis blocked; user prompted to upload via chat attach.' },
  { missing: 'Revenue or industry', effect: 'Blocked for benchmark / value bridge / business case intents.' },
  { missing: 'Headcount', effect: 'heuristic-analyzer excluded; weaker per-FTE and efficiency narrative.' },
  { missing: 'Budget lines', effect: 'No BvA; analysis limited to peer and temporal views.' },
  { missing: 'Contract / payment terms', effect: 'Savings marked hypothesis; SME probe questions surfaced.' },
  { missing: 'Documents', effect: 'Weaker non-addressable spend and strategic context in recommendations.' },
  { missing: 'Deep research', effect: 'Narrative relies on uploaded numbers and sector benchmarks only.' },
  { missing: 'Sector-pack KPIs', effect: 'Generic levers only; industry-specific plays under-specified.' },
];

export const GUIDEBOOK_ACCEPTED_FORMATS = [
  'CSV, Excel (.xlsx, .xls), PDF (embedded spend tables), JSON',
  'Documents: PDF, DOCX, TXT',
  'ERP export via file upload today; native connectors planned',
];
