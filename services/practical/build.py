# -*- coding: utf-8 -*-
"""1부 빌드(실기) — 실기 집필 결과로 **실습파일 · 그림 · 검증**을 만든다.

  06/practical/mNN/mNN_문제.xlsx    시트 자료만 깐 문제 파일(수험자가 받는 것)
  06/practical/mNN/mNN_정답.xlsx    모범답안 수식을 넣고 재계산한 정답 파일
  06/practical/mNN/verify.json      문항마다 엑셀 계산값 ↔ 집필이 적은 결과값 대조
  02/practical/mNN/images/*.png     그림 설계(표·대화상자·차트)를 새로 그린 PNG — 원고 MD 가 이것을 부른다

★ 사용자 결정(2026-11-09): 「1부 빌드」 자리에 둔다. 실기에서는 e-test 발행(객관식 전제)을 숨긴다.
★ 원본 그림(출판사 저작물)은 쓰지 않는다 — 그림은 집필이 남긴 **설계**로 새로 그린다.
★ 검증은 계산작업처럼 **결과값이 셀 주소로 적힌** 문항만 기계로 본다. 서식·필터·피벗·차트처럼
  값으로 대조할 수 없는 문항은 「사람 확인」 으로 남긴다(거짓 통과를 만들지 않는다).
★ 이 PC 는 Office 2019 — 2021 전용 함수(XLOOKUP·FILTER·LET 등)가 나오면 #NAME? 이 되고,
  그것은 「검증 불가(2019)」 로 따로 표시한다(틀린 답으로 세지 않는다).
★ 차트 그림은 설계(종류·범위·제목·범례·계열)대로 엑셀이 정답 파일에 차트를 만들어 PNG 로 내보낸다.
  세부 서식(글꼴·색상표·쪼개진 요소·그림자)은 아직 옮기지 않는다 — 대화상자 그림은 설계 카드다.
"""
from __future__ import annotations

import datetime as dt
import glob
import html
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from core.atomic_io import atomic_write_text
from services.book import paths
from services.practical import author as pa

XL_XLSX = 51
CELL_RE = re.compile(r"^\$?([A-Z]{1,3})\$?(\d{1,7})$")
NEW_FUNCS = ("XLOOKUP", "XMATCH", "FILTER", "SORT(", "SORTBY", "UNIQUE", "SEQUENCE", "LET(", "LAMBDA", "TEXTJOIN", "IFS(", "SWITCH(", "CONCAT(", "MAXIFS", "MINIFS")


def out_dir(m: int) -> str:
    return os.path.join(paths.book_dir(), "06", "practical", f"m{m:02d}")


def img_dir(m: int) -> str:
    return os.path.join(pa.round_dir(m), "images")


# ── 셀 주소 ───────────────────────────────────────────────────────────────
def col_num(s: str) -> int:
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - 64)
    return n


