"""Natural-language spend query router — skills, structured aggregate, or SQL."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Tuple

from app.config import logger
from app.opar.tools.context import ToolSessionContext
from app.services.compliance import append_audit_event
from app.services.spend_schema import load_spend_schema
from app.services.spend_store import SpendQueryError

from app.opar.tools.catalog import _open_agent_store

Tier = Literal["skill", "aggregate", "sql"]
Prefer = Literal["auto", "skill", "aggregate", "sql"]

_SKILL_PATTERNS: List[Tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\b(peer|benchmark|sector|p25|p50|p75|gap)\b", re.I), "get_benchmarks", "benchmark comparison"),
    (re.compile(r"\b(profile|concentration|top categor)", re.I), "spend-profiler", "spend profile"),
    (re.compile(r"\b(cohort|pareto|tier|movers?|qoq|yoy)\b", re.I), "cohort-segmenter", "cohort segmentation"),
    (re.compile(r"\b(trend|temporal|over time|monthly|quarterly)\b", re.I), "temporal-analyzer", "temporal trend"),
    (re.compile(r"\b(root cause|why is|driver)\b", re.I), "root-cause-analyzer", "root cause"),
]

_AGGREGATE_PATTERNS = [
    re.compile(r"\btop\s+(\d+)\s+(\w+)", re.I),
    re.compile(r"\b(breakdown|rollup|roll-up|group(?:ed)? by|by)\s+(\w+)", re.I),
    re.compile(r"\bhow much\b.*\b(in|for)\s+(\w+)", re.I),
]

_DIM_ALIASES = {
    "vendor": "supplier",
    "vendors": "supplier",
    "supplier": "supplier",
    "suppliers": "supplier",
    "category": "category_name",
    "categories": "category_name",
    "bu": "business_unit",
    "business unit": "business_unit",
    "business_unit": "business_unit",
    "gl": "gl_code",
    "cost center": "cost_center_id",
    "cost_center": "cost_center_id",
    "period": "fiscal_period",
    "fiscal period": "fiscal_period",
    "year": "fiscal_year",
}


def classify_nl_query_tier(question: str, *, prefer: Prefer = "auto") -> Tier:
    """Rule-based tier classification; used when prefer=auto."""
    if prefer != "auto":
        return prefer  # type: ignore[return-value]
    q = question.lower()
    for pattern, _skill, _reason in _SKILL_PATTERNS:
        if pattern.search(q):
            return "skill"
    if any(p.search(q) for p in _AGGREGATE_PATTERNS):
        return "aggregate"
    if re.search(r"\b(where|having|join|with\b|percent|growth|>\s*\d)", q):
        return "sql"
    return "aggregate"


def _resolve_dimension(token: str, valid_cols: set[str]) -> str | None:
    key = token.strip().lower().replace("-", " ")
    col = _DIM_ALIASES.get(key, token.strip())
    if col in valid_cols:
        return col
    if key in valid_cols:
        return key
    return None


def _rule_based_aggregate_spec(question: str, valid_cols: set[str]) -> Dict[str, Any] | None:
    """Parse simple aggregate questions without LLM."""
    q = question.lower()
    limit = 50
    m_top = re.search(r"\btop\s+(\d+)\b", q)
    if m_top:
        limit = int(m_top.group(1))

    group_by: List[str] = []
    for pattern in _AGGREGATE_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        dim_token = m.group(m.lastindex or 2)
        col = _resolve_dimension(str(dim_token), valid_cols)
        if col and col not in group_by:
            group_by.append(col)

    # explicit "by X" / "by X and Y"
    by_match = re.search(r"\bby\s+([\w\s,/&]+)", q)
    if by_match:
        for part in re.split(r"[,/&]|\band\b", by_match.group(1)):
            col = _resolve_dimension(part, valid_cols)
            if col and col not in group_by:
                group_by.append(col)

    if not group_by:
        group_by = ["category_name"] if "category_name" in valid_cols else ["supplier"]

    filters: Dict[str, Any] = {}
    for dim in ("category_name", "supplier", "business_unit"):
        if dim not in valid_cols:
            continue
        m = re.search(rf"\b(in|for)\s+([A-Za-z0-9][\w\s&.-]{{2,40}})", question, re.I)
        if m and dim == "category_name":
            filters[dim] = m.group(2).strip()
            break

    metrics = {"spend": "SUM(amount)", "lines": "COUNT(*)"}
    return {
        "group_by": group_by,
        "metrics": metrics,
        "filters": filters or None,
        "limit": limit,
        "order_by": "spend DESC",
    }


def _llm_aggregate_or_sql(
    question: str,
    schema: Dict[str, Any],
    *,
    tier: Literal["aggregate", "sql"],
) -> Dict[str, Any] | str | None:
    from app.opar.llm_provider import call_llm

    col_names = [c["name"] for c in schema.get("columns", [])]
    samples = json.dumps(schema.get("sample_values") or {}, ensure_ascii=False)[:2000]
    if tier == "aggregate":
        system = (
            "You translate natural-language spend questions into a JSON aggregate spec. "
            "Return ONLY valid JSON with keys: group_by (list of column names), "
            "metrics (dict name->SQL expr like SUM(amount)), filters (dict or null), "
            "limit (int), order_by (string or null). "
            "Use only columns from the schema. Use fiscal_period not period."
        )
        user = f"Question: {question}\nColumns: {col_names}\nSamples: {samples}"
    else:
        system = (
            "You write a single DuckDB SELECT or WITH…SELECT against view `spend`. "
            "Return ONLY the SQL text, no markdown. Use fiscal_period not period. "
            "Read-only; no DDL/DML."
        )
        user = f"Question: {question}\nColumns: {col_names}\nSamples: {samples}"

    raw = call_llm(system, user, max_tokens=800, skill_name="natural_language_query")
    if not raw:
        return None
    text = raw.strip()
    if tier == "sql":
        text = re.sub(r"^```(?:sql)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()
    try:
        from app.opar.claude_client import _extract_json

        return _extract_json(text)  # type: ignore[return-value]
    except Exception:
        logger.warning("nl_query: failed to parse LLM aggregate spec")
        return None


def _execute_skill_tier(session: ToolSessionContext, question: str) -> Dict[str, Any]:
    q = question.lower()
    for pattern, skill_or_tool, reason in _SKILL_PATTERNS:
        if pattern.search(q):
            if skill_or_tool == "get_benchmarks":
                from app.opar.tools.catalog import _get_benchmarks

                result = _get_benchmarks(session, {})
            else:
                result = session.invoke_skill(skill_or_tool)
            return {"skill": skill_or_tool, "reason": reason, "result": result}
    # default skill path
    out = session.invoke_skill("spend-profiler")
    return {"skill": "spend-profiler", "reason": "default spend summary", "result": out}


def run_natural_language_query(
    session: ToolSessionContext,
    *,
    question: str,
    prefer: Prefer = "auto",
) -> Dict[str, Any]:
    """Route NL question to skill, aggregate, or SQL tier and execute."""
    question = (question or session.user_message or "").strip()
    if not question:
        raise ValueError("natural_language_query requires a question")

    store = _open_agent_store(session)
    if store is None:
        tier: Tier = "skill"
        result = _execute_skill_tier(session, question)
        return {
            "tier": tier,
            "question": question,
            "provenance": result,
            "fallback": "no_spend_store",
        }

    schema = load_spend_schema(store)
    valid_cols = {c["name"] for c in schema.get("columns", [])}
    tier = classify_nl_query_tier(question, prefer=prefer)

    if tier == "skill":
        provenance = _execute_skill_tier(session, question)
        append_audit_event(
            f"nl_query session={session.session_id} tier=skill q={question[:80]!r}"
        )
        return {"tier": tier, "question": question, "provenance": provenance}

    if tier == "aggregate":
        spec = _rule_based_aggregate_spec(question, valid_cols)
        if spec is None:
            spec = _llm_aggregate_or_sql(question, schema, tier="aggregate")
        if not isinstance(spec, dict):
            tier = "sql"
        else:
            try:
                result = store.aggregate(
                    group_by=spec.get("group_by") or ["category_name"],
                    metrics=spec.get("metrics"),
                    filters=spec.get("filters"),
                    limit=int(spec.get("limit") or 500),
                    order_by=spec.get("order_by"),
                )
                append_audit_event(
                    f"nl_query session={session.session_id} tier=aggregate "
                    f"rows={result.row_count}"
                )
                return {
                    "tier": tier,
                    "question": question,
                    "aggregate_spec": spec,
                    "result": result.to_dict(),
                }
            except SpendQueryError as exc:
                return {
                    "tier": tier,
                    "question": question,
                    "aggregate_spec": spec,
                    "error": str(exc),
                    "retry_hint": "Try natural_language_query with prefer=sql",
                }

    # Tier 3 — SQL with one repair attempt
    sql = _rule_based_aggregate_spec(question, valid_cols)
    if isinstance(sql, dict):
        # Build SQL from aggregate spec as fallback
        gb = ", ".join(sql["group_by"])
        metrics = sql.get("metrics") or {"spend": "SUM(amount)"}
        select = ", ".join([gb] + [f"{expr} AS {n}" for n, expr in metrics.items()])
        sql_text = f"SELECT {select} FROM spend GROUP BY {gb} ORDER BY spend DESC LIMIT {sql.get('limit', 50)}"
    else:
        sql_text = ""

    if not sql_text:
        llm_sql = _llm_aggregate_or_sql(question, schema, tier="sql")
        sql_text = str(llm_sql or "").strip()

    if not sql_text:
        sql_text = (
            "SELECT category_name, SUM(amount) AS spend, COUNT(*) AS lines "
            "FROM spend GROUP BY category_name ORDER BY spend DESC LIMIT 25"
        )

    try:
        result = store.run_sql(sql_text, limit=500)
    except SpendQueryError as first_err:
        repaired = _llm_aggregate_or_sql(
            f"{question}\n\nPrevious SQL failed: {first_err}\nFix the SQL.",
            schema,
            tier="sql",
        )
        if repaired and str(repaired).strip() != sql_text:
            try:
                result = store.run_sql(str(repaired).strip(), limit=500)
                sql_text = str(repaired).strip()
            except SpendQueryError as exc:
                return {"tier": "sql", "question": question, "sql": sql_text, "error": str(exc)}
        else:
            return {"tier": "sql", "question": question, "sql": sql_text, "error": str(first_err)}

    append_audit_event(
        f"nl_query session={session.session_id} tier=sql rows={result.row_count}"
    )
    return {
        "tier": "sql",
        "question": question,
        "sql": sql_text,
        "result": result.to_dict(),
    }
