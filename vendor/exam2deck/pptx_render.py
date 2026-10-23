# -*- coding: utf-8 -*-
"""`[ir.Page]` → .pptx (네이티브 도형).

★ 좌표계는 하나다 — `layout.px_emu()`. 여기서 새 단위를 만들지 않는다.
  1px = 0.5pt = 6350 EMU 이고, 그 환산이 정확히 나눠떨어지므로 원본 CSS 픽셀을
  그대로 놓으면 HTML 과 같은 자리에 온다.

★ 색·글자 크기는 `_deck-export/*.html` 의 `<style>` 에서 읽은 값이다. 여기서
  "더 예뻐 보이는" 값으로 바꾸지 않는다 — 사이트·영상·PPT 가 같은 화면이어야 한다.

★ 텍스트 줄간격은 **배수가 아니라 고정값**(`Pt(size*lh)`)으로 준다. PowerPoint 의
  배수 줄간격은 폰트의 ascent/descent 로 계산해서 CSS `line-height` 와 다르다.
  고정값이면 `layout.block_h` 가 계산한 높이와 정확히 맞는다 — 두 곳이 어긋나면
  블록이 아래로 밀려 다음 블록을 덮는다.

★ 표는 python-pptx 가 테두리를 안 열어 준다. `_cell_border()` 가 `a:lnL/R/T/B` 를
  직접 쓴다. 표 스타일의 자동 밴딩(`firstRow`/`bandRow`)은 **끈다** — 켜져 있으면
  우리가 칠한 색 위에 테마 색이 덮인다.
"""
from __future__ import annotations

import os
from typing import List, Optional

from pptx.util import Emu, Pt

from . import layout as L
from .ir import Block, Page

# ── 색 (`--c-*` 토큰. 덱 HTML 의 <style> 에서 그대로) ──────────────────────
INK = "1e2637"        # --c-ink    본문 최진함 (발문)
BODY = "46536b"       # --c-body   본문
MUTED = "6b7688"      # --c-muted  보조 (원숫자·머리)
BLUE = "2c5ce6"       # --c-blue   문번·강조
LINE = "e3e8f0"       # --c-line   테두리
SOFT = "f6f8fc"       # --c-soft   지문 배경
SOFT2 = "f2f4f8"      # --c-soft   표 머리 배경
PAPER = "ffffff"      # --c-paper  보기 칸 배경
OK = "0f7355"         # --c-ok     정답
OK_BG = "e3f1ec"      # --c-ok-bg  정답 배경
# 난도 pill (`.pill-orange`)
PILL_BG, PILL_FG, PILL_BD = "fdf0e6", "a75a12", "f6d9bd"
# 코드블록 (사이트 `pre.sql`)
PRE_BG, PRE_FG = "0f172a", "e2e8f0"

FONT = "Pretendard"
FONT_MONO = "Consolas"

# ── 과목별 강조색 (이론 덱) ────────────────────────────────────────────────
# ★ 사용자 확정(2026-08-21): 과목마다 색을 다르게 한다. 여러 과목을 이어 들을 때
#   "지금 몇 과목인가" 를 색으로 알 수 있게 하는 것이 목적이다.
#
# ★ 전부 흰 바탕에서 **4.5:1 이상**이다(글자로도 쓰이므로 AA 를 지켜야 한다).
#   2과목의 틸(#0f766e)은 요약노트 원본 HTML 이 쓰던 색을 그대로 가져왔다 —
#   SQL 과목을 보던 사람에게 같은 색이 남는다.
# ★ 색만으로 뜻을 전달하지 않는다. 과목 이름이 표지와 대단원 칩에 늘 함께 나온다.
SUBJECT_COLORS = {
    1: ("1f4ed8", "e9eefc"),   # blue   — 문제 덱과 같은 계열(기본)
    2: ("0f766e", "e7f3f1"),   # teal   — 요약노트 원본 색
    3: ("6b46c1", "efe9fb"),   # purple
    4: ("b45309", "fdf0e6"),   # orange
    5: ("b91c40", "fdeaee"),   # crimson
    6: ("15803d", "e8f5ec"),   # green
}


def palette(subject_no: int):
    """(강조색, 연한 배경). 모르는 과목이면 문제 덱과 같은 파랑으로 떨어진다."""
    return SUBJECT_COLORS.get(int(subject_no or 0), (BLUE, "e9eefc"))


