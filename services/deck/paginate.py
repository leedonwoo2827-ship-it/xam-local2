# -*- coding: utf-8 -*-
"""카드 내용을 슬라이드 여러 장으로 **쪼갠다.**

★ 왜 파이썬으로 재는가 — `render_deck()` 은 미리보기와 베이크가 **같은 함수**를 쓴다는
  규약을 지고 있다(`preview.py` 머리말). 미리보기는 요청마다 그리므로 여기서 Chromium 을
  띄우면 화면이 몇 초씩 멈춘다. 그래서 **추정**으로 쪼개고, 실제 넘침은 캡처 단계의
  `deck_capture.capture_deck()` 가 `overflow` 로 돌려준다 — 두 겹이다.

★ 추정이 틀리는 방향을 정해 둔다: **넉넉히 잡아 일찍 쪼갠다.** 덜 쪼개면 잘려서
  내용이 사라지고(그건 영상에 그대로 나간다), 더 쪼개면 장이 한 장 늘 뿐이다.
  그래서 글자 폭을 한글 기준(1.0em)으로 잡는다 — 라틴이 섞이면 실제로는 더 들어간다.

★ 이어지는 장의 모양은 사용자가 정한 규약이다(2026-08-12):

      첫 장   상단 테두리 O · 머리 O · 하단 테두리 X · 푸터 X
      중간 장 상단 테두리 X · 머리 X · 하단 테두리 X · 푸터 X
      끝 장   상단 테두리 X · 머리 X · 하단 테두리 O · 푸터 O

  즉 한 문항이 **한 장의 카드가 이어지는 것처럼** 보여야 한다. 그래서 머리·푸터를
  넣고 빼는 판단이 분할과 같은 자리에 있어야 한다 — 따로 두면 어긋난다.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import List

from . import theme

# ── 실측 기하 ───────────────────────────────────────────────────────────────
# 카드 안쪽 폭. 슬라이드 1920 − 좌우 여백 96×2 − 카드 패딩 56×2 − 테두리 3×2.
INNER_W = theme.SLIDE_W - theme.PAD * 2 - theme.CARD_PAD * 2 - theme.CARD_BORDER * 2

TS = theme.TEXT_SCALE          # 2.67
SS = theme.SPACE_SCALE         # 2.40


def _px(base: float) -> float:
    """CSS `calc(Npx * var(--ts))` 와 같은 값."""
    return base * TS


def _sp(base: float) -> float:
    """CSS `calc(Npx * var(--ss))` 와 같은 값."""
    return base * SS


# 각 요소의 글자 크기·행간 — `slidecss.py` 의 선언과 **같은 수를 쓴다.**
# 한 곳에서 바뀌면 다른 곳도 바뀌어야 하므로 그 사실을 여기 적어 둔다.
Q_FS, Q_LH = _px(15), 1.5            # 발문
PASSAGE_FS, PASSAGE_LH = _px(13.5), 1.6
OPT_FS, OPT_LH = _px(14), 1.4
EXPL_FS, EXPL_LH = _px(13.5), 1.7
TABLE_FS, TABLE_LH = _px(12.5), 1.45
BADGE_FS = _px(13)

CARD_GAP = _sp(10)                   # `.qcard` 의 flex gap
PASSAGE_PAD = _sp(12) * 2            # 위아래
OPT_PAD = _sp(6) * 2
OPT_GAP = _sp(8)
OPT_COL_GAP = _sp(18)
BADGE_PAD = _sp(5) * 2
EXPL_P_GAP = _sp(9)
TABLE_CELL_PAD = _sp(6) * 2
FIG_H = float(theme.avail(True) * theme.FIGURE_MAX_RATIO)   # `--fig-max`

# ── 예산 ────────────────────────────────────────────────────────────────────
# ★ Chromium 실측(2026-08-12, 3번들 94장)으로 잡은 값이다. 계산으로 유도하지 않는다 —
#   처음에 `safe_line − CARD_PAD×2 − CARD_BORDER×2 = 522` 로 계산했다가 **틀렸다.**
#   `theme.avail()` 이 이미 카드 **안쪽** 상자이므로 패딩을 또 뺀 것이었다. 그 결과
#   예산이 120px 작아져 과분할이 났다(중앙 사용률 34%, 60px 짜리 장까지 생겼다).
#
#   카드 안쪽 실측:
#     머리·푸터 다 있는 장      652px   ← 첫 장이면서 끝 장(안 쪼개진 문항)
#     한쪽만 없는 장            863px   ← 첫 장(푸터 없음) 또는 끝 장(머리 없음)
#     양쪽 다 없는 중간 장     1080px
#
# ★ 첫 장은 **652 기준**으로 잡는다. 쪼개질지 아직 모르는데 863 으로 잡으면, 안 쪼개진
#   문항이 652 를 넘겨 잘린다. 두 번째 장부터는 머리가 확실히 없으므로 863 을 쓴다.
#   중간 장의 1080 은 쓰지 않는다 — 어느 장이 중간인지는 다 쌓아 본 뒤에야 알 수 있고,
#   그걸 맞추려고 되풀이하면 장수가 오히려 흔들린다.
# ★ 첫 장은 머리(`1번 [하]`) 한 줄을, 끝 장은 푸터(`2 / 22`) 한 줄을 카드 안에서
#   쓴다. 그 한 줄만 빼고 나머지를 다 쓴다 — 띠로 118px 을 미리 잡아 두지 않는다.
HEAD_LINE = _px(13) * 1.4 + _sp(8)          # 머리 한 줄 + 아래 간격
FOOT_LINE = _px(11.5) * 1.4 + _sp(8)        # 푸터 한 줄 + 위 간격

#   카드 안쪽 실측(Chromium, 머리·푸터를 카드 안으로 넣은 뒤):
#     머리·푸터가 있는 장   776px
#     둘 다 없는 이어지는 장 928px   ← `cont-top`/`cont-bottom` 이 패딩을 접어 더 넓다
BUDGET = float(theme.safe_line(True)) - HEAD_LINE - FOOT_LINE   # 첫 장 = 끝 장
BUDGET_CONT = 928.0 - theme.SAFETY                              # 머리·푸터 없는 장

# ★ 넘침 허용치. 예산을 이만큼 넘어도 쪼개지 않는다.
#
#   왜 필요한가 — 예산을 딱 지키면 **마지막 장이 거의 빈다.** 실측(3번들 84장):
#   추정은 정확한데(추정/실제 중앙 1.00) 내용이 예산의 45% 만 찼다. 조각 하나가
#   조금 넘쳐서 다음 장으로 가고, 그 장에 한 줄만 남기 때문이다.
#   그리고 그 빈 장이 영상에서 가장 나쁘다 — 1920×1080 프레임에 한 줄만 떠서
#   **핸드폰에서 글자가 거의 안 보인다**(2026-08-12 지시).
#
#   ★ 사용자가 아래를 약간 잘리는 것은 괜찮다고 했다("밑에가 상관이 없어요 약간은").
#     그래서 조금 넘치는 것을 쪼개는 것보다 그대로 두는 편이 낫다 — 잘리는 것은
#     여백 몇 px 이고, 쪼개면 반쯤 빈 장이 하나 생긴다.
#
#   ★ 0.18 → 0.04 로 내렸다. 예산 자체가 커졌기 때문이다(머리·푸터 띠 118px 을 더는
#     빼지 않는다 — `theme.avail` 머리말). 큰 예산에 큰 허용치를 같이 두면 **이중으로
#     넘쳐** 실제로 글자가 잘린다. 실측에서 그렇게 됐다: 허용치 0.18 로 5장이
#     카드 안에서 최대 95px 잘렸다. 허용치는 마지막 몇 px 을 위한 것이다.
TOLERANCE = 0.04

# ★ 고아 방지. 남은 조각이 이 높이보다 작으면 다음 장으로 보내지 않고 이 장에 붙인다.
#   "3번은 한 줄 붙은 채로 가자" 가 이 규칙이다(2026-08-12 지시).
ORPHAN = 150.0


def _lines(text: str, font_px: float, width: float = INNER_W) -> int:
    """줄 수. 한글 한 글자를 `font_px` 폭으로 본다(넉넉한 쪽).

    ★ 태그를 벗기고 센다. `<b>` 가 글자 수에 들어가면 줄 수가 부풀어 과분할이 된다.
    """
    plain = re.sub(r"<[^>]+>", "", text or "")
    per = max(1, int(width // font_px))
    n = 0
    # 문단별로 센다 — 문단이 바뀌면 줄이 새로 시작한다.
    for para in re.split(r"\n\s*\n", plain):
        chars = len(para.strip())
        n += max(1, math.ceil(chars / per)) if chars else 0
    return max(1, n)


# ── 카드 조각 ───────────────────────────────────────────────────────────────
@dataclass
class Piece:
    """카드 안에 들어가는 한 덩어리. `html` 은 그대로 나가고 `h` 로 자리를 잡는다."""
    html: str
    h: float
    # ★ 이 조각만 따로 한 장을 차지해도 되는가. 그림·표는 쪼갤 수 없다.
    atomic: bool = True
    # 발문처럼 **첫 장에 반드시 있어야** 하는 것. 없으면 무슨 문제인지 모른다.
    sticky: bool = False
    # ★★ **다음 조각과 같은 장**에 있어야 하는 것. 표 위의 이름표(「[ORDERS]」)가
    #   그렇다. 떨어지면 앞 장 끝에 이름표만 남고 표가 다음 장에서 시작한다 —
    #   무엇의 표인지 알 수 없다(2026-08-20 실측 SQLD 11·12번).
    #   `sticky` 로는 안 된다. 그건 「첫 장에 남는다」 는 뜻이라 자리가 다르다.
    with_next: bool = False
    # ★★ 남는 자리에 맞춰 **둘로 쪼개는** 함수. `f(자리높이) -> (앞, 뒤) | None`.
    #   표는 행으로, 코드는 줄로 쪼갠다(2026-08-20 지시: 「쭈욱 흐르게 해도 됩니다.
    #   박스가 중간에 끊겨도 되고요」 · 「지문이나 표를 안 읽는다」). 낭독이 발문만
    #   읽고 해설로 넘어가므로, 문제 면은 **눈으로 훑는 자리**다 — 장 경계에서
    #   끊겨도 읽는 데 지장이 없다. 못 쪼개면 None 을 주면 통째로 넘어간다.
    #   쪼개지 못하던 때는 한 장에 표 하나만 남고 아래가 텅 비었다.
    splitter: object = None


@dataclass
class Page:
    pieces: List[Piece] = field(default_factory=list)

    @property
    def h(self) -> float:
        if not self.pieces:
            return 0.0
        return sum(p.h for p in self.pieces) + CARD_GAP * (len(self.pieces) - 1)

    @property
    def html(self) -> str:
        return "".join(p.html for p in self.pieces)


# ★ 쪼개려면 남는 자리가 최소 이만큼은 있어야 한다. 그보다 좁으면 표 머리나
#   코드 한 줄만 남아 보기 나쁘다.
SPLIT_MIN = 140.0


def pack(pieces: List[Piece], budget: float = BUDGET,
         budget_cont: float = BUDGET_CONT) -> List[Page]:
    """조각을 예산 안에 채워 페이지 목록으로. **넘치면 다음 장으로 넘긴다.**

    ★ `sticky` 조각(발문)은 첫 장에 남는다. 발문이 2장으로 밀리면 첫 장이 무슨
      문제인지 알 수 없는 장이 된다.
    ★ 조각 하나가 예산보다 크면 **그것만으로 한 장**을 만든다. 거기서 더 쪼갤 수
      없으면 캡처 단계가 `overflow` 로 잡아 준다 — 조용히 잘리지는 않는다.
    """
    pages: List[Page] = [Page()]
    for k, p in enumerate(pieces):
        cur = pages[-1]
        # 첫 장은 머리·푸터가 다 있어 예산이 작다. 두 번째 장부터 넓어진다.
        lim = (budget if len(pages) == 1 else budget_cont) * (1.0 + TOLERANCE)
        need = p.h + (CARD_GAP if cur.pieces else 0)
        # ★ 남은 것이 얼마 없으면 쪼개지 않는다. 쪼개면 그 장에 한 줄만 남고,
        #   1920×1080 프레임에 한 줄만 뜨면 핸드폰에서 안 보인다.
        rest = sum(x.h for x in pieces[k:]) + CARD_GAP * max(0, len(pieces) - k - 1)
        # ★ `with_next` 면 **다음 조각까지** 들어갈 자리를 본다. 이름표만 넣고
        #   표를 다음 장으로 보내면 이름표가 홀로 남는다.
        if p.with_next and k + 1 < len(pieces):
            need += CARD_GAP + pieces[k + 1].h
        if cur.pieces and cur.h + need > lim and rest > ORPHAN:
            # ★ 넘어가기 전에 **쪼갤 수 있으면 쪼갠다.** 남는 자리가 한 줌이면
            #   쪼개지 않는다 — 표 머리만 남은 장이 생긴다.
            room = lim - cur.h - CARD_GAP
            cut = None
            if p.splitter and room > SPLIT_MIN and not p.with_next:
                cut = p.splitter(room)
            if cut:
                head, tail = cut
                cur.pieces.append(head)
                pages.append(Page())
                cur = pages[-1]
                p = tail
            else:
                pages.append(Page())
                cur = pages[-1]
        cur.pieces.append(p)
    return [pg for pg in pages if pg.pieces]


# ── 높이 계산기 ─────────────────────────────────────────────────────────────
def h_text(html: str, font_px: float, line_h: float, *,
           pad: float = 0.0, para_gap: float = 0.0) -> float:
    n = _lines(html, font_px)
    paras = max(1, len(re.split(r"\n\s*\n", re.sub(r"<[^>]+>", "", html or ""))))
    return n * font_px * line_h + pad + para_gap * (paras - 1)


def h_question(html: str) -> float:
    return h_text(html, Q_FS, Q_LH)


def h_passage(html: str) -> float:
    return h_text(html, PASSAGE_FS, PASSAGE_LH, pad=PASSAGE_PAD)


def h_expl(html: str) -> float:
    return h_text(html, EXPL_FS, EXPL_LH, para_gap=EXPL_P_GAP)


def h_badge() -> float:
    return BADGE_FS * 1.3 + BADGE_PAD


def h_figure() -> float:
    return FIG_H + _sp(6)


def h_choices(choices: List[str], two_col: bool) -> float:
    """보기 묶음 전체 높이. 2×2 면 행이 2개다.

    ★ 2열일 때 **행 높이는 그 행에서 긴 쪽**이 정한다. 짧은 쪽으로 계산하면
      실제보다 낮게 나와 덜 쪼갠다.
    """
    if not choices:
        return 0.0
    w = (INNER_W - OPT_COL_GAP) / 2 if two_col else INNER_W
    hs = [max(1, _lines(c, OPT_FS, w)) * OPT_FS * OPT_LH + OPT_PAD for c in choices]
    if not two_col:
        return sum(hs) + OPT_GAP * (len(hs) - 1)
    rows = [hs[i:i + 2] for i in range(0, len(hs), 2)]
    return sum(max(r) for r in rows) + OPT_GAP * (len(rows) - 1)


def h_table(rows: int) -> float:
    return rows * (TABLE_FS * TABLE_LH + TABLE_CELL_PAD)
