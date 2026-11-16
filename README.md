# P2X Green-Ammonia Techno-Economic Engine

A Python one-case engine that ports and extends the UNSW **HySupply Ammonia Analysis Tool V1.0**
(Excel/VBA). Given one input configuration it runs an 8,760-hour dispatch simulation across every
year of the plant's life, a 25-year discounted cash flow, and produces a levelised cost of ammonia
(LCOA) and hydrogen (LCOH) plus a self-contained chart report.

The engine is built so a later layer can drive multiple iterations / sizing sweeps / optimisation
over the same pure `run_case()` function; v1 ships one validated case end-to-end.

## Status

| Workstream | What | State |
|---|---|---|
| 1 | Project scaffold + Excel data extraction | ✅ done |
| 2 | Core port to parity (sizing → dispatch → DCF/LCOA) | ✅ done — matches the workbook (LCOH exact, LCOA within 0.0015%, annual production ±0.00% over 25 yr) |
| 4 | Chart suite + HTML report (14 charts) | ✅ done |
| 3 | New financial features (full replacement schedules, financing layer, break-even/ROI/cash-flow) | ⏳ pending |
| 5 | Excel bug report + corrected copy | ⏳ pending |

See `/Users/vgkumar/.claude/plans/the-following-describes-what-delightful-dragonfly.md` for the full plan.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install .                                  # regular install (see note at the bottom)
python scripts/extract_excel_data.py           # workbook -> data/ + config/ (first time only)
p2x-run config/default_fitzroy_hybrid.yaml     # -> outputs/<case>/report.html + CSVs
pytest                                         # parity + unit tests (45)
```

Open `outputs/default_fitzroy_hybrid/report.html` in any browser for the full chart report.

---

## Usage & how it works

### How a run is structured

One run = **one input configuration (a YAML file) → one `CaseResult`**. Internally the engine does two
nested loops, mirroring the original workbook:

- **Inner loop — hourly dispatch.** For a given year it steps through all **8,760 hours**, carrying
  state hour-to-hour (battery state-of-charge, H₂ storage level, cumulative ammonia). Each hour it
  allocates renewable power (ASU/Haber-Bosch first, electrolyser next), charges/discharges the
  battery, makes and stores H₂, and runs the ammonia plant subject to its minimum-load floor.
- **Outer loop — the 25-year sweep.** It **runs that full hourly simulation once per plant-year**
  (default 25), applying solar/wind degradation and electrolyser-stack degradation, and triggering a
  **stack replacement** when cumulative operating hours cross the stack lifetime and a **battery
  replacement** on its lifetime interval. The resulting 25-year production and cost streams feed the
  discounted cash flow → LCOA / LCOH.

So **yes — every run simulates all 8,760 hours for all 25 years** (≈219,000 hour-steps), in well under
a second. The HTML report's hourly charts (duration curves, battery/storage traces) are drawn for one
**reporting year**, which defaults to year 1 — change it with `--reporting-year N`.

### Changing inputs

Every input lives in the case YAML (`config/default_fitzroy_hybrid.yaml`). **Don't edit the default in
place** — copy it, so your baseline stays clean:

```bash
cp config/default_fitzroy_hybrid.yaml config/my_test.yaml
```

Then open `config/my_test.yaml` and change the `value:` under any input. Each entry carries its unit
and its section, e.g.:

```yaml
  financing:
    discount_rate:
      value: 0.07        # <- change to 0.10 to test a higher cost of capital
      unit: fraction/yr
