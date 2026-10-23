# -*- coding: utf-8 -*-
"""요약노트 HTML → `ir.Doc`.

입력은 `xam-lo/services/authoring/theory.py` 가 낸 `03/N<key>.html` 이다. 문제 덱과
달리 **슬라이드로 쪼개져 있지 않고** 흐르는 글이다:

    h1                  1과목 · 데이터 모델링의 이해
    h2 + label.q        1. 정규화와 함수 종속        (대단원)
    h3 + label.q        1.1. 정규화의 목적과 성능    (소단원 = 슬라이드 한 장)
    p                   리드 한 문장
    ul > li             항목 (b 로 강조)
    table / svg         표 · 도식
    span.fd             인라인 칩 ("학번 → 학생명")

★ 슬라이드 단위는 **h3** 다. 규약이 원본에 적혀 있다(`theory.py`:408) —
  *"목차는 우리가 낸 h2/h3 가 이미 목차이고, 시각물은 그 앱이 장마다 채운다"*.
  실측도 같은 답이다: h3 당 항목 4개 · 300자(중앙값)로 한 장에 딱 맞는다
  (파일1 h3 59개 · 파일2 90개, 최대 1,531자만 두 장이 된다).

★ **출제이력(`label.q`)을 버린다.** 제목마다 `<label class="q"><input type=checkbox>
  <b>20</b><span class="qn">모의 1회 6번 · 2회 3번 · …</span></label>` 이 붙어 있고,
  많은 것은 36건이다. 웹에서는 "이 문항 봤다" 체크박스로 쓰이지만 슬라이드에서는
  제목을 밀어내는 잡음이다(사용자 확정 2026-08-21: "일괄이면 지우면 되지 않을까").
  문항 번호는 문제 덱이 발문 앞에 이미 보여 준다.

★ h1 의 "N과목" 에서 과목 번호를 뽑는다. **색을 고르는 열쇠**다(사용자 확정:
  과목별로 다른 색). 못 읽으면 0 이고, 그때는 기본 색으로 떨어진다.
"""
from __future__ import annotations

import html as _html
import os
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .ir import Block, Doc, Topic

_TAG = re.compile(r"<[^>]+>")
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
# "1과목 · 데이터 모델링의 이해"
_SUBJ = re.compile(r"(\d+)\s*과목\s*[·:\-—\s]*(.*)")
# 제목 앞머리 번호 "1.8." / "1." → 번호와 본문을 가른다
_NUM = re.compile(r"^\s*([\d.]+?)\.?\s+(.*)$", re.S)


def _drop_qrefs(frag: str) -> str:
    """출제이력 `label.q` 를 통째로 지운다.

    ★ 태그를 벗기는 것으로는 안 된다 — 안의 글자("20모의 1회 6번 · …")가 제목에
      붙어 남는다. 실측에서 h3 제목이 그 꼴로 나왔다. 요소째로 지운다.
    """
    return re.sub(r"<label\b[^>]*class=\"q\"[^>]*>.*?</label>", "", frag,
                  flags=re.S)


def _text(frag: str) -> str:
    return _html.unescape(_TAG.sub("", _drop_qrefs(frag or ""))).strip()


def _inline(frag: str) -> str:
    """인라인 태그만 벗겨 한 줄로. `<b>`·`<span class="fd">` 의 글자는 살린다.

    ★ 굵기는 잃는다. `Block` 이 문단을 문자열로 들고 있어서다 — 런 단위로 바꾸려면
      측정도 런 단위가 되어야 하고, 그 값이 지금은 굵기 하나뿐이다(_CONTEXT 참고).
    """
    t = _drop_qrefs(frag or "")
    t = re.sub(r"<br\s*/?>", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub("", t))).strip()


