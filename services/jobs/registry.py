"""잡 레지스트리 — 메모리 + 파일. 렌더·발행이 공통으로 쓴다.

SSE 를 쓰지 않는다. 스레드 + JSON 파일 + 클라이언트 2초 폴링이다(aim-local 패턴).
클라이언트는 `?log_from=N` 커서로 로그 증분만 받아 간다.
"""
from __future__ import annotations

import sys
import threading
import uuid
from typing import Any, Callable

from core.constants import LOG_TAIL
from services.jobs import jobstore

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.RLock()


def restore_history() -> tuple[int, int]:
    with _LOCK:
        return jobstore.restore(_JOBS)


def create(kind: str, label: str, targets: list[str], *, note: str = "",
           steps: list[str] | None = None) -> dict[str, Any]:
    """잡 레코드를 만들고 즉시 저장한다.

    steps 가 주어지면(발행처럼 단계가 고정인 경우) items 를 단계로 만든다.
    아니면 targets(번들 코드)를 items 로 만든다.
    """
    jid = uuid.uuid4().hex
    keys = steps if steps is not None else targets
    job = {
        "id": jid,
        "kind": kind,
        "label": label,
        "note": note,
        "status": "queued",
        "created_at": jobstore.now_iso(),
        "started_at": None,
        "finished_at": None,
        "error": None,
        "cancel_requested": False,
        "targets": list(targets),
        "current": None,
        "done_count": 0,
        "total_count": len(keys),
        "items": {k: {"status": "queued", "scene_done": 0, "scene_total": 0,
                      "seconds": None, "output": None, "error": None} for k in keys},
        "log": [],
        "log_seq": 0,
        "result": None,
        "publish": None,
    }
    with _LOCK:
        _JOBS[jid] = job
    jobstore.save(job)
    return job


def get(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is not None:
            return job
    # 메모리에 없으면 파일에서 (서버 재시작 후 이력 조회)
    rec = jobstore.load(job_id)
    if rec:
        with _LOCK:
            _JOBS[job_id] = rec
    return rec


def list_jobs(limit: int = 20, kind: str = "") -> list[dict[str, Any]]:
    with _LOCK:
        mem = [jobstore.summary(j) for j in _JOBS.values()]
    seen = {m["id"] for m in mem}
    for m in jobstore.list_jobs(limit=limit * 3):
        if m["id"] not in seen:
            mem.append(m)
    if kind:
        mem = [m for m in mem if m.get("kind") == kind]
    mem.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return mem[:limit]


def running(kind: str = "") -> dict[str, Any] | None:
    """지금 돌고 있는 잡. 렌더는 동시 1개만 허용하므로 이걸로 막는다."""
    with _LOCK:
        for j in _JOBS.values():
            if j.get("status") in ("running", "queued"):
                if not kind or j.get("kind") == kind:
                    return j
    return None


def log(job: dict[str, Any], line: str, *, force: bool = False) -> None:
    """로그 한 줄. 스냅샷에는 꼬리만 남고 전체는 .log 파일로 간다.

    ★ run.bat 콘솔에도 그대로 찍는다. 터미널이 여러 개면 어디를 봐야 하는지 헷갈린다 —
      서버 창 하나가 곧 이 앱의 터미널이다. 브라우저 화면은 그 창을 그대로 비춘다.
    """
    if line is None:
        return
    line = line.rstrip("\r\n")
    _echo(job, line)
    with _LOCK:
        job["log"].append(line)
        job["log_seq"] = job.get("log_seq", 0) + 1
        # 메모리도 무한히 키우지 않는다
        if len(job["log"]) > LOG_TAIL * 3:
            job["log"] = job["log"][-LOG_TAIL:]
    jobstore.append_log_file(job["id"], [line])
    jobstore.save(job, force=force)


def _echo(job: dict[str, Any], line: str) -> None:
    """서버 콘솔(run.bat 창)에 한 줄 흘린다.

    콘솔이 cp949 라 한글 이외 문자에서 UnicodeEncodeError 가 날 수 있다. 로그 한 줄
    때문에 렌더 스레드를 죽일 수는 없으니 전부 삼킨다 — 진짜 로그는 파일에 있다.
    """
    try:
        kind = (job.get("kind") or "job")[:6]
        print(f"[{kind}] {line}", flush=True)
    except Exception:
        try:
            sys.stdout.buffer.write(
                (line.encode("utf-8", "replace") + b"\n"))
            sys.stdout.flush()
        except Exception:
            pass


def update(job: dict[str, Any], **fields) -> None:
    """상태 전이 — 즉시 저장한다(스로틀 대상이 아니다)."""
    with _LOCK:
        job.update(fields)
    jobstore.save(job, force=True)


def item(job: dict[str, Any], key: str, **fields) -> None:
    with _LOCK:
        it = job["items"].setdefault(key, {"status": "queued"})
        it.update(fields)
        # ★ 「끝난 것」만 센다 (2026-09-08).
        #
        #   전에는 `skipped` 도 셌다. 그런데 이 상태를 찍는 자리가 둘 다 **안 한**
        #   경우다 — 취소로 남은 파트, 앞선 파트가 연속 실패해 포기한 파트.
        #   그래서 일시정지하면 남은 55파트가 전부 done_count 에 들어가
        #   화면이 **「60/60 (100%)」**을 그렸다. 실제로 만들어진 것은 5파트였고,
        #   사람은 그것을 보고 7시간짜리 집필이 41분에 끝난 줄 알았다(실측).
        #
        #   `error` 는 센다 — 돈이 나갔고 더 기다릴 것이 없다. 그것은 «끝난» 것이다.
        job["done_count"] = sum(
            1 for v in job["items"].values()
            if v.get("status") in ("done", "error"))
    jobstore.save(job, force=True)


def finish(job: dict[str, Any], status: str = "done", error: str | None = None,
           result: dict | None = None) -> None:
    update(job, status=status, error=error, result=result,
           finished_at=jobstore.now_iso(), current=None)


def request_cancel(job_id: str) -> bool:
    job = get(job_id)
    if not job or job.get("status") not in ("running", "queued"):
        return False
    update(job, cancel_requested=True)
    return True


def spawn(job: dict[str, Any], target: Callable[[dict], None]) -> None:
    """워커 스레드 시작. 예외는 잡 레코드에 남긴다 — 조용히 죽으면 안 된다."""
    def run():
        try:
            update(job, status="running", started_at=jobstore.now_iso())
            target(job)
            if job.get("status") == "running":
                finish(job, "done")
        except Exception as e:                     # noqa: BLE001
            import traceback
            log(job, f"[error] {type(e).__name__}: {e}", force=True)
            log(job, traceback.format_exc(), force=True)
            finish(job, "error", error=f"{type(e).__name__}: {e}")

    threading.Thread(target=run, daemon=True, name=f"job-{job['id'][:8]}").start()


def view(job: dict[str, Any], log_from: int = 0) -> dict[str, Any]:
    """폴링 응답 — 로그는 커서 이후 증분만 담는다."""
    with _LOCK:
        seq = job.get("log_seq", 0)
        buf = job.get("log") or []
        # 버퍼가 들고 있는 가장 이른 줄 번호
        first_in_buf = max(0, seq - len(buf))
        start = max(log_from, first_in_buf)
        lines = buf[start - first_in_buf:] if start <= seq else []
        out = {k: v for k, v in job.items() if k != "log"}
        out["log"] = {
            "from": start,
            "next": seq,
            "lines": lines,
            "dropped": start > log_from,   # 앞부분이 링버퍼에서 밀려났다
        }
    return out
