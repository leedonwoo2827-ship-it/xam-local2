# -*- coding: utf-8 -*-
"""`/slide/` 미리보기 — 파일을 굽지 않고 요청마다 지금 데이터로 그린다.

`services/export/printdoc.py` 와 같은 패턴이다. 그래서 **미리보기와 베이크가 같은
함수**(`render.render_deck`)를 쓴다는 규약이 유지된다 — 셋이 갈라지면 "OK 한 면" 과
"나가는 면" 이 달라진다.

★ 실패하면 빈 문서가 아니라 예외를 낸다. `app.py` 의 `_print_page` 가 409 + 이유로
  바꿔 준다. 조용히 빈 덱을 내면 "슬라이드가 없는 번들" 로 읽힌다.
"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Tuple

# ★ `BOOK_DIR` 을 **모듈 상수로 잡지 않는다.** 그것은 `.env` 의 첫 실행 기본값이고,
#   실제로 쓰는 폴더는 작업 폴더 화면에서 고른 것이다(`paths.book_dir()`).
#   상수로 잡아 두니 폴더를 SQLD 로 바꿔도 화면이 시작할 때의 빅분기를 계속 읽었다
#   — 집필 화면에 SQLD 시험정보와 빅분기 회차가 함께 뜬 원인이다(2026-08-19).

from . import render, theme
from services.book import paths


def _bundles() -> List[str]:
    d = os.path.join(paths.book_dir(), "05")
    if not os.path.isdir(d):
        return []
    return sorted(x for x in os.listdir(d)
                  if os.path.isdir(os.path.join(d, x)) and not x.startswith("_"))


def _load(b: str) -> Tuple[Dict[str, Any], str]:
    """번들의 lesson JSON 과 그림 폴더 상대경로."""
    src = os.path.join(paths.book_dir(), "05", b, "source")
    p = os.path.join(src, f"lesson_{b}.json")
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"번들 lesson 을 찾지 못했습니다: {p}\n"
            f"`05/{b}/source/lesson_{b}.json` 이 있어야 합니다.")
    with open(p, encoding="utf-8") as f:
        lesson = json.load(f)
    # 그림은 `02/assets/` 에 있고 번들에는 복사돼 있지 않다. 미리보기는 `/book` 마운트로
    # 실제 파일을 가리킨다(베이크 때는 번들 안 상대경로로 바뀐다).
    return lesson, "/book/02/assets"


def index_html() -> str:
    bs = _bundles()
    rows = "".join(
        f'<li><a href="/slide/bundle?b={html.escape(b)}">{html.escape(b)}</a> '
        f'<a class="fit" href="/slide/bundle?b={html.escape(b)}&fit=1">?fit=1</a></li>'
        for b in bs)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>슬라이드 미리보기</title><style>
body{{font:14px/1.8 -apple-system,"Malgun Gothic",sans-serif;padding:26px;
      max-width:820px;margin:0 auto;color:#1e2637}}
h1{{font-size:20px}} ul{{columns:3;list-style:none;padding:0}}
li{{margin:2px 0}} a{{color:#2c5ce6;text-decoration:none}}
a.fit{{color:#dc2626;font-size:12px;margin-left:4px}}
.note{{background:#f6f8fc;border:1px solid #e3e8f0;border-radius:8px;
       padding:12px 14px;margin:14px 0}}
</style></head><body>
<h1>슬라이드 미리보기 — {len(bs)}번들</h1>
<div class="note">
  <b>?fit=1</b> 은 안전선({theme.safe_line(True)}px)을 빨간 띠로 얹습니다.
  <b>빨간 게 없으면 통과</b>입니다.<br>
  슬라이드는 <b>수식을 그리지 않습니다</b> — 미리보기에만 켜면 슬라이드에 없는 수식을
  보여주게 되어 더 나쁩니다.<br>
  ★ 분할(paginate)은 <b>붙어 있습니다.</b> 다만 <b>문제 면은 최대 2장</b>,
  해설 면은 필요한 만큼 쪼갭니다. 지문(표·SQL)이 커서 2장으로도 안 담기면
  <b>그때부터 넘칩니다</b> — 그 넘침을 눈으로 보는 것이 이 화면의 목적입니다.
  넘친 문항은 「문항 교정」에서 지문·해설을 줄이면 됩니다.
</div>
<ul>{rows or "<li>05/ 에 번들이 없습니다.</li>"}</ul>
</body></html>"""


def bundle_html(b: str | None = None, fit: bool = False) -> str:
    if not b:
        raise ValueError("번들 코드가 필요합니다 (예: /slide/bundle?b=m01-1).")
    if "/" in b or "\\" in b or ".." in b:
        raise ValueError(f"번들 코드가 올바르지 않습니다: {b}")
    lesson, asset_dir = _load(b)
    return render.render_deck(lesson, tokens_css=theme.tokens_css(),
                              asset_dir=asset_dir, fit=fit)
