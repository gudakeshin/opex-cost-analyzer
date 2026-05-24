# OpEx Intelligence Platform — UI/UX Evaluation Report

**Date:** 2026-05-20  
**Evaluated by:** Claude (automated live-browser eval)  
**App version:** Branch `claude/vibrant-pascal-212eb4`  
**Viewport tested:** 1440×900 (desktop), 375×812 (mobile)

---

## Executive Summary

The platform has a strong FP&A-domain model — percentile scenarios, macroeconomic stress tests, audit chain, FACT vs AI-INFERENCE provenance labels — all concepts that resonate with CFO-office users. The visual language (Deloitte green, clean cards, Open Sans typography) is professional and on-brand.

However, three areas hold the product back disproportionately:

1. **Mobile navigation is broken.** The Analysis page bypasses the standard header (`hideHeader={true}`), so the hamburger menu never renders. Users on mobile are stranded on a single page with no escape route.
2. **The primary action ("Attach data") is visually the weakest element** on the most important page. A text link competes with two equally-styled text links — the opposite of good CTA hierarchy.
3. **Discovery of high-value features requires scrolling or prior knowledge.** The Trends / BVA / Payment Terms tabs, trust footer with exports, and the Executive view toggle are all below the fold or inside collapsed sections.

Overall score across 10 dimensions: **3.0 / 5.0**

---

## Dimension Score Heatmap

| Dimension | Analysis | Diagnostic | Cost Room | History | Trust Rail | Mobile | **Avg** |
|---|---|---|---|---|---|---|---|
| 1. Onboarding & First Run | 3 | 3 | 4 | 4 | 3 | 2 | **3.2** |
| 2. Navigation & IA | 3 | 4 | 3 | 4 | 3 | **1** | **3.0** |
| 3. Visual Hierarchy & Density | 3 | 3 | 2 | 4 | 3 | 3 | **3.0** |
| 4. Interaction & Feedback | **2** | 3 | 3 | 4 | **2** | **2** | **2.7** |
| 5. FP&A Workflow Alignment | 3 | 3 | 4 | 3 | 4 | 3 | **3.3** |
| 6. Trust & Transparency | 3 | 2 | 3 | 3 | 5 | 2 | **3.0** |
| 7. Data Tables & Charts | — | — | 3 | — | 3 | — | **3.0** |
| 8. Responsiveness & A11y | **2** | 4 | 3 | 4 | **2** | **1** | **2.7** |
| 9. Performance Perception | 3 | **2** | 3 | 4 | 3 | 3 | **3.0** |
| 10. Dual Audience UX | 3 | 3 | 3 | 3 | 3 | 2 | **2.8** |
| **Page avg** | **2.8** | **3.0** | **3.2** | **3.7** | **3.1** | **1.9** | |

Scores ≤ 2 are in **bold** — each is a flagged improvement area.

---

## Screen-by-Screen Findings

### Screen 1 — Analysis (Procurement Chat)
**File:** `frontend/src/pages/ProcurementAnalysis.tsx`

**What's working well**
- Welcome state with "How can I help…" heading and 6 contextual suggested prompts is a great pattern for a chat interface.
- The split layout (chat on left, Insights panel on right) correctly anticipates post-analysis use.
- Keyboard hint ("Shift+Enter for new line · Human-in-the-loop OPAR with trust rail") is a thoughtful power-user affordance.

**Issues found**

| # | Severity | Observation |
|---|----------|-------------|
| A1 | P0 | **Mobile hamburger missing.** `hideHeader={true}` is passed to `MainLayout`, which skips the `<header>` element entirely — including the `{isMobile && <button>…</button>}` hamburger. On 375px viewport there is zero navigation. See `MainLayout.tsx:51-62`. |
| A2 | P1 | **"Attach data" is styled identically to "New session"** — both are `text-xs px-2.5 py-1.5 rounded-lg text-brand-muted`. The primary upload action is visually indistinguishable from a destructive one. `ChatComposer.tsx:55-80`. |
| A3 | P1 | **Session badge shows raw UUID.** `PageHeader.tsx:29` renders `Session {sessionId.slice(0, 8)}…`. Users see "Session 42c39642…" — meaningless without a company name. Context stores `company_name` in `SessionContext`; it just isn't surfaced here. |
| A4 | P1 | **Dark mode toggle inaccessible.** `ThemeToggle` lives inside the standard `<header>` (`MainLayout.tsx:65`), which is skipped when `hideHeader={true}`. Users cannot toggle dark mode from the Analysis page. |
| A5 | P2 | **6 prompts overflow above the fold.** The welcome heading + Deloitte logo + first 2 prompts scroll off-screen before the visible 4, meaning the invitation to scroll is implicit and easy to miss. |
| A6 | P2 | **Insights panel empty state is vague.** "Results appear after upload and analysis." doesn't tell users *what* kinds of insights to expect (category breakdowns? benchmark gaps? savings levers?). |
| A7 | P2 | **Sidebar collapses by default at all widths**, even 1440px desktop. Users see icon-only nav with no labels on first load. The default should be `expanded` for viewports ≥ 1024px. |

