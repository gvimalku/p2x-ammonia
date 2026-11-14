"""Orchestrator: run one case end-to-end.

Mirrors the VBA Calc_Button year sweep: for each plant-year it applies solar/wind + stack
degradation, runs the 8,760-hour dispatch, determines stack replacement from cumulative
operating hours (N resets to 0 the year the integer part of stack-life-consumed increments),
then feeds annual production into the DCF/LCOA. `run_case(case)` is pure and is the seam a
future multi-iteration / sizing-sweep layer maps over.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Case, load_case
from .dispatch import YearResult, simulate_year
from .economics import LCOAResult, compute_financials
from .sizing import compute_sizing
from .weather import load_weather


@dataclass
class CaseResult:
    case: Case
    annual: list[dict]                       # per-year production + YearResult
    lcoa: LCOAResult
    stack_replace_years: set[int]
    battery_replace_years: set[int]
    hourly: dict | None = None               # traces for the reporting year
    summary: dict = field(default_factory=dict)


def run_case(case: Case, solar_cf: np.ndarray, wind_cf: np.ndarray,
             reporting_year: int = 1) -> CaseResult:
    r = case.raw
    life = int(r["plant_life_years"])
    deg_rate = r["stack_degradation_pct_yr"]
    stack_lifetime = r["stack_lifetime_hours"]
    batt_lifetime = int(r["battery_lifetime_yr"])

    cum_hours = 0.0
    last_reset = 0
    stack_replace_years: set[int] = set()
    annual: list[dict] = []
    hourly = None

    for y in range(1, life + 1):
        capture = y == reporting_year
        exponent = y - last_reset
        n_prov = 1 - 1 / (1 + deg_rate) ** exponent
        res = simulate_year(case, solar_cf, wind_cf, y, n_prov, capture_hourly=capture)

        q_prev = math.floor(cum_hours / stack_lifetime)
        q_now = math.floor((cum_hours + res.op_hours) / stack_lifetime)
        if q_now - q_prev == 1:
            # replacement year: fresh stack, no degradation this year
            res = simulate_year(case, solar_cf, wind_cf, y, 0.0, capture_hourly=capture)
            last_reset = y
            stack_replace_years.add(y)

        cum_hours += res.op_hours
        if capture:
            hourly = res.hourly
        annual.append({
            "year": y,
            "re_mwh": res.re_mwh,
            "h2_tpa": res.h2_kg / 1000,
            "n2_tpa": res.n2_kg / 1000,
            "nh3_tpa": res.nh3_kg / 1000,
            "op_hours": res.op_hours,
            "power_allocated_mwh": res.power_allocated_mwh,
            "excess_mwh": res.excess_mwh,
            "batt_charge_mwh": res.batt_charge_mwh,
        })

    battery_replace_years = {y for y in range(1, life + 1) if batt_lifetime > 0 and y % batt_lifetime == 0}

    lcoa = compute_financials(case, annual, stack_replace_years, battery_replace_years)

    summary = {
        "lc_nh3": lcoa.lc_nh3,
        "lc_h2": lcoa.lc_h2,
        "capex_total": lcoa.capex_total,
        "nh3_tpa_year1": annual[0]["nh3_tpa"],
        "h2_tpa_year1": annual[0]["h2_tpa"],
        "op_hours_year1": annual[0]["op_hours"],
        "avg_elec_cf_year1": (annual[0]["h2_tpa"]),  # placeholder; results.py computes richer stats
    }

    return CaseResult(
        case=case, annual=annual, lcoa=lcoa,
        stack_replace_years=stack_replace_years, battery_replace_years=battery_replace_years,
        hourly=hourly, summary=summary,
    )


def run_from_config(config_path: str | Path, reporting_year: int = 1) -> CaseResult:
    case = compute_sizing(load_case(config_path))
    solar, wind, _ = load_weather(case.weather_file)
    return run_case(case, solar, wind, reporting_year=reporting_year)
