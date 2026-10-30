# Skills Improvement Plan
**Date:** July 2026 (updated 2026-07-05 post-remediation) | **Linked to:** `skills_evaluation.md`

> **Status:** All P0 items, all P1 items, and all P2 items in the original plan were implemented in commit `884c1c3` ("Harden the skill authoring/catalog pipeline and fix doc-implementation drift"), verified 2026-07-05: 21/21 skill tests pass, `scripts/lint_skills.py` OK, `eval/run_skill_catalog_eval.py` overall_pass with zero manifest drift. This document is now a **completion ledger** plus the remaining open backlog (section R).

---

## P0 — Trust & Safety of the Authoring Path ✅ COMPLETE

### P0-A: Slug validation and path containment on skill create — ✅ DONE

Implemented in `app/skills/validation.py`: `validate_skill_slug_http()` enforces the slug regex and `resolve_skill_md_path()` guarantees path containment under `skills/`. Every skill endpoint in `app/routers/skills.py` (get, update, create, test, activate) validates before touching the filesystem.

**Acceptance verified:** invalid slugs and traversal names rejected with 400; covered by `tests/test_skill_authoring.py`.

### P0-B: Draft → test → activate lifecycle — ✅ DONE

- `_compose_skill_md()` writes `status: draft` (`app/routers/skills.py:49`).
- `create_structured_skill()` appends a `status: draft` manifest row (`app/routers/skills.py:179`).
- `POST /api/v1/skills/{name}/activate` (`app/routers/skills.py:312-363`) runs the smoke test, returns **409** unless it passes, then flips SKILL.md frontmatter and the manifest row to `active` and emits a `skill_activated` audit event.

**Acceptance verified:** draft skills stay out of the OPAR plan (planner skips non-active rows); activation without a passing test → 409; covered by `tests/test_skill_authoring.py`.

### P0-C: Fail-closed smoke test — ✅ DONE

`_evaluate_smoke_result()` (`app/routers/skills.py:73-89`) fails on: degraded reason ∈ `FAIL_DEGRADED_REASONS` (`provider_unavailable`, `timeout`, `schema_parse_fail` — `app/skills/validation.py`), non-dict output, or empty output dict. `provider_disabled` (no API key, e.g. under pytest) reports **skipped**, never pass.

**Acceptance verified:** empty `{}` with `provider_unavailable` → fail; Python skill returning populated dict → pass; declarative + `provider_disabled` → skipped.

### P0-D: Auto-reindex discovery on create/update — ✅ DONE

`_invalidate_discovery_index()` is called at the end of `create_skill`, `create_structured_skill` (via `create_skill`), `update_skill`, and `activate_skill` (`app/routers/skills.py:32-35, 143, 157, 361`). Manual `POST /api/skills/reindex` remains available but is no longer required.

### P0-E: `depends_on` / `inputs` conflation — ✅ DONE

`create_structured_skill()` uses `validate_depends_on(payload.depends_on)` only (`app/routers/skills.py:167`) — each dependency must be a known skill name (400 otherwise); `inputs` appear in SKILL.md prose only.

---

## P1 — Catalog Hygiene ✅ COMPLETE

### P1-A: Frontmatter and methodology for DAG hub stubs — ✅ DONE

`savings-modeler` (38 lines), `root-cause-analyzer` (36 lines), and `chart-builder` (41 lines) now have full YAML frontmatter with 300+ char trigger descriptions plus Inputs / Outputs / Methodology sections sourced from their engine implementations (`app/skills/engine/savings.py`, `app/skills/engine/benchmarking.py`), each ending with an explicit implementation pointer.

**Acceptance verified:** catalog eval discovery cases rank `savings-modeler` #1 for "model savings NPV phased initiatives cost to achieve" and `root-cause-analyzer` #1 for "diagnose why spend is above peers root cause" (`eval/skill_catalog_report.md`, MRR@3 = 1.0).

### P1-B: Broken reference paths — ✅ DONE

- `heuristic-analyzer/SKILL.md` cites `references/heuristic_targets.json` (lines 16, 43); file exists.
- `peer-disclosure-miner/SKILL.md:16` cites the real `skills/sector-packs/<pack_id>/peer_set.json` pattern.
- skill-lint enforces reference resolution going forward.

### P1-C: Register unmanifested skills; complete manifest rows — ✅ DONE

`data-classifier`, `llm-context-builder`, and `pii-stripper` are in the manifest (40 entries total, matching the 40 SKILL.md dirs on disk). `temporal-analyzer` row carries `status: active` (`skills/manifest.yaml:189-198`). `validate_manifest_drift()` was extended to flag any discoverable on-disk skill missing from the manifest (`app/skills/manifest.py:112-116`).

### P1-D: Rewrite drifted SKILL.md bodies — ✅ DONE

`spend-profiler`, `dashboard-builder`, `peer-benchmarker`, `document-contextualizer`, and `heuristic-analyzer` each carry a `## Runtime Methodology (Python…)` section naming the actual dispatcher/engine function (file:line), the real algorithm steps, and the emitted dict shape. Residual "ask the user" prose is explicitly scoped as narrative framing, not dispatcher behavior. Frontmatter trigger descriptions were left unchanged — they drive discovery correctly.

### P1-E: `sensitivity-analyzer` smoke-test failure — ✅ DONE

