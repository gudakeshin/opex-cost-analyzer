#!/usr/bin/env python3
"""Synthetic golden fixtures for the context-management quality eval.

Builds deterministic fixtures into ``tests/eval/golden/context_management/``:

  full_skill_payload.json — a realistic 26-skill outputs payload whose pre-slim
      token estimate deliberately exceeds reflect_advisory._LLM_TOKEN_LIMIT, so
      the eval can exercise slimming, relevance filtering, and budget gating
      end-to-end.
  relevance_cases.json    — golden query→capability detection cases plus
      select_relevant_outputs selection/bypass cases with hand-derived
      expected skill sets.
  chat_adversarial.json   — generation spec for the adversarial chat-history
      and oversized-field probes (the runner expands it; only the small spec
      is committed).
  rag_corpus.md           — markdown corpus with uniquely-worded facts per
      section and one section engineered to trigger parent auto-merge.
  rag_cases.json          — query→expect_contains retrieval pairs + the
      auto-merge trigger query.
  expected.json           — snapshot of derived app constants so drift
      surfaces as eval evidence instead of a silent pass.

The initiative/lever builders replicate the shape used in
tests/test_synthesis_payload_budget.py (_initiative/_lever) — duplicated here
rather than imported because tests/ is not a package and shadows eval/ under
pytest. Everything is deterministic (no randomness) so fixtures are committable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "tests" / "eval" / "golden" / "context_management"

_PAYLOAD_PATH = FIXTURES_DIR / "full_skill_payload.json"
_RELEVANCE_PATH = FIXTURES_DIR / "relevance_cases.json"
_CHAT_SPEC_PATH = FIXTURES_DIR / "chat_adversarial.json"
_RAG_CORPUS_PATH = FIXTURES_DIR / "rag_corpus.md"
_RAG_CASES_PATH = FIXTURES_DIR / "rag_cases.json"
_EXPECTED_PATH = FIXTURES_DIR / "expected.json"

# Pre-slim token band the full payload must land in (estimate = chars // 4).
PRESLIM_TOKEN_BAND = (90_000, 120_000)

_N_INITIATIVES = 40
_N_LEVERS = 34


def _fill(phrase: str, n: int) -> str:
    """Deterministic prose filler of exactly n characters."""
    if not phrase.endswith(" "):
        phrase += " "
    return (phrase * (n // len(phrase) + 1))[:n]


# ---------------------------------------------------------------------------
# Full 26-skill payload
# ---------------------------------------------------------------------------

_LEVER_FAMILIES = ("commercial", "demand", "process", "technology")
_CATEGORY_NAMES = (
    "IT & Telecom", "Professional Services", "Logistics", "Facilities",
    "Travel", "Marketing", "Contract Labour", "Packaging", "Utilities",
    "Insurance", "MRO & Spares", "Fleet", "Security Services",
    "Office Supplies", "Cloud & SaaS",
)


def _initiative(idx: int) -> Dict[str, Any]:
    fam = _LEVER_FAMILIES[idx % len(_LEVER_FAMILIES)]
    cat = idx % len(_CATEGORY_NAMES)
    return {
        # synthesis-relevant — must survive slimming
        "category_id": f"CAT{cat:02d}",
        "category_name": _CATEGORY_NAMES[cat],
        "lever": f"lever_{idx % 12}",
        "lever_name": f"Lever {idx % 12}",
        "lever_family": fam,
        "gross_savings": {"low": 0.5 + idx * 0.1, "mid": 1.0 + idx * 0.1, "high": 1.5 + idx * 0.1},
        "net_savings": {"low": 0.4 + idx * 0.1, "mid": 0.8 + idx * 0.1, "high": 1.2 + idx * 0.1},
        "confidence": ("low", "mid", "high")[idx % 3],
        "savings_type": ("run_rate", "one_time", "mixed")[idx % 3],
        "business_rationale": _fill(
            f"Fragmented supplier base in wave {idx} keeps unit rates above the negotiated frame.", 240
        ),
        "risks": [{
            "risk": _fill(f"supplier pushback in wave {idx}", 120),
            "mitigation": _fill("phased award with dual sourcing", 120),
        }],
        # UI-only enrichment — must be stripped from the LLM payload
        "execution_playbook": [
            {"step": _fill(f"Negotiate consolidated master agreement covering tail suppliers wave {idx} step {j}.", 420),
             "owner_role": "CPO"}
            for j in range(3)
        ],
        "change_management": {"plan": _fill(f"Stakeholder cadence and adoption plan for wave {idx}.", 500)},
        "kpis": [
            {"kpi": f"kpi_{j}", "target": _fill("reduce active supplier count by category", 160)}
            for j in range(2)
        ],
        "owner": {"name": f"Owner {idx}", "raci": _fill("R=category manager A=CPO C=finance I=business unit heads", 260)},
        "provenance": {"figures": [
            _fill(f"figure trace for initiative {idx} drawn from normalized spend lines", 420),
            _fill("benchmark percentile source and adjustment factors applied", 420),
        ]},
        "affected_vendors": [f"Vendor {idx}-{j}" for j in range(6)],
        "contract_levers": [_fill("renegotiate auto-renewal and indexation clauses ahead of expiry", 300) for _ in range(2)],
        "condition_precedents": [_fill("contract register validated and renewal calendar confirmed", 180) for _ in range(2)],
        "required_data_fields": [f"field_{j}" for j in range(6)],
        "business_detail_enriched": True,
    }


def _lever(idx: int) -> Dict[str, Any]:
    return {
        "lever_id": f"lever_{idx}",
        "lever_name": f"Lever {idx}",
        "lever_family": _LEVER_FAMILIES[idx % len(_LEVER_FAMILIES)],
        "eligibility_score": round(0.10 + (idx % 80) / 100.0, 2),
        "root_cause_match": idx % 2 == 0,
        "trigger_signals": [f"signal_{idx % 5}"],
        "sustainability_score": 0.8,
        "bounce_back_risk": ("low", "medium", "high")[idx % 3],
        # bulk fields — must be stripped
        "execution_playbook": [
            {"step": _fill(f"Lever {idx} execution step {j} with workstream owners and milestones.", 450)}
            for j in range(2)
        ],
        "condition_precedents": [_fill(f"precondition {j} for lever {idx} validated with data owner", 320) for j in range(2)],
    }


def _category_profile_row(idx: int) -> Dict[str, Any]:
    spend = 50_000_000 - idx * 2_500_000
    return {
        "category_id": f"CAT{idx:02d}",
        "category_name": _CATEGORY_NAMES[idx],
        "spend": spend,
        "spend_pct": round(18.0 - idx, 2),
        "hhi": 0.18 + idx * 0.01,
        "concentration_flag": idx % 3 == 0,
        "benchmark_gap_pct": round(4.0 + idx * 0.3, 1),
        "addressable_spend": spend * 0.6,
        "addressable_pct": 60.0,
        "supplier_count": 12 + idx,
        "fixed_spend": spend * 0.4,
        "variable_spend": spend * 0.6,
        "line_count": 220 + idx * 7,
        "share_of_total": round(18.0 - idx, 2),
        # passthrough bulk a real profile carries
        "top_suppliers": [
            {"supplier": f"Supplier {idx}-{j}", "spend": spend * (0.2 - j * 0.03),
             "note": _fill("multi-year framework with quarterly true-up", 60)}
            for j in range(5)
        ],
        "top_geos": [{"geo": g, "spend_pct": p} for g, p in (("IN-MH", 40), ("IN-KA", 30), ("IN-TN", 30))],
        "monthly_series": [{"month": f"2025-{m:02d}", "spend": spend / 12} for m in range(1, 13)],
    }


def build_full_skill_payload() -> Dict[str, Any]:
    """Realistic 26-skill validated-outputs dict, pre-slim estimate > token limit."""
    levers = [_lever(i) for i in range(_N_LEVERS)]
    payload: Dict[str, Any] = {
        "spend-profiler": {
            "total_spend": 600_000_000,
            "category_count": 15,
            "category_profile": [_category_profile_row(i) for i in range(15)],
        },
        "savings-modeler": {
            "summary": {"total_mid_savings": 84.0, "currency": "INR"},
            "initiatives": [_initiative(i) for i in range(_N_INITIATIVES)],
            "eligible_levers": levers,
        },
        "root-cause-analyzer": {
            "root_cause_findings": [
                {"finding": _fill(f"Root cause {i}: rate variance driven by uncontracted tail spend.", 320),
                 "category_id": f"CAT{i % 15:02d}", "severity": ("high", "medium")[i % 2]}
                for i in range(20)
            ],
            "eligible_levers_summary": levers,
        },
        "sme-critique": {
            "critique_summary": {"verdicts": {"proceed": 6, "probe_first": 4, "redesign": 2}},
            "initiative_critiques": [
                {
                    "category_name": _CATEGORY_NAMES[i % 15],
                    "lever": f"lever_{i % 12}",
                    "sme_verdict": ("proceed", "probe_first")[i % 2],
                    "evidence_maturity": ("low", "medium", "high")[i % 3],
                    "critical_risk": _fill("no contract register for the category", 90),
                    "probe_questions": [
                        {"question": f"Is contract {i} up for renewal this year?",
                         "why_critical": "locks negotiation timing", "extra": _fill("supporting detail", 80)},
                        {"question": "Who owns the demand policy?", "why_critical": "controls volume lever"},
                    ],
                    "bulk_field": _fill(f"extended critique narrative {i}", 500),
                }
                for i in range(12)
            ],
            "portfolio_probes": [
                {"question": f"Portfolio probe {i}", "why_critical": "gates the savings case"} for i in range(6)
            ],
        },
        "bva-analyzer": {
            "variances": [
                {"category_id": f"CAT{i % 15:02d}", "total_variance": 1_000_000 * (20 - i),
                 "price_variance": 400_000, "volume_variance": 350_000, "mix_variance": 250_000,
                 "note": _fill("actuals ran ahead of phased budget", 120)}
                for i in range(20)
            ],
        },
        "temporal-analyzer": {
            "period_trends": [
                {"period": f"2024-{(i % 12) + 1:02d}", "spend": 48_000_000 + i * 250_000,
                 "yoy_pct": round(2.0 + i * 0.2, 1)}
                for i in range(24)
            ],
            "category_trends": [
                {"category_id": f"CAT{i:02d}", "trend": "rising", "cagr_pct": round(3.0 + i * 0.4, 1),
                 "note": _fill("seasonality-adjusted trajectory", 120)}
                for i in range(15)
            ],
            "annualized_run_rate": 610_000_000,
        },
        "payment-terms-optimizer": {
            "opportunities": [
                {"supplier": f"Supplier PT-{i}", "current_terms_days": 30, "target_terms_days": 60,
                 "annual_cash_value": 2_000_000 * (12 - i), "note": _fill("shift to Net-60 at renewal", 140)}
                for i in range(12)
            ],
            "dpo_current": 38.0,
        },
        "peer-benchmarker": {
            "comparisons": [
                {"category_id": f"CAT{i:02d}", "peer_median_pct": 4.2, "company_pct": 5.1,
                 "percentile": 62, "note": _fill("above peer median on revenue-normalized basis", 160)}
                for i in range(15)
            ],
        },
        "internal-benchmarker": {
            "comparisons": [
                {"unit": f"BU-{i}", "metric": "spend_per_head", "gap_pct": round(3.0 + i, 1),
                 "note": _fill("vs best-run internal unit", 140)}
                for i in range(12)
            ],
        },
        "value-bridge-calculator": {
            "value_matrix": [
                {"category_id": f"CAT{i % 15:02d}", "lever": f"lever_{i % 12}",
                 "deduped_mid_savings": 1.2 + i * 0.1, "net_npv": 3.4 + i * 0.2,
                 "payback_months": 9 + i % 12, "confidence": ("low", "mid", "high")[i % 3]}
                for i in range(20)
            ],
            "confidence_bands": {"conservative": 52.0, "base": 84.0, "accelerated": 101.0},
        },
        "evidence-gatherer": {
            "evidence_items": [
                {"claim": f"claim {i}", "source": "normalized_spend",
                 "detail": _fill("two independent spend slices support the figure", 180)}
                for i in range(10)
            ],
        },
        "heuristic-analyzer": {"signals": [{"signal": f"sig_{i}", "strength": 0.5} for i in range(8)]},
        "scenario-modeler": {"scenarios": [{"name": s, "npv": 10.0} for s in ("base", "downside", "upside")]},
        "cost-to-serve-analyzer": {"segments": [{"segment": f"seg_{i}", "cts_pct": 4.0 + i} for i in range(6)]},
        "vendor-master-builder": {"vendor_count": 1240, "duplicates_found": 86},
        "consolidation-analyzer": {"clusters": [{"cluster": f"c{i}", "vendors": 9} for i in range(8)]},
        "conflict-detector": {"conflicts": [{"pair": f"v{i}/v{i+1}", "type": "intercompany"} for i in range(4)]},
        "contract-lifecycle-manager": {
            "renewal_alerts": [
                {"supplier": f"Supplier R-{i}", "renews": f"2026-{(i % 12) + 1:02d}",
                 "note": _fill("auto-renewal with indexation", 110)}
                for i in range(12)
            ],
        },
        "peer-disclosure-miner": {"disclosures": [{"peer": f"Peer {i}", "metric": "opex_pct"} for i in range(5)]},
        "indian-tax-optimizer": {"opportunities": [{"area": "GST ITC", "value": 4_000_000}]},
        "msme-compliance-checker": {"flags": [{"supplier": f"Supplier M-{i}", "rule": "45-day"} for i in range(5)]},
        "value-to-shareholder-bridge": {"ebitda_bps": 42, "narrative": _fill("EBITDA bridge narrative", 400)},
        "brsr-cobenefit-calculator": {"co_benefits": [{"lever": f"lever_{i}", "co2_tons": 120} for i in range(4)]},
    }
    # UI-artefact skills (_SKIP_SKILLS) — present in validated outputs, must never
    # reach the synthesis payload.
    for skip_skill in (
        "chart-builder", "document-contextualizer", "business-case-builder",
        "pii-stripper", "data-classifier", "llm-context-builder",
        "data-validator", "export-formatter", "dashboard-builder",
    ):
        payload[skip_skill] = {
            "artefact": skip_skill,
            "blob": _fill(f"ui artefact body for {skip_skill}", 800),
        }
    return payload


# ---------------------------------------------------------------------------
# Relevance fixtures (CM-06/07/08)
# ---------------------------------------------------------------------------

def build_relevance_fixture() -> Dict[str, Any]:
    # Small per-skill outputs with known item counts (headline checks read them).
    validated_outputs: Dict[str, Any] = {
        "spend-profiler": {"category_profile": [{"category_id": "CAT00"}], "total_spend": 1_000_000},
        "savings-modeler": {"initiatives": [{"lever": "x"}], "summary": {}},
        "value-bridge-calculator": {"value_matrix": [{"lever": "x"}]},
        "sme-critique": {"critique_summary": {}, "initiative_critiques": []},
        "evidence-gatherer": {"evidence_items": [{"claim": "c"}]},
        "peer-benchmarker": {"comparisons": [{"cat": "IT"}, {"cat": "HR"}, {"cat": "TR"}]},
        "internal-benchmarker": {"comparisons": [{"unit": "BU-1"}]},
        "bva-analyzer": {"variances": [{"cat": f"c{i}"} for i in range(9)]},
        "temporal-analyzer": {"period_trends": [{"period": f"p{i}"} for i in range(7)]},
        "payment-terms-optimizer": {"opportunities": [{"supplier": f"s{i}"} for i in range(4)]},
        "root-cause-analyzer": {"root_cause_findings": [{"finding": "f"}]},
        "vendor-master-builder": {"vendor_count": 12},
        "chart-builder": {"charts": []},                 # _SKIP_SKILLS member
        "document-contextualizer": {"context_summary": "memo"},  # _SKIP_SKILLS member
    }
    core = ["spend-profiler", "savings-modeler", "value-bridge-calculator", "sme-critique", "evidence-gatherer"]
    non_core = ["peer-benchmarker", "internal-benchmarker", "bva-analyzer", "temporal-analyzer",
                "payment-terms-optimizer", "root-cause-analyzer", "vendor-master-builder"]

    def expected(extra: List[str]) -> Dict[str, List[str]]:
        selected = sorted(set(core) | set(extra))
        excluded = sorted(s for s in non_core if s not in extra)
        return {"expected_selected": selected, "expected_excluded": excluded}

    selection_cases = [
        {"name": "benchmarking_only", "query": "benchmark my IT spend vs peers",
         "intent_class": "benchmark", "capabilities": ["benchmarking"], "explicit_category": None,
         **expected(["peer-benchmarker", "internal-benchmarker"])},
        {"name": "value_modeling_only", "query": "what savings opportunities exist",
         "intent_class": "value_bridge", "capabilities": ["value_modeling"], "explicit_category": None,
         **expected([])},
        {"name": "variance_plus_trend", "query": "budget vs actual variance and the monthly trend",
         "intent_class": "drill_down", "capabilities": ["variance_analysis", "temporal_trend"],
         "explicit_category": None,
         **expected(["bva-analyzer", "temporal-analyzer"])},
        {"name": "working_capital_with_category", "query": "improve payment terms for IT",
         "intent_class": "drill_down", "capabilities": ["working_capital"], "explicit_category": "IT",
         **expected(["payment-terms-optimizer", "root-cause-analyzer"])},
        {"name": "root_cause_only", "query": "why is logistics cost so high",
         "intent_class": "drill_down", "capabilities": ["root_cause"], "explicit_category": None,
         **expected(["root-cause-analyzer"])},
        {"name": "supplier_breakdown_only", "query": "break down spend by supplier",
         "intent_class": "drill_down", "capabilities": ["supplier_breakdown"], "explicit_category": None,
         **expected(["vendor-master-builder"])},
    ]

    detection_cases = [
        {"query": "benchmark my IT spend against industry peers", "expected": ["benchmarking"]},
        {"query": "what savings opportunities exist and what's the NPV", "expected": ["value_modeling"]},
        {"query": "show budget vs actual variance", "expected": ["variance_analysis"]},
        {"query": "how has spend trended month on month", "expected": ["temporal_trend"]},
        {"query": "can we shift payment terms and lift DPO", "expected": ["working_capital"]},
        {"query": "why is logistics cost so high", "expected": ["root_cause"]},
        {"query": "plot a chart of spend split", "expected": ["visualization"]},
        {"query": "which columns map to which schema roles", "expected": ["schema_lookup"]},
        {"query": "what constraints do our contracts impose", "expected": ["document_context"]},
        {"query": "prepare an executive readout for the CFO", "expected": ["executive_narrative"]},
        {"query": "break down spend by supplier", "expected": ["supplier_breakdown"]},
        {"query": "compare quarter trends for travel by vendor",
         "expected": ["benchmarking", "temporal_trend", "supplier_breakdown"]},
        {"query": "hello", "expected": []},
        {"query": "thanks, sounds good", "expected": []},
    ]

    return {
        "validated_outputs": validated_outputs,
        "selection_cases": selection_cases,
        "detection_cases": detection_cases,
        "headline_checks": [
            {"skill": "temporal-analyzer", "expected_headline": "period-over-period trends across 7 periods"},
            {"skill": "bva-analyzer", "expected_headline": "budget-vs-actuals variance for 9 categories"},
            {"skill": "payment-terms-optimizer", "expected_headline": "4 payment-terms / working-capital opportunities"},
        ],
    }


# ---------------------------------------------------------------------------
# Chat adversarial spec (CM-09/10) — small spec, runner expands deterministically
# ---------------------------------------------------------------------------

def build_chat_spec() -> Dict[str, Any]:
    return {
        "history": {
            "well_formed_turns": 44,
            "turn_char_len": 60,
            # indices 44..49 — the window build_chat_context actually reads
            "tail": [
                {"kind": "valid_long", "label": "t44", "content_chars": 10_000},
                {"kind": "missing_role", "label": "t45"},
                {"kind": "valid", "label": "t46", "content_chars": 200},
                {"kind": "none_content", "label": "t47"},
                {"kind": "valid_long", "label": "t48", "content_chars": 10_000},
                {"kind": "empty_content", "label": "t49"},
            ],
            "expected_window_labels": ["t44", "t46", "t48"],
        },
        "slice_caps": {
            "categories_in": 15, "categories_max": 12,
            "pt_opportunities_in": 9, "pt_opportunities_max": 5,
            "initiatives_in": 20, "initiatives_max": 12,
            "value_matrix_in": 20, "value_matrix_max": 12,
            "root_findings_in": 12, "root_findings_max": 8,
            "renewals_in": 12, "renewals_max": 8,
            "context_summary_chars_in": 5_000, "context_summary_max": 1_200,
        },
        "boundedness": {
            "fat_chars": 200_000,
            "many_items": 500,
            "bounded_contribution_chars": 5_000,
            "fields": [
                "recent_turns", "categories", "payment_terms_opportunities",
                "document_context", "deep_research_summary",
                "business_override_note", "probe_answers", "portfolio_probes",
            ],
        },
    }


# ---------------------------------------------------------------------------
# RAG corpus + cases (CM-11/12)
# ---------------------------------------------------------------------------

_RAG_CORPUS = """# Procurement Context Memo — Aranya Digital Services

