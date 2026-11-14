#!/usr/bin/env python3
"""Dump the exact formulas we need to port, into data/raw_extract/formulas.txt (provenance).

READ-ONLY. Developer aid for the faithful port of sizing, thresholds and the hourly engine.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "HySupply Ammonia Analysis Tool V1.0.xlsm"
OUT = ROOT / "data" / "raw_extract" / "formulas.txt"

S1 = "S1. Inputs"
S3 = "S3. Levelised Cost Analysis"
S5 = "S5. Working Data"
A3 = "A3. Conversion Factors"


def main() -> None:
    wb_f = load_workbook(WORKBOOK, data_only=False, keep_vba=True)   # formulas
    wb_v = load_workbook(WORKBOOK, data_only=True, keep_vba=True)    # cached values
    lines: list[str] = []

    def emit(s: str = "") -> None:
        lines.append(s)

    def dump_cell(ws_f, ws_v, ref: str, label: str = "") -> None:
        f = ws_f[ref].value
        v = ws_v[ref].value
        lab = f"  [{label}]" if label else ""
        emit(f"  {ref:>5}{lab}: formula={f!r}  value={v!r}")

    # --- S1 sizing / calc cells (rows 4..191): label in A, formula/value in B ---
    emit("=" * 80)
    emit("S1. Inputs  (col A label | col B formula & cached value)   rows 4..191")
    emit("=" * 80)
    s1f, s1v = wb_f[S1], wb_v[S1]
    for r in range(4, 192):
        a = s1f[f"A{r}"].value
        bf = s1f[f"B{r}"].value
        bv = s1v[f"B{r}"].value
        if a in (None, "") and bf in (None, "") and bv in (None, ""):
            continue
        label = str(a).strip() if a else ""
        emit(f"  B{r:<3} | {label[:46]:46} | f={bf!r}  v={bv!r}")

    # --- A3 power-region thresholds & stoichiometry (rows 5..27) ---
    emit("")
    emit("=" * 80)
    emit("A3. Conversion Factors  (rows 5..27)")
    emit("=" * 80)
    a3f, a3v = wb_f[A3], wb_v[A3]
    for r in range(5, 28):
        a = a3f[f"A{r}"].value
        bf = a3f[f"B{r}"].value
        bv = a3v[f"B{r}"].value
        if a in (None, "") and bf in (None, "") and bv in (None, ""):
            continue
        label = str(a).strip() if a else ""
        emit(f"  B{r:<3} | {label[:40]:40} | f={bf!r}  v={bv!r}")

    # --- S5 hourly engine: header row 18, seed row 19, recurrence row 20, cols B..AZ ---
    emit("")
    emit("=" * 80)
    emit("S5. Working Data  (per column: header row18 | seed row19 | recurrence row20)")
    emit("cols B..AZ (2..52). Row 19 = first hour (seed); row 20 = general hour (copied down).")
    emit("=" * 80)
    s5f, s5v = wb_f[S5], wb_v[S5]
    for c in range(2, 53):  # B..AZ
        col = get_column_letter(c)
        h = s5f[f"{col}18"].value
        f19 = s5f[f"{col}19"].value
        f20 = s5f[f"{col}20"].value
        if h in (None, "") and f19 in (None, "") and f20 in (None, ""):
            continue
        emit(f"\n--- col {col} | header: {str(h).strip()!r}")
        emit(f"    row19: {f19!r}")
        emit(f"    row20: {f20!r}")

    # --- S5 summary band rows 11..14 for a few key columns (avg/total/min/max) ---
    emit("")
    emit("=" * 80)
    emit("S5 summary band (rows 11=avg,12=total,13=min,14=max) key cols")
    emit("=" * 80)
    for col in ("C", "D", "E", "F", "G", "M", "N", "R", "V", "AD", "AE", "AF", "AP", "AQ", "AR", "AS", "AU"):
        parts = []
        for r in (11, 12, 13, 14):
            parts.append(f"{r}={s5f[f'{col}{r}'].value!r}")
        emit(f"  col {col}: " + " | ".join(parts))

    # --- S3 right-block schedule anchors: rows 48 (year0 CAPEX), 49 (year1), 92, 129, 130 ---
    emit("")
    emit("=" * 80)
    emit("S3 schedule anchors: row48 (yr0 CAPEX), row49 (yr1), row92 (disc yr0), 129/130 (LCOA)")
    emit("cols F..AE (6..31)")
    emit("=" * 80)
    s3f = wb_f[S3]
    from openpyxl.utils import get_column_letter as gcl
    for r in (47, 48, 49, 91, 92, 93, 128, 129, 130):
        emit(f"\n-- S3 row {r} --")
        for c in range(6, 32):
            col = gcl(c)
            val = s3f[f"{col}{r}"].value
            if val not in (None, ""):
                emit(f"    {col}{r}: {val!r}")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT.relative_to(ROOT)} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
