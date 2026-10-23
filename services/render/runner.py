"""#3 렌더 엔진 구동 — `vendor/chodangi/make_bundle_video.py` 를 서브프로세스로.

★ 엔진이 이 저장소 안에 있다 (2026-08-03). 예전에는 외부 폴더
  `D:\\00work\\chodangi-mp4-forge-main`(이 PC 에 없던 경로)를 가리켰다. 이제
  `vendor/chodangi/` 에 들어와 있고 자막 시간축 수정 4건도 그 소스에 영구 반영됐다
  — 패치 도구가 아니라 코드다.

★ 서브프로세스로 돌리는 것은 그대로 유지한다. in-process 로 부르면
  onnxruntime 모델(수백 MB)과 Chromium·ffmpeg 자식이 FastAPI 프로세스에 얹히고,
  취소가 사실상 불가능해진다. 격리·취소·메모리 회수가 다 공짜인 쪽을 고른다.
  엔진 폴더를 cwd 로 주므로 `from slides import …` 같은 절대 import 가 그대로 산다.

★ render.bat 은 쓰지 않는다. chcp·pause·드래그드롭 분기가 서브프로세스에서 방해되고,
  BOOK 경로가 그 안에 하드코딩되어 있다. 드라이버를 직접 부르며 --book 을 명시한다.

★ 렌더는 언제나 1개만 돌린다.
  - munje/chNN 스크래치가 exist_ok=True 로 만들어져서 같은 cid 두 프로세스가 서로의
    images/·clips/ 를 덮어쓴다. 실측 24번들은 ch11~ch38 로 충돌하지 않지만 규칙이
    안전하지 않다(m11-1 과 m01-11 이 둘 다 ch111).
  - 더 근본적으로 Chromium · Supertonic TTS · ffmpeg 가 자원을 다 쓴다.

진행률 정규식은 chodangi-mp4-forge-main/app/render.py:29-33 을 그대로 옮겼다.
"""
from __future__ import annotations

import os
import re
import subprocess
import threading

from core.constants import BASE_DIR, ENGINE_DIR
from services.book import paths
from services.jobs import registry
from services.render import bundles, precheck

# 동시 실행 방지 — 비차단 획득에 실패하면 409 를 낸다.
_RENDER_LOCK = threading.Lock()
_PROCS: dict[str, subprocess.Popen] = {}

_RE_PROGRESS = re.compile(r"\[scene\]\s+sc(\d+)\s+done.*progress=(\d+)/(\d+)")
# TTS 진행 — make_bundle_video 가 씬마다 찍는다. 번들당 몇 분인 구간이라 이게 없으면
# 화면이 멈춘 것처럼 보인다. mp4maker 의 [scene] 진행률보다 먼저 온다.
_RE_TTS = re.compile(r"\[tts\]\s+음성\s+(\d+)/(\d+)")
# 단계 이름 — 조용한 구간에도 "지금 뭐 하는 중" 을 보여주기 위해 잡에 기록한다.
_STAGES = (
    (re.compile(r"deck 캡처 시작"), "deck 캡처 (Chromium)"),
    (re.compile(r"deck 캡처:"), "카운트다운·간격 프레임"),
    (re.compile(r"음성/자막"), "음성·자막 합성 (TTS)"),
    (re.compile(r"\[tts\]"), "음성·자막 합성 (TTS)"),
    (re.compile(r"MP4 합성"), "MP4 합성 (ffmpeg)"),
    (re.compile(r"\[stage\]\s+(\S+)"), None),        # mp4maker 의 단계명을 그대로
)
_RE_DONE = re.compile(r"\[done\]\s+(.+)$")
_RE_TOTAL = re.compile(r"\[total\]\s+([\d.]+)s")
_RE_ERROR = re.compile(r"\[(?:error|ERROR)\]\s*(.*)$")
_RE_WARN = re.compile(r"\[warn\]\s*(.*)$")


def engine_dir() -> str:
    """내장한 렌더 엔진 폴더. 서브프로세스의 cwd 이자 sys.path 뿌리다."""
    return ENGINE_DIR


def driver_python() -> str:
    """엔진을 돌릴 파이썬 — **이 앱의 venv** 다.

    예전에는 chodangi 저장소의 `.venv` 를 썼다. 엔진이 안으로 들어왔으니 의존성도
    이 venv 하나로 합친다(requirements.txt 에 onnxruntime·playwright 등을 넣었다).
    """
    return os.path.join(BASE_DIR, "venv", "Scripts", "python.exe") \
        if os.name == "nt" else os.path.join(BASE_DIR, "venv", "bin", "python")


def driver_script() -> str:
    return os.path.join(ENGINE_DIR, "make_bundle_video.py")


def _which(name: str) -> str:
    import shutil as _sh
    return _sh.which(name) or ""


