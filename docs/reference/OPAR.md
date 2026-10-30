# OpEx Intelligence Platform
## Observe → Plan → Act → Reflect: Agentic Loop Implementation Specification

**Author:** Pallav Chaturvedi | **Version:** 1.0 | **Date:** March 2026

---

## 0. Architecture Overview

The OpEx Intelligence Platform is structured as an explicit four-phase agentic loop. Unlike a standard chat application where each message is a stateless request-response, every user interaction triggers a full **Observe → Plan → Act → Reflect (OPAR)** cycle. The FastAPI orchestrator owns and enforces this loop — it is not left to the model to organise implicitly.

The loop is re-entrant: each cycle's Reflect output can trigger the next Observe, making multi-turn analysis sessions a sequence of complete OPAR iterations that progressively build toward the final deliverable.

| Phase | Owner | Primary Input | Primary Output | Mem0 Interaction |
|-------|-------|--------------|----------------|-----------------|
| OBSERVE | Orchestrator + Mem0 | User message, uploaded files, session state | ObserveContext object | READ: user_memory, session_memory, agent_memory |
| PLAN | Claude (reasoning) | ObserveContext | ExecutionPlan + user-visible summary | READ: agent_memory for skill calibration |
| ACT | Skills Engine | ExecutionPlan + ObserveContext | ActResult (raw skill outputs) | WRITE: session_memory (intermediate results) |
| REFLECT | Orchestrator + Claude | ActResult + ExecutionPlan | ReflectOutput (validated, scored) | WRITE: user_memory, agent_memory |

---

## Phase 1: OBSERVE
> *What do we know? What do we have? What is the user trying to accomplish?*

### Purpose

The Observe phase assembles a complete, enriched context object before Claude or any skill is invoked. Its job is to answer three questions with high fidelity:
1. What did the user just say or upload?
2. What does the system already know about this user, their company, and their prior analyses?
3. Is the available data sufficient to proceed, or should the system pause and ask for clarification?

### Inputs

- Incoming user message (text)
- File references attached to this turn (IDs pointing to S3 objects uploaded in this session)
- Current session state from PostgreSQL: which skills have already run, what files are loaded
- Mem0 user memory: company profile, industry, spend taxonomy preferences, prior analysis summaries
- Mem0 session memory: intermediate results and corrections from earlier turns in this session
- Mem0 agent memory: skill-specific calibration data (e.g., custom benchmark tables per industry)

### The ObserveContext Data Structure

```python
@dataclass
class ObserveContext:
    # User intent
    user_message:      str
    intent_class:      str          # 'upload_data' | 'benchmark' | 'value_bridge' | 'business_case'
    explicit_category: str | None   # e.g. 'IT & Technology' if user specified

    # Data availability
    uploaded_file_ids:       list[str]    # S3 keys of files available this session
    spend_profile_ready:     bool         # True if spend-profiler has already run
    benchmark_results_ready: bool

    # Memory — pre-fetched before planning
    user_memory:    list[dict]      # from mem0.get_all(user_id)
    session_memory: list[dict]      # from mem0.search(session_id=session_id)
    agent_memories: dict[str, list] # {skill_name: [memories]}

    # Data quality signals
    file_parse_status:      dict[str, str]  # {file_id: 'ok'|'partial'|'failed'}
    missing_fields:         list[str]       # e.g. ['headcount', 'revenue']
    data_quality_score:     float           # 0.0 – 1.0 composite
    clarification_required: bool
    clarification_prompt:   str | None
```

### Orchestrator Logic