---

### Screen 2 — Diagnostic
**File:** `frontend/src/pages/Diagnostic.tsx`

**What's working well**
- Clean 4-field form with sensible defaults (₹5,000 Cr revenue, Manufacturing sector).
- Full-width green "Run Diagnostic" button is the right CTA weight.
- `Source URLs (one per line, optional)` label gives clear instruction.

**Issues found**

| # | Severity | Observation |
|---|----------|-------------|
| B1 | P1 | **No output preview.** "Benchmark-backed research and value-at-table" is abstract. Users don't know if they'll get a PDF, a table, a score, or a chat response. A ghost/skeleton preview of the result card would set expectations. |
| B2 | P2 | **"Industry (sector pack)" label is unexplained.** "Sector pack" is internal product jargon. A tooltip (ℹ) explaining it selects the benchmark dataset and lever framework would help. |
| B3 | P2 | **No time estimate** on "Run Diagnostic". Diagnostic calls a web-scraping + LLM pipeline that can take 20-40s. A subtle `~30 seconds` hint under the button would reduce abandonment. |
| B4 | P2 | **No trust indicators.** Unlike Analysis, this page has no "Trust rail" button. Users submitting company URLs don't know what data is retained or how the research is conducted. |

---

### Screen 3 — Cost Room
**File:** `frontend/src/pages/CostRoom.tsx`

**What's working well**
- **Excellent empty state** with icon, clear message, two CTAs ("Go to Analysis", "Download spend template"). Best-in-class empty state across all pages.
- P10 / P50 / P90 percentile toggle is immediately understandable to FP&A professionals.
- Macro-scenario dropdown with named stress tests (INR -5%, Wage +200bps, Commodity +15%) is a differentiating FP&A feature.
- Trust footer with audit count, chain validity, and last-sync timestamp is comprehensive.

**Issues found**

| # | Severity | Observation |
|---|----------|-------------|
| C1 | P1 | **Raw API error rendered as orphan paragraph.** When the conflicts API returns a non-200 (e.g., "No analysis for session"), `ConflictsPanel.tsx:24` renders `{error}` directly as a `<p className="text-sm text-brand-muted">`. The error floats between the EmptyPipeline block and the FP&A detail toggle with no card container, no icon, no user-friendly copy. |
| C2 | P1 | **FP&A detail tabs buried below fold** and collapsed by default. Trends, Budget vs Actuals, and Payment Terms are the analytical backbone of the FP&A workflow, yet they require the user to scroll to the bottom and expand a toggle. These should default to open or be surfaced earlier. |
| C3 | P1 | **Trust footer and export buttons below fold** with no visual cue that they exist. "Export to deck" and "Export Excel" are high-value actions; they should appear in the page header or toolbar, not at the very bottom. |
| C4 | P2 | **"Needs action" toggle label is vague.** Users don't know what "action" means. Rename to "Pending review" or "Awaiting decision" to clarify that these are initiatives waiting for Accept/Defer/Reject. |
| C5 | P2 | **Control density is overwhelming at first visit.** ScenarioControls + FilterBar presents P10/P50/P90 + Scenario dropdown + 5 filter dropdowns simultaneously before any data is loaded. Progressive disclosure (hide filters until data exists) would reduce cognitive load. |

---

### Screen 4 — History
**File:** `frontend/src/pages/SessionHistory.tsx`

**What's working well**
- Cleanest empty state in the app — icon, message, single CTA, nothing extra.
- "Browse and resume previous engagements" subtitle clearly communicates purpose.

**Issues found**

| # | Severity | Observation |
|---|----------|-------------|
| D1 | P2 | **No skeleton of what a session card looks like.** Users don't know if history shows company name, date, initiative count, etc. A ghost placeholder card would set expectations. |
| D2 | P2 | **No data retention disclosure.** Sessions are deleted after 30 days (`SESSION_TTL_DAYS`). This should be surfaced as a note ("Sessions are retained for 30 days") so users know to export before that. |

