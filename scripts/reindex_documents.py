#!/usr/bin/env python3
"""Backfill: hierarchically chunk + index every engagement's parsed documents.

Existing engagements have cached ``markdown.md`` but no parent/child nodes. This
re-runs the splitter + indexer over each ready context document so they become
retrievable via the parent-child RAG path.

Usage:
    PYTHONPATH=. python3 scripts/reindex_documents.py            # all engagements
    PYTHONPATH=. python3 scripts/reindex_documents.py <eng_id>   # one engagement
"""
from __future__ import annotations

import sys

from app.services.document_pipeline import reindex_engagement
from app.services.engagements_store import list_engagements


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        engagement_ids = [argv[1]]
    else:
        engagement_ids = [e["engagement_id"] for e in list_engagements()]

    if not engagement_ids:
        print("No engagements found.")
        return 0

    grand_docs = grand_chunks = grand_parents = 0
    for eid in engagement_ids:
        summary = reindex_engagement(eid)
        grand_docs += summary["documents"]
        grand_chunks += summary["chunks"]
        grand_parents += summary["parents"]
        print(
            f"{eid}: {summary['documents']} docs, "
            f"{summary['parents']} parents, {summary['chunks']} chunks"
        )

    print(
        f"\nDone. {grand_docs} documents indexed "
        f"({grand_parents} parents, {grand_chunks} chunks)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
