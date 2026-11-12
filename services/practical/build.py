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


COLOR_RGB = {"빨강": (255, 0, 0), "노랑": (255, 255, 0), "파랑": (0, 112, 192), "초록": (0, 176, 80),
             "녹색": (0, 176, 80), "주황": (255, 192, 0), "검정": (0, 0, 0), "흰색": (255, 255, 255),
             "회색": (191, 191, 191), "자주": (112, 48, 160), "연한 녹색": (146, 208, 80), "하늘색": (0, 176, 240)}


def _bgr(c) -> Optional[int]:
    """「#FF0000」·「빨강」·(255,0,0) → 엑셀 색 값(BGR 정수)."""
    if c is None or c == "":
        return None
    if isinstance(c, (list, tuple)) and len(c) == 3:
        r, g, b = (int(x) for x in c)
    else:
        s = str(c).strip()
        m = re.fullmatch(r"#?([0-9A-Fa-f]{6})", s)
        if m:
            r, g, b = int(m.group(1)[0:2], 16), int(m.group(1)[2:4], 16), int(m.group(1)[4:6], 16)
        else:
            rgb = next((v for k, v in sorted(COLOR_RGB.items(), key=lambda kv: -len(kv[0])) if k in s), None)
            if not rgb:
                return None
            r, g, b = rgb
    return r + g * 256 + b * 65536


def apply_styles(ws, styles) -> None:
    """★ 2026-11-12 녹화 회신: 「글꼴 색이 빨강인 데이터를 위로」 같은 문항은 그 색이 문제 파일에 있어야 성립한다.
    styles = [{range, font_color, fill, bold}] — 원문 그림의 서식 중 지시에 쓰이는 것."""
    for s in styles or []:
        if not isinstance(s, dict) or not s.get("range"):
            continue
        try:
            rg = ws.Range(str(s["range"]).replace(" ", ""))
        except Exception:                       # noqa: BLE001
            continue
        fc, fl = _bgr(s.get("font_color")), _bgr(s.get("fill"))
        if fc is not None:
            rg.Font.Color = fc
        if fl is not None:
            rg.Interior.Color = fl
        if s.get("bold"):
            rg.Font.Bold = True


INPUT_KEEP = {"all": (), "body": ("title",), "data": ("title", "columns")}


def for_problem(t: dict) -> Optional[dict]:
    """★ 수험자가 **입력하는** 자료(기본작업-1)는 문제 파일에 넣지 않는다(실제 시험처럼 빈 시트).
    input: "all" = 전부 입력(빈 시트) · "body" = 제목만 미리 · "data" = 제목·머리글 미리, 자료 행만 입력.
    2026-11-12: 1부 빌드가 입력할 자료까지 문제 파일에 채워 두고 있었다."""
    mode = str(t.get("input") or "").strip()
    if mode not in INPUT_KEEP:
        return t
    keep = INPUT_KEEP[mode]
    if not keep:
        return None
    return {**t, "rows": [], "columns": t.get("columns") if "columns" in keep else [],
            "title": t.get("title") if "title" in keep else "", "styles": []}


def write_table(ws, t: dict) -> None:
    r0, c0 = split_cell(t.get("anchor") or "A1")
    title = str(t.get("title") or "").strip()
    tc = str(t.get("title_cell") or "").strip().upper().replace("$", "")
    if title and CELL_RE.match(tc):
        # ★ 제목 자리를 집필이 정했으면 그대로(「차트 제목은 [B2] 셀과 연동」 — 02·09회 녹화 회신)
        _put(ws.Range(tc), title)
    elif title:
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
    apply_styles(ws, t.get("styles"))


def table_box(t: dict) -> Tuple[int, int, int, int]:
    """표 하나가 차지하는 (머리글 행, 첫 열, 끝 행, 끝 열)."""
    r0, c0 = split_cell(t.get("anchor") or "A1")
    ncol = max([len(t.get("columns") or [])] + [len(r or []) for r in t.get("rows") or []] + [1])
    return r0, c0, r0 + len(t.get("rows") or []), c0 + ncol - 1


