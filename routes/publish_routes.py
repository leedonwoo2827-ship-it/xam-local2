"""/api/publish — 사전점검 · 빌드 · problems.json 검증 · FTP 목록 · 체크리스트.

발행은 '버튼 하나' 가 아니다. axexam 절차의 순서를 틀릴 수 없게 만드는 것이 이
화면의 일이다. 임포트는 브라우저 단계라서 우리가 대신 누를 수 없다.
"""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

from core.constants import PD_CODE, PUBLISH_DIR, SITE_BASE, SITE_PATH
from core.atomic_io import atomic_write_json
from services.book import paths
from services.jobs import registry
from services.publish import buildcheck, ftplist, validate

logger = logging.getLogger(__name__)

_STATE = os.path.join(PUBLISH_DIR, "checklist.json")


def _state_key(scope: str) -> str:
    """기록을 담을 칸 이름 — `<품목>|<단계>`.

    ★ 전에는 한 파일에 평평하게 담아서, **다른 품목의 체크가 그대로 보였다.**
      SQLD 를 발행하려고 열었더니 8월 4일 빅분기 기록이 다 켜져 있었다
      (2026-08-26). 발행 이력은 품목마다 다른 이야기다.
    """
    try:
        from services.publish import buildcheck
        pd = buildcheck.active_pd() or "?"
    except Exception:                                        # noqa: BLE001
        pd = "?"
    return f"{pd}|{'problems' if scope == 'problems' else 'video'}"