```python
async def observe(msg: str, session_id: str, user_id: str,
                  file_ids: list[str]) -> ObserveContext:

    # 1. Classify intent via lightweight Claude call (low token cost)
    intent = await classify_intent(msg)

    # 2. Retrieve all three memory scopes in parallel
    user_mem, session_mem, agent_mems = await asyncio.gather(
        mem0.get_all(user_id=user_id),
        mem0.search(query=msg, session_id=session_id, limit=10),
        fetch_agent_memories(intent)   # only skills relevant to this intent
    )

    # 3. Parse any newly uploaded files (async, parallel per file)
    parse_results = await asyncio.gather(
        *[parse_file(fid) for fid in file_ids]
    )

    # 4. Assess data quality and flag missing fields
    dq_score, missing = assess_data_quality(parse_results, intent)
    clarify = dq_score < 0.6 or len(missing) > 0

    return ObserveContext(
        user_message=msg, intent_class=intent,
        user_memory=user_mem, session_memory=session_mem, agent_memories=agent_mems,
        data_quality_score=dq_score, missing_fields=missing,
        clarification_required=clarify, ...
    )
```

### Mem0 Calls in Observe

| Call | Mem0 API | Purpose |
|------|----------|---------|
| Load full user profile | `mem0.get_all(user_id)` | Inject company name, industry, prior spend summary, custom taxonomy overrides into context |
| Retrieve session state | `mem0.search(query, session_id=session_id)` | Find intermediate results from earlier turns in this session |
| Load skill calibration | `mem0.search(query, agent_id=skill_name)` | Pull custom benchmark tables or learned heuristic thresholds the skill has built up over prior runs |

### Observe Output: What Goes to Plan

The ObserveContext is the single input to the Plan phase. If `clarification_required` is `True`, the orchestrator short-circuits: it skips Plan and Act entirely, presents the `clarification_prompt` to the user, and waits. No LLM call for planning, no skill invocation, no wasted compute.

---

## Phase 2: PLAN
> *What should we do, in what order, with what data?*

### Purpose

The Plan phase takes the ObserveContext and produces a deterministic execution blueprint: which skills run, in what order or in parallel, with what inputs, and what the expected output schema is for each. The plan is surfaced to the user as a brief summary before any skill executes — giving them the opportunity to steer or stop before compute is spent.

### The ExecutionPlan Data Structure

```python
@dataclass
class SkillTask:
    skill_name:       str
    inputs:           dict          # resolved inputs for this skill invocation
    depends_on:       list[str]     # skill_names that must complete first
    parallel_group:   int           # tasks with same group_id run concurrently
    expected_schema:  dict          # JSON schema for output validation in Reflect
    estimated_tokens: int

@dataclass
class ExecutionPlan:
    tasks:              list[SkillTask]
    total_skills:       int
    parallel_groups:    int
    user_summary:       str        # 1–3 sentence plain English explanation for the user
    estimated_duration: str        # e.g. '45–90 seconds'
    requires_approval:  bool       # True for business case generation or exports
```

### Planning Logic: Skill DAG Construction

The orchestrator sends the ObserveContext to Claude with a planning system prompt. Claude returns a structured skill invocation list. The orchestrator validates it against the skill registry, resolves dependencies, assigns parallel groups, and locks the plan.

```python
PLANNING_SYSTEM_PROMPT = """
You are the planning agent for OpEx Intelligence Platform.
Given the context below, output a JSON array of skill invocations.
Skills available: spend-profiler, peer-benchmarker, internal-benchmarker,
                  heuristic-analyzer, value-bridge-calculator, business-case-builder

Rules:
- spend-profiler must run before any benchmarker skill
- peer-benchmarker and internal-benchmarker can run in parallel (same parallel_group)
- value-bridge-calculator requires all benchmarker outputs
- business-case-builder requires value-bridge-calculator output
- If headcount/revenue data is missing, exclude heuristic-analyzer
- For each category explicitly requested, create one benchmarker invocation

Output ONLY valid JSON. No prose."""
```

### Skill Dependency Map

| Skill | Depends On | Can Run In Parallel With | Typical Trigger |
|-------|-----------|--------------------------|-----------------|
| spend-profiler | — | Nothing (always first) | Any new file upload |
| peer-benchmarker | spend-profiler | internal-benchmarker, heuristic-analyzer | User requests peer comparison |
| internal-benchmarker | spend-profiler | peer-benchmarker, heuristic-analyzer | User requests BU/geo comparison |
| heuristic-analyzer | spend-profiler + headcount/revenue data | peer-benchmarker, internal-benchmarker | User requests outcomes-per-dollar analysis |
| value-bridge-calculator | All benchmarker outputs | Nothing | User requests value-at-the-table view |
| business-case-builder | value-bridge-calculator | Nothing | User requests business case for a category |

