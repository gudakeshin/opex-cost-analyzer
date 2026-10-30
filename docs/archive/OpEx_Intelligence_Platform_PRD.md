# OpEx Intelligence Platform — Product Requirements Document

**Agentic Cost Optimization & Value Lever Analysis Engine**


| Field            | Detail                                               |
| ---------------- | ---------------------------------------------------- |
| Document Version | 1.8                                                  |
| Date             | March 9, 2026                                        |
| Author           | Pallav Chaturvedi                                    |
| Status           | Implementation Complete                              |
| Classification   | Internal                                             |
| LLM Runtime      | Claude Sonnet 4.6 (claude-sonnet-4-6)                |
| Memory Service   | Local MemoryStore (default) + Mem0 (when configured) |


---

## 1. Problem Statement

Enterprises spend millions annually on operating expenditures across dozens of categories — from IT infrastructure and professional services to facilities, travel, and marketing. Despite this scale, most organizations lack a systematic, data-driven method to identify where they are overspending relative to peers, internal benchmarks, or outcomes-per-dollar norms established by leading consulting firms.

Today, procurement and finance teams manually compile spreadsheets, request one-off consulting engagements, and rely on tribal knowledge to estimate savings potential. This process is slow (weeks to months per analysis cycle), expensive (consulting retainers of $200K–$2M+), and inconsistent (different analysts apply different heuristics). For consulting firms advising clients, the same challenge exists: each new engagement requires rebuilding the analytical scaffolding from scratch.

The cost of inaction is significant. BCG reports that cost efficiency remains a top C-suite priority, with organizations pursuing 20–50% efficiency gains through a combination of traditional levers and AI-powered approaches. Without a unified platform, enterprises either miss savings opportunities entirely or pay premium rates for analyses that could be substantially automated.

### 1.1 Who Experiences This Problem


| Persona                                    | Pain Point                                                                        | Frequency            |
| ------------------------------------------ | --------------------------------------------------------------------------------- | -------------------- |
| Chief Procurement Officer / VP Procurement | Cannot systematically benchmark spend categories against peers or industry norms  | Quarterly / annually |
| Finance Business Partner                   | Manually builds variance analyses in Excel; no standardized value-lever framework | Monthly              |
| Management Consultant (Strategy/Ops)       | Rebuilds opex analytical frameworks from scratch for every engagement             | Per engagement       |
| CFO / COO                                  | Lacks a single view of savings opportunity across all spend categories            | Board cycles         |


---

## 2. Goals

### 2.1 User Goals

- **Reduce analysis cycle time**: From weeks/months to hours. Users should be able to upload spend data and receive a category-level value-at-the-table estimate within a single working session.
- **Democratize consulting-grade frameworks**: Apply the same benchmarking and value-lever methodologies used by McKinsey, BCG, and Deloitte without needing a $1M+ consulting engagement.
- **Build institutional memory**: Each analysis should enrich the platform's understanding of the business, so subsequent analyses are faster and more contextualized.

### 2.2 Business Goals

- **Quantifiable savings identification**: Surface at least 8–15% of addressable spend as validated savings opportunities across the top 10 spend categories within the first 90 days of deployment.
- **Reusable analytical asset**: Create a library of composable skills that can be extended, tested, and shared across teams — reducing the marginal cost of each subsequent analysis to near zero.
- **Competitive differentiation for consulting firms**: Enable advisory teams to deliver faster, more data-driven recommendations, increasing win rates on cost-transformation proposals.

---

## 3. Non-Goals (v1)


| Non-Goal                                  | Rationale                                                                                                                                                                |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Real-time ERP integration                 | v1 operates on uploaded data snapshots (Excel/CSV/documents). Direct SAP, Oracle, or Coupa connectors are a v2 initiative requiring significant integration engineering. |
| Automated contract renegotiation          | The platform identifies opportunities and builds business cases; actual supplier negotiations remain a human-led activity.                                               |
| Role-based access control (RBAC)          | v1 is single-tenant with a shared workspace. Enterprise RBAC with audit trails is a v2 requirement for multi-team deployments.                                           |
| Mobile-native interface                   | The chat interface is web-responsive but not optimized for mobile workflows. Mobile is deferred pending user demand signal.                                              |
| Cost center hierarchy / allocation engine | Intra-company cost allocation (shared services, IT chargebacks, HR split pools) requires ERP integration or a structured chart-of-accounts feed; deferred to v2.         |


> **Note:** Multi-currency normalization and automated savings pipeline tracking, previously listed as non-goals, were implemented in v1.6 (see §6.5 and §6.8).

---

## 4. User Stories

### 4.1 Data Ingestion & Business Understanding

- As a **procurement analyst**, I want to upload multiple Excel files containing spend data by category, supplier, and time period so that the platform can build a comprehensive view of my company's operating expenditure.
- As a **finance business partner**, I want to upload supporting documents (contracts, policy memos, budget narratives) so that the platform contextualizes the numbers with business rationale.
- As a **management consultant**, I want the platform to automatically classify spend into standard categories (e.g., IT, Facilities, Travel, Professional Services, Marketing) so that I can compare across clients.

### 4.2 Benchmarking & Value Lever Analysis

- As a **CPO**, I want to see how my company's spend per category compares to industry peers (peer benchmarking) so that I can identify categories where we are significantly above median.
- As a **finance analyst**, I want to compare spend across business units or geographies within my organization (internal benchmarking) so that I can spot inconsistencies and best-practice opportunities.
- As a **consultant**, I want the platform to apply heuristic comparisons based on outcomes-per-dollar norms from leading consulting frameworks so that I can quickly estimate the savings potential per lever.
- As a **CFO**, I want a consolidated value-at-the-table view showing the total estimated savings by spend category and value lever so that I can prioritize transformation initiatives.

### 4.3 Business Case Generation

- As a **procurement director**, I want to generate a structured business case document for a specific savings initiative so that I can secure executive sponsorship and funding.
- As a **consultant**, I want the business case to include implementation timeline, risk factors, and confidence intervals so that the recommendation is credible and actionable.

### 4.4 Skills Management

- As a **power user**, I want to browse the library of available analytical skills so that I can understand what analyses the platform can perform.
- As an **analyst**, I want to edit an existing skill's parameters or prompts so that I can fine-tune it for my industry or company context.
- As a **platform administrator**, I want to test a skill against sample data before publishing it so that I can ensure it produces accurate results.
- As a **consultant**, I want to create a new custom skill (e.g., industry-specific benchmarking) so that I can extend the platform's analytical repertoire.

### 4.5 Memory & Context Continuity

- As a **returning user**, I want the platform to remember my company's spend profile, industry context, and previous analyses so that I don't have to re-upload and re-explain each session.
- As a **consultant working across clients**, I want the platform to maintain separate memory contexts per client engagement so that data and insights don't leak across accounts.

### 4.6 FP&A: Budget vs. Actuals

- As a **finance business partner**, I want to upload both actual spend and budget data in the same file so that the platform automatically decomposes variances into price, volume, and mix effects per category.
- As a **FP&A analyst**, I want to see which categories are most over-budget and understand the primary driver (price inflation vs. higher volume vs. product mix shift) so that I can escalate the right issue to the right team.
- As a **CFO**, I want a summary of total actual vs. budget variance with over-budget and under-budget category counts so that I can quickly assess P&L risk in the monthly close review.

### 4.7 FP&A: Temporal Trend Analysis

- As a **finance analyst**, I want the platform to detect fiscal periods from uploaded data and compute month-over-month and year-over-year spend changes automatically so that I can identify accelerating cost trends before they become a problem.
- As a **procurement director**, I want an annualized run-rate estimate per category so that I can compare in-year pacing against the annual budget without manually extrapolating partial-year data.
- As a **CPO**, I want to see trend direction (rising / stable / declining) for each spend category across all available periods so that I can focus renegotiation attention on fast-growing categories.

### 4.8 FP&A: Working Capital & Payment Terms

- As a **treasurer**, I want to know which spend categories have the longest Days Payable Outstanding (DPO) gap versus industry benchmarks so that I can identify the highest-value working capital optimization opportunities.
- As a **CFO**, I want to see the one-time working capital release and its annualized WACC value for each category if we extend payment terms to the benchmark target, so that I can prioritize the payment terms program.
- As a **procurement lead**, I want payment terms recommendations that account for our industry's adjustment factor and our WACC, not just generic defaults, so that the numbers are defensible in supplier negotiations.

### 4.9 FP&A: Run-Rate vs. One-Time Savings & Forecast to Complete

- As a **finance controller**, I want savings initiatives classified as run-rate or one-time so that I can correctly model them in the P&L forecast and budget.
- As a **program manager**, I want a Forecast to Complete (FTC) estimate for each in-flight initiative based on the actual savings run rate, so that I can surface at-risk initiatives early.
- As a **CFO**, I want the pipeline summary to separately show committed run-rate and one-time savings so that I can assess the sustainability of the cost improvement program.

---

## 5. Requirements

### 5.1 Must-Have (P0)

#### 5.1.1 Chat Interface & Data Ingestion


| ID    | Requirement                                                  | Acceptance Criteria                                                                                                                                                                                       |
| ----- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0-01 | Web-based conversational chat interface for user interaction | User can type natural-language queries; system responds with text, tables, and charts. Supports file upload via drag-and-drop or file picker. Optional plan preview with confirm/cancel before execution. |
| P0-02 | Upload and parse Excel files (.xlsx, .xls, .csv)             | System extracts tabular data, infers column types (spend amount, category, supplier, date, BU), and presents a data summary for user confirmation within 30 seconds for files up to 50MB.                 |
| P0-03 | Upload and parse documents (.docx, .pdf, .txt)               | System extracts text content and stores it in the business context layer. Supports up to 20 documents per session.                                                                                        |
| P0-04 | Automatic spend category classification                      | System maps raw spend line items to a standard taxonomy of 15–25 categories with >85% accuracy. User can override/correct mappings.                                                                       |


#### 5.1.2 Value Lever Analysis Engine


