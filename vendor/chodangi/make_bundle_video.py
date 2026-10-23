"""번들 렌더 드라이버 (파이프라인 05) — deck.html 슬라이드 기반 '일반 영상'.

exambook-forge(#2)가 만든 `05/<회차>/` 번들을 입력으로:
  1) source/deck.html 을 headless Chromium 으로 캡처 → images/slide_%02d.png (밝은 슬라이드)
  2) 카운트다운(생각할 시간 54321)·간격 씬은 밝은 Pillow 프레임/클립으로 생성
  3) Supertonic3 로컬 TTS 로 음성/자막 (자막·음성 최종 OK 지점)
  4) mp4maker(ffmpeg) 합성 → draft/<회차>.static.mp4 + <회차>.ko.vtt
  5) review.json / slides.json / <회차>.timing.json 갱신

기존 make_video.py(Pillow, lesson JSON 직접 렌더)는 그대로 두고, 이 드라이버는
deck.html 기반 경로를 추가한다. 렌더 엔진(#3의 slides 캡처·synth·mp4maker)은 재사용.

사용:
  python make_bundle_video.py --book D:/00work/ocr-output-260723 --round m01
  python make_bundle_video.py --book ... --round m01 --no-audio   # 슬라이드만(합성/음성 생략)
  python make_bundle_video.py --book ...                          # 05/ 아래 모든 회차

전제: #2에서 `python scripts/bundle.py --book <book> --round m01` 로 05 번들이 만들어져 있어야 함.
의존성: playwright(+chromium)  ·  기존 requirements-render.txt(onnxruntime/Pillow/pysrt/lxml/…).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("VOICEWRIGHT_VOICE_MAP", str(ROOT / "config" / "voice_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_PRONUNCIATION_MAP", str(ROOT / "config" / "pronunciation_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_ASSETS_DIR", str(ROOT / "assets"))
os.environ.setdefault("VOICEWRIGHT_WORKSPACE", os.environ.get("MF_OUTPUT_DIR") or str(ROOT / "munje"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ★ 원본은 `from app import bundles` 였다. xam-local 의 루트에 `app.py`(FastAPI 앱)가
#   있어서 그 이름을 쓰면 어느 쪽이 잡힐지 sys.path 순서에 달린다 — 조용히 엉뚱한
#   모듈을 import 하는 사고가 난다. 그래서 이 패키지만 `chodangi_app` 으로 옮겼다.
from chodangi_app import bundles               # noqa: E402
from slides import animate, deck_capture       # noqa: E402

CPS = 6.5
MIN_SECONDS = 4

# ★ 씬 경계 crossfade — 자막·타이밍·합성이 **같은 값**을 써야 하는 단 하나의 상수.
#
#   mp4maker 는 씬을 xfade/acrossfade 로 이 초만큼 겹쳐서 잇는다. 그래서 완성
#   영상에서 scene N 이 시작하는 시각은 `합 - N*CROSSFADE_SEC` 이다. 예전에는
#   합성에만 이 값이 있고 자막·review.json 은 몰라서 자막이 앞섰다. 값이 두
#   군데로 갈리지 않게 여기서 한 번 정해 내려보낸다.
#     → chodangi_app.synth.synthesize(crossfade=...)   통합 SRT / .ko.vtt
#     → python -m mp4maker --crossfade ...             실제 합성
#     → _finalize_bundle()                             review.json 의 startSec
CROSSFADE_SEC = 0.6


def _secs(text: str) -> int:
    return max(MIN_SECONDS, round(len((text or "").strip()) / CPS))


def _chapter_of(round_code: str) -> int:
    digits = re.sub(r"\D", "", round_code) or "1"
    return int(digits)


def _build_records(series: dict, cid: str) -> list[dict]:
    """_series 씬 → #3 스크립트 씬 레코드(1-based idx, 파일명, 낭독/무음)."""
    recs: list[dict] = []
    for s in series.get("scenes", []):
        si = int(s.get("scene", len(recs)))
        idx = si + 1
        kind = s.get("kind", "content")
        capture = bool(s.get("capture"))
        narration = (s.get("narration_text") or s.get("narration") or "").strip()
        # ★ 자막은 **원문**이다. `narration_text` 는 TTS 입력이라 숫자가 소리로 바뀌어
        #   있고(「이천칠 년」) 사람이 발음만 고쳐 놓기도 한다. 그걸 그대로 자막에
        #   쓰면 화면에 「이천칠 년 삼 월」이 뜬다. voicewright 는 원래 두 트랙을
        #   받는다(`schemas.ScriptScene.srt_text` · `batch.py` 의 `srt_text or
        #   narration_text`) — 여기서 나르지 않아 쓰이지 못하고 있었다.
        srt = (s.get("srt_text") or s.get("narration") or "").strip()
        rec = {
            "si": si, "idx": idx, "kind": kind, "capture": capture,
            "number": s.get("number"), "heading": s.get("heading") or "",
            "srt_text": srt,
            "image_filename": f"{cid}_{idx:02d}_{kind}.png",
            "video_filename": f"{cid}_{idx:02d}.mp4",
        }
        if kind in ("countdown", "gap"):
            rec["silent"] = True
            rec["seconds"] = int(s.get("countdown_seconds") or s.get("gap_seconds") or
                                 (5 if kind == "countdown" else 2))
            rec["narration_text"] = ""
        elif not narration and s.get("hold_seconds"):
            # ★ xam-local: 낭독을 한 장에 모은 문항의 **나머지 장**이다.
            #   `hold_seconds` 만큼 그 슬라이드를 보여 주고 소리는 내지 않는다.
            #   이 가지가 없으면 아래 폴백이 `"…"` 를 읽으려 하고, 장은
            #   실제 문자 길이만큼만 머무러 한 눈에 지나간다.
            rec["silent"] = True
            rec["seconds"] = max(1, int(round(float(s["hold_seconds"]))))
            rec["narration_text"] = ""
        else:
            rec["narration_text"] = narration or rec["heading"] or "…"
            rec["narration_seconds"] = _secs(rec["narration_text"])
        recs.append(rec)
    return recs


