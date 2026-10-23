"""렌더 사전점검 — chodangi 가 SystemExit 로 죽기 전에 우리가 막는다.

make_bundle_video.build() 는 deck 슬라이드 수와 capture:true 씬 수가 다르면
    [error] deck 슬라이드(N) ≠ 캡처 씬(M) — 슬라이드/씬 1:1 이 깨졌습니다.
로 즉시 종료한다. Playwright 로 deck 을 다 캡처한 **뒤에** 죽으므로 시간도 버린다.
그래서 스폰 전에 같은 검사를 하고, 어긋난 자리를 나란히 보여준다.

★ **강의덱(pptx)을 쓰는 번들은 기준이 다르다** (2026-08-24). 그 번들은 슬라이드가
  `source/deck.pptx` 에서 나오고 장 수는 `source/pages.json` 이 진실이다. deck.html 은
  변환기의 입력으로만 남아 장 수가 **일부러 다르다**(과분할을 되붙여 다시 쪼갠다).
  그래서 pages.json 이 있으면 그것과 대조하고, deck.html 과의 차이는 오류가 아니다.
  대신 **그림파일(images/)이 준비됐는지**를 본다 — 렌더가 실제로 쓰는 것이 그것이다.
"""
from __future__ import annotations

import json
import os
import re

from services.book import paths
from services.render import bundles

_SLIDE_RE = re.compile(
    r'<section[^>]*class="[^"]*\bslide\b[^"]*"[^>]*>(.*?)</section>', re.S | re.I)
_HEADING_RE = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _pptx_slides(bundle: str) -> int:
    """`source/pages.json` 의 장 수. 0 이면 이 번들은 강의덱을 쓰지 않는다."""
    p = paths.bundle_pages(bundle)
    if not os.path.isfile(p):
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            return int(json.load(f).get("slides") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _images_ready(bundle: str) -> bool:
    try:
        from services.deck import slideimg
        return slideimg.images_ready(bundle)
    except Exception:                                        # noqa: BLE001
        return False


def _deck_headings(deck_path: str) -> list[str]:
    """각 .slide 의 첫 제목. 씬과 나란히 놓고 눈으로 대조하기 위한 것."""
    try:
        with open(deck_path, encoding="utf-8", newline="") as f:
            html = f.read()
    except OSError:
        return []
    out = []
    for body in _SLIDE_RE.findall(html):
        m = _HEADING_RE.search(body)
        text = _TAG_RE.sub("", m.group(1)) if m else ""
        out.append(" ".join(text.split())[:70])
    if out:
        return out
    # <section> 이 아닌 태그를 쓴 deck 대비 — 개수만이라도 맞춘다.
    n = len(re.findall(r'class="[^"]*\bslide\b[^"]*"', html))
    return [""] * n


def run(bundle: str) -> dict:
    info = bundles.scan_one(bundle)
    messages: list[dict] = []

    if not info["has_script"]:
        messages.append({"level": "error",
                         "text": f"script JSON 이 없습니다: {paths.rel(paths.bundle_script(bundle))}"})
    if not info["has_deck"]:
        messages.append({"level": "error",
                         "text": f"deck.html 이 없습니다: {paths.rel(paths.bundle_deck(bundle))}"})

    scenes = []
    if info["has_script"]:
        try:
            with open(paths.bundle_script(bundle), encoding="utf-8") as f:
                doc = json.load(f)
            for s in doc.get("scenes") or []:
                scenes.append({
                    "scene": s.get("scene"),
                    "kind": s.get("kind"),
                    "capture": bool(s.get("capture")),
                    "heading": (s.get("heading") or "")[:70],
                    "countdown_seconds": s.get("countdown_seconds"),
                    "gap_seconds": s.get("gap_seconds"),
                })
        except (OSError, json.JSONDecodeError) as e:
            messages.append({"level": "error", "text": f"script JSON 을 읽을 수 없습니다: {e}"})

    headings = _deck_headings(paths.bundle_deck(bundle)) if info["has_deck"] else []
    cap_scenes = [s for s in scenes if s["capture"]]

    n_pages = _pptx_slides(bundle)
    if n_pages:
        # ── 강의덱 경로 ────────────────────────────────────────────────────
        delta = n_pages - len(cap_scenes)
        if delta != 0:
            messages.append({
                "level": "error",
                "text": (f"[error] pptx 장({n_pages}) ≠ 캡처 씬({len(cap_scenes)}) — "
                         "1:1 이 깨졌습니다. 「슬라이드」 화면에서 ②를 다시 돌리세요."),
            })
        if not _images_ready(bundle):
            messages.append({
                "level": "error",
                "text": ("[error] 그림파일이 없거나 지금 pptx 에서 나온 것이 아닙니다 — "
                         "「슬라이드」 화면의 ④ [그림파일 뽑기] 를 먼저 누르세요. "
                         "deck.html 캡처로는 장 수가 맞지 않습니다."),
            })
    else:
        delta = len(headings) - len(cap_scenes)
        if scenes and headings and delta != 0:
            messages.append({
                "level": "error",
                "text": (f"[error] deck 슬라이드({len(headings)}) ≠ 캡처 씬({len(cap_scenes)}) — "
                         "슬라이드/씬 1:1 이 깨졌습니다. "
                         "도구 #2 로 deck.html 을 다시 만들어야 합니다."),
            })

    # 나란히 정렬 — 어디서 어긋나는지 눈으로 찾을 수 있게
    rows = []
    for i in range(max(len(headings), len(cap_scenes))):
        h = headings[i] if i < len(headings) else None
        s = cap_scenes[i] if i < len(cap_scenes) else None
        rows.append({
            "i": i,
            "deck": h,
            "scene": s["heading"] if s else None,
            "scene_no": s["scene"] if s else None,
            "kind": s["kind"] if s else None,
            "ok": h is not None and s is not None,
        })

    if info["status"] == "stale":
        messages.append({"level": "warn", "text": info["reason"]})
    if not info["has_lesson"]:
        messages.append({"level": "warn",
                         "text": "lesson JSON 이 없습니다 — 문항 편집이 이 번들에 반영되지 않습니다."})

    ok = not any(m["level"] == "error" for m in messages)
    return {
        "bundle": bundle,
        "ok": ok,
        "pptx_slides": n_pages,
        "slides_src": "pages.json" if n_pages else "deck.html",
        "images_ready": _images_ready(bundle) if n_pages else None,
        "deck_slides": len(headings),
        "capture_scenes": len(cap_scenes),
        "scene_total": len(scenes),
        "delta": delta,
        "rows": rows,
        "scenes": scenes,
        "messages": messages,
        "info": info,
    }
