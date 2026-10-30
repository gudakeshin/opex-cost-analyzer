# OpEx Intelligence Platform

A cost-diagnostic workbench for large (primarily Indian) enterprises. It ingests a company's
spend data and context documents, classifies and profiles spend, benchmarks it against peers,
sizes and prioritises savings initiatives, and produces CFO-ready outputs.

It is built as a **consultant-operated tool**: an advisory team uploads the client's ledgers,
P&L and supporting documents, runs the analysis, and works the results with the client's
CFO / Cost Transformation Office. Reference implementation aligned to
`OpEx_Intelligence_Platform_PRD_v2.0.md`.

What makes it different from a generic spend-cube tool:

- **India layer** — INR with lakh/crore formatting, GST / GSTIN / PAN / MSME handling, Ind AS 116
  lease treatment, BRSR disclosures, April–March fiscal year.
- **16 sector packs** — authored lever libraries, taxonomies, peer sets and benchmark percentiles per sector.
- **A deterministic core.** Classification, benchmarking, savings sizing, NPV/IRR and validation
  are code, not LLM output. The LLM writes the narrative on top and every run records provenance.
- **Honest about uncertainty** — see [Limitations](#limitations).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then add an LLM key (optional, see below)

cd frontend && npm install && npm run build && cd ..   # builds the UI that FastAPI serves
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/ui/`. The frontend must be built once, otherwise `/ui/` has nothing to serve.

**Try it without your own data:** on the Analysis page click **Load demo engagement**. It creates an
engagement and uploads the bundled sample ledger so you can run a full analysis straight away.

**Works without an LLM key.** All deterministic skills (ingestion, profiling, benchmarking, savings,
validation) run regardless. Without a key the narrative/advisory synthesis falls back to a
deterministic composer, and `analysis-synthesizer` / `executive-communication` return a degraded result.
See [docs/known_stubs.md](docs/known_stubs.md).

### Frontend development (hot reload)

```bash
uvicorn app.main:app --reload            # terminal 1: API on :8000
cd frontend && npm run dev               # terminal 2: Vite on :5173, proxies /api to :8000
```

Open `http://localhost:5173/ui/`.

## The app, page by page

| Page | Use it to |
|---|---|
| **Analysis** (`/`) | Upload data, chat with the planning agent, run the full analysis, see insights, trust rail and provenance. Has a Stop button, an engagement switcher and a first-run guide. |
| **Diagnostic** | Capture engagement context (sector, annual revenue, company URLs) and get a benchmark-gap diagnostic. |
| **Workbench** | Compose, run and compare individual analyses (see below). |
| **Cost Room** | Track initiatives through the pipeline: committed / deferred / rejected, actuals, PMO and export views. |
| **Benchmarks** | Browse benchmark datasets and sector-pack benchmark percentiles. |
| **Pack Studio** (`/sector-packs`) | Author and publish sector packs (manifest, taxonomy, peers, levers, KPIs, benchmarks, regulatory layer). |
| **Skills** | View and edit the skill catalogue (`skills/*/SKILL.md`). |
| **Documents** | Create and manage engagements and their uploaded documents. |
| **Guidebook** | Reference for the data tiers and files an engagement needs. |
| **History** | Resume earlier sessions. |

**Executive view** (toggle in the sidebar, available after an analysis) shows only the Cost Room, without the consultant tooling.

### Workbench

The Workbench is for working the numbers after (or alongside) the main analysis. It has four tabs:

- **Compose** — pick analyses from a catalogue, set assumptions (WACC, tax rate, horizon, revenue), get live validation, run, then **branch** or **chain** runs, **compare** two runs side by side, and **promote** a run's results to Cost Room initiatives.
- **Query** — ask questions in plain language; it generates a read-only `SELECT` over the engagement's spend (`spend` view), shows the SQL, and lets you save queries and export results.
- **What-if** — change drivers and compare scenarios against a base case; save scenario sets.
- **Analyst** — free-form Q&A over the engagement's analysis outputs.

## How it works

```
upload → ingestion & classification → OPAR agent loop → skills → validation → synthesis → outputs
```

- **Ingestion** (`app/services/ingestion.py`): CSV/XLSX/JSON ledgers and P&L workbooks. Detects delimiter and
  encoding, parses Indian number formats, classifies lines, and returns a report of rows read/dropped and why.
  Re-uploading an identical file to the same engagement is rejected (`409`, override with `?allow_duplicate=true`).
- **OPAR loop** (`app/opar/`): Observe → Plan → Act → Reflect. The plan is shown for approval before expensive work.
- **Skills** (`skills/`, runtime in `app/skills/`): 40 skills — spend profiler, peer/internal benchmarker,
  heuristic analyzer, value-bridge calculator, savings modeler, scenario/sensitivity, and so on.
- **Sector packs**: `sector_packs/<pack_id>/` is the authored source of truth. `skills/sector-packs/<pack_id>/sector_levers.json`
  is generated from it by `scripts/sync_category_levers_runtime.py` — edit the former, then re-sync.
- **Savings figures** carry both a full-delivery view and a probability-weighted `risk_adjusted` view.
- **Persistence**: SQLite (`data/opex.db`) for engagements, documents, sessions and jobs; files under `data/`
  for uploads, parsed documents and per-engagement spend stores (Parquet/DuckDB).
- **Outputs**: board deck, CFO brief, MoR pack, PMO workbook, evidence appendix, business case, dashboards.
- **Source-system connectors** (`app/connectors/`): `ariba_csv`, `hrms_csv`, `tally_xml`, `bank_mt940`,
  `gst_portal` (file-based) and `sap_odata` (needs live credentials), via `POST /api/v1/connectors/{type}/ingest`,
  with optional async and delta-sync modes.
- **Compliance**: audit log, privacy controls, risk register, and an engagement tear-down protocol
  (`GET /api/v1/engagement/{id}/teardown-plan` previews it).

## Configuration

Copy `.env.example` to `.env`. The important settings:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | auto | `anthropic` or `gemini`; auto-selects Gemini when only `GEMINI_API_KEY` is set |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | — | Enable LLM synthesis. Optional. |
| `LLM_MODE` | `M2` | `M1` deterministic only, `M2` managed API, `M3` on-prem (Ollama) |
| `AUTH_ENABLED` | `false` | Bearer-token auth (`API_AUTH_TOKENS`). Turn on for anything beyond localhost. |
| `REPOSITORY_BACKEND` | `sqlite` | Storage backend for engagements/sessions |
| `OPEX_DATA_DIR` | `./data` | Where all runtime state lives |
| `QDRANT_ENABLED` / `DOC_RAG_ENABLED` | `true` | Document retrieval; set to `false` to run without Qdrant |
| `REDIS_URL` | unset | Required for more than one worker (distributed locks) |
| `LLM_TEMPERATURE` | unset | Lower for more repeatable narratives |

All variables the code reads are listed, with defaults, in `.env.example`.

## API

Interactive docs at `http://127.0.0.1:8000/docs` (OpenAPI). About 115 endpoints live under `/api/v1/`, grouped by:
`engagements`, `sessions`, `analyze` (background runs: `/analyze/runs/{id}`, `/cancel`), `chat`, `workbench`, `query`, `sensitivity`, `analyst`, `skills`, `sector-packs`,
`benchmarks`, `initiatives` / `pipeline` (Cost Room), `connectors`, `jobs`, `compliance`, plus export routes
(`board-deck`, `cfo-brief`, `mor-pack`, `pmo-export`, `business-case`, `evidence-appendix`, `dashboard`).

## Testing and evaluation

```bash
pytest -q
```

The suite runs against a **temporary data directory** (`OPEX_DATA_DIR`) and aborts if it would touch the real
`data/`, so it is safe to run while you have local engagements.

Evaluation harnesses live in `eval/` (`python -m eval.run_<name>_eval`). Most are **structural** — they check
that skills are wired and outputs are complete, not that the analysis is correct. The content-checking
evals are `run_llm_judge_eval.py` and `run_llm_golden_eval.py` (NL→SQL and scenario parsing). Set empty
`ANTHROPIC_API_KEY` / `GEMINI_API_KEY` to run the deterministic ones without cost.

Sample data: see [test_data/README.md](test_data/README.md).

## Limitations

Stated plainly so nobody mistakes them for finished work (more detail in [docs/known_stubs.md](docs/known_stubs.md)):

- **Peer benchmarks are thin.** Sector-pack percentiles come from the public disclosures of a handful of companies per
  sector (typically 6 to 10), so confidence intervals are wide. The platform's generic seed benchmarks (used when no
  sector pack matches) have no sample at all: no interval is shown and the output is flagged illustrative. Licensed
  feeds (CMIE, Capitaline, CRISIL, ICRA) are integration stubs and are not on any live path.
