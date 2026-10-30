"""Route general_qa chat turns to agent investigation vs one-shot synthesis."""
from __future__ import annotations

import re
from typing import Any

_INTERACTIVE_QA_CAPABILITIES = frozenset({
    "value_modeling",
    "benchmarking",
    "root_cause",
    "executive_narrative",
    "document_context",
})

_INTERACTIVE_QA_TOKENS = (
    "savings",
    "save money",
    "optimize",
    "optimise",
    "priorit",
    "opportunity",
    "opportunities",
    "value bridge",
    "value-at-the-table",
    "addressable",
    "business case",
    "npv",
    "payback",
    "benchmark",
    "peer",
    "compare",
    "root cause",
    "why ",
    "driver",
    "executive",
    "cfo",
    "board",
    "reduce cost",
    "cost reduction",
    "cost optimization",
    "cost optimisation",
    "renegotiat",
    "re-negotiat",
    "renewal",
    "initiative",
    "lever",
)

# Signals bespoke / ad-hoc analysis that benefits from the tool loop.
_AGENT_CHAT_TOKENS = (
    "what if",
    "what-if",
    "whatif",
    "scenario",
    "stress test",
    "sensitivity",
    "npv",
    "discount rate",
    "sql",
    "query",
    "filter",
    "where ",
    "having",
    "grew",
    "growth",
    "qoq",
    "yoy",
    "mom",
    "compare across",
    "run rate",
    "ad hoc",
    "ad-hoc",
    "custom",
    "supplier price",
    "cost driver",
    "cost-driver",
    "bounce back",
    "bounce-back",
    "execution rate",
    "timeline slip",
    "delayed",
    "macro",
    "commodity",
    "wage",
    "fx ",
    "pareto",
    "cohort",
    "movers",
    "temporal",
    "trend",
    "breakdown by",
    "group by",
    "rollup",
)


def should_use_cached_qa_fastpath(ctx: Any, msg: str) -> bool:
    """Return True only for simple spend lookups answerable from cached context."""
    caps = set(getattr(ctx, "query_capabilities", None) or [])
    if caps & _INTERACTIVE_QA_CAPABILITIES:
        return False
    lowered = (msg or "").lower()
    if any(token in lowered for token in _INTERACTIVE_QA_TOKENS):
        return False
    return True


def needs_agent_investigation(msg: str) -> bool:
    """True when the question likely needs tools (NL query, sensitivity, skills)."""
    lowered = (msg or "").lower()
    if any(token in lowered for token in _AGENT_CHAT_TOKENS):
        return True
    if re.search(r">\s*\d|%\s*(growth|increase|decline|drop|rise)", lowered):
        return True
    if re.search(r"\btop\s+\d+\s+\w+\s+by\b", lowered):
        return True
    return False


def is_simple_contextual_qa(ctx: Any, msg: str) -> bool:
    """One-shot synthesis is enough — cached spend context answers directly."""
    if needs_agent_investigation(msg):
        return False
    return should_use_cached_qa_fastpath(ctx, msg)


def should_use_agent_chat_path(ctx: Any, msg: str) -> bool:
    """True when a follow-up chat turn should run the agent tool loop first."""
    from app.opar.agent_runtime import agent_loop_available

    if not agent_loop_available():
        return False
    if not (
        getattr(ctx, "has_tabular_spend", False)
        or getattr(ctx, "spend_profile_ready", False)
        or getattr(ctx, "has_document_files", False)
    ):
        return False
    if is_simple_contextual_qa(ctx, msg):
        return False
    caps = set(getattr(ctx, "query_capabilities", None) or [])
    if caps & _INTERACTIVE_QA_CAPABILITIES:
        return True
    if any(token in (msg or "").lower() for token in _INTERACTIVE_QA_TOKENS):
        return True
    return needs_agent_investigation(msg)
