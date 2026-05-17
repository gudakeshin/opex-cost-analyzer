from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.config import OUTPUT_DIR


def _confidence_color(confidence: str) -> str:
    mapping = {"high": "#70AD47", "medium": "#FFC000", "low": "#C00000"}
    return mapping.get((confidence or "medium").lower(), "#FFC000")


def build_dashboard_html(analysis: Dict[str, Any], filename: str = "dashboard.html") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename

    skill_outputs = analysis.get("skill_outputs", {})
    bridge = skill_outputs.get("value-bridge-calculator", {})
    matrix = bridge.get("value_matrix", [])
    conf_bands = bridge.get("confidence_bands", {})
    category_profile = skill_outputs.get("spend-profiler", {}).get("category_profile", [])

    # Chart 1: Horizontal grouped bar — low / mid / high per category
    labels: List[str] = [x.get("category_name") or x.get("category_id", "") for x in matrix[:12]]
    mid_vals = [round(x.get("deduped_mid_savings", 0.0), 0) for x in matrix[:12]]
    low_vals = [round(v * 0.8, 0) for v in mid_vals]
    high_vals = [round(v * 1.2, 0) for v in mid_vals]
    chart1_payload = json.dumps({"labels": labels, "low": low_vals, "mid": mid_vals, "high": high_vals})

    # Chart 2: Waterfall — Total Spend → Non-Addressable → Addressable → Identified Savings
    total_spend = skill_outputs.get("spend-profiler", {}).get("total_spend", 0.0)
    addressable_spend = sum(float(c.get("addressable_spend", 0.0)) for c in category_profile)
    non_addressable = max(total_spend - addressable_spend, 0.0)
    identified_savings = float(conf_bands.get("mid", 0.0))
    unidentified_gap = max(addressable_spend - identified_savings, 0.0)
    wf_labels = ["Total Spend", "Non-Addressable", "Addressable Spend", "Unidentified Gap", "Identified Savings"]
    wf_values = [total_spend, non_addressable, addressable_spend, unidentified_gap, identified_savings]
    wf_bases = [0.0, total_spend - non_addressable, 0.0, identified_savings, 0.0]
    wf_colors = ["#4472C4", "#A9A9A9", "#ED7D31", "#FFD966", "#70AD47"]
    chart2_payload = json.dumps({
        "labels": wf_labels,
        "bases": wf_bases,
        "values": wf_values,
        "colors": wf_colors,
    })

    # Summary table rows
    table_rows_html = ""
    for item in matrix[:12]:
        cat_name = item.get("category_name") or item.get("category_id", "")
        npv = float(item.get("net_npv", 0.0))
        payback = item.get("payback_months", "—")
        conf = item.get("confidence", "medium")
        color = _confidence_color(conf)
        mid_s = float(item.get("deduped_mid_savings", 0.0))
        table_rows_html += (
            f"<tr>"
            f"<td>{cat_name}</td>"
            f"<td>${mid_s:,.0f}</td>"
            f"<td>${npv:,.0f}</td>"
            f"<td>{payback}</td>"
            f"<td style='background:{color};color:#fff;text-align:center'>{conf.upper()}</td>"
            f"</tr>"
        )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>OpEx Value Bridge Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; background: #f9f9f9; }}
    h1 {{ color: #1F3864; }}
    h2 {{ color: #2F5597; margin-top: 40px; }}
    .chart-wrap {{ background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 40px;
                   box-shadow: 0 1px 4px rgba(0,0,0,0.12); }}
    table {{ border-collapse: collapse; width: 100%; background: #fff;
             box-shadow: 0 1px 4px rgba(0,0,0,0.12); border-radius: 8px; overflow: hidden; }}
    th {{ background: #1F3864; color: #fff; padding: 10px 14px; text-align: left; }}
    td {{ padding: 9px 14px; border-bottom: 1px solid #eee; }}
    tr:last-child td {{ border-bottom: none; }}
    tr:nth-child(even) {{ background: #f4f6fb; }}
  </style>
</head>
<body>
  <h1>OpEx Value Bridge Dashboard</h1>

  <h2>Savings by Category — Confidence Bands</h2>
  <div class="chart-wrap">
    <canvas id="chart1" height="120"></canvas>
  </div>

  <h2>Value Waterfall</h2>
  <div class="chart-wrap">
    <canvas id="chart2" height="80"></canvas>
  </div>

  <h2>Initiative Summary</h2>
  <table>
    <thead>
      <tr>
        <th>Category</th><th>Mid Savings (3yr)</th><th>Net NPV</th><th>Payback (mo)</th><th>Confidence</th>
      </tr>
    </thead>
    <tbody>
      {table_rows_html}
    </tbody>
  </table>

  <script>
    // Chart 1 — Horizontal grouped bar with confidence bands
    (function() {{
      const d = {chart1_payload};
      const ctx = document.getElementById('chart1');
      new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: d.labels,
          datasets: [
            {{ label: 'Low', data: d.low, backgroundColor: '#C00000' }},
            {{ label: 'Mid', data: d.mid, backgroundColor: '#4472C4' }},
            {{ label: 'High', data: d.high, backgroundColor: '#70AD47' }}
          ]
        }},
        options: {{
          indexAxis: 'y',
          responsive: true,
          plugins: {{ legend: {{ position: 'top' }} }},
          scales: {{
            x: {{ ticks: {{ callback: v => '$' + Number(v).toLocaleString() }} }}
          }}
        }}
      }});
    }})();

    // Chart 2 — Waterfall (stacked bar with transparent base)
    (function() {{
      const d = {chart2_payload};
      const ctx = document.getElementById('chart2');
      new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: d.labels,
          datasets: [
            {{
              label: 'base',
              data: d.bases,
              backgroundColor: 'transparent',
              borderColor: 'transparent',
              stack: 'wf'
            }},
            {{
              label: 'Amount',
              data: d.values,
              backgroundColor: d.colors,
              stack: 'wf'
            }}
          ]
        }},
        options: {{
          responsive: true,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                label: function(ctx) {{
                  if (ctx.dataset.label === 'base') return null;
                  return '$' + Number(ctx.raw).toLocaleString();
                }}
              }}
            }}
          }},
          scales: {{
            x: {{ stacked: true }},
            y: {{ stacked: true, ticks: {{ callback: v => '$' + Number(v).toLocaleString() }} }}
          }}
        }}
      }});
    }})();
  </script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
    return path