def col_name(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def split_cell(a: str) -> Tuple[int, int]:
    m = CELL_RE.match(a.strip().upper())
    if not m:
        raise ValueError(f"셀 주소가 아닙니다: {a}")
    return int(m.group(2)), col_num(m.group(1))


# ── 회차 읽기 ─────────────────────────────────────────────────────────────
def load_round(m: int) -> List[dict]:
    """part1~4.json — 문항 파일의 교정이 part 에 같이 들어가 있다(author.save_item)."""
    parts = []
    for p in (1, 2, 3, 4):
        f = os.path.join(pa.round_dir(m), f"part{p}.json")
        if os.path.isfile(f):
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            d["part"] = p
            parts.append(d)
    return parts


def sheets_of(parts: List[dict]) -> List[dict]:
    """시트 이름 순서 그대로, 같은 이름은 표를 합친다."""
    order, by = [], {}
    for d in parts:
        for s in d.get("sheets") or []:
            name = str(s.get("name") or "").strip()[:31] or f"시트{len(order) + 1}"
            if name not in by:
                by[name] = {"name": name, "tables": []}
                order.append(name)
            by[name]["tables"].extend(s.get("tables") or [])
    return [by[n] for n in order]


# ── 엑셀 쓰기 ─────────────────────────────────────────────────────────────
def _put(cell, v) -> None:
    """값 하나 — 문자열은 사람이 쳐 넣은 것처럼(날짜·시간·백분율이 엑셀 값이 되게)."""
    if v is None or v == "":
        return
    if isinstance(v, bool):
        cell.Value = v
    elif isinstance(v, (int, float)):
        cell.Value = v
    else:
        s = str(v)
        # ★ 「=C4*C5+C6」 처럼 시트 자료에 수식이 오면 **수식으로** 넣는다 — 시나리오·데이터 표·목표값 찾기
        #   문항은 시트에 수식이 있어야 성립한다(05-3-02 실측: 글자로 넣었더니 결과 칸이 수식 글자가 됐다).
        try:
            cell.Formula = s
        except Exception:                       # noqa: BLE001 — 엑셀이 못 받는 수식이면 글자로
            cell.Formula = "'" + s


def write_table(ws, t: dict) -> None:
    r0, c0 = split_cell(t.get("anchor") or "A1")
    title = str(t.get("title") or "").strip()
    if title:
        # 「[표1] …」·「<…>」 같은 표 머리는 표 바로 위, 시트 제목은 A1
        if re.match(r"^[\[<(]", title) and r0 > 1:
            _put(ws.Cells(r0 - 1, c0), title)
        elif r0 > 1 and not ws.Cells(1, 1).Value:
            _put(ws.Cells(1, 1), title)
    cols = t.get("columns") or []
    rows = t.get("rows") or []
    if not rows and len(cols) == 1:             # 열 하나·행 없음 = 제목 한 줄
        _put(ws.Cells(r0, c0), cols[0])
        return
    for j, h in enumerate(cols):
        _put(ws.Cells(r0, c0 + j), h)
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row or []):
            _put(ws.Cells(r0 + i, c0 + j), v)


def new_workbook(xl, sheets: List[dict]):
    wb = xl.Workbooks.Add()
    while wb.Worksheets.Count < max(1, len(sheets)):
        wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
    for i, sh in enumerate(sheets, 1):
        ws = wb.Worksheets(i)
        ws.Name = sh["name"]
        for t in sh["tables"]:
            write_table(ws, t)
        ws.Columns.AutoFit()
    wb.Worksheets(1).Activate()
    return wb


CRIT_RE = re.compile(r"\[([A-Z]{1,3}\d{1,7})(?::[A-Z]{1,3}\d{1,7})?\][^\n]{0,30}?(?:영역|셀)에[^\n]*조건")
TOKLINE = re.compile(r"^\{\{(f-\d+)\}\}$")


def apply_criteria(ws, it: dict) -> List[str]:
    """「[K17:K18] 영역에 〈그림〉과 같이 조건을 입력한다」 + 바로 뒤 표 그림 → 그 표를 조건 칸에 쓴다.
    ★ DSUM·DAVERAGE·고급 필터의 조건은 수험자가 **입력하는 값**이라 수식 목록에 없다(02-2-04 · 03-2-05 실측).
      그림 설계의 표(columns·rows)가 곧 그 값이다."""
    figs = {f.get("id"): f for f in it.get("figures") or []}
    steps = [str(x).strip() for x in (it.get("answer") or {}).get("steps") or []]
    done = []
    for i, line in enumerate(steps):
        m = CRIT_RE.search(line)
        if not m:
            continue
        nxt = next((TOKLINE.match(x) for x in steps[i + 1:i + 3] if TOKLINE.match(x)), None)
        f = figs.get(nxt.group(1)) if nxt else None
        if not f or f.get("kind") != "table" or not f.get("columns"):
            continue
        cols = list(f["columns"])
        rows = f.get("rows") or []
        # 그림 표에 행 번호·열 머리(A·B…) 같은 화면 장식이 붙어 있으면 뗀다
        if cols and str(cols[0]).strip() in ("", "행") and rows and all(isinstance(r, list) and r for r in rows):
            cols, rows = cols[1:], [r[1:] for r in rows]
        r0, c0 = split_cell(m.group(1))
        if all(re.fullmatch(r"[A-Z]{1,3}", str(c).strip()) for c in cols):
            cols = []                        # 머리 줄이 열 이름(K·L…)뿐이면 화면 장식 — 값은 rows 부터
            r0 -= 1
        for j, h in enumerate(cols):
            _put(ws.Cells(r0, c0 + j), h)
        for k, row in enumerate(rows, 1):
            for j, v in enumerate(row or []):
                _put(ws.Cells(r0 + k, c0 + j), v)
        done.append(m.group(1))
    return done


