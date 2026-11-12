# -*- coding: utf-8 -*-
"""두 실습파일 폴더(06/practical 형태)를 칸 단위로 대조 — 1부 빌드 결과가 손으로 고친 파일과 같은지 본다.

  venv\\Scripts\\python tools\\practical_diff_xlsx.py <기준 폴더> <비교 폴더> [1,2,3]

칸: 수식(둘 중 하나라도 수식이면 수식 글자) · 값(숫자는 1e-6) · 글꼴 색 · 채우기 색.
차트: 시트별 개수 · 종류 · 계열 수식.
"""
from __future__ import annotations

import os
import sys


def cell_map(ws) -> dict:
    out = {}
    ur = ws.UsedRange
    r0, c0 = ur.Row, ur.Column
    for r in range(r0, r0 + ur.Rows.Count):
        for c in range(c0, c0 + ur.Columns.Count):
            cl = ws.Cells(r, c)
            f = str(cl.Formula or "")
            fc = int(cl.Font.Color or 0)
            fill = int(cl.Interior.Color) if int(cl.Interior.ColorIndex) != -4142 else None
            if f == "" and fc == 0 and fill is None:
                continue
            v = cl.Value
            if hasattr(v, "year"):
                v = str(cl.Text)
            out[str(cl.Address).replace("$", "")] = (f if f.startswith("=") else None, v, fc, fill)
    return out


def charts(ws) -> list:
    out = []
    for i in range(1, ws.ChartObjects().Count + 1):
        ch = ws.ChartObjects(i).Chart
        ser = []
        for k in range(1, ch.SeriesCollection().Count + 1):
            try:
                ser.append(str(ch.SeriesCollection(k).Formula))
            except Exception:                   # noqa: BLE001
                ser.append("?")
        out.append((int(ch.ChartType), ch.HasTitle and str(ch.ChartTitle.Text) or "", tuple(ser)))
    return out


def same_v(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    return (a if a not in (None, "") else None) == (b if b not in (None, "") else None)


def diff_book(xl, a: str, b: str, xl2=None) -> list:
    # 이름이 같은 두 파일은 한 엑셀에 같이 못 연다 — 엑셀 둘
    wa, wb = xl.Workbooks.Open(a, ReadOnly=True), (xl2 or xl).Workbooks.Open(b, ReadOnly=True)
    out = []
    try:
        na = [wa.Worksheets(i).Name for i in range(1, wa.Worksheets.Count + 1)]
        nb = [wb.Worksheets(i).Name for i in range(1, wb.Worksheets.Count + 1)]
        if na != nb:
            out.append(f"시트 다름 {na} ≠ {nb}")
        for sh in [x for x in na if x in nb]:
            ma, mb = cell_map(wa.Worksheets(sh)), cell_map(wb.Worksheets(sh))
            for k in sorted(set(ma) | set(mb), key=lambda x: (len(x), x)):
                x, y = ma.get(k, (None, None, 0, None)), mb.get(k, (None, None, 0, None))
                if x[0] or y[0]:
                    if (x[0] or "") != (y[0] or ""):
                        out.append(f"{sh}!{k} 수식 {x[0] or x[1]!r} ≠ {y[0] or y[1]!r}")
                elif not same_v(x[1], y[1]):
                    out.append(f"{sh}!{k} 값 {x[1]!r} ≠ {y[1]!r}")
                if x[2] != y[2] or x[3] != y[3]:
                    out.append(f"{sh}!{k} 색 글꼴 {x[2]}/{y[2]} 채우기 {x[3]}/{y[3]}")
            ca, cb = charts(wa.Worksheets(sh)), charts(wb.Worksheets(sh))
            if len(ca) != len(cb):
                out.append(f"{sh} 차트 {len(ca)}개 ≠ {len(cb)}개")
            for p, q in zip(ca, cb):
                if p != q:
                    out.append(f"{sh} 차트 {p} ≠ {q}")
    finally:
        wa.Close(False)
        wb.Close(False)
    return out


def main() -> int:
    base, other = sys.argv[1], sys.argv[2]
    rounds = [int(x) for x in (sys.argv[3] if len(sys.argv) > 3 else "1,2,3,4,5,6,7,8,9,10").split(",")]
    import pythoncom
    import win32com.client as w
    pythoncom.CoInitialize()
    xl = w.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    xl2 = w.DispatchEx("Excel.Application")
    xl2.Visible = False
    xl2.DisplayAlerts = False
    total = 0
    try:
        for m in rounds:
            for kind in [k for k in ("문제", "정답") if os.environ.get("DIFF_KIND", k) == k]:
                fa = os.path.join(base, f"m{m:02d}", f"m{m:02d}_{kind}.xlsx")
                fb = os.path.join(other, f"m{m:02d}", f"m{m:02d}_{kind}.xlsx")
                d = diff_book(xl, fa, fb, xl2)
                total += len(d)
                print(f"[m{m:02d} {kind}] 차이 {len(d)}", flush=True)
                skip = os.environ.get("DIFF_SKIP", "")
                shown = [x for x in d if not (skip and x.startswith(skip + "!"))]
                print(f"    ({skip} 제외 {len(shown)})" if skip else "", flush=True)
                for x in shown[:200]:
                    print("   ", x, flush=True)
    finally:
        xl.Quit()
        xl2.Quit()
    print(f"합계 차이 {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
