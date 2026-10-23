# -*- coding: utf-8 -*-
"""발음대본 — 사람이 고친 낭독문을 남기고, 그 씬만 다시 합성한다.

**왜 별도 파일인가.** 문제 씬의 낭독은 `question` 을 그대로 읽는다
(`bake._narration()`). 해설처럼 `explanation_speech` 같은 낭독문 칸이 없어서,
발음만 손보려면 발문 자체를 고쳐야 하고 그러면 화면·자막·인쇄물이 다 같이 바뀐다.
그래서 **발음만 담는 덮어쓰기 파일**을 번들 옆에 둔다.

  05/<번들>/script/<번들>_speech.json

`bake` 가 이 파일을 **병합만** 한다 — 덮어쓰지 않는다(`youtube_map` 과 같은 규약).
그래서 다시 구워도 손수정이 살아남는다.

★ `from` 에 **고칠 때의 자막 원문**을 함께 남긴다. 이것이 `tools/learn_speech.py` 의
  원재료다 — 값만 남기면 나중에 무엇을 왜 고쳤는지 복원할 수 없고, 발문이 그 뒤에
  고쳐졌는지도 알 수 없다.

★ 자막(`narration`)은 원문 그대로 두고 발음(`narration_text`)만 갈린다. 엔진이 이미
  그 두 필드를 나눠 읽는다(`make_bundle_video._build_records`) — 스키마는 원래 있었고
  bake 가 두 값을 같게 써 왔을 뿐이다.
"""
from __future__ import annotations

import json
import os
import re

from core.atomic_io import atomic_write_json
from services.book import paths

_NOTE = ("사람이 고친 자막·발음. bake 가 병합만 한다(덮어쓰지 않는다). "
         "from 은 고칠 때의 자막 원문 — 발문이 그 뒤에 바뀌면 bake 가 경고한다. "
         "subtitle 은 고친 자막, text 는 고친 발음. 둘 중 하나만 있어도 된다.")


def path(bundle: str) -> str:
    return os.path.join(paths.bundle_dir(bundle), "script", f"{bundle}_speech.json")


def read_raw(bundle: str) -> dict:
    """`{씬번호(str): {text, from}}`. 파일이 없거나 깨져도 예외를 내지 않는다.

    ★ 깨진 파일을 조용히 빈 dict 로 만들면 **손수정이 사라진 채로 렌더가 돈다.**
      읽기는 비게 두지만 `save()` 는 그 위에 덮어쓰지 않고 멈춘다.
    """
    p = path(bundle)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f) or {}
    except (OSError, ValueError):
        return {}
    out = {}
    for k, v in (doc.get("scenes") or {}).items():
        # ★ 자막만 고친 항목도 살린다 — 전에는 `text`(발음)가 있어야만 읽어서,
        #   자막만 고치면 저장은 되고 다시 구울 때 조용히 사라졌다.
        if isinstance(v, dict) and ((v.get("text") or "").strip()
                                    or (v.get("subtitle") or "").strip()):
            out[str(k)] = v
    return out


def overrides(bundle: str) -> dict[int, dict]:
    """씬 번호(int) → 항목. bake 와 화면이 같이 쓴다."""
    out: dict[int, dict] = {}
    for k, v in read_raw(bundle).items():
        try:
            out[int(k)] = v
        except ValueError:
            continue
    return out


def save(bundle: str, scene: int, text: str, *, src: str = "",
         subtitle: str = "") -> dict:
    """그 씬의 발음을 덮어쓰기 파일에 남긴다.

    `src` 는 지금 화면에 있는 **자막 원문**이다. 빈 값이면 script.json 의
    `narration` 에서 읽는다 — 화면이 안 보내도 `from` 이 비지 않게.

    빈 문자열을 주면 그 씬의 덮어쓰기를 **지운다**(원문 낭독으로 되돌림).
    """
    p = path(bundle)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f) or {}
        except ValueError as e:
            raise ValueError(
                f"{os.path.basename(p)} 가 깨져 있어 덮어쓰지 않았습니다: {e} — "
                "손수정이 들어 있는 파일이라 지우지 않고 멈춥니다.") from e
    else:
        doc = {}
    doc.setdefault("_note", _NOTE)
    scenes = dict(doc.get("scenes") or {})

    key = str(int(scene))
    body = (text or "").strip()
    sub = (subtitle or "").strip()
    origin = (src or _subtitle_of(bundle, scene)).strip()
    # ★ 자막을 원문 그대로 두었으면 자막 덮어쓰기는 남기지 않는다 — 안 그러면
    #   손대지 않은 씬까지 「고침」으로 표시되고, 원문이 바뀌어도 옛 자막에 묶인다.
    if sub == origin:
        sub = ""
    if not body and not sub:
        scenes.pop(key, None)
        removed = True
    else:
        e = {"from": origin}
        if sub:
            e["subtitle"] = sub
        if body:
            e["text"] = body
        scenes[key] = e
        removed = False

    doc["scenes"] = scenes
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write_json(p, doc, indent=2, trailing_newline=True)
    return {"bundle": bundle, "scene": int(scene), "removed": removed,
            "count": len(scenes), "path": paths.rel(p)}


