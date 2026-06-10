from __future__ import annotations

import contextvars
import logging
import os
import re
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
_LOG_FORMAT = '{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","rid":"%(request_id)s","msg":%(message)s}'


def _configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, _LOG_LEVEL, logging.INFO),
        format=_LOG_FORMAT,
    )
    logging.getLogger("opex").addFilter(_RequestIdFilter())
    logging.getLogger().addFilter(_RequestIdFilter())
    # Logger-level filters only run for records created on those exact loggers.
    # Records from child loggers ("opex.*") and third-party libraries propagate
    # straight to the root *handlers*, so the filter must also sit on the
    # handlers — otherwise the format's %(request_id)s raises KeyError.
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, _RequestIdFilter) for f in handler.filters):
            handler.addFilter(_RequestIdFilter())


_configure_logging()
logger = logging.getLogger("opex")


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
            value = value.strip()
            # Strip a trailing inline comment ("KEY=value   # note"), but only
            # when the "#" is preceded by whitespace so values that legitimately
            # contain "#" (e.g. URLs with fragments) are left intact.
            comment_match = re.search(r"\s+#", value)
            if comment_match:
                value = value[: comment_match.start()].strip()
            value = value.strip("\"").strip("'")
            os.environ.setdefault(key, value)
        break


_load_env_file()


def _clean_env(key: str, default: str = "") -> str:
    """Read env var and strip trailing inline comments (defense in depth after _load_env_file)."""
    raw = os.getenv(key, default) or default
    comment_match = re.search(r"\s+#", raw)
    if comment_match:
        raw = raw[: comment_match.start()]
    return raw.strip()


MAX_UPLOAD_MB = int(_clean_env("MAX_UPLOAD_MB", "50") or "50")
# Full OPAR loop (agent tool-use + reflect synthesis). Must exceed agent + LLM synthesis budgets.
OPAR_TIMEOUT_SECONDS = int(_clean_env("OPAR_TIMEOUT_SECONDS", "240") or "240")
# Wall-clock budgets for reflect/chat LLM synthesis (thread-pool futures).
LLM_SYNTHESIS_TIMEOUT_SECONDS = int(_clean_env("LLM_SYNTHESIS_TIMEOUT_SECONDS", "90") or "90")
LLM_THINKING_TIMEOUT_SECONDS = int(_clean_env("LLM_THINKING_TIMEOUT_SECONDS", "180") or "180")

# Optional external connectors; app works in local mode without these.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_ENABLED = bool(ANTHROPIC_API_KEY)

# Gemini provider — set LLM_PROVIDER=gemini to route all LLM calls through Gemini.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_ENABLED = bool(GEMINI_API_KEY)
GEMINI_MODEL = _clean_env("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_THINKING_MODEL = _clean_env("GEMINI_THINKING_MODEL", "gemini-2.5-pro")
GEMINI_TOOL_MODEL = _clean_env("GEMINI_TOOL_MODEL", "gemini-2.5-flash")
# "gemini" (default when key present) | "anthropic"
_default_llm_provider = "gemini" if GEMINI_ENABLED else "anthropic"
_llm_provider_raw = _clean_env("LLM_PROVIDER", _default_llm_provider).lower()
LLM_PROVIDER = _llm_provider_raw if _llm_provider_raw in ("anthropic", "gemini") else "anthropic"


def llm_synthesis_timeout_seconds(payload_bytes: int | None = None) -> int:
    """Wall-clock budget for standard (non-extended-thinking) synthesis calls."""
    base = max(30, LLM_SYNTHESIS_TIMEOUT_SECONDS)
    if payload_bytes:
        if payload_bytes > 100_000:
            base = max(base, 120)
        elif payload_bytes > 50_000:
            base = max(base, 105)
        elif payload_bytes > 35_000:
            base = max(base, 90)
    # Leave headroom for observe/plan/act before reflect synthesis runs.
    return min(base, max(OPAR_TIMEOUT_SECONDS - 45, 60))


def llm_thinking_timeout_seconds() -> int:
    """Wall-clock budget for extended-thinking synthesis calls."""
    cap = max(90, LLM_THINKING_TIMEOUT_SECONDS)
    return min(cap, max(OPAR_TIMEOUT_SECONDS - 30, 90))

# LLM-first intent classification — the LLM reads each chat message and routes
# over the full intent taxonomy; the keyword classifier is the deterministic
# fallback (offline / timeout / pytest). On by default when a provider exists.
LLM_INTENT_CLASSIFICATION_ENABLED = (
    os.getenv("LLM_INTENT_CLASSIFICATION_ENABLED", "true").lower() not in ("false", "0", "no")
    and bool(ANTHROPIC_API_KEY or GEMINI_API_KEY)
)

# LLM-first chat answer synthesis — the LLM reads the question + full spend
# context and writes the answer; the deterministic keyword composer
# (qa_lookup.answer_general_qa) is the offline / timeout / pytest fallback.
# Provider-agnostic: routed by LLM_PROVIDER (Claude default) with cross-provider
# fallback. On by default when a provider exists.
LLM_CHAT_SYNTHESIS_ENABLED = (
    os.getenv("LLM_CHAT_SYNTHESIS_ENABLED", "true").lower() not in ("false", "0", "no")
    and bool(ANTHROPIC_API_KEY or GEMINI_API_KEY)
)

# Agent controller — LLM tool-use loop (M2/M3 only; pytest/M1 use deterministic fallback)
AGENT_CONTROLLER_ENABLED = os.getenv("AGENT_CONTROLLER_ENABLED", "true").lower() not in ("false", "0", "no")
AGENT_MAX_TOOL_ITERATIONS = int(os.getenv("AGENT_MAX_TOOL_ITERATIONS", "12"))
AGENT_TOOL_TIMEOUT_SECONDS = float(os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "45"))
AGENT_THINKING_BUDGET = int(os.getenv("AGENT_THINKING_BUDGET", "8192"))
AGENT_LLM_NUMERIC_ADJUSTMENT_PCT = float(os.getenv("AGENT_LLM_NUMERIC_ADJUSTMENT_PCT", "0.25"))
ANTHROPIC_MODEL = _clean_env("ANTHROPIC_MODEL", "claude-sonnet-4-6")
ANTHROPIC_AGENT_MODEL = os.getenv("ANTHROPIC_AGENT_MODEL", "claude-sonnet-4-6")
ANTHROPIC_TOOL_MODEL = os.getenv("ANTHROPIC_TOOL_MODEL", "claude-sonnet-4-6")
SKILL_CATALOG_COLLECTION = os.getenv("SKILL_CATALOG_COLLECTION", "skill_catalog")

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

