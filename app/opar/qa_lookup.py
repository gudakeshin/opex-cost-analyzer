"""Deterministic general_qa lookup.

Single implementation of the keyword-driven "answer from cached spend outputs"
logic. Shared by the orchestrator (cached fast-path, before any pipeline runs)
and by reflect (the QA_LOOKUP response mode, after a profiler-only general_qa
turn). Keeping it here avoids a circular import (reflect <- orchestrator) and a
duplicated narrative producer.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from app.opar.category_resolver import match_category_from_query
from app.utils.inr_format import format_money

_SAVINGS_QUERY_TOKENS = (
    "savings",
    "save money",
    "priorit",
    "opportunity",
    "opportunities",
    "value bridge",
    "value-at-the-table",
    "addressable",
    "npv",
    "payback",
    "reduce cost",
    "cost reduction",
)

_INTERACTIVE_QA_CAPABILITIES = frozenset({
    "value_modeling",
    "benchmarking",
    "root_cause",
    "executive_narrative",
})

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


def _is_portfolio_savings_query(msg: str) -> bool:
    """True for cross-category savings prioritization asks (not category drill-down)."""
    lowered = (msg or "").lower()
    return any(
        token in lowered
        for token in (
            "priorit",
            "which savings",
            "what savings",
            "top savings",
            "savings opportunities",
            "savings opportunity",
            "where should we save",
            "where to save",
        )
    )


def is_interactive_savings_query(
    msg: str,
    capabilities: Optional[Iterable[str]] = None,
) -> bool:
    """True when the message needs advisory/SME narrative, not a canned lookup."""
    caps = set(capabilities or [])
    if caps & _INTERACTIVE_QA_CAPABILITIES:
        return True
    lowered = (msg or "").lower()
    return any(token in lowered for token in _SAVINGS_QUERY_TOKENS)


def build_sme_critique_section(validated: Dict[str, Any], currency: str = "USD") -> str:
    """Render deterministic SME qualification block from sme-critique skill output."""
    sme = validated.get("sme-critique", {})
    if not isinstance(sme, dict):
        return ""
    fmt = lambda v: format_money(float(v or 0.0), currency)  # noqa: E731
    summary = sme.get("critique_summary", {}) if isinstance(sme.get("critique_summary"), dict) else {}
    critiques = sme.get("initiative_critiques", []) if isinstance(sme.get("initiative_critiques"), list) else []

    ready = int(summary.get("ready_count", 0) or 0)
    probe = int(summary.get("probe_count", 0) or 0)
    insufficient = int(summary.get("insufficient_count", 0) or 0)
    savings_ready = float(summary.get("savings_ready", 0) or 0)
    savings_probe = float(summary.get("savings_probe", 0) or 0)
    savings_insufficient = float(summary.get("savings_insufficient", 0) or 0)

    if not critiques and ready == 0 and probe == 0 and insufficient == 0:
        return ""

    lines: list[str] = ["**SME qualification (before calling this a value case)**"]
    if ready > 0 and savings_ready > 0:
        lines.append(
            f"- Ready for business case: **{fmt(savings_ready)}** ({ready} initiative{'s' if ready != 1 else ''})"
        )
    answered_families = int(summary.get("answered_probe_families", 0) or 0)
    if answered_families > 0:
        lines.append(
            f"- User-confirmed assumptions: **{answered_families}** probe famil{'ies' if answered_families != 1 else 'y'} recorded"
        )
    if probe > 0 and savings_probe > 0:
        lines.append(
            f"- Needs probing first: **{fmt(savings_probe)}** ({probe} initiative{'s' if probe != 1 else ''})"
        )
    if insufficient > 0 and savings_insufficient > 0:
        lines.append(
            f"- Insufficient data: **{fmt(savings_insufficient)}** ({insufficient} initiative{'s' if insufficient != 1 else ''})"
        )

    flagged = [
        c for c in critiques
        if isinstance(c, dict) and str(c.get("sme_verdict", "")) in ("probe_first", "insufficient_data")
    ]
    for critique in flagged[:3]:
        cat = str(critique.get("category_name") or critique.get("category_id") or "Category")
        risk = str(critique.get("critical_risk") or "").strip()
        if risk:
            lines.append(f"- **{cat}**: {risk}")
        probes = critique.get("probe_questions", []) if isinstance(critique.get("probe_questions"), list) else []
        if probes and isinstance(probes[0], dict):
            q = str(probes[0].get("question") or "").strip()
            why = str(probes[0].get("why_critical") or "").strip()
            if q:
                lines.append(f"  - Probe: {q}")
            if why:
                lines.append(f"  - Why it matters: {why}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _answer_savings_priorities(msg: str, validated: Dict[str, Any], currency: str) -> Optional[str]:
    """Top savings initiatives with SME qualification when value model exists in cache."""
    fmt = lambda v: format_money(float(v or 0.0), currency)  # noqa: E731
    value_matrix = validated.get("value-bridge-calculator", {}).get("value_matrix", [])
    if not isinstance(value_matrix, list) or not value_matrix:
        savings_model = validated.get("savings-modeler", {})
        initiatives = savings_model.get("initiatives", []) if isinstance(savings_model, dict) else []
        if not initiatives:
            return None
        rows = sorted(
            [i for i in initiatives if isinstance(i, dict)],
            key=lambda r: float((r.get("net_savings") or {}).get("total_3yr", 0) or 0),
            reverse=True,
        )[:3]
        lines = ["**Top modeled savings priorities**"]
        for i, row in enumerate(rows, 1):
            cat = str(row.get("category_name") or row.get("category_id") or "Category")
            lever = str(row.get("lever_name") or row.get("lever") or "optimization").replace("_", " ")
            amt = float((row.get("net_savings") or {}).get("total_3yr", 0) or 0)
            conf = str(row.get("confidence") or "medium")
            lines.append(f"{i}. **{cat}** — {fmt(amt)} via {lever} (confidence: {conf})")
    else:
        rows = sorted(
            [r for r in value_matrix if isinstance(r, dict)],
            key=lambda r: float(r.get("deduped_mid_savings", 0) or 0),
            reverse=True,
        )[:3]
        lines = ["**Top modeled savings priorities**"]
        for i, row in enumerate(rows, 1):
            cat = str(row.get("category_name") or row.get("category_id") or "Category")
            lever = str(row.get("lever") or "optimization").replace("_", " ")
            mid = float(row.get("deduped_mid_savings", 0) or 0)
            conf = str(row.get("confidence") or "medium")
            lines.append(f"{i}. **{cat}** — {fmt(mid)} mid-case via {lever} (confidence: {conf})")

    bands = validated.get("value-bridge-calculator", {}).get("confidence_bands", {})
    if isinstance(bands, dict) and bands.get("mid"):
        lines.append(
            f"\nPortfolio mid-case: **{fmt(bands.get('mid', 0))}** "
            f"(low {fmt(bands.get('low', 0))}, high {fmt(bands.get('high', 0))})."
        )

    sme_block = build_sme_critique_section(validated, currency)
    if sme_block:
        lines.append("")
        lines.append(sme_block)

    lowered = msg.lower()
    if "business case" in lowered:
        lines.append("\nAsk to **generate a business case** for NPV and payback detail.")
    return "\n".join(lines)


_SUPPLIER_TOKENS = ("supplier", "vendor", "by supplier", "by vendor", "payee")
_GEO_TOKENS = ("geo", "geograph", "region", "country", "by country", "by region")
_LEVER_DETAIL_TOKENS = (
    "renegotiat",
    "re-negotiat",
    "renewal",
    "contract",
    "lever",
    "initiative",
    "commercial term",
    "should-cost",
)


def _asks_lever_or_contract_detail(msg: str) -> bool:
    lowered = (msg or "").lower()
    return any(token in lowered for token in _LEVER_DETAIL_TOKENS)


def _target_lever_from_query(msg: str) -> str | None:
    """Map a natural-language lever ask to a canonical lever id when possible."""
    lowered = (msg or "").lower()
    if "renegotiat" in lowered or "re-negotiat" in lowered:
        return "contract_renegotiation"
    if "supplier consolidat" in lowered:
        return "supplier_consolidation"
    if "maverick" in lowered or "guided buying" in lowered:
        return "maverick_compliance"
    if "demand management" in lowered or "demand challenge" in lowered:
        return "demand_management"
    if "payment term" in lowered or "dpo" in lowered:
        return "payment_terms"
    return None


def _row_matches_lever_query(
    row: Dict[str, Any],
    *,
    target_lever: str | None,
    msg: str,
) -> bool:
    lever = str(row.get("lever") or "").lower()
    lever_name = str(row.get("lever_name") or "").lower()
    if target_lever:
        return lever == target_lever or target_lever.replace("_", " ") in lever_name
    lowered = (msg or "").lower()
    if "contract" in lowered:
        return "contract" in lever_name or lever == "contract_renegotiation"
    if "renewal" in lowered:
        return "renewal" in lever_name or "contract" in lever_name
    return False


def _answer_lever_or_contract_details(
    msg: str,
    validated: Dict[str, Any],
    currency: str,
) -> Optional[str]:
    """Answer lever / contract / initiative detail asks from modeled outputs."""
    fmt = lambda v: format_money(float(v or 0.0), currency)  # noqa: E731
    target_lever = _target_lever_from_query(msg)
    matched_cat = match_category_from_query(
        msg,
        validated.get("spend-profiler", {}).get("category_profile", []),
    )
    cat_id = str(matched_cat.get("category_id") or "") if matched_cat else ""
    cat_name = str(matched_cat.get("category_name") or matched_cat.get("category_id") or "") if matched_cat else ""

    savings_model = validated.get("savings-modeler", {})
    initiatives = (
        savings_model.get("initiatives", [])
        if isinstance(savings_model, dict) and isinstance(savings_model.get("initiatives"), list)
        else []
    )
    filtered_initiatives = [
        i
        for i in initiatives
        if isinstance(i, dict)
        and _row_matches_lever_query(i, target_lever=target_lever, msg=msg)
        and (not cat_id or str(i.get("category_id") or "") == cat_id)
    ]

    value_matrix = validated.get("value-bridge-calculator", {}).get("value_matrix", [])
    if not isinstance(value_matrix, list):
        value_matrix = []
    filtered_matrix = [
        r
        for r in value_matrix
        if isinstance(r, dict)
        and _row_matches_lever_query(r, target_lever=target_lever, msg=msg)
        and (not cat_id or str(r.get("category_id") or "") == cat_id)
    ]

    contract_skill = validated.get("contract-lifecycle-manager", {})
    renewals = (
        contract_skill.get("renewal_alerts", [])
        if isinstance(contract_skill, dict) and isinstance(contract_skill.get("renewal_alerts"), list)
        else []
    )

    doc_ctx = validated.get("document-contextualizer", {})
    constraints = (
        doc_ctx.get("constraints", [])
        if isinstance(doc_ctx, dict) and isinstance(doc_ctx.get("constraints"), list)
        else []
    )
    contract_constraints = [
        c for c in constraints
        if isinstance(c, str) and any(w in c.lower() for w in ("contract", "renewal", "renegotiat", "term"))
    ]

    if not filtered_initiatives and not filtered_matrix and not renewals and not contract_constraints:
        if initiatives or value_matrix:
            lever_label = (target_lever or "requested lever").replace("_", " ")
            return (
                f"No modeled initiatives matched **{lever_label}** in the current session outputs. "
                "Run **value-at-the-table** analysis to refresh the savings model, "
                "or ask about a specific category where renegotiation may apply."
            )
        return (
            "I don't have modeled **contract renegotiation** or savings-lever detail in this session yet. "
            "Run **value-at-the-table** analysis (or ask me to **calculate savings opportunities**) "
            "so initiatives and contract levers are modeled from your spend data."
        )

    title = "**Contract renegotiation details**"
    if target_lever and target_lever != "contract_renegotiation":
        title = f"**{target_lever.replace('_', ' ').title()} details**"
    if cat_name:
        title += f" — {cat_name}"

    lines = [title]

    if filtered_initiatives:
        lines.append("\n**Modeled initiatives**")
        for i, row in enumerate(filtered_initiatives[:6], 1):
            cat = str(row.get("category_name") or row.get("category_id") or "Category")
            lever = str(row.get("lever_name") or row.get("lever") or "optimization").replace("_", " ")
            amt = float((row.get("net_savings") or {}).get("total_3yr", 0) or row.get("annualized_run_rate_savings", 0) or 0)
            conf = str(row.get("confidence") or "medium")
            horizon = str(row.get("horizon") or "").strip()
            suffix = f", horizon: {horizon}" if horizon else ""
            lines.append(f"{i}. **{cat}** — {fmt(amt)} via {lever} (confidence: {conf}{suffix})")

    if filtered_matrix:
        lines.append("\n**Value bridge (deduped mid-case)**")
        for i, row in enumerate(filtered_matrix[:6], 1):
            cat = str(row.get("category_name") or row.get("category_id") or "Category")
            lever = str(row.get("lever") or "optimization").replace("_", " ")
            mid = float(row.get("deduped_mid_savings", 0) or 0)
            payback = int(row.get("payback_months", 0) or 0)
            payback_txt = f", payback {payback} mo" if payback else ""
            lines.append(f"{i}. **{cat}** — {fmt(mid)} via {lever}{payback_txt}")

    if renewals:
        lines.append("\n**Contract renewal alerts**")
        for i, alert in enumerate(renewals[:5], 1):
            if not isinstance(alert, dict):
                continue
            supplier = str(alert.get("supplier") or "Supplier")
            alert_type = str(alert.get("alert_type") or alert.get("status") or "renewal")
            spend = float(alert.get("annual_spend", 0) or alert.get("spend", 0) or 0)
            days = alert.get("days_to_expiry")
            expiry_note = f", {days} days to expiry" if isinstance(days, int) else ""
            lines.append(f"{i}. **{supplier}** — {alert_type}{expiry_note} ({fmt(spend)} annual spend)")

    if contract_constraints:
        lines.append("\n**Document constraints**")
        for bullet in contract_constraints[:5]:
            lines.append(f"- {bullet}")

    sme_block = build_sme_critique_section(validated, currency)
    if sme_block:
        lines.append("")
        lines.append(sme_block)

    return "\n".join(lines)


def _asks_supplier(lowered: str) -> bool:
    return any(w in lowered for w in _SUPPLIER_TOKENS)


def _asks_geo(lowered: str) -> bool:
    return any(w in lowered for w in _GEO_TOKENS)


def _parse_top_limit(msg: str, default: int = 10) -> int:
    match = re.search(r"\btop\s+(\d+)\b", (msg or "").lower())
    if match:
        return max(1, min(int(match.group(1)), 25))
    return default


def aggregate_portfolio_suppliers(
    categories: Iterable[Dict[str, Any]],
    *,
    limit: int = 10,
    total_spend: float = 0.0,
) -> List[Dict[str, Any]]:
    """Roll up per-category top_suppliers into a portfolio-wide ranking."""
    totals: Dict[str, float] = {}
    for cat in categories:
        for sup in cat.get("top_suppliers") or []:
            if not isinstance(sup, dict):
                continue
            name = str(sup.get("supplier") or "").strip()
            if not name:
                continue
            totals[name] = totals.get(name, 0.0) + float(sup.get("spend", 0) or 0.0)
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]
    denom = float(total_spend or 0) or sum(totals.values())
    return [
        {
            "supplier": name,
            "spend": spend,
            "share_of_total": (spend / denom * 100) if denom else 0.0,
        }
        for name, spend in ranked
    ]


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
    asks_savings = is_interactive_savings_query(msg)
    asks_supplier = _asks_supplier(lowered)
    asks_geo = _asks_geo(lowered)
    value_matrix = validated.get("value-bridge-calculator", {}).get("value_matrix", [])

    if _is_portfolio_savings_query(msg):
        savings_answer = _answer_savings_priorities(msg, validated, currency)
        if savings_answer:
            return savings_answer

    if _asks_lever_or_contract_detail(msg):
        lever_answer = _answer_lever_or_contract_details(msg, validated, currency)
        if lever_answer:
            return lever_answer

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
        if asks_supplier:
            suppliers = matched_cat.get("top_suppliers", []) if isinstance(matched_cat.get("top_suppliers"), list) else []
            if suppliers:
                lines_out = [f"**{nm}** spend by supplier (total category spend **{fmt(spend)}**):"]
                for i, sup in enumerate(suppliers[:10], 1):
                    sname = sup.get("supplier", "Unknown")
                    sspend = float(sup.get("spend", 0.0) or 0.0)
                    share = float(sup.get("share_of_category", 0.0) or 0.0)
                    lines_out.append(f"  {i}. **{sname}**: {fmt(sspend)} ({share:.1f}% of category)")
                return "\n".join(lines_out)
            return (
                f"**{nm}** has **{fmt(spend)}** total spend, but supplier-level detail is not available "
                "in the uploaded file. Ensure your spend file includes a Supplier/Vendor column."
            )
        if asks_geo:
            geos = matched_cat.get("top_geos", []) if isinstance(matched_cat.get("top_geos"), list) else []
            if geos:
                lines_out = [f"**{nm}** spend by geography (total category spend **{fmt(spend)}**):"]
                for i, g in enumerate(geos[:8], 1):
                    gname = g.get("geo", g.get("region", "Unknown"))
                    gspend = float(g.get("spend", 0.0) or 0.0)
                    share = float(g.get("share_of_category", 0.0) or 0.0)
                    lines_out.append(f"  {i}. **{gname}**: {fmt(gspend)} ({share:.1f}% of category)")
                return "\n".join(lines_out)
            return (
                f"**{nm}** has **{fmt(spend)}** total spend, but geography breakdown is not available "
                "in the uploaded file. Add a Country/Region column to enable geo analysis."
            )
        if asks_optimization and isinstance(value_matrix, list) and value_matrix:
            row = next(
                (r for r in value_matrix if str(r.get("category_name", "")).lower() == str(nm).lower() or str(r.get("category_id", "")).lower() == str(matched_cat.get("category_id", "")).lower()),
                None,
            )
            if row:
                lever = str(row.get("lever", "optimization")).replace("_", " ")
                mid = float(row.get("deduped_mid_savings", 0.0) or 0.0)
                sme_block = build_sme_critique_section(validated, currency)
                out = (
                    f"**{nm} optimization focus**\n"
                    f"- Modeled lever: **{lever}**\n"
                    f"- Modeled value-release potential: **{fmt(mid)}**\n"
                    f"- Business rationale: address root-cause bottlenecks and shift spend to controlled commercial terms."
                    f"\n- Ask for a **business case** if you want NPV/payback economics."
                )
                if sme_block:
                    out += f"\n\n{sme_block}"
                return out
        return (
            f"**{nm}** accounts for **{fmt(spend)}** ({pct:.1f}% of total spend) "
            f"across {lines} line item(s)."
        )

    if asks_supplier:
        limit = _parse_top_limit(msg)
        suppliers = aggregate_portfolio_suppliers(categories, limit=limit, total_spend=total)
        if suppliers:
            lines_out = [f"Top {len(suppliers)} suppliers by spend (total portfolio **{fmt(total)}**):"]
            for i, sup in enumerate(suppliers, 1):
                sname = sup.get("supplier", "Unknown")
                sspend = float(sup.get("spend", 0.0) or 0.0)
                share = float(sup.get("share_of_total", 0.0) or 0.0)
                lines_out.append(f"  {i}. **{sname}**: {fmt(sspend)} ({share:.1f}% of total)")
            return "\n".join(lines_out)
        return (
            "Supplier-level detail is not available in the uploaded file. "
            "Ensure your spend file includes a Supplier/Vendor column."
        )

    if asks_savings or asks_optimization:
        savings_answer = _answer_savings_priorities(msg, validated, currency)
        if savings_answer:
            return savings_answer

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

    # Total / biggest / top categories (skip when user asked for supplier/geo breakdown)
    if not asks_geo and any(
        w in lowered
        for w in ["total", "biggest", "largest", "top", "highest", "most", "overview", "summarize", "summary", "concentration"]
    ):
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
