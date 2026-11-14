#!/usr/bin/env python3
"""Extract data from the HySupply Ammonia Analysis Tool V1.0 workbook into durable files.

READ-ONLY against the workbook. Produces:
  config/default_fitzroy_hybrid.yaml   - the v1 input case (from S1. Inputs)
  config/constants.yaml                - A3 conversion factors + stoichiometry + SEC fit coeffs
  config/electrolyser_curve.csv        - A1 SEC-vs-load curve points
  data/weather/<location>.parquet      - S4 hourly solar+wind capacity factors for the case location
  data/golden/excel_cached_outputs.json- S2/S3 cached results (golden parity targets)
  data/raw_extract/s1_inputs_dump.csv  - full label/value/unit dump of S1 (provenance)

Run:
  source .venv/bin/activate
  python scripts/extract_excel_data.py
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import pandas as pd
import yaml
from openpyxl import load_workbook

# --- paths -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "HySupply Ammonia Analysis Tool V1.0.xlsm"
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
WEATHER_DIR = DATA_DIR / "weather"
GOLDEN_DIR = DATA_DIR / "golden"
RAW_DIR = DATA_DIR / "raw_extract"
for d in (CONFIG_DIR, WEATHER_DIR, GOLDEN_DIR, RAW_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- sheet names (exact, from the workbook) ----------------------------------
S1 = "S1. Inputs"
S2 = "S2. Results"
S3 = "S3. Levelised Cost Analysis"
S4 = "S4. Raw Data"
A1 = "A1.Electrolyser Parameters"
A3 = "A3. Conversion Factors"

WARNINGS: list[str] = []


def warn(msg: str) -> None:
    WARNINGS.append(msg)
    print(f"  [warn] {msg}")


def cell(ws, ref: str):
    try:
        return ws[ref].value
    except Exception as exc:  # noqa: BLE001
        warn(f"could not read {ws.title}!{ref}: {exc}")
        return None


# -----------------------------------------------------------------------------
# S1 input mapping.  key -> (cell, unit, review_flag)
# Values are read with data_only=True so user inputs AND cached [calc] cells resolve.
# `review=True` marks the parameters the brief wants Ashok to verify.
# -----------------------------------------------------------------------------
S1_MAP: dict[str, dict] = {
    "scope": {
        "location":                 ("B4",  "",      False),
        "power_plant_config":       ("B5",  "",      False),
        "balancing_technology":     ("B6",  "",      False),
    },
    "sizing": {
        "nh3_capacity_ktpa":        ("B12", "kTPA",      False),
        "electrolyser_oversizing":  ("B18", "fraction",  False),
        "hybrid_split_solar":       ("B22", "fraction",  False),
        "re_oversizing":            ("B24", "fraction",  False),
        "h2_storage_capacity_kg":   ("B26", "kg",        False),
    },
    "ammonia_plant": {
        "sec_nh3_kwh_per_kg":       ("B30", "kWhe/kgNH3", False),
        "sec_asu_kwh_per_kg_n2":    ("B31", "kWhe/kgN2",  False),
        "nh3_min_turndown":         ("B33", "fraction",   True),   # REVIEW: NH3 plant minimum load
        "nh3_storage_days":         ("B35", "days",       False),
        "capex_nh3_synthesis_per_t":("B38", "A$/tNH3",    False),
        "capex_nh3_storage_per_t":  ("B39", "A$/tNH3",    False),
        "capex_asu_per_t":          ("B40", "A$/tNH3",    False),
        "install_pct_nh3":          ("B41", "fraction",   False),
        "land_pct_nh3":             ("B42", "fraction",   False),
        "opex_nh3_synthesis_pct":   ("B44", "fraction/yr",False),
        "opex_nh3_storage_pct":     ("B45", "fraction/yr",False),
        "opex_asu_pct":             ("B46", "fraction/yr",False),
    },
    "electrolyser": {
        "electrolyser_type":        ("B49", "",           False),
        "sec_nominal_kwh_per_kg":   ("B51", "kWhe/kgH2",  True),   # REVIEW: electrolyser energy use
        "sec_vs_load":              ("B53", "",           False),
        "sec_correction_factor":    ("B54", "",           False),
        "elec_max_load":            ("B57", "fraction",   False),
        "elec_min_load":            ("B58", "fraction",   False),
        "stack_replacement_type":   ("B60", "",           False),
        "stack_lifetime_hours":     ("B61", "hours",      False),
        "stack_degradation_pct_yr": ("B62", "%/yr",       False),
        "water_l_per_kg":           ("B64", "L/kgH2",     False),
        "min_h2_storage_frac":      ("B65", "fraction",   False),
        "elec_ref_capacity_kw":     ("B68", "kW",         False),
        "elec_ref_cost_per_kw":     ("B69", "A$/kW",      False),
        "elec_scale_type":          ("B71", "",           False),
        "elec_scale_index":         ("B72", "",           False),
        "elec_cost_reduction_scale":("B74", "fraction",   False),
        "elec_ref_fold_increase":   ("B75", "",           False),
        "h2_storage_cost_per_kg":   ("B77", "A$/kg",      False),
        "elec_install_pct":         ("B79", "fraction",   False),
        "elec_land_pct":            ("B80", "fraction",   False),
        "opex_elec_pct":            ("B82", "fraction/yr",False),
        "opex_h2_storage_pct":      ("B83", "fraction/yr",False),
        "stack_replacement_cost_frac":("B84","fraction",  False),
        "water_cost_per_kl":        ("B85", "A$/kL",      False),
    },
    "power_plant": {
        "solar_degradation_pct_yr": ("B88", "%/yr",       False),
        "wind_degradation_pct_yr":  ("B89", "%/yr",       False),
        "excess_electricity":       ("B90", "",           False),
        "solar_ref_capacity_kw":    ("B94", "kW",         False),
        "solar_ref_cost_per_kw":    ("B95", "A$/kW",      False),
        "solar_scale_index":        ("B98", "",           False),
        "solar_install_pct":        ("B102","fraction",   False),
        "solar_land_pct":           ("B103","fraction",   False),
        "solar_opex_per_mw_yr":     ("B105","A$/MW/yr",   False),
        "wind_ref_capacity_kw":     ("B109","kW",         False),
        "wind_ref_cost_per_kw":     ("B110","A$/kW",      False),
        "wind_scale_index":         ("B113","",           False),
        "wind_install_pct":         ("B117","fraction",   False),
        "wind_land_pct":            ("B118","fraction",   False),
        "wind_opex_per_mw_yr":      ("B120","A$/MW/yr",   False),
    },
    "transmission": {
        "transmission_distance_km": ("B123","km",         True),   # REVIEW: transmission losses
        "transmission_loss_per_km": ("B124","fraction/km",True),   # REVIEW: transmission losses
        "transmission_equip_cost_per_km":("B126","A$/km", False),
        "transmission_install_pct": ("B127","fraction",   False),
        "transmission_land_pct":    ("B128","fraction",   False),
        "transmission_opex_pct":    ("B130","fraction/yr",False),
    },
    "battery": {
        "battery_power_mw":         ("B148","MW",         False),
        "battery_duration_h":       ("B149","hours",      False),
        "battery_rte":              ("B151","fraction",   False),
        "battery_min_soc":          ("B152","fraction",   False),
        "battery_max_soc":          ("B153","fraction",   False),
        "battery_lifetime_yr":      ("B154","years",      False),
        "battery_cost_per_kwh":     ("B156","A$/kWh",     False),
        "battery_install_pct":      ("B157","fraction",   False),
        "battery_land_pct":         ("B158","fraction",   False),
        "battery_opex_per_mw_yr":   ("B160","A$/MW/yr",   False),
        "battery_replacement_cost_frac":("B161","fraction",False),
    },
    "financing": {
        "plant_life_years":         ("B190","years",      False),
        "discount_rate":            ("B191","fraction/yr",False),
    },
}


def extract_s1_inputs(wb) -> tuple[dict, list[str]]:
    ws = wb[S1]
    out: dict = {}
    review: list[str] = []
    for section, params in S1_MAP.items():
        out[section] = {}
        for key, (ref, unit, is_review) in params.items():
            val = cell(ws, ref)
            if val is None:
                warn(f"S1!{ref} ({section}.{key}) is empty")
            out[section][key] = {"value": val, "unit": unit}
            if is_review:
                out[section][key]["review"] = True
                review.append(f"{section}.{key}")
    return out, review


def dump_s1_raw(wb) -> None:
    ws = wb[S1]
    path = RAW_DIR / "s1_inputs_dump.csv"
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row", "A_label", "B_value", "C_unit", "D_note", "E_ref"])
        for r in range(1, 192):
            row = [r]
            for col in ("A", "B", "C", "D", "E"):
                row.append(ws[f"{col}{r}"].value)
            if any(v not in (None, "") for v in row[1:]):
                w.writerow(row)
    print(f"  wrote {path.relative_to(ROOT)}")


def extract_constants(wb) -> dict:
    a3 = wb[A3]
    a1 = wb[A1]
    # Stoichiometry embedded in S1 formulas: per 34.181 units NH3 -> 6.047 H2 + 28.134 N2
    nh3_molar, h2_molar, n2_molar = 34.181, 6.047, 28.134
    consts = {
        "_source": "A3. Conversion Factors + A1 fit coeffs + S1 stoichiometry formulas",
        "lhv_h2_kwh_per_kg":       {"value": cell(a3, "B5"),  "unit": "kWh/kg"},
        "nm3_h2_to_kg":            {"value": cell(a3, "B6"),  "unit": "kgH2/Nm3"},
        "hydrogen_lhv_mj_per_kg":  {"value": cell(a3, "B9"),  "unit": "MJ/kg"},
        "ammonia_lhv_mj_per_kg":   {"value": cell(a3, "B10"), "unit": "MJ/kg"},
        "gw_to_mw":                {"value": cell(a3, "B16"), "unit": "MW/GW"},
        "mw_to_kw":                {"value": cell(a3, "B17"), "unit": "kW/MW"},
        "stoichiometry": {
            "_note": "Molar basis per 34.181 units NH3 -> 6.047 H2 + 28.134 N2 (from S1 sizing "
                     "formulas). Ratios computed from these, not rounded.",
            "nh3_molar_basis":  {"value": nh3_molar, "unit": "mass units"},
            "h2_molar_basis":   {"value": h2_molar, "unit": "mass units", "review": True},
            "n2_molar_basis":   {"value": n2_molar, "unit": "mass units", "review": True},
            "h2_kg_per_t_nh3":  {"value": round(1000 * h2_molar / nh3_molar, 4), "unit": "kgH2/tNH3 (derived)"},
            "n2_kg_per_t_nh3":  {"value": round(1000 * n2_molar / nh3_molar, 4), "unit": "kgN2/tNH3 (derived)"},
            "nh3_conversion_efficiency": {"value": 0.99, "unit": "fraction", "review": True},
        },
        "electrolyser_sec_fit": {
            "_note": "SEC = a*CF^2 + b*CF + c (used when sec_vs_load = Variable). From A1!F21:F23.",
            "a": {"value": cell(a1, "F21")},
            "b": {"value": cell(a1, "F22")},
            "c": {"value": cell(a1, "F23")},
        },
    }
    return consts


def extract_electrolyser_curve(wb) -> None:
    ws = wb[A1]
    path = CONFIG_DIR / "electrolyser_curve.csv"
    rows = []
    for r in range(7, 15):  # A1 rows 7..14
        load = cell(ws, f"B{r}")
        pct_nominal = cell(ws, f"C{r}")
        sec = cell(ws, f"D{r}")
        kg_per_kwh = cell(ws, f"E{r}")
        if load is None:
            continue
        rows.append([load, pct_nominal, sec, kg_per_kwh])
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["load_fraction", "pct_of_nominal_sec", "sec_kwh_per_kg", "kg_h2_per_kwh"])
        w.writerows(rows)
    print(f"  wrote {path.relative_to(ROOT)} ({len(rows)} points)")


def excel_serial_to_datetime(serial: float):
    if serial is None:
        return None
    try:
        return pd.Timestamp("1899-12-30") + pd.to_timedelta(float(serial), unit="D")
    except Exception:  # noqa: BLE001
        return None


def col_letter_range(start: str, end: str) -> list[int]:
    from openpyxl.utils import column_index_from_string
    return list(range(column_index_from_string(start), column_index_from_string(end) + 1))


def extract_weather(location: str) -> dict:
    """Read S4 solar+wind hourly capacity factors for one location (by its text label)."""
    print(f"  reading S4 weather for location: {location!r} (this reads ~8760 rows)...")
    wb_ro = load_workbook(WORKBOOK, read_only=True, data_only=True)
    ws = wb_ro[S4]
    # Pull everything once; S4 is rows 1..8769, cols A..CK.
    grid = list(ws.iter_rows(min_row=1, max_row=8769, values_only=True))
    wb_ro.close()

    header_loc = grid[5]  # row 6 (1-based) = plain-English location text
    solar_cols = [i - 1 for i in col_letter_range("C", "AR")]   # 0-based indices
    wind_cols = [i - 1 for i in col_letter_range("AV", "CK")]

    def find_col(cols: list[int], label: str) -> int | None:
        target = str(label).strip().lower()
        for i in cols:
            v = header_loc[i] if i < len(header_loc) else None
            if v is not None and str(v).strip().lower() == target:
                return i
        return None

    si = find_col(solar_cols, location)
    wi = find_col(wind_cols, location)
    if si is None:
        warn(f"solar column for {location!r} not found in S4 row 6")
    if wi is None:
        warn(f"wind column for {location!r} not found in S4 row 6")

    records = []
    for hour_idx, excel_row in enumerate(range(10, 8770)):  # data rows 10..8769
        g = grid[excel_row - 1]
        serial = g[1] if len(g) > 1 else None  # column B
        solar = g[si] if (si is not None and si < len(g)) else None
        wind = g[wi] if (wi is not None and wi < len(g)) else None
        dt = excel_serial_to_datetime(serial)
        records.append({
            "hour": hour_idx,
            "datetime": dt,
            "month": dt.month if dt is not None else None,
            "solar_cf": solar,
            "wind_cf": wind,
        })

    df = pd.DataFrame.from_records(records)
    slug = location.split(",")[0].strip().lower().replace(" ", "_")
    out = WEATHER_DIR / f"{slug}.parquet"
    df.to_parquet(out, index=False)
    solar_mean = df["solar_cf"].astype("float64").mean() if si is not None else float("nan")
    wind_mean = df["wind_cf"].astype("float64").mean() if wi is not None else float("nan")
    print(f"  wrote {out.relative_to(ROOT)} ({len(df)} hours); "
          f"annual mean CF solar={solar_mean:.4f} wind={wind_mean:.4f}")
    return {"file": str(out.relative_to(ROOT)), "hours": len(df),
            "annual_mean_solar_cf": None if math.isnan(solar_mean) else round(solar_mean, 6),
            "annual_mean_wind_cf": None if math.isnan(wind_mean) else round(wind_mean, 6)}


def extract_golden(wb) -> dict:
    s2 = wb[S2]
    s3 = wb[S3]
    golden: dict = {
        "_note": "Cached values from the workbook's last calculation. Parity targets for the Python port.",
        "lcoa": {
            "lc_h2_s3_AE129": cell(s3, "AE129"),
            "lc_nh3_s3_AE130": cell(s3, "AE130"),
            "lc_h2_s2_F32": cell(s2, "F32"),
            "lc_nh3_s2_F33": cell(s2, "F33"),
        },
        "s2_results_summary": [],
        "s3_annual_profile": [],
    }
    # S2 key results summary rows 17..33: label from first non-empty of A..E, value in F.
    for r in range(17, 34):
        label = None
        for col in ("A", "B", "C", "D", "E"):
            v = cell(s2, f"{col}{r}")
            if v not in (None, ""):
                label = v
                break
        val = cell(s2, f"F{r}")
        if label is not None or val is not None:
            golden["s2_results_summary"].append({"row": r, "label": label, "value": val})
    # S3 annual profile rows 9..33 (years 1..25): F total energy, G H2, H N2, I NH3, J power, O elec hrs.
    for r in range(9, 34):
        rec = {
            "row": r,
            "total_energy_gen": cell(s3, f"F{r}"),
            "h2_tpa": cell(s3, f"G{r}"),
            "n2_tpa": cell(s3, f"H{r}"),
            "nh3_tpa": cell(s3, f"I{r}"),
        }
        if any(v is not None for v in (rec["h2_tpa"], rec["nh3_tpa"])):
            golden["s3_annual_profile"].append(rec)
    return golden


def write_yaml(path: Path, data: dict, header: str) -> None:
    with path.open("w") as fh:
        fh.write(f"# {header}\n")
        fh.write("# Generated by scripts/extract_excel_data.py (read-only from the workbook).\n")
        fh.write("# Edit values here; re-running the extractor overwrites this file.\n\n")
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False, allow_unicode=True)
    print(f"  wrote {path.relative_to(ROOT)}")


def main() -> None:
    if not WORKBOOK.exists():
        raise SystemExit(f"Workbook not found: {WORKBOOK}")
    print(f"Extracting from: {WORKBOOK.name}")

    print("\n[1/6] S1 inputs -> config/default_fitzroy_hybrid.yaml")
    wb = load_workbook(WORKBOOK, data_only=True, keep_vba=True)
    inputs, review = extract_s1_inputs(wb)
    location = inputs["scope"]["location"]["value"]

    print("\n[2/6] S1 raw dump -> data/raw_extract/s1_inputs_dump.csv")
    dump_s1_raw(wb)

    print("\n[3/6] A3 constants + A1 fit -> config/constants.yaml")
    constants = extract_constants(wb)
    write_yaml(CONFIG_DIR / "constants.yaml", constants, "Conversion factors, stoichiometry, SEC fit coefficients")

    print("\n[4/6] A1 electrolyser curve -> config/electrolyser_curve.csv")
    extract_electrolyser_curve(wb)

    print("\n[6/6] S2/S3 golden outputs -> data/golden/excel_cached_outputs.json")
    golden = extract_golden(wb)
    (GOLDEN_DIR / "excel_cached_outputs.json").write_text(json.dumps(golden, indent=2, default=str))
    print(f"  wrote {(GOLDEN_DIR / 'excel_cached_outputs.json').relative_to(ROOT)}")
    wb.close()

    print("\n[5/6] S4 weather -> data/weather/")
    weather_meta = extract_weather(location) if location else {}

    # Assemble the case config now that we know the weather file + review list.
    case = {
        "case_name": "default_fitzroy_hybrid",
        "description": "HySupply V1.0 default scenario: Fitzroy QLD, Standalone Hybrid + Battery, 1000 kTPA.",
        "weather_file": weather_meta.get("file"),
        "inputs": inputs,
        "_review_required": {
            "_note": "Parameters flagged for Ashok to verify before production use.",
            "parameters": review + [
                "constants.stoichiometry.h2_kg_per_t_nh3",
                "constants.stoichiometry.n2_kg_per_t_nh3",
                "constants.stoichiometry.nh3_conversion_efficiency",
            ],
        },
    }
    write_yaml(CONFIG_DIR / "default_fitzroy_hybrid.yaml", case,
               "Default input case (v1) extracted from S1. Inputs")

    print("\nDone.")
    if WARNINGS:
        print(f"\n{len(WARNINGS)} warning(s) — review the mappings above.")
    else:
        print("\nNo warnings. All mapped cells resolved.")


if __name__ == "__main__":
    main()
