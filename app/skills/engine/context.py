"""Context skills: pii_stripper, data_classifier, llm_context_builder,
assumption_register, vendor_master_builder, consolidation_analyzer."""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from app.models import NormalizedSpendLine


# ---------------------------------------------------------------------------
# PII Stripper
# ---------------------------------------------------------------------------

def pii_stripper(
    lines: List[NormalizedSpendLine],
    *,
    quarantine_threshold: int = 1,
) -> Dict[str, Any]:
    """Scan spend lines for PII and return redacted lines + detection summary."""
    from app.security.pii import scan_record

    rows_with_pii: int = 0
    quarantine_ids: List[int] = []
    pii_type_counts: Dict[str, int] = {}
    affected_fields: set = set()
    redacted_lines: List[Dict[str, Any]] = []

    for line in lines:
        record = line.model_dump() if hasattr(line, "model_dump") else line.__dict__
        cleaned, matches = scan_record(record, redact=True)
        if matches:
            rows_with_pii += 1
            for m in matches:
                pii_type_counts[m.pii_type] = pii_type_counts.get(m.pii_type, 0) + 1
            for m in matches:
                affected_fields.add(m.pii_type)
            if len(matches) >= quarantine_threshold:
                quarantine_ids.append(line.row_id)
        redacted_lines.append(cleaned)

    return {
        "rows_scanned": len(lines),
        "rows_with_pii": rows_with_pii,
        "rows_quarantined": len(quarantine_ids),
        "pii_type_counts": pii_type_counts,
        "affected_fields": sorted(affected_fields),
        "quarantine_row_ids": quarantine_ids,
        "redacted_lines": redacted_lines,
    }


# ---------------------------------------------------------------------------
# Data Classifier
# ---------------------------------------------------------------------------

def data_classifier(
    lines: List[NormalizedSpendLine],
    skill_outputs: Dict[str, Any] | None = None,
    *,
    k_threshold: int = 5,
) -> Dict[str, Any]:
    """Classify spend lines and skill-output blocks with B1–B4 data bands."""
    from app.security.classification import DataBand, classify_spend_line, classify_output_block

    line_bands: List[Dict[str, Any]] = []
    b4_ids: List[int] = []
    worst_line_band = DataBand.B1

    for line in lines:
        record = line.model_dump() if hasattr(line, "model_dump") else line.__dict__
        band = classify_spend_line(record)
        reason_parts = []
        if record.get("supplier"):
            reason_parts.append("supplier field non-empty")
        if record.get("gstin"):
            reason_parts.append("GSTIN present")
        if record.get("gl_code"):
            reason_parts.append("GL code present")
        reason = ", ".join(reason_parts) if reason_parts else "no sensitive fields"
        line_bands.append({"row_id": line.row_id, "band": band.value, "reason": reason})
        if band == DataBand.B4:
            b4_ids.append(line.row_id)
        if list(DataBand).index(band) > list(DataBand).index(worst_line_band):
            worst_line_band = band

    aggregate_bands: Dict[str, Any] = {}
    worst_agg_band = DataBand.B1
    for skill, output in (skill_outputs or {}).items():
        if not isinstance(output, dict):
            continue
        source_count = output.get("row_count") or len(lines)
        band, reason = classify_output_block(
            output, source_row_count=source_count, k_threshold=k_threshold
        )
        from app.security.bands import _inference_risk_score
        risk = _inference_risk_score(band, source_count)
        aggregate_bands[skill] = {
            "band": band.value,
            "inference_risk_score": round(risk, 3),
            "reason": reason,
        }
        if list(DataBand).index(band) > list(DataBand).index(worst_agg_band):
            worst_agg_band = band

    all_bands = [DataBand(lb["band"]) for lb in line_bands] + list(
        DataBand(v["band"]) for v in aggregate_bands.values()
    )
    worst_overall = max(all_bands, key=lambda b: list(DataBand).index(b)) if all_bands else DataBand.B1

    return {
        "line_bands": line_bands,
        "aggregate_bands": aggregate_bands,
        "worst_band": worst_overall.value,
        "b4_row_ids": b4_ids,
        "b4_count": len(b4_ids),
        "summary": (
            f"{len(lines)} rows classified; worst band {worst_overall.value}; "
            f"{len(b4_ids)} B4 row(s) detected."
        ),
    }


