"""Sector pack authoring API — create, update, publish, import."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.schemas import (
    SectorPackComponentUpdateRequest,
    SectorPackCreateRequest,
    SectorPackPublishRequest,
)
from app.services.sector_pack_authoring import (
    VALID_COMPONENTS,
    SectorPackAuthoringError,
    create_pack,
    import_pack_from_workbook,
    publish_pack,
    validate_pack_id,
    write_component,
)

router = APIRouter()


def _authoring_error(exc: SectorPackAuthoringError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post("/api/v1/sector-packs")
def create_sector_pack(payload: SectorPackCreateRequest) -> Dict[str, Any]:
    try:
        pack_id = validate_pack_id(payload.pack_id)
        return create_pack(pack_id, sector=payload.sector, description=payload.description)
    except SectorPackAuthoringError as exc:
        msg = str(exc)
        if "already exists" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise _authoring_error(exc) from exc


@router.put("/api/v1/sector-packs/{pack_id}/components/{component}")
def update_pack_component(
    pack_id: str,
    component: str,
    payload: SectorPackComponentUpdateRequest,
) -> Dict[str, str]:
    if component not in VALID_COMPONENTS:
        raise HTTPException(status_code=404, detail=f"Unknown component: {component}")
    try:
        return write_component(pack_id, component, payload.payload)
    except SectorPackAuthoringError as exc:
        raise _authoring_error(exc) from exc


@router.post("/api/v1/sector-packs/{pack_id}/publish")
def publish_sector_pack(pack_id: str, payload: SectorPackPublishRequest) -> Dict[str, Any]:
    try:
        return publish_pack(
            pack_id,
            bump=payload.bump,
            target_status=payload.target_status,
        )
    except SectorPackAuthoringError as exc:
        msg = str(exc)
        if "Regression test failed" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise _authoring_error(exc) from exc


@router.post("/api/v1/sector-packs/import")
async def import_sector_pack_workbook(
    file: UploadFile = File(...),
    dry_run: bool = Query(True),
    pack_id: Optional[str] = None,
) -> Dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    try:
        return import_pack_from_workbook(data, dry_run=dry_run, pack_id=pack_id)
    except SectorPackAuthoringError as exc:
        raise _authoring_error(exc) from exc