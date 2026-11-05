"""/api/ebook — 이북 시험지(07/) 굽기.

★ 핸들러는 `async def` 가 아니다. PDF 를 sync_playwright 로 찍는데, 그건 asyncio
  루프 안에서 못 돈다(`deck_capture` 에서 겪은 함정). `def` 면 FastAPI 가 스레드에서 돌린다.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Body, HTTPException

from services.book import paths
from services.export import answerbook, ebookexam


def setup_ebook_routes() -> APIRouter:
    router = APIRouter(prefix="/api/ebook", tags=["ebook"])

    @router.get("/status")
    def status():
        return ebookexam.status()

    @router.post("/build")
    def build(body: dict = Body(default={})):
        want = [str(r) for r in (body.get("rounds") or [])]
        have = paths.round_codes()
        rcs = [r for r in want if r in have] if want else have
        if not rcs:
            raise HTTPException(400, "구울 회차가 없습니다 — _rounds/ 에 집필된 회차가 있어야 합니다.")
        pdf = body.get("pdf", True) is not False
        results = []
        for rc in rcs:
            try:
                results.append(ebookexam.build_round(rc, pdf=pdf))
            except Exception as e:                               # noqa: BLE001
                results.append({"round_code": rc, "error": str(e)})
        return {"results": results, **ebookexam.status()}

    @router.post("/answers")
    def answers(body: dict = Body(default={})):
        """교재 정답·해설편 — 고른 회차(기본: 구운 회차 앞 5개)의 정답·해설을 한 권으로 → 07/_textbook/"""
        have = paths.round_codes()
        want = [str(r) for r in (body.get("rounds") or [])]
        rcs = [r for r in want if r in have] if want else have[:5]
        if not rcs:
            raise HTTPException(400, "회차가 없습니다 — _rounds/ 에 집필된 회차가 있어야 합니다.")
        return answerbook.build(rcs, pdf=body.get("pdf", True) is not False)

    @router.post("/open")
    def open_folder(body: dict = Body(default={})):
        rc = str(body.get("round") or "")
        target = ebookexam.round_dir(rc) if rc else ebookexam.ebook_dir()
        if not os.path.isdir(target):
            target = paths.book_dir()
        os.startfile(target)                  # noqa: S606  (로컬 단일 사용자 앱)
        return {"ok": True, "path": target}

    return router
