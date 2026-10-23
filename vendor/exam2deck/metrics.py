# -*- coding: utf-8 -*-
"""글자 폭 실측 — 줄 수를 세는 유일한 자리.

★ 왜 실측이 필요한가. 원본 분할기(`xam-lo/services/deck/paginate.py`)는 한글 한 글자를
  `font_px` 통째로 본다. 주석에 의도가 적혀 있다 — *"넉넉히 잡아 일찍 쪼갠다"*. 캡처
  파이프라인에서는 맞는 선택이다(덜 쪼개면 잘려서 내용이 **사라진다**). 그런데 그 대가로
  라틴·숫자·공백이 섞인 발문에서 줄 수가 최대 2배로 부풀고, 장이 하나 더 늘고, 늘어난
  장의 아래가 빈다. 사용자가 지적한 "위치간격" 이 이것이다.

  PPTX 는 캡처가 아니다. 넘치면 잘리는 게 아니라 도형이 아래로 삐져나가고, 우리가
  좌표를 직접 잡으므로 **재서 정확히 놓을 수 있다.** 그래서 여기서 실제 폰트의
  advance width 를 읽는다.

★ 폴백은 원본과 같은 1.0em 휴리스틱이다. Pretendard 가 없는 PC 에서도 결과가 나와야
  하고, 그때 방향은 **일찍 쪼개는 쪽**이어야 한다(원본과 같은 이유).

★ 측정 단위는 **px** 다. 레이아웃 전체가 원본 CSS 픽셀로 굴러가고
  (`layout.py`: 1px = 0.5pt), 여기서만 pt 로 바꾸면 두 단위가 섞인다.
"""
from __future__ import annotations

import math
import os
import re
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

# ── 폰트 위치 ───────────────────────────────────────────────────────────────
# Pretendard 는 사용자 폰트 폴더에 설치되어 있다(Regular/SemiBold/Bold).
# 시스템 폴더도 본다 — 다른 PC 에서는 전역 설치일 수 있다.
_FONT_DIRS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
]
# 굵기 → 파일 후보. 700 이상은 Bold, 600 은 SemiBold.
_FACES: Dict[str, Tuple[str, ...]] = {
    "regular": ("Pretendard-Regular.ttf", "malgun.ttf"),
    "semibold": ("Pretendard-SemiBold.ttf", "malgunbd.ttf", "malgun.ttf"),
    "bold": ("Pretendard-Bold.ttf", "malgunbd.ttf", "malgun.ttf"),
    "mono": ("consola.ttf",),
}


def _face_for(weight: int, mono: bool) -> str:
    if mono:
        return "mono"
    if weight >= 700:
        return "bold"
    if weight >= 600:
        return "semibold"
    return "regular"


def _find(names: Tuple[str, ...]) -> Optional[str]:
    for n in names:
        for d in _FONT_DIRS:
            if not d:
                continue
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


class _Metrics:
    """한 폰트의 글자 → advance(em 비율) 표."""

    def __init__(self, path: str):
        from fontTools.ttLib import TTFont
        f = TTFont(path, fontNumber=0, lazy=True)
        self.upem = f["head"].unitsPerEm
        self._hmtx = f["hmtx"]
        self._cmap = f.getBestCmap()
        self._cache: Dict[str, float] = {}
        self._default = f["hhea"].advanceWidthMax / self.upem
        f.close()

    def adv(self, ch: str) -> float:
        v = self._cache.get(ch)
        if v is None:
            gname = self._cmap.get(ord(ch))
            if gname is None:
                # 표에 없는 글자(예: 폴백 폰트의 특수기호)는 전각으로 본다 —
                # 모르는 글자를 좁게 보면 넘친다.
                v = 1.0
            else:
                v = self._hmtx[gname][0] / self.upem
            self._cache[ch] = v
        return v


@lru_cache(maxsize=8)
def _metrics(face: str) -> Optional[_Metrics]:
    path = _find(_FACES[face])
    if not path:
        return None
    try:
        return _Metrics(path)
    except Exception:
        return None


def font_source() -> Dict[str, str]:
    """진단용 — 어느 파일로 재고 있는지. 리포트에 남긴다."""
    return {k: (_find(v) or "폴백(1.0em 휴리스틱)") for k, v in _FACES.items()}


