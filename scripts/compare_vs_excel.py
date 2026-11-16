"""Side-by-side parity report: Python engine vs the workbook's cached outputs.

Reads data/golden/excel_cached_outputs.json (values pulled straight from the .xlsm
cells) and the live engine run, and prints a table of Excel vs Python with the %
difference for every headline number. This is the human-readable version of
tests/test_parity.py.

Run:  PYTHONPATH=src python scripts/compare_vs_excel.py
"""
from __future__ import annotations

import json
from pathlib import Path

from p2x_ammonia.engine import run_from_config

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / "data/golden/excel_cached_outputs.json").read_text())


def pct(excel: float, py: float) -> str:
    if excel == 0:
        return "n/a"
    d = (py - excel) / excel * 100
    return f"{d:+.4f}%"


def row(label: str, cell: str, excel, py):
    e = "" if excel is None else f"{excel:,.4f}"
    p = "" if py is None else f"{py:,.4f}"
    diff = pct(excel, py) if (excel is not None and py is not None) else ""
    print(f"  {label:<48} {cell:<14} {e:>18} {p:>18}  {diff:>11}")


def main() -> None:
    res = run_from_config("config/default_fitzroy_hybrid.yaml")
    a = res.annual
    mean = lambda k: sum(x[k] for x in a) / len(a)

    print("\n" + "=" * 112)
    print("  PARITY REPORT  -  Python engine  vs  HySupply Excel (cached cell values)")
    print("=" * 112)
    print(f"  {'Metric':<48} {'Excel cell':<14} {'Excel':>18} {'Python':>18}  {'Diff':>11}")
    print("  " + "-" * 108)

    # --- Headline LCOA (Sheet S3 / S2) ------------------------------------
    print("  LEVELISED COST  (Sheet 'S3. Economics' / 'S2. Results')")
    row("Levelised Cost of Ammonia  (A$/kg NH3)", "S3!AE130",
        GOLDEN["lcoa"]["lc_nh3_s3_AE130"], res.lcoa.lc_nh3)
    row("Levelised Cost of Hydrogen (A$/kg H2)", "S3!AE129",
        GOLDEN["lcoa"]["lc_h2_s3_AE129"], res.lcoa.lc_h2)

    # --- Plant-life average production (Sheet S2, col F) ------------------
    # NOTE: S2's F28-30 are 25-year AVERAGES, so compare against the Python mean,
    # not year 1. (S2's CF and battery rows read the workbook's last-calculated
    # working year, so they are not plant-life aggregates and are omitted here;
    # the rigorous year-by-year check is the S3 profile below.)
    s2 = {r["row"]: r for r in GOLDEN["s2_results_summary"]}
    print("\n  PLANT-LIFE AVERAGE PRODUCTION  (Sheet 'S2. Results', col F = 25-yr mean)")
    row("Hydrogen Production (mean TPA)", "S2!F28", s2[28]["value"], mean("h2_tpa"))
    row("Nitrogen Production (mean TPA)", "S2!F29", s2[29]["value"], mean("n2_tpa"))
    row("Ammonia Production (mean TPA)", "S2!F30", s2[30]["value"], mean("nh3_tpa"))

    # --- 25-year production profile (Sheet S3, rows 9-33) -----------------
    print("\n  25-YEAR PRODUCTION PROFILE  (Sheet 'S3. Economics', rows 9-33)")
    print(f"  {'Year':<6} {'Excel NH3 TPA':>16} {'Python NH3 TPA':>16} {'Diff':>10}"
          f"   {'Excel H2 TPA':>14} {'Python H2 TPA':>14} {'Diff':>10}")
    for prof in GOLDEN["s3_annual_profile"]:
        yr = prof["row"] - 8
        got = next(a for a in res.annual if a["year"] == yr)
        print(f"  {yr:<6} {prof['nh3_tpa']:>16,.2f} {got['nh3_tpa']:>16,.2f} "
              f"{pct(prof['nh3_tpa'], got['nh3_tpa']):>10}   "
              f"{prof['h2_tpa']:>14,.2f} {got['h2_tpa']:>14,.2f} "
              f"{pct(prof['h2_tpa'], got['h2_tpa']):>10}")

    print("=" * 112)
    print("  All % diffs are Python relative to Excel. test_parity.py asserts these stay")
    print("  within tolerance (LCOA <=0.1%, annual production <=0.05%).\n")


if __name__ == "__main__":
    main()
