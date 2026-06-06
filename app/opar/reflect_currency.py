"""Reflect currency helpers — session reporting currency for formatted output."""
from __future__ import annotations

from app.utils.inr_format import format_money

_REFLECT_CURRENCY: str = "INR"


def set_reflect_currency(currency: str) -> None:
    global _REFLECT_CURRENCY
    _REFLECT_CURRENCY = currency or "INR"


def format_currency(value: float) -> str:
    return format_money(float(value or 0), _REFLECT_CURRENCY)


def get_reflect_currency() -> str:
    return _REFLECT_CURRENCY
