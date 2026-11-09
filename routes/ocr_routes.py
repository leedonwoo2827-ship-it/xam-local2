"""/api/ocr — 도구 #1(OCR 검수) 의 페이지 단위 작업.

레이어는 이 앱의 UX 원칙을 따른다.
    위층 패널  `/api/ocr/overview`            페이지 목록 (고르는 곳)
    아래층 바탕 `/api/ocr/draft/{src}/{page}`  그 페이지 작업 (일하는 곳)

`services/scan_routes.py` 는 **확정된 `01/*.md` 를 한 문항씩** 손보는 화면이고,
여기는 **초안을 페이지 단위로** 검수해 그 `01/*.md` 를 만드는 화면이다. 둘 다 남는다.

★ 판독(OCR)은 여기에 없다. Claude Code 창이 `raw_pages/*.png` 를 읽어 초안을 쓴다.
"""
from __future__ import annotations

import io
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from services.book import paths
from services.jobs import registry
from services.ocr import answers as ocr_answers
from services.ocr import checks, draft, finalize, pdfrender, project, readpage

logger = logging.getLogger(__name__)


def setup_ocr_routes() -> APIRouter:
    router = APIRouter(prefix="/api/ocr", tags=["ocr"])

    def _need_project() -> None:
        if not project.exists():
            raise HTTPException(
                status_code=503,
                detail=(f"OCR 판독 폴더를 찾을 수 없습니다: "
                        f"{project.ocr_dir() or '(미지정)'}. "
                        "좌하단 작업 폴더 패널에서 지정하거나 .env 의 XAM_OCR 을 채우세요."))

    # ── 위층 패널: 페이지 목록 ──────────────────────────────────────────────
    @router.get("/overview")
    async def overview():
        """회차별로 묶은 페이지 목록 + 책 정보. ★ 캐시하지 않는다 —
        Claude Code 창에서 새 초안을 만들면 패널만 다시 열어도 보여야 한다."""
        info = project.info()
        if not info["exists"]:
            return {"exists": False, "info": info, "pages": [], "finalized": {},
                    "error": (f"OCR 판독 폴더가 없습니다: "
                              f"{project.ocr_dir() or '(미지정)'}")}

        pm = project.page_map()

        # ★ '이어지는 면' — 문항이 0개인데 **다른 페이지의 문항이 이 쪽을 물고 있는** 면.
        #   걸친 문항은 시작한 쪽이 갖는다(`readpage` 규칙). 그래서 뒷부분만 있는 면은
        #   판독이 끝났어도 문항이 0개다. 그걸 「초안」으로 표시하면 미완처럼 보여서
        #   사람이 없애려 한다(2026-08-18: "이걸 없앨려면 어떻게 해야 해요?").
        #   ★ 모델이 준 플래그를 쓰지 않는다 — source_pages 는 코드가 쓴 값이라 더 믿을 만하다.
        carried: set = set()
        for _s in project.visible_srcs():
            for _p in project.list_pages(_s):
                for q in ((draft.load(_s, _p) or {}).get("questions") or []):
                    for sp in (q.get("source_pages") or []):
                        if int(sp) != int(_p):
                            carried.add((_s, int(sp)))

        pages = []
        for src in project.visible_srcs():
            entry = project.source_entry(src)
            for page in project.list_pages(src):
                meta = pm.get(f"{src}:{page}", {})
                d = draft.load(src, page)
                qs = (d or {}).get("questions") or []
                pages.append({
                    "src": src,
                    "page": page,
                    "role": entry.get("role") or "문제",
                    "pair": entry.get("pair") or "",
                    "round": meta.get("round") or (d or {}).get("round"),
                    "round_label": (meta.get("round_label")
                                    or (d or {}).get("round_label") or ""),
                    "question_range": meta.get("question_range"),
                    "has_draft": d is not None,
                    "n_questions": len(qs),
                    "n_verified": sum(1 for q in qs if q.get("verified")),
                    # 앞 면 문항의 뒷부분만 있는 면 — 문항 0개가 정상이다
                    "continuation": (not qs) and (src, page) in carried,
                })

        # 확정 현황 — 01/ 의 {RR}-{NN}.md 를 회차별로 센다(상수 없음).
        finalized: dict[str, int] = {}
        stage = os.path.join(paths.book_dir(), "01")
        if os.path.isdir(stage):
            for f in sorted(os.listdir(stage)):
                if f.endswith(".md") and not f.startswith("_") and len(f) >= 5:
                    finalized[f[:2]] = finalized.get(f[:2], 0) + 1

        gate_ok, gate_msg = checks.gate_ok()
        return {"exists": True, "info": info, "pages": pages,
                "finalized": finalized,
                "gate": {"ok": gate_ok, "message": gate_msg}}

    # ── 아래층 바탕: 페이지 초안 ────────────────────────────────────────────
    @router.get("/draft/{src}/{page}")
    async def get_draft(src: str, page: int):
        _need_project()
        d = draft.load_or_skeleton(src, page)
        entry = project.source_entry(src)
        d["_meta"] = {
            "source_pdf": project.source_pdf_name(src),
            "role": entry.get("role") or "문제",
            "pair": entry.get("pair") or "",
            "scan": f"/api/ocr/scan/{src}/{page}",
            "has_scan": os.path.isfile(project.scan_png(src, page)),
            "pages": project.list_pages(src),
            "questions_per_round": project.questions_per_round(),
            "subjects": project.subjects(),
        }
        return d

    @router.post("/draft/{src}/{page}")
    async def post_draft(src: str, page: int, request: Request):
        """초안 저장. 확정과 달리 게이트를 보지 않는다 — 초안은 작업 중인 값이다."""
        _need_project()
        body = await request.json()
        body.pop("_meta", None)
        try:
            p, wrote = draft.save(src, page, body)
        except PermissionError as e:
            raise HTTPException(status_code=423, detail=(
                f"초안을 저장하지 못했습니다: {os.path.basename(str(e.filename or ''))}. "
                "편집기에서 열어 두었다면 닫고 다시 시도하세요.")) from e
        return {"ok": True, "path": p, "wrote": wrote}

    @router.delete("/draft/{src}/{page}")
    async def delete_draft(src: str, page: int):
        """이 페이지 초안 삭제. 확정본(01/*.md)은 건드리지 않는다."""
        _need_project()
        return draft.remove(src, page)

    # ── 스캔 이미지 · 크롭 미리보기 ─────────────────────────────────────────
    # ★ 아래 둘은 **`async def` 가 아니다.** 이미지를 여는 일은 무겁다 — 컴활2급 실기 스캔은 한 장이
    #   6417×9506(13.7MB)이라 크롭 한 번에 1.2초였고, async 핸들러에서 하면 그동안 **서버 전체가 멈춘다**
    #   (실측 2026-11-09: 그림이 많은 쪽을 열자 다른 요청이 45초씩 밀려 화면이 비었다).
    #   일반 def 는 FastAPI 가 스레드 풀에서 돌리므로 다른 요청을 막지 않는다. 결과는 디스크에 캐시한다.
    import threading
    _DEC = {"key": None, "img": None}
    _DEC_LOCK = threading.Lock()

    def _decoded(p: str):
        key = (p, os.path.getmtime(p))
        with _DEC_LOCK:
            if _DEC["key"] != key:
                from PIL import Image
                with Image.open(p) as im:
                    im.load()
                    _DEC["img"], _DEC["key"] = im.copy(), key
            return _DEC["img"]

    def _cache_dir(kind: str) -> str:
        d = os.path.join(project.ocr_dir(), "data", "view_cache", kind)
        os.makedirs(d, exist_ok=True)
        return d

    @router.get("/scan/{src}/{page}")
    def scan_image(src: str, page: int, w: int = 0):
        """스캔 원본. `w` 를 주면 그 폭으로 줄인 JPEG(화면 보기용, 캐시) — 좌표는 원본 기준으로 쓴다."""
        p = project.scan_png(src, page)
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail=(
                f"스캔 이미지가 없습니다: {src} p.{page}. "
                "`python -m services.ocr.pdfrender` 로 렌더하세요."))
        if w <= 0:
            return FileResponse(p, media_type="image/png")
        w = max(400, min(int(w), 4000))
        out = os.path.join(_cache_dir("scan"), f"{src}_p{int(page):03d}_w{w}.jpg")
        if not os.path.isfile(out) or os.path.getmtime(out) < os.path.getmtime(p):
            from PIL import Image
            with Image.open(p) as im:
                if im.width <= w:
                    return FileResponse(p, media_type="image/png")
                im = im.convert("RGB")
                im.thumbnail((w, w * 10), Image.LANCZOS)
                tmp = out + ".tmp"
                im.save(tmp, format="JPEG", quality=85)
                os.replace(tmp, out)
        return FileResponse(out, media_type="image/jpeg")

    @router.get("/crop")
    def crop(src: str, page: int, x: int, y: int, w: int, h: int):
        """드래그한 영역 미리보기. 같은 영역은 캐시에서 바로 준다(원본이 바뀌면 다시 자른다)."""
        p = project.scan_png(src, page)
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail="스캔 이미지가 없습니다.")
        out = os.path.join(_cache_dir("crop"), f"{src}_p{int(page):03d}_{x}_{y}_{w}_{h}.png")
        if os.path.isfile(out) and os.path.getmtime(out) >= os.path.getmtime(p):
            return FileResponse(out, media_type="image/png")
        # ★ 한 쪽의 그림 여러 장이 동시에 온다 — 원본(6417×9506) 해독이 1.2초라 장마다 열면 그만큼 곱해진다.
        #   마지막에 연 쪽을 메모리에 하나 들고, 같은 쪽 크롭은 그것을 쓴다(잠금으로 한 번만 해독).
        img = _decoded(p)
        buf = io.BytesIO()
        img.crop((x, y, x + w, y + h)).save(buf, format="PNG", compress_level=1)
        data = buf.getvalue()
        try:
            tmp = out + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, out)
        except OSError:
            pass
        return Response(data, media_type="image/png")

    @router.get("/figure/{name}")
    async def figure(name: str):
        """확정된 그림 — 01/images/ 아래."""
        p = os.path.join(paths.book_dir(), "01", "images", os.path.basename(name))
        if not os.path.isfile(p):
            raise HTTPException(status_code=404, detail="그림 파일이 없습니다.")
        return FileResponse(p, media_type="image/png")

    # ── 확정 ────────────────────────────────────────────────────────────────
    @router.post("/finalize")
    async def do_finalize(request: Request):
        """`{src, page, questions:[…]}` → 01/{RR}-{NN}.md 기록 + 그림 크롭.

        ★ 확정 왕복 게이트를 먼저 본다. 통과하지 않는 렌더러로 확정하면 이미
          검수해 둔 01/*.md 가 조용히 바뀐다.
        """
        _need_project()
        body = await request.json()
        src = str(body.get("src") or "")
        page = int(body.get("page") or 0)
        questions = body.get("questions") or []
        if not src or not page:
            raise HTTPException(status_code=400, detail="src · page 가 필요합니다.")
        # ★ 게이트는 **이 면을 빼고** 본다. 이 면이 달라지는 것은 사람이 방금 고친
        #   것이고, 확정은 이 면의 문항만 쓴다. 전체로 보면 25번에 그림 하나 넣은 것이
        #   26번 확정까지 막는다 — 빠져나갈 길이 없는 자리였다(2026-08-19 실측).
        ok, msg = checks.gate_ok((src, page))
        if not ok:
            raise HTTPException(status_code=409, detail=msg)
        try:
            return finalize.finalize_page(src, page, questions)
        except finalize.LockedError as e:
            raise HTTPException(status_code=423, detail=str(e)) from e
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    # ── 검증 · 도구 ─────────────────────────────────────────────────────────
    @router.get("/verify")
    async def verify():
        """확정 왕복 게이트 + 회차 정합성. 화면의 `검증` 버튼이 쓴다."""
        return {"refinalize": checks.refinalize(),
                "rounds": checks.verify_all_rounds()}

    @router.get("/render/plan")
    async def render_plan():
        """00/ 의 PDF 를 어떻게 렌더할지. 중복·역할·짝이 여기서 보인다."""
        return pdfrender.run(dry=True)

    @router.post("/render")
    async def do_render(request: Request):
        """00/*.pdf → raw_pages/*.png. 이미 있는 소스는 건너뛴다(force 로 강제).

        ★ 여기만 `_need_project()` 를 쓰지 않는다. 이 단계는 판독 폴더를 **만드는**
          쪽이다 — 요구하면 닭-달걀이 된다. 판독 폴더를 지우고 `00/`+`01/` 만 남긴
          뒤 스캔을 다시 뜨려 할 때, 폴더가 없어서 503 이고 폴더는 이 버튼으로만
          생긴다(실측 2026-08-18: 판독 폴더를 지워도 되는지 물어보다 발견).
          `pdfrender.run()` 이 raw_pages 를 makedirs 하고, `plan()` 은 `00/` 만 본다.
        """
        if not project.ocr_dir():
            raise HTTPException(
                status_code=503,
                detail=("판독 폴더 위치가 정해지지 않았습니다 — 작업 폴더 패널에서 "
                        "지정하거나 .env 의 XAM_OCR 을 채우세요."))
        body = await request.json() if await request.body() else {}
        return pdfrender.run(force=bool(body.get("force")))

    @router.post("/read")
    async def do_read(request: Request):
        """**판독** — 스캔 PNG 를 읽어 초안을 쓴다. 잡으로 돈다(한 장 40~60초).

        `pages` 를 주면 그 페이지만, 없으면 **아직 판독되지 않은 페이지 전부**다 —
        151장을 매번 다시 읽지 않게 기본을 그렇게 둔다.
        """
        _need_project()
        body = await request.json() if await request.body() else {}
        src = str(body.get("src") or "").strip()
        if not src:
            raise HTTPException(status_code=400, detail="src 가 없습니다.")
        pages = [int(p) for p in (body.get("pages") or [])]
        overwrite = bool(body.get("overwrite"))
        if not pages:
            all_pages = project.list_pages(src)
            done = {p for s, p in draft.all_drafts(src)
                    if (draft.load(s, p) or {}).get("questions")}
            pages = [p for p in all_pages if overwrite or p not in done]
        if not pages:
            raise HTTPException(status_code=400,
                                detail="판독할 페이지가 없습니다 — 이미 다 읽었습니다.")
        try:
            job = readpage.start(src, pages, model=str(body.get("model") or ""),
                                 effort=(body.get("effort") or None),
                                 overwrite=overwrite)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return registry.view(job)

    @router.post("/answers/merge")
    async def merge_answers(request: Request):
        """분리형 교재의 정답·해설을 초안에 주입."""
        _need_project()
        body = await request.json() if await request.body() else {}
        r = ocr_answers.merge(body.get("src") or None,
                              body.get("round") or None,
                              force=bool(body.get("force")),
                              check=bool(body.get("check", True)))
        if not r["ok"]:
            raise HTTPException(status_code=404, detail=r["error"])
        return r

    return router
