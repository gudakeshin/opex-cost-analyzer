# Skills Improvement Plan
**Date:** July 2026 | **Linked to:** `skills_evaluation.md`

Organised into three priority tiers (P0 → P1 → P2). Each item names affected files, concrete changes, effort estimate, and acceptance criteria. **No code changes in this document** — implementation backlog only.

---

## P0 — Trust & Safety of the Authoring Path
*Target: 2–3 days. Blocks consultant self-service authoring until complete.*

---

### P0-A: Slug validation and path containment on skill create

**Why it matters:** `create_skill()` concatenates `payload.name` directly into the filesystem path (`app/routers/skills.py:92-94`) with no validation — path traversal and arbitrary directory names are possible.

**Files:**
```
app/schemas.py                          — SkillCreateRequest, SkillStructuredCreateRequest
app/routers/skills.py                   — create_skill(), create_structured_skill()
tests/test_skill_catalog.py             — new test cases
```

**Changes:**
1. Add Pydantic validator on `name`:
   ```python
   SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
   ```
2. In `create_skill()`, after building `skill_dir`, assert containment:
   ```python
   skill_dir = (ROOT_DIR / "skills" / payload.name).resolve()
   if not str(skill_dir).startswith(str((ROOT_DIR / "skills").resolve())):
       raise HTTPException(400, "Invalid skill name")
   ```
3. Reject reserved names: `_capability_matrix`, `manifest`, `sector-packs`, `references`.

**Effort:** ~2 hours

**Acceptance criteria:**
- `POST /api/v1/skills` with `name: "../escape"` → 400
- `POST /api/v1/skills` with `name: "My Skill!"` → 400
- `POST /api/v1/skills` with `name: "my-custom-analyzer"` → 201, file at `skills/my-custom-analyzer/SKILL.md` only

---

### P0-B: Draft → test → activate lifecycle

**Why it matters:** `create_structured_skill()` writes `status: active` in both SKILL.md (`app/routers/skills.py:31`) and manifest (`app/routers/skills.py:120`), immediately inserting new skills into the production DAG. Planner already skips non-active rows (`app/opar/plan.py:370-371`).

**Files:**
```
app/routers/skills.py                   — _compose_skill_md(), create_structured_skill()
app/skills/manifest.py                  — optional: append_manifest_entry() status default
app/schemas.py                          — SkillActivateRequest (new)
tests/test_skill_catalog.py             — lifecycle tests
```

**Changes:**
1. `_compose_skill_md()`: change `status: active` → `status: draft` (`app/routers/skills.py:31`).
2. `create_structured_skill()`: manifest entry `"status": "draft"` (`app/routers/skills.py:120`).
3. New endpoint `POST /api/v1/skills/{name}/activate`:
   - Requires most recent `test_skill` result with `status: pass`, non-empty `output_keys` (for declarative), and no `degraded_reason` in `{provider_unavailable, timeout, schema_parse_fail}`.
   - Updates SKILL.md frontmatter `status: active` and manifest row.
   - Emits `skill_activated` audit event.
4. UI copy: "Save as draft" / "Run test" / "Activate" — backend-only in this phase is acceptable.

**Effort:** ~1 day

**Acceptance criteria:**
- New structured skill has `status: draft` in SKILL.md and manifest; does **not** appear in OPAR plan tasks.
- After passing smoke test + activate call, skill appears in plan with correct `parallel_group`.
- Activate without prior pass → 409.

---

### P0-C: Make `test_skill` fail on empty output and provider degradation

**Why it matters:** `_run_declarative_skill()` returns `({}, "provider_unavailable")` on any exception (`app/skills/dispatch.py:181-182`). `test_skill()` treats any dict as pass (`app/routers/skills.py:234-237`), so failed LLM calls report success with 0 output keys.

**Files:**
```
app/routers/skills.py                   — test_skill()
tests/test_skill_catalog.py             — extend assertions
```

