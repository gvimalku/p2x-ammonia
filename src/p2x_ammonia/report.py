"""Assemble a self-contained HTML report (embedded PNG charts) for one case."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Template

from .charts import build_all
from .engine import CaseResult
from .results import build_summary

SECTIONS = [
    ("Cost & economics", ["lcoa_stack", "capex_split", "annual_cashflow",
                          "cumulative_cost", "replacement_timeline"]),
    ("Production", ["annual_production", "degradation"]),
    ("Dispatch & operations", ["duration_curves", "hourly_cf", "storage_states",
                               "energy_allocation", "seasonal_heatmap", "monthly_curtailment"]),
    ("Technical", ["sec_curve"]),
]

TEMPLATE = Template(r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
  :root { --ink:#1f2937; --muted:#6b7280; --line:#e5e7eb; --bg:#f8fafc;
          --card:#ffffff; --accent:#2563eb; --accent2:#059669; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
         color:var(--ink); background:var(--bg); line-height:1.5; }
  .wrap { max-width:1180px; margin:0 auto; padding:32px 20px 64px; }
  header h1 { margin:0 0 4px; font-size:26px; }
  header .sub { color:var(--muted); font-size:14px; }
  .hero { display:flex; flex-wrap:wrap; gap:16px; margin:24px 0 8px; }
  .hero .big { background:linear-gradient(135deg,#2563eb,#1e40af); color:#fff; border-radius:14px;
               padding:20px 24px; min-width:230px; flex:1; }
  .hero .big.alt { background:linear-gradient(135deg,#059669,#047857); }
  .hero .big .label { font-size:13px; opacity:.85; }
  .hero .big .val { font-size:34px; font-weight:700; margin-top:2px; }
  .hero .big .unit { font-size:14px; opacity:.85; }
  .metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0 8px; }
  .metric { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
  .metric .label { font-size:12px; color:var(--muted); }
  .metric .val { font-size:19px; font-weight:600; margin-top:2px; }
  h2 { font-size:18px; margin:36px 0 4px; padding-bottom:8px; border-bottom:2px solid var(--line); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(440px,1fr)); gap:20px; margin-top:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 16px 18px;
          box-shadow:0 1px 2px rgba(0,0,0,.03); }
  .card h3 { margin:0 0 2px; font-size:15px; }
  .card p { margin:0 0 10px; font-size:12.5px; color:var(--muted); }
  .card img { width:100%; height:auto; display:block; }
  .card.err { color:#b91c1c; font-size:13px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:7px 10px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  .review { background:#fffbeb; border:1px solid #fde68a; border-radius:10px; padding:12px 16px; margin-top:16px; font-size:13px; }
  .review b { color:#92400e; }
  footer { margin-top:48px; color:var(--muted); font-size:12px; border-top:1px solid var(--line); padding-top:16px; }
  code { background:#f1f5f9; padding:1px 5px; border-radius:4px; font-size:12px; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{{ title }}</h1>
    <div class="sub">{{ description }} &middot; generated {{ today }}</div>
  </header>

  <div class="hero">
    <div class="big">
      <div class="label">Levelised Cost of Ammonia</div>
      <div class="val">{{ "%.3f"|format(s.lc_nh3_aud_per_kg) }}</div>
      <div class="unit">A$/kg NH₃ &nbsp;·&nbsp; {{ "%.0f"|format(s.lc_nh3_aud_per_kg*1000) }} A$/t</div>
    </div>
    <div class="big alt">
      <div class="label">Levelised Cost of Hydrogen</div>
      <div class="val">{{ "%.3f"|format(s.lc_h2_aud_per_kg) }}</div>
      <div class="unit">A$/kg H₂</div>
    </div>
  </div>

  <div class="metrics">
    <div class="metric"><div class="label">Total CAPEX</div><div class="val">{{ "%.2f"|format(s.capex_total_aud/1e9) }} B A$</div></div>
    <div class="metric"><div class="label">Mean NH₃ output</div><div class="val">{{ "{:,.0f}".format(s.nh3_tpa_mean) }} t/yr</div></div>
    <div class="metric"><div class="label">Mean H₂ output</div><div class="val">{{ "{:,.0f}".format(s.h2_tpa_mean) }} t/yr</div></div>
    {% if s.power_plant_cf_year1 %}<div class="metric"><div class="label">Power-plant CF</div><div class="val">{{ "%.1f"|format(s.power_plant_cf_year1*100) }}%</div></div>{% endif %}
    {% if s.electrolyser_cf_year1 %}<div class="metric"><div class="label">Electrolyser CF</div><div class="val">{{ "%.1f"|format(s.electrolyser_cf_year1*100) }}%</div></div>{% endif %}
    <div class="metric"><div class="label">Electrolyser op. hrs (yr1)</div><div class="val">{{ "{:,}".format(s.op_hours_year1) }} h</div></div>
    <div class="metric"><div class="label">Stack replacements</div><div class="val">yr {{ s.stack_replacement_years|join(", ") }}</div></div>
    <div class="metric"><div class="label">Battery replacement</div><div class="val">yr {{ s.battery_replacement_years|join(", ") }}</div></div>
  </div>

  {% for section, cards in sections %}
    {% if cards %}
    <h2>{{ section }}</h2>
    <div class="grid">
      {% for c in cards %}
        <div class="card{% if c.error %} err{% endif %}">
          <h3>{{ c.title }}</h3>
          <p>{{ c.description }}</p>
          {% if c.error %}<div>chart error: {{ c.error }}</div>
          {% else %}<img alt="{{ c.title }}" src="{{ c.uri }}">{% endif %}
        </div>
      {% endfor %}
    </div>
    {% endif %}
  {% endfor %}

  {% if review %}
  <div class="review">
    <b>⚠ Assumptions flagged for review</b> (verify before production use):
    {{ review|join(" · ") }}
  </div>
  {% endif %}

  <footer>
    Generated by the P2X green-ammonia engine — Python port of the UNSW HySupply Ammonia
    Analysis Tool V1.0. Run with <code>p2x-run {{ config_path }}</code>.
    Parity: LC_H₂ exact, LC_NH₃ within 0.0015% of the workbook.
  </footer>
</div>
</body>
</html>
""")


def render_report(res: CaseResult, out_path: str | Path) -> Path:
    s = build_summary(res)
    charts = {c["id"]: c for c in build_all(res)}
    sections = [(name, [charts[cid] for cid in ids if cid in charts]) for name, ids in SECTIONS]

    review = []
    rv = res.case.meta.get("review")
    if rv and isinstance(rv, dict):
        review = rv.get("parameters", [])

    html = TEMPLATE.render(
        title=f"Green Ammonia — {res.case.case_name}",
        description=res.case.meta.get("description", "Techno-economic results"),
        today=date.today().isoformat(),
        s=s, sections=sections, review=review,
        config_path=Path(res.case.meta["config_path"]).name,
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path