def new_workbook(xl, sheets: List[dict], problem: bool = False):
    wb = xl.Workbooks.Add()
    while wb.Worksheets.Count < max(1, len(sheets)):
        wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
    for i, sh in enumerate(sheets, 1):
        ws = wb.Worksheets(i)
        ws.Name = sh["name"]
        for t in sh["tables"]:
            t2 = for_problem(t) if problem else t
            if t2 is not None:
                write_table(ws, t2)
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
        elif cols and r0 > 1 and str(ws.Cells(r0 - 1, c0).Value or "").strip() == str(cols[0]).strip():
            # ★ 조건 칸 바로 위에 같은 머리글이 이미 있다(통합 [표4] 「강좌명」 아래 [G15:G17]) — 머리글을 또 쓰면
            #   한 줄 밀린다(04·09-3-02, 2026-11-12 녹화 회신). 값만 지시 칸부터.
            cols = []
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
            # 엑셀 표시는 사사오입(11.25 → 11.3) — 파이썬 round 는 짝수 쪽(11.2)이라 Decimal 로 맞춘다
            from decimal import ROUND_HALF_UP, Decimal
            q = Decimal(1).scaleb(-d)
            return Decimal(repr(gn)).quantize(q, ROUND_HALF_UP) == Decimal(repr(wn)).quantize(q, ROUND_HALF_UP)
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


def chart_box(ws, sheet: Optional[dict]) -> Tuple[float, float, float, float]:
    """차트 자리 — 그 시트 표들의 오른쪽 한 칸 띄우고 3행부터. 문제(제공 차트)·정답(결과 차트)이 **같은 자리**."""
    last = max([table_box(t)[3] for t in (sheet or {}).get("tables") or []] + [3])
    return ws.Cells(3, last + 2).Left, ws.Cells(3, 1).Top, 480, 300


def _style_chart(ch, spec: dict) -> None:
    t = spec.get("title")
    t = t.get("text") if isinstance(t, dict) else t
    # 「4월 … 비율(돋움, 15, 진한 파랑)」 — 설계에 서식 메모가 붙어 온다. 제목 글에는 넣지 않는다(08-4-02)
    t = re.sub(r"\s*\([^()]*,[^()]*\)\s*$", "", str(t or "")).strip()
    if t:
        ch.HasTitle = True
        ch.ChartTitle.Text = str(t)
    elif "title" in spec:
        ch.HasTitle = False
    lg = spec.get("legend")
    lg = (lg.get("position") if isinstance(lg, dict) else lg) or ""
    if "없음" in str(lg):
        ch.HasLegend = False
    else:
        for k, v in LEGEND_POS.items():
            if k in str(lg):
                ch.HasLegend = True
                ch.Legend.Position = v


def _item_sheet(d: dict, it: dict, names: List[str], f: Optional[dict] = None) -> str:
    sh = str((f or {}).get("sheet") or it.get("sheet") or "").strip()[:31]
    if sh in names:
        return sh
    own = [str(x.get("name") or "").strip()[:31] for x in d.get("sheets") or []]
    return next((x for x in own if x in names), "")


def draw_given(wb, names: List[str], sheets: List[dict], parts: List[dict], log) -> int:
    """★ 「제공 차트」(2026-11-12 녹화 회신: 차트 문항 10개 모두 문제 파일에 차트가 없었다).
    차트 문항의 given_chart = 지시 ①~⑤ 를 적용하기 **전** 차트 — 문제 파일에 그린다."""
    by = {s["name"]: s for s in sheets}
    n = 0
    for d in parts:
        for it in d.get("items") or []:
            g = it.get("given_chart")
            if not isinstance(g, dict):
                continue
            sh = _item_sheet(d, it, names)
            rng = _ranges(g.get("range") or g.get("data_range") or "", sh)
            if not sh or not rng:
                log(f"  제공 차트 범위 없음 {d['part']}-{it.get('no')}")
                continue
            try:
                ws = wb.Worksheets(sh)
                co = ws.ChartObjects().Add(*chart_box(ws, by.get(sh)))
                ch = co.Chart
                ch.SetSourceData(ws.Range(rng))
                ch.ChartType = _chart_type(str(g.get("type") or ""))
                _style_chart(ch, {"title": g.get("title"), **({"legend": g["legend"]} if g.get("legend") else {})})
                n += 1
            except Exception as e:                      # noqa: BLE001
                log(f"  제공 차트 실패 {d['part']}-{it.get('no')}: {e}")
    return n


