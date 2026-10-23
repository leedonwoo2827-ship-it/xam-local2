# -*- coding: utf-8 -*-
"""`_deck-export/*.html` → `ir.Round`.

★ **원본 분할을 되붙인다.** 입력 HTML 은 이미 슬라이드로 쪼개져 있다:

      <section class="slide content ch4">             문제 (단독)
      <section class="slide content ch4 cont-bottom"> 문제 1/2
      <section class="slide content ch4 cont-top">    문제 2/2
      <section class="slide content">                 해설 (정답배지로 시작)

  그 분할을 그대로 PPTX 로 옮기면 원본이 비워 둔 자리까지 같이 옮겨진다
  (사용자 지적: "디자인보다는 위치간격이 문제"). 그래서 여기서 **문항 단위로
  복원**하고 `layout.py` 가 우리 예산으로 다시 쪼갠다.

  경계 규칙 — 실측(9파일 1,463섹션)으로 확인한 것:
    · `div.s-head` 가 있는 섹션이 **새 문항의 시작**이다 (720개 = 문항 수)
    · `div.answer-badge` 가 있는 섹션은 그 문항의 **해설**이다 (720개, 전부 1장)
    · `cont-top` 섹션은 머리가 없다 → 앞 문항의 문제 면에 이어 붙인다

★ 파서는 정규식이다. BeautifulSoup 을 쓰지 않는 이유: 이 HTML 은 사람이 아니라
  `render.py` 가 만든 것이라 태그 모양이 고정이고(9파일에서 예외 0건), 의존성을
  하나 늘리는 값이 없다. 대신 **모르는 모양이 나오면 조용히 넘기지 않고 센다** —
  `parse_file()` 이 `unknown` 카운터를 돌려주므로 새 시험 종목을 넣었을 때
  놓친 요소가 드러난다.
"""
from __future__ import annotations

import html as _html
import os
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .ir import Block, Question, Round

_SECTION = re.compile(r'<section class="(slide[^"]*)"[^>]*>(.*?)</section>', re.S)
_QCARD = re.compile(r'<div class="qcard">(.*)</div>\s*$', re.S)
_TITLE = re.compile(r"<title>(.*?)</title>", re.S)
_TAG = re.compile(r"<[^>]+>")
_ROUND = re.compile(r"(\d+\s*회)")


# ── 텍스트 ──────────────────────────────────────────────────────────────────
def _text(frag: str) -> str:
    """태그를 벗기고 엔티티를 푼다."""
    return _html.unescape(_TAG.sub("", frag or "")).strip()


def _paras(frag: str) -> List[str]:
    """문단 목록. `<p>` 단위로 나누고 `<br>` 도 한 줄씩 편다.

    ★ `<br>` 을 문단으로 펴는 이유: 지문 202건이 `ㄱ.…<br>ㄴ.…` 꼴이고,
      PPTX 텍스트프레임에서 줄바꿈은 단락이 가장 다루기 쉽다(간격을 단락에 준다).
    """
    frag = frag or ""
    blocks = re.findall(r"<p>(.*?)</p>", frag, re.S) or [frag]
    out: List[str] = []
    for b in blocks:
        for line in re.split(r"<br\s*/?>", b):
            t = _text(line)
            if t:
                out.append(t)
    return out


