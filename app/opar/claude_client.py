"""Claude API client for OPAR intent classification, planning, synthesis, and communication."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Dict, List, Tuple

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_ENABLED, GEMINI_ENABLED, LLM_PROVIDER
from app.opar.models import ObserveContext

INTENT_CLASSIFY_PROMPT = """Classify the user's intent for an OpEx cost analysis platform.

User message: "{message}"

Respond with ONLY a JSON object (no markdown, no prose):
{{"intent": "<one of: general_qa, upload_data, benchmark, value_bridge, business_case, export_business_case>", "explicit_category": "<category name or null>", "confidence": 0.0, "category_confidence": 0.0}}

Rules:
- general_qa: conversational question, greeting, follow-up, or request for explanation — NOT an analysis trigger
- upload_data: user explicitly wants to upload/import/add files or data
- benchmark: user wants to compare, benchmark, or analyze spend vs peers/industry
- value_bridge: user wants value-at-the-table, savings matrix, savings opportunity, or how to optimize/reduce category costs with levers
- business_case: user wants a business case, proposal, or structured recommendation
- export_business_case: user wants to export, download, or save a document (docx/pdf)
- explicit_category: only if user names a specific spend category (e.g. "IT & Technology"); otherwise null

When in doubt between general_qa and an analysis intent, choose general_qa.
"""

PLANNING_SYSTEM_PROMPT = """You are the planning agent for OpEx Intelligence Platform.
Given the ObserveContext below, output a JSON object with:
1. "tasks": array of skill invocations, each: {"skill_name": str, "depends_on": [str], "parallel_group": int}
2. "user_summary": 1-3 sentence plain English for the user
3. "estimated_duration": e.g. "~60 seconds"
4. "requires_approval": boolean (true for business_case)

Skills available: spend-profiler, document-contextualizer, chart-builder, peer-benchmarker, internal-benchmarker, payment-terms-optimizer, bva-analyzer, temporal-analyzer, heuristic-analyzer, root-cause-analyzer, savings-modeler, value-bridge-calculator, data-validator, business-case-builder, analysis-synthesizer, executive-communication

Rules:
- spend-profiler must run first (parallel_group 0)
- document-contextualizer is optional; include only when document files are present or user explicitly asks for document-context summary
- chart-builder depends on spend-profiler and should be included when user asks for spend profile visualization (parallel_group 1)
- peer-benchmarker, internal-benchmarker, payment-terms-optimizer, bva-analyzer, temporal-analyzer, heuristic-analyzer can run in parallel (parallel_group 1) after spend-profiler
- root-cause-analyzer requires spend-profiler + peer-benchmarker (parallel_group 2)
- savings-modeler requires peer-benchmarker + internal-benchmarker + root-cause-analyzer (+ heuristic-analyzer only when included) (parallel_group 3)
- value-bridge-calculator requires peer-benchmarker + internal-benchmarker + savings-modeler (+ heuristic-analyzer only when included) (parallel_group 4)
- data-validator requires value-bridge-calculator (parallel_group 5)
- business-case-builder requires value-bridge-calculator (parallel_group 5, business_case intent only)
- analysis-synthesizer requires value-bridge-calculator + data-validator (+ document-contextualizer only when included) (parallel_group 6)
- executive-communication requires analysis-synthesizer (parallel_group 7)
- If headcount/revenue data is missing (check missing_fields), exclude heuristic-analyzer
- For upload_data intent: only spend-profiler
- For benchmark intent: use minimal benchmark plan (profiling + benchmarkers + FP&A diagnostics bva/temporal, optional heuristic)
- For value_bridge intent: include modeling chain (root-cause, savings-modeler, value-bridge, data-validator)
- Include analysis-synthesizer/executive-communication only when user asks for executive narrative/recommendations, or for business_case
- Prefer minimum viable plan that satisfies intent, data availability, and dependencies. Do not include unnecessary skills.

