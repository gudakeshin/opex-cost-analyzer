"""INR formatting utilities for the Indian numbering system.

Indian system: ones, thousands, then Lakhs (100K), Crores (10M).
Executive outputs use Lakh/Crore notation; a toggle allows millions/billions
for global investor decks.
"""
from __future__ import annotations

from typing import Literal

Scale = Literal["auto", "crore", "lakh", "absolute"]


def format_inr(
    amount: float,
    scale: Scale = "auto",
    decimals: int = 2,
    symbol: bool = True,
    international: bool = False,
) -> str:
    """Return a human-readable INR string.

    Args:
        amount: Raw amount in INR.
        scale: Force a display scale or let 'auto' pick based on magnitude.
        decimals: Decimal places (0–2).
        symbol: Prepend ₹ symbol when True.
        international: Use millions/billions notation instead of Lakh/Crore.
    """
    prefix = "₹" if symbol else ""

    if international:
        return _format_international(amount, prefix, decimals)

    if scale == "auto":
        abs_amount = abs(amount)
        if abs_amount >= 1_00_00_000:   # ≥ 1 Crore
            scale = "crore"
        elif abs_amount >= 1_00_000:    # ≥ 1 Lakh
            scale = "lakh"
        else:
            scale = "absolute"

    if scale == "crore":
        value = amount / 1_00_00_000
        suffix = " Cr"
    elif scale == "lakh":
        value = amount / 1_00_000
        suffix = " L"
    else:
        value = amount
        suffix = ""

    formatted = f"{value:,.{decimals}f}"
    return f"{prefix}{formatted}{suffix}"


_CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "AUD": "A$", "SGD": "S$"}


def format_money(amount: float, currency: str | None = None, decimals: int | None = None) -> str:
    """Currency-aware money formatter.

    INR uses the Indian Lakh/Crore convention (₹1.20 Cr); other currencies use
    their symbol with grouped thousands. Unknown currencies fall back to the
    ISO code suffix. This is the single helper chat/general-QA responses should
    use instead of hardcoding '$'.
    """
    cur = (currency or "USD").upper()
    if cur == "INR":
        return format_inr(amount, decimals=2 if decimals is None else decimals)
    dp = 0 if decimals is None else decimals
    symbol = _CURRENCY_SYMBOLS.get(cur)
    if symbol:
        return f"{symbol}{amount:,.{dp}f}"
    return f"{amount:,.{dp}f} {cur}"


def format_inr_range(p10: float, p50: float, p90: float, **kwargs) -> str:
    """Return a P10/P50/P90 range string, e.g. '₹190–260–320 Cr'."""
    def _val(v: float) -> str:
        return format_inr(v, symbol=False, **kwargs)
    sym = "₹" if kwargs.get("symbol", True) else ""
    return f"{sym}{_val(p10)}–{_val(p50)}–{_val(p90)}"


def _format_international(amount: float, prefix: str, decimals: int) -> str:
    abs_amount = abs(amount)
    if abs_amount >= 1_000_000_000:
        return f"{prefix}{amount / 1_000_000_000:,.{decimals}f}B"
    if abs_amount >= 1_000_000:
        return f"{prefix}{amount / 1_000_000:,.{decimals}f}M"
    return f"{prefix}{amount:,.{decimals}f}"


def inr_to_crore(amount: float) -> float:
    """Convert a raw INR amount to Crore."""
    return amount / 1_00_00_000


def inr_to_lakh(amount: float) -> float:
    """Convert a raw INR amount to Lakh."""
    return amount / 1_00_000


def crore_to_inr(crore: float) -> float:
    """Convert Crore to raw INR."""
    return crore * 1_00_00_000


def lakh_to_inr(lakh: float) -> float:
    """Convert Lakh to raw INR."""
    return lakh * 1_00_000


def bps_label(bps: float, decimals: int = 0) -> str:
    """Format a basis-point value, e.g. '+180 bps'."""
    sign = "+" if bps >= 0 else ""
    return f"{sign}{bps:.{decimals}f} bps"
