#!/usr/bin/env python3
"""Dump the .text of the specific ARRAY formulas needed for the port. READ-ONLY."""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.worksheet.formula import ArrayFormula

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "HySupply Ammonia Analysis Tool V1.0.xlsm"

TARGETS = {
    "S1. Inputs": ["B19", "B25", "B146", "B164"],
    "A3. Conversion Factors": ["B26"],
    "S5. Working Data": [
        "C19", "C20", "E19", "F19", "G19",
        "M19", "M20", "N19", "N20",
        "S20", "T20", "W20", "Z19", "Z20",
        "AF19", "AF20", "AH20", "AI19", "AI20",
        "AK19", "AK20", "AO19", "AO20",
    ],
    "S3. Levelised Cost Analysis": ["I48", "P49", "Q49", "S49"],
}


def txt(v) -> str:
    if isinstance(v, ArrayFormula):
        return f"(array) {v.text}"
    return repr(v)


def main() -> None:
    wb = load_workbook(WORKBOOK, data_only=False, keep_vba=True)
    for sheet, refs in TARGETS.items():
        ws = wb[sheet]
        print(f"\n===== {sheet} =====")
        for ref in refs:
            print(f"  {ref}: {txt(ws[ref].value)}")


if __name__ == "__main__":
    main()