### What the User Sees

Before execution begins, the orchestrator streams the `user_summary` to the chat interface:

> *"I'll run peer benchmarking and internal benchmarking for your IT & Technology and Professional Services spend categories in parallel (2 skills, ~60 seconds). Then I'll aggregate the results into a value-at-the-table matrix. Ready to proceed?"*

---

## Phase 3: ACT
> *Execute the plan. Invoke skills. Capture results.*

### Purpose

The Act phase executes the ExecutionPlan produced by Plan. It dispatches skills in the correct order, honouring dependency constraints and maximising parallelism within each group. Intermediate results are written to Mem0 session memory after each skill completes, enabling recovery if a later skill fails. Progress is streamed to the user throughout.

### Execution Engine

```python
async def act(plan: ExecutionPlan, ctx: ObserveContext) -> ActResult:
    results: dict[str, SkillOutput] = {}
    errors:  dict[str, str] = {}

    # Group tasks by parallel_group, execute groups sequentially
    for group_id in sorted(set(t.parallel_group for t in plan.tasks)):
        group_tasks = [t for t in plan.tasks if t.parallel_group == group_id]

        # Within a group: fan out all skill invocations concurrently
        group_results = await asyncio.gather(
            *[invoke_skill(task, results, ctx) for task in group_tasks],
            return_exceptions=True
        )

        for task, result in zip(group_tasks, group_results):
            if isinstance(result, Exception):
                errors[task.skill_name] = str(result)
            else:
                results[task.skill_name] = result
                # Write intermediate result to session memory immediately
                await mem0.add(
                    messages=[{'role': 'system', 'content': result.summary}],
                    session_id=ctx.session_id,
                    metadata={'skill': task.skill_name, 'turn': ctx.turn_id}
                )
                yield ProgressEvent(skill=task.skill_name, status='complete')

    return ActResult(skill_outputs=results, errors=errors, duration_ms=elapsed())
```

### Skill Invocation Pattern

Each skill is loaded via the Claude Agent Skills `container` parameter in the Messages API call. The skill's SKILL.md, reference data, and scripts are bundled into the container. Claude executes within the sandbox, producing structured JSON output plus a narrative explanation.

```python
async def invoke_skill(task: SkillTask, prior_results: dict,
                       ctx: ObserveContext) -> SkillOutput:

    # Resolve inputs: merge task inputs with outputs from dependency skills
    resolved_inputs = {**task.inputs}
    for dep in task.depends_on:
        resolved_inputs[dep + '_output'] = prior_results[dep].data

    # Inject memory context for this skill
    agent_memory = ctx.agent_memories.get(task.skill_name, [])

    response = await anthropic.messages.create(
        model='claude-sonnet-4-5-20250929',
        max_tokens=4096,
        container={ 'skill': task.skill_name },   # loads SKILL.md + scripts + ref data
        messages=[{
            'role': 'user',
            'content': build_skill_prompt(task, resolved_inputs, agent_memory, ctx)
        }],
        stream=True
    )

    return parse_skill_output(response, task.expected_schema)
```

### Parallel Execution: Concrete Example

For a request to benchmark IT & Technology and Professional Services across both peer and internal dimensions:

| Group | Skills Running in Parallel | Wait For |
|-------|---------------------------|----------|
| Group 0 | spend-profiler (IT & Tech), spend-profiler (Prof. Services) | Nothing — runs first |
| Group 1 | peer-benchmarker (IT & Tech), peer-benchmarker (Prof. Services), internal-benchmarker (IT & Tech), internal-benchmarker (Prof. Services) | Group 0 complete |
| Group 2 | value-bridge-calculator | All of Group 1 complete |

### Error Handling in Act