- **Analysis cancel is cooperative.** A run is a background job (one per session) that survives a page reload and can be
  resumed. **Stop** asks the server to cancel; it takes effect between pipeline stages, so the stage already running
  finishes first and nothing partial is saved. Chat requests are not cancellable server-side. Run state is per process.
- **Single-node by default.** Locks are in-process unless `REDIS_URL` is set.
- **Column mapping is automatic.** The detected mapping is not shown for confirmation; check the ingest report's dropped-row counts and warnings.
- **Regulatory watcher** uses a static sample catalogue unless `REG_WATCHER_LIVE=1`.
- **No multi-user review workflow** (comments, approvals) and no cross-engagement comparison.
- **LLM narrative is not reproducible bit-for-bit.** Figures in it are checked against skill outputs and unmatched ones are listed
  in `quality_signals.unverified_figures`, but treat that list as a prompt to review, not proof.

## Repository layout

```
app/            FastAPI backend (routers, services, OPAR loop, skills runtime, connectors)
frontend/       React + Vite + TypeScript + Tailwind UI
skills/         Skill definitions (SKILL.md + references); skills/sector-packs is generated
sector_packs/   Authored sector packs (source of truth)
eval/           Evaluation harnesses and their latest reports
tests/          pytest suite
test_data/      Sample engagement packs for manual testing
data/           Runtime state; only a few fixtures (samples/, risk register) are committed
docs/           Architecture docs and known stubs
scripts/        Local server, perf check, pack tooling
```
