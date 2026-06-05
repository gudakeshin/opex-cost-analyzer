"""Deterministic general_qa lookup.

Single implementation of the keyword-driven "answer from cached spend outputs"
logic. Shared by the orchestrator (cached fast-path, before any pipeline runs)
and by reflect (the QA_LOOKUP response mode, after a profiler-only general_qa
turn). Keeping it here avoids a circular import (reflect <- orchestrator) and a
duplicated narrative producer.
"""

from __future__ import annotations

from typing import Any, Dict

from app.opar.category_resolver import match_category_from_query
from app.utils.inr_format import format_money

_FILE_FORMAT_MSG = (
    "Your spend file (.xlsx or .csv) should have these columns "
    "(exact names not required — I'll auto-detect similar names):\n\n"
    "| Column | Required? | Example values |\n"
    "|--------|-----------|----------------|\n"
    "| **Amount / Spend / Cost / Total** | ✅ Yes | 125000, 45000.50 |\n"
    "| **Supplier / Vendor / Payee** | Recommended | Infosys, AWS |\n"
    "| **Description / Memo / Line Item** | Recommended | Cloud hosting, Legal advisory |\n"
    "| **Department / BU / Business Unit** | Optional | Finance, IT, Marketing |\n"
    "| **Date / Invoice Date / Month** | Optional | 2024-03-15 |\n"
    "| **Country / Region / Geo** | Optional | India, APAC |\n\n"
    "Click the **📎** button in the chat to attach your file."
)

_CAPABILITIES_MSG = (
    "Here's what I can do once your spend data is uploaded:\n\n"
    "• **Spend Profiling** — classify your spend into standard categories and show totals.\n"
    "• **Peer Benchmarking** — compare each category against industry percentile benchmarks.\n"
    "• **Internal Benchmarking** — identify best-practice business units within your org.\n"
    "• **Heuristic Analysis** — apply outcomes-per-dollar norms (cost-per-employee, etc.).\n"
    "• **Value-at-the-Table** — build a savings opportunity matrix across all levers.\n"
    "• **Business Case** — generate a structured proposal with NPV, timeline, and risks.\n\n"
    "Upload a spend file using the 📎 button to get started."
)