# ── 블록 파서 ───────────────────────────────────────────────────────────────
def _table(frag: str) -> Optional[Block]:
    headers = [_inline(c) for c in re.findall(r"<th[^>]*>(.*?)</th>", frag, re.S)]
    rows: List[List[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", frag, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if tds:
            rows.append([_inline(c) for c in tds])
    if not headers and not rows:
        return None
    return Block(kind="table", headers=headers, rows=rows)


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
    if not m:
        return None
    svg = m.group(0)
    aspect, vw = _viewbox(svg)
    # 이론 덱의 도식은 흐름 안에 있다 — 카드 맨 위로 올리지 않는다.
    return Block(kind="figure", svg=svg, aspect=aspect,
                 svg_font=_svg_font(svg), svg_vw=vw, top=False)


def _bullets(frag: str) -> Optional[Block]:
    items = [_inline(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", frag, re.S)]
    items = [t for t in items if t]
    return Block(kind="bullets", paras=items) if items else None


def _para(frag: str) -> Optional[Block]:
    t = _inline(frag)
    return Block(kind="passage", paras=[t]) if t else None


# ── 본문 조각 → 블록들 ──────────────────────────────────────────────────────
# ★ 최상위 요소만 순서대로 훑는다. 이 HTML 은 사람이 아니라 `theory.py` 의 계약을
#   지키는 모델이 낸 것이라 구조가 얕다(실측: 중첩 목록 0건).
_TOP = re.compile(
    r"<(p|ul|ol|table|figure|svg|pre|blockquote|div)\b[^>]*>.*?</\1>"
    r"|<svg\b[^>]*>.*?</svg>", re.S | re.I)


def _blocks(chunk: str, unknown: Counter) -> List[Block]:
    out: List[Block] = []
    for m in _TOP.finditer(chunk):
        frag = m.group(0)
        tag = (m.group(1) or "svg").lower()
        blk: Optional[Block] = None
        if tag in ("ul", "ol"):
            blk = _bullets(frag)
        elif tag == "table":
            blk = _table(frag)
        elif tag in ("figure", "svg", "div"):
            blk = _figure(frag) or _table(frag)
            if blk is None and tag == "div":
                blk = _para(frag)
        elif tag == "pre":
            inner = re.sub(r"^<pre[^>]*>|</pre>$", "", frag.strip(), flags=re.S)
            lines = _html.unescape(_TAG.sub("", inner)).split("\n")
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()
            if lines:
                blk = Block(kind="pre", paras=[l.rstrip() for l in lines])
        elif tag in ("p", "blockquote"):
            blk = _para(frag)
        if blk is not None:
            out.append(blk)
        else:
            unknown[f"theory/{tag}"] += 1
    return out


# ── 공개 API ────────────────────────────────────────────────────────────────
def parse_file(path: str, exam: str = "") -> Tuple[Doc, Dict[str, int]]:
    """요약노트 HTML 한 개 → (`Doc`, 못 알아본 요소 카운터)."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    body = raw.split("</style>")[-1]
    body = body.split("<body", 1)[1] if "<body" in body else body

    doc = Doc(exam=exam, source=path)
    m = _H1.search(raw)
    if m:
        doc.title = _text(m.group(1))
        sm = _SUBJ.match(doc.title)
        if sm:
            doc.subject_no = int(sm.group(1))
            doc.subject = sm.group(2).strip()
        else:
            doc.subject = doc.title

    unknown: Counter = Counter()

    # h2/h3 경계로 자른다. h2 다음 h3 전의 글은 그 h2 의 도입부이므로 h3 없는
    # Topic 으로 만든다 — 버리면 대단원 첫머리 설명이 사라진다.
    marks = [(m.start(), m.group(1).lower(), m.group(2))
             for m in re.finditer(r"<(h2|h3)[^>]*>(.*?)</\1>", body, re.S)]
    chap_no = chap = ""
    for i, (pos, tag, title_html) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        head = _text(title_html)
        num, name = "", head
        nm = _NUM.match(head)
        if nm:
            num, name = nm.group(1), nm.group(2).strip()
        chunk = body[pos:end]
        # 제목 요소 자체는 블록에서 뺀다
        chunk = re.sub(r"^<(h2|h3)[^>]*>.*?</\1>", "", chunk, count=1, flags=re.S)
        blocks = _blocks(chunk, unknown)
        if tag == "h2":
            chap_no, chap = num, name
            if not blocks:
                continue          # 간지용 제목뿐이면 슬라이드를 만들지 않는다
            doc.topics.append(Topic(no=num, title=name, blocks=blocks,
                                    chapter_no=num, chapter=name))
        else:
            doc.topics.append(Topic(no=num, title=name, blocks=blocks,
                                    chapter_no=chap_no, chapter=chap))
    return doc, dict(unknown)


def looks_like_theory(path: str) -> bool:
    """이 파일이 요약노트인가. 파일 하나만 보고 파서를 고르는 데 쓴다.

    ★ 파일명으로 고르지 않는다. 문제 덱은 `01회.html`, 요약노트는 `1summary_*.html`
      이지만 업로드되면 `deck__1summary_datamodel.html` 처럼 이름이 바뀐다(실측 —
      그래서 요약노트가 문제 덱 파서로 들어가 0장이 나왔다). 내용으로 판정한다.
    """
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(200000)
    except Exception:
        return False
    if 'class="slide' in head or 'class="qcard"' in head:
        return False
    return bool(re.search(r"<h3[^>]*>", head))
