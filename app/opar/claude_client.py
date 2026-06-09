"""Claude API client for OPAR intent classification, planning, synthesis, and communication."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Tuple

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_ENABLED, GEMINI_ENABLED, LLM_PROVIDER
from app.services.llm_selection import (
    get_resolved_llm_model,
    get_resolved_llm_provider,
    submit_with_context,
)
from app.opar.gemini_client import CHAT_RESPONSE_SYSTEM_PROMPT
from app.opar.models import IntentClass

# Canonical intent set — derived from the typed enum so the prompt menu below and
# the validator stay in sync as intents are added.
_VALID_INTENTS = {ic.value for ic in IntentClass}

# Analytical capability vocabulary the LLM may emit. Mirrors the keyword tokens in
# app/opar/observe.py::_detect_query_capabilities; that keyword detector remains the
# deterministic floor (observe unions the two), so this list only gates LLM output.
_VALID_CAPABILITIES = {
    "benchmarking",
    "value_modeling",
    "variance_analysis",
    "temporal_trend",
    "working_capital",
    "root_cause",
    "visualization",
    "schema_lookup",
    "document_context",
    "executive_narrative",
    "supplier_breakdown",
}

INTENT_CLASSIFY_PROMPT = """You are the intent router for an enterprise OpEx (operating expense) cost-analysis platform. Read the user's message and decide which analysis the platform should run.

User message: "{message}"

Respond with ONLY a JSON object (no markdown, no prose):
{{"intent": "<one intent id>", "explicit_category": "<spend category name or null>", "confidence": 0.0, "category_confidence": 0.0, "capabilities": ["<capability id>", ...]}}

Intent ids (choose exactly one):
- general_qa: conversational question, greeting, follow-up, or explanation request — NOT an analysis trigger
- upload_data: user wants to upload / import / attach spend files or data
- benchmark: compare spend vs industry peers / internal benchmarks / percentiles
- value_bridge: savings opportunities, addressable spend, value-at-the-table, savings matrix, or how to optimize/reduce a category's cost with levers
- savings_plan: build a list of savings initiatives, an initiative/savings roadmap, or a multi-year savings plan
- business_case: a structured business case / proposal / recommendation with financials
- export_business_case: export / download / save a document (docx/pdf)
- drill_down: deep-dive or break down a dimension (supplier, geography, category)
- sensitivity: what-if, scenario analysis, stress test, discount-rate sensitivity
- temporal: trend over time, YoY/QoQ/MoM, run-rate, seasonality
- bva: budget vs actual, variance analysis, over/under budget
- payment_terms: payment terms, DPO, days payable, working-capital optimization
- cost_to_serve: cost-to-serve, per-employee cost, segment profitability
- conflict_review: detect/reconcile multi-source data conflicts, mismatches, duplicates
- consolidate: group/entity rollup, intercompany elimination, multi-entity consolidation
- vendor_master: vendor master, vendor dedup, canonical/duplicate vendors
- contract_review: contract lifecycle, expiry, auto-renewal, exit penalties
- gstr_reconcile: GST / GSTR reconciliation, input tax credit (India)
- zbb: zero-based budgeting

capabilities (include every analytical dimension the request needs; use [] if none apply):
benchmarking, value_modeling, variance_analysis, temporal_trend, working_capital, root_cause, visualization, schema_lookup, document_context, executive_narrative, supplier_breakdown

Rules:
- explicit_category: set only when the user names a specific spend category (e.g. "IT & Technology", "Travel"); otherwise null.
- A request to "create / list / build initiatives", "what should we go after", or "where can we save" is savings_plan with capabilities including value_modeling.
- When genuinely ambiguous between general_qa and an analysis intent, choose general_qa.
"""

ANALYSIS_SYNTHESIS_SYSTEM_PROMPT = """You are an executive FP&A synthesis copilot.
You must produce recommendations ONLY from provided skill outputs and document excerpts.
Never invent categories, values, assumptions, benchmarks, suppliers, or sources.

Return ONLY valid JSON with this schema:
{
  "executive_takeaway": "string",
  "quick_wins_from_data": ["string"],
  "category_focus_section": "string — REQUIRED when the question targets a specific spend category. Write 3-5 substantive paragraphs as a standalone CFO decision memo covering ALL of: (1) what the data shows NOW about this category—spend magnitude, addressable portion, and specific gap vs. peers or budget using exact numbers from inputs; (2) WHICH specific suppliers, lanes, or geographies are driving the issue—name them explicitly; (3) WHAT exact commercial, policy, or operational change should happen and WHY that specific mechanism releases value; (4) the financial outcome tied to modeled numbers; (5) execution dependency or leadership decision required. This must be self-contained, not a single sentence. Leave as empty string '' only when the question is not category-specific.",
  "business_levers": [
    {
      "lever_name": "string",
      "what_changes": "string",
      "why_it_works": "string",
      "evidence": ["string"]
    }
  ],
  "executive_callouts": ["string"],
  "priority_actions_30_60_90": [
    {"timeline": "30|60|90", "action": "string", "expected_impact": "string"}
  ],
  "recommendations": [
    {
      "category_id": "string",
      "category_name": "string",
      "lever": "string",
      "priority": 1,
      "financials": {
        "mid_case_savings": 0.0,
        "net_npv": 0.0,
        "payback_months": 0
      },
      "confidence": {
        "level": "low|mid|high",
        "rationale": "string"
      },
      "evidence": [
        {"source": "peer|internal|heuristic|root_cause|model|doc", "detail": "string"}
      ],
      "examples": [
        {"supplier": "string", "description": "string", "amount": 0.0, "why_relevant": "string"}
      ],
      "risks": ["string"],
      "decisions_required": ["string"]
    }
  ],
  "assumptions": ["string"],
  "citations": ["string"],
  "sme_qualification_narrative": "string"
}

