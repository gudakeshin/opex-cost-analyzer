"""Parse and evaluate sector-lever ``applicable_if`` rules against client context."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

_CATEGORY_PREFIX = re.compile(r"^category:\s*", re.IGNORECASE)
_OR_SPLIT = re.compile(r"\s+or\s+", re.IGNORECASE)
_PCT_QUAL = re.compile(
    r"(?:>\s*(?P<threshold>[\d.]+)\s*%\s*(?P<base>spend|revenue|opex)"
    r"|spend\s*>\s*(?P<threshold2>[\d.]+)\s*%\s*revenue)\s*$",
    re.IGNORECASE,
)
_KEYWORD_DETECTED = re.compile(r"^([a-z0-9_]+)_keywords?\s+detected", re.IGNORECASE)
_REVENUE_THRESHOLD = re.compile(r"annual_revenue\s*>\s*([\d.]+)\s*([mb])?", re.IGNORECASE)
_HEADCOUNT_THRESHOLD = re.compile(r"headcount\s*>\s*([\d.]+)", re.IGNORECASE)
_SUPPLIER_COUNT = re.compile(r"supplier_count(?:_([A-Z0-9_]+))?\s*>\s*([\d.]+)", re.IGNORECASE)
_EXPRESS_PCT = re.compile(r"express_like_pct\s*>\s*([\d.]+)", re.IGNORECASE)


class RuleOutcome(str, Enum):
    HARD_PASS = "hard_pass"
    HARD_FAIL = "hard_fail"
    SOFT = "soft"


@dataclass
class RuleResult:
    outcome: RuleOutcome
    tokens: List[str]


def _normalize_cats(cat_expr: str) -> List[str]:
    return [c.strip().upper() for c in _OR_SPLIT.split(cat_expr) if c.strip()]


def _resolve_cat_key(cat_id: str, cat_spend: Dict[str, float], categories_present: Set[str]) -> Optional[str]:
    present_upper = {c.upper() for c in categories_present}
    upper = cat_id.upper()
    if upper not in present_upper and upper not in {k.upper() for k in cat_spend}:
        return None
    for key in cat_spend:
        if key.upper() == upper:
            return key
    for c in categories_present:
        if c.upper() == upper:
            return c
    return upper


def _matched_spend(
    cat_ids: List[str],
    categories_present: Set[str],
    cat_spend: Dict[str, float],
) -> Tuple[float, List[str]]:
    matched: List[str] = []
    total = 0.0
    for cid in cat_ids:
        key = _resolve_cat_key(cid, cat_spend, categories_present)
        if key is None:
            continue
        if key not in matched:
            matched.append(key)
        total += float(cat_spend.get(key, cat_spend.get(key.upper(), 0.0)))
    return total, matched


def _parse_revenue_threshold(rule_lower: str) -> Optional[float]:
    m = _REVENUE_THRESHOLD.search(rule_lower)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    suffix = (m.group(2) or "").lower()
    if suffix == "m":
        val *= 1e6
    elif suffix == "b":
        val *= 1e9
    return val


def _evaluate_category_rule(
    rule: str,
    categories_present: Set[str],
    cat_spend: Dict[str, float],
    total_spend: float,
    annual_revenue: float,
) -> RuleResult:
    body = _CATEGORY_PREFIX.sub("", rule.strip())
    if body.lower().endswith(" present"):
        cat_part = body[: -len(" present")].strip()
        cat_ids = _normalize_cats(cat_part)
        _, matched = _matched_spend(cat_ids, categories_present, cat_spend)
        if matched:
            tokens = [f"category:{cid}_present" for cid in matched]
            return RuleResult(RuleOutcome.HARD_PASS, tokens)
        return RuleResult(RuleOutcome.HARD_FAIL, [])

    m = _PCT_QUAL.search(body)
    if m:
        cat_part = body[: m.start()].strip()
        cat_ids = _normalize_cats(cat_part)
        threshold = float(m.group("threshold") or m.group("threshold2"))
        base = (m.group("base") or "revenue").lower()
        spend, matched = _matched_spend(cat_ids, categories_present, cat_spend)
        if not matched:
            return RuleResult(RuleOutcome.HARD_FAIL, [])
        if base == "spend":
            ratio = spend / total_spend if total_spend > 0 else 0.0
        elif base == "opex":
            ratio = spend / total_spend if total_spend > 0 else 0.0
        else:
            ratio = spend / annual_revenue if annual_revenue > 0 else 0.0
        if ratio > threshold / 100.0:
            tokens = [f"category:{cid}_present" for cid in matched]
            tokens.append(rule.strip())
            return RuleResult(RuleOutcome.HARD_PASS, tokens)
        # Category present but below materiality — still eligible (presence token only).
        tokens = [f"category:{cid}_present" for cid in matched]
        return RuleResult(RuleOutcome.SOFT, tokens)

    return RuleResult(RuleOutcome.SOFT, [])


def _keyword_family(rule_lower: str) -> Optional[str]:
    m = _KEYWORD_DETECTED.match(rule_lower.strip())
    if m:
        return m.group(1).lower()
    if "keywords detected" in rule_lower:
        for token in rule_lower.replace(" detected", "").split():
            if token.endswith("_keywords") or token.endswith("_keyword"):
                return token.replace("_keywords", "").replace("_keyword", "")
    return None


def _corpus_has_family(family: str, corpus: Set[str], keyword_families: Dict[str, List[str]]) -> bool:
    family_l = family.lower()
    if family_l in corpus:
        return True
    for kw in keyword_families.get(family_l, []):
        if kw.lower() in corpus:
            return True
    return False


def _evaluate_keyword_rule(
    rule: str,
    signal_corpus: Optional[Set[str]],
    keyword_families: Dict[str, List[str]],
) -> RuleResult:
    family = _keyword_family(rule.lower())
    if not family:
        return RuleResult(RuleOutcome.SOFT, [rule.strip()])
    if signal_corpus is not None and _corpus_has_family(family, signal_corpus, keyword_families):
        return RuleResult(RuleOutcome.HARD_PASS, [rule.strip()])
    # Unconfirmed keyword — permissive; never blocks other rules.
    return RuleResult(RuleOutcome.SOFT, [rule.strip()])


def _it_spend_gt_pct_revenue(
    pct: float,
    cat_spend: Dict[str, float],
    annual_revenue: float,
) -> bool:
    it_spend = float(cat_spend.get("IT", 0.0))
    return annual_revenue > 0 and (it_spend / annual_revenue) > pct / 100.0


def evaluate_applicable_rule(
    rule: str,
    *,
    categories_present: Set[str],
    cat_spend: Dict[str, float],
    total_spend: float,
    annual_revenue: float,
    headcount: float,
    signal_corpus: Optional[Set[str]],
    keyword_families: Dict[str, List[str]],
    multi_bu_inferable: bool,
    spend_profile: Dict[str, Any],
    line_flags: Optional[Dict[str, Any]] = None,
) -> RuleResult:
    """Evaluate a single applicable_if rule (supports internal OR for compound rules)."""
    rule = rule.strip()
    if not rule:
        return RuleResult(RuleOutcome.SOFT, [])

    if re.search(r"\s+or\s+", rule, re.IGNORECASE) and not rule.lower().startswith("category:"):
        parts = _OR_SPLIT.split(rule)
        any_pass = False
        tokens: List[str] = []
        all_soft = True
        for part in parts:
            sub = evaluate_applicable_rule(
                part.strip(),
                categories_present=categories_present,
                cat_spend=cat_spend,
                total_spend=total_spend,
                annual_revenue=annual_revenue,
                headcount=headcount,
                signal_corpus=signal_corpus,
                keyword_families=keyword_families,
                multi_bu_inferable=multi_bu_inferable,
                spend_profile=spend_profile,
                line_flags=line_flags,
            )
            if sub.outcome == RuleOutcome.HARD_PASS:
                any_pass = True
                tokens.extend(sub.tokens)
                all_soft = False
            elif sub.outcome == RuleOutcome.HARD_FAIL:
                all_soft = False
        if any_pass:
            return RuleResult(RuleOutcome.HARD_PASS, tokens)
        if all_soft:
            return RuleResult(RuleOutcome.SOFT, [])
        return RuleResult(RuleOutcome.HARD_FAIL, [])

    rule_lower = rule.lower()

    if rule_lower.startswith("category:"):
        return _evaluate_category_rule(
            rule, categories_present, cat_spend, total_spend, annual_revenue
        )

    if "headcount >" in rule_lower:
        m = _HEADCOUNT_THRESHOLD.search(rule_lower)
        if m:
            threshold = float(m.group(1))
            if headcount and headcount > threshold:
                return RuleResult(RuleOutcome.HARD_PASS, [f"headcount>{threshold:.0f}"])
            return RuleResult(RuleOutcome.HARD_FAIL, [])
        return RuleResult(RuleOutcome.SOFT, [])

    if "annual_revenue >" in rule_lower:
        threshold = _parse_revenue_threshold(rule_lower)
        if threshold is not None:
            if annual_revenue and annual_revenue > threshold:
                return RuleResult(RuleOutcome.HARD_PASS, [f"revenue>{threshold:.0f}"])
            return RuleResult(RuleOutcome.HARD_FAIL, [])
        return RuleResult(RuleOutcome.SOFT, [])

    if "multi_bu_structure" in rule_lower:
        if multi_bu_inferable:
            return RuleResult(RuleOutcome.HARD_PASS, ["multi_bu_inferred"])
        return RuleResult(RuleOutcome.SOFT, [])

    if rule_lower == "multiple_cost_centers_present":
        diversity = spend_profile.get("organizational_diversity", {})
        if int(diversity.get("distinct_cost_centers", 0)) > 1:
            return RuleResult(RuleOutcome.HARD_PASS, [rule])
        return RuleResult(RuleOutcome.HARD_FAIL, [])

    m = _SUPPLIER_COUNT.search(rule_lower)
    if m:
        cat_filter = (m.group(1) or "").upper()
        threshold = float(m.group(2))
        if cat_filter:
            cat_row = next(
                (c for c in spend_profile.get("category_profile", []) if c.get("category_id") == cat_filter),
                None,
            )
            count = int(cat_row.get("supplier_count", 0)) if cat_row else 0
        else:
            count = max(
                (int(c.get("supplier_count", 0)) for c in spend_profile.get("category_profile", [])),
                default=0,
            )
        if count > threshold:
            return RuleResult(RuleOutcome.HARD_PASS, [rule.strip()])
        return RuleResult(RuleOutcome.HARD_FAIL, [])

    m = _EXPRESS_PCT.search(rule_lower)
    if m:
        threshold = float(m.group(1))
        for cat in spend_profile.get("category_profile", []):
            if float(cat.get("express_like_pct", 0.0)) > threshold:
                cid = cat.get("category_id", "")
                return RuleResult(
                    RuleOutcome.HARD_PASS,
                    [rule.strip(), f"category:{cid}_present"],
                )
        return RuleResult(RuleOutcome.HARD_FAIL, [])

    if "it_spend_gt" in rule_lower.replace(" ", "") or rule_lower.strip() == "it_spend_gt_5pct_revenue":
        pct = 5.0
        if _it_spend_gt_pct_revenue(pct, cat_spend, annual_revenue):
            tokens = ["it_spend_gt_5pct_revenue"]
            if "IT" in cat_spend or "IT" in {c.upper() for c in categories_present}:
                tokens.append("category:IT_present")
            return RuleResult(RuleOutcome.HARD_PASS, tokens)
        return RuleResult(RuleOutcome.HARD_FAIL, [])

    flags = line_flags or {}
    if "gst_treatment field present" in rule_lower:
        return (
            RuleResult(RuleOutcome.HARD_PASS, [rule.strip()])
            if flags.get("gst_treatment_present")
            else RuleResult(RuleOutcome.HARD_FAIL, [])
        )
    if "lease_treatment field present" in rule_lower:
        return (
            RuleResult(RuleOutcome.HARD_PASS, [rule.strip()])
            if flags.get("lease_treatment_present")
            else RuleResult(RuleOutcome.HARD_FAIL, [])
        )
    if "related_party_flag_high" in rule_lower:
        return (
            RuleResult(RuleOutcome.HARD_PASS, [rule.strip()])
            if flags.get("related_party_high")
            else RuleResult(RuleOutcome.HARD_FAIL, [])
        )
    if "related_party_flag present" in rule_lower:
        return (
            RuleResult(RuleOutcome.HARD_PASS, [rule.strip()])
            if flags.get("related_party_present")
            else RuleResult(RuleOutcome.HARD_FAIL, [])
        )

    if "contract_status:" in rule_lower:
        if flags.get("contract_status_rolling_or_expiring"):
            return RuleResult(RuleOutcome.HARD_PASS, [rule.strip()])
        return RuleResult(RuleOutcome.HARD_FAIL, [])

    if rule_lower.startswith("metric:"):
        return RuleResult(RuleOutcome.SOFT, [])

    if "keywords detected" in rule_lower or "_keywords" in rule_lower:
        return _evaluate_keyword_rule(rule, signal_corpus, keyword_families)

    if "_gt_" in rule_lower and "pct" in rule_lower:
        return RuleResult(RuleOutcome.SOFT, [])

    return RuleResult(RuleOutcome.SOFT, [])


def evaluate_lever_applicable_if(
    rules: List[str],
    *,
    categories_present: Set[str],
    cat_spend: Dict[str, float],
    total_spend: float,
    annual_revenue: float,
    headcount: float,
    signal_corpus: Optional[Set[str]],
    keyword_families: Dict[str, List[str]],
    multi_bu_inferable: bool,
    spend_profile: Dict[str, Any],
    line_flags: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Return trigger signals if the lever qualifies; empty list if not.

    Permissive policy (not strict AND):
    - Rules are combined with OR — any satisfied rule qualifies the lever.
    - Category materiality below threshold still passes on category presence.
    - Keyword and multi-BU rules never block; unconfirmed keywords add soft tokens.
    """
    if not rules:
        return ["no_restriction"]

    signals: List[str] = []

    for rule in rules:
        result = evaluate_applicable_rule(
            rule,
            categories_present=categories_present,
            cat_spend=cat_spend,
            total_spend=total_spend,
            annual_revenue=annual_revenue,
            headcount=headcount,
            signal_corpus=signal_corpus,
            keyword_families=keyword_families,
            multi_bu_inferable=multi_bu_inferable,
            spend_profile=spend_profile,
            line_flags=line_flags,
        )
        if result.outcome in (RuleOutcome.HARD_PASS, RuleOutcome.SOFT) and result.tokens:
            for tok in result.tokens:
                if tok not in signals:
                    signals.append(tok)

    return signals