**Changes:**
```python
# After invoke_skill():
FAIL_DEGRADED = {"provider_unavailable", "timeout", "schema_parse_fail"}
if degraded in FAIL_DEGRADED:
    status = "fail"
elif isinstance(output, dict) and len(output) == 0:
    status = "fail"  # empty dict is not a passing smoke run
elif not isinstance(output, dict):
    status = "fail"
else:
    status = "pass"
```
For declarative skills with `provider_disabled` (pytest / no API key), keep `status: skipped` (`tests/test_skill_catalog.py:48-49`).

**Effort:** ~3 hours

**Acceptance criteria:**
- Mock declarative skill returning `({}, "provider_unavailable")` → `status: fail`, not pass.
- Python skill returning `{}` without exception → `status: fail`.
- Python skill returning `{"findings": [...]}` → `status: pass`.
- Declarative + `provider_disabled` during pytest → `status: skipped` (unchanged).

---

### P0-D: Auto-reindex discovery on create and update

**Why it matters:** Create/update never invalidate the discovery index (`app/routers/skills.py:90-122`, `app/routers/skills.py:81-87`). New skills are invisible to `POST /api/skills/discover` until manual reindex (`app/routers/skills.py:134-141`).

**Files:**
```
app/routers/skills.py                   — create_skill(), update_skill(), create_structured_skill()
app/skills/discovery.py                 — clear_discovery_index() (already exists)
```

**Changes:** Call `clear_discovery_index()` at end of create, structured create, and update (after successful write). Optionally lazy-rebuild on next discover call instead of eager rebuild — either is acceptable if discover latency stays <500ms for 50 skills.

**Effort:** ~1 hour

**Acceptance criteria:**
- Create skill → `discover_relevant_skills("<description keyword>")` returns new skill without manual reindex.
- Update skill description → next discover query reflects new text.

---

### P0-E: Fix `depends_on` vs `inputs` conflation

**Why it matters:** `depends_on=list(payload.depends_on or payload.inputs)` (`app/routers/skills.py:115`) creates bogus DAG edges when data inputs aren't skill names.

**Files:**
```
app/routers/skills.py                   — create_structured_skill()
app/schemas.py                          — document depends_on vs inputs
```

**Changes:**
1. Manifest `depends_on` = `payload.depends_on` only (default `[]`).
2. Validate each dependency ∈ `manifest_skill_names()` ∪ `registered_skills()` at create time; 400 on unknown name.
3. Keep `inputs` in SKILL.md prose only (already written in `_compose_skill_md`, `app/routers/skills.py:20-21`).

**Effort:** ~2 hours

**Acceptance criteria:**
- Structured create with `inputs=["spend-profiler"]`, `depends_on=[]` → manifest `depends_on: []`.
- Structured create with `depends_on=["not-a-skill"]` → 400.

---

## P1 — Catalog Hygiene
*Target: 3–5 days. Improves discovery, SME review, and manifest completeness.*

---

### P1-A: Add frontmatter and methodology to DAG hub stubs

**Why it matters:** `savings-modeler` and `root-cause-analyzer` are 4-line stubs (`skills/savings-modeler/SKILL.md`, `skills/root-cause-analyzer/SKILL.md`) — discovery uses H1 fallback (`app/skills/registry.py:88-89`).

**Files:**
```
skills/savings-modeler/SKILL.md
skills/root-cause-analyzer/SKILL.md
skills/chart-builder/SKILL.md
app/skills/engine/savings.py            — source for savings methodology
app/skills/engine/benchmarking.py       — source for root-cause methodology
app/skills/dispatch.py                  — chart-builder handler for output contract
```

**Changes:** For each stub, add YAML frontmatter with ≥80-char trigger description (mirror style of `evidence-gatherer`, `skills/evidence-gatherer/SKILL.md:1-4`) plus sections:
- **What You Do / Methodology** — describe deterministic Python steps (lever resolution, phasing, NPV for savings; threshold flags, maverick tiers, HHI for root-cause).
- **Inputs** — upstream skill names from manifest `depends_on`.
- **Outputs** — key dict fields returned by handler (e.g. `initiatives`, `root_cause_findings`).

