from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Tuple

from app.config import ANTHROPIC_ENABLED, MEMORY_DIR, UPLOAD_DIR
from app.opar.memory_adapter import get_memory_adapter
from app.opar.models import ObserveContext
from app.skills.model_contextualizer import (
    build_workbook_manifest,
    compute_file_fingerprint,
    should_run_model_contextualizer,
)
from app.storage import read_json


def _extract_explicit_category(msg: str) -> Tuple[str | None, float]:
    lowered = (msg or "").lower()
    patterns = [
        r"(?:in|for|within)\s+([a-z0-9&/\-\s]{3,60}?)\s+(?:costs?|spend|category)\b",
        r"optimi[sz]e\s+my\s+([a-z0-9&/\-\s]{3,60}?)\s+costs?\b",
        r"addressable\s+([a-z0-9&/\-\s]{3,60}?)\s+spend\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, lowered)
        if not m:
            continue
        raw = " ".join((m.group(1) or "").split()).strip(" -_")
        if raw and len(raw) >= 3:
            return raw.title(), 0.8
    return None, 0.0


def _detect_query_capabilities(msg: str) -> List[str]:
    lowered = (msg or "").lower()
    capability_tokens = {
        "benchmarking": ["benchmark", "peer", "compare", "percentile", "industry"],
        "value_modeling": [
            "value bridge",
            "addressable",
            "savings",
            "npv",
            "irr",
            "payback",
            "opportunity",
            "optimize",
            "optimise",
            "cost reduction",
            "cost optimization",
            "cost optimisation",
        ],
        "variance_analysis": ["budget vs actual", "variance", "over budget", "under budget", "bva"],
        "temporal_trend": ["trend", "month", "quarter", "season", "time", "over time"],
        "working_capital": ["payment terms", "dpo", "net 30", "net 45", "working capital"],
        "root_cause": ["why", "driver", "root cause", "cause", "bottleneck"],
        "visualization": ["chart", "graph", "plot", "dashboard", "visual"],
        "schema_lookup": ["schema", "columns", "headers", "semantic map", "field mapping"],
        "document_context": ["document", "contract", "policy", "constraint", "pdf", "docx", "txt"],
        "executive_narrative": ["executive", "board", "cfo", "leadership", "decision-ready"],
    }
    capabilities: List[str] = []
    for capability, tokens in capability_tokens.items():
        if any(t in lowered for t in tokens):
            capabilities.append(capability)
    return capabilities


def _detect_conflict_signals(msg: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Detect multi-source upload signals and surface pre-computed conflict context.

    Returns a dict with keys: multi_source_upload, conflict_count,
    unresolved_conflict_count, has_intercompany_lines, conflict_summary.
    """
    files = manifest.get("files", [])
    source_systems: set = set()
    for f in files:
        ss = f.get("source_system_id") or ""
        if ss:
            source_systems.add(ss)
    # Also detect multi-source from file names hinting at different systems
    sap_kw = ("sap", "gl", "s4hana", "hana")
    ariba_kw = ("ariba", "coupa", "po_register", "ap_")
    bank_kw = ("bank", "mt940", "statement", "ledger")
    gst_kw = ("gstr", "gst_", "2a_", "2b_")
    detected_systems: set = set()
    for f in files:
        fname = (f.get("name") or "").lower()
        if any(k in fname for k in sap_kw):
            detected_systems.add("SAP")
        if any(k in fname for k in ariba_kw):
            detected_systems.add("ARIBA")
        if any(k in fname for k in bank_kw):
            detected_systems.add("BANK")
        if any(k in fname for k in gst_kw):
            detected_systems.add("GSTR")
    all_systems = source_systems | detected_systems
    multi_source = len(all_systems) >= 2 or len(files) >= 2

    # Pull pre-computed conflict state if it exists in manifest
    conflict_state = manifest.get("conflict_state") or {}
    conflict_count = int(conflict_state.get("total") or 0)
    unresolved = int(conflict_state.get("unresolved") or 0)

    # Detect intercompany signals from message text
    ic_keywords = ["intercompany", "related party", "intragroup", "intra-group", "subsidiary", "group entity"]
    has_ic = any(k in msg.lower() for k in ic_keywords) or bool(conflict_state.get("has_intercompany"))

    # Classify intent override for conflict-specific queries
    conflict_query_kw = [
        "conflict", "mismatch", "discrepan", "reconcil", "tds mismatch", "gst mismatch",
        "duplicate vendor", "intercompany", "consolidat",
    ]
    has_conflict_query = any(k in msg.lower() for k in conflict_query_kw)

    return {
        "multi_source_upload": multi_source,
        "conflict_count": conflict_count,
        "unresolved_conflict_count": unresolved,
        "has_intercompany_lines": has_ic,
        "conflict_summary": conflict_state,
        "has_conflict_query": has_conflict_query,
    }


def _classify_intent_rule_based(msg: str) -> Tuple[str, str | None]:
    """Rule-based intent classification. Returns (intent_class, explicit_category).

    Priority order matters: more specific intents checked first so they're not
    swallowed by the broader analysis keywords lower in the list.
    Fallback is general_qa — never upload_data — so conversational messages
    (greetings, questions about results, follow-ups) are handled gracefully.
    """
    lowered = msg.lower().strip()

    # 0. Conflict-specific intents (must check before broader analysis keywords)
    if any(w in lowered for w in ["conflict", "mismatch", "discrepan", "reconcile conflicts", "show conflicts", "resolve conflict"]):
        return "conflict_review", None
    if any(w in lowered for w in ["consolidat", "group view", "entity rollup", "multi-entity", "intercompany elimination"]):
        return "consolidate", None
    if any(w in lowered for w in ["vendor master", "vendor dedup", "duplicate vendor", "canonical vendor"]):
        return "vendor_master", None
    if any(w in lowered for w in ["contract review", "contract lifecycle", "contract expiry", "auto-renewal", "exit penalty"]):
        return "contract_review", None
    if any(w in lowered for w in ["gstr reconcil", "gst reconcil", "gstr-2a", "gstr2a", "itc reconcil", "input tax credit"]):
        return "gstr_reconcile", None
    if any(w in lowered for w in ["zero based", "zbb ", " zbb", "zero-based"]):
        return "zbb", None

    # 0.5 FP&A-specific intents — checked before the generic value/benchmark
    # keywords so NPV-sensitivity, savings-plan, trend, BvA, working-capital and
    # cost-to-serve asks route to their dedicated DAGs instead of value_bridge.
    if any(w in lowered for w in ["sensitivity", "what if", "what-if", "stress test", "discount rate", "scenario analysis"]):
        return "sensitivity", None
    if any(w in lowered for w in ["savings plan", "savings roadmap", "3-year plan", "three year plan", "initiative roadmap"]):
        return "savings_plan", None
    if any(w in lowered for w in ["cost to serve", "cost-to-serve", "per-employee cost", "per employee cost", "unprofitable segment", "segment profitability"]):
        return "cost_to_serve", None
    if any(w in lowered for w in ["payment terms", "dpo", "days payable", "working capital"]):
        return "payment_terms", None
    if any(w in lowered for w in ["budget vs", "budget versus", "budget-vs", "variance analysis", "bva", "over budget", "under budget", "budget variance"]):
        return "bva", None
    if any(w in lowered for w in ["year over year", "year-over-year", "yoy", "qoq", "month over month", "run rate", "run-rate", "spend trend", "trend analysis", "trend over time"]):
        return "temporal", None
    if any(w in lowered for w in ["drill down", "drill-down", "deep dive", "deep-dive", "drill into"]):
        return "drill_down", None

    # 1. Export / download intent (must precede business_case to avoid partial match)
    if any(w in lowered for w in ["export", "download", "save as docx", "generate docx", "create document"]):
        return "export_business_case", None

    # 2. Business case / proposal
    if any(w in lowered for w in ["business case", "businesscase", "proposal", "generate case"]):
        return "business_case", None

    # 3. Value bridge / savings matrix
    if any(w in lowered for w in [
        "value bridge",
        "valuebridge",
        "value at the table",
        "savings matrix",
        "opportunity",
        "addressable",
        "addressable spend",
        "addressable spends",
        "addressability",
        "optimize cost",
        "optimize costs",
        "optimise cost",
        "optimise costs",
        "optimize my",
        "optimise my",
        "cost optimization",
        "cost optimisation",
        "how can i optimize",
        "how can we optimize",
        "payback",
        "npv",
        "irr",
        "modeled savings",
    ]):
        return "value_bridge", None

    # 3.5. Interrogative capability questions — must precede benchmark keywords so
    # "what can you analyze" / "can you analyze X" route to general_qa, not benchmark.
    if any(lowered.startswith(p) for p in [
        "what can you", "what do you", "what are you able", "can you analyze",
        "can you help", "can you tell", "how do you", "what does this",
        "what will you", "show me what",
    ]):
        return "general_qa", None

    # 4. Full analysis / benchmarking keywords.
    # "analyze" is safe here: step 3.5 already pre-empts interrogative forms
    # ("what can you analyze", "can you analyze X") so only imperative uses
    # ("analyze my spend") reach this step.
    if any(w in lowered for w in [
        "benchmark", "benchmarks", "compare", "peer", "industry", "percentile",
        "analyze", "analysis", "run analysis", "full analysis",
    ]):
        return "benchmark", None
    # 4b. Implicit optimization asks that typically require benchmark/value analysis
    if any(w in lowered for w in [
        "reduce procurement", "reduce cost", "reduce costs", "cost reduction",
        "savings", "optimize spend", "optimization",
    ]):
        return "benchmark", None

    # 5. Explicit upload / file attachment keywords
    if any(w in lowered for w in ["upload", "attach", "add data", "import", "load file", "add file"]):
        return "upload_data", None

    # 6. Default: conversational question — answered from existing context,
    #    NOT by running the analysis pipeline from scratch.
    return "general_qa", None


def _infer_engagement_week(manifest: Dict[str, Any], session_mem: Any) -> int:
    """Infer which engagement week we are in (1–12) from session metadata.

    Precedence: explicit manifest field (clamped to 1–12) → session memory turn count → 1.
    """
    explicit = manifest.get("engagement_week")
    if isinstance(explicit, int) and explicit >= 1:
        return max(1, min(12, explicit))
    # Proxy: count stored turns in session memory
    mem_list = session_mem if isinstance(session_mem, list) else ([session_mem] if session_mem else [])
    turn_count = len([m for m in mem_list if m])
    # Rough mapping: ~3 turns/week
    week = max(1, min(12, (turn_count // 3) + 1))
    return week


def _infer_decision_gate(engagement_week: int, intent_class: str) -> str:
    """Map engagement week to the nearest decision gate label.

    Gate-1: Week 2  — spend profile signed off
    Gate-2: Week 5  — initiative list approved
    Gate-3: Week 9  — business case approved
    Gate-4: Week 11 — implementation launched
    """
    if engagement_week >= 11:
        return "Gate-4"
    if engagement_week >= 9:
        return "Gate-3"
    if engagement_week >= 5:
        return "Gate-2"
    if engagement_week >= 2:
        return "Gate-1"
    return "pre-Gate-1"


def _classify_intent_rule_based_with_meta(msg: str) -> Dict[str, Any]:
    intent, explicit = _classify_intent_rule_based(msg)
    confidence = {
        "export_business_case": 0.98,
        "business_case": 0.9,
        "value_bridge": 0.9,
        "benchmark": 0.85,
        "upload_data": 0.95,
        "general_qa": 0.72,
        "conflict_review": 0.95,
        "consolidate": 0.93,
        "vendor_master": 0.93,
        "contract_review": 0.90,
        "gstr_reconcile": 0.95,
        "zbb": 0.88,
        "sensitivity": 0.88,
        "savings_plan": 0.90,
        "cost_to_serve": 0.88,
        "payment_terms": 0.88,
        "bva": 0.85,
        "temporal": 0.85,
        "drill_down": 0.82,
    }.get(intent, 0.7)
    if explicit is None:
        extracted, category_conf = _extract_explicit_category(msg)
        explicit = extracted
    else:
        category_conf = 0.9
    return {
        "intent_class": intent,
        "explicit_category": explicit,
        "intent_source": "rule_based",
        "intent_confidence": confidence,
        "category_confidence": category_conf if explicit else 0.0,
    }


def classify_intent(msg: str) -> Tuple[str, str | None]:
    """Classify user intent using rule-based classifier."""
    return _classify_intent_rule_based(msg)


def classify_intent_with_meta(msg: str) -> Dict[str, Any]:
    """Classify user intent with source/confidence/category metadata."""
    return _classify_intent_rule_based_with_meta(msg)


def assess_data_quality(
    parse_results: List[Dict[str, Any]], intent: str, manifest: Dict[str, Any]
) -> Tuple[float, List[str]]:
    """Compute data_quality_score from schema completeness, null ratios, required fields."""
    missing: List[str] = []
    score = 0.0
    files = manifest.get("files", [])

    # Build parse_results from manifest if not provided (schemas from upload)
    if not parse_results:
        parse_results = [f.get("schema") for f in files if f.get("schema")]

    spend_files = [f for f in files if Path(f.get("path", "")).suffix.lower() in (".csv", ".xlsx", ".xls")]
    if not spend_files and intent in ("benchmark", "value_bridge", "business_case"):
        missing.append("spend_data")
        return 0.0, missing

    if spend_files:
        score += 0.3  # Has spend file
        # Schema completeness: amount column required
        for f in spend_files:
            schema = f.get("schema", {})
            sem_map = schema.get("semantic_map", {})
            if sem_map.get("amount"):
                score += 0.25
                break
        # Null ratios: penalize high nulls in key columns
        avg_null = 0.0
        null_count = 0
        for pr in parse_results:
            for col in pr.get("columns", []):
                nr = col.get("null_ratio", 0.0)
                if isinstance(nr, (int, float)):
                    avg_null += nr
                    null_count += 1
        if null_count:
            avg_null /= null_count
            if avg_null < 0.1:
                score += 0.15
            elif avg_null < 0.3:
                score += 0.08
        # Required manifest fields
        if manifest.get("industry"):
            score += 0.1
        if manifest.get("annual_revenue"):
            score += 0.2
        else:
            missing.append("annual_revenue")

    if intent in ("benchmark", "value_bridge", "business_case") and not manifest.get("industry"):
        missing.append("industry")

    return min(score, 1.0), missing


def observe(
    msg: str,
    session_id: str,
    user_id: str,
    file_ids: List[str] | None = None,
    manifest: Dict[str, Any] | None = None,
) -> ObserveContext:
    """Assemble ObserveContext from message, session, memory, and files."""
    adapter = get_memory_adapter()
    user_mem = adapter.get_user_memory(user_id)
    session_mem = adapter.get_session_memory(session_id, query=msg, limit=10)
    engagement_id = str(manifest.get("engagement_id") or session_id) if manifest else session_id

    if manifest is None:
        manifest_path = UPLOAD_DIR / session_id / "manifest.json"
        manifest = read_json(manifest_path, {"files": [], "industry": "", "annual_revenue": 0.0})

    files = manifest.get("files", [])
    model_manifest: Dict[str, Any] = dict(manifest.get("model_manifest") or {})
    schema_confirmation_required = False
    schema_confirmation_note: str | None = None
    model_manifest_confidence = float(model_manifest.get("confidence") or 0.0)
    lowered = msg.lower()
    raw_headcount = manifest.get("headcount")
    headcount = float(raw_headcount) if raw_headcount and float(raw_headcount) > 0 else None
    intent_meta = classify_intent_with_meta(msg)
    intent_class = str(intent_meta.get("intent_class") or "general_qa")
    explicit_category = intent_meta.get("explicit_category")
    intent_source = str(intent_meta.get("intent_source") or "rule_based")
    intent_confidence = float(intent_meta.get("intent_confidence") or 0.0)
    category_confidence = float(intent_meta.get("category_confidence") or 0.0)
    query_capabilities = _detect_query_capabilities(msg)
    has_tabular_spend = any(
        Path(f.get("path", "")).suffix.lower() in (".csv", ".xlsx", ".xls")
        for f in files
    )
    has_document_files = any(
        Path(f.get("path", "")).suffix.lower() in (".txt", ".docx", ".pdf")
        for f in files
    )
    has_annual_revenue = bool(float(manifest.get("annual_revenue") or 0.0) > 0)
    has_headcount = headcount is not None
    wants_executive_narrative = any(
        token in lowered for token in [
            "executive",
            "leadership",
            "board",
            "cfo",
            "narrative",
            "recommendation",
            "recommendations",
            "communication",
            "communicate",
            "decision-ready",
            "decision ready",
        ]
    )
    wants_document_context = any(
        token in lowered for token in [
            "document",
            "contract",
            "policy",
            "context",
            "constraint",
            "txt",
            "pdf",
            "docx",
            "summar",
        ]
    )
    wants_spend_visualization = any(
        token in lowered for token in [
            "chart",
            "visual",
            "graph",
            "plot",
            "dashboard",
            "spend profile",
            "spend profiling",
            "spend summary",
        ]
    )

    uploaded_file_ids = file_ids or [f.get("path", "") for f in files if f.get("path")]
    file_parse_status: Dict[str, str] = {}
    for f in files:
        fid = f.get("path", "") or f.get("name", "")
        if f.get("schema"):
            file_parse_status[fid] = "ok"
        else:
            suffix = Path(fid).suffix.lower() if fid else ""
            file_parse_status[fid] = "ok" if suffix in (".csv", ".xlsx", ".xls", ".txt", ".docx", ".pdf") else "partial"

    session_memory = session_mem
    session_state = session_mem
    spend_profile_ready = any(
        "spend-profiler" in str(s.get("content", {})) or "skill_outputs" in str(s.get("content", {}))
        for s in (session_state if isinstance(session_state, list) else [session_state])
    )
    session_state_path = MEMORY_DIR / "session" / f"{session_id}.json"
    spend_profile_ready = spend_profile_ready or bool(read_json(session_state_path, {}))

    parse_results = [f.get("schema") for f in files if f.get("schema")]
    dq_score, missing_fields = assess_data_quality(parse_results, intent_class, manifest)
    engagement_week = _infer_engagement_week(manifest, session_mem)
    decision_gate = _infer_decision_gate(engagement_week, intent_class)
    conflict_signals = _detect_conflict_signals(msg, manifest)
    # If message is a conflict query but intent was misclassified, correct it
    if conflict_signals["has_conflict_query"] and intent_class == "general_qa":
        intent_class = "conflict_review"

    # Planning-model structural interpretation (one-time per workbook fingerprint).
    workbook_fingerprint = compute_file_fingerprint(files)
    try:
        should_contextualize = should_run_model_contextualizer(files, msg)
    except Exception:
        should_contextualize = False

    if should_contextualize:
        existing_fp = str(model_manifest.get("workbook_fingerprint") or "")
        if not model_manifest or (workbook_fingerprint and workbook_fingerprint != existing_fp):
            for f in files:
                path = Path(str(f.get("path") or ""))
                if path.suffix.lower() not in (".xlsx", ".xls") or not path.exists():
                    continue
                try:
                    built, meta = build_workbook_manifest(
                        path,
                        user_message=msg,
                        session_meta=manifest,
                    )
                    model_manifest = built.model_dump()
                    model_manifest["workbook_fingerprint"] = workbook_fingerprint
                    model_manifest["source_file"] = path.name
                    model_manifest["source"] = "llm" if meta.get("llm_used") else "heuristic"
                    model_manifest["fallback_reason"] = meta.get("fallback_reason")
                    manifest["model_manifest"] = model_manifest
                    break
                except Exception:
                    continue
            # Persist newly computed manifest for downstream turns.
            if model_manifest:
                manifest_path = UPLOAD_DIR / session_id / "manifest.json"
                try:
                    manifest_path.write_text(json.dumps(manifest, indent=2))
                except Exception:
                    pass
                adapter.add_session(
                    session_id,
                    {"type": "model_manifest", "model_manifest": model_manifest},
                    {"type": "model_manifest"},
                )
        model_manifest_confidence = float(model_manifest.get("confidence") or 0.0)
        if model_manifest_confidence < 0.70:
            schema_confirmation_required = True
            roles = [
                f"{node.get('sheet_name')}: {node.get('role')}"
                for node in model_manifest.get("sheet_graph", [])[:8]
            ]
            role_hint = "; ".join(roles) if roles else "No sheet roles were confidently detected."
            schema_confirmation_note = (
                "Low-confidence planning model interpretation detected. "
                f"Detected sheet roles: {role_hint}"
            )

    # Only gate analysis intents on data quality/completeness.
    # general_qa and upload_data should never be blocked by clarification —
    # the former is conversational, the latter is exactly how data gets provided.
    _analysis_intents = {"benchmark", "value_bridge", "business_case"}
    clarification_required = bool(
        intent_class in _analysis_intents
        and ("spend_data" in missing_fields or dq_score < 0.6)
    )
    clarification_prompt = None
    if clarification_required and missing_fields:
        parts: list[str] = []
        if "spend_data" in missing_fields:
            parts.append("spend data file (.xlsx / .csv) — attach it using the 📎 button in the chat")
        if "annual_revenue" in missing_fields:
            parts.append("annual revenue (enter it in the session settings above the chat)")
        if "industry" in missing_fields:
            parts.append("industry type (enter it in the session settings above the chat)")
        clarification_prompt = "To run this analysis I need: " + "; and ".join(parts) + "."

    return ObserveContext(
        user_message=msg,
        intent_class=intent_class,
        explicit_category=explicit_category,
        intent_source=intent_source,
        intent_confidence=max(0.0, min(1.0, intent_confidence)),
        category_confidence=max(0.0, min(1.0, category_confidence)),
        query_capabilities=query_capabilities,
        uploaded_file_ids=uploaded_file_ids,
        headcount=headcount,
        spend_profile_ready=spend_profile_ready,
        benchmark_results_ready=spend_profile_ready,
        has_tabular_spend=has_tabular_spend,
        has_document_files=has_document_files,
        has_annual_revenue=has_annual_revenue,
        has_headcount=has_headcount,
        wants_executive_narrative=wants_executive_narrative,
        wants_document_context=wants_document_context,
        wants_spend_visualization=wants_spend_visualization,
        model_manifest=model_manifest,
        model_manifest_confidence=max(0.0, min(1.0, model_manifest_confidence)),
        schema_confirmation_required=schema_confirmation_required,
        schema_confirmation_note=schema_confirmation_note,
        user_memory=user_mem,
        session_memory=session_memory if isinstance(session_memory, list) else [session_memory] if session_memory else [],
        agent_memories=adapter.get_agent_memories(
            ["spend-profiler", "peer-benchmarker", "internal-benchmarker", "heuristic-analyzer", "value-bridge-calculator"]
        ),
        file_parse_status=file_parse_status,
        missing_fields=missing_fields,
        data_quality_score=dq_score,
        clarification_required=clarification_required,
        clarification_prompt=clarification_prompt,
        session_id=session_id,
        user_id=user_id,
        turn_id=session_id,
        engagement_id=engagement_id,
        engagement_week=engagement_week,
        decision_gate=decision_gate,
        multi_source_upload=conflict_signals["multi_source_upload"],
        conflict_count=conflict_signals["conflict_count"],
        unresolved_conflict_count=conflict_signals["unresolved_conflict_count"],
        has_intercompany_lines=conflict_signals["has_intercompany_lines"],
        conflict_summary=conflict_signals["conflict_summary"],
        deep_research_summary=manifest.get("deep_research_summary") or None,
    )