def _rgb(h: str):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(h.upper())


# ── 저수준 ──────────────────────────────────────────────────────────────────
def _strip_slides(prs) -> None:
    from pptx.oxml.ns import qn
    lst = prs.slides._sldIdLst
    for sldId in list(lst):
        rId = sldId.get(qn("r:id"))
        lst.remove(sldId)
        if rId:
            try:
                prs.part.drop_rel(rId)
            except Exception:
                pass


def _blank(prs):
    """빈 판. 레이아웃 placeholder 는 지운다 — 우리가 좌표를 다 잡는다."""
    layout_ = prs.slide_layouts[min(len(prs.slide_layouts) - 1,
                                    _blank_layout_index(prs))]
    s = prs.slides.add_slide(layout_)
    for ph in list(s.placeholders):
        ph._element.getparent().remove(ph._element)
    return s


def _blank_layout_index(prs) -> int:
    """가장 빈 레이아웃. 이름에 '빈'/'blank' 가 있으면 그것, 없으면 placeholder 최소."""
    best, best_n = 0, 10 ** 9
    for i, lay in enumerate(prs.slide_layouts):
        name = (lay.name or "").lower()
        n = len(lay.placeholders)
        if "blank" in name or "빈" in name:
            return i
        if n < best_n:
            best, best_n = i, n
    return best


def _set_font(run, *, size_px: float, color: str, bold: bool, mono: bool = False):
    """글꼴 한 벌. 한글도 같은 글꼴을 쓰게 `a:ea`·`a:cs` 까지 심는다.

    ★ `font.name` 은 `a:latin` 만 건드린다. 그것만 두면 한글이 테마의 동아시아
      글꼴(맑은 고딕)로 떨어져 라틴과 한글의 굵기·자폭이 갈린다.

    ★ **코드블록의 동아시아 글꼴은 본문 글꼴을 쓴다.** 전에는 `a:ea` 에도
      `Consolas` 를 박았는데, Consolas 에는 **한글이 하나도 없다**(실측: 자모 0/4 ·
      음절 0/2). 그래서 코드블록 안의 `ㄱ. ㄴ. ㄷ. ㄹ.` 이 두부(▯)로 나갔다
      (2026-08-25 SQLD 01회 30번). 라틴은 Consolas 로 두어 SQL 의 열 맞춤을
      지키고, 한글만 본문 글꼴로 떨어뜨린다 — 코드블록 안의 한글은 어차피 문장이라
      고정폭일 이유가 없다.
    """
    from pptx.oxml.ns import qn
    f = run.font
    name = FONT_MONO if mono else FONT
    ea_name = FONT if mono else name          # ← 한글은 언제나 본문 글꼴
    f.name = name
    f.size = Pt(L.px_pt(size_px))
    f.bold = bold
    f.color.rgb = _rgb(color)
    rPr = run._r.get_or_add_rPr()
    # ★ 언어를 한국어로 못박는다. 비워 두면 PowerPoint 가 en-US 로 보고 **라틴 조판
    #   규칙**을 쓴다 — 그러면 `hangingPunct` 가 안 먹어서 문단 끝 마침표가 혼자
    #   다음 줄로 내려간다(실측 01회 1번 해설). 맞춤법 검사 언어도 이걸 따른다.
    rPr.set("lang", "ko-KR")
    rPr.set("altLang", "en-US")
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", ea_name)


