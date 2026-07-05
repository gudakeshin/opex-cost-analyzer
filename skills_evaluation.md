# Skills Catalog & Authoring Pipeline Evaluation — OpEx Cost Analyzer
**Date:** July 2026 (updated 2026-07-05 post-remediation) | **Scope:** All `skills/*/SKILL.md` files (40 on disk), `skills/manifest.yaml` (40 entries), discovery/routing (`app/skills/registry.py`, `app/skills/discovery.py`), dispatch (`app/skills/dispatch.py`), declarative runtime (`app/opar/claude_client.py:1433`), and no-code authoring (`app/routers/skills.py`)

> **Revision note:** The original 2026-07-05 evaluation identified 14 issues across catalog quality and authoring-pipeline safety. All P0 and P1 items (and most P2 items) were fixed the same day in commit `884c1c3` ("Harden the skill authoring/catalog pipeline and fix doc-implementation drift"). This document now describes the **current** state; the original findings are preserved in the Resolved Findings ledger below so the before/after is auditable.

---

## Executive Summary

The skills layer now has **solid infrastructure and a hardened authoring path** — a manifest DAG with parallel execution, drift validation, catalog integrity tests, audit events, a fail-closed smoke-test endpoint, a draft→test→activate lifecycle, YAML-safe frontmatter parsing, deterministic skill-lint and catalog-eval harnesses wired into CI.

**Catalog (stored skills):** All 40 on-disk skills have YAML frontmatter with trigger descriptions and are registered in the manifest. The former 4-line stubs at the DAG hubs (`savings-modeler`, `root-cause-analyzer`) are now full documents (38 and 36 lines) with frontmatter, inputs, outputs, and methodology matching their Python engines. Broken reference paths are fixed. SKILL.md bodies that described interactive-agent workflows the deterministic runtime never performs now carry accurate runtime-methodology sections.

**Authoring pipeline (drafted skills):** Skill names are slug-validated with path containment (`app/skills/validation.py`); structured creates start as `status: draft` and stay out of the production DAG until `POST /api/v1/skills/{name}/activate` succeeds — which requires a passing smoke test. The smoke test fails closed on empty output or provider degradation (`_evaluate_smoke_result`, `app/routers/skills.py:73-89`). Create/update auto-invalidate the discovery index. `depends_on` is validated against known skill names and no longer conflated with `inputs`. `update_skill` validates content and bumps the version.

**Test ground truth (re-run 2026-07-05, post-fix):**
```
$ pytest tests/test_skill_catalog.py tests/test_skill_manifest.py tests/test_skill_discovery.py \
         tests/test_skill_authoring.py tests/test_skill_lint.py -q
21 passed, 4 warnings in 8.66s

$ python scripts/lint_skills.py
skill-lint: OK

$ python eval/run_skill_catalog_eval.py
overall_pass: true | manifest_skill_count: 40 | manifest_drift_errors: [] | discovery MRR@3: 1.0
```
The `sensitivity-analyzer` smoke-test crash reported in the original evaluation is fixed (`app/services/sensitivity.py`) and no longer reproduces.

**Bottom line:** Routing, execution, and the authoring lifecycle are now trustworthy for self-service use. The remaining gap is **content depth**, not safety: 23 of 40 skills score below the 3.0 rubric threshold in the catalog eval (average 2.62/5), mostly for missing structured Methodology/Inputs/Outputs sections. The declarative runtime is schema-enforced but still **latent** — zero production skills declare `runtime: declarative`, and live LLM validation awaits API billing restoration.

---

## What's Working Well

**Clean lifecycle architecture.** SKILL.md metadata is parsed via `yaml.safe_load` in `parse_skill_md()` (`app/skills/registry.py`), registered handlers dispatch via `invoke_skill()` (`app/skills/dispatch.py:122-139`), and the OPAR planner executes skills in `parallel_group` order (`app/opar/act.py`). Manifest rows carry `parallel_group`, `depends_on`, `estimated_tokens`, and `status` for all 40 skills.

**Drift validation with full-disk inventory.** `validate_manifest_drift()` cross-checks manifest names against `_DEP_MAP`, registered handlers, on-disk SKILL.md files, `discover_skills()`, and — since the remediation — flags any discoverable on-disk skill missing from the manifest (`app/skills/manifest.py:71-118`). Current run: no drift errors.

**Fail-closed smoke testing.** `POST /api/v1/skills/{name}/test` builds synthetic spend lines, pre-seeds the core chain, and invokes the handler (`app/routers/skills.py:213-309`). Empty output dicts, non-dict results, and degraded reasons in `FAIL_DEGRADED_REASONS` all report **fail**; `provider_disabled` (no API key) reports **skipped**, never pass (`_evaluate_smoke_result`, `app/routers/skills.py:73-89`).

