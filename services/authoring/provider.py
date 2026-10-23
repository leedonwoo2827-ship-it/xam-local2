# -*- coding: utf-8 -*-
"""집필 프로바이더 — Claude Code **구독 OAuth**. API 키를 쓰지 않는다.

★ 출처: showcase-agent/llm/claude_provider.py (2026-08-08 판) 를 이 앱의 필요에
  맞춰 줄인 것이다. `find_cli` · `scrubbed_env` · `_classify_error` · `_run` 은
  **동작을 바꾸지 않았다.** 두 앱이 같은 PC·같은 구독을 쓰므로 여기가 갈리면
  같은 증상에 서로 다른 안내가 나간다.

왜 이 방식인가 — 집필자(SME)마다 자기 $100/$200 계정으로 들어온다.
  API 키를 한 개 두고 공유하면 누가 얼마를 썼는지 가를 수 없고, 키가 유출되면
  전원이 멈춘다. 각자의 로그인을 그대로 빌려 쓰면 사용량·한도가 자연히 갈린다.

★ 계층 규약: 이 파일은 FastAPI 를 import 하지 않는다(services/* 공통).
  겉면은 전부 동기다 — 호출부가 잡 워커 스레드이기 때문이다. 안에서만 asyncio 한다.

── 이 PC 에서 실측한 것 (2026-08-10, CLI 2.1.226 · claude-agent-sdk 0.2.134) ──
  · 키 없이 인증 통과. `~/.claude/.credentials.json` 의 구독 로그인으로 나간다
    (subscriptionType=team, rateLimitTier=default_claude_max_5x).
  · `output_format={"type":"json_schema","schema":…}` 동작. 문항 JSON 이 그대로 온다.
  · `cwd` + allowed_tools=[Read,Grep,Glob] 로 book 폴더의 `01/` 기출을 실제로 읽었다.
  · ★ **호출당 최소 비용 약 $0.25.** "OK" 한 마디도 같다 — 하네스 시스템 프롬프트가
    캐시 생성 42,852 토큰이기 때문이다. 그래서 **문항당 1회 호출은 금지다.**
    파트(10문항) 단위로 묶는다. 문항 1개 집필 실측 = 3턴 · 57초 · $0.288.
  · 같은 접두로 1시간 안에 다시 부르면 33,682 토큰이 캐시 **읽기**로 전환되어
    비용이 $0.257 → $0.066 로 떨어진다. → 한 회차의 파트 8개는 **연달아** 돌린다.
    사이를 벌리면 매번 캐시를 새로 만든다.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .errors import NotAuthenticated, ProviderError, QuotaExceeded


# ── CLI 찾기 ────────────────────────────────────────────────────────────────
def find_cli() -> Optional[Path]:
    """claude 실행 파일. **VSCode 확장에 번들된 것까지** 찾는다.

    ★ 이 마지막 경로가 없으면 안 된다. 이 PC 에는 `claude` 가 PATH 에도, npm 전역에도,
      `~/.local/bin` 에도 없다 — 실행 파일은 VSCode 확장 안에만 있다(287MB).
      SME PC 도 같을 가능성이 높다(대부분 확장으로 처음 깔았다).
    """
    if env := (os.environ.get("CLAUDE_CLI") or "").strip().strip('"'):
        p = Path(env).expanduser()
        if p.exists():
            return p
    # ★ PATH 의 npm 래퍼(`claude.cmd`)는 고르지 않는다. SDK 0.2.134 가 .bat/.cmd 실행을
    #   거부한다("Refusing to execute batch script … cmd.exe 인자 주입"). v2 이관 때
    #   이 PC 의 PATH 에 npm 판이 먼저 잡혀 채팅이 첫 마디에서 죽었다(2026-10-24).
    if (w := shutil.which("claude")) and Path(w).suffix.lower() not in (".cmd", ".bat"):
        return Path(w)
    native = Path.home() / ".local" / "bin" / "claude.exe"
    if native.exists():
        return native
    for pat in ("anthropic.claude-code-*/resources/native-binary/claude.exe",
                "anthropic.claude-code-*/resources/native-binary/claude"):
        hits = sorted((Path.home() / ".vscode" / "extensions").glob(pat))
        if hits:
            return hits[-1]      # 확장 버전이 올라가면 경로가 바뀐다 → 최신 선택
    # 마지막: SDK 휠에 들어 있는 claude.exe (Windows x64 휠). 로그인은 같은 ~/.claude 를 쓴다.
    try:
        import claude_agent_sdk
        b = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude.exe"
        if b.exists():
            return b
    except Exception:                                            # noqa: BLE001
        pass
    return None


def scrubbed_env() -> Dict[str, str]:
    """낡은 export 가 OAuth 를 조용히 가로채 **다른 계정에 과금**하는 것을 막는다.

    ★ 빈 문자열로 **덮어야** 한다. 키를 지우는 것이 아니라 빈 값을 자식 환경에
      넣어 무력화하는 것이다 — 삭제만 하면 부모 환경의 값이 그대로 상속된다.
    ★ 이것이 없으면 증상이 최악이다: 집필은 정상 동작하고, 요금만 엉뚱한 곳에
      찍힌다. 아무도 몇 달 뒤 청구서를 보기 전까지 모른다.
    """
    return {"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": "", "ANTHROPIC_BASE_URL": ""}


def _classify_error(msg: str) -> ProviderError:
    """문자열 매칭으로 타입화 — showcase-agent 와 같은 규칙."""
    low = (msg or "").lower()
    if any(k in low for k in ("not authenticated", "sign in", "401", "unauthorized", "login")):
        return NotAuthenticated(msg)
    if any(k in low for k in ("quota", "rate limit", "429", "usage limit", "overloaded")):
        return QuotaExceeded(msg)
    return ProviderError(msg)


def _run(coro):
    """동기 겉면 — 이미 asyncio 루프가 돌고 있으면 별도 스레드에서 돌린다.

    ★ FastAPI 안에서 부르면 루프가 돌고 있다. `asyncio.run` 을 그대로 부르면
      RuntimeError 로 죽는다. (같은 함정을 `deck_capture` 의 sync_playwright 에서
      이미 겪었다 — 그래서 그 라우트 핸들러는 `async def` 가 아니다.)
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