def build_signal_corpus(
    spend_profile: Dict[str, Any],
    document_context: Optional[Dict[str, Any]] = None,
) -> Set[str]:
    """Lower-case tokens/phrases for keyword-family matching."""
    corpus: Set[str] = set()
    for cat in spend_profile.get("category_profile", []):
        cid = str(cat.get("category_id", "")).lower()
        cname = str(cat.get("category_name", "")).lower()
        if cid:
            corpus.add(cid)
        if cname:
            corpus.add(cname)
            for word in cname.split():
                if len(word) > 2:
                    corpus.add(word)
    if document_context:
        summary = str(document_context.get("context_summary", "")).lower()
        if summary:
            corpus.add(summary)
            for line in summary.split():
                if len(line) > 2:
                    corpus.add(line)
        for pack_id, hit_count in (document_context.get("industry_signals") or {}).items():
            if hit_count:
                corpus.add(str(pack_id).lower())
    return corpus


def infer_multi_bu(
    sector_weights: Optional[Dict[str, float]],
    spend_profile: Dict[str, Any],
) -> bool:
    if sector_weights and len([w for w in sector_weights.values() if w > 0]) > 1:
        return True
    diversity = spend_profile.get("organizational_diversity", {})
    if int(diversity.get("distinct_business_units", 0)) > 1:
        return True
    if int(diversity.get("distinct_cost_centers", 0)) > 1:
        return True
    return False


