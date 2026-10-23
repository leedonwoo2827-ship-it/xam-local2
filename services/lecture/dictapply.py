# -*- coding: utf-8 -*-
"""발음 사전 → 적용 → 재굽기 (v2).

사전이 여기저기(backplate · supertonic · chodangi · 품목 JSON) 흩어져 있던 것을 이 앱의 사전
하나로 모았다(services/render/lexicon.MAP_PATH). 이 파일은 그 사전에 **넣은 말을 원고와 소리에
반영하는** 두 단계다(사용자 지시 2026-10-24: 넣기 · 적용 · 재굽기를 이 앱에서).

    적용   강의 노트(03-2·03-3)의 장 중 그 말이 자막에 나오는 장 → 낭독(data-read)에 그 소리를 넣는다.
           사람이 고친 낭독은 통째로 다시 만들지 않고 **그 말 자리만** 바꾼다.
           문항 번들(05)은 엔진이 합성할 때 사전을 걸므로 글을 바꾸지 않고, 그 말이 나오는 씬만 찾는다.
    재굽기 바뀐 장의 미리듣기 mp3 와 찾은 씬의 wav 를 다시 굽는다(잡). 낭독이 바뀐 장의 듣기 OK 는
           hash 가 달라져 자동으로 '낡음' 이 된다 — 다시 들어야 한다.

★ 계층 규약: FastAPI 를 import 하지 않는다.
"""
from __future__ import annotations

import asyncio
import glob
import json
import os
import re
from typing import Any, Callable, Dict, List

from services.book import paths

from . import notes as N
from .common import KINDS


def _rules(terms: List[str] | None) -> Dict[str, str]:
    from services.render import lexicon
    allr = dict(lexicon.read().get("rules") or {})
    if terms:
        return {t: allr[t] for t in terms if t in allr}
    return allr


def _pat(term: str):
    # 엔진·사전과 같은 경계 — 앞뒤에 라틴 글자가 붙지 않은 것만
    return re.compile(r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])")


def apply(terms: List[str] | None = None) -> Dict[str, Any]:
    """강의 노트 낭독에 사전을 넣는다. 반환: 바뀐 장 · 찾은 문항 씬."""
    rules = _rules(terms)
    if not rules:
        return {"rules": 0, "notes": [], "scenes": []}
    order = sorted(rules, key=len, reverse=True)          # 긴 말부터 (CRISP-DM 이 CRISP 보다 먼저)
    changed: List[Dict[str, Any]] = []
    for kind in ("summary", "full"):
        for jp in sorted(glob.glob(os.path.join(paths.book_dir(), KINDS[kind][0], "*.json"))):
            key = os.path.splitext(os.path.basename(jp))[0]
            doc = N.load(kind, key)
            if not doc:
                continue
            hit = []
            for sl in N.slides(doc):
                say = sl.get("say") or ""
                if not say or not any(_pat(t).search(say) for t in order):
                    continue
                cur = sl.get("read") or say
                new = cur
                for t in order:
                    new = _pat(t).sub(rules[t], new)
                if new != cur:
                    sl["read"] = "" if new == say else new
                    hit.append(sl["id"])
            if hit:
                N.save(doc)
                changed.append({"kind": kind, "key": key, "ids": hit})
    return {"rules": len(rules), "notes": changed, "scenes": scenes(list(rules))}


def scenes(terms: List[str]) -> List[Dict[str, Any]]:
    """문항 번들에서 그 말이 자막에 나오는 씬 — 엔진이 합성 때 사전을 걸므로 다시 굽기만 하면 된다."""
    out = []
    pats = [_pat(t) for t in sorted(terms, key=len, reverse=True)]
    for sp in sorted(glob.glob(os.path.join(paths.book_dir(), "05", "*", "script", "*_script.json"))):
        try:
            doc = json.load(open(sp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        bundle = os.path.basename(os.path.dirname(os.path.dirname(sp)))
        for s in doc.get("scenes") or []:
            t = s.get("narration") or ""
            if any(p.search(t) for p in pats):
                out.append({"bundle": bundle, "scene": int(s.get("scene") or 0)})
    return out


def rebake(plan: Dict[str, Any], loop: asyncio.AbstractEventLoop, *, log: Callable[[str], None],
           cancelled: Callable[[], bool]) -> Dict[str, int]:
    """잡 스레드에서 — 바뀐 장의 미리듣기와 찾은 씬의 음성을 다시 굽는다(합성은 앱 루프)."""
    from services.render import speech

    from . import listen
    made = scn = 0
    for n in plan.get("notes") or []:
        for sid in n["ids"]:
            if cancelled():
                return {"slides": made, "scenes": scn}
            asyncio.run_coroutine_threadsafe(listen.synth(n["kind"], n["key"], sid), loop).result(timeout=300)
            made += 1
        log(f"{n['kind']} {n['key']} — 미리듣기 {len(n['ids'])}장")
    for s in plan.get("scenes") or []:
        if cancelled():
            break
        try:
            asyncio.run_coroutine_threadsafe(speech.resynth(s["bundle"], s["scene"]), loop).result(timeout=300)
            scn += 1
            if scn % 10 == 0:
                log(f"문항 씬 {scn}/{len(plan['scenes'])}")
        except Exception as e:                               # noqa: BLE001
            log(f"(건너뜀) {s['bundle']} 씬{s['scene']}: {e}")
    log(f"끝 — 미리듣기 {made}장 · 문항 씬 {scn}개. 문항 mp4 는 [이 번들 재렌더] 또는 CLI 렌더로 다시 굽는다.")
    return {"slides": made, "scenes": scn}