Output ONLY valid JSON. No markdown code blocks, no prose."""

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
  "citations": ["string"]
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


def _call_claude(
    system: str,
    user_content: str,
    max_tokens: int = 512,
    model: str = "claude-sonnet-4-5-20250929",
) -> str:
    """Call LLM. Routes to Gemini when LLM_PROVIDER=gemini, else Anthropic."""
    if LLM_PROVIDER == "gemini" and GEMINI_ENABLED:
        from app.opar.gemini_client import call_gemini
        return call_gemini(system=system, user_content=user_content, max_tokens=max_tokens)

    # Keep local/unit tests deterministic and offline.
    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Claude calls disabled during pytest runs")
    if not ANTHROPIC_ENABLED or not ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic not configured")
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    text = response.content[0].text if response.content else ""
    return text.strip()


def _call_claude_with_thinking(
    system: str,
    user_content: str,
    max_tokens: int = 1800,
    model: str = "claude-sonnet-4-5-20250929",
    budget_tokens: int = 8000,
) -> Tuple[str, str | None]:
    """Call LLM with extended thinking. Gemini Flash-Lite has no thinking — falls back to plain call."""
    if LLM_PROVIDER == "gemini" and GEMINI_ENABLED:
        from app.opar.gemini_client import call_gemini_with_thinking
        return call_gemini_with_thinking(system=system, user_content=user_content, max_tokens=max_tokens)

    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("Claude calls disabled during pytest runs")
    if not ANTHROPIC_ENABLED or not ANTHROPIC_API_KEY:
        raise RuntimeError("Anthropic not configured")
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=model,
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
    """Classify user intent via Claude. Returns (intent_class, explicit_category)."""
    prompt = INTENT_CLASSIFY_PROMPT.format(message=msg)
    raw = _call_claude(
        system="You are an intent classifier. Output only valid JSON.",
        user_content=prompt,
        max_tokens=128,
    )
    data = _extract_json(raw)
    if isinstance(data, dict):
        intent = data.get("intent", "general_qa")
        _valid = {"general_qa", "upload_data", "benchmark", "value_bridge", "business_case", "export_business_case"}
        if intent not in _valid:
            intent = "general_qa"
        explicit = data.get("explicit_category")
        if explicit and not isinstance(explicit, str):
            explicit = None
        return intent, explicit
    return "general_qa", None


def classify_intent_claude_with_meta(msg: str) -> Dict[str, Any]:
    prompt = INTENT_CLASSIFY_PROMPT.format(message=msg)
    raw = _call_claude(
        system="You are an intent classifier. Output only valid JSON.",
        user_content=prompt,
        max_tokens=160,
    )
    data = _extract_json(raw)
    if not isinstance(data, dict):
        return {
            "intent_class": "general_qa",
            "explicit_category": None,
            "intent_confidence": 0.0,
            "category_confidence": 0.0,
        }
    intent = data.get("intent", "general_qa")
    _valid = {"general_qa", "upload_data", "benchmark", "value_bridge", "business_case", "export_business_case"}
    if intent not in _valid:
        intent = "general_qa"
    explicit = data.get("explicit_category")
    if explicit and not isinstance(explicit, str):
        explicit = None
    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    try:
        category_confidence = float(data.get("category_confidence", 0.0))
    except Exception:
        category_confidence = 0.0
    return {
        "intent_class": intent,
        "explicit_category": explicit,
        "intent_confidence": max(0.0, min(1.0, confidence)),
        "category_confidence": max(0.0, min(1.0, category_confidence)),
    }


def plan_with_claude(ctx: ObserveContext) -> Dict[str, Any] | None:
    """Generate ExecutionPlan via Claude. Returns parsed plan dict or None on failure."""
    context_str = (
        f"user_message: {ctx.user_message}\n"
        f"intent_class: {ctx.intent_class}\n"
        f"explicit_category: {ctx.explicit_category}\n"
        f"spend_profile_ready: {ctx.spend_profile_ready}\n"
        f"benchmark_results_ready: {ctx.benchmark_results_ready}\n"
        f"uploaded_file_ids: {ctx.uploaded_file_ids}\n"
        f"missing_fields: {ctx.missing_fields}\n"
        f"data_quality_score: {ctx.data_quality_score}\n"
        f"file_parse_status: {ctx.file_parse_status}\n"
    )
    raw = _call_claude(
        system=PLANNING_SYSTEM_PROMPT,
        user_content=f"ObserveContext:\n{context_str}\n\nOutput the plan as JSON:",
        max_tokens=1024,
    )
    data = _extract_json(raw)
    if isinstance(data, dict) and "tasks" in data:
        return data
    return None


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
    future = executor.submit(_call_claude, _CHART_SELECTION_SYSTEM_PROMPT, user_prompt, 512)
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


# Pure UI artefacts — no narrative value for synthesis
_SKIP_SKILLS = frozenset({"chart-builder", "document-contextualizer", "business-case-builder"})

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

        else:
            slimmed[skill] = output

    return slimmed


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
) -> Tuple[Dict[str, Any] | None, str | None]:
    """Synthesize executive recommendations from deterministic skill outputs.

    Returns (advisory_dict, thinking_text). thinking_text is None unless thinking_enabled=True.
    """
    if not ANTHROPIC_ENABLED:
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
        "document_chunks": _truncate_doc_chunks(docs_text, max_chunks=2),
        "transaction_examples_by_category": _slim_transaction_examples(transaction_examples),
    }
    if deep_research_summary:
        payload["deep_research_context"] = deep_research_summary
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
    timeout_s = 35 if thinking_enabled else 8
    executor = ThreadPoolExecutor(max_workers=1)
    if thinking_enabled:
        future = executor.submit(
            _call_claude_with_thinking,
            ANALYSIS_SYNTHESIS_SYSTEM_PROMPT,
            user_prompt,
            1800,
            "claude-sonnet-4-5-20250929",
            thinking_budget_tokens,
        )
    else:
        future = executor.submit(
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
    except Exception:
        return None, thinking_text
    if isinstance(data, dict):
        return data, thinking_text
    return None, thinking_text


def _timeout_budget_seconds(payload: Dict[str, Any], strict_mode: bool = False) -> int:
    payload_bytes = len(json.dumps(payload, ensure_ascii=False))
    base = 8 if payload_bytes < 35_000 else 12 if payload_bytes < 75_000 else 16
    if strict_mode:
        base += 2
    return max(8, min(22, base))


def synthesize_analysis_claude_with_meta(
    user_message: str,
    manifest: Dict[str, Any],
    model_manifest: Dict[str, Any] | None,
    skill_outputs: Dict[str, Any],
    docs_text: List[str],
    transaction_examples: Dict[str, List[Dict[str, Any]]] | None = None,
    strict_mode: bool = False,
    deep_research_summary: str | None = None,
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
        "document_chunks": _truncate_doc_chunks(docs_text, max_chunks=2),
        "transaction_examples_by_category": _slim_transaction_examples(transaction_examples),
    }
    if deep_research_summary:
        payload["deep_research_context"] = deep_research_summary
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
        future = executor.submit(
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
    future = executor.submit(
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
