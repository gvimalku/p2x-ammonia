#!/usr/bin/env python3
"""Dump S3 economics: named-range map, CAPEX/OPEX left block, annual profile. READ-ONLY."""
from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

ROOT = Path(__file__).resolve().parent.parent
WORKBOOK = ROOT / "HySupply Ammonia Analysis Tool V1.0.xlsm"
OUT = ROOT / "data" / "raw_extract" / "economics.txt"
S3 = "S3. Levelised Cost Analysis"


def ftxt(v) -> str:
    if isinstance(v, ArrayFormula):
        return f"(array) {v.text}"
    return repr(v)


def main() -> None:
    wb_f = load_workbook(WORKBOOK, data_only=False, keep_vba=True)
    wb_v = load_workbook(WORKBOOK, data_only=True, keep_vba=True)
    lines: list[str] = []
    out = lines.append

    out("=" * 80)
    out("DEFINED NAMES -> destination")
    out("=" * 80)
    for name, dn in sorted(wb_f.defined_names.items()):
        try:
            dests = list(dn.destinations)
            dest_str = "; ".join(f"{s}!{c}" for s, c in dests) if dests else f"(formula) {dn.value}"
        except Exception:
            dest_str = f"(value) {dn.value}"
        out(f"  {name:28} -> {dest_str}")

    s3f, s3v = wb_f[S3], wb_v[S3]

    out("")
    out("=" * 80)
    out("S3 LEFT BLOCK  (col A label | col B formula & value)  rows 6..156")
    out("=" * 80)
    for r in range(6, 157):
        a = s3f[f"A{r}"].value
        bf = s3f[f"B{r}"].value
        bv = s3v[f"B{r}"].value
        if a in (None, "") and bf in (None, "") and bv in (None, ""):
            continue
        label = str(a).strip()[:44] if a else ""
        out(f"  B{r:<3} | {label:44} | f={ftxt(bf)}  v={bv!r}")

    out("")
    out("=" * 80)
    out("S3 ANNUAL PROFILE  cols D..R, rows 7..12 (headers + yr1,yr2) + row 43 (yr last)")
    out("=" * 80)
    for r in list(range(7, 13)) + [43]:
        out(f"\n-- row {r} --")
        for c in range(4, 19):  # D..R
            col = get_column_letter(c)
            f = s3f[f"{col}{r}"].value
            v = s3v[f"{col}{r}"].value
            if f in (None, "") and v in (None, ""):
                continue
            out(f"    {col}{r}: f={ftxt(f)}  v={v!r}")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT.relative_to(ROOT)} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