def _textbox(slide, x, y, w, h, paras, *, size_px, line_h, color, bold=False,
             align="l", anchor="t", mono=False, para_gap_px=0.0, wrap=True):
    """문단 목록을 텍스트박스 하나로. 높이는 `layout` 이 이미 계산한 값이다.

    ★ `wrap=False` 는 알약처럼 **한 줄이라고 확신하는** 자리에만 쓴다. 켜 두면
      우리가 잰 폭과 PowerPoint 의 폭이 1~2px 어긋나는 순간 마지막 글자가 둘째 줄로
      내려가고, 그 줄은 알약 밖에 떠서 화면에 점처럼 남는다(실측: 정답 배지의
      마지막 마침표가 배지 아래에 점으로 찍혔다).
    """
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR, MSO_AUTO_SIZE
    from . import metrics as M
    tb = slide.shapes.add_textbox(Emu(L.px_emu(x)), Emu(L.px_emu(y)),
                                  Emu(L.px_emu(w)), Emu(L.px_emu(h)))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE,
                          "b": MSO_ANCHOR.BOTTOM}[anchor]
    al = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
    items = paras or [""]
    for i, txt in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = al
        _ea_linebreak(p)
        # ★ `ㄱ. ㄴ. ㄷ. ㄹ.` 항목은 내어쓰기. 잰 폭과 같은 값을 심는다
        #   (`metrics.jamo_indent` 가 유일한 소유자다).
        _hanging_indent(p, M.jamo_indent(txt, size_px,
                                         weight=700 if bold else 400))
        # ★ 고정 줄간격. 배수로 주면 CSS line-height 와 어긋난다(머리말 참고).
        p.line_spacing = Pt(L.px_pt(size_px * line_h))
        p.space_before = Pt(L.px_pt(para_gap_px) if i else 0)
        p.space_after = Pt(0)
        r = p.add_run()
        r.text = txt
        _set_font(r, size_px=size_px, color=color, bold=bold, mono=mono)
    return tb


def _hanging_indent(paragraph, indent_px: float) -> None:
    """둘째 줄부터 `indent_px` 만큼 들여 쓴다 — `ㄱ. ` 표지 아래로 글이 붙지 않게.

    ★ OOXML 은 `marL`(문단 왼쪽 들여쓰기) + `indent`(첫 줄 **음수** = 내어쓰기) 다.
      PowerPoint 의 [단락] 창에서 "텍스트 앞 0.85cm · 첫 줄 내어쓰기 0.85cm" 로
      보이는 그 값이다. 사람이 손으로 넣던 것을 여기서 심는다.

    ★ 폭은 `metrics.jamo_indent` 가 실제 글꼴로 잰 값이다 — 0.85cm 같은 어림수를
      쓰면 글꼴·글자크기가 바뀔 때 표지와 본문이 어긋난다.
    """
    if indent_px <= 0.5:
        return
    emu = L.px_emu(indent_px)
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("marL", str(int(emu)))
    pPr.set("indent", str(-int(emu)))


def _ea_linebreak(paragraph) -> None:
    """동아시아 줄바꿈 규칙을 켠다 — `hangingPunct` 가 핵심이다.

    ★ 이걸 안 켜면 문단 끝의 마침표 하나가 **혼자 다음 줄로 내려간다**(실측: 01회
      1번 해설에서 "…정보다" 다음 줄에 "." 만 찍혔다). PowerPoint 는 "." 을 독립
      낱말로 보고 폭이 딱 맞으면 넘겨 버린다. `hangingPunct="1"` 이면 구두점이
      오른쪽 여백으로 **매달려** 줄을 넘기지 않는다 — 한국어 조판의 기본이다.

    ★ 우리가 재는 줄 수도 구두점을 매단다고 보고 세지 않는다. 그래서 이 설정이
      없으면 잰 높이보다 한 줄 커져 카드가 넘친다 — 보기보다 나쁜 쪽이다.
    """
    from pptx.oxml.ns import qn
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("eaLnBrk", "1")
    pPr.set("hangingPunct", "1")
    pPr.set("latinLnBrk", "0")


def _box(slide, x, y, w, h, *, fill=None, line=None, radius=0.0):
    """(둥근) 사각형. `radius` 는 CSS `border-radius` 픽셀값."""
    from pptx.enum.shapes import MSO_SHAPE
    rounded = radius > 0.5
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Emu(L.px_emu(x)), Emu(L.px_emu(y)), Emu(L.px_emu(w)), Emu(L.px_emu(h)))
    if rounded:
        # ROUNDED_RECTANGLE 의 adj 는 "짧은 변의 절반" 에 대한 비율이다.
        half = min(w, h) / 2.0
        try:
            shp.adjustments[0] = max(0.0, min(1.0, radius / half if half else 0))
        except Exception:
            pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = _rgb(fill)
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = _rgb(line)
        shp.line.width = Pt(0.75)          # CSS 1px = 0.5pt. 0.75 가 화면에서 1px 로 보인다
    shp.shadow.inherit = False
    shp.text_frame.word_wrap = True
    return shp


