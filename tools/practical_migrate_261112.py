# -*- coding: utf-8 -*-
"""2026-11-12 녹화 회신 이전 — 허브 녹화 쪽이 **엑셀 파일을 직접 고친 것**을 집필 원고(02/practical)에 옮겨 담는다.

  venv\\Scripts\\python tools\\practical_migrate_261112.py "D:\\00work\\ocr-ouput261108-com2-practical" [--dry]

왜: 1부 빌드는 02/practical 의 JSON 에서 엑셀을 **처음부터 다시** 만든다. 엑셀만 고쳐 두면 다음 빌드에 사라진다.
무엇을(고친 문제.xlsx = _전달-261112-문제집/1-고친원천/06/practical/mNN/mNN_문제.xlsx 를 읽어):
  - 표 머리글 줄을 찾아 anchor 를 맞춘다(03 분석작업 두 줄 아래, 08 할증·할인 표 한 줄 위).
  - 표 칸 중 수식인 칸 → rows 에 「=…」 수식 문자열, 값이 바뀌거나 채워진 칸 → 그 값.
  - 표 안 글꼴 색·채우기 → styles(01·06회 색 기준 정렬).
  - 차트작업 문항 → given_chart(fix_source.py 의 CHARTS 와 같은 「지시 적용 전」 차트).
partN.json · 같은 묶음 문항 파일(sheets 공용) · 차트 문항 파일(given_chart)을 함께 쓴다(author.save_item 과 같은 방식).
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.atomic_io import atomic_write_text  # noqa: E402
from services.book import paths  # noqa: E402
from services.practical import author as pa  # noqa: E402
from services.practical import build as pb  # noqa: E402

# 회차 → (원본 범위, 종류, 제목) — 허브 쪽 fix_source.py CHARTS 그대로(지시 ①~⑤ 적용 전)
GIVEN = {
    1: ("A3:B11", "원형", None),
    2: ("B3:F10", "묶은 세로 막대형", None),
    3: ("B3:C9", "묶은 세로 막대형", "산지별 원두 수입량"),
    4: ("B3:B9,D3:E9", "묶은 세로 막대형", None),
    5: ("B3:H11", "묶은 세로 막대형", None),
    6: ("A3:B12", "원형", None),
    7: ("A3:D9", "묶은 세로 막대형", None),
    8: ("B3:C9", "묶은 세로 막대형", None),
    9: ("B4:B11,E4:F11", "묶은 세로 막대형", None),
    10: ("A3:D8", "묶은 세로 막대형", None),
}


def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _num(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def find_header(ws, t: dict) -> int:
    r0, c0 = pb.split_cell(t.get("anchor") or "A1")
    cols = [str(c).strip() for c in t.get("columns") or []]
    if len(cols) < 2:
        return r0
    for r in sorted(range(1, 80), key=lambda x: abs(x - r0)):
        if all(_txt(ws.Cells(r, c0 + j).Value) == cols[j] for j in range(min(len(cols), 4))):
            return r
    return 0


def migrate_table(ws, t: dict, log, tag: str) -> int:
    n = 0
    r0, c0 = pb.split_cell(t.get("anchor") or "A1")
    h = find_header(ws, t)
    if not h:
        log(f"  {tag} {t.get('anchor')} 머리글을 못 찾음 — 건너뜀")
        return 0
    if h != r0:
        t["anchor"] = f"{pb.col_name(c0)}{h}"
        log(f"  {tag} anchor {pb.col_name(c0)}{r0} → {t['anchor']}")
        n += 1
    styles = []
    ncol = len(t.get("columns") or [])
    for i, row in enumerate(t.get("rows") or [], 1):
        while len(row) < ncol:
            row.append(None)
        for j in range(len(row)):
            cell = ws.Cells(h + i, c0 + j)
            jv = row[j]
            if cell.HasFormula:
                f = str(cell.Formula)
                if jv != f:
                    row[j] = f
                    n += 1
            else:
                v = cell.Value
                if isinstance(jv, str) and jv.startswith("="):
                    row[j] = _num(v)
                    n += 1
                elif jv in (None, "") and isinstance(v, (int, float)):
                    # 숫자만 — 빈칸에 걸친 다른 표의 제목(「[표4] 결과」 등)은 그 표의 것이다
                    row[j] = _num(v)
                    log(f"  {tag} {pb.col_name(c0 + j)}{h + i} 빈칸 → {row[j]!r}")
                    n += 1
                elif isinstance(jv, (int, float)) and isinstance(v, (int, float)) and abs(float(jv) - float(v)) > 1e-9:
                    log(f"  {tag} {pb.col_name(c0 + j)}{h + i} {jv!r} → {v!r}")
                    row[j] = _num(v)
                    n += 1
                elif isinstance(jv, str) and isinstance(v, str) and jv.strip() != v.strip():
                    log(f"  {tag} {pb.col_name(c0 + j)}{h + i} {jv!r} → {v!r}")
                    row[j] = v
                    n += 1
            addr = f"{pb.col_name(c0 + j)}{h + i}"
            st = {}
            fc = int(cell.Font.Color or 0)
            if fc != 0:
                st["font_color"] = "#%02X%02X%02X" % (fc & 255, (fc >> 8) & 255, (fc >> 16) & 255)
            if int(cell.Interior.ColorIndex) != -4142:
                ic = int(cell.Interior.Color)
                st["fill"] = "#%02X%02X%02X" % (ic & 255, (ic >> 8) & 255, (ic >> 16) & 255)
            if st:
                styles.append({"range": addr, **st})
    if styles and styles != t.get("styles"):
        t["styles"] = styles
        log(f"  {tag} styles {len(styles)}칸 {[s['range'] for s in styles]}")
        n += 1
    return n


def migrate_round(xl, book: str, m: int, dry: bool, log) -> int:
    fixed = os.path.join(book, "_전달-261112-문제집", "1-고친원천", "06", "practical", f"m{m:02d}", f"m{m:02d}_문제.xlsx")
    wb = xl.Workbooks.Open(fixed, ReadOnly=True)
    total = 0
    try:
        names = [wb.Worksheets(i).Name for i in range(1, wb.Worksheets.Count + 1)]
        for p in (1, 2, 3, 4):
            pj = os.path.join(pa.round_dir(m), f"part{p}.json")
            with open(pj, encoding="utf-8") as fh:
                part = json.load(fh)
            n = 0
            for s in part.get("sheets") or []:
                nm = str(s.get("name") or "").strip()[:31]
                if nm not in names:
                    log(f"  {m:02d}-{p} 시트 없음: {nm}")
                    continue
                for t in s.get("tables") or []:
                    n += migrate_table(wb.Worksheets(nm), t, log, f"{m:02d}-{p} {nm}")
            if m == 3 and p == 3:
                # 03-3-02: 건당 단가 표가 머리 한 줄([B14] '건당 단가' · [C14] 빈칸)이라 변경 셀이 비었다 — 허브 쪽이 850 을 넣었다
                for s in part.get("sheets") or []:
                    for t in s.get("tables") or []:
                        if t.get("anchor") == "B14" and (t.get("columns") or [None])[0] == "건당 단가" \
                                and str((t.get("columns") + [""])[1]).strip() == "":
                            t["columns"] = ["건당 단가", "850"]
                            log("  03-3 분석작업-2 [C14] 건당 단가 850")
                            n += 1
            gc_items = []
            if p == 4 and m in GIVEN:
                rng, typ, title = GIVEN[m]
                g = {"range": rng, "type": typ, "title": title}
                for it in part.get("items") or []:
                    if "차트" in str(it.get("sheet") or "") and it.get("given_chart") != g:
                        it["given_chart"] = g
                        gc_items.append(int(it.get("no") or 0))
                        log(f"  {m:02d}-4-{int(it.get('no')):02d} given_chart {g}")
                        n += 1
            total += n
            if n and not dry:
                atomic_write_text(pj, json.dumps(part, ensure_ascii=False, indent=2))
                for f in glob.glob(os.path.join(pa.round_dir(m), f"{m:02d}-{p}-[0-9][0-9].json")):
                    with open(f, encoding="utf-8") as fh:
                        o = json.load(fh)
                    o["sheets"] = part.get("sheets") or []
                    no = int(o.get("no") or 0)
                    if no in gc_items:
                        o["given_chart"] = next(it["given_chart"] for it in part["items"] if int(it.get("no") or 0) == no)
                    atomic_write_text(f, json.dumps(o, ensure_ascii=False, indent=2))
    finally:
        wb.Close(False)
    return total


# ── 허브 쪽이 엑셀에서 아직 고치지 않은 것 — 원고(JSON)에서 직접 고친다(여러 번 돌려도 같은 결과) ──
def _save_part(m: int, p: int, part: dict) -> None:
    pj = os.path.join(pa.round_dir(m), f"part{p}.json")
    atomic_write_text(pj, json.dumps(part, ensure_ascii=False, indent=2))
    for f in glob.glob(os.path.join(pa.round_dir(m), f"{m:02d}-{p}-[0-9][0-9].json")):
        with open(f, encoding="utf-8") as fh:
            o = json.load(fh)
        o["sheets"] = part.get("sheets") or []
        it = next((x for x in part.get("items") or [] if int(x.get("no") or 0) == int(o.get("no") or 0)), None)
        if it:
            for k in pa.EDITABLE:
                if k in it:
                    o[k] = it[k]
        atomic_write_text(f, json.dumps(o, ensure_ascii=False, indent=2))


def _load_part(m: int, p: int) -> dict:
    with open(os.path.join(pa.round_dir(m), f"part{p}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _table(part: dict, sheet: str, anchor: str) -> dict:
    for s in part.get("sheets") or []:
        if s.get("name") == sheet:
            for t in s.get("tables") or []:
                if t.get("anchor") == anchor:
                    return t
    raise KeyError(f"{sheet} {anchor}")


def _item(part: dict, no: int) -> dict:
    return next(x for x in part.get("items") or [] if int(x.get("no") or 0) == no)


PIVOT_NOTE = ("※ 엑셀 버전에 따라 빈 셀이 '-' 대신 0 으로 보일 수 있습니다(엑셀 2016 확인). "
              "[피벗 테이블 옵션]의 '빈 셀 표시'에 - 가 들어 있으면 지시대로 한 것입니다.")


def manual_fixes(log) -> None:
    # 05·10 기본작업-3 — 머리글 「A」(원본 그림의 열 머리)를 떼고 첫 줄을 [A3] 에(지시 [A3:A14]·[A3:A15] 와 칸 수가 맞게)
    for m in (5, 10):
        part = _load_part(m, 1)
        t = _table(part, "기본작업-3", "A3")
        if t.get("columns") == ["A"] and t.get("rows"):
            first = t["rows"].pop(0)
            t["columns"] = [str(first[0])]
            _save_part(m, 1, part)
            log(f"  {m:02d}-1 기본작업-3 머리 「A」 뗌 → [A3] = {t['columns'][0][:20]}… ({len(t['rows']) + 1}줄)")
    # 03 기본작업-2 · 05 차트작업 제목 — 지시 메모 걷기
    part = _load_part(3, 1)
    t = _table(part, "기본작업-2", "A3")
    if "(" in str(t.get("title") or ""):
        t["title"] = "로스터리 카페 원두 월별 판매 현황"
        _save_part(3, 1, part)
        log("  03-1 기본작업-2 제목 메모 걷음")
    part = _load_part(5, 4)
    t = _table(part, "차트작업", "B3")
    if "(" in str(t.get("title") or ""):
        t["title"], t["title_cell"] = "시내버스 노선별 승객 만족도 조사", "B1"
        _save_part(5, 4, part)
        log("  05-4 차트작업 제목 메모 걷음 · [B1]")
    # 02 · 09 차트 제목 — 「[B1]/[B2] 셀과 연동」 자리에
    for m, anchor, cell in ((2, "B3", "B1"), (9, "B4", "B2")):
        part = _load_part(m, 4)
        t = _table(part, "차트작업", anchor)
        if t.get("title_cell") != cell:
            t["title_cell"] = cell
            _save_part(m, 4, part)
            log(f"  {m:02d}-4 차트작업 제목 → [{cell}]")
    # 09-4-02 ④ — 범례 서식에는 「둥근 모서리」가 없다(차트 영역에만) → 차트 영역으로
    part = _load_part(9, 4)
    it = _item(part, 2)
    ch = False
    for k, arr in (("instructions", it["instructions"]), ("steps", it["answer"]["steps"])):
        for i, x in enumerate(arr):
            if "둥근 모서리" in x and "범례" in x and "차트 영역" not in x:
                if k == "instructions":
                    arr[i] = ("④ 범례의 위치는 '위쪽'으로 지정하고, 범례 테두리는 '실선', 너비 '1.5pt'로 설정한 후, "
                              "차트 영역 테두리에 '둥근 모서리'를 설정하시오.")
                else:
                    arr[i] = ("⑩ [범례 서식]-[채우기 및 선]의 '테두리'에서 '실선'을 선택하고 '너비'를 1.5pt로 지정한다. "
                              "이어서 차트 영역을 선택하고 [차트 영역 서식]-[채우기 및 선]-[테두리] 아래쪽의 '둥근 모서리'를 체크한다.")
                ch = True
    if ch:
        _save_part(9, 4, part)
        log("  09-4-02 ④ 둥근 모서리 → 차트 영역")
    # 08-3-01 — 필터를 넣으면 엑셀이 필터를 [A19], 피벗 표를 [A21] 에 둔다(녹화 실측) → 결과 그림 행 번호
    part = _load_part(8, 3)
    it = _item(part, 1)
    f1 = next(f for f in it.get("figures") or [] if f.get("id") == "f-1")
    if f1.get("anchor") == "A21":
        f1["anchor"] = "A19"
        f1["caption"] = "피벗 테이블 결과 화면(19~26행)"
        for r in f1.get("rows") or []:
            if r and isinstance(r[0], (int, float)):
                r[0] = int(r[0]) - 2
        it["answer"]["steps"].insert(it["answer"]["steps"].index("{{f-2}}") + 1,
                                     "※ '고객유형'을 필터에 넣으면 엑셀이 필터를 [A19] 셀에, 피벗 테이블 표를 [A21] 셀부터 둡니다.")
        _save_part(8, 3, part)
        log("  08-3-01 결과 그림 19~26행 · 필터 위치 안내")
    # ── 다시 빌드한 뒤 원천 점검이 더 찾은 것(허브 회신 밖) ──
    # 02-1 기본작업-2: 머리글이 열 이름 A~H(원본 그림의 열 머리) → 1행이 한 줄씩 밀림. 제목 줄을 [A1] 로
    part = _load_part(2, 1)
    t = _table(part, "기본작업-2", "A1")
    if all(len(str(c)) == 1 for c in t.get("columns") or []) and t.get("rows"):
        first = t["rows"].pop(0)
        t["columns"] = [("" if v is None else v) for v in first]
        _save_part(2, 1, part)
        log("  02-1 기본작업-2 머리 A~H 뗌 → 제목 [A1]")
    # 06-1 기본작업-2·3: 「제목 행」 표가 머리 「A」 + 제목 한 줄 → [A1]='A', [A2]=제목 이 됨
    part = _load_part(6, 1)
    ch = False
    for sh in ("기본작업-2", "기본작업-3"):
        t = _table(part, sh, "A1")
        if t.get("columns") == ["A"] and len(t.get("rows") or []) == 1:
            t["columns"], t["rows"], t["title"] = [str(t["rows"][0][0])], [], ""
            ch = True
            log(f"  06-1 {sh} 제목 줄 「A」 뗌 → [A1]")
    if ch:
        _save_part(6, 1, part)
    # 03-1 기본작업-1·3 제목 메모
    part = _load_part(3, 1)
    ch = False
    for sh, anchor in (("기본작업-1", "A3"), ("기본작업-3", "A3")):
        t = _table(part, sh, anchor)
        if "(" in str(t.get("title") or ""):
            t["title"] = str(t["title"]).split("(")[0].strip()
            ch = True
            log(f"  03-1 {sh} 제목 메모 걷음 → {t['title']}")
    if ch:
        _save_part(3, 1, part)
    # 05-4 매크로작업 — 제목은 [A2] '하늘인쇄 3월 주문 내역'
    part = _load_part(5, 4)
    t = _table(part, "매크로작업", "A4")
    if "(" in str(t.get("title") or ""):
        t["title"], t["title_cell"] = "하늘인쇄 3월 주문 내역", "A2"
        _save_part(5, 4, part)
        log("  05-4 매크로작업 제목 → [A2]")
    # 기본작업-1 입력 문항 — 문제 파일은 비워 둔다(노트에 적힌 미리 입력된 부분만 남김)
    INPUT = {1: "all", 2: "all", 3: "all", 4: "all", 5: "data", 6: "all", 8: "all", 9: "all", 10: "body"}
    for m, mode in INPUT.items():
        part = _load_part(m, 1)
        ch = False
        for s in part.get("sheets") or []:
            if s.get("name") != "기본작업-1":
                continue
            for t in s.get("tables") or []:
                if m in (2, 6) and all(len(str(c)) == 1 for c in t.get("columns") or []) and t.get("rows"):
                    first = t["rows"].pop(0)
                    t["columns"] = [("" if v is None else v) for v in first]
                    t["title"] = ""
                    log(f"  {m:02d}-1 기본작업-1 머리 A~ 뗌 → 제목 [A1]")
                    ch = True
                if t.get("input") != mode:
                    t["input"] = mode
                    ch = True
                    log(f"  {m:02d}-1 기본작업-1 input={mode}")
        if ch:
            _save_part(m, 1, part)
    part = _load_part(2, 1)
    t = _table(part, "기본작업-3", "A1")
    if all(len(str(c)) == 1 for c in t.get("columns") or []) and t.get("rows"):
        first = t["rows"].pop(0)
        t["columns"] = [("" if v is None else v) for v in first]
        _save_part(2, 1, part)
        log("  02-1 기본작업-3 머리 A~H 뗌 → 제목 [A1]")
    # 02-1 기본작업-1·2·3 · 06-1 기본작업-1 — 「머리글」 자리에 시트 제목 줄이 들어간 표 → 제목 + 3행 머리글로
    #   (빌드 결과 칸은 같다. 원천 점검이 「지시 범위 [A3:H14] 첫 행 ≠ 머리글 행 1」 로 잘못 잡지 않게)
    for m, sheets_ in ((2, ("기본작업-1", "기본작업-2", "기본작업-3")), (6, ("기본작업-1",))):
        part = _load_part(m, 1)
        ch = False
        for sh in sheets_:
            t = _table(part, sh, "A1") if any(x.get("anchor") == "A1" for s_ in part["sheets"] if s_["name"] == sh
                                               for x in s_["tables"]) else None
            rows = (t or {}).get("rows") or []
            if t and len(rows) >= 2 and all(v in (None, "") for v in rows[0]) and all(v not in (None, "") for v in rows[1][:2]):
                t["title"] = str(t["columns"][0])
                t["columns"] = rows[1]
                t["rows"] = rows[2:]
                t["anchor"] = "A3"
                ch = True
                log(f"  {m:02d}-1 {sh} 제목 줄 + 3행 머리글로")
        if ch:
            _save_part(m, 1, part)
    # 08·10-3-01 — 「빈 셀 표시 -」 버전 차이 안내
    for m in (8, 10):
        part = _load_part(m, 3)
        st = _item(part, 1)["answer"]["steps"]
        if PIVOT_NOTE not in st:
            i = next(i for i, x in enumerate(st) if "빈 셀 표시" in x)
            st.insert(i + 1, PIVOT_NOTE)
            _save_part(m, 3, part)
            log(f"  {m:02d}-3-01 빈 셀 '-' 버전 안내")


def main() -> int:
    book = sys.argv[1]
    dry = "--dry" in sys.argv
    rounds = [int(x) for x in next((a for a in sys.argv[2:] if a[0].isdigit()), "1,2,3,4,5,6,7,8,9,10").split(",")]
    import pythoncom
    import win32com.client as w
    log = lambda s: print(s, flush=True)  # noqa: E731
    pythoncom.CoInitialize()
    xl = w.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        with paths.using_book(book):
            if "--manual" in sys.argv:
                log("[원고에서 직접 고칠 것]")
                manual_fixes(log)
                return 0
            for m in rounds:
                log(f"[{m:02d}회]")
                log(f"  → 바꾼 곳 {migrate_round(xl, book, m, dry, log)}" + (" (dry)" if dry else ""))
    finally:
        xl.Quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
