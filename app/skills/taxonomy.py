"""Skill behavioral taxonomy — kind, runtime, weight defaults."""
from __future__ import annotations

from typing import Dict, Literal, Optional

SkillKind = Literal["analysis", "quality_gate", "output", "security", "ingestion"]
SkillRuntime = Literal["python", "declarative"]
SkillWeight = Literal["light", "heavy"]

# Functional tier map (shared with workbench catalog).
TIER_MAP: Dict[str, str] = {
    "spend-profiler": "Diagnostics",
    "bva-analyzer": "Diagnostics",
    "temporal-analyzer": "Diagnostics",
    "internal-benchmarker": "Diagnostics",
    "peer-benchmarker": "Benchmarking",
    "heuristic-analyzer": "Benchmarking",
    "peer-disclosure-miner": "Benchmarking",
    "payment-terms-optimizer": "Working Capital",
    "root-cause-analyzer": "Savings & Value",
    "savings-modeler": "Savings & Value",
    "value-bridge-calculator": "Savings & Value",
    "data-validator": "Savings & Value",
    "evidence-gatherer": "Savings & Value",
    "sme-critique": "Savings & Value",
    "assumption-register": "Savings & Value",
    "zbb-modeler": "Savings & Value",
    "scenario-modeler": "Strategic",
    "value-to-shareholder-bridge": "Strategic",
    "indian-tax-optimizer": "Compliance & India",
    "brsr-cobenefit-calculator": "Compliance & India",
    "gstr-reconciler": "Compliance & India",
    "msme-compliance-checker": "Compliance & India",
    "conflict-detector": "Enterprise Data",
    "vendor-master-builder": "Enterprise Data",
    "consolidation-analyzer": "Enterprise Data",
    "contract-lifecycle-manager": "Enterprise Data",
    "cost-to-serve-analyzer": "Enterprise Data",
    "chart-builder": "Outputs & Reporting",
    "dashboard-builder": "Outputs & Reporting",
    "business-case-builder": "Outputs & Reporting",
    "export-formatter": "Outputs & Reporting",
    "analysis-synthesizer": "Outputs & Reporting",
    "executive-communication": "Outputs & Reporting",
    "document-contextualizer": "Outputs & Reporting",
    "data-quality-gate": "Diagnostics",
}

_KIND_OVERRIDES: Dict[str, SkillKind] = {
    "sme-critique": "quality_gate",
    "data-quality-gate": "quality_gate",
    "pii-stripper": "security",
    "data-classifier": "security",
    "llm-context-builder": "security",
    "document-contextualizer": "ingestion",
}

_WEIGHT_OVERRIDES: Dict[str, SkillWeight] = {
    "export-formatter": "heavy",
    "business-case-builder": "light",
}

_OUTPUT_TIER = "Outputs & Reporting"


def classify_kind(name: str) -> SkillKind:
    if name in _KIND_OVERRIDES:
        return _KIND_OVERRIDES[name]
    if TIER_MAP.get(name) == _OUTPUT_TIER:
        return "output"
    return "analysis"


def classify_weight(name: str, *, kind: Optional[SkillKind] = None) -> SkillWeight:
    if name in _WEIGHT_OVERRIDES:
        return _WEIGHT_OVERRIDES[name]
    resolved_kind = kind or classify_kind(name)
    if resolved_kind == "output" and name in ("export-formatter",):
        return "heavy"
    return "light"