def answer_general_qa(msg: str, validated: Dict[str, Any], currency: str = "USD") -> str:
    """Construct a contextual answer for general_qa when spend data is available."""
    fmt = lambda v: format_money(float(v or 0.0), currency)  # noqa: E731
    lowered = msg.lower()
    profile = validated.get("spend-profiler", {})
    doc_ctx = validated.get("document-contextualizer", {})
    categories = profile.get("category_profile", [])
    total = profile.get("total_spend", 0.0)

    asks_addressable = any(w in lowered for w in ["addressable", "addressability", "opportunity"])
    asks_share = any(w in lowered for w in ["share", "percent", "percentage", "mix"])
    asks_line_count = any(w in lowered for w in ["line item", "line items", "transactions", "count"])
    asks_discretionary = any(w in lowered for w in ["discretionary", "non discretionary", "non-discretionary"])
    asks_optimization = any(
        w in lowered
        for w in ["optimize", "optimise", "reduce cost", "cost optimization", "savings levers", "business lever"]
    )
    value_matrix = validated.get("value-bridge-calculator", {}).get("value_matrix", [])

    matched_cat = match_category_from_query(msg, categories)
    if matched_cat:
        spend = float(matched_cat.get("spend", 0.0) or 0.0)
        pct = (spend / total * 100) if total else 0.0
        lines = int(matched_cat.get("line_count", 0) or 0)
        addressable = float(matched_cat.get("addressable_spend", 0.0) or 0.0)
        addressable_pct_cat = (addressable / spend * 100) if spend else 0.0
        discretionary = float(matched_cat.get("discretionary_spend", 0.0) or 0.0)
        nondisc = float(matched_cat.get("non_discretionary_spend", 0.0) or 0.0)
        nm = matched_cat.get("category_name", matched_cat.get("category_id", "Selected category"))

        if asks_addressable:
            return (
                f"**{nm}** has **{fmt(addressable)}** modeled as addressable spend "
                f"({addressable_pct_cat:.1f}% of that category; total category spend {fmt(spend)})."
            )
        if asks_discretionary:
            disc_pct = (discretionary / spend * 100) if spend else 0.0
            nondisc_pct = (nondisc / spend * 100) if spend else 0.0
            return (
                f"**{nm}** discretionary mix: discretionary **{fmt(discretionary)}** ({disc_pct:.1f}%), "
                f"non-discretionary **{fmt(nondisc)}** ({nondisc_pct:.1f}%)."
            )
        if asks_line_count:
            return f"**{nm}** contains **{lines:,}** line item(s), with total spend **{fmt(spend)}**."
        if asks_share:
            return f"**{nm}** represents **{fmt(spend)}** ({pct:.1f}% of total spend)."
        if asks_optimization and isinstance(value_matrix, list) and value_matrix:
            row = next(
                (r for r in value_matrix if str(r.get("category_name", "")).lower() == str(nm).lower() or str(r.get("category_id", "")).lower() == str(matched_cat.get("category_id", "")).lower()),
                None,
            )
            if row:
                lever = str(row.get("lever", "optimization")).replace("_", " ")
                mid = float(row.get("deduped_mid_savings", 0.0) or 0.0)
                return (
                    f"**{nm} optimization focus**\n"
                    f"- Modeled lever: **{lever}**\n"
                    f"- Modeled value-release potential: **{fmt(mid)}**\n"
                    f"- Business rationale: address root-cause bottlenecks and shift spend to controlled commercial terms."
                    f"\n- Ask for a **business case** if you want NPV/payback economics."
                )
        return (
            f"**{nm}** accounts for **{fmt(spend)}** ({pct:.1f}% of total spend) "
            f"across {lines} line item(s)."
        )

    if any(w in lowered for w in ["addressable", "addressability", "opportunity"]):
        addr_total = sum(float(c.get("addressable_spend", 0.0) or 0.0) for c in categories)
        addr_pct_total = (addr_total / total * 100) if total else 0.0
        top_addr = sorted(categories, key=lambda c: float(c.get("addressable_spend", 0.0) or 0.0), reverse=True)[:3]
        lines_out = [
            f"Total modeled **addressable spend** is **{fmt(addr_total)}** ({addr_pct_total:.1f}% of total spend)."
        ]
        if top_addr:
            lines_out.append("Top addressable categories:")
            for i, c in enumerate(top_addr, 1):
                nm = c.get("category_name", c.get("category_id", "Category"))
                amt = float(c.get("addressable_spend", 0.0) or 0.0)
                lines_out.append(f"  {i}. **{nm}**: {fmt(amt)}")
        return "\n".join(lines_out)

    # Total / biggest / top categories
    if any(w in lowered for w in ["total", "biggest", "largest", "top", "highest", "most", "overview"]):
        if categories:
            top = sorted(categories, key=lambda c: c.get("spend", 0), reverse=True)[:5]
            lines_out = [f"Your total spend is **{fmt(total)}**. Top categories:"]
            for i, c in enumerate(top, 1):
                pct = (c.get("spend", 0) / total * 100) if total else 0.0
                lines_out.append(f"  {i}. **{c.get('category_name')}**: {fmt(c.get('spend', 0))} ({pct:.1f}%)")
            return "\n".join(lines_out)

    # Category list
    if any(w in lowered for w in ["categor", "how many", "list", "show me", "what spend"]):
        cat_list = ", ".join(c.get("category_name", "") for c in categories[:8])
        suffix = " and more." if len(categories) > 8 else "."
        return (
            f"I've classified your spend into **{len(categories)} categories**: "
            f"{cat_list}{suffix}"
        )

    # File format question
    if any(w in lowered for w in ["column", "format", "template", "header", "field"]):
        return _FILE_FORMAT_MSG

    # Capabilities question
    if any(w in lowered for w in ["can you", "what can", "capabilities", "what do", "help me"]):
        return _CAPABILITIES_MSG

    # Generic: quote available summary
    has_spend_profile = bool(categories) or float(total or 0) > 0
    if has_spend_profile:
        return (
            f"Based on your uploaded data: total spend is **{fmt(total)}** across "
            f"**{len(categories)} spend categories**. "
            "Ask me to **benchmark**, run **value-at-the-table** analysis, "
            "or **generate a business case**."
        )

    # Document-only context (e.g. txt/docx/pdf with policies, contracts, operating model notes)
    if doc_ctx:
        constraints = doc_ctx.get("constraints", [])
        context_summary = str(doc_ctx.get("context_summary", "")).strip()
        preview = context_summary[:700] + ("..." if len(context_summary) > 700 else "")
        if "summary" in lowered or "summarize" in lowered or "key points" in lowered:
            if constraints:
                bullets = "\n".join([f"• {c}" for c in constraints[:5]])
                return f"Here is a summary of uploaded document context:\n\n{bullets}\n\n**Context excerpt:**\n{preview}"
            return f"Here is a summary of uploaded document context:\n\n{preview or 'No extractable text was found.'}"
        if constraints:
            bullets = "\n".join([f"• {c}" for c in constraints[:5]])
            return f"I captured semantic context from your uploaded documents:\n\n{bullets}\n\nAsk for a summary, risks, or policy constraints in detail."
        return (
            "I processed your uploaded document text and stored it as contextual input for analysis. "
            "Ask me to summarize key points, constraints, or implications."
        )

    return (
        "I'm ready to help. Upload your spend file using the 📎 button, then ask me to "
        "benchmark, calculate savings opportunities, or generate a business case."
    )