| ID    | Requirement                                                                                      | Acceptance Criteria                                                                                                                                                                                                                                                                                                                                             |
| ----- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0-05 | Peer benchmarking: Compare spend per category against industry benchmarks                        | For each spend category, show percentile ranking (e.g., 75th percentile vs. industry) with source attribution. Support at least 10 industry verticals.                                                                                                                                                                                                          |
| P0-06 | Internal benchmarking: Compare spend across BUs, geographies, or time periods                    | Generate comparison tables and variance highlights. Flag categories where internal spread exceeds 20%.                                                                                                                                                                                                                                                          |
| P0-07 | Heuristic comparison: Apply outcomes-per-dollar norms from consulting frameworks                 | For each category, apply at least 2 heuristic lenses (e.g., cost-per-employee, cost-as-%-of-revenue) with reference ranges from consulting eminence.                                                                                                                                                                                                            |
| P0-08 | Value-at-the-table calculation: Aggregate savings potential by category and lever                | Produce a summary matrix: rows = spend categories, columns = value levers, cells = estimated savings ($, %). Include confidence bands (low/mid/high).                                                                                                                                                                                                           |
| P0-17 | Budget vs. Actuals (BvA) analysis: Decompose spend variances into price, volume, and mix effects | When both `actual` and `budget` amount_type lines are present, produce a BvA report with total variance, per-category flag (over/under/on budget), and primary driver identification (price/volume/mix).                                                                                                                                                        |
| P0-18 | Temporal trend analysis: Detect fiscal periods and compute period-over-period deltas             | When `fiscal_period` is populated on ≥2 periods, produce MoM and YoY spend deltas per category, annualized run rate, and trend direction (rising/stable/declining).                                                                                                                                                                                             |
| P0-19 | Payment terms optimizer: Identify DPO extension opportunities vs. industry benchmarks            | For categories with `payment_terms_days` populated, compute working capital release and annual WACC-adjusted cash value vs. p50/p75 benchmark DPO by category and industry.                                                                                                                                                                                     |
| P0-20 | Multi-currency normalization: Normalize spend lines to a single reporting currency               | Accept `currency` and `fx_rate_to_reporting` on each spend line; compute `reporting_amount` automatically. All downstream analysis uses reporting currency amounts.                                                                                                                                                                                             |
| P0-21 | Savings type classification: Distinguish run-rate from one-time savings                          | Each initiative is tagged `run_rate`, `one_time`, or `mixed` based on lever type. Annualized run rate (`annualized_run_rate_savings`) is stored separately. Pipeline summary breaks out run-rate vs. one-time committed savings.                                                                                                                                |
| P0-22 | Tax-adjusted NPV and phased cash flow modeling                                                   | Savings modeler computes both pre-tax and after-tax NPV using a configurable `effective_tax_rate`. Implementation costs are phased by cost type (consulting front-loaded 65/25/10, technology 50/35/15).                                                                                                                                                        |
| P0-23 | Layer 1 — Skill-level golden dataset unit tests                                                  | Golden JSON fixtures for spend-profiler, bva-analyzer, temporal-analyzer, payment-terms-optimizer. Each fixture defines input lines and output assertions (required keys, value ranges, bool flags). `run_golden_suite()` invokes skill directly without OPAR. All assertions run deterministically in CI with no LLM API calls.                                |
| P0-24 | Layer 2 — OPAR trace instrumentation and trace-grounded LLM judge                                | `act()` accepts `enable_tracing=False`. When `True`, per-skill input snapshots, full outputs, timing, and errors are captured in a `SkillTrace` list and persisted as `EvalTrace` to `eval_trace.json`. `TraceGroundedJudge` verifies that claims in the final brief trace to raw input data. LLM judge gated by `pytest.mark.llm_judge` and `RUN_LLM_JUDGE=1`. |
| P0-25 | Layer 3 — Counterfactual signal injection and prioritization scoring                             | `inject_signal()` embeds a known high-priority overrun (actual + budget lines) into a baseline dataset. `score_prioritization()` deterministically checks keyword presence and BvA top-3 rank. `build_noise_lines()` provides noise categories to verify signal is not suppressed.                                                                              |
| P0-26 | Expert review bundle — per-session markdown evaluation report                                    | `python -m app.eval.review <session_id>` writes `review_bundle.md` to the session directory. Combines EvalTrace table, optional per-skill faithfulness judge scores, and counterfactual prioritization result. `--with-judge` flag enables LLM scoring pass.                                                                                                    |


#### 5.1.3 Skills Architecture


| ID    | Requirement                                                                                                                                                                                                                                                 | Acceptance Criteria                                                                                                                                                                                           |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0-09 | Skill-based architecture                                                                                                                                                                                                                                    | Each analytical capability is a discrete skill with a SKILL.md, supporting scripts, and reference data. Skills execute via Python `app.skills.engine`; Claude Agent Skills container is a future enhancement. |
| P0-10 | Core skills: spend-profiler, chart-builder, peer-benchmarker, internal-benchmarker, heuristic-analyzer, root-cause-analyzer, savings-modeler, value-bridge-calculator, data-validator, business-case-builder, analysis-synthesizer, executive-communication | Skills produce structured JSON outputs, are composed adaptively by intent/data availability, and support deterministic + LLM-grounded synthesis for executive communication.                                  |
| P0-11 | Skills management UI: list, view, edit, test, create skills                                                                                                                                                                                                 | Admin interface shows all installed skills with name, description, version, and status. Edit opens SKILL.md and config files in a code editor. Test runs skill against sample data and shows output.          |


#### 5.1.4 Memory Management (Mem0)


| ID    | Requirement                                          | Acceptance Criteria                                                                                                                                                                                        |
| ----- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0-12 | Integrate Mem0 for persistent memory across sessions | After a user uploads data and receives analysis, key facts (company name, industry, spend profile, category mappings) are stored in Mem0 user memory. On next session, these are retrieved and pre-loaded. |
| P0-13 | Session memory for in-conversation context           | Current analysis state, intermediate results, and user corrections are tracked in Mem0 session memory. Supports multi-turn analysis workflows without context loss.                                        |
| P0-14 | Agent memory for skill-specific learned parameters   | Each skill can store and retrieve calibration data (e.g., industry benchmark tables, user-customized heuristic ranges) in Mem0 agent memory.                                                               |


#### 5.1.5 Business Case Generation


| ID    | Requirement                                                      | Acceptance Criteria                                                                                                                                                                               |
| ----- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0-15 | Generate structured business case document from analysis results | Business case includes: executive summary, current state analysis, savings opportunity sizing, implementation approach, timeline, risks, and financial projections. Exportable as .docx and .pdf. |
| P0-16 | Business case skill with configurable templates                  | Users can select from templates (e.g., executive summary, detailed proposal, board-ready) and customize sections. Skill uses value-lever outputs as inputs.                                       |


### 5.2 Nice-to-Have (P1)


| ID    | Requirement                                                              | Rationale                                                                                                                                                  |
| ----- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1-01 | Interactive dashboards with Chart.js for spend visualization             | Improves user experience; HTML dashboards can be shared with stakeholders without platform access.                                                         |
| P1-02 | Confidence scoring and sensitivity analysis for savings estimates        | Adds credibility to recommendations; enables scenario planning. Driver-based scenarios (headcount growth, revenue growth, timeline compression) supported. |
| P1-03 | Export analysis to PowerPoint presentation                               | Consultants and finance teams frequently need deck-ready outputs.                                                                                          |
| P1-04 | Benchmark data enrichment via web search                                 | Allows the platform to pull fresher benchmark data from public sources for comparison.                                                                     |
| P1-05 | Multi-language support for global deployments (Hindi, Spanish, Mandarin) | Extends addressable market to non-English-speaking teams.                                                                                                  |


### 5.3 Future Considerations (P2)


| ID    | Requirement                                                                                                   | Design Implication                                                                                                       |
| ----- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| P2-01 | Real-time ERP/procurement system connectors (SAP Ariba, Coupa, Oracle)                                        | Design data ingestion layer with an adapter pattern so connectors can be plugged in without rewriting the core pipeline. |
| P2-02 | Live FX rate feed for multi-currency normalization                                                            | Static FX rates per upload are supported in v1.6; live feed via an FX API is a v2 capability.                            |
| P2-03 | Role-based access control and multi-tenant isolation                                                          | Design memory scoping (Mem0 user/agent IDs) to support tenant isolation from day one.                                    |
| P2-04 | Skill marketplace: publish, share, and monetize custom skills                                                 | Use Claude Skills API versioning and listing endpoints as the foundation for a marketplace catalog.                      |
| P2-05 | Cost center hierarchy / allocation engine                                                                     | Intra-company cost allocation (shared services chargebacks, split pools) requires ERP feed or CoA import.                |
| P2-06 | Organizational context APIs in OPAR Observe phase (locked categories, pending org decisions, budget calendar) | Keep as FP&A backlog item for a later increment; wire into ObserveContext and planning exclusions once implemented.      |


---

## 6. Technical Architecture

### 6.1 System Overview

The OpEx Intelligence Platform is a three-tier web application with a skills-based architecture, OPAR agentic loop orchestration, and a chat frontend. The backend uses Python (FastAPI) with a local file-backed memory store by default; Mem0 is supported when `MEM0_API_KEY` is configured.


| Layer                  | Technology                                                 | Responsibility                                                                                                                                                                                                                                                                             |
| ---------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Frontend               | HTML, CSS, JavaScript                                      | Chat interface, chat-integrated file upload (📎 attach button, drag-and-drop onto chat shell, staged file chips), schema confirmation system notes, collapsible System Output and Pipeline panels, skills management UI, live collapsible thinking trace, and inline chart preview in chat |
| Backend / Orchestrator | Python (FastAPI), OPAR loop                                | Observe → Plan → Act → Reflect orchestration, skill routing, memory adapter, file processing pipeline                                                                                                                                                                                      |
| LLM Runtime            | Claude Sonnet 4.5 via Anthropic Messages API               | Analysis synthesis (`analysis-synthesizer`) and executive communication drafting (`executive-communication`) only. Intent classification and plan generation are always rule-based.                                                                                                         |
| Memory Layer           | Local MemoryStore (default) or Mem0                        | User memory, session memory, agent memory via `MemoryAdapterInterface`                                                                                                                                                                                                                     |
| Skills Engine          | Python `app.skills.engine`                                 | Skill execution via pandas, openpyxl; SKILL.md specs in `skills/*/`                                                                                                                                                                                                                        |
| Data Processing        | Python (pandas, openpyxl, python-docx, pypdf)              | Excel/CSV parsing, document text extraction, spend category classification                                                                                                                                                                                                                 |
| Storage                | Local filesystem (data/uploads, data/memory, data/outputs) | Uploaded files, manifest, analysis state, generated documents                                                                                                                                                                                                                              |


### 6.2 OPAR Agentic Loop Architecture

The core analysis workflow follows the **Observe → Plan → Act → Reflect (OPAR)** loop. Every user message triggers a full cycle. The orchestrator (`app.opar.orchestrator`) owns and enforces this loop.