def _pill(slide, x, y, text, *, size_px, pad_v, pad_h, bg, fg, bd=None,
          bold=True, max_w=None, radius=None):
    """알약. 폭은 글자에 맞추고, `max_w` 를 넘으면 여러 줄 둥근 상자로 떨어진다.

    반환: (폭, 높이)

    ★ 폭에 2% 를 더한다. 우리는 폰트의 advance width 합으로 재는데 PowerPoint 는
      자기 커닝·힌팅을 더해 조금 더 넓게 그린다. 좁으면 마지막 글자가 알약 테두리에
      닿는다 — 남는 쪽이 눈에 안 띈다.
    """
    from . import metrics as M
    weight = 800 if bold else 400
    tw = M.text_width(text, size_px, weight=weight) * 1.02 + 2
    line_h = 1.4
    if max_w is not None and tw + pad_h * 2 > max_w:
        # 한 줄에 안 들어간다 — 전폭 둥근 상자에 줄바꿈해 담는다.
        inner = max_w - pad_h * 2
        lines = M.line_count(text, size_px, L.mw(inner, size_px), weight=weight)
        h = lines * size_px * line_h + pad_v * 2
        _box(slide, x, y, max_w, h, fill=bg, line=bd,
             radius=radius if radius is not None else size_px * 0.8)
        _textbox(slide, x + pad_h, y + pad_v, inner, h - pad_v * 2, [text],
                 size_px=size_px, line_h=line_h, color=fg, bold=bold)
        return max_w, h
    w = tw + pad_h * 2
    h = size_px * line_h + pad_v * 2
    _box(slide, x, y, w, h, fill=bg, line=bd,
         radius=radius if radius is not None else h / 2)
    _textbox(slide, x + pad_h, y + pad_v, tw, size_px * line_h, [text],
             size_px=size_px, line_h=line_h, color=fg, bold=bold, wrap=False)
    return w, h


# ── 표 테두리 (python-pptx 가 안 열어 주는 부분) ────────────────────────────
_BORDER_TAGS = ("a:lnL", "a:lnR", "a:lnT", "a:lnB")


def _cell_border(cell, color: str, width_pt: float = 0.75) -> None:
    from pptx.oxml.ns import qn
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in _BORDER_TAGS:
        el = tcPr.find(qn(tag))
        if el is not None:
            tcPr.remove(el)
        el = tcPr.makeelement(qn(tag), {
            "w": str(int(width_pt * 12700)), "cap": "flat",
            "cmpd": "sng", "algn": "ctr"})
        fill = el.makeelement(qn("a:solidFill"), {})
        clr = fill.makeelement(qn("a:srgbClr"), {"val": color.upper()})
        fill.append(clr)
        el.append(fill)
        # 순서 규약: lnL, lnR, lnT, lnB 는 tcPr 의 맨 앞에 와야 한다.
        tcPr.insert(_BORDER_TAGS.index(tag), el)


# ── 블록 렌더러 ─────────────────────────────────────────────────────────────
def _draw_q(slide, blk: Block, x, y, w, st) -> None:
    _textbox(slide, x, y, w, L.block_h(blk, st, w), blk.paras,
             size_px=st.q_fs, line_h=st.q_lh, color=INK, bold=True)


def _draw_passage(slide, blk: Block, x, y, w, st) -> None:
    h = L.block_h(blk, st, w)
    _box(slide, x, y, w, h, fill=SOFT, line=LINE, radius=st.pass_radius)
    _textbox(slide, x + st.pass_pad_h, y + st.pass_pad_v,
             w - st.pass_pad_h * 2, h - st.pass_pad_v * 2, blk.paras,
             size_px=st.pass_fs, line_h=st.pass_lh, color=BODY)


def _draw_label(slide, blk: Block, x, y, w, st) -> None:
    _textbox(slide, x, y, w, L.block_h(blk, st, w), blk.paras,
             size_px=st.pass_fs, line_h=st.pass_lh, color=INK, bold=True)


def _draw_pre(slide, blk: Block, x, y, w, st) -> None:
    h = L.block_h(blk, st, w)
    _box(slide, x, y, w, h, fill=PRE_BG, line=None, radius=st.pre_radius)
    _textbox(slide, x + st.pre_pad_h, y + st.pre_pad_v,
             w - st.pre_pad_h * 2, h - st.pre_pad_v * 2, blk.paras,
             size_px=st.pre_fs, line_h=st.pre_lh, color=PRE_FG, mono=True)


