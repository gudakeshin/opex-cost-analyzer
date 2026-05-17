"""Cache-getter helpers, path constants, and shared module-level constants."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import ROOT_DIR

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
HEURISTIC_TARGETS_PATH = ROOT_DIR / "skills" / "heuristic-analyzer" / "references" / "heuristic_targets.json"
MODEL_PARAMETERS_PATH = ROOT_DIR / "skills" / "savings-modeler" / "references" / "model_parameters.json"
ROOT_CAUSE_THRESHOLDS_PATH = ROOT_DIR / "skills" / "root-cause-analyzer" / "references" / "diagnostic_thresholds.json"
CLASSIFICATION_RULES_PATH = ROOT_DIR / "skills" / "spend-profiler" / "references" / "classification_rules.json"
DPO_BENCHMARKS_PATH = ROOT_DIR / "skills" / "payment-terms-optimizer" / "references" / "dpo_benchmarks.json"
SWITCHING_COST_PATH = ROOT_DIR / "skills" / "spend-profiler" / "references" / "switching_cost_benchmarks.json"
REGULATORY_EXCLUSIONS_PATH = ROOT_DIR / "skills" / "spend-profiler" / "references" / "regulatory_exclusions.json"
SECTOR_PACKS_DIR = ROOT_DIR / "skills" / "sector-packs"
GST_RULES_PATH = ROOT_DIR / "skills" / "indian-tax-optimizer" / "references" / "gst_rules.json"

# ---------------------------------------------------------------------------
# Module-level cache variables
# ---------------------------------------------------------------------------
_HEURISTIC_RANGES: Dict[str, float] | None = None
_PER_EMPLOYEE_TARGETS: Dict[str, float] | None = None
_MODEL_PARAMS: Dict[str, Any] | None = None
_ROOT_CAUSE_THRESHOLDS: Dict[str, Any] | None = None
_CLASSIFICATION_RULES: Dict[str, Any] | None = None
_DPO_BENCHMARKS: Dict[str, Any] | None = None
_SWITCHING_COSTS: Dict[str, Any] | None = None
_REGULATORY_EXCLUSIONS: Dict[str, Any] | None = None
_SECTOR_LEVERS_CACHE: Dict[str, Any] = {}
_GST_RULES: Dict[str, Any] | None = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_HEADCOUNT_APPLICABLE_CATEGORIES = {"HR", "IT", "FACILITIES"}

# Industry signal → sector pack ID mapping
_INDUSTRY_TO_PACK: Dict[str, str] = {
    "banking": "bfsi_banks",
    "bank": "bfsi_banks",
    "nbfc": "bfsi_banks",
    "financial services": "bfsi_banks",
    "bfsi": "bfsi_banks",
    "insurance": "insurance_general",
    "manufacturing": "manufacturing_diversified",
    "industrial": "manufacturing_diversified",
    "auto": "manufacturing_diversified",
    "automotive": "manufacturing_diversified",
    "chemicals": "manufacturing_diversified",
    "it": "it_ites",
    "it services": "it_ites",
    "ites": "it_ites",
    "software": "it_ites",
    "technology": "it_ites",
    "saas": "it_ites",
    "fmcg": "fmcg_consumer",
    "consumer goods": "fmcg_consumer",
    "consumer": "fmcg_consumer",
    "pharma": "pharma_lifesciences",
    "pharmaceutical": "pharma_lifesciences",
    "life sciences": "pharma_lifesciences",
    "healthcare": "pharma_lifesciences",
    "energy": "energy_utilities",
    "utilities": "energy_utilities",
    "power": "energy_utilities",
    "retail": "retail_organized",
    "ecommerce": "retail_organized",
    "e-commerce": "retail_organized",
    "telecom": "telecom_infra",
    "telecommunications": "telecom_infra",
    "psu": "psu_cpse",
    "cpse": "psu_cpse",
    "public sector": "psu_cpse",
    "conglomerate": "conglomerate",
    "diversified": "conglomerate",
    # Healthcare / Hospital Systems (intentionally NOT remapping "healthcare" to avoid
    # breaking existing pharma_lifesciences sessions; add specific hospital signals instead)
    "hospital": "healthcare_hospitals",
    "hospital system": "healthcare_hospitals",
    "hospital chain": "healthcare_hospitals",
    "clinic": "healthcare_hospitals",
    "clinic chain": "healthcare_hospitals",
    "diagnostics": "healthcare_hospitals",
    "diagnostic lab": "healthcare_hospitals",
    "health system": "healthcare_hospitals",
    # Hospitality & Travel
    "hotel": "hospitality_travel",
    "hotel chain": "hospitality_travel",
    "hospitality": "hospitality_travel",
    "restaurant": "hospitality_travel",
    "restaurant chain": "hospitality_travel",
    "travel management": "hospitality_travel",
    "qsr": "hospitality_travel",
    # Financial Services (Non-Bank)
    "asset management": "financial_services_nonbank",
    "asset manager": "financial_services_nonbank",
    "fintech": "financial_services_nonbank",
    "fund management": "financial_services_nonbank",
    "investment management": "financial_services_nonbank",
    "wealth management": "financial_services_nonbank",
    "amc": "financial_services_nonbank",
    "mutual fund": "financial_services_nonbank",
}

# ---------------------------------------------------------------------------
# JSON loader
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Cache getters
# ---------------------------------------------------------------------------

def _get_heuristic_ranges() -> Dict[str, float]:
    global _HEURISTIC_RANGES
    if _HEURISTIC_RANGES is None:
        _HEURISTIC_RANGES = {
            str(k): float(v)
            for k, v in _read_json(HEURISTIC_TARGETS_PATH).get("targets_pct", {}).items()
        }
    return _HEURISTIC_RANGES


def _get_per_employee_targets() -> Dict[str, float]:
    global _PER_EMPLOYEE_TARGETS
    if _PER_EMPLOYEE_TARGETS is None:
        _PER_EMPLOYEE_TARGETS = {
            str(k): float(v)
            for k, v in _read_json(HEURISTIC_TARGETS_PATH).get("per_employee_targets", {}).items()
        }
    return _PER_EMPLOYEE_TARGETS


def _get_model_params() -> Dict[str, Any]:
    global _MODEL_PARAMS
    if _MODEL_PARAMS is None:
        _MODEL_PARAMS = _read_json(MODEL_PARAMETERS_PATH)
    return _MODEL_PARAMS


def _get_root_cause_thresholds() -> Dict[str, Any]:
    global _ROOT_CAUSE_THRESHOLDS
    if _ROOT_CAUSE_THRESHOLDS is None:
        _ROOT_CAUSE_THRESHOLDS = _read_json(ROOT_CAUSE_THRESHOLDS_PATH)
    return _ROOT_CAUSE_THRESHOLDS


def _get_classification_rules() -> Dict[str, Any]:
    global _CLASSIFICATION_RULES
    if _CLASSIFICATION_RULES is None:
        _CLASSIFICATION_RULES = _read_json(CLASSIFICATION_RULES_PATH)
    return _CLASSIFICATION_RULES


def _get_dpo_benchmarks() -> Dict[str, Any]:
    global _DPO_BENCHMARKS
    if _DPO_BENCHMARKS is None:
        _DPO_BENCHMARKS = _read_json(DPO_BENCHMARKS_PATH)
    return _DPO_BENCHMARKS


def _get_switching_costs() -> Dict[str, Any]:
    global _SWITCHING_COSTS
    if _SWITCHING_COSTS is None:
        _SWITCHING_COSTS = _read_json(SWITCHING_COST_PATH)
    return _SWITCHING_COSTS


def _get_regulatory_exclusions() -> Dict[str, Any]:
    global _REGULATORY_EXCLUSIONS
    if _REGULATORY_EXCLUSIONS is None:
        _REGULATORY_EXCLUSIONS = _read_json(REGULATORY_EXCLUSIONS_PATH)
    return _REGULATORY_EXCLUSIONS


def _get_sector_levers(pack_id: str) -> Dict[str, Any]:
    if pack_id not in _SECTOR_LEVERS_CACHE:
        path = SECTOR_PACKS_DIR / pack_id / "sector_levers.json"
        if path.exists():
            _SECTOR_LEVERS_CACHE[pack_id] = _read_json(path)
        else:
            _SECTOR_LEVERS_CACHE[pack_id] = {}
    return _SECTOR_LEVERS_CACHE[pack_id]


def _get_gst_rules() -> Dict[str, Any]:
    global _GST_RULES
    if _GST_RULES is None:
        _GST_RULES = _read_json(GST_RULES_PATH)
    return _GST_RULES


def _resolve_pack_id(industry: str) -> str:
    """Map a free-text industry string to the nearest sector pack ID."""
    if not industry:
        return ""
    lower = industry.lower().strip()
    if lower in _INDUSTRY_TO_PACK:
        return _INDUSTRY_TO_PACK[lower]
    for key, pack in _INDUSTRY_TO_PACK.items():
        if key in lower or lower in key:
            return pack
    return ""
