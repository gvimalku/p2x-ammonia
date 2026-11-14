"""Standard chart suite for the HTML report (matplotlib -> base64 PNG).

Covers cost (LCOA stack, CAPEX split, cash-flow, replacement timeline), production
(annual output, degradation), dispatch (duration curves, hourly traces, allocation,
seasonal heatmap) and technical (SEC curve). Mirrors the Excel charts and adds the ones
the brief asks for.
"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

from .engine import CaseResult

# --- palette / style ---------------------------------------------------------
INK = "#1f2937"
GRID = "#e5e7eb"
PALETTE = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed",
           "#0891b2", "#ca8a04", "#db2777", "#64748b", "#16a34a"]
SEQ = "viridis"

plt.rcParams.update({
    "figure.dpi": 110,
    "font.size": 10.5,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})

# representative fortnight for time-series charts (mid-January)
WIN_START, WIN_LEN = 7 * 24, 14 * 24


def _fig_to_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _style(ax, title, xlabel=None, ylabel=None):
    ax.set_title(title, fontsize=12.5, fontweight="bold", pad=10, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


# --- cost charts -------------------------------------------------------------
def chart_lcoa_stack(res: CaseResult):
    bd = {k: v for k, v in res.lcoa.cost_breakdown_nh3.items() if v > 1e-6}
    items = sorted(bd.items(), key=lambda kv: kv[1])
    labels = [k.replace("capex_", "CAPEX ").replace("_", " ").title() for k, _ in items]
    vals = [v for _, v in items]
    fig, ax = plt.subplots(figsize=(7.2, 6))
    colors = [PALETTE[0] if k.startswith("capex") else PALETTE[1] for k, _ in items]
    ax.barh(labels, vals, color=colors)
    for y, v in enumerate(vals):
        ax.text(v, y, f" {v:.3f}", va="center", fontsize=8.5)
    _style(ax, f"LCOA breakdown — total {res.lcoa.lc_nh3:.3f} A$/kg NH₃",
           xlabel="A$/kg NH₃")
    ax.margins(x=0.12)
    return fig


def chart_capex_split(res: CaseResult):
    led = res.lcoa.ledger
    comps = {k: led.capex[k] + led.indirect.get(k, 0.0) for k in led.capex if led.capex[k] > 0}
    comps["indirect (installation+land)"] = sum(led.indirect.values())
    # show direct components + a combined indirect slice
    direct = {k: led.capex[k] for k in led.capex if led.capex[k] > 0}
    direct["indirect"] = sum(led.indirect.values())
    items = sorted(direct.items(), key=lambda kv: kv[1], reverse=True)
    labels = [k.replace("_", " ").title() for k, _ in items]
    vals = [v / 1e9 for _, v in items]
    fig, ax = plt.subplots(figsize=(7.2, 5))
    ax.bar(labels, vals, color=PALETTE)
    for x, v in enumerate(vals):
        ax.text(x, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8.5)
    _style(ax, f"Capital cost breakdown — total {res.lcoa.capex_total/1e9:.2f} B A$",
           ylabel="A$ billion")
    ax.tick_params(axis="x", rotation=35)
    for lbl in ax.get_xticklabels():
        lbl.set_ha("right")
    return fig


def chart_annual_cashflow(res: CaseResult):
    sched = pd.DataFrame(res.lcoa.schedule)
    years = sched["year"].to_numpy()
    base = (sched["power_plant_opex"] + sched["transmission_opex"] + sched["battery_opex"]
            + sched["electrolyser_opex"] + sched["h2_storage_opex"] + sched["ammonia_opex"]
            + sched["asu_opex"] + sched["additional_annual"]).to_numpy() / 1e6
    water = sched["water"].to_numpy() / 1e6
    stack = sched["stack_replacement"].to_numpy() / 1e6
    batt = sched["battery_replacement"].to_numpy() / 1e6
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.bar(years, base, label="Fixed O&M", color=PALETTE[0])
    ax.bar(years, water, bottom=base, label="Water", color=PALETTE[5])
    ax.bar(years, stack, bottom=base + water, label="Stack replacement", color=PALETTE[3])
    ax.bar(years, batt, bottom=base + water + stack, label="Battery replacement", color=PALETTE[4])
    _style(ax, "Year-by-year operating cash flow (undiscounted)",
           xlabel="Plant year", ylabel="A$ million/yr")
    ax.legend(frameon=False, ncol=4, fontsize=9, loc="upper left")
    return fig


def chart_cumulative_discounted(res: CaseResult):
    sched = pd.DataFrame(res.lcoa.schedule)
    disc = res.case.raw["discount_rate"]
    years = sched["year"].to_numpy()
    yearly_disc = sched["total"].to_numpy() / (1 + disc) ** years
    capex0 = res.lcoa.capex_total
    cum = np.cumsum(np.concatenate([[capex0], yearly_disc])) / 1e9
    xs = np.concatenate([[0], years])
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(xs, cum, color=PALETTE[0], lw=2.2, marker="o", ms=3)
    ax.fill_between(xs, 0, cum, color=PALETTE[0], alpha=0.08)
    ax.annotate(f"Year-0 CAPEX\n{capex0/1e9:.2f} B A$", (0, cum[0]),
                textcoords="offset points", xytext=(10, -4), fontsize=8.5)
    _style(ax, "Cumulative discounted lifetime cost",
           xlabel="Plant year", ylabel="Cumulative A$ billion")
    ax.text(0.99, 0.04, "Revenue/break-even added with the financing module (WS3)",
            transform=ax.transAxes, ha="right", fontsize=8, color="#6b7280", style="italic")
    return fig


def chart_replacement_timeline(res: CaseResult):
    life = int(res.case.raw["plant_life_years"])
    assets = [
        ("Power plant / ASU / NH₃", "lifetime", life, [], PALETTE[8]),
        ("Electrolyser stack", "replace", res.case.raw["stack_lifetime_hours"],
         sorted(res.stack_replace_years), PALETTE[3]),
        ("Battery", "replace", res.case.raw["battery_lifetime_yr"],
         sorted(res.battery_replace_years), PALETTE[4]),
    ]
    fig, ax = plt.subplots(figsize=(10, 3.4))
    for i, (name, _kind, _life, years, color) in enumerate(assets):
        ax.hlines(i, 0, life, color=GRID, lw=8)
        ax.plot(0, i, "s", color=color, ms=10)          # initial install
        for y in years:
            ax.plot(y, i, "o", color=color, ms=11)
            ax.annotate(f"yr {y}", (y, i), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8)
    ax.set_yticks(range(len(assets)))
    ax.set_yticklabels([a[0] for a in assets])
    ax.set_ylim(-0.6, len(assets) - 0.4)
    ax.set_xlim(-0.5, life + 0.5)
    ax.grid(axis="y", visible=False)
    _style(ax, "Asset replacement timeline  (■ install  ● replacement)", xlabel="Plant year")
    return fig


# --- production charts -------------------------------------------------------
def chart_annual_production(res: CaseResult):
    a = pd.DataFrame(res.annual)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.plot(a["year"], a["nh3_tpa"] / 1000, label="NH₃", color=PALETTE[0], lw=2, marker="o", ms=3)
    ax.plot(a["year"], a["n2_tpa"] / 1000, label="N₂", color=PALETTE[2], lw=2, marker="o", ms=3)
    ax.plot(a["year"], a["h2_tpa"] / 1000, label="H₂", color=PALETTE[1], lw=2, marker="o", ms=3)
    for y in res.stack_replace_years:
        ax.axvline(y, color=PALETTE[3], ls="--", lw=1, alpha=0.6)
    _style(ax, "Annual production over plant life", xlabel="Plant year", ylabel="kt / year")
    ax.legend(frameon=False, ncol=3, fontsize=9)
    ax.text(0.99, 0.04, "dashed = stack replacement", transform=ax.transAxes,
            ha="right", fontsize=8, color="#6b7280", style="italic")
    return fig


def chart_degradation(res: CaseResult):
    a = pd.DataFrame(res.annual)
    nh3 = a["nh3_tpa"] / a["nh3_tpa"].iloc[0] * 100
    h2 = a["h2_tpa"] / a["h2_tpa"].iloc[0] * 100
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(a["year"], nh3, label="NH₃ output", color=PALETTE[0], lw=2)
    ax.plot(a["year"], h2, label="H₂ output", color=PALETTE[1], lw=2)
    for y in res.stack_replace_years:
        ax.axvline(y, color=PALETTE[3], ls="--", lw=1, alpha=0.6)
    _style(ax, "Output vs year 1 (degradation & stack renewal)",
           xlabel="Plant year", ylabel="% of year-1 output")
    ax.legend(frameon=False, ncol=2, fontsize=9)
    return fig


# --- dispatch charts ---------------------------------------------------------
def _duration(ax, series, color, label):
    s = np.sort(series)[::-1]
    x = np.linspace(0, 100, len(s))
    ax.plot(x, s, color=color, lw=2, label=label)
    ax.fill_between(x, 0, s, color=color, alpha=0.08)
    ax.xaxis.set_major_formatter(PercentFormatter())


def chart_duration_curves(res: CaseResult):
    h = res.hourly
    fig, ax = plt.subplots(figsize=(10, 4.6))
    _duration(ax, h["C"], PALETTE[0], "Power plant")
    _duration(ax, h["AE"], PALETTE[1], "Electrolyser")
    _duration(ax, h["AS"], PALETTE[2], "Ammonia plant")
    ax.set_ylim(0, None)
    _style(ax, "Load duration curves (year 1)",
           xlabel="% of year at or above", ylabel="Capacity factor / load")
    ax.legend(frameon=False, ncol=3, fontsize=9)
    return fig


def chart_hourly_cf(res: CaseResult):
    h = res.hourly
    sl = slice(WIN_START, WIN_START + WIN_LEN)
    days = np.arange(WIN_LEN) / 24
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(days, h["C"][sl], color=PALETTE[0], lw=1.4, label="Power plant")
    ax.plot(days, h["AE"][sl], color=PALETTE[1], lw=1.4, label="Electrolyser")
    ax.plot(days, h["AS"][sl], color=PALETTE[2], lw=1.6, label="Ammonia plant")
    _style(ax, "Hourly capacity factors (representative fortnight)",
           xlabel="Day", ylabel="Capacity factor / load")
    ax.legend(frameon=False, ncol=3, fontsize=9)
    return fig


def chart_storage_states(res: CaseResult):
    h = res.hourly
    sl = slice(WIN_START, WIN_START + WIN_LEN)
    days = np.arange(WIN_LEN) / 24
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.plot(days, h["V"][sl] * 100, color=PALETTE[4], lw=1.6, label="Battery SOC")
    ax.plot(days, h["AM"][sl] * 100, color=PALETTE[5], lw=1.6, label="H₂ storage level")
    ax.set_ylim(0, 105)
    _style(ax, "Storage state of charge (representative fortnight)",
           xlabel="Day", ylabel="% full")
    ax.legend(frameon=False, ncol=2, fontsize=9)
    return fig


def chart_energy_allocation(res: CaseResult):
    h = res.hourly
    sl = slice(WIN_START, WIN_START + WIN_LEN)
    days = np.arange(WIN_LEN) / 24
    elec = h["AD"][sl]
    asu = h["AN"][sl]
    charge = h["R"][sl]
    curtail = np.clip(h["AU"][sl], 0, None)
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.stackplot(days, asu, elec, charge, curtail,
                 labels=["ASU / Haber-Bosch", "Electrolyser", "Battery charge", "Curtailed"],
                 colors=[PALETTE[2], PALETTE[1], PALETTE[4], PALETTE[8]], alpha=0.9)
    _style(ax, "Hourly energy allocation (representative fortnight)",
           xlabel="Day", ylabel="MW")
    ax.legend(frameon=False, ncol=4, fontsize=8.5, loc="upper left")
    return fig


def chart_seasonal_heatmap(res: CaseResult):
    h = res.hourly
    if "month" not in h or h.get("hour_of_day") is None:
        return None
    df = pd.DataFrame({"month": h["month"], "hod": h["hour_of_day"], "cf": h["C"]})
    piv = df.pivot_table(index="hod", columns="month", values="cf", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(9, 4.8))
    im = ax.imshow(piv.values, aspect="auto", origin="lower", cmap=SEQ,
                   extent=[0.5, 12.5, 0, 24])
    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.set_label("Mean power-plant CF")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_yticks([0, 6, 12, 18, 24])
    ax.grid(False)
    _style(ax, "Generation by month & hour of day", xlabel="Month", ylabel="Hour of day")
    return fig


def chart_monthly_curtailment(res: CaseResult):
    h = res.hourly
    if "month" not in h:
        return None
    df = pd.DataFrame({"month": h["month"], "curtail": np.clip(h["AU"], 0, None)})
    monthly = df.groupby("month")["curtail"].sum() / 1e3   # GWh
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(monthly.index, monthly.values, color=PALETTE[8])
    ax.set_xticks(range(1, 13))
    _style(ax, "Curtailed energy by month (year 1)", xlabel="Month", ylabel="GWh")
    return fig


# --- technical ---------------------------------------------------------------
def chart_sec_curve(res: CaseResult):
    cfg_dir = Path(res.case.meta["config_path"]).parent
    path = cfg_dir / "electrolyser_curve.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path).sort_values("load_fraction")
    df = df[df["load_fraction"] <= 1.0]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    ax.plot(df["load_fraction"] * 100, df["sec_kwh_per_kg"], color=PALETTE[1],
            lw=2, marker="o")
    _style(ax, "Electrolyser specific energy consumption vs load",
           xlabel="Electrolyser load (%)", ylabel="SEC (kWh/kg H₂)")
    return fig


# --- registry ----------------------------------------------------------------
CHARTS = [
    ("lcoa_stack", "LCOA cost breakdown", "Contribution of each cost line to the levelised cost of ammonia.", chart_lcoa_stack),
    ("capex_split", "Capital cost breakdown", "Direct CAPEX by component plus combined installation/land indirects.", chart_capex_split),
    ("annual_cashflow", "Annual operating cash flow", "Undiscounted operating cost each year, including replacement spikes.", chart_annual_cashflow),
    ("cumulative_cost", "Cumulative discounted cost", "Running discounted lifetime cost from year-0 CAPEX onward.", chart_cumulative_discounted),
    ("replacement_timeline", "Replacement timeline", "When each asset is installed and replaced over the plant life.", chart_replacement_timeline),
    ("annual_production", "Annual production", "H2 / N2 / NH3 output across the 25-year life.", chart_annual_production),
    ("degradation", "Output degradation", "Output relative to year 1, showing degradation and stack renewal.", chart_degradation),
    ("duration_curves", "Load duration curves", "Sorted hourly capacity factors for power plant, electrolyser and NH3 plant.", chart_duration_curves),
    ("hourly_cf", "Hourly capacity factors", "Dispatch over a representative fortnight.", chart_hourly_cf),
    ("storage_states", "Storage state of charge", "Battery and hydrogen storage levels over a fortnight.", chart_storage_states),
    ("energy_allocation", "Energy allocation", "Where generated power goes, hour by hour.", chart_energy_allocation),
    ("seasonal_heatmap", "Seasonal generation", "Mean generation capacity factor by month and hour of day.", chart_seasonal_heatmap),
    ("monthly_curtailment", "Monthly curtailment", "Curtailed (wasted) energy by month.", chart_monthly_curtailment),
    ("sec_curve", "Electrolyser efficiency", "Specific energy consumption versus load.", chart_sec_curve),
]


def build_all(res: CaseResult) -> list[dict]:
    out = []
    for cid, title, desc, fn in CHARTS:
        try:
            fig = fn(res)
        except Exception as exc:  # noqa: BLE001
            out.append({"id": cid, "title": title, "description": desc, "error": str(exc)})
            continue
        if fig is None:
            continue
        out.append({"id": cid, "title": title, "description": desc, "uri": _fig_to_uri(fig)})
    return out