## Contract Escalations

The Oracle database maintenance contract carries an auto-escalation clause of
12 percent applied at every anniversary. Procurement flagged the escalation as
the single largest avoidable rate increase in the IT category. The escalation
clause survives assignment, so a reseller switch alone does not remove it.
Renegotiating before the anniversary window closes is the only way to suspend
the auto-escalation for the next cycle.

## Payment Terms

Zenmark Logistics invoices on Net-30 terms across all three distribution hubs.
Treasury modelling shows that shifting Zenmark to Net-60 at the next rate
review releases INR 4.2 crore of working capital without any price concession.
The Zenmark master agreement allows terms amendments at each quarterly review,
which makes the Net-60 shift executable this fiscal year.

## Travel Programme

The company runs three regional travel desks, referred to internally as the
trifecta desks. Consolidating the trifecta desks into a single managed travel
programme saves 18 percent on airfare through route deals and unused-ticket
recovery. The trifecta consolidation also removes duplicated desk fees charged
by each regional agency.

## Cloud Licensing

The Cloudspire enterprise agreement renews in September 2026. Usage telemetry
shows 31 percent of provisioned Cloudspire licences were dormant for the last
two quarters. Right-sizing before the September 2026 renewal is the largest
single software saving available this year.

## MSME Compliance

