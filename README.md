# OpEx Intelligence Platform

Reference implementation aligned to `OpEx_Intelligence_Platform_PRD.md` with:
- FastAPI backend
- React + Vite + TypeScript + Tailwind frontend (`frontend/`)
- Skill discovery/runtime from `skills/*/SKILL.md`
- Upload + ingestion + classification pipeline
- Core analysis skills orchestration
- Value bridge + validation + sensitivity
- Business case + dashboard exports
- Skills Management UI
- Claude-like planning-agent chat interface
- Baseline compliance/privacy controls

## Quick start

1. Create env and install dependencies:
   - `python -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Build frontend (first time or after UI changes):
   - `cd frontend && npm install && npm run build`
3. Run API:
   - `uvicorn app.main:app --reload`
4. Open UI:
   - Production (served by FastAPI): `http://127.0.0.1:8000/ui/`

### Frontend development (hot reload)

Run in two terminals:

```bash
# Terminal 1 — API
uvicorn app.main:app --reload

# Terminal 2 — Vite dev server (proxies /api to :8000)
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173/ui/` for hot-reload development.

## Local hosting

- Start local server (script):
  - `bash scripts/run_local_server.sh`
- Or directly with uvicorn:
  - `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`

## Testing

- Run full test suite:
  - `pytest -q`
- Tests include:
  - service/unit tests for ingestion and skill engine
  - API integration tests for upload/analyze/export/skills/compliance/memory flows
  - planning-agent follow-up question flow and schema endpoint coverage
  - contract-validation tests for strict skill-output schemas
  - performance smoke tests for upload/analyze timing and file-size guardrails

## Performance benchmark (local server)

- Ensure local server is running:
  - `bash scripts/run_local_server.sh`
- Run 50MB benchmark check:
  - `python3 scripts/perf_50mb_check.py`
- Optional env overrides:
  - `OPEX_BASE_URL` (default `http://127.0.0.1:8000`)
  - `OPEX_PERF_TARGET_MB` (default `49`, leaves multipart headroom under 50MB limit)
  - `OPEX_UPLOAD_BUDGET_SECS` (default `30`)
  - `OPEX_ANALYZE_BUDGET_SECS` (default `60`)

## Main API endpoints

- `POST /api/sessions`
- `POST /api/upload/{session_id}`
- `POST /api/analyze/{session_id}`
- `GET /api/schema/{session_id}`
- `POST /api/chat/{session_id}`
- `GET /api/sessions/{session_id}`
- `POST /api/business-case/{session_id}`
- `POST /api/dashboard/{session_id}`
- `GET /api/sensitivity/{session_id}`
- `GET /api/skills`, `GET/PUT /api/skills/{name}`, `POST /api/skills/{name}/test`, `POST /api/skills`
- `DELETE /api/memory/{scope}/{key}`
- `GET /api/compliance/risk-register`, `GET /api/compliance/privacy-controls`

## Notes

- This project uses local JSON/file-backed memory as a baseline implementation for user/session/agent memory scopes.
- The API shape is intentionally compatible with future external connectors (Mem0 managed service, Claude API calls, and licensed benchmark feeds).
- Manual test files are included in:
  - `test_data/sample_spend_for_manual_testing.csv`
  - `test_data/sample_context_for_manual_testing.txt`
  - `test_data/realistic_pack/` (multi-file nuanced scenario pack)