1. **OBSERVE**: Assemble `ObserveContext` from user message, session state, memory (user/session/agent), and file parse status. Classify intent (`general_qa` | `upload_data` | `benchmark` | `value_bridge` | `business_case` | `export_business_case`) via deterministic rule-based keyword matching; default is `general_qa`. Assess data quality; set `clarification_required` **only** for analysis intents (`benchmark`, `value_bridge`, `business_case`) when spend data is absent or DQ score < 0.6 — conversational and upload intents never trigger the clarification gate.
2. **PLAN**: Generate `ExecutionPlan` — skill DAG with parallel groups via deterministic rule-based mapping (`_plan_rule_based`). Planning uses adaptive minimality: benchmark requests run a light benchmark chain, value-bridge requests add modeling layers, and business-case requests add document generation layers. Optional skills (document-contextualizer, analysis-synthesizer, executive-communication, chart-builder) are included only when required by intent/context.
3. **ACT**: Execute skills in parallel within each `parallel_group` via `asyncio.gather` and `asyncio.to_thread`. Current analysis DAG includes spend-profiler, chart-builder, document-contextualizer, peer/internal/heuristic benchmarkers, root-cause-analyzer, savings-modeler, value-bridge-calculator, data-validator, business-case-builder (intent-dependent), analysis-synthesizer, and executive-communication. Results are written to session memory after each skill. `act()` accepts an optional `enable_tracing=False` kwarg; when `True`, per-skill input snapshots, full outputs, individual timing (`SkillTrace.duration_ms`), and errors are captured in an `EvalTrace` object that is persisted to `UPLOAD_DIR/<session_id>/eval_trace.json` for post-hoc evaluation. Production paths default to `enable_tracing=False` for zero overhead.
4. **REFLECT**: Three-layer validation — (1) schema contracts (`validate_core_skill_outputs` + optional synthesis/communication output contracts), (2) coherence checks, (3) domain confidence scoring. Reflect prefers LLM-grounded communication output when present and valid; otherwise it falls back to deterministic response rendering.
5. **Response**: Return `response_text`, `next_loop_trigger`, `loop_complete`, `response_artefacts` (e.g., business case .docx path).

If `clarification_required` is true, the loop short-circuits before Plan: the user sees the clarification prompt and no skills execute.

The orchestrator (`app.opar.orchestrator`) implements a `general_qa` early-exit branch: if prior session analysis exists, `_answer_general_qa()` answers directly from stored results (top categories, specific category totals, total spend); if files are uploaded but no analysis exists yet, it falls through to run the profiler; if no data at all, `_handle_no_data_qa()` returns onboarding guidance, file format instructions, or a capabilities overview based on the user's message keywords. Progress trace events include selected skills and explicit skipped-skill reasons for transparency.

### 6.3 Skills Architecture Detail

Each skill is a self-contained folder following the Claude Agent Skills specification:


| Component       | Purpose                                                                             | Example (peer-benchmarker skill)                                                                        |
| --------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| SKILL.md        | Prompt template with YAML frontmatter (name, description) and detailed instructions | Instructions for comparing spend data against industry benchmark tables; output format specification    |
| reference-data/ | Static data files the skill needs                                                   | industry_benchmarks.json with percentile distributions by category and vertical                         |
| scripts/        | Python scripts for computation                                                      | calculate_percentiles.py — computes percentile ranking given spend data and benchmark table             |
| config.json     | Skill parameters and defaults                                                       | `{"default_verticals": ["technology", "manufacturing", "financial_services"], "confidence_level": 0.9}` |


#### 6.3.1 Core Skills Catalog


| Skill Name              | Input                                                                          | Output                                                                                                                                                                                                          | Value Lever                      |
| ----------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| spend-profiler          | Raw Excel/CSV spend data (actual lines only; filters `amount_type = "actual"`) | Categorized spend summary with taxonomy mapping, top-N suppliers per category, `currency_breakdown`, `gl_breakdown`, `trend_analysis` (when >= 2 periods), and per-category supplier concentration index (`hhi`, `concentration_flag: "high" \| "moderate" \| "competitive"`) | Foundation (no direct lever)     |
| peer-benchmarker        | Categorized spend + industry vertical                                          | Percentile rankings per category with target percentile savings (`benchmark_target_pct`, typically P25), plus benchmark provenance metadata                                                                     | Peer Benchmarking                |
| internal-benchmarker    | Categorized spend by BU/geography                                              | Comparison matrix showing spend per BU; variance highlights; best-practice BU identification                                                                                                                    | Internal Benchmarking            |
| heuristic-analyzer      | Categorized spend + headcount/revenue data                                     | Outcomes-per-dollar ratios with optional headcount-normalized signals (`actual_cost_per_employee`, `target_cost_per_employee`, headcount-based savings)                                                         | Heuristic Comparison             |
| chart-builder           | Spend profiler output (+ trend/addressability signals)                         | FP&A-driven chart selection metadata, commentary points, and themed spend profile chart export URL                                                                                                              | Visualization & Decision Support |
| root-cause-analyzer     | Profile + peer benchmark + line data                                           | Category-level root-cause hypotheses mapped to recommended levers, complexity, and timeline                                                                                                                     | Root-Cause Diagnostics           |
| savings-modeler         | Raw opportunities + root causes                                                | 3-year phased model with cost-to-achieve phased by cost type (consulting/technology/internal), net savings, payback, pre-tax NPV, after-tax NPV, IRR (`irr_pct`), `savings_type`, `annualized_run_rate_savings` | Financial Modeling               |
| value-bridge-calculator | Outputs from benchmarkers + savings model                                      | Consolidated value-at-the-table matrix with confidence bands and overlap de-duplication                                                                                                                         | All (aggregation)                |
| business-case-builder   | Value-bridge output + user parameters                                          | Structured business case document (.docx/.pdf) with exec summary, financials, timeline, risks                                                                                                                   | Business Case                    |
| analysis-synthesizer    | Deterministic skill outputs + document context + transaction examples          | LLM-grounded recommendation JSON with evidence, concrete examples, risks, and decision asks                                                                                                                     | Executive Synthesis              |
| executive-communication | Synthesized analysis + deterministic outputs + audience                        | Finance Business Partner-style narrative tailored to audience (CFO/CEO/BU leader/Board)                                                                                                                         | Executive Communication          |
| bva-analyzer            | Spend lines with `amount_type = "actual"` and `"budget"`                       | Budget vs. Actuals report: total variance, per-category spend variance, over/under budget flag. `primary_driver = "spend"` always — P/V/M decomposition omitted (requires per-unit quantity data per CIMA standard) | FP&A Variance Analysis           |
| temporal-analyzer       | Spend lines with populated `fiscal_period`                                     | Period-over-period trend report: MoM/YoY deltas per period, annualized run rate (`arr_basis: "TTM"` when ≥12 periods, else `"3M_extrapolated"`), CAGR (gated on ≥3 periods), category-level trend direction and CAGR | FP&A Trend Analysis              |
| payment-terms-optimizer | Spend lines with `payment_terms_days`; WACC and industry                       | Working capital release and annual cash value per category vs. p50/p75 DPO benchmark; industry-adjusted targets                                                                                                 | Working Capital Optimization     |


Skills are dispatched via `app/skills/dispatch.py` — a `@register("skill-name")` decorator registry that replaces the previous 130-line switch statement in `act.py`. Each handler receives a `SkillContext` dataclass with standardised fields (`lines`, `docs_text`, `manifest`, `prior_results`, `user_message`, `headcount`) and convenience properties (`industry`, `annual_revenue`, `prior(skill)`).


### 6.4 Memory Architecture

The platform uses a `MemoryAdapterInterface` (`app.opar.memory_adapter`) with two implementations:


| Implementation     | When Used                                      | Backend                                                                                                                                                                                                     |
| ------------------ | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LocalMemoryAdapter | Default (no `MEM0_API_KEY`)                    | File-backed `MemoryStore`; keys use `{session_id}_opar`, `{agent_id}_opar` to isolate OPAR data                                                                                                             |
| Mem0MemoryAdapter  | When `MEM0_API_KEY` is set and SDK initializes | Mem0 SDK with scoped identifiers: `get_all(user_id/agent_id)`, `search(query, run_id)`, `add(..., user_id/agent_id/run_id)`; runtime write-failure fallback to local adapter prevents chat request failures |


#### 6.4.1 Memory Scopes


| Scope   | Mapping                               | What Is Stored                                                  |
| ------- | ------------------------------------- | --------------------------------------------------------------- |
| User    | `user_id` (e.g., company slug)        | Company profile, last_total_spend, industry                     |
| Session | `session_id`                          | OPAR entries: skill outputs, value_bridge, intermediate results |
| Agent   | `skill_name` (e.g., peer-benchmarker) | Skill calibration, learned thresholds                           |


#### 6.4.2 Adapter Interface


| Method                                         | Purpose                                |
| ---------------------------------------------- | -------------------------------------- |
| `get_user_memory(user_id)`                     | Load user profile for Observe          |
| `get_session_memory(session_id, query, limit)` | Retrieve session context for planning  |
| `get_agent_memories(skill_names)`              | Load skill calibration data            |
| `add_session(session_id, content, metadata)`   | Store skill output after each Act step |
| `add_user(user_id, content)`                   | Persist user profile in Reflect        |
| `add_agent(agent_id, content)`                 | Update skill calibration               |


### 6.5 Data Model

#### 6.5.1 Core Entities


| Entity              | Key Fields                                                                                                                                                                                                                                       | Relationships                                                                   |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| User                | user_id, email, org_name, industry, created_at                                                                                                                                                                                                   | Has many Sessions, Analyses                                                     |
| Session             | session_id, user_id, created_at, status, wacc, effective_tax_rate                                                                                                                                                                                | Belongs to User; has many Messages, UploadedFiles                               |
| UploadedFile        | file_id, session_id, filename, file_type, parsed_data_ref                                                                                                                                                                                        | Belongs to Session                                                              |
| SpendRecord         | record_id, file_id, category, subcategory, supplier, amount, currency, period, business_unit                                                                                                                                                     | Belongs to UploadedFile                                                         |
| NormalizedSpendLine | row_id, supplier, description, amount, category_id, category_name, business_unit, geo, spend_date, gl_code, cost_center_id, currency, fx_rate_to_reporting, amount_reporting, amount_type, fiscal_year, fiscal_period, payment_terms_days        | Core analytical unit; `reporting_amount` computed property                      |
| SkillTrace          | skill_name, parallel_group, input_snapshot, output, error, duration_ms                                                                                                                                                                           | One entry per skill execution when `enable_tracing=True`; part of EvalTrace     |
| EvalTrace           | session_id, turn_id, created_at, skill_traces, total_duration_ms                                                                                                                                                                                 | Full act() execution trace; persisted as `eval_trace.json` in session directory |
| Analysis            | analysis_id, session_id, skill_name, input_params, output_json, confidence                                                                                                                                                                       | Belongs to Session; references Skill                                            |
| ValueBridge         | bridge_id, analysis_id, category, lever, savings_low, savings_mid, savings_high                                                                                                                                                                  | Belongs to Analysis                                                             |
| BusinessCase        | case_id, analysis_id, template, generated_doc_ref, status                                                                                                                                                                                        | Belongs to Analysis                                                             |
| Skill               | skill_id, name, version, description, status, files_ref                                                                                                                                                                                          | Has many SkillVersions                                                          |
| PipelineInitiative  | initiative_id, analysis_id, category, lever, gross_savings_y1/y2/y3, cost_to_achieve, net_npv, committed_savings, savings_type, annualized_run_rate_savings, implementation_cost_schedule, stage, owner, committed_date, target_realization_date | Has many Milestones, Actuals                                                    |


#### 6.5.2 NormalizedSpendLine FP&A Fields (v1.6)


