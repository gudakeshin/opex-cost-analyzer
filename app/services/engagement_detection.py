"""Auto-detect company name and industry for an engagement from its processed
documents.

The Documents page already parses spend files and context docs; this module
aggregates the signal those leave behind (filenames, legal-entity IDs, spend
category mix, narrative text) into a single recommended company + industry so the
Diagnostic and Analysis pages can pre-fill an override-able default instead of
making the user re-pick every time.

Detection combines fast heuristics with the LLM document-contextualizer:
- company: context-doc text + LLM, then legal_entity_id, then spend filename prefix;
- revenue: context-doc text + LLM (₹ Cr);
- industry: spend-pattern heuristic, overridden by the LLM-inferred sector pack
  when context docs are present. The LLM call is cached on the engagement
  manifest keyed by a hash of the concatenated context-doc text, so incremental
  uploads don't re-incur a Gemini call when the narrative corpus is unchanged.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from app.config import logger
from app.models import NormalizedSpendLine
from app.services.document_pipeline import load_cached_markdown, load_cached_spend_lines
from app.services.engagement_sanity import (
    _normalize_company,
    _signals_from_spend_lines,
    extract_company_from_context_text,
    extract_company_from_filename,
    extract_revenue_cr_from_context_text,
    is_low_confidence_company_guess,
    pick_best_company_guess,
)
from app.services.engagements_store import read_engagement_manifest
from app.skills.engine import profiler

# Canonical display labels for the 15 sector packs (mirrors the frontend
# SECTOR_OPTIONS in Diagnostic.tsx). Kept here so the backend can hand the UI a
# ready-to-render label alongside the raw pack id.
SECTOR_PACK_LABELS: Dict[str, str] = {
    "bfsi_banks": "BFSI / Banks",
    "it_ites": "IT / ITES",
    "fmcg_consumer": "FMCG / Consumer",
    "pharma_lifesciences": "Pharma / Life Sciences",
    "energy_utilities": "Energy / Utilities",
    "insurance_general": "Insurance (General)",
    "retail_organized": "Retail (Organized)",
    "telecom_infra": "Telecom / Infrastructure",
    "manufacturing_diversified": "Manufacturing (Diversified)",
    "psu_cpse": "PSU / CPSE",
    "conglomerate": "Conglomerate",
    "financial_services_nonbank": "Financial Services (Non-bank)",
    "gcc_capability_centers": "GCC / Capability Centers",
    "healthcare_hospitals": "Healthcare / Hospitals",
    "hospitality_travel": "Hospitality / Travel",
}

_SPEND_ROLES = {"spend_tabular", "mixed"}
_CONTEXT_ROLES = {"context_doc", "mixed"}

_WEIGHT_LLM = 3.0
_WEIGHT_CONTEXT_TEXT = 2.0
_WEIGHT_LEGAL_ENTITY = 2.0
_WEIGHT_FILENAME = 1.0


def industry_label(pack_id: str) -> str:
    """Human label for a sector-pack id (falls back to a title-cased id)."""
    pack_id = (pack_id or "").strip()
    if not pack_id:
        return ""
    return SECTOR_PACK_LABELS.get(pack_id, pack_id.replace("_", " ").title())


def _pick_revenue_cr(
    regex_votes: Dict[float, float],
    revenue_llm: Optional[float],
) -> Optional[float]:
    if revenue_llm is not None and revenue_llm > 0:
        return revenue_llm
    if not regex_votes:
        return None
    return max(regex_votes, key=regex_votes.__getitem__)


def detect_engagement_profile(engagement_id: str) -> Dict[str, Any]:
    """Aggregate company + industry signals across an engagement's ready documents.

    Returns a detection dict (never raises for missing data — returns empty
    strings instead). The LLM contextualizer is skipped and its prior result
    reused when the concatenated context-doc text is unchanged since the last
    detection (compared via ``context_text_hash`` on the manifest).
    """
    manifest = read_engagement_manifest(engagement_id)
    documents = [d for d in (manifest.get("documents") or []) if isinstance(d, dict)]
    ready_docs = [d for d in documents if d.get("status") == "ready"]

    company_votes: Dict[str, float] = {}
    company_display: Dict[str, str] = {}
    company_sources: Dict[str, List[str]] = {}
    revenue_votes: Dict[float, float] = {}
    revenue_sources: Dict[float, List[str]] = {}

    def _vote_company(name: str, source: str, weight: float = 1.0) -> None:
        cleaned = (name or "").strip()
        if not cleaned:
            return
        key = _normalize_company(cleaned)
        if not key:
            return
        company_votes[key] = company_votes.get(key, 0.0) + weight
        prev = company_display.get(key, "")
        if len(cleaned) > len(prev):
            company_display[key] = cleaned
        company_sources.setdefault(key, []).append(source)

    def _vote_revenue(value: float, source: str, weight: float = 1.0) -> None:
        if value <= 0:
            return
        revenue_votes[value] = revenue_votes.get(value, 0.0) + weight
        revenue_sources.setdefault(value, []).append(source)

    # --- Aggregate spend lines (for legal-entity + spend-pattern industry) ----
    all_lines: List[NormalizedSpendLine] = []
    spend_doc_names: List[str] = []
    for doc in ready_docs:
        if doc.get("role") in _SPEND_ROLES:
            try:
                lines = load_cached_spend_lines(engagement_id, str(doc.get("document_id") or ""))
            except Exception:
                lines = []
            if lines:
                all_lines.extend(lines)
                spend_doc_names.append(str(doc.get("filename") or ""))

    for doc in ready_docs:
        if doc.get("role") not in _SPEND_ROLES:
            continue
        fname = str(doc.get("filename") or "")
        guess = extract_company_from_filename(fname)
        if guess and not is_low_confidence_company_guess(guess):
            _vote_company(guess, fname, _WEIGHT_FILENAME)

    for sig in _signals_from_spend_lines(all_lines):
        guess = sig.get("company_guess")
        if guess and not is_low_confidence_company_guess(guess):
            _vote_company(guess, "legal_entity_id", _WEIGHT_LEGAL_ENTITY)

    # --- Context docs: regex headers + LLM contextualizer (cached) -------------
    context_texts: List[str] = []
    context_doc_names: List[str] = []
    for doc in ready_docs:
        if doc.get("role") in _CONTEXT_ROLES:
            try:
                md = load_cached_markdown(engagement_id, str(doc.get("document_id") or ""))
            except Exception:
                md = ""
            if md.strip():
                context_texts.append(md)
                fname = str(doc.get("filename") or "")
                context_doc_names.append(fname)
                guess = extract_company_from_context_text(md)
                if guess:
                    _vote_company(guess, fname, _WEIGHT_CONTEXT_TEXT)
                rev = extract_revenue_cr_from_context_text(md)
                if rev is not None:
                    _vote_revenue(rev, fname, _WEIGHT_CONTEXT_TEXT)

    context_blob = "\n".join(context_texts)
    context_hash = (
        hashlib.sha256(context_blob.encode("utf-8")).hexdigest()[:16] if context_blob else ""
    )
    prior_hash = str(manifest.get("context_text_hash") or "")
    prior_signals = manifest.get("detection_signals")
    cached_llm_industry = (
        str(prior_signals.get("industry_llm") or "")
        if isinstance(prior_signals, dict)
        else ""
    )
    cached_llm_company = (
        str(prior_signals.get("company_llm") or "")
        if isinstance(prior_signals, dict)
        else ""
    )
    cached_llm_revenue: Optional[float] = None
    if isinstance(prior_signals, dict) and prior_signals.get("revenue_llm") is not None:
        try:
            cached_llm_revenue = float(prior_signals["revenue_llm"])
        except (TypeError, ValueError):
            cached_llm_revenue = None

    industry_llm = ""
    company_llm = ""
    revenue_llm: Optional[float] = None
    if context_blob:
        if prior_hash and prior_hash == context_hash:
            industry_llm = cached_llm_industry
            company_llm = cached_llm_company
            revenue_llm = cached_llm_revenue
        else:
            try:
                ctx = profiler.document_contextualizer(context_texts)
                industry_llm = str(ctx.get("inferred_industry") or "")
                company_llm = str(ctx.get("inferred_company_name") or "")
                raw_rev = ctx.get("inferred_annual_revenue_cr")
                if raw_rev is not None and str(raw_rev).strip() != "":
                    try:
                        revenue_llm = float(raw_rev)
                    except (TypeError, ValueError):
                        revenue_llm = None
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("document_contextualizer failed for %s: %s", engagement_id, exc)

    if company_llm:
        _vote_company(company_llm, "llm_contextualizer", _WEIGHT_LLM)
    if revenue_llm is not None and revenue_llm > 0:
        _vote_revenue(revenue_llm, "llm_contextualizer", _WEIGHT_LLM)

    detected_company = pick_best_company_guess(company_votes, company_display)
    detected_company_key = _normalize_company(detected_company) if detected_company else ""
    detected_revenue_cr = _pick_revenue_cr(revenue_votes, revenue_llm)

    # --- Industry: spend-pattern heuristic -----------------------------------
    industry_spend = ""
    if all_lines:
        total_spend = sum(x.reporting_amount for x in all_lines)
        try:
            industry_spend = profiler.infer_industry_from_spend(all_lines, total_spend) or ""
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("infer_industry_from_spend failed for %s: %s", engagement_id, exc)

    # Combine: prefer the LLM-inferred sector pack, fall back to spend heuristic.
    if industry_llm:
        detected_industry = industry_llm
        industry_source = "llm"
        industry_docs = context_doc_names
    elif industry_spend:
        detected_industry = industry_spend
        industry_source = "spend"
        industry_docs = spend_doc_names
    else:
        detected_industry = ""
        industry_source = ""
        industry_docs = []

    company_docs = (
        sorted(set(company_sources.get(detected_company_key, [])))
        if detected_company_key
        else []
    )
    revenue_docs = (
        sorted(set(revenue_sources.get(detected_revenue_cr, [])))
        if detected_revenue_cr is not None
        else []
    )

    return {
        "detected_company_name": detected_company,
        "detected_industry": detected_industry,
        "detected_industry_label": industry_label(detected_industry),
        "detected_annual_revenue_cr": detected_revenue_cr,
        "industry_source": industry_source,
        "industry_llm": industry_llm,
        "industry_spend": industry_spend,
        "company_llm": company_llm,
        "revenue_llm": revenue_llm,
        "context_text_hash": context_hash,
        "source_documents": {
            "company": company_docs,
            "industry": industry_docs,
            "revenue": revenue_docs,
        },
    }
