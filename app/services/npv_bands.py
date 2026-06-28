"""Band-scaled NPV — mirrors savings_modeler phased cash flows at P10/P50/P90."""
from __future__ import annotations

DEFAULT_DISCOUNT_RATE = 0.10
CTA_Y2_FRACTION = 0.25
DEFAULT_P10_FACTOR = 0.70
DEFAULT_P90_FACTOR = 1.30


def band_savings_amount(
    *,
    band: str,
    p10_savings: float | None = None,
    p50_savings: float | None = None,
    p90_savings: float | None = None,
    gross_savings_y1: float = 0.0,
    net_npv: float = 0.0,
) -> float:
    """Resolve P10/P50/P90 savings for an initiative (absolute currency units)."""
    base = float(p50_savings if p50_savings is not None else gross_savings_y1 or net_npv or 0.0)
    if band == "p10":
        if p10_savings is not None:
            return float(p10_savings)
        return base * DEFAULT_P10_FACTOR
    if band == "p90":
        if p90_savings is not None:
            return float(p90_savings)
        return base * DEFAULT_P90_FACTOR
    return base


def compute_band_npv(
    *,
    gross_y1: float,
    gross_y2: float,
    gross_y3: float,
    cost_to_achieve_3yr: float,
    band_savings: float,
    p50_savings: float,
    net_npv_p50: float = 0.0,
    discount_rate: float = DEFAULT_DISCOUNT_RATE,
) -> float:
    """NPV of 3-year net savings scaled to a percentile band.

  Savings (gross Y1–Y3) and cost-to-achieve scale linearly with the band
  factor (band_savings / p50_savings). CTA is front-loaded using the same
  Y1/Y2 split as savings_modeler (75% / 25% / 0%).
    """
    p50 = float(p50_savings)
    if p50 <= 0:
        return float(net_npv_p50)

    factor = float(band_savings) / p50
    y1, y2, y3 = float(gross_y1) * factor, float(gross_y2) * factor, float(gross_y3) * factor
    gross_total = y1 + y2 + y3

    if gross_total > 0:
        cta_total = float(cost_to_achieve_3yr) * factor
        cta_y1 = cta_total * (1.0 - CTA_Y2_FRACTION)
        cta_y2 = cta_total * CTA_Y2_FRACTION
        ny1, ny2, ny3 = y1 - cta_y1, y2 - cta_y2, y3
        r = float(discount_rate)
        return (
            ny1 / (1.0 + r) ** 1
            + ny2 / (1.0 + r) ** 2
            + ny3 / (1.0 + r) ** 3
        )

    stored = float(net_npv_p50)
    return stored * factor if stored else 0.0


def initiative_band_npv(initiative: dict, band: str, discount_rate: float = DEFAULT_DISCOUNT_RATE) -> float:
    """Convenience wrapper for pipeline / API initiative rows."""
    p50 = band_savings_amount(
        band="p50",
        p50_savings=initiative.get("p50_savings"),
        gross_savings_y1=initiative.get("gross_savings_y1"),
        net_npv=initiative.get("net_npv"),
    )
    band_amt = band_savings_amount(
        band=band,
        p10_savings=initiative.get("p10_savings"),
        p50_savings=initiative.get("p50_savings"),
        p90_savings=initiative.get("p90_savings"),
        gross_savings_y1=initiative.get("gross_savings_y1"),
        net_npv=initiative.get("net_npv"),
    )
    return compute_band_npv(
        gross_y1=float(initiative.get("gross_savings_y1") or 0.0),
        gross_y2=float(initiative.get("gross_savings_y2") or 0.0),
        gross_y3=float(initiative.get("gross_savings_y3") or 0.0),
        cost_to_achieve_3yr=float(initiative.get("cost_to_achieve") or 0.0),
        band_savings=band_amt,
        p50_savings=p50,
        net_npv_p50=float(initiative.get("net_npv") or 0.0),
        discount_rate=discount_rate,
    )