# ── 폭 ─────────────────────────────────────────────────────────────────────
_WS = re.compile(r"\s")
# 강제 줄바꿈 — `<br>` 이 남긴 개행·수직탭. `_WS` 와 따로 본다.
_HARD_BREAK = re.compile(r"[\n\r\v\f\u2028\u2029]")


def text_width(text: str, size_px: float, *, weight: int = 400,
               mono: bool = False) -> float:
    """한 줄로 놓았을 때의 폭(px)."""
    m = _metrics(_face_for(weight, mono))
    if m is None:
        return len(text or "") * size_px          # 폴백: 원본과 같은 1.0em
    return sum(m.adv(c) for c in (text or "")) * size_px


# ★ 줄바꿈을 어디서 하는가. **어절 단위다.**
#
#   처음에는 브라우저를 흉내냈다 — 한글은 글자마다, 라틴은 낱말 단위(`word-break:
#   normal` 기본). 그런데 이 자는 브라우저가 아니라 **PowerPoint 를 위한 것**이다.
#   PowerPoint 는 `lang="ko-KR"` + `eaLnBrk="1"` 에서 한글을 어절 가운데서 끊지
#   않는다. 두 규칙이 갈리면 우리만 촘촘히 세고, 실제로는 줄이 늘어 카드가 넘친다.
#
#   실측(2026-09-10, ADSP 01회 1번 보기 4개):
#       글자 단위로 세면  3·4·3·3 줄  ← ③번이 2줄 모자란다
#       어절 단위로 세면  3·4·5·3 줄  = PowerPoint 실제와 **4개 다 일치**
#   ③번 `'오늘 서울의 낮 최고기온은 31℃이다'라는 자료는 …` 이 걸렸다. `최고기온은`
#   과 `31℃이다'라는` 이 긴 어절이라 글자 단위로는 촘촘히 들어가지만 PowerPoint 는
#   통째로 넘긴다. 칸은 4줄(140px)뿐이라 5번째 줄이 카드 밖으로 나갔다.
#
#   ★ 이 자가 4줄을 넘게 세면 `layout.OPT4_MAX_LINES` 가 1×4 를 2×2 로 바꾼다.
#     예측이 정확히 4로 나와 그 탈출구가 발동하지 않았던 것이다.
_HANGUL = re.compile(r"[\uac00-\ud7a3\u3130-\u318f\u4e00-\u9fff\u3000-\u303f"
                     r"\uff00-\uffef\u2460-\u24ff\u25a0-\u25ff\u2190-\u21ff]")


# ★ 매달리는 구두점. PowerPoint 가 `hangingPunct="1"` + `lang="ko-KR"` 에서 오른쪽
#   여백으로 넘겨 주는 글자들이다(`pptx_render._ea_linebreak` 참고). 그래서 폭 계산에
#   넣으면 우리만 한 줄을 더 세어 빈 줄이 생긴다 — 실측으로 맞춰 둔 목록이다.
#   따옴표는 **넣지 않는다** — 여는 따옴표와 닫는 따옴표를 구분할 수 없고, 여는
#   따옴표를 매달면 줄 첫머리에 와야 할 글자를 빼먹는다. 빼면 우리 쪽이 보수적이
#   된다(PowerPoint 가 매달아 주면 한 줄 덜 쓸 뿐이고, 넘치지는 않는다).
_HANG = set(".,·;:!?)]}>%…、。」』")


def _tokens(text: str) -> List[str]:
    """줄바꿈 가능 단위 — **어절**. 공백에서만 끊는다(머리말 참고).

    ★ 매달리는 구두점은 어절 끝에서 **떼어 낸다.** 붙여 두면 어절 폭에 섞여 들어가
      한 줄을 더 세는데, PowerPoint 는 그것을 오른쪽 여백으로 매단다.
      `있다.` → [`있다`, `.`] 로 갈라야 `.` 이 줄을 넘기지 않는 계산이 산다.
    """
    out: List[str] = []
    for tok in re.findall(r"\s|\S+", text or ""):
        if _WS.match(tok):
            out.append(tok)
            continue
        tail = ""
        while tok and tok[-1] in _HANG:
            tail = tok[-1] + tail
            tok = tok[:-1]
        if tok:
            out.append(tok)
        out.extend(tail)
    return out


