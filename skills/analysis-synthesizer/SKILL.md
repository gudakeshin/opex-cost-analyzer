---
name: analysis-synthesizer
description: >
  Synthesizes outputs from upstream OpEx Intelligence skills (variance decomposition,
  root-cause analysis, savings modeling, pipeline tracking) into a single CFO-grade
  narrative. Use this skill whenever the platform needs to consolidate multi-skill
  outputs into an executive-ready OpEx intelligence brief, management commentary,
  board pack insert, or cost performance story. Trigger on phrases like "synthesize
  the analysis", "give me the full OpEx picture", "pull it all together", "write the
  management commentary", "summarize OpEx performance", or whenever more than one
  upstream skill output is available in context and a human-readable synthesis is needed.
  This is the final OPAR loop step that converts structured analytical outputs into
  a coherent, decision-driving narrative.
---

# Analysis Synthesizer Skill

## Purpose

The Analysis Synthesizer is the **narrative layer** of the OpEx Intelligence Platform. It takes structured outputs from upstream skills — variance decomposition, root-cause analysis, CFO savings modeling, and pipeline tracking — and assembles them into a single, coherent, CFO-grade intelligence brief.

Its job is not to re-analyze. It is to **tell the cost performance story** with the right emphasis, the right sequence, and the right call to action.

---

## When This Skill Triggers

Trigger this skill when:
- Two or more upstream skill outputs are present in context and a synthesis is requested
- The user asks for "management commentary", "CFO brief", "OpEx narrative", or "board pack insert"
- The OPAR loop has completed its Observe → Plan → Act cycle and a Report output is needed
- A periodic OpEx review (monthly, quarterly) synthesis is requested
- The user says "pull it all together" or "what's the full picture"

---

## Inputs Expected

The synthesizer reads from context. It expects one or more of the following to be available:

| Input | Source Skill | What It Contains |
|---|---|---|
| Variance decomposition | `variance-decomposer` | Period vs. budget/prior, bridge components, materiality flags |
| Root cause analysis | `root-cause-analyzer` | Causal chain, driver classification (price/volume/mix/efficiency), confidence level |
| Savings model | `savings-modeler` | Identified opportunities, quantified benefit, realization timeline, owner |
| Pipeline tracker | `pipeline-tracker` | Initiative status, savings-at-risk, milestone RAG status |
| Context metadata | Platform memory / Mem0 | Company, cost center, period, currency, SAP GL structure |

If an upstream output is missing, the synthesizer notes the gap explicitly and synthesizes from what is available — it does not stall.

---

## Output Structure

The synthesizer produces a **structured OpEx Intelligence Brief** in the following format. Adapt length and depth to the audience tier (see Audience Calibration below).

```
## OpEx Intelligence Brief
### [Entity] | [Period] | [Currency]

#### 1. Headline Performance (3 sentences max)
  - Total OpEx vs. budget and prior period, in absolute and % terms
  - Direction of travel (improving / deteriorating / stable)
  - Single most important insight

#### 2. Variance Story (the bridge narrative)
  - Walk from budget/prior to actual
  - Name the top 3 drivers, quantified
  - Distinguish controllable from structural / one-off

#### 3. Root Cause Synthesis
  - For each material variance driver: what caused it, what evidence supports the cause
  - Classify: Price effect | Volume/Mix effect | Efficiency effect | Policy/Process effect
  - Flag any compounding interactions between drivers

#### 4. Savings Pipeline Status
  - Initiatives on track vs. at-risk vs. delivered
  - Cumulative savings realized YTD vs. target
  - Top 1-2 initiatives requiring CFO / leadership attention

#### 5. Forward View & Risks
  - Run-rate trajectory if current trends persist
  - Key cost risks in next 1-2 periods
  - Assumptions that could invalidate the current picture

#### 6. Recommended Actions
  - 2-3 specific, owner-assignable actions
  - Each action tied to a quantified impact or risk mitigated
  - Priority sequence: immediate / 30-day / 60-day
```