def _draw_table(slide, blk: Block, x, y, w, st) -> None:
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from . import metrics as M
    ncol = max(len(blk.headers), max((len(r) for r in blk.rows), default=1), 1)
    has_head = bool(blk.headers)
    nrow = len(blk.rows) + (1 if has_head else 0)
    if nrow == 0 or ncol == 0:
        return
    h = L.block_h(blk, st, w)
    gt = slide.shapes.add_table(nrow, ncol, Emu(L.px_emu(x)), Emu(L.px_emu(y)),
                               Emu(L.px_emu(w)), Emu(L.px_emu(h)))
    tbl = gt.table
    # ★ 자동 밴딩을 끈다 — 켜져 있으면 우리가 칠한 색 위에 테마 색이 덮인다.
    tbl.first_row = False
    tbl.horz_banding = False
    colw = L.px_emu(w / ncol)
    for c in tbl.columns:
        c.width = Emu(colw)

    cw = w / ncol - st.tbl_pad_h * 2 - 2
    rows: List[List[str]] = []
    if has_head:
        rows.append([str(v) for v in blk.headers])
    rows.extend([[str(v) for v in r] for r in blk.rows])

    for i, row in enumerate(rows):
        head = has_head and i == 0
        lines = max([M.line_count(v, st.tbl_fs, L.mw(cw, st.tbl_fs),
                                  weight=700 if head else 400) for v in row] or [1])
        tbl.rows[i].height = Emu(L.px_emu(lines * st.tbl_fs * st.tbl_lh
                                          + st.tbl_pad_v * 2 + 2))
        for j in range(ncol):
            cell = tbl.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(SOFT2 if head else PAPER)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Emu(L.px_emu(st.tbl_pad_h))
            cell.margin_top = cell.margin_bottom = Emu(L.px_emu(st.tbl_pad_v))
            _cell_border(cell, LINE)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            # CSS `text-align:left` — 원본 슬라이드 표는 왼쪽 정렬이다.
            p.alignment = PP_ALIGN.LEFT
            _ea_linebreak(p)
            p.line_spacing = Pt(L.px_pt(st.tbl_fs * st.tbl_lh))
            r = p.add_run()
            r.text = row[j] if j < len(row) else ""
            _set_font(r, size_px=st.tbl_fs, color=INK if head else BODY,
                      bold=head)


def _draw_opts(slide, blk: Block, x, y, w, st, *, correct: str = "") -> None:
    """보기. 열 수는 `layout._opts_cols` 가 정한다 — 재는 쪽과 그리는 쪽이 같아야 한다."""
    from . import metrics as M
    cols = L._opts_cols(blk, st, w)
    n = len(blk.choices)
    if cols == 1:
        cn_w = M.text_width("④", st.opt_fs, weight=800) + st.opt_gap_in
        tw = w - st.opt_pad_h * 2 - 2 - cn_w
        cy = y
        for cn, txt in blk.choices:
            lines = M.line_count(txt, st.opt_fs, L.mw(tw, st.opt_fs))
            ch = lines * st.opt_fs * st.opt_lh + st.opt_pad_v * 2 + 2
            hit = bool(correct) and cn == correct
            _box(slide, x, cy, w, ch,
                 fill=OK_BG if hit else PAPER, line=OK if hit else LINE,
                 radius=st.opt_radius)
            _textbox(slide, x + st.opt_pad_h, cy + st.opt_pad_v,
                     cn_w, st.opt_fs * st.opt_lh, [cn],
                     size_px=st.opt_fs, line_h=st.opt_lh,
                     color=OK if hit else MUTED, bold=True)
            _textbox(slide, x + st.opt_pad_h + cn_w, cy + st.opt_pad_v,
                     tw, ch - st.opt_pad_v * 2, [txt],
                     size_px=st.opt_fs, line_h=st.opt_lh, color=BODY)
            cy += ch + st.opts_gap
        return

    gap = st.opts_gap4 if cols == 4 else st.opts_gap_x2
    cell_w = (w - gap * (cols - 1)) / cols
    tw = cell_w - st.opt_pad_h * 2 - 2
    rows = (n + cols - 1) // cols
    # 한 줄 안의 칸들은 **가장 높은 칸에 맞춘다**(CSS grid 와 같다).
    row_h: List[float] = []
    for r in range(rows):
        hs = []
        for cn, txt in blk.choices[r * cols:(r + 1) * cols]:
            lines = M.line_count(txt, st.opt4_fs, L.mw(tw, st.opt4_fs))
            hs.append(st.opt4_fs * st.opt4_lh + st.opt4_gap
                      + lines * st.opt4_fs * st.opt4_lh
                      + st.opt_pad_v * 2 + 2)
        row_h.append(max(hs) if hs else 0.0)
    cy = y
    for r in range(rows):
        for c, (cn, txt) in enumerate(blk.choices[r * cols:(r + 1) * cols]):
            cx = x + c * (cell_w + gap)
            hit = bool(correct) and cn == correct
            _box(slide, cx, cy, cell_w, row_h[r],
                 fill=OK_BG if hit else PAPER, line=OK if hit else LINE,
                 radius=st.opt_radius)
            _textbox(slide, cx + st.opt_pad_h, cy + st.opt_pad_v,
                     tw, st.opt4_fs * st.opt4_lh, [cn],
                     size_px=st.opt4_fs, line_h=st.opt4_lh,
                     color=OK if hit else MUTED, bold=True)
            _textbox(slide, cx + st.opt_pad_h,
                     cy + st.opt_pad_v + st.opt4_fs * st.opt4_lh + st.opt4_gap,
                     tw, row_h[r] - st.opt_pad_v * 2
                     - st.opt4_fs * st.opt4_lh - st.opt4_gap,
                     [txt], size_px=st.opt4_fs, line_h=st.opt4_lh, color=BODY)
        cy += row_h[r] + st.opts_gap


