from __future__ import annotations

from app.services.spend_charts import _js_format_money_fn, build_spend_profile_chart_html


def test_spend_profile_chart_html_uses_inr_formatting(tmp_path, monkeypatch) -> None:
    from app.config import OUTPUT_DIR

    monkeypatch.setattr("app.services.spend_charts.OUTPUT_DIR", tmp_path)

    profile = {
        "total_spend": 25_000_000.0,
        "category_profile": [
            {
                "category_id": "IT",
                "category_name": "IT",
                "spend": 25_000_000.0,
                "addressable_spend": 10_000_000.0,
            }
        ],
    }
    chart_plan = {"selected_charts": [], "commentary_points": []}

    path = build_spend_profile_chart_html(
        profile,
        chart_plan,
        filename="test_chart.html",
        reporting_currency="INR",
    )
    html = path.read_text(encoding="utf-8")

    assert "formatMoney" in html
    assert "'$' + Number(v)" not in html
    assert "₹" in html
    assert '"currency": "INR"' in html


def test_js_format_money_fn_usd_uses_dollar_symbol() -> None:
    js = _js_format_money_fn("USD")
    assert "sym = '$'" in js
    assert "₹" not in js
