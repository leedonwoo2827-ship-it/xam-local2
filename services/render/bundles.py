"""05/ 번들 24개의 상태 스캔.

상태 판정 순서(먼저 걸리는 것이 이긴다):
  broken  script/deck 이 없거나 슬라이드↔씬 1:1 이 깨짐 → 렌더 자체가 불가
  missing mp4 가 없다
  stale   mp4 가 deck.html · script.json · lesson.json 보다 낡았다
  done    준비 완료

stale 에 lesson.json 을 넣은 이유: 문항을 고치면 lesson 이 갱신되고, 그러면 이
번들의 deck 과 영상이 낡는다. 그 사실이 이 표에서 바로 보여야 한다.
"""
from __future__ import annotations

import json
import os
import re

from core.constants import ENGINE_DIR
from services.book import paths
from services.render import speech

# 옛 번들(review.json 에 timebase 가 없는 것)을 보정할 때 쓰는 기본값.
# 지금 chodangi 는 make_bundle_video.CROSSFADE_SEC 를 review.json 의 crossfadeSec 에
# 같이 적으므로, 새 번들은 그 값을 읽어 쓴다. 이 상수는 옛 번들 폴백용이다.
CROSSFADE_SEC = 0.6

# chodangi 의 bundles.create_bundle 이 쓰는 챕터 id 규칙을 그대로 재현한다.
#   m01-1 → 숫자만 뽑아 "011" → 11 → munje/ch11
# 실측 24번들은 ch11~ch38 로 충돌하지 않지만, 규칙 자체가 안전하지 않다
# (m11-1 과 m01-11 이 둘 다 ch111 이 된다). 그래서 렌더는 언제나 1개만 돌린다.
def chapter_id(bundle: str) -> str:
    digits = re.sub(r"\D", "", bundle or "")
    return f"ch{int(digits):02d}" if digits else "ch00"


def scratch_dir(bundle: str) -> str:
    return os.path.join(ENGINE_DIR, "munje", chapter_id(bundle))


def _count(dir_path: str, suffix: str) -> int:
    if not os.path.isdir(dir_path):
        return 0
    return sum(1 for f in os.listdir(dir_path) if f.endswith(suffix))