def _scratch_script(series: dict, recs: list[dict], chap: int) -> dict:
    scenes = []
    for r in recs:
        sc = {
            "scene": r["idx"],
            "title": r["heading"] or f"씬 {r['idx']}",
            "image_filename": r["image_filename"],
            "video_filename": r["video_filename"],
            "narration_text": r["narration_text"],
        }
        # 발음과 자막이 다를 때만 넘긴다 — 같으면 배치가 알아서 폴백한다
        if r.get("srt_text") and r["srt_text"] != r["narration_text"]:
            sc["srt_text"] = r["srt_text"]
        if r.get("silent"):
            sc["silent"] = True
            sc["narration_seconds"] = int(r["seconds"])
        else:
            sc["narration_seconds"] = int(r["narration_seconds"])
        scenes.append(sc)
    return {
        "version": "1.0", "kind": "lesson", "chapter": chap,
        "title": series.get("round") or "", "subject": series.get("subject") or "",
        "theme": series.get("theme") or "", "round": series.get("round") or "",
        "voice": series.get("voice") or "F2", "speed": series.get("speed", 1.05),
        "ai_reading": False, "aspect_ratio": "16:9", "scenes": scenes,
    }


def _srt_to_vtt(srt_text: str) -> str:
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt_text)
    return "WEBVTT\n\n" + body.strip() + "\n"


def _parse_srt_cues(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for m in re.finditer(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            path.read_text(encoding="utf-8")):
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        out.append({"start": round(start, 3), "end": round(end, 3)})
    return out


def _wav_dur(path: Path) -> float:
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return round(info.frames / float(info.samplerate), 3)
    except Exception:
        return 0.0


# deck.html 의 `.slide` 를 브라우저 없이 세기 위한 패턴.
# capture_deck() 의 page.query_selector_all(".slide") 와 같은 수를 노린다.
# (class 목록 중간에 있어도, 작은따옴표여도 매치.)
_SLIDE_TAG = re.compile(
    r"""class\s*=\s*(?P<q>["'])(?:[^"']*\s)?slide(?:\s[^"']*)?(?P=q)""", re.I)


def _count_deck_slides(deck: Path) -> int:
    """deck.html 의 .slide 개수. 파싱 실패/오류면 0(호출부에서 '검증 생략')."""
    try:
        return len(_SLIDE_TAG.findall(deck.read_text(encoding="utf-8", errors="ignore")))
    except OSError:
        return 0


def _count_pages_manifest(b05: Path) -> int:
    """source/pages.json 의 장 수. **강의덱(pptx)을 쓰면 이쪽이 진실이다.**

    ★ 왜 필요한가 (xam-local 이 고친 곳). 슬라이드가 pptx 에서 나오면 장 나눔이
      deck.html 과 다르다 — 변환기가 원본의 과분할을 되붙여 다시 쪼개기 때문이다
      (SQLD 01회: 145장 → 112장). 그 상태에서 deck.html 을 세면 정상인데도
      1:1 이 깨졌다고 멈춘다. pages.json 이 있으면 그것을 본다.
      없으면 지금까지처럼 deck.html 을 센다(옛 번들이 그대로 돈다).
    """
    p = b05 / "source" / "pages.json"
    if not p.is_file():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("slides") or 0)
    except (OSError, ValueError):
        return 0