def _draw_expl(slide, blk: Block, x, y, w, st) -> None:
    # CSS `.slide .expl` 은 상자가 없다 — 글자만이다.
    _textbox(slide, x, y, w, L.block_h(blk, st, w), blk.paras,
             size_px=st.expl_fs, line_h=st.expl_lh, color=BODY,
             para_gap_px=st.expl_p_gap)


def _draw_figure(slide, blk: Block, x, y, w, st, *, max_h: float) -> float:
    """도식. 크기는 `layout.figure_size` 가 정한다 — 재는 쪽과 같은 함수다.

    ★ 폭을 채우지 않는 이유는 그 함수의 머리말에 있다(도식마다 안 글자 크기가
      달라지는 문제). 여기서 폭을 다시 정하면 잰 높이와 어긋난다.
    """
    path = blk.img_path
    if not path or not os.path.isfile(path):
        return 0.0
    dw, dh = L.figure_size(blk, st, w, cap_h=max_h)
    # 가로 가운데 (CSS `justify-content:center`)
    slide.shapes.add_picture(path, Emu(L.px_emu(x + (w - dw) / 2)),
                             Emu(L.px_emu(y)), Emu(L.px_emu(dw)),
                             Emu(L.px_emu(dh)))
    return dh


def _draw_heading(slide, blk: Block, x, y, w, st) -> None:
    _textbox(slide, x, y, w, L.block_h(blk, st, w), blk.paras,
             size_px=st.head3_fs, line_h=st.head3_lh, color=INK, bold=True)


def _draw_bullets(slide, blk: Block, x, y, w, st, *, accent: str = BLUE) -> None:
    """항목 목록. 글머리표를 **본문과 다른 텍스트박스**에 그린다.

    ★ 한 텍스트박스에 `"• " + 본문` 으로 넣으면 둘째 줄이 글머리표 아래로 붙어
      들여쓰기가 풀린다(PowerPoint 의 목록 들여쓰기는 단락 속성이고, 우리는 단락
      간격을 고정값으로 쓰고 있어서 같이 쓰면 어긋난다). 점과 글을 갈라 놓으면
      둘째 줄부터 저절로 맞는다.
    """
    from . import metrics as M
    tw = w - st.bul_indent
    cy = y
    for i, t in enumerate(blk.paras):
        n = M.line_count(t, st.bul_fs, L.mw(tw, st.bul_fs))
        h = n * st.bul_fs * st.bul_lh
        _textbox(slide, x, cy, st.bul_indent, st.bul_fs * st.bul_lh, ["•"],
                 size_px=st.bul_fs, line_h=st.bul_lh, color=accent, bold=True,
                 wrap=False)
        _textbox(slide, x + st.bul_indent, cy, tw, h, [t],
                 size_px=st.bul_fs, line_h=st.bul_lh, color=BODY)
        cy += h + (st.bul_gap if i < len(blk.paras) - 1 else 0)