def _load_all() -> dict:
    if os.path.isfile(_STATE):
        try:
            with open(_STATE, encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            pass
    return {}


def _load_state(scope: str = "all") -> dict:
    """이 품목·이 단계의 기록만. 옛 평평한 기록은 읽지 않는다(다른 품목 것이다)."""
    d = _load_all().get(_state_key(scope))
    return d if isinstance(d, dict) else {}


def setup_publish_routes() -> APIRouter:
    router = APIRouter(prefix="/api/publish", tags=["publish"])

    @router.get("/preflight")
    async def preflight(scope: str = ""):
        """발행 사전점검. `scope=problems` 면 **1차(문제집)** 기준으로만 센다.

        ★ 발행은 2단계다 — 1차 «문제집», 2차 «영상». 범위 밖 그룹도 목록에는 그대로
          내려보내고(`out_of_scope`), 세지만 않는다. 사람이 "2차에 무엇이 남았는지"
          를 같이 봐야 다음을 안다.
        """
        r = validate.run(scope or validate.DEFAULT_SCOPE)
        if r.get("error"):
            raise HTTPException(status_code=503, detail=r["error"])
        return r

    @router.get("/env")
    async def env():
        e = buildcheck.env_info()
        # pd 가 안 정해진 폴더에서는 명령을 만들 수 없다 — 화면이 그 사실을 보여준다.
        try:
            e["command"] = buildcheck.command_text()
            e["pd_ok"] = True
        except ValueError as ex:
            e["command"] = ""
            e["pd_ok"] = False
            e["pd_error"] = str(ex)
        e["site"] = SITE_BASE + SITE_PATH
        return e

    @router.post("/build")
    async def build(request: Request):
        """axexam 의 build_check.py 를 --book/--pd 를 명시해 호출한다.

        오류(error)가 하나라도 있으면 시작하지 않는다. 경고는
        force_ignore_warnings 로 통과시킬 수 있다.
        """
        body = await request.json() if await request.body() else {}
        force = bool(body.get("force_ignore_warnings"))
        # ★ 1차(문제집)면 영상·유튜브·요약노트는 게이트에서 뺀다. 빌더는 영상이
        #   없어도 돈다(`build_check.py`: "없으면 영상 없음"), 임포트는 DELETE 를
        #   하지 않으므로 2차가 그 위에 덮어쓴다.
        scope = body.get("scope") or validate.DEFAULT_SCOPE

        pre = validate.run(scope)
        if pre.get("error"):
            raise HTTPException(status_code=503, detail=pre["error"])
        # ★ 목록도 **이 단계의 것만** 낸다. 개수는 범위 밖을 안 세는데 목록은 다
        #   담고 있어서, 1차인데 「mp4 · 요약노트 · summary_index」 가 경고로 줄줄이
        #   떴다 — 「경고 2건」 이라 적고 6줄을 보여 주니 무엇을 보라는 것인지 알 수
        #   없다(2026-08-26 실측).
        def _bad(level: str) -> list:
            return [c["label"] for g in pre["groups"] if not g.get("out_of_scope")
                    for c in g["checks"] if c["level"] == level and not c["ok"]]

        if pre["errors"]:
            bad = _bad("error")
            raise HTTPException(
                status_code=409,
                detail=(f"[{pre['scope_label']}] 사전점검 오류가 남아 있어 빌드를 시작하지 않았습니다 "
                        f"({pre['errors']}건).\n· " + "\n· ".join(bad[:8])))
        if pre["warnings"] and not force:
            bad = _bad("warn")
            raise HTTPException(
                status_code=409,
                detail=(f"경고 {pre['warnings']}건이 있습니다. 확인한 뒤 다시 누르면 "
                        "진행합니다.\n· " + "\n· ".join(bad[:8])))

        busy = registry.running("build")
        if busy:
            raise HTTPException(status_code=409, detail="이미 빌드가 돌고 있습니다.")
        try:
            job = buildcheck.start(scope)
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        return registry.view(job)

    @router.get("/problems")
    async def problems():
        """마지막으로 만들어진 problems.json 검증 (임포트 드라이런)."""
        return buildcheck.validate_problems_json()

    @router.get("/ftplist")
    async def get_ftplist(hash: int = 0):
        r = ftplist.build(with_hash=bool(hash))
        if not r["ok"]:
            raise HTTPException(status_code=409, detail=r.get("error") or "06/ 가 없습니다.")
        return r

    @router.post("/open")
    async def open_folder(request: Request):
        """탐색기로 폴더를 연다 — `out`(06/) · `videos`(모아 둔 mp4) · 그 밖은 발행 기록."""
        body = await request.json() if await request.body() else {}
        which = body.get("which") or "out"
        if which == "videos":
            target = os.path.join(paths.book_dir(), "_videos")
        elif which == "out":
            target = paths.out_dir()
        else:
            target = PUBLISH_DIR
        if not os.path.isdir(target):
            raise HTTPException(status_code=404, detail=f"폴더가 없습니다: {target}")
        try:
            os.startfile(target)          # noqa: S606  (로컬 단일 사용자 앱)
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"폴더를 열지 못했습니다: {e}") from e
        return {"ok": True, "path": target}

    @router.get("/ytmap")
    async def get_ytmap():
        """영상 매핑 상태 — 번들별 링크가 채워졌는지."""
        from services.publish import ytmap
        return ytmap.read()

    @router.post("/ytmap/sync")
    async def sync_ytmap(request: Request):
        """매핑 골격 생성 / 빠진 번들 채우기. **이미 넣은 링크는 건드리지 않는다.**

        빌더의 `--init-youtube-map` 은 "파일이 있으면 아무것도 안 함" 이라 회차가
        늘어난 뒤에는 쓸 수 없다. 그래서 여기서 증분으로 맞춘다.
        """
        from services.publish import ytmap
        body = await request.json() if await request.body() else {}
        try:
            return ytmap.sync(provider=(body.get("provider") or "").strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/ytmap/preview")
    async def preview_ytmap(request: Request):
        """붙여넣은/떨어뜨린 목록의 판정만 — **파일을 쓰지 않는다.**

        무엇이 새로 채워지고 무엇이 갈아끼워지는지 누르기 전에 보여 주는 자리다.
        같은 ID 가 두 자리에 붙었으면 `dup` 에 담겨 오고, 화면이 [반입] 을 막는다.
        """
        from services.publish import ytmap
        body = await request.json() if await request.body() else {}
        try:
            return ytmap.parse_text(body.get("text") or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/ytmap/paste")
    async def paste_ytmap(request: Request):
        """붙여넣은 목록으로 링크 72개를 한 번에 채운다.

        한 줄에서 번들코드와 ID/URL 을 각각 찾아 맞추므로 형식이 느슨해도 된다.
        번들이 72개라 손으로 넣으면 한 줄 밀려 영상이 엉뚱한 회차에 붙는다 —
        그건 영상을 봐야 알 수 있어서 되돌리기 비싸다.

        쓰기 전에 `.bak` 를 남긴다(`/ytmap/restore` 가 되돌린다). `force` 는 `dup`
        경고를 무릅쓰고 쓰는 탈출구다 — 화면은 기본적으로 보내지 않는다.
        """
        from services.publish import ytmap
        body = await request.json() if await request.body() else {}
        try:
            return ytmap.apply_text(body.get("text") or "",
                                    force=bool(body.get("force")))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.post("/ytmap/restore")
    async def restore_ytmap():
        """직전 반입을 되돌린다 — `.bak` 와 현재 파일을 맞바꾼다."""
        from services.publish import ytmap
        try:
            return ytmap.restore()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @router.post("/ytmap/open")
    async def open_ytmap():
        """매핑 파일을 기본 편집기로 연다 — 링크를 붙여넣는 자리."""
        from services.publish import ytmap
        p = ytmap.path()
        if not os.path.isfile(p):
            raise HTTPException(status_code=404,
                                detail=f"매핑 파일이 없습니다: {p} — [영상 매핑 만들기] 를 먼저 누르세요.")
        try:
            os.startfile(p)               # noqa: S606  (로컬 단일 사용자 앱)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"열지 못했습니다: {e}") from e
        return {"ok": True, "path": p}

    @router.get("/partial")
    async def get_partial():
        """problems.json 을 무엇으로 쪼갤 수 있는지 (회차·번들 목록)."""
        from services.publish import partial
        try:
            return partial.summary()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @router.post("/partial")
    async def make_partial(request: Request):
        """회차·번들·문항만 담은 부분 임포트 파일을 만든다.

        임포트가 DELETE 를 하지 않으므로(problem.php:13) 여기 없는 문항은 서버에 그대로
        남는다. 전체 714KB 를 다시 올리는 대신 회차 92KB · 문항 2.6KB 만 올린다.
        용량보다 **확인**이 이득이다 — 리포트가 '갱신 1' 만 찍으면 끝난다.
        """
        from services.publish import partial
        b = await request.json() if await request.body() else {}
        try:
            return partial.write(rounds=b.get("rounds") or None,
                                 bundles=b.get("bundles") or None,
                                 keys=b.get("keys") or None,
                                 label=(b.get("label") or "").strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    @router.get("/stage")
    async def get_stage():
        """업로드 폴더 상태 — 만들지 않고 본다."""
        from services.publish import stage
        return stage.summary()

    @router.post("/stage")
    async def make_stage(request: Request):
        """`_upload/` 를 **서버와 똑같은 모양**으로 만든다.

        올릴 것이 로컬 두 곳에서 서버 세 곳으로 가는데(06/ → /exam/,
        web/exam → /exam/, web/adm → /adm/), 그 매핑을 사람이 하면 반드시 틀린다.
        여기서 한 번 해 두면 폴더 하나를 /www/ 에 통째로 올리는 것으로 끝난다.
        """
        from services.publish import stage
        try:
            return stage.build()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

    @router.post("/stage/clear")
    async def clear_stage():
        """다 올린 뒤 지운다. 남겨 두면 다음에 무엇이 새것인지 헷갈린다."""
        import shutil
        from services.publish import stage
        d = stage.stage_dir()
        if os.path.isdir(d):
            shutil.rmtree(d)
        return {"ok": True, "dir": d}

    @router.post("/stage/open")
    async def open_stage():
        from services.publish import stage
        d = stage.stage_dir()
        if not os.path.isdir(d):
            raise HTTPException(status_code=404,
                                detail="업로드 폴더가 없습니다 — [업로드 폴더 만들기] 를 먼저 누르세요.")
        try:
            os.startfile(d)           # noqa: S606
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return {"ok": True, "dir": d}

    @router.post("/gather-videos")
    async def do_gather_videos():
        """mp4 100편을 한 폴더로 모은다 — 2차의 첫 일(드라이브 업로드)의 손잡이."""
        try:
            return ftplist.gather_videos()
        except Exception as e:                               # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.get("/checklist")
    async def get_checklist(scope: str = "all"):
        return {"pd": PD_CODE, "items": ftplist.server_checklist(scope),
                "state": _load_state(scope), "scope": scope}

    @router.put("/checklist")
    async def put_checklist(request: Request):
        """서버 단계 진행상태 기록.

        서버에서 되읽을 수 없으므로(/exam/.htaccess 가 .json 을 403) 이 로컬
        기록이 유일한 발행 이력이다.
        """
        body = await request.json()
        scope = (body.get("scope") or "all").strip()
        allst = _load_all()
        slot = _state_key(scope)
        state = allst.get(slot)
        if not isinstance(state, dict):
            state = {}
        key = (body.get("key") or "").strip()
        if not key:
            raise HTTPException(status_code=400, detail="key 가 없습니다.")
        state[key] = {
            "done": bool(body.get("done")),
            "note": (body.get("note") or "").strip(),
            "at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        }
        allst[slot] = state
        os.makedirs(PUBLISH_DIR, exist_ok=True)
        atomic_write_json(_STATE, allst, indent=2)
        return {"ok": True, "state": state, "scope": scope}

    return router