# ── 블록별 파서 ─────────────────────────────────────────────────────────────
def _table(frag: str) -> List[Block]:
    """표. **비뚤어진 행은 떼어낸다.**

    ★ 원본 데이터에 열 수가 안 맞는 행이 섞여 있다. 01회 77번은 2×4 표 뒤에
      `ㄱ. 민감도…` 같은 **한 칸짜리 행 4개**가 같은 `<tbody>` 안에 붙어 있다
      (집필 실수다 — HTML 에서도 빈 칸 3개가 딸린 행으로 보인다). 그대로 옮기면
      슬라이드에도 빈 칸이 줄줄이 남는다.

      그래서 표 **끝쪽**에 몰린 한 칸 행들은 표에서 빼내 지문 문단으로 돌린다.
      원문 글자는 하나도 버리지 않고 자리만 옮기는 것이다. 표 중간에 섞여 있으면
      건드리지 않는다 — 그건 병합 셀일 수 있고, 함부로 옮기면 뜻이 바뀐다.
    """
    headers = [_text(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", frag, re.S)]
    rows: List[List[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", frag, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if tds:
            rows.append([_text(c) for c in tds])
    ncol = max([len(headers)] + [len(r) for r in rows] or [1])
    tail: List[str] = []
    while ncol > 1 and rows and len(rows[-1]) == 1:
        tail.insert(0, rows.pop()[0])
    out: List[Block] = []
    if headers or rows:
        out.append(Block(kind="table", headers=headers, rows=rows))
    if tail:
        out.append(Block(kind="passage", paras=tail))
    return out


def _pre(frag: str) -> Block:
    """코드블록. `<pre>` 안은 공백이 의미를 가지므로 **strip 하지 않는다.**"""
    inner = re.sub(r"^<pre[^>]*>|</pre>$", "", frag.strip(), flags=re.S)
    inner = _html.unescape(_TAG.sub("", inner))
    lines = inner.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return Block(kind="pre", paras=[ln.rstrip() for ln in lines])


# ★ 따옴표를 **둘 다** 받는다. 덱 산출물이 파일마다 섞여 있다 —
#   01~07회는 `viewBox="…"`, 08·09회는 `viewBox='…'` 가 섞여 있고(실측 6·7건)
#   겹따옴표만 보다가 그 도식들의 비율을 못 읽어 정사각형으로 그렸다.
#   SVG 를 손으로 쓴 사람/모델이 따옴표를 고르므로 이쪽이 맞춰야 한다.
_VB = re.compile(r'viewBox\s*=\s*["\']([\d.\s+-]+)["\']')
_FS = re.compile(r'font-size\s*=\s*["\']([\d.]+)["\']')


def _viewbox(svg: str):
    """(가로/세로 비율, viewBox 가로). 못 읽으면 (0, 0)."""
    m = _VB.search(svg)
    if not m:
        return 0.0, 0.0
    n = [float(x) for x in m.group(1).split()]
    if len(n) != 4 or not n[3]:
        return 0.0, 0.0
    return n[2] / n[3], n[2]


def _svg_font(svg: str) -> float:
    """도식 안 **대표** 글자 크기(viewBox 단위).

    ★ 최댓값이 아니라 **최빈값**을 쓴다. 도식에는 제목 한 줄이 크게 들어가는 일이
      있고(예: 20), 나머지 라벨이 전부 13 이다. 최댓값으로 맞추면 라벨이 너무
      작아진다 — 화면에서 읽어야 하는 것은 라벨이다.
    """
    vals = [float(x) for x in _FS.findall(svg)]
    if not vals:
        return 0.0
    from collections import Counter
    return Counter(vals).most_common(1)[0][0]


def _figure(frag: str) -> Optional[Block]:
    m = re.search(r"<svg[^>]*>.*?</svg>", frag, re.S)
    if m:
        svg = m.group(0)
        aspect, vw = _viewbox(svg)
        # ★ `inflow` 가 없으면 원본 CSS 가 `order:-1` 로 카드 맨 위에 올린다.
        return Block(kind="figure", svg=svg, aspect=aspect,
                     svg_font=_svg_font(svg), svg_vw=vw,
                     top="inflow" not in frag)
    m = re.search(r'<img[^>]*src="([^"]+)"', frag)
    if m:
        return Block(kind="figure", img_path=m.group(1),
                     top="inflow" not in frag)
    return None


# 짧은 지문 + 다음이 표/코드면 **라벨**이다. 원본 `render.py` 의 `with_next` 규칙.
_LABEL_MAX = 40


def _passage(frag: str, nxt: str) -> List[Block]:
    """지문 하나 → 블록 여러 개. **순서를 지킨다.**

    ★ 한 `.passage` 안에 글과 표가 함께 있다(01회 77번:
      `<p>1,000명을 대상으로…</p><table>…</table>`). 표만 뽑으면 앞의 글이
      사라진다 — 실측에서 그렇게 한 줄이 조용히 없어졌다. 그래서 자식을 훑으며
      나온 순서대로 블록을 만든다.

    ★ 표·코드 바로 앞의 짧은 글(≤40자)은 **라벨**로 본다(`[TEAM]`). 원본
      `render.py` 의 `with_next` 규칙이고, 라벨은 다음 블록과 붙어야 한다 —
      떨어지면 무슨 표인지 알 수 없다.
    """
    out: List[Block] = []
    buf: List[str] = []

    def flush(next_is_block: bool) -> None:
        if not buf:
            return
        plain = " ".join(buf)
        is_label = next_is_block and len(plain) <= _LABEL_MAX and len(buf) == 1
        out.append(Block(kind="passage_label" if is_label else "passage",
                         paras=list(buf), glue_next=is_label))
        buf.clear()

    kids = _children(_inner(frag))
    if not kids:
        kids = [("", frag)]
    for i, (_cls, f) in enumerate(kids):
        low = f.lstrip().lower()
        nxt_f = kids[i + 1][1].lstrip().lower() if i + 1 < len(kids) else nxt
        if low.startswith("<table"):
            flush(True)
            out.extend(_table(f))
        elif low.startswith("<pre"):
            flush(True)
            out.append(_pre(f))
        else:
            buf.extend(_paras(f))
            if nxt_f.startswith(("<table", "<pre")):
                flush(True)
    flush(nxt.lstrip().lower().startswith(("<table", "<pre")))
    return out


# ── 섹션 자식 나누기 ────────────────────────────────────────────────────────
_VOID = {"br", "img", "hr", "meta", "input", "use", "path", "line", "circle",
         "rect", "polygon", "polyline", "ellipse", "stop"}


def _inner(frag: str) -> str:
    """가장 바깥 태그 한 겹을 벗긴다.

    ★ `_children()` 은 넘긴 조각의 **최상위** 자식을 센다. 그래서 `<div class="ans-row">…`
      를 그대로 넘기면 자기 자신 하나만 돌려준다(실측: ans-row 235건이 전부
      `unknown` 으로 빠졌다). 한 겹 안으로 들어갈 때는 반드시 이것을 통과한다.
    """
    m = re.match(r"<[A-Za-z][^>]*>", frag or "")
    if not m:
        return frag or ""
    end = (frag or "").rfind("</")
    return frag[m.end():end] if end > m.end() else frag[m.end():]


def _children(frag: str) -> List[Tuple[str, str]]:
    """최상위 자식만 `[(class 또는 tag, 원문), ...]` 로 돌려준다."""
    out: List[Tuple[str, str]] = []
    depth = 0
    start = 0
    key = ""
    for m in re.finditer(r"<(/?)([A-Za-z][\w:-]*)([^>]*)>", frag):
        close, tag, attrs = m.groups()
        self_close = attrs.rstrip().endswith("/") or tag.lower() in _VOID
        if not close and depth == 0:
            cls = re.search(r'class="([^"]*)"', attrs)
            key = cls.group(1) if cls else tag
            start = m.start()
        if self_close:
            if depth == 0 and not close:
                out.append((key, frag[start:m.end()]))
            continue
        depth += -1 if close else 1
        if close and depth == 0:
            out.append((key, frag[start:m.end()]))
    return out


def _opts(frag: str) -> Block:
    choices: List[tuple] = []
    for m in re.finditer(r'<div class="opt">(.*?)</div>', frag, re.S):
        inner = m.group(1)
        cn = re.search(r'<span class="cn">(.*?)</span>', inner, re.S)
        rest = re.sub(r'<span class="cn">.*?</span>', "", inner, count=1, flags=re.S)
        choices.append((_text(cn.group(1)) if cn else "", _text(rest)))
    return Block(kind="opts", choices=choices)


def _mark_labels(blocks: List[Block]) -> List[Block]:
    """짧은 지문 + 다음이 표/코드 → **라벨**로 바꿔 붙인다.

    ★ 왜 후처리인가. 처음엔 `_passage()` 안에서 "다음 형제 HTML 이 `<table>` 로
      시작하는가" 로 봤는데, 표가 **자기 `.passage` 로 한 번 더 감싸여 있으면**
      다음 형제가 `<div class="passage">` 라서 못 알아봤다(SQLD 의 `[EMP]` + 표).
      감싸개 모양을 세는 대신 **만들어진 블록의 종류**를 보면 감싸기와 무관하다.

    ★ 라벨은 다음 블록과 붙는다(`glue_next`). 떨어지면 무슨 표인지 알 수 없다 —
      원본 `render.py` 의 `with_next` 규칙과 같은 이유다.
    """
    for i, b in enumerate(blocks[:-1]):
        if b.kind not in ("passage", "passage_label"):
            continue
        if blocks[i + 1].kind not in ("table", "pre"):
            continue
        plain = " ".join(b.paras)
        if len(b.paras) == 1 and len(plain) <= _LABEL_MAX:
            b.kind = "passage_label"
            b.glue_next = True
    return blocks


# ── 섹션 → 블록들 ──────────────────────────────────────────────────────────
def _problem_blocks(qcard: str, unknown: Counter) -> Tuple[List[Block], str, str]:
    """문제 면 섹션 하나. 반환: (블록들, 문번, 난도)"""
    blocks: List[Block] = []
    no = diff = ""
    kids = _children(qcard)
    for i, (cls, frag) in enumerate(kids):
        nxt = kids[i + 1][1] if i + 1 < len(kids) else ""
        base = cls.split()[0] if cls else ""
        if base == "s-head":
            m = re.search(r'<span class="qnum">(.*?)</span>', frag, re.S)
            no = _text(m.group(1)) if m else ""
            m = re.search(r'<span class="pill[^"]*">(.*?)</span>', frag, re.S)
            diff = _text(m.group(1)) if m else ""
        elif base == "q":
            blocks.append(Block(kind="q", paras=_paras(frag)))
        elif base == "passage":
            blocks.extend(_passage(frag, nxt))
        elif base == "opts":
            blocks.append(_opts(frag))
        elif base in ("diagram", "figure"):
            fb = _figure(frag)
            if fb:
                blocks.append(fb)
        elif base == "s-foot":
            pass          # 푸터는 IR 에 담지 않는다 — 레이아웃이 다시 정한다
        else:
            unknown["problem/" + cls] += 1
    return _mark_labels(blocks), no, diff


_BADGE = re.compile(r"정답\s*([①-⑮\d]+)\s*(.*)$", re.S)


def _answer_parts(qcard: str, unknown: Counter):
    """해설 면 섹션 하나. 반환: (정답번호, 정답본문, 해설블록들, 도식)"""
    ano = atext = ""
    expl: List[Block] = []
    fig: Optional[Block] = None
    for cls, frag in _children(qcard):
        base = cls.split()[0] if cls else ""
        if base == "answer-badge":
            t = _text(frag)
            # "정답 ③  ㄴ, ㄹ" — 번호와 본문을 가른다. 실측 720/720 이 이 꼴이다.
            m = _BADGE.match(t)
            if m:
                ano, atext = m.group(1), m.group(2).strip()
            else:
                ano, atext = "", t
        elif base == "ans-row":
            # 2단 — 왼쪽 도식, 오른쪽 해설
            for c2, f2 in _children(_inner(frag)):
                b2 = c2.split()[0] if c2 else ""
                if b2 == "ans-fig":
                    fb = _figure(f2)
                    if fb:
                        fb.top = False       # 2단 안에서는 order:-1 이 의미 없다
                        fig = fb
                elif b2 == "ans-txt":
                    for c3, f3 in _children(_inner(f2)):
                        if (c3.split()[0] if c3 else "") == "expl":
                            expl.append(Block(kind="expl", paras=_paras(f3)))
                        else:
                            unknown["answer/ans-txt/" + c3] += 1
                else:
                    unknown["answer/ans-row/" + c2] += 1
        elif base == "expl":
            expl.append(Block(kind="expl", paras=_paras(frag)))
        elif base in ("diagram", "figure"):
            fb = _figure(frag)
            if fb:
                fig = fb
        elif base == "table":
            expl.extend(_table(frag))
        elif base == "s-foot":
            pass
        else:
            unknown["answer/" + cls] += 1
    return ano, atext, _mark_labels(expl), fig


# ── 공개 API ────────────────────────────────────────────────────────────────
def parse_file(path: str, exam: str = "") -> Tuple[Round, Dict[str, int]]:
    """덱 HTML 한 개 → (`Round`, 못 알아본 요소 카운터).

    ★ `exam`(자격증명)은 HTML 에 없다. `<title>` 은 "모의고사 01회 — 문제 풀이" 까지다.
      간지 eyebrow 에 들어가는 값이므로 호출부가 준다(CLI `--exam`,
      또는 `_book.json` 의 `label`).
    """
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    mt = _TITLE.search(raw)
    title = _text(mt.group(1)) if mt else ""
    m = _ROUND.search(title) or _ROUND.search(os.path.basename(path))
    rnd = Round(exam=exam, round_no=m.group(1).replace(" ", "") if m else "",
                title=title, source=path)

    unknown: Counter = Counter()
    body = raw.split("<body", 1)[1] if "<body" in raw else raw
    cur: Optional[Question] = None
    for cls, inner in _SECTION.findall(body):
        mq = _QCARD.search(inner)
        qcard = mq.group(1) if mq else inner
        # ★ 머리도 배지도 없는 장은 **이어지는 장**이다. 그 장이 문제의 2장째인지
        #   해설의 2장째인지는 마크업에 없다 — 앞 문항이 어디까지 왔는지가 안다.
        #   전에는 전부 문제 면 파서로 보냈고, 그래서 해설의 이어지는 장에 있던
        #   `div.expl` 이 `unknown["problem/expl"]` 로 세어지고 **버려졌다**
        #   (SQLD 20회차 실측 105건 — 해설 뒷부분이 통째로 사라졌다).
        cont_answer = ('class="answer-badge"' not in qcard
                       and '<div class="s-head"' not in qcard
                       and cur is not None
                       and bool(cur.answer_no or cur.expl))
        if 'class="answer-badge"' in qcard or cont_answer:
            if cur is None:
                unknown["answer-before-any-question"] += 1
                continue
            ano, atext, expl, fig = _answer_parts(qcard, unknown)
            # ★ 해설이 여러 섹션으로 쪼개져 있으면 **이어 붙인다.**
            if cur.answer_no or cur.expl:
                # ★ 도식 자리는 하나뿐이다(2단 배치용). 이어지는 장이 도식을 또
                #   들고 오면 **본문 흐름에 넣는다** — `_answer_page` 가
                #   `blocks.extend(q.expl)` 로 그대로 흘려 준다. 버리면 사라진다.
                if fig is not None:
                    if cur.figure is None:
                        cur.figure = fig
                    else:
                        fig.top = False
                        cur.expl.append(fig)
                cur.expl.extend(expl)
            else:
                cur.answer_no, cur.answer_text = ano, atext
                cur.expl, cur.figure = expl, fig
            continue

        blocks, no, diff = _problem_blocks(qcard, unknown)
        if no:                                   # s-head 있음 → 새 문항
            n = int(re.sub(r"\D", "", no) or 0)
            cur = Question(no=n, difficulty=diff, blocks=blocks)
            rnd.questions.append(cur)
        elif cur is not None:                    # cont-top → 앞 문항에 이어 붙인다
            cur.blocks.extend(blocks)
        else:
            unknown["orphan-section"] += 1
    return rnd, dict(unknown)