---

## Audience Calibration

Before writing, identify the audience tier from context or by asking:

| Tier | Audience | Length | Emphasis |
|---|---|---|---|
| **T1** | CFO / CEO / Board | 1 page max | Headline + key risk + recommended actions |
| **T2** | VP Finance / FP&A Head | 2 pages | Full brief, bridge narrative, pipeline status |
| **T3** | Cost Center Managers | Detail annex | Root cause depth, initiative-level tracking |

Default to **T2** if audience is unspecified.

---

## Synthesis Rules

### Rule 1: Lead with the So-What
Never open with data. Open with the business implication.
> ❌ "Total OpEx was ₹142 Cr vs. budget of ₹138 Cr."
> ✅ "OpEx overran budget by ₹4 Cr (2.9%), driven primarily by controllable maintenance costs that signal an underlying scheduling discipline issue — not a structural cost shift."

### Rule 2: Distinguish Signal from Noise
Only surface variances that are:
- Above materiality threshold (default: >2% of cost line or >₹1 Cr, whichever is lower — override from platform config if set)
- Recurring or structurally significant (not one-off timing)
- Actionable within the next two planning cycles

### Rule 3: Causal Chain Integrity
Every narrative claim about cause must trace to root-cause analyzer output. Do not introduce new causal hypotheses at synthesis stage. If root cause is uncertain, say so:
> "The maintenance overrun is likely driven by [X], though the root cause is not yet confirmed — recommend field validation."

### Rule 4: Savings Pipeline Honesty
Never project savings that are not in the pipeline tracker. If a savings opportunity has been identified but not yet committed, flag it as "unbooked upside" — not as a delivered saving.

### Rule 5: Forward View is Driver-Based
The forward view must anchor on identified cost drivers, not extrapolation. If drivers are unknown, say the forward view is uncertain and specify what information would resolve it.

### Rule 6: Actions Must Have Owners
Never write a recommended action without specifying the owner role (e.g., "Plant Manager", "Procurement Head", "FP&A") and the expected output (e.g., "revised maintenance schedule by [date]").

---

## Tone & Language Standards

The synthesizer writes as a **senior FP&A business partner briefing a CFO**. This means:

- Precise and quantified — every claim has a number behind it
- Commercially aware — connects cost performance to business outcomes
- Direct — no hedging language, no passive voice
- Concise — no sentence that doesn't add information
- Constructive — problems are paired with paths forward

Avoid:
- Accounting jargon without business translation (e.g., don't say "adverse variance in cost of goods" — say "production costs came in higher than planned, reducing margin by X bps")
- Hedge phrases like "it seems", "possibly", "it could be argued"
- Data dumps — the synthesizer interprets, it does not transcribe

---

## Integration with OPAR Loop

The Analysis Synthesizer is the **Report** output of the OPAR loop:

```
Observe  →  variance-decomposer, data-ingestion-skill
Plan     →  root-cause-analyzer, savings-modeler
Act      →  pipeline-tracker, action-assignment-skill
Report   →  analysis-synthesizer  ← THIS SKILL
```

After synthesis, the brief is persisted to Mem0 under the key:
`opex_brief:{entity}:{period}:{run_timestamp}`

This enables:
- Trend-comparison across periods ("how does this month compare to last month's brief")
- Retrieval for board pack assembly
- Input to the next OPAR cycle's Observe step (prior period actuals as baseline)

---

## Handling Missing Inputs

| Missing Input | Synthesizer Behavior |
|---|---|
| No variance decomposition | Note gap; use raw actuals vs. budget from context if available; flag as "preliminary — full bridge pending" |
| No root cause | Narrative covers "what" but not "why"; explicitly states root cause analysis pending |
| No savings pipeline data | Omit Section 4; note "pipeline data not available for this period" |
| No forward view data | Omit Section 5; note "forward view requires updated forecast assumptions" |
| All inputs missing | Do not fabricate; ask user to run upstream skills first or provide data |

---

