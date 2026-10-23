# -*- coding: utf-8 -*-
"""05/ 의 편별 `deck.html` 을 **회차 한 파일로** 이어붙인다 (`_deck-export/`).

  python tools/deck_rounds.py                     전부 (m01 … m09)
  python tools/deck_rounds.py m01 m03             일부 회차만
  python tools/deck_rounds.py --out D:/어디/폴더   내보낼 곳 지정
  python tools/deck_rounds.py --keep-chrome       표지·페이지번호를 남긴다 (원본 그대로)

**왜 이 도구가 있나.** `deck.html` 은 영상 한 편(문항 10개) 단위로 굽는다 — 렌더가
편별로 돌기 때문이다. 그런데 pptx 로 옮길 때는 **회차**가 단위다. 편별 8개를 따로
넘기면 pptx 도 8개가 되고, 넘침을 고쳐 달라고 말할 자리가 8곳으로 갈라진다.

**합치기가 안전한 이유.** `deck.html` 은 외부 의존이 0 이다 — CSS 는 인라인이고
(`services/deck/render.py` 머리말: 캡처가 `file://` 로 연다), 도식은 인라인 SVG,
MathJax·웹폰트도 링크하지 않는다. 그래서 `<head>` 를 첫 편 것 하나만 두고 나머지
편의 `<section>` 만 뒤에 붙이면 모양이 그대로 보존된다.

★ **슬라이드를 다시 그리지 않는다.** 원본 `<section>` 을 문자 그대로 옮긴다.
  다시 그리면 `render_deck()` 을 한 번 더 통과하게 되고, 그러면 영상에 나간 면과
  pptx 로 가는 면이 갈라질 수 있다 — 그 규약이 이 파일보다 위다. 그래서 아래 제거는
  **지우기만** 한다. 값을 다시 계산하지 않는다.

── 편(篇)의 흔적을 뺀다 (2026-08-21 지시) ─────────────────────────────────────
받는 쪽은 `aim-local` 79 레시피다. 그쪽은 이 HTML 을 읽어 pptx 를 만들고 **넘친 장을
보고**한다. 편 단위의 표기가 남아 있으면 그 보고의 좌표가 어긋난다 — "3 / 21" 이 한
파일에 8번 되풀이되고, 표지가 "8편 중 3편" 이라고 말하므로 회차 문서를 편 문서로 읽는다.

  · `.s-foot`      페이지 번호 + 전체 장수. 편 안에서의 위치라 합친 문서에선 틀리다
  · `.slide.cover` 편 표지 72장. "(3/8)" · "8편 중 3편" · "21번부터 30번까지"
  · `data-generator` 내부 도구명

★ `.s-foot` 은 HTML 에서 빼는 것으로 끝난다. `slidecss.py:122` 는 `--slide-foot` 이
  자리를 잡아 둔다고 적어 두었지만, 지금 그 변수를 **소비하는 규칙이 없다**(CSS 가 쓰는
  것은 `--slide-w/h/pad/head/safe` 뿐). `.s-foot` 은 `margin-top:auto` 로 바닥에 붙는
  보통 흐름 요소라, 지우면 그 높이(약 44px)가 본문으로 돌아간다 — 넘침이 줄어든다.

★ 남기는 것: `data-slides` · `data-safe-line` · `--slide-*` 기하. 받는 쪽의 넘침
  판정이 그 값을 읽는다. 이건 "문제될 것" 이 아니라 판정의 근거다.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BOOK = Path(r"D:\00work\ocr-output-260730")
SEC = '<section class="slide'

# 편 표지 한 장. 안에 <section> 이 없으므로 비탐욕으로 닫는 데까지가 정확하다.
RE_COVER = re.compile(r'<section class="slide cover".*?</section>', re.S)
# 발 줄. 안에 <span> 만 있다(전 회차 720개 전부 확인).
RE_FOOT = re.compile(r'<div class="s-foot">.*?</div>', re.S)


def rounds(book: Path) -> list[str]:
    """05/ 에 있는 회차 접두어. 폴더가 진실이다 — 개수를 코드에 박지 않는다."""
    return sorted({p.name.split("-")[0] for p in (book / "05").glob("m*-*") if p.is_dir()})


def merge(book: Path, rd: str, keep_chrome: bool = False) -> tuple[str, int, int, int]:
    """회차 하나 → (합친 HTML, 편 수, 장 수, 뺀 장 수)."""
    parts = sorted(
        (book / "05").glob(f"{rd}-*/source/deck.html"),
        key=lambda p: int(p.parts[-3].split("-")[1]),        # -10 이 -2 뒤로 가야 한다
    )
    if not parts:
        raise SystemExit(f"{rd}: deck.html 이 없다. tools/bake_all.py 를 먼저 돌린다")

    head, secs = "", []
    for f in parts:
        t = f.read_text(encoding="utf-8")
        if not head:
            head = t[: t.index(SEC)]
        secs.append(t[t.index(SEC) : t.rindex("</div></body>")])

    body = "\n".join(secs)
    before = len(RE_COVER.findall(body))
    if not keep_chrome:
        body = RE_COVER.sub("", body)
        body = RE_FOOT.sub("", body)
    else:
        before = 0

    n = len(re.findall(re.escape(SEC), body))
    # 표지의 "(1/8)" 은 첫 편 것이다 — 합친 문서의 제목으로는 틀리다.
    head = re.sub(r"\s*\((\d+)/(\d+)\)(?=</title>)", "", head, count=1)
    head = re.sub(r'data-slides="\d+"', f'data-slides="{n}"', head, count=1)
    if not keep_chrome:
        head = re.sub(r'\s*data-generator="[^"]*"', "", head, count=1)
    return head + body + "\n</div></body></html>\n", len(parts), n, before


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rounds", nargs="*", help="회차 접두어 (기본: 전부)")
    ap.add_argument("--book", default=str(BOOK))
    ap.add_argument("--out", default="", help="기본: <book>/_deck-export")
    ap.add_argument("--keep-chrome", action="store_true", help="표지·페이지번호를 남긴다")
    a = ap.parse_args()

    book = Path(a.book)
    out = Path(a.out) if a.out else book / "_deck-export"
    out.mkdir(parents=True, exist_ok=True)

    want = a.rounds or rounds(book)
    total = 0
    for rd in want:
        doc, k, n, cut = merge(book, rd, a.keep_chrome)
        # m01 → 01회. 파일 이름이 좌표를 그대로 말해야 pptx 쪽에서 헷갈리지 않는다.
        dst = out / f"{rd.lstrip('m')}회.html"
        dst.write_text(doc, encoding="utf-8")
        total += n
        print(f"{dst.name:12s} 편 {k}  장 {n:4d}  표지제거 {cut}  {dst.stat().st_size / 1024:6.0f}KB")

    print(f"\n{out}  회차 {len(want)}  장 {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