def env_info() -> dict:
    """실행 환경 점검 — 화면 상단 카드가 이걸 그린다.

    ★ 내장할 수 없는 것 둘을 여기서 확인한다. 바이너리라서 저장소에 넣을 수 없다.
      · ffmpeg          PATH 에 있어야 한다. 없으면 TTS 를 몇 분 돌린 뒤 마지막에 실패한다.
      · Chromium        playwright 가 내려받는다(`python -m playwright install chromium`).
      둘 중 하나라도 없으면 **시작 전에** 끊는다.
    """
    py = driver_python()
    drv = driver_script()
    assets = os.path.join(ENGINE_DIR, "assets")
    onnx = os.path.join(assets, "onnx")
    ffmpeg = _which("ffmpeg")
    try:
        import playwright  # noqa: F401
        pw_ok = True
    except ImportError:
        pw_ok = False
    return {
        "engine": ENGINE_DIR,
        "python": py,
        "python_ok": os.path.isfile(py),
        "driver": drv,
        "driver_ok": os.path.isfile(drv),
        # TTS 모델 — .gitignore 대상이라 clone 직후에는 없다.
        "assets_ok": os.path.isdir(onnx),
        "assets": assets,
        "ffmpeg": ffmpeg,
        "ffmpeg_ok": bool(ffmpeg),
        "playwright_ok": pw_ok,
        "book": paths.book_dir(),
        "concurrency": 1,
        "busy": registry.running("render") is not None,
    }


