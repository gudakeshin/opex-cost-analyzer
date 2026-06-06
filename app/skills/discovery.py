"""Semantic skill discovery — embed catalog and rank by query relevance."""
from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any, Dict, List

from app.config import EMBEDDING_MODEL, QDRANT_ENABLED, SKILL_CATALOG_COLLECTION, logger
from app.skills.registry import discover_skills_rich

_INDEX: Dict[str, Any] | None = None
_VECTORS: List[tuple[str, List[float], Dict[str, Any]]] | None = None


def _skill_document(meta: Dict[str, Any]) -> str:
    parts = [
        meta.get("name", ""),
        meta.get("description", ""),
        meta.get("when_to_use", ""),
        meta.get("purpose", ""),
        meta.get("methodology_summary", ""),
    ]
    return "\n".join(p for p in parts if p)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _keyword_score(query: str, meta: Dict[str, Any]) -> float:
    q = _tokenize(query)
    doc = _tokenize(_skill_document(meta))
    if not q or not doc:
        return 0.0
    overlap = len(q & doc)
    return overlap / math.sqrt(len(q) * len(doc))


@lru_cache(maxsize=1)
def _embedder():
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(EMBEDDING_MODEL)
    except Exception as exc:
        logger.warning('"skill_discovery embedder unavailable: %s"', exc)
        return None


def _embed(texts: List[str]) -> List[List[float]]:
    model = _embedder()
    if model is None:
        return []
    return model.encode(texts, normalize_embeddings=True).tolist()


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _ensure_index() -> None:
    global _VECTORS
    if _VECTORS is not None:
        return
    catalog = discover_skills_rich()
    docs = [_skill_document(m) for m in catalog]
    vectors = _embed(docs)
    _VECTORS = []
    for meta, vec in zip(catalog, vectors):
        _VECTORS.append((meta["name"], vec, meta))
    if QDRANT_ENABLED and vectors:
        _try_qdrant_upsert(catalog, vectors)


def _try_qdrant_upsert(catalog: List[Dict[str, Any]], vectors: List[List[float]]) -> None:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels

        from app.config import QDRANT_API_KEY, QDRANT_HOST, QDRANT_PORT

        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY or None)
        dim = len(vectors[0])
        collections = {c.name for c in client.get_collections().collections}
        if SKILL_CATALOG_COLLECTION not in collections:
            client.create_collection(
                collection_name=SKILL_CATALOG_COLLECTION,
                vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
            )
        points = []
        for i, (meta, vec) in enumerate(zip(catalog, vectors)):
            points.append(
                qmodels.PointStruct(
                    id=i + 1,
                    vector=vec,
                    payload={"name": meta["name"], "description": meta.get("description", "")},
                )
            )
        client.upsert(collection_name=SKILL_CATALOG_COLLECTION, points=points)
    except Exception as exc:
        logger.debug('"skill_catalog qdrant upsert skipped: %s"', exc)


def discover_relevant_skills(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """Return top-k skills ranked by semantic similarity with keyword fallback."""
    query = (query or "").strip()
    if not query:
        return []

    _ensure_index()
    catalog = discover_skills_rich()

    # Try Qdrant search first
    qdrant_hits = _qdrant_search(query, k=k)
    if qdrant_hits:
        return qdrant_hits

    # In-memory vector rank
    if _VECTORS:
        q_vec = _embed([query])
        if q_vec:
            scored = []
            for name, vec, meta in _VECTORS:
                score = _cosine(q_vec[0], vec)
                scored.append((score, meta))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [
                {
                    "name": m["name"],
                    "description": m.get("description", ""),
                    "score": round(float(s), 4),
                }
                for s, m in scored[:k]
                if s > 0.05
            ]

    # Keyword fallback
    ranked = sorted(
        (( _keyword_score(query, m), m) for m in catalog),
        key=lambda x: x[0],
        reverse=True,
    )
    return [
        {
            "name": m["name"],
            "description": m.get("description", ""),
            "score": round(float(s), 4),
        }
        for s, m in ranked[:k]
        if s > 0
    ]


def _qdrant_search(query: str, k: int) -> List[Dict[str, Any]]:
    if not QDRANT_ENABLED:
        return []
    try:
        from qdrant_client import QdrantClient

        from app.config import QDRANT_API_KEY, QDRANT_HOST, QDRANT_PORT

        q_vec = _embed([query])
        if not q_vec:
            return []
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY or None)
        collections = {c.name for c in client.get_collections().collections}
        if SKILL_CATALOG_COLLECTION not in collections:
            return []
        hits = client.search(
            collection_name=SKILL_CATALOG_COLLECTION,
            query_vector=q_vec[0],
            limit=k,
        )
        return [
            {
                "name": h.payload.get("name", ""),
                "description": h.payload.get("description", ""),
                "score": round(float(h.score), 4),
            }
            for h in hits
        ]
    except Exception:
        return []