# ---------------------------------------------------------------------------
# LLM Context Builder
# ---------------------------------------------------------------------------

def llm_context_builder(
    skill_outputs: Dict[str, Any],
    classification: Dict[str, Any] | None = None,
    *,
    mode: str = "M2",
) -> Dict[str, Any]:
    """Assemble sanitised LLM context from banded skill outputs."""
    import hashlib
    from app.security.classification import DataBand

    aggregate_bands = {}
    if classification and isinstance(classification, dict):
        aggregate_bands = classification.get("aggregate_bands", {})

    included = 0
    tokenised = 0
    excluded = 0
    exclusion_log: List[str] = []
    sanitised: Dict[str, Any] = {}

    if mode == "M1":
        return {
            "context_ready": False,
            "blocks_included": 0,
            "blocks_tokenised": 0,
            "blocks_excluded": len(skill_outputs),
            "worst_band_in_context": "B1",
            "sanitised_skill_outputs": {},
            "exclusion_log": [f"{s}: excluded (mode M1 — no LLM)" for s in skill_outputs],
        }

    worst_band = DataBand.B1

    for skill, output in skill_outputs.items():
        if not isinstance(output, dict):
            sanitised[skill] = output
            included += 1
            continue

        band_info = aggregate_bands.get(skill, {})
        band_str = band_info.get("band", "B3")
        try:
            band = DataBand(band_str)
        except ValueError:
            band = DataBand.B3

        if band == DataBand.B4:
            excluded += 1
            exclusion_log.append(f"{skill}: excluded (B4 — PII/Regulated)")
            continue

        if band == DataBand.B3 and mode == "M3":
            excluded += 1
            exclusion_log.append(f"{skill}: excluded (B3 — restricted; M3 on-prem constraint)")
            continue

        if band == DataBand.B3 and mode == "M2":
            block = dict(output)
            if "category_profile" in block and isinstance(block["category_profile"], list):
                new_cats = []
                for cat in block["category_profile"]:
                    cat = dict(cat)
                    if "top_suppliers" in cat and isinstance(cat["top_suppliers"], list):
                        cat["top_suppliers"] = [
                            {
                                **{k: v for k, v in s.items() if k != "supplier"},
                                "supplier": "VENDOR_" + hashlib.sha256(
                                    str(s.get("supplier", "")).encode()
                                ).hexdigest()[:6].upper(),
                            }
                            if isinstance(s, dict) else s
                            for s in cat["top_suppliers"]
                        ]
                    new_cats.append(cat)
                block["category_profile"] = new_cats
            if "supplier" in block:
                block["supplier"] = "VENDOR_" + hashlib.sha256(
                    str(block["supplier"]).encode()
                ).hexdigest()[:6].upper()
            sanitised[skill] = block
            tokenised += 1
        else:
            sanitised[skill] = output
            included += 1

        if list(DataBand).index(band) > list(DataBand).index(worst_band):
            worst_band = band

    return {
        "context_ready": True,
        "blocks_included": included,
        "blocks_tokenised": tokenised,
        "blocks_excluded": excluded,
        "worst_band_in_context": worst_band.value,
        "sanitised_skill_outputs": sanitised,
        "exclusion_log": exclusion_log,
    }


# ---------------------------------------------------------------------------
# Assumption Register
# ---------------------------------------------------------------------------