Velmora Components and its two affiliates are registered MSME suppliers, so
invoices fall under the 45-day payment rule. Any terms-extension programme must
exclude Velmora entities; stretching their terms beyond the 45-day rule creates
statutory interest liability and a disclosure obligation.

## Insurance

The Harbourline group insurance premium increased 22 percent at the last
renewal following two large claims. Brokers advise that a three-year claims
remediation narrative could bring the Harbourline premium back near the
pre-claims baseline at the next renewal.

## Facilities

The Northgate facility lease costs INR 1.4 crore annually and includes a break
clause exercisable in March 2027 with six months notice. Exercising the
Northgate break clause requires a relocation decision by September 2026 at the
latest, given the notice period.

## Kavetail Rebate Provisions

The kavetail rebate provisions in the distributor agreements accrue quarterly
and are settled annually against audited volumes. Finance estimates unclaimed
kavetail rebates of INR 2.1 crore sit with the top four distributors because
volume attestations were never submitted. Recovering the kavetail accruals
needs the attestation backlog cleared before the annual settlement date.

The kavetail clause also entitles the company to interim statements on request.
Requesting interim kavetail statements each quarter would surface accrual gaps
early instead of at annual settlement, and gives procurement a standing data
feed for rebate assurance. The distributor compliance team has confirmed the
kavetail statement requests can be automated through the partner portal.
"""


def build_rag_cases() -> Dict[str, Any]:
    return {
        "merge_query": "kavetail rebate provisions interim statements",
        "broad_query": "INR crore contract renewal percent savings",
        "format_query": "oracle auto-escalation clause",
        "pairs": [
            {"query": "oracle auto-escalation clause percentage", "expect_contains": "12 percent"},
            {"query": "zenmark net-60 working capital release", "expect_contains": "4.2 crore"},
            {"query": "trifecta travel desk consolidation airfare saving", "expect_contains": "18 percent"},
            {"query": "when does the cloudspire enterprise agreement renew", "expect_contains": "September 2026"},
            {"query": "velmora msme payment rule", "expect_contains": "45-day"},
            {"query": "harbourline insurance premium increase", "expect_contains": "22 percent"},
            {"query": "northgate lease break clause date", "expect_contains": "March 2027"},
            {"query": "unclaimed kavetail rebates value", "expect_contains": "2.1 crore"},
        ],
    }


# ---------------------------------------------------------------------------
# expected.json — snapshot of app constants so drift surfaces as evidence
# ---------------------------------------------------------------------------

def build_expected() -> Dict[str, Any]:
    return {
        "preslim_token_band": list(PRESLIM_TOKEN_BAND),
        "llm_token_limit": 80_000,
        "skip_skills": sorted([
            "chart-builder", "document-contextualizer", "business-case-builder",
            "pii-stripper", "data-classifier", "llm-context-builder",
            "data-validator", "export-formatter", "dashboard-builder",
        ]),
        "core_synthesis_skills": sorted([
            "spend-profiler", "savings-modeler", "value-bridge-calculator",
            "sme-critique", "evidence-gatherer",
        ]),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def ensure_fixtures() -> Dict[str, Any]:
    """Build any missing fixture files, then load and return all of them."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    if not _PAYLOAD_PATH.exists():
        _PAYLOAD_PATH.write_text(
            json.dumps(build_full_skill_payload(), indent=1), encoding="utf-8"
        )
    if not _RELEVANCE_PATH.exists():
        _RELEVANCE_PATH.write_text(json.dumps(build_relevance_fixture(), indent=1), encoding="utf-8")
    if not _CHAT_SPEC_PATH.exists():
        _CHAT_SPEC_PATH.write_text(json.dumps(build_chat_spec(), indent=1), encoding="utf-8")
    if not _RAG_CORPUS_PATH.exists():
        _RAG_CORPUS_PATH.write_text(_RAG_CORPUS, encoding="utf-8")
    if not _RAG_CASES_PATH.exists():
        _RAG_CASES_PATH.write_text(json.dumps(build_rag_cases(), indent=1), encoding="utf-8")
    if not _EXPECTED_PATH.exists():
        _EXPECTED_PATH.write_text(json.dumps(build_expected(), indent=1), encoding="utf-8")

    return {
        "full_payload": json.loads(_PAYLOAD_PATH.read_text(encoding="utf-8")),
        "relevance": json.loads(_RELEVANCE_PATH.read_text(encoding="utf-8")),
        "chat_spec": json.loads(_CHAT_SPEC_PATH.read_text(encoding="utf-8")),
        "rag_corpus": _RAG_CORPUS_PATH.read_text(encoding="utf-8"),
        "rag_cases": json.loads(_RAG_CASES_PATH.read_text(encoding="utf-8")),
        "expected": json.loads(_EXPECTED_PATH.read_text(encoding="utf-8")),
    }


if __name__ == "__main__":
    fx = ensure_fixtures()
    blob = json.dumps(fx["full_payload"], default=str)
    est = len(blob) // 4
    lo, hi = PRESLIM_TOKEN_BAND
    band = "IN BAND" if lo <= est <= hi else "OUT OF BAND"
    print(f"full_skill_payload: {len(blob):,} chars ≈ {est:,} tokens [{band} {lo:,}–{hi:,}]")
    print(f"fixtures dir: {FIXTURES_DIR}")
