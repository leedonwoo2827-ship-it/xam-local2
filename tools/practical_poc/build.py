"""실기(작업형) PoC — 회차 JSON 하나로 문제 파일 · 정답 파일 · 문제지 원고를 만들고 검증한다.

    venv\\Scripts\\python.exe tools\\practical_poc\\build.py tools\\practical_poc\\rounds\\c1-poc01.json

흐름
  1. seed 로 데이터를 만든다(시나리오별 생성기).
  2. 실제 엑셀(COM)로 정답을 적용한 통합 문서를 만들고 재계산한다.
  3. 엑셀이 낸 값을 **파이썬이 따로 계산한 값**과 대조한다(두 계산이 같아야 통과).
  4. 결과가 시시하면(필터 0행, 한쪽 분기만 등) seed 를 바꿔 다시 만든다.
  5. 통과하면 문제 파일(정답 칸 비움) · 정답 파일 · 문제지.md · verify.json 을 쓴다.

출력: data/practical_poc/<id>/ (data/ 는 git 에 올리지 않는다)
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

import win32com.client as w

REPO = Path(__file__).resolve().parents[2]
XL_FILTER_COPY = 2
XL_EXPRESSION = 2
XL_XLSX = 51
BLUE = 0xC07000          # 표준 색 - 파랑 RGB(0,112,192) → BGR 정수
COLORS = {"표준 색 - 파랑": BLUE}
EPOCH = dt.date(1899, 12, 30)


def serial(d: dt.date) -> int:
    return (d - EPOCH).days


# ── 1. 데이터 생성기 ──────────────────────────────────────────────────────
TITLES = {
    "KOR": ("문학", ["봄날의 정원", "바람의 지도", "작은 서점 이야기", "푸른 섬", "달빛 우체국", "겨울 기차"]),
    "ENG": ("외국어", ["실용 영어 회화", "여행 일본어", "기초 중국어", "비즈니스 영작", "스페인어 첫걸음"]),
    "SCI": ("과학", ["우주의 구조", "생활 속 화학", "곤충 관찰기", "기후와 바다", "빛의 과학"]),
    "HIS": ("역사", ["조선의 시장", "실크로드 여행", "근대 도시사", "고대 문명 산책"]),
    "ART": ("예술", ["색채의 이해", "사진 입문", "건축 스케치", "음악의 역사"]),
}
NAMES = ["김하늘", "이도윤", "박서연", "최민준", "정예린", "강지호", "윤서아", "임태현", "한지우", "오세빈",
         "신유나", "조현우", "배수아", "류건우", "문채원", "송다온", "황보민", "전시우", "홍예준", "남궁린"]


def gen_loans(rng: random.Random, n: int) -> list[list]:
    # 분포를 심는다 — 무작위에 맡기면 필터가 0행이 되거나 서식이 절반을 덮는다.
    #   3월 KOR 는 4~7건을 먼저 넣고, 나머지는 「3월이면서 KOR」 가 되지 않게 뽑는다.
    rows, used = [], set()
    planted = rng.randint(4, 7)
    while len(rows) < n:
        if len(rows) < planted:
            p, month = "KOR", 3
        else:
            p = rng.choices(list(TITLES), weights=[3, 2, 2, 2, 2])[0]
            month = rng.choice([2, 4]) if p == "KOR" else rng.choice([2, 3, 4])
        code = f"{p}-{rng.choices(['23', '24', '25'], weights=[1, 2, 2])[0]}-{rng.randint(1, 999):04d}"
        if code in used:
            continue
        used.add(code)
        loan = dt.date(2026, month, rng.randint(1, 28))
        due = loan + dt.timedelta(days=14)
        ret = loan + dt.timedelta(days=rng.choice([6, 9, 12, 13, 14, 14, 15, 16, 18, 19, 24, 29]))
        cnt = rng.randint(1, 3)
        fee = max(0, (ret - due).days) * 200 * cnt
        cat, titles = TITLES[p]
        rows.append([code, loan, due, ret, cat, rng.choice(titles), cnt, fee])
    rows.sort(key=lambda r: (r[1], r[0]))
    return rows


def gen_members(rng: random.Random, n: int) -> list[list]:
    # 열람실 × 월(3~5) 9칸이 모두 1건 이상이어야 평균이 #DIV/0! 이 안 난다 — 먼저 한 건씩 깐다.
    cells = [(room, m) for room in ["1관", "2관", "3관"] for m in [3, 4, 5]]
    rows, used = [], set()
    while len(rows) < n:
        mid = f"{rng.choice(['BK', 'LB', 'RD'])}{rng.choice(['24', '25'])}-{rng.randint(1, 999):04d}"
        if mid in used:
            continue
        used.add(mid)
        room, m = cells[len(rows)] if len(rows) < len(cells) else rng.choice(cells)
        loan = dt.date(2026, m, rng.randint(1, 28))
        rows.append([mid, rng.choice(NAMES), room, loan, rng.randint(0, 12)])
    rng.shuffle(rows)
    return rows


GENERATORS = {"loans": gen_loans, "members": gen_members}


# ── 2. 파이썬 쪽 정답(엑셀과 따로 계산) ──────────────────────────────────
def ref_filter_mar_kor(data):
    return [r[0] for r in data["기본작업"] if r[1].month == 3 and r[0].startswith("KOR")]


def ref_cf_late_or_23(data):
    return [i for i, r in enumerate(data["기본작업"]) if (r[3] - r[1]).days >= 21 or r[0][4:6] == "23"]


def ref_new_id(data):
    out = []
    for r in data["계산작업"]:
        mid = r[0]
        out.append("VIP" + mid[2:] if int(mid[-4:]) >= 500 else mid.lower())
    return out


def ref_avg_room_month(data):
    grid = []
    for room in ["1관", "2관", "3관"]:
        line = []
        for m in [3, 4, 5]:
            v = [r[4] for r in data["계산작업"] if r[2] == room and r[3].month == m]
            line.append((sum(v) / len(v)) if v else None)
        grid.append(line)
    return grid


# ── 3. 엑셀로 통합 문서 만들기 ───────────────────────────────────────────
def to_cell(v):
    return serial(v) if isinstance(v, dt.date) else v


def write_sheet(ws, sh: dict, rows: list[list]) -> None:
    ws.Range(sh["title_cell"]).Value = sh["title"]
    hr = sh["header_row"]
    cols = sh["columns"]
    last_col = chr(ord("A") + len(cols) - 1)
    ws.Range(f"A{hr}:{last_col}{hr}").Value = [cols]
    body = [[to_cell(v) for v in r] + [None] * (len(cols) - len(r)) for r in rows]
    top, bot = hr + 1, hr + len(rows)
    ws.Range(f"A{top}:{last_col}{bot}").Value = body
    for j, v in enumerate(rows[0]):
        if isinstance(v, dt.date):
            c = chr(ord("A") + j)
            ws.Range(f"{c}{top}:{c}{bot}").NumberFormat = "yyyy-mm-dd"
    if sh.get("extra") == "avg_table":
        ws.Range("H1").Value = "[표2] 열람실별 월별 평균 연체일수"
        ws.Range("H2:K2").Value = [["열람실", 3, 4, 5]]
        ws.Range("I2:K2").NumberFormat = '0"월"'
        ws.Range("H3:H5").Value = [["1관"], ["2관"], ["3관"]]
    ws.Columns.AutoFit()


def apply_answer(ws, it: dict) -> None:
    a = it["answer"]
    if it["kind"] == "advanced_filter":
        c0 = a["criteria_range"].split(":")[0]
        col, row = c0[0], int(c0[1:])
        ws.Range(f"{col}{row}").Value = a["criteria"][0]
        ws.Range(f"{col}{row + 1}").Formula = a["criteria"][1]
        dst = a["copy_to"]
        end = chr(ord(dst[0]) + len(a["copy_columns"]) - 1)
        hdr = ws.Range(f"{dst}:{end}{dst[1:]}")
        hdr.Value = [a["copy_columns"]]
        ws.Range(a["list_range"]).AdvancedFilter(XL_FILTER_COPY, ws.Range(a["criteria_range"]), hdr, False)
    elif it["kind"] == "conditional_format":
        fc = ws.Range(a["applies_to"]).FormatConditions.Add(XL_EXPRESSION, None, a["formula"])
        fc.Font.Bold = a["font"]["bold"]
        fc.Font.Color = COLORS[a["font"]["color"]]
    elif it["kind"] == "formula":
        rng = ws.Range(a["range"])
        if a["array"]:
            first = rng.Cells(1, 1)
            first.FormulaArray = a["formula"]
            r1c1 = first.FormulaR1C1          # 상대 참조는 R1C1 로 옮기면 칸마다 저절로 맞는다
            for c in rng:
                c.FormulaArray = r1c1
        else:
            rng.Formula = a["formula"]
        if a.get("number_format"):
            rng.NumberFormat = a["number_format"]
    else:
        raise ValueError(f"모르는 kind: {it['kind']}")


def is_xl_error(v) -> bool:
    return isinstance(v, int) and v < -2146820000


# ── 4. 대조 ──────────────────────────────────────────────────────────────
def verify(ws_by_name, data, it) -> dict:
    ref, chk = it["check"]["ref"], it["check"]
    ws = ws_by_name[it["sheet"]]
    res = {"no": it["no"], "kind": it["kind"], "ok": True, "notes": []}

    def fail(msg):
        res["ok"] = False
        res["notes"].append(msg)

    if ref == "filter_mar_kor":
        exp = ref_filter_mar_kor(data)
        top = ws.Range(it["answer"]["copy_to"]).Row + 1
        got = []
        while ws.Cells(top + len(got), 1).Value not in (None, ""):
            got.append(ws.Cells(top + len(got), 1).Value)
        res.update(expected=exp, excel=got)
        if got != exp:
            fail("엑셀 필터 결과와 파이썬 계산이 다르다")
        if not chk["rows_min"] <= len(exp) <= chk["rows_max"]:
            fail(f"결과 {len(exp)}행 — {chk['rows_min']}~{chk['rows_max']}행이어야 문제답다")
    elif ref == "cf_late_or_23":
        exp = ref_cf_late_or_23(data)
        top = 4
        got = [i for i in range(len(data["기본작업"])) if ws.Cells(top + i, 1).DisplayFormat.Font.Bold]
        res.update(expected=[top + i for i in exp], excel=[top + i for i in got])
        if got != exp:
            fail("엑셀이 서식을 입힌 행과 파이썬 계산이 다르다")
        if not chk["rows_min"] <= len(exp) <= chk["rows_max"]:
            fail(f"해당 {len(exp)}행 — {chk['rows_min']}~{chk['rows_max']}행이어야 문제답다")
    elif ref == "new_id":
        exp = ref_new_id(data)
        got = [r[0] for r in ws.Range(it["answer"]["range"]).Value]
        res.update(excel_sample=got[:5], expected_sample=exp[:5])
        if got != exp:
            fail("변경ID 가 다르다")
        vip = sum(1 for v in exp if v.startswith("VIP"))
        if min(vip, len(exp) - vip) < chk["each_branch_min"]:
            fail(f"분기 치우침 — VIP {vip} / 소문자 {len(exp) - vip}")
    elif ref == "avg_room_month":
        exp = ref_avg_room_month(data)
        got = [list(r) for r in ws.Range(it["answer"]["range"]).Value]
        res.update(expected=exp, excel=got)
        for i, line in enumerate(exp):
            for j, e in enumerate(line):
                g = got[i][j]
                if e is None:
                    fail(f"표본 0개 칸({i},{j}) — 엑셀은 #DIV/0! 이 난다")
                elif is_xl_error(g) or abs(g - e) > 1e-9:
                    fail(f"칸({i},{j}) 엑셀 {g} ≠ 파이썬 {e}")
        cells = list(ws.Range(it["answer"]["range"]))
        if not all(c.HasArray for c in cells):
            fail("배열 수식이 아닌 칸이 있다")
    else:
        fail(f"모르는 검증: {ref}")
    return res


# ── 5. 문제지 원고 ────────────────────────────────────────────────────────
def problem_md(rd: dict) -> str:
    out = [f"# {rd['label']}", "", f"> 시나리오: {rd['scenario']['domain']}", ""]
    part = None
    for it in rd["items"]:
        if it["part"] != part:
            part = it["part"]
            pts = sum(x["points"] for x in rd["items"] if x["part"] == part)
            out += [f"## 문제 {part}  {it['part_name']}({pts}점 · PoC 발췌)", ""]
        out.append(f"**{it['no'].split('-')[1]}. {it['lead']} ({it['points']}점)**")
        out += [f"- ▶ {s}" for s in it["instructions"]]
        out.append("")
    out += ["---", "", "## 정답", ""]
    for it in rd["items"]:
        a = it["answer"]
        if it["kind"] == "advanced_filter":
            s = f"[{a['criteria_range'].split(':')[0][0]}{int(a['criteria_range'].split(':')[0][1:]) + 1}] `{a['criteria'][1]}` · 목록 {a['list_range']} · 복사 위치 {a['copy_to']}"
        elif it["kind"] == "conditional_format":
            s = f"{a['applies_to']} · `{a['formula']}` · 굵게 · {a['font']['color']}"
        else:
            f = "{" + a["formula"] + "}" if a["array"] else a["formula"]
            s = f"{a['range']} · `{f}`"
        out.append(f"- {it['no']} {s}")
    return "\n".join(out) + "\n"


# ── 실행 ──────────────────────────────────────────────────────────────────
def build_once(xl, rd: dict, seed: int, out_dir: Path, save: bool):
    rng = random.Random(seed)
    data = {sh["name"]: GENERATORS[sh["gen"]](rng, sh["rows"]) for sh in rd["sheets"]}

    def new_wb():
        wb = xl.Workbooks.Add()
        while wb.Worksheets.Count < len(rd["sheets"]):
            wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
        for i, sh in enumerate(rd["sheets"], 1):
            ws = wb.Worksheets(i)
            ws.Name = sh["name"]
            write_sheet(ws, sh, data[sh["name"]])
        return wb

    wb = new_wb()
    by = {sh["name"]: wb.Worksheets(sh["name"]) for sh in rd["sheets"]}
    for it in rd["items"]:
        apply_answer(by[it["sheet"]], it)
    xl.CalculateFull()
    results = [verify(by, data, it) for it in rd["items"]]
    ok = all(r["ok"] for r in results)
    if ok and save:
        for sh in rd["sheets"]:
            by[sh["name"]].Columns.AutoFit()
        wb.SaveAs(str(out_dir / f"{rd['id']}_정답.xlsx"), XL_XLSX)
    wb.Close(False)
    if ok and save:
        wb2 = new_wb()
        wb2.SaveAs(str(out_dir / f"{rd['id']}.xlsx"), XL_XLSX)
        wb2.Close(False)
    return ok, results


def main(path: str) -> int:
    rd = json.loads(Path(path).read_text(encoding="utf-8"))
    out_dir = REPO / "data" / "practical_poc" / rd["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    xl = w.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    tries = []
    try:
        for k in range(12):
            seed = rd["seed"] + k
            ok, results = build_once(xl, rd, seed, out_dir, save=False)
            tries.append({"seed": seed, "ok": ok,
                          "fails": [f"{r['no']}: {n}" for r in results for n in r["notes"]]})
            print(f"seed {seed}: {'통과' if ok else '탈락'}", *tries[-1]["fails"], sep="\n  ")
            if ok:
                build_once(xl, rd, seed, out_dir, save=True)
                break
        else:
            print("12번 안에 통과하는 데이터를 못 만들었다")
            return 1
    finally:
        xl.Quit()
    (out_dir / "문제지.md").write_text(problem_md(rd), encoding="utf-8")
    report = {"id": rd["id"], "seed": seed, "tries": tries, "items": results}
    (out_dir / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("→", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "rounds" / "c1-poc01.json")))
