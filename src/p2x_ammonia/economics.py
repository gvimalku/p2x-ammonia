"""CAPEX/OPEX ledger, 25-year DCF and LCOA — faithful port of 'S3. Levelised Cost Analysis'.

Keeps direct equipment CAPEX separate from installation + land indirects (accumulated into a
single 'Indirect Costs' line, matching S3!L48). LCOA = total discounted lifetime cost divided
by total discounted lifetime output; CAPEX booked undiscounted at year 0; OPEX/replacements
discounted over years 1..Plant_Life at the real discount rate. No debt/tax/depreciation (as in V1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import Case
from .sizing import balancing_type


def scaled_purchase_cost(profile: str, ref_cost: float, ref_cap_kw: float, cap_kw: float,
                         scale_index: float, cost_reduction: float, ref_fold: float) -> float:
    """Port of the 'Scaled Purchase Cost' cells (S3 B17/B33/B115)."""
    if cap_kw <= 0:
        return 0.0
    if str(profile).strip() == "Self Defined":
        fold = math.log(cap_kw / ref_cap_kw, ref_fold) if ref_fold > 0 else 0.0
        reduction = 1 - (1 - cost_reduction) ** fold
        return ref_cost * (1 - reduction)
    # "Scale Index"
    return ((ref_cost * ref_cap_kw) * (cap_kw / ref_cap_kw) ** scale_index) / cap_kw


@dataclass
class CostLedger:
    capex: dict[str, float] = field(default_factory=dict)       # year-0 direct CAPEX by component
    indirect: dict[str, float] = field(default_factory=dict)    # installation+land by component
    opex_fixed: dict[str, float] = field(default_factory=dict)  # constant annual OPEX by component
    stack_replacement_cost: float = 0.0
    battery_replacement_cost: float = 0.0
    water_unit: float = 0.0        # A$ per tonne-H2-per-year (multiply by H2 TPA)
    extras: dict[str, float] = field(default_factory=dict)


def build_ledger(case: Case) -> CostLedger:
    r = case.raw
    d = case.derived
    led = CostLedger()
    gen = d["GenType"]
    btype = balancing_type(r["balancing_technology"])

    # ---------------- Power plant (solar / wind / hybrid) ----------------
    solar_cost = scaled_purchase_cost(
        "Scale Index" if r.get("solar_scale_index") is not None else "Scale Index",
        r["solar_ref_cost_per_kw"], r["solar_ref_capacity_kw"], d["SolarCap"] * 1000,
        r["solar_scale_index"], 0.0, 0.0)
    wind_cost = scaled_purchase_cost(
        "Scale Index", r["wind_ref_cost_per_kw"], r["wind_ref_capacity_kw"], d["WindCap"] * 1000,
        r["wind_scale_index"], 0.0, 0.0)
    solar_capex = solar_cost * d["SolarCap"] * 1000
    wind_capex = wind_cost * d["WindCap"] * 1000
    solar_indirect = r["solar_install_pct"] * (solar_cost * 1000) + r["solar_land_pct"] * solar_capex
    wind_indirect = r["wind_install_pct"] * wind_capex + r["wind_land_pct"] * wind_capex
    solar_opex = d["SolarCap"] * r["solar_opex_per_mw_yr"]
    wind_opex = d["WindCap"] * r["wind_opex_per_mw_yr"]

    if gen == "Hybrid":
        led.capex["power_plant"] = solar_capex + wind_capex
        led.indirect["power_plant"] = solar_indirect + wind_indirect
        led.opex_fixed["power_plant"] = solar_opex + wind_opex
    elif gen == "Solar":
        led.capex["power_plant"] = solar_capex
        led.indirect["power_plant"] = solar_indirect
        led.opex_fixed["power_plant"] = solar_opex
    elif gen == "Wind":
        led.capex["power_plant"] = wind_capex
        led.indirect["power_plant"] = wind_indirect
        led.opex_fixed["power_plant"] = wind_opex
    else:
        led.capex["power_plant"] = 0.0
        led.indirect["power_plant"] = 0.0
        led.opex_fixed["power_plant"] = 0.0

    # ---------------- Transmission ----------------
    trans_capex = r["transmission_equip_cost_per_km"] * r["transmission_distance_km"]
    led.capex["transmission"] = trans_capex
    led.opex_fixed["transmission"] = trans_capex * r["transmission_opex_pct"]
    # NB: S3!L48 does NOT include transmission indirect — matched intentionally (see docs/excel_bugs.md)

    # ---------------- Balancing tech (battery) ----------------
    if btype == "Battery":
        batt_cap_mwh = r["battery_duration_h"] * r["battery_power_mw"]
        batt_capex = (batt_cap_mwh * r["battery_cost_per_kwh"] * 1000) + (r["battery_power_mw"] * 1000)
        led.capex["battery"] = batt_capex
        led.indirect["battery"] = (r["battery_cost_per_kwh"] * batt_cap_mwh * 1000) * r["battery_install_pct"] \
            + (r["battery_cost_per_kwh"] * batt_cap_mwh * 1000) * r["battery_land_pct"]
        led.opex_fixed["battery"] = r["battery_opex_per_mw_yr"] * r["battery_power_mw"]
        led.battery_replacement_cost = r["battery_replacement_cost_frac"] * batt_capex
    else:
        led.capex["battery"] = 0.0
        led.indirect["battery"] = 0.0
        led.opex_fixed["battery"] = 0.0

    # ---------------- Electrolyser ----------------
    elec_cost = scaled_purchase_cost(
        r["elec_scale_type"], r["elec_ref_cost_per_kw"], r["elec_ref_capacity_kw"],
        d["elecCapacity"] * 1000, r["elec_scale_index"], r["elec_cost_reduction_scale"],
        r["elec_ref_fold_increase"])
    elec_capex = elec_cost * d["elecCapacity"] * 1000
    led.capex["electrolyser"] = elec_capex
    led.indirect["electrolyser"] = r["elec_install_pct"] * elec_capex + r["elec_land_pct"] * elec_capex
    led.opex_fixed["electrolyser"] = r["opex_elec_pct"] * elec_capex
    led.stack_replacement_cost = r["stack_replacement_cost_frac"] * elec_capex

    # ---------------- H2 storage ----------------
    h2_capex = r["h2_storage_capacity_kg"] * r["h2_storage_cost_per_kg"]
    led.capex["h2_storage"] = h2_capex
    led.indirect["h2_storage"] = r["elec_install_pct"] * h2_capex   # S3!B128 uses elec install %
    led.opex_fixed["h2_storage"] = r["opex_h2_storage_pct"] * h2_capex

    # ---------------- Ammonia + ASU ----------------
    nh3_ktpa = d["NH3Cap"] * 8760 / 1_000_000
    nh3_storage_cap = r["nh3_storage_days"] * (nh3_ktpa / 365 * 1000)        # tonnes
    asu_cap_tpd = d["ASU_Cap"] * 365 / 1000                                  # S3!B138 (kTPA basis)
    ammonia_capex = (nh3_ktpa * 1000 * r["capex_nh3_synthesis_per_t"]) + (nh3_storage_cap * r["capex_nh3_storage_per_t"])
    asu_capex = asu_cap_tpd * 1000 * r["capex_asu_per_t"]
    led.capex["ammonia"] = ammonia_capex
    led.capex["asu"] = asu_capex
    led.indirect["ammonia_asu"] = r["install_pct_nh3"] * (ammonia_capex + asu_capex) \
        + r["land_pct_nh3"] * (ammonia_capex + asu_capex)
    led.opex_fixed["ammonia"] = r["opex_nh3_synthesis_pct"] * (nh3_ktpa * 1000 * r["capex_nh3_synthesis_per_t"]) \
        + r["opex_nh3_storage_pct"] * (nh3_storage_cap * r["capex_nh3_storage_per_t"])
    led.opex_fixed["asu"] = r["opex_asu_pct"] * asu_capex

    # ---------------- Water (variable, per tonne-H2/yr) ----------------
    led.water_unit = 1000 * r["water_l_per_kg"] * r["water_cost_per_kl"] / 1000

    # ---------------- Additional ----------------
    led.extras["additional_upfront"] = r.get("additional_upfront_cost") or 0.0
    led.extras["additional_annual"] = r.get("additional_annual_cost") or 0.0

    return led


@dataclass
class LCOAResult:
    lc_nh3: float
    lc_h2: float
    total_discounted_cost: float
    discounted_h2_kg: float
    discounted_nh3_kg: float
    capex_total: float
    cost_breakdown_nh3: dict[str, float]      # A$/kg NH3 by cost line
    ledger: CostLedger
    schedule: list[dict] = field(default_factory=list)   # per-year undiscounted rows


def compute_financials(case: Case, annual: list[dict],
                       stack_replace_years: set[int],
                       battery_replace_years: set[int]) -> LCOAResult:
    """annual: list of per-year dicts {year, h2_tpa, nh3_tpa}. years 1..Plant_Life."""
    r = case.raw
    led = build_ledger(case)
    disc = r["discount_rate"]
    life = int(r["plant_life_years"])

    capex_lines = {
        "power_plant": led.capex["power_plant"],
        "transmission": led.capex["transmission"],
        "battery": led.capex["battery"],
        "electrolyser": led.capex["electrolyser"],
        "h2_storage": led.capex["h2_storage"],
        "indirect": sum(led.indirect.values()),
        "ammonia": led.capex["ammonia"],
        "asu": led.capex["asu"],
        "additional": led.extras["additional_upfront"],
    }
    capex_total = sum(capex_lines.values())

    opex_const = {
        "power_plant_opex": led.opex_fixed["power_plant"],
        "transmission_opex": led.opex_fixed["transmission"],
        "battery_opex": led.opex_fixed["battery"],
        "electrolyser_opex": led.opex_fixed["electrolyser"],
        "h2_storage_opex": led.opex_fixed["h2_storage"],
        "ammonia_opex": led.opex_fixed["ammonia"],
        "asu_opex": led.opex_fixed["asu"],
        "additional_annual": led.extras["additional_annual"],
    }

    # discounted totals by cost line (CAPEX at year 0, everything else over years 1..life)
    disc_cost: dict[str, float] = {f"capex_{k}": v for k, v in capex_lines.items()}  # year0, factor 1
    for k in opex_const:
        disc_cost[k] = 0.0
    disc_cost["water"] = 0.0
    disc_cost["stack_replacement"] = 0.0
    disc_cost["battery_replacement"] = 0.0

    disc_h2 = 0.0
    disc_nh3 = 0.0
    schedule: list[dict] = []
    for rec in annual:
        y = rec["year"]
        if y > life:
            continue
        df = (1 + disc) ** y
        h2_kg = rec["h2_tpa"] * 1000
        nh3_kg = rec["nh3_tpa"] * 1000
        disc_h2 += h2_kg / df
        disc_nh3 += nh3_kg / df

        water = led.water_unit * rec["h2_tpa"]
        stack = led.stack_replacement_cost if y in stack_replace_years else 0.0
        battery = led.battery_replacement_cost if y in battery_replace_years else 0.0

        for k, v in opex_const.items():
            disc_cost[k] += v / df
        disc_cost["water"] += water / df
        disc_cost["stack_replacement"] += stack / df
        disc_cost["battery_replacement"] += battery / df

        row = {"year": y, **opex_const, "water": water,
               "stack_replacement": stack, "battery_replacement": battery,
               "h2_tpa": rec["h2_tpa"], "nh3_tpa": rec["nh3_tpa"]}
        row["total"] = sum(opex_const.values()) + water + stack + battery
        schedule.append(row)

    total_disc_cost = sum(disc_cost.values())
    lc_h2 = total_disc_cost / disc_h2
    lc_nh3 = total_disc_cost / disc_nh3

    breakdown_nh3 = {k: v / disc_nh3 for k, v in disc_cost.items()}

    return LCOAResult(
        lc_nh3=lc_nh3, lc_h2=lc_h2, total_discounted_cost=total_disc_cost,
        discounted_h2_kg=disc_h2, discounted_nh3_kg=disc_nh3,
        capex_total=capex_total, cost_breakdown_nh3=breakdown_nh3, ledger=led, schedule=schedule,
    )
