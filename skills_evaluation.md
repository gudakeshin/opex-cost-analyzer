# Skills Catalog & Authoring Pipeline Evaluation — OpEx Cost Analyzer
**Date:** July 2026 | **Scope:** All `skills/*/SKILL.md` files (40 on disk), `skills/manifest.yaml` (37 entries), discovery/routing (`app/skills/registry.py`, `app/skills/discovery.py`), dispatch (`app/skills/dispatch.py`), declarative runtime (`app/opar/claude_client.py:1433`), and no-code authoring (`app/routers/skills.py`)

---

## Executive Summary

The skills layer has **solid infrastructure** — a manifest DAG with parallel execution, drift validation, catalog integrity tests, audit events, and a smoke-test endpoint — but **uneven catalog quality** and **authoring-path gaps** undermine consultant trust.

**Catalog (stored skills):** Python handlers generally execute and return structured dicts, but two load-bearing DAG hubs (`savings-modeler`, `root-cause-analyzer`) are 4-line stubs with no frontmatter, so semantic discovery falls back to H1 headings. Several rich SKILL.md bodies describe interactive LLM agent workflows that the deterministic Python runtime never performs, misleading both embeddings and human readers. Broken reference paths and manifest omissions affect 5+ skills.

**Authoring pipeline (drafted skills):** The structured-create path can write a skill straight into the production manifest as `status: active` with no slug validation, no draft lifecycle, no post-create reindex, and a smoke test that reports **pass** on empty `{}` output when the LLM provider fails. There are currently **zero declarative skills** in the catalog, so the declarative runtime is untested in production — but the failure modes are already wired in.

**Test ground truth (re-run 2026-07-05):**
```
$ pytest tests/test_skill_catalog.py tests/test_skill_manifest.py tests/test_skill_discovery.py -q
..F.....
1 failed, 7 passed, 4 warnings in 9.42s
```
Failure: `sensitivity-analyzer` smoke test — `unsupported operand type(s) for +: 'float' and 'NoneType'` (`tests/test_skill_catalog.py:51`). `validate_manifest_drift()` returned an empty list (OK per `app/skills/manifest.py:53`).

**Bottom line:** Routing and execution work for most Python skills, but consultants cannot yet **trust** the no-code authoring path, and the catalog's **documentation–implementation alignment** is too weak for discovery and SME review to be reliable without manual curation.

---

## What's Working Well

**Clean lifecycle architecture.** SKILL.md metadata is parsed by `parse_skill_md()` (`app/skills/registry.py:73-99`), registered handlers dispatch via `invoke_skill()` (`app/skills/dispatch.py:122-139`), and the OPAR planner executes skills in `parallel_group` order (`app/opar/act.py:226-228`). Manifest rows carry `parallel_group`, `depends_on`, and `estimated_tokens` (`skills/manifest.yaml`).

**Drift validator exists.** `validate_manifest_drift()` cross-checks manifest names against `_DEP_MAP`, registered handlers, on-disk SKILL.md files, and `discover_skills()` (`app/skills/manifest.py:52-90`). Covered by `tests/test_skill_manifest.py:6-8`. Current run: no drift errors.

**Smoke-test endpoint and catalog guards.** `POST /api/v1/skills/{name}/test` builds synthetic spend lines, pre-seeds the core chain, and invokes the handler (`app/routers/skills.py:156-254`). `tests/test_skill_catalog.py:26-30` ensures every registered handler has a SKILL.md; `tests/test_skill_discovery.py:24-27` verifies semantic discovery ranks benchmarking queries.

**Audit and execution status.** Create/update emit audit events (`app/routers/skills.py:99`, `app/routers/skills.py:86`). `list_skills()` surfaces `execution_status` as `python`, `declarative`, or `doc-only` via `_skill_execution_status()` (`app/routers/skills.py:40-49`, `app/routers/skills.py:52-61`).

**Best-in-class SKILL.md examples.** `spend-profiler`, `peer-benchmarker`, and `dashboard-builder` combine rich trigger descriptions (638–751 chars in frontmatter), step-by-step methodology, edge cases, and reference data files. `evidence-gatherer` is the only skill scoring ≥5.5 on the rubric below — compact but complete (inputs, outputs, methodology aligned to Python behavior).

---

## Issues by Category

### A. Catalog Quality — Stored SKILL.md Files

#### A1. Extreme depth variance; critical DAG hubs are stubs

