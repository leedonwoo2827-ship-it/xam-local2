"""/api/chat — 우측 채팅 패널 (v2).

    GET    /api/chat/sessions               대화 목록
    POST   /api/chat/sessions               새 대화
    DELETE /api/chat/{sid}                  대화 지우기
    GET    /api/chat/{sid}/events?since=N   커서 폴링 (0.7초)
    POST   /api/chat/{sid}/send             {text, ctx}  — 턴을 시작하고 바로 돌아온다
    POST   /api/chat/{sid}/approve          {id, ok, note}  — 승인 카드
    POST   /api/chat/{sid}/interrupt        중단

★ 엔드포인트 목록을 시스템 프롬프트에 넣는다 — `request.app.routes` 에서 뽑으므로
  손으로 고칠 목록이 없다. /api/chat 자신과 정적·페이지 라우트는 뺀다.
★ 계층 규약: JSON 만 돌려준다. 무거운 일은 services/chat/session.py.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Request

from services.book import paths
from services.chat import session as chat

_CTX_KEYS = (("route", "화면"), ("note", "노트"), ("question", "문항"), ("bundle", "번들"),
             ("subject", "과목"), ("book", "책"), ("pd", "품목"), ("selection", "선택한 글"))


def _walk(routes, prefix: str = ""):
    """★ 이 FastAPI 는 include_router 한 라우터를 `_IncludedRouter` 하나로 감싸 둔다
    (app.routes 가 31개뿐이다). 펼쳐서 실제 APIRoute 까지 내려간다."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            ctx = getattr(r, "include_context", None)
            yield from _walk(inner.routes, prefix + (getattr(ctx, "prefix", "") or ""))
        else:
            yield prefix, r


def _endpoints(request: Request) -> List[Tuple[str, str, str]]:
    out = []
    for prefix, r in _walk(request.app.routes):
        p = prefix + getattr(r, "path", "")
        if not p.startswith("/api/") or p.startswith("/api/chat"):
            continue
        doc = ((getattr(r, "endpoint", None) and r.endpoint.__doc__) or "").strip()
        doc = doc.splitlines()[0].strip() if doc else ""
        for m in sorted(getattr(r, "methods", None) or ()):
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append((m, p, doc[:120]))
    out.sort(key=lambda x: (x[1], x[0]))
    return out


def _ctx_note(ctx: Dict[str, Any]) -> str:
    lines = []
    for k, label in _CTX_KEYS:
        v = ctx.get(k)
        if v:
            v = str(v)
            lines.append(f"{label}: {v[:1500]}")
    return "\n".join(lines)


def setup_chat_routes() -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])

    def _get(sid: str) -> chat.ChatSession:
        s = chat.get(sid)
        if s is None:
            raise HTTPException(status_code=404, detail="대화를 찾지 못했습니다.")
        return s

    @router.get("/status")
    async def status(route: str = ""):
        """오른쪽 칸 기본 화면 — 지금 하는 일 · 다음에 할 일. 모델을 부르지 않는다."""
        from services.chat import status as st
        return st.compute(route)

    @router.get("/sessions")
    async def sessions():
        """대화 목록 (최근 것부터)."""
        return {"items": chat.listing()}

    @router.post("/sessions")
    async def new_session():
        """새 대화."""
        return chat.create().meta()

    @router.delete("/{sid}")
    async def delete(sid: str):
        if not chat.remove(sid):
            raise HTTPException(status_code=404, detail="대화를 찾지 못했습니다.")
        return {"ok": True}

    @router.get("/{sid}/events")
    async def events(sid: str, since: int = 0):
        return _get(sid).view(max(0, since))

    @router.post("/{sid}/send")
    async def send(sid: str, request: Request):
        s = _get(sid)
        body = await request.json()
        text = (body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="보낼 내용이 없습니다.")
        ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
        # 도구가 부를 주소 — run.bat 의 PORT 로 바뀌어도 맞도록 이 요청이 들어온 곳을 쓴다.
        s.base_url = f"http://127.0.0.1:{request.url.port or 80}"
        cwd = paths.book_dir()
        system = chat.build_system(_endpoints(request))
        chat.trim_live()
        try:
            s.send(text, ctx_note=_ctx_note(ctx), system=system, cwd=cwd)
        except RuntimeError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        return {"ok": True}

    @router.post("/{sid}/approve")
    async def approve(sid: str, request: Request):
        body = await request.json()
        ok = _get(sid).resolve(str(body.get("id") or ""), bool(body.get("ok")),
                               (body.get("note") or "").strip())
        if not ok:
            raise HTTPException(status_code=409, detail="이미 처리됐거나 없는 승인 요청입니다.")
        return {"ok": True}

    @router.post("/{sid}/interrupt")
    async def interrupt(sid: str):
        _get(sid).interrupt()
        return {"ok": True}

    return router