Do **not** copy interactive-agent instructions from peer skills.

**Effort:** ~1 day (content + review)

**Acceptance criteria:**
- Rubric score ≥4.0 for all three skills.
- `discover_relevant_skills("model savings NPV phased initiatives")` ranks `savings-modeler` in top 3.
- `discover_relevant_skills("diagnose why spend is above peers")` ranks `root-cause-analyzer` in top 3.

---

### P1-B: Fix broken reference paths

**Files:**
```
skills/heuristic-analyzer/SKILL.md      — line 32
skills/peer-disclosure-miner/SKILL.md   — line 16
```

**Changes:**
1. `heuristic-analyzer`: replace `heuristic_ranges.json` → `heuristic_targets.json` (file exists at `skills/heuristic-analyzer/references/heuristic_targets.json`).
2. `peer-disclosure-miner`: change prose to cite `skills/sector-packs/<pack>/peer_set.json` pattern, or add a `references/README.md` explaining sector-pack layout.

**Effort:** ~30 minutes

**Acceptance criteria:** Rubric "Refs" column = Y for both skills; skill-lint (P2-A) passes reference resolution.

---

### P1-C: Register or explicitly exclude unmanifested security skills

**Why it matters:** `data-classifier`, `llm-context-builder`, `pii-stripper` have SKILL.md + Python handlers but no manifest row — invisible to DAG planning and token budgeting.

**Files:**
```
skills/manifest.yaml
skills/data-classifier/SKILL.md         — set discoverable: false if internal-only
skills/pii-stripper/SKILL.md
skills/llm-context-builder/SKILL.md
app/skills/manifest.py                  — extend validate_manifest_drift() (optional)
```

**Changes:**
1. Add manifest entries in `parallel_group: 0` (pre-processing) with appropriate `depends_on: []`.
2. Set `discoverable: false` in frontmatter for internal/security skills not meant for consultant discovery.
3. Add `status: active` to `temporal-analyzer` row (`skills/manifest.yaml:160-168`).

**Effort:** ~2 hours

**Acceptance criteria:**
- All 40 SKILL.md skills either in manifest or explicitly marked `discoverable: false` with documented reason.
- `temporal-analyzer` manifest row includes `status: active`.

---

### P1-D: Rewrite drifted SKILL.md bodies to match Python runtime — DONE (2026-07-05)

**Why it matters:** Skills like `spend-profiler` describe user prompts and LLM classification (`skills/spend-profiler/SKILL.md:26-52`) but execute deterministic rules (`app/skills/engine/profiler.py:472-509`, `app/skills/dispatch.py:246-250`).

**Files (priority order) — all five now carry an accurate "Runtime Methodology" section:**
```
skills/spend-profiler/SKILL.md            — added earlier in this pass
skills/dashboard-builder/SKILL.md         — added earlier in this pass
skills/peer-benchmarker/SKILL.md          — added: percentile/CI methodology, notes no peer-group confirmation dialog
skills/document-contextualizer/SKILL.md   — added: single-shot Gemini extraction + keyword fallback (this skill is the one exception that *does* call an LLM, non-interactively)
skills/heuristic-analyzer/SKILL.md        — added: gap calc + headcount overlay, notes graceful degradation instead of blocking on missing metrics
```

**Changes applied:** Each file gained a `## Runtime Methodology (Python...)` section right after the intro, naming the actual dispatcher/engine function (file:line), the real algorithm steps, the emitted dict shape, and an explicit note that the older "ask the user" / step-by-step agent prose below it describes a narrative framing, not code the handler executes. Frontmatter trigger descriptions were left unchanged — they still drive discovery correctly.

**Effort:** ~2 days (spent: ~1.5 hours for the remaining 3 files, done in one pass)

**Acceptance criteria:**
- SME can read SKILL.md and predict handler output structure without reading Python. ✅
- No SKILL.md step is presented as literal runtime behavior unless the handler actually does it — residual "ask the user" prose is now explicitly scoped as narrative/interactive framing, not dispatcher behavior. ✅
- Verified: `pytest tests/test_skill_catalog.py tests/test_skill_manifest.py tests/test_skill_discovery.py tests/test_skill_lint.py tests/test_skill_authoring.py -q` → 21 passed; `python scripts/lint_skills.py` → OK; `python eval/run_skill_catalog_eval.py` → `overall_pass: true`.

