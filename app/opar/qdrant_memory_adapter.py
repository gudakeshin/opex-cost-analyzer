"""QdrantMemoryAdapter — self-hosted vector memory replacing Mem0.

Uses four Qdrant collections:
  - session_memories    : OPAR interaction logs, keyed by session_id
  - user_memories       : user profile and preferences, keyed by user_id
  - agent_memories      : per-skill learning, keyed by skill_name
  - engagement_memories : multi-session engagement state, keyed by engagement_id

Embeddings are generated locally via sentence-transformers (no external API call).
Model: all-MiniLM-L6-v2 (90 MB, 384-dim, fast, license-free).

Qdrant is expected to be running at QDRANT_HOST:QDRANT_PORT (see docker-compose.yml).
The adapter falls back to LocalMemoryAdapter when Qdrant is unreachable.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger("opex.qdrant_memory")

_EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension
_COLLECTIONS = ["session_memories", "user_memories", "agent_memories", "engagement_memories"]


class QdrantMemoryAdapter:
    """Qdrant-backed semantic memory adapter.

    Falls back to LocalMemoryAdapter at construction time if Qdrant is
    unreachable or the qdrant-client / sentence-transformers packages are absent.
    """

    def __init__(self) -> None:
        from app.config import EMBEDDING_MODEL, QDRANT_API_KEY, QDRANT_HOST, QDRANT_PORT
        from app.opar.memory_adapter import LocalMemoryAdapter

        self._fallback = LocalMemoryAdapter()
        self._qdrant_ok = False

        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
            from sentence_transformers import SentenceTransformer

            api_key = QDRANT_API_KEY or None
            self._client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=api_key, timeout=5)
            self._encoder = SentenceTransformer(EMBEDDING_MODEL)
            self._ensure_collections()
            self._qdrant_ok = True
            logger.info('"qdrant_memory_adapter_ready host=%s port=%s"', QDRANT_HOST, QDRANT_PORT)
        except ImportError as exc:
            logger.warning('"qdrant_import_error err=%s; using local fallback"', exc)
        except Exception as exc:
            logger.warning('"qdrant_connection_error err=%s; using local fallback"', exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_collections(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self._client.get_collections().collections}
        for name in _COLLECTIONS:
            if name not in existing:
                self._client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=_EMBEDDING_DIM, distance=Distance.COSINE),
                )

    def _embed(self, text: str) -> List[float]:
        return self._encoder.encode(text, convert_to_numpy=True).tolist()  # type: ignore[return-value]

    def _upsert(self, collection: str, payload: Dict[str, Any], text: str) -> None:
        from qdrant_client.models import PointStruct

        point_id = str(uuid.uuid4())
        payload["_stored_at"] = datetime.now(timezone.utc).isoformat()
        self._client.upsert(
            collection_name=collection,
            points=[PointStruct(id=point_id, vector=self._embed(text), payload=payload)],
        )

    def _search(self, collection: str, query: str, limit: int, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        must = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
            if v is not None
        ]
        qfilter = Filter(must=must) if must else None
        hits = self._client.search(
            collection_name=collection,
            query_vector=self._embed(query or "general context"),
            limit=limit,
            query_filter=qfilter,
        )
        return [{"score": h.score, **h.payload} for h in hits]

    def _scroll(self, collection: str, filters: Dict[str, Any], limit: int = 50) -> List[Dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        must = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
            if v is not None
        ]
        qfilter = Filter(must=must) if must else None
        records, _ = self._client.scroll(
            collection_name=collection,
            scroll_filter=qfilter,
            limit=limit,
            with_payload=True,
        )
        return [r.payload for r in records if r.payload]

    # ------------------------------------------------------------------
    # MemoryAdapterInterface implementation
    # ------------------------------------------------------------------

    def get_user_memory(self, user_id: str) -> List[Dict[str, Any]]:
        if not self._qdrant_ok:
            return self._fallback.get_user_memory(user_id)
        try:
            return self._scroll("user_memories", {"user_id": user_id})
        except Exception as exc:
            logger.warning('"qdrant_get_user_error user=%s err=%s"', user_id, exc)
            return self._fallback.get_user_memory(user_id)

    def get_session_memory(self, session_id: str, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        if not self._qdrant_ok:
            return self._fallback.get_session_memory(session_id, query, limit)
        try:
            return self._search("session_memories", query, limit, {"session_id": session_id})
        except Exception as exc:
            logger.warning('"qdrant_get_session_error session=%s err=%s"', session_id, exc)
            return self._fallback.get_session_memory(session_id, query, limit)

    def get_agent_memories(self, skill_names: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        if not self._qdrant_ok:
            return self._fallback.get_agent_memories(skill_names)
        out: Dict[str, List[Dict[str, Any]]] = {}
        for name in skill_names:
            try:
                out[name] = self._scroll("agent_memories", {"skill_name": name})
            except Exception as exc:
                logger.warning('"qdrant_get_agent_error skill=%s err=%s"', name, exc)
                out[name] = self._fallback.get_agent_memories([name]).get(name, [])
        return out

    def add_session(self, session_id: str, content: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> None:
        if not self._qdrant_ok:
            self._fallback.add_session(session_id, content, metadata)
            return
        try:
            payload = {"session_id": session_id, "content": json.dumps(content, default=str), **(metadata or {})}
            text = content.get("summary") or content.get("response_text") or json.dumps(content, default=str)[:500]
            self._upsert("session_memories", payload, text)
        except Exception as exc:
            logger.warning('"qdrant_add_session_error session=%s err=%s"', session_id, exc)
            self._fallback.add_session(session_id, content, metadata)

    def add_user(self, user_id: str, content: Dict[str, Any]) -> None:
        if not self._qdrant_ok:
            self._fallback.add_user(user_id, content)
            return
        try:
            payload = {"user_id": user_id, "content": json.dumps(content, default=str)}
            text = json.dumps(content, default=str)[:500]
            self._upsert("user_memories", payload, text)
        except Exception as exc:
            logger.warning('"qdrant_add_user_error user=%s err=%s"', user_id, exc)
            self._fallback.add_user(user_id, content)

    def add_agent(self, agent_id: str, content: Dict[str, Any]) -> None:
        if not self._qdrant_ok:
            self._fallback.add_agent(agent_id, content)
            return
        try:
            payload = {"skill_name": agent_id, "content": json.dumps(content, default=str)}
            text = json.dumps(content, default=str)[:500]
            self._upsert("agent_memories", payload, text)
        except Exception as exc:
            logger.warning('"qdrant_add_agent_error agent=%s err=%s"', agent_id, exc)
            self._fallback.add_agent(agent_id, content)

    def get_engagement_memory(self, engagement_id: str) -> Dict[str, Any]:
        if not self._qdrant_ok:
            return self._fallback.get_engagement_memory(engagement_id)
        try:
            records = self._scroll("engagement_memories", {"engagement_id": engagement_id}, limit=1)
            return records[0] if records else {}
        except Exception as exc:
            logger.warning('"qdrant_get_engagement_error id=%s err=%s"', engagement_id, exc)
            return self._fallback.get_engagement_memory(engagement_id)

    def add_engagement(self, engagement_id: str, content: Dict[str, Any]) -> None:
        if not self._qdrant_ok:
            self._fallback.add_engagement(engagement_id, content)
            return
        try:
            payload = {"engagement_id": engagement_id, **content}
            text = json.dumps(content, default=str)[:500]
            self._upsert("engagement_memories", payload, text)
        except Exception as exc:
            logger.warning('"qdrant_add_engagement_error id=%s err=%s"', engagement_id, exc)
            self._fallback.add_engagement(engagement_id, content)

    def teardown_engagement(self, engagement_id: str) -> Dict[str, Any]:
        existing = self.get_engagement_memory(engagement_id)
        if self._qdrant_ok:
            try:
                from qdrant_client.models import FieldCondition, Filter, MatchValue

                self._client.delete(
                    collection_name="engagement_memories",
                    points_selector=Filter(
                        must=[FieldCondition(key="engagement_id", match=MatchValue(value=engagement_id))]
                    ),
                )
                # Also remove all session memories tied to this engagement
                self._client.delete(
                    collection_name="session_memories",
                    points_selector=Filter(
                        must=[FieldCondition(key="engagement_id", match=MatchValue(value=engagement_id))]
                    ),
                )
                logger.info('"qdrant_teardown_done engagement_id=%s"', engagement_id)
            except Exception as exc:
                logger.warning('"qdrant_teardown_error id=%s err=%s"', engagement_id, exc)
        else:
            self._fallback.teardown_engagement(engagement_id)
        return existing