def assumption_register(
    lines: List[NormalizedSpendLine],
    initiatives: List[Dict[str, Any]] | None = None,
    *,
    method: str = "three_point",
) -> Dict[str, Any]:
    """Build a per-initiative assumption register with P10/P50/P90 ranges."""
    initiatives = initiatives or []
    total_spend = sum(float(getattr(ln, "amount", 0) or 0) for ln in lines)
    spend_std = 0.0
    if lines:
        amounts = [float(getattr(ln, "amount", 0) or 0) for ln in lines]
        mean = total_spend / len(amounts)
        spend_std = math.sqrt(sum((a - mean) ** 2 for a in amounts) / len(amounts))

    register: List[Dict[str, Any]] = []
    for init in initiatives:
        mid = float(init.get("mid_case_savings") or init.get("deduped_mid_savings") or 0.0)
        if mid <= 0:
            mid = total_spend * 0.05

        if method == "three_point":
            p_low = mid * 0.60
            p_high = mid * 1.50
            p10 = round(p_low + (mid - p_low) * 0.10, 2)
            p50 = round(mid, 2)
            p90 = round(p_high - (p_high - mid) * 0.10, 2)
            pert_mean = round((p10 + 4 * p50 + p90) / 6, 2)

        elif method == "historical":
            cv = (spend_std / (total_spend / max(1, len(lines)))) if total_spend else 0.20
            cv = max(0.05, min(0.50, cv))
            p10 = round(mid * (1 - 1.28 * cv), 2)
            p50 = round(mid, 2)
            p90 = round(mid * (1 + 1.28 * cv), 2)
            pert_mean = p50

        elif method == "mc":
            sigma = mid * 0.25
            draws = [random.gauss(mid, sigma) for _ in range(1000)]
            draws.sort()
            p10 = round(draws[99], 2)
            p50 = round(draws[499], 2)
            p90 = round(draws[899], 2)
            pert_mean = round(sum(draws) / len(draws), 2)

        else:
            p10 = round(mid * 0.75, 2)
            p50 = round(mid, 2)
            p90 = round(mid * 1.30, 2)
            pert_mean = p50

        assumption_quality = "rule_of_thumb" if method == "expert" else "expert_estimate"
        register.append({
            "initiative_id": str(init.get("category_id") or init.get("initiative_id") or "unknown"),
            "category_name": init.get("category_name") or init.get("category_id") or "Unknown",
            "p10": max(0.0, p10),
            "p50": max(0.0, p50),
            "p90": max(0.0, p90),
            "pert_mean": max(0.0, pert_mean),
            "method": method,
            "assumptions": init.get("assumptions", []),
            "source_class": assumption_quality,
            "owner_sign_off": False,
            "validation_date": None,
        })

    return {
        "register": register,
        "initiative_count": len(register),
        "method": method,
        "p10_total": round(sum(r["p10"] for r in register), 2),
        "p50_total": round(sum(r["p50"] for r in register), 2),
        "p90_total": round(sum(r["p90"] for r in register), 2),
        "summary": (
            f"{len(register)} initiative(s) registered using {method} method; "
            f"portfolio P50 = {sum(r['p50'] for r in register):,.0f}."
        ),
    }


# ---------------------------------------------------------------------------
# Vendor Master Builder
# ---------------------------------------------------------------------------