def _build_env() -> dict:
    """자식 프로세스 환경.

    PYTHONIOENCODING=utf-8 은 필수다 — chodangi 의 로그 전문이 한국어라서
    cp949 콘솔에서 UnicodeEncodeError 로 죽는다.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _reuse_images(bundle: str) -> bool:
    """이 번들의 `images/` 가 **지금 pptx 에서 나온 것**인가.

    ★ 맞으면 deck.html 캡처를 건너뛰고 그 PNG 를 그대로 쓴다 — 사람이 PowerPoint 로
      확정한 화면이 그대로 영상이 되는 자리다. 조금이라도 어긋나면 False 를 돌려
      캡처로 떨어진다(드라이버 쪽도 부분 재사용을 금지한다).
    """
    try:
        from services.deck import slideimg
        return slideimg.images_ready(bundle)
    except Exception:                                        # noqa: BLE001
        return False


def _args(bundle: str, *, no_audio: bool, keep_scratch: bool) -> list[str]:
    a = [driver_python(), "make_bundle_video.py",
         # ★ 항상 명시하고, 상수가 아니라 **지금 고른 폴더**를 넘긴다.
         #   상수를 넘기면 폴더를 바꿔도 옛 책을 렌더한다.
         "--book", paths.book_dir(),
         "--round", bundle]
    if _reuse_images(bundle):
        a.append("--reuse-images")
    if no_audio:
        a.append("--no-audio")
    if keep_scratch:
        # 실패 원인을 보려면 필요하다 — 기본은 rmtree 로 증거가 사라진다.
        a.append("--keep-scratch")
    return a


def start(codes: list[str], *, no_audio: bool = False, keep_scratch: bool = False,
          stop_on_error: bool = True) -> dict:
    """렌더 잡을 시작한다. 사전점검을 통과하지 못한 번들은 시작조차 하지 않는다."""
    env = env_info()
    if not env["python_ok"]:
        raise FileNotFoundError(
            f"chodangi 의 python 을 찾을 수 없습니다: {env['python']}\n"
            "chodangi-mp4-forge 폴더에서 setup.bat 을 먼저 실행하세요.")
    if not env["driver_ok"]:
        raise FileNotFoundError(f"make_bundle_video.py 를 찾을 수 없습니다: {env['driver']}")

    blocked = []
    for c in codes:
        pc = precheck.run(c)
        if not pc["ok"]:
            blocked.append({"bundle": c,
                            "messages": [m["text"] for m in pc["messages"]
                                         if m["level"] == "error"]})
    if blocked:
        lines = [f"· {b['bundle']}: {' / '.join(b['messages'])}" for b in blocked]
        raise ValueError("사전점검을 통과하지 못한 번들이 있어 렌더를 시작하지 않았습니다.\n"
                         + "\n".join(lines))

    if not _RENDER_LOCK.acquire(blocking=False):
        raise RuntimeError("이미 렌더가 돌고 있습니다. 동시에 하나만 실행됩니다 "
                           "(Chromium·TTS·ffmpeg 가 자원을 다 쓰고, 스크래치 폴더가 "
                           "서로를 덮어씁니다).")

    label = f"영상 렌더 · {len(codes)}개 번들" if len(codes) > 1 else f"영상 렌더 · {codes[0]}"
    job = registry.create("render", label, codes)
    job["options"] = {"no_audio": no_audio, "keep_scratch": keep_scratch,
                      "stop_on_error": stop_on_error}
    for c in codes:
        job["items"][c]["chapter_id"] = bundles.chapter_id(c)

    def work(j: dict) -> None:
        try:
            _run_all(j, codes, no_audio=no_audio, keep_scratch=keep_scratch,
                     stop_on_error=stop_on_error)
        finally:
            _RENDER_LOCK.release()

    registry.spawn(job, work)
    return job


def _run_all(job: dict, codes: list[str], *, no_audio: bool, keep_scratch: bool,
             stop_on_error: bool) -> None:
    outputs, failed = [], []
    for c in codes:
        if job.get("cancel_requested"):
            registry.item(job, c, status="skipped", error="사용자가 취소했습니다.")
            continue
        registry.update(job, current=c)
        rc = _run_one(job, c, no_audio=no_audio, keep_scratch=keep_scratch)
        if rc == 0:
            out = job["items"][c].get("output")
            if out:
                outputs.append(out)
        else:
            failed.append(c)
            if stop_on_error:
                registry.log(job, f"[make] {c} 실패 — 이후 번들을 건너뜁니다"
                                  " (stop_on_error).", force=True)
                for rest in codes[codes.index(c) + 1:]:
                    registry.item(job, rest, status="skipped",
                                  error="앞 번들이 실패해 건너뜀")
                break

    if job.get("cancel_requested"):
        registry.finish(job, "error", error="사용자가 취소했습니다.",
                        result={"outputs": outputs})
        registry.log(job, "[make] 취소했습니다. munje 스크래치 폴더가 남아 있으면 "
                          "지워도 됩니다(다음 실행이 덮어씁니다).", force=True)
    elif failed:
        registry.finish(job, "error", error=f"실패한 번들: {', '.join(failed)}",
                        result={"outputs": outputs, "failed": failed})
    else:
        registry.finish(job, "done", result={"outputs": outputs})


def _run_one(job: dict, bundle: str, *, no_audio: bool, keep_scratch: bool) -> int:
    registry.item(job, bundle, status="running", scene_done=0)
    args = _args(bundle, no_audio=no_audio, keep_scratch=keep_scratch)
    registry.log(job, f"[make] {bundle} 시작 — {' '.join(args[1:])}", force=True)

    proc = subprocess.Popen(
        args, cwd=ENGINE_DIR, env=_build_env(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    _PROCS[job["id"]] = proc

    try:
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            registry.log(job, line)

            # 단계 이름을 먼저 갱신한다 — 조용한 구간에도 화면이 뭔가를 보여줘야 한다.
            for rx, name in _STAGES:
                sm = rx.search(line)
                if sm:
                    registry.item(job, bundle,
                                  stage=name or (sm.group(1) if sm.groups() else line[:40]))
                    break

            m = _RE_TTS.search(line)
            if m:
                registry.item(job, bundle, tts_done=int(m.group(1)),
                              tts_total=int(m.group(2)))
                continue

            m = _RE_PROGRESS.search(line)
            if m:
                registry.item(job, bundle, scene_done=int(m.group(2)),
                              scene_total=int(m.group(3)))
                continue
            m = _RE_DONE.search(line)
            if m:
                registry.item(job, bundle, output=m.group(1).strip())
                continue
            m = _RE_TOTAL.search(line)
            if m:
                registry.item(job, bundle, seconds=float(m.group(1)))
                continue
            m = _RE_ERROR.search(line)
            if m:
                registry.item(job, bundle, error=m.group(1).strip() or line)

            if job.get("cancel_requested"):
                _kill(proc)
                break
    finally:
        proc.stdout.close() if proc.stdout else None
        rc = proc.wait()
        _PROCS.pop(job["id"], None)

    if job.get("cancel_requested"):
        registry.item(job, bundle, status="error", error="사용자가 취소했습니다.")
        return rc or 1

    if rc == 0:
        # 실제로 mp4 가 생겼는지 확인한다 — 종료코드만 믿지 않는다.
        mp4 = paths.bundle_mp4(bundle)
        size = paths.size(mp4)
        if size < 1024 * 1024:
            registry.item(job, bundle, status="error",
                          error=f"종료코드는 0 인데 mp4 가 없거나 너무 작습니다 ({size} bytes).")
            return 1
        registry.item(job, bundle, status="done", output=mp4)
        registry.log(job, f"[make] {bundle} 완료 — {size / 1048576:.1f} MB", force=True)
        return 0

    hint = ""
    if rc == 2:
        # chodangi 규약: 종료코드 2 = 입력/검증 오류
        hint = " 번들 입력(deck/script)이 잘못됐습니다. 사전점검을 확인하세요."
    registry.item(job, bundle, status="error",
                  error=(job["items"][bundle].get("error")
                         or f"종료코드 {rc}.{hint}"))
    return rc


def _kill(proc: subprocess.Popen) -> None:
    """자식 트리를 통째로 죽인다.

    taskkill /T 가 Chromium · ffmpeg 손자 프로세스까지 잡는다(psutil 의존 회피).
    make_bundle_video.py 는 mp4 를 마지막에 copy2 로만 옮기므로, 중간에 죽여도
    05/ 에 반쪽 파일이 남지 않는다.
    """
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, timeout=20)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def cancel(job_id: str) -> bool:
    if not registry.request_cancel(job_id):
        return False
    proc = _PROCS.get(job_id)
    if proc:
        _kill(proc)
    return True
