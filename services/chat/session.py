# -*- coding: utf-8 -*-
"""채팅 세션 — 대화 하나 = `ClaudeSDKClient` 하나 = 그 전용 asyncio 루프 스레드 하나.

왜 클라이언트를 상주시키나
  `provider.ClaudeAuthor` 처럼 턴마다 `query()` 를 새로 띄우면 매번 CLI 를 띄우고
  하네스 접두(약 4만 토큰)의 캐시를 새로 만든다 — 실측 호출당 $0.25 다. 대화는 짧은
  턴이 이어지므로, 연결을 붙잡아 두고 같은 프로세스에 이어 묻는 편이 싸고 빠르다.

왜 전용 루프 스레드인가
  SDK 클라이언트는 자기를 만든 이벤트 루프에 묶인다. FastAPI 핸들러의 루프나 잡
  워커 스레드에서 번갈아 부르면 "attached to a different loop" 로 죽는다. 그래서
  세션마다 `run_forever` 루프를 하나 두고, 바깥은 `run_coroutine_threadsafe` 로만 넣는다.

화면과는 **커서 폴링**으로 만난다(잡 모델과 같다). 이벤트는 불변 목록이고 seq 가 인덱스다.
    user · seg(새 글 덩어리) · delta(글자) · text(스트리밍이 없을 때 통째로) ·
    tool · tool_done · approve · approved · denied · navigate · done · error · info

★ 계층 규약: FastAPI 를 import 하지 않는다.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_json
from core.constants import BASE_DIR, DATA_DIR

from . import prompt as _prompt
from . import tools as _tools

CHAT_DIR = os.path.join(DATA_DIR, "chat")
MAX_EVENTS = 6000
MAX_LIVE = 3                     # 동시에 살려 두는 CLI 프로세스 수 — 넘치면 오래된 것부터 닫는다
APPROVE_TIMEOUT = 30 * 60        # 승인 카드를 30분 내버려 두면 거절로 본다

# 승인 없이 쓰는 것. 나머지(api_call)는 can_use_tool 이 카드로 묻는다.
FREE_TOOLS = ["Read", "Grep", "Glob", "WebSearch", "WebFetch", *_tools.AUTO]
BLOCKED = ["Bash", "Write", "Edit", "NotebookEdit", "Task", "KillShell"]

_TOOL_KO = {"Read": "읽기", "Grep": "찾기", "Glob": "훑기", "WebSearch": "웹 검색",
            "WebFetch": "웹 읽기", _tools.GET: "앱 조회", _tools.CALL: "앱 실행",
            _tools.NAV: "화면 이동", "ToolSearch": "도구 찾기"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _brief(name: str, inp: Dict[str, Any]) -> str:
    """도구 사용 한 줄 — 코캣의 "코캣: … 사용 중" 줄에 해당한다."""
    if name in (_tools.GET, _tools.CALL):
        m = inp.get("method", "GET") if name == _tools.CALL else "GET"
        return f"{m} {inp.get('path', '')}"
    if name == _tools.NAV:
        return str(inp.get("route", ""))
    v = (inp.get("file_path") or inp.get("pattern") or inp.get("path")
         or inp.get("query") or inp.get("url") or "")
    v = str(v).replace("\\", "/")
    if "/" in v and not v.startswith("http"):
        v = "/".join(v.rstrip("/").split("/")[-2:])
    return v[:160]


class ChatSession:
    def __init__(self, sid: str, data: Optional[Dict[str, Any]] = None):
        d = data or {}
        self.sid = sid
        self.title: str = d.get("title") or "새 대화"
        self.created: str = d.get("created") or _now()
        self.updated: str = d.get("updated") or self.created
        self.claude_session: str = d.get("claude_session") or ""
        self.cwd: str = d.get("cwd") or ""
        self.events: List[Dict[str, Any]] = list(d.get("events") or [])
        self.cost: float = float(d.get("cost") or 0.0)
        self.base_url = "http://127.0.0.1:8871"
        self.busy = False
        self._lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._streamed = False
        self.last_used = time.monotonic()

    # ── 이벤트 ──────────────────────────────────────────────────────────────
    def emit(self, ev: Dict[str, Any]) -> None:
        with self._lock:
            ev = dict(ev, seq=len(self.events), at=_now())
            self.events.append(ev)
            if len(self.events) > MAX_EVENTS:
                # 인덱스가 커서다 — 앞을 잘라내면 화면의 커서가 틀어진다. 대신 새 대화를 권한다.
                pass

    def view(self, since: int) -> Dict[str, Any]:
        with self._lock:
            return {"sid": self.sid, "title": self.title, "busy": self.busy,
                    "next": len(self.events), "cost": round(self.cost, 4),
                    "events": self.events[since:],
                    "pending": [e for e in self.events
                                if e["t"] == "approve" and e["id"] in self._pending]}

    def meta(self) -> Dict[str, Any]:
        return {"sid": self.sid, "title": self.title, "created": self.created,
                "updated": self.updated, "busy": self.busy, "cost": round(self.cost, 4)}

    # ── 저장 ────────────────────────────────────────────────────────────────
    def _compact(self) -> List[Dict[str, Any]]:
        """디스크에는 delta 를 합친 형태로 둔다. 다시 열 때는 seq 0 부터 새로 읽는다."""
        out: List[Dict[str, Any]] = []
        for e in self.events:
            t = e["t"]
            if t == "delta":
                if out and out[-1]["t"] == "text" and out[-1].get("open"):
                    out[-1]["text"] += e["text"]
                else:
                    out.append({"t": "text", "text": e["text"], "open": True, "at": e["at"]})
                continue
            if out and out[-1].get("open"):
                out[-1].pop("open", None)
            if t in ("seg",):
                continue
            out.append({k: v for k, v in e.items() if k != "seq"})
        if out and out[-1].get("open"):
            out[-1].pop("open", None)
        for i, e in enumerate(out):
            e["seq"] = i
        return out

    def save(self) -> None:
        os.makedirs(CHAT_DIR, exist_ok=True)
        with self._lock:
            doc = {"sid": self.sid, "title": self.title, "created": self.created,
                   "updated": self.updated, "claude_session": self.claude_session,
                   "cwd": self.cwd, "cost": self.cost, "events": self._compact()}
        atomic_write_json(os.path.join(CHAT_DIR, f"{self.sid}.json"), doc, indent=1)

    # ── 루프 ────────────────────────────────────────────────────────────────
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            loop = asyncio.new_event_loop()
            threading.Thread(target=loop.run_forever, name=f"chat-{self.sid}",
                             daemon=True).start()
            self._loop = loop
        return self._loop

    def _submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._ensure_loop())

    # ── 권한 ────────────────────────────────────────────────────────────────
    async def _can_use_tool(self, name: str, inp: Dict[str, Any], _ctx):
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        if name in FREE_TOOLS:
            return PermissionResultAllow()
        if name not in _tools.NEEDS_APPROVAL:
            return PermissionResultDeny(message=f"{name} 은(는) 이 채팅에서 쓸 수 없습니다.")
        aid = uuid.uuid4().hex[:10]
        fut = asyncio.get_running_loop().create_future()
        self._pending[aid] = fut
        self.emit({"t": "approve", "id": aid, "tool": name,
                   "method": inp.get("method", "POST"), "path": inp.get("path", ""),
                   "why": inp.get("why", ""), "body": inp.get("body") or {}})
        try:
            ok, note = await asyncio.wait_for(fut, APPROVE_TIMEOUT)
        except asyncio.TimeoutError:
            ok, note = False, "30분 동안 승인이 없어 거절로 처리했습니다."
        finally:
            self._pending.pop(aid, None)
        self.emit({"t": "approved" if ok else "denied", "id": aid, "note": note})
        if ok:
            return PermissionResultAllow()
        return PermissionResultDeny(message="사람이 거절했습니다." + (f" 사유: {note}" if note else ""))

    def resolve(self, aid: str, ok: bool, note: str = "") -> bool:
        fut = self._pending.get(aid)
        if not fut or self._loop is None:
            return False
        self._loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result((ok, note)))
        return True

    # ── 연결 ────────────────────────────────────────────────────────────────
    def _options(self, system: str, cwd: str, resume: str):
        from claude_agent_sdk import ClaudeAgentOptions

        from services.authoring.provider import find_cli, scrubbed_env

        exe = find_cli()
        if exe is None:
            raise RuntimeError("Claude Code CLI 를 찾지 못했습니다. Claude Code 를 설치하고 "
                               "한 번 로그인하거나, .env 의 CLAUDE_CLI 로 경로를 지정하십시오.")
        kw: Dict[str, Any] = dict(
            cli_path=str(exe),
            # ★ 각자의 ~/.claude 설정·CLAUDE.md 를 들이지 않는다(집필과 같은 이유).
            setting_sources=[],
            env=scrubbed_env(),
            system_prompt=system,
            mcp_servers={_tools.SERVER: _tools.build_server(self)},
            allowed_tools=list(FREE_TOOLS),
            disallowed_tools=list(BLOCKED),
            permission_mode="default",
            can_use_tool=self._can_use_tool,
            include_partial_messages=True,
            cwd=cwd,
            add_dirs=[BASE_DIR],
            max_turns=60,
            max_buffer_size=8 * 1024 * 1024,
        )
        if m := (os.getenv("XAM_CHAT_MODEL") or "").strip():
            kw["model"] = m
        if resume:
            kw["resume"] = resume
        return ClaudeAgentOptions(**kw)

    async def _connect(self, system: str, cwd: str):
        from claude_agent_sdk import ClaudeSDKClient

        # 책 폴더가 바뀌었으면 이어 쓰지 않는다 — CLI 의 세션 기록은 cwd 별로 갈린다.
        resume = self.claude_session if (self.claude_session and self.cwd == cwd) else ""
        if self.claude_session and not resume:
            self.emit({"t": "info", "text": "작업 폴더가 바뀌어 새 맥락으로 이어 갑니다."})
        try:
            c = ClaudeSDKClient(self._options(system, cwd, resume))
            await c.connect()
        except Exception:
            if not resume:
                raise
            # 이어 쓸 기록이 지워졌을 수 있다 — 새로 연다.
            self.emit({"t": "info", "text": "이전 맥락을 찾지 못해 새로 시작합니다."})
            c = ClaudeSDKClient(self._options(system, cwd, ""))
            await c.connect()
        self._client = c
        self.cwd = cwd

    async def _disconnect(self):
        c, self._client = self._client, None
        if c is not None:
            try:
                await c.disconnect()
            except Exception:                                    # noqa: BLE001
                pass

    def close(self) -> None:
        for aid in list(self._pending):
            self.resolve(aid, False, "대화가 닫혔습니다.")
        if self._loop is not None and self._client is not None:
            try:
                self._submit(self._disconnect()).result(timeout=15)
            except Exception:                                    # noqa: BLE001
                pass

    # ── 한 턴 ───────────────────────────────────────────────────────────────
    def send(self, text: str, *, ctx_note: str, system: str, cwd: str) -> None:
        with self._lock:
            if self.busy:
                raise RuntimeError("아직 답하는 중입니다. 끝나거나 [중단] 한 뒤 보내십시오.")
            self.busy = True
        self.last_used = time.monotonic()
        if self.title == "새 대화":
            self.title = text.strip().splitlines()[0][:40] or "새 대화"
        self.emit({"t": "user", "text": text, "ctx": ctx_note})
        self.save()
        msg = text if not ctx_note else f"{text}\n\n<화면>\n{ctx_note}\n</화면>"
        self._submit(self._turn(msg, system, cwd))

    async def _turn(self, msg: str, system: str, cwd: str):
        from claude_agent_sdk import (AssistantMessage, ResultMessage, StreamEvent,
                                      SystemMessage, TextBlock, ToolResultBlock,
                                      ToolUseBlock, UserMessage)
        try:
            if self._client is None or self.cwd != cwd:
                await self._disconnect()
                await self._connect(system, cwd)
            await self._client.query(msg)
            self._streamed = False
            async for m in self._client.receive_response():
                if isinstance(m, StreamEvent):
                    ev = m.event or {}
                    et = ev.get("type")
                    if et == "content_block_start" and (ev.get("content_block") or {}).get("type") == "text":
                        self.emit({"t": "seg"})
                    elif et == "content_block_delta":
                        d = ev.get("delta") or {}
                        if d.get("type") == "text_delta" and d.get("text"):
                            self._streamed = True
                            self.emit({"t": "delta", "text": d["text"]})
                elif isinstance(m, AssistantMessage):
                    for b in m.content:
                        if isinstance(b, TextBlock) and not self._streamed and b.text:
                            self.emit({"t": "text", "text": b.text})
                        elif isinstance(b, ToolUseBlock):
                            self.emit({"t": "tool", "id": b.id, "name": b.name,
                                       "label": _TOOL_KO.get(b.name, b.name),
                                       "brief": _brief(b.name, b.input or {})})
                    self._streamed = False
                elif isinstance(m, UserMessage):
                    content = m.content if isinstance(m.content, list) else []
                    for b in content:
                        if isinstance(b, ToolResultBlock):
                            self.emit({"t": "tool_done", "id": b.tool_use_id,
                                       "error": bool(b.is_error)})
                elif isinstance(m, SystemMessage):
                    sid = (getattr(m, "data", None) or {}).get("session_id")
                    if sid:
                        self.claude_session = sid
                elif isinstance(m, ResultMessage):
                    if getattr(m, "session_id", None):
                        self.claude_session = m.session_id
                    c = float(getattr(m, "total_cost_usd", 0.0) or 0.0)
                    self.cost += c
                    self.emit({"t": "done", "cost": round(c, 4),
                               "turns": int(getattr(m, "num_turns", 0) or 0),
                               "ms": int(getattr(m, "duration_ms", 0) or 0),
                               "error": bool(getattr(m, "is_error", False))})
        except Exception as e:                                   # noqa: BLE001
            from services.authoring.provider import _classify_error
            err = _classify_error(str(e))
            self.emit({"t": "error", "kind": type(err).__name__, "text": str(e)[:800]})
            await self._disconnect()
        finally:
            self.busy = False
            self.updated = _now()
            self.save()

    def interrupt(self) -> None:
        for aid in list(self._pending):
            self.resolve(aid, False, "중단했습니다.")
        if self._client is not None and self._loop is not None:
            self._submit(self._client.interrupt())


# ── 관리자 ──────────────────────────────────────────────────────────────────
_SESS: Dict[str, ChatSession] = {}
_MLOCK = threading.Lock()


def _path(sid: str) -> str:
    return os.path.join(CHAT_DIR, f"{sid}.json")


def _valid(sid: str) -> bool:
    return bool(sid) and len(sid) <= 40 and all(c.isalnum() or c in "-_" for c in sid)


def get(sid: str) -> Optional[ChatSession]:
    if not _valid(sid):
        return None
    with _MLOCK:
        s = _SESS.get(sid)
        if s is None and os.path.isfile(_path(sid)):
            with open(_path(sid), encoding="utf-8") as f:
                s = ChatSession(sid, json.load(f))
            _SESS[sid] = s
        return s


def create() -> ChatSession:
    sid = time.strftime("%y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    s = ChatSession(sid)
    with _MLOCK:
        _SESS[sid] = s
    s.save()
    return s


def listing(limit: int = 40) -> List[Dict[str, Any]]:
    out = []
    if os.path.isdir(CHAT_DIR):
        for fn in os.listdir(CHAT_DIR):
            if not fn.endswith(".json"):
                continue
            sid = fn[:-5]
            live = _SESS.get(sid)
            if live:
                out.append(live.meta())
                continue
            try:
                with open(os.path.join(CHAT_DIR, fn), encoding="utf-8") as f:
                    d = json.load(f)
                out.append({"sid": sid, "title": d.get("title") or "새 대화",
                            "created": d.get("created"), "updated": d.get("updated"),
                            "busy": False, "cost": d.get("cost", 0)})
            except Exception:                                    # noqa: BLE001
                continue
    out.sort(key=lambda x: x.get("updated") or "", reverse=True)
    return out[:limit]


def remove(sid: str) -> bool:
    s = get(sid)
    if s is None:
        return False
    s.close()
    with _MLOCK:
        _SESS.pop(sid, None)
    try:
        os.remove(_path(sid))
    except OSError:
        pass
    return True


def trim_live() -> None:
    """CLI 프로세스가 대화마다 하나씩 쌓이지 않게 — 오래 안 쓴 연결부터 닫는다."""
    with _MLOCK:
        live = [s for s in _SESS.values() if s._client is not None and not s.busy]
    live.sort(key=lambda s: s.last_used, reverse=True)
    for s in live[MAX_LIVE:]:
        s.close()


def shutdown() -> None:
    with _MLOCK:
        ss = list(_SESS.values())
    for s in ss:
        s.close()


def build_system(endpoints, ctx_note: str = "") -> str:
    return _prompt.build(endpoints, ctx_note)