---

### Screen 5 — Trust Rail (drawer on Analysis)
**File:** `frontend/src/components/Trust/TrustRail.tsx`

**What's working well**
- **Hash chain validation** ("Chain valid · 674 records") is an outstanding transparency feature — production-grade audit capability.
- FACT vs AI INFERENCE labels in the Logic trace tab are exactly the right conceptual distinction for FP&A audiences.
- Loading server audit log on open (instead of eagerly) is the right performance tradeoff.

**Issues found**

| # | Severity | Observation |
|---|----------|-------------|
| E1 | P1 | **4th tab ("Confidence") is clipped** — the Trust Rail drawer is 320px wide and the 4 tab labels exceed that. The tab overflows with no scroll indicator. Users cannot see or click "Confidence" without knowing to scroll the tab bar. `TrustRail.tsx` tab container needs `overflow-x-auto` or shorter tab labels. |
| E2 | P1 | **Drawer overlay dims entire main content** — the backdrop makes the whole left panel unreadable. Consider a narrower, non-blocking drawer or a persistent side panel instead. |
| E3 | P2 | **Audit log entries truncate session IDs mid-string.** Rows show `session_id=52dd1099-887e-4dca-9d11-ca2b99634dda` as raw UUIDs — not scannable. Should show company name or abbreviated event description. |
| E4 | P2 | **"Trust rail" button is text-only** with no icon. Users unfamiliar with the term may not click it. A shield/lock icon would signal its security/audit nature immediately. |

---

### Screen 6 — Mobile (375px)
**File:** `frontend/src/components/Layout/MainLayout.tsx`, `frontend/src/pages/ProcurementAnalysis.tsx`

**What's working well**
- Content stacks vertically acceptably.
- Prompt buttons reflow to single-column correctly.

**Issues found**

| # | Severity | Observation |
|---|----------|-------------|
| F1 | **P0** | **No navigation whatsoever.** `ProcurementAnalysis` passes `hideHeader` to `MainLayout`, bypassing the hamburger button. On mobile, users are permanently stuck on the Analysis page. Navigation to Diagnostic, Cost Room, and History is impossible. |
| F2 | P1 | **"Attach data / Run analysis / New session" crowd the composer footer.** At 375px, the three action labels run together on one line with no visual separation. "New session" (destructive action) appears immediately after "Run analysis" (primary action) with identical styling. |
| F3 | P2 | **No bottom navigation bar.** The sidebar-based navigation pattern doesn't translate to mobile. A bottom tab bar (Analysis, Diagnostic, Cost Room, History) is the standard mobile pattern for 4 top-level sections. |

---

## Improvement Opportunities

### P0 — Critical (blocks task completion)

#### P0-1: Restore mobile navigation on Analysis page
**Problem:** `ProcurementAnalysis.tsx:218` passes `hideHeader` to `MainLayout`, skipping the hamburger entirely.  
**Fix:** Remove `hideHeader` prop from Analysis page. Move the custom header content (`Trust rail` button, session badge, Insights toggle) into the `headerExtra` prop slot instead. This restores the hamburger on mobile without losing the custom header elements.

```tsx
// ProcurementAnalysis.tsx — replace this:
<MainLayout hideHeader>
  {/* custom header inline */}

// with this:
<MainLayout
  title="Analysis"
  subtitle="Human-in-the-loop spend intelligence"
  headerExtra={<>
    <Badge>Session {sessionId?.slice(0,8)}…</Badge>
    <button onClick={openTrustRail}>Trust rail</button>
  </>}
>
```

**Files:** `frontend/src/pages/ProcurementAnalysis.tsx:218`, `frontend/src/components/Layout/MainLayout.tsx:51-62`

---

#### P0-2: Handle ConflictsPanel API errors gracefully
**Problem:** `ConflictsPanel.tsx:24` renders `{error}` directly — raw API error string shown as orphan text in the page flow.  
**Fix:** Replace with a styled empty/error state.

```tsx
// ConflictsPanel.tsx:22-25 — replace:
if (error) {
  return <p className="text-sm text-brand-muted">{error}</p>;
}

// with:
if (error) {
  return null; // hide entirely when no analysis exists yet; the EmptyPipeline above already explains the state
}
```

