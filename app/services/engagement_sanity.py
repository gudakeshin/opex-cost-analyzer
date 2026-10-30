"""Sanity checks between diagnostic engagement context and uploaded spend data."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import NormalizedSpendLine

_PLACEHOLDER_INDUSTRY = "manufacturing_diversified"

_INDUSTRY_UMBRELLA = frozenset({"conglomerate"})

_PLACEHOLDER_COMPANIES = frozenset(
    {
        "",
        "client",
        "new engagement",
        "opex engagement",
        "unnamed engagement",
        "smoketest co",
    }
)

_FILENAME_SKIP_TOKENS = frozenset(
    {
        "detailed",
        "spend",
        "report",
        "ledger",
        "expense",
        "expenses",
        "summary",
        "sample",
        "template",
        "data",
        "table",
        "workbook",
        "upload",
        "analysis",
        "opex",
        "cost",
        "costs",
        "procurement",
        "indirect",
        "fy",
        "annual",
        "quarterly",
        "q1",
        "q2",
        "q3",
        "q4",
        # Finance / doc-type tokens common in enterprise filenames
        "budget",
        "actual",
        "memo",
        "vs",
        "bva",
        "pnl",
        "lineitem",
        "headcount",
        "aggregate",
        "vendor",
        "master",
        "contract",
        "register",
        "aging",
        "roster",
        "capex",
        "treasury",
        "utilization",
        "offshore",
        "onshore",
        "deep",
        "research",
        "brief",
        "policy",
        "disclosure",
        "excerpt",
        "structure",
        "programmes",
        "calibration",
        "pack",
        "gl",
        "ap",
        "extract",
        "segment",
        "revenue",
        "entity",
        "tree",
        "operational",
        "drivers",
        "payment",
        "terms",
        "working",
        "capital",
        "material",
        "procurement",
        "diagnostic",
        "urls",
        "brsr",
        "fx",
    }
)

_COMPANY_HEADER_RE = re.compile(
    r"(?:^|\n)\s*([A-Z][A-Za-z0-9&\.\'\-\s]{2,80}?"
    r"(?:Ltd\.?|Limited|Pvt\.?\s*Ltd\.?|Inc\.?|Corp\.?|Corporation|LLP|PLC))"
    r"(?:\s*[—\-–|:])?",
    re.MULTILINE,
)

_COMPANY_INLINE_RE = re.compile(
    r"(?:\bfor|\babout|\bon)\s+([A-Z][A-Za-z0-9&\.\'\-\s]{2,80}?"
    r"(?:Ltd\.?|Limited|Pvt\.?\s*Ltd\.?|Inc\.?|Corp\.?|Corporation|LLP|PLC))\)?",
    re.IGNORECASE,
)

_REVENUE_CR_RE = re.compile(
    r"(?:consolidated\s+)?revenue\s+was[^\d₹]{0,40}₹?\s*([\d,]+(?:\.\d+)?)\s*Cr\b",
    re.IGNORECASE,
)

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(ltd\.?|limited|pvt\.?\s*ltd\.?|inc\.?|corp\.?|corporation|llp|plc)\b",
    re.IGNORECASE,
)


def _normalize_company(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return " ".join(cleaned.split())


def is_placeholder_company(name: Optional[str]) -> bool:
    return _normalize_company(name or "") in _PLACEHOLDER_COMPANIES


def is_placeholder_industry(industry: Optional[str]) -> bool:
    value = (industry or "").strip()
    return not value or value == _PLACEHOLDER_INDUSTRY


def infer_industry_from_company_name(company: Optional[str]) -> str:
    """Map a legal entity name to a sector pack when the name is sector-specific."""
    name = (company or "").strip()
    if not name:
        return ""
    low = name.lower()
    if re.search(r"\b(?:bank|banking|nbfc)\b", low):
        return "bfsi_banks"
    if re.search(r"\binsurance\b|\bassurance\b", low):
        return "insurance_general"
    if re.search(
        r"\b(?:digital services|technologies|infotech|software solutions|ites|it services)\b",
        low,
    ):
        return "it_ites"
    return ""


def industries_align(set_id: str, detected_id: str, *, strict: bool = False) -> bool:
    """True when the user-set sector pack is compatible with a detected pack id."""
    a = (set_id or "").strip()
    b = (detected_id or "").strip()
    if not a or not b:
        return True
    if a == b:
        return True
    if a in _INDUSTRY_UMBRELLA:
        return True
    if not strict and b in _INDUSTRY_UMBRELLA:
        return True
    return False


def merge_engagement_detection_context(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay engagement-level detection fields onto a session manifest view."""
    engagement_id = str(manifest.get("engagement_id") or "").strip()
    if not engagement_id:
        return manifest
    try:
        from app.services.engagements_store import read_engagement_manifest

        engagement = read_engagement_manifest(engagement_id)
    except Exception:
        return manifest
    if not engagement.get("engagement_id"):
        return manifest

    merged = dict(manifest)
    for key in (
        "detected_industry",
        "detected_industry_label",
        "detected_company_name",
        "detection_signals",
    ):
        if engagement.get(key) and not merged.get(key):
            merged[key] = engagement[key]
    eng_industry = str(engagement.get("industry") or "").strip()
    if eng_industry and is_placeholder_industry(merged.get("industry")):
        merged["industry"] = eng_industry
    from app.services.engagement_detection import reconcile_detection_view

    return reconcile_detection_view(merged)