| Field                  | Type         | Default    | Purpose                                                                                      |
| ---------------------- | ------------ | ---------- | -------------------------------------------------------------------------------------------- |
| `gl_code`              | str | None   | None       | General Ledger account code; used as primary classifier before keyword fallback              |
| `cost_center_id`       | str | None   | None       | Cost center / department identifier                                                          |
| `currency`             | str          | `"USD"`    | ISO 4217 currency code of the raw amount                                                     |
| `fx_rate_to_reporting` | float        | `1.0`      | Multiplier: raw amount × rate = reporting currency amount                                    |
| `amount_reporting`     | float | None | None       | Explicit override for reporting amount; if None, computed as `amount × fx_rate_to_reporting` |
| `amount_type`          | str          | `"actual"` | One of: `"actual"`, `"budget"`, `"forecast"`, `"accrual"`                                    |
| `fiscal_year`          | int | None   | None       | Derived from `spend_date` if present                                                         |
| `fiscal_period`        | str | None   | None       | ISO month key e.g. `"2025-03"`; used by temporal analyzer                                    |
| `payment_terms_days`   | int | None   | None       | Current DPO in days; used by payment terms optimizer                                         |


### 6.6 Security Architecture

Security controls implemented across the backend. All four attack surfaces addressed with defense-in-depth measures.

#### 6.6.1 Input Validation


| Attack Surface         | Control                       | Implementation                                                                              |
| ---------------------- | ----------------------------- | ------------------------------------------------------------------------------------------- |
| Session ID path params | UUID v4 regex validation      | `_UUID_RE` compiled regex; `_validate_session_id()` called on every session-scoped endpoint |
| File upload filename   | Name stripping                | `Path(file.filename or "upload").name` — strips directory components before storage         |
| Export filename        | Resolved-path prefix check    | `(OUTPUT_DIR / filename).resolve()` checked against `OUTPUT_DIR.resolve()` prefix           |
| Memory delete key      | Separator/traversal rejection | Keys containing `/`, `\`, or `..` are rejected with HTTP 400                                |


#### 6.6.2 CORS Policy

CORS `allow_origins` is driven by the `ALLOWED_ORIGINS` environment variable (default: `http://localhost:3000,http://localhost:8000`). The wildcard `*` origin is not permitted in any deployment configuration. Multi-origin values are comma-separated in the env var.

#### 6.6.3 Skills Endpoint Hardening

`POST /api/skills/{name}/test` validates skill existence by checking for `skills/{name}/SKILL.md` on disk directly, replacing the previous glob-based `discover_skills()` traversal that exposed the directory tree.

---

### 6.7 Performance & Concurrency

#### 6.7.1 Module-Level Caching


| Cache                           | Scope            | Benefit                                                                                                               |
| ------------------------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------- |
| `_TAXONOMY` (analysis.py)       | Process lifetime | Taxonomy JSON read from disk once; subsequent calls return in-memory dict                                             |
| `_HEURISTIC_RANGES` (engine.py) | Process lifetime | Dict of 8 category → target-pct constants; was rebuilt per `heuristic_analyzer` call                                  |
| `_DPO_BENCHMARKS` (engine.py)   | Process lifetime | DPO benchmark JSON read once; reused across all `payment_terms_optimizer` calls                                       |
| `MemoryStore` singletons        | Module level     | One `_memory = MemoryStore()` per module (main, analysis, orchestrator, reflect) instead of per-request instantiation |


#### 6.7.2 Concurrency Safety

`threading.Lock` guards all read-modify-write operations on shared JSON files:


| Module                   | Lock Variable | Protected Operations                                                                               |
| ------------------------ | ------------- | -------------------------------------------------------------------------------------------------- |
| `services/pipeline.py`   | `_LOCK`       | `create_initiative`, `update_initiative_stage`, `reject_initiative`, `add_milestone`, `add_actual` |
| `services/benchmarks.py` | `_LOCK`       | `create_dataset`                                                                                   |


#### 6.7.3 Spend Ingestion Vectorization

`services/ingestion.py` replaced `DataFrame.iterrows()` (Python-loop per row) with pre-extracted pandas `Series` and range-based `iloc` access. For a 10,000-row spend file this yields a 5–10× speedup. Column existence is handled via a `_col(name, fill)` helper that gracefully returns an empty Series for missing optional columns.

#### 6.7.4 Eliminated Redundant Computation


| Redundancy                                                                       | Fix                                                                                                                                                                                                    |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `value_bridge_calculator` called twice (once in `analysis.py`, once in `act.py`) | `engine.build_raw_rows(peer, internal, heuristic)` extracted as a public helper; both call sites use it to populate `savings_modeler`, then pass the result to a single `value_bridge_calculator` call |
| `pipeline_summary` called `_load_store()` twice                                  | Merged into one load; initiative totals and actuals derived from the same snapshot                                                                                                                     |
| `at_risk_initiatives` looped O(n×m) over milestones                              | Pre-indexed milestones and actuals by `initiative_id`; lookup is O(1) per initiative                                                                                                                   |
| `select_best_dataset` computed today's ISO date per dataset in loop              | `today_iso` computed once before the loop                                                                                                                                                              |
| `spend_profiler` called two classify functions per line                          | `_classify_line(text)` single-pass helper returns both `cost_behaviour` and `discretionary` flag                                                                                                       |


#### 6.7.5 LLM Token-ROI Optimisation (v1.8)

Two low-value LLM calls were removed from the hot path; synthesis input payload was slimmed to stay within the 8-second fast-path timeout on every call.

| Change | File | Latency saved | Tokens saved |
| --- | --- | --- | --- |
| Removed LLM intent classification | `app/opar/observe.py` | 1–2 s/req | ~760 t/req |
| Removed LLM plan generation | `app/opar/plan.py` | 2–4 s/req | ~1 400 t/req |
| `_slim_skill_outputs()`: 8 relevant skills only; spend-profiler top-5 categories × 7 fields; doc chunks 6→2; no tx examples | `app/opar/claude_client.py` | 8–14 s/req (eliminates retry path) | ~15–30 k t/req |
| Synthesis `max_tokens` 2000 → 1400 | `app/opar/claude_client.py` | ~0.6 s/req | 600 t/req |
| Exec-comm `max_tokens` 1800 → 1200 | `app/opar/claude_client.py` | ~0.6 s/req | 600 t/req |

**Net: 11–20 s and 27–42 k tokens saved per full pipeline run.** The only remaining LLM calls are `analysis-synthesizer` and `executive-communication`, both gated on `wants_executive_narrative` and present only when the user requests an executive narrative.

---

### 6.8 API Contracts

#### 6.8.1 Chat & OPAR API


| Endpoint                           | Method | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| /api/v1/chat                       | POST   | Run full OPAR loop. Body: `{message, session_id, user_id, run_id, company_name, industry, annual_revenue, currency, audience, headcount}`. Returns `{response_text, artefacts, loop_complete, next_loop_trigger, progress_steps, run_id}`.                                                                                                                                                                                                                                                        |
| /api/v1/chat/with-files            | POST   | Upload files + run full OPAR loop in a single multipart request. Form fields: `message`, `session_id`, `user_id` (optional), `run_id`, `company_name`, `industry`, `annual_revenue`, `currency`, `audience`, `headcount`, `files[]` (0-n UploadFile). Returns `{response_text, uploaded_files: [{name, file_kind, rows, detected_columns, text_chars, text_lines, text_preview}], next_options, run_id}`. Files are processed before OPAR so analysis runs immediately with new data/doc context. |
| /api/v1/chat/progress/{run_id}     | GET    | Returns live progress stream snapshot for current chat run: `{status, steps[], error}` used by frontend polling for real-time collapsible thinking trace.                                                                                                                                                                                                                                                                                                                                         |
| /api/v1/chat/plan                  | POST   | Observe + Plan only (no Act). Returns `{clarification_required, clarification_prompt, user_summary, estimated_duration, requires_approval, plan}` for confirm/cancel flow.                                                                                                                                                                                                                                                                                                                        |
| /api/chat/{session_id}             | POST   | Thin wrapper delegating to OPAR. Body: `{message}`. Returns `{assistant_message, asked_question, response_text, next_loop_trigger, loop_complete}`.                                                                                                                                                                                                                                                                                                                                               |
| /api/sessions                      | POST   | Create session. Body: `{company_name, industry, annual_revenue, currency, audience, headcount, wacc, effective_tax_rate}`.                                                                                                                                                                                                                                                                                                                                                                        |
| /api/upload/{session_id}           | POST   | Upload file; triggers schema inference for .csv/.xlsx/.xls (detects gl_code, cost_center, currency, fx_rate, amount_type, payment_terms columns).                                                                                                                                                                                                                                                                                                                                                 |
| /api/analyze/{session_id}          | POST   | Run full pipeline (batch mode). Body: `{company_name, industry, annual_revenue, currency, audience, headcount, wacc, effective_tax_rate}`.                                                                                                                                                                                                                                                                                                                                                        |
| /api/schema/{session_id}           | GET    | Return detected schemas from uploaded files.                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| /api/business-case/{session_id}    | POST   | Generate business case from analysis.                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| /api/dashboard/{session_id}        | POST   | Build HTML dashboard.                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| /api/sensitivity/{session_id}      | GET    | Sensitivity analysis scenarios. Query params: `discount_rate`, `effective_tax_rate`, `headcount_growth_pct`, `revenue_growth_pct`, `execution_rate_pct`, `timeline_compression_factor`. Returns 6 named scenarios with both `npv_pretax` and `npv_aftertax`.                                                                                                                                                                                                                                      |
| /api/v1/trends/{session_id}        | GET    | Temporal trend analysis results from the last completed analysis. Returns `TemporalAnalyzerOutput` (period_trends, category_trends, annualized_run_rate).                                                                                                                                                                                                                                                                                                                                         |
| /api/v1/bva/{session_id}           | GET    | Budget vs. Actuals analysis results. Returns `BvAAnalyzerOutput` (total_variance, per-category spend variance, flag, primary_driver).                                                                                                                                                                                                                                                                                                                                                             |
| /api/v1/payment-terms/{session_id} | GET    | Payment terms optimizer results. Returns `PaymentTermsOptimizerOutput` (opportunities, total_working_capital_release, total_annual_cash_value).                                                                                                                                                                                                                                                                                                                                                   |


#### 6.8.2 Pipeline Management API (Updated v1.6)


