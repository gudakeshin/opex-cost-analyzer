"""Schema and tool definition for ask_business_clarification."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

ASK_BUSINESS_CLARIFICATION_TOOL = {
    "name": "ask_business_clarification",
    "description": (
        "Pause analysis and ask the FP&A user to choose how to proceed when data "
        "or context is ambiguous. Options must be analytical paths or accounting "
        "treatments in business terms — not technical instructions."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Core clarifying question in business terms.",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 4,
                "description": "2-4 highly probable analytical paths or accounting treatments.",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why human intervention is required.",
            },
        },
        "required": ["question", "options", "reasoning"],
    },
}


class BusinessClarificationPayload(BaseModel):
    question: str
    options: list[str] = Field(min_length=2, max_length=4)
    reasoning: str

    @field_validator("options")
    @classmethod
    def validate_options_count(cls, v: list[str]) -> list[str]:
        cleaned = [o.strip() for o in v if o and o.strip()]
        if len(cleaned) < 2 or len(cleaned) > 4:
            raise ValueError("options must contain between 2 and 4 non-empty items")
        return cleaned


class ClarificationAnswer(BaseModel):
    selected_option: str | None = None
    free_text: str | None = None

    def has_response(self) -> bool:
        return bool((self.selected_option or "").strip() or (self.free_text or "").strip())
