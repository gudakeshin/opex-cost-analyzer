"""Tests for the parent-child document index + auto-merging retriever.

Tests run against ``LocalDocumentIndex`` (Qdrant is forced off under pytest, as
in the memory adapter), so they exercise the chunk store + auto-merge logic with
no external vector DB.
"""
from __future__ import annotations

import pytest

from app.services.document_index import (
    LocalDocumentIndex,
    get_document_index,
    retrieve_context,
)
from app.services.document_pipeline import index_document_nodes, reindex_engagement
from app.services.engagements_store import (
    add_document_record,
    create_engagement_manifest,
    load_child_nodes,
    load_parent_nodes,
)

# A deck whose key figure sits well past the first ~2,400 chars (the old
# front-truncation window) — only real retrieval can surface it.
_FILLER = ("This deck opens with a long preamble about company history and "
           "market context that is not relevant to the budget question. ") * 40

DECK = f"""# Company Overview
{_FILLER}

# R&D AI Infrastructure Budget
| Workstream | Cost |
| --- | --- |
| AI infrastructure GPU clusters for the R&D team | ₹190 Cr |
| AI infrastructure AWS partnership for the R&D team | ₹90 Cr |
| AI infrastructure data platform for the R&D team | ₹50 Cr |

The R&D team also plans to hire 11 FTEs to operate the AI infrastructure.
"""


@pytest.fixture
def engagement(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    manifest = create_engagement_manifest(company_name="Wonder Cement")
    eid = manifest["engagement_id"]
    did = "00000000-0000-4000-8000-000000000abc"
    add_document_record(
        eid, document_id=did, filename="strategy.pdf",
        content_type="application/pdf", size_bytes=1234, raw_path="x",
    )
    index_document_nodes(eid, did, DECK, "strategy.pdf")
    return eid, did


def test_pytest_forces_local_index():
    assert isinstance(get_document_index(), LocalDocumentIndex)


def test_index_persists_parents_and_children(engagement):
    eid, did = engagement
    parents = load_parent_nodes(eid, did)
    children = load_child_nodes(eid, did)
    assert parents and children
    # every child's parent_id resolves to a stored parent
    assert all(c["parent_id"] in parents for c in children)


def test_retrieve_finds_deep_figure_and_merges_to_parent(engagement):
    eid, _ = engagement
    blocks = get_document_index().retrieve(eid, "AI infrastructure budget for the R&D team")
    assert blocks
    joined = "\n".join(b["text"] for b in blocks)
    # the buried figure is surfaced despite being past the old truncation window
    assert "₹190 Cr" in joined
    # sibling leaf hits collapsed into the full parent (context traceback):
    # the merged parent also carries the surrounding hiring context
    merged = [b for b in blocks if b["level"] == "parent"]
    assert merged, "expected at least one auto-merged parent block"
    assert any("11 FTEs" in b["text"] for b in merged)
    assert merged[0]["merged_children"] >= 2


def test_no_merge_returns_precise_child(engagement):
    eid, _ = engagement
    # merge disabled -> we get the individual leaf row, not the whole section
    blocks = get_document_index().retrieve(
        eid, "AWS partnership", merge_min_children=999,
    )
    assert blocks
    assert all(b["level"] == "child" for b in blocks)
    assert any("₹90 Cr" in b["text"] and "AWS" in b["text"] for b in blocks)


def test_char_budget_caps_output(engagement):
    eid, _ = engagement
    blocks = get_document_index().retrieve(
        eid, "AI infrastructure budget for the R&D team", char_budget=50,
    )
    # at least one block (we always keep the first), but budget keeps it small
    assert len(blocks) == 1


def test_retrieve_context_formats_provenance(engagement):
    eid, _ = engagement
    out = retrieve_context(eid, "AI infrastructure budget for the R&D team")
    assert out and isinstance(out, list)
    assert any("strategy.pdf" in block for block in out)


def test_retrieve_context_empty_inputs_return_empty(engagement):
    eid, _ = engagement
    assert retrieve_context("", "anything") == []
    assert retrieve_context(eid, "   ") == []


def test_retrieve_unknown_engagement_is_empty():
    assert get_document_index().retrieve("eng-does-not-exist", "anything") == []


def test_process_document_indexes_on_ingest(monkeypatch, tmp_path):
    """End-to-end: processing a context doc chunks + indexes and records counts."""
    monkeypatch.setattr("app.services.engagements_store.ENGAGEMENTS_DIR", tmp_path)
    from app.services.document_pipeline import process_engagement_document
    from app.services.engagements_store import document_dir
    from app.services.analysis import load_taxonomy

    manifest = create_engagement_manifest(company_name="Ingest Test")
    eid = manifest["engagement_id"]
    did = "00000000-0000-4000-8000-000000000def"
    ddir = document_dir(eid, did)
    ddir.mkdir(parents=True)
    (ddir / "raw.txt").write_text(DECK, encoding="utf-8")
    add_document_record(
        eid, document_id=did, filename="strategy.txt",
        content_type="text/plain", size_bytes=len(DECK), raw_path=str(ddir / "raw.txt"),
    )
    result = process_engagement_document(eid, did, taxonomy=load_taxonomy())

    assert result["status"] == "ready"
    assert result["indexed"] is True
    assert result["chunk_count"] > 0
    assert result["parent_count"] > 0
    assert load_parent_nodes(eid, did)
    # the indexed corpus is retrievable
    blocks = get_document_index().retrieve(eid, "AI infrastructure budget for the R&D team")
    assert any("₹190 Cr" in b["text"] for b in blocks)


def test_reindex_is_idempotent(engagement, monkeypatch):
    eid, did = engagement
    # mark the doc ready so reindex_engagement picks it up
    from app.services.engagements_store import update_document_record
    update_document_record(eid, did, {"status": "ready"})
    # cached markdown is needed for reindex; write it where load_cached_markdown reads
    from app.services.engagements_store import document_parsed_dir
    (document_parsed_dir(eid, did) / "markdown.md").write_text(DECK, encoding="utf-8")

    before = len(load_child_nodes(eid, did))
    summary = reindex_engagement(eid)
    after = len(load_child_nodes(eid, did))
    assert summary["documents"] == 1
    assert after == before  # re-indexing overwrites, never duplicates