- **Partial failure:** if one skill in a parallel group fails, the others complete. The orchestrator notes the error and proceeds to Reflect with partial results.
- **Dependency failure:** if a skill that others depend on fails, all downstream skills are marked as blocked and not invoked. The user is informed with a specific error message.
- **Output schema mismatch:** if a skill returns output that doesn't conform to `expected_schema`, it's flagged as a soft failure and passed to Reflect for assessment rather than silently discarded.

---

## Phase 4: REFLECT
> *Is the output credible? What should we remember? What comes next?*

### Purpose

Reflect is where the system exercises analytical judgment on its own outputs. It validates raw skill outputs against expected schemas, applies the domain-specific confidence scoring and de-duplication logic defined in the Value Lever Framework, persists validated facts to Mem0, and determines whether to surface results to the user or trigger another loop iteration.

This phase is what separates a production-grade finance platform from a wrapper around a chat API. The confidence scoring here is not cosmetic — it's the mechanism by which the platform earns credibility with CFOs and CPOs.

### The ReflectOutput Data Structure

```python
@dataclass
class ConfidenceScore:
    level:     Literal['low', 'mid', 'high']  # 0.5 | 0.75 | 0.9
    factor:    float
    rationale: str   # e.g. 'Benchmark covers 7/10 categories; headcount data absent'

@dataclass
class ReflectOutput:
    validated_outputs:    dict[str, SkillOutput]      # skills that passed validation
    failed_validations:   dict[str, str]               # skill -> reason
    confidence_scores:    dict[str, ConfidenceScore]   # per skill output
    value_bridge_matrix:  DataFrame | None             # populated if value-bridge ran
    dedup_factor:         float                        # 0.6–0.8 applied to avoid lever overlap

    # Memory instructions
    user_memory_updates:  list[MemoryUpdate]
    agent_memory_updates: dict[str, list[MemoryUpdate]]

    # Loop control
    loop_complete:        bool
    next_loop_trigger:    str | None  # clarification or follow-on prompt if not complete

    # User-facing output
    response_text:        str
    response_artefacts:   list[str]   # file paths: .xlsx, .docx, charts
```

### Validation Logic

Each skill output is validated in three layers:

**Layer 1 — Schema Validation**
- Output JSON validated against the skill's `expected_schema` (defined in the ExecutionPlan)
- Checks for required fields, numeric ranges (savings % must be 0–100), non-null categories
- Failures here are **hard failures**: the skill result is excluded from downstream aggregation

**Layer 2 — Analytical Coherence Check**
- Cross-skill consistency: peer benchmark savings cannot exceed total addressable spend
- Internal benchmark: best-practice BU spend must be ≤ current BU spend
- Heuristic ratios: cost-per-employee must fall within plausible human ranges
- Failures here are **soft flags**: result is included with a low confidence score

**Layer 3 — Confidence Scoring (domain-specific)**
- Applied to each category × lever cell in the value bridge
- **High (0.9):** benchmark data directly matches industry vertical, all required fields present, >1,000 data points
- **Mid (0.75):** benchmark is proxy industry or adjacent vertical, most fields present
- **Low (0.5):** benchmark is cross-industry average, key fields missing, data quality score < 0.6

### Value Bridge Assembly and De-duplication

```python
def assemble_value_bridge(reflect_out: ReflectOutput,
                          categories: list[str]) -> DataFrame:
    rows = []
    for category in categories:
        for lever in ['peer', 'internal', 'heuristic', 'ai_automation']:
            raw_savings  = get_lever_savings(category, lever, reflect_out)
            addressable  = get_addressable_spend(category)
            confidence   = reflect_out.confidence_scores[f'{category}_{lever}'].factor

            savings = addressable * raw_savings * confidence
            rows.append({
                'category':     category,
                'lever':        lever,
                'savings_low':  savings * 0.5,
                'savings_mid':  savings * 0.75,
                'savings_high': savings * 0.9,
            })

    df = pd.DataFrame(rows)

    # De-duplication: levers often target the same addressable pool.
    # Apply a factor of 0.6–0.8 to total to avoid double-counting.
    dedup = compute_dedup_factor(df)   # based on lever overlap analysis
    df['savings_mid_dedup'] = df['savings_mid'] * dedup

    return df
```