_DRAW = {
    "heading": _draw_heading,
    "q": _draw_q,
    "passage": _draw_passage,
    "passage_label": _draw_label,
    "pre": _draw_pre,
    "table": _draw_table,
    "expl": _draw_expl,
}


def _draw_block(slide, blk: Block, x, y, w, st, *, correct: str = "",
                accent: str = BLUE) -> float:
    """블록 하나를 그리고 쓴 높이를 돌려준다."""
    if blk.kind == "bullets":
        _draw_bullets(slide, blk, x, y, w, st, accent=accent)
        return L.block_h(blk, st, w)
    if blk.kind == "opts":
        _draw_opts(slide, blk, x, y, w, st, correct=blk.correct)
        return L.block_h(blk, st, w)
    if blk.kind == "figure":
        cap = blk.fixed_h if blk.fixed_h > 0 else L.fig_max_h(st)
        return _draw_figure(slide, blk, x, y, w, st, max_h=cap)
    fn = _DRAW.get(blk.kind)
    if fn is None:
        return 0.0
    fn(slide, blk, x, y, w, st)
    return L.block_h(blk, st, w)


# ── 슬라이드 ────────────────────────────────────────────────────────────────
def _style_for(page: Page):
    """이 장을 **잰 그 판**을 되살린다.

    ★ 전에는 조여 담은 장에 `L.STYLE_DENSE` 를 그대로 돌려줬다. 그것은 배율 1.0
      으로 만들어 둔 상수라 **덱 배율(1.6)이 통째로 사라진다.** 배치기는
      `Scale(TS_DENSE*1.6, SS_DENSE*1.6)` 로 재놓고 그리는 쪽은
      `Scale(TS_DENSE, SS_DENSE)` 로 그렸다 — 잰 크기와 그린 크기가 다르다.

      실측(2026-09-10, ADSP 01회 42번 문제 면): 발문이 이웃 장 25.6pt 인데 혼자
      **13.78pt**, 보기 19.2pt 인데 **10.33pt** 로 나왔다. 그 장만 62% 로
      쪼그라들고 아래가 텅 비었다.

    ★ `page.scale` 은 `st.sc.ts / TS` 로 저장된다(`_pages_for`). 그래서 dense 장은
      `page.scale * TS` 가 그 장의 실제 `ts` 다. 거기서 배율을 되짚어 dense 판을
      같은 배율로 다시 만든다 — 상수를 쓰지 않는다.
    """
    if page.dense:
        mult = (page.scale * L.TS) / L.TS_DENSE
        return L.Style(L.Scale(L.TS_DENSE * mult, L.SS_DENSE * mult))
    return L.style_for(page.scale)


def _content_origin(page: Page):
    """카드 내용이 시작하는 좌표.

    ★ `cont-top` / `cont-bottom` 은 CSS 에서 카드 패딩을 접는다. 그 규약이
      "한 문항이 한 장의 카드처럼 이어져 보인다" 를 만든다(2026-08-12 사용자 확정,
      사용자 재확인 2026-08-21: "하단, 상단에 뭐가 없어요").
    """
    x = L.PAD + L.CARD_PAD
    y = L.PAD + (0 if page.cont_top else L.CARD_PAD) + page.pad_top_px
    return x, y, L.INNER_W


def _slide_cover(prs, page: Page) -> None:
    """간지. 좌측 정렬 · 세로 중앙 (`.slide.cover`)."""
    s = _blank(prs)
    st = L.style_for(1.0)
    x = L.PAD + L.CARD_PAD
    w = L.INNER_W
    eb_fs = st.cover_eyebrow_fs
    ti_fs = st.cover_title_fs
    ld_fs = st.cover_lead_fs
    gap = st.cover_gap
    h_eb = eb_fs * 1.4 if page.cover_eyebrow else 0.0
    h_ti = ti_fs * 1.25
    h_ld = ld_fs * 1.6 if page.cover_lead else 0.0
    total = h_eb + h_ti + h_ld + gap * (bool(h_eb) + bool(h_ld))
    y = (L.SLIDE_H - total) / 2
    if page.cover_eyebrow:
        _textbox(s, x, y, w, h_eb, [page.cover_eyebrow],
                 size_px=eb_fs, line_h=1.4, color=palette(page.subject_no)[0],
                 bold=True)
        y += h_eb + gap
    _textbox(s, x, y, w, h_ti, [page.cover_title],
             size_px=ti_fs, line_h=1.25, color=INK, bold=True)
    y += h_ti
    if page.cover_lead:
        y += gap
        _textbox(s, x, y, w, h_ld, [page.cover_lead],
                 size_px=ld_fs, line_h=1.6, color=MUTED)