def vendor_master_builder(lines: List[NormalizedSpendLine]) -> Dict[str, Any]:
    """Build a canonical vendor master by deduplicating on GSTIN (primary key)
    and normalized supplier name (fallback)."""
    def _norm_name(name: str) -> str:
        import re
        n = re.sub(r"\s+", " ", (name or "").upper().strip())
        for suffix in [
            " PRIVATE LIMITED", " PVT LTD", " PVT. LTD.", " LIMITED",
            " LTD", " LLP", " LLC", " INC", " CORP", " CO",
        ]:
            if n.endswith(suffix):
                n = n[: -len(suffix)].strip()
        return n

    by_gstin: Dict[str, List[NormalizedSpendLine]] = defaultdict(list)
    no_gstin: List[NormalizedSpendLine] = []

    for line in lines:
        gstin = (line.vendor_gstin or "").strip().upper()
        if gstin and len(gstin) == 15:
            by_gstin[gstin].append(line)
        else:
            no_gstin.append(line)

    by_name: Dict[str, List[NormalizedSpendLine]] = defaultdict(list)
    for line in no_gstin:
        key = _norm_name(line.supplier or "UNKNOWN")
        by_name[key].append(line)

    def _build_entry(vid: int, gstin_key: Optional[str], group: List[NormalizedSpendLine]) -> Dict[str, Any]:
        names = [ln.supplier for ln in group if ln.supplier]
        name_counts: Counter = Counter(names)
        canonical = name_counts.most_common(1)[0][0] if name_counts else "Unknown"
        aliases = sorted(set(names) - {canonical})

        total_spend = sum(ln.reporting_amount for ln in group)
        source_systems = sorted(set(ln.source_system_id for ln in group if ln.source_system_id))

        cat_spend: Dict[str, float] = defaultdict(float)
        for ln in group:
            cat_spend[ln.category_id or "uncategorized"] += ln.reporting_amount
        top_cat = max(cat_spend, key=lambda k: cat_spend[k]) if cat_spend else None

        msme_flags = [ln.vendor_msme_flag for ln in group if ln.vendor_msme_flag is not None]

        return {
            "vendor_id": f"V{vid:05d}",
            "canonical_name": canonical,
            "aliases": aliases,
            "gstin": gstin_key,
            "total_spend": round(total_spend, 2),
            "line_count": len(group),
            "source_systems": source_systems,
            "msme_flag": msme_flags[0] if msme_flags else None,
            "top_category": top_cat,
        }

    vendors: List[Dict[str, Any]] = []
    duplicate_aliases_removed = 0
    vid = 1

    for gstin_key, group in by_gstin.items():
        entry = _build_entry(vid, gstin_key, group)
        duplicate_aliases_removed += len(entry["aliases"])
        vendors.append(entry)
        vid += 1

    for _norm_key, group in by_name.items():
        entry = _build_entry(vid, None, group)
        duplicate_aliases_removed += len(entry["aliases"])
        vendors.append(entry)
        vid += 1

    vendors.sort(key=lambda v: v["total_spend"], reverse=True)

    total_spend_all = sum(v["total_spend"] for v in vendors)
    gstin_covered = sum(
        1 for ln in lines
        if (ln.vendor_gstin or "").strip() and len((ln.vendor_gstin or "").strip()) == 15
    )
    coverage_pct = round(gstin_covered / max(len(lines), 1) * 100, 1)

    alias_spend = sum(
        v["total_spend"] for v in vendors if v["aliases"]
    )
    estimated_dedup_savings = round(alias_spend * 0.03, 2)

    return {
        "vendor_count": len(vendors),
        "total_spend_covered": round(total_spend_all, 2),
        "coverage_pct_with_gstin": coverage_pct,
        "duplicate_aliases_removed": duplicate_aliases_removed,
        "estimated_dedup_savings": estimated_dedup_savings,
        "vendors": vendors,
    }


# ---------------------------------------------------------------------------
# Consolidation Analyzer
# ---------------------------------------------------------------------------

def consolidation_analyzer(
    lines: List[NormalizedSpendLine],
    entity_tree: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Multi-entity rollup + intercompany elimination using ConsolidationEngine."""
    from app.services.consolidation import ConsolidationEngine
    from app.models import EntityTree as _EntityTree

    tree: Optional[_EntityTree] = None
    if entity_tree:
        try:
            tree = _EntityTree.model_validate(entity_tree)
        except Exception:
            pass

    eng = ConsolidationEngine(entity_tree=tree)
    result = eng.consolidate(lines)
    completeness = result.get("completeness", {})

    return {
        "consolidation_available": True,
        "reason": None,
        "group_total_spend": result.get("group_total_spend", 0.0),
        "group_addressable_spend": result.get("group_addressable_spend", 0.0),
        "intercompany_eliminated": result.get("intercompany_eliminated", 0.0),
        "addressable_pct": result.get("addressable_pct", 0.0),
        "entity_count": result.get("entity_count", 0),
        "completeness_coverage_pct": completeness.get("coverage_pct", 100.0),
        "missing_entities": completeness.get("missing_entities", []),
        "entities": result.get("entities", []),
        "top_categories": result.get("top_categories", []),
    }
