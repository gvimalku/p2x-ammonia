# P2X Green-Ammonia Techno-Economic Engine

A Python one-case engine that ports and extends the UNSW **HySupply Ammonia Analysis Tool V1.0**
(Excel/VBA). Given one input configuration it runs an 8,760-hour dispatch simulation, a 25-year
discounted cash flow, and produces a levelised cost of ammonia (LCOA) plus a chart report.

The engine is built so a later layer can drive multiple iterations / sizing sweeps / optimisation
over the same pure `run_case()` function; v1 ships one validated case end-to-end.

## Status

Workstream 1 — project scaffold and Excel data extraction. See
`/Users/vgkumar/.claude/plans/the-following-describes-what-delightful-dragonfly.md` for the full plan.

## Layout

```
config/    input config (YAML), constants, electrolyser curve
data/      extracted weather traces + golden parity targets (from the workbook)
src/p2x_ammonia/   the engine package
scripts/   extract_excel_data.py (workbook -> data/), make_fixed_workbook.py
tests/     parity + unit tests
docs/      bug report, cost scope, assumptions-for-review
outputs/   run artifacts (gitignored)
```

## Quickstart (once built)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python scripts/extract_excel_data.py          # workbook -> data/ + config/
p2x-run config/default_fitzroy_hybrid.yaml     # -> outputs/report.html
pytest                                         # parity + unit tests
```

## Source model

`HySupply Ammonia Analysis Tool V1.0.xlsm` — UNSW, 2022, MIT-licensed. Australia–Germany HySupply
study. The workbook is the source of truth; `scripts/extract_excel_data.py` regenerates all derived
data from it (read-only).
