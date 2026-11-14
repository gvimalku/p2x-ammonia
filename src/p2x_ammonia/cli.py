"""Command-line entry point: run one case from a config file."""
from __future__ import annotations

import argparse
from pathlib import Path

from .engine import run_from_config
from .results import build_summary, export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the P2X green-ammonia engine for one case.")
    parser.add_argument("config", help="Path to the case config YAML (e.g. config/default_fitzroy_hybrid.yaml)")
    parser.add_argument("--out", default=None, help="Output directory (default: outputs/<case_name>)")
    parser.add_argument("--reporting-year", type=int, default=1, help="Year to capture hourly traces for")
    args = parser.parse_args(argv)

    res = run_from_config(args.config, reporting_year=args.reporting_year)
    out_dir = Path(args.out) if args.out else Path("outputs") / res.case.case_name
    export(res, out_dir)
    s = build_summary(res)

    print(f"\nCase: {s['case']}")
    print("=" * 52)
    print(f"  Levelised Cost of Ammonia : {s['lc_nh3_aud_per_kg']:.4f}  A$/kg NH3")
    print(f"  Levelised Cost of Hydrogen: {s['lc_h2_aud_per_kg']:.4f}  A$/kg H2")
    print(f"  Total CAPEX               : {s['capex_total_aud']:,.0f}  A$")
    print(f"  Mean NH3 production        : {s['nh3_tpa_mean']:,.0f}  TPA")
    print(f"  Mean H2 production         : {s['h2_tpa_mean']:,.0f}  TPA")
    pp = s["power_plant_cf_year1"]
    el = s["electrolyser_cf_year1"]
    print(f"  Power-plant CF (yr1)       : {pp:.3f}" if pp is not None else "")
    print(f"  Electrolyser CF (yr1)      : {el:.3f}" if el is not None else "")
    print(f"  Stack replacements (yrs)   : {s['stack_replacement_years']}")
    print(f"  Battery replacements (yrs) : {s['battery_replacement_years']}")
    print("=" * 52)
    print(f"  Results written to: {out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
