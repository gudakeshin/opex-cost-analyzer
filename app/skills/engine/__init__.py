"""Re-export facade for app.skills.engine.

All public names from the original engine.py are re-exported here so that
any existing import like `from app.skills.engine import foo` continues to work
without modification.
"""
from __future__ import annotations

# _loaders — path constants, cache getters, shared helpers
from ._loaders import (
    HEURISTIC_TARGETS_PATH,
    MODEL_PARAMETERS_PATH,
    ROOT_CAUSE_THRESHOLDS_PATH,
    CLASSIFICATION_RULES_PATH,
    DPO_BENCHMARKS_PATH,
    SWITCHING_COST_PATH,
    REGULATORY_EXCLUSIONS_PATH,
    SECTOR_PACKS_DIR,
    GST_RULES_PATH,
    _HEADCOUNT_APPLICABLE_CATEGORIES,
    _INDUSTRY_TO_PACK,
    _read_json,
    _get_heuristic_ranges,
    _get_per_employee_targets,
    _get_model_params,
    _get_root_cause_thresholds,
    _get_classification_rules,
    _get_dpo_benchmarks,
    _get_switching_costs,
    _get_regulatory_exclusions,
    _get_sector_levers,
    _get_gst_rules,
    _resolve_pack_id,
)

# profiler — spend profiling, classification, industry inference, lever resolution
from .profiler import (
    _DOC_INDUSTRY_SIGNALS,
    _contract_addressability_multiplier,
    _regulatory_addressability_override,
    _switching_cost_offset,
    _classify_line,
    classify_cost_behaviour,
    classify_discretionary,
    infer_industry_from_spend,
    _evaluate_lever_signals,
    _build_lever_entry,
    resolve_eligible_levers,
    spend_profiler,
    chart_builder,
    document_contextualizer,
)

# benchmarking — peer/internal benchmarking, heuristics, root cause
from .benchmarking import (
    _category_pct_of_revenue,
    peer_benchmarker,
    internal_benchmarker,
    heuristic_analyzer,
    root_cause_analyzer,
)

# savings — savings modeler, value bridge, data validator, IRR
from .savings import (
    _compute_irr,
    savings_modeler,
    build_raw_rows,
    value_bridge_calculator,
    data_validator,
)

# fpa — BvA, temporal, payment terms
from .fpa import (
    bva_analyzer,
    temporal_analyzer,
    payment_terms_optimizer,
)

# compliance — Indian tax, GSTR, MSME, BRSR
from .compliance import (
    indian_tax_optimizer,
    gstr_reconciler,
    msme_compliance_checker,
    brsr_cobenefit_calculator,
)

# context — PII, data classification, LLM context, assumption register,
#            vendor master, consolidation
from .context import (
    pii_stripper,
    data_classifier,
    llm_context_builder,
    assumption_register,
    vendor_master_builder,
    consolidation_analyzer,
)

# sme_critique — evidence qualification and probe question engine
from .sme_critique import sme_critique_analyzer

# strategic — scenario modeler, shareholder bridge, peer disclosure miner,
#              contract lifecycle, conflict detector, cost-to-serve, ZBB
from .strategic import (
    _PEER_COST_PATTERNS,
    scenario_modeler,
    value_to_shareholder_bridge,
    peer_disclosure_miner,
    contract_lifecycle_manager,
    conflict_detector,
    cost_to_serve_analyzer,
    zbb_modeler,
)

__all__ = [
    # paths
    "HEURISTIC_TARGETS_PATH",
    "MODEL_PARAMETERS_PATH",
    "ROOT_CAUSE_THRESHOLDS_PATH",
    "CLASSIFICATION_RULES_PATH",
    "DPO_BENCHMARKS_PATH",
    "SWITCHING_COST_PATH",
    "REGULATORY_EXCLUSIONS_PATH",
    "SECTOR_PACKS_DIR",
    "GST_RULES_PATH",
    # constants
    "_HEADCOUNT_APPLICABLE_CATEGORIES",
    "_INDUSTRY_TO_PACK",
    "_DOC_INDUSTRY_SIGNALS",
    "_PEER_COST_PATTERNS",
    # loaders
    "_read_json",
    "_get_heuristic_ranges",
    "_get_per_employee_targets",
    "_get_model_params",
    "_get_root_cause_thresholds",
    "_get_classification_rules",
    "_get_dpo_benchmarks",
    "_get_switching_costs",
    "_get_regulatory_exclusions",
    "_get_sector_levers",
    "_get_gst_rules",
    "_resolve_pack_id",
    # profiler helpers
    "_contract_addressability_multiplier",
    "_regulatory_addressability_override",
    "_switching_cost_offset",
    "_classify_line",
    "classify_cost_behaviour",
    "classify_discretionary",
    "infer_industry_from_spend",
    "_evaluate_lever_signals",
    "_build_lever_entry",
    "resolve_eligible_levers",
    # profiler skills
    "spend_profiler",
    "chart_builder",
    "document_contextualizer",
    # benchmarking
    "_category_pct_of_revenue",
    "peer_benchmarker",
    "internal_benchmarker",
    "heuristic_analyzer",
    "root_cause_analyzer",
    # savings
    "_compute_irr",
    "savings_modeler",
    "build_raw_rows",
    "value_bridge_calculator",
    "data_validator",
    # fpa
    "bva_analyzer",
    "temporal_analyzer",
    "payment_terms_optimizer",
    # compliance
    "indian_tax_optimizer",
    "gstr_reconciler",
    "msme_compliance_checker",
    "brsr_cobenefit_calculator",
    # context
    "pii_stripper",
    "data_classifier",
    "llm_context_builder",
    "assumption_register",
    "vendor_master_builder",
    "consolidation_analyzer",
    # sme critique
    "sme_critique_analyzer",
    # strategic
    "scenario_modeler",
    "value_to_shareholder_bridge",
    "peer_disclosure_miner",
    "contract_lifecycle_manager",
    "conflict_detector",
    "cost_to_serve_analyzer",
    "zbb_modeler",
]