| Skill | Lines | Frontmatter | Discovery description source |
|---|---:|---|---|
| `savings-modeler` | 4 | None | H1: "Savings Modeler" (`skills/savings-modeler/SKILL.md:1-3`) |
| `root-cause-analyzer` | 4 | None | H1: "Root Cause Analyzer" (`skills/root-cause-analyzer/SKILL.md:1-3`) |
| `chart-builder` | 36 | None | H1 fallback (`skills/chart-builder/SKILL.md:1-3`) |
| `spend-profiler` | 132 | Yes (638-char description) | Frontmatter (`skills/spend-profiler/SKILL.md:1-4`) |
| `dashboard-builder` | 202 | Yes (743-char description) | Frontmatter (`skills/dashboard-builder/SKILL.md:1-4`) |

Both `savings-modeler` and `root-cause-analyzer` feed downstream skills (`value-bridge-calculator`, `scenario-modeler`, `evidence-gatherer`, etc.) via manifest `depends_on` edges. With no frontmatter, `parse_skill_md()` sets `description` from the H1 heading only (`app/skills/registry.py:88-89`), producing poor discovery embeddings for two of the most important skills in the DAG.

The Python implementations are substantial — e.g. `savings_modeler()` in `app/skills/engine/savings.py:83-97` and `root_cause_analyzer()` in `app/skills/engine/benchmarking.py:219-228` — but none of that logic is reflected in SKILL.md.

#### A2. Broken or misleading reference paths

| Skill | Cited path | Actual |
|---|---|---|
| `heuristic-analyzer` | `references/heuristic_ranges.json` (`skills/heuristic-analyzer/SKILL.md:32`) | `references/heuristic_targets.json` (only file in that dir) |
| `peer-disclosure-miner` | sector pack `peer_set.json` (`skills/peer-disclosure-miner/SKILL.md:16`) | No `references/` dir under the skill; peer sets live under `skills/sector-packs/` |

#### A3. Documentation–implementation drift

**Spend-profiler** SKILL.md instructs the agent to ask users to confirm column mapping, run a two-pass rule + LLM classification, and learn from user corrections (`skills/spend-profiler/SKILL.md:26-33`, `skills/spend-profiler/SKILL.md:48-52`, `skills/spend-profiler/SKILL.md:76`). Runtime is deterministic: `@register("spend-profiler")` → `_engine.spend_profiler(ctx.lines)` (`app/skills/dispatch.py:246-250`) → keyword/rule classification in `spend_profiler()` (`app/skills/engine/profiler.py:472-509`). No user prompts, no LLM pass, no correction learning.

Similar drift appears in `peer-benchmarker` ("tell the user what you need and pause", `skills/peer-benchmarker/SKILL.md:17`) and `dashboard-builder` (describes Chart.js HTML file generation, `skills/dashboard-builder/SKILL.md:22-28`) while handlers produce platform-native outputs.

This misleads:
- **Semantic discovery** — embeddings index agent-instruction prose, not runtime behavior (`app/skills/registry.py:136-147`).
- **Consultant review** — SKILL.md reads like an interactive playbook; execution is a batch pipeline.

#### A4. Manifest and disk inventory gaps

Empirical inventory (2026-07-05 script):

| Metric | Count |
|---|---:|
| Child directories under `skills/` (excl. files) | 43 |
| Directories with `SKILL.md` | 40 |
| Manifest entries | 37 |
| On disk, not in manifest | 3: `data-classifier`, `llm-context-builder`, `pii-stripper` |
| Non-catalog directories (no SKILL.md) | `sector-packs/`, `model-contextualizer/` (prompts only), `references/` |

`temporal-analyzer` is in the manifest but has **no `status` field** (`skills/manifest.yaml:160-168`). Planner defaults missing status to `"active"` (`app/opar/plan.py:370`), so behavior is correct but the manifest row is incomplete.

`validate_manifest_drift()` did not flag the 3 unmanifested skills because they are not in `_DEP_MAP` (`app/skills/manifest.py:63-69`) — the validator checks registered/planned skills, not full disk inventory.

#### A5. Frontmatter parsing fragility affects discovery quality

`_parse_frontmatter()` is a naive line splitter with no YAML library (`app/skills/registry.py:15-25`). Consequences verified by round-trip script:

| Test case | Result |
|---|---|
| Description with embedded double quotes | `_compose_skill_md()` swaps `"` → `'` (`app/routers/skills.py:25`); round-trip **fails** (unbalanced quote in parsed value) |
| Multi-line description (`description: >` block) | `analysis-synthesizer` parsed description is literally `">"` — **1 char**, rubric trigger quality **poor** despite 185-line file |
| Colon in single-line description | Parses correctly |

