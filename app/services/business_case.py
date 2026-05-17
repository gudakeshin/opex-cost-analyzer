from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict

from docx import Document

from app.config import OUTPUT_DIR


def _top_categories_from_profile(outputs: Dict[str, Any], limit: int = 3) -> list[str]:
    profile = outputs.get("spend-profiler", {})
    cats = profile.get("category_profile", [])
    return [c.get("category_name", c.get("category_id", "")) for c in cats[:limit] if c.get("category_name") or c.get("category_id")]


def _dynamic_risks(outputs: Dict[str, Any]) -> list[str]:
    risks: list[str] = []
    ctx = outputs.get("document-contextualizer", {})
    for constraint in ctx.get("constraints", []):
        risks.append(str(constraint))
    peer = outputs.get("peer-benchmarker", {})
    metadata = peer.get("benchmark_metadata", {}) if isinstance(peer, dict) else {}
    if metadata:
        note = metadata.get("data_quality_note", "")
        if note:
            risks.append(f"Benchmark data quality: {note}")
        score = metadata.get("specificity_score")
        if score is not None and float(score) < 0.7:
            risks.append(f"Benchmark specificity score {score:.2f} — consider acquiring a targeted licensed dataset.")
    checks = outputs.get("data-validator", {}).get("checks", {})
    if checks and not all(bool(v) for v in checks.values()):
        risks.append("Data validation checks indicate potential reliability gaps.")
    if not risks:
        risks.append("No critical model risks detected from current uploaded data.")
    return risks