def _slide_problem(prs, page: Page) -> None:
    s = _blank(prs)
    st = _style_for(page)
    x, y, w = _content_origin(page)
    if page.head_no:
        cw, ch = _pill(s, x, y, page.head_no, size_px=st.head_fs,
                       pad_v=st.s(3), pad_h=st.s(12),
                       bg=BLUE, fg=PAPER, bd=None)
        if page.head_difficulty:
            _pill(s, x + cw + st.s(8), y, page.head_difficulty,
                  size_px=st.pill_fs, pad_v=st.s(4), pad_h=st.s(9),
                  bg=PILL_BG, fg=PILL_FG, bd=PILL_BD)
        y += st.head_h
    _stack(s, page.blocks, x, y, w, st, page.gap_px)


def _slide_answer(prs, page: Page) -> None:
    s = _blank(prs)
    st = _style_for(page)
    x, y, w = _content_origin(page)
    if page.badge_no:
        label = f"정답 {page.badge_no}"
        if page.badge_text:
            label += f"   {page.badge_text}"
        _, bh = _pill(s, x, y, label, size_px=st.badge_fs,
                      pad_v=st.badge_pad_v, pad_h=st.badge_pad_h,
                      bg=OK_BG, fg=OK, bd=None, max_w=w)
        y += bh + page.gap_px
    _stack(s, page.blocks, x, y, w, st, page.gap_px)


def _stack(slide, blocks: List[Block], x, y, w, st, gap: float,
           *, accent: str = BLUE) -> None:
    prev: Optional[Block] = None
    for blk in blocks:
        if prev is not None:
            # 붙임(라벨→표)은 간격을 주지 않는다 — 한 덩어리로 읽혀야 한다.
            y += 0.0 if prev.glue_next else gap
        used = _draw_block(slide, blk, x, y, w, st, accent=accent)
        y += used
        prev = blk


def _slide_topic(prs, page: Page) -> None:
    """이론 덱 한 장 — 대단원 칩 → 소단원 제목 → 리드·항목·표·도식."""
    s = _blank(prs)
    st = _style_for(page)
    accent, soft = palette(page.subject_no)
    x, y, w = _content_origin(page)
    if page.eyebrow:
        # 대단원 칩. 문제 덱의 문번 알약과 같은 자리·같은 크기다.
        _, ch = _pill(s, x, y, page.eyebrow, size_px=st.eyebrow_fs,
                      pad_v=st.s(3), pad_h=st.s(12),
                      bg=soft, fg=accent, bd=None, max_w=w)
        y += ch + st.s(6)
    if page.heading:
        h = _textbox(s, x, y, w, 0, [page.heading], size_px=st.head3_fs,
                     line_h=st.head3_lh, color=INK, bold=True)
        from . import metrics as M
        hh = M.block_height([page.heading], st.head3_fs, st.head3_lh,
                            L.mw(w, st.head3_fs), weight=700)
        h.height = Emu(L.px_emu(hh))
        y += hh + st.s(10)
    _stack(s, page.blocks, x, y, w, st, page.gap_px, accent=accent)


_SLIDE = {"cover": _slide_cover, "problem": _slide_problem,
          "answer": _slide_answer, "topic": _slide_topic}


def render(pages: List[Page], out_path: str,
           template: Optional[str] = None) -> str:
    from pptx import Presentation
    if template and os.path.exists(template):
        prs = Presentation(template)
        _strip_slides(prs)
    else:
        prs = Presentation()
    prs.slide_width = Emu(L.px_emu(L.SLIDE_W))
    prs.slide_height = Emu(L.px_emu(L.SLIDE_H))
    for pg in pages:
        _SLIDE.get(pg.kind, _slide_problem)(prs, pg)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    prs.save(out_path)
    return out_path