def draw_charts(wb, names: List[str], m: int, parts: List[dict], log, sheets: Optional[List[dict]] = None) -> List[str]:
    """결과 차트 — 그림 설계마다 그려 PNG 로 내보내고, 정답 파일에는 문항당 **마지막 하나만** 남긴다
    (04·08회처럼 차트 그림이 둘인 문항이 같은 차트를 두 번 남겼다 — 2026-11-12 녹화 회신)."""
    made = []
    by = {s["name"]: s for s in sheets or []}
    os.makedirs(img_dir(m), exist_ok=True)
    for d in parts:
        for it in d.get("items") or []:
            keep = None
            for f in it.get("figures") or []:
                if f.get("kind") != "chart" or not isinstance(f.get("chart"), dict):
                    continue
                spec = f["chart"]
                sh = _item_sheet(d, it, names, f)
                rng = _ranges(spec.get("data_range") or "", sh)
                if not sh or not rng:
                    continue                            # 피벗 차트(원본 범위 없음)는 수험자가 만든다
                stem = f"{m:02d}-{d['part']}-{int(it.get('no') or 0):02d}"
                path = os.path.join(img_dir(m), f"{stem}-{f.get('id')}.png")
                try:
                    ws = wb.Worksheets(sh)
                    co = ws.ChartObjects().Add(*chart_box(ws, by.get(sh)))
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
                    _style_chart(ch, {k: spec[k] for k in ("title", "legend") if k in spec})
                    if spec.get("data_labels"):
                        try:
                            ch.ApplyDataLabels()
                        except Exception:               # noqa: BLE001
                            pass
                    ch.Export(path)
                    made.append(os.path.basename(path))
                    if keep is not None:
                        keep.Delete()
                    keep = co
                except Exception as e:                  # noqa: BLE001
                    log(f"  차트 실패 {stem} {f.get('id')}: {e}")
    if made:
        log(f"  차트 {len(made)}장(엑셀)")
    return made


# ── 원천 점검 ─────────────────────────────────────────────────────────────
# ★ 2026-11-12 녹화 회신(허브 녹화기가 120문항을 돌리다 찾은 원천 오류)을 다음 회차·다른 과정에서 미리 잡는다.
#   문제 파일(수험자가 받는 것)을 열어 둔 채로 지시와 맞춰 본다. 고치지는 않고 목록만 남긴다.
RANGE_RE = re.compile(r"\[\$?([A-Z]{1,3})\$?(\d{1,7})(?::\$?([A-Z]{1,3})\$?(\d{1,7}))?\]")
LINK_RE = re.compile(r"\[\$?([A-Z]{1,3})\$?(\d{1,7})\]\s*셀과\s*연동")
WHAT_IF = ("시나리오", "데이터 표", "목표값")


def _texts(it: dict) -> List[str]:
    return [str(it.get("lead") or "")] + [str(x) for x in it.get("instructions") or []]


def _cells_after(text: str, word: str) -> List[str]:
    """「변경 셀은 [C14], [C15]」·「결과 셀: [F12]」 → 그 뒤 대괄호 셀 주소들(같은 문장 안)."""
    out = []
    for m in re.finditer(word, text):
        tail = re.split(r"[.。▶①②③④⑤\n]|으로 하시오|로 하시오", text[m.end():m.end() + 80])[0]
        for a, b, c, d in RANGE_RE.findall(tail):
            out.append(f"{a}{b}:{c}{d}" if c else f"{a}{b}")
    return out


def _singles(s: str) -> List[str]:
    return [f"{a}{b}" for a, b, c, d in RANGE_RE.findall(s or "") if not c]


