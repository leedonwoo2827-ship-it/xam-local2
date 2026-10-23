# -*- coding: utf-8 -*-
"""중간 표현(IR) — 파서와 렌더러가 만나는 **유일한** 자리.

★ 왜 IR 을 따로 두는가. 입력이 하나가 아니다: 지금은 `_deck-export/*.html` 이고,
  나중에 긁힌 PDF 가 들어온다(사용자 2026-08-21). 파서를 늘려도 레이아웃·렌더러는
  그대로여야 하므로, 둘 사이에 이 파일만 놓는다. 파서는 `Round` 를 만들고
  렌더러는 `Round` 만 읽는다 — HTML 을 아는 코드는 `parse_html.py` 안에서 끝난다.

★ **DOM 순서를 보존한다.** 실측(9파일 1,463섹션)에서 문제 면 순서는
  `발문 → 지문 → 보기` 두 가지뿐이었지만, 정보처리기사·SQLD 에는
  `발문 → 보기 → 그림` 이 있다(사용자 지적). 그래서 블록을 종류별 필드로
  나누지 않고 **한 줄의 리스트**로 들고 다닌다. 순서가 곧 집필의 판단이다.

★ 원본 CSS `figure.diagram{order:-1}` 은 DOM 순서와 무관하게 그림을 카드 맨 위로
  끌어올린다. 그 동작이 필요한 그림만 `Block.top` 을 켠다 — 순서를 뒤섞어 표현하지
  않는다(뒤섞으면 "왜 여기 있나"가 코드에서 사라진다).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── 블록 종류 ───────────────────────────────────────────────────────────────
#   q             발문
#   passage       지문 (문단/줄바꿈 목록)
#   passage_label 지문 라벨 — 짧은 머리말([TEAM]). **다음 블록과 붙는다**
#   table         표
#   pre           코드블록 (SQL·소스)
#   opts          보기 (원숫자 + 본문)
#   figure        도식 (인라인 SVG 또는 비트맵)
#   expl          해설 문단
#   heading       소제목 (이론 덱의 h3) — 문제 덱의 발문과 같은 자리
#   bullets       항목 목록 (이론 덱의 ul>li)
KINDS = ("q", "passage", "passage_label", "table", "pre", "opts", "figure", "expl",
         "heading", "bullets")


@dataclass
class Block:
    kind: str
    # 텍스트계(q · passage · passage_label · pre · expl). 문단 목록이다 —
    # 한 문단이 한 <p> 이고, 줄바꿈(<br>)도 문단으로 펴서 넣는다.
    paras: List[str] = field(default_factory=list)
    # 표: 머리 행 + 본문 행들
    headers: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)
    # 보기: [(원숫자, 본문), ...]. 실측 720문항 전부 4개·①②③④ 였지만 3·5개도 받는다.
    choices: List[tuple] = field(default_factory=list)
    # 도식: 인라인 SVG 원문 또는 이미지 경로. 하나만 채운다.
    svg: str = ""
    img_path: str = ""
    # 원본 viewBox 비율(w/h). 래스터화 크기와 자리 예산에 쓴다.
    aspect: float = 0.0
    # 도식 안 글자 크기(viewBox 단위)와 viewBox 폭.
    # ★ 도식을 얼마나 키울지 정하는 값이다 — 안 글자를 슬라이드 글자에 맞춘다.
    #   사용자 확정(2026-08-21): "svg의 글자가 적당하다는거야" — 도식 안 글자가
    #   기준이고 본문이 그 크기로 내려온다. 그래서 도식은 안 글자가 목표 pt 가
    #   되도록 확대한다. 폭에 맞춰 늘리면 도식마다 글자 크기가 달라진다.
    svg_font: float = 0.0
    svg_vw: float = 0.0
    # ★ CSS `order:-1` 재현 — 이 그림만 카드 맨 위로 올린다.
    top: bool = False
    # ★ 다음 블록과 **붙는다**(라벨→표). 분할기가 둘 사이를 자르지 않는다.
    glue_next: bool = False
    # 보기 블록에서 정답 원숫자. 해설 면의 보기만 채운다(정답 칸을 초록으로 칠한다).
    correct: str = ""
    # 높이를 밖에서 못 박았을 때. 도식은 남은 자리를 보고 정하므로 여기에 담는다.
    fixed_h: float = 0.0


@dataclass
class Question:
    no: int                       # 문항 번호 (1..80)
    difficulty: str = ""          # 하 / 중 / 상
    # 문제 면 블록 — DOM 순서 그대로
    blocks: List[Block] = field(default_factory=list)
    # 해설 면
    answer_no: str = ""           # "③"
    answer_text: str = ""         # 정답 보기의 본문
    expl: List[Block] = field(default_factory=list)
    figure: Optional[Block] = None   # 해설 도식 (있으면 2단 배치)

    def choices(self) -> List[tuple]:
        for b in self.blocks:
            if b.kind == "opts":
                return b.choices
        return []


@dataclass
class Round:
    """한 회차. `01회.html` 하나가 이것 하나가 된다."""
    exam: str = ""                # 자격증명 — 간지 eyebrow. HTML 에 없어서 밖에서 받는다
    round_no: str = ""            # "01회"
    title: str = ""               # "모의고사 01회 — 문제 풀이"
    questions: List[Question] = field(default_factory=list)
    source: str = ""              # 원본 파일 경로 (추적용)


# ── 페이지 (레이아웃 결과) ──────────────────────────────────────────────────
@dataclass
class Page:
    """슬라이드 한 장. `layout.paginate_round()` 가 만들고 렌더러가 그린다."""
    kind: str                     # "cover" | "problem" | "answer" | "topic"
    blocks: List[Block] = field(default_factory=list)
    # 머리(문번 + 난도) — 문제 면 첫 장에만. 없으면 빈 문자열.
    head_no: str = ""
    head_difficulty: str = ""
    # 이론 덱의 머리 — 대단원 칩(eyebrow)과 소단원 제목. 토픽 첫 장에만.
    eyebrow: str = ""
    heading: str = ""
    # 과목 번호. 색을 고르는 열쇠다 (`pptx_render.palette`).
    subject_no: int = 0
    # 정답 배지 — 해설 면 첫 장에만.
    badge_no: str = ""
    badge_text: str = ""
    # 이어짐 표시. 원본 규약(2026-08-12 사용자 확정)을 그대로 옮긴다:
    #   첫 장 머리 O · 푸터 X / 중간 장 머리 X · 푸터 X / 끝 장 푸터 O
    #   → 문제 면은 푸터를 아예 안 쓰고, 해설 면은 머리를 안 쓴다.
    cont_top: bool = False        # 위에서 이어진 장 (상단 패딩 접음)
    cont_bottom: bool = False     # 아래로 이어지는 장 (하단 패딩 접음)
    dense: bool = False           # 조여 담은 장 (ts 2.30 / ss 2.05)
    # 배율. 1.0 = 원본 CSS(ts 2.67). 문항 단위로 하나만 쓴다 — `layout._choose_style`.
    scale: float = 1.0
    gap_px: float = 0.0           # 블록 간 간격 (잔여 공간 흡수 후 확정값)
    # 간지 전용
    cover_eyebrow: str = ""
    cover_title: str = ""
    cover_lead: str = ""
    # 잔여 공간 흡수 결과 — 카드 위쪽에 더 둘 여백. 단독 장에서만 0 이 아니다.
    pad_top_px: float = 0.0
    # 해설 2단(왼쪽 도식 · 오른쪽 해설). 도식이 있는 해설 첫 장만 True.
    two_col: bool = False
    figure: Optional[Block] = None
    # 진단용 — 이 장이 예산을 얼마나 썼는가
    used_px: float = 0.0
    budget_px: float = 0.0
    q_no: int = 0                 # 어느 문항에서 나왔는지 (리포트·오류 메시지용)


# ── 이론 요약 덱 ────────────────────────────────────────────────────────────
# ★ 문제 덱(`Round`/`Question`)과 **다른 IR 을 쓴다.** 억지로 Question 에 끼워
#   넣어 봤자 `answer_no`·`choices` 가 늘 비고, 다음 사람이 "문항인데 정답이 없다" 로
#   읽는다. 두 문서는 서로 다른 것이므로 자료구조도 다르다.
#   대신 **`Block` 과 `Page` 는 공유한다** — 재는 것(`layout`)과 그리는 것
#   (`pptx_render`)이 한 벌이어야 한다.


@dataclass
class Topic:
    """`h3` 하나. 이론 덱의 슬라이드 단위다.

    ★ 왜 h3 인가. `xam-lo/services/authoring/theory.py` 가 규약을 적어 뒀다 —
      *"목차는 우리가 낸 h2/h3 가 이미 목차"*. 그리고 실측으로 h3 당 항목 4개·
      300자(중앙값)라서 한 장에 딱 맞는다(파일1 59개 · 파일2 90개).
    """
    no: str = ""                  # "1.8"
    title: str = ""               # "이행 함수 종속과 제3정규형"
    blocks: List[Block] = field(default_factory=list)
    chapter_no: str = ""          # 소속 h2 번호 "1"
    chapter: str = ""             # 소속 h2 제목 "정규화와 함수 종속"


@dataclass
class Doc:
    """요약노트 한 과목. `03/N<key>.html` 하나가 이것 하나가 된다."""
    subject_no: int = 0           # h1 의 "1과목" → 1. 색을 고르는 열쇠다
    subject: str = ""             # "데이터 모델링의 이해"
    title: str = ""               # h1 전문 "1과목 · 데이터 모델링의 이해"
    exam: str = ""                # 자격증명 (간지 eyebrow) — 밖에서 받는다
    topics: List[Topic] = field(default_factory=list)
    source: str = ""
