# -*- coding: utf-8 -*-
"""기하 · 재분할 — **숫자의 단일 소유자.**

★ 단위는 원본 CSS 픽셀이다. `xam-lo/services/deck/theme.py` 가 슬라이드를 1920×1080 으로
  고정했고 PPTX 16:9 는 13.333in = 960pt 이므로 **1920px ↔ 960pt**, 즉

        1 px = 0.5 pt = 6350 EMU        (12192000 EMU / 1920 = 6350, 나머지 없음)

  이다. 그래서 CSS 를 다시 디자인하지 않고 픽셀값을 그대로 옮긴다. 렌더러는
  `px_pt()` / `px_emu()` 만 쓰고 자기 좌표계를 만들지 않는다 — 두 좌표계가 생기면
  어긋난 자리를 눈으로 찾아야 한다.

★ 여기 적힌 수는 전부 `_deck-export/*.html` 의 `<style>` 에서 읽어 온 것이다.
  (`.slide .q{font-size:calc(15px * var(--ts))}` → `Q_FS = 15 * TS`) 값을 바꿀 일이
  생기면 CSS 를 먼저 보고 여기를 맞춘다. 반대로 하지 않는다.

★ **원본 분할기와 다른 점 하나** — 줄 수를 `metrics.py` 로 실측한다. 원본은 한글 1자를
  1.0em 으로 넉넉히 봐서 일찍 쪼갠다(캡처에서 잘리면 내용이 사라지므로 맞는 선택이다).
  PPTX 는 우리가 좌표를 직접 잡으니 재서 놓을 수 있고, 그래야 장마다 아래가 비지 않는다
  (사용자 지적 2026-08-21: "디자인보다는 위치간격이 문제").
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from functools import lru_cache as _lru
from typing import Callable, List, Optional, Tuple

from . import metrics as M
from .ir import Block, Doc, Page, Question, Round, Topic

# ── 캔버스 ──────────────────────────────────────────────────────────────────
SLIDE_W, SLIDE_H = 1920, 1080
PAD = 40                  # 바깥 패딩 (theme.PAD)
CARD_PAD = 20             # 카드 안쪽 패딩 (theme.CARD_PAD)
SAFETY = 12               # 안전 여유 (theme.SAFETY)

INNER_W = SLIDE_W - PAD * 2 - CARD_PAD * 2        # 1800
AVAIL = SLIDE_H - PAD * 2 - CARD_PAD * 2          # 960
SAFE = AVAIL - SAFETY                             # 948

EMU_PER_PX = 6350
PT_PER_PX = 0.5


def px_emu(px: float) -> int:
    return int(round(px * EMU_PER_PX))


def px_pt(px: float) -> float:
    return px * PT_PER_PX


# ── 배율 ────────────────────────────────────────────────────────────────────
TS, SS = 2.67, 2.40                # 기본
TS_DENSE, SS_DENSE = 2.30, 2.05    # `.slide.dense`

# 도식 높이 상한 비율 (theme.FIGURE_MAX_RATIO). AVAIL*0.62 = 595px → `--fig-max:595px`
FIGURE_MAX_RATIO = 0.62
# 해설 면에 보기를 다시 넣을 때의 도식 높이 상한 비율. 배지 + 보기 + 도식 + 해설
# 첫 문단이 한 장에 들어가는 선으로 잡았다(0.62 로 두면 해설이 늘 둘째 장으로 간다).
FIG_ANS_RATIO_WITH_OPTS = 0.40

# 지문(회색)·코드블록(검정) 상자의 모서리 반지름(px). 0 = 각진 모서리.
# 보기 알약은 이것과 무관하다(`Style.opt_radius`).
BOX_RADIUS = 0.0

# ★ 채움 목표. 이 아래면 남은 높이를 간격으로 흡수하고, 그래도 남으면 세로 중앙에 놓는다.
FILL_TARGET = 0.78
# 간격을 최대 몇 배까지 늘리는가. 3배를 넘기면 블록이 서로 남남처럼 보인다.
GAP_MAX_MULT = 2.0
# 문제 면 장수 상한. 넘으면 조여(dense) 다시 담는다. (render.py `cap=5`)
PROBLEM_CAP = 5
# 마지막 장이 이보다 비면 균형 재분배를 시도한다.
LAST_PAGE_MIN_FILL = 0.40
# ★ 줄바꿈 안전 여유 — **글자 폭의 배수**로 잡는다(비율이 아니다).
#
#   같은 폰트 파일의 advance width 로 재지만 PowerPoint 는 자기 커닝·힌팅이 있어
#   1~2px 좁게 끊는다. 처음엔 1.5% 여유(폭 비율)로 뒀는데, 1800px 에서 27px 이라
#   **한 글자보다 작았다.** 그래서 실측에서 문단 끝의 마침표 하나가 셋째 줄로
#   내려가 우리가 잰 높이보다 한 줄 더 커졌다(01회 1번 해설).
#
#   여유는 "한 글자가 더 들어갈지 말지" 를 가르는 값이므로 글자 크기에 비례해야
#   한다. 방향은 늘 "일찍 줄바꿈" — 늦게 끊으면 카드가 넘친다.
#
#   ★ 0.6em → 0.3em 으로 내렸다. 애초에 0.6 이 필요했던 원인(문단 끝 구두점이 혼자
#     다음 줄로 내려가는 것)이 진짜 원인을 고쳐서 사라졌다 — 런의 `lang="ko-KR"` 를
#     안 심어서 PowerPoint 가 라틴 조판 규칙을 쓰고 있었다. 이제 양쪽 다 구두점을
#     매달므로(`metrics._HANG`) 남은 오차는 커닝 수준이고, 0.6 을 유지하면 우리만
#     한 줄을 더 세어 화면에 빈 줄이 남는다.
# ★ 0.3 → 0.8 (2026-09-10). `metrics._tokens` 를 어절 단위로 고치고 나서, 남은
#   오차를 ADSP 01회 1번 보기 4개의 **실제 줄바꿈 자리**로 다시 잡았다.
#     들어간 줄 중 가장 넓은 것  219.5px   (`지식은 지혜를 바탕으로`)
#     넘긴 줄 중 가장 좁은 것    246.3px   (`정성적 데이터에 ⏎해당한다.`)
#   → 폭 253px 칸에서 PowerPoint 의 실효 폭은 이 둘 사이다. 0.3em(245.8px)은
#   위쪽 끝에 0.5px 붙어 있었고, 그 0.5px 때문에 ③번이 한 줄 모자라게 나왔다.
#   0.8em(233.8px)은 두 경계 어느 쪽에서도 멀다.
#
# ★ 방향은 **넉넉히 세는 쪽**이어야 한다. 적게 세면 카드 밖으로 글이 나가고(사람이
#   보고 나서야 안다), 많이 세면 카드가 조금 높아지거나 장이 하나 늘 뿐이다.
WRAP_SAFETY_EM = 0.8

# 남은 조각이 이보다 작으면 다음 장으로 보내지 않고 이 장에 붙인다 (paginate.ORPHAN).
ORPHAN = 150.0
# 고아를 앞 장에 붙일 때 허용하는 넘침 비율 (paginate.TOLERANCE).
TOLERANCE = 0.04


@dataclass
class Scale:
    """한 장의 타입·여백 배율. 기본판과 조밀판 둘뿐이다."""
    ts: float = TS
    ss: float = SS

    def t(self, base: float) -> float:
        """CSS `calc(Npx * var(--ts))`."""
        return base * self.ts

    def s(self, base: float) -> float:
        """CSS `calc(Npx * var(--ss))`."""
        return base * self.ss


NORMAL = Scale(TS, SS)
DENSE = Scale(TS_DENSE, SS_DENSE)

# ── 글자 크기 — **여기가 유일한 출처다** ──────────────────────────────────
#
# ★ 단위는 **pt** 다(px 가 아니다). 사용자가 크기를 pt 로 말하고(2026-08-21:
#   "해설 10이면 되지 않아?! 발문 좀더좀더 크고 보기가 중간이고"), PowerPoint 도
#   pt 로 보여 준다. px 로 적어 두면 값을 옮길 때마다 2로 나눠야 한다.
#
# ★ 원본 CSS 를 그대로 옮기던 것을 **여기서 끊었다.** 원본은 발문 15 · 보기 14 ·
#   해설 13.5px 로 거의 같은 크기였고, `ts=2.67` 을 곱해 20 / 18.7 / 18pt 가 됐다.
#   사용자는 그것이 ① 너무 크고 ② 위계가 없다고 봤다. 그래서 값을 새로 잡는다:
#
#       발문 > 보기 > 해설      (사용자 지시)
#       해설 ≈ 도식 안 글자     (실측 기준: 도식의 13 유닛이 화면에서 12.3pt 였고,
#                              사용자가 그 크기를 "적당" 이라고 했다)
#
# ★ 사용자가 템플릿 샘플을 주면 **이 표만** 고친다. 다른 파일은 건드리지 않는다.
TYPE_PT = {
    # 문제 덱
    "q":        16.0,   # 발문 — 이 장의 주제이므로 가장 크다
    "opt":      12.5,   # 보기 (1단 세로)
    "opt4":     12.0,   # 보기 (1×4 · 2×2 — 칸이 좁아 한 단 작다)
    "passage":  11.0,   # 지문
    "table":    10.0,   # 표
    "expl":     10.0,   # 해설
    "head":     12.0,   # 문번 알약
    "pill":     10.0,   # 난도 알약
    "badge":    12.0,   # 정답 배지
    "pre":      10.0,   # 코드블록
    # 이론 덱
    "head3":    17.0,   # 소단원 제목
    "eyebrow":  11.0,   # 대단원 칩
    "bullets":  10.5,   # 항목
    # 도식 — **안 글자**의 목표 크기. 도식을 얼마나 키울지 이 값이 정한다.
    #   사용자 확정(2026-08-21): "svg의 글자가 적당하다는거야" — 기준으로 보여 준
    #   화면의 도식 안 글자가 12.3pt 였다. 본문(해설 10pt)보다 조금 큰 것이 맞다.
    "fig_text": 12.0,
    # 표지
    "cover_eyebrow": 12.0,
    "cover_title":   28.0,
    "cover_lead":    12.0,
}

# 여백 배율. 글자가 작아진 만큼 같이 줄여야 한다 — 안 줄이면 간격만 큰 화면이 된다.
# (원본 ss=2.40 · 글자가 0.55배가 됐으므로 여백도 그 근처로 잡았다.)
SPACE_SS = 1.35

# ★ 위 두 값은 **템플릿이 덮어쓸 수 있다**(`template_spec` · `apply_spec`).
#   기본값을 따로 보관해 두는 이유: 템플릿 없이 돌릴 때마다 여기로 되돌아와야 하고,
#   웹 서버는 한 프로세스에서 여러 작업을 돌리므로 앞 작업의 규격이 남으면 안 된다.
_DEFAULT_TYPE_PT = dict(TYPE_PT)
_DEFAULT_PAD = PAD
_GAP_PX: Optional[float] = None      # 템플릿이 준 블록 간격(px). None 이면 계산값.


def apply_spec(spec: Optional[dict] = None) -> dict:
    """템플릿 규격을 적용한다. **작업 시작마다 반드시 부른다**(빈 spec 이면 기본값).

    반환: 실제로 적용된 값(리포트에 남긴다 — 무엇이 먹었는지 보여야 한다).
    """
    global PAD, INNER_W, AVAIL, SAFE, _GAP_PX
    TYPE_PT.clear()
    TYPE_PT.update(_DEFAULT_TYPE_PT)
    PAD = _DEFAULT_PAD
    _GAP_PX = None
    spec = spec or {}
    TYPE_PT.update(spec.get("type_pt") or {})
    if spec.get("pad_px"):
        PAD = float(spec["pad_px"])
    if spec.get("gap_px"):
        _GAP_PX = float(spec["gap_px"])
    # ★ 파생 상수를 다시 계산한다. 안 하면 여백만 바뀌고 예산은 옛 값으로 남는다.
    INNER_W = SLIDE_W - PAD * 2 - CARD_PAD * 2
    AVAIL = SLIDE_H - PAD * 2 - CARD_PAD * 2
    SAFE = AVAIL - SAFETY
    style_for.cache_clear()
    return {"type_pt": dict(TYPE_PT), "pad_px": PAD, "gap_px": _GAP_PX,
            "inner_w": INNER_W, "safe": SAFE}


# ── 요소별 치수 ────────────────────────────────────────────────────────────
class Style:
    """한 배율에서의 실제 픽셀 치수.

    ★ 글자는 `TYPE_PT` 에서, 여백은 원본 CSS 의 px × `SPACE_SS` 에서 온다.
      `sc.ts` 는 이제 **전체 배율**(1.0 = 기본)이고 원본 CSS 의 2.67 이 아니다.
    """

    def __init__(self, sc: Scale):
        self.sc = sc
        mult = sc.ts / TS                      # 1.0 = 기본
        self.mult = mult

        def f(key: str) -> float:
            """pt → px. 1px = 0.5pt 이므로 ×2 다."""
            return TYPE_PT[key] * 2.0 * mult

        def s(base: float) -> float:
            """원본 CSS 의 여백 px × SPACE_SS × 배율."""
            return base * SPACE_SS * mult

        # ★ 밖에서도 여백을 재야 한다(렌더러의 알약 패딩 등). `sc.s()` 를 쓰면
        #   원본 CSS 의 2.40 이 걸려 여기와 어긋난다 — 반드시 이 통로로 온다.
        self.s = s
        self.f = f
        self.card_gap = (_GAP_PX * mult) if _GAP_PX else s(10)
        # 머리 — 문번 알약 + 난도 알약
        self.head_fs = f("head")
        self.pill_fs = f("pill")
        self.head_h = self.head_fs * 1.4 + s(8)
        # 발문
        self.q_fs, self.q_lh = f("q"), 1.5
        # 지문
        self.pass_fs, self.pass_lh = f("passage"), 1.6
        self.pass_pad_v, self.pass_pad_h = s(12), s(14)
        # ★ **지문·코드블록은 각지게.** 보기 알약과 달리 여기는 모서리를 굴리지
        #   않는다(2026-08-25 지시). 굴린 검정 상자가 슬라이드에서 버튼처럼 보여
        #   "누르는 것" 으로 읽힌다 — 보기(`opt_radius`)만 굴린다.
        self.pass_radius = BOX_RADIUS
        # 보기
        self.opt_fs, self.opt_lh = f("opt"), 1.4
        self.opt_pad_v, self.opt_pad_h = s(6), s(12)
        self.opt_gap_in = s(10)
        self.opt_radius = s(10)
        self.opts_gap = s(8)
        self.opts_gap_x2 = s(18)
        self.opts_gap4 = s(10)
        self.opt4_fs, self.opt4_lh = f("opt4"), 1.35
        self.opt4_gap = s(3)
        # 정답 배지
        self.badge_fs = f("badge")
        self.badge_pad_v, self.badge_pad_h = s(5), s(14)
        # 해설
        self.expl_fs, self.expl_lh = f("expl"), 1.7
        self.expl_p_gap = s(9)
        # 표
        self.tbl_fs, self.tbl_lh = f("table"), 1.45
        self.tbl_pad_v, self.tbl_pad_h = s(6), s(10)
        # 코드블록
        self.pre_fs, self.pre_lh = f("pre"), 1.5
        self.pre_pad_v, self.pre_pad_h = s(14), s(16)
        self.pre_radius = BOX_RADIUS          # 위 `pass_radius` 와 같은 결정
        # 도식 — 안 글자를 이 크기로 맞춘다 (`figure_size`)
        self.fig_text_fs = f("fig_text")
        self.fig_gap = s(6)
        self.ansrow_gap = s(16)
        self.ansfig_ratio = 0.44
        self.anstxt_gap = s(8)
        # 이론 덱
        self.eyebrow_fs = f("eyebrow")
        self.head3_fs, self.head3_lh = f("head3"), 1.35
        self.bul_fs, self.bul_lh = f("bullets"), 1.7
        self.bul_gap = s(7)
        self.bul_indent = s(16)
        # 표지
        self.cover_eyebrow_fs = f("cover_eyebrow")
        self.cover_title_fs = f("cover_title")
        self.cover_lead_fs = f("cover_lead")
        self.cover_gap = s(14)


# ★★ 키우는 사다리 — `dense` 의 반대다. **이것이 "위치간격" 문제의 실제 해답이다.**
#
#   원본 ts=2.67 은 *하한*이다("1080p h.264 에서 읽히는 최소 크기", slidecss.py).
#   상한이 아니다. 그런데 줄 수를 실측으로 정확히 재고 나면 한 문항이 예산의 39%
#   (01회 중앙값)밖에 안 쓴다 — 원본이 한글 1자를 1.0em 으로 넉넉히 보던 탓에
#   과분할되어 있던 것이 풀렸기 때문이다. 그 결과가 첨부한 11번 슬라이드처럼
#   아래가 크게 빈 화면이다.
#
#   간격만 늘려서는 못 메운다(간격을 2배로 해도 몇십 px 이다). 메우는 방법은 하나뿐 —
#   **글자를 키운다.** 1920×1080 을 핸드폰으로 보는 시청자에게 이건 순이득이다
#   (원본 주석이 되풀이해 걱정하는 것도 "핸드폰에서 글자가 안 보인다" 쪽이다).
#
#   ★★ **2026-08-21 정정 — 이 사다리를 기본으로 쓰지 않는다.**
#
#     사용자가 실제 산출물을 보고 지적했다: "폰트들이 너무 큰데… 요소의 사이즈들이
#     제각각이면 안되고". 09회 실측에서 발문이 21.6pt ~ 38.0pt 로 장마다 달랐다.
#
#     채움률을 올리려고 장마다 배율을 따로 고른 것이 원인이다. 그런데 사용자는
#     빈자리를 문제로 보지 않는다: **"위쪽으로 붙어보여도 상관이 없어… 끝이 비어도
#     상관이 없다는 거지."** 즉 이 거래는 처음부터 반대였다 — 크기의 일관성이
#     채움률보다 중요하다. 슬라이드가 이어질 때 글자 크기가 튀는 것이 빈 아래쪽보다
#     훨씬 눈에 거슬린다.
#
#     그래서 기본값은 **고정 배율 1.0**(원본 CSS ts=2.67 = 발문 20pt)이고, 남는
#     자리는 그냥 비워 둔다. 사다리는 `--scale` 로 전체를 한 번에 키울 때만 쓴다 —
#     그때도 **모든 장이 같은 값**이다.
# 전체 배율로 쓸 수 있는 값들. 장마다 고르는 것이 아니라 **덱 하나에 하나**다.
GROW_LADDER = (1.0, 1.08, 1.16, 1.25, 1.35, 1.45, 1.55, 1.65,
               1.78, 1.90, 2.05, 2.20)

# ★ 기본 배율. 원본 CSS 와 같다(ts 2.67 → 발문 20pt · 보기 17.4pt · 해설 18pt).
#   덱 전체가 이 하나를 쓴다. 바꾸려면 CLI `--scale` 또는 지시문 `scale=1.2`.
DEFAULT_SCALE = 1.0


@_lru(maxsize=64)
def style_for(mult: float) -> "Style":
    """배율 `mult` 배 판. 1.0 이 원본 CSS(ts 2.67 / ss 2.40)."""
    return Style(Scale(TS * mult, SS * mult))


STYLE_NORMAL = Style(NORMAL)
STYLE_DENSE = Style(DENSE)


def mw(width: float, size_px: float) -> float:
    """**잴 때** 쓰는 폭. 그릴 때는 제 폭을 쓴다 — `WRAP_SAFETY_EM` 머리말 참고."""
    return max(size_px, width - size_px * WRAP_SAFETY_EM)


# ── 블록 높이 ───────────────────────────────────────────────────────────────
def _opts_cols(blk: Block, st: Style, width: float) -> int:
    """보기 배치 열 수. 1 / 2 / 4.

    ★ HTML 의 `ch4`(1×4) 를 기본으로 유지한다 — 원본 덱이 그것으로 나갔고, 사용자가
      고쳐 달라고 한 것은 배치가 아니라 간격이다. 다만 칸이 좁아 4줄을 넘기면 2×2 로
      내려간다(칸이 두 배 넓어져 줄 수가 절반이 된다). 보기가 4개가 아니면 1단이다.
    """
    n = len(blk.choices)
    if n != 4:
        return 1
    lines = _opt4_max_lines(blk, st, width, 4)
    if lines <= OPT4_MAX_LINES:
        return 4
    if _opt4_max_lines(blk, st, width, 2) <= OPT2_MAX_LINES:
        return 2
    return 1


OPT4_MAX_LINES = 4      # 1×4 를 유지하는 한 칸의 줄 수 상한
OPT2_MAX_LINES = 5      # 2×2 를 유지하는 한 칸의 줄 수 상한


def _opt_cell_w(st: Style, width: float, cols: int) -> float:
    gap = st.opts_gap4 if cols == 4 else st.opts_gap_x2
    return (width - gap * (cols - 1)) / cols


def _opt4_max_lines(blk: Block, st: Style, width: float, cols: int) -> int:
    cw = _opt_cell_w(st, width, cols) - st.opt_pad_h * 2 - 2
    return max(M.line_count(t, st.opt4_fs, mw(cw, st.opt4_fs)) for _, t in blk.choices)


def _opts_h(blk: Block, st: Style, width: float) -> float:
    cols = _opts_cols(blk, st, width)
    if cols == 1:
        # 한 줄에 하나. 원숫자와 본문이 나란히(flex row).
        cn_w = M.text_width("④", st.opt_fs, weight=800) + st.opt_gap_in
        tw = width - st.opt_pad_h * 2 - 2 - cn_w
        h = 0.0
        for _, t in blk.choices:
            n = M.line_count(t, st.opt_fs, mw(tw, st.opt_fs))
            h += n * st.opt_fs * st.opt_lh + st.opt_pad_v * 2 + 2
        return h + st.opts_gap * (len(blk.choices) - 1)
    # 2 또는 4 칸 — 원숫자를 본문 위에 쌓는다(.ch4 .opt{flex-direction:column}).
    cw = _opt_cell_w(st, width, cols) - st.opt_pad_h * 2 - 2
    heights = []
    for _, t in blk.choices:
        n = M.line_count(t, st.opt4_fs, mw(cw, st.opt4_fs))
        heights.append(st.opt4_fs * st.opt4_lh                # 원숫자 줄
                       + st.opt4_gap
                       + n * st.opt4_fs * st.opt4_lh
                       + st.opt_pad_v * 2 + 2)
    rows = math.ceil(len(heights) / cols)
    total = 0.0
    for r in range(rows):
        total += max(heights[r * cols:(r + 1) * cols])
    return total + st.opts_gap * (rows - 1)


def _table_h(blk: Block, st: Style, width: float) -> float:
    ncol = max(len(blk.headers), max((len(r) for r in blk.rows), default=1), 1)
    cw = width / ncol - st.tbl_pad_h * 2 - 2
    h = 0.0
    if blk.headers:
        n = max(M.line_count(c, st.tbl_fs, mw(cw, st.tbl_fs), weight=700) for c in blk.headers)
        h += n * st.tbl_fs * st.tbl_lh + st.tbl_pad_v * 2 + 2
    for row in blk.rows:
        n = max([M.line_count(c, st.tbl_fs, mw(cw, st.tbl_fs)) for c in row] or [1])
        h += n * st.tbl_fs * st.tbl_lh + st.tbl_pad_v * 2 + 2
    return h


def _pre_h(blk: Block, st: Style, width: float) -> float:
    tw = width - st.pre_pad_h * 2
    n = sum(M.line_count(ln, st.pre_fs, mw(tw, st.pre_fs), mono=True) or 1 for ln in blk.paras)
    return n * st.pre_fs * st.pre_lh + st.pre_pad_v * 2


def fig_max_h(st: Style) -> float:
    return AVAIL * FIGURE_MAX_RATIO


def figure_size(blk: Block, st: Style, width: float,
                cap_h: float = 0.0) -> Tuple[float, float]:
    """도식의 배치 크기 (폭, 높이). **재는 쪽과 그리는 쪽이 이 함수를 같이 쓴다.**

    ★ 폭을 다 채우지 않는다. 폭에 맞춰 늘리면 **도식마다 안 글자 크기가 달라진다** —
      viewBox 가로가 400 인 도식과 1040 인 도식이 같은 폭으로 늘어나면 라벨이
      2.6배 차이 난다. 실제로 그래서 어떤 장은 도식 글자가 본문보다 크고 어떤 장은
      개미만 했다(사용자 지적: "그냥 두면 되게 이상해").

      그래서 **안 글자를 `TYPE_PT["fig_text"]` 에 맞춘다.** 확대율은
      `목표 글자 / 도식 안 글자` 이고, 그 결과 폭이 자리보다 크면 자리에 맞춘다
      (그때는 글자가 목표보다 작아지지만 잘리는 것보다 낫다).

    ★ `font-size` 가 없는 도식(도형만 있는 것)은 잴 기준이 없으므로 폭을 채운다.
    """
    cap = cap_h or fig_max_h(st)
    aspect = blk.aspect if blk.aspect and blk.aspect > 0 else 1.0
    if blk.svg_font and blk.svg_vw:
        w = blk.svg_vw * (st.fig_text_fs / blk.svg_font)
    else:
        w = width
    w = min(w, width)
    h = w / aspect
    if h > cap:                       # 높이가 자리를 넘으면 높이에 맞춘다
        h = cap
        w = h * aspect
    return w, h


def _figure_h(blk: Block, st: Style, width: float) -> float:
    return figure_size(blk, st, width)[1]


def block_h(blk: Block, st: Style, width: float) -> float:
    """블록 하나의 높이(px)."""
    if blk.fixed_h > 0:
        return blk.fixed_h
    k = blk.kind
    if k == "q":
        return M.block_height(blk.paras, st.q_fs, st.q_lh, mw(width, st.q_fs), weight=700)
    if k == "passage":
        tw = width - st.pass_pad_h * 2 - 2
        return (M.block_height(blk.paras, st.pass_fs, st.pass_lh, mw(tw, st.pass_fs))
                + st.pass_pad_v * 2 + 2)
    if k == "passage_label":
        # 라벨은 상자가 없다 — 굵은 한 줄.
        return M.block_height(blk.paras, st.pass_fs, st.pass_lh, mw(width, st.pass_fs), weight=700)
    if k == "table":
        return _table_h(blk, st, width)
    if k == "pre":
        return _pre_h(blk, st, width)
    if k == "opts":
        return _opts_h(blk, st, width)
    if k == "figure":
        return _figure_h(blk, st, width)
    if k == "expl":
        return M.block_height(blk.paras, st.expl_fs, st.expl_lh, mw(width, st.expl_fs),
                              para_gap=st.expl_p_gap)
    if k == "heading":
        return M.block_height(blk.paras, st.head3_fs, st.head3_lh,
                              mw(width, st.head3_fs), weight=700)
    if k == "bullets":
        # 글머리표만큼 좁은 폭에 글이 들어간다.
        tw = width - st.bul_indent
        n = sum(M.line_count(t, st.bul_fs, mw(tw, st.bul_fs)) for t in blk.paras)
        return (n * st.bul_fs * st.bul_lh
                + st.bul_gap * max(0, len(blk.paras) - 1))
    return 0.0


def badge_label(q: Question, *, with_text: bool) -> str:
    """정답 배지 글자. 렌더러와 **같은 식**을 써야 높이가 맞는다.

    ★ `with_text=False` 는 같은 장에 보기가 다시 실릴 때다. 그때 정답 본문을 배지에도
      넣으면 바로 아래 초록 칸과 **똑같은 문장이 두 번** 나온다(05회 5번은 88자짜리가
      겹쳐서 배지가 두 줄을 먹었다). 원본이 배지에 본문을 넣은 이유는 보기를 반복하지
      않아서 "정답 ③" 만 보면 시청자가 앞 화면을 기억해야 했기 때문이다 — 보기를
      되살린 지금은 그 이유가 없다.
    """
    s = f"정답 {q.answer_no}"
    if with_text and q.answer_text:
        s += f"   {q.answer_text}"
    return s


def badge_h(st: Style, text: str = "") -> float:
    """정답 배지 높이. 길면 전폭 상자로 떨어져 여러 줄이 된다(`pptx_render._pill`)."""
    lines = 1
    if text:
        w1 = M.text_width(text, st.badge_fs, weight=800) * 1.02 + 2
        if w1 + st.badge_pad_h * 2 > INNER_W:
            lines = M.line_count(text, st.badge_fs,
                                 mw(INNER_W - st.badge_pad_h * 2, st.badge_fs), weight=800)
    return lines * st.badge_fs * 1.4 + st.badge_pad_v * 2


# ── 조각 ────────────────────────────────────────────────────────────────────
@dataclass
class Piece:
    """카드에 들어가는 한 덩어리. 자리는 `h`, 내용은 `block` 이다."""
    block: Block
    h: float
    glue_next: bool = False
    # 이 블록을 더 쪼갤 수 있으면 `splitter(room, width, st)` → (앞조각, 뒷조각)
    splitter: Optional[Callable] = None


def _split_table(blk: Block, room: float, st: Style, width: float):
    """표를 행으로 쪼갠다. 머리 행은 **두 쪽 다** 붙인다 — 열 뜻이 사라지면 못 읽는다."""
    ncol = max(len(blk.headers), max((len(r) for r in blk.rows), default=1), 1)
    cw = width / ncol - st.tbl_pad_h * 2 - 2
    head_h = 0.0
    if blk.headers:
        n = max(M.line_count(c, st.tbl_fs, mw(cw, st.tbl_fs), weight=700) for c in blk.headers)
        head_h = n * st.tbl_fs * st.tbl_lh + st.tbl_pad_v * 2 + 2
    used = head_h
    cut = 0
    for i, row in enumerate(blk.rows):
        n = max([M.line_count(c, st.tbl_fs, mw(cw, st.tbl_fs)) for c in row] or [1])
        rh = n * st.tbl_fs * st.tbl_lh + st.tbl_pad_v * 2 + 2
        if used + rh > room:
            break
        used += rh
        cut = i + 1
    # 한 행도 못 넣거나 전부 들어가면 쪼갤 값이 없다.
    if cut == 0 or cut >= len(blk.rows):
        return None
    a = Block(kind="table", headers=list(blk.headers), rows=blk.rows[:cut])
    b = Block(kind="table", headers=list(blk.headers), rows=blk.rows[cut:])
    return a, b


def _split_pre(blk: Block, room: float, st: Style, width: float):
    """코드블록을 줄로 쪼갠다."""
    tw = width - st.pre_pad_h * 2
    used = st.pre_pad_v * 2
    cut = 0
    for i, ln in enumerate(blk.paras):
        n = M.line_count(ln, st.pre_fs, mw(tw, st.pre_fs), mono=True) or 1
        lh = n * st.pre_fs * st.pre_lh
        if used + lh > room:
            break
        used += lh
        cut = i + 1
    if cut == 0 or cut >= len(blk.paras):
        return None
    return (Block(kind="pre", paras=blk.paras[:cut]),
            Block(kind="pre", paras=blk.paras[cut:]))


def _split_paras(blk: Block, room: float, st: Style, width: float):
    """문단 블록(지문·해설)을 문단 단위로 쪼갠다."""
    if len(blk.paras) < 2:
        return None
    if blk.kind == "expl":
        fs, lh, gap, tw = st.expl_fs, st.expl_lh, st.expl_p_gap, width
        extra = 0.0
    else:
        fs, lh, gap = st.pass_fs, st.pass_lh, 0.0
        tw = width - st.pass_pad_h * 2 - 2
        extra = st.pass_pad_v * 2 + 2
    used = extra
    cut = 0
    for i, p in enumerate(blk.paras):
        ph = M.line_count(p, fs, mw(tw, fs)) * fs * lh + (gap if i else 0)
        if used + ph > room:
            break
        used += ph
        cut = i + 1
    if cut == 0 or cut >= len(blk.paras):
        return None
    return (Block(kind=blk.kind, paras=blk.paras[:cut]),
            Block(kind=blk.kind, paras=blk.paras[cut:]))


def _split_bullets(blk: Block, room: float, st: Style, width: float):
    """항목 목록을 항목 단위로 쪼갠다. 한 항목을 반으로 자르지는 않는다."""
    if len(blk.paras) < 2:
        return None
    tw = width - st.bul_indent
    used = 0.0
    cut = 0
    for i, t in enumerate(blk.paras):
        h = (M.line_count(t, st.bul_fs, mw(tw, st.bul_fs)) * st.bul_fs * st.bul_lh
             + (st.bul_gap if i else 0))
        if used + h > room:
            break
        used += h
        cut = i + 1
    if cut == 0 or cut >= len(blk.paras):
        return None
    return (Block(kind="bullets", paras=blk.paras[:cut]),
            Block(kind="bullets", paras=blk.paras[cut:]))


_SPLITTERS = {"table": _split_table, "pre": _split_pre,
              "passage": _split_paras, "expl": _split_paras,
              "bullets": _split_bullets}


def to_pieces(blocks: List[Block], st: Style, width: float) -> List[Piece]:
    out: List[Piece] = []
    for b in blocks:
        out.append(Piece(block=b, h=block_h(b, st, width),
                         glue_next=b.glue_next,
                         splitter=_SPLITTERS.get(b.kind)))
    return out


# ── 담기 ────────────────────────────────────────────────────────────────────
@dataclass
class Packed:
    pieces: List[Piece] = field(default_factory=list)
    used: float = 0.0
    budget: float = 0.0

    def fill(self) -> float:
        return (self.used / self.budget) if self.budget else 0.0


def _budget(first: bool, last: bool, *, head_h: float) -> float:
    """이 장의 내용 예산(px).

    ★ `cont-top` / `cont-bottom` 이 카드 패딩을 접으므로(CSS `.slide.cont-top{padding-top:0}`)
      이어지는 장은 그만큼 넓다. 원본 `paginate.BUDGET_CONT` 가 실측 928px 로
      박아 둔 값을 여기서는 **식으로** 낸다 — 패딩을 바꿨을 때 두 곳이 어긋나지 않게.
    """
    b = SAFE
    if first:
        b -= head_h            # 머리(문번·난도) 한 줄. 문제 면 첫 장에만 있다.
    else:
        b += CARD_PAD          # cont-top: 상단 패딩 접힘
    if not last:
        b += CARD_PAD          # cont-bottom: 하단 패딩 접힘
    return b


def pack(pieces: List[Piece], st: Style, width: float, *, head_h: float,
         budget_scale: float = 1.0, keep_split: bool = False) -> List[Packed]:
    """조각을 장으로 담는다. 간격은 담을 때 함께 센다.

    ★ `budget_scale` 은 균형 재분배용이다. 1.0 보다 작게 주면 일찍 넘겨 앞 장을
      덜 채우고, 그 결과 마지막 장이 덜 빈다.

    ★ `keep_split` (xam-local) — **사람이 장수를 정했을 때** 켠다. 고아 보정
      (`_fix_orphan`)이 방금 만든 마지막 장을 앞 장에 도로 붙여 버리기 때문이다
      (실측: 「문제 1장 → 2장」 지정이 늘 실패했다. 보기 138px 이 ORPHAN 150px 보다
      작아 되돌려졌다). 사람이 정한 장수는 자동 보정보다 위다.
    """
    pages: List[Packed] = []
    cur: List[Piece] = []
    used = 0.0
    queue = list(pieces)
    gap = st.card_gap
    i = 0
    guard = 0
    while i < len(queue):
        guard += 1
        if guard > 4000:                       # 쪼개기가 진척 없이 도는 것을 막는다
            break
        p = queue[i]
        # ★ 예산은 **가장 좁은 경우**(마지막 장)로 잡는다. 마지막 장인지는 다 담아
        #   봐야 아는데, 넉넉한 쪽으로 잡으면 마지막 장이 최대 CARD_PAD(20px) 넘친다.
        #   중간 장을 20px 덜 채우는 것은 눈에 안 보이고, 넘치는 것은 보인다.
        cap = _budget(not pages, True, head_h=head_h) * budget_scale
        add = p.h + (gap if cur else 0.0)
        if used + add <= cap:
            cur.append(p)
            used += add
            i += 1
            continue
        # 안 들어간다 — 쪼갤 수 있으면 쪼개서 남은 자리를 채운다.
        room = cap - used - (gap if cur else 0.0)
        if p.splitter and room > st.q_fs * 2:
            r = p.splitter(p.block, room, st, width)
            if r:
                a, b = r
                cur.append(Piece(block=a, h=block_h(a, st, width)))
                pages.append(Packed(pieces=cur, used=used + gap * bool(cur[:-1])
                                    + block_h(a, st, width)))
                cur, used = [], 0.0
                queue[i] = Piece(block=b, h=block_h(b, st, width),
                                 splitter=_SPLITTERS.get(b.kind))
                continue
        if not cur:
            # 쪼갤 수 없는데 한 장보다 크다 — 그대로 한 장에 놓는다(넘침은 리포트가 잡는다).
            cur.append(p)
            used += p.h
            i += 1
            pages.append(Packed(pieces=cur, used=used))
            cur, used = [], 0.0
            continue
        pages.append(Packed(pieces=cur, used=used))
        cur, used = [], 0.0
    if cur:
        pages.append(Packed(pieces=cur, used=used))
    # ★ 붙임(glue) 보정 — 라벨이 장 끝에 혼자 남으면 다음 장으로 내린다.
    _fix_glue(pages, st)
    # ★ 고아 보정 — 마지막 장이 ORPHAN 보다 작으면 앞 장에 붙여 본다.
    if not keep_split:
        _fix_orphan(pages, st, head_h)
    # 확정된 장 수로 예산을 다시 매긴다(마지막 장 여부가 이제 정해졌다).
    n = len(pages)
    for k, pg in enumerate(pages):
        pg.budget = _budget(k == 0, k == n - 1, head_h=head_h)
    return pages


def _fix_glue(pages: List[Packed], st: Style) -> None:
    for k in range(len(pages) - 1):
        pg = pages[k]
        while pg.pieces and pg.pieces[-1].glue_next:
            moved = pg.pieces.pop()
            pg.used -= moved.h + (st.card_gap if pg.pieces else 0.0)
            nxt = pages[k + 1]
            nxt.pieces.insert(0, moved)
            nxt.used += moved.h + (st.card_gap if len(nxt.pieces) > 1 else 0.0)


def _fix_orphan(pages: List[Packed], st: Style, head_h: float) -> None:
    """마지막 장이 한 줄만 남았으면 앞 장에 붙인다.

    ★ 원본 규칙과 같다(`paginate.ORPHAN`, "3번은 한 줄 붙은 채로 가자"). 그 한 줄짜리
      장이 영상에서 가장 나쁘다 — 1920×1080 에 한 줄만 떠서 핸드폰에서 안 읽힌다.
      약간 넘치는 것은 괜찮다고 사용자가 정했다("밑에가 상관이 없어요 약간은").

    ★ 다만 허용치는 **예산의 4%** 다(원본 `paginate.TOLERANCE`). ORPHAN(150px)까지
      넘치게 두면 카드가 슬라이드 밖으로 나간다 — 실측에서 01회 77번이 예산 880px 에
      939px 로 병합되어 카드 아래가 47px 삐져나갔다. 넘칠 자리는 카드 바깥 패딩
      (AVAIL 960 − SAFE 948 = 12px)뿐이고, 4% (약 35px)면 그 안이다.
    """
    if len(pages) < 2:
        return
    last = pages[-1]
    if last.used > ORPHAN or any(p.splitter for p in last.pieces):
        return
    prev = pages[-2]
    room = _budget(len(pages) == 2, True, head_h=head_h)
    if prev.used + st.card_gap + last.used <= room * (1.0 + TOLERANCE):
        prev.pieces.extend(last.pieces)
        prev.used += st.card_gap + last.used
        pages.pop()


def _balance(pieces: List[Piece], st: Style, width: float, head_h: float,
             pages: List[Packed]) -> List[Packed]:
    """장 수를 유지한 채 마지막 장을 덜 비게 만든다.

    ★★ **더는 부르지 않는다**(2026-09-10). 함수는 남겨 둔다 — 왜 안 쓰는지가
       코드에 보여야 하고, 되살릴 일이 생기면 여기만 고치면 된다.

       이것이 앞 장을 일부러 비웠다. 예산을 0.94→0.70 으로 줄여 다시 담으므로
       앞 장에 들어가던 조각이 뒤로 밀린다. 실측(ADSP 01회 2번, 배율 1.6):

           그리디      1장 발문·지문·도식 90.0%   2장 보기 25.0%
           _balance    1장 발문·지문     23.3%   2장 도식·보기 86.8%

       뒤엣것이 나갔다. 발문이 "**위** 도식의 ( )에" 라고 하는데 도식은 다음
       장에 있었고, 발문 장은 23% 만 차 있었다. 사용자 지적 그대로다 —
       *"발문 밑은 비고, 뒤가 뚱뚱하면 종이인쇄면 사고처럼 보인다."*

    ★ 마지막 장이 비는 것은 이미 허용된 것이다(`_absorb` 머리말, 2026-08-21:
      *"위쪽으로 붙어보여도 상관이 없어… 끝이 비어도 상관이 없다"*). 이 함수는
      그 결정과 처음부터 어긋나 있었다.
    """
    if len(pages) < 2 or pages[-1].fill() >= LAST_PAGE_MIN_FILL:
        return pages
    best = pages
    for scale in (0.94, 0.88, 0.82, 0.76, 0.70):
        cand = pack(pieces, st, width, head_h=head_h, budget_scale=scale)
        if len(cand) != len(pages):
            continue
        if cand[-1].fill() > best[-1].fill():
            best = cand
        if best[-1].fill() >= LAST_PAGE_MIN_FILL:
            break
    return best


# ── 잔여 공간 흡수 ──────────────────────────────────────────────────────────
def _absorb(pg: Packed, st: Style, *, standalone: bool) -> Tuple[float, float]:
    """블록 간 간격과 위 여백. **둘 다 고정값이다.**

    ★ 전에는 남은 높이를 간격으로 흘리고 단독 장은 세로 중앙에 놓았다. 지웠다 —
      사용자가 "위쪽으로 붙어보여도 상관이 없어… 끝이 비어도 상관이 없다" 고
      정했고(2026-08-21), 장마다 간격이 달라지는 것이 곧 "요소 사이즈가 제각각"
      으로 보인다. 같은 블록이 어느 장에 있든 같은 자리에 있어야 한다.

    ★ 함수를 지우지 않고 남긴다 — 호출부가 둘(문제·이론)이고, "여기서 흡수하지
      않는다" 는 결정이 코드에 보여야 한다. 되살릴 일이 생기면 여기만 고친다.
    """
    return st.card_gap, 0.0


# ── 문항 → 장 ───────────────────────────────────────────────────────────────
def _problem_pages(q: Question, st: Style,
                   budget_scale: float = 1.0) -> List[Packed]:
    """주어진 배율에서 문제 면을 장으로 담는다.

    ★ `budget_scale` 은 **장수를 사람이 지정했을 때만** 1.0 이 아니다
      (`_force_pages`). 일찍 넘겨 장을 더 만드는 손잡이다.
    """
    blocks = _reorder_top_figures(q.blocks)
    pieces = to_pieces(blocks, st, INNER_W)
    pages = pack(pieces, st, INNER_W, head_h=st.head_h,
                 budget_scale=budget_scale, keep_split=(budget_scale != 1.0))
    # ★ 균형 재분배를 하지 않는다 — 들어가는 만큼 앞에서 채운다(`_balance` 머리말).
    return pages


def _reorder_top_figures(blocks: List[Block]) -> List[Block]:
    """CSS `figure.diagram{order:-1}` 재현 — `top` 인 그림만 맨 앞으로.

    ★ 순서를 파서에서 바꾸지 않고 여기서 바꾼다. 파서는 DOM 을 그대로 옮기는 일만
      하고, "왜 앞으로 왔는가" 는 CSS 규칙이므로 레이아웃의 몫이다.
    """
    tops = [b for b in blocks if b.kind == "figure" and b.top]
    if not tops:
        return blocks
    rest = [b for b in blocks if not (b.kind == "figure" and b.top)]
    return tops + rest


def _answer_pages(q: Question, st: Style, *, repeat_opts: bool = True,
                  budget_scale: float = 1.0) -> List[Packed]:
    """해설 장. 배지 → (보기·정답표시) → 도식 → 해설 순으로 **전폭 세로 쌓기.**

    ★ 원본은 도식이 있으면 2단(`.ans-row`, 왼쪽 그림 44% · 오른쪽 해설)이었다.
      그 2단은 예산이 652px 이던 시절의 우회로다 — 도식 481px 을 세로로 쌓으면
      해설이 다음 장으로 갈려서, 옆에 붙여 한 바닥에 모았다(render.py 머리말).
      지금은 예산이 948px 이고 줄 수를 실측으로 재므로 그 제약이 없다. 전폭으로
      쌓으면 ① 도식이 792px → 1800px 로 두 배 넓어지고 ② 넘칠 때 문단 단위로
      깔끔히 다음 장으로 흐른다. 사용자 요구("해설도 2장이라면 하단 상단에 없이
      끝납니다")와도 맞는다.

    ★ **보기를 다시 넣는다**(정답 칸을 초록으로). 사용자 요구 3번이 사이트의
      "정답 보기 누른 상태" 를 목표로 못박았다. 원본이 이걸 뺀 이유는 보기 228px 이
      652px 예산의 35% 를 먹어서였다 — 그 계산의 전제(작은 예산·부풀린 줄 수)가
      둘 다 사라졌다. `repeat_opts=False` 로 끌 수 있게 둔다.
    """
    blocks: List[Block] = []
    opts_h = 0.0
    shown_opts = False
    if repeat_opts:
        src = next((b for b in q.blocks if b.kind == "opts"), None)
        if src is not None and src.choices:
            ob = Block(kind="opts", choices=list(src.choices),
                       correct=q.answer_no)
            opts_h = block_h(ob, st, INNER_W)
            blocks.append(ob)
            shown_opts = True
    if q.figure is not None:
        fb = Block(kind="figure", svg=q.figure.svg, img_path=q.figure.img_path,
                   aspect=q.figure.aspect)
        ratio = FIG_ANS_RATIO_WITH_OPTS if opts_h else FIGURE_MAX_RATIO
        cap = SAFE * ratio
        fb.fixed_h = min(INNER_W / fb.aspect, cap) if fb.aspect else cap
        blocks.append(fb)
    blocks.extend(q.expl)

    head = badge_h(st, badge_label(q, with_text=not shown_opts)) + st.card_gap
    pieces = to_pieces(blocks, st, INNER_W)
    pages = pack(pieces, st, INNER_W, head_h=head, budget_scale=budget_scale,
                 keep_split=(budget_scale != 1.0))
    # ★ 문제 면과 같은 이유로 재분배하지 않는다(`_balance` 머리말).
    return pages


def paginate_round(rnd: Round, *, part_size: int = 10, cover: bool = True,
                   repeat_opts: bool = True,
                   scale: float = DEFAULT_SCALE) -> List[Page]:
    """회차 하나 → 슬라이드 목록. 간지는 `part_size` 문항마다 앞에 붙는다."""
    out: List[Page] = []
    qs = rnd.questions
    parts = max(1, math.ceil(len(qs) / part_size)) if part_size else 1
    for idx, q in enumerate(qs):
        if cover and part_size and idx % part_size == 0:
            pi = idx // part_size + 1
            lo = qs[idx].no
            hi = qs[min(idx + part_size, len(qs)) - 1].no
            rng = f"{lo}번부터 {hi}번까지" if hi != lo else f"{lo}번"
            out.append(Page(
                kind="cover",
                cover_eyebrow=rnd.exam,
                cover_title=f"{rnd.title} ({pi}/{parts})" if parts > 1 else rnd.title,
                cover_lead=f"{rng} · {parts}편 중 {pi}편" if parts > 1 else rng,
                q_no=q.no))
        out.extend(_pages_for(q, repeat_opts=repeat_opts, scale=scale))
    return out


# 장수를 사람이 지정했을 때만 쓰는 사다리들 (xam-local 이 더한 것).
#   SHRINK  줄일 때 배율을 내려가는 순서. 하한 아래로는 가지 않는다 —
#           그 아래는 글자가 영상에서 안 읽힌다.
#   SPLIT   늘릴 때 예산을 깎는 순서. 일찍 넘겨 장을 더 만든다.
SHRINK_LADDER = (1.0, 0.94, 0.88, 0.82, 0.76)
SHRINK_FLOOR = 0.75          # 요청 배율 대비 하한
SPLIT_LADDER = (0.92, 0.84, 0.76, 0.68, 0.60, 0.52, 0.45, 0.38, 0.32)


def _fit(build, scale: float, want: int = 0):
    """고정 배율로 담는다. 넘치면 한 단 조여 본다. 반환: (배율판, 장들)

    ★ 배율을 **장마다 고르지 않는다**(위 `GROW_LADDER` 머리말의 정정). 덱 하나가
      한 배율을 쓰고, 그 배율에서 넘치는 장만 `dense` 로 떨어진다 — 조이는 것은
      잘리는 것을 막기 위한 마지막 안전판이고, 채움률을 위한 것이 아니다.

    ★ `want` (xam-local 이 더한 것) — 사람이 화면에서 이 문항의 장수를 정했을 때
      그 수를 맞춘다. 못 맞추면 **자연 장수로 되돌리고** 호출부가 그것을 보고한다.
      조용히 잘라 내지 않는다 — 잘리면 내용이 사라진다.
    """
    st = style_for(scale)
    pages = build(st, 1.0)
    if want and len(pages) != want:
        got = _force_pages(build, scale, want, len(pages))
        if got is not None:
            return got
    if not _overflows(pages):
        return st, pages
    dense = Style(Scale(TS_DENSE * scale, SS_DENSE * scale))
    cand = build(dense, 1.0)
    if not _overflows(cand):
        return dense, cand
    # 조여도 넘치면 원래 판을 쓴다 — 리포트가 넘침을 보고한다.
    return st, pages


def _force_pages(build, scale: float, want: int, natural: int):
    """장수를 `want` 로 맞춰 본다. 못 맞추면 None.

    줄일 때는 **배율을 내리고**(dense 를 먼저 써 본다), 늘릴 때는 **예산을 깎는다.**
    두 손잡이를 섞지 않는 이유는 하나 — 배율은 눈에 보이고 예산은 안 보인다.
    글자가 작아졌다는 것을 화면이 말할 수 있어야 사람이 되돌릴 수 있다.
    """
    if want < 1:
        return None
    if want < natural:                      # 줄인다 — 배율을 내린다
        for mult in SHRINK_LADDER:
            if mult < SHRINK_FLOOR:
                break
            for st in (style_for(scale * mult),
                       Style(Scale(TS_DENSE * scale * mult,
                                   SS_DENSE * scale * mult))):
                pages = build(st, 1.0)
                if len(pages) == want and not _overflows(pages):
                    return st, pages
                if len(pages) < want:
                    # 너무 줄었다 — 예산을 깎아 다시 want 로 쪼갠다
                    got = _split_to(build, st, want)
                    if got is not None:
                        return got
        return None
    # 늘린다 — 배율은 그대로 두고 예산만 깎는다
    return _split_to(build, style_for(scale), want)


def _split_to(build, st: "Style", want: int):
    """예산을 깎아 `want` 장으로 쪼갠다. 못 하면 None.

    ★ 넘침은 **깎기 전 예산**으로 판정한다. `budget_scale` 은 "여기서 넘겨라" 는
      신호일 뿐 실제 슬라이드 높이가 아니다. 깎은 예산으로 재면 한 조각이 그보다
      크기만 해도 넘침으로 보여, 쪼갤 수 있는 문항이 못 쪼갠 것으로 떨어진다
      (실측: 발문+보기 두 조각짜리 문항이 2장으로 안 갈렸다).
    """
    for bs in SPLIT_LADDER:
        pages = build(st, bs)
        if len(pages) != want:
            continue
        if all(pg.used <= pg.budget / bs for pg in pages):
            return st, pages
    return None


def _overflows(pages: List[Packed]) -> bool:
    return any(pg.used > pg.budget for pg in pages)


def _plan(q: Question, *, repeat_opts: bool = True,
          scale: float = DEFAULT_SCALE, want=None):
    """이 문항의 문제 면·해설 면 계획. 반환: (문제배율, 문제장들, 해설배율, 해설장들)

    ★ **두 면이 같은 배율을 쓴다.** 전에는 면마다 따로 골라 채움률을 올렸는데,
      그것이 곧 "요소 사이즈가 제각각" 이었다(2026-08-21 사용자 지적). 지금은
      덱 전체가 한 배율이고 여기서는 넘칠 때만 조인다.
    """
    want = want or {}
    pst, ppages = _fit(lambda st, bs: _problem_pages(q, st, bs), scale,
                       int(want.get("problem") or 0))
    ast, apages = _fit(
        lambda st, bs: _answer_pages(q, st, repeat_opts=repeat_opts,
                                     budget_scale=bs),
        scale, int(want.get("answer") or 0))
    return pst, ppages, ast, apages


def _shows_opts(apages: List[Packed]) -> bool:
    """해설 첫 장에 보기가 다시 실렸는가. 배지에 본문을 넣을지 가른다."""
    return bool(apages) and any(p.block.kind == "opts" for p in apages[0].pieces)


def _pages_for(q: Question, *, repeat_opts: bool = True,
               scale: float = DEFAULT_SCALE, want=None) -> List[Page]:
    """★ `want` = {"problem": n, "answer": m} — 사람이 화면에서 정한 장수(xam-local)."""
    out: List[Page] = []
    st, pages, ast, apages = _plan(q, repeat_opts=repeat_opts, scale=scale,
                                   want=want)
    n = len(pages)
    for k, pg in enumerate(pages):
        first, last = k == 0, k == n - 1
        gap, top = _absorb(pg, st, standalone=(first and last))
        out.append(Page(
            kind="problem",
            blocks=[p.block for p in pg.pieces],
            head_no=(f"{q.no}번" if first else ""),
            head_difficulty=(q.difficulty if first else ""),
            cont_top=not first, cont_bottom=not last,
            dense=(st.sc.ts < TS * scale),
            gap_px=gap, used_px=pg.used, budget_px=pg.budget, q_no=q.no,
            pad_top_px=top, scale=st.sc.ts / TS))

    an = len(apages)
    for k, pg in enumerate(apages):
        first, last = k == 0, k == an - 1
        gap, top = _absorb(pg, ast, standalone=(first and last))
        p = Page(
            kind="answer",
            blocks=[pc.block for pc in pg.pieces],
            badge_no=(q.answer_no if first else ""),
            badge_text=(q.answer_text
                        if (first and not _shows_opts(apages)) else ""),
            cont_top=not first, cont_bottom=not last,
            dense=(ast.sc.ts < TS * scale),
            gap_px=gap, used_px=pg.used, budget_px=pg.budget, q_no=q.no,
            pad_top_px=top, scale=ast.sc.ts / TS)
        out.append(p)
    return out


# ── 이론 덱 ─────────────────────────────────────────────────────────────────
def head3_h(st: Style, topic: Topic) -> float:
    """토픽 머리(대단원 칩 + 소단원 제목)가 먹는 높이.

    문제 덱의 `st.head_h` 와 같은 자리다 — 첫 장에서만 예산에서 빠진다.
    """
    eye = st.eyebrow_fs * 1.4 + st.s(6)
    title = M.block_height([f"{topic.no} {topic.title}".strip()],
                           st.head3_fs, st.head3_lh,
                           mw(INNER_W, st.head3_fs), weight=700)
    return eye + title + st.s(10)


def _topic_pages(t: Topic, st: Style) -> List[Packed]:
    pieces = to_pieces(t.blocks, st, INNER_W)
    head = head3_h(st, t)
    pages = pack(pieces, st, INNER_W, head_h=head)
    return _balance(pieces, st, INNER_W, head, pages)


def pages_for_topic(t: Topic, subject_no: int = 0,
                    scale: float = DEFAULT_SCALE) -> List[Page]:
    """토픽 하나 → 슬라이드들. 배율은 문제 덱과 같이 **고정**이다."""
    # ★ xam-local v2(2026-10-24): `_fit` 이 build(st, 예산배율) 로 부르게 바뀐 뒤(page_want)
    #   이론 쪽만 인자 하나짜리로 남아 TypeError 로 죽었다 — xam-lo 는 문제 덱만 써서 몰랐다.
    #   이론 토픽은 예산을 조이지 않으므로 둘째 인자는 받고 버린다.
    st, pages = _fit(lambda x, _bs=1.0: _topic_pages(t, x), scale)
    n = len(pages)
    out: List[Page] = []
    for k, pg in enumerate(pages):
        first, last = k == 0, k == n - 1
        gap, top = _absorb(pg, st, standalone=(first and last))
        out.append(Page(
            kind="topic",
            blocks=[pc.block for pc in pg.pieces],
            eyebrow=(f"{t.chapter_no}. {t.chapter}".strip(" .") if first else ""),
            heading=(f"{t.no} {t.title}".strip() if first else ""),
            subject_no=subject_no,
            cont_top=not first, cont_bottom=not last,
            dense=(st.sc.ts < TS * scale),
            gap_px=gap, used_px=pg.used, budget_px=pg.budget,
            pad_top_px=top, scale=st.sc.ts / TS))
    return out


def doc_cover(doc: Doc, *, part: int = 0, parts: int = 0,
              lo: str = "", hi: str = "") -> Page:
    """요약노트 표지. 파일 **앞에만** 한 장 온다(사용자 확정 2026-08-21).

    ★ 문제 덱과 같은 규약이다 — 간지를 본문 사이에 흩지 않고 파일을 쪼갠다.
      "간지는 10문제마다 파일을 쪼갤거기 때문에 파일 앞에만 나오면 됩니다."
    """
    title = doc.title or doc.subject
    if parts > 1:
        title = f"{title} ({part}/{parts})"
    lead = ""
    if lo and hi and lo != hi:
        lead = f"{lo} ~ {hi}"
    elif lo:
        lead = lo
    if parts > 1:
        lead = " · ".join(x for x in (lead, f"{parts}편 중 {part}편") if x)
    return Page(kind="cover", cover_eyebrow=doc.exam, cover_title=title,
                cover_lead=lead, subject_no=doc.subject_no)


def paginate_doc(doc: Doc, *, cover: bool = True,
                 scale: float = DEFAULT_SCALE) -> List[Page]:
    """요약노트 하나 → 슬라이드 목록(표지 1장 + 토픽들). 파일 쪼개기는 `build` 가 한다."""
    out: List[Page] = []
    if cover and doc.topics:
        out.append(doc_cover(doc, lo=_topic_label(doc.topics[0]),
                             hi=_topic_label(doc.topics[-1])))
    for t in doc.topics:
        out.extend(pages_for_topic(t, doc.subject_no, scale))
    return out


def _topic_label(t: Topic) -> str:
    return (f"{t.no} {t.title}").strip()
