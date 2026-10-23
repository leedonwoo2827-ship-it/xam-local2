"""/api/outline · /api/lecture — 이론 묶음(v2).

    해설 모아 노트 구조화   /api/outline[/{key}]           collect · structure(잡) · approve
    요약반 · 종합반 노트    /api/lecture/{kind}[/{key}]    init · stage(잡) · approve · slide 편집
    듣기 검수               /api/lecture/{kind}/{key}/audio/{id} · review · resolve · tts(잡)

★ 듣기 검수의 `POST …/review` 만은 LAN 보기 전용에서도 받는다(core/lan.py LAN_WRITABLE).
  여러 사람이 각자 자리에서 듣고 누르는 것이 이 기능의 전부라서다. 원고를 바꾸는
  resolve·slide 편집은 운영자 PC 에서만 된다.
★ 계층 규약: JSON·파일 전송만. 무거운 일은 services/lecture/*.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from services.jobs import registry
from services.lecture import common, listen, notes, outline, stages

KIND_JOB = "lecture"


def _bad(e: Exception) -> HTTPException:
    return HTTPException(status_code=409 if isinstance(e, ValueError) else 500, detail=str(e))


async def _body(request: Request) -> Dict[str, Any]:
    return await request.json() if await request.body() else {}


def _need(kind: str, key: str) -> None:
    try:
        common.check_kind(kind)
        common.check_key(key)
        common.subject(key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _busy() -> None:
    j = registry.running(KIND_JOB)
    if j:
        raise HTTPException(status_code=409,
                            detail=f"이론 노트 작업이 이미 돌고 있습니다 — {j.get('label')}. 끝난 뒤 다시 누르세요.")


def setup_lecture_routes() -> APIRouter:
    router = APIRouter(tags=["lecture"])

    # ── 해설 모아 노트 구조화 ──────────────────────────────────────────────
    @router.get("/api/outline")
    async def outline_list():
        """과목마다 모은 해설 · 구조화한 노트의 개수."""
        return {"items": [{**s, **outline.summary(s["key"])} for s in common.subjects()]}

    @router.get("/api/outline/{key}")
    async def outline_get(key: str):
        _need("summary", key)
        md = ""
        try:
            with open(outline.outline_md_path(key), encoding="utf-8") as f:
                md = f.read()
        except OSError:
            pass
        return {"summary": outline.summary(key), "outline": outline.read_outline(key), "md": md}

    @router.post("/api/outline/{key}/collect")
    async def outline_collect(key: str):
        """_rounds 해설을 과목별로 모은다(모델 없음 · 즉시)."""
        _need("summary", key)
        try:
            return outline.collect(key)
        except Exception as e:                               # noqa: BLE001
            raise _bad(e) from e

    @router.post("/api/outline/structure")
    async def outline_structure(request: Request):
        """모은 해설을 Claude 가 과목→항목→상세로 구조화한다(잡). keys 를 비우면 전 과목."""
        b = await _body(request)
        keys = b.get("keys") or [s["key"] for s in common.subjects()]
        for k in keys:
            _need("summary", k)
        _busy()
        job = registry.create(KIND_JOB, f"해설 구조화 {len(keys)}과목", list(keys))

        def work(j):
            for k in keys:
                if j.get("cancel_requested"):
                    registry.item(j, k, status="skipped", error="취소됨")
                    continue
                registry.update(j, current=k)
                registry.item(j, k, status="running")
                try:
                    outline.collect(k)
                    d = outline.structure(k, log=lambda s, j=j: registry.log(j, s))
                    registry.item(j, k, status="done",
                                  output=f"대단원 {len(d['topics'])}개 · ${d['cost_usd']:.3f}")
                except Exception as e:                       # noqa: BLE001
                    registry.item(j, k, status="error", error=str(e))
                    registry.log(j, f"[{k}] (문제) {e}", force=True)
            registry.finish(j, "done")

        registry.spawn(job, work)
        return registry.view(job)

    @router.post("/api/outline/{key}/approve")
    async def outline_approve(key: str, request: Request):
        _need("summary", key)
        b = await _body(request)
        try:
            return outline.approve(key, bool(b.get("on", True)))
        except Exception as e:                               # noqa: BLE001
            raise _bad(e) from e

    # ── 강의 노트 ──────────────────────────────────────────────────────────
    @router.get("/api/lecture/{kind}")
    async def lecture_list(kind: str):
        """과목마다 노트가 있는지 · 몇 장인지 · 단계가 어디까지 왔는지."""
        try:
            common.check_kind(kind)
            return {"kind": kind, "label": notes.KIND_LABEL[kind], "items": notes.overview(kind)}
        except Exception as e:                               # noqa: BLE001
            raise _bad(e) from e

    @router.get("/api/lecture/{kind}/{key}")
    async def lecture_get(kind: str, key: str):
        """노트 전체(장 목록 포함) · 단계표 · 듣기 검수 집계."""
        _need(kind, key)
        d = notes.load(kind, key)
        if not d:
            return {"exists": False, "subject": common.subject(key),
                    "summary_ready": os.path.isfile(notes.paths.summary_html(key))}
        return {"exists": True, "doc": d, "stages": notes.stage_view(d),
                "listen": listen.summary(kind, key),
                "html": common.html_name(kind, key, int(d.get("factor") or common.DEFAULT_FACTOR))}

    @router.post("/api/lecture/{kind}/{key}/init")
    async def lecture_init(kind: str, key: str, request: Request):
        """노트 만들기 — 요약반은 이론 요약 노트에서, 종합반은 승인된 요약반 노트에서."""
        _need(kind, key)
        b = await _body(request)
        try:
            d = notes.init(kind, key, factor=int(b.get("factor") or common.DEFAULT_FACTOR),
                           redo=bool(b.get("redo")))
            return {"ok": True, "slides": len(notes.slides(d))}
        except Exception as e:                               # noqa: BLE001
            raise _bad(e) from e

    @router.post("/api/lecture/{kind}/{key}/stage")
    async def lecture_stage(kind: str, key: str, request: Request):
        """단계 실행(잡) — stage: say|read|fig|expand|build. redo 면 채운 장도 다시."""
        _need(kind, key)
        b = await _body(request)
        st = str(b.get("stage") or "")
        _busy()
        d = notes.load(kind, key)
        if not d:
            raise HTTPException(status_code=409, detail="노트가 없습니다 — 먼저 [노트 만들기] 를 누르세요.")
        label = dict((s["stage"], s["label"]) for s in notes.stage_view(d)).get(st, st)
        job = registry.create(KIND_JOB, f"{notes.KIND_LABEL[kind]} · {key} · {label}", [key])

        def work(j):
            registry.item(j, key, status="running")
            try:
                r = stages.run(kind, key, st, log=lambda s, j=j: registry.log(j, s),
                               cancelled=lambda j=j: bool(j.get("cancel_requested")),
                               redo=bool(b.get("redo")), sections=b.get("sections"),
                               model=str(b.get("model") or ""), effort=b.get("effort") or None)
                registry.item(j, key, status="done", output=str(r.get("changed", r.get("deck_dir", ""))))
                registry.finish(j, "done", result=r)
            except Exception as e:                           # noqa: BLE001
                registry.item(j, key, status="error", error=str(e))
                registry.log(j, f"(문제) {type(e).__name__}: {e}", force=True)
                registry.finish(j, "error", error=str(e))

        registry.spawn(job, work)
        return registry.view(job)

    @router.post("/api/lecture/{kind}/{key}/approve")
    async def lecture_approve(kind: str, key: str, request: Request):
        """사람 승인 — 승인해야 다음 단계가 열린다. 듣기 검수는 필요 인원이 다 들어야 된다."""
        _need(kind, key)
        b = await _body(request)
        st = str(b.get("stage") or "")
        d = notes.load(kind, key)
        if not d:
            raise HTTPException(status_code=404, detail="노트가 없습니다.")
        view = {s["stage"]: s for s in notes.stage_view(d)}
        if st not in view or not view[st]["human"]:
            raise HTTPException(status_code=400, detail="승인하는 단계가 아닙니다.")
        if st == "listen":
            ls = listen.summary(kind, key)
            if not ls["ready"]:
                raise HTTPException(status_code=409, detail=(
                    f"듣기 검수가 덜 끝났습니다 — {ls['done']}/{ls['total']}장 · 안 닫힌 지적 {ls['open_fixes']}개."))
        elif view[st]["status"] not in ("done", "approved"):
            raise HTTPException(status_code=409, detail="아직 실행하지 않은 단계입니다.")
        elif b.get("on", True) and (left := stages.incomplete(d, st)):
            # 대단원 일부만 돌린 채 승인하면 다음 단계가 빈 장을 들고 간다.
            raise HTTPException(status_code=409, detail=(
                f"아직 안 채운 장이 {len(left)}개 있습니다({', '.join(left[:6])}…) — 이 단계를 한 번 더 실행하세요."))
        notes.set_stage(d, st, "approved" if b.get("on", True) else "done")
        notes.save(d)
        return {"ok": True, "stages": notes.stage_view(d)}

    @router.put("/api/lecture/{kind}/{key}/slide/{sid}")
    async def lecture_slide(kind: str, key: str, sid: str, request: Request):
        """장 하나 고치기 — say · read · fig · title · body. 낭독이 바뀌면 그 장의 OK 는 낡는다."""
        _need(kind, key)
        b = await _body(request)
        d = notes.load(kind, key)
        if not d:
            raise HTTPException(status_code=404, detail="노트가 없습니다.")
        try:
            r = notes.edit_slide(d, sid, b)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"없는 장입니다: {sid}") from e
        notes.save(d)
        return r

    @router.get("/api/lecture/{kind}/{key}/html")
    async def lecture_html(kind: str, key: str):
        """원고 HTML — 지금 원천에서 바로 구워 보여 준다(저장도 한다)."""
        _need(kind, key)
        d = notes.load(kind, key)
        if not d:
            raise HTTPException(status_code=404, detail="노트가 없습니다.")
        p = notes.write_html(d)
        return FileResponse(p, media_type="text/html; charset=utf-8")

    @router.post("/api/lecture/{kind}/{key}/open")
    async def lecture_open(kind: str, key: str):
        """빌드 결과 폴더(덱 · narration · RENDER.txt)를 탐색기로 연다."""
        _need(kind, key)
        p = stages.deck_dir(kind, key)
        if not os.path.isdir(p):
            raise HTTPException(status_code=404, detail="아직 빌드하지 않았습니다.")
        os.startfile(p)                                      # noqa: S606
        return {"ok": True, "path": p}

    # ── 듣기 검수 ──────────────────────────────────────────────────────────
    @router.get("/api/lecture/{kind}/{key}/audio/{sid}")
    async def lecture_audio(kind: str, key: str, sid: str):
        """그 장의 소리. 없으면 지금 굽는다(영상과 같은 엔진·목소리). GET 이라 LAN 검수자도 된다."""
        _need(kind, key)
        try:
            p = await listen.synth(kind, key, sid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=f"없는 장입니다: {sid}") from e
        except Exception as e:                               # noqa: BLE001
            raise _bad(e) from e
        return FileResponse(p, media_type="audio/mpeg")

    @router.post("/api/lecture/{kind}/{key}/tts")
    async def lecture_tts(kind: str, key: str):
        """과목 하나의 미리듣기를 통째로 굽는다(잡). 검수자들이 기다리지 않게 미리."""
        _need(kind, key)
        _busy()
        loop = asyncio.get_running_loop()
        job = registry.create(KIND_JOB, f"미리듣기 굽기 · {key}", [key])

        def work(j):
            try:
                r = listen.bake_all(kind, key, loop, log=lambda s, j=j: registry.log(j, s),
                                    cancelled=lambda j=j: bool(j.get("cancel_requested")))
                registry.item(j, key, status="done", output=f"{r['made']}개 구움 · {r['had']}개 있음")
                registry.finish(j, "done", result=r)
            except Exception as e:                           # noqa: BLE001
                registry.item(j, key, status="error", error=str(e))
                registry.finish(j, "error", error=str(e))

        registry.spawn(job, work)
        return registry.view(job)

    @router.get("/api/lecture/{kind}/{key}/reviews")
    async def lecture_reviews(kind: str, key: str, reviewer: str = ""):
        """집계 + (이름을 주면) 그 사람이 어디까지 들었는지."""
        _need(kind, key)
        out = listen.summary(kind, key)
        if reviewer:
            out["mine"] = listen.mine(kind, key, reviewer)
        return out

    @router.post("/api/lecture/{kind}/{key}/review")
    async def lecture_review(kind: str, key: str, request: Request):
        """판정 한 줄 — {reviewer, id, verdict: ok|fix, memo, suggest}. LAN 검수자도 쓴다."""
        _need(kind, key)
        b = await _body(request)
        try:
            return listen.judge(kind, key, reviewer=str(b.get("reviewer") or ""),
                                sid=str(b.get("id") or ""), verdict=str(b.get("verdict") or ""),
                                memo=str(b.get("memo") or ""), suggest=str(b.get("suggest") or ""))
        except KeyError as e:
            raise HTTPException(status_code=404, detail="없는 장입니다.") from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/lecture/{kind}/{key}/resolve")
    async def lecture_resolve(kind: str, key: str, request: Request):
        """지적 처리 — action: applied(수정안을 낭독에 반영) | dismissed(기각)."""
        _need(kind, key)
        b = await _body(request)
        try:
            return listen.resolve(kind, key, ref=int(b.get("ref") or 0), action=str(b.get("action") or ""))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    return router
