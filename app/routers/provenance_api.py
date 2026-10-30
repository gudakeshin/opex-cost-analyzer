"""Provenance replay API — sentence-level narrative tags per turn."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.opar.provenance import load_snapshot

router = APIRouter()


@router.get("/api/v1/provenance/{engagement_id}/{turn_id}")
def get_provenance_snapshot(engagement_id: str, turn_id: str) -> dict:
    records = load_snapshot(engagement_id, turn_id)
    if not records:
        raise HTTPException(status_code=404, detail="No provenance snapshot for this turn")
    return {
        "engagement_id": engagement_id,
        "turn_id": turn_id,
        "sentences": records,
        "sentence_count": len(records),
    }