| Endpoint                              | Method | Description                                                                                                                                                                       |
| ------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| /api/pipeline/initiatives             | GET    | List initiatives. Filters: `user_id`, `session_id`, `stage`, `category`, `lever`.                                                                                                 |
| /api/pipeline/initiatives             | POST   | Create initiative. Body includes: `savings_type` (`run_rate` | `one_time` | `mixed`), `annualized_run_rate_savings`, `implementation_cost_schedule` (list of `{period, amount}`). |
| /api/pipeline/initiatives/{id}/stage  | PUT    | Advance stage. Allowed: `identified`, `committed`, `in_flight`, `realized`, `rejected`.                                                                                           |
| /api/pipeline/initiatives/{id}/reject | POST   | Reject with reason.                                                                                                                                                               |
| /api/pipeline/milestones/{id}         | POST   | Add milestone with `description`, `due_date`, `status`, `evidence_doc_ref`.                                                                                                       |
| /api/pipeline/actuals/{id}            | POST   | Record actual savings for a period; computes variance vs. committed.                                                                                                              |
| /api/pipeline/summary                 | GET    | Portfolio summary including `run_rate_committed_savings` and `one_time_committed_savings`.                                                                                        |
| /api/pipeline/at-risk                 | GET    | At-risk initiatives: past target date, overdue milestones, negative variance, Forecast to Complete < 90% of committed.                                                            |


#### 6.8.4 Skills Management API


| Endpoint                | Method | Description                                           |
| ----------------------- | ------ | ----------------------------------------------------- |
| /api/skills             | GET    | List all installed skills (from `skills/*/SKILL.md`). |
| /api/skills             | POST   | Create a new skill.                                   |
| /api/skills/{name}      | GET    | Retrieve skill content (SKILL.md).                    |
| /api/skills/{name}      | PUT    | Update skill content.                                 |
| /api/skills/{name}/test | POST   | Run skill smoke test.                                 |


#### 6.8.5 Memory API


| Endpoint                  | Method | Description                                                        |
| ------------------------- | ------ | ------------------------------------------------------------------ |
| /api/memory/{scope}/{key} | DELETE | Delete memory (scope: user, session, agent). Validates key format. |


#### 6.8.6 Evaluation API (Dev / Internal)


| Endpoint         | Method | Description                                                                                                                                                                                                                                                                                                                                |
| ---------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| /api/v1/eval/run | POST   | Run evaluation layers for a session. Body: `{session_id, layers: ["layer1", "layer2", "layer3"]}`. Requires `X-Eval-Key` header checked against `EVAL_API_KEY` env var. Returns per-layer scores: Layer 1 golden pass/fail per skill, Layer 2 trace completeness + optional grounding score, Layer 3 counterfactual prioritization result. |


---

## 7. Value Lever Framework

The platform applies four primary value levers to each spend category, drawing from established consulting methodologies:

### 7.1 Value Lever Definitions


| Value Lever           | Methodology                                                                                                                                        | Consulting Reference                                                                        | Typical Savings Range |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- | --------------------- |
| Peer Benchmarking     | Compare category spend against industry percentile distributions (P25, P50, P75). Savings = gap between current spend and target percentile.       | McKinsey Global Operations Benchmark; BCG Cost Advantage Database                           | 5–20%                 |
| Internal Benchmarking | Identify lowest-cost BU or geography within the organization for each category. Savings = gap between current BU spend and internal best practice. | Deloitte Operations Strategy; McKinsey Organizational Health Index                          | 3–15%                 |
| Heuristic Comparison  | Apply outcomes-per-dollar norms: cost-per-employee, cost-as-%-of-revenue, cost-per-transaction. Compare against reference ranges.                  | BCG Value Creation Framework; Deloitte Cost Excellence                                      | 5–25%                 |
| AI/Automation Lever   | Estimate savings from GenAI-assisted workflows: procurement automation, contact center AI, predictive maintenance, knowledge management.           | BCG Executive Perspectives (May 2025): 20–50% efficiency gains from GenAI-enabled workflows | 20–50%                |


### 7.2 Value-at-the-Table Calculation

For each spend category C and value lever L, the platform calculates:

**Savings(C, L) = Addressable Spend(C) × Savings Rate(L, C) × Confidence Factor**

Where:

- **Addressable Spend(C)**: Total spend in category C minus non-addressable items (contractually locked, regulatory, etc.)
- **Savings Rate(L, C)**: Derived from the lever-specific methodology (percentile gap, internal gap, heuristic gap, or AI adoption curve)
- **Confidence Factor**: Low (0.5), Mid (0.75), High (0.9) based on data quality, benchmark relevance, and lever maturity

The value-bridge-calculator skill aggregates these into a matrix and applies a de-duplication factor (typically 0.6–0.8) to avoid double-counting where levers overlap.

---

## 8. Success Metrics

### 8.1 Leading Indicators (Week 1–4)


| Metric                                  | Target                               | Measurement Method                                            |
| --------------------------------------- | ------------------------------------ | ------------------------------------------------------------- |
| Time to first value-at-the-table output | < 2 hours from data upload           | Session timestamp: file upload to value-bridge output         |
| Spend category classification accuracy  | > 85% without user correction        | Compare auto-classification vs. user-confirmed mappings       |
| Skill execution success rate            | > 95% (no errors or hallucinations)  | Automated output validation against schema + spot-check audit |
| User sessions per week (per user)       | > 3 sessions/week within first month | Session creation logs                                         |
| File upload success rate                | > 99% for supported formats          | Upload pipeline error logs                                    |


### 8.2 Lagging Indicators (Month 1–6)


| Metric                                             | Target                                        | Measurement Method                                        |
| -------------------------------------------------- | --------------------------------------------- | --------------------------------------------------------- |
| Identified savings as % of total addressable spend | 8–15% across top 10 categories                | Value-bridge outputs aggregated across all analyses       |
| Business cases generated per month                 | > 5 per active user                           | business-case-builder skill invocation count              |
| Memory recall accuracy                             | > 90% relevant memories retrieved             | User feedback on memory-injected context (thumbs up/down) |
| Skill library growth                               | > 2 new custom skills per quarter             | Skills API creation logs                                  |
| Analysis reuse rate                                | > 40% of sessions reference previous analysis | Mem0 search hit rate at session start                     |


---

## 9. Open Questions


| #   | Question                                                                                                                                                                                  | Owner                  | Blocking? |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | --------- |
| 1   | What industry benchmark datasets can we license or source for v1? Options: public datasets (BLS, Eurostat), proprietary (IBISWorld, Gartner), or crowd-sourced from anonymized user data. | Product + Data         | Yes       |
| 2   | Should Mem0 be self-hosted (full control, higher ops burden) or use the managed platform (lower ops, SOC2/HIPAA compliant)?                                                               | Engineering + Security | Yes       |
| 3   | What is the maximum file size and row count we should support in v1? Trade-off between user flexibility and Claude context window / code execution limits.                                | Engineering            | Yes       |
| 4   | How should we handle spend categories that don't map cleanly to the standard taxonomy? Options: force-fit with user override, create a custom category, or flag for manual review.        | Product + UX           | No        |
| 5   | Should the business case template be fully generated by Claude or use a hybrid approach (Claude fills a docx template)?                                                                   | Engineering + Design   | No        |
| 6   | What is the pricing/licensing model for benchmark data used by the peer-benchmarker skill?                                                                                                | Legal + Finance        | Yes       |
| 7   | How do we ensure consulting framework references (McKinsey, BCG, Deloitte heuristics) are used appropriately without IP infringement?                                                     | Legal                  | Yes       |


---

## 10. Timeline & Phasing


| Phase                                | Duration    | Deliverables                                                                                                                                                                                                                                                                                                                                                                                                                        | Status     |
| ------------------------------------ | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| Phase 0: Foundation                  | Weeks 1–4   | FastAPI scaffold, file upload pipeline, spend-profiler and core skills, chat UI, OPAR data structures and orchestrator                                                                                                                                                                                                                                                                                                              | ✅ Complete |
| Phase 1: Core Analysis               | Weeks 5–10  | peer-benchmarker, internal-benchmarker, heuristic-analyzer, value-bridge-calculator, data-validator; memory adapter; Claude intent/plan when ANTHROPIC_ENABLED                                                                                                                                                                                                                                                                      | ✅ Complete |
| Phase 2: Business Case & Skills Mgmt | Weeks 11–14 | business-case-builder; skills management UI; export to .docx; parallel Act, 3-layer Reflect, loop control                                                                                                                                                                                                                                                                                                                           | ✅ Complete |
| Phase 3: Polish & Launch             | Weeks 15–18 | Mem0 adapter, plan preview, chat wrapper, frontend confirm/cancel; dashboard; confidence scoring                                                                                                                                                                                                                                                                                                                                    | ✅ Complete |
| Phase 4: FP&A Enhancement            | Weeks 19–22 | BvA analyzer, temporal analyzer, payment terms optimizer; multi-currency normalization; GL code classification; savings type (run-rate vs. one-time); tax-adjusted NPV; driver-based sensitivity scenarios; Forecast to Complete (FTC) in pipeline; 3 new API endpoints                                                                                                                                                             | ✅ Complete |
| Phase 5: Evaluation Framework        | Weeks 23–24 | 3-layer evaluation framework: Layer 1 golden dataset unit tests (4 skills, 164 total tests); Layer 2 OPAR trace instrumentation (`EvalTrace`, `SkillTrace`, per-skill timing, `enable_tracing` kwarg); Layer 3 counterfactual signal injection and prioritization scoring; LLM-as-judge faithfulness + trace-grounded scorers (gated `llm_judge` marker); expert review bundle CLI; `pyproject.toml` with `llm_judge` pytest marker | ✅ Complete |


### 10.1 OPAR Implementation (Completed)


| OPAR Phase | Deliverables                                                                                                          |
| ---------- | --------------------------------------------------------------------------------------------------------------------- |
| Phase 0    | `ObserveContext`, `ExecutionPlan`, `ActResult`, `ReflectOutput`; memory adapter; `run_opar_loop`; `POST /api/v1/chat` |
| Phase 1    | Claude intent classification; enhanced data quality; Claude plan generation                                           |
| Phase 2    | Parallel Act via `asyncio.gather`; 3-layer Reflect; `determine_loop_control`; value-bridge dedup                      |
| Phase 3    | Mem0 adapter; `POST /api/v1/chat/plan`; `/api/chat/{session_id}` thin wrapper; frontend plan preview                  |


### 10.2 Dependencies

- Claude API (optional; rule-based fallback when `ANTHROPIC_API_KEY` not set)
- Mem0 (optional; `LocalMemoryAdapter` when `MEM0_API_KEY` not set)
- Benchmark data: `skills/peer-benchmarker/references/industry_benchmarks.json`
- Legal review of consulting framework references (ongoing)

---

## 11. Appendix

### A. Standard Spend Category Taxonomy


| #   | Category                    | Examples                                                      | Typical % of OpEx |
| --- | --------------------------- | ------------------------------------------------------------- | ----------------- |
| 1   | IT & Technology             | Software licenses, cloud infrastructure, hardware, IT support | 15–25%            |
| 2   | Professional Services       | Consulting, legal, audit, advisory                            | 8–15%             |
| 3   | Facilities & Real Estate    | Rent, utilities, maintenance, security                        | 10–18%            |
| 4   | Travel & Entertainment      | Business travel, meals, events                                | 3–8%              |
| 5   | Marketing & Advertising     | Digital, print, events, brand                                 | 5–12%             |
| 6   | HR & Recruitment            | Staffing agencies, training, benefits admin                   | 3–7%              |
| 7   | Logistics & Supply Chain    | Freight, warehousing, distribution                            | 5–15%             |
| 8   | Telecommunications          | Voice, data, mobile, conferencing                             | 2–5%              |
| 9   | Insurance & Risk            | Property, liability, D&O, cyber                               | 2–4%              |
| 10  | Office Supplies & Equipment | Furniture, supplies, printing                                 | 1–3%              |