def apply_formulas(ws, a: dict) -> List[str]:
    """모범답안 수식 — 첫 셀에 넣고 채우기 영역으로 복사(채우기 핸들과 같은 상대 참조).
    ★ 「{=TABLE(…)}」(데이터 표)은 수식이 아니라 기능이다 — 넣지 않는다(그 문항은 사람 확인)."""
    done = []
    for f in a.get("formulas") or []:
        if not isinstance(f, dict) or not f.get("cell") or not str(f.get("formula") or "").startswith("="):
            continue
        c = ws.Range(f["cell"])
        c.Formula = f["formula"]
        if f.get("fill") and str(f["fill"]).upper() != str(f["cell"]).upper():
            c.Copy(ws.Range(f["fill"]))
        done.append(f["cell"])
    return done


# ── 대조 ──────────────────────────────────────────────────────────────────
def _norm(v) -> Any:
    if hasattr(v, "year") and hasattr(v, "month"):
        try:
            if getattr(v, "hour", 0) or getattr(v, "minute", 0) or getattr(v, "second", 0):
                if v.year <= 1900:
                    return f"{v.hour}:{v.minute:02d}:{v.second:02d}"
            return f"{v.year:04d}-{v.month:02d}-{v.day:02d}"
        except Exception:                       # noqa: BLE001
            return str(v)
    return v


def _num(x) -> Optional[float]:
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    try:
        if s.endswith("%"):
            return float(s[:-1]) / 100
        return float(s)
    except ValueError:
        return None


def _decimals(w) -> Optional[int]:
    """「1,246」 → 0, 「12.5%」 → 1(백분율), 「0.83」 → 2. 숫자 글자가 아니면 None."""
    s = str(w).strip().replace(",", "")
    m = re.fullmatch(r"-?\d+(?:\.(\d+))?(%?)", s)
    if not m:
        return None
    d = len(m.group(1) or "")
    return d + 2 if m.group(2) else d


def same(got, want, text: str = "") -> bool:
    """엑셀 값(got)·표시 글자(text) ↔ 집필이 적은 값(want).
    ★ 집필은 결과를 **표시된 모양**으로 적기도 한다(「2,255」·「420건」·「2026년 3월 2일 월요일」) —
      값으로도, 표시 글자로도 비교하고, 숫자 글자면 그 자릿수로 반올림해 비교한다."""
    g, w = _norm(got), want
    if text and str(text).strip() == str(w).strip():
        return True
    gn, wn = _num(g), _num(w)
    if gn is not None and wn is not None:
        if abs(gn - wn) <= max(1e-4, abs(wn) * 1e-4) or round(gn, 2) == round(wn, 2):
            return True
        d = _decimals(w) if isinstance(w, str) else None
        if d is not None:
            return round(gn, d) == round(wn, d)
        if isinstance(w, (int, float)) and float(w).is_integer():
            return round(gn) == wn             # 정수로 적었으면 표시 형식(#,##0)으로 반올림된 값
        return False
    return str(g).strip() == str(w).strip()


def is_xl_error(v) -> bool:
    return isinstance(v, int) and v < -2146820000


def covered(ws, a: dict) -> set:
    """모범답안 수식이 닿는 셀(첫 셀 + 채우기 영역) — 대조는 여기서만 한다."""
    out = set()
    for f in a.get("formulas") or []:
        if not isinstance(f, dict) or not f.get("cell") or not str(f.get("formula") or "").startswith("="):
            continue
        for ref in (f.get("cell"), f.get("fill")):
            if not ref:
                continue
            try:
                for c in ws.Range(str(ref)).Cells:
                    out.add(str(c.Address).replace("$", ""))
            except Exception:                   # noqa: BLE001
                continue
    return out


