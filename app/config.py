from __future__ import annotations

import contextvars
import logging
import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
ENGAGEMENTS_DIR = DATA_DIR / "engagements"
OUTPUT_DIR = DATA_DIR / "outputs"
MEMORY_DIR = DATA_DIR / "memory"
SKILLS_DIR = ROOT_DIR / "skills"

APP_NAME = "OpEx Intelligence Platform"
APP_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Per-request correlation ID — set in middleware, readable anywhere in the
# request call-stack (including OPAR skills) via contextvars.
# ---------------------------------------------------------------------------
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")
        return True


# ---------------------------------------------------------------------------
# Structured logging — JSON format suitable for ECS / CloudWatch / stdout
# ---------------------------------------------------------------------------
_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","rid":"%(request_id)s","msg":%(message)s}',
)
logger = logging.getLogger("opex")
logger.addFilter(_RequestIdFilter())
# Propagate the filter to the root logger so all child loggers pick it up.
logging.getLogger().addFilter(_RequestIdFilter())


def _load_env_file() -> None:
    """
    Lightweight env loader to avoid extra dependency on python-dotenv.
    Priority:
    1) Existing process environment variables
    2) .env file
    3) .env.example file
    """
    candidates = [ROOT_DIR / ".env", ROOT_DIR / ".env.example"]
    for path in candidates:
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"").strip("'")
            os.environ.setdefault(key, value)
        break


_load_env_file()

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))

# Optional external connectors; app works in local mode without these.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_ENABLED = bool(ANTHROPIC_API_KEY)

# Gemini provider — set LLM_PROVIDER=gemini to route all LLM calls through Gemini.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ENABLED = bool(GEMINI_API_KEY)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
# "gemini" (default when key present) | "anthropic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini" if bool(os.getenv("GEMINI_API_KEY", "")) else "anthropic")

# Qdrant vector memory (replaces Mem0; self-hosted, no external SaaS dependency)
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")  # Optional; leave blank for local
QDRANT_ENABLED = os.getenv("QDRANT_ENABLED", "true").lower() not in ("false", "0", "no")

# Sentence-transformers embedding model used for Qdrant semantic search (runs locally, no API cost)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Parent-child (hierarchical) document RAG over engagement documents.
# Children (leaf chunks) are embedded into the DOC_CHUNKS_COLLECTION Qdrant collection;
# parents (full sections) live in a filesystem doc store and are merged back in at retrieval.
DOC_RAG_ENABLED = os.getenv("DOC_RAG_ENABLED", "true").lower() not in ("false", "0", "no")
DOC_CHUNKS_COLLECTION = os.getenv("DOC_CHUNKS_COLLECTION", "document_chunks")
DOC_PARENT_CHARS = int(os.getenv("DOC_PARENT_CHARS", "4000"))   # ~1024 tokens
DOC_CHILD_CHARS = int(os.getenv("DOC_CHILD_CHARS", "1000"))     # ~256 tokens
DOC_CHILD_OVERLAP = int(os.getenv("DOC_CHILD_OVERLAP", "150"))
DOC_RETRIEVE_TOP_K = int(os.getenv("DOC_RETRIEVE_TOP_K", "12"))
DOC_MERGE_MIN_CHILDREN = int(os.getenv("DOC_MERGE_MIN_CHILDREN", "2"))
DOC_CONTEXT_CHAR_BUDGET = int(os.getenv("DOC_CONTEXT_CHAR_BUDGET", "8000"))

# Deep Research — uses Google Interactions API (same GEMINI_API_KEY, requires google-genai package)
DEEP_RESEARCH_ENABLED = bool(GEMINI_API_KEY)

# LlamaParse — multimodal document parsing (https://cloud.llamaindex.ai/)
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY", "") or os.getenv("LLAMAPARSE_API_KEY", "")
LLAMAPARSE_ENABLED = os.getenv("LLAMAPARSE_ENABLED", "true").lower() not in ("false", "0", "no") and bool(LLAMA_CLOUD_API_KEY)
LLAMAPARSE_RESULT_TYPE = os.getenv("LLAMAPARSE_RESULT_TYPE", "markdown")
LLAMAPARSE_PREMIUM_MODE = os.getenv("LLAMAPARSE_PREMIUM_MODE", "false").lower() in ("true", "1", "yes")

