"""End-to-end parity: Python engine vs the workbook's cached outputs (golden targets)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2x_ammonia.engine import run_from_config

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = json.loads((ROOT / "data/golden/excel_cached_outputs.json").read_text())


@pytest.fixture(scope="module")
def result():
    return run_from_config("config/default_fitzroy_hybrid.yaml")


def test_lcoa_nh3(result):
    expected = GOLDEN["lcoa"]["lc_nh3_s3_AE130"]
    assert result.lcoa.lc_nh3 == pytest.approx(expected, rel=1e-3)


def test_lcoa_h2(result):
    expected = GOLDEN["lcoa"]["lc_h2_s3_AE129"]
    assert result.lcoa.lc_h2 == pytest.approx(expected, rel=1e-3)


def test_replacement_schedule(result):
    assert result.stack_replace_years == {11, 21}
    assert result.battery_replace_years == {15}


@pytest.mark.parametrize("row", GOLDEN["s3_annual_profile"])
def test_annual_production(result, row):
    """Each cached year's H2/N2/NH3 (TPA) must match within 0.05%."""
    year = row["row"] - 8               # S3 profile row 9 == year 1
    got = next(a for a in result.annual if a["year"] == year)
    assert got["h2_tpa"] == pytest.approx(row["h2_tpa"], rel=5e-4)
    assert got["n2_tpa"] == pytest.approx(row["n2_tpa"], rel=5e-4)
    assert got["nh3_tpa"] == pytest.approx(row["nh3_tpa"], rel=5e-4)