`analysis-synthesizer` uses YAML folded scalar syntax (`skills/analysis-synthesizer/SKILL.md:3-13`) which the parser cannot read — a high-value synthesis skill is effectively invisible to description-based routing.

#### A6. Smoke-test regression: `sensitivity-analyzer`

Handler at `app/skills/dispatch.py:617-630` calls `compute_sensitivity()` with bridge + savings outputs. On synthetic smoke data it raises:
```
unsupported operand type(s) for +: 'float' and 'NoneType'
```
The catalog integrity test that was designed to catch broken handlers (`tests/test_skill_catalog.py:38-40`) now fails on this skill — evidence the smoke endpoint is valuable but the catalog has an unresolved handler bug.

---

### B. Authoring Pipeline Efficacy — Drafted / UI-Created Skills

#### B1. No name validation on create

`create_skill()` uses `payload.name` directly in the filesystem path (`app/routers/skills.py:92-94`):
```python
skill_dir = ROOT_DIR / "skills" / payload.name
```
No slug regex, no collision rules beyond `skill_path.exists()`, no path-containment check — a name like `../escape` could write outside `skills/`. `SkillCreateRequest` accepts any string (`app/schemas.py:218-220`).

#### B2. No draft lifecycle — immediate production registration

`_compose_skill_md()` hardcodes `status: active` (`app/routers/skills.py:31`). `create_structured_skill()` appends to manifest with `"status": "active"` (`app/routers/skills.py:111-121`), `estimated_tokens: 400`, default `parallel_group: 8`, and `tier: TIER_MAP.get(payload.name, "Other")` — always `"Other"` for new names (`app/routers/skills.py:113`, `app/skills/taxonomy.py` TIER_MAP).

Planner filters non-active skills (`app/opar/plan.py:370-371`), but newly drafted skills skip draft entirely and enter the execution DAG immediately.

#### B3. Discovery index staleness

`create_skill()`, `create_structured_skill()`, and `update_skill()` never call `clear_discovery_index()`. Reindex is manual via `POST /api/skills/reindex` (`app/routers/skills.py:134-141`). New or edited skills are invisible to semantic discovery until someone reindexes.

#### B4. `depends_on` conflated with `inputs`

```python
"depends_on": list(payload.depends_on or payload.inputs),
```
(`app/routers/skills.py:115`)

Data-input names like `spend-profiler` become manifest DAG edges even when they are upstream **data** references, not skill dependencies — creating bogus planner edges for declarative skills.

#### B5. Silent failure masking in declarative runtime and smoke test

`_run_declarative_skill()` catches all exceptions and returns `({}, "provider_unavailable")` (`app/skills/dispatch.py:171-182`). `run_declarative_skill_claude_with_meta()` returns `(None, "provider_disabled")` when `ANTHROPIC_ENABLED` is false (`app/opar/claude_client.py:1442-1443`); on timeout/unparseable JSON returns `(None, "timeout"|"schema_parse_fail")` (`app/opar/claude_client.py:1469-1486`).

`test_skill()` treats any dict output as pass (`app/routers/skills.py:234-237`):
```python
ok = isinstance(output, dict)
return {"status": "pass" if ok else "fail", ...}
```
An empty `{}` with `degraded_reason: "provider_unavailable"` reports **pass** with "0 output field(s)". The test only special-cases `provider_disabled` for declarative skills (`tests/test_skill_catalog.py:48-49`), not `provider_unavailable` or empty output.

**Current state:** Zero skills declare `runtime: declarative` in the catalog — the declarative path is **latent**, not exercised. When consultants begin authoring declarative skills, the false-pass behavior will surface immediately (Anthropic key currently unbilled — deterministic checks only in this evaluation).

#### B6. No output contract enforcement

`output_fields` from `SkillStructuredCreateRequest` are written into SKILL.md prose (`app/routers/skills.py:21`, `app/routers/skills.py:36`) but never validated at runtime. `run_declarative_skill_claude_with_meta()` accepts any JSON dict (`app/opar/claude_client.py:1481-1486`) with 1,200 max tokens and 12s timeout (`app/opar/claude_client.py:1465-1468`) — tight for multi-field analysis skills.

#### B7. `update_skill()` accepts anything

`update_skill()` overwrites SKILL.md with raw content, no parse validation, no version bump (`app/routers/skills.py:81-87`). Can overwrite built-in Python skill documentation with invalid frontmatter; no guard against editing skills with registered handlers.

