"""Evidence layer — structured indexes, lever requirements, and document RAG gathering.

Consolidates the former evidence_index, evidence_requirements, and evidence_gatherer
modules into a single source for category-level signal lookup and initiative evidence.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from app.models import NormalizedSpendLine


def build_contracts_by_category(
    lines: List[NormalizedSpendLine],
    contract_lifecycle: Dict[str, Any] | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Derive category-level contract evidence from spend lines and renewal_alerts."""
    by_category: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()

    for line in lines:
        cat = str(line.category_id or "").lower()
        if not cat:
            continue
        if line.contract_expiry_date or line.contract_status:
            supplier = str(line.supplier or "Unknown")
            key = (cat, supplier)
            if key not in seen:
                seen.add(key)
                by_category[cat].append({
                    "category_id": cat,
                    "supplier": supplier,
                    "contract_expiry_date": str(line.contract_expiry_date) if line.contract_expiry_date else None,
                    "contract_status": line.contract_status,
                    "source": "spend_ledger",
                })

    # Map renewal_alerts to categories via supplier name on spend lines
    supplier_to_cats: Dict[str, set[str]] = defaultdict(set)
    for line in lines:
        cat = str(line.category_id or "").lower()
        supplier = str(line.supplier or "").strip().lower()
        if cat and supplier:
            supplier_to_cats[supplier].add(cat)

    for alert in (contract_lifecycle or {}).get("renewal_alerts", []) or []:
        if not isinstance(alert, dict):
            continue
        supplier = str(alert.get("supplier") or "").strip().lower()
        cats = supplier_to_cats.get(supplier)
        if not cats:
            continue
        for cat in cats:
            key = (cat, supplier)
            if key in seen:
                continue
            seen.add(key)
            by_category[cat].append({
                "category_id": cat,
                "supplier": alert.get("supplier"),
                "contract_expiry_date": alert.get("contract_expiry_date"),
                "contract_status": alert.get("contract_status"),
                "alert_type": alert.get("alert_type"),
                "source": "contract_lifecycle",
            })

    return dict(by_category)


