"""Parent-child document RAG: embed leaf chunks, retrieve with auto-merge.

Mirrors the self-hosted Qdrant pattern of ``app/opar/qdrant_memory_adapter.py``:
children (leaf nodes) are embedded into the ``document_chunks`` Qdrant collection;
parents live in the filesystem doc store (``parent_nodes.json``). Retrieval does a
high-precision search over children, then *auto-merges* — when several leaf hits
share a parent, the full parent node is swapped in to give the LLM surrounding
context (the "context traceback").

Falls back to a keyword-scored ``LocalDocumentIndex`` over the on-disk child store
when Qdrant / sentence-transformers are unavailable, so the app and tests work
with no live vector DB (tests are forced local, as in the memory adapter).
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.config import (
    DOC_CHUNKS_COLLECTION,
    DOC_CONTEXT_CHAR_BUDGET,
    DOC_MERGE_MIN_CHILDREN,
    DOC_RAG_ENABLED,
    DOC_RETRIEVE_TOP_K,
    QDRANT_ENABLED,
)
from app.services.engagements_store import (
    load_child_nodes,
    load_parent_node,
    read_engagement_manifest,
    write_child_nodes,
)

logger = logging.getLogger("opex.document_index")

_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2
_TOKEN_RE = re.compile(r"[a-z0-9₹$%.]+")

RetrievedBlock = Dict[str, Any]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _child_to_payload(child: Any) -> Dict[str, Any]:
    return child.to_dict() if hasattr(child, "to_dict") else dict(child)


def _engagement_document_ids(engagement_id: str) -> List[str]:
    manifest = read_engagement_manifest(engagement_id)
    return [
        d.get("document_id")
        for d in (manifest.get("documents") or [])
        if d.get("document_id")
    ]


def _auto_merge(
    hits: List[Dict[str, Any]],
    engagement_id: str,
    *,
    merge_min_children: int,
    char_budget: int,
) -> List[RetrievedBlock]:
    """Collapse sibling child hits into their parent; cap by char budget."""
    groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    for h in hits:
        doc_id = h.get("document_id") or h.get("doc_id")
        groups[(doc_id, h["parent_id"])].append(h)

    blocks: List[RetrievedBlock] = []
    for (doc_id, parent_id), ghits in groups.items():
        best = max(ghits, key=lambda x: x["score"])
        if len(ghits) >= merge_min_children:
            parent = load_parent_node(engagement_id, doc_id, parent_id)
            if parent:
                blocks.append({
                    "text": parent["text"],
                    "filename": parent.get("filename", ""),
                    "heading_path": parent.get("heading_path", ""),
                    "score": best["score"],
                    "level": "parent",
                    "parent_id": parent_id,
                    "document_id": doc_id,
                    "merged_children": len(ghits),
                })
                continue
        seen: set = set()
        for h in sorted(ghits, key=lambda x: -x["score"]):
            if h["text"] in seen:
                continue
            seen.add(h["text"])
            blocks.append({
                "text": h["text"],
                "filename": h.get("filename", ""),
                "heading_path": h.get("heading_path", ""),
                "score": h["score"],
                "level": "child",
                "parent_id": parent_id,
                "document_id": doc_id,
            })

    blocks.sort(key=lambda b: -b["score"])
    out: List[RetrievedBlock] = []
    total = 0
    for b in blocks:
        if out and total + len(b["text"]) > char_budget:
            break
        out.append(b)
        total += len(b["text"])
    return out


def _keyword_score(query_tokens: set, text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = set(_TOKEN_RE.findall(text.lower()))
    if not text_tokens:
        return 0.0
    overlap = len(query_tokens & text_tokens)
    return overlap / (len(query_tokens) ** 0.5)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class DocumentIndexInterface(ABC):
    @abstractmethod
    def index_document(self, engagement_id: str, document_id: str, children: List[Any]) -> int:
        """Persist + embed leaf children for one document. Returns count indexed."""

    @abstractmethod
    def retrieve(
        self,
        engagement_id: str,
        query: str,
        *,
        top_k: int = DOC_RETRIEVE_TOP_K,
        merge_min_children: int = DOC_MERGE_MIN_CHILDREN,
        char_budget: int = DOC_CONTEXT_CHAR_BUDGET,
    ) -> List[RetrievedBlock]:
        """Search leaf children for ``query`` and return auto-merged context blocks."""


# ---------------------------------------------------------------------------
# Local keyword fallback
# ---------------------------------------------------------------------------

class LocalDocumentIndex(DocumentIndexInterface):
    """Keyword/overlap scoring over the on-disk child store. No external deps."""

    def index_document(self, engagement_id: str, document_id: str, children: List[Any]) -> int:
        payload = [_child_to_payload(c) for c in children]
        write_child_nodes(engagement_id, document_id, payload)
        return len(payload)

    def _all_children(self, engagement_id: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for doc_id in _engagement_document_ids(engagement_id):
            out.extend(load_child_nodes(engagement_id, doc_id))
        return out

    def retrieve(
        self,
        engagement_id: str,
        query: str,
        *,
        top_k: int = DOC_RETRIEVE_TOP_K,
        merge_min_children: int = DOC_MERGE_MIN_CHILDREN,
        char_budget: int = DOC_CONTEXT_CHAR_BUDGET,
    ) -> List[RetrievedBlock]:
        children = self._all_children(engagement_id)
        if not children:
            return []
        query_tokens = set(_TOKEN_RE.findall((query or "").lower()))
        scored: List[Dict[str, Any]] = []
        for c in children:
            score = _keyword_score(query_tokens, c.get("text", ""))
            if score <= 0:
                continue
            scored.append({**c, "score": score})
        scored.sort(key=lambda x: -x["score"])
        hits = scored[:top_k]
        if not hits:
            return []
        return _auto_merge(
            hits, engagement_id,
            merge_min_children=merge_min_children, char_budget=char_budget,
        )


# ---------------------------------------------------------------------------
# Qdrant-backed index
# ---------------------------------------------------------------------------

class QdrantDocumentIndex(DocumentIndexInterface):
    """Embed children into Qdrant; auto-merge at retrieval. Local fallback inside."""

    def __init__(self) -> None:
        from app.config import EMBEDDING_MODEL, QDRANT_API_KEY, QDRANT_HOST, QDRANT_PORT

        self._fallback = LocalDocumentIndex()
        self._qdrant_ok = False
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            from sentence_transformers import SentenceTransformer

            api_key = QDRANT_API_KEY or None
            self._client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=api_key, timeout=5)
            self._encoder = SentenceTransformer(EMBEDDING_MODEL)
            existing = {c.name for c in self._client.get_collections().collections}
            if DOC_CHUNKS_COLLECTION not in existing:
                self._client.create_collection(
                    collection_name=DOC_CHUNKS_COLLECTION,
                    vectors_config=VectorParams(size=_EMBEDDING_DIM, distance=Distance.COSINE),
                )
            self._qdrant_ok = True
            logger.info('"document_index_ready host=%s port=%s"', QDRANT_HOST, QDRANT_PORT)
        except ImportError as exc:
            logger.warning('"document_index_import_error err=%s; using local fallback"', exc)
        except Exception as exc:
            logger.warning('"document_index_connection_error err=%s; using local fallback"', exc)

    def _embed(self, text: str) -> List[float]:
        return self._encoder.encode(text, convert_to_numpy=True).tolist()  # type: ignore[return-value]

    def index_document(self, engagement_id: str, document_id: str, children: List[Any]) -> int:
        # Always persist to the on-disk child store (reindex + local-fallback parity).
        count = self._fallback.index_document(engagement_id, document_id, children)
        if not self._qdrant_ok:
            return count
        try:
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                MatchValue,
                PointStruct,
            )

            # Idempotent: drop existing points for this document before re-indexing.
            self._client.delete(
                collection_name=DOC_CHUNKS_COLLECTION,
                points_selector=Filter(must=[
                    FieldCondition(key="engagement_id", match=MatchValue(value=engagement_id)),
                    FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                ]),
            )
            points = []
            for c in children:
                payload = _child_to_payload(c)
                payload["document_id"] = document_id
                payload["engagement_id"] = engagement_id
                points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=self._embed(payload["text"]),
                    payload=payload,
                ))
            if points:
                self._client.upsert(collection_name=DOC_CHUNKS_COLLECTION, points=points)
        except Exception as exc:
            logger.warning('"document_index_upsert_error doc=%s err=%s"', document_id, exc)
        return count

    def retrieve(
        self,
        engagement_id: str,
        query: str,
        *,
        top_k: int = DOC_RETRIEVE_TOP_K,
        merge_min_children: int = DOC_MERGE_MIN_CHILDREN,
        char_budget: int = DOC_CONTEXT_CHAR_BUDGET,
    ) -> List[RetrievedBlock]:
        if not self._qdrant_ok:
            return self._fallback.retrieve(
                engagement_id, query,
                top_k=top_k, merge_min_children=merge_min_children, char_budget=char_budget,
            )
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            results = self._client.search(
                collection_name=DOC_CHUNKS_COLLECTION,
                query_vector=self._embed(query or "general context"),
                limit=top_k,
                query_filter=Filter(must=[
                    FieldCondition(key="engagement_id", match=MatchValue(value=engagement_id)),
                ]),
            )
            hits = [{"score": float(h.score), **h.payload} for h in results if h.payload]
            if not hits:
                return self._fallback.retrieve(
                    engagement_id, query,
                    top_k=top_k, merge_min_children=merge_min_children, char_budget=char_budget,
                )
            return _auto_merge(
                hits, engagement_id,
                merge_min_children=merge_min_children, char_budget=char_budget,
            )
        except Exception as exc:
            logger.warning('"document_index_search_error err=%s; using local fallback"', exc)
            return self._fallback.retrieve(
                engagement_id, query,
                top_k=top_k, merge_min_children=merge_min_children, char_budget=char_budget,
            )


# ---------------------------------------------------------------------------
# Factory (mirrors get_memory_adapter)
# ---------------------------------------------------------------------------

_INDEX_SINGLETON: Optional[DocumentIndexInterface] = None
_INDEX_META: Dict[str, Any] = {
    "backend": "local",
    "rag_enabled": DOC_RAG_ENABLED,
    "qdrant_active": False,
    "reason": "default_local",
}


def get_document_index() -> DocumentIndexInterface:
    """Return the document index. Qdrant preferred; falls back to local keyword store."""
    global _INDEX_SINGLETON

    if os.getenv("PYTEST_CURRENT_TEST"):
        _INDEX_SINGLETON = LocalDocumentIndex()
        _INDEX_META.update({"backend": "local", "qdrant_active": False, "reason": "pytest_forced_local"})
        return _INDEX_SINGLETON

    if _INDEX_SINGLETON is not None:
        return _INDEX_SINGLETON

    if DOC_RAG_ENABLED and QDRANT_ENABLED:
        try:
            adapter = QdrantDocumentIndex()
            active = getattr(adapter, "_qdrant_ok", False)
            _INDEX_SINGLETON = adapter
            _INDEX_META.update({
                "backend": "qdrant" if active else "local",
                "qdrant_active": active,
                "reason": "ok" if active else "qdrant_unreachable_using_local_fallback",
            })
            return _INDEX_SINGLETON
        except Exception as exc:  # pragma: no cover - defensive
            _INDEX_META.update({"backend": "local", "qdrant_active": False, "reason": f"qdrant_init_failed:{type(exc).__name__}"})

    _INDEX_SINGLETON = LocalDocumentIndex()
    _INDEX_META.update({"backend": "local", "qdrant_active": False, "reason": "qdrant_disabled_or_failed"})
    return _INDEX_SINGLETON


def get_document_index_status() -> Dict[str, Any]:
    get_document_index()
    return dict(_INDEX_META)


def retrieve_context(engagement_id: str, query: str, **kwargs: Any) -> List[str]:
    """Convenience wrapper: auto-merged retrieval formatted as labelled text blocks.

    Returns ``[]`` (so callers fall back to existing behaviour) when there is no
    engagement, no query, or no indexed content.
    """
    if not engagement_id or not query or not str(query).strip():
        return []
    try:
        blocks = get_document_index().retrieve(engagement_id, query, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning('"document_retrieve_error eng=%s err=%s"', engagement_id, exc)
        return []
    out: List[str] = []
    for b in blocks:
        prov = b.get("filename") or ""
        head = b.get("heading_path") or ""
        label = f"[{prov}{' › ' + head if head else ''}]".strip()
        out.append(f"{label}\n{b.get('text', '')}".strip())
    return out