---

### P1-E: Fix `sensitivity-analyzer` smoke-test failure

**Why it matters:** Current catalog test failure — `unsupported operand type(s) for +: 'float' and 'NoneType'` when smoke-running `sensitivity-analyzer` (`app/skills/dispatch.py:617-630` → `app/services/sensitivity.py`).

**Files:**
```
app/services/sensitivity.py             — null-safe arithmetic
app/skills/dispatch.py                  — ensure smoke context seeds required bridge fields
app/routers/skills.py                   — _smoke_context() pre-seed chain
tests/test_skill_catalog.py             — should pass without skip
```

**Changes:** Diagnose None propagation in `compute_sensitivity()` when savings model lacks expected numeric fields on synthetic data; add defensives or ensure `_smoke_context()` seeds complete bridge + savings shapes.

**Effort:** ~4 hours

**Acceptance criteria:**
```
pytest tests/test_skill_catalog.py::test_test_skill_endpoint_smoke_runs_every_skill -q
# → pass (0 failures)
```

---

## P2 — Quality Gates & Evals
*Target: 4–6 days. Prevents regression as catalog grows.*

---

### P2-A: Skill-lint CI check

**Files:**
```
scripts/lint_skills.py                  — new
tests/test_skill_lint.py                — new
.github/workflows/ or existing CI       — add step
app/skills/registry.py                  — replace _parse_frontmatter with yaml.safe_load
```

**Checks:**
1. Frontmatter parses via `yaml.safe_load` (fixes `description: >` blocks — `skills/analysis-synthesizer/SKILL.md:3-13`).
2. Required keys: `name`, `description` (≥30 chars), `runtime`, `status`.
3. All `references/*` paths cited in SKILL.md resolve on disk.
4. Manifest `depends_on` ⊆ known skill names.
5. On-disk skills with `discoverable: true` appear in manifest (or explicit waiver list).
6. No stub skills (≤10 lines, no frontmatter) in manifest `_DEP_MAP` hubs: `savings-modeler`, `root-cause-analyzer`.

**Effort:** ~1.5 days

**Acceptance criteria:**
- `python scripts/lint_skills.py` exits 0 on main branch after P1 fixes.
- `analysis-synthesizer` description parses to full text, not `">"`.

---

### P2-B: Replace naive frontmatter parser with YAML library

**Why it matters:** `_parse_frontmatter()` line splitter (`app/skills/registry.py:15-25`) breaks multi-line descriptions and mishandles quotes with `_compose_skill_md()` (`app/routers/skills.py:25`).

**Files:**
```
app/skills/registry.py                  — _parse_frontmatter()
app/routers/skills.py                   — _compose_skill_md() use yaml.dump for frontmatter
tests/test_skill_discovery.py           — add round-trip tests
```

**Changes:**
1. Parse frontmatter with `yaml.safe_load`.
2. Compose with `yaml.dump` for frontmatter block (preserve multiline descriptions via `|` or `>`).
3. Round-trip tests for quotes, colons, multiline.

**Effort:** ~1 day

**Acceptance criteria:**
- Round-trip script: all three test cases in evaluation (quotes, colons, multiline) pass.
- `analysis-synthesizer` `description` length >200 after parse.

---

### P2-C: Enforce `output_fields` in declarative runtime

**Files:**
```
app/opar/claude_client.py               — run_declarative_skill_claude_with_meta() :1433
app/skills/dispatch.py                  — _run_declarative_skill() :147
app/skills/registry.py                  — extract output_fields from SKILL.md
app/skills/contracts.py                 — optional JSON schema builder
```

