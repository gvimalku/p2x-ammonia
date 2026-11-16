#!/usr/bin/env python3
"""Extract hourly solar+wind capacity-factor traces for ALL 42 S4 sites in one pass.

READ-ONLY against the workbook. Writes one `data/weather/<slug>.parquet` per site (same
schema as scripts/extract_excel_data.py's single-site output) plus a `data/weather/sites.json`
manifest that the Streamlit app uses to build its site dropdown and map label -> trace file.

This reuses the existing extractor's helpers and reads the 18 MB workbook's S4 grid ONCE,
slicing all 84 generation columns, rather than re-opening it per site.

Run:
  source .venv/bin/activate
  python scripts/extract_all_sites.py
"""
from __future__ import annotations

import json
import math

import pandas as pd
from openpyxl import load_workbook

from extract_excel_data import (
    S4,
    WEATHER_DIR,
    ROOT,
    col_letter_range,
    excel_serial_to_datetime,
)
from extract_excel_data import WORKBOOK


def slugify(label: str) -> str:
    """Same rule as extract_weather(): first comma-part, lowercased, spaces -> underscores."""
    return label.split(",")[0].strip().lower().replace(" ", "_")


def main() -> None:
    print(f"reading {WORKBOOK.name} (S4, ~8760 rows, all 42 sites)...")
    wb = load_workbook(WORKBOOK, read_only=True, data_only=True)
    ws = wb[S4]
    grid = list(ws.iter_rows(min_row=1, max_row=8769, values_only=True))
    wb.close()

    header = grid[5]  # row 6 = plain-English location labels
    solar_cols = [i - 1 for i in col_letter_range("C", "AR")]   # 0-based
    wind_cols = [i - 1 for i in col_letter_range("AV", "CK")]

    def label_at(i: int):
        v = header[i] if i < len(header) else None
        return str(v).strip() if v not in (None, "") else None

    # Map each site label -> (solar_col, wind_col).
    wind_by_label = {label_at(i): i for i in wind_cols if label_at(i)}
    sites: list[tuple[str, int, int]] = []
    for si in solar_cols:
        lab = label_at(si)
        if lab and lab in wind_by_label:
            sites.append((lab, si, wind_by_label[lab]))

    print(f"found {len(sites)} sites with both solar and wind columns")

    # Pre-compute the datetime/month index once (shared across all sites).
    serials = [grid[excel_row - 1][1] if len(grid[excel_row - 1]) > 1 else None
               for excel_row in range(10, 8770)]
    dts = [excel_serial_to_datetime(s) for s in serials]
    months = [dt.month if dt is not None else None for dt in dts]

    manifest = []
    for lab, si, wi in sites:
        solar = [grid[excel_row - 1][si] for excel_row in range(10, 8770)]
        wind = [grid[excel_row - 1][wi] for excel_row in range(10, 8770)]
        df = pd.DataFrame({
            "hour": range(len(solar)),
            "datetime": dts,
            "month": months,
            "solar_cf": solar,
            "wind_cf": wind,
        })
        s_mean = df["solar_cf"].astype("float64").mean()
        w_mean = df["wind_cf"].astype("float64").mean()
        if math.isnan(s_mean) or math.isnan(w_mean):
            print(f"  {lab:<22} -> SKIPPED (empty/placeholder column, no CF data)")
            continue
        slug = slugify(lab)
        out = WEATHER_DIR / f"{slug}.parquet"
        df.to_parquet(out, index=False)
        manifest.append({
            "label": lab,
            "slug": slug,
            "file": str(out.relative_to(ROOT)),
            "annual_mean_solar_cf": round(float(s_mean), 6),
            "annual_mean_wind_cf": round(float(w_mean), 6),
        })
        print(f"  {lab:<22} -> {out.name:<22} solar={s_mean:.4f} wind={w_mean:.4f}")

    manifest.sort(key=lambda m: m["label"])
    (WEATHER_DIR / "sites.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nwrote {len(manifest)} traces + data/weather/sites.json")


if __name__ == "__main__":
    main()