### B. Technology Stack Summary


| Component     | Technology                | Version / Notes                                                                                        |
| ------------- | ------------------------- | ------------------------------------------------------------------------------------------------------ |
| LLM           | Claude Sonnet 4.5         | Anthropic Messages API; used for intent/plan plus synthesis/communication skills (with fallback paths) |
| Orchestration | OPAR loop                 | Observe → Plan → Act → Reflect; `app.opar.orchestrator`                                                |
| Memory        | Local MemoryStore / Mem0  | File-backed default; Mem0 when `MEM0_API_KEY` set                                                      |
| Backend       | Python / FastAPI          | Python 3.11+; asyncio for parallel Act                                                                 |
| Frontend      | HTML, CSS, JavaScript     | Chat UI with plan preview; Deloitte branding                                                           |
| Skills Engine | Python (pandas, openpyxl) | `app.skills.engine`; SKILL.md specs in `skills/*/`                                                     |
| Storage       | Local filesystem          | data/uploads, data/memory, data/outputs                                                                |


#### B.1 Pinned Python Dependencies

All dependencies are version-pinned in `requirements.txt` for reproducible builds.


| Package           | Pinned Version | Purpose                                             |
| ----------------- | -------------- | --------------------------------------------------- |
| fastapi           | 0.116.0        | REST API framework                                  |
| uvicorn[standard] | 0.35.0         | ASGI server                                         |
| python-multipart  | 0.0.20         | File upload form parsing                            |
| pydantic          | 2.11.7         | Data validation and models                          |
| pandas            | 2.3.1          | Tabular spend data processing                       |
| openpyxl          | 3.1.5          | Excel file parsing                                  |
| python-docx       | 1.2.0          | .docx export for business cases                     |
| pypdf             | 6.7.1          | PDF document text extraction                        |
| pytest            | 8.4.1          | Test suite (164 tests: 97 core + 67 eval framework) |
| anthropic         | 0.83.0         | Claude API client                                   |
| mem0ai            | latest         | Mem0 SDK for persistent user/session/agent memory   |


### C. Changelog

#### v1.8 — March 9, 2026 (FP&A Correctness · Engineering Architecture · Latency/Token ROI)

**FP&A Model Correctness**
- **T1-1 BvA decomposition fix**: Removed incorrect Price/Volume/Mix decomposition for heterogeneous spend. `primary_driver = "spend"` on all rows per CIMA standard — P/V/M is only valid with per-unit quantity data. `BvAVarianceRow` fields `price_variance`, `volume_variance`, `mix_variance` are now `Optional[float] = None`.
- **T1-2 CAGR**: `temporal_analyzer` now returns `cagr_pct` at portfolio level and per category (formula: `(last/first)^(12/months_elapsed) − 1`; gated on ≥3 periods).
- **T1-3 HHI**: `spend_profiler` now returns per-category `hhi` (Herfindahl-Hirschman Index) and `concentration_flag` ("high" >0.25 / "moderate" >0.15 / "competitive" ≤0.15).
- **T1-4 TTM ARR**: `temporal_analyzer` uses trailing-12-month sum when ≥12 periods (avoids Q4 seasonality bias); adds `arr_basis: "TTM" | "3M_extrapolated"` field.
- **T1-5 Configurable exec rates**: Sensitivity conservative/accelerated execution rates now read from `skills/savings-modeler/references/model_parameters.json` (`conservative_execution_rate`, `accelerated_execution_rate`) — was hardcoded 0.60/0.85.

**Engineering Architecture**
- **T2-2 Skill dispatch registry**: New `app/skills/dispatch.py` with `@register("skill-name")` decorator and `SkillContext` dataclass. Replaces 130-line if/elif switch in `act.py`. All 15 skills registered.
- **T2-3 IntentClass enum**: `IntentClass(str, Enum)` added to `app/opar/models.py` with 12 typed constants. `ObserveContext.intent_class` stays `str` to handle unknown values gracefully.
- **T2-4 LLM output validation**: `_validate_llm_output()` in `act.py` validates synthesis skill outputs against Pydantic contracts post-execution; returns `{"analysis_available": False}` on `ValidationError`.
- **T2-6 Financial field validators**: `_FinancialParamsMixin(BaseModel)` added to `app/main.py` with `@field_validator` guards: `annual_revenue ≥ 0`, `0 < wacc < 1`, `0 ≤ effective_tax_rate ≤ 1`.

**Observability & Operations**
- **T3-3 Rate limiting + timeout**: Global 200 req/min via `slowapi`; `asyncio.wait_for` 120s hard timeout on all three OPAR endpoints; returns HTTP 408 on timeout.

**Latency / Token-ROI Optimisation**
- Intent classification: removed LLM call path entirely; always rule-based. Saves 1–2 s, ~760 t/req.
- Plan generation: removed `_plan_from_claude`; always `_plan_rule_based`. Saves 2–4 s, ~1 400 t/req.
- `_slim_skill_outputs()` in `claude_client.py`: sends only 8 synthesis-relevant skills; spend-profiler limited to top-5 categories × 7 fields; doc chunks 6→2; transaction examples removed. Payload drops from ~75 kB → <8 kB, eliminating timeout+retry path. Saves 8–14 s, ~15–30 k t/req.
- Synthesis `max_tokens` reduced 2000 → 1400; exec-comm 1800 → 1200.
- **Net saving: 11–20 s and 27–42 k tokens per full pipeline run.**

**Test Coverage**
- 4 new golden fixtures: `bva_analyzer_all_favorable`, `temporal_analyzer_single_period`, `temporal_analyzer_12mo`, `spend_profiler_hhi`.
- New `tests/test_skills_edge_cases.py`: 22 edge-case tests (zero/negative/empty/boundary) across all FP&A skills.
- Test suite: **171 → 212 passed, 0 failed**.

---

#### v1.7 — March 8, 2026 (3-Layer Evaluation Framework)

**OPAR Trace Instrumentation**


| File                 | Change                                                                                                                                                                                                                                                                                                                                                           |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/opar/models.py` | Added `SkillTrace(skill_name, parallel_group, input_snapshot, output, error, duration_ms)` — per-skill execution record                                                                                                                                                                                                                                          |
| `app/opar/models.py` | Added `EvalTrace(session_id, turn_id, created_at, skill_traces, total_duration_ms)` — full act() trace, Pydantic v2 model                                                                                                                                                                                                                                        |
| `app/opar/models.py` | `ActResult` extended with `eval_trace: EvalTrace                                                                                                                                                                                                                                                                                                                 |
| `app/opar/act.py`    | `act()` and `_act_async()` gain `enable_tracing: bool = False` kwarg                                                                                                                                                                                                                                                                                             |
| `app/opar/act.py`    | When `enable_tracing=True`: per-skill `input_snapshot` captured before dispatch, `duration_ms` measured per skill, `SkillTrace` appended after each skill completes/fails, `EvalTrace` built and persisted to `UPLOAD_DIR/<session_id>/eval_trace.json` via `_save_eval_trace()`; failures in tracing are silently swallowed to avoid breaking the main pipeline |


`**app/eval/` Package (New)**


| File                         | Change                                                                                                                                                                                                                                                                                                                             |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/eval/__init__.py`       | Package init with 3-layer docstring                                                                                                                                                                                                                                                                                                |
| `app/eval/trace.py`          | `load_trace(session_id)`, `save_trace(trace)`, `summarize_trace(trace)` → markdown table; `assert_trace_complete(trace, skills)`, `get_skill_trace(trace, skill_name)`                                                                                                                                                             |
| `app/eval/judge.py`          | `FaithfulnessJudge.score(skill_name, input_data, output_text) → FaithfulnessResult` — uses `claude-haiku-4-5`; identifies unsupported numerical claims vs. source data                                                                                                                                                             |
| `app/eval/judge.py`          | `TraceGroundedJudge.score(response_text, trace) → TraceGroundingResult` — verifies final brief claims trace to raw `SkillTrace.input_snapshot` data                                                                                                                                                                                |
| `app/eval/golden.py`         | `run_golden_suite(fixture_path) → GoldenResult`; fixture JSON schema: `{skill, input_lines, extra_kwargs, assertions}`; assertion checker supports `required_keys`, `forbidden_keys`, `min_<key>` (scalar int or list), `contains_<key>`, and direct equality; dispatches to `_SKILL_DISPATCH` dict for zero-OPAR skill invocation |
| `app/eval/counterfactual.py` | `SignalSpec` dataclass; `inject_signal(base_lines, signal, include_budget_line=True)` — appends actual + budget lines; `score_prioritization(response_text, signal, bva_output) → PrioritizationResult` — keyword + BvA rank check; `build_noise_lines(n, base_amount, spend_date)` — distinct-category noise generator            |
| `app/eval/review.py`         | `generate_review_bundle(session_id, run_faithfulness_judge=False) → ReviewBundle` — markdown report: EvalTrace table + faithfulness scores + counterfactual section; saves to `review_bundle.md`; CLI: `python -m app.eval.review <session_id> [--with-judge]`                                                                     |


**Golden Fixtures (New)**


| File                                             | Change                                                                                                                                                   |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/eval/golden/spend_profiler.json`          | 6 actual lines; 3 categories (software, professional_services, facilities); total_spend=600,000; asserts 3+ category_profile rows                        |
| `tests/eval/golden/bva_analyzer.json`            | 3 actual+budget pairs (cloud, marketing, hr_systems); all actuals > budget; asserts 3+ `variances` rows, all `total_variance > 0`, cloud variance = 50k  |
| `tests/eval/golden/temporal_analyzer.json`       | 4 lines Oct–Jan with `fiscal_period` set; monotonically increasing spend; asserts `temporal_available=true`, `period_count >= 4`, `category_trends >= 1` |
| `tests/eval/golden/payment_terms_optimizer.json` | 4 suppliers with `payment_terms_days` 14–21; asserts `payment_terms_available=true`, `total_working_capital_release > 0`, 1+ `opportunities`             |


**Test Suites (New — 67 eval tests)**