def build_supplier_counts(spend_profile: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for cat_entry in spend_profile.get("category_profile", []) or []:
        if not isinstance(cat_entry, dict):
            continue
        cat_id = str(cat_entry.get("category_id") or "").lower()
        if "supplier_count" in cat_entry:
            counts[cat_id] = int(cat_entry["supplier_count"] or 0)
        elif "top_suppliers" in cat_entry:
            counts[cat_id] = len(cat_entry["top_suppliers"] or [])
    return counts


def build_root_cause_counts(root_causes: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for finding in root_causes.get("root_cause_findings", []) or []:
        if not isinstance(finding, dict):
            continue
        cat_id = str(finding.get("category_id") or "").lower()
        signals = finding.get("root_causes") or []
        counts[cat_id] = len(signals) if isinstance(signals, list) else 0
    return counts


def spend_provenance_files(spend_profile: Dict[str, Any]) -> List[str]:
    files: List[str] = []
    for item in spend_profile.get("ingestion_reports", []) or []:
        if isinstance(item, dict) and item.get("source_file"):
            files.append(str(item["source_file"]))
    return files


@dataclass(frozen=True)
class EvidenceRequirement:
    signal_type: str
    rag_queries: tuple[str, ...]
    data_to_request: str


LEVER_ALIASES: Dict[str, str] = {
    "contract_renegotiation": "renegotiation",
    "maverick_compliance": "maverick_buying_reduction",
    "process_standardization": "process_automation",
    "tail_spend_automation": "process_automation",
    "should_cost_modeling": "strategic_sourcing",
}


def normalize_lever_id(lever: str) -> str:
    """Map savings-modeler lever slugs to SME/evidence registry keys."""
    raw = (lever or "").strip()
    return LEVER_ALIASES.get(raw, raw)


# Default requirements for any lever
_DEFAULT_REQUIREMENTS: tuple[EvidenceRequirement, ...] = (
    EvidenceRequirement(
        signal_type="supplier_fragmentation",
        rag_queries=("{category_name} vendor list supplier master annual spend per vendor",),
        data_to_request="Vendor master for this category with annual spend per vendor",
    ),
    EvidenceRequirement(
        signal_type="structural_drivers",
        rag_queries=("{category_name} cost driver root cause cost centre breakdown",),
        data_to_request="Cost-centre breakdown and diagnostic drivers for this category",
    ),
)

_LEVER_REQUIREMENTS: Dict[str, tuple[EvidenceRequirement, ...]] = {
    "supplier_consolidation": (
        EvidenceRequirement(
            signal_type="contract_terms",
            rag_queries=(
                "{category_name} contract expiry renewal auto-renewal termination notice vendor agreement",
                "{category_name} master service agreement MSA renewal date",
            ),
            data_to_request="Contract register with vendor name, category, expiry date, and auto-renewal clause",
        ),
        EvidenceRequirement(
            signal_type="supplier_fragmentation",
            rag_queries=("{category_name} vendor list supplier master annual spend fragmentation",),
            data_to_request="Vendor master for this category with annual spend per vendor",
        ),
        EvidenceRequirement(
            signal_type="structural_drivers",
            rag_queries=("{category_name} supplier concentration HHI fragmentation",),
            data_to_request="Supplier concentration analysis for this category",
        ),
    ),
    "renegotiation": (
        EvidenceRequirement(
            signal_type="contract_terms",
            rag_queries=(
                "{category_name} contract expiry renewal renegotiation notice period",
            ),
            data_to_request="Contract register with vendor name, category, expiry date, and auto-renewal clause",
        ),
        EvidenceRequirement(
            signal_type="supplier_fragmentation",
            rag_queries=("{category_name} vendor spend supplier master",),
            data_to_request="Vendor master for this category with annual spend per vendor",
        ),
    ),
    "strategic_sourcing": (
        EvidenceRequirement(
            signal_type="contract_terms",
            rag_queries=(
                "{category_name} tender RFP competitive bid last tender date",
            ),
            data_to_request="Last tender date, shortlist size, and whether a should-cost model was used",
        ),
        EvidenceRequirement(
            signal_type="benchmark_specificity",
            rag_queries=("{category_name} peer benchmark comparable industry",),
            data_to_request="Industry-specific benchmark from a sourced advisory database or prior engagement data",
        ),
    ),
    "demand_management": (
        EvidenceRequirement(
            signal_type="cost_centre_split",
            rag_queries=("{category_name} cost centre business unit discretionary spend approval",),
            data_to_request="Cost-centre breakdown and approval flow — which BUs control this spend",
        ),
        EvidenceRequirement(
            signal_type="spend_trend",
            rag_queries=("{category_name} spend trend revenue growth prior year",),
            data_to_request="2-year spend trend by category alongside revenue for the same periods",
        ),
    ),
    "maverick_buying_reduction": (
        EvidenceRequirement(
            signal_type="po_coverage",
            rag_queries=("{category_name} purchase order PO compliance maverick spend",),
            data_to_request="PO coverage rate by category from your ERP (AP module)",
        ),
    ),
    "process_automation": (
        EvidenceRequirement(
            signal_type="transaction_volume",
            rag_queries=("{category_name} invoice count AP transaction volume cycle time",),
            data_to_request="AP transaction log with invoice count and average days-to-pay for this category",
        ),
    ),
    "specification_optimization": (
        EvidenceRequirement(
            signal_type="specification_data",
            rag_queries=("{category_name} SKU specification standardization harmonization",),
            data_to_request="SKU or specification master per BU for this category",
        ),
    ),
}


def requirements_for_initiative(initiative: Dict[str, Any]) -> List[EvidenceRequirement]:
    """Return evidence requirements for a savings initiative based on its lever."""
    lever = normalize_lever_id(str(initiative.get("lever") or initiative.get("lever_id") or ""))
    reqs = _LEVER_REQUIREMENTS.get(lever, _DEFAULT_REQUIREMENTS)
    return list(reqs)


def format_rag_queries(
    requirements: List[EvidenceRequirement],
    category_name: str,
) -> List[tuple[str, str]]:
    """Expand query templates; returns (signal_type, query) pairs."""
    out: List[tuple[str, str]] = []
    for req in requirements:
        for template in req.rag_queries:
            out.append((req.signal_type, template.format(category_name=category_name)))
    return out


def data_to_request_for_signal(signal_type: str, requirements: List[EvidenceRequirement]) -> str:
    for req in requirements:
        if req.signal_type == signal_type:
            return req.data_to_request
    return "Relevant supporting data for this category and lever"

def build_structured_evidence_indexes(
    lines: List[NormalizedSpendLine],
    spend_profile: Dict[str, Any],
    root_causes: Dict[str, Any],
    contract_lifecycle: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build shared category indexes once for gatherer + SME critique."""
    contracts = build_contracts_by_category(lines, contract_lifecycle)
    return {
        "contracts_by_category": contracts,
        "supplier_counts": build_supplier_counts(spend_profile),
        "root_cause_counts": build_root_cause_counts(root_causes),
        "contract_categories": list(contracts.keys()),
    }


def resolve_structured_indexes(
    evidence_output: Dict[str, Any] | None,
    lines: List[NormalizedSpendLine],
    spend_profile: Dict[str, Any],
    root_causes: Dict[str, Any],
    contract_lifecycle: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int], Dict[str, int]]:
    """Reuse indexes from evidence_gatherer output when available."""
    cached = (evidence_output or {}).get("structured_indexes")
    if cached:
        contracts = cached.get("contracts_by_category")
        if contracts is None:
            cats = cached.get("contract_categories") or []
            contracts = {c: [{"category_id": c}] for c in cats}
        return (
            contracts,
            dict(cached.get("supplier_counts") or {}),
            dict(cached.get("root_cause_counts") or {}),
        )
    built = build_structured_evidence_indexes(lines, spend_profile, root_causes, contract_lifecycle)
    return built["contracts_by_category"], built["supplier_counts"], built["root_cause_counts"]


_CONTRACT_KW = re.compile(
    r"\b(contract|expiry|renewal|auto[- ]?renew|termination|msa|master service|agreement|notice period)\b",
    re.I,
)
_SUPPLIER_KW = re.compile(
    r"\b(vendor|supplier|contractor|service provider|annual spend|vendor master)\b",
    re.I,
)
_STRUCTURAL_KW = re.compile(
    r"\b(cost driver|root cause|cost centre|cost center|business unit|hhi|concentration|fragment)\b",
    re.I,
)
_TREND_KW = re.compile(r"\b(trend|prior year|yoy|year over year|growth rate|spend growth)\b", re.I)
_PO_KW = re.compile(r"\b(purchase order|\bpo\b|maverick|off[- ]?contract|compliance)\b", re.I)
_TXN_KW = re.compile(r"\b(invoice|transaction|cycle time|days[- ]?to[- ]?pay|ap module)\b", re.I)
_SPEC_KW = re.compile(r"\b(sku|specification|standardiz|harmoniz|spec master)\b", re.I)
_BENCH_KW = re.compile(r"\b(benchmark|peer|comparable|percentile|p25|p50|p75)\b", re.I)
_COST_CENTRE_KW = re.compile(r"\b(cost centre|cost center|business unit|bu split|department)\b", re.I)


def _chunk_matches_signal(signal_type: str, text: str) -> bool:
    patterns = {
        "contract_terms": _CONTRACT_KW,
        "supplier_fragmentation": _SUPPLIER_KW,
        "structural_drivers": _STRUCTURAL_KW,
        "spend_trend": _TREND_KW,
        "po_coverage": _PO_KW,
        "transaction_volume": _TXN_KW,
        "specification_data": _SPEC_KW,
        "benchmark_specificity": _BENCH_KW,
        "cost_centre_split": _COST_CENTRE_KW,
    }
    pat = patterns.get(signal_type)
    return bool(pat and pat.search(text))


def _parse_chunk_label(chunk: str) -> Tuple[str, str]:
    """Extract [filename › heading] provenance from retrieve_context output."""
    lines = chunk.strip().split("\n", 1)
    if not lines:
        return "", chunk
    header = lines[0].strip()
    body = lines[1] if len(lines) > 1 else ""
    if header.startswith("[") and header.endswith("]"):
        return header[1:-1], body
    return header[:80], body


def _signal_from_structured(
    signal_type: str,
    category_id: str,
    category_name: str,
    contracts_by_category: Dict[str, List[Dict[str, Any]]],
    supplier_counts: Dict[str, int],
    root_cause_counts: Dict[str, int],
    spend_profile: Dict[str, Any],
    benchmarks: Dict[str, Any],
) -> Dict[str, Any] | None:
    cat = category_id.lower()
    prov_files = spend_provenance_files(spend_profile)

    if signal_type == "contract_terms":
        contracts = contracts_by_category.get(cat, [])
        if contracts:
            suppliers = ", ".join(
                str(c.get("supplier") or "") for c in contracts[:3] if c.get("supplier")
            )
            expiry = next(
                (c.get("contract_expiry_date") for c in contracts if c.get("contract_expiry_date")),
                None,
            )
            summary = f"{len(contracts)} contract(s) on file"
            if suppliers:
                summary += f" ({suppliers})"
            if expiry:
                summary += f"; nearest expiry {expiry}"
            return {
                "status": "found",
                "source": "spend_ledger",
                "provenance": prov_files or ["spend ledger"],
                "summary": summary,
            }

    if signal_type == "supplier_fragmentation":
        count = supplier_counts.get(cat, 0)
        if count > 1:
            hhi = None
            for entry in spend_profile.get("category_profile", []) or []:
                if isinstance(entry, dict) and str(entry.get("category_id", "")).lower() == cat:
                    hhi = entry.get("hhi")
                    break
            summary = f"{count} suppliers"
            if hhi is not None:
                summary += f"; HHI {hhi}"
            return {
                "status": "found",
                "source": "spend_ledger",
                "provenance": prov_files or ["spend ledger"],
                "summary": summary,
            }

    if signal_type == "structural_drivers":
        rc_count = root_cause_counts.get(cat, 0)
        if rc_count >= 2:
            return {
                "status": "found",
                "source": "root_cause",
                "provenance": ["root-cause-analyzer"],
                "summary": f"{rc_count} diagnostic drivers identified",
            }
        if rc_count == 1:
            return {
                "status": "partial",
                "source": "root_cause",
                "provenance": ["root-cause-analyzer"],
                "summary": "1 driver identified; additional structural signals needed",
            }

    if signal_type == "cost_centre_split":
        for entry in spend_profile.get("category_profile", []) or []:
            if isinstance(entry, dict) and str(entry.get("category_id", "")).lower() == cat:
                if entry.get("cost_center_breakdown"):
                    return {
                        "status": "found",
                        "source": "spend_ledger",
                        "provenance": prov_files or ["spend ledger"],
                        "summary": "Cost-centre breakdown available",
                    }
        if any(
            isinstance(e, dict) and e.get("cost_center_breakdown")
            for e in spend_profile.get("category_profile", []) or []
        ):
            return {
                "status": "partial",
                "source": "spend_ledger",
                "provenance": prov_files or ["spend ledger"],
                "summary": "Cost-centre data present for other categories",
            }

    if signal_type == "spend_trend":
        if spend_profile.get("trend_analysis"):
            return {
                "status": "found",
                "source": "spend_ledger",
                "provenance": prov_files or ["spend ledger"],
                "summary": "Multi-period spend trend available",
            }

    if signal_type == "po_coverage":
        for entry in spend_profile.get("category_profile", []) or []:
            if isinstance(entry, dict) and str(entry.get("category_id", "")).lower() == cat:
                rate = entry.get("po_coverage_rate")
                if rate is not None:
                    return {
                        "status": "found",
                        "source": "spend_ledger",
                        "provenance": prov_files or ["spend ledger"],
                        "summary": f"PO coverage {float(rate):.0%}",
                    }

    if signal_type == "transaction_volume":
        for entry in spend_profile.get("category_profile", []) or []:
            if isinstance(entry, dict) and str(entry.get("category_id", "")).lower() == cat:
                txn = entry.get("transaction_count")
                if txn is not None:
                    return {
                        "status": "found",
                        "source": "spend_ledger",
                        "provenance": prov_files or ["spend ledger"],
                        "summary": f"{int(txn)} transactions recorded",
                    }

    if signal_type == "specification_data":
        if spend_profile.get("specification_data"):
            return {
                "status": "found",
                "source": "spend_ledger",
                "provenance": prov_files or ["spend ledger"],
                "summary": "Specification master data available",
            }

    if signal_type == "benchmark_specificity":
        for comp in benchmarks.get("comparisons", []) or []:
            if isinstance(comp, dict) and str(comp.get("category_id", "")).lower() == cat:
                spec = float(comp.get("specificity_score") or comp.get("dataset_specificity") or 0.5)
                if spec >= 0.60:
                    return {
                        "status": "found",
                        "source": "benchmark",
                        "provenance": ["peer-benchmarker"],
                        "summary": f"Benchmark specificity {spec:.0%}",
                    }
                if spec >= 0.40:
                    return {
                        "status": "partial",
                        "source": "benchmark",
                        "provenance": ["peer-benchmarker"],
                        "summary": f"Moderate benchmark specificity ({spec:.0%})",
                    }

    return None


def _signal_from_rag_chunks(
    signal_type: str,
    chunks: List[str],
) -> Dict[str, Any] | None:
    matched: List[str] = []
    for chunk in chunks:
        label, body = _parse_chunk_label(chunk)
        if _chunk_matches_signal(signal_type, f"{label} {body}"):
            matched.append(label or "document chunk")

    if not matched:
        return None
    status = "found" if len(matched) >= 2 else "partial"
    return {
        "status": status,
        "source": "document",
        "provenance": matched[:3],
        "summary": f"Referenced in {len(matched)} document section(s)",
    }


def evidence_gatherer(
    savings_model: Dict[str, Any],
    spend_profile: Dict[str, Any],
    root_causes: Dict[str, Any],
    contract_lifecycle: Dict[str, Any],
    benchmarks: Dict[str, Any],
    lines: List[NormalizedSpendLine],
    engagement_id: str = "",
    docs_text: List[str] | None = None,
) -> Dict[str, Any]:
    """Build per-initiative evidence_inventory by searching structured data + RAG."""
    initiatives = savings_model.get("initiatives", []) or []
    if not initiatives:
        return {
            "evidence_inventory": [],
            "corpus_summary": {
                "searched_documents": 0,
                "retrieval_queries_run": 0,
                "chunks_retrieved": 0,
                "signals_found": 0,
            },
        }

    indexes = build_structured_evidence_indexes(lines, spend_profile, root_causes, contract_lifecycle)
    contracts_by_category = indexes["contracts_by_category"]
    supplier_counts = indexes["supplier_counts"]
    root_cause_counts = indexes["root_cause_counts"]

    doc_count = 0
    if engagement_id:
        try:
            from app.services.engagements_store import read_engagement_manifest
            manifest = read_engagement_manifest(engagement_id)
            doc_count = sum(
                1 for d in (manifest.get("documents") or [])
                if isinstance(d, dict) and d.get("status") == "ready"
            )
        except Exception:
            doc_count = len(docs_text or [])

    total_queries = 0
    total_chunks = 0
    signals_found = 0
    inventory: List[Dict[str, Any]] = []

    retrieve_fn = None
    if engagement_id:
        try:
            from app.services.document_index import retrieve_context
            retrieve_fn = retrieve_context
        except Exception:
            retrieve_fn = None

    for initiative in initiatives:
        if not isinstance(initiative, dict):
            continue
        category_id = str(initiative.get("category_id") or "").lower()
        category_name = str(initiative.get("category_name") or category_id)
        lever = str(initiative.get("lever") or initiative.get("lever_id") or "")

        requirements = requirements_for_initiative(initiative)
        req_types = [r.signal_type for r in requirements]
        signals: Dict[str, Any] = {}
        gaps: List[str] = []
        queries_run = 0

        # Cache RAG chunks per initiative (one combined retrieval pass per query)
        rag_cache: Dict[str, List[str]] = {}

        for req in requirements:
            structured = _signal_from_structured(
                req.signal_type,
                category_id,
                category_name,
                contracts_by_category,
                supplier_counts,
                root_cause_counts,
                spend_profile,
                benchmarks,
            )
            if structured and structured.get("status") == "found":
                signals[req.signal_type] = structured
                signals_found += 1
                continue
            if structured and structured.get("status") == "partial":
                signals[req.signal_type] = structured

            # RAG fallback for unresolved requirements
            if engagement_id and retrieve_fn and (
                structured is None or structured.get("status") == "partial"
            ):
                for _sig, query in format_rag_queries([req], category_name):
                    if query in rag_cache:
                        chunks = rag_cache[query]
                    else:
                        chunks = retrieve_fn(engagement_id, query) or []
                        rag_cache[query] = chunks
                        queries_run += 1
                        total_queries += 1
                        total_chunks += len(chunks)
                    rag_hit = _signal_from_rag_chunks(req.signal_type, chunks)
                    if rag_hit:
                        prev = signals.get(req.signal_type)
                        if prev and prev.get("status") == "partial" and rag_hit.get("status") == "partial":
                            signals[req.signal_type] = {
                                **rag_hit,
                                "status": "found",
                                "summary": f"{prev.get('summary', '')}; {rag_hit.get('summary', '')}".strip("; "),
                                "provenance": list(dict.fromkeys(
                                    (prev.get("provenance") or []) + (rag_hit.get("provenance") or [])
                                )),
                            }
                            signals_found += 1
                        elif not prev or prev.get("status") != "found":
                            signals[req.signal_type] = rag_hit
                            if rag_hit.get("status") == "found":
                                signals_found += 1
                        break
            elif structured and req.signal_type not in signals:
                signals[req.signal_type] = structured
                if structured.get("status") in ("found", "partial"):
                    signals_found += 1
            elif req.signal_type not in signals:
                signals[req.signal_type] = {
                    "status": "missing",
                    "source": "none",
                    "provenance": [],
                    "summary": "Not found in spend ledger or document corpus",
                }

        for req_type in req_types:
            sig = signals.get(req_type)
            if not sig or sig.get("status") in ("missing", "partial"):
                gaps.append(req_type)

        inventory.append({
            "category_id": category_id,
            "category_name": category_name,
            "lever": lever,
            "requirements": req_types,
            "signals": signals,
            "gaps": gaps,
            "searched_documents": doc_count,
            "retrieval_queries_run": queries_run,
        })

    return {
        "evidence_inventory": inventory,
        "structured_indexes": {
            "supplier_counts": supplier_counts,
            "root_cause_counts": root_cause_counts,
            "contract_categories": list(contracts_by_category.keys()),
            "contracts_by_category": contracts_by_category,
        },
        "corpus_summary": {
            "searched_documents": doc_count,
            "retrieval_queries_run": total_queries,
            "chunks_retrieved": total_chunks,
            "signals_found": signals_found,
        },
    }