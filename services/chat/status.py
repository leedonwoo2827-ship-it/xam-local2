# -*- coding: utf-8 -*-
"""오른쪽 칸의 기본 화면 — 「지금 하는 일 · 다음에 할 일」. **모델을 부르지 않는다.**

사용자 지시(2026-10-24): 시장조사나 진짜 대화가 필요한 경우가 아니면 오른쪽에는 지금
하는 일과 다음에 할 일만 나오면 된다. 그래서 채팅은 물을 때만 열리고, 평소에는 이 상태판이다.
화면을 열 때마다 $0.25 를 태울 수 없으니(provider.py 머리말) 전부 파일·잡 목록에서 센다.

    now      돌고 있는 잡(집필 · 이론 단계 · 렌더 · 빌드 …) + **CLI 로 돌리는 렌더**
             (실전에서는 tools/render_all.bat 으로 밤새 돌린다 — 앱 잡 목록에 없다)
    reflect  무언가를 고친 뒤 **이어서 반영해야 할 것** — 낭독 다시 · 듣기 다시 ·
             노트 빌드 다시 · 원천이 바뀜 · 문항을 고쳐 낡은 영상 번들
    next     할 일 몇 개 — 지금 보는 화면의 것이 맨 앞, 그다음 이론 묶음 · 문항 검수

★ 계층 규약: FastAPI 를 import 하지 않는다.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List

MAX_NEXT = 5


def _jobs() -> List[Dict[str, Any]]:
    from services.jobs import registry
    out = []
    for j in registry.list_jobs(limit=12):
        if j.get("status") not in ("running", "queued"):
            continue
        out.append({"id": j.get("id"), "label": j.get("label") or j.get("kind"),
                    "kind": j.get("kind"), "done": j.get("done_count") or 0,
                    "total": j.get("total_count") or 0, "current": j.get("current"),
                    "status": j.get("status")})
    return out


def _cli_render() -> List[Dict[str, Any]]:
    """tools/render_all.bat 이 돌고 있으면 그 로그의 마지막 줄을 보여 준다."""
    import time

    from core.constants import DATA_DIR
    log = os.path.join(DATA_DIR, "render_all.log")
    pidf = os.path.join(DATA_DIR, "render_all.pid")
    if not os.path.isfile(log):
        return []
    alive = False
    try:
        with open(pidf, encoding="utf-8") as f:
            alive = _pid_alive(int(f.read().strip() or 0))
    except (OSError, ValueError):
        pass
    fresh = time.time() - os.path.getmtime(log) < 180
    if not (alive or fresh):
        return []
    last = ""
    try:
        with open(log, "rb") as f:
            f.seek(max(0, os.path.getsize(log) - 4096))
            lines = [ln.strip() for ln in f.read().decode("utf-8", "replace").splitlines() if ln.strip()]
        last = lines[-1] if lines else ""
        if last.startswith("exit="):
            return []
    except OSError:
        pass
    return [{"id": "", "label": "CLI 렌더 (render_all.bat)", "kind": "cli-render",
             "detail": last[:120], "status": "running"}]


def _pid_alive(pid: int) -> bool:
    """★ os.kill(pid, 0) 을 쓰지 않는다 — Windows 에서는 그 호출이 프로세스를 **끝낸다.**
    읽기 권한으로 열어 종료 코드만 본다."""
    if pid <= 0:
        return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259             # STILL_ACTIVE
    except Exception:                                        # noqa: BLE001
        return False


def _reflect() -> List[Dict[str, Any]]:
    """고친 뒤 이어서 반영할 것 — 고친 사람이 잊기 쉬운 아래쪽 산물들."""
    from services.book import paths
    from services.lecture import common, listen, notes, outline

    out: List[Dict[str, Any]] = []
    for s in common.subjects():
        key, name = s["key"], f"{s['no']}과목"
        o = outline.read_outline(key)
        sh = paths.summary_html(key)
        if o and o.get("approved") and os.path.isfile(sh):
            try:
                made = os.path.getmtime(outline.outline_path(key))
                if made > os.path.getmtime(sh):
                    out.append({"text": f"{name} 노트 구조가 바뀜 → 이론 요약 노트 다시", "route": "#/summary"})
            except OSError:
                pass
        for kind, label in (("summary", "요약반"), ("full", "종합반")):
            d = notes.load(kind, key)
            if not d:
                continue
            route = f"#/lecture/{kind}/{key}"
            src = notes.source_now(d)
            if src and d.get("source_hash") and src != d["source_hash"]:
                up = "이론 요약 노트" if kind == "summary" else "요약반 노트"
                out.append({"text": f"{name} {up}가 바뀜 → {label} 노트에 반영 확인", "route": route})
            st = d.get("stages") or {}
            if (st.get("read") or {}).get("status") in ("done", "approved"):
                n = sum(1 for x in notes.slides(d) if x.get("say") and not x.get("read_done"))
                if n:
                    out.append({"text": f"{name} {label} 자막을 고친 {n}장 → 낭독 다시", "route": route})
            b = st.get("build") or {}
            if b.get("status") == "done" and b.get("hash") and b["hash"] != notes.content_hash(d):
                out.append({"text": f"{name} {label} 원고가 바뀜 → 노트 빌드 다시", "route": route})
            ls = listen.summary(kind, key)
            stale = sum(1 for r in ls.get("slides") or [] if r["stale"] and not r["ok"])
            if stale:
                out.append({"text": f"{name} {label} 낭독이 바뀐 {stale}장 → 다시 듣기",
                            "route": f"#/listen/{kind}/{key}"})
    try:
        old = _stale_bundles()
        if old:
            out.append({"text": f"문항을 고쳐 낡은 영상 번들 {len(old)}개 ({', '.join(old[:3])}…) → 슬라이드·영상 다시",
                        "route": "#/video"})
    except Exception:                                        # noqa: BLE001
        pass
    return out


_STALE = {"at": 0.0, "book": "", "v": []}


def _stale_bundles() -> List[str]:
    """번들 75개를 훑는 데 2초 — 상태판은 몇 초마다 다시 부르므로 30초 담아 둔다."""
    import time

    from services.book import paths
    from services.render import bundles
    if time.time() - _STALE["at"] > 30 or _STALE["book"] != paths.book_dir():
        _STALE.update(at=time.time(), book=paths.book_dir(),
                      v=[b["bundle"] for b in bundles.scan_all() if b.get("status") == "stale"])
    return list(_STALE["v"])


def _note_next(kind: str, key: str, name: str) -> Dict[str, Any] | None:
    """이 강의 노트에서 다음에 누를 것 하나."""
    from services.lecture import listen, notes

    label = "요약반" if kind == "summary" else "종합반"
    d = notes.load(kind, key)
    route = f"#/lecture/{kind}/{key}"
    if not d:
        return {"text": f"{name} {label} 노트 만들기", "route": route}
    for st in notes.stage_view(d):
        if not st["open"]:
            break
        if st["status"] == "approved" or (st["stage"] == "build" and st["status"] == "done"):
            continue
        if st["stage"] == "listen":
            ls = listen.summary(kind, key)
            if ls["open_fixes"]:
                return {"text": f"{name} {label} 듣기 지적 {ls['open_fixes']}건 처리", "route": route}
            return {"text": f"{name} {label} 듣기 검수 {ls['done']}/{ls['total']}장 (각 {ls['need']}명)",
                    "route": f"#/listen/{kind}/{key}"}
        if st["status"] == "running":
            return None
        from services.lecture import stages
        left = stages.incomplete(d, st["stage"]) if st["status"] == "done" else []
        if left:
            return {"text": f"{name} {label} {st['label']} — 남은 {len(left)}장 실행", "route": route}
        verb = "승인" if st["status"] == "done" else "실행"
        return {"text": f"{name} {label} {st['label']} {verb}", "route": route}
    return None


def _theory(focus: str = "") -> List[Dict[str, Any]]:
    from services.book import paths
    from services.lecture import common, notes, outline

    out: List[Dict[str, Any]] = []
    for s in common.subjects():
        key, name = s["key"], f"{s['no']}과목"
        if focus and key != focus:
            continue
        o = outline.summary(key)
        if not o["outline"]:
            out.append({"text": f"{name} 해설 모아 노트 구조화", "route": "#/outline"})
            continue
        if not o["outline"]["approved"]:
            out.append({"text": f"{name} 노트 구조(목차) 검토 후 승인", "route": "#/outline"})
            continue
        if not os.path.isfile(paths.summary_html(key)):
            out.append({"text": f"{name} 이론 요약 노트 만들기", "route": "#/summary"})
            continue
        n = _note_next("summary", key, name)
        if n:
            out.append(n)
            continue
        f = _note_next("full", key, name)
        if f:
            out.append(f)
    return out


def _questions() -> List[Dict[str, Any]]:
    try:
        from services.book import index as bindex
        res = bindex.query()
        left = int(res.get("total") or 0) - int(res.get("reviewed") or 0)
        if left > 0:
            return [{"text": f"문항 교정 — 미검수 {left}개 남음", "route": "#/questions"}]
    except Exception:                                            # noqa: BLE001
        pass
    return []


def compute(route: str = "") -> Dict[str, Any]:
    nxt: List[Dict[str, Any]] = []
    m = re.match(r"^#/(?:lecture|listen)/(summary|full)/([^/?]+)", route or "")
    if m:
        try:
            from services.lecture import common
            s = common.subject(m.group(2))
            n = _note_next(m.group(1), m.group(2), f"{s['no']}과목")
            if n:
                n["here"] = True
                nxt.append(n)
        except Exception:                                        # noqa: BLE001
            pass
    try:
        for n in _theory():
            if all(n["text"] != x["text"] for x in nxt):
                nxt.append(n)
    except Exception:                                            # noqa: BLE001
        pass
    if route.startswith("#/questions"):
        nxt = _questions() + nxt
    else:
        nxt += _questions()
    try:
        reflect = _reflect()
    except Exception:                                            # noqa: BLE001
        reflect = []
    return {"now": _jobs() + _cli_render(), "reflect": reflect[:MAX_NEXT], "next": nxt[:MAX_NEXT]}