def _reuse_capture_images(b05: Path, scratch: Path, cap_recs: list[dict]) -> int:
    """05/<회차>/images/slide_NN.png(0-based si) → scratch/images/<image_filename>.

    캡처 씬이 하나라도 빠져 있으면 **아무것도 복사하지 않고 0** 을 돌려준다
    (부분 복사는 이미지↔음성 정렬을 조용히 깨뜨리므로 금지). 0 = 캡처로 폴백.
    """
    src_dir = b05 / "images"
    if not src_dir.is_dir():
        print(f"[warn] --reuse-images: images 폴더가 없습니다: {src_dir}")
        return 0
    plan: list[tuple[Path, Path]] = []
    missing: list[str] = []
    for r in cap_recs:
        src = src_dir / f"slide_{r['si']:02d}.png"
        if src.exists():
            plan.append((src, scratch / "images" / r["image_filename"]))
        else:
            missing.append(src.name)
    if missing:
        head = ", ".join(missing[:6])
        more = f" 외 {len(missing) - 6}장" if len(missing) > 6 else ""
        print(f"[warn] --reuse-images: 없는 슬라이드 {len(missing)}/{len(cap_recs)}장 "
              f"({head}{more}) @ {src_dir}")
        return 0
    (scratch / "images").mkdir(parents=True, exist_ok=True)
    for src, dst in plan:
        shutil.copy2(src, dst)
    return len(plan)


def _render_jobs() -> int:
    """장면 인코딩을 몇 개까지 동시에. 환경변수 `XAM_RENDER_JOBS` 로 덮을 수 있다."""
    env = os.environ.get("XAM_RENDER_JOBS", "").strip()
    if env.isdigit() and int(env) > 0:
        return int(env)
    return max(1, min(8, (os.cpu_count() or 4) - 1))