### Memory Persistence in Reflect

Only validated, de-duplicated results are written to persistent memory. Raw intermediate outputs stay in session memory only.

| What | Written To | Mem0 Scope | Lifecycle |
|------|-----------|------------|-----------|
| Confirmed spend taxonomy (user-corrected mappings) | User memory | `user_id` | Permanent — reused in all future sessions |
| Value-at-the-table summary per category | User memory | `user_id` | Permanent — injected into next session Observe |
| Industry vertical confirmed for this company | User memory | `user_id` | Permanent — used by benchmarker skills automatically |
| Intermediate benchmarker output for this session | Session memory | `session_id` | 24h — available for value-bridge in later turns |
| Custom benchmark thresholds validated against user data | Agent memory | `agent_id = skill_name` | Permanent — skill gets better over time |

### Loop Control: When Does the Loop Continue?

```python
def determine_loop_control(reflect_out: ReflectOutput) -> tuple[bool, str | None]:

    # Case 1: Hard failure — critical skill failed, can't proceed
    if 'spend-profiler' in reflect_out.failed_validations:
        return False, 'Spend classification failed. Please review the uploaded file format.'

    # Case 2: Soft failure — missing data discovered during execution
    if reflect_out.missing_fields and reflect_out.confidence_scores_all_low():
        clarify = f'To improve confidence, please provide: {reflect_out.missing_fields}'
        return True, clarify   # triggers next OPAR loop with clarification prompt

    # Case 3: Natural continuation — benchmarking done, suggest next step
    if reflect_out.benchmarks_complete and not reflect_out.value_bridge_complete:
        return True, 'Benchmarking complete. Shall I calculate the value-at-the-table matrix?'

    # Case 4: Complete — surface final results
    return False, None
```

---

## 5. Multi-Turn Session: OPAR Loop in Action

A complete example showing how the four loops chain across a real analysis session for a manufacturing company's IT and Professional Services spend.

### Turn 1: File Upload

| Phase | What Happens |
|-------|-------------|
| **OBSERVE** | No prior user_memory (new company). File parse: 3 Excel files detected, IT spend ($42M), Prof. Services ($18M), Facilities ($11M). Data quality score: 0.82. Intent: `upload_data`. |
| **PLAN** | Single skill: spend-profiler. No parallelism needed. User summary: *"I'll classify your spend data across 3 files into the standard taxonomy (~20 seconds)."* |
| **ACT** | spend-profiler runs. Classifies 847 line items. 91% auto-mapped. 9% (76 items) flagged for user review. Writes taxonomy draft to session memory. |
| **REFLECT** | Schema valid. Taxonomy coherence check: all 847 items have a category. Write `company`, `industry='Manufacturing'`, `total_spend='$71M'` to user_memory. Loop continues: surface taxonomy for user confirmation. |

### Turn 2: User Confirms Taxonomy, Requests Peer Benchmarking

| Phase | What Happens |
|-------|-------------|
| **OBSERVE** | user_memory now has company profile. session_memory has confirmed taxonomy. Intent: `benchmark`. Missing: headcount and revenue — heuristic-analyzer excluded from plan. |
| **PLAN** | 2 skills in parallel: peer-benchmarker (IT & Tech) and peer-benchmarker (Prof. Services) in `parallel_group=1`. value-bridge-calculator in `parallel_group=2`. User summary: *"3 skills, ~60 seconds. Benchmarking then value-at-the-table."* |
| **ACT** | Group 1: 2 peer-benchmarker calls run concurrently. IT spend at 73rd percentile vs manufacturing peers. Prof. Services at 58th percentile. Both write to session_memory. Group 2: value-bridge-calculator aggregates, applies de-duplication factor 0.72. |
| **REFLECT** | Confidence: IT benchmark = High (0.9, direct manufacturing vertical match). Prof. Services = Mid (0.75, proxy data). Value bridge: IT savings $4.2M–$7.8M (mid: $6.1M). Prof. Services $1.1M–$2.8M (mid: $1.9M). Write value-bridge summary to user_memory. Loop complete: surface matrix. |