Null-safe arithmetic in `app/services/sensitivity.py` fixed the `float + NoneType` crash. `tests/test_skill_catalog.py` smoke-runs every skill and passes (part of the 21-test green run, re-verified 2026-07-05).

---

## P2 — Quality Gates & Evals ✅ COMPLETE

### P2-A: Skill-lint CI check — ✅ DONE

`scripts/lint_skills.py` validates frontmatter schema (via yaml lib), required keys, description length, reference-file resolution, and `depends_on ⊆` known skills. Wired into CI (`.github/workflows/ci.yml:69-70`); guarded by `tests/test_skill_lint.py`. Current run: `skill-lint: OK`.

### P2-B: YAML frontmatter parsing — ✅ DONE

`app/skills/registry.py` parses frontmatter with `yaml.safe_load` and composes with `yaml.dump` (lines 8, 28, 38). The `analysis-synthesizer` folded-scalar description that previously parsed as `">"` (1 char) now parses to its full 781 characters. Round-trip (quotes, colons, multiline) covered in `tests/test_skill_authoring.py`.

### P2-C: `output_fields` enforcement in declarative runtime — ✅ DONE

`run_declarative_skill_claude_with_meta()` takes `output_fields` and treats them as required keys (`app/opar/claude_client.py:1443-1448`); `_run_declarative_skill()` passes the declared fields and validates the result via `validate_declarative_output()`, degrading to `schema_parse_fail` on mismatch (`app/skills/dispatch.py:180-186`). Combined with P0-C, a schema failure fails the smoke test rather than silently passing.

### P2-D: Drafted-skill eval harness (no live LLM) — ✅ DONE

`eval/run_skill_catalog_eval.py` scores, deterministically:
1. **Discovery routing** — query → expected-skill cases, MRR@3 (currently 1.0 on 4 cases).
2. **Rubric** — per-skill 0–5 quality score with a 3.0 threshold.
3. **Manifest drift** — `validate_manifest_drift()` must return empty.
4. **Declarative schema conformance** — mocked LLM fixtures, no live calls.

Outputs `eval/skill_catalog_report.md` + `eval/skill_catalog_scores.json`; runs in CI (`.github/workflows/ci.yml:72-73`).

### P2-E: Guard `update_skill` — ✅ DONE

`update_skill()` validates content via `validate_skill_md_content()` (400 on invalid frontmatter), requires registered Python skills to retain `runtime: python`, and auto-bumps the patch version on success (`app/routers/skills.py:120-145`).

---

## R — Remaining Open Backlog

The safety and infrastructure work is done. What remains is content depth and eval breadth:

### R1: Rubric uplift for the 23 below-threshold skills — **OPEN, Medium priority**

Current catalog eval: average **2.62/5**, with 23 skills under the 3.0 threshold (list in `eval/skill_catalog_report.md`). The misses are structural — no `## Inputs` / `## Outputs` headings or no recognized methodology section — not routing or execution defects.

**Approach:** batch-edit each below-threshold SKILL.md to add the three structured sections, sourcing content from the corresponding handler in `app/skills/dispatch.py` / `app/skills/engine/` (same pattern used for the P1-A hub rewrites). Highest value first: `analysis-synthesizer`, `spend-profiler`, `peer-benchmarker`, `value-bridge-calculator`, `dashboard-builder` (heaviest DAG traffic).

**Effort:** ~2 days for all 23. **Acceptance:** `eval/run_skill_catalog_eval.py` rubric average ≥3.5, `below_threshold` empty.

### R2: Live declarative-skill validation — **BLOCKED (API billing)**

Schema enforcement (P2-C) is verified with mocked fixtures only; zero production skills declare `runtime: declarative`, and the Anthropic key currently has no credits. Once billing is restored: author one real declarative skill through the UI path, run draft→test→activate end-to-end, and confirm `schema_parse_fail` surfaces on a deliberately malformed prompt.

**Effort:** ~2 hours once unblocked.

### R3: Broaden discovery-routing eval — **OPEN, Low priority**

The harness has 4 routing cases (all passing). The original target was ~20 queries covering every tier, including negative cases (queries that should *not* route to a given skill).

**Effort:** ~half a day. **Acceptance:** ≥20 cases, MRR@3 ≥0.85, wired into the existing CI step.

### R4: Full rewrite of residual narrative prose — **OPEN, Low priority**

P1-D scoped the interactive-agent prose as non-runtime framing rather than deleting it. A cleaner end state removes it entirely so SKILL.md bodies contain only accurate runtime documentation. Fold into R1 batch edits where convenient.

---

## Summary

| Tier | Items | Status |
|---|---|---|
| **P0** Trust & safety | P0-A … P0-E | ✅ All done (`884c1c3`) |
| **P1** Catalog hygiene | P1-A … P1-E | ✅ All done (`884c1c3`) |
| **P2** Quality gates | P2-A … P2-E | ✅ All done (`884c1c3`) |
| **R** Remaining | R1 rubric uplift, R2 live declarative (blocked), R3 eval breadth, R4 prose cleanup | Open |

**Verification snapshot (2026-07-05):** `pytest tests/test_skill_catalog.py tests/test_skill_manifest.py tests/test_skill_discovery.py tests/test_skill_authoring.py tests/test_skill_lint.py -q` → **21 passed** · `python scripts/lint_skills.py` → **OK** · `python eval/run_skill_catalog_eval.py` → **overall_pass: true**, manifest drift **[]**, discovery MRR@3 **1.0**.
