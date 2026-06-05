"""Hierarchical (parent-child) Markdown chunking for engagement documents.

Pure, dependency-free splitter — no Qdrant / embedding imports — so it stays
fully unit-testable (mirrors the style of ``engagement_sanity.py``).

The document is split twice:
  * Parent nodes (Level 1): Markdown sections (heading boundaries), further split
    at a ~1024-token char budget. These are "complete thoughts" — stored whole in
    a filesystem doc store and merged back in at retrieval time.
  * Child / leaf nodes (Level 2): each parent split into ~256-token chunks at
    sentence boundaries (with overlap). Table rows are kept intact and each data
    row becomes its own leaf (carrying the header for column context) so a single
    figure buried in a table row stays precisely retrievable.

Only child nodes are embedded into the vector store; every child carries a
``parent_id`` pointer back to its parent.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Tuple

from app.config import DOC_CHILD_CHARS, DOC_CHILD_OVERLAP, DOC_PARENT_CHARS

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_PARA_RE = re.compile(r"\n\s*\n")


@dataclass
class ParentNode:
    parent_id: str
    doc_id: str
    engagement_id: str
    filename: str
    heading_path: str
    order: int
    text: str
    child_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChildNode:
    child_id: str
    parent_id: str
    doc_id: str
    engagement_id: str
    filename: str
    heading_path: str
    order: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Parent-level splitting
# ---------------------------------------------------------------------------

def _split_into_sections(markdown: str) -> List[Tuple[str, str]]:
    """Split markdown into (heading_path, section_text) by heading boundaries."""
    sections: List[Tuple[str, str]] = []
    heading_stack: Dict[int, str] = {}
    cur_path = ""
    cur_lines: List[str] = []

    def flush() -> None:
        text = "\n".join(cur_lines).strip()
        if text:
            sections.append((cur_path, text))

    for line in markdown.split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            flush()
            cur_lines = []
            level = len(m.group(1))
            title = m.group(2).strip()
            for lv in [lv for lv in heading_stack if lv >= level]:
                del heading_stack[lv]
            heading_stack[level] = title
            cur_path = " > ".join(heading_stack[lv] for lv in sorted(heading_stack))
        cur_lines.append(line)
    flush()
    return sections


def _pack_parents(sections: List[Tuple[str, str]], parent_chars: int) -> List[Tuple[str, str]]:
    """Within over-long sections, split on paragraph boundaries to honour the budget."""
    parents: List[Tuple[str, str]] = []
    for path, text in sections:
        if len(text) <= parent_chars:
            parents.append((path, text))
            continue
        buf = ""
        for para in _PARA_RE.split(text):
            para = para.strip()
            if not para:
                continue
            if buf and len(buf) + len(para) + 2 > parent_chars:
                parents.append((path, buf.strip()))
                buf = para
            else:
                buf = f"{buf}\n\n{para}" if buf else para
        if buf.strip():
            parents.append((path, buf.strip()))
    return parents


# ---------------------------------------------------------------------------
# Child-level splitting
# ---------------------------------------------------------------------------

def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and (stripped.startswith("|") or stripped.count("|") >= 2)


def _is_separator_row(line: str) -> bool:
    stripped = line.strip().strip("|").strip()
    return bool(stripped) and set(stripped) <= set("-: |")


def _segment_blocks(text: str) -> List[Tuple[str, List[str]]]:
    """Group consecutive lines into ('table'|'prose', lines) blocks."""
    blocks: List[Tuple[str, List[str]]] = []
    cur_kind = ""
    cur: List[str] = []
    for line in text.split("\n"):
        kind = "table" if _is_table_line(line) else "prose"
        if kind != cur_kind and cur:
            blocks.append((cur_kind, cur))
            cur = []
        cur_kind = kind
        cur.append(line)
    if cur:
        blocks.append((cur_kind, cur))
    return blocks


def _table_children(lines: List[str]) -> List[str]:
    rows = [ln for ln in lines if ln.strip()]
    if not rows:
        return []
    header = rows[0]
    body_start = 1
    prefix = header
    if len(rows) > 1 and _is_separator_row(rows[1]):
        prefix = f"{header}\n{rows[1]}"
        body_start = 2
    data_rows = rows[body_start:]
    if not data_rows:
        return ["\n".join(rows)]
    return [f"{prefix}\n{row}" for row in data_rows]


def _explode_long(sentences: List[str], limit: int) -> List[str]:
    out: List[str] = []
    for s in sentences:
        if len(s) <= limit:
            out.append(s)
        else:
            out.extend(s[i:i + limit] for i in range(0, len(s), limit))
    return out


def _prose_children(prose: str, child_chars: int, overlap: int) -> List[str]:
    sentences = _explode_long([s for s in _SENTENCE_RE.split(prose) if s.strip()], child_chars)
    chunks: List[str] = []
    cur = ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > child_chars:
            chunks.append(cur.strip())
            tail = cur[-overlap:] if overlap > 0 else ""
            cur = f"{tail} {s}".strip()
        else:
            cur = f"{cur} {s}".strip() if cur else s
    if cur.strip():
        chunks.append(cur.strip())
    return chunks


def _children_for_text(text: str, child_chars: int, overlap: int) -> List[str]:
    children: List[str] = []
    for kind, block_lines in _segment_blocks(text):
        if kind == "table":
            children.extend(_table_children(block_lines))
        else:
            prose = "\n".join(block_lines).strip()
            if prose:
                children.extend(_prose_children(prose, child_chars, overlap))
    return [c for c in children if c.strip()]


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def split_markdown_hierarchical(
    markdown: str,
    *,
    doc_id: str,
    engagement_id: str,
    filename: str,
    parent_chars: int = DOC_PARENT_CHARS,
    child_chars: int = DOC_CHILD_CHARS,
    overlap: int = DOC_CHILD_OVERLAP,
) -> Tuple[List[ParentNode], List[ChildNode]]:
    """Split a parsed Markdown document into parent + child nodes.

    Returns ``(parents, children)``. Every child's ``parent_id`` resolves to a
    parent in the returned list.
    """
    parents: List[ParentNode] = []
    children: List[ChildNode] = []
    if not markdown or not markdown.strip():
        return parents, children

    sections = _split_into_sections(markdown)
    child_order = 0
    for p_idx, (path, text) in enumerate(_pack_parents(sections, parent_chars)):
        parent_id = f"{doc_id}::p{p_idx}"
        child_texts = _children_for_text(text, child_chars, overlap)
        if not child_texts and text.strip():
            child_texts = [text.strip()]
        child_ids: List[str] = []
        for c_idx, ctext in enumerate(child_texts):
            child_id = f"{parent_id}::c{c_idx}"
            children.append(
                ChildNode(
                    child_id=child_id,
                    parent_id=parent_id,
                    doc_id=doc_id,
                    engagement_id=engagement_id,
                    filename=filename,
                    heading_path=path,
                    order=child_order,
                    text=ctext,
                )
            )
            child_ids.append(child_id)
            child_order += 1
        parents.append(
            ParentNode(
                parent_id=parent_id,
                doc_id=doc_id,
                engagement_id=engagement_id,
                filename=filename,
                heading_path=path,
                order=p_idx,
                text=text,
                child_ids=child_ids,
            )
        )
    return parents, children