def check_item(ws, it: dict) -> dict:
    a = it.get("answer") or {}
    res = a.get("results") or {}
    cover = covered(ws, a)
    cells = {k: v for k, v in res.items()
             if CELL_RE.match(str(k).strip().upper()) and str(k).strip().upper().replace("$", "") in cover}
    out = {"no": it.get("no"), "sheet": it.get("sheet"), "checked": 0, "ok": 0, "fails": [], "status": ""}
    if not cells:
        # 서식·필터·피벗·시나리오·통합·차트 — 수식이 아니라 **기능을 실행한 결과**라 값 대조를 하지 않는다
        out["status"] = "사람 확인"
        return out
    new = any(n in json.dumps(a.get("formulas") or [], ensure_ascii=False).upper() for n in NEW_FUNCS)
    for k, want in cells.items():
        got = ws.Range(k).Value
        try:
            text = ws.Range(k).Text
        except Exception:                       # noqa: BLE001
            text = ""
        out["checked"] += 1
        if is_xl_error(got):
            out["fails"].append({"cell": k, "want": want, "got": "#오류", "why": "엑셀 오류"})
        elif same(got, want, text):
            out["ok"] += 1
        else:
            out["fails"].append({"cell": k, "want": want, "got": _norm(got)})
    out["status"] = ("통과" if not out["fails"] else "검증 불가(2019)" if new else "불일치")
    return out


# ── 그림 ──────────────────────────────────────────────────────────────────
FIG_CSS = """body{margin:0;font-family:'Malgun Gothic',sans-serif;background:#fff}
.box{display:inline-block;padding:10px;background:#fff}
table{border-collapse:collapse;font-size:13px}
td,th{border:1px solid #9aa;padding:3px 8px;white-space:nowrap}
th{background:#e8eef4;font-weight:700}
.cap{font-size:12px;color:#555;margin:0 0 6px}
.dlg{width:520px;border:1px solid #889;border-radius:4px;box-shadow:0 2px 8px #0002;font-size:13px}
.dlg .bar{background:#f0f2f5;padding:7px 10px;font-weight:700;border-bottom:1px solid #ccd}
.dlg .body{padding:12px 14px;line-height:1.75;white-space:pre-wrap}
.dlg .ok{text-align:right;padding:0 14px 12px}
.dlg .ok span{display:inline-block;border:1px solid #3a6ea5;background:#e8f0fb;padding:3px 18px;border-radius:3px}
.chart{width:520px;border:1px dashed #889;padding:12px;font-size:13px;line-height:1.7;white-space:pre-wrap}"""


def fig_html(f: dict) -> str:
    e = html.escape
    cap = f"<p class='cap'>{e(f.get('caption') or '')}</p>"
    k = f.get("kind")
    if k == "table" and f.get("columns"):
        head = "".join(f"<th>{e(str(c))}</th>" for c in f["columns"])
        body = "".join("<tr>" + "".join(f"<td>{'' if v is None else e(str(v))}</td>" for v in (r or [])) + "</tr>"
                       for r in f.get("rows") or [])
        inner = f"{cap}<table><tr>{head}</tr>{body}</table>"
    elif k == "dialog":
        desc = str(f.get("desc") or "")
        title = (f.get("caption") or "대화상자").split("—")[0].strip()
        lines = "\n".join(s.strip() for s in re.split(r"\s*/\s*", desc) if s.strip())
        inner = f"<div class='dlg'><div class='bar'>{e(title)}</div><div class='body'>{e(lines)}</div><div class='ok'><span>확인</span></div></div>"
    else:
        spec = f.get("chart")
        txt = json.dumps(spec, ensure_ascii=False, indent=1) if spec else str(f.get("desc") or "")
        inner = f"{cap}<div class='chart'>〔차트 설계 — 실제 차트 그림은 다음 판〕\n{e(txt)}</div>"
    return f"<!doctype html><meta charset='utf-8'><style>{FIG_CSS}</style><div class='box' id='fig'>{inner}</div>"