def build(book: Path, round_code: str, do_audio: bool, keep_scratch: bool,
          reuse_images: bool = False) -> Path | None:
    b05 = book / "05" / round_code
    series_path = b05 / "script" / f"{round_code}_script.json"
    deck = b05 / "source" / "deck.html"
    review_path = b05 / "review.json"
    if not series_path.exists() or not deck.exists():
        raise SystemExit(
            f"[error] 05 번들이 없습니다: {b05}\n"
            f"        먼저 #2에서: python scripts/bundle.py --book \"{book}\" --round {round_code}")

    series = json.loads(series_path.read_text(encoding="utf-8"))
    chap = _chapter_of(round_code)
    cid = f"ch{chap:02d}"
    # ★ 스크래치를 먼저 비운다. create_bundle 은 exist_ok=True 라 예전 내용이 남는다.
    #
    #   보통은 이 스크립트가 끝나면서 rmtree 하지만, **취소하거나 중간에 죽으면
    #   남는다.** 그 상태로 다시 돌리면 지난 실행의 wav/srt/png 가 섞인다. 특히
    #   씬 수가 줄어든 경우 고아 wav 가 남아 자막 시간축이 그만큼 늘어난다 —
    #   rebuild_chapter_srt 가 audio/*.wav 를 훑기 때문이다.
    #   사람이 '이전 것을 지워야 하나' 를 고민하지 않아도 되게 코드가 보장한다.
    scratch = bundles.bundle_path(cid)
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch = bundles.create_bundle(cid)
    (scratch / "clips").mkdir(parents=True, exist_ok=True)
    print(f"[make] round={round_code} scratch={scratch} (비우고 시작)", flush=True)

    recs = _build_records(series, cid)
    n_cap = sum(1 for r in recs if r["capture"])

    # 1) 캡처 씬 이미지 — 05/images 재사용(--reuse-images) 또는 deck.html 캡처
    cap_recs = [r for r in recs if r["capture"]]
    cap_files = [r["image_filename"] for r in cap_recs]
    reused = _reuse_capture_images(b05, scratch, cap_recs) if reuse_images else 0
    if reuse_images and not reused:
        print("[warn] --reuse-images: 재사용할 수 없어 deck 캡처로 폴백합니다 "
              "(이 경로는 playwright+chromium 이 필요합니다).")

    if reused:
        # 캡처를 건너뛰면 deck_slides != n_cap 검증이 사라진다.
        # 브라우저 없이 같은 안전장치를 걸려고 deck.html 의 .slide 를 정적으로 센다.
        n_pages = _count_pages_manifest(b05)
        deck_slides = n_pages or _count_deck_slides(deck)
        src = "pages.json" if n_pages else "deck .slide"
        print(f"[make] 이미지 재사용: {reused}/{n_cap}  "
              f"({src}={deck_slides or '?'}, 캡처 생략)")
        if reused != n_cap or (deck_slides and deck_slides != n_cap):
            raise SystemExit(
                f"[error] 재사용 이미지({reused})·{src}({deck_slides}) ≠ 캡처 씬({n_cap})"
                f" — 슬라이드/씬 1:1 이 깨졌습니다.\n"
                f"        이대로 만들면 이미지와 음성이 어긋난 영상이 나옵니다.\n"
                f"        images: {b05 / 'images'}\n"
                f"        deck  : {deck}\n"
                f"        script: {series_path}\n"
                f"        --reuse-images 없이 다시 렌더(캡처)하거나, #2 에서 05 번들을 재생성하세요.")
        if not deck_slides:
            print("[warn] pages.json 도 deck.html 도 세지 못해 슬라이드/씬 정렬 "
                  "검증을 생략했습니다.")
    else:
        # Chromium 을 띄우고 슬라이드를 찍는 동안 1~2분 조용하다. 시작을 알려 둔다.
        print(f"[make] deck 캡처 시작 — 슬라이드 {n_cap}장 (Chromium)", flush=True)
        saved, deck_slides, overflow = deck_capture.capture_deck(deck, scratch / "images", cap_files)
        print(f"[make] deck 캡처: {len(saved)}/{n_cap}  (deck .slide={deck_slides})")
        # ★ pages.json 이 있으면 이 번들은 **강의덱(pptx)** 을 쓰는 번들이다. deck.html
        #   캡처로는 절대 수가 맞지 않는다(변환기가 다시 쪼갠다). 캡처를 탓하지 말고
        #   무엇을 눌러야 하는지 말한다 — xam-local 이 더한 안내다.
        if _count_pages_manifest(b05) and deck_slides != n_cap:
            raise SystemExit(
                f"[error] 이 번들은 강의덱(pptx)을 씁니다 — deck.html 캡처로는 맞지 "
                f"않습니다(캡처 {deck_slides} != 씬 {n_cap}).\n"
                f"        앱의 「슬라이드」 화면에서 4단계 [그림파일 뽑기] 를 먼저 "
                f"누르세요.\n"
                f"        그러면 05/{round_code}/images/ 가 채워지고 렌더가 그것을 "
                f"씁니다.\n"
                f"        pptx : {b05}")
        if deck_slides != n_cap:
            # 어긋나면 캡처가 앞에서부터 잘려 이미지↔음성 인덱스가 통째로 밀린다 → 중단.
            raise SystemExit(
                f"[error] deck 슬라이드({deck_slides}) ≠ 캡처 씬({n_cap}) — 슬라이드/씬 1:1 이 깨졌습니다.\n"
                f"        이대로 만들면 이미지와 음성이 어긋난 영상이 나옵니다.\n"
                f"        deck : {deck}\n"
                f"        script: {series_path}\n"
                f"        #2 에서 deck.html 과 script.json 을 같은 슬라이드 수로 다시 생성하세요\n"
                f"        (페이지 분할로 슬라이드가 늘면 씬·narration_text 도 같이 늘어야 합니다).")
        if overflow:
            worst = ", ".join(f"{i+1}번째 +{px}px" for i, px in overflow[:8])
            more = f" 외 {len(overflow)-8}장" if len(overflow) > 8 else ""
            print(f"[warn] 내용이 슬라이드(1080px)를 넘어 잘린 슬라이드 {len(overflow)}장: {worst}{more}")
            print("       #2 build-deck 의 페이지 분할이 필요합니다(보기 4개는 반드시 전부 보여야 함).")

    # 2) 카운트다운/간격 프레임·클립 (밝게)
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    last_problem_img: dict = {}
    for r in recs:
        if r["capture"] and r["kind"] == "problem":
            last_problem_img[r.get("number")] = scratch / "images" / r["image_filename"]
    for r in recs:
        img_path = scratch / "images" / r["image_filename"]
        if r["kind"] == "countdown":
            base = last_problem_img.get(r.get("number"))
            base = base if (base and base.exists()) else None
            if base is None:
                deck_capture.solid_frame().save(img_path)
                frames = deck_capture.countdown_frames(img_path, r["seconds"])
            else:
                frames = deck_capture.countdown_frames(base, r["seconds"])
            frames[0].save(img_path)
            if ffmpeg_ok:
                try:
                    animate.render_countdown_clip(frames, scratch / "clips" / r["video_filename"])
                except Exception as exc:
                    print(f"[warn] 카운트다운 클립 실패 씬{r['idx']}: {exc}")
        elif r["kind"] == "gap":
            deck_capture.solid_frame().save(img_path)

    # 3) 스크래치 대본 저장
    (scratch / "script").mkdir(parents=True, exist_ok=True)
    (scratch / "script" / f"{cid}_script.json").write_text(
        json.dumps(_scratch_script(series, recs, chap), ensure_ascii=False, indent=2),
        encoding="utf-8")

    if not do_audio:
        print("[make] --no-audio: 음성/합성 생략 (슬라이드만). 05 이미지 복사 후 종료.")
        _copy_images_only(scratch, b05, recs, cid)
        return None

    # 4) 음성/자막 (Supertonic3)
    print("[make] 음성/자막 (Supertonic3) …", flush=True)
    # 늦은 import(env 설정 후, 모델 로드 무거움). app → chodangi_app 로 옮겼다.
    from chodangi_app.synth import synthesize

    # ★ 씬마다 한 줄 찍는다. 이 구간이 번들당 몇 분인데 예전에는 아무것도 안 뱉어서
    #   지켜보는 쪽에서 멈춘 것처럼 보였다. XAM LOCAL 이 이 줄로 진행률을 센다.
    #   flush 하지 않으면 파이프에 갇혀 끝나야 한꺼번에 나온다.
    def _tts_progress(done: int, total: int, scene: int | None = None) -> None:
        tag = f" (씬 {scene})" if scene is not None else ""
        print(f"[tts] 음성 {done}/{total}{tag}", flush=True)

    asyncio.run(synthesize(scratch, voice_override=series.get("voice"),
                           speed=series.get("speed"), crossfade=CROSSFADE_SEC,
                           on_progress=_tts_progress))

    # 5) mp4maker 합성 (레슨: Ken Burns off, 자막 하드번인 없음)
    print("[make] MP4 합성 (mp4maker) …")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    rc = subprocess.run([sys.executable, "-m", "mp4maker", str(scratch),
                         # ★ 명시한다. mp4maker 기본값도 0.6 이지만, 자막을 그 값에
                         #   맞춰 만들어 놓고 합성만 딴 값을 쓰면 조용히 다시 어긋난다.
                         "--crossfade", str(CROSSFADE_SEC),
                         "--kenburns", "off", "--no-subs", "--no-soft-sub",
                         # ★ 명시한다. mp4maker 기본값은 `CPU-1` 이라 이 PC 에서는 31개가
                         #   동시에 돌았고, 메모리를 다 써서 x264 가 죽었다(2026-08-25).
                         #   장면 하나는 몇 초짜리라 31병렬로 얻는 것도 없다 — 그보다
                         #   렌더 중에도 PC 를 쓸 수 있는 편이 낫다.
                         "--jobs", str(_render_jobs())],
                        cwd=str(ROOT), env=env).returncode
    if rc != 0:
        raise SystemExit(f"[error] mp4maker 실패 (종료코드 {rc})")

    # 6) 05 번들로 산출물 이관 + review.json/slides.json/timing.json 갱신
    dest = _finalize_bundle(scratch, b05, recs, cid, round_code, review_path)
    if not keep_scratch:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"[done] {dest}")
    return dest