### Turn 3: User Requests Business Case for IT

| Phase | What Happens |
|-------|-------------|
| **OBSERVE** | user_memory has full profile + value-bridge results. session_memory has all benchmarker outputs. Intent: `business_case`. Category: `IT & Technology`. All inputs available. `clarification_required: False`. |
| **PLAN** | Single skill: business-case-builder. `requires_approval: True`. User summary: *"I'll build the executive business case for IT savings, generating a .docx and .pdf (~90 seconds). Confirm?"* |
| **ACT** | business-case-builder runs. Generates: exec summary, current state ($42M at 73rd percentile), opportunity sizing ($6.1M mid-case), implementation roadmap (18 months), risk register, financial projections. Produces `business_case_IT.docx`. |
| **REFLECT** | Document structure validation: all required sections present. Numerical coherence: projections consistent with value-bridge. Write `business_case_generated_IT` to user_memory. Write custom IT benchmark thresholds to agent_memory (peer-benchmarker skill). Loop complete: deliver file. |

---

## 6. Implementation Checklist

### Phase 0 — Foundation (Weeks 1–4)

- [ ] Implement `ObserveContext` dataclass and `observe()` function skeleton
- [ ] Wire Mem0 `get_all()` and `search()` calls with `user_id` and `session_id` scopes
- [ ] Build file parsing pipeline (pandas + Tika) → store parsed data to S3 + DB
- [ ] Implement intent classifier (lightweight Claude call with structured output)
- [ ] Implement data quality scorer with `missing_fields` detection
- [ ] Build `ExecutionPlan` dataclass and basic `plan()` function (hardcode skill rules initially)
- [ ] Implement `act()` loop with parallel group dispatch using `asyncio.gather`
- [ ] Build `reflect()` stub: schema validation + `mem0.add()` calls
- [ ] Wire the full OPAR loop in the FastAPI `/api/v1/chat` endpoint with SSE streaming

### Phase 1 — Core Analysis (Weeks 5–10)

- [ ] Implement spend-profiler skill (SKILL.md + pandas classification scripts + taxonomy JSON)
- [ ] Implement peer-benchmarker skill with `industry_benchmarks.json` reference data
- [ ] Implement internal-benchmarker skill with BU variance detection logic
- [ ] Implement heuristic-analyzer skill with outcomes-per-dollar reference ranges
- [ ] Implement value-bridge-calculator with de-duplication factor logic
- [ ] Build confidence scoring engine (3-layer: schema, coherence, domain confidence)
- [ ] Implement agent_memory writes in Reflect for benchmark threshold calibration
- [ ] Build value bridge DataFrame assembly and export to `.xlsx`

### Phase 2 — Business Case & Skills Mgmt (Weeks 11–14)

- [ ] Implement business-case-builder skill with docx template generation
- [ ] Build skills management CRUD API (`/api/v1/skills` endpoints)
- [ ] Build skill testing harness (run skill against sample data, validate output)
- [ ] Implement skill versioning in PostgreSQL
- [ ] Build Reflect loop-control logic (clarification triggers, natural continuation prompts)

### Phase 3 — Polish (Weeks 15–18)

- [ ] Add Chart.js dashboard generation as an Act output (HTML artefacts)
- [ ] Add sensitivity analysis to Reflect (low/mid/high confidence band visualisation)
- [ ] Add scheduled task support for recurring analyses
- [ ] Performance: add Redis caching for Mem0 user_memory fetches at Observe phase
- [ ] Multi-client isolation: enforce Mem0 `user_id` scoping for consulting firm use cases

---

*OpEx Intelligence Platform | OPAR Loop Specification | v1.0 | Pallav Chaturvedi*