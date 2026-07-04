"""JSON schemas for Anthropic structured-output LLM calls."""

from __future__ import annotations

from app.opar.models import IntentClass

_VALID_INTENTS = sorted(ic.value for ic in IntentClass)

_VALID_CAPABILITIES = sorted(
    {
        "benchmarking",
        "value_modeling",
        "variance_analysis",
        "temporal_trend",
        "working_capital",
        "root_cause",
        "visualization",
        "schema_lookup",
        "document_context",
        "executive_narrative",
        "supplier_breakdown",
    }
)

INTENT_CLASSIFY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": _VALID_INTENTS},
        "explicit_category": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "category_confidence": {"type": "number"},
        "capabilities": {
            "type": "array",
            "items": {"type": "string", "enum": _VALID_CAPABILITIES},
        },
    },
    "required": ["intent", "explicit_category", "confidence", "category_confidence", "capabilities"],
    "additionalProperties": False,
}

CHART_SELECTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "selected_charts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "chart": {
                        "type": "string",
                        "enum": [
                            "pareto_spend",
                            "ranked_bar_spend",
                            "stacked_addressability",
                            "trend_line_total_spend",
                        ],
                    },
                    "reason": {"type": "string"},
                },
                "required": ["chart", "reason"],
                "additionalProperties": False,
            },
        },
        "commentary_points": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 5,
        },
    },
    "required": ["selected_charts", "commentary_points"],
    "additionalProperties": False,
}

NL_AGGREGATE_SPEC_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "group_by": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "metrics": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "filters": {
            "type": ["object", "null"],
            "additionalProperties": True,
        },
        "limit": {"type": "integer"},
        "order_by": {"type": ["string", "null"]},
    },
    "required": ["group_by", "metrics", "limit"],
    "additionalProperties": False,
}

NL_SQL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "minLength": 8},
    },
    "required": ["sql"],
    "additionalProperties": False,
}

SCENARIO_PARSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "target": {"type": "string", "enum": ["portfolio", "category"]},
                    "id": {"type": ["string", "null"]},
                    "savings_pct_delta": {"type": "number"},
                    "timeline_factor": {"type": "number"},
                    "execution_rate": {"type": ["number", "null"]},
                    "addressable_spend_delta_pct": {"type": "number"},
                    "spend_pool_delta_pct": {"type": "number"},
                    "bounce_back_override": {"type": ["string", "null"]},
                    "cost_driver_deltas": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                },
                "required": [
                    "name",
                    "target",
                    "savings_pct_delta",
                    "timeline_factor",
                ],
                "additionalProperties": False,
            },
        },
        "drivers": {
            "type": "object",
            "additionalProperties": {"type": "number"},
        },
    },
    "required": ["scenarios", "drivers"],
    "additionalProperties": False,
}