**Changes:**
1. Parse `## Outputs` / declared `output_fields` into required key list.
2. After `_extract_json()`, validate all required keys present and types coarse-match (string/number/list/dict).
3. Return `(None, "schema_parse_fail")` on mismatch — same degradation path as malformed JSON (`app/opar/claude_client.py:1481-1486`).
4. Increase `max_tokens` to 2400 and timeout to 30s for declarative skills with >5 output fields.

**Effort:** ~1.5 days

**Acceptance criteria:**
- Declarative skill declaring `output_fields: [summary, confidence]` rejects `{"summary": "ok"}` (missing confidence).
- Valid full response → pass smoke test.

---

### P2-D: Drafted-skill eval harness (no live LLM)

**Files:**
```
eval/run_skill_catalog_eval.py          — new
eval/_fixtures_skill_catalog.py         — new
tests/eval/golden/skill_catalog/        — golden cases
```

**Scenarios (deterministic fixtures only):**
1. **Discovery routing:** 20 queries → expected top-3 skill names; score MRR@3.
2. **Dependency validity:** all manifest `depends_on` edges resolve; no cycles outside allowed groups.
3. **Frontmatter quality:** rubric score ≥3.0 for all manifest skills.
4. **Declarative output conformance:** mock `run_declarative_skill_claude_with_meta` with fixture JSON; verify schema enforcement (P2-C).
5. **Authoring round-trip:** `_compose_skill_md` → parse → lint passes.

**Effort:** ~2 days

**Acceptance criteria:**
- `python eval/run_skill_catalog_eval.py` produces `eval/skill_catalog_report.md` with scores.
- CI runs harness on PRs touching `skills/` or `app/skills/`.
- No live Anthropic/Gemini calls (mock LLM client).

---

### P2-E: Guard `update_skill` for built-in Python skills

**Files:**
```
app/routers/skills.py                   — update_skill()
```

**Changes:**
1. Parse incoming content; reject if frontmatter fails YAML parse.
2. If skill ∈ `registered_skills()` and runtime ≠ declarative, require `content` to retain valid frontmatter with `runtime: python` (prevent accidental conversion to declarative doc-only).
3. Bump `version` patch in frontmatter on successful update.

**Effort:** ~3 hours

**Acceptance criteria:**
- `update_skill("spend-profiler", content="broken")` → 400.
- Valid edit increments version `0.1.0` → `0.1.1`.

---

## Regression Test Additions

Add to `tests/test_skill_catalog.py`:

```python
def test_create_skill_rejects_invalid_slug(client):
    assert client.post("/api/v1/skills", json={"name": "../x", "content": "---\n..."}).status_code == 400

def test_structured_skill_starts_as_draft(client):
    # after P0-B
    body = client.post("/api/v1/skills/structured", json={...}).json()
    meta = parse_skill_md(ROOT_DIR / "skills" / body["name"] / "SKILL.md")
    assert meta["status"] == "draft"

def test_compose_frontmatter_roundtrip():
    # after P2-B
    ...
```

Extend `validate_manifest_drift()` (`app/skills/manifest.py:52`) optionally:

```python
for path in SKILLS_DIR.glob("*/SKILL.md"):
    name = path.parent.name
    if name not in manifest_names and parse_skill_md(path).get("discoverable", True):
        errors.append(f"discoverable skill not in manifest: {name}")
```

---

## Summary

| Priority | Items | Effort | Risk |
|---|---|---|---|
| **P0** Trust & safety | P0-A through P0-E | 2–3 days | Low — isolated router/schema changes |
| **P1** Catalog hygiene | P1-A through P1-E | 3–5 days | Low — mostly content + one bugfix |
| **P2** Quality gates | P2-A through P2-E | 4–6 days | Low — additive CI/eval |

**Recommended sequence:** P0-A → P0-C → P0-B → P0-D → P0-E → P1-E (unblock CI) → P1-A → P1-B → P1-C → P2-B → P2-A → P1-D → P2-C → P2-D → P2-E.

Start with **P0-A + P0-C** because they close security and false-pass holes in a single PR. **P1-E** should land early to restore green `test_skill_catalog` before content-heavy P1-A/P1-D work proceeds in parallel.
