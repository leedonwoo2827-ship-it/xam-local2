# -*- coding: utf-8 -*-
"""듣기 검수 — 장별 TTS 미리듣기 · 여러 사람의 검수 기록 · 집계.

미리듣기
  장마다 낭독(없으면 자막)을 **영상과 같은 엔진·목소리**(vendor/chodangi 의 voicewright)
  로 합성해 `<노트폴더>/_audio/<key>/<id>.<hash>.mp3` 에 둔다(wav 는 장당 4.5MB 라
  143장 과목이면 650MB — 64kbps mp3 로 줄인다. 듣기 검수에 충분하다). 낭독이 바뀌면 hash 가
  바뀌어 새로 굽는다 — 옛 파일은 지우지 않는다(다른 사람이 아직 듣고 있을 수 있다).
  다른 목소리로 들으면 검수가 의미 없다. 그래서 브라우저 TTS 를 쓰지 않는다.

검수 기록
  `<노트폴더>/_review/<key>.jsonl` 에 **덧붙이기만** 한다. 한 줄 = 한 판정:
    {seq, at, reviewer, id, hash, verdict: ok|fix, memo, suggest}
    {seq, at, reviewer, type: resolve, ref: <fix 의 seq>, action: applied|dismissed}
  여러 사람이 동시에 눌러도 깨지지 않게 프로세스 안 잠금으로 줄 단위로 쓴다.
  OK 는 **그 hash 에 대한 OK** 다 — 낭독을 고치면 그 장의 OK 는 '낡음' 이 되고 다시 들어야 한다.

★ 계층 규약: FastAPI 를 import 하지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from services.book import paths

from . import notes as N
from .common import DEFAULT_LISTENERS, audio_dir, h, review_path

_LOCK = threading.Lock()


# ── 미리듣기 ────────────────────────────────────────────────────────────────
def audio_path(kind: str, key: str, sid: str, text: str) -> str:
    return os.path.join(audio_dir(kind, key), f"{sid}.{h(text)}.mp3")


def _voice() -> str:
    """회차 파일의 목소리 — 문제풀이 영상과 같은 목소리로 듣는다."""
    d = os.path.join(paths.book_dir(), "_rounds")
    try:
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".json"):
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    v = (json.load(f) or {}).get("voice")
                if v:
                    return str(v)
    except (OSError, ValueError):
        pass
    return "F2"


def _engine_env() -> None:
    import sys

    from services.render import runner
    env = runner.env_info()
    if not env.get("python_ok") or not env.get("assets_ok"):
        raise RuntimeError("음성 엔진이 준비되지 않았습니다 — vendor/chodangi/assets(TTS 모델)를 확인하세요.")
    eng = env["engine"]
    if eng not in sys.path:
        sys.path.insert(0, eng)
    # speech.resynth 와 같은 세 줄 — 엔진 기본 경로가 CWD 기준이라 앱 프로세스에서는 못 찾는다.
    for k, rel in (("VOICEWRIGHT_ASSETS_DIR", "assets"),
                   ("VOICEWRIGHT_VOICE_MAP", "config/voice_map.yaml"),
                   ("VOICEWRIGHT_PRONUNCIATION_MAP", "config/pronunciation_map.yaml")):
        os.environ.setdefault(k, os.path.join(eng, *rel.split("/")))


async def synth(kind: str, key: str, sid: str) -> str:
    """그 장의 wav 경로. 없으면 지금 굽는다. ★ 앱의 이벤트 루프에서 부른다(엔진 캐시가 루프에 묶인다)."""
    doc = N.load(kind, key)
    if not doc:
        raise ValueError("노트가 없습니다.")
    if sid == "_h1":
        h1 = doc.get("h1") or {}
        text = (h1.get("read") or h1.get("say") or "").strip()
    else:
        text = N.spoken(N.find(doc, sid))
    if not text:
        raise ValueError("읽을 글이 없습니다 — 자막대본이 비어 있습니다.")
    p = audio_path(kind, key, sid, text)
    if os.path.isfile(p):
        return p
    _engine_env()
    from voicewright.audio_io import write_wav     # noqa: PLC0415
    from voicewright.engine import Engine          # noqa: PLC0415
    eng = await Engine.get()
    wav = await eng.synth(text, voice_code=_voice())
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp.wav"
    write_wav(tmp, wav, eng.sample_rate)
    await asyncio.to_thread(_to_mp3, tmp, p)
    return p


def _to_mp3(wav: str, mp3: str) -> None:
    import subprocess
    part = mp3 + ".part.mp3"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-ac", "1",
                        "-b:a", "64k", part], check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        os.replace(part, mp3)
    finally:
        for f in (wav, part):
            try:
                os.remove(f)
            except OSError:
                pass


def bake_all(kind: str, key: str, loop: asyncio.AbstractEventLoop, *, log, cancelled) -> Dict[str, int]:
    """잡 스레드에서 — 과목 하나의 미리듣기를 통째로 굽는다. 합성은 앱 루프에 넘긴다."""
    doc = N.load(kind, key)
    ids = [s["id"] for s in N.slides(doc) if N.spoken(s)]
    made = have = 0
    for i, sid in enumerate(ids, 1):
        if cancelled():
            log("취소했습니다.")
            break
        sl = N.find(doc, sid)
        if os.path.isfile(audio_path(kind, key, sid, N.spoken(sl))):
            have += 1
            continue
        asyncio.run_coroutine_threadsafe(synth(kind, key, sid), loop).result(timeout=300)
        made += 1
        if made % 5 == 0 or i == len(ids):
            log(f"{i}/{len(ids)} 장 — 새로 구운 것 {made}")
    return {"made": made, "had": have, "total": len(ids)}


# ── 검수 기록 ───────────────────────────────────────────────────────────────
def _read_lines(kind: str, key: str) -> List[Dict[str, Any]]:
    p = review_path(kind, key)
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return out


def _append(kind: str, key: str, rec: Dict[str, Any]) -> Dict[str, Any]:
    p = review_path(kind, key)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with _LOCK:
        rec = dict(rec, seq=len(_read_lines(kind, key)) + 1, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _reviewer(name: str) -> str:
    n = " ".join((name or "").split())[:20]
    if not n:
        raise ValueError("검수자 이름이 없습니다.")
    return n


def judge(kind: str, key: str, *, reviewer: str, sid: str, verdict: str,
          memo: str = "", suggest: str = "") -> Dict[str, Any]:
    if verdict not in ("ok", "fix"):
        raise ValueError("판정은 ok 또는 fix 입니다.")
    doc = N.load(kind, key)
    if not doc:
        raise ValueError("노트가 없습니다.")
    sl = N.find(doc, sid)
    if verdict == "fix" and not (memo.strip() or suggest.strip()):
        raise ValueError("고칠 곳은 메모나 낭독 수정안을 적어 주세요.")
    return _append(kind, key, {"reviewer": _reviewer(reviewer), "id": sid,
                               "hash": h(N.spoken(sl)), "verdict": verdict,
                               "memo": memo.strip()[:1000], "suggest": suggest.strip()[:3000]})


def resolve(kind: str, key: str, *, ref: int, action: str, reviewer: str = "운영자") -> Dict[str, Any]:
    """지적 하나를 처리한다. applied 면 제안한 낭독을 원고에 반영한다."""
    if action not in ("applied", "dismissed"):
        raise ValueError("action 은 applied 또는 dismissed 입니다.")
    rec = next((r for r in _read_lines(kind, key) if r.get("seq") == int(ref)), None)
    if not rec or rec.get("verdict") != "fix":
        raise ValueError("그런 지적이 없습니다.")
    if action == "applied":
        if not rec.get("suggest"):
            raise ValueError("이 지적에는 낭독 수정안이 없습니다 — 장을 직접 고친 뒤 [처리함] 으로 닫으세요.")
        doc = N.load(kind, key)
        N.edit_slide(doc, rec["id"], {"read": rec["suggest"]})
        N.save(doc)
    return _append(kind, key, {"reviewer": _reviewer(reviewer), "type": "resolve",
                               "ref": int(ref), "action": action})


def summary(kind: str, key: str, need: int = DEFAULT_LISTENERS) -> Dict[str, Any]:
    """장마다 [지금 소리에 대한 OK 한 사람들] · [안 닫힌 지적] — 그리고 승인 가능 여부."""
    doc = N.load(kind, key)
    if not doc:
        return {"slides": [], "ready": False}
    lines = _read_lines(kind, key)
    closed = {r["ref"]: r for r in lines if r.get("type") == "resolve"}
    cur = {s["id"]: h(N.spoken(s)) for s in N.slides(doc)}
    last: Dict[tuple, Dict[str, Any]] = {}
    fixes: Dict[str, List[Dict[str, Any]]] = {}
    for r in lines:
        if r.get("type") == "resolve":
            continue
        last[(r["id"], r["reviewer"])] = r
        if r.get("verdict") == "fix" and r["seq"] not in closed:
            fixes.setdefault(r["id"], []).append(r)
    rows, ready, reviewers = [], True, set()
    for s in N.slides(doc):
        oks, stale = [], []
        for (sid, who), r in last.items():
            if sid != s["id"]:
                continue
            reviewers.add(who)
            if r.get("verdict") == "ok":
                (oks if r.get("hash") == cur[s["id"]] else stale).append(who)
        open_fix = fixes.get(s["id"], [])
        done = len(oks) >= need and not open_fix
        ready = ready and done
        rows.append({"id": s["id"], "ok": sorted(oks), "stale": sorted(stale),
                     "fixes": open_fix, "done": done})
    return {"need": need, "ready": ready and bool(rows), "reviewers": sorted(reviewers),
            "done": sum(1 for r in rows if r["done"]), "total": len(rows),
            "open_fixes": sum(len(r["fixes"]) for r in rows), "slides": rows}


def mine(kind: str, key: str, reviewer: str) -> Dict[str, str]:
    """이 검수자의 장별 마지막 판정 — 검수 화면이 '내가 어디까지 들었나' 를 그린다."""
    doc = N.load(kind, key)
    cur = {s["id"]: h(N.spoken(s)) for s in N.slides(doc)} if doc else {}
    out: Dict[str, str] = {}
    for r in _read_lines(kind, key):
        if r.get("reviewer") == reviewer and r.get("id") in cur:
            out[r["id"]] = r["verdict"] if r.get("hash") == cur[r["id"]] else "stale"
    return out
