from app.services.deep_research_prompt import build_default_deep_research_prompt


def test_build_default_deep_research_prompt_includes_context():
    prompt = build_default_deep_research_prompt("Infosys Ltd", "it_ites", 150_000.0)

    assert "Infosys Ltd" in prompt
    assert "it_ites" in prompt
    assert "150,000" in prompt
    assert "Company-specific developments" in prompt
    assert "Peer and competitive landscape" in prompt
    assert "Sector and macro context" in prompt
    assert "Implications for cost optimization" in prompt