def render_figs(m: int, items: List[Tuple[str, dict]], log) -> List[str]:
    """[(stem, figure)] → images/{stem}-{fid}.png. Playwright(sync) 한 번 띄워 차례로."""
    from playwright.sync_api import sync_playwright
    os.makedirs(img_dir(m), exist_ok=True)
    made = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(device_scale_factor=2)
        for stem, f in items:
            name = f"{stem}-{f.get('id') or 'f'}.png"
            pg.set_content(fig_html(f))
            pg.locator("#fig").screenshot(path=os.path.join(img_dir(m), name))
            made.append(name)
        b.close()
    log(f"  그림 {len(made)}장")
    return made



# ── 차트 그림 — 설계대로 엑셀이 정답 파일에 차트를 만들고 PNG 로 내보낸다 ─────────────
# (긴 이름부터 본다 — 「원형 대 가로 막대형」 이 「원형」 보다 먼저 걸려야 한다)
CHART_TYPES = [
    ("원형 대 가로 막대형", 71), ("원형 대 원형", 68), ("3차원 원형", -4102), ("도넛형", -4120), ("원형", 5),
    ("3차원 묶은 세로 막대형", 54), ("3차원 누적 세로 막대형", 55), ("100% 기준 누적 세로 막대형", 53),
    ("누적 세로 막대형", 52), ("묶은 세로 막대형", 51), ("3차원 묶은 가로 막대형", 60),
    ("누적 가로 막대형", 58), ("묶은 가로 막대형", 57), ("표식이 있는 꺾은선형", 65), ("꺾은선형", 4),
    ("표식이 있는 방사형", 81), ("방사형", -4151), ("분산형", -4169), ("영역형", 1), ("세로 막대형", 51), ("가로 막대형", 57),
]
LEGEND_POS = {"아래": -4107, "오른": -4152, "위": -4160, "왼": -4131}


def _chart_type(name: str) -> int:
    for k, v in CHART_TYPES:
        if k in (name or ""):
            return v
    return 51


def _ranges(spec_range: str, sheet: str) -> str:
    """「차트작업!$A$3:$B$11」·「[B3:F3], [B7:F10]」·「'차트작업'!$B$3:$G$11」 → 「A3:B11」·「B3:F3,B7:F10」."""
    s = re.sub(r"'?[^'!\[\],]*'?!", "", str(spec_range or ""))
    parts = [x.strip().strip("[]").replace("$", "") for x in re.split(r"\]\s*,\s*\[|,", s)]
    parts = [x.strip("[] ") for x in parts if re.fullmatch(r"[A-Z]{1,3}\d+(:[A-Z]{1,3}\d+)?", x.strip("[] "))]
    return ",".join(parts)


def draw_charts(wb, names: List[str], m: int, parts: List[dict], log) -> List[str]:
    made = []
    os.makedirs(img_dir(m), exist_ok=True)
    for d in parts:
        own = [str(x.get("name") or "").strip()[:31] for x in d.get("sheets") or []]
        for it in d.get("items") or []:
            for f in it.get("figures") or []:
                if f.get("kind") != "chart" or not isinstance(f.get("chart"), dict):
                    continue
                spec = f["chart"]
                sh = str(f.get("sheet") or it.get("sheet") or "").strip()[:31]
                if sh not in names:
                    sh = next((x for x in own if x in names), "")
                rng = _ranges(spec.get("data_range") or "", sh)
                if not sh or not rng:
                    continue
                stem = f"{m:02d}-{d['part']}-{int(it.get('no') or 0):02d}"
                path = os.path.join(img_dir(m), f"{stem}-{f.get('id')}.png")
                try:
                    ws = wb.Worksheets(sh)
                    co = ws.ChartObjects().Add(ws.Range("D3").Left + 300, ws.Range("D3").Top, 480, 300)
                    ch = co.Chart
                    ch.SetSourceData(ws.Range(rng))
                    ch.ChartType = _chart_type(str(spec.get("type") or ""))
                    for s_ in spec.get("series") or []:     # 혼합 — 계열마다 종류·보조 축
                        if not isinstance(s_, dict) or not s_.get("name"):
                            continue
                        for k in range(1, ch.SeriesCollection().Count + 1):
                            se = ch.SeriesCollection(k)
                            if str(se.Name).strip() == str(s_["name"]).strip():
                                if s_.get("type"):
                                    se.ChartType = _chart_type(str(s_["type"]))
                                if "보조" in str(s_.get("axis") or ""):
                                    se.AxisGroup = 2
                    t = spec.get("title")
                    t = t.get("text") if isinstance(t, dict) else t
                    if t:
                        ch.HasTitle = True
                        ch.ChartTitle.Text = str(t)
                    lg = spec.get("legend")
                    lg = (lg.get("position") if isinstance(lg, dict) else lg) or ""
                    if "없음" in str(lg):
                        ch.HasLegend = False
                    else:
                        for k, v in LEGEND_POS.items():
                            if k in str(lg):
                                ch.HasLegend = True
                                ch.Legend.Position = v
                    if spec.get("data_labels"):
                        try:
                            ch.ApplyDataLabels()
                        except Exception:               # noqa: BLE001
                            pass
                    ch.Export(path)
                    made.append(os.path.basename(path))
                except Exception as e:                  # noqa: BLE001
                    log(f"  차트 실패 {stem} {f.get('id')}: {e}")
    if made:
        log(f"  차트 {len(made)}장(엑셀)")
    return made


