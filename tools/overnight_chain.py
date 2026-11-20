# -*- coding: utf-8 -*-
"""밤샘 이어 돌리기 — 1교시 엑셀 집필 → 2교시 액세스 집필 → 1부 빌드(엑셀) → 3부 문제집 → 2부(끝까지)를 차례로 건다.

  사람이 화면에서 누르는 단추와 **같은 API** 를 부른다 — 잡은 화면의 「최근 작업」 에 그대로 보인다.
  run.bat(서버, 포트 8871)이 켜져 있어야 한다.

  ★ 2026-11-19 지시: 다음 날 이 PC 를 교육에 쓴다 — 마감 시각(기본 07:30)에 돌고 있는 잡은 멈추고
    그 뒤 단계는 시작하지 않는다. 1부 빌드는 엑셀을 자동으로 열고 닫아서, 사람이 엑셀을 쓰는 동안 돌면 안 된다.
  ★ 순서: 3부가 1부의 그림·실습파일을 가져다 쓴다(집필 → 1부 → 3부). 2부는 가장 오래 걸려서 맨 뒤.
  ★ 도는 동안만 절전·화면 꺼짐 때문에 PC 가 잠들지 않게 한다(SetThreadExecutionState). 끝나면 원래대로.

  venv\\Scripts\\python tools\\overnight_chain.py                    1-10회 · 마감 07:30
  venv\\Scripts\\python tools\\overnight_chain.py --rounds 1-10 --deadline 07:00
  venv\\Scripts\\python tools\\overnight_chain.py --skip part2         2부는 빼고
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8871"
LOG = None


def log(msg: str) -> None:
    line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def call(method: str, path: str, body=None, timeout: float = 60):
    data = json.dumps(body or {}).encode("utf-8") if method == "POST" else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8")).get("detail")
        except Exception:                                      # noqa: BLE001
            detail = str(e)
        return e.code, {"detail": detail}


def keep_awake(on: bool) -> None:
    """도는 동안만 잠자기 방지 — 윈도가 아니면 아무것도 안 한다."""
    if os.name != "nt":
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


def past(deadline: dt.datetime) -> bool:
    return dt.datetime.now() >= deadline


def wait_job(job: dict, deadline: dt.datetime, name: str) -> str:
    """잡이 끝날 때까지. 마감이 지나면 멈추기를 누르고 지금 묶음이 끝날 때까지 기다린다."""
    jid, asked, last = job["id"], False, ""
    while True:
        code, j = call("GET", f"/api/jobs/{jid}")
        if code != 200:
            log(f"  {name}: 잡 상태를 못 읽었습니다({code}) — 서버(run.bat)가 꺼졌는지 확인하세요.")
            return "lost"
        prog = f"{j.get('done_count', 0)}/{j.get('total_count', 0)} {j.get('current') or ''}".strip()
        if prog != last:
            log(f"  {name}: {prog}")
            last = prog
        if j.get("finished_at"):
            st = "cancelled" if j.get("cancel_requested") else (j.get("status") or "done")
            log(f"  {name}: 끝 — {st}" + (f" · {j.get('error')}" if j.get("error") else ""))
            return st
        if past(deadline) and not asked:
            log(f"  {name}: 마감 시각이 지났습니다 — 멈추기를 누릅니다(지금 묶음까지 마치고 섭니다).")
            call("POST", f"/api/jobs/{jid}/cancel")
            asked = True
        time.sleep(20)


NEVER = dt.datetime(2999, 1, 1)
RETRY_WAIT = 20 * 60          # 사용량 한도 · 연속 실패면 20분 뒤 다시 건다(쓴 묶음은 남고 남은 것부터 잇는다)
RETRY_MAX = 24                # 최대 8시간


def start_job(name: str, path: str, body: dict, deadline: dt.datetime = NEVER, retry: bool = False) -> str:
    """잡을 걸고 끝까지 기다린다. retry 면 오류(한도·연속 실패)·서버 끊김 뒤 20분마다 다시 건다.

    ★ 2026-11-19 지시: 「사용량에 걸리면 풀리면 계속하셔도 돼요」 — 집필·2부는 한도가 풀리면 이어 간다.
    """
    for k in range(RETRY_MAX + 1):
        if past(deadline):
            log(f"{name}: 마감 시각이 지나 시작하지 않습니다.")
            return "skipped"
        log(f"{name}: 시작" + (f" (다시 {k}번째)" if k else ""))
        code, j = call("POST", path, body)
        if code == 200 and j.get("id"):
            st = wait_job(j, deadline, name)
        elif code == 400:
            log(f"{name}: 할 것이 없습니다 — {j.get('detail')}")
            return "nothing" if k == 0 else "done"
        else:
            log(f"{name}: 시작하지 못했습니다({code}) — {j.get('detail')}")
            st = "failed"
        if st in ("done", "cancelled", "skipped") or not retry:
            return st
        log(f"{name}: {st} — 사용량 한도일 수 있습니다. {RETRY_WAIT // 60}분 뒤 다시 겁니다(쓴 것은 남습니다).")
        time.sleep(RETRY_WAIT)
    return "gave-up"


def access_build(rounds: str, deadline: dt.datetime) -> str:
    """2교시 액세스 실습파일(.accdb) — 서버를 거치지 않고 이 프로세스에서 빌더를 직접 부른다.

    ★ 빌더(services/practical/build_access.py)는 집필이 도는 동안 만든다(2026-11-19) — 그때 서버를 다시
      켜지 않아도 되게, 이 단계가 올 때 모듈을 새로 읽는다. 아직 없으면 건너뛴다.
    ★ 액세스 프로그램을 여므로 1부 빌드와 같은 마감을 건다.
    """
    if past(deadline):
        log("액세스 빌드: 마감 시각이 지나 시작하지 않습니다.")
        return "skipped"
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        import importlib
        ba = importlib.import_module("services.practical.build_access")
    except ImportError as e:
        log(f"액세스 빌드: 빌더가 아직 없습니다 — 건너뜁니다({e}).")
        return "no-builder"
    lo, _, hi = rounds.partition("-")
    want = list(range(int(lo), int(hi or lo) + 1))
    log(f"액세스 빌드: 시작 — {len(want)}회")
    ok = 0
    for m in want:
        if past(deadline):
            log("액세스 빌드: 마감 시각 — 여기서 멈춥니다.")
            break
        try:
            r = ba.build_round(m)
            ok += 1
            log(f"  액세스 {m:02d}회: {r.get('summary') or r}")
        except Exception as e:                                   # noqa: BLE001
            log(f"  액세스 {m:02d}회: 실패 — {type(e).__name__}: {e}")
    return f"{ok}/{len(want)}회"


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", default="1-10")
    ap.add_argument("--deadline", default="07:30", help="HH:MM — 이 시각이 지나면 멈춘다(다음 날 아침)")
    ap.add_argument("--skip", default="", help="빼고 돌릴 단계: author,access,build,ebook,part2 (쉼표)")
    a = ap.parse_args()

    hh, mm = (int(x) for x in a.deadline.split(":"))
    now = dt.datetime.now()
    deadline = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if deadline <= now:
        deadline += dt.timedelta(days=1)
    skip = {x.strip() for x in a.skip.split(",") if x.strip()}

    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "data"), exist_ok=True)
    LOG = os.path.join(os.path.dirname(__file__), "..", "data", f"overnight_{now:%Y%m%d_%H%M}.log")
    code, _ = call("GET", "/api/practical/track")
    if code != 200:
        print("서버(run.bat)가 켜져 있지 않습니다 — run.bat 을 먼저 켜세요.")
        return 1
    log(f"밤샘 이어 돌리기 — {a.rounds}회 · 1부 빌드(엑셀) 마감 {deadline:%m-%d %H:%M} · 로그 {os.path.abspath(LOG)}")
    keep_awake(True)
    res = {}
    try:
        # ★ 마감(07:30)은 엑셀을 여는 1부 빌드에만 — 교육 중에 엑셀이 자동으로 열리면 안 된다.
        #   집필·3부·2부는 Claude · 브라우저 인쇄만 써서 끝까지 간다(멈추려면 화면의 멈추기 · 이 창 닫기).
        if "author" not in skip:
            res["집필"] = start_job("집필(1교시 엑셀)", "/api/practical/author", {"rounds": a.rounds}, retry=True)
        if "access" not in skip:
            res["액세스 집필"] = start_job("집필(2교시 액세스)", "/api/practical/author-access",
                                         {"rounds": a.rounds}, retry=True)
        if "build" not in skip:
            res["1부 빌드"] = start_job("1부 빌드(엑셀)", "/api/practical/build", {"rounds": a.rounds}, deadline)
        if "access-build" not in skip:
            res["액세스 빌드"] = access_build(a.rounds, deadline)
        if "ebook" not in skip:
            if True:
                log("3부 문제집: 시작(회차마다 HTML · PDF)")
                code, j = call("POST", "/api/practical/ebook", {"rounds": a.rounds, "pdf": True}, timeout=7200)
                bad = [b for b in (j.get("built") or []) if b.get("error") or b.get("pdf_errors")]
                res["3부"] = "done" if code == 200 and not bad else f"문제 {len(bad)}회차"
                for b in j.get("built") or []:
                    log(f"  3부 {b.get('round'):02d}회: " + (b.get("error") or ", ".join(b.get("pdf_errors") or []) or
                                                          f"{b.get('questions')}문항 · 실습파일 {len(b.get('files') or [])}"))
        if "part2" not in skip:
            res["2부"] = start_job("2부(끝까지)", "/api/part2-auto", {}, retry=True)
    finally:
        keep_awake(False)
    log("끝 — " + " · ".join(f"{k} {v}" for k, v in res.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