**Draft → test → activate lifecycle.** `_compose_skill_md()` writes `status: draft` (`app/routers/skills.py:49`); `create_structured_skill()` appends a draft manifest row (`app/routers/skills.py:179`); the planner skips non-active rows; `POST /api/v1/skills/{name}/activate` refuses with 409 unless the smoke test passes (`app/routers/skills.py:312-363`).

**CI quality gates.** `scripts/lint_skills.py` (frontmatter schema, reference resolution, depends_on validity, description length) and `eval/run_skill_catalog_eval.py` (discovery routing MRR@3, rubric scoring, manifest drift, declarative schema enforcement — no live LLM) both run in CI (`.github/workflows/ci.yml:69-73`).

**Discovery routing accuracy.** The catalog eval's 4 routing cases all hit their expected skill in the top 3 (MRR@3 = 1.0), including the former stub hubs: "model savings NPV phased initiatives" → `savings-modeler` ranked #1; "diagnose why spend is above peers root cause" → `root-cause-analyzer` ranked #1 (`eval/skill_catalog_report.md`).

**Best-in-class SKILL.md examples.** `evidence-gatherer`, `spend-profiler`, `peer-benchmarker`, and `dashboard-builder` combine rich trigger descriptions, step-by-step methodology, and reference data files; the rewritten `savings-modeler` and `root-cause-analyzer` now follow the same pattern with implementation pointers to their engine functions.

---

## Resolved Findings (original 2026-07-05 evaluation → fixed in `884c1c3`)

### A. Catalog quality

| # | Original finding | Resolution (verified 2026-07-05) |
|---|---|---|
| A1 | `savings-modeler` and `root-cause-analyzer` were 4-line stubs with no frontmatter; `chart-builder` lacked frontmatter; discovery fell back to H1 headings for two DAG hubs | All three rewritten with full frontmatter (≥300-char trigger descriptions), Inputs, Outputs, Methodology, and engine-function pointers (`skills/savings-modeler/SKILL.md` 38 lines, `skills/root-cause-analyzer/SKILL.md` 36 lines, `skills/chart-builder/SKILL.md` 41 lines). Discovery ranks both hubs #1 for their trigger queries. |
| A2 | Broken reference paths: `heuristic-analyzer` cited nonexistent `heuristic_ranges.json`; `peer-disclosure-miner` cited a peer_set path that didn't resolve | `heuristic-analyzer/SKILL.md` now cites `references/heuristic_targets.json` (lines 16, 43 — file exists); `peer-disclosure-miner/SKILL.md:16` cites the real `skills/sector-packs/<pack_id>/peer_set.json` pattern. skill-lint enforces reference resolution. |
| A3 | Doc–implementation drift: SKILL.md bodies described interactive-agent workflows ("ask the user to confirm column mapping", LLM classification, learning from corrections) that the deterministic Python runtime never performs | `spend-profiler`, `peer-benchmarker`, `dashboard-builder`, `heuristic-analyzer`, and `document-contextualizer` each gained a "Runtime Methodology" section naming the actual dispatcher/engine function and emitted dict shape; residual narrative prose is explicitly scoped as framing, not runtime behavior. |
| A4 | 3 on-disk skills (`data-classifier`, `llm-context-builder`, `pii-stripper`) absent from manifest; `temporal-analyzer` row missing `status`; drift validator didn't check full disk inventory | Manifest now has 40 entries covering every SKILL.md on disk; `temporal-analyzer` row carries `status: active` (`skills/manifest.yaml:189-198`); `validate_manifest_drift()` extended to flag discoverable on-disk skills missing from the manifest (`app/skills/manifest.py:112-116`). |
| A5 | Naive line-splitting frontmatter parser broke `description: >` folded scalars (`analysis-synthesizer` parsed as `">"`, 1 char) and `_compose_skill_md` mangled quotes | Registry parses with `yaml.safe_load` and composes with `yaml.dump` (`app/skills/registry.py:8,28,38`). `analysis-synthesizer` description now parses to 781 characters. Round-trip covered by `tests/test_skill_authoring.py`. |
| A6 | `sensitivity-analyzer` smoke test crashed: `unsupported operand type(s) for +: 'float' and 'NoneType'` | Null-safe arithmetic in `app/services/sensitivity.py`; smoke test passes (part of the 21-test green run). |

### B. Authoring pipeline