def _pages_slides(bundle: str) -> int:
    """`05/<번들>/source/pages.json` 의 장 수. 없으면 0(강의덱을 안 쓰는 번들)."""
    p = paths.bundle_pages(bundle)
    if not os.path.isfile(p):
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            return int(json.load(f).get("slides") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _deck_slides(deck_path: str) -> int:
    """deck.html 의 .slide 개수. chodangi 는 Playwright 로 세지만 우리는 정규식으로
    충분하다 — 목적이 '스폰 전에 1:1 이 깨졌는지' 만 보는 것이다."""
    try:
        with open(deck_path, encoding="utf-8", newline="") as f:
            html = f.read()
    except OSError:
        return -1
    return len(re.findall(r'class="[^"]*\bslide\b[^"]*"', html))


def _speech_edited(bundle: str) -> int:
    """사람이 자막·발음을 고친 씬의 수. 없으면 0."""
    try:
        from services.render import speech
        return len(speech.read_raw(bundle))
    except Exception:                                        # noqa: BLE001
        return 0


def _images_ready(bundle: str) -> bool:
    """`slideimg.images_ready` 를 그대로 쓴다 — 규칙을 여기에 베끼지 않는다."""
    try:
        from services.deck import slideimg
        return bool(slideimg.images_ready(bundle))
    except Exception:                                        # noqa: BLE001
        return False


def scan_one(bundle: str) -> dict:
    parsed = paths.parse_bundle(bundle)
    lo, hi = paths.bundle_range(bundle) or (0, 0)
    d = paths.bundle_dir(bundle)

    deck = paths.bundle_deck(bundle)
    script = paths.bundle_script(bundle)
    lesson = paths.bundle_lesson(bundle)
    mp4 = paths.bundle_mp4(bundle)
    vtt = paths.bundle_vtt(bundle)
    review = paths.bundle_review(bundle)

    has_deck = os.path.isfile(deck)
    has_script = os.path.isfile(script)

    scenes = capture = 0
    title = ""
    if has_script:
        try:
            with open(script, encoding="utf-8") as f:
                doc = json.load(f)
            sc = doc.get("scenes") or []
            scenes = len(sc)
            capture = sum(1 for s in sc if s.get("capture"))
            title = (sc[0].get("heading") if sc else "") or ""
        except (OSError, json.JSONDecodeError):
            pass

    # ★ **장 나눔의 진실이 어디인가.** 강의덱(pptx)을 쓰는 번들은 `source/pages.json`
    #   이 있고, 그 장 수가 씬의 근거다. deck.html 은 변환기의 입력·미리보기로만
    #   남으므로 장 수가 다르다(변환기가 과분할을 되붙여 다시 쪼갠다). 그것을 모르고
    #   deck.html 을 세면 멀쩡한 번들을 「1:1 깨짐」으로 표시한다.
    n_pages = _pages_slides(bundle)
    deck_slides = _deck_slides(deck) if has_deck else -1
    slide_src = "pages.json" if n_pages else "deck.html"
    ref_slides = n_pages or deck_slides
    ok_1to1 = bool(has_script) and ref_slides == capture and (has_deck or n_pages)

    total_seconds = None
    review_slides = None
    if os.path.isfile(review):
        try:
            with open(review, encoding="utf-8") as f:
                rv = json.load(f)
            total_seconds = rv.get("totalSeconds")
            review_slides = len(rv.get("slides") or [])
            title = rv.get("title") or title
        except (OSError, json.JSONDecodeError):
            pass

    mp4_bytes = paths.size(mp4)
    mp4_mtime = paths.mtime(mp4)
    # ★ 손수정(`<번들>_speech.json`)도 **입력이다.** 자막·발음을 고치면 script.json 은
    #   그대로라, 이것을 빼면 고쳐도 목록이 「완료」 로 남아 낡은 mp4 가 그대로 나간다
    #   (실측 2026-08-26 — 사람이 고치고도 다시 돌려야 하는 줄 알 방법이 없었다).
    speech_json = os.path.join(d, "script", f"{bundle}_speech.json")
    newest_input = max(paths.mtime(deck), paths.mtime(script), paths.mtime(lesson),
                       paths.mtime(speech_json))

    if not (has_deck and has_script):
        status, reason = "broken", "deck.html 또는 script JSON 이 없습니다."
    elif not ok_1to1:
        status, reason = "broken", (
            f"{slide_src} 슬라이드({ref_slides}) ≠ 캡처 씬({capture}) — "
            f"슬라이드/씬 1:1 이 깨졌습니다.")
    elif not mp4_bytes:
        status, reason = "missing", "아직 렌더하지 않았습니다."
    elif mp4_mtime < newest_input:
        status = "stale"
        reason = ("자막·발음을 고쳤습니다 — 다시 렌더해야 영상에 들어갑니다."
                  if paths.mtime(speech_json) > mp4_mtime
                  else "문항·deck 이 mp4 보다 새롭습니다 — 다시 렌더해야 합니다.")
    else:
        status, reason = "done", None

    return {
        "code": bundle,
        "round": paths.round_code(parsed[0]) if parsed else "",
        "round_no": parsed[0] if parsed else 0,
        "part": parsed[1] if parsed else 0,
        "chapter_id": chapter_id(bundle),
        "title": title,
        "questions": f"{lo}–{hi}번",
        "question_from": lo,
        "question_to": hi,
        "scenes": scenes,
        "capture_scenes": capture,
        "deck_slides": deck_slides,
        # ★ 1:1 판정에 실제로 쓴 수와 그 출처. 강의덱을 쓰는 번들은
        #   pages.json 이 진실이고 deck_slides 와 **일부러 다르다.**
        "slides_ref": ref_slides,
        "slides_src": slide_src,
        "ok_1to1": ok_1to1,
        "has_deck": has_deck,
        "has_script": has_script,
        "has_lesson": os.path.isfile(lesson),
        "mp4": {"exists": bool(mp4_bytes), "bytes": mp4_bytes,
                "mtime": mp4_mtime, "url": paths.book_url(mp4) if mp4_bytes else None},
        "vtt": {"exists": os.path.isfile(vtt), "bytes": paths.size(vtt),
                "url": paths.book_url(vtt) if os.path.isfile(vtt) else None},
        "review": {"exists": os.path.isfile(review), "total_seconds": total_seconds,
                   "slides": review_slides},
        "images": _count(paths.bundle_images_dir(bundle), ".png"),
        # ★ 렌더가 그 PNG 를 **그대로 쓰는가**(`--reuse-images`). 판정은 한 곳뿐이다 —
        #   runner 도 같은 함수를 부른다. 어긋나면 deck.html 캡처로 폴백하므로,
        #   화면이 그것을 말해 주지 않으면 「확정한 화면과 다른 영상」이 조용히 나간다.
        "images_ready": _images_ready(bundle),
        # 이 번들에서 사람이 자막·발음을 고친 씬 수 — 목록이 배지로 보여 준다
        "speech_edited": _speech_edited(bundle),
        "audio": _count(paths.bundle_audio_dir(bundle), ".wav"),
        "exists": os.path.isdir(d),
        "status": status,
        "reason": reason,
    }


def scan_all() -> list[dict]:
    return [scan_one(b) for b in paths.all_bundles()]


def scenes(bundle: str) -> dict:
    """씬별 상세 — 슬라이드 이미지 · 음성 · 자막 큐 · 낭독문.

    화면 바닥에서 씬을 눌러 슬라이드를 보고 음성을 듣고 자막을 고치는 데 쓴다.

    ★ 자막 시각 보정 — 번들마다 시간축이 다르다. review.json 의 timebase 로 가른다.

      "video"  chodangi 가 crossfade 를 반영해 쓴 값. **그대로 쓴다.**
      키 없음  옛 번들. startSec 이 durSec 단순 합이라 mp4 실제 위치는
               startSec - (씬순서 × crossfade) 다. 실측으로 24.2초 앞서 있었다.

      ★ 마커를 안 보고 무조건 빼면, 고쳐서 만든 번들을 또 빼서 반대로 틀어진다.
        옛 번들과 새 번들이 한 폴더에 섞여 있을 수 있으므로 번들 단위로 판단한다.
    """
    script = paths.bundle_script(bundle)
    review = paths.bundle_review(bundle)
    if not os.path.isfile(script):
        return {"bundle": bundle, "ok": False,
                "error": f"script JSON 이 없습니다: {paths.rel(script)}", "scenes": []}

    try:
        with open(script, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"bundle": bundle, "ok": False, "error": f"script JSON 읽기 실패: {e}",
                "scenes": []}

    rv = {}
    rvdoc: dict = {}
    if os.path.isfile(review):
        try:
            with open(review, encoding="utf-8") as f:
                rvdoc = json.load(f)
            rv = {int(s.get("index", -1)): s for s in (rvdoc.get("slides") or [])}
        except (OSError, json.JSONDecodeError):
            rvdoc = {}

    # 이 번들의 startSec 이 이미 mp4 기준인가.
    compensated = (rvdoc.get("timebase") == "video")
    xf = float(rvdoc.get("crossfadeSec") or CROSSFADE_SEC)

    # 사람이 발음을 고쳐 둔 씬 — 화면이 「손수정」 배지를 띄운다
    hand = speech.overrides(bundle)

    out = []
    for s in doc.get("scenes") or []:
        si = int(s.get("scene", len(out)))
        slide = rv.get(si, {})
        img = os.path.join(paths.bundle_images_dir(bundle), f"slide_{si:02d}.png")
        wav = os.path.join(paths.bundle_audio_dir(bundle), f"scene_{si:02d}.wav")
        start = slide.get("startSec")
        out.append({
            "scene": si,
            "kind": s.get("kind"),
            "capture": bool(s.get("capture")),
            "heading": s.get("heading") or "",
            # ★ **두 트랙이다.** 전에는 한 값으로 합쳐 내려서 화면이 자막과 발음을
            #   구별할 수 없었다(둘 다 같은 값이었으니 문제가 없어 보였다).
            #     narration  자막 — 화면에 뜨는 원문
            #     speech     발음 — TTS 가 읽는 글(숫자가 소리로 바뀌어 있고 손수정이 얹힌다)
            "narration": s.get("narration") or "",
            # 고치기 전의 자막 원문 — 화면이 저장할 때 `from` 으로 되돌려 보낸다
            "narration_src": s.get("narration_src") or s.get("narration") or "",
            "speech": s.get("narration_text") or s.get("narration") or "",
            "speech_edited": si in hand,
            "silent": s.get("kind") in ("countdown", "gap"),
            "countdown_seconds": s.get("countdown_seconds"),
            "gap_seconds": s.get("gap_seconds"),
            "dur_sec": slide.get("durSec"),
            "start_sec": start,
            # mp4 위에서 실제로 이 씬이 시작하는 시각. 이미 보정된 번들은 그대로 쓴다.
            "mp4_start_sec": (None if not isinstance(start, (int, float))
                              else round(start, 3) if compensated
                              else round(max(0.0, start - si * xf), 3)),
            "cues": slide.get("cues") or [],
            "image": {"exists": os.path.isfile(img),
                      "url": paths.book_url(img) if os.path.isfile(img) else None},
            "audio": {"exists": os.path.isfile(wav), "bytes": paths.size(wav),
                      "url": paths.book_url(wav) if os.path.isfile(wav) else None},
        })

    info = scan_one(bundle)
    return {
        "bundle": bundle,
        "ok": True,
        "voice": doc.get("voice"),
        "speed": doc.get("speed"),
        "title": doc.get("round") or info["title"],
        "count": len(out),
        "crossfade_sec": xf,
        # 보정된 번들은 드리프트가 없다. 옛 번들만 화면에 경고를 띄운다.
        "compensated": compensated,
        "drift_sec": 0.0 if compensated else round(max(0, len(out) - 1) * xf, 2),
        "scenes": out,
        "info": info,
        "subtitles": _subtitle_text(bundle),
        # 씬 재합성으로 wav 만 갱신된 씬 — mp4 가 그만큼 낡았다는 뜻이다
        "stale_scenes": speech.stale_scenes(bundle),
    }


def _subtitle_text(bundle: str) -> dict:
    p = paths.bundle_srt(bundle)
    vtt = paths.bundle_vtt(bundle)
    return {
        "srt_exists": os.path.isfile(p),
        "vtt_exists": os.path.isfile(vtt),
        "vtt_url": paths.book_url(vtt) if os.path.isfile(vtt) else None,
    }


def review_toc(bundle: str) -> list[dict]:
    """review.json → 미리보기 목차. 클릭하면 그 시각으로 시크한다."""
    path = paths.bundle_review(bundle)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            rv = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for s in rv.get("slides") or []:
        out.append({
            "index": s.get("index"),
            "heading": s.get("heading") or "",
            "start_sec": s.get("startSec"),
            "dur_sec": s.get("durSec"),
        })
    return out
