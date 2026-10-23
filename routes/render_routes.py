"""/api/render — 번들 상태 · 사전점검 · 렌더 잡.
   /api/jobs   — 렌더·발행 공용 잡 조회 (셸의 최근 작업 목록도 이걸 쓴다)
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core.speak import speak_numbers
from services.book import paths
from services.jobs import jobstore, registry
from services.render import bundles, lexicon, precheck, runner, speech

logger = logging.getLogger(__name__)


def _need_bundle(code: str) -> None:
    """번들 코드 형식 검사 — 네 곳이 같은 문구를 되풀이하고 있었다."""
    if not paths.parse_bundle(code):
        raise HTTPException(status_code=400, detail=f"번들 코드 형식이 잘못됐습니다: {code!r}")


def setup_render_routes() -> APIRouter:
    router = APIRouter(tags=["render"])

    # ── 번들 ────────────────────────────────────────────────────────────────
    @router.get("/api/render/env")
    async def env():
        return runner.env_info()

    @router.get("/api/render/bundles")
    async def list_bundles():
        items = bundles.scan_all()
        counts = {"done": 0, "stale": 0, "missing": 0, "broken": 0}
        for i in items:
            counts[i["status"]] = counts.get(i["status"], 0) + 1
        return {"count": len(items), "counts": counts, "items": items}

    @router.get("/api/render/bundles/{code}")
    async def one_bundle(code: str):
        _need_bundle(code)
        return {"info": bundles.scan_one(code), "toc": bundles.review_toc(code)}

    @router.get("/api/render/bundles/{code}/scenes")
    async def bundle_scenes(code: str):
        """씬별 슬라이드 · 음성 · 자막 — 화면 바닥의 실행 판이 이걸 쓴다."""
        _need_bundle(code)
        d = bundles.scenes(code)
        if not d["ok"]:
            raise HTTPException(status_code=404, detail=d.get("error") or "씬을 읽을 수 없습니다.")
        return d

    # ── 발음대본 ────────────────────────────────────────────────────────────
    #
    # 자막은 그대로 두고 **발음만** 고친다. 두 값은 script.json 의 `narration`(자막)과
    # `narration_text`(발음)로 갈리고, 손수정은 `<번들>_speech.json` 에 남아 재베이크를
    # 견딘다(services/render/speech.py 머리말).
    @router.get("/api/render/bundles/{code}/speech")
    async def get_speech(code: str):
        _need_bundle(code)
        d = speech.read(code)
        d["stale_scenes"] = speech.stale_scenes(code)
        return d

    @router.post("/api/render/bundles/{code}/speech")
    async def put_speech(code: str, request: Request):
        """그 씬의 **자막·발음**을 저장한다. 둘 다 비면 덮어쓰기를 지운다."""
        _need_bundle(code)
        body = await request.json()
        try:
            scene = int(body.get("scene"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="scene 이 없습니다.") from None
        try:
            # `from` = 고칠 때의 자막 **원문**(대조용) · `subtitle` = 고친 자막
            return speech.save(code, scene, body.get("text") or "",
                               src=body.get("from") or "",
                               subtitle=body.get("subtitle") or "")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @router.post("/api/render/bundles/{code}/resynth")
    async def do_resynth(code: str, request: Request):
        """그 씬 wav 하나만 다시 만든다. mp4·통합자막은 그대로 — 번들 재렌더가 낸다."""
        _need_bundle(code)
        body = await request.json()
        try:
            scene = int(body.get("scene"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="scene 이 없습니다.") from None
        # ★ 렌더와 같은 TTS 엔진(같은 GPU·모델)을 쓴다. 동시에 돌리면 둘 다 느려지거나
        #   모델 적재에서 부딪힌다 — 렌더는 원래 동시 1개만 허용한다.
        if registry.running("render"):
            raise HTTPException(
                status_code=409,
                detail="렌더가 돌고 있습니다 — 같은 엔진을 쓰므로 끝난 뒤에 하세요.")
        try:
            return await speech.resynth(code, scene, text=body.get("text") or "")
        except (ValueError, RuntimeError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # ── 용어 사전 ───────────────────────────────────────────────────────────
    #
    # 발음 고침의 **1차 자리**다. 한 줄 넣으면 전 품목에 걸리고 자막은 원문을 지킨다.
    # 씬마다 손으로 고치는 것보다 싸므로, 되풀이되는 용어는 여기로 올린다.
    @router.get("/api/render/lexicon")
    async def get_lexicon(round: str = ""):
        """두 사전을 **같이** 준다 — 품목 사전과 공용 사전.

        ★ 전에는 공용 하나만 냈다. `DENSE_RANK` 를 고치려고 이 박스를 열면 없어서
          사람이 못 찾았다(2026-08-26) — 그것은 품목 사전에 있다.
        """
        d = lexicon.read()
        d["product"] = lexicon.read_product()
        # 사전에 없어서 낱자로 읽히는 약어 — 빈 화면을 주지 않으려고 후보를 같이 낸다
        d["candidates"] = lexicon.candidates(round)
        return d

    @router.post("/api/render/lexicon")
    async def put_lexicon(request: Request):
        """`scope` 가 `common` 이면 공용 사전, 아니면 **품목 사전**(기본)."""
        body = await request.json()
        common = (body.get("scope") or "product") == "common"
        try:
            if body.get("remove"):
                return (lexicon.remove if common else lexicon.remove_product)(
                    body.get("term") or "")
            return (lexicon.save if common else lexicon.save_product)(
                body.get("term") or "", body.get("say") or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/api/render/speak-numbers")
    async def do_speak_numbers(request: Request):
        """숫자를 소리대로 — **발음 칸 안에서만** 쓴다(자막에서 다시 만들지 않는다)."""
        body = await request.json()
        return {"text": speak_numbers(body.get("text") or "")}

    @router.get("/api/render/bundles/{code}/precheck")
    async def do_precheck(code: str):
        _need_bundle(code)
        return precheck.run(code)

    # ── 렌더 잡 ─────────────────────────────────────────────────────────────
    @router.post("/api/render/bake")
    async def start_bake(request: Request):
        """★ 05/ 를 **굽는다**(deck.html · script · lesson). mp4 는 안 만든다.

        전에는 입구가 `tools/bake_all.py` 뿐이었다 — 앱에 버튼이 없어서, 05/ 가
        없는 책은 영상 화면에서 100번들이 `broken` 으로 뜨고 [미완성만 렌더] 는
        「렌더할 번들이 없습니다」 로 끝났다(2026-08-20 실측). 굽는 단계가 화면에
        없으면 사람이 다음에 무엇을 눌러야 하는지 알 수 없다.

        ★ 모델을 부르지 않는다. 룰베이스 조립이라 100번들이 몇 분이다.
        ★ 1:1 이 깨진 번들은 **그것만 건너뛴다** — `bake_one` 이 쓰기 전에 예외를
          내므로 반쪽 파일이 남지 않는다.
        """
        from services.render import bake

        body = await request.json() if await request.body() else {}
        codes = body.get("codes")
        all_codes = paths.all_bundles()
        if codes in (None, "all"):
            codes = all_codes
        elif codes == "unbaked":
            codes = [b["code"] for b in bundles.scan_all() if b["status"] == "broken"]
        elif isinstance(codes, str):
            codes = [codes]
        codes = [c for c in codes if c in all_codes]
        if not codes:
            raise HTTPException(status_code=400, detail="구울 번들이 없습니다.")
        if (busy := registry.running("bake")):
            raise HTTPException(409, f"이미 굽고 있습니다 — {busy.get('label')}")

        job = registry.create("bake", f"슬라이드 굽기 {len(codes)}번들", codes)

        def work(j):
            ok = err = 0
            for code in codes:
                if j.get("cancel_requested"):
                    registry.item(j, code, status="skipped", error="취소됨")
                    continue
                registry.update(j, current=code)
                registry.item(j, code, status="running")
                try:
                    r = bake.bake_one(code)
                except Exception as e:                       # noqa: BLE001
                    err += 1
                    registry.item(j, code, status="error", error=str(e))
                    registry.log(j, f"[{code}] 건너뜀 — {e}", force=True)
                    continue
                ok += 1
                registry.item(j, code, status="done")
                registry.log(j, f"[{code}] 슬라이드 {r.get('slides', '?')}장 · "
                                f"씬 {r.get('scenes', '?')}개", force=True)
            registry.log(j, f"끝 — {ok}번들 구웠고 {err}번들 건너뜀.", force=True)
            registry.finish(j, "done" if ok else "error",
                            result={"ok": ok, "error": err})

        registry.spawn(job, work)
        return registry.view(job)

    # ── 강의덱(PPTX) ────────────────────────────────────────────────────────
    # ★ 여기서부터가 **슬라이드의 진실**이다. deck.html 을 캡처하던 자리를 pptx 가
    #   가져갔고, 사람이 PowerPoint 로 확정한 그 파일에서 PNG 를 뽑는다.
    #   순서: ② 슬라이드 만들기 → ③ 장수 확정 → ④ 이미지 뽑기 → 렌더.

    def _round_list(codes) -> list[str]:
        all_rc = paths.round_codes()
        if codes in (None, "all"):
            return all_rc
        if isinstance(codes, str):
            codes = [codes]
        return [c for c in codes if c in all_rc]

    @router.get("/api/render/slides/status")
    async def slides_status(rd: str = ""):
        """번들마다 pptx 유무·장수·채움·손질·이미지. 화면의 표가 이걸 읽는다."""
        from services.deck import pptxdeck, slideimg

        codes = [rd] if rd else paths.round_codes()
        rounds = [pptxdeck.round_status(rc) for rc in codes]
        return {"rounds": rounds, "powerpoint": slideimg.available(),
                "scale": pptxdeck.spec_scale(), "exam": pptxdeck.exam_label()}

    @router.get("/api/render/slides/pages")
    async def slides_pages(rd: str):
        """③의 장수 표 — 문항별 문제/해설 장수·배율·채움. 지정값(lock)을 얹어서 준다."""
        from services.deck import pptxdeck

        if not paths.parse_round_code(rd):
            raise HTTPException(400, f"회차 코드가 아닙니다: {rd!r}")
        return pptxdeck.pages_table(rd)

    @router.put("/api/render/slides/pages")
    async def save_slides_pages(rd: str, request: Request):
        """장수 표 저장 → `_deck-export/NN회.pages.json`. 다시 만들 때 이 값을 지킨다."""
        from services.deck import pptxdeck

        if not paths.parse_round_code(rd):
            raise HTTPException(400, f"회차 코드가 아닙니다: {rd!r}")
        body = await request.json()
        return pptxdeck.save_pages_table(rd, body.get("questions") or [])

    @router.get("/api/render/slides/pptx")
    async def download_pptx(b: str):
        _need_bundle(b)
        p = paths.bundle_pptx(b)
        if not os.path.isfile(p):
            raise HTTPException(404, f"{b}: deck.pptx 가 없습니다.")
        return FileResponse(
            p, filename=f"{b}.pptx",
            media_type="application/vnd.openxmlformats-officedocument"
                       ".presentationml.presentation")

    @router.post("/api/render/slides/open")
    async def open_slide_target(request: Request):
        """PowerPoint 로 pptx 를, 또는 탐색기로 그 폴더를 연다.

        ★ pptx 는 **`04-2/` 한 폴더에** 다 모여 있다(`01회_강의_11-20.pptx` …).
          `rd` 를 주면 그 회차의 5편을 한꺼번에 연다 — PowerPoint 가 창을 편마다
          하나씩 띄운다. `which="folder"` 는 `04-2/` 를 탐색기로 연다.
        """
        from services.deck import pptxdeck

        body = await request.json() if await request.body() else {}
        b = body.get("bundle") or ""
        rd = body.get("rd") or ""
        which = body.get("which") or "pptx"

        if rd:
            if not paths.parse_round_code(rd):
                raise HTTPException(400, f"회차 코드가 아닙니다: {rd!r}")
            files = [paths.bundle_pptx(x) for x in pptxdeck.bundles_of(rd)]
            files = [f for f in files if os.path.isfile(f)]
            if not files:
                raise HTTPException(404, f"{rd}: pptx 가 없습니다 — ②를 먼저 돌리세요.")
            opened = []
            for f in files:
                try:
                    os.startfile(f)       # noqa: S606  (로컬 단일 사용자 앱)
                    opened.append(os.path.basename(os.path.dirname(
                        os.path.dirname(f))))
                except Exception as e:    # noqa: BLE001
                    raise HTTPException(500, f"열지 못했습니다: {e}") from e
            return {"ok": True, "count": len(opened), "bundles": opened}

        if b and which == "images":
            _need_bundle(b)
            target = paths.bundle_images_dir(b)
        elif b and which == "pptx":
            _need_bundle(b)
            target = paths.bundle_pptx(b)
        else:
            # 기본은 pptx 가 다 모여 있는 폴더 — 사람이 제일 자주 여는 자리다.
            target = paths.pptx_dir()
        if not os.path.exists(target):
            raise HTTPException(404, f"없습니다: {target}")
        try:
            os.startfile(target)          # noqa: S606  (로컬 단일 사용자 앱)
        except Exception as e:            # noqa: BLE001
            raise HTTPException(500, f"열지 못했습니다: {e}") from e
        return {"ok": True, "path": target}

    @router.post("/api/render/slides")
    async def start_slides(request: Request):
        """② 회차 → 번들마다 `deck.pptx` + `pages.json` + 씬 다시 매기기."""
        from services.deck import pptxdeck

        body = await request.json() if await request.body() else {}
        codes = _round_list(body.get("rounds"))
        if not codes:
            raise HTTPException(400, "만들 회차가 없습니다.")
        scale = body.get("scale")
        rebake = bool(body.get("rebake"))
        busy = registry.running("slides")
        if busy:
            raise HTTPException(409, f"이미 만들고 있습니다 — {busy.get('label')}")

        job = registry.create("slides", f"슬라이드(PPTX) {len(codes)}회차", codes)

        def work(j):
            ok = err = 0
            for rc in codes:
                if j.get("cancel_requested"):
                    registry.item(j, rc, status="skipped", error="취소됨")
                    continue
                registry.update(j, current=rc)
                registry.item(j, rc, status="running")
                try:
                    r = pptxdeck.build_round(
                        rc, scale=scale, rebake=rebake,
                        log=lambda m, _j=j: registry.log(_j, m, force=True))
                except Exception as e:                       # noqa: BLE001
                    err += 1
                    registry.item(j, rc, status="error", error=str(e))
                    registry.log(j, f"[{rc}] 실패 — {e}", force=True)
                    continue
                ok += 1
                registry.item(j, rc, status="done")
                registry.log(j, f"[{rc}] 편 {r['parts']} · 장 {r['slides']} · "
                                f"채움 {r['fill_median']} · 넘침 "
                                f"{len(r['overflow'])}", force=True)
            registry.log(j, f"끝 — {ok}회차 만들었고 {err}회차 실패.", force=True)
            registry.finish(j, "error" if err and not ok else "done",
                            result={"ok": ok, "error": err})

        registry.spawn(job, work)
        return registry.view(job)

    @router.post("/api/render/slideimg")
    async def start_slideimg(request: Request):
        """④ 확정한 pptx → `images/slide_NN.png`. PowerPoint 로 뽑는다."""
        from services.deck import pptxdeck, slideimg

        av = slideimg.available()
        if not av.get("ok"):
            raise HTTPException(503, av.get("why") or "PowerPoint 를 쓸 수 없습니다.")

        body = await request.json() if await request.body() else {}
        codes = body.get("codes")
        if codes in (None, "all"):
            codes = [b for rc in paths.round_codes()
                     for b in pptxdeck.bundles_of(rc)]
        elif isinstance(codes, str) and paths.parse_round_code(codes):
            codes = pptxdeck.bundles_of(codes)
        elif isinstance(codes, str):
            codes = [codes]
        codes = [c for c in codes if paths.parse_bundle(c)]
        if not codes:
            raise HTTPException(400, "이미지를 뽑을 번들이 없습니다.")
        busy = registry.running("slideimg")
        if busy:
            raise HTTPException(409, f"이미 뽑고 있습니다 — {busy.get('label')}")

        job = registry.create("slideimg", f"슬라이드 이미지 {len(codes)}번들", codes)

        def work(j):
            ok = err = 0
            # ★ PowerPoint 인스턴스를 **하나로** 잡고 배치를 돈다. 번들마다 잡았다
            #   놓으면 마지막 문서를 닫는 순간 PowerPoint 가 끝나고, 다음 호출이
            #   죽는 인스턴스를 붙잡아 터진다(실측 100번들 중 23개 실패).
            with slideimg.Session() as ss:
                for code in codes:
                    if j.get("cancel_requested"):
                        registry.item(j, code, status="skipped", error="취소됨")
                        continue
                    registry.update(j, current=code)
                    registry.item(j, code, status="running")
                    try:
                        r = slideimg.export_bundle(code, session=ss)
                    except Exception as e:                   # noqa: BLE001
                        err += 1
                        registry.item(j, code, status="error", error=str(e))
                        registry.log(j, f"[{code}] 실패 — {e}", force=True)
                        continue
                    ok += 1
                    registry.item(j, code, status="done")
                    registry.log(j, f"[{code}] {r['slides']}장", force=True)
            registry.log(j, f"끝 — {ok}번들 뽑았고 {err}번들 실패.", force=True)
            registry.finish(j, "error" if err and not ok else "done",
                            result={"ok": ok, "error": err})

        registry.spawn(job, work)
        return registry.view(job)

    @router.post("/api/render/jobs")
    async def start_render(request: Request):
        body = await request.json()
        codes = body.get("codes")
        no_audio = bool(body.get("no_audio"))
        keep_scratch = bool(body.get("keep_scratch"))
        stop_on_error = bool(body.get("stop_on_error", True))

        all_codes = paths.all_bundles()
        if codes == "all" or codes is None:
            codes = all_codes
        elif codes == "missing":
            codes = [b["code"] for b in bundles.scan_all()
                     if b["status"] in ("missing", "stale")]
        elif isinstance(codes, str):
            codes = [codes]
        codes = [c for c in codes if c in all_codes]
        if not codes:
            raise HTTPException(status_code=400, detail="렌더할 번들이 없습니다.")

        busy = registry.running("render")
        if busy:
            raise HTTPException(
                status_code=409,
                detail=("이미 렌더가 돌고 있습니다 — 동시에 하나만 실행됩니다. "
                        f"진행 중: {busy.get('label')} ({busy.get('current') or '준비 중'})"))
        try:
            job = runner.start(codes, no_audio=no_audio, keep_scratch=keep_scratch,
                               stop_on_error=stop_on_error)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return registry.view(job)

    return router


def setup_job_routes() -> APIRouter:
    """잡 조회는 렌더·발행이 공유한다."""
    router = APIRouter(prefix="/api/jobs", tags=["jobs"])

    @router.get("")
    @router.get("/")
    async def list_jobs(limit: int = 20, kind: str = ""):
        return {"jobs": registry.list_jobs(limit=limit, kind=kind)}

    @router.get("/{job_id}")
    async def get_job(job_id: str, log_from: int = 0):
        job = registry.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return registry.view(job, log_from=log_from)

    @router.get("/{job_id}/log")
    async def full_log(job_id: str):
        p = jobstore.log_path(job_id)
        if not p:
            raise HTTPException(status_code=404, detail="로그 파일이 없습니다.")
        return FileResponse(p, media_type="text/plain; charset=utf-8",
                            filename=f"{job_id}.log")

    @router.post("/{job_id}/cancel")
    async def cancel(job_id: str):
        job = registry.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        if job.get("kind") == "render":
            ok = runner.cancel(job_id)
        else:
            ok = registry.request_cancel(job_id)
        if not ok:
            raise HTTPException(status_code=409, detail="이미 끝난 작업입니다.")
        return {"ok": True}

    return router