# ── 회차 하나 ─────────────────────────────────────────────────────────────
def build_round(m: int, *, log=lambda s: None) -> dict:
    import pythoncom
    import win32com.client as w
    parts = load_round(m)
    if not parts:
        raise FileNotFoundError(f"{m:02d}회 집필 결과가 없습니다.")
    sheets = sheets_of(parts)
    od = out_dir(m)
    os.makedirs(od, exist_ok=True)
    report = {"round": m, "built_at": dt.datetime.now().isoformat(timespec="seconds"), "items": [], "errors": []}
    charts: List[str] = []
    pythoncom.CoInitialize()
    xl = w.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = new_workbook(xl, sheets)
        wb.SaveAs(os.path.join(od, f"m{m:02d}_문제.xlsx"), XL_XLSX)
        wb.Close(False)
        wb = new_workbook(xl, sheets)
        names = [sh["name"] for sh in sheets]

        def sheet_of(d, it):
            sh = str(it.get("sheet") or "").strip()[:31]
            if sh in names:
                return sh
            own = [str(s.get("name") or "").strip()[:31] for s in d.get("sheets") or []]
            return own[0] if len(own) == 1 else sh    # 집필이 sheet 를 비웠으면 묶음 시트가 하나일 때 그것

        for d in parts:
            for it in d.get("items") or []:
                sh = sheet_of(d, it)
                if sh not in names:
                    continue
                a = it.get("answer") or {}
                # 결과값이 셀 주소로 적힌 문항만 수식을 넣는다 — 조건부 서식 수식 같은 것을 셀에 쓰면 자료가 지워진다
                if any(CELL_RE.match(str(k).strip().upper()) for k in (a.get("results") or {})):
                    try:
                        apply_criteria(wb.Worksheets(sh), it)
                        apply_formulas(wb.Worksheets(sh), a)
                    except Exception as e:      # noqa: BLE001
                        report["errors"].append(f"{d['part']}-{it.get('no')}: 수식 넣기 실패 — {e}")
        xl.CalculateFull()
        for d in parts:
            for it in d.get("items") or []:
                if not it.get("no"):
                    continue
                sh = sheet_of(d, it)
                r = check_item(wb.Worksheets(sh), it) if sh in names else \
                    {"no": it.get("no"), "sheet": sh, "status": "시트 없음", "fails": [], "checked": 0, "ok": 0}
                r["id"] = f"{m:02d}-{d['part']}-{int(it.get('no')):02d}"
                report["items"].append(r)
        for sh in names:
            wb.Worksheets(sh).Columns.AutoFit()
        charts = draw_charts(wb, names, m, parts, log)
        wb.Worksheets(1).Activate()
        wb.SaveAs(os.path.join(od, f"m{m:02d}_정답.xlsx"), XL_XLSX)
        wb.Close(False)
    finally:
        try:
            xl.Quit()
        except Exception:                       # noqa: BLE001
            pass
        pythoncom.CoUninitialize()
    # 그림 → PNG, 원고 MD 다시(그림 자리에 PNG)
    figs = []
    for d in parts:
        for it in d.get("items") or []:
            stem = f"{m:02d}-{d['part']}-{int(it.get('no') or 0):02d}"
            figs += [(stem, f) for f in it.get("figures") or []
                     if f.get("id") and f"{stem}-{f.get('id')}.png" not in charts]   # 엑셀이 그린 차트는 그대로
    try:
        report["figures"] = render_figs(m, figs, log) + charts
        report["charts"] = charts
    except Exception as e:                      # noqa: BLE001
        report["errors"].append(f"그림 그리기 실패 — {e}")
        report["figures"] = []
    rewrite_md(m)
    st = [x["status"] for x in report["items"]]
    report["summary"] = {s: st.count(s) for s in sorted(set(st))}
    atomic_write_text(os.path.join(od, "verify.json"), json.dumps(report, ensure_ascii=False, indent=2))
    return report


