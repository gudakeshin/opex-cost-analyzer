"""Narrative provenance — tag, store, and replay LLM-generated narrative.

Every sentence produced by an LLM call is tagged with:
  data_slice    — which skill outputs were in context
  prompt_hash   — SHA-256 of the rendered prompt (first 12 hex chars)
  model_version — model ID string
  seed          — deterministic seed (0 for non-seeded providers)

Snapshots are stored as JSONL in data/provenance/{engagement_id}/{turn_id}.jsonl.
Re-running with the same seed/prompt_hash/model_version must produce byte-identical
narrative (verified in tests).  Snapshots survive engagement tear-down (they are
transferred to the attested archive before IaC destroy).
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import ROOT_DIR

_PROVENANCE_DIR = ROOT_DIR / "data" / "provenance"
_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Tag structure                                                                 #
# --------------------------------------------------------------------------- #

def _make_prompt_hash(prompt_text: str) -> str:
    return hashlib.sha256(prompt_text.encode()).hexdigest()[:12]


def build_provenance_tag(
    data_slice: List[str],
    prompt_text: str,
    model_version: str,
    seed: int = 0,
) -> Dict[str, Any]:
    """Build a provenance tag dict for one LLM call."""
    return {
        "data_slice": sorted(data_slice),
        "prompt_hash": _make_prompt_hash(prompt_text),
        "model_version": model_version,
        "seed": seed,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- #
# Sentence-level tagging                                                        #
# --------------------------------------------------------------------------- #

def tag_narrative(
    narrative_text: str,
    provenance_tag: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Split narrative into sentences and attach provenance to each.

    Returns a list of {sentence, provenance} dicts.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narrative_text.strip()) if s.strip()]
    return [{"sentence": s, "provenance": provenance_tag} for s in sentences]


# --------------------------------------------------------------------------- #
# Snapshot store                                                                #
# --------------------------------------------------------------------------- #

def _snapshot_path(engagement_id: str, turn_id: str) -> Path:
    return _PROVENANCE_DIR / engagement_id / f"{turn_id}.jsonl"


def save_snapshot(
    engagement_id: str,
    turn_id: str,
    tagged_sentences: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
) -> Path:
    """Persist tagged sentences to the provenance store.

    File is opened in append mode; subsequent calls for the same turn append
    additional entries (e.g. when multiple LLM calls contribute to one turn).
    Returns the path to the snapshot file.
    """
    path = _snapshot_path(engagement_id, turn_id)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for entry in tagged_sentences:
                record = {
                    "engagement_id": engagement_id,
                    "turn_id": turn_id,
                    "sentence": entry.get("sentence", ""),
                    "provenance": entry.get("provenance", {}),
                    "metadata": metadata or {},
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def load_snapshot(engagement_id: str, turn_id: str) -> List[Dict[str, Any]]:
    """Load all tagged sentences for a given turn.  Returns [] if not found."""
    path = _snapshot_path(engagement_id, turn_id)
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    with _lock:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def replay_snapshot(engagement_id: str, turn_id: str) -> str:
    """Reconstruct the original narrative text from a stored snapshot."""
    records = load_snapshot(engagement_id, turn_id)
    return " ".join(r["sentence"] for r in records if r.get("sentence"))


# --------------------------------------------------------------------------- #
# Verification helper                                                            #
# --------------------------------------------------------------------------- #

def verify_reproducibility(
    engagement_id: str,
    turn_id: str,
    regenerated_text: str,
) -> Dict[str, Any]:
    """Compare a freshly regenerated narrative against the stored snapshot.

    Returns a dict with: match (bool), original_sentences, new_sentences,
    diff_count.  Byte-identical iff match is True.
    """
    stored = replay_snapshot(engagement_id, turn_id)
    match = stored.strip() == regenerated_text.strip()
    orig_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", stored.strip()) if s.strip()]
    new_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", regenerated_text.strip()) if s.strip()]
    return {
        "match": match,
        "original_sentences": orig_sentences,
        "new_sentences": new_sentences,
        "diff_count": sum(1 for o, n in zip(orig_sentences, new_sentences) if o != n)
        + abs(len(orig_sentences) - len(new_sentences)),
    }


# --------------------------------------------------------------------------- #
# Convenience wrapper used by reflect.py                                        #
# --------------------------------------------------------------------------- #

def record_llm_narrative(
    narrative: str,
    *,
    engagement_id: str,
    turn_id: str,
    skill_outputs_used: List[str],
    prompt_text: str,
    model_version: str,
    seed: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Tag and persist narrative from a single LLM call.

    Returns the provenance tag dict (for attaching to the response payload).
    """
    tag = build_provenance_tag(skill_outputs_used, prompt_text, model_version, seed)
    tagged = tag_narrative(narrative, tag)
    save_snapshot(engagement_id, turn_id, tagged, metadata=metadata)
    return tag