def what_if_cells(text: str) -> Tuple[List[str], List[str]]:
    """시나리오·데이터 표 지시에서 (변경 셀, 결과 셀).
    「할증률[C14]과 할인율[C15]이 변동하는 경우 대여금액 합계[F12]의 변동 시나리오」 /
    「판매단가[C4], …를 이용하여 순이익[C10]을 계산한 것이다」 / 「[D15] 셀은 '할증률' … 이름을 정의」."""
    chg = [c for c in _cells_after(text, r"변경\s*셀|입력\s*셀|값을 바꿀\s*셀") if ":" not in c]
    res = [c for c in _cells_after(text, r"결과\s*셀|수식\s*셀") if ":" not in c]
    for line in text.splitlines():
        m = re.search(r"변동하는\s*경우(.{0,80}?)의\s*변동", line)
        if m:
            chg += _singles(line[:m.start()])
            res += _singles(m.group(1))
            continue
        m = re.search(r"\[([A-Z]{1,3}\d+)\]\s*(?:을|를)\s*계산한", line)
        if m:
            res.append(m.group(1))
            chg += _singles(line[:m.start()])
    if res and not chg:                     # 「[D15] 셀은 '할증률', … [I12] 셀은 '결제총액'으로 이름을 정의」
        for line in text.splitlines():
            if "이름" in line and "정의" in line:
                chg += [c for c in _singles(line) if c not in res]
    uniq = lambda xs: list(dict.fromkeys(xs))   # noqa: E731
    res = uniq(res)
    return [c for c in uniq(chg) if c not in res], res


def _value(ws, addr: str):
    try:
        return ws.Range(addr).Value
    except Exception:                           # noqa: BLE001
        return None


