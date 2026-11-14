"""Parity check: derived sizing must match the workbook's cached S1/A3 values."""
from __future__ import annotations

import math

import pytest

from p2x_ammonia.config import load_case
from p2x_ammonia.sizing import compute_sizing

# Cached values from the workbook (data/raw_extract/formulas.txt).
EXPECTED = {
    "NH3_PowDem": 46.80365296803653,
    "ASU_Cap": 2255.037946660265,
    "N2_PowDem": 21.61078032216087,
    "H2_Output": 484.6880807369952,
    "elecCapacity": 1832.726805286763,
    "H2Stoic": 20195.336697374798,
    "SolarCap": 3011.4077219059054,
    "WindCap": 1551.3312506787995,
    "RECap": 4562.738972584705,
    "Prated_Elec": 1832.726805286763,
    "Elec_StoicP": 1009.76683486874,
    "Prated_ASU_HB": 68.4144332901974,
    "Pmax": 1901.1412385769604,
    "Pstoic": 1078.1812681589374,
    "Pmin": 22.57676298576514,
    "NH3Cap": 114155.25114155251,
    "MinH2StorCap": 50000.0,
}


@pytest.fixture(scope="module")
def case():
    return compute_sizing(load_case("config/default_fitzroy_hybrid.yaml"))


@pytest.mark.parametrize("key,expected", EXPECTED.items())
def test_sizing_matches_excel(case, key, expected):
    got = case.derived[key]
    assert math.isclose(got, expected, rel_tol=1e-9), f"{key}: {got} != {expected}"