def rewrite_md(m: int) -> None:
    """그림 PNG 가 있으면 원고 MD 를 다시 쓴다(author.item_md 가 PNG 를 부른다)."""
    for f in glob.glob(os.path.join(pa.round_dir(m), f"{m:02d}-[0-9]-[0-9][0-9].json")):
        with open(f, encoding="utf-8") as fh:
            j = json.load(fh)
        atomic_write_text(f[:-5] + ".md", pa.item_md(m, int(j.get("part") or 0), j))


def status(rounds: List[int]) -> List[dict]:
    rows = []
    for m in rounds:
        od = out_dir(m)
        v = {}
        vp = os.path.join(od, "verify.json")
        if os.path.isfile(vp):
            try:
                with open(vp, encoding="utf-8") as fh:
                    v = json.load(fh)
            except (OSError, ValueError):
                v = {}
        rows.append({"round": m, "written": all(pa.part_done(m, p) for p in (1, 2, 3, 4)),
                     "built_at": v.get("built_at") or "", "summary": v.get("summary") or {},
                     "errors": v.get("errors") or [], "items": v.get("items") or [],
                     "files": [os.path.basename(x) for x in glob.glob(os.path.join(od, "*.xlsx"))],
                     "figures": len(v.get("figures") or [])})
    return rows


# ── 잡 ────────────────────────────────────────────────────────────────────
_LOCK = threading.Lock()


def start(rounds: List[int]) -> dict:
    from services.jobs import registry
    todo = [m for m in rounds if all(pa.part_done(m, p) for p in (1, 2, 3, 4))]
    if not todo:
        raise ValueError("빌드할 회차가 없습니다 — 집필이 끝난(문제1~4 다 쓴) 회차만 빌드합니다.")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("이미 실기 빌드가 돌고 있습니다.")
    job = registry.create("practical-build", f"실기 빌드 · {todo[0]:02d}~{todo[-1]:02d}회 ({len(todo)}회)",
                          [f"m{m:02d}" for m in todo])

    def work(j: dict) -> None:
        try:
            for m in todo:
                if j.get("cancel_requested"):
                    registry.log(j, "[취소] 사람이 멈췄습니다.", force=True)
                    break
                key = f"m{m:02d}"
                registry.item(j, key, status="running")
                j["current"] = f"{m:02d}회"
                registry.log(j, f"[빌드] {m:02d}회 — 실습파일·검증·그림", force=True)
                try:
                    r = build_round(m, log=lambda s: registry.log(j, s))
                except Exception as e:          # noqa: BLE001
                    registry.item(j, key, status="error", error=f"{type(e).__name__}: {e}")
                    registry.log(j, f"[실패] {m:02d}회 — {e}", force=True)
                    continue
                j["done_count"] = j.get("done_count", 0) + 1
                s = " · ".join(f"{k} {v}" for k, v in r["summary"].items())
                registry.item(j, key, status="done", output=s)
                registry.log(j, f"  → {s}" + (f" · 오류 {len(r['errors'])}" if r["errors"] else ""), force=True)
            registry.finish(j, "done")
        finally:
            _LOCK.release()

    registry.spawn(job, work)
    return job
