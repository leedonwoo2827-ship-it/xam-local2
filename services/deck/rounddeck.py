# -*- coding: utf-8 -*-
r"""05/ 의 편별 `deck.html` 을 **회차 한 파일로** 이어붙인다 (`_deck-export/NN회.html`).

`tools/deck_rounds.py` 에 있던 것을 서비스로 옮긴 것이다. 옮긴 이유는 하나 —
그 파일이 책 경로를 상수로 들고 있어서(`BOOK = D:\00work\ocr-output-260730`),
작업 폴더를 SQLD 로 바꿔도 빅분기를 합쳤다. 여기서는 `paths.book_dir()` 를 쓴다.
CLI 는 이 함수를 부르는 얇은 껍데기로 남는다 — 둘이 갈라지면 화면과 명령줄이
다른 파일을 만든다.

**왜 회차로 합치나.** `deck.html` 은 영상 한 편(문항 10개) 단위로 굽는다 — 렌더가
편별로 돌기 때문이다. pptx 로 옮길 때는 **회차**가 단위다. 회차 하나를 넘겨야
변환기가 문항을 되붙여 다시 쪼갤 수 있고, 넘침 보고의 좌표도 한 곳으로 모인다.

**합치기가 안전한 이유.** `deck.html` 은 외부 의존이 0 이다 — CSS 는 인라인이고
(`render.py` 머리말: 캡처가 `file://` 로 연다), 도식은 인라인 SVG, MathJax·웹폰트도
링크하지 않는다. 그래서 `<head>` 를 첫 편 것 하나만 두고 나머지 편의 `<section>` 만
뒤에 붙이면 모양이 그대로 보존된다.

★ **슬라이드를 다시 그리지 않는다.** 원본 `<section>` 을 문자 그대로 옮긴다.
  다시 그리면 `render_deck()` 을 한 번 더 통과하게 되고, 그러면 영상에 나간 면과
  pptx 로 가는 면이 갈라질 수 있다 — 그 규약이 이 파일보다 위다.

── 편(篇)의 흔적을 뺀다 ────────────────────────────────────────────────────
  · `.s-foot`      페이지 번호 + 전체 장수. 편 안에서의 위치라 합친 문서에선 틀리다
  · `.slide.cover` 편 표지. 변환기가 편마다 자기 간지를 새로 만든다
  · `data-generator` 내부 도구명

★ 남기는 것: `data-slides` · `data-safe-line` · `--slide-*` 기하. 변환기의 넘침
  판정이 그 값을 읽는다.
"""
from __future__ import annotations

import os
import re

from services.book import paths

SEC = '<section class="slide'

# 편 표지 한 장. 안에 <section> 이 없으므로 비탐욕으로 닫는 데까지가 정확하다.
RE_COVER = re.compile(r'<section class="slide cover".*?</section>', re.S)
# 발 줄. 안에 <span> 만 있다.
RE_FOOT = re.compile(r'<div class="s-foot">.*?</div>', re.S)


def bundle_decks(round_code: str, book: str = "") -> list[str]:
    """그 회차의 편별 deck.html 경로. **폴더가 진실이다** — 편 수를 코드에 박지 않는다.

    `-10` 이 `-2` 뒤로 가야 하므로 편 번호를 정수로 보고 정렬한다.
    """
    book = book or paths.book_dir()
    root = os.path.join(book, "05")
    if not os.path.isdir(root):
        return []
    found: list[tuple[int, str]] = []
    for name in os.listdir(root):
        parsed = paths.parse_bundle(name)
        if not parsed or paths.round_code(parsed[0]) != round_code:
            continue
        p = os.path.join(root, name, "source", "deck.html")
        if os.path.isfile(p):
            found.append((parsed[1], p))
    return [p for _n, p in sorted(found)]


def merge(round_code: str, *, book: str = "",
          keep_chrome: bool = False) -> tuple[str, int, int, int]:
    """회차 하나 → (합친 HTML, 편 수, 장 수, 뺀 표지 수)."""
    parts = bundle_decks(round_code, book)
    if not parts:
        raise FileNotFoundError(
            f"{round_code}: deck.html 이 없습니다. 먼저 「굽기」를 돌리세요 "
            f"({paths.rel(os.path.join(book or paths.book_dir(), '05'))})")

    head, secs = "", []
    for f in parts:
        with open(f, encoding="utf-8") as fh:
            t = fh.read()
        if SEC not in t or "</div></body>" not in t:
            raise ValueError(f"{paths.rel(f)}: deck.html 의 모양이 예상과 다릅니다 "
                             f"(`{SEC}` … `</div></body>` 를 찾지 못했습니다)")
        if not head:
            head = t[: t.index(SEC)]
        secs.append(t[t.index(SEC): t.rindex("</div></body>")])

    body = "\n".join(secs)
    cut = len(RE_COVER.findall(body))
    if not keep_chrome:
        body = RE_COVER.sub("", body)
        body = RE_FOOT.sub("", body)
    else:
        cut = 0

    n = len(re.findall(re.escape(SEC), body))
    # 표지의 "(1/8)" 은 첫 편 것이다 — 합친 문서의 제목으로는 틀리다.
    head = re.sub(r"\s*\((\d+)/(\d+)\)(?=</title>)", "", head, count=1)
    head = re.sub(r'data-slides="\d+"', f'data-slides="{n}"', head, count=1)
    if not keep_chrome:
        head = re.sub(r'\s*data-generator="[^"]*"', "", head, count=1)
    return head + body + "\n</div></body></html>\n", len(parts), n, cut


def write_round(round_code: str, *, book: str = "",
                keep_chrome: bool = False) -> dict:
    """회차 하나를 `<book>/_deck-export/NN회.html` 로 쓴다."""
    doc, k, n, cut = merge(round_code, book=book, keep_chrome=keep_chrome)
    dst = paths.round_deck_html(round_code, book=book)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    # 이 파일은 변환기(기계)만 읽는다 — 줄끝은 LF 로 고정한다.
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(doc)
    return {"round": round_code, "path": dst, "rel": paths.rel(dst),
            "parts": k, "slides": n, "covers_removed": cut,
            "size_kb": os.path.getsize(dst) // 1024}


def rounds_in(book: str = "") -> list[str]:
    """그 책의 회차 코드. `05/` 에 실제로 있는 것만 — 폴더가 진실이다."""
    book = book or paths.book_dir()
    root = os.path.join(book, "05")
    if not os.path.isdir(root):
        return []
    out = set()
    for name in os.listdir(root):
        parsed = paths.parse_bundle(name)
        if parsed:
            out.add(paths.round_code(parsed[0]))
    return sorted(out)


def write_all(round_codes: list[str] | None = None, *,
              book: str = "") -> list[dict]:
    codes = round_codes or rounds_in(book)
    return [write_round(rc, book=book) for rc in codes]
