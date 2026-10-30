from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.config import OUTPUT_DIR

_CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥", "AUD": "A$", "SGD": "S$"}


def _js_format_money_fn(currency: str) -> str:
    """Return a JS formatMoney(v) helper matching frontend formatSpendAmount."""
    cur = (currency or "INR").upper()
    if cur == "INR":
        return """
    function formatMoney(v) {
      const n = Number(v);
      if (Math.abs(n) >= 10000000) return '₹' + (n / 10000000).toFixed(1) + ' Cr';
      if (Math.abs(n) >= 100000) return '₹' + (n / 100000).toFixed(1) + ' L';
      return '₹' + n.toLocaleString('en-IN');
    }"""
    sym = _CURRENCY_SYMBOLS.get(cur, f"{cur} ")
    sym_js = sym.replace("\\", "\\\\").replace("'", "\\'")
    return f"""
    function formatMoney(v) {{
      const n = Number(v);
      const sym = '{sym_js}';
      if (Math.abs(n) >= 1000000) return sym + (n / 1000000).toFixed(2) + 'M';
      if (Math.abs(n) >= 1000) return sym + (n / 1000).toFixed(1) + 'K';
      return sym + n.toLocaleString('en-US', {{ maximumFractionDigits: 0 }});
    }}"""


def _safe_filename(name: str) -> str:
    # Preserve extension so exported HTML is served/rendered correctly by browsers.
    keep = [c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name]
    safe = "".join(keep).strip("._")
    if not safe:
        safe = "spend_profile_chart.html"
    if "." not in safe:
        safe = f"{safe}.html"
    return safe


def build_spend_profile_chart_html(
    profile: Dict[str, Any],
    chart_plan: Dict[str, Any],
    filename: str = "spend_profile_chart.html",
    reporting_currency: str = "INR",
) -> Path:
    """Render themed spend-profile chart view for chat/download."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / _safe_filename(filename)

    rows = profile.get("category_profile", []) if isinstance(profile, dict) else []
    rows = sorted(rows, key=lambda x: float(x.get("spend", 0.0)), reverse=True)[:10]
    labels: List[str] = [str(r.get("category_name") or r.get("category_id") or "Unknown") for r in rows]
    spend_vals: List[float] = [float(r.get("spend", 0.0)) for r in rows]
    addr_vals: List[float] = [float(r.get("addressable_spend", 0.0)) for r in rows]
    non_addr_vals: List[float] = [max(s - a, 0.0) for s, a in zip(spend_vals, addr_vals)]
    total = sum(spend_vals) or 1.0
    cumulative: List[float] = []
    running = 0.0
    for s in spend_vals:
        running += s
        cumulative.append(round(running / total * 100.0, 1))

    trend = profile.get("trend_analysis", {}) if isinstance(profile, dict) else {}
    period_totals = trend.get("period_totals", {}) if isinstance(trend, dict) else {}
    trend_labels = sorted(period_totals.keys())
    trend_vals = [float(period_totals[p]) for p in trend_labels]

    currency = (reporting_currency or "INR").upper()
    chart_payload = json.dumps(
        {
            "labels": labels,
            "spend": spend_vals,
            "addressable": addr_vals,
            "non_addressable": non_addr_vals,
            "cumulative_pct": cumulative,
            "trend_labels": trend_labels,
            "trend_values": trend_vals,
            "selected_charts": chart_plan.get("selected_charts", []),
            "currency": currency,
        }
    )
    format_money_js = _js_format_money_fn(currency)
    commentary = chart_plan.get("commentary_points", [])
    commentary_html = "".join(f"<li>{str(x)}</li>" for x in commentary[:6])

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Spend Profile Chart View</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {{
      --panel: #ffffff;
      --bg: #f7f7f8;
      --border: #dde2d6;
      --accent: #86bc25;
      --assistant: #eef1eb;
      --text: #202124;
      --muted: #60646b;
    }}
    body {{
      margin: 0;
      padding: 20px;
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 14px;
      box-shadow: 0 8px 24px rgba(27, 31, 23, 0.06);
    }}
    h1 {{ margin: 0 0 8px; font-size: 20px; }}
    h2 {{ margin: 0 0 10px; font-size: 15px; color: #2a3022; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    ul {{ margin: 8px 0 0 18px; }}
    li {{ margin: 4px 0; font-size: 13px; }}
    canvas {{ max-height: 360px; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Spend Profile Visual Summary</h1>
    <div class="muted">FP&A-oriented chart selection with focused commentary.</div>
  </div>

  <div class="card">
    <h2>Pareto Spend Concentration</h2>
    <canvas id="paretoChart"></canvas>
  </div>

  <div class="card">
    <h2>Addressable vs Non-Addressable Spend</h2>
    <canvas id="addressabilityChart"></canvas>
  </div>

  <div class="card" id="trendCard" style="display:none;">
    <h2>Spend Trend (Period Totals)</h2>
    <canvas id="trendChart"></canvas>
  </div>

  <div class="card">
    <h2>Commentary</h2>
    <ul>{commentary_html}</ul>
  </div>

  <script>
    const d = {chart_payload};
    {format_money_js}
    new Chart(document.getElementById('paretoChart'), {{
      data: {{
        labels: d.labels,
        datasets: [
          {{ type: 'bar', label: 'Spend', data: d.spend, backgroundColor: '#86bc25' }},
          {{ type: 'line', label: 'Cumulative %', data: d.cumulative_pct, yAxisID: 'y2', borderColor: '#2f6fbb', tension: 0.25 }}
        ]
      }},
      options: {{
        responsive: true,
        scales: {{
          y: {{ ticks: {{ callback: v => formatMoney(v) }} }},
          y2: {{
            position: 'right',
            grid: {{ drawOnChartArea: false }},
            min: 0,
            max: 100,
            ticks: {{ callback: v => Number(v).toFixed(0) + '%' }}
          }}
        }}
      }}
    }});

    new Chart(document.getElementById('addressabilityChart'), {{
      type: 'bar',
      data: {{
        labels: d.labels,
        datasets: [
          {{ label: 'Addressable', data: d.addressable, backgroundColor: '#70ad47' }},
          {{ label: 'Non-Addressable', data: d.non_addressable, backgroundColor: '#c8d0bf' }}
        ]
      }},
      options: {{
        responsive: true,
        scales: {{
          x: {{ stacked: true }},
          y: {{ stacked: true, ticks: {{ callback: v => formatMoney(v) }} }}
        }}
      }}
    }});

    if (d.trend_labels && d.trend_labels.length >= 2) {{
      document.getElementById('trendCard').style.display = 'block';
      new Chart(document.getElementById('trendChart'), {{
        type: 'line',
        data: {{
          labels: d.trend_labels,
          datasets: [{{ label: 'Total Spend', data: d.trend_values, borderColor: '#4472c4', tension: 0.25 }}]
        }},
        options: {{
          responsive: true,
          scales: {{
            y: {{ ticks: {{ callback: v => formatMoney(v) }} }}
          }}
        }}
      }});
    }}
  </script>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")
    return path