```

Run the variant (the default is untouched):

```bash
p2x-run config/my_test.yaml          # -> outputs/my_test/report.html + CSVs
# or, without reinstalling after code changes:
PYTHONPATH=src python -m p2x_ammonia.cli config/my_test.yaml
```

**Knobs worth trying** (all within the default hybrid+battery plant):

| Section | Example inputs |
|---|---|
| `sizing` | `nh3_capacity_ktpa` (plant size), `electrolyser_oversizing`, `hybrid_split_solar`, `re_oversizing`, `h2_storage_capacity_kg` |
| `electrolyser` | `sec_nominal_kwh_per_kg` (energy use), `elec_min_load`, `stack_lifetime_hours`, `stack_degradation_pct_yr`, costs |
| `battery` | `battery_power_mw`, `battery_duration_h`, `battery_rte`, `battery_lifetime_yr` |
| `power_plant` | solar/wind reference costs, degradation, OPEX |
| `financing` | `plant_life_years`, `discount_rate` |
| CAPEX/OPEX `%` | install/land percentages and OPEX fractions on every asset |

Sanity check (all behave as expected): raising `discount_rate` 7%→10% lifts LCOA ~20%; growing
`nh3_capacity_ktpa` 1000→1500 drops it ~8% (economies of scale); worsening electrolyser
`sec_nominal_kwh_per_kg` 50→55 raises it ~6%.

**Limit (v1):** the *categorical topology* choices — `power_plant_config` (hybrid), `balancing_technology`
(battery), `electrolyser.sec_vs_load` (Fixed vs part-load curve) — are only wired for the default
**hybrid + battery** case. Changing those to other options (standalone solar, hydrogen-storage
balancing, etc.) is the multi-config work the architecture is designed for but v1 does not yet ship.
Numeric inputs within the hybrid+battery setup are all fair game.

### Changing the site

The case points at a pre-extracted weather trace:

```yaml
weather_file: data/weather/fitzroy.parquet
```

**v1 ships only Fitzroy, QLD.** Editing the `location:` text alone does nothing — the hourly solar and
wind capacity factors come from `weather_file`, not the location string. To model another site you must
first **extract that region's trace** from the workbook's `S4. Raw Data` sheet (it holds all 42 Australian
renewable-energy zones), save it as a new `data/weather/<region>.parquet`, and point `weather_file` at
it. `scripts/extract_excel_data.py` is the tool for that pull (extending it to emit any/all 42 REZ is a
small, planned addition). Until then, other sites aren't available out of the box.

### Outputs — what to check

A run writes to `outputs/<case_name>/`:

| File | Contents | What to look at |
|---|---|---|
| `report.html` | Self-contained report, 14 charts | The headline LCOA, cost breakdown, duration curves, 25-yr production & replacement timeline |
| `summary.json` | Headline results | `lc_nh3_aud_per_kg`, `lc_h2_aud_per_kg`, `capex_total_aud`, mean production, replacement years |
| `annual_production.csv` | Per-year H₂/N₂/NH₃ (TPA), energy, operating hours | That production declines with degradation and jumps up in replacement years |
| `cost_schedule.csv` | Year-by-year discounted cost stream | CAPEX at year 0, OPEX + replacements years 1–25 |
| `capex_ledger.csv` | CAPEX by component (direct + indirect) | Power plant / battery / electrolyser / H₂ storage / ammonia / ASU / transmission split |
| `lcoa_breakdown.csv` | LCOA contribution by cost category | Which components dominate the levelised cost |

The CLI also prints the headline summary to the terminal when the run finishes.

### Checking it against the Excel

Parity is validated automatically against values read straight from the workbook's own cached cells
(`data/golden/excel_cached_outputs.json`):

```bash
pytest tests/test_parity.py -v                        # pass/fail within tolerance
PYTHONPATH=src python scripts/compare_vs_excel.py      # human-readable side-by-side table
```

The script lines up: LCOH/LCOA (`S3!AE129` / `AE130`), the 25-year production profile (`S3` rows 9–33),
and plant-life average production (`S2` col F). Note the `S2` summary rows are **25-year averages**, not
year-1 values.

> **Reading the workbook itself:** open it in **Microsoft Excel** (enable macros; the `Calc` button runs
> the year sweep). **Apple Numbers recalculates the file with its own formula engine on open and gets the
> LCOA wrong** (it can't evaluate all the Excel functions the model uses), so its displayed `AE129/AE130`
> are not the real figures. The engine is validated against the true Excel values (3.8051 / 0.8645).

## Layout

```
config/    input config (YAML), constants, electrolyser curve
data/      extracted weather traces + golden parity targets (from the workbook)
src/p2x_ammonia/   the engine package
scripts/   extract_excel_data.py (workbook -> data/), compare_vs_excel.py, make_fixed_workbook.py
tests/     parity + unit tests
docs/      bug report, cost scope, assumptions-for-review
outputs/   run artifacts (gitignored)
```

**Install note:** this project's `.venv` is built on an Anaconda base Python whose `site`
does not reliably honour editable (`pip install -e .`) `.pth` files, so a regular
`pip install .` is used. Re-run `pip install .` after changing the package code to refresh
the installed console script. For fast iteration without reinstalling, run against `src/`
directly:

```bash
PYTHONPATH=src python -m p2x_ammonia.cli config/default_fitzroy_hybrid.yaml
```

Tests already run against `src/` (configured in `pyproject.toml`), so `pytest` needs no reinstall.

## Source model

`HySupply Ammonia Analysis Tool V1.0.xlsm` — UNSW, 2022, MIT-licensed. Australia–Germany HySupply
study. The workbook is the source of truth; `scripts/extract_excel_data.py` regenerates all derived
data from it (read-only).