def source_checks(wb, sheets: List[dict], parts: List[dict], m: int) -> List[dict]:
    names = [s["name"] for s in sheets]
    by = {s["name"]: s for s in sheets}
    out: List[dict] = []

    def add(d, it, kind, msg):
        out.append({"id": f"{m:02d}-{d['part']}-{int(it.get('no') or 0):02d}", "kind": kind, "msg": msg})

    # 표 자체(제목 메모·열 머리 글자)
    for s in sheets:
        for t in s["tables"]:
            title = str(t.get("title") or "")
            if re.search(r"\(.*\[[A-Z]{1,3}\d+\].*(셀|행|열)", title):
                out.append({"id": f"{m:02d}-{s['name']}", "kind": "제목 메모",
                            "msg": f"표 제목에 지시 메모가 섞임: 「{title}」"})
            for i, r in enumerate((t.get("rows") or [])[:2]):
                cells = [x for x in (r or []) if x not in (None, "")]
                if cells and all(re.fullmatch(r"[A-Z]{1,2}", str(x).strip()) for x in cells):
                    out.append({"id": f"{m:02d}-{s['name']}", "kind": "열 머리 글자",
                                "msg": f"{t.get('anchor')} 표 {i + 1}번째 줄이 열 머리 글자뿐: {cells[:6]}"})
                    break
            cols = t.get("columns") or []
            if cols and (all(re.fullmatch(r"[A-Z]{1,2}", str(c).strip()) for c in cols)
                         or (len(cols) <= 2 and any(re.fullmatch(r"[A-Z]", str(c).strip()) for c in cols))):
                out.append({"id": f"{m:02d}-{s['name']}", "kind": "열 머리 글자",
                            "msg": f"{t.get('anchor')} 표 머리글이 {cols}(원본 그림의 열 머리일 수 있음)"})

    for d in parts:
        for it in d.get("items") or []:
            if not it.get("no"):
                continue
            sh = _item_sheet(d, it, names)
            if not sh:
                continue
            ws = wb.Worksheets(sh)
            text = "\n".join(_texts(it))
            # 1) 시나리오·데이터 표·목표값 찾기 — 결과 셀은 수식, 변경 셀은 숫자, 바꾸면 결과가 바뀐다
            if any(w in text for w in WHAT_IF):
                chg, res = what_if_cells(text)
                for c in chg:
                    v = _value(ws, c)
                    if not isinstance(v, (int, float)):
                        add(d, it, "변경 셀", f"변경 셀 [{c}] 이 숫자가 아님: {v!r} (표가 밀렸거나 비어 있음)")
                for c in res:
                    try:
                        hf = bool(ws.Range(c).HasFormula)
                    except Exception:           # noqa: BLE001
                        hf = False
                    if not hf:
                        add(d, it, "결과 셀 수식", f"결과 셀 [{c}] 에 수식이 없음 — 값만 있으면 결과가 안 바뀜")
                if chg and res and all(isinstance(_value(ws, c), (int, float)) for c in chg):
                    before = [_value(ws, c) for c in res]
                    olds = [ws.Range(c).Formula for c in chg]
                    try:
                        for c in chg:
                            ws.Range(c).Value = (_value(ws, c) or 0) * 1.37 + 1
                        wb.Application.Calculate()
                        after = [_value(ws, c) for c in res]
                    finally:
                        for c, f in zip(chg, olds):
                            ws.Range(c).Formula = f
                        wb.Application.Calculate()
                    if before == after:
                        add(d, it, "결과 셀 수식", f"변경 셀 {chg} 을 바꿔도 결과 셀 {res} 이 그대로")
                elif "시나리오" in text and not chg:
                    add(d, it, "변경 셀", "지시에서 변경 셀을 찾지 못함(점검 생략)")
            # 0) 「자료를 주어진 대로 입력하시오」 — 문제 파일은 비어 있어야(시트 자료에 input)
            if "입력하시오" in str(it.get("lead") or "") and "주어진 대로" in str(it.get("lead") or ""):
                if by[sh]["tables"] and not any(t.get("input") for t in by[sh]["tables"]):
                    add(d, it, "입력 자료", "입력 문항인데 시트 자료에 input 표시가 없어 문제 파일에 자료가 미리 들어감")
            # 2) 차트 문항 — 제공 차트
            if "차트" in sh and any("차트" in x for x in it.get("instructions") or []):
                if not isinstance(it.get("given_chart"), dict):
                    add(d, it, "제공 차트", "given_chart(지시 적용 전 차트)가 없음 — 문제 파일에 차트가 없게 됨")
                elif ws.ChartObjects().Count != 1:
                    add(d, it, "제공 차트", f"문제 파일 차트 {ws.ChartObjects().Count}개(1개여야 함)")
            # 3) 지시 범위 첫 행 = 표 머리글 행
            for a, b, c, e in RANGE_RE.findall(text):
                if not c:
                    continue
                r1, c1, r2, c2 = int(b), col_num(a), int(e), col_num(c)
                if r2 - r1 < 2 or c2 - c1 < 1:
                    continue
                for t in by[sh]["tables"]:
                    h, tc0, tr2, tc2 = table_box(t)
                    width = min(c2, tc2) - max(c1, tc0) + 1
                    if width < max(2, (tc2 - tc0 + 1) // 2) or r2 < h or r1 > tr2:
                        continue
                    if r1 not in (h, h + 1):
                        add(d, it, "범위·표 위치", f"지시 범위 [{a}{b}:{c}{e}] 첫 행 {r1} ≠ 표 머리글 행 {h}({t.get('anchor')})")
            # 4) 「[X] 셀과 연동」
            for a, b in LINK_RE.findall(text):
                if _value(ws, f"{a}{b}") in (None, ""):
                    add(d, it, "연동 셀", f"[{a}{b}] 셀과 연동하라는데 문제 파일의 [{a}{b}] 이 비어 있음")
            # 5) 색 기준 정렬·필터
            if re.search(r"(글꼴|셀)\s*색", text) and re.search(r"정렬|필터", text):
                if not any(t.get("styles") for t in by[sh]["tables"]):
                    add(d, it, "서식 색", "색 기준 정렬·필터인데 시트 자료에 styles(글꼴 색·채우기)가 없음")
    return out


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
        names = [sh["name"] for sh in sheets]
        wb = new_workbook(xl, sheets, problem=True)
        draw_given(wb, names, sheets, parts, log)
        wb.Worksheets(1).Activate()
        wb.SaveAs(os.path.join(od, f"m{m:02d}_문제.xlsx"), XL_XLSX)
        try:
            report["source_checks"] = source_checks(wb, sheets, parts, m)   # 저장한 뒤 — 점검이 칸을 잠깐 바꿨다 되돌린다
        except Exception as e:                  # noqa: BLE001
            report["errors"].append(f"원천 점검 실패 — {e}")
        wb.Close(False)
        wb = new_workbook(xl, sheets)

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
        charts = draw_charts(wb, names, m, parts, log, sheets)
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
                     "source_checks": v.get("source_checks") or [],
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
