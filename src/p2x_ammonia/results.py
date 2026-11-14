"""Aggregate results (S2-style summary) and export them to CSV/JSON."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import CaseResult


def build_summary(res: CaseResult) -> dict:
    a = res.annual
    hourly = res.hourly or {}

    def hmean(key):
        return float(np.mean(hourly[key])) if key in hourly else None

    pp_cf = hmean("C")                       # year-1 power-plant capacity factor
    elec_cf = hmean("AE")
    nh3_load = hmean("AS")

    summary = {
        "case": res.case.case_name,
        "lc_nh3_aud_per_kg": res.lcoa.lc_nh3,
        "lc_h2_aud_per_kg": res.lcoa.lc_h2,
        "capex_total_aud": res.lcoa.capex_total,
        "discounted_nh3_kg": res.lcoa.discounted_nh3_kg,
        "discounted_h2_kg": res.lcoa.discounted_h2_kg,
        "nh3_tpa_mean": float(np.mean([x["nh3_tpa"] for x in a])),
        "h2_tpa_mean": float(np.mean([x["h2_tpa"] for x in a])),
        "n2_tpa_mean": float(np.mean([x["n2_tpa"] for x in a])),
        "op_hours_year1": a[0]["op_hours"],
        "power_plant_cf_year1": pp_cf,
        "electrolyser_cf_year1": elec_cf,
        "nh3_plant_load_year1": nh3_load,
        "stack_replacement_years": sorted(res.stack_replace_years),
        "battery_replacement_years": sorted(res.battery_replace_years),
    }
    return summary


def export(res: CaseResult, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # summary
    summary = build_summary(res)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    # annual production + undiscounted cost schedule
    pd.DataFrame(res.annual).to_csv(out_dir / "annual_production.csv", index=False)
    pd.DataFrame(res.lcoa.schedule).to_csv(out_dir / "cost_schedule.csv", index=False)

    # CAPEX ledger
    led = res.lcoa.ledger
    capex_rows = [{"component": k, "direct_capex_aud": v,
                   "indirect_aud": led.indirect.get(k, 0.0),
                   "opex_fixed_aud_yr": led.opex_fixed.get(k, 0.0)}
                  for k, v in led.capex.items()]
    pd.DataFrame(capex_rows).to_csv(out_dir / "capex_ledger.csv", index=False)

    # LCOA cost breakdown (A$/kg NH3 by line)
    bd = pd.DataFrame([{"cost_line": k, "aud_per_kg_nh3": v}
                       for k, v in res.lcoa.cost_breakdown_nh3.items()])
    bd = bd.sort_values("aud_per_kg_nh3", ascending=False)
    bd.to_csv(out_dir / "lcoa_breakdown.csv", index=False)

    return out_dir
