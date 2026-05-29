"""Currency-aware money formatting for chat answers (INR Lakh/Crore vs others)."""
from __future__ import annotations

from app.opar.orchestrator import _answer_general_qa
from app.utils.inr_format import format_money

_PROFILE = {
    "spend-profiler": {
        "total_spend": 50_000_000,
        "category_profile": [
            {"category_name": "IT", "category_id": "IT", "spend": 30_000_000},
            {"category_name": "Travel", "category_id": "TRAVEL", "spend": 20_000_000},
        ],
    }
}


def test_format_money_inr_uses_crore_lakh() -> None:
    assert format_money(12_000_000, "INR") == "₹1.20 Cr"
    assert format_money(250_000, "INR") == "₹2.50 L"


def test_format_money_usd_and_unknown() -> None:
    assert format_money(12_000_000, "USD") == "$12,000,000"
    assert format_money(500_000, "EUR") == "€500,000"
    assert format_money(100_000, "XOF") == "100,000 XOF"
    assert format_money(100_000, None) == "$100,000"  # default preserves prior behaviour


def test_general_qa_inr_answer_has_rupee_not_dollar() -> None:
    out = _answer_general_qa("what is my total spend", _PROFILE, currency="INR")
    assert "₹" in out and "$" not in out
    assert "Cr" in out


def test_general_qa_usd_answer_unchanged() -> None:
    out = _answer_general_qa("what is my total spend", _PROFILE, currency="USD")
    assert "$50,000,000" in out