# ★ `ㄱ. ㄴ. ㄷ. ㄹ.` 항목의 **내어쓰기**(hanging indent).
#
#   이 표지가 붙은 문단은 둘째 줄부터 표지 폭만큼 들여 써야 글이 표지 아래가 아니라
#   본문 아래로 붙는다. PowerPoint 쪽은 `pptx_render._textbox` 가 `marL`/`indent` 로
#   심고, 재는 쪽은 여기다 — **두 값이 같아야** 잰 높이와 그린 높이가 맞는다.
#
#   내어쓰기가 걸리면 모든 줄의 글 폭이 `width - 표지폭` 으로 같아진다(첫 줄은 표지가
#   들여쓰기 자리를 채우고 글은 나머지에서 시작한다). 그래서 표지를 뗀 나머지를
#   좁아진 폭으로 재면 그것이 정확한 줄 수다.
_JAMO_MARK = re.compile(r"^([ㄱ-ㅎ]\s*[.·)])(\s+)")


def jamo_indent(text: str, size_px: float, *, weight: int = 400) -> float:
    """`ㄱ. ` 표지의 폭(px). 표지가 없으면 0."""
    m = _JAMO_MARK.match(text or "")
    if not m:
        return 0.0
    return text_width(m.group(1) + m.group(2), size_px, weight=weight)


def line_count(text: str, size_px: float, width_px: float, *,
               weight: int = 400, mono: bool = False) -> int:
    """`width_px` 폭에 넣었을 때의 줄 수. 빈 문자열도 1줄로 센다."""
    if width_px <= 0:
        return 1
    m = _metrics(_face_for(weight, mono))
    if m is None:
        per = max(1, int(width_px // size_px))
        return max(1, math.ceil(len(text or "") / per))
    lines = 1
    used = 0.0
    for tok in _tokens(text):
        # ★ **강제 줄바꿈은 무조건 센다.** 개행문자도 `\s` 에 걸리므로 전에는
        #   보통 공백과 똑같이 흘려보냈다 — 폭이 남으면 줄을 안 넘긴 것으로 셌다.
        #
        #   실측(2026-09-10, ADSP 02회 49번 해설): 한 문단 안에 개행이 들어
        #   있는 `지지도 = … / 향상도 = …` 를 1줄로 세어 상자를 36.3px(=1줄)
        #   로 잡았다. PowerPoint 는 2줄로 그렸고, 다음 문단이 그 위에 겹쳐
        #   **글자가 포개져 나갔다.**
        if _HARD_BREAK.search(tok):
            lines += sum(tok.count(c) for c in ('\n', '\r', '\x0b')) or 1
            used = 0.0
            continue
        w = sum(m.adv(c) for c in tok) * size_px
        if _WS.match(tok):
            # 줄 끝의 공백은 흘려보낸다(브라우저와 같다).
            if used + w > width_px:
                lines += 1
                used = 0.0
            else:
                used += w
            continue
        if used > 0 and used + w > width_px:
            if tok in _HANG:
                # 매달린다 — 줄을 넘기지 않고 오른쪽 여백으로 나간다.
                used += w
                continue
            lines += 1
            used = 0.0
        if w > width_px:
            # 한 낱말이 한 줄보다 길다 — 브라우저는 그대로 넘치게 두지만(overflow-wrap
            # 기본값), 우리는 자리를 잡아야 하므로 넘친 만큼 줄로 센다.
            n = math.ceil(w / width_px)
            lines += n - 1
            used = w - (n - 1) * width_px
            continue
        used += w
    return max(1, lines)


def block_height(paras: List[str], size_px: float, line_h: float, width_px: float,
                 *, weight: int = 400, mono: bool = False,
                 para_gap: float = 0.0) -> float:
    """문단 목록의 총 높이(px)."""
    if not paras:
        return 0.0
    # ★ 문단마다 `ㄱ.` 표지를 따로 본다 — 한 지문 안에 표지가 있는 줄과 없는 줄이
    #   섞인다(`다음은 …` 머리글 + `ㄱ. …` 항목 4개).
    n = 0
    for p in paras:
        ind = jamo_indent(p, size_px, weight=weight)
        n += line_count(p, size_px, max(size_px, width_px - ind),
                        weight=weight, mono=mono)
    return n * size_px * line_h + para_gap * (len(paras) - 1)
