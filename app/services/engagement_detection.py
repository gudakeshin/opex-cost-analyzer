"""Auto-detect company name and industry for an engagement from its processed
documents.

The Documents page already parses spend files and context docs; this module
aggregates the signal those leave behind (filenames, legal-entity IDs, spend
category mix, narrative text) into a single recommended company + industry so the
Diagnostic and Analysis pages can pre-fill an override-able default instead of
making the user re-pick every time.

Detection combines fast heuristics with the LLM document-contextualizer:
- company: filename prefix + legal_entity_id voting;
- industry: spend-pattern heuristic, overridden by the LLM-inferred sector pack
  when context docs are present. The LLM call is cached on the engagement
  manifest keyed by a hash of the concatenated context-doc text, so incremental
  uploads don't re-incur a Gemini call when the narrative corpus is unchanged.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from app.config import logger
from app.models import NormalizedSpendLine
from app.services.document_pipeline import load_cached_markdown, load_cached_spend_lines
from app.services.engagement_sanity import (
    _signals_from_spend_lines,
    extract_company_from_filename,
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


def industry_label(pack_id: str) -> str:
    """Human label for a sector-pack id (falls back to a title-cased id)."""
    pack_id = (pack_id or "").strip()
    if not pack_id:
        return ""
    return SECTOR_PACK_LABELS.get(pack_id, pack_id.replace("_", " ").title())


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

    # --- Company detection: filename prefixes + legal-entity voting ----------
    company_votes: Dict[str, int] = {}
    company_sources: Dict[str, List[str]] = {}

    def _vote_company(name: str, source: str) -> None:
        company_votes[name] = company_votes.get(name, 0) + 1
        company_sources.setdefault(name, []).append(source)

    for doc in ready_docs:
        fname = str(doc.get("filename") or "")
        guess = extract_company_from_filename(fname)
        if guess:
            _vote_company(guess, fname)

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

    for sig in _signals_from_spend_lines(all_lines):
        guess = sig.get("company_guess")
        if guess:
            _vote_company(guess, "legal_entity_id")

    detected_company = max(company_votes, key=company_votes.__getitem__) if company_votes else ""

    # --- Industry: spend-pattern heuristic -----------------------------------
    industry_spend = ""
    if all_lines:
        total_spend = sum(x.reporting_amount for x in all_lines)
        try:
            industry_spend = profiler.infer_industry_from_spend(all_lines, total_spend) or ""
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("infer_industry_from_spend failed for %s: %s", engagement_id, exc)

    # --- Industry: LLM contextualizer over context docs (cached) -------------
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
                context_doc_names.append(str(doc.get("filename") or ""))

    context_blob = "\n".join(context_texts)
    context_hash = (
        hashlib.sha256(context_blob.encode("utf-8")).hexdigest()[:16] if context_blob else ""
    )
    prior_hash = str(manifest.get("context_text_hash") or "")
    prior_signals = manifest.get("detection_signals")
    cached_llm = (
        str(prior_signals.get("industry_llm") or "")
        if isinstance(prior_signals, dict)
        else ""
    )

    industry_llm = ""
    if context_blob:
        if prior_hash and prior_hash == context_hash:
            # Context corpus unchanged — reuse the prior LLM result, no Gemini call.
            industry_llm = cached_llm
        else:
            try:
                ctx = profiler.document_contextualizer(context_texts)
                industry_llm = str(ctx.get("inferred_industry") or "")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("document_contextualizer failed for %s: %s", engagement_id, exc)

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

    company_docs = sorted(set(company_sources.get(detected_company, []))) if detected_company else []

    return {
        "detected_company_name": detected_company,
        "detected_industry": detected_industry,
        "detected_industry_label": industry_label(detected_industry),
        "industry_source": industry_source,
        "industry_llm": industry_llm,
        "industry_spend": industry_spend,
        "context_text_hash": context_hash,
        "source_documents": {
            "company": company_docs,
            "industry": industry_docs,
        },
    }