| # | Original finding | Resolution (verified 2026-07-05) |
|---|---|---|
| B1 | No name validation on create — `payload.name` used directly in filesystem path; path traversal possible | `validate_skill_slug_http()` + `resolve_skill_md_path()` enforce slug regex and path containment on every skill endpoint (`app/skills/validation.py`, used throughout `app/routers/skills.py`). Covered by `tests/test_skill_authoring.py`. |
| B2 | No draft lifecycle — structured create wrote `status: active` straight into the production manifest DAG | Creates are `status: draft` in both SKILL.md and manifest; `POST /activate` flips to active only after a passing smoke test, else 409 (`app/routers/skills.py:312-363`). |
| B3 | Discovery index never invalidated on create/update; new skills invisible until manual reindex | `_invalidate_discovery_index()` called at the end of create, structured create, update, and activate (`app/routers/skills.py:32-35,143,157,361`). |
| B4 | `depends_on` conflated with `inputs` — data inputs became bogus DAG edges | `validate_depends_on(payload.depends_on)` validates each dependency against known skill names; `inputs` stay in SKILL.md prose only (`app/routers/skills.py:167`). |
| B5 | Silent failure masking — `test_skill` reported **pass** on `{}` output with `degraded_reason: provider_unavailable` | Fail-closed: degraded reasons in `FAIL_DEGRADED_REASONS`, empty dicts, and non-dict outputs all fail; `provider_disabled` is skipped, never pass (`app/routers/skills.py:73-89`). |
| B6 | Declared `output_fields` never enforced at runtime | `run_declarative_skill_claude_with_meta()` accepts `output_fields` and the dispatch layer validates output via `validate_declarative_output()`, returning `schema_parse_fail` on mismatch (`app/opar/claude_client.py:1443-1448`, `app/skills/dispatch.py:180-186`). Verified by the catalog eval's declarative-schema check (passes with mocked fixtures). |
| B7 | `update_skill` accepted anything — no parse validation, no version bump, could corrupt built-in skills' docs | `validate_skill_md_content()` gates updates (400 on invalid frontmatter); registered Python skills must retain `runtime: python`; version auto-bumps on success (`app/routers/skills.py:120-145`). |
| B8 | No eval coverage for drafted skills | `eval/run_skill_catalog_eval.py` scores discovery routing (MRR@3), per-skill rubric, manifest drift, and declarative schema conformance with deterministic fixtures — no live LLM. Runs in CI. |

---

## Current Scoring — Catalog Eval Rubric

The authoritative rubric now lives in `eval/run_skill_catalog_eval.py` (scored 0–5; report at `eval/skill_catalog_report.md`, scores at `eval/skill_catalog_scores.json`). It is stricter than the original evaluation's hand rubric: full credit requires parseable frontmatter, a ≥80-char trigger description, **and** structured Methodology, Inputs, and Outputs sections.

**Current distribution (2026-07-05 run):** average **2.62 / 5**; **23 of 40** skills below the 3.0 threshold:

> analysis-synthesizer, assumption-register, brsr-cobenefit-calculator, business-case-builder, cohort-segmenter, dashboard-builder, data-classifier, data-validator, document-contextualizer, executive-communication, export-formatter, heuristic-analyzer, indian-tax-optimizer, internal-benchmarker, llm-context-builder, peer-benchmarker, peer-disclosure-miner, pii-stripper, scenario-modeler, sensitivity-analyzer, spend-profiler, value-bridge-calculator, value-to-shareholder-bridge

These are **content-depth** gaps (missing `## Inputs` / `## Outputs` / methodology headings the rubric recognizes), not safety or routing problems — discovery MRR@3 is 1.0 and all handlers pass smoke tests. The below-threshold list is the primary remaining backlog (see `skills_improvement_plan.md`, item R1).

---

## Catalog Quality vs Authoring Pipeline — Current Summary

| Dimension | Catalog (stored) | Authoring pipeline (draft) |
|---|---|---|
| **Routing / discovery** | MRR@3 = 1.0 on eval cases; all 40 skills have parseable trigger descriptions | New/edited skills discoverable immediately (auto-reindex) |
| **Execution** | All Python handlers pass smoke tests (21/21 tests green) | Declarative path fail-closed; schema-enforced; latent (0 production declarative skills) |
| **Documentation trust** | Frontmatter accurate everywhere; 5 formerly-drifted skills carry runtime-methodology sections; 23 skills still thin on structured sections | Composed SKILL.md YAML-safe; round-trip tested |
| **Manifest integrity** | 40/40 on disk ↔ manifest; drift validator covers full disk inventory | Draft rows until activation; depends_on validated |
| **Consultant readiness** | Usable; content-depth uplift recommended for the 23 below-threshold skills | Safe for self-service authoring; live declarative runs pending API billing |

---

## Remaining Gaps

| Area | Current state | Priority |
|---|---|---|
| SKILL.md content depth | 23/40 below rubric threshold 3.0 (avg 2.62) — missing structured Inputs/Outputs/Methodology sections | Medium |
| Declarative runtime, live | Schema enforcement verified with mocks only; Anthropic key unbilled, zero production declarative skills | Low (blocked on billing) |
| Discovery eval breadth | 4 routing cases in the harness; plan targeted 20 queries | Low |
| Residual narrative prose | Interactive-agent framing remains in some SKILL.md bodies, explicitly scoped as non-runtime — acceptable, but full rewrites would be cleaner | Low |
