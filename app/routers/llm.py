"""LLM model catalog for the analysis UI."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from app.config import LLM_PROVIDER
from app.services.llm_selection import available_models, default_model_id

router = APIRouter()


@router.get("/api/v1/llm/models")
def list_llm_models() -> Dict[str, Any]:
    models = available_models()
    return {
        "models": models,
        "default_model_id": default_model_id(),
        "default_provider": LLM_PROVIDER,
    }
