"""PII detection for Indian enterprise spend data.

Detects:
- Email addresses
- Indian mobile phone numbers
- PAN card numbers
- Aadhaar numbers (12-digit)
- GSTIN (business-linkable; classified B3 not B4, but flagged)
- Name + prefix patterns (Mr./Mrs./Ms./Dr.)

Uses regex only — no heavy NLP dependencies at runtime.
Presidio / spaCy can be layered on top in Phase 3 for 99.2% recall target.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_EMAIL = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Indian mobile: optional +91 / 0, then 10 digits starting 6-9
_PHONE_IN = re.compile(
    r"(?<!\d)(?:\+91[\s\-]?|0)?[6-9]\d{9}(?!\d)",
)

# PAN: 5 letters, 4 digits, 1 letter (all uppercase)
_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# Aadhaar: 12 digits, optionally space-separated in groups of 4
_AADHAAR = re.compile(r"(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}(?!\d)")

# GSTIN: 2-digit state code + PAN + 1-digit entity + Z + check char
_GSTIN = re.compile(
    r"\b\d{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z][Z][0-9A-Z]\b",
    re.IGNORECASE,
)

# Name with title prefix
_TITLED_NAME = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Shri|Smt|Kumari)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b",
)

# Simple Indian surname/name heuristics — common two-word patterns
_FULL_NAME = re.compile(
    r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3}\b",
)

_REDACT_CHAR = "█"


@dataclass
class PiiMatch:
    pii_type: str          # "email" | "phone" | "pan" | "aadhaar" | "gstin" | "name"
    value: str             # raw matched text
    start: int
    end: int
    confidence: float      # 0.0 – 1.0


@dataclass
class ScanResult:
    original: str
    redacted: str
    matches: List[PiiMatch] = field(default_factory=list)

    @property
    def has_pii(self) -> bool:
        return bool(self.matches)

    @property
    def pii_types(self) -> List[str]:
        return list({m.pii_type for m in self.matches})


def scan_text(text: str, *, redact: bool = True) -> ScanResult:
    """Scan a text string for PII patterns.  Returns redacted version + matches."""
    if not text or not isinstance(text, str):
        return ScanResult(original=text or "", redacted=text or "", matches=[])

    matches: List[PiiMatch] = []

    def _collect(pattern: re.Pattern, pii_type: str, confidence: float) -> None:
        for m in pattern.finditer(text):
            matches.append(
                PiiMatch(
                    pii_type=pii_type,
                    value=m.group(),
                    start=m.start(),
                    end=m.end(),
                    confidence=confidence,
                )
            )

    _collect(_EMAIL, "email", 0.99)
    _collect(_PAN, "pan", 0.98)
    _collect(_GSTIN, "gstin", 0.97)
    _collect(_PHONE_IN, "phone", 0.92)
    _collect(_AADHAAR, "aadhaar", 0.85)
    _collect(_TITLED_NAME, "name", 0.80)

    if not redact:
        return ScanResult(original=text, redacted=text, matches=matches)

    # Build redacted string by replacing matched spans with block chars
    # Process in reverse order to preserve index positions
    redacted = list(text)
    for m in sorted(matches, key=lambda x: x.start, reverse=True):
        replacement = _REDACT_CHAR * len(m.value)
        redacted[m.start: m.end] = list(replacement)
    return ScanResult(original=text, redacted="".join(redacted), matches=matches)


def scan_record(record: Dict[str, Any], *, redact: bool = True) -> Tuple[Dict[str, Any], List[PiiMatch]]:
    """Scan all string values in a dict record.  Returns (cleaned_record, all_matches)."""
    cleaned: Dict[str, Any] = {}
    all_matches: List[PiiMatch] = []
    for key, value in record.items():
        if isinstance(value, str):
            result = scan_text(value, redact=redact)
            cleaned[key] = result.redacted if redact else value
            all_matches.extend(result.matches)
        elif isinstance(value, dict):
            sub, sub_matches = scan_record(value, redact=redact)
            cleaned[key] = sub
            all_matches.extend(sub_matches)
        elif isinstance(value, list):
            new_list: List[Any] = []
            for item in value:
                if isinstance(item, str):
                    r = scan_text(item, redact=redact)
                    new_list.append(r.redacted if redact else item)
                    all_matches.extend(r.matches)
                elif isinstance(item, dict):
                    sub, sub_matches = scan_record(item, redact=redact)
                    new_list.append(sub)
                    all_matches.extend(sub_matches)
                else:
                    new_list.append(item)
            cleaned[key] = new_list
        else:
            cleaned[key] = value
    return cleaned, all_matches


def is_pii_free(text: str) -> bool:
    """Quick check — returns True if no PII pattern fires."""
    result = scan_text(text, redact=False)
    return not result.has_pii


def quarantine_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return a record with all string values replaced by '[QUARANTINED]'.

    Used when a B4 record cannot be safely processed further.
    """
    out: Dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, str):
            out[key] = "[QUARANTINED]"
        elif isinstance(value, dict):
            out[key] = quarantine_record(value)
        else:
            out[key] = value
    return out