Constraints:
- Include 2-4 recommendations max.
- Rank by modeled impact (mid_case_savings descending).
- Every recommendation must include at least 2 evidence bullets.
- Every recommendation must include at least 1 concrete transaction example from provided transaction_examples_by_category.
- In business_levers, explain what should change operationally or commercially; never return vague labels only.
- Avoid standalone generic phrasing such as "internal best practice" unless paired with explicit changes.
- Use only numbers from provided skill outputs.
- Make executive_takeaway specific to the asked category when the question is category-focused.
- Do not use generic opener templates like "top initiatives represent X%" unless tied to the explicit category context.
- executive_takeaway must be 4-6 sentences with clear business logic:
  1) what is happening in the data now,
  2) what operational/commercial change should happen,
  3) why that mechanism creates value,
  4) what financial/business outcome to expect,
  5) what decision is required from leadership.
- Avoid vague language; write like an experienced FP&A advisor preparing a decision memo.
- When the user question targets a specific spend category, you MUST populate `category_focus_section` with a substantive 3-5 paragraph decision memo (minimum 250 words). This is the primary deliverable for category-focused asks — it must stand alone as something a CFO can read and act on. Rules:
  - Paragraph 1: State what the data shows — name the exact spend, addressable fraction, and measured gap vs. benchmark or budget (use numbers from skill outputs).
  - Paragraph 2: Name the specific suppliers, sub-categories, geographies, or payment terms patterns driving the issue — never leave these as generic "the data shows a gap".
  - Paragraph 3: State the exact commercial/policy/operational action to take. Not "optimize" or "improve" — write what specifically changes (e.g. "renegotiate Oracle maintenance contracts from Net-30 to Net-60", "shift 18% of air freight to ocean for lanes with 5+ day lead time buffer").
  - Paragraph 4: Explain the causal mechanism — why this specific action creates the financial outcome. Connect the action to the number.
  - Paragraph 5: State the execution risk, dependency, or leadership decision required.
  - Do NOT duplicate this narrative into executive_takeaway; executive_takeaway should be brief context when category_focus_section is populated.
- When NOT category-focused, leave `category_focus_section` as an empty string.
- Avoid section headers like "Top recommendations" for category-focused asks; frame as focused category actions.
- If `deep_research_context` is present in the input, treat it as verified background research on this company/industry. Use it to strengthen evidence citations and benchmark references — do not contradict it.
- When `sme_critique_data` is present in the input: populate `sme_qualification_narrative` with 2–4 sentences written as a Deloitte senior manager who just reviewed the output. For each initiative flagged as probe_first or insufficient_data, name the category, state the specific evidence gap, and explain what risk that creates for the saving. Be direct and specific — do NOT hedge with "it may be possible". Example tone: "The IT Cloud consolidation saving assumes contracts are up for renewal, but no contract register was provided — if locked beyond 18 months, this saving is FY27+ at best." Leave sme_qualification_narrative as empty string if no sme_critique_data is present or all initiatives are verdict=proceed.
"""

EXECUTIVE_COMMUNICATION_SYSTEM_PROMPT = """You are a Finance Business Partner communicating to CFO/leadership.
Rewrite the analysis into clear, executive-ready communication.
Use ONLY provided numbers/evidence. Do not invent facts.

Return ONLY valid JSON with:
{
  "message": "string",
  "sections": {
    "executive_takeaway": "string",
    "why_now": "string",
    "recommended_actions": ["string"],
    "financial_view": ["string"],
    "risks_and_mitigations": ["string"],
    "decisions_required": ["string"]
  }
}

