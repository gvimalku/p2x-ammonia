"""Derived plant sizing and power-region thresholds.

Ports the S1 '[calc]' cells and the A3 'Power Demand Regions' block. Fills case.derived
with the named-range quantities the hourly dispatch and economics depend on.
"""
from __future__ import annotations

from .config import Case, const_value


def compute_sizing(case: Case) -> Case:
    r = case.raw
    c = case.constants

    # Stoichiometry (parameterised; molar ratios 6.047/28.134 per 34.181 NH3, as in the S1 formulas)
    if c and "stoichiometry" in c and "h2_molar_basis" in c["stoichiometry"]:
        nh3_molar = const_value(c, "stoichiometry", "nh3_molar_basis")
        h2_per_nh3 = const_value(c, "stoichiometry", "h2_molar_basis") / nh3_molar
        n2_per_nh3 = const_value(c, "stoichiometry", "n2_molar_basis") / nh3_molar
    else:
        h2_per_nh3 = 6.047 / 34.181
        n2_per_nh3 = 28.134 / 34.181

    NH3_Cap = r["nh3_capacity_ktpa"]              # kTPA
    SECNH3 = r["sec_nh3_kwh_per_kg"]
    SECN2 = r["sec_asu_kwh_per_kg_n2"]
    SEC_nominal = r["sec_nominal_kwh_per_kg"]     # S1!B51
    elecEff = r["sec_correction_factor"]          # S1!B54
    ElecOversize = r["electrolyser_oversizing"]
    RE_oversize = r["re_oversizing"]
    split_solar = r["hybrid_split_solar"]
    MinLoadNH3 = r["nh3_min_turndown"]
    H2Stor_Cap = r["h2_storage_capacity_kg"]
    min_h2_frac = r["min_h2_storage_frac"]
    gen_type = _generator_type(r["power_plant_config"])

    # --- S1 derived sizing cells ---
    NH3_PowDem = (NH3_Cap / 8760 * 1_000_000) * SECNH3 / 1000               # B13 (MW)
    ASU_Cap = (NH3_Cap * 1000 / 365) * n2_per_nh3                           # B14 (TPD)
    N2_PowDem = (ASU_Cap / 24) * SECN2                                      # B15 (MW)
    H2_Output = (NH3_Cap * 1000 / 365) * h2_per_nh3                         # B16 (TPD)
    elecCapacity = (H2_Output / 24) * SEC_nominal * (1 + ElecOversize)      # B17 (MW)
    H2Stoic = (H2_Output / 24) * 1000                                       # named H2Stoic (kg/hr)
    SECH2 = SEC_nominal / elecEff                                           # B55

    base = NH3_PowDem + N2_PowDem + elecCapacity                           # = Pmax
    if gen_type == "Hybrid":
        SolarCap = base * (1 + RE_oversize) * split_solar                   # B20
        WindCap = base * (1 + RE_oversize) * (1 - split_solar)              # B21
        RECap = SolarCap + WindCap                                         # B25
    elif gen_type == "Solar":
        SolarCap = NH3_PowDem + N2_PowDem + elecCapacity * (1 + RE_oversize)
        WindCap = 0.0
        RECap = SolarCap
    elif gen_type == "Wind":
        SolarCap = 0.0
        WindCap = NH3_PowDem + N2_PowDem + elecCapacity * (1 + RE_oversize)
        RECap = WindCap
    else:  # Grid
        SolarCap = WindCap = 0.0
        RECap = 0.0

    # --- A3 power-demand regions ---
    Prated_Elec = elecCapacity                                             # A3!B22
    Elec_StoicP = elecCapacity / (1 + ElecOversize)                        # A3!B23
    Prated_ASU_HB = NH3_PowDem + N2_PowDem                                 # A3!B24
    Pmax = NH3_PowDem + N2_PowDem + elecCapacity                           # A3!B20
    Pstoic = Elec_StoicP + Prated_ASU_HB                                   # A3!B21
    Pmin = Prated_ASU_HB * MinLoadNH3                                      # A3!B25
    NH3Cap = NH3_Cap * 1_000_000 / 8760                                    # A3!B27 (kg/hr)
    MinH2StorCap = min_h2_frac * H2Stor_Cap                                # named MinH2StorCap

    case.derived.update(
        GenType=gen_type,
        NH3_PowDem=NH3_PowDem, ASU_Cap=ASU_Cap, N2_PowDem=N2_PowDem, H2_Output=H2_Output,
        elecCapacity=elecCapacity, H2Stoic=H2Stoic, SECH2=SECH2,
        SolarCap=SolarCap, WindCap=WindCap, RECap=RECap,
        Prated_Elec=Prated_Elec, Elec_StoicP=Elec_StoicP, Prated_ASU_HB=Prated_ASU_HB,
        Pmax=Pmax, Pstoic=Pstoic, Pmin=Pmin, NH3Cap=NH3Cap, MinH2StorCap=MinH2StorCap,
        h2_per_nh3=h2_per_nh3, n2_per_nh3=n2_per_nh3,
    )
    return case


def _generator_type(pp_config: str) -> str:
    """Port of S1!B19 IFS(SEARCH(...))."""
    s = str(pp_config)
    for token, gen in (("Solar", "Solar"), ("Wind", "Wind"), ("Hybrid", "Hybrid"), ("Grid", "Grid")):
        if token in s:
            return gen
    return "Hybrid"


def balancing_type(b_tech: str) -> str:
    """Port of S1!B146."""
    s = str(b_tech)
    if "Battery" in s:
        return "Battery"
    if "Combined Cycle" in s:
        return "Combined Cycle Gas Turbine"
    if "Open Cycle" in s:
        return "Open Cycle Gas Turbine"
    if "Grid" in s:
        return "Grid Balanced"
    if "No Balancing" in s:
        return "No Balancing Technology"
    return s