def _script(bundle: str) -> dict:
    try:
        with open(paths.bundle_script(bundle), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _subtitle_of(bundle: str, scene: int) -> str:
    """그 씬의 자막 원문 — `narration`. 발음(`narration_text`)이 아니다."""
    for s in _script(bundle).get("scenes") or []:
        if int(s.get("scene", -1)) == int(scene):
            return str(s.get("narration") or "")
    return ""


def read(bundle: str) -> dict:
    """씬별 자막·발음·덮어쓰기 상태. 화면이 표로 그린다."""
    ov = overrides(bundle)
    items = []
    for s in _script(bundle).get("scenes") or []:
        si = int(s.get("scene", len(items)))
        sub = str(s.get("narration") or "")
        e = ov.get(si) or {}
        edited = bool((e.get("text") or "").strip())
        sub_edited = bool((e.get("subtitle") or "").strip())
        # ★ 다시 굽기 전에도 화면은 **고친 값**을 보여야 한다. script.json 의
        #   `narration` 은 다음 굽기까지 원문 그대로다.
        shown_sub = e.get("subtitle") if sub_edited else sub
        items.append({
            "scene": si,
            "kind": s.get("kind"),
            "number": s.get("number"),
            "subtitle": shown_sub,                            # 자막 — 고친 것이 있으면 그것
            "subtitle_src": sub,                              # 자막 원문 (drift 대조용)
            "subtitle_edited": sub_edited,
            "speech": (e.get("text") or "") if edited else shown_sub,
            "edited": edited,
            # 고친 뒤에 발문이 바뀌었나 — bake 가 이 경우 덮지 않는다
            "drifted": bool((edited or sub_edited)
                            and (e.get("from") or "").strip() != sub.strip()),
        })
    return {"bundle": bundle, "path": paths.rel(path(bundle)),
            "edited": sum(1 for i in items if i["edited"] or i["subtitle_edited"]),
            "drifted": [i["scene"] for i in items if i["drifted"]],
            "items": items}


# ── 씬 하나만 다시 합성 ────────────────────────────────────────────────────
def stale_scenes(bundle: str) -> list[int]:
    """mp4 보다 새로운 wav 의 씬 번호. **mp4 가 낡았다**는 뜻이다.

    ★ 씬 재합성은 wav 만 갈아 끼운다(mp4 재조립은 번들 재렌더가 한다). 그걸 조용히
      두면 어긋난 mp4 가 그대로 드라이브로 올라간다 — 화면이 말하게 한다.
    """
    mp4 = paths.bundle_mp4(bundle)
    if not os.path.isfile(mp4):
        return []
    base = os.path.getmtime(mp4)
    adir = paths.bundle_audio_dir(bundle)
    out = []
    try:
        names = os.listdir(adir)
    except OSError:
        return []
    for n in names:
        m = re.match(r"scene_(\d+)\.wav$", n)
        if m and os.path.getmtime(os.path.join(adir, n)) > base + 1:
            out.append(int(m.group(1)))
    return sorted(out)


async def resynth(bundle: str, scene: int, *, text: str = "") -> dict:
    """그 씬의 wav 하나를 지금 발음으로 다시 만든다.

    ★ mp4·통합 자막은 **건드리지 않는다.** 발음 한 군데 고칠 때마다 번들 전체를
      다시 돌리면(실측 165초) 검수가 끝나지 않는다. 여기서 고치고 여기서 듣고,
      다 OK 한 뒤에 [이 번들 재렌더] 한 번으로 mp4 를 낸다.

    ★ 벤더의 `synth_scene_text()` 를 쓰지 않는다. 그 함수는 폴더가 `ch11`,
      파일이 `ch11_02_narration.wav` 인 **엔진 레이아웃**을 기대한다. 책 번들은
      `m01-1` / `audio/scene_01.wav` 라서(`_finalize_bundle` 이 이름을 바꿔 옮긴다)
      엔진을 직접 부르고 책 경로에 쓰는 쪽이 짧고 오해가 없다.

    ★ 발음사전·약어 음역·연도 변환은 `Engine.synth()` **안에서** 걸린다. 여기서
      미리 적용하면 이중 변환이 된다.
    """
    import sys

    body = (text or "").strip()
    if not body:
        for i in read(bundle)["items"]:
            if i["scene"] == int(scene):
                body = (i["speech"] or "").strip()
                break
    if not body:
        raise ValueError(f"{scene}번 씬에 읽을 글이 없습니다 — 발음 칸을 채우세요.")

    from services.render import runner
    env = runner.env_info()
    if not env.get("python_ok") or not env.get("assets_ok"):
        raise RuntimeError("음성 엔진이 준비되지 않았습니다 — 렌더 환경 카드를 보세요.")

    engine_dir = env["engine"]
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)
    # ★ 엔진 경로는 **환경변수로 준다.** 기본값이 CWD 기준 상대경로라, 앱 프로세스에서
    #   그냥 부르면 `vendor/assets` 를 찾다가 죽는다(실측). `make_bundle_video.py` 가
    #   머리에서 하는 것과 **같은 세 줄**이다 — 그쪽은 서브프로세스라 cwd 가 엔진이었다.
    for key, rel in (("VOICEWRIGHT_ASSETS_DIR", "assets"),
                     ("VOICEWRIGHT_VOICE_MAP", "config/voice_map.yaml"),
                     ("VOICEWRIGHT_PRONUNCIATION_MAP", "config/pronunciation_map.yaml")):
        os.environ.setdefault(key, os.path.join(engine_dir, *rel.split("/")))

    wav_path = os.path.join(paths.bundle_audio_dir(bundle), f"scene_{int(scene):02d}.wav")
    was = _wav_seconds(wav_path)

    from voicewright.audio_io import write_wav     # noqa: PLC0415
    from voicewright.engine import Engine          # noqa: PLC0415

    async def go():
        eng = await Engine.get()
        wav = await eng.synth(body, voice_code=_voice(bundle))
        os.makedirs(os.path.dirname(wav_path), exist_ok=True)
        write_wav(wav_path, wav, eng.sample_rate)
        return len(wav) / float(eng.sample_rate)

    # ★ `asyncio.run()` 을 쓰지 않는다. 이 함수는 **FastAPI 라우트 안**에서
    #   불리고, 거기에는 이미 돌고 있는 루프가 있다 — 그 안에서 `asyncio.run()` 은
    #   `cannot be called from a running event loop` 으로 죽는다(실측 2026-08-26).
    # ★ 쓰레드로 돌려도 안 된다. `Engine.get()` 이 엔진을 캐시하므로 부를 때마다
    #   새 루프를 만들면 두 번째부터 다른 루프의 객체를 건드리게 된다.
    #   앱의 루프 하나를 그대로 쓴다.
    sec = await go()
    return {"bundle": bundle, "scene": int(scene), "sec": round(sec, 3),
            "was": was, "text": body,
            # 길이가 달라지면 자막 시각이 밀린다 — 조용히 두지 않고 화면이 말한다
            "shifted": (was is None or abs(sec - was) > 0.02),
            "stale_scenes": stale_scenes(bundle)}


def _voice(bundle: str) -> str:
    """이 번들이 쓰는 목소리. `_series`(script.json)의 값을 따른다."""
    return str(_script(bundle).get("voice") or "F2")


def _wav_seconds(p: str) -> float | None:
    if not os.path.isfile(p):
        return None
    try:
        import wave
        with wave.open(p, "rb") as w:
            return round(w.getnframes() / float(w.getframerate()), 3)
    except Exception:                        # noqa: BLE001  — 길이는 보여주기만 한다
        return None