# ── 프로바이더 ──────────────────────────────────────────────────────────────
@dataclass
class ClaudeAuthor:
    """집필 1회 = `structured()` 1회. 스키마를 주고 dict 를 받는다.

    ★ 파일을 쓰게 하지 않는다(`Write`/`Edit` 금지). 모델 출력이 `_rounds/` 에
      직접 닿으면 안 된다 — 받은 dict 를 앱이 검증한 뒤 스테이징에 쓴다.
      읽기(Read/Grep/Glob)는 허용한다: 기출 `01/` 240문항과 syllabus 를 프롬프트에
      통째로 넣으면 접두가 거대해지고, 모델이 필요한 것만 읽는 편이 싸다.
    """
    model: str = ""                       # 빈 값 = CLI 기본
    effort: Optional[str] = None           # low | medium | high | xhigh | max
    cwd: Optional[str] = None              # book 폴더 — 기출·syllabus 를 여기서 읽는다
    allowed_tools: List[str] = field(default_factory=lambda: ["Read", "Grep", "Glob"])
    # 문항 1개에 3턴이 걸렸다. 10문항이면 기출을 여러 개 읽으므로 넉넉히 둔다.
    # ★ 상한이 있어야 한다 — 없으면 모델이 헤맬 때 구독 한도를 통째로 태운다.
    max_turns: int = 40
    # ★ 달러 상한은 **기본으로 걸지 않는다**(`None`). 처음엔 $4 를 걸어 뒀다가
    #   9회차 실행에서 그것 때문에 6과목·$29 를 통째로 잃었다(2026-08-10):
    #
    #     m04-p2  $6.24 · 35.9분 → 상한에 잘림 → **0문항**
    #     m02-p4  $5.31 · 32.9분 → 상한에 잘림 → **0문항**
    #     (합격한 과목의 최고가 $3.83 이었다 — 방어선이 정상 범위 안에 있었다)
    #
    #   달러는 **재는 값**이지 끊는 값이 아니다. 30분 돌린 것을 마지막에 잘라 0문항으로
    #   버리면 그 돈은 그대로 나가고 결과만 사라진다 — 방어가 아니라 손실이다.
    #   폭주는 `max_turns` 가 구조적으로 막고(턴 수는 늘 유한하다), 한도에 걸려 줄줄이
    #   실패하는 것은 잡 쪽 브레이크(`STALL_LIMIT`)가 막는다. 달러가 낄 자리가 없다.
    #
    #   ★ 값을 주면 그때만 건다. 폭주가 의심되는 실험에서 일시적으로 쓰는 용도다.
    budget_usd: Optional[float] = None
    # ★ 벽시계 상한. 잘림(`_abort_reason`)이 아닌 방식으로 되풀이하는 경우의 마지막
    #   방어선이다. 실측 최장 과목이 36분(m08-p1 · 2158.9초)이므로 60분이면 정상
    #   과목을 건드리지 않는다.
    # ★ **메시지가 올 때만** 검사한다. 타이머(`asyncio.wait_for`)로는 못 끊는다 —
    #   아래 `_structured` 머리말 참조. CLI 가 한 글자도 안 보내고 멈추면 이 상한은
    #   안 걸린다. 실측에서는 시도마다 13분에 한 번씩 응답이 왔다.
    timeout_sec: float = 3600.0
    # ★ CLI stdout 버퍼 상한(바이트). 기본 1MB 로는 **스캔 이미지를 읽는 호출이 죽는다** —
    #   `Read` 가 PNG 를 base64 로 실어 보내므로 500KB 그림 한 장이 ~700KB 가 되고,
    #   OCR 판독은 걸친 문항 때문에 두 장을 준다. 실측으로 20장 중 4장이
    #   "JSON message exceeded maximum buffer size of 1048576 bytes" 로 실패했다.
    #   집필(텍스트만)은 이 값이 필요 없지만, 같은 provider 를 쓰므로 여기에 둔다.
    max_buffer_size: Optional[int] = None
    exe: Optional[Path] = field(default=None)
    # ★ 모델이 도구를 쓸 때마다 부른다. 파트 1개가 몇 분씩 가는데 화면이 한 글자도
    #   안 바뀌면 **멈춘 것으로 보인다.** 답변초안 화면에서 이미 같은 말을 들었다
    #   ("이거 진행중인거 만들어주기로 하지 않았나요?! 상태표시라도...").
    on_activity: Optional[Callable[[str], None]] = field(default=None, repr=False)

    # 마지막 호출의 계량 — 화면이 "이번에 얼마 썼나" 를 보여줄 근거
    last_cost_usd: float = 0.0
    last_turns: int = 0
    last_usage: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.exe is None:
            self.exe = find_cli()

    # ── 옵션 조립 ──
    def _options(self, *, system: str, schema: Dict[str, Any]):
        from claude_agent_sdk import ClaudeAgentOptions

        if self.exe is None:
            raise NotAuthenticated(
                "Claude Code CLI 를 찾지 못했습니다. Claude Code 에 로그인한 뒤 다시 "
                "시도하거나, CLAUDE_CLI 환경변수로 실행 파일 경로를 지정하십시오.")

        kw: Dict[str, Any] = dict(
            cli_path=str(self.exe),
            # ★ 각자의 전역 ~/.claude/CLAUDE.md · settings 유입을 차단한다.
            #   안 하면 **집필자마다 결과가 달라진다.** 문제집은 재현성이 요구사항이다
            #   (같은 회차를 다시 만들면 같은 것이 나와야 검증이 성립한다).
            setting_sources=[],
            env=scrubbed_env(),
            max_turns=self.max_turns,
            allowed_tools=list(self.allowed_tools),
            disallowed_tools=["Bash", "Write", "Edit", "NotebookEdit",
                              "WebFetch", "WebSearch", "Task"],
            permission_mode="default",
            system_prompt=system,          # 문자열 — claude_code 프리셋을 쓰지 않는다
            output_format={"type": "json_schema", "schema": schema},
        )
        # 값을 준 경우에만 건다 — 기본은 상한 없음(위 머리말 참조).
        if self.budget_usd is not None:
            kw["max_budget_usd"] = self.budget_usd
        if (m := (self.model or "").strip()) and m not in ("cli-default", "default"):
            kw["model"] = m
        if self.effort:
            kw["effort"] = self.effort
        if self.cwd:
            kw["cwd"] = str(self.cwd)
        if self.max_buffer_size:
            kw["max_buffer_size"] = int(self.max_buffer_size)
        return ClaudeAgentOptions(**kw)

    # ── 지금 무엇을 읽고 있는가 ──
    _TOOL_KO = {"Read": "읽는 중", "Grep": "찾는 중", "Glob": "훑는 중"}

    def _activity(self, blocks) -> None:
        """ToolUseBlock 을 사람이 읽는 한 줄로. 경로는 뒤 두 칸만 남긴다."""
        if not self.on_activity:
            return
        for b in blocks:
            name = getattr(b, "name", "")
            if name not in self._TOOL_KO:
                continue
            inp = getattr(b, "input", None) or {}
            what = str(inp.get("file_path") or inp.get("pattern") or inp.get("path") or "")
            what = "/".join(what.replace("\\", "/").rstrip("/").split("/")[-2:])
            try:
                self.on_activity(f"{what} {self._TOOL_KO[name]}" if what
                                 else self._TOOL_KO[name])
            except Exception:      # noqa: BLE001 — 표시용이다. 본작업을 절대 죽이지 않는다
                pass

    # ── 집필 ──
    def structured(self, system: str, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """스키마에 맞는 dict 를 받는다. 실패는 예외다 — 빈 dict 를 돌려주지 않는다.

        ★ 조용한 부분 성공을 만들지 않는다. 문항 10개를 요청해 3개만 오면 그것도
          `subtype=="success"` 다. 개수 검증은 호출부(draft)가 하고, 여기서는
          "dict 가 아니면 실패" 까지만 본다.
        """
        return _run(self._structured(system, prompt, schema))

    # ── 지금 끊어야 하는가 ──
    def _abort_reason(self, m: Any, t0: float) -> str:
        """이 응답을 보고 **여기서 끊어야 하는가.** 빈 문자열이면 계속 간다.

        ★ 이것이 없으면 무한루프가 된다. 2026-08-12 m09-p1 에서 실측한 것:

            08:31  45,024토큰 · stop=tool_use    → 스키마 반려
                   (/items/16/explanation: must NOT have fewer than 140 characters)
            08:36  64,000토큰 · stop=max_tokens  ← 잘림
            08:49  64,000토큰 · stop=max_tokens  ← 잘림
            09:03  64,000토큰 · stop=max_tokens  ← 잘림

          **한 번 잘리면 끝이다.** 잘린 응답이 다음 시도의 컨텍스트에 그대로 얹히므로
          다음도 잘린다 — 세 번이 정확히 같은 값에서 멈춘 것이 그 증거다. 그런데
          `max_turns=40` 이라 40번까지 그렇게 간다: 13분 × 40 = 8.7시간이다.
          화면은 한 글자도 안 바뀌므로 사람에게는 "멈춘 것"으로 보인다 — 멈춘 것이
          아니라 구독 한도를 태우고 있었다. 그날 5시간 · 237,000토큰 · 0문항이었다.

        ★ 잘림을 `ResultMessage` 로 알 수는 없다. 그것은 루프가 다 끝난 뒤에 온다.
          `AssistantMessage.stop_reason` 이 매 응답마다 오므로 그것을 본다.
        """
        el = time.monotonic() - t0
        if getattr(m, "stop_reason", None) == "max_tokens":
            got = int((getattr(m, "usage", None) or {}).get("output_tokens") or 0)
            return (f"응답이 출력 상한에서 잘렸습니다 ({got:,}토큰 · {el / 60:.1f}분). "
                    f"다시 시도해도 잘린 응답이 컨텍스트에 남아 또 잘리므로 여기서 "
                    f"끊습니다. 한 문항이 스키마에 걸려 20문항을 다시 쓰는 중일 수 "
                    f"있습니다 — 스테이징의 problems 를 보고, 반복되면 "
                    f"draft.PART_SIZE 를 줄이십시오.")
        if el > self.timeout_sec:
            return (f"{el / 60:.0f}분이 지나 끊었습니다(상한 "
                    f"{self.timeout_sec / 60:.0f}분). 정상 과목은 실측 23~36분입니다 — "
                    f"그보다 오래 걸리면 같은 응답을 되풀이하고 있을 가능성이 큽니다.")
        return ""

    async def _structured(self, system: str, prompt: str,
                          schema: Dict[str, Any]) -> Dict[str, Any]:
        """★ `aclosing` 이 있어야 자식 `claude.exe` 가 죽는다.

        SDK 가 주석으로 못을 박아 두었다(`_internal/client.py`):
          "``async for`` does NOT close its iterator when the loop body raises
           (PEP 533 was deferred)."
        닫히지 않으면 `query.close()` 의 terminate/kill 이 돌지 않아 자식이 남는다.
        부모(앱)는 과목 사이에 죽지 않으므로 SDK 의 atexit 회수도 오지 않는다 →
        고아가 몇 시간 한도를 태우는데 앱은 태연히 다음 과목을 시작한다. 아래
        `break` 를 쓰려면 이것이 먼저다. (이 파일이 원래 `aclosing` 없이 예외를
        던지고 있었다 — 위 반려 실패 경로에서 이미 자식이 남을 수 있었다.)

        ★ 같은 이유로 `asyncio.wait_for` 로는 시간 상한을 못 건다. SDK 가 그 경우를
          명시해 두었다(`subprocess_cli.py` 의 `close()` 머리말): 생 asyncio 취소는
          anyio shield 를 통과해 terminate/kill escalation 을 **건너뛴다.** 그래서
          시간 상한도 타이머가 아니라 **메시지 경계에서 `break`** 로 건다.
        """
        from contextlib import aclosing

        from claude_agent_sdk import AssistantMessage, ResultMessage, query

        out: Optional[Dict[str, Any]] = None
        sub = "?"
        abort = ""          # 비어 있으면 정상 종료. 채워지면 **우리가** 끊은 것이다
        t0 = time.monotonic()
        try:
            stream = query(prompt=prompt,
                           options=self._options(system=system, schema=schema))
            async with aclosing(stream):
                async for m in stream:
                    if isinstance(m, AssistantMessage):
                        self._activity(m.content)
                        if abort := self._abort_reason(m, t0):
                            break
                    elif isinstance(m, ResultMessage):
                        self.last_cost_usd = float(getattr(m, "total_cost_usd", 0.0) or 0.0)
                        self.last_turns = int(getattr(m, "num_turns", 0) or 0)
                        self.last_usage = dict(getattr(m, "usage", None) or {})
                        sub = getattr(m, "subtype", "?")
                        out = getattr(m, "structured_output", None)
        except Exception as e:   # noqa: BLE001
            if isinstance(e, ProviderError):
                raise
            raise _classify_error(str(e)) from e

        if abort:
            # ★ 끊었으므로 `ResultMessage` 를 못 받았다 → `last_cost_usd` 가 0 이다.
            #   draft/잡 쪽은 비용 0 을 "모델을 아예 못 불렀다" 로 읽어 STALL_LIMIT 를
            #   올린다. 이 경우엔 그것이 맞다 — 연속 3회 잘리면 스키마나 파트 크기가
            #   문제이므로 남은 과목을 계속 태울 이유가 없다. 실제로 쓴 돈은 잡히지
            #   않지만, 그것을 살리려고 끊지 않는 것은 오늘 겪은 쪽이 훨씬 비싸다.
            raise ProviderError(abort)

        if not isinstance(out, dict):
            # ★ subtype=="success" 인데 structured_output 이 없는 경우가 문서에 명시돼
            #   있다. 실패로 취급한다 — 통과시키면 빈 파트가 스테이징에 들어간다.
            raise ProviderError(
                f"구조화 출력을 받지 못했습니다 (subtype={sub}, "
                f"{self.last_turns}턴, ${self.last_cost_usd:.3f} 소모). "
                "프롬프트가 스키마와 어긋났거나 턴/예산 상한에 걸렸을 수 있습니다.")
        return out

    # ── 상태 ──
    def ping(self) -> Tuple[bool, str]:
        """설정 화면의 연결 칩이 읽는다. ★ 약 $0.25 가 든다 — 자동 호출 금지."""
        if self.exe is None:
            return False, "Claude Code CLI 를 찾지 못했습니다 (CLAUDE_CLI 로 지정 가능)."
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
        try:
            got = self.structured("You are a connection tester.",
                                  'Return {"ok": true}.', schema)
            return bool(got.get("ok")), (
                f"연결됨 · {self.last_turns}턴 · ${self.last_cost_usd:.3f}")
        except Exception as e:   # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"


def status() -> Dict[str, Any]:
    """화면 상단 칩이 읽는 것. ★ 모델을 부르지 않는다(무료·즉시).

    `ping()` 과 나누는 이유: 화면을 열 때마다 $0.25 를 태울 수 없다.
    여기서는 "깔려 있는가 · 로그인 파일이 있는가" 까지만 본다.
    """
    exe = find_cli()
    cred = Path.home() / ".claude" / ".credentials.json"
    return {
        "provider": "claude",
        "label": "Claude Code (구독 OAuth)",
        "installed": exe is not None,
        "path": str(exe) if exe else None,
        "credentials": cred.is_file(),
        # ★ 켜져 있으면 경고해야 한다. 우리는 `scrubbed_env()` 로 무력화하지만,
        #   SME 가 "왜 내 계정에 안 찍히지" 를 물을 때 짚을 곳이 필요하다.
        "api_key_env": bool(os.environ.get("ANTHROPIC_API_KEY")
                            or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
    }