#### B8. No eval coverage for drafted skills

`eval/` contains 12 domain harnesses but nothing scores drafted-skill quality (trigger description, dependency validity, output conformance, discovery routing accuracy). Catalog tests cover registry↔dispatch alignment and one discovery ranking case (`tests/test_skill_discovery.py:24-27`) — not authoring-path regression.

---

## Scoring Rubric

Each SKILL.md scored 0–6 against six criteria (1 point each unless noted):

| Criterion | Full credit | Partial / none |
|---|---|---|
| **Frontmatter** | YAML block present | Missing → 0 (discovery uses H1 fallback) |
| **Trigger description** | `description` ≥80 chars, parseable | 30–79 chars = 0.5; H1 fallback or broken parse = 0 |
| **Methodology** | Section titled Step-by-Step Workflow, Methodology, What You Do, or Steps | Missing → 0 |
| **Inputs** | `## Inputs` section | Missing → 0 |
| **Outputs** | `## Outputs` or `## Output Contract` section | Missing → 0 |
| **References** | All cited `references/*` files exist on disk | Broken cite → 0 |

**Distribution (40 skills):** min 1.0, max 5.5, avg 3.14 | No frontmatter: 3 | Not in manifest: 3 | Broken refs: 2

### Per-Skill Scorecard

| Skill | Lines | FM | Desc | Trigger | Meth | In | Out | Refs | Exec | Man | Score |
|---|---:|---|---:|---|---|---|---|---|---|---|---:|---:|
| analysis-synthesizer | 185 | Y | 1 | poor | N | N | N | Y | python | Y | 2.0 |
| assumption-register | 76 | Y | 161 | good | N | N | N | Y | python | Y | 3.0 |
| brsr-cobenefit-calculator | 78 | Y | 202 | good | N | N | N | Y | python | Y | 3.0 |
| business-case-builder | 184 | Y | 803 | good | N | N | N | Y | python | Y | 3.0 |
| bva-analyzer | 41 | Y | 535 | good | N | N | Y | Y | python | Y | 3.5 |
| chart-builder | 36 | N | 0 | fallback_h1 | N | Y | N | Y | python | Y | 2.5 |
| cohort-segmenter | 14 | Y | 258 | good | N | N | N | Y | python | Y | 3.0 |
| conflict-detector | 34 | Y | 455 | good | N | N | Y | Y | python | Y | 3.5 |
| consolidation-analyzer | 36 | Y | 422 | good | N | N | Y | Y | python | Y | 3.5 |
| contract-lifecycle-manager | 35 | Y | 401 | good | N | N | Y | Y | python | Y | 3.5 |
| cost-to-serve-analyzer | 35 | Y | 417 | good | N | N | Y | Y | python | Y | 3.5 |
| dashboard-builder | 202 | Y | 743 | good | N | N | N | Y | python | Y | 3.0 |
| data-classifier | 50 | Y | 180 | good | N | N | N | Y | python | **N** | 3.0 |
| data-quality-gate | 22 | Y | 142 | good | N | Y | Y | Y | python | Y | 4.5 |
| data-validator | 149 | Y | 713 | good | N | N | N | Y | python | Y | 3.0 |
| document-contextualizer | 144 | Y | 708 | good | N | N | N | Y | python | Y | 3.0 |
| evidence-gatherer | 32 | Y | 247 | good | Y | Y | Y | Y | python | Y | **5.5** |
| executive-communication | 44 | Y | 300 | good | N | N | N | Y | python | Y | 3.0 |
| export-formatter | 184 | Y | 729 | good | N | N | N | Y | python | Y | 3.0 |
| gstr-reconciler | 34 | Y | 382 | good | N | N | Y | Y | python | Y | 3.5 |
| heuristic-analyzer | 165 | Y | 869 | good | N | N | N | **N** | python | Y | 2.0 |
| indian-tax-optimizer | 84 | Y | 417 | good | Y | N | N | Y | python | Y | 4.0 |
| internal-benchmarker | 124 | Y | 759 | good | N | N | N | Y | python | Y | 3.0 |
| llm-context-builder | 50 | Y | 250 | good | N | N | N | Y | python | **N** | 3.0 |
| msme-compliance-checker | 34 | Y | 422 | good | N | N | Y | Y | python | Y | 3.5 |
| payment-terms-optimizer | 38 | Y | 458 | good | N | N | Y | Y | python | Y | 3.5 |
| peer-benchmarker | 136 | Y | 751 | good | N | N | N | Y | python | Y | 3.0 |
| peer-disclosure-miner | 73 | Y | 217 | good | N | N | N | **N** | python | Y | 2.0 |
| pii-stripper | 55 | Y | 225 | good | N | N | N | Y | python | **N** | 3.0 |
| root-cause-analyzer | 4 | N | 0 | fallback_h1 | N | N | N | Y | python | Y | **1.0** |
| savings-modeler | 4 | N | 0 | fallback_h1 | N | N | N | Y | python | Y | **1.0** |
| scenario-modeler | 69 | Y | 211 | good | N | N | N | Y | python | Y | 3.0 |
| sensitivity-analyzer | 14 | Y | 232 | good | N | N | N | Y | python | Y | 3.0 |
| sme-critique | 23 | Y | 236 | good | N | Y | Y | Y | python | Y | 4.5 |
| spend-profiler | 132 | Y | 638 | good | Y | N | N | Y | python | Y | 4.0 |
| temporal-analyzer | 37 | Y | 443 | good | N | N | Y | Y | python | Y | 3.5 |
| value-bridge-calculator | 155 | Y | 757 | good | N | N | N | Y | python | Y | 3.0 |
| value-to-shareholder-bridge | 63 | Y | 172 | good | N | N | N | Y | python | Y | 3.0 |
| vendor-master-builder | 34 | Y | 427 | good | N | N | Y | Y | python | Y | 3.5 |
| zbb-modeler | 35 | Y | 417 | good | N | N | Y | Y | python | Y | 3.5 |

