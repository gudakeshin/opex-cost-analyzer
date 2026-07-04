"""Natural-language spend query router — skills, structured aggregate, or SQL."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Tuple

from app.config import logger
from app.opar.tools.context import ToolSessionContext
from app.services.compliance import append_audit_event
from app.services.spend_schema import load_spend_schema
from app.services.spend_store import SpendQueryError, SpendStore

from app.opar.tools.catalog import _open_agent_store

Tier = Literal["skill", "aggregate", "sql"]
Prefer = Literal["auto", "skill", "aggregate", "sql"]

MAX_SQL_ATTEMPTS = 3
NL_SQL_MAX_TOKENS = 1200

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


def _schema_for_llm(schema: Dict[str, Any]) -> str:
    """Full schema payload for LLM SQL/aggregate generation (not truncated)."""
    return json.dumps(
        {
            "columns": schema.get("columns") or [],
            "sample_values": schema.get("sample_values") or {},
            "line_count": schema.get("line_count"),
            "total_spend": schema.get("total_spend"),
        },
        ensure_ascii=False,
    )


def _llm_aggregate_or_sql(
    question: str,
    schema: Dict[str, Any],
    *,
    tier: Literal["aggregate", "sql"],
    max_tokens: int | None = None,
) -> Dict[str, Any] | str | None:
    from app.opar.llm_provider import call_llm_structured
    from app.opar.llm_schemas import NL_AGGREGATE_SPEC_SCHEMA, NL_SQL_SCHEMA

    schema_blob = _schema_for_llm(schema)
    if tier == "aggregate":
        system = (
            "You translate natural-language spend questions into a JSON aggregate spec. "
            "Use only columns from the schema. Use fiscal_period not period."
        )
        user = f"Question: {question}\nSchema:\n{schema_blob}"
        data = call_llm_structured(
            system,
            user,
            NL_AGGREGATE_SPEC_SCHEMA,
            max_tokens=max_tokens or 800,
            skill_name="natural_language_query",
        )
        return data if isinstance(data, dict) else None

    system = (
        "You write a single DuckDB SELECT or WITH…SELECT against view `spend`. "
        "Use fiscal_period not period. Read-only; no DDL/DML."
    )
    user = f"Question: {question}\nSchema:\n{schema_blob}"
    data = call_llm_structured(
        system,
        user,
        NL_SQL_SCHEMA,
        max_tokens=max_tokens or NL_SQL_MAX_TOKENS,
        skill_name="natural_language_query",
    )
    if isinstance(data, dict):
        sql = str(data.get("sql") or "").strip()
        return sql or None
    return None


def _aggregate_spec_to_sql(spec: Dict[str, Any]) -> str:
    gb = ", ".join(spec["group_by"])
    metrics = spec.get("metrics") or {"spend": "SUM(amount)"}
    select = ", ".join([gb] + [f"{expr} AS {n}" for n, expr in metrics.items()])
    return (
        f"SELECT {select} FROM spend GROUP BY {gb} "
        f"ORDER BY {spec.get('order_by') or 'spend DESC'} LIMIT {int(spec.get('limit') or 50)}"
    )


def _execute_sql_with_repair_loop(
    store: SpendStore,
    question: str,
    schema: Dict[str, Any],
    *,
    initial_sql: str | None = None,
) -> Dict[str, Any]:
    """Generate SQL, execute, inspect errors, and revise up to MAX_SQL_ATTEMPTS times."""
    sql_text = (initial_sql or "").strip()
    last_err: Exception | None = None
    attempts: List[Dict[str, str]] = []

    for attempt in range(MAX_SQL_ATTEMPTS):
        if not sql_text:
            generated = _llm_aggregate_or_sql(question, schema, tier="sql")
            sql_text = str(generated or "").strip()
        if not sql_text:
            break
        try:
            result = store.run_sql(sql_text, limit=500)
            return {
                "tier": "sql",
                "question": question,
                "sql": sql_text,
                "result": result.to_dict(),
                "sql_attempts": attempt + 1,
                "repair_trace": attempts,
            }
        except SpendQueryError as exc:
            last_err = exc
            attempts.append({"sql": sql_text, "error": str(exc)})
            if attempt >= MAX_SQL_ATTEMPTS - 1:
                break
            repair_prompt = (
                f"{question}\n\nPrevious SQL failed:\n{sql_text}\n\nError: {exc}\n"
                f"Fix the SQL. Attempt {attempt + 2}/{MAX_SQL_ATTEMPTS}."
            )
            repaired = _llm_aggregate_or_sql(repair_prompt, schema, tier="sql")
            next_sql = str(repaired or "").strip()
            sql_text = next_sql if next_sql and next_sql != sql_text else ""

    fallback_sql = (
        "SELECT category_name, SUM(amount) AS spend, COUNT(*) AS lines "
        "FROM spend GROUP BY category_name ORDER BY spend DESC LIMIT 25"
    )
    if not sql_text:
        sql_text = fallback_sql
    return {
        "tier": "sql",
        "question": question,
        "sql": sql_text,
        "error": str(last_err) if last_err else "sql_generation_failed",
        "sql_attempts": len(attempts) + (1 if sql_text else 0),
        "repair_trace": attempts,
    }


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

    rule_spec = _rule_based_aggregate_spec(question, valid_cols)
    initial_sql = _aggregate_spec_to_sql(rule_spec) if isinstance(rule_spec, dict) else None
    if not initial_sql:
        initial_sql = str(_llm_aggregate_or_sql(question, schema, tier="sql") or "").strip() or None

    out = _execute_sql_with_repair_loop(store, question, schema, initial_sql=initial_sql)
    append_audit_event(
        f"nl_query session={session.session_id} tier=sql rows="
        f"{out.get('result', {}).get('row_count', 0) if isinstance(out.get('result'), dict) else 0}"
    )
    return out
