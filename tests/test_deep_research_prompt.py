from app.services.deep_research_prompt import (
    build_default_deep_research_prompt,
    build_research_markdown,
)


def test_build_default_deep_research_prompt_includes_context():
    prompt = build_default_deep_research_prompt("Infosys Ltd", "it_ites", 150_000.0)

    assert "Infosys Ltd" in prompt
    assert "it_ites" in prompt
    assert "150,000" in prompt
    # New business-model + industry context sections.
    assert "Company business and business model" in prompt
    assert "Industry deep-dive" in prompt
    assert "Revenue model and monetization" in prompt
    assert "Competitive dynamics" in prompt
    # Retained sections.
    assert "Peer and competitive landscape" in prompt
    assert "Company-specific developments" in prompt
    assert "Macro context" in prompt
    assert "Implications for cost optimization" in prompt


def test_build_research_markdown_renders_sections_and_sources():
    md = build_research_markdown(
        "Acme Corp",
        "telecom",
        5_000.0,
        summary="Condensed CFO summary.",
        full_report="Full telecom research body.",
        sources=[
            {"title": "TRAI report", "url": "https://example.com/trai"},
            {"title": "title only, no url"},
            {"not": "a real source"},  # ignored
        ],
    )

    assert md.startswith("# Industry & Business Context Research — Acme Corp")
    assert "Industry: telecom" in md
    assert "₹5,000 Cr" in md
    assert "## Executive Summary" in md
    assert "Condensed CFO summary." in md
    assert "## Full Research Report" in md
    assert "Full telecom research body." in md
    assert "## Sources" in md
    assert "[TRAI report](https://example.com/trai)" in md
    assert "- title only, no url" in md


def test_build_research_markdown_handles_missing_fields():
    md = build_research_markdown(
        "",
        "",
        0.0,
        summary="",
        full_report="",
        sources=None,
    )
    assert "Industry & Business Context Research — Company" in md
    assert "_No summary available._" in md
    assert "_No report content available._" in md
    assert "## Sources" not in md  # no sources block when empty
