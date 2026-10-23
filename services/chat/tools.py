# -*- coding: utf-8 -*-
"""채팅의 앱 도구 — in-process MCP 서버 `xam`.

★ 도구가 앱 함수를 직접 부르지 않고 **앱 자신의 REST API 를 루프백으로** 부른다.
  화면 버튼과 같은 길을 타야 같은 게이트를 지난다 — 5파일 저장 트랜잭션의 409/423,
  `require_pd()`, 집필 잡의 동시 실행 금지, 렌더 1개 제한. 서비스 함수를 직접 부르면
  그 검사들이 라우트 쪽에 있는 것은 전부 건너뛴다.
  루프백이라 LAN 보기 전용 미들웨어(core/lan.py)에도 걸리지 않는다.

    api_get    GET /api/...            자유 (읽기)
    api_call   POST·PUT·DELETE /api/... 사람 승인 (session.can_use_tool 이 카드로 묻는다)
    navigate   가운데 화면을 #/... 로    자유 (화면만 바꾼다)

★ 계층 규약: FastAPI 를 import 하지 않는다(services/* 공통).
"""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

SERVER = "xam"
GET = f"mcp__{SERVER}__api_get"
CALL = f"mcp__{SERVER}__api_call"
NAV = f"mcp__{SERVER}__navigate"
AUTO = (GET, NAV)               # 승인 없이 쓰는 도구
NEEDS_APPROVAL = (CALL,)

# 모델 컨텍스트에 그대로 들어간다. 문항 720개 목록이 통째로 오면 한 번에 수십만 자다.
MAX_CHARS = 60_000
# 렌더·빌드는 잡을 만들고 바로 돌아온다(잡 id). 오래 붙잡는 호출이 없어야 한다.
TIMEOUT = 180


def _ok(text: str, err: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if err:
        out["is_error"] = True
    return out


def _check_path(path: str) -> str:
    p = (path or "").strip()
    if not p.startswith("/api/"):
        raise ValueError("path 는 /api/ 로 시작해야 합니다.")
    if p.startswith("/api/chat"):
        # 채팅이 채팅을 부르면 승인 대기 중인 자기 자신을 기다리게 된다.
        raise ValueError("/api/chat 은 도구로 부를 수 없습니다.")
    return p


def _http(base: str, method: str, path: str, body: Any = None) -> str:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None and method != "GET":
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        status = e.code
    text = raw.decode("utf-8", "replace")
    if len(text) > MAX_CHARS:
        text = (text[:MAX_CHARS]
                + f"\n…(잘림: 전체 {len(text):,}자. 쿼리 파라미터로 범위를 좁혀 다시 부르십시오)")
    return f"HTTP {status}\n{text}"


def build_server(sess):
    """세션마다 하나. `navigate` 가 그 세션의 이벤트 줄에 써야 해서 클로저로 묶는다."""
    from claude_agent_sdk import create_sdk_mcp_server, tool

    @tool("api_get",
          "앱의 읽기 API 를 부른다(GET). 현황·목록·상태·사전점검·검증 결과를 볼 때 쓴다. "
          "path 는 /api/ 로 시작하고 쿼리스트링을 포함해도 된다. 엔드포인트 목록은 시스템 프롬프트에 있다.",
          {"type": "object", "properties": {"path": {"type": "string"}},
           "required": ["path"]})
    async def api_get(args):
        try:
            p = _check_path(args.get("path", ""))
        except ValueError as e:
            return _ok(str(e), True)
        return _ok(await asyncio.to_thread(_http, sess.base_url, "GET", p))

    @tool("api_call",
          "앱의 쓰기·실행 API 를 부른다(POST·PUT·DELETE) — 집필 시작, 굽기, 렌더, 빌드, 저장, "
          "이론 원고 단계 실행 등. ★ 부를 때마다 사람이 화면에서 승인해야 실행된다. "
          "why 에 무엇을 왜 하는지 한 문장으로 쓴다(승인 카드에 그대로 보인다).",
          {"type": "object",
           "properties": {"method": {"type": "string", "enum": ["POST", "PUT", "DELETE"]},
                          "path": {"type": "string"},
                          "body": {"type": "object"},
                          "why": {"type": "string"}},
           "required": ["method", "path", "why"]})
    async def api_call(args):
        try:
            p = _check_path(args.get("path", ""))
        except ValueError as e:
            return _ok(str(e), True)
        m = (args.get("method") or "POST").upper()
        if m not in ("POST", "PUT", "DELETE"):
            return _ok("method 는 POST·PUT·DELETE 중 하나입니다.", True)
        return _ok(await asyncio.to_thread(_http, sess.base_url, m, p, args.get("body") or {}))

    @tool("navigate",
          "가운데 작업 화면을 해시 라우트로 옮긴다(예: #/questions/m01-07, #/theory-video/datamodel). "
          "사람에게 결과를 보여 줄 때 쓴다. 데이터는 바꾸지 않는다.",
          {"type": "object", "properties": {"route": {"type": "string"}},
           "required": ["route"]})
    async def navigate(args):
        r = (args.get("route") or "").strip()
        if not r.startswith("#/"):
            r = "#/" + r.lstrip("#/")
        sess.emit({"t": "navigate", "route": r})
        return _ok(f"화면을 {r} 로 옮겼습니다.")

    return create_sdk_mcp_server(SERVER, tools=[api_get, api_call, navigate])