def engagement_company_from_manifest(manifest: Dict[str, Any]) -> Optional[str]:
    """Canonical company from diagnostic handoff, falling back to manifest."""
    diagnostic = manifest.get("diagnostic_result")
    if isinstance(diagnostic, dict):
        diag_name = str(diagnostic.get("company_name") or "").strip()
        if diag_name and not is_placeholder_company(diag_name):
            return diag_name
    manifest_name = str(manifest.get("company_name") or "").strip()
    if manifest_name and not is_placeholder_company(manifest_name):
        return manifest_name
    return None


def company_names_align(expected: str, detected: str) -> bool:
    exp = _normalize_company(expected)
    det = _normalize_company(detected)
    if not exp or not det:
        return True
    if exp == det:
        return True
    if exp in det or det in exp:
        return True
    exp_tokens = set(exp.split())
    det_tokens = set(det.split())
    return bool(exp_tokens & det_tokens)


def extract_company_from_filename(filename: str) -> Optional[str]:
    """Heuristic: company prefix in enterprise spend filenames (e.g. Belrise_Detailed_Spend…)."""
    stem = Path(filename or "").stem
    if not stem:
        return None
    low_stem = stem.lower()
    if "sample" in low_stem or "template" in low_stem:
        return None

    parts = re.split(r"[_\-\s]+", stem)
    candidates: List[str] = []
    for part in parts:
        token = re.sub(r"[^a-zA-Z0-9]", "", part)
        if len(token) < 3:
            continue
        low = token.lower()
        if low in _FILENAME_SKIP_TOKENS:
            continue
        if re.fullmatch(r"t\d+", low):
            continue
        if re.fullmatch(r"fy\d{2,4}", low):
            continue
        if re.fullmatch(r"v\d+", low):
            continue
        if token.isdigit():
            continue
        candidates.append(token)

    if not candidates:
        return None
    # First token is usually the company prefix in `{Co}_Detailed_Spend_…` patterns.
    return candidates[0]


def extract_company_from_context_text(text: str) -> Optional[str]:
    """Extract a legal-entity style company name from document header or inline text."""
    excerpt = (text or "")[:500]
    for pattern in (_COMPANY_HEADER_RE, _COMPANY_INLINE_RE):
        match = pattern.search(excerpt)
        if not match:
            continue
        name = match.group(1).strip()
        if name and not is_placeholder_company(name):
            return name
    return None


def extract_revenue_cr_from_context_text(text: str) -> Optional[float]:
    """Extract consolidated annual revenue in ₹ Cr from narrative context docs."""
    excerpt = (text or "")[:2000]
    match = _REVENUE_CR_RE.search(excerpt)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    return value if value > 0 else None


def is_low_confidence_company_guess(name: Optional[str]) -> bool:
    """True for single-token generic filename guesses unlikely to be a company."""
    cleaned = (name or "").strip()
    if not cleaned:
        return True
    if " " in cleaned:
        return False
    if _LEGAL_SUFFIX_RE.search(cleaned):
        return False
    low = cleaned.lower()
    if low in _FILENAME_SKIP_TOKENS:
        return True
    return len(cleaned) <= 4


def should_auto_apply_company(name: Optional[str]) -> bool:
    """True when a detected company name is safe to auto-fill on the manifest."""
    cleaned = (name or "").strip()
    if not cleaned or is_placeholder_company(cleaned):
        return False
    return not is_low_confidence_company_guess(cleaned)


def pick_best_company_guess(votes: Dict[str, float], display_names: Dict[str, str]) -> str:
    """Select highest-weight company among high-confidence candidates only."""
    if not votes:
        return ""
    high_conf = {
        key: weight
        for key, weight in votes.items()
        if not is_low_confidence_company_guess(display_names.get(key, key))
    }
    if not high_conf:
        return ""
    best_key = max(high_conf, key=high_conf.__getitem__)
    return display_names.get(best_key, best_key)