**File:** `frontend/src/components/PageComponents/CostRoom/ConflictsPanel.tsx:22-25`

---

### P1 — High (significant friction)

#### P1-1: Elevate "Attach data" to a proper button
**Problem:** `ChatComposer.tsx:55-68` styles all three action buttons identically as ghost text. Upload data is the critical first action.  
**Fix:** Give "Attach data" a distinct variant — at minimum a border; ideally a small icon + label button.

```tsx
// ChatComposer.tsx:55-63 — replace the Attach data button:
<button
  type="button"
  onClick={onUploadClick}
  disabled={loading}
  className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg
             border border-brand-border text-brand-navy font-medium
             hover:bg-deloitte-green/10 hover:border-deloitte-green
             disabled:opacity-50 transition-colors"
>
  <PaperclipIcon className="w-3.5 h-3.5" />
  Attach data
</button>
```

**File:** `frontend/src/components/PageComponents/Analysis/ChatComposer.tsx:55-80`

---

#### P1-2: Show company name in session badge
**Problem:** `PageHeader.tsx:29` renders `Session {sessionId.slice(0, 8)}…`. The `SessionContext` already resolves `company_name`.  
**Fix:** Pass `companyName` into `PageHeader` and prefer it over the UUID.

```tsx
// PageHeader.tsx:29 — replace:
<Badge tone="success">Session {sessionId.slice(0, 8)}…</Badge>

// with:
<Badge tone="success">{companyName ?? `Session ${sessionId.slice(0, 8)}…`}</Badge>
```

**File:** `frontend/src/components/Common/PageHeader.tsx:29`  
**Data source:** `useSession().engagement.company_name` already available in context.

---

#### P1-3: Default sidebar to expanded at ≥ 1024px
**Problem:** `SidebarContext` initializes `collapsed: true` regardless of viewport width, forcing users to manually expand on first load.  
**Fix:** Initialize state based on window width.

```tsx
// SidebarContext.tsx — change initial state:
const [collapsed, setCollapsed] = useState(() => window.innerWidth < 1024);
```

**File:** `frontend/src/context/SidebarContext.tsx` (initial `collapsed` state)

---

#### P1-4: Fix Trust Rail tab clipping
**Problem:** 4 tab labels ("Audit", "Logic trace", "Provenance", "Confidence") overflow the 320px drawer width with no scroll affordance.  
**Fix:** Either shorten labels or make the tab bar scrollable.

```tsx
// TrustRail.tsx — tab container:
// Option A: shorten labels
const TRUST_TABS = [
  { id: 'audit',      label: 'Audit' },
  { id: 'trace',      label: 'Trace' },      // was "Logic trace"
  { id: 'provenance', label: 'Provenance' },
  { id: 'confidence', label: 'Confidence' },
];

// Option B: add overflow-x-auto to tab bar wrapper in Tabs.tsx
<div className="flex overflow-x-auto scrollbar-hide border-b border-brand-border">
  {tabs.map(...)}
</div>
```

**File:** `frontend/src/components/Trust/TrustRail.tsx:16-21`, `frontend/src/components/Common/Tabs.tsx`

---

#### P1-5: Restore dark mode toggle on Analysis page
**Problem:** `ThemeToggle` lives in `MainLayout`'s `<header>` (`MainLayout.tsx:65`), which is skipped when `hideHeader={true}`.  
**Fix:** Move `ThemeToggle` to the Sidebar footer (already has a footer section) so it's always visible regardless of header state.

```tsx
// Sidebar.tsx — add to the sidebar footer section alongside "Executive view":
<ThemeToggle />
```

**File:** `frontend/src/components/Navigation/Sidebar.tsx` (footer section), `frontend/src/components/Layout/MainLayout.tsx:65`

---

#### P1-6: Surface FP&A detail tabs by default
**Problem:** `CostRoom.tsx:484` `fpaOpen` state defaults to `false`. Trends/BVA/Payment Terms are core analytical views, not optional extras.  
**Fix:** Default `fpaOpen` to `true`.

```tsx
// CostRoom.tsx — change:
const [fpaOpen, setFpaOpen] = useState(false);
// to:
const [fpaOpen, setFpaOpen] = useState(true);
```

**File:** `frontend/src/pages/CostRoom.tsx` (`fpaOpen` initial state)

---

### P2 — Medium (polish / delight)

#### P2-1: Add result preview skeleton to Diagnostic
**File:** `frontend/src/pages/Diagnostic.tsx`  
Add a collapsed preview card below the form showing placeholder chips: "Industry benchmarks", "Value-at-table levers", "Key findings". Animate to real content when the API responds.