| File                                       | Change                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/eval/test_layer1_golden.py`         | 28 deterministic tests across 4 golden fixture classes + 4 parametric smoke tests; validates output keys, values, and format compliance with no LLM                                                                                                                                                                                            |
| `tests/eval/test_layer2_trace.py`          | 20 tests: `SkillTrace`/`EvalTrace` model validation; save/load round-trip; `summarize_trace()` markdown output; `assert_trace_complete()` / `get_skill_trace()` helpers; `ActResult.eval_trace` field; per-skill timing non-negative; input snapshot dependency keys; 1 `llm_judge`-gated `TraceGroundedJudge` test                            |
| `tests/eval/test_layer3_counterfactual.py` | 19 tests: `inject_signal()` line count, amounts, category, base immutability; spend profiler inflation; BvA surfaces overrun (category present, delta positive); signal ranks #1 with 10× multiplier; `score_prioritization()` keyword/category/BvA rank checks; noise does not suppress signal; `build_noise_lines()` count/type/distinctness |


**Pytest Configuration**


| File             | Change                                                                                                                                                                                   |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pyproject.toml` | New file. Registers `llm_judge` pytest marker: marks tests requiring live LLM API calls. Standard CI: `pytest -m "not llm_judge"`. LLM eval runs: `RUN_LLM_JUDGE=1 pytest -m llm_judge`. |


---

#### v1.6 — March 7, 2026 (FP&A Intelligence Layer: BvA, Trends, Payment Terms, Multi-Currency, Savings Type)

**New FP&A Skills**


| File                                                            | Change                                                                                                                                                                                                                                               |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/skills/engine.py`                                          | Added `bva_analyzer()`: decomposes spend into actual vs. budget per category; computes price, volume, and mix variance; flags over/under budget; identifies primary driver                                                                           |
| `app/skills/engine.py`                                          | Added `temporal_analyzer()`: groups spend by `fiscal_period`; computes MoM/YoY deltas; derives annualized run rate from last 3 periods; produces category-level trend direction                                                                      |
| `app/skills/engine.py`                                          | Added `payment_terms_optimizer()`: computes spend-weighted average DPO per category; benchmarks against p50/p75 targets from `dpo_benchmarks.json`; applies industry multiplier; outputs working capital release and WACC-adjusted annual cash value |
| `skills/payment-terms-optimizer/references/dpo_benchmarks.json` | New reference file: p50/p75/p90 DPO benchmarks for 12 spend categories; industry adjustment factors (manufacturing 1.20, retail 1.30, technology 0.90, etc.)                                                                                         |


**Data Model Enhancements**


| File            | Change                                                                                                                                                                                                      |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/models.py` | `NormalizedSpendLine` extended with 9 FP&A fields: `gl_code`, `cost_center_id`, `currency`, `fx_rate_to_reporting`, `amount_reporting`, `amount_type`, `fiscal_year`, `fiscal_period`, `payment_terms_days` |
| `app/models.py` | Added `reporting_amount` computed property: returns `amount_reporting` when set, else `amount × fx_rate_to_reporting` (defaults 1.0, so USD→USD passthrough is zero-change)                                 |


**Ingestion Pipeline Enhancements**


| File                        | Change                                                                                                                                                                         |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app/services/ingestion.py` | Added `_classify_by_gl()`: maps GL code ranges from taxonomy to category_id; used as primary classifier before keyword fallback — improves accuracy for structured ERP exports |
| `app/services/ingestion.py` | Added `_derive_fiscal_period()`: parses 8+ date formats to derive `fiscal_year` and `fiscal_period` (`YYYY-MM`) from `spend_date`                                              |
| `app/services/ingestion.py` | Added `_detect_amount_type()`: infers `actual` / `budget` / `forecast` / `accrual` from column names and row content                                                           |
| `app/services/ingestion.py` | Added `_parse_payment_terms()`: extracts integer DPO from "net-30", "30 days", "N30" and similar formats                                                                       |
| `app/services/ingestion.py` | `infer_tabular_schema()` extended to detect `gl_code`, `cost_center`, `currency`, `fx_rate`, `amount_type`, `payment_terms` columns                                            |
| `app/services/ingestion.py` | `parse_spend_file()` accepts `default_amount_type` and `reporting_currency` parameters                                                                                         |


**Savings Modeler Enhancements**


| File                                                      | Change                                                                                                                                            |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/skills/engine.py`                                    | `savings_modeler` now classifies each initiative as `run_rate`, `one_time`, or `mixed` via `savings_type_by_lever` lookup                         |
| `app/skills/engine.py`                                    | Computes `annualized_run_rate_savings` as stabilized annual savings (gap × peak phasing factor)                                                   |
| `app/skills/engine.py`                                    | Implementation costs phased by cost type using `implementation_cost_phasing` config (consulting 65/25/10, technology 50/35/15, internal 45/40/15) |
| `app/skills/engine.py`                                    | Outputs `npv_pretax` and `npv_aftertax` (tax-adjusted with configurable `effective_tax_rate`) per initiative and in portfolio `summary`           |
| `skills/savings-modeler/references/model_parameters.json` | Added `savings_type_by_lever`, `implementation_cost_phasing`, `effective_tax_rate` default (0.0)                                                  |


**Sensitivity Analysis Enhancements**


| File                          | Change                                                                                                                                                                      |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/services/sensitivity.py` | Added `_npv_phased()`: per-year cash flow discounting with tax adjustment; replaces uniform-annual approximation when `savings_model` phased data is available              |
| `app/services/sensitivity.py` | `compute_sensitivity()` accepts `effective_tax_rate` and `drivers` dict (`headcount_growth_pct`, `revenue_growth_pct`, `execution_rate_pct`, `timeline_compression_factor`) |
| `app/services/sensitivity.py` | Expanded from 5 to 6 scenarios: `conservative`, `base`, `accelerated`, `delayed`, `partial_success`, `volume_growth`                                                        |
| `app/services/sensitivity.py` | Each scenario now includes both `npv_pretax` and `npv_aftertax`; `driver_adjusted` flag; `execution_rate` field                                                             |


**Pipeline Tracking Enhancements**


| File                       | Change                                                                                                                                                   |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/services/pipeline.py` | `create_initiative` accepts `savings_type`, `annualized_run_rate_savings`, `implementation_cost_schedule` (`[{period, amount}]`), `forecast_to_complete` |
| `app/services/pipeline.py` | `pipeline_summary` adds `run_rate_committed_savings` and `one_time_committed_savings` to portfolio summary                                               |
| `app/services/pipeline.py` | `at_risk_initiatives` computes Forecast to Complete (FTC) from actuals run rate × remaining months; flags when FTC < 90% of committed savings            |


**Core Pipeline & API**


| File                       | Change                                                                                                                                                                                               |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/services/analysis.py` | `run_core_pipeline` accepts `wacc`, `effective_tax_rate`, `reporting_currency`; wires `bva_analyzer`, `temporal_analyzer`, `payment_terms_optimizer`; all three included in `skill_outputs`          |
| `app/services/analysis.py` | Agent memory records `has_budget_data`, `has_temporal_data`, `has_payment_terms` for OPAR planning context                                                                                           |
| `app/skills/contracts.py`  | Added Pydantic models: `BvAVarianceRow`, `BvAAnalyzerOutput`, `TemporalPeriodRow`, `TemporalCategoryTrendRow`, `TemporalAnalyzerOutput`, `PaymentTermsOpportunityRow`, `PaymentTermsOptimizerOutput` |
| `app/skills/contracts.py`  | Added validators: `validate_bva_output()`, `validate_temporal_output()`, `validate_payment_terms_output()`                                                                                           |
| `app/main.py`              | `SessionCreateRequest` and `AnalyzeRequest` extended with `wacc: float = 0.10`, `effective_tax_rate: float = 0.0`                                                                                    |
| `app/main.py`              | `InitiativeCreateRequest` extended with `savings_type`, `annualized_run_rate_savings`, `implementation_cost_schedule`                                                                                |
| `app/main.py`              | Sensitivity endpoint updated: 6 new query params (`discount_rate`, `effective_tax_rate`, `headcount_growth_pct`, `revenue_growth_pct`, `execution_rate_pct`, `timeline_compression_factor`)          |
| `app/main.py`              | New endpoint: `GET /api/v1/trends/{session_id}` — returns `TemporalAnalyzerOutput`                                                                                                                   |
| `app/main.py`              | New endpoint: `GET /api/v1/bva/{session_id}` — returns `BvAAnalyzerOutput`                                                                                                                           |
| `app/main.py`              | New endpoint: `GET /api/v1/payment-terms/{session_id}` — returns `PaymentTermsOptimizerOutput`                                                                                                       |


---

#### v1.5 — March 7, 2026 (Adaptive Skill Routing, Live Thinking UX, Chart Builder)

**Adaptive Skill Selection & Planning**


| File                                                  | Change                                                                                                                                                                                                 |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app/opar/models.py`, `app/opar/observe.py`           | Added adaptive planning signals (`has_tabular_spend`, `has_document_files`, `has_annual_revenue`, `has_headcount`, `wants_executive_narrative`, `wants_document_context`, `wants_spend_visualization`) |
| `app/opar/plan.py`                                    | Refactored fixed intent bundles into adaptive minimal DAGs (benchmark -> lean benchmark chain; value_bridge -> adds modeling chain; business_case -> adds business-case-builder and executive layers)  |
| `app/opar/claude_client.py`                           | Updated planning prompt rules to prefer minimum viable plans; optionalized document/synthesis/communication/chart skills                                                                               |
| `app/opar/orchestrator.py`                            | Added skipped-skill reasoning in progress trace (why optional skills were not selected)                                                                                                                |
| `tests/test_opar.py`, `tests/test_api_integration.py` | Added/updated regression tests for reduced skill breadth and intent-specific chain composition                                                                                                         |


**Live Thinking Trace & Interaction UX**


| File                                             | Change                                                                                                                                                                                    |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/main.py`                                    | Added run-scoped progress state and endpoint `GET /api/v1/chat/progress/{run_id}` for in-flight thinking updates                                                                          |
| `app/opar/orchestrator.py`, `app/opar/act.py`    | Added timestamped progress callback emissions during Observe/Plan/Act/Reflect and per-skill execution updates                                                                             |
| `frontend/index.html`, `frontend/assets/app.css` | Added collapsible live “Model thinking” panel grouped by phase with mini badges and timestamps; preserves user collapse state while polling; typography tuned to secondary metadata style |


**Spend Visualization (New Chart Builder Skill)**


| File                                                         | Change                                                                                                                    |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `skills/chart-builder/SKILL.md`                              | New skill definition for FP&A-driven chart selection and commentary generation                                            |
| `app/skills/engine.py`                                       | Added `chart_builder()` selector logic (Pareto concentration, addressability stack, trend line) and commentary generation |
| `app/services/spend_charts.py`                               | New themed chart renderer for spend profile exports (`.html`)                                                             |
| `app/opar/plan.py`, `app/opar/act.py`, `app/opar/reflect.py` | Integrated `chart-builder` into planning/execution/response: chart URL artefact + chat commentary + next action           |
| `frontend/index.html`, `frontend/assets/app.css`             | Added inline chart preview embedded directly under assistant response                                                     |
| `app/main.py`, `app/services/spend_charts.py`                | Fixed export content serving for HTML charts (proper extension/content-type) to avoid raw HTML display in browser         |


**Memory Backend Resilience**


| File                         | Change                                                                                                                                              |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/opar/memory_adapter.py` | Added Mem0 re-init retry behavior and runtime write-failure graceful fallback to local memory adapter to prevent 500 errors during chat/write paths |