def _industry_conflict(manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    set_industry = str(manifest.get("industry") or "").strip()
    if is_placeholder_industry(set_industry):
        return None

    signals = manifest.get("detection_signals") or {}
    if not isinstance(signals, dict):
        signals = {}
    industry_spend = str(signals.get("industry_spend") or "").strip()
    detected_industry = str(manifest.get("detected_industry") or "").strip()

    mismatches: List[Dict[str, str]] = []
    if industry_spend and not industries_align(set_industry, industry_spend, strict=True):
        mismatches.append({"id": industry_spend, "source": "spend_pattern"})
    if detected_industry:
        spend_matches_detected = bool(
            industry_spend and industries_align(industry_spend, detected_industry, strict=False)
        )
        if (
            not spend_matches_detected
            and not industries_align(set_industry, detected_industry, strict=False)
            and not any(item["id"] == detected_industry for item in mismatches)
        ):
            mismatches.append({"id": detected_industry, "source": "document_detection"})

    if not mismatches:
        return None

    from app.services.engagement_detection import industry_label

    primary = mismatches[0]["id"]
    primary_label = (
        str(manifest.get("detected_industry_label") or "").strip()
        if primary == detected_industry
        else industry_label(primary)
    ) or industry_label(primary)
    set_label = industry_label(set_industry)
    detected_ids = [item["id"] for item in mismatches]

    return {
        "kind": "industry_mismatch",
        "severity": "warning",
        "engagement_industry": set_industry,
        "engagement_industry_label": set_label,
        "detected_industry": primary,
        "detected_industry_label": primary_label,
        "industry_spend": industry_spend or None,
        "detected_industries": detected_ids,
        "signal_source": mismatches[0]["source"],
        "message": (
            f"This engagement is set to **{set_label}**, but uploaded documents/spend "
            f"suggest **{primary_label}**. Benchmarks, sector levers, and category sanity "
            f"checks may be wrong until you align industry."
        ),
    }


def _signals_from_spend_lines(lines: List[NormalizedSpendLine]) -> List[Dict[str, str]]:
    counts: Dict[str, int] = {}
    for line in lines[:500]:
        entity = (line.legal_entity_id or "").strip()
        if not entity or len(entity) < 3:
            continue
        key = entity
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return []
    top = max(counts, key=lambda k: counts[k])
    return [{"source": "legal_entity", "company_guess": top}]


def compute_engagement_sanity(
    manifest: Dict[str, Any],
    spend_lines: Optional[List[NormalizedSpendLine]] = None,
) -> Dict[str, Any]:
    """Compare engagement company to signals inferred from uploads and spend lines."""
    manifest = merge_engagement_detection_context(manifest)
    engagement_company = engagement_company_from_manifest(manifest)
    has_diagnostic = isinstance(manifest.get("diagnostic_result"), dict)

    upload_signals: List[Dict[str, str]] = []
    for item in manifest.get("files") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        guess = extract_company_from_filename(name)
        if guess:
            upload_signals.append(
                {"source": "filename", "file": name, "company_guess": guess}
            )

    if spend_lines:
        upload_signals.extend(_signals_from_spend_lines(spend_lines))

    conflicts: List[Dict[str, Any]] = []
    if engagement_company:
        seen_guesses: Dict[str, List[str]] = {}
        for sig in upload_signals:
            guess = sig.get("company_guess") or ""
            if not guess:
                continue
            seen_guesses.setdefault(guess, []).append(sig.get("file") or sig.get("source") or "")
            if company_names_align(engagement_company, guess):
                continue
            conflicts.append(
                {
                    "kind": "upload_company_mismatch",
                    "severity": "warning",
                    "engagement_company": engagement_company,
                    "detected_company": guess,
                    "source": sig.get("file") or sig.get("source") or "upload",
                    "signal_source": sig.get("source") or "unknown",
                    "message": (
                        f"Uploaded data appears to be for **{guess}**, but this session is "
                        f"set up for **{engagement_company}**"
                        + (" (from Company Diagnostic)" if has_diagnostic else "")
                        + "."
                    ),
                }
            )

        guesses = [g for g in seen_guesses if g]
        if len(guesses) >= 2:
            unique = [g for g in guesses if not any(
                company_names_align(g, other) for other in guesses if other != g
            )]
            if len(unique) >= 2:
                conflicts.append(
                    {
                        "kind": "uploads_disagree",
                        "severity": "warning",
                        "engagement_company": engagement_company,
                        "detected_companies": unique[:5],
                        "message": (
                            "Uploaded files suggest different companies: "
                            + ", ".join(unique[:5])
                            + ". Verify you attached the correct spend pack."
                        ),
                    }
                )

    industry_issue = _industry_conflict(manifest)
    if industry_issue:
        conflicts.append(industry_issue)

    # De-duplicate filename mismatches (same detected company)
    deduped: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for c in conflicts:
        key = (
            f"{c.get('kind')}:"
            f"{c.get('detected_company') or c.get('detected_industry')}:"
            f"{c.get('engagement_company') or c.get('engagement_industry')}"
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(c)

    return {
        "engagement_company": engagement_company,
        "has_diagnostic_context": has_diagnostic,
        "upload_signals": upload_signals,
        "conflicts": deduped,
        "has_conflicts": len(deduped) > 0,
    }


def apply_engagement_sanity_to_manifest(
    manifest: Dict[str, Any],
    spend_lines: Optional[List[NormalizedSpendLine]] = None,
) -> Dict[str, Any]:
    manifest["engagement_sanity"] = compute_engagement_sanity(manifest, spend_lines)
    return manifest