def build_line_flags(lines: List[Any]) -> Dict[str, Any]:
    """Aggregate line-level fields used by applicable_if rules."""
    gst = lease = rp = False
    rp_high_spend = 0.0
    contract_ok = False
    for line in lines:
        if getattr(line, "gst_treatment", None):
            gst = True
        if getattr(line, "lease_treatment", None):
            lease = True
        if getattr(line, "related_party_flag", False):
            rp = True
            rp_high_spend += float(getattr(line, "reporting_amount", 0.0) or getattr(line, "amount", 0.0))
        status = getattr(line, "contract_status", None)
        if status in ("rolling", "expired", "at_risk"):
            contract_ok = True
        elif status == "in_contract":
            expiry = getattr(line, "contract_expiry_date", None)
            if expiry is not None:
                from datetime import date

                today = date.today()
                months = (expiry.year - today.year) * 12 + (expiry.month - today.month)
                if months < 18:
                    contract_ok = True
    total = sum(
        float(getattr(l, "reporting_amount", 0.0) or getattr(l, "amount", 0.0)) for l in lines
    ) or 1.0
    return {
        "gst_treatment_present": gst,
        "lease_treatment_present": lease,
        "related_party_present": rp,
        "related_party_high": rp and (rp_high_spend / total) > 0.05,
        "contract_status_rolling_or_expiring": contract_ok,
    }