Style requirements:
- concise but not terse
- decision-oriented
- financially explicit
- candid on confidence and risk
- include concrete examples (supplier/description/amount) to support claims
"""

_AUDIENCE_HINTS = {
    "cfo": "Prioritize financial rigor, assumptions, confidence bands, and return metrics.",
    "ceo": "Emphasize strategic impact, speed-to-value, and enterprise trade-offs.",
    "bu_leader": "Focus on operational implications, ownership, and near-term execution steps.",
    "board": "Use governance-oriented language, downside protection, and decision clarity.",
}


def _anthropic_http_timeout_seconds() -> float:
    from app.config import llm_synthesis_timeout_seconds

    return float(llm_synthesis_timeout_seconds()) + 15.0


def _call_anthropic_native(
    system: str,
    user_content: str,
    max_tokens: int = 512,
    model: str | None = None,
    *,
    http_timeout_s: float | None = None,
) -> str:
    """Call Anthropic directly — never routed through Gemini."""
    active_model = model or get_resolved_llm_model(provider="anthropic")
    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Claude calls disabled during pytest runs")
    if not ANTHROPIC_ENABLED or not ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic not configured")
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed")

    timeout = http_timeout_s if http_timeout_s is not None else _anthropic_http_timeout_seconds()
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=timeout)
    response = client.messages.create(
        model=active_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    text = getattr(response.content[0], "text", "") if response.content else ""
    return text.strip()


def _call_claude(
    system: str,
    user_content: str,
    max_tokens: int = 512,
    model: str | None = None,
) -> str:
    """Call LLM. Preferred provider first, cross-provider fallback on failure."""
    prefer_gemini = get_resolved_llm_provider() == "gemini"
    if prefer_gemini and GEMINI_ENABLED:
        try:
            from app.opar.gemini_client import call_gemini

            return call_gemini(
                system=system, user_content=user_content, max_tokens=max_tokens, model=model
            )
        except Exception:
            if ANTHROPIC_ENABLED:
                return _call_anthropic_native(
                    system, user_content, max_tokens=max_tokens, model=model
                )
            raise
    if ANTHROPIC_ENABLED:
        return _call_anthropic_native(
            system, user_content, max_tokens=max_tokens, model=model
        )
    if GEMINI_ENABLED:
        from app.opar.gemini_client import call_gemini

        return call_gemini(
            system=system, user_content=user_content, max_tokens=max_tokens, model=model
        )
    raise RuntimeError("No LLM provider configured")


def _call_claude_with_thinking(
    system: str,
    user_content: str,
    max_tokens: int = 1800,
    model: str | None = None,
    budget_tokens: int = 8000,
) -> Tuple[str, str | None]:
    """Call LLM with extended thinking. Preferred provider first, cross-provider fallback."""
    active_model = model or get_resolved_llm_model(thinking=True, provider="anthropic")
    prefer_gemini = get_resolved_llm_provider() == "gemini"
    if prefer_gemini and GEMINI_ENABLED:
        try:
            from app.opar.gemini_client import call_gemini_with_thinking

            return call_gemini_with_thinking(
                system=system,
                user_content=user_content,
                max_tokens=max_tokens,
                model=model,
            )
        except Exception:
            if not ANTHROPIC_ENABLED:
                raise

    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Claude calls disabled during pytest runs")
    if not ANTHROPIC_ENABLED or not ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic not configured")
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed")

    from app.config import llm_thinking_timeout_seconds

    http_timeout = float(llm_thinking_timeout_seconds()) + 20.0
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=http_timeout)
    response = client.messages.create(
        model=active_model,
        max_tokens=max_tokens + budget_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        thinking={"type": "enabled", "budget_tokens": budget_tokens},
    )
    text = ""
    thinking = ""
    for block in response.content:
        if getattr(block, "type", None) == "thinking":
            thinking = getattr(block, "thinking", "") or ""
        elif getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
    return text.strip(), thinking.strip() or None


def _extract_json(text: str) -> Dict[str, Any] | List[Any]:
    """Extract JSON from response, handling markdown code blocks."""
    text = text.strip()
    # Remove markdown code blocks if present
    if "```json" in text:
        match = re.search(r"```json\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    elif "```" in text:
        match = re.search(r"```\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    return json.loads(text)


def classify_intent_claude(msg: str) -> Tuple[str, str | None]:
    """Classify user intent via the LLM. Returns (intent_class, explicit_category)."""
    meta = classify_intent_claude_with_meta(msg)
    if meta is None:
        return "general_qa", None
    return str(meta.get("intent_class") or "general_qa"), meta.get("explicit_category")


def classify_intent_claude_with_meta(msg: str) -> Dict[str, Any] | None:
    """LLM intent classification over the full intent taxonomy.

    Returns a meta dict on success, or ``None`` when the LLM is unavailable —
    provider disabled, pytest, timeout/error, or unparseable output — so the
    caller can fall back to the deterministic rule-based classifier. (A returned
    ``general_qa`` means the LLM *chose* general_qa, which is distinct from None.)
    """
    prompt = INTENT_CLASSIFY_PROMPT.format(message=msg)
    try:
        raw = _call_claude(
            system="You are an intent classifier. Output only valid JSON.",
            user_content=prompt,
            max_tokens=220,
        )
        data = _extract_json(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    intent = data.get("intent", "general_qa")
    if intent not in _VALID_INTENTS:
        intent = "general_qa"

    explicit = data.get("explicit_category")
    if not isinstance(explicit, str) or explicit.strip().lower() in ("", "null", "none"):
        explicit = None

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    try:
        category_confidence = float(data.get("category_confidence", 0.0))
    except Exception:
        category_confidence = 0.0

    raw_caps = data.get("capabilities")
    capabilities = (
        [c for c in raw_caps if isinstance(c, str) and c in _VALID_CAPABILITIES]
        if isinstance(raw_caps, list)
        else []
    )

    return {
        "intent_class": intent,
        "explicit_category": explicit,
        "intent_source": "llm",
        "intent_confidence": max(0.0, min(1.0, confidence)),
        "category_confidence": max(0.0, min(1.0, category_confidence)),
        "query_capabilities": capabilities,
    }


_CHART_SELECTION_SYSTEM_PROMPT = (
    "You are a data-visualization advisor for an OpEx cost analysis platform. "
    "Given the user's question and a spend profile summary, choose 1–3 chart types "
    "that best answer the question. "
    "Respond with JSON only — no prose, no markdown fence."
)

_AVAILABLE_CHARTS = (
    "Available chart types:\n"
    "- pareto_spend: Pareto concentration view — best when top-3 categories dominate (>55% of spend) "
    "or when the user asks about concentration, top spenders, or where most money goes.\n"
    "- ranked_bar_spend: Ranked bar chart — best for distributed portfolios or 'which categories?' questions.\n"
    "- stacked_addressability: Addressable vs fixed vs variable split — best for optimization, "
    "savings, addressable spend, or 'what can we cut?' questions.\n"
    "- trend_line_total_spend: Spend trend over time — only select if has_trend is true; "
    "best for trajectory, trend, run rate, or period-over-period questions.\n"
)


def select_charts_claude(
    user_message: str,
    profile_summary: Dict[str, Any],
) -> Dict[str, Any] | None:
    """Use Claude to select chart types and generate commentary based on user intent.

    Returns {"selected_charts": [...], "commentary_points": [...]} or None on failure.
    """
    if not ANTHROPIC_ENABLED:
        return None
    top_cats = profile_summary.get("top_categories", [])
    cat_lines = "\n".join(
        f"  - {c['name']}: ${float(c.get('spend', 0)):,.0f} spend, "
        f"${float(c.get('addressable_spend', 0)):,.0f} addressable"
        for c in top_cats[:5]
    )
    user_prompt = (
        f"User question: {user_message}\n\n"
        f"Spend profile summary:\n"
        f"  total_spend: ${float(profile_summary.get('total_spend', 0)):,.0f}\n"
        f"  top3_share: {float(profile_summary.get('top3_share', 0)):.1%}\n"
        f"  has_trend_data: {profile_summary.get('has_trend', False)}\n"
        f"  top categories:\n{cat_lines}\n\n"
        f"{_AVAILABLE_CHARTS}\n"
        "Output JSON with keys 'selected_charts' (array of {{chart, reason}}) "
        "and 'commentary_points' (array of 3–5 strings that directly address the user's question "
        "using the profile numbers above)."
    )
    executor = ThreadPoolExecutor(max_workers=1)
    future = submit_with_context(executor, _call_claude, _CHART_SELECTION_SYSTEM_PROMPT, user_prompt, 512)
    try:
        raw = future.result(timeout=10)
    except (FuturesTimeoutError, Exception):
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        return None
    finally:
        if not future.cancelled():
            executor.shutdown(wait=True, cancel_futures=True)
    try:
        data = _extract_json(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    charts = data.get("selected_charts")
    if not isinstance(charts, list) or not charts:
        return None
    valid_types = {"pareto_spend", "ranked_bar_spend", "stacked_addressability", "trend_line_total_spend"}
    charts = [c for c in charts if isinstance(c, dict) and c.get("chart") in valid_types]
    if not charts:
        return None
    return {
        "selected_charts": charts,
        "commentary_points": data.get("commentary_points") or [],
    }


# Skills with no narrative value for synthesis (UI artefacts, security pipeline, exports).
_SKIP_SKILLS = frozenset({
    "chart-builder",
    "document-contextualizer",
    "business-case-builder",
    "pii-stripper",
    "data-classifier",
    "llm-context-builder",
    "data-validator",
    "export-formatter",
    "dashboard-builder",
})

_SPEND_PROFILER_KEYS = frozenset({
    "category_id", "category_name", "spend", "spend_pct",
    "hhi", "concentration_flag", "benchmark_gap_pct",
    "addressable_spend", "addressable_pct", "supplier_count",
    "fixed_spend", "variable_spend",
})


def _slim_skill_outputs(skill_outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Trim large arrays within each skill to top-N rows; keep all analytical skills.

    The payload bulk comes from array lengths, NOT from skill count.
    Trimming arrays keeps payload ~21 kB (well under the 35 kB fast-path threshold)
    while preserving every analytical signal the synthesis prompt needs.
    """
    slimmed: Dict[str, Any] = {}
    for skill, output in skill_outputs.items():
        if skill in _SKIP_SKILLS:
            continue  # pure UI artefacts — no narrative value

        if skill == "spend-profiler":
            cats = sorted(
                output.get("category_profile", []),
                key=lambda r: float(r.get("spend", 0) or 0),
                reverse=True,
            )[:8]
            slimmed[skill] = {
                "total_spend": output.get("total_spend"),
                "category_count": output.get("category_count"),
                "category_profile": [
                    {k: v for k, v in c.items() if k in _SPEND_PROFILER_KEYS}
                    | {"top_suppliers": c.get("top_suppliers", [])[:2]}
                    for c in cats
                ],
            }

        elif skill == "bva-analyzer":
            top_var = sorted(
                output.get("variances", []),
                key=lambda r: abs(float(r.get("total_variance", 0) or 0)),
                reverse=True,
            )[:8]
            slimmed[skill] = {k: v for k, v in output.items() if k != "variances"}
            slimmed[skill]["variances"] = top_var

        elif skill == "temporal-analyzer":
            slimmed[skill] = {
                k: v for k, v in output.items()
                if k not in {"period_trends", "category_trends"}
            }
            slimmed[skill]["period_trends"] = output.get("period_trends", [])[-6:]
            slimmed[skill]["category_trends"] = output.get("category_trends", [])[:5]

        elif skill == "payment-terms-optimizer":
            top_opp = sorted(
                output.get("opportunities", []),
                key=lambda r: float(r.get("annual_cash_value", 0) or 0),
                reverse=True,
            )[:5]
            slimmed[skill] = {k: v for k, v in output.items() if k != "opportunities"}
            slimmed[skill]["opportunities"] = top_opp

        elif skill == "savings-modeler":
            initiatives = output.get("initiatives", []) if isinstance(output.get("initiatives"), list) else []
            slimmed[skill] = {k: v for k, v in output.items() if k != "initiatives"}
            slimmed[skill]["initiatives"] = initiatives[:12]

        elif skill == "root-cause-analyzer":
            findings = (
                output.get("root_cause_findings", [])
                if isinstance(output.get("root_cause_findings"), list)
                else []
            )
            slimmed[skill] = {k: v for k, v in output.items() if k != "root_cause_findings"}
            slimmed[skill]["root_cause_findings"] = findings[:8]

        else:
            slimmed[skill] = output

    return slimmed


