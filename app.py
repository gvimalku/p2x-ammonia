"""Streamlit wrapper for the P2X green-ammonia engine.

A thin UI over the EXISTING engine — it changes no engine code. For one chosen site + a
handful of input overrides it writes a temporary case config (a sibling of the real
config/constants.yaml, so paths resolve exactly as the CLI does), calls the engine's own
`run_from_config`, and shows the results + the existing HTML chart report + downloads.

Run locally:   streamlit run app.py
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

# --- make the engine importable without installing (same trick as the README) ----
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2x_ammonia.engine import run_from_config          # noqa: E402
from p2x_ammonia.report import render_report            # noqa: E402
from p2x_ammonia.results import build_summary, export   # noqa: E402

CONFIG_DIR = ROOT / "config"
BASELINE = CONFIG_DIR / "default_fitzroy_hybrid.yaml"
SITES_FILE = ROOT / "data" / "weather" / "sites.json"

st.set_page_config(page_title="P2X Green-Ammonia Model", page_icon="⚡", layout="wide")


# --------------------------------------------------------------------- access gate
def check_password() -> bool:
    """Gate the app behind a shared password stored in Streamlit secrets.

    The password lives in Streamlit Cloud's Secrets (key `app_password`), never in
    this repo. If no secret is configured (e.g. local dev), the app is open.
    """
    try:
        correct = st.secrets["app_password"]
    except Exception:
        correct = None
    if not correct:                         # no password configured -> open (local dev)
        return True
    if st.session_state.get("auth_ok"):
        return True
    st.title("⚡ P2X Green-Ammonia Model")
    st.caption("This app is private. Enter the access password to continue.")
    pw = st.text_input("Access password", type="password")
    if pw:
        if pw == str(correct):
            st.session_state["auth_ok"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()


# ----------------------------------------------------------------------------- data
@st.cache_data
def load_baseline() -> dict:
    return yaml.safe_load(BASELINE.read_text())


@st.cache_data
def load_sites() -> list[dict]:
    return json.loads(SITES_FILE.read_text())


def bval(cfg: dict, section: str, key: str):
    return cfg["inputs"][section][key]["value"]


def run_case(overrides: dict, site: dict) -> "object":
    """Write a temp config (sibling of constants.yaml) + run the engine. No engine changes."""
    cfg = copy.deepcopy(load_baseline())
    for (section, key), val in overrides.items():
        cfg["inputs"][section][key]["value"] = val
    cfg["inputs"]["scope"]["location"]["value"] = site["label"]
    cfg["weather_file"] = site["file"]          # relative path -> resolves via project root
    cfg["case_name"] = "webapp_run"
    tmp = CONFIG_DIR / f"_tmp_{uuid.uuid4().hex}.yaml"
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False))
    try:
        return run_from_config(str(tmp))
    finally:
        tmp.unlink(missing_ok=True)


# ----------------------------------------------------------------------------- UI
base = load_baseline()
sites = load_sites()
labels = [s["label"] for s in sites]
default_idx = labels.index("Fitzroy, QLD") if "Fitzroy, QLD" in labels else 0

st.title("⚡ P2X Green-Ammonia Techno-Economic Model")
st.caption(
    "Hourly dispatch + 25-year discounted cash flow → levelised cost of ammonia (LCOA). "
    "Pick a site and inputs, then run. One configuration per run."
)

with st.sidebar:
    st.header("Inputs")
    site_label = st.selectbox("Site (renewable-energy zone)", labels, index=default_idx)
    site = next(s for s in sites if s["label"] == site_label)
    st.caption(
        f"Annual mean CF — solar {site['annual_mean_solar_cf']:.2f}, "
        f"wind {site['annual_mean_wind_cf']:.2f}"
    )

    st.subheader("Plant")
    nh3_ktpa = st.number_input("Ammonia capacity (kTPA)", 50.0, 5000.0,
                               float(bval(base, "sizing", "nh3_capacity_ktpa")), step=50.0)
    hybrid_solar_pct = st.slider("Solar share of hybrid (%)", 0, 100,
                                 int(round(bval(base, "sizing", "hybrid_split_solar") * 100)))
    re_oversize = st.number_input("RE oversizing (×)", 1.0, 4.0,
                                  float(bval(base, "sizing", "re_oversizing")), step=0.1)

    st.subheader("Electrolyser")
    sec = st.number_input("Energy use SEC (kWh/kg H₂)", 40.0, 70.0,
                          float(bval(base, "electrolyser", "sec_nominal_kwh_per_kg")), step=1.0)
    elec_oversize = st.number_input("Electrolyser oversizing (fraction)", 0.0, 3.0,
                                    float(bval(base, "sizing", "electrolyser_oversizing")), step=0.05)

    st.subheader("Battery")
    batt_mw = st.number_input("Battery power (MW)", 0.0, 5000.0,
                              float(bval(base, "battery", "battery_power_mw")), step=50.0)
    batt_h = st.selectbox("Battery duration (h)", [2, 4, 6, 8],
                          index=[2, 4, 6, 8].index(int(bval(base, "battery", "battery_duration_h")))
                          if int(bval(base, "battery", "battery_duration_h")) in [2, 4, 6, 8] else 3)

    st.subheader("Finance")
    discount_pct = st.number_input("Discount rate (%)", 0.0, 20.0,
                                   float(bval(base, "financing", "discount_rate") * 100), step=0.5)
    plant_life = st.number_input("Plant life (years)", 1, 40,
                                 int(bval(base, "financing", "plant_life_years")), step=1)

    run_clicked = st.button("Run simulation", type="primary", use_container_width=True)

overrides = {
    ("sizing", "nh3_capacity_ktpa"): nh3_ktpa,
    ("sizing", "hybrid_split_solar"): hybrid_solar_pct / 100.0,
    ("sizing", "re_oversizing"): re_oversize,
    ("sizing", "electrolyser_oversizing"): elec_oversize,
    ("electrolyser", "sec_nominal_kwh_per_kg"): sec,
    ("battery", "battery_power_mw"): batt_mw,
    ("battery", "battery_duration_h"): int(batt_h),
    ("financing", "discount_rate"): discount_pct / 100.0,
    ("financing", "plant_life_years"): int(plant_life),
}

if not run_clicked:
    st.info("Set your inputs in the sidebar and click **Run simulation**. "
            "The default inputs reproduce the validated Fitzroy baseline (LCOA ≈ 0.86 A$/kg).")
    st.stop()

with st.spinner(f"Running {site_label} — 8,760 hours × {int(plant_life)} years…"):
    res = run_case(overrides, site)
    summary = build_summary(res)
    # reuse the engine's own exporters, into a temp dir
    out_dir = Path(tempfile.mkdtemp(prefix="p2x_"))
    export(res, out_dir)
    report_path = render_report(res, out_dir / "report.html")
    report_html = Path(report_path).read_text()

# --- headline ---------------------------------------------------------------------
st.subheader(f"Results — {site_label}")
c1, c2, c3 = st.columns(3)
c1.metric("Levelised Cost of Ammonia", f"{summary['lc_nh3_aud_per_kg']:.4f} A$/kg")
c2.metric("Levelised Cost of Hydrogen", f"{summary['lc_h2_aud_per_kg']:.4f} A$/kg")
c3.metric("Total CAPEX", f"A$ {summary['capex_total_aud']:,.0f}")

c4, c5, c6 = st.columns(3)
c4.metric("Mean NH₃ production", f"{summary['nh3_tpa_mean']:,.0f} TPA")
c5.metric("Mean H₂ production", f"{summary['h2_tpa_mean']:,.0f} TPA")
c6.metric("Power-plant CF (yr 1)",
          f"{summary['power_plant_cf_year1']:.3f}" if summary['power_plant_cf_year1'] else "—")

with st.expander("Summary detail"):
    st.dataframe(
        pd.DataFrame(
            [(k, str(v)) for k, v in summary.items()], columns=["metric", "value"]
        ),
        use_container_width=True, hide_index=True,
    )

# --- downloads --------------------------------------------------------------------
st.subheader("Downloads")
dl = st.columns(3)
files = [
    ("report.html", "📊 Full HTML report", "text/html"),
    ("annual_production.csv", "📈 Annual production CSV", "text/csv"),
    ("cost_schedule.csv", "💰 Cost schedule CSV", "text/csv"),
    ("capex_ledger.csv", "🏗️ CAPEX ledger CSV", "text/csv"),
    ("lcoa_breakdown.csv", "🧮 LCOA breakdown CSV", "text/csv"),
    ("summary.json", "🧾 Summary JSON", "application/json"),
]
for i, (fname, label, mime) in enumerate(files):
    fp = out_dir / fname
    if fp.exists():
        dl[i % 3].download_button(label, fp.read_bytes(), file_name=f"{site['slug']}_{fname}",
                                  mime=mime, use_container_width=True)

# --- embedded chart report --------------------------------------------------------
st.subheader("Chart report")
st.components.v1.html(report_html, height=900, scrolling=True)
