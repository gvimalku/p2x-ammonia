"""Hourly energy-balance engine — faithful port of 'S5. Working Data'.

One forward pass over 8,760 hours for a given plant-year. State (battery SOC, H2 storage,
cumulative NH3/excess) carries hour-to-hour. Row 19 (seed) vs row 20 (recurrence) differences
are handled by the `h == 0` branch. v1 implements the Standalone Hybrid + Battery case;
gas-turbine / grid-balancing branches evaluate to zero here and are stubbed for later configs.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Case


@dataclass
class YearResult:
    re_mwh: float            # SUM(D)  — RE electricity after transmission
    h2_kg: float             # SUM(AF)
    n2_kg: float             # SUM(AQ)
    nh3_kg: float            # SUM(AR)
    power_allocated_mwh: float   # SUM(AN+AD)
    excess_mwh: float        # SUM(AU)
    batt_charge_mwh: float   # SUM(R)
    op_hours: int            # COUNTIF(AE>0)
    hourly: dict | None = None   # optional full traces (for the reporting year)


def simulate_year(
    case: Case,
    solar_cf: np.ndarray,
    wind_cf: np.ndarray,
    year: int,
    stack_deg: float,
    capture_hourly: bool = False,
) -> YearResult:
    d = case.derived
    r = case.raw

    # --- sizing / thresholds ---
    SolarCap, WindCap, RECap = d["SolarCap"], d["WindCap"], d["RECap"]
    Pmax, Pstoic, Pmin = d["Pmax"], d["Pstoic"], d["Pmin"]
    Prated_Elec, Prated_ASU_HB = d["Prated_Elec"], d["Prated_ASU_HB"]
    elecCapacity, H2Stoic, NH3Cap = d["elecCapacity"], d["H2Stoic"], d["NH3Cap"]
    MinH2StorCap = d["MinH2StorCap"]

    # --- parameters ---
    SolarDeg, WindDeg = r["solar_degradation_pct_yr"], r["wind_degradation_pct_yr"]
    Power_Loss, Tran_Dist = r["transmission_loss_per_km"], r["transmission_distance_km"]
    SECH2 = d["SECH2"]
    sec_fixed = str(r["sec_vs_load"]).strip().lower() == "fixed"
    ElecMinLoad = r["elec_min_load"]
    ElecOversize = r["electrolyser_oversizing"]
    MinLoadNH3 = r["nh3_min_turndown"]
    BattPower, BattCap = r["battery_power_mw"], r["battery_duration_h"] * r["battery_power_mw"]
    BattEff, BattMin, BattMax = r["battery_rte"], r["battery_min_soc"], r["battery_max_soc"]
    H2Stor_Cap = r["h2_storage_capacity_kg"]
    eff_half = 1 - (1 - BattEff) / 2          # delivery factor per charge/discharge (0.925)
    nh3_conv = 0.99
    try:
        nh3_conv = case.constants["stoichiometry"]["nh3_conversion_efficiency"]["value"]
    except Exception:
        pass

    # SEC-vs-load quadratic coeffs (only used if not fixed)
    a1 = b1 = c1 = 0.0
    if not sec_fixed:
        fit = case.constants["electrolyser_sec_fit"]
        a1, b1, c1 = fit["a"]["value"], fit["b"]["value"], fit["c"]["value"]

    sdeg = (1 - SolarDeg) ** (year - 1)
    wdeg = (1 - WindDeg) ** (year - 1)
    trans_loss = Power_Loss * Tran_Dist
    deg_factor = 1 - stack_deg

    n = len(solar_cf)

    # carried state
    V_prev = BattMin            # battery SOC (fraction)
    AL_prev = H2Stor_Cap        # H2 in storage (kg) — starts full
    AT_prev = 0.0               # cumulative NH3 (T)
    AW_prev = 0.0               # cumulative excess H2 (T)

    # aggregates
    sum_D = sum_AF = sum_AQ = sum_AR = sum_AN_AD = sum_AU = sum_R = 0.0
    op_hours = 0

    traces: dict[str, np.ndarray] = {}
    if capture_hourly:
        for name in ("C", "D", "AE", "AF", "AS", "V", "AM", "AU", "AD", "AN"):
            traces[name] = np.empty(n, dtype="float64")

    for h in range(n):
        seed = h == 0
        AM_prev = (AL_prev / H2Stor_Cap) if AL_prev > 0 else 0.0

        # --- generation ---
        C = (solar_cf[h] * SolarCap * sdeg + wind_cf[h] * WindCap * wdeg) / RECap
        D = RECap * C - trans_loss

        # --- operating region (mutually exclusive) ---
        H = D >= Pmax
        I = Pstoic <= D < Pmax
        J = Prated_ASU_HB < D < Pstoic
        K = Pmin < D < Prated_ASU_HB
        L = D < Pmin

        # --- RE allocation: ASU/HB prioritised, electrolyser gets the surplus ---
        if H:
            M = Prated_Elec
            N = Prated_ASU_HB
        elif I:
            M = Prated_Elec - (Pmax - D)
            N = Prated_ASU_HB
        elif J:
            M = max(Prated_Elec - (Pmax - D), 0.0)
            N = Prated_ASU_HB
        elif K:
            M = 0.0
            N = D
        elif L:
            M = 0.0
            N = D
        else:
            M = 0.0
            N = 0.0

        P = (D - (Prated_Elec + Prated_ASU_HB)) if H else 0.0   # excess
        # (Q deficit not needed explicitly below)

        # --- battery (BT1) ---
        if seed:
            R = min(BattPower, D - Pmax) if P > 0 else 0.0
            S = 0.0
            T = 0.0
        else:
            if P > 0 and V_prev != BattMax:
                R = min(BattPower, D - Pmax, (BattMax - V_prev) * BattCap)
            else:
                R = 0.0
            # discharge to ASU/NH3
            S = 0.0
            if (K or L) and V_prev > BattMin:
                if K:
                    S = -min(BattPower, (V_prev - BattMin) * BattCap, (Prated_ASU_HB - N) / eff_half)
                elif L:
                    S = -min(BattPower, V_prev * BattCap, (Pmin - N) / eff_half)
            # discharge to electrolyser
            T = 0.0
            if (V_prev - (abs(S) / BattCap)) > BattMin:
                if J and AM_prev <= 0.1 and ElecOversize > 0 and V_prev > BattMin:
                    T = -min(BattPower, (V_prev - BattMin) * BattCap)
                elif M < Prated_Elec:
                    T = -min(BattPower, Prated_Elec - M,
                             ((V_prev - abs(S) / BattCap) - BattMin) * BattCap, BattPower + S)
                else:  # M == Prated_Elec
                    T = 0.0

        # --- ASU/HB power incl. battery ---
        AN = N + (-S * eff_half if S < 0 else 0.0)

        # --- electrolyser power incl. battery ---
        avail = M + (-T * eff_half if T < 0 else 0.0)
        AD = min(avail, Prated_Elec) if avail >= ElecMinLoad * Prated_Elec else 0.0
        AE = AD / Prated_Elec

        # --- H2 production ---
        sec_term = (1.0 / SECH2) if sec_fixed else 1.0 / (a1 * AE * AE + b1 * AE + c1)
        AF = sec_term * AD * 1000.0 * deg_factor

        # --- NH3 unit H2 demand ---
        AG = H2Stoic if AN == Prated_ASU_HB else (AN / Prated_ASU_HB) * H2Stoic

        # --- excess / deficit H2 ---
        if seed:
            AH = (AF - AG) if AF > AG else 0.0
        else:
            if AF >= AG:
                AH = AF - AG
            elif AL_prev == MinH2StorCap and AF < H2Stoic * MinLoadNH3:
                AH = AF
            elif AF + (AL_prev - MinH2StorCap) > H2Stoic * MinLoadNH3:
                AH = 0.0
            elif AF + (AL_prev - MinH2StorCap) < H2Stoic * MinLoadNH3:
                AH = AF
            elif AF >= H2Stoic * MinLoadNH3:
                AH = 0.0
            else:
                AH = 0.0

        if (J or K or L) and AH == 0:
            # all branches reduce to AF-AG here
            AI = AF - AG
        else:
            AI = 0.0

        # --- H2 storage charge/discharge ---
        if seed:
            AJ = 0.0
            if AI < 0 and H2Stor_Cap >= MinH2StorCap + AI and \
               AF + (H2Stor_Cap - MinH2StorCap) >= H2Stoic * MinLoadNH3:
                AK = -min(abs(AI), H2Stor_Cap - MinH2StorCap)
            else:
                AK = 0.0
        else:
            if AL_prev < H2Stor_Cap and (AH / H2Stor_Cap) <= 1 - AM_prev:
                AJ = AH
            else:
                AJ = 0.0
            if AI < 0 and AL_prev >= MinH2StorCap + AI and \
               AF + (AL_prev - MinH2StorCap) >= H2Stoic * MinLoadNH3:
                AK = -min(abs(AI), AL_prev - MinH2StorCap)
            else:
                AK = 0.0

        AL = AL_prev + (AJ + AK)
        AM = (AL / H2Stor_Cap) if (seed and AL <= 0) is False else AL / H2Stor_Cap

        # --- H2 feed to NH3 unit ---
        if seed:
            if AF < H2Stoic:
                AO = AF + abs(AK)
            elif AF < H2Stoic * MinLoadNH3 and AL_prev == MinH2StorCap:
                AO = 0.0
            elif AF >= H2Stoic:
                AO = H2Stoic
            else:
                AO = 0.0
        else:
            if AF < H2Stoic and AN >= Prated_ASU_HB:
                AO = AF + abs(AK)
            elif AF < H2Stoic and AN < Prated_ASU_HB:
                AO = AG
            elif AF < H2Stoic * MinLoadNH3 and AL_prev == MinH2StorCap:
                AO = 0.0
            elif AF >= H2Stoic:
                AO = H2Stoic
            else:
                AO = 0.0

        AP = AO / H2Stoic
        if AP >= MinLoadNH3:
            AQ = ((AO / 2) / 3.01) * 28
            AR = (AO + AQ) * nh3_conv
        else:
            AQ = 0.0
            AR = 0.0
        AS = AR / NH3Cap

        AU = D - (R + AD + AN)           # excess power after allocation

        # --- battery SOC update (carries to next hour) ---
        if seed:
            V = BattMin
        elif V_prev == BattMax and S == 0 and T == 0:
            V = V_prev
        else:
            V = V_prev + (R + S + T) / BattCap

        # --- aggregates ---
        sum_D += D
        sum_AF += AF
        sum_AQ += AQ
        sum_AR += AR
        sum_AN_AD += AN + AD
        sum_AU += AU
        sum_R += R
        if AE > 0:
            op_hours += 1

        if capture_hourly:
            traces["C"][h] = C
            traces["D"][h] = D
            traces["AE"][h] = AE
            traces["AF"][h] = AF
            traces["AS"][h] = AS
            traces["V"][h] = V
            traces["AM"][h] = AM
            traces["AU"][h] = AU
            traces["AD"][h] = AD
            traces["AN"][h] = AN

        # advance state
        V_prev = V
        AL_prev = AL
        AT_prev = AT_prev + AR / 1000.0
        AW_prev = AW_prev + (AF - (AJ + AO + AK)) / 1000.0

    return YearResult(
        re_mwh=sum_D,
        h2_kg=sum_AF,
        n2_kg=sum_AQ,
        nh3_kg=sum_AR,
        power_allocated_mwh=sum_AN_AD,
        excess_mwh=sum_AU,
        batt_charge_mwh=sum_R,
        op_hours=op_hours,
        hourly=traces if capture_hourly else None,
    )
