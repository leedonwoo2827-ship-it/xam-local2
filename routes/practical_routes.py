"""/api/practical — 실기(작업형) 트랙.

스캔 뜨기는 필기와 같은 `/api/ocr/render` 를 쓴다(PDF → 페이지 이미지는 시험 종류와 무관).
여기는 실기 판독 · 쪽/회차 확인표 · 판독 결과 보기/고치기만 맡는다.
"""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, HTTPException, Request

from services.jobs import registry
from services.ocr import project
from services.practical import read as pread


def _parse_pages(text: str, all_pages: list[int]) -> list[int]:
    """「1-15, 20」 → [1..15, 20]. 있는 쪽만 남긴다."""
    want: set[int] = set()
    for part in re.split(r"[,\s]+", (text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*[-~]\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            want.update(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            want.add(int(part))
        else:
            raise ValueError(f"쪽 범위를 읽지 못했습니다: {part!r} — 예: 1-15, 20")
    return [p for p in all_pages if p in want]


def setup_practical_routes() -> APIRouter:
    router = APIRouter(prefix="/api/practical", tags=["practical"])

    @router.get("/overview")
    async def overview():
        if not project.ocr_dir():
            return {"exists": False, "srcs": [],
                    "error": "판독 폴더가 정해지지 않았습니다 — 작업 폴더를 먼저 고르세요."}
        srcs = []
        for src in project.rendered_srcs():
            rows = pread.page_table(src)
            srcs.append({
                "src": src, "pages": rows,
                "total": len(rows), "read": sum(1 for r in rows if r["read"]),
                "cost_usd": round(sum(r["cost_usd"] or 0 for r in rows), 2),
            })
        running = registry.running("practical-read")
        return {"exists": True, "ocr_dir": project.ocr_dir(), "srcs": srcs,
                "running": registry.view(running) if running else None}

    @router.get("/review")
    async def review(src: str = "", round: int = 0):
        """문항 단위 검수 — 회차를 안 주면 회차 목록만."""
        from services.practical import review as prev
        srcs = project.rendered_srcs()
        src = src or (srcs[0] if srcs else "")
        if not src:
            return {"src": "", "rounds": [], "items": []}
        out = {"src": src, "rounds": prev.rounds(src)}
        if round:
            out.update(prev.round_items(src, round))
        return out

    @router.delete("/page/{src}/{page}")
    async def delete_page(src: str, page: int):
        """이 쪽 판독 결과 삭제 — 다시 판독하려는 것. 확정본은 건드리지 않는다."""
        return {"ok": pread.remove(src, page)}

    @router.post("/finalize")
    async def finalize(request: Request):
        """확정 — 이 쪽이 속한 **회차 전체**를 01/practical/ 에 문항마다 다시 쓴다."""
        from services.practical import finalize as pfin
        b = await request.json()
        src, page = str(b.get("src") or ""), int(b.get("page") or 0)
        rnd = int(b.get("round") or 0)
        if not rnd:
            row = next((r for r in pread.page_table(src) if r["page"] == page), None)
            rnd = int((row or {}).get("round") or 0)
        if not rnd:
            raise HTTPException(status_code=400, detail="이 쪽의 회차를 모릅니다 — 회차를 먼저 넣으세요.")
        # ★ 스레드에서 — 그림을 자르는 동안 다른 요청(쪽 열기·저장, 필기 화면)이 기다리지 않게
        from starlette.concurrency import run_in_threadpool
        return await run_in_threadpool(pfin.finalize_round, src, rnd)

    @router.post("/item-fix")
    async def item_fix(request: Request):
        """검수 카드에서 문제 하나의 묶음·번호·배점을 고친다."""
        from services.practical import review as prev
        b = await request.json()
        try:
            it = prev.fix_item(str(b.get("src") or ""), int(b.get("page") or 0), int(b.get("idx") or 0),
                               part=b.get("part"), no=b.get("no"), points=b.get("points"),
                               figure_bbox=b["figure_bbox"] if "figure_bbox" in b else "keep")
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "item": it}

    @router.post("/read")
    async def do_read(request: Request):
        """실기 판독 잡. `pages` 가 「1-15」 같은 글이면 그 쪽만, 비우면 미판독 전부."""
        body = await request.json() if await request.body() else {}
        src = str(body.get("src") or "").strip()
        if not src:
            raise HTTPException(status_code=400, detail="src 가 없습니다.")
        all_pages = project.list_pages(src)
        if not all_pages:
            raise HTTPException(status_code=400, detail="뜬 스캔이 없습니다 — ① 스캔 뜨기를 먼저 누르세요.")
        overwrite = bool(body.get("overwrite"))
        text_only = bool(body.get("text_only"))      # 원문만 채우기 — 카드는 그대로
        try:
            pages = _parse_pages(str(body.get("pages") or ""), all_pages) if body.get("pages") else all_pages
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if text_only:
            pages = [p for p in pages if overwrite or not ((pread.load(src, p) or {}).get("ocr_text") or "").strip()]
        elif not overwrite:
            pages = [p for p in pages if pread.load(src, p) is None]
        if not pages:
            raise HTTPException(status_code=400,
                                detail="판독할 쪽이 없습니다 — 이미 다 읽었습니다(다시 읽기를 켜면 덮어씁니다).")
        try:
            job = pread.start(src, pages, overwrite=overwrite, text_only=text_only)
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return registry.view(job)

    # ── 실기 문제 집필 ──────────────────────────────────────────────────
    @router.get("/author/overview")
    async def author_overview(rounds: str = "1-10"):
        from services.practical import author as pa
        try:
            want = _parse_pages(rounds, list(range(1, 41)))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        running = registry.running("practical-author")
        return {"sources": pa.sources_ready(), "src_dir": pa.src_dir(), "out_dir": pa.out_root(),
                "rows": pa.status(want),
                "running": registry.view(running) if running else None}

    @router.post("/author")
    async def author_start(request: Request):
        """실기 집필 잡 — rounds 「1-10」, overwrite 면 쓴 묶음도 다시 쓴다."""
        from services.practical import author as pa
        b = await request.json() if await request.body() else {}
        try:
            want = _parse_pages(str(b.get("rounds") or "1-10"), list(range(1, 41)))
            have = pa.sources_ready()
            miss = sorted({pa.source_round(m) for m in want} - set(have))
            if miss:
                raise ValueError(f"확정본이 없는 바탕 회차가 있습니다: {miss} — OCR 검수에서 확정하세요.")
            job = pa.start(want, overwrite=bool(b.get("overwrite")))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return registry.view(job)

    @router.get("/author/item")
    async def author_item(round: int, part: int, no: int):
        from services.practical import author as pa
        p = os.path.join(pa.round_dir(round), f"{round:02d}-{part}-{no:02d}.md")
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail="아직 쓰지 않은 문항입니다.")
        with open(p, encoding="utf-8") as f:
            return {"md": f.read(), "path": p}

    @router.post("/pagemap")
    async def set_pagemap(request: Request):
        """③ 확인표에서 사람이 고친 쪽 종류·회차."""
        body = await request.json()
        try:
            ent = pread.set_pagemap(str(body.get("src") or ""), int(body.get("page") or 0),
                                    kind=body.get("kind"),
                                    round_=body.get("round"))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "entry": ent}

    @router.get("/page/{src}/{page}")
    async def get_page(src: str, page: int):
        d = pread.load(src, page)
        png = project.scan_png(src, page)
        size = None
        if os.path.isfile(png):
            from PIL import Image
            with Image.open(png) as im:          # 머리만 읽는다 — 가볍다
                size = list(im.size)
        # ★ 화면에는 줄인 이미지를 준다(원본 6417px · 13.7MB). 드래그 좌표는 scan_size(원본)로 되돌린다.
        return {"src": src, "page": page, "read": d,
                "scan": f"/api/ocr/scan/{src}/{page}?w=2400",
                "scan_size": size,
                "has_scan": size is not None}

    @router.post("/page/{src}/{page}")
    async def save_page(src: str, page: int, request: Request):
        """④ 사람이 고친 판독 결과. JSON 그대로 받되 최소 모양만 본다."""
        body = await request.json()
        if not isinstance(body, dict) or body.get("page_kind") not in pread.KINDS:
            raise HTTPException(status_code=400,
                                detail=f"page_kind 는 {', '.join(pread.KINDS)} 중 하나여야 합니다.")
        for k in ("problem_items", "answer_entries"):
            if not isinstance(body.get(k, []), list):
                raise HTTPException(status_code=400, detail=f"{k} 는 배열이어야 합니다.")
        body["src"], body["page"] = src, int(page)
        body["_edited"] = True
        return {"ok": True, "path": pread.save(src, page, body)}

    return router
