from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from app.config import DATA_DIR, MAX_UPLOAD_MB, UPLOAD_DIR, logger
from app.routers._shared import (
    _memory,
    merge_context_into_manifest,
    progress_append,
    progress_complete,
    progress_init,
    read_manifest,
    session_dir,
    session_lock,
    utc_now_iso,
    validate_session_id,
    write_manifest,
)
from app.schemas import AnalyzeRequest, DiagnosticContextPatch, SessionCreateRequest, SessionManifestPatch
from app.services.analysis import load_taxonomy, run_core_pipeline
from app.services.compliance import append_audit_event
from app.services.engagement_sanity import apply_engagement_sanity_to_manifest
from app.services.engagement_corpus import load_analysis_corpus
from app.services.engagements_store import (
    create_engagement_manifest,
    read_engagement_manifest,
    register_session_on_engagement,
)
from app.services.ingestion import infer_tabular_schema, parse_document, parse_spend_file_with_report
from app.skills.model_contextualizer import (
    build_workbook_manifest,
    compute_file_fingerprint,
    maybe_interpret_workbook_on_upload,
    should_run_model_contextualizer,
)

router = APIRouter()

SAMPLES_DIR = DATA_DIR / "samples"

_SAMPLE_FILES: Dict[str, Dict[str, str]] = {
    "spend-ledger.csv": {
        "path": "spend_ledger_sample.csv",
        "media_type": "text/csv",
        "download_name": "spend_ledger_sample.csv",
        "description": "Transactional spend ledger (supplier, description, amount)",
    },
    "pnl-expense.csv": {
        "path": "pnl_expense_summary_sample.csv",
        "media_type": "text/csv",
        "download_name": "pnl_expense_summary_sample.csv",
        "description": "Hierarchical P&L-style expense table (CSV)",
    },
    "pnl-expense.xlsx": {
        "path": "pnl_expense_summary_sample.xlsx",
        "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "download_name": "pnl_expense_summary_sample.xlsx",
        "description": "Hierarchical P&L-style expense table (Excel, offset header row)",
    },
    "hul-spend-ledger.csv": {
        "path": "hul_india_spend_ledger_fy25.csv",
        "media_type": "text/csv",
        "download_name": "hul_india_spend_ledger_fy25.csv",
        "description": "HUL India FY25 synthetic spend ledger (FMCG test)",
    },
    "hul-pnl-expense.csv": {
        "path": "hul_india_pnl_expense_fy25.csv",
        "media_type": "text/csv",
        "download_name": "hul_india_pnl_expense_fy25.csv",
        "description": "HUL India FY25 synthetic P&L OpEx extract (lakhs)",
    },
}


@router.get("/api/v1/samples")
def list_sample_files() -> Dict[str, Any]:
    """List downloadable sample spend files for testing uploads."""
    items = []
    for slug, meta in _SAMPLE_FILES.items():
        path = SAMPLES_DIR / meta["path"]
        items.append(
            {
                "id": slug,
                "filename": meta["download_name"],
                "description": meta["description"],
                "download_url": f"/api/v1/samples/{slug}",
                "available": path.is_file(),
            }
        )
    return {"samples": items, "readme": "See data/samples/README.md for layout guidance."}


