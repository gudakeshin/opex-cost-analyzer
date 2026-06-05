"""Tests for the hierarchical (parent-child) Markdown chunker."""
from __future__ import annotations

from app.services.chunking import split_markdown_hierarchical

EID = "eng-1"
DID = "doc-1"


def _split(md, **kw):
    return split_markdown_hierarchical(md, doc_id=DID, engagement_id=EID, filename="deck.pdf", **kw)


def test_empty_returns_nothing():
    parents, children = _split("")
    assert parents == [] and children == []
    parents, children = _split("   \n  \n")
    assert parents == [] and children == []


def test_no_headings_single_parent():
    parents, children = _split("Just a paragraph of plain text with no headings at all.")
    assert len(parents) == 1
    assert parents[0].heading_path == ""
    assert len(children) >= 1


def test_heading_split_sets_breadcrumb():
    md = "# Strategy\nIntro.\n\n## R&D\nDetails about research.\n\n## Sales\nSales notes."
    parents, _ = _split(md)
    paths = [p.heading_path for p in parents]
    assert "Strategy" in paths
    assert "Strategy > R&D" in paths
    assert "Strategy > Sales" in paths


def test_parent_char_budget_splits_long_section():
    body = "\n\n".join(f"Paragraph number {i} with some filler content." for i in range(60))
    md = f"# Big\n{body}"
    parents, _ = _split(md, parent_chars=300)
    assert len(parents) > 1
    # all carry the same heading breadcrumb
    assert all(p.heading_path == "Big" for p in parents)


def test_every_child_resolves_to_a_parent():
    md = "# A\nlong text. " * 200 + "\n\n# B\nmore text here. " * 50
    parents, children = _split(md, parent_chars=400, child_chars=120)
    parent_ids = {p.parent_id for p in parents}
    assert children
    assert all(c.parent_id in parent_ids for c in children)
    # parent.child_ids must match the children that point back to it
    for p in parents:
        owned = {c.child_id for c in children if c.parent_id == p.parent_id}
        assert set(p.child_ids) == owned


def test_child_order_is_monotonic():
    md = "# A\n" + "Sentence one. Sentence two. Sentence three. " * 40
    _, children = _split(md, child_chars=80)
    orders = [c.order for c in children]
    assert orders == sorted(orders)
    assert orders == list(range(len(children)))


def test_table_rows_become_individual_children():
    md = (
        "# Budget\n"
        "| Item | Cost |\n"
        "| --- | --- |\n"
        "| GPU clusters | ₹190 Cr |\n"
        "| AWS partnership | ₹90 Cr |\n"
        "| Data platform | ₹50 Cr |\n"
    )
    parents, children = _split(md)
    # one section/parent, three data rows -> three leaf children
    assert len(parents) == 1
    row_children = [c for c in children if "Cr" in c.text]
    assert len(row_children) == 3
    # each data-row child keeps the header for column context
    assert all("Item" in c.text and "Cost" in c.text for c in row_children)
    # the specific figure is isolated in its own leaf (precise retrieval)
    assert any("₹190 Cr" in c.text for c in row_children)
    # the parent keeps the whole table
    assert "₹190 Cr" in parents[0].text and "₹90 Cr" in parents[0].text


def test_single_giant_table_no_headings():
    rows = "\n".join(f"| Row {i} | value {i} |" for i in range(50))
    md = "| Item | Value |\n| --- | --- |\n" + rows
    parents, children = _split(md)
    assert len(parents) == 1
    assert len([c for c in children if "Row" in c.text]) == 50


def test_overlap_carryover_between_prose_children():
    md = "# A\n" + " ".join(f"word{i}." for i in range(400))
    _, children = _split(md, child_chars=120, overlap=40)
    assert len(children) > 1
