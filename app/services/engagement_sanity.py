"""Sanity checks between diagnostic engagement context and uploaded spend data."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import NormalizedSpendLine

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
    }
)


def _normalize_company(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (name or "").lower())
    return " ".join(cleaned.split())


def is_placeholder_company(name: Optional[str]) -> bool:
    return _normalize_company(name or "") in _PLACEHOLDER_COMPANIES


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
    top = max(counts, key=counts.get)
    return [{"source": "legal_entity", "company_guess": top}]


def compute_engagement_sanity(
    manifest: Dict[str, Any],
    spend_lines: Optional[List[NormalizedSpendLine]] = None,
) -> Dict[str, Any]:
    """Compare engagement company to signals inferred from uploads and spend lines."""
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

    # De-duplicate filename mismatches (same detected company)
    deduped: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for c in conflicts:
        key = f"{c.get('kind')}:{c.get('detected_company')}:{c.get('engagement_company')}"
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
