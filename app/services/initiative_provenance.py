"""Build assumption → source-data trace for Cost Room initiative drill-down."""
from __future__ import annotations

from typing import Any, Dict, List

from app.routers._shared import read_manifest


def _match_category(line: Dict[str, Any], category: str) -> bool:
    cat = (category or "").strip().lower()
    if not cat:
        return False
    for key in ("category_name", "category_id"):
        val = str(line.get(key) or "").strip().lower()
        if not val:
            continue
        if val == cat or cat in val or val in cat:
            return True
    return False


def _initiative_assumptions(analysis: Dict[str, Any], initiative: Dict[str, Any]) -> List[Dict[str, Any]]:
    direct = initiative.get("assumptions") or []
    if direct:
        return [a if isinstance(a, dict) else {"text": str(a)} for a in direct]

    ar = (analysis.get("skill_outputs") or {}).get("assumption-register") or {}
    cat = initiative.get("category")
    lever = initiative.get("lever")
    matched: List[Dict[str, Any]] = []
    for ia in ar.get("initiative_assumptions") or []:
        if not isinstance(ia, dict):
            continue
        ia_cat = ia.get("category_name") or ia.get("category_id") or ia.get("initiative_id")
        ia_lever = ia.get("lever")
        if cat and ia_cat and str(ia_cat).lower() == str(cat).lower():
            if not lever or not ia_lever or str(ia_lever).lower() == str(lever).lower():
                for item in ia.get("assumptions") or []:
                    matched.append(item if isinstance(item, dict) else {"text": str(item)})
    return matched


def build_initiative_provenance(
    initiative: Dict[str, Any],
    analysis: Dict[str, Any] | None,
    session_id: str,
) -> Dict[str, Any]:
    """Trace an initiative number back through assumptions to source spend rows."""
    category = initiative.get("category") or ""
    session_id = session_id or initiative.get("session_id") or initiative.get("analysis_id") or ""

    manifest = read_manifest(session_id) if session_id else {}
    source_files = [
        {
            "filename": f.get("original_name") or f.get("name") or f.get("path", "").split("/")[-1],
            "path": f.get("path"),
            "uploaded_at": f.get("uploaded_at"),
            "size_bytes": f.get("size_bytes"),
        }
        for f in (manifest.get("files") or [])
        if isinstance(f, dict)
    ]

    spend_lines: List[Dict[str, Any]] = []
    if analysis:
        for line in analysis.get("normalized_spend") or []:
            if isinstance(line, dict) and _match_category(line, category):
                spend_lines.append({
                    "row_id": line.get("row_id"),
                    "supplier": line.get("supplier"),
                    "description": line.get("description"),
                    "category_id": line.get("category_id"),
                    "category_name": line.get("category_name"),
                    "amount_reporting": line.get("amount_reporting") or line.get("amount"),
                    "spend_date": line.get("spend_date"),
                    "fiscal_period": line.get("fiscal_period"),
                    "cost_center": line.get("cost_center"),
                    "entity": line.get("entity"),
                    "source_file": line.get("source_file"),
                })

    spend_lines.sort(key=lambda x: float(x.get("amount_reporting") or 0), reverse=True)

    assumptions = _initiative_assumptions(analysis or {}, initiative)
    ingestion = manifest.get("ingestion_summary") or manifest.get("ingestion_report")

    trace_steps = [
        {
            "step": 1,
            "label": "Initiative savings (P50)",
            "value": initiative.get("p50_savings") or initiative.get("gross_savings_y1"),
            "source": "value-bridge-calculator / savings-modeler",
        },
        {
            "step": 2,
            "label": "Assumption register",
            "count": len(assumptions),
            "source": "assumption-register skill",
        },
        {
            "step": 3,
            "label": "Normalized spend rows",
            "count": len(spend_lines),
            "source": "spend-profiler ingestion",
        },
        {
            "step": 4,
            "label": "Source files",
            "count": len(source_files),
            "source": "upload manifest",
        },
    ]

    return {
        "initiative_id": initiative.get("initiative_id"),
        "category": category,
        "lever": initiative.get("lever"),
        "session_id": session_id,
        "trace_steps": trace_steps,
        "assumptions": assumptions[:20],
        "source_spend_rows": spend_lines[:25],
        "source_files": source_files,
        "ingestion_summary": ingestion,
        "analysis_revision": analysis.get("revision") if analysis else None,
    }