**Manual spot-check (6 skills):** Best — `evidence-gatherer`, `spend-profiler`, `peer-benchmarker` — confirmed rich triggers and (for evidence-gatherer) methodology aligned to handler. Worst — `savings-modeler`, `root-cause-analyzer`, `heuristic-analyzer` — confirmed stub/ broken-ref issues above. Rubric scores match manual reads.

---

## Catalog Quality vs Authoring Pipeline — Summary

| Dimension | Catalog (stored) | Authoring pipeline (draft) |
|---|---|---|
| **Routing / discovery** | Works for most skills; 3 stubs + 1 broken YAML parse hurt embeddings | New skills not discoverable until manual reindex |
| **Execution** | Python handlers mostly pass smoke test; 1 known failure (`sensitivity-analyzer`) | Declarative path would false-pass on provider failure |
| **Documentation trust** | High variance; agent-instruction prose ≠ Python behavior | Composed SKILL.md inherits quote-mangle + naive parser issues |
| **Manifest integrity** | Drift validator passes; 3 disk skills unmanifested | Creates active manifest entries with guessed tokens/tier |
| **Consultant readiness** | Usable for built-in skills if SME curates SKILL.md | Not safe for self-service authoring without P0 fixes |

---

## Prioritized Improvement Roadmap (Preview)

See `skills_improvement_plan.md` for full workstreams. Headline priorities:

| Priority | Theme | Examples |
|---|---|---|
| **P0** | Trust & safety of authoring | Slug validation, draft→test→activate, fail smoke test on empty output, auto-reindex |
| **P1** | Catalog hygiene | Frontmatter for DAG hubs, fix broken refs, manifest the 3 security skills, align SKILL.md to Python |
| **P2** | Quality gates & evals | skill-lint CI, output schema enforcement, `eval/run_skill_catalog_eval.py` |

---

## Summary Table

| Area | Current State | Gap | Priority |
|---|---|---|---|
| DAG hub SKILL.md (`savings-modeler`, `root-cause-analyzer`) | 4-line stubs, no frontmatter | Poor discovery; consultants can't review methodology | High |
| Doc–implementation alignment | Agent-instruction prose | Misleads discovery and SME review | High |
| Authoring path safety | No slug validation | Path traversal + collision risk | High |
| Draft lifecycle | Immediate `status: active` | Untested skills enter production DAG | High |
| Smoke test false pass | `{}` → pass | Declarative failures invisible | High |
| Frontmatter parser | Naive line split | Breaks `description: >` blocks | Medium |
| Manifest inventory | 3 skills on disk, not in manifest | Security/utility skills orphaned | Medium |
| Reference paths | 2 broken cites | Broken trust in SKILL.md | Medium |
| `sensitivity-analyzer` smoke test | Fails on synthetic data | Handler bug in sensitivity path | Medium |
| Declarative output contract | Not enforced | Authoring UI fields are cosmetic | Medium |
| Drafted-skill eval harness | Missing | No regression for consultant-authored skills | Low |
