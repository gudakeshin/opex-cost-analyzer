from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.schemas import BenchmarkDatasetCreateRequest, BenchmarkSelectRequest, PeerSetCreateRequest
from app.services.benchmarks import (
    benchmark_csv_template,
    create_dataset,
    create_peer_set,
    dataset_coverage,
    get_peer_set,
    ingest_benchmark_csv,
    list_datasets,
    list_peer_sets,
    select_best_dataset,
)
from app.services.compliance import append_audit_event

router = APIRouter()


@router.get("/api/v1/template/benchmark-csv")
def download_benchmark_template() -> Response:
    """Return downloadable benchmark CSV template (APQC-style peer percentiles)."""
    return Response(
        content=benchmark_csv_template(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=benchmark_template.csv"},
    )


@router.get("/api/v1/benchmarks")
def get_benchmark_datasets() -> Dict[str, Any]:
    return {"datasets": list_datasets()}


@router.post("/api/v1/benchmarks")
def post_benchmark_dataset(payload: BenchmarkDatasetCreateRequest) -> Dict[str, Any]:
    ds = create_dataset(payload.model_dump())
    append_audit_event(f"benchmark_dataset_ingested id={ds['dataset_id']}")
    return ds


@router.get("/api/v1/benchmarks/{dataset_id}/coverage")
def get_benchmark_dataset_coverage(dataset_id: str) -> Dict[str, Any]:
    cov = dataset_coverage(dataset_id)
    if not cov:
        raise HTTPException(status_code=404, detail="Benchmark dataset not found")
    return cov


@router.post("/api/v1/benchmarks/select")
def post_benchmark_select(payload: BenchmarkSelectRequest) -> Dict[str, Any]:
    return select_best_dataset(
        industry=payload.industry,
        categories=payload.categories,
        annual_revenue=payload.annual_revenue,
    )


@router.post("/api/v1/benchmarks/upload")
async def upload_benchmark_file(
    request: Request,
    file: UploadFile = File(...),
    source: str = Form(...),
    industry_code: str | None = Form(None),
    industry_name: str | None = Form(None),
    vintage_date: str | None = Form(None),
    sample_size: int = Form(0),
    geography: str = Form("India"),
    specificity_score: float = Form(0.7),
    revenue_band_min: float | None = Form(None),
    revenue_band_max: float | None = Form(None),
    license_expiry: str | None = Form(None),
) -> Dict[str, Any]:
    _bench_max = 10 * 1024 * 1024
    cl = request.headers.get("content-length")
    if cl and int(cl) > _bench_max:
        raise HTTPException(status_code=413, detail="Benchmark CSV exceeds 10 MB")
    content = await file.read()
    if len(content) > _bench_max:
        raise HTTPException(status_code=413, detail="Benchmark CSV exceeds 10 MB")
    try:
        dataset = ingest_benchmark_csv(
            file_bytes=content,
            source=source,
            industry_code=industry_code,
            industry_name=industry_name,
            vintage_date=vintage_date,
            sample_size=sample_size,
            geography=geography,
            specificity_score=specificity_score,
            revenue_band_min=revenue_band_min,
            revenue_band_max=revenue_band_max,
            license_expiry=license_expiry,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    append_audit_event(f"benchmark_csv_uploaded source={source} dataset_id={dataset['dataset_id']}")
    return dataset


@router.get("/api/v1/benchmarks/peer-sets")
def list_benchmark_peer_sets() -> Dict[str, Any]:
    return {"peer_sets": list_peer_sets()}


@router.post("/api/v1/benchmarks/peer-sets")
def create_benchmark_peer_set(payload: PeerSetCreateRequest) -> Dict[str, Any]:
    ps = create_peer_set(
        name=payload.name,
        industry=payload.industry,
        dataset_ids=payload.dataset_ids,
        description=payload.description,
        override_categories=payload.override_categories,
    )
    append_audit_event(f"peer_set_created name={payload.name}")
    return ps


@router.get("/api/v1/benchmarks/peer-sets/{name}")
def get_benchmark_peer_set(name: str) -> Dict[str, Any]:
    ps = get_peer_set(name)
    if not ps:
        raise HTTPException(status_code=404, detail="Peer set not found")
    return ps
