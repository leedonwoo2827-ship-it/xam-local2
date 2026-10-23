# -*- coding: utf-8 -*-
"""인라인 SVG → PNG.

★ 왜 래스터화하는가. python-pptx 는 SVG 를 못 넣는다(`add_picture` 가 아는 형식에
  SVG 가 없다). 그리고 SVG 의 도형을 PPT 도형으로 옮기는 것도 답이 아니다 —
  실측 도식 235개 안에 `<path>` 184개, `<marker>` 11개가 있어서 재현이 어긋나는
  순간 그림이 조용히 틀린 그림이 된다. 텍스트는 도형으로 정확히 옮길 수 있고(그래서
  옮긴다), 그림은 그림으로 두는 것이 맞다.

★ Chromium 을 **한 번만** 띄운다. 회차당 도식이 26개(01회)이고 9회차면 235개인데,
  브라우저를 매번 띄우면 그것만으로 몇 분이 나간다. `Raster` 를 컨텍스트 매니저로
  써서 한 세션에 다 뽑는다.

★ 배치 폭의 2배를 조금 넘게 뽑는다. 도식이 차지하는 자리는 최대 슬라이드의 44%
  (≈790px = 5.5in)이므로 1800px 이면 약 330DPI 다 — PowerPoint 가 늘려도 뭉개지지
  않고 회차당 3MB 안쪽이다. 4배(3200px)로 뽑아 봤지만 눈에 차이가 없고 파일만 컸다.

★ 같은 SVG 는 한 번만 뽑는다(원문 해시). 회차 사이에 겹치는 도식이 있고, 다시 돌릴
  때도 캐시가 살아 있으면 브라우저를 아예 안 띄운다.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List, Optional

# 도식 렌더 폭(px). 실제 배치 폭이 아니라 **원본 해상도**다 — 배치는 PPTX 가 한다.
RENDER_W = 900
SCALE = 2

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;padding:0;background:#fff}}
/* ★ 배경을 흰색으로 깐다. 원본 SVG 대부분이 배경을 안 그려서(투명) 그대로 뽑으면
   PPTX 에서 검은 배경으로 보이는 뷰어가 있다. */
svg{{display:block;width:{w}px;height:auto}}
text{{font-family:"Pretendard","Malgun Gothic","맑은 고딕",sans-serif}}
</style></head><body>{svg}</body></html>"""


def _key(svg: str) -> str:
    return hashlib.sha1(svg.encode("utf-8")).hexdigest()[:16]


def _sized(svg: str) -> str:
    """`width`/`height` 속성을 지워 CSS 가 폭을 정하게 한다.

    원본 SVG 는 `viewBox` 만 있거나 고정 `width` 가 붙어 있다. 고정 폭이 남으면
    `RENDER_W` 로 안 커져서 2배 해상도가 안 나온다.
    """
    svg = re.sub(r'(<svg[^>]*?)\s+width="[^"]*"', r"\1", svg, count=1)
    svg = re.sub(r'(<svg[^>]*?)\s+height="[^"]*"', r"\1", svg, count=1)
    return svg


class Raster:
    """도식 래스터화 세션.

        with Raster(cache_dir) as rz:
            png = rz.png(svg)          # → 파일 경로 (없으면 None)

    ★ Playwright 가 없거나 브라우저가 안 깔려 있으면 **죽지 않고** `None` 을 돌려준다.
      그 문항은 도식 없이 해설만 나가고, `misses` 에 몇 개가 빠졌는지 남는다 —
      조용히 사라지지 않게 하는 것이 요점이다.
    """

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._pw = None
        self._browser = None
        self._page = None
        self.misses: List[str] = []
        self.rendered = 0
        self.cached = 0

    # ── 세션 ────────────────────────────────────────────────────────────
    def __enter__(self) -> "Raster":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _ensure(self) -> bool:
        if self._page is not None:
            return True
        if self._pw is False:          # 한 번 실패했으면 다시 시도하지 않는다
            return False
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch()
            self._page = self._browser.new_page(
                viewport={"width": RENDER_W, "height": 900},
                device_scale_factor=SCALE)
            return True
        except Exception:
            self._pw = False
            return False

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
        finally:
            if self._pw not in (None, False):
                try:
                    self._pw.stop()
                except Exception:
                    pass
            self._pw = self._browser = self._page = None

    # ── 변환 ────────────────────────────────────────────────────────────
    def png(self, svg: str) -> Optional[str]:
        if not svg:
            return None
        out = os.path.join(self.cache_dir, _key(svg) + ".png")
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            self.cached += 1
            return out
        if not self._ensure():
            self.misses.append(_key(svg))
            return None
        try:
            self._page.set_content(_HTML.format(w=RENDER_W, svg=_sized(svg)),
                                   wait_until="load")
            el = self._page.query_selector("svg")
            if el is None:
                self.misses.append(_key(svg))
                return None
            el.screenshot(path=out, omit_background=False)
            self.rendered += 1
            return out
        except Exception:
            self.misses.append(_key(svg))
            return None

    def stats(self) -> Dict[str, int]:
        return {"rendered": self.rendered, "cached": self.cached,
                "missed": len(self.misses)}
