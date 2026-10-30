#!/usr/bin/env python3
"""
eval/run_categorization_eval.py — Spend Categorization Precision/Recall Evaluator

Tests the keyword-based spend classifier (_classify) against a labeled golden set of
80 spend lines. Reports per-category precision, recall, F1, and macro/micro averages.

SCOPE: This measures keyword-classifier accuracy only (ingestion.py::_classify).
A high score here does NOT imply savings recommendations are correct — it means
supplier descriptions map to taxonomy categories with acceptable accuracy.

Addresses finding C7 from the partner evaluation: "No categorization accuracy
measurement despite a history of substring false-positives."

Usage:
    PYTHONPATH=. python eval/run_categorization_eval.py
    PYTHONPATH=. python eval/run_categorization_eval.py --output eval/categorization_report.md

Exit codes:
    0 — micro-F1 >= PASS_THRESHOLD (0.80)
    1 — micro-F1 < PASS_THRESHOLD
    2 — critical error (taxonomy load failure)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).parent.parent
DEFAULT_OUTPUT_MD = ROOT / "eval" / "categorization_report.md"
DEFAULT_OUTPUT_JSON = ROOT / "eval" / "categorization_scores.json"
PASS_THRESHOLD = 0.80  # micro-F1 to pass

# ---------------------------------------------------------------------------
# Golden set — 80 labeled spend lines
# Format: (description, supplier, expected_category_id, note)
# ---------------------------------------------------------------------------
# Note field marks intent:
#   "clear"  — unambiguous, should always pass
#   "edge"   — known ambiguity, documents expected behavior
#   "false+" — known false-positive pattern being tracked
# ---------------------------------------------------------------------------

GOLDEN_SET: List[Tuple[str, str, str, str]] = [
    # ── IT & Technology ──────────────────────────────────────────────────────
    ("AWS cloud infrastructure", "Amazon Web Services", "IT", "clear"),
    ("Microsoft Azure subscription", "Microsoft", "IT", "clear"),
    ("Salesforce CRM license", "Salesforce Inc", "IT", "clear"),
    ("Laptop procurement Q2", "Dell Technologies", "IT", "clear"),
    ("Cybersecurity firewall renewal", "Palo Alto Networks", "IT", "clear"),
    ("ServiceNow ITSM license", "ServiceNow", "IT", "clear"),
    ("Data center hosting services", "Equinix", "IT", "clear"),
    ("Jira software license", "Atlassian", "IT", "clear"),

    # ── Professional Services ─────────────────────────────────────────────────
    ("Management consulting engagement", "McKinsey & Company", "PROF_SVCS", "clear"),
    ("Tax advisory services", "Deloitte LLP", "PROF_SVCS", "clear"),
    ("Legal counsel retainer", "AZB & Partners", "PROF_SVCS", "clear"),
    ("External audit fees", "KPMG", "PROF_SVCS", "clear"),
    ("Regulatory compliance advisory", "EY India", "PROF_SVCS", "clear"),
    ("Strategy consulting project", "BCG India", "PROF_SVCS", "clear"),

    # ── Facilities & Real Estate ──────────────────────────────────────────────
    ("Office lease — Gurgaon HQ", "DLF Cyber Hub", "FACILITIES", "clear"),
    ("Building maintenance contract", "Jones Lang LaSalle", "FACILITIES", "clear"),
    ("Janitorial cleaning services", "ISS Facility Services", "FACILITIES", "clear"),
    ("HVAC annual maintenance", "Blue Star HVAC", "FACILITIES", "clear"),
    ("Security guard services", "G4S Security", "FACILITIES", "clear"),
    ("Office parking lease", "IndiaBulls Real Estate", "FACILITIES", "clear"),

    # ── Travel & Entertainment ────────────────────────────────────────────────
    ("Business travel flights Q3", "IndiGo Airlines", "TRAVEL", "clear"),
    ("Hotel accommodation — client visit", "Taj Hotels", "TRAVEL", "clear"),
    ("Cab and taxi reimbursements", "Ola Corporate", "TRAVEL", "clear"),
    ("Conference registration fees", "NASSCOM Events", "TRAVEL", "clear"),
    ("Team offsite accommodation", "Club Mahindra", "TRAVEL", "clear"),

    # ── Marketing & Advertising ───────────────────────────────────────────────
    ("Digital advertising campaign", "Google Ads India", "MARKETING", "clear"),
    ("Social media marketing", "Facebook India", "MARKETING", "clear"),
    ("SEO and SEM services", "iProspect India", "MARKETING", "clear"),
    ("Brand campaign production", "Ogilvy India", "MARKETING", "clear"),
    ("PR agency retainer", "Adfactors PR", "MARKETING", "clear"),
    ("Sponsorship — IPL branding", "BCCI", "MARKETING", "clear"),
    # Edge: "brand" keyword present; should be MARKETING not anything else
    ("Brand strategy review", "Brand Finance", "MARKETING", "edge"),

    # ── HR & Recruitment ─────────────────────────────────────────────────────
    ("Recruitment agency fees", "ABC Staffing India", "HR", "clear"),
    ("LinkedIn Recruiter license", "LinkedIn India", "HR", "clear"),
    ("L&D training programs", "Skillsoft India", "HR", "clear"),
    ("Payroll processing services", "ADP India", "HR", "clear"),
    ("Employee benefits administration", "Sodexo Benefits", "HR", "clear"),

    # ── Logistics & Supply Chain ──────────────────────────────────────────────
    ("Freight forwarding services", "DHL Express India", "LOGISTICS", "clear"),
    ("Warehouse management", "Mahindra Logistics", "LOGISTICS", "clear"),
    ("Last-mile courier services", "Delhivery", "LOGISTICS", "clear"),
    ("Ocean freight container shipping", "Maersk India", "LOGISTICS", "clear"),
    ("3PL distribution services", "Blue Dart Express", "LOGISTICS", "clear"),

    # ── Telecommunications ────────────────────────────────────────────────────
    ("Mobile connectivity plan", "Airtel Business", "TELECOM", "clear"),
    ("MPLS leased line", "Tata Communications", "TELECOM", "clear"),
    ("Broadband internet service", "ACT Fibernet", "TELECOM", "clear"),
    ("VoIP telephony system", "RingCentral India", "TELECOM", "clear"),
    ("SD-WAN network services", "Vodafone India", "TELECOM", "clear"),

    # ── Insurance & Risk ─────────────────────────────────────────────────────
    ("Directors and officers insurance", "HDFC Ergo", "INSURANCE", "clear"),
    ("Cyber insurance policy", "ICICI Lombard", "INSURANCE", "clear"),
    ("Property insurance premium", "New India Assurance", "INSURANCE", "clear"),
    ("Workers compensation policy", "United India Insurance", "INSURANCE", "clear"),

    # ── Office Supplies & Equipment ───────────────────────────────────────────
    ("Office stationery and supplies", "Staples India", "OFFICE", "clear"),
    ("Office furniture — desks and chairs", "Herman Miller India", "OFFICE", "clear"),
    ("Printer toner and paper", "HP India", "OFFICE", "clear"),
    ("Pantry and coffee supplies", "Nescafe Corporate", "OFFICE", "clear"),

    # ── R&D & Engineering ─────────────────────────────────────────────────────
    ("Product prototype development", "Tata Elxsi R&D", "RND", "clear"),
    ("Lab equipment procurement", "Thermo Fisher India", "RND", "clear"),
    ("Patent filing and IP management", "Remfry & Sagar", "RND", "clear"),
    ("QA testing automation tools", "Tricentis India", "RND", "clear"),

    # ── Contingent Workforce ──────────────────────────────────────────────────
    ("Contract worker placement", "TeamLease Services", "CONTINGENT", "clear"),
    ("Freelancer SOW — UI design", "Toptal", "CONTINGENT", "clear"),
    ("Temporary staffing — peak season", "Manpower India", "CONTINGENT", "clear"),
    ("Independent contractor — data science", "Upwork India", "CONTINGENT", "clear"),

    # ── Power & Energy ────────────────────────────────────────────────────────
    ("Electricity grid connection charges", "MSEDCL", "POWER_ENERGY", "clear"),
    ("Diesel fuel for backup generators", "HPCL", "POWER_ENERGY", "clear"),
    ("Solar power purchase agreement", "Adani Green Energy", "POWER_ENERGY", "clear"),
    ("LPG industrial fuel supply", "Bharat Gas", "POWER_ENERGY", "clear"),

    # ── Outsourced Operations ─────────────────────────────────────────────────
    ("BPO back-office operations", "Genpact India", "OUTSOURCED", "clear"),
    ("Contact center managed services", "Wipro BPS", "OUTSOURCED", "clear"),
    ("IT managed services outsourcing", "Infosys BPO", "OUTSOURCED", "clear"),

    # ── Known edge / false-positive patterns ─────────────────────────────────
    # "voice" keyword is in TELECOM — "voice of customer" is NOT a telecom expense
    ("Voice of customer research study", "Kantar India", "MARKETING", "false+"),
    # "mobile" keyword is in TELECOM — mobile app dev is IT/RND, not TELECOM
    ("Mobile application development", "ThoughtWorks India", "IT", "false+"),
    # "conference" is in TRAVEL — a software conference tool is IT
    ("Video conferencing software license", "Zoom India", "IT", "false+"),
    # terse / PO-style description with no keywords → should fall to OTHER
    ("PO-2024-00451", "", "OTHER", "edge"),
    ("Vendor payment — Q3 adjustment", "", "OTHER", "edge"),
    # "premium" keyword is in INSURANCE — but premium quality coffee is OFFICE
    ("Premium coffee machine — office pantry", "Nespresso Corporate", "OFFICE", "false+"),
    # "research" keyword in RND — market research is closer to MARKETING
    ("Consumer market research report", "Nielsen India", "MARKETING", "false+"),
]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class CategoryMetrics:
    category_id: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def support(self) -> int:
        return self.tp + self.fn


@dataclass
class EvalResult:
    eval_date: str
    score_type: str
    total: int
    correct: int
    micro_f1: float
    macro_f1: float
    per_category: Dict[str, CategoryMetrics]
    false_positives: List[Dict]
    false_negatives: List[Dict]
    edge_case_accuracy: float
    passed: bool


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _load_classifier():
    """Import the taxonomy and _classify function from ingestion."""
    try:
        from app.services.analysis import load_taxonomy
        from app.services.ingestion import _classify
        taxonomy = load_taxonomy()
        return taxonomy, _classify
    except Exception as exc:
        return None, str(exc)


def run_eval() -> EvalResult:
    taxonomy, classify_or_err = _load_classifier()
    if taxonomy is None:
        print(f"[CRITICAL] Cannot load classifier: {classify_or_err}", file=sys.stderr)
        sys.exit(2)
    classify = classify_or_err  # it's the function

    per_cat: Dict[str, CategoryMetrics] = defaultdict(CategoryMetrics)
    for cm in per_cat.values():
        cm.category_id = "?"

    total = 0
    correct = 0
    false_positives: List[Dict] = []
    false_negatives: List[Dict] = []
    edge_correct = 0
    edge_total = 0

    for description, supplier, expected, note in GOLDEN_SET:
        predicted_id, predicted_name = classify(description, supplier, taxonomy)
        is_correct = predicted_id == expected

        # Ensure CategoryMetrics objects exist
        if expected not in per_cat:
            per_cat[expected] = CategoryMetrics(category_id=expected)
        if predicted_id not in per_cat:
            per_cat[predicted_id] = CategoryMetrics(category_id=predicted_id)

        if is_correct:
            per_cat[expected].tp += 1
            correct += 1
        else:
            per_cat[predicted_id].fp += 1
            per_cat[expected].fn += 1
            false_positives.append({
                "description": description,
                "supplier": supplier,
                "expected": expected,
                "predicted": predicted_id,
                "note": note,
            })

        total += 1

        if note in ("edge", "false+"):
            edge_total += 1
            if is_correct:
                edge_correct += 1

    # Micro F1: weighted by support
    total_tp = sum(cm.tp for cm in per_cat.values())
    total_fp = sum(cm.fp for cm in per_cat.values())
    total_fn = sum(cm.fn for cm in per_cat.values())
    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) > 0 else 0.0

    # Macro F1: unweighted average over categories with support > 0
    cats_with_support = [cm for cm in per_cat.values() if cm.support > 0]
    macro_f1 = sum(cm.f1 for cm in cats_with_support) / len(cats_with_support) if cats_with_support else 0.0

    edge_acc = edge_correct / edge_total if edge_total > 0 else 0.0

    return EvalResult(
        eval_date=date.today().isoformat(),
        score_type="categorical_accuracy",
        total=total,
        correct=correct,
        micro_f1=micro_f1,
        macro_f1=macro_f1,
        per_category=dict(per_cat),
        false_positives=false_positives,
        false_negatives=[],  # FN info is embedded in per_cat
        edge_case_accuracy=edge_acc,
        passed=micro_f1 >= PASS_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------

def _write_json(result: EvalResult, path: Path) -> None:
    payload = {
        "eval_date": result.eval_date,
        "score_type": result.score_type,
        "scope": (
            "keyword-classifier accuracy only — measures whether ingestion.py::_classify "
            "maps spend descriptions to taxonomy categories correctly. Does NOT validate "
            "savings recommendations or analytical quality."
        ),
        "pass_threshold_micro_f1": PASS_THRESHOLD,
        "total": result.total,
        "correct": result.correct,
        "accuracy": round(result.correct / result.total, 4) if result.total else 0,
        "micro_f1": round(result.micro_f1, 4),
        "macro_f1": round(result.macro_f1, 4),
        "edge_case_accuracy": round(result.edge_case_accuracy, 4),
        "passed": result.passed,
        "per_category": {
            cat_id: {
                "precision": round(cm.precision, 3),
                "recall": round(cm.recall, 3),
                "f1": round(cm.f1, 3),
                "support": cm.support,
                "tp": cm.tp,
                "fp": cm.fp,
                "fn": cm.fn,
            }
            for cat_id, cm in sorted(result.per_category.items())
            if cm.support > 0 or cm.fp > 0
        },
        "false_positives": result.false_positives,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_markdown(result: EvalResult, path: Path) -> None:
    status = "✅ PASS" if result.passed else "❌ FAIL"
    accuracy = result.correct / result.total if result.total else 0.0
    lines = [
        "# OpEx Platform — Spend Categorization Eval",
        "",
        f"**Date:** {result.eval_date}  |  **Micro-F1:** {result.micro_f1:.3f}  |"
        f"  **Macro-F1:** {result.macro_f1:.3f}  |  **Status:** {status}",
        "",
        "> **SCOPE:** This eval measures **keyword-classifier accuracy** — whether",
        "> `ingestion.py::_classify` maps spend descriptions to the correct taxonomy",
        "> category. It does NOT validate savings recommendations, benchmark accuracy,",
        "> or analytical quality. A score of 1.0 here means the classifier works;",
        "> it says nothing about whether the savings opportunities are correct.",
        "",
        f"**Golden set:** {result.total} labeled lines  |"
        f"  **Correct:** {result.correct} ({accuracy:.1%})  |"
        f"  **Pass threshold:** micro-F1 ≥ {PASS_THRESHOLD}",
        "",
    ]

    # Per-category table
    lines += [
        "## Per-Category Results",
        "",
        "| Category | Precision | Recall | F1 | Support | TP | FP | FN |",
        "|----------|-----------|--------|----|---------|----|----|----|",
    ]
    cats_sorted = sorted(
        [(cat_id, cm) for cat_id, cm in result.per_category.items() if cm.support > 0],
        key=lambda x: x[1].f1,
        reverse=True,
    )
    for cat_id, cm in cats_sorted:
        f1_str = f"{cm.f1:.2f}"
        flag = " ⚠️" if cm.f1 < 0.70 else ""
        lines.append(
            f"| {cat_id} | {cm.precision:.2f} | {cm.recall:.2f} |"
            f" {f1_str}{flag} | {cm.support} | {cm.tp} | {cm.fp} | {cm.fn} |"
        )

    lines += [
        "",
        f"**Micro-F1:** {result.micro_f1:.3f}  |"
        f"  **Macro-F1:** {result.macro_f1:.3f}  |"
        f"  **Edge-case accuracy:** {result.edge_case_accuracy:.1%}"
        f" ({sum(1 for fp in result.false_positives if fp['note'] in ('edge','false+'))} wrong"
        f" of {sum(1 for _, _, _, n in GOLDEN_SET if n in ('edge','false+'))} edge cases)",
        "",
    ]

    # False positives
    if result.false_positives:
        lines += [
            "## Misclassifications",
            "",
            "| Description | Supplier | Expected | Predicted | Note |",
            "|-------------|----------|----------|-----------|------|",
        ]
        for fp in result.false_positives:
            desc = fp["description"][:45].replace("|", "&#124;")
            sup = fp["supplier"][:20].replace("|", "&#124;")
            lines.append(
                f"| {desc} | {sup} | {fp['expected']} | {fp['predicted']} | {fp['note']} |"
            )
        lines.append("")

    # Top gaps
    failing_cats = [(cat_id, cm) for cat_id, cm in cats_sorted if cm.f1 < 0.70]
    if failing_cats:
        lines += [
            "## Categories Below 0.70 F1",
            "",
            "These categories have low classification accuracy and may produce incorrect"
            " savings analysis.",
            "",
        ]
        for cat_id, cm in failing_cats:
            fps_for_cat = [fp for fp in result.false_positives if fp["expected"] == cat_id]
            fns_for_cat = [fp for fp in result.false_positives if fp["predicted"] == cat_id and fp["expected"] != cat_id]
            lines += [
                f"### {cat_id} — F1 {cm.f1:.2f} (P={cm.precision:.2f}, R={cm.recall:.2f})",
                "",
            ]
            if fps_for_cat:
                lines.append(f"**Missed (FN):** " + "; ".join(f'"{fp["description"]}"' for fp in fps_for_cat[:3]))
                lines.append("")
            if fns_for_cat:
                lines.append(f"**Wrong prediction (FP):** " + "; ".join(f'"{fp["description"]}" → predicted {fp["predicted"]}' for fp in fns_for_cat[:3]))
                lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Spend Categorization Precision/Recall Evaluator")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    print(f"Running categorization eval on {len(GOLDEN_SET)} golden lines...")

    result = run_eval()

    json_path = args.output.with_suffix(".json") if not args.json_only else args.output
    if args.json_only:
        _write_json(result, json_path)
    else:
        _write_json(result, DEFAULT_OUTPUT_JSON)
        _write_markdown(result, args.output)

    # Summary
    print(f"\n{'='*60}")
    print(f"CATEGORIZATION EVAL — {result.eval_date}")
    print(f"{'='*60}")
    print(f"Scope:        keyword-classifier accuracy (NOT analytical quality)")
    print(f"Total:        {result.total} lines  |  Correct: {result.correct}")
    print(f"Micro-F1:     {result.micro_f1:.3f}  ({'PASS' if result.passed else 'FAIL'}, threshold {PASS_THRESHOLD})")
    print(f"Macro-F1:     {result.macro_f1:.3f}")
    print(f"Edge cases:   {result.edge_case_accuracy:.1%} correct")
    print()

    if result.false_positives:
        print(f"Misclassifications ({len(result.false_positives)}):")
        for fp in result.false_positives[:10]:
            print(f"  [{fp['note']}] '{fp['description'][:40]}' → predicted {fp['predicted']}, expected {fp['expected']}")
        if len(result.false_positives) > 10:
            print(f"  ... and {len(result.false_positives) - 10} more (see report)")
    print()

    if not args.json_only:
        print(f"Report: {args.output}")
        print(f"Scores: {DEFAULT_OUTPUT_JSON}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