def _copy_images_only(scratch: Path, b05: Path, recs: list[dict], cid: str) -> None:
    (b05 / "images").mkdir(parents=True, exist_ok=True)
    for r in recs:
        srcimg = scratch / "images" / r["image_filename"]
        if srcimg.exists():
            shutil.copy2(srcimg, b05 / "images" / f"slide_{r['si']:02d}.png")


def _finalize_bundle(scratch: Path, b05: Path, recs: list[dict], cid: str,
                     round_code: str, review_path: Path) -> Path:
    for sub in ("images", "audio", "subtitles", "draft"):
        (b05 / sub).mkdir(parents=True, exist_ok=True)

    # 이미지·오디오 → pressplay 파일명(0-base)
    durations: dict[int, float] = {}
    cues_map: dict[int, list] = {}
    for r in recs:
        si, idx = r["si"], r["idx"]
        srcimg = scratch / "images" / r["image_filename"]
        if srcimg.exists():
            shutil.copy2(srcimg, b05 / "images" / f"slide_{si:02d}.png")
        srcaud = scratch / "audio" / f"{cid}_{idx:02d}_narration.wav"
        if srcaud.exists():
            shutil.copy2(srcaud, b05 / "audio" / f"scene_{si:02d}.wav")
            durations[si] = _wav_dur(srcaud)
        cues_map[si] = _parse_srt_cues(scratch / "subtitles" / f"{cid}_{idx:02d}_narration.srt")

    # 통합 자막 → subtitles/subtitles.srt + draft/<round>.ko.vtt
    combined = scratch / "subtitles" / f"{cid}.srt"
    if combined.exists():
        srt_text = combined.read_text(encoding="utf-8")
        (b05 / "subtitles" / "subtitles.srt").write_text(srt_text, encoding="utf-8")
        (b05 / "draft" / f"{round_code}.ko.vtt").write_text(_srt_to_vtt(srt_text), encoding="utf-8")

    # 최종 영상 → draft/<round>.static.mp4
    final_src = scratch / "draft" / f"{cid}_final.mp4"
    dest = b05 / "draft" / f"{round_code}.static.mp4"
    if final_src.exists():
        shutil.copy2(final_src, dest)

    # 타이밍 누적
    # ★ startSec 은 **완성된 mp4 기준**이다. 오디오 길이 합이 아니다.
    #   mp4maker 가 씬 경계마다 CROSSFADE_SEC 만큼 겹치므로 scene N 은
    #   `합 - N*CROSSFADE_SEC` 에 시작한다(mp4maker/timeline.py 와 같은 식).
    #   예전에는 합을 그대로 넣어서, 이 값으로 시크하면 씬마다 0.6초씩 빗나갔다.
    cumulative = 0.0
    timing = []
    for n, r in enumerate(recs):
        si = r["si"]
        d = durations.get(si, 0.0)
        start = max(0.0, cumulative - n * CROSSFADE_SEC)
        timing.append({"scene": si, "kind": r["kind"], "durSec": d,
                       "startSec": round(start, 3)})
        cumulative += d
    # 완성 영상의 총 길이도 겹친 만큼 짧다.
    total = round(max(0.0, cumulative - max(0, len(recs) - 1) * CROSSFADE_SEC), 3)

    # review.json 갱신(있으면 로드, 없으면 최소 생성)
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {"slides": []}
    review["totalSeconds"] = total
    # ★ 이 번들의 startSec·자막이 어느 시간축인지 밝힌다.
    #   "video"  = crossfade 보정 완료(이 수정 이후에 만든 것). 그대로 시크하면 맞는다.
    #   키 없음  = 예전 번들. 오디오 길이 합이라 읽는 쪽이 n*crossfade 를 빼야 한다.
    #   이게 없으면 보정한 번들을 또 보정해서 반대로 틀어진다.
    review["timebase"] = "video"
    review["crossfadeSec"] = CROSSFADE_SEC
    by_index = {sl.get("index"): sl for sl in review.get("slides", [])}
    for t in timing:
        sl = by_index.get(t["scene"])
        if sl is not None:
            sl["durSec"] = t["durSec"]
            sl["startSec"] = t["startSec"]
            sl["cues"] = cues_map.get(t["scene"], [])
    review["staticVideo"] = f"{round_code}.static.mp4" if dest.exists() else None
    review["staticSubtitles"] = f"{round_code}.ko.vtt" if (b05 / "draft" / f"{round_code}.ko.vtt").exists() else None
    review.setdefault("motionVideo", None)
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    # slides.json (캡처 매니페스트) + timing.json
    slides_manifest = {
        "version": "1.0", "round": round_code,
        "slides": [{"index": r["si"], "image": f"slide_{r['si']:02d}.png",
                    "heading": r["heading"], "capture": r["capture"], "kind": r["kind"]}
                   for r in recs],
    }
    (b05 / "source" / "slides.json").write_text(
        json.dumps(slides_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (b05 / "source" / f"{round_code}.timing.json").write_text(
        json.dumps({"round": round_code, "totalSeconds": total, "scenes": timing},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def _resolve_book_round(path: Path) -> tuple[Path, str]:
    """드래그드롭된 경로 → (book, round_code).

    허용: 번들 폴더 `<book>/05/<round>` 또는 그 안의 `script/<round>_script.json` / 아무 파일.
    """
    p = path.resolve()
    # 파일이면 번들 폴더까지 거슬러 올라간다(…/05/<round>/script/x.json → …/05/<round>).
    if p.is_file():
        p = p.parent
        if p.name.lower() == "script":
            p = p.parent
    bundle = p                      # …/<book>/05/<round>
    round_code = bundle.name
    book = bundle.parent.parent     # …/<book>
    return book, round_code


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="make_bundle_video.py",
                                description="05 번들(deck.html) → 일반영상 static.mp4 + review.json")
    p.add_argument("paths", nargs="*",
                   help="드래그드롭된 번들 폴더/스크립트 json 경로(들). 주면 --book/--round 무시.")
    p.add_argument("--book", default="D:/00work/ocr-output-260723", help="책 루트")
    p.add_argument("--round", default="", help="회차코드 (예: m01-1). 생략 시 05/ 아래 모든 회차")
    p.add_argument("--no-audio", action="store_true", help="음성/합성 생략(슬라이드 캡처만)")
    p.add_argument("--keep-scratch", action="store_true", help="munje/ 스크래치 번들 유지(디버그)")
    p.add_argument("--reuse-images", action="store_true",
                   help="deck 캡처 대신 05/<회차>/images/slide_NN.png 재사용 "
                        "(playwright/chromium 불필요). 한 장이라도 없으면 캡처로 자동 폴백")
    p.add_argument("--force", action="store_true",
                   help="전체 스캔 시 이미 만들어진 번들도 다시 렌더(기본: 미완성만)")
    args = p.parse_args(argv)

    # 드래그드롭 경로가 있으면 그것들만 (순차) 렌더 — 명시 요청이므로 항상 렌더
    if args.paths:
        for raw in args.paths:
            book, rc = _resolve_book_round(Path(raw))
            print(f"[drop] {raw} → book={book} round={rc}")
            build(book, rc, not args.no_audio, args.keep_scratch, args.reuse_images)
        return 0

    book = Path(args.book).resolve()
    if args.round:
        # 회차 명시 = 항상 렌더
        build(book, args.round, not args.no_audio, args.keep_scratch, args.reuse_images)
        return 0

    # 전체 스캔: 05/ 아래 모든 번들. 기본은 '미완성만'(static.mp4 없는 것), --force 면 전부.
    d05 = book / "05"
    rounds = sorted(x.name for x in d05.iterdir() if x.is_dir()) if d05.is_dir() else []
    if not rounds:
        raise SystemExit(f"[error] 처리할 회차가 없습니다: {book}/05 (--round 로 지정)")

    made, skipped = 0, []
    for rc in rounds:
        done = (book / "05" / rc / "draft" / f"{rc}.static.mp4").exists()
        if done and not args.force and not args.no_audio:
            skipped.append(rc)
            continue
        build(book, rc, not args.no_audio, args.keep_scratch, args.reuse_images)
        made += 1
    if skipped:
        print(f"[skip] 이미 완료된 {len(skipped)}개 건너뜀: {', '.join(skipped)}")
    print(f"[all] 렌더 {made}개 / 전체 {len(rounds)}개 (미완성만; 전체 재렌더는 --force)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