#### P2-2: Add tooltip to "Industry (sector pack)" label
**File:** `frontend/src/pages/Diagnostic.tsx`  
Wrap the label with an info tooltip: *"Sector packs contain industry-specific cost benchmarks and lever frameworks. Selecting the right pack improves recommendation accuracy."*

#### P2-3: Add time-estimate hint to "Run Diagnostic"
**File:** `frontend/src/pages/Diagnostic.tsx`  
Add `<p className="text-xs text-brand-muted text-center mt-2">Takes ~30 seconds</p>` below the CTA.

#### P2-4: Rename "Needs action" tab to "Pending review"
**File:** `frontend/src/components/PageComponents/CostRoom/FilterBar.tsx` or wherever the tab label is defined.  
"Pending review" communicates that these initiatives need an Accept/Defer/Reject decision.

#### P2-5: Add "Trust rail" icon to the button
**File:** `frontend/src/pages/ProcurementAnalysis.tsx` (the Trust rail button)  
A `ShieldCheckIcon` from Heroicons placed before "Trust rail" text signals security/audit intent at a glance.

#### P2-6: Improve Insights panel empty state
**File:** `frontend/src/pages/ProcurementAnalysis.tsx` (Insights panel empty state)  
Replace "Results appear after upload and analysis." with a list of what to expect:
```
After analysis you'll see:
  • Spend by category (addressable %)
  • Benchmark gaps vs. industry peers  
  • Top 5 savings levers (₹ Cr)
```

#### P2-7: Add mobile bottom navigation bar
**File:** New component `frontend/src/components/Navigation/MobileBottomNav.tsx`  
For mobile viewports, render a 4-tab bottom bar (Analysis, Diagnostic, Cost Room, History) using the same icons already defined in `NavIcons.tsx`. Show it in `MainLayout` when `isMobile`.

#### P2-8: Add session retention note to History page
**File:** `frontend/src/pages/SessionHistory.tsx`  
Add a subtle note: *"Sessions are retained for 30 days. Export your business case before it expires."*

#### P2-9: Humanize audit log entries in Trust Rail
**File:** `frontend/src/components/Trust/AuditLogPanel.tsx`  
Map raw event names (`session_created`, `analysis_completed`, `file_uploaded`) to human-readable labels. Show company name instead of full UUID in the log row.

---

## Recommended Quick Wins (< 1 day each)

| Task | File | Est. effort |
|------|------|-------------|
| P0-2: Suppress ConflictsPanel error (return null) | `ConflictsPanel.tsx:22-25` | 15 min |
| P1-2: Show company name in session badge | `PageHeader.tsx:29` | 30 min |
| P1-3: Expand sidebar by default on wide screens | `SidebarContext.tsx` | 15 min |
| P1-4: Fix Trust Rail tab overflow (overflow-x-auto) | `Tabs.tsx` or `TrustRail.tsx` | 20 min |
| P1-5: Move ThemeToggle to Sidebar footer | `Sidebar.tsx` | 30 min |
| P1-6: Default FP&A detail tabs to open | `CostRoom.tsx` | 5 min |
| P2-3: Add "~30 seconds" hint to Diagnostic CTA | `Diagnostic.tsx` | 10 min |
| P2-4: Rename "Needs action" → "Pending review" | `FilterBar.tsx` or tab label | 5 min |
| P2-5: Add shield icon to "Trust rail" button | `ProcurementAnalysis.tsx` | 15 min |

**Total quick wins: ~2.5 hours**

---

## Recommended Larger Investments

| Task | Effort | Impact |
|------|--------|--------|
| P0-1: Restore mobile navigation (refactor Analysis header) | 1 day | Critical — unlocks mobile |
| P2-7: Mobile bottom nav bar component | 1 day | High — completes mobile story |
| P1-1: Elevate "Attach data" CTA design + drag-drop zone | 0.5 day | High — core first action |
| P2-1: Diagnostic result skeleton preview | 0.5 day | Medium — reduces uncertainty |
| E3: Humanize audit log entries in Trust Rail | 0.5 day | Medium — improves trust signal readability |
| B1: Executive mode — evaluable only after analysis exists | — | Blocked until test data loaded |

---

*Report generated from live browser evaluation. Screenshots captured at 1440×900 and 375×812. Backend at commit `4b490b4`.*