#### v1.4 — March 2, 2026 (FP&A Closure, LLM Synthesis, Mem0 Compatibility)

**FP&A Analytical Enhancements**


| File                                                          | Change                                                                                                                    |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `app/skills/engine.py`                                        | Peer benchmark savings shifted to top-quartile target (P25) and returns `benchmark_target_pct`; P50 retained as reference |
| `app/skills/engine.py`                                        | Added `_compute_irr()` and `irr_pct` in savings model outputs                                                             |
| `app/skills/engine.py`                                        | `heuristic_analyzer` supports optional headcount-normalized signals with per-employee targets                             |
| `app/skills/engine.py`                                        | `spend_profiler` emits `trend_analysis` (MoM growth) when >=2 distinct periods exist                                      |
| `skills/heuristic-analyzer/references/heuristic_targets.json` | Added `per_employee_targets`                                                                                              |
| `data/benchmarks/registry.json`                               | Added `data_quality_note` for benchmark transparency                                                                      |
| `app/services/sensitivity.py`                                 | Expanded to five named scenarios with scenario-level NPV output                                                           |
| `app/services/business_case.py`                               | Added financial projections table, IRR summary, and do-nothing comparison in generated business case                      |
| `app/services/dashboard.py`                                   | Enhanced dashboard visuals including confidence bands and waterfall view                                                  |


**LLM-Grounded Recommendation & Communication Layer**


| File                                      | Change                                                                                                      |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `skills/analysis-synthesizer/SKILL.md`    | Added synthesis skill for evidence-backed recommendation assembly                                           |
| `skills/executive-communication/SKILL.md` | Added Finance Business Partner communication skill for leadership-ready narrative                           |
| `app/opar/plan.py`                        | DAG extended with `analysis-synthesizer` and `executive-communication` tasks                                |
| `app/opar/act.py`                         | Added invocation paths for synthesis + communication; transaction examples injected for narrative grounding |
| `app/opar/claude_client.py`               | Added synthesis and executive communication prompts with strict JSON contracts                              |
| `app/opar/reflect.py`                     | Prefer synthesized/communication outputs when valid; render concrete examples in recommendations            |
| `app/skills/contracts.py`                 | Added contract schemas for synthesis and executive communication outputs                                    |


**UI, Session Context, and Memory**


| File                                             | Change                                                                                                                                      |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/index.html`, `frontend/assets/app.css` | Added audience selector, tightened context layout, and session/context persistence via browser storage                                      |
| `app/main.py`                                    | Added `audience`, `currency`, and `headcount` fields in session/analyze contracts; health endpoint now reports active memory backend status |
| `app/opar/memory_adapter.py`                     | Mem0 compatibility update: uses required `user_id/agent_id/run_id` scoping and write-role semantics aligned with current SDK                |
| `requirements.txt`                               | Added `mem0ai` dependency                                                                                                                   |


#### v1.3 — March 1, 2026 (Chat-Integrated Upload & OPAR Intent Fixes)

**OPAR Intent Classification**


| File                        | Change                                                                                                                                                                                                                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app/opar/observe.py`       | Added `general_qa` and `export_business_case` to the intent taxonomy; default rule-based fallback changed from `upload_data` → `general_qa`                                                                                                                                                      |
| `app/opar/observe.py`       | Clarification gate now fires **only** for analysis intents (`benchmark`, `value_bridge`, `business_case`) — conversational messages and upload requests no longer return "please provide spend data"                                                                                             |
| `app/opar/observe.py`       | Clarification prompt updated to reference the 📎 button and context field locations                                                                                                                                                                                                              |
| `app/opar/plan.py`          | Added `general_qa` case to `_plan_rule_based()`: light `spend-profiler` refresh when data is ready; empty plan (→ onboarding guidance) when no data                                                                                                                                              |
| `app/opar/claude_client.py` | `INTENT_CLASSIFY_PROMPT` extended with `general_qa` and `export_business_case`; "when in doubt, choose general_qa" rule added                                                                                                                                                                    |
| `app/opar/claude_client.py` | `classify_intent_claude` allowed set expanded from 4 → 6 intents; default fallback → `general_qa`                                                                                                                                                                                                |
| `app/opar/orchestrator.py`  | Full rewrite: constants `_ONBOARDING_MSG`, `_FILE_FORMAT_MSG`, `_CAPABILITIES_MSG`, `_NO_DATA_NEXT_OPTS`; helper functions `_answer_general_qa()` and `_handle_no_data_qa()`; `run_opar_loop` `general_qa` early-exit branch with three sub-cases (existing analysis / files uploaded / no data) |
| `tests/test_opar.py`        | `test_classify_intent_rule_based` updated: "hello" asserts `general_qa` (was `upload_data`); two additional `general_qa` assertions added                                                                                                                                                        |


**Chat-Integrated File Upload**


| File                      | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/main.py`             | New `POST /api/v1/chat/with-files` multipart endpoint: accepts `message + session_id + files[]`; uploads files, infers schema, runs full OPAR loop, returns `uploaded_files` with detected column role mappings                                                                                                                                                                                                                                                                                |
| `frontend/index.html`     | Complete rewrite: removed standalone "Upload Files" section; added hidden `<input id="chatFileInput">`, circular 📎 `<button id="attachBtn">` in the chat input row, `<div id="pendingFilesBar">` for staged file chips above the textarea                                                                                                                                                                                                                                                     |
| `frontend/index.html`     | Drag-and-drop onto the chat shell triggers file staging                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `frontend/index.html`     | Send logic: uses `POST /api/v1/chat/with-files` (FormData) when pending files exist, else `POST /api/v1/chat` (JSON)                                                                                                                                                                                                                                                                                                                                                                           |
| `frontend/index.html`     | `addFileUploadNote()`: renders schema confirmation as an inline system note after upload (detected row count and column → role mappings)                                                                                                                                                                                                                                                                                                                                                       |
| `frontend/index.html`     | `addSystemNote()`: blue-tinted inline note for upload confirmations, schema details, and errors                                                                                                                                                                                                                                                                                                                                                                                                |
| `frontend/index.html`     | `addThinkingIndicator()`: animated three-dot indicator while API call is in flight                                                                                                                                                                                                                                                                                                                                                                                                             |
| `frontend/index.html`     | System Output and Pipeline Management sections collapsed into `<details>` elements by default                                                                                                                                                                                                                                                                                                                                                                                                  |
| `frontend/index.html`     | Business Case and Show Schema actions moved to chat header action buttons                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `frontend/assets/app.css` | Complete rewrite: `--system` / `--system-border` CSS variables; `.context-row` 4-column responsive grid; `.chat-shell.drag-over` highlight; `.chat-header-actions` / `.header-btn`; `.pending-files-bar` / `.file-chip` (icon, name, size, remove); `.attach-btn` (40px circle); `.send-btn`; `.msg.system` / `.msg-wrap.system` (full-width blue-tinted); `.thinking-wrap` / `.thinking-dot` with `@keyframes bounce`; `<details>` summary styles; responsive breakpoints at 1060px and 780px |


---

#### v1.2 — March 1, 2026 (Security Hardening & Performance Optimization)

**Security**


| File          | Change                                                                                                   |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| `app/main.py` | CORS `allow_origins` moved to `ALLOWED_ORIGINS` env var; wildcard `*` removed                            |
| `app/main.py` | UUID v4 regex validation (`_UUID_RE` + `_validate_session_id()`) applied to all session-scoped endpoints |
| `app/main.py` | Upload filename sanitized via `Path(filename).name` to strip directory traversal components              |
| `app/main.py` | Export endpoint checks resolved path stays within `OUTPUT_DIR` prefix                                    |
| `app/main.py` | `delete_memory` key sanitized to reject `/`, `\`, `..`                                                   |
| `app/main.py` | `test_skill` endpoint uses direct `SKILL.md` existence check instead of `discover_skills()` glob         |


**Data Integrity**


| File                                                         | Change                                                                                                                                                 |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `app/services/pipeline.py`                                   | `threading.Lock` (`_LOCK`) added; all read-modify-write paths on the JSON store are now atomic                                                         |
| `app/services/benchmarks.py`                                 | `threading.Lock` (`_LOCK`) added to `create_dataset`                                                                                                   |
| `app/services/pipeline.py`                                   | `pipeline_summary` consolidates to a single `_load_store()` call                                                                                       |
| `app/main.py`, `app/services/compliance.py`, `app/models.py` | All `datetime.utcnow()` calls replaced with `datetime.now(timezone.utc)`; `models.py` Pydantic `default_factory` fields use private `_utcnow()` helper |


**Performance**


| File                         | Change                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `app/services/analysis.py`   | Module-level `_TAXONOMY` cache; taxonomy JSON read from disk only once per process                                       |
| `app/skills/engine.py`       | `_HEURISTIC_RANGES` module-level constant replaces per-call dict construction                                            |
| `app/skills/engine.py`       | `_classify_line(text)` single-pass helper; `spend_profiler` now does one string-build + one classify call per spend line |
| `app/skills/engine.py`       | `build_raw_rows()` public helper eliminates duplicate `value_bridge_calculator` execution in analysis and act paths      |
| `app/services/ingestion.py`  | `iterrows()` replaced with pre-extracted `Series` + `iloc`; 5–10× faster on large files                                  |
| `app/services/pipeline.py`   | `at_risk_initiatives` pre-indexes milestones and actuals by `initiative_id` for O(1) per-initiative lookup               |
| `app/services/benchmarks.py` | `today_iso` computed once before dataset selection loop                                                                  |


**Code Quality**


| File                                                                                         | Change                                                                                     |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `app/main.py`, `app/services/analysis.py`, `app/opar/orchestrator.py`, `app/opar/reflect.py` | `MemoryStore()` singleton pattern — module-level `_memory` replaces per-call instantiation |
| `app/main.py`, `app/opar/act.py`                                                             | Deferred inline imports moved to module top-level                                          |
| `requirements.txt`                                                                           | All 10 dependencies pinned to exact versions for reproducible builds                       |


---

#### v1.1 — February 28, 2026

Initial release with full OPAR loop, core skills, memory adapter, and business case export.

---

### D. References

- BCG Cost Management & Cost Advantage Strategy
- BCG Executive Perspectives May 2025: Driving Sustainable Cost Advantage with AI
- McKinsey Global Operations Benchmark
- Mem0: Universal Memory Layer for AI Agents (github.com/mem0ai/mem0)
- OPAR Loop Specification (OPAR.md) — Observe → Plan → Act → Reflect agentic loop
- Claude Agent Skills Architecture (platform.claude.com/docs/en/agents-and-tools/agent-skills)
- Anthropic Engineering: Equipping Agents for the Real World with Agent Skills