def _slim_sme_critique(sme_output: Any) -> Dict[str, Any] | None:
    """Trim SME critique for synthesis prompt — explicit sme_critique_data field."""
    if not isinstance(sme_output, dict):
        return None
    summary = sme_output.get("critique_summary", {})
    critiques = sme_output.get("initiative_critiques", []) if isinstance(sme_output.get("initiative_critiques"), list) else []
    slim_critiques: List[Dict[str, Any]] = []
    for c in critiques[:5]:
        if not isinstance(c, dict):
            continue
        probes = c.get("probe_questions", []) if isinstance(c.get("probe_questions"), list) else []
        top_probe = probes[0] if probes and isinstance(probes[0], dict) else {}
        slim_critiques.append({
            "category_name": c.get("category_name"),
            "lever": c.get("lever"),
            "sme_verdict": c.get("sme_verdict"),
            "evidence_maturity": c.get("evidence_maturity"),
            "critical_risk": c.get("critical_risk"),
            "top_probe_question": top_probe.get("question"),
            "top_probe_why_critical": top_probe.get("why_critical"),
        })
    if not slim_critiques and not summary:
        return None
    return {
        "critique_summary": summary if isinstance(summary, dict) else {},
        "initiative_critiques": slim_critiques,
    }


def _slim_transaction_examples(
    tx: Dict[str, List[Dict[str, Any]]] | None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Cap to top 5 categories, 2 examples each.

    Satisfies the ANALYSIS_SYNTHESIS_SYSTEM_PROMPT hard constraint (line 117):
    'Every recommendation must include at least 1 concrete transaction example
    from provided transaction_examples_by_category.'
    Keeps the transaction block to ~0.5 kB.
    """
    if not tx:
        return {}
    return {cat: examples[:2] for cat, examples in list(tx.items())[:5]}


def _truncate_doc_chunks(docs_text: List[str], max_chunks: int = 6, max_chars: int = 1200) -> List[str]:
    chunks: List[str] = []
    for text in docs_text:
        if not text:
            continue
        normalized = " ".join(text.split())
        if not normalized:
            continue
        step = max_chars
        for i in range(0, len(normalized), step):
            chunks.append(normalized[i:i + step])
            if len(chunks) >= max_chunks:
                return chunks
    return chunks[:max_chunks]


def synthesize_chat_response_claude(
    context: Dict[str, Any],
    *,
    thinking_enabled: bool = False,
) -> Tuple[str | None, str | None]:
    """Conversational QA answer from structured context via Claude.

    Mirrors ``synthesize_chat_response_gemini`` (same prompt, same ``(text, thinking)``
    return shape) so the chat path can be provider-agnostic. Returns ``(None, None)``
    when Anthropic is unavailable, on timeout, or on error — the caller then falls
    back to the deterministic keyword composer.
    """
    if not ANTHROPIC_ENABLED:
        return None, None
    user_prompt = (
        "Answer the user's question from this context. Return markdown only.\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )
    from app.config import llm_synthesis_timeout_seconds, llm_thinking_timeout_seconds

    payload_bytes = len(user_prompt)
    timeout_s = (
        llm_thinking_timeout_seconds()
        if thinking_enabled
        else llm_synthesis_timeout_seconds(payload_bytes)
    )
    max_tokens = 2048 if thinking_enabled else 1024
    executor = ThreadPoolExecutor(max_workers=1)
    if thinking_enabled:
        future: Future[Any] = submit_with_context(
            executor,
            _call_claude_with_thinking,
            CHAT_RESPONSE_SYSTEM_PROMPT,
            user_prompt,
            max_tokens,
        )
    else:
        future = submit_with_context(
            executor,
            _call_anthropic_native,
            CHAT_RESPONSE_SYSTEM_PROMPT,
            user_prompt,
            max_tokens,
        )
    try:
        result = future.result(timeout=timeout_s)
        if thinking_enabled:
            text, thinking = result
            return (text or "").strip() or None, thinking
        return (result or "").strip() or None, None
    except FuturesTimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        from app.config import logger

        logger.warning(
            '"synthesize_chat_response_claude timeout after %ss (thinking=%s)"',
            timeout_s,
            thinking_enabled,
        )
        return None, None
    except Exception as exc:  # noqa: BLE001 — degrade to deterministic fallback
        from app.config import logger

        logger.warning('"synthesize_chat_response_claude failed error=%s"', exc)
        return None, None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _timeout_budget_seconds(payload: Dict[str, Any], strict_mode: bool = False) -> int:
    from app.config import llm_synthesis_timeout_seconds

    payload_bytes = len(json.dumps(payload, ensure_ascii=False))
    base = llm_synthesis_timeout_seconds(payload_bytes)
    if strict_mode:
        base = int(base * 1.1)
    return base


def synthesize_analysis_claude(
    user_message: str,
    manifest: Dict[str, Any],
    model_manifest: Dict[str, Any] | None,
    skill_outputs: Dict[str, Any],
    docs_text: List[str],
    transaction_examples: Dict[str, List[Dict[str, Any]]] | None = None,
    strict_mode: bool = False,
    thinking_enabled: bool = False,
    thinking_budget_tokens: int = 8000,
    deep_research_summary: str | None = None,
    retrieved_context: List[str] | None = None,
) -> Tuple[Dict[str, Any] | None, str | None]:
    """Synthesize executive recommendations from deterministic skill outputs.

    Returns (advisory_dict, thinking_text). thinking_text is None unless thinking_enabled=True.
    """
    if not GEMINI_ENABLED and not ANTHROPIC_ENABLED:
        return None, None
    payload = {
        "user_message": user_message,
        "session_context": {
            "company_name": manifest.get("company_name"),
            "industry": manifest.get("industry"),
            "annual_revenue": manifest.get("annual_revenue"),
            "currency": manifest.get("currency"),
        },
        "model_manifest": model_manifest or {},
        "skill_outputs": _slim_skill_outputs(skill_outputs),
        "document_chunks": retrieved_context if retrieved_context else _truncate_doc_chunks(docs_text, max_chunks=2),
        "transaction_examples_by_category": _slim_transaction_examples(transaction_examples),
    }
    if deep_research_summary:
        payload["deep_research_context"] = deep_research_summary
    sme_data = _slim_sme_critique(skill_outputs.get("sme-critique"))
    if sme_data:
        payload["sme_critique_data"] = sme_data
    strict_hint = ""
    if strict_mode:
        strict_hint = (
            "\nSTRICT QUALITY MODE:\n"
            "- At least 3 business_levers.\n"
            "- Each business lever must include specific operational/commercial changes.\n"
            "- Include at least 2 executive_callouts with concrete numbers.\n"
            "- Include at least 3 quick_wins_from_data.\n"
            "- If the user question targets a specific category: `category_focus_section` MUST be "
            "a decision-memo-quality analysis of at least 250 words. Write 3-5 paragraphs. "
            "Name the exact suppliers and amounts from the data. Do NOT write a single sentence. "
            "Explain the causal mechanism, not just the gap. "
            "Make it self-contained — a CFO must be able to act on it without reading anything else.\n"
        )
    user_prompt = (
        "Synthesize recommendations from this JSON context:\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
        f"{strict_hint}"
    )
    from app.config import llm_thinking_timeout_seconds

    timeout_s = (
        llm_thinking_timeout_seconds()
        if thinking_enabled
        else _timeout_budget_seconds(payload, strict_mode=strict_mode)
    )
    executor = ThreadPoolExecutor(max_workers=1)
    if thinking_enabled:
        future: Future[Any] = submit_with_context(
            executor,
            _call_claude_with_thinking,
            ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            2048,
            None,
            thinking_budget_tokens,
        )
    else:
        future = submit_with_context(
            executor,
            _call_claude,
            ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            1800,
        )
    try:
        result = future.result(timeout=timeout_s)
    except FuturesTimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        from app.config import logger

        logger.warning(
            '"synthesize_analysis_claude timeout after %ss (thinking=%s)"',
            timeout_s,
            thinking_enabled,
        )
        return None, None
    finally:
        if not future.cancelled():
            executor.shutdown(wait=True, cancel_futures=True)

    if thinking_enabled:
        raw, thinking_text = result
    else:
        raw, thinking_text = result, None

    try:
        data = _extract_json(raw)
    except Exception as exc:
        from app.config import logger as _log

        _log.warning(
            '"synthesize_analysis_claude json_parse_failed error=%s raw_len=%d"',
            exc,
            len(raw or ""),
        )
        return None, thinking_text
    if isinstance(data, dict):
        return data, thinking_text
    return None, thinking_text


def synthesize_analysis_claude_with_meta(
    user_message: str,
    manifest: Dict[str, Any],
    model_manifest: Dict[str, Any] | None,
    skill_outputs: Dict[str, Any],
    docs_text: List[str],
    transaction_examples: Dict[str, List[Dict[str, Any]]] | None = None,
    strict_mode: bool = False,
    deep_research_summary: str | None = None,
    retrieved_context: List[str] | None = None,
) -> Tuple[Dict[str, Any] | None, str | None]:
    if not ANTHROPIC_ENABLED:
        return None, "provider_disabled"
    payload = {
        "user_message": user_message,
        "session_context": {
            "company_name": manifest.get("company_name"),
            "industry": manifest.get("industry"),
            "annual_revenue": manifest.get("annual_revenue"),
            "currency": manifest.get("currency"),
        },
        "model_manifest": model_manifest or {},
        "skill_outputs": _slim_skill_outputs(skill_outputs),
        "document_chunks": retrieved_context if retrieved_context else _truncate_doc_chunks(docs_text, max_chunks=2),
        "transaction_examples_by_category": _slim_transaction_examples(transaction_examples),
    }
    if deep_research_summary:
        payload["deep_research_context"] = deep_research_summary
    sme_data = _slim_sme_critique(skill_outputs.get("sme-critique"))
    if sme_data:
        payload["sme_critique_data"] = sme_data
    strict_hint = ""
    if strict_mode:
        strict_hint = (
            "\nSTRICT QUALITY MODE:\n"
            "- At least 3 business_levers.\n"
            "- Each business lever must include specific operational/commercial changes.\n"
            "- Include at least 2 executive_callouts with concrete numbers.\n"
            "- Include at least 3 quick_wins_from_data.\n"
            "- If the user question targets a specific category: `category_focus_section` MUST be "
            "a decision-memo-quality analysis of at least 250 words. Write 3-5 paragraphs. "
            "Name the exact suppliers and amounts from the data. Do NOT write a single sentence. "
            "Explain the causal mechanism, not just the gap. "
            "Make it self-contained — a CFO must be able to act on it without reading anything else.\n"
        )

    def _run_with_payload(in_payload: Dict[str, Any], timeout_s: int) -> Tuple[Dict[str, Any] | None, str | None]:
        executor = ThreadPoolExecutor(max_workers=1)
        future = submit_with_context(
            executor,
            _call_claude,
            ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
            (
                "Synthesize recommendations from this JSON context:\n"
                f"{json.dumps(in_payload, ensure_ascii=False)}\n"
                f"{strict_hint}"
            ),
            1800,
        )
        try:
            raw = future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            return None, "timeout"
        except Exception:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            return None, "provider_unavailable"
        finally:
            if not future.cancelled():
                executor.shutdown(wait=True, cancel_futures=True)
        try:
            data = _extract_json(raw)
        except Exception:
            return None, "schema_parse_fail"
        if isinstance(data, dict):
            return data, None
        return None, "schema_parse_fail"

    timeout_s = _timeout_budget_seconds(payload, strict_mode=strict_mode)
    out, reason = _run_with_payload(payload, timeout_s)
    if out is not None:
        return out, None
    return None, reason or "unknown"


def draft_executive_communication_claude(
    user_message: str,
    manifest: Dict[str, Any],
    model_manifest: Dict[str, Any] | None,
    skill_outputs: Dict[str, Any],
    transaction_examples: Dict[str, List[Dict[str, Any]]] | None = None,
) -> Dict[str, Any] | None:
    """Draft executive communication from synthesized + deterministic outputs."""
    if not ANTHROPIC_ENABLED:
        return None
    payload = {
        "user_message": user_message,
        "session_context": {
            "company_name": manifest.get("company_name"),
            "industry": manifest.get("industry"),
            "annual_revenue": manifest.get("annual_revenue"),
            "currency": manifest.get("currency"),
            "audience": manifest.get("audience") or "cfo",
        },
        "model_manifest": model_manifest or {},
        "skill_outputs": _slim_skill_outputs(skill_outputs),
    }
    audience = str((manifest.get("audience") or "cfo")).lower()
    audience_hint = _AUDIENCE_HINTS.get(audience, _AUDIENCE_HINTS["cfo"])
    executor = ThreadPoolExecutor(max_workers=1)
    future = submit_with_context(
        executor,
        _call_claude,
        EXECUTIVE_COMMUNICATION_SYSTEM_PROMPT,
        (
            f"Target audience: {audience}\n"
            f"Audience style hint: {audience_hint}\n\n"
            f"Draft executive communication from this JSON context:\n{json.dumps(payload, ensure_ascii=False)}"
        ),
        1200,
    )
    try:
        raw = future.result(timeout=8)
    except FuturesTimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        return None
    finally:
        if not future.cancelled():
            executor.shutdown(wait=True, cancel_futures=True)
    data = _extract_json(raw)
    if isinstance(data, dict):
        return data
    return None


def draft_executive_communication_claude_with_meta(
    user_message: str,
    manifest: Dict[str, Any],
    model_manifest: Dict[str, Any] | None,
    skill_outputs: Dict[str, Any],
    transaction_examples: Dict[str, List[Dict[str, Any]]] | None = None,
) -> Tuple[Dict[str, Any] | None, str | None]:
    if not ANTHROPIC_ENABLED:
        return None, "provider_disabled"
    try:
        out = draft_executive_communication_claude(
            user_message=user_message,
            manifest=manifest,
            model_manifest=model_manifest,
            skill_outputs=skill_outputs,
            transaction_examples=transaction_examples,
        )
    except FuturesTimeoutError:
        return None, "timeout"
    except Exception:
        return None, "provider_unavailable"
    if out is None:
        return None, "timeout"
    return out, None


def interpret_workbook_structure_claude_with_meta(
    structural_summary: Dict[str, Any],
) -> Tuple[Dict[str, Any] | None, str | None]:
    """Run lightweight structural interpretation for planning-model workbooks."""
    if not GEMINI_ENABLED and not ANTHROPIC_ENABLED:
        return None, "provider_disabled"
    try:
        payload = json.dumps(structural_summary, ensure_ascii=False)
        from app.opar.gemini_client import call_gemini
        raw = call_gemini(
            system=(
                "You are a financial model architect. "
                "Return only valid JSON that matches the WorkbookManifest schema. "
                "No prose. No markdown."
            ),
            user_content=(
                "Interpret this workbook structural summary and output WorkbookManifest JSON.\n"
                f"{payload}"
            ),
            max_tokens=900,
        )
        data = _extract_json(raw)
        if isinstance(data, dict):
            return data, None
        return None, "schema_parse_fail"
    except FuturesTimeoutError:
        return None, "timeout"
    except Exception:
        return None, "provider_unavailable"


class ClaudeToolTransport:
    """Anthropic tool_use transport for ``run_tool_loop``."""

    def __init__(
        self,
        *,
        model: str | None = None,
        max_tokens: int = 4096,
        thinking_budget: int = 8000,
    ) -> None:
        self.thinking_budget = thinking_budget
        self.model = model or get_resolved_llm_model(provider="anthropic")
        # Anthropic requires max_tokens > thinking.budget_tokens.
        self.max_tokens = max(max_tokens, thinking_budget + 2048)

    def generate(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list,
        thinking: bool = True,
    ) -> tuple[str | None, list, str | None]:
        from app.opar.agent_runtime import ToolCall, ToolDefinition

        if os.getenv("PYTEST_CURRENT_TEST"):
            raise RuntimeError("Claude calls disabled during pytest runs")
        if not ANTHROPIC_ENABLED or not ANTHROPIC_API_KEY:
            raise RuntimeError("Anthropic not configured")
        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        anthropic_tools = [t.to_anthropic() if isinstance(t, ToolDefinition) else t for t in tools]
        api_messages = _to_anthropic_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": api_messages,
            "tools": anthropic_tools,
        }
        if thinking:
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}

        response = client.messages.create(**kwargs)

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            btype = getattr(block, "type", None)
            if btype == "thinking":
                thinking_parts.append(getattr(block, "thinking", "") or "")
            elif btype == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif btype == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=dict(block.input or {}),
                    )
                )

        return (
            "\n".join(text_parts).strip() or None,
            tool_calls,
            "\n".join(thinking_parts) if thinking_parts else None,
        )


def _to_anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert generic agent messages to Anthropic API format."""
    from app.opar.agent_runtime import ToolCall

    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        if role not in ("user", "assistant"):
            role = "user"
        content = msg.get("content")
        blocks: list[dict[str, Any]] = []

        if isinstance(content, str) and content:
            blocks.append({"type": "text", "text": content})
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": item.get("tool_use_id") or item.get("tool_call_id"),
                            "content": item.get("content", ""),
                        }
                    )
                elif isinstance(item, str):
                    blocks.append({"type": "text", "text": item})

        for call in msg.get("tool_calls") or []:
            if isinstance(call, ToolCall):
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.id,
                        "name": call.name,
                        "input": call.arguments,
                    }
                )

        if blocks:
            out.append({"role": role, "content": blocks})
    return out