@router.get("/api/v1/samples/{sample_id}")
def download_sample_file(sample_id: str) -> Response:
    meta = _SAMPLE_FILES.get(sample_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Sample not found")
    path = SAMPLES_DIR / meta["path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sample file missing on server")
    content = path.read_bytes()
    return Response(
        content=content,
        media_type=meta["media_type"],
        headers={"Content-Disposition": f'attachment; filename="{meta["download_name"]}"'},
    )


def _dominant_currency(lines: List[Any]) -> str | None:
    """Currency carrying the largest share of native spend across parsed lines.

    Used to anchor the engagement reporting currency to what the data is
    actually denominated in, instead of falling back to a hard-coded default.
    """
    totals: Dict[str, float] = {}
    for ln in lines:
        ccy = str(getattr(ln, "currency", "") or "").upper().strip()
        if not ccy:
            continue
        try:
            totals[ccy] = totals.get(ccy, 0.0) + abs(float(getattr(ln, "amount", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    if not totals:
        return None
    return max(totals, key=totals.__getitem__)


_TABULAR_SUFFIXES = {".csv", ".xlsx", ".xls", ".json"}


def _collect_source_files(manifest: Dict[str, Any]) -> Dict[str, List[str]]:
    """Gather source-document names for trace attribution, split spend vs context.

    Pulls engagement-level documents (which carry an explicit role) and
    session-local uploads (classified by file extension). Best-effort: missing or
    malformed entries are skipped so tracing never blocks analysis.
    """
    spend: List[str] = []
    context: List[str] = []

    engagement_id = manifest.get("engagement_id")
    if engagement_id:
        try:
            em = read_engagement_manifest(str(engagement_id))
        except Exception:
            em = {}
        for doc in em.get("documents") or []:
            if not isinstance(doc, dict) or doc.get("status") != "ready":
                continue
            name = str(doc.get("filename") or "").strip()
            if not name:
                continue
            role = doc.get("role")
            if role in ("spend_tabular", "mixed"):
                spend.append(name)
            if role in ("context_doc", "mixed"):
                context.append(name)

    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        if Path(name).suffix.lower() in _TABULAR_SUFFIXES:
            spend.append(name)
        else:
            context.append(name)

    return {"spend": sorted(set(spend)), "context": sorted(set(context))}


def _format_ingestion_summary(report: Dict[str, Any]) -> str:
    if report.get("files"):
        parts = [_format_ingestion_summary(f) for f in report.get("files", []) if isinstance(f, dict)]
        return " ".join(p for p in parts if p)
    ingested = report.get("sheets_ingested") or []
    skipped = report.get("sheets_skipped") or []
    lines: List[str] = []
    for item in ingested:
        if isinstance(item, dict):
            lines.append(
                f"Ingested worksheet '{item.get('sheet')}' ({item.get('rows', 0)} lines, {item.get('strategy', 'standard')})."
            )
    for item in skipped[:5]:
        if isinstance(item, dict):
            lines.append(
                f"Skipped '{item.get('sheet')}' ({item.get('role', 'unknown')}: {item.get('reason', '')})."
            )
    return " ".join(lines)


@router.get("/api/template/spend-csv")
@router.get("/api/v1/template/spend-csv")
def download_spend_template() -> Response:
    """Return a downloadable CSV template whose columns match NormalizedSpendLine."""
    headers_row = (
        "supplier,description,amount,currency,business_unit,cost_center_id,"
        "gl_code,country,category,spend_date,fiscal_year,fiscal_period,"
        "amount_type,payment_terms_days,contract_id,contract_expiry_date"
    )
    example_row = (
        "Infosys Ltd,Cloud infrastructure services,5000000,INR,Engineering,"
        "CC-101,5100,India,IT & Cloud,2024-01-31,FY2024,Q4,actual,30,"
        "C-2024-001,2025-12-31"
    )
    csv_content = f"{headers_row}\n{example_row}\n"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=opex_spend_template.csv"},
    )


@router.post("/api/sessions")
@router.post("/api/v1/sessions")
def create_session(payload: SessionCreateRequest) -> Dict[str, Any]:
    session_id = str(uuid.uuid4())
    session_dir(session_id).mkdir(parents=True, exist_ok=True)

    engagement_id = (payload.engagement_id or "").strip()
    if engagement_id:
        from app.routers._shared import validate_engagement_id
        from app.services.engagements_store import ensure_engagement_exists

        validate_engagement_id(engagement_id)
        eng = ensure_engagement_exists(engagement_id)
        company_name = payload.company_name or eng.get("company_name")
        industry = payload.industry or eng.get("industry") or ""
        annual_revenue = payload.annual_revenue or float(eng.get("annual_revenue") or 0.0)
        currency = payload.currency or eng.get("currency")
        headcount = payload.headcount if payload.headcount is not None else eng.get("headcount")
    else:
        eng_manifest = create_engagement_manifest(
            company_name=payload.company_name,
            industry=payload.industry,
            annual_revenue=payload.annual_revenue,
            currency=payload.currency or "INR",
            headcount=payload.headcount,
        )
        engagement_id = eng_manifest["engagement_id"]
        company_name = payload.company_name
        industry = payload.industry or ""
        annual_revenue = payload.annual_revenue
        currency = payload.currency
        headcount = payload.headcount

    manifest = {
        "session_id": session_id,
        "engagement_id": engagement_id,
        "company_name": company_name,
        "industry": industry or "",
        "annual_revenue": annual_revenue,
        "currency": currency,
        "audience": payload.audience or "cfo",
        "headcount": headcount,
        "wacc": payload.wacc,
        "effective_tax_rate": payload.effective_tax_rate,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": [],
    }
    write_manifest(session_id, manifest)
    register_session_on_engagement(engagement_id, session_id)
    append_audit_event(
        f"session_created session_id={session_id} engagement_id={engagement_id}"
    )
    return manifest


@router.post("/api/upload/{session_id}")
@router.post("/api/v1/upload/{session_id}")
async def upload_file(session_id: str, request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    validate_session_id(session_id)
    sdir = session_dir(session_id)
    if not sdir.exists():
        # Recreate if analysis data exists (session dir was wiped but memory intact).
        analysis = _memory.get("session", session_id)
        if analysis:
            sdir.mkdir(parents=True, exist_ok=True)
            recovered: Dict[str, Any] = {
                "session_id": session_id,
                "company_name": analysis.get("company_name", ""),
                "industry": analysis.get("industry", ""),
                "annual_revenue": analysis.get("annual_revenue"),
                "currency": analysis.get("reporting_currency", "INR"),
                "audience": "consultant",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "files": [],
            }
            write_manifest(session_id, recovered)
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    _max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    cl = request.headers.get("content-length")
    if cl and int(cl) > _max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
    content = await file.read()
    if len(content) > _max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
    safe_filename = Path(file.filename or "upload").name
    out_path = session_dir(session_id) / safe_filename
    out_path.write_bytes(content)
    entry: Dict[str, Any] = {
        "name": safe_filename,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(content),
        "path": str(out_path),
    }
    if out_path.suffix.lower() in (".csv", ".xlsx", ".xls"):
        entry["schema"] = await asyncio.to_thread(infer_tabular_schema, out_path)
    elif out_path.suffix.lower() == ".json":
        entry["schema"] = {"format": "json"}
    async with session_lock(session_id):
        manifest = read_manifest(session_id)
        manifest["files"].append(entry)
        if out_path.suffix.lower() in (".xlsx", ".xls"):
            interpreted = await asyncio.to_thread(
                maybe_interpret_workbook_on_upload,
                out_path,
                manifest,
                "",
            )
            if interpreted:
                manifest["model_manifest"] = interpreted
        apply_engagement_sanity_to_manifest(manifest)
        write_manifest(session_id, manifest)
    append_audit_event(f"file_uploaded session_id={session_id} file={safe_filename}")
    sanity = read_manifest(session_id).get("engagement_sanity") or {}
    return {
        "uploaded": safe_filename,
        "size_bytes": len(content),
        "engagement_sanity": sanity,
    }


@router.post("/api/analyze/{session_id}")
@router.post("/api/v1/analyze/{session_id}")
async def analyze_session(session_id: str, payload: AnalyzeRequest) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    if should_run_model_contextualizer(manifest.get("files", []), "run analysis"):
        model_manifest = manifest.get("model_manifest") if isinstance(manifest, dict) else None
        workbook_fingerprint = compute_file_fingerprint(manifest.get("files", []))
        if not model_manifest or str(model_manifest.get("workbook_fingerprint") or "") != workbook_fingerprint:
            for item in manifest.get("files", []):
                path = Path(item.get("path", ""))
                if path.suffix.lower() not in (".xlsx", ".xls") or not path.exists():
                    continue
                try:
                    parsed_manifest, meta = await asyncio.to_thread(
                        build_workbook_manifest,
                        path,
                        user_message="run analysis",
                        session_meta=manifest,
                    )
                    model_manifest = parsed_manifest.model_dump()
                    model_manifest["workbook_fingerprint"] = workbook_fingerprint
                    model_manifest["source_file"] = path.name
                    model_manifest["source"] = "llm" if meta.get("llm_used") else "heuristic"
                    manifest["model_manifest"] = model_manifest
                    write_manifest(session_id, manifest)
                    break
                except Exception:
                    logger.warning(
                        "workbook_manifest_build_failed session_id=%s file=%s",
                        session_id, path.name, exc_info=True,
                    )
                    manifest["workbook_manifest_degraded"] = True
                    continue
    spend_lines, docs_text, ingestion_reports, corpus_warnings, manifest = await asyncio.to_thread(
        load_analysis_corpus, session_id
    )
    if corpus_warnings:
        manifest["corpus_warnings"] = corpus_warnings
    if not spend_lines:
        raise HTTPException(
            status_code=400,
            detail=(
                "No spend data found. Upload a CSV, Excel, or JSON spend file on the Documents page "
                "or attach one in Analysis."
            ),
        )
    manifest["ingestion_report"] = ingestion_reports[0] if len(ingestion_reports) == 1 else {
        "source_file": "multiple",
        "files": ingestion_reports,
    }
    write_manifest(session_id, manifest)
    apply_engagement_sanity_to_manifest(manifest, spend_lines)
    write_manifest(session_id, manifest)
    if payload.currency is not None:
        manifest["currency"] = payload.currency
    if payload.audience is not None:
        manifest["audience"] = payload.audience
    # Anchor reporting currency to the data when the user did not specify one.
    # Precedence: explicit request > manifest > detected-from-data > INR (the
    # platform's Indian-enterprise default). This stops INR ledgers from being
    # reported under a hard-coded USD label.
    detected_currency = _dominant_currency(spend_lines)
    reporting_currency = str(
        payload.currency or manifest.get("currency") or detected_currency or "INR"
    )
    currency_changed = manifest.get("currency") != reporting_currency
    if currency_changed:
        manifest["currency"] = reporting_currency
    if payload.currency is not None or payload.audience is not None or currency_changed:
        write_manifest(session_id, manifest)
    ingestion_summary = _format_ingestion_summary(manifest.get("ingestion_report") or {})
    if corpus_warnings:
        ingestion_summary = (
            f"{ingestion_summary} Warnings: {'; '.join(corpus_warnings[:5])}".strip()
        )

    # Source-document attribution for the analysis trace: engagement-level docs
    # (which carry an explicit role) plus session-local uploads (classified by
    # extension). Names let each trace step cite where its insight came from.
    source_files = _collect_source_files(manifest)

    # Live progress: when the client supplies a run_id it polls
    # GET /api/v1/chat/progress/{run_id} while the pipeline runs.
    run_id = payload.run_id
    progress_cb = None
    if run_id:
        progress_init(run_id, session_id)
        progress_append(run_id, "observe", "Loading spend and context documents…")
        progress_cb = lambda phase, msg: progress_append(run_id, phase, msg)  # noqa: E731

    try:
        analysis = await asyncio.to_thread(
            run_core_pipeline,
            session_id=session_id,
            lines=spend_lines,
            docs_text=docs_text,
            industry=payload.industry or manifest.get("industry") or "",
            annual_revenue=payload.annual_revenue or float(manifest.get("annual_revenue") or 0.0),
            company_name=payload.company_name or manifest.get("company_name"),
            wacc=float(manifest.get("wacc") or payload.wacc or 0.10),
            effective_tax_rate=float(manifest.get("effective_tax_rate") or payload.effective_tax_rate or 0.0),
            reporting_currency=reporting_currency,
            engagement_id=manifest.get("engagement_id"),
            ingestion_summary=ingestion_summary or None,
            progress_cb=progress_cb,
            source_files=source_files,
        )
    except Exception as exc:
        if run_id:
            progress_complete(run_id, failed=True, error=str(exc)[:300])
        raise
    if run_id:
        progress_append(run_id, "reflect", "Analysis complete.")
        progress_complete(run_id)
    manifest_changed = False
    if analysis.get("company_name") and manifest.get("company_name") != analysis["company_name"]:
        manifest["company_name"] = analysis["company_name"]
        manifest_changed = True
    if analysis.get("industry") and manifest.get("industry") != analysis["industry"]:
        manifest["industry"] = analysis["industry"]
        manifest_changed = True
    if analysis.get("annual_revenue") and not manifest.get("annual_revenue"):
        manifest["annual_revenue"] = analysis["annual_revenue"]
        manifest_changed = True
    if manifest_changed:
        manifest.setdefault("gate_label", "Gate 2: Portfolio sign-off")
        write_manifest(session_id, manifest)
    append_audit_event(f"analysis_completed session_id={session_id}")
    return analysis


@router.get("/api/sessions/{session_id}/status")
@router.get("/api/v1/sessions/{session_id}/status")
def get_session_status(session_id: str) -> Dict[str, Any]:
    """Lightweight session probe — always 200; avoids 404 noise when analysis is not ready."""
    validate_session_id(session_id)
    sdir = session_dir(session_id)
    manifest_path = sdir / "manifest.json"
    has_manifest = manifest_path.is_file()
    meta = _memory.get("session_meta", session_id) or _memory.get("session", session_id)
    session_exists = has_manifest or bool(meta)
    analysis = _memory.get("session", session_id)
    has_analysis = bool(analysis)
    manifest = read_manifest(session_id) if has_manifest else {}
    return {
        "session_id": session_id,
        "session_exists": session_exists,
        "has_manifest": has_manifest,
        "has_analysis": has_analysis,
        "file_count": len(manifest.get("files", [])) if manifest else 0,
    }


@router.get("/api/sessions/{session_id}")
@router.get("/api/v1/sessions/{session_id}")
def get_session_analysis(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    result = _memory.get("session", session_id)
    if not result:
        raise HTTPException(status_code=404, detail="No analysis for session")
    return result


@router.patch("/api/sessions/{session_id}/manifest")
@router.patch("/api/v1/sessions/{session_id}/manifest")
async def patch_session_manifest(session_id: str, payload: SessionManifestPatch) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    async with session_lock(session_id):
        manifest = read_manifest(session_id)
        if merge_context_into_manifest(
            manifest,
            company_name=payload.company_name,
            industry=payload.industry,
            annual_revenue=payload.annual_revenue,
            currency=payload.currency,
            audience=payload.audience,
        ):
            write_manifest(session_id, manifest)
    manifest.setdefault("session_id", session_id)
    return manifest


@router.get("/api/sessions/{session_id}/manifest")
@router.get("/api/v1/sessions/{session_id}/manifest")
def get_session_manifest(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    sdir = session_dir(session_id)
    if not sdir.exists():
        # Try to recover from persisted data before giving up.
        # Prefer the thin session_meta snapshot; fall back to the full analysis blob.
        meta = _memory.get("session_meta", session_id) or _memory.get("session", session_id)
        if not meta:
            raise HTTPException(status_code=404, detail="Session not found")
        sdir.mkdir(parents=True, exist_ok=True)
        recovered: Dict[str, Any] = {
            "session_id": session_id,
            "company_name": meta.get("company_name", ""),
            "industry": meta.get("industry", ""),
            "annual_revenue": meta.get("annual_revenue"),
            "currency": meta.get("reporting_currency", meta.get("currency", "INR")),
            "audience": "consultant",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "files": [],
        }
        write_manifest(session_id, recovered)
        logger.info('"session_recovered session_id=%s"', session_id)
    manifest = read_manifest(session_id)
    manifest.setdefault("session_id", session_id)
    apply_engagement_sanity_to_manifest(manifest)
    return manifest


@router.get("/api/schema/{session_id}")
@router.get("/api/v1/schema/{session_id}")
def get_session_schema(session_id: str) -> Dict[str, Any]:
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    schemas = [f["schema"] for f in manifest.get("files", []) if f.get("schema")]
    return {"session_id": session_id, "schemas": schemas}


@router.get("/api/v1/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    """Return a summary of all sessions, newest first. Used by the History page."""
    from app.storage import read_json as _read_json
    summaries: List[Dict[str, Any]] = []
    if not UPLOAD_DIR.exists():
        return summaries
    for session_path in UPLOAD_DIR.iterdir():
        if not session_path.is_dir():
            continue
        try:
            uuid.UUID(session_path.name, version=4)
        except ValueError:
            continue
        manifest_file = session_path / "manifest.json"
        if not manifest_file.exists():
            continue
        try:
            manifest = _read_json(manifest_file, {})
            analysis = _memory.get("session", session_path.name)
            top_savings = None
            if analysis and isinstance(analysis, dict):
                top_savings = analysis.get("total_savings_opportunity")
            from app.services.engagements_store import backfill_engagement_for_session

            engagement_id = backfill_engagement_for_session(session_path.name, manifest)
            summaries.append({
                "session_id": session_path.name,
                "engagement_id": engagement_id,
                "company_name": manifest.get("company_name") or "Unknown",
                "industry": manifest.get("industry") or "",
                "currency": manifest.get("currency") or "INR",
                "annual_revenue": manifest.get("annual_revenue"),
                "created_at": manifest.get("created_at"),
                "file_count": len(manifest.get("files", [])),
                "has_analysis": analysis is not None,
                "top_savings_estimate": top_savings,
            })
        except Exception:
            continue
    summaries.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return summaries


@router.post("/api/v1/analyze/{session_id}/incremental")
async def incremental_analyze(session_id: str, files: List[UploadFile] = File(default=[])) -> Dict[str, Any]:
    """Upload additional spend files and merge into an existing session."""
    validate_session_id(session_id)
    if not session_dir(session_id).exists():
        raise HTTPException(status_code=404, detail="Session not found")
    manifest = read_manifest(session_id)
    taxonomy = load_taxonomy()
    new_lines = []
    for file in files:
        if not file.filename:
            continue
        content = await file.read()
        if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"File '{file.filename}' exceeds {MAX_UPLOAD_MB} MB")
        safe_filename = Path(file.filename).name
        out_path = session_dir(session_id) / safe_filename
        out_path.write_bytes(content)
        if out_path.suffix.lower() in (".csv", ".xlsx", ".xls"):
            from app.services.ingestion import parse_spend_file as _psf
            try:
                parsed = await asyncio.to_thread(_psf, out_path, taxonomy)
                new_lines.extend(parsed)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
    if not new_lines:
        raise HTTPException(status_code=400, detail="No parseable spend files uploaded")
    from app.services.analysis import run_incremental_pipeline
    try:
        result = run_incremental_pipeline(session_id=session_id, new_lines=new_lines)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    append_audit_event(f"incremental_analysis session_id={session_id} lines_added={result.get('lines_added', 0)}")
    return result


@router.patch("/api/v1/sessions/{session_id}/diagnostic-context")
def patch_diagnostic_context(session_id: str, patch: DiagnosticContextPatch) -> dict:
    """Sync company/industry/revenue and deep research context from the Diagnostic page."""
    validate_session_id(session_id)
    manifest = read_manifest(session_id)
    if patch.company_name is not None:
        manifest["company_name"] = patch.company_name
    if patch.industry is not None:
        manifest["industry"] = patch.industry
    if patch.annual_revenue_cr is not None:
        manifest["annual_revenue"] = patch.annual_revenue_cr * 10_000_000  # Cr → rupees
    if patch.deep_research_summary is not None:
        manifest["deep_research_summary"] = patch.deep_research_summary
    if patch.deep_research_interaction_id is not None:
        manifest["deep_research_interaction_id"] = patch.deep_research_interaction_id
    if patch.diagnostic_urls is not None:
        manifest["diagnostic_urls"] = patch.diagnostic_urls
    if patch.diagnostic_result is not None:
        manifest["diagnostic_result"] = patch.diagnostic_result
    if patch.diagnostic_completed_at is not None:
        manifest["diagnostic_completed_at"] = patch.diagnostic_completed_at
    write_manifest(session_id, manifest)
    append_audit_event(
        "diagnostic_context_patched",
        data={
            "session_id": session_id,
            "has_deep_research": patch.deep_research_summary is not None,
            "has_diagnostic_result": patch.diagnostic_result is not None,
        },
    )
    return {"ok": True, "session_id": session_id}
