# Known Stubs & Graceful Degradation

These are **intentional** placeholders, not gaps. They degrade gracefully and are
documented here so they are not mistaken for incomplete work during future audits.

## Regulatory watcher (Phase 3 catalogue)
`app/services/reg_watcher.py` uses a static sample event catalogue by default. Matching events
are surfaced at Reflect gates for awareness but **do not force HITL** unless
`REG_WATCHER_LIVE=1` is set (Phase 4 live HTTP feeds).

## Licensed India benchmark adapters
`app/services/benchmarks_india.py` — `CmieAdapter`, `CapitalineAdapter`, `CrisilAdapter`,
`IcraAdapter` attempt licensed HTTP calls when API keys are set; they return `[]` and log a
warning on network/parse failure. Without keys they return empty lists. They are **not invoked
in any live request path**; they exist as integration seams for licensed data feeds (CMIE
Prowess IQ, Capitaline, CRISIL, ICRA). Free-source parsers (MCA21, BSE/NSE, BRSR, RBI, CEA)
are similarly gated on HTTP access.

## Document export fallbacks
- `app/services/board_deck.py::export_board_deck_pptx` writes a plain-text stub file when
  `python-pptx` is not installed (so the export endpoint still returns a downloadable file).
- `app/services/pmo_export.py::export_pmo_xlsx` writes a plain-text stub when `openpyxl` is
  not installed.
- `app/services/cfo_brief.py` / `mor_pack.py` DOCX exports require `python-docx`.

Install `python-pptx`, `openpyxl`, and `python-docx` (already in `requirements.txt`) for
fully formatted binary exports.

## Source-system connectors
Six connectors are registered and reachable through `POST /api/v1/connectors/{type}/ingest`
(optionally async or delta-sync, with per-engagement watermarks): `ariba_csv`, `hrms_csv`, `tally_xml`,
`bank_mt940` and `gst_portal` read an exported file; `sap_odata` calls a live SAP S/4HANA service and needs
credentials. The web UI does not expose them yet — they are API-only.

## Per-engagement GL-code classification
Line classification is keyword-based (whole-word match against the spend taxonomy). GL-code ranges are
client-specific, so the taxonomy ships without a generic `gl_code_ranges` table; a per-engagement chart-of-accounts
mapping would be needed to classify by GL code.

## Analytics cache
`app/services/cache.py` falls back to a pure-Python implementation when `duckdb` is not
installed. Functionality is preserved; only the columnar-cache acceleration is skipped.

## LLM synthesis skills
`analysis-synthesizer` and `executive-communication` call the Claude provider and return an
empty result with `degraded_reason="provider_unavailable"` when `ANTHROPIC_API_KEY` is unset,
rather than failing the OPAR loop. Deterministic skills always run regardless.
