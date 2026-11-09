"""/api/practical — 실기(작업형) 트랙.

스캔 뜨기는 필기와 같은 `/api/ocr/render` 를 쓴다(PDF → 페이지 이미지는 시험 종류와 무관).
여기는 실기 판독 · 쪽/회차 확인표 · 판독 결과 보기/고치기만 맡는다.
"""
from __future__ import annotations

import glob
import json
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


def paths_book() -> str:
    from services.book import paths
    return paths.book_dir()


def setup_practical_routes() -> APIRouter:
    router = APIRouter(prefix="/api/practical", tags=["practical"])

    @router.get("/track")
    async def track():
        """왼쪽 메뉴가 트랙을 고르는 근거 — 시험정보 format, 없으면 실기 판독 유무."""
        from services.authoring import parts
        spec = parts.active() or {}
        fmt = str(spec.get("format") or "").strip()
        read = False
        if not fmt and project.ocr_dir():
            try:
                read = any(any(r["read"] for r in pread.page_table(s)) for s in project.rendered_srcs())
            except Exception:                                   # noqa: BLE001 — 표시용
                read = False
        practical = fmt in ("task", "written") or (not fmt and read)
        return {"track": fmt or ("task" if read else "mcq"), "practical": practical,
                "spec_id": spec.get("id") or "", "label": spec.get("label") or ""}

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

    # ── 구조화 MD로 정리(실기) — 확정본 01/practical 문항 목록 · 보기 ─────────────
    @router.get("/items")
    async def items(q: str = "", unverified: int = 0):
        from services.practical import finalize as pfin
        d = pfin.out_dir()
        rows = []
        for f in sorted(glob.glob(os.path.join(d, "*.json"))):
            stem = os.path.basename(f)[:-5]
            if not re.fullmatch(r"\d{2}-\d-\d{2}", stem):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    j = json.load(fh)
            except (OSError, ValueError) as e:
                rows.append({"id": stem, "error": f"읽지 못함: {e}"})
                continue
            p0 = (j.get("problems") or [{}])[0]
            ans = j.get("answer") or {}
            pages = sorted({int(p.get("page")) for p in j.get("problems") or [] if p.get("page")}
                           | {int(x) for x in ans.get("pages") or []})
            rows.append({
                "id": stem, "round": j.get("round"), "part": j.get("part"), "no": j.get("no"),
                "head": bool(j.get("head")), "points": p0.get("points"),
                "verified": bool(j.get("verified")), "flags": j.get("flags") or [],
                "figures": len(j.get("figures") or []) + len(j.get("answer_figures") or []),
                "has_answer": bool(ans), "pages": pages,
                "preview": (p0.get("lead") or "")[:160],
            })
        n, nv = len(rows), sum(1 for r in rows if r.get("verified"))
        out = rows
        if unverified:
            out = [r for r in out if not r.get("verified")]
        if q:
            out = [r for r in out if q in r["id"] or q in (r.get("preview") or "")]
        return {"dir": d, "count": n, "verified": nv, "filtered": len(out), "items": out}

    @router.get("/item/{stem}")
    async def item(stem: str):
        from services.practical import finalize as pfin
        if not re.fullmatch(r"\d{2}-\d-\d{2}", stem):
            raise HTTPException(status_code=400, detail="문항 id 는 RR-P-NN 입니다.")
        base = os.path.join(pfin.out_dir(), stem)
        if not os.path.isfile(base + ".json"):
            raise HTTPException(status_code=404, detail="확정본에 없는 문항입니다.")
        with open(base + ".json", encoding="utf-8") as fh:
            j = json.load(fh)
        md = open(base + ".md", encoding="utf-8").read() if os.path.isfile(base + ".md") else ""
        return {"id": stem, "json": j, "md": md, "path": base + ".md", "src": next(iter(project.rendered_srcs()), "")}

    @router.get("/img/{which}/{name}")
    def img(which: str, name: str):
        """확정본(01)·집필(02) 원고가 부르는 그림 — images/ 아래 파일만."""
        from fastapi.responses import FileResponse
        from services.practical import author as pa
        from services.practical import finalize as pfin
        if which == "01":
            d = os.path.join(pfin.out_dir(), "images")
        elif re.fullmatch(r"m\d{2}", which):
            d = os.path.join(pa.round_dir(int(which[1:])), "images")
        else:
            raise HTTPException(status_code=400, detail="which 는 01 또는 mNN")
        p = os.path.join(d, os.path.basename(name))
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail="그림이 없습니다.")
        return FileResponse(p)

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

    # ── 1부 빌드(실기) — 실습파일·그림·검증 ─────────────────────────────────
    @router.get("/build/overview")
    async def build_overview(rounds: str = "1-10"):
        from services.practical import build as pb
        try:
            want = _parse_pages(rounds, list(range(1, 41)))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        running = registry.running("practical-build")
        return {"out_dir": os.path.join(paths_book(), "06", "practical"), "rows": pb.status(want),
                "running": registry.view(running) if running else None}

    @router.post("/build")
    async def build_start(request: Request):
        from services.practical import build as pb
        b = await request.json() if await request.body() else {}
        try:
            want = _parse_pages(str(b.get("rounds") or "1-10"), list(range(1, 41)))
            job = pb.start(want)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return registry.view(job)

    @router.post("/build/open")
    async def build_open(round: int = 0):
        """탐색기로 06/practical(/mNN) 를 연다 — 로컬 앱이라 서버가 곧 사용자 PC 다."""
        from services.practical import build as pb
        d = pb.out_dir(round) if round else os.path.join(paths_book(), "06", "practical")
        if not os.path.isdir(d):
            raise HTTPException(status_code=404, detail="아직 빌드하지 않았습니다.")
        os.startfile(d)                                          # noqa: S606 — 로컬 전용
        return {"ok": True, "dir": d}

    # ── 3부 HTML 문제집(실기) — 시험지·해설·실습파일·대본 → 07/mNN ───────────────
    @router.get("/ebook/overview")
    async def ebook_overview(rounds: str = "1-10"):
        from services.practical import ebook as pe
        try:
            want = _parse_pages(rounds, list(range(1, 41)))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        running = registry.running("practical-actions")
        return {"out_dir": os.path.join(paths_book(), "07"), "rows": pe.status(want),
                "running": registry.view(running) if running else None}

    @router.post("/ebook")
    def ebook_build(body: dict):
        """굽기 — sync def(Playwright PDF 는 asyncio 루프 안에서 못 돈다)."""
        from services.practical import ebook as pe
        try:
            want = _parse_pages(str(body.get("rounds") or "1-10"), list(range(1, 41)))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        out = []
        for m in want:
            if not os.path.isdir(os.path.join(paths_book(), "02", "practical", f"m{m:02d}")):
                continue
            try:
                out.append(pe.build_round(m, pdf=bool(body.get("pdf", True))))
            except Exception as e:                              # noqa: BLE001
                out.append({"round": m, "error": str(e)})
        return {"built": out}

    @router.post("/ebook/open")
    async def ebook_open(round: int = 0):
        from services.practical import ebook as pe
        d = pe.out_dir(round) if round else os.path.join(paths_book(), "07")
        if not os.path.isdir(d):
            raise HTTPException(status_code=404, detail="아직 굽지 않았습니다.")
        os.startfile(d)                                          # noqa: S606 — 로컬 전용
        return {"ok": True, "dir": d}

    @router.post("/actions")
    async def actions_start(request: Request):
        """종합본 영상 입력 — 모범답안 → 녹화 조작 단계(lesson.yaml). 문항마다 Claude 1회."""
        from services.practical import actions as pact
        b = await request.json() if await request.body() else {}
        try:
            want = _parse_pages(str(b.get("rounds") or "6-10"), list(range(1, 41)))
            job = pact.start(want, overwrite=bool(b.get("overwrite")))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return registry.view(job)

    # ── 문항 교정(실기) — 02/practical 문항 ──────────────────────────────────
    @router.get("/edit/items")
    async def edit_items(round: int = 0, q: str = "", unreviewed: int = 0):
        from services.practical import author as pa
        rows = pa.list_items([round] if round else None)
        n, nr = len(rows), sum(1 for r in rows if r.get("reviewed"))
        if unreviewed:
            rows = [r for r in rows if not r.get("reviewed")]
        if q:
            rows = [r for r in rows if q in r["id"] or q in (r.get("preview") or "") or q in (r.get("scenario") or "")
                    or any(q.upper() == str(f).upper() for f in r.get("functions") or [])]
        return {"count": n, "reviewed": nr, "filtered": len(rows), "items": rows}

    @router.get("/edit/item/{stem}")
    async def edit_item(stem: str):
        from services.practical import author as pa
        try:
            return pa.read_item(stem)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @router.put("/edit/item/{stem}")
    async def edit_save(stem: str, request: Request):
        from services.practical import author as pa
        b = await request.json()
        if not isinstance(b, dict):
            raise HTTPException(status_code=400, detail="JSON 객체를 보내세요.")
        for k in ("instructions", "figures"):
            if k in b and not isinstance(b[k], list):
                raise HTTPException(status_code=400, detail=f"{k} 는 배열이어야 합니다.")
        if "answer" in b and not isinstance(b["answer"], dict):
            raise HTTPException(status_code=400, detail="answer 는 객체여야 합니다.")
        if "sheets" in b and not isinstance(b["sheets"], list):
            raise HTTPException(status_code=400, detail="sheets 는 배열이어야 합니다.")
        try:
            return pa.save_item(stem, b)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

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