def _build_financial_projections(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Y1/Y2/Y3 table from savings_modeler initiatives."""
    initiatives = outputs.get("savings-modeler", {}).get("initiatives", [])
    gross = [0.0, 0.0, 0.0]
    cta = [0.0, 0.0, 0.0]
    net = [0.0, 0.0, 0.0]
    for init in initiatives:
        for i, k in enumerate(["y1", "y2", "y3"]):
            gross[i] += float(init.get("gross_savings", {}).get(k, 0.0))
            cta[i] += float(init.get("cost_to_achieve", {}).get(k, 0.0))
            net[i] += float(init.get("net_savings", {}).get(k, 0.0))
    cum = [net[0], net[0] + net[1], net[0] + net[1] + net[2]]
    return {
        "headers": ["", "Year 1", "Year 2", "Year 3", "3-Year Total"],
        "rows": [
            ["Gross Savings"] + [f"${v:,.0f}" for v in gross] + [f"${sum(gross):,.0f}"],
            ["Cost to Achieve"] + [f"(${v:,.0f})" for v in cta] + [f"(${sum(cta):,.0f})"],
            ["Net Savings"] + [f"${v:,.0f}" for v in net] + [f"${sum(net):,.0f}"],
            ["Cumulative Net"] + [f"${v:,.0f}" for v in cum] + [""],
        ],
    }


def _build_irr_summary(outputs: Dict[str, Any]) -> list[str]:
    lines_out = []
    for init in outputs.get("savings-modeler", {}).get("initiatives", []):
        irr = init.get("irr_pct")
        if irr is not None:
            lines_out.append(
                f"{init.get('category_name', init.get('category_id', '?'))}: "
                f"IRR = {irr}%, Payback = {init.get('payback_months', '?')} months"
            )
    return lines_out or ["No CTA-based initiatives; IRR not applicable."]


def _build_do_nothing(conf: Dict[str, Any]) -> str:
    mid = float(conf.get("mid", 0.0))
    return (
        f"Cost of inaction over 3 years: ${mid:,.0f} in foregone savings. "
        f"Competitors operating at P25 efficiency hold a structural cost advantage "
        f"of approximately ${mid / 3:,.0f} per annum."
    )


def _build_assumption_register_section(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Pull assumption register data into business-case section."""
    ar = outputs.get("assumption-register", {})
    if not ar:
        return {"available": False, "note": "Run assumption-register skill to populate this section."}
    return {
        "available": True,
        "portfolio_aqs": ar.get("portfolio_aqs"),
        "method": ar.get("method"),
        "initiative_count": len(ar.get("initiative_assumptions", [])),
        "gate2_threshold": 0.65,
        "gate2_status": (
            "PASS" if (ar.get("portfolio_aqs") or 0) >= 0.65 else "BLOCKED — CFO override required"
        ),
        "p10_p50_p90_summary": [
            {
                "initiative": ia.get("initiative_id"),
                "p10": ia.get("p10"),
                "p50": ia.get("p50"),
                "p90": ia.get("p90"),
                "aqs": ia.get("composite_score"),
            }
            for ia in ar.get("initiative_assumptions", [])[:5]
        ],
    }


def _build_rag_section(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """Risk-adjusted growth: scenario floor and macro sensitivity."""
    sm = outputs.get("scenario-modeler", {})
    return {
        "macro_sensitivity": sm.get("macro_sensitivity_rating", "unknown"),
        "downside_floor": sm.get("downside_floor"),
        "downside_pct_of_base": sm.get("downside_floor_pct_of_base"),
        "p10_savings": sm.get("p10_savings"),
        "p90_savings": sm.get("p90_savings"),
    }


def build_business_case(analysis: Dict[str, Any], template: str = "detailed_proposal") -> Dict[str, Any]:
    outputs = analysis.get("skill_outputs", {})
    bridge = outputs.get("value-bridge-calculator", {})
    conf = bridge.get("confidence_bands", {})
    company_name = analysis.get("company_name") or "Client"
    top_categories = _top_categories_from_profile(outputs)
    top_text = ", ".join(top_categories) if top_categories else "top identified categories"

    sections = {
        "executive_summary": (
            f"{company_name} has an estimated savings opportunity of "
            f"${conf.get('mid', 0):,.0f} (mid-case), ranging from ${conf.get('low', 0):,.0f} "
            f"to ${conf.get('high', 0):,.0f}."
        ),
        "current_state": f"Current-state baseline built from uploaded spend and contextual documents, with focus on {top_text}.",
        "financial_projections": _build_financial_projections(outputs),
        "irr_summary": _build_irr_summary(outputs),
        "do_nothing_comparison": _build_do_nothing(conf),
        "savings_opportunity": bridge.get("value_matrix", []),
        "implementation_approach": [
            f"Wave 1: Execute initiatives in {top_text}.",
            "Wave 2: Extend controls to remaining categories with measurable variance.",
            "Wave 3: Institutionalize governance and monthly tracking in pipeline.",
        ],
        "risk_assessment": _dynamic_risks(outputs),
        "assumption_register": _build_assumption_register_section(outputs),
        "rag_factors": _build_rag_section(outputs),
    }
    return {"template": template, "generated_on": str(date.today()), "sections": sections}


def _render_table(doc: Document, table_data: Dict[str, Any]) -> None:
    headers = table_data.get("headers", [])
    rows = table_data.get("rows", [])
    if not headers or not rows:
        return
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for j, h in enumerate(headers):
        table.rows[0].cells[j].text = str(h)
    for i, row_data in enumerate(rows):
        for j, cell_val in enumerate(row_data[: len(headers)]):
            table.rows[i + 1].cells[j].text = str(cell_val)
    doc.add_paragraph("")


def export_docx(business_case: Dict[str, Any], filename: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    doc = Document()
    doc.add_heading("OpEx Business Case", level=0)
    doc.add_paragraph(f"Generated: {business_case.get('generated_on')}")
    for key, value in business_case.get("sections", {}).items():
        doc.add_heading(key.replace("_", " ").title(), level=1)
        if isinstance(value, str):
            doc.add_paragraph(value)
        elif isinstance(value, dict) and "headers" in value and "rows" in value:
            _render_table(doc, value)
        elif isinstance(value, list):
            for item in value:
                doc.add_paragraph(str(item), style="List Bullet")
        else:
            doc.add_paragraph(str(value))
    doc.save(path)
    return path


def export_pdf_like_text(business_case: Dict[str, Any], filename: str) -> Path:
    """
    Lightweight fallback export that produces a printable report text file.
    This keeps the endpoint stable without requiring external PDF binaries.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    lines = [f"OpEx Business Case - {business_case.get('generated_on')}"]
    for key, value in business_case.get("sections", {}).items():
        lines.append("")
        lines.append(key.replace("_", " ").upper())
        lines.append("-" * 40)
        if isinstance(value, dict) and "headers" in value and "rows" in value:
            headers = value.get("headers", [])
            lines.append(" | ".join(str(h) for h in headers))
            lines.append("-" * 60)
            for row in value.get("rows", []):
                lines.append(" | ".join(str(c) for c in row))
        elif isinstance(value, list):
            lines.extend([f"- {item}" for item in value])
        else:
            lines.append(str(value))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
