"""/api/theory — 요약노트(이론) 4과목을 앱 안에서 집필한다.

★ 이론은 **회차별이 아니라 과목별**이다. 문항 집필(`/api/authoring`)이 회차 단위로
  도는 것과 다르다 — 산출물이 `03/summary_<key>.html` 4개이고, 회차가 늘면 같은
  4개를 다시 만든다(덮어쓰기가 맞다). 그래서 여기에는 회차 인자가 없다.

★ 모델은 **CLI 기본**(문항 집필과 같은 것)이다. 한때 Fable 을 기본으로 두었다가
  되돌렸다 — 회차 문항을 전부 같은 모델로 만들었으므로 이론만 다른 모델로 만들면
  같은 문제집 안에서 서술의 결이 갈린다(2026-08-12 지시: "페이블 쓰지 마시고
  평소대로"). 필요하면 `model` 로 그때만 바꾼다.

★ 집필이 돌고 있으면 **막는다.** 규약이 "m01~m09 전체를 병합" 이므로 회차가 다 차기
  전에 만들면 다시 만들어야 하고, 같은 PC 에서 두 잡이 도는 것은 사람이 화면에서
  구별하기 어렵다. 정말 같이 돌리려면 `allow_while_authoring: true` 로 부른다.

★ 계층 규약: 이 파일은 JSON 만 돌려준다. 무거운 일은 `services/authoring/theory.py`.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException

# ★ `BOOK_DIR` 을 **모듈 상수로 잡지 않는다.** 그것은 `.env` 의 첫 실행 기본값이고,
#   실제로 쓰는 폴더는 작업 폴더 화면에서 고른 것이다(`paths.book_dir()`).
#   상수로 잡아 두니 폴더를 SQLD 로 바꿔도 화면이 시작할 때의 빅분기를 계속 읽었다
#   — 집필 화면에 SQLD 시험정보와 빅분기 회차가 함께 뜬 원인이다(2026-08-19).
from services.authoring import theory
from services.book import paths
from services.jobs import registry

KIND = "theory"

# ★ 문항 집필의 KIND. 여기서 "돌고 있나" 를 물어야 하므로 문자열을 안다.
#   import 하지 않는다 — `routes.authoring_routes` 는 claude-agent-sdk 가 없으면
#   아예 미탑재이고(app.py 머리말), 그때 이 라우트까지 같이 죽으면 안 된다.
AUTHORING_KIND = "authoring"

# ★ 기대 회차 수는 **시험정보에서** 온다(`amplification.target_items` ÷ 회차 문항수).
#   상수 9 는 빅분기 것이었다 — SQLD 는 20회차라, 9회차만 있어도 「다 찼다」 고 봤다.
#   못 채웠으면 막지 않고 경고만 한다 — 있는 회차로 만들어 두는 것이 쓸모가 있다.
def rounds_expected() -> int:
    from services.authoring import parts

    d = parts.active() or {}
    try:
        target = int((d.get("amplification") or {}).get("target_items") or 0)
    except (TypeError, ValueError):
        target = 0
    per = parts.round_size(d) or 0
    if target > 0 and per > 0:
        return max(1, -(-target // per))
    return 9

# ★ 빈 값 = CLI 기본. 문항 집필(`/api/authoring`)이 쓰는 것과 같은 모델이다.
#   여기에 특정 모델명을 박지 않는다 — 문제집 하나가 두 모델로 갈리면 이론과 해설의
#   결이 달라지고, 그것은 나중에 고치기가 매우 어렵다.
DEFAULT_MODEL = ""


def setup_theory_routes() -> APIRouter:
    router = APIRouter(prefix="/api/theory", tags=["theory"])

    # ── 상태 ────────────────────────────────────────────────────────────────
    @router.get("/status")
    async def status() -> Dict[str, Any]:
        """모델을 부르지 않는다(무료·즉시). 화면이 "무엇이 있고 무엇이 없나" 를 그린다."""
        rounds = theory.available_rounds(paths.book_dir())
        items: List[Dict[str, Any]] = []
        for key, no in theory.keys():
            # ★ `.md` 는 만들지 않으므로 여기서도 말하지 않는다. 있는 것처럼 보고하면
            #   화면이 그 경로를 보여 주고, 사람이 그 파일을 찾으러 간다
            #   (theory.py 의 `.md` 머리말 참조).
            hp = paths.summary_html(key)
            # ★ 편 정보를 함께 준다 — 화면이 「2과목 (2/3) · 25~37번」 으로 적는다.
            _u = theory.unit_of(key)
            _pt, _rng = (_u[1], _u[2]) if _u else ((1, 1), None)
            items.append({
                "key": key, "subject_no": no, "subject": theory.subjects().get(no, ''),
                "part": _pt[0], "part_total": _pt[1],
                "q_from": (_rng or [None, None])[0], "q_to": (_rng or [None, None])[1],
                "label": theory.unit_label(key),
                "range_label": theory.unit_range_label(key),
                "html_path": paths.rel(hp), "html_bytes": paths.size(hp),
                "exists": os.path.isfile(hp),
            })
        return {
            "provider": "claude", "default_model": DEFAULT_MODEL,
            "book": paths.book_dir(),
            "keys": [k for k, _ in theory.keys()],
            "items": items,
            "rounds": rounds,
            "rounds_expected": rounds_expected(),
            # ★ 화면이 "지금 눌러도 되나" 를 이 값으로 판단한다.
            "rounds_ready": len(rounds) >= rounds_expected(),
            "authoring_running": bool(registry.running(AUTHORING_KIND)),
            "running_job": (registry.running(KIND) or {}).get("id"),
        }

    # ── 집필 ────────────────────────────────────────────────────────────────
    @router.post("/draft")
    async def start_draft(body: Dict[str, Any] = Body(default_factory=dict)):
        """과목 몇 개를 **연달아** 집필한다.

        ★ 연달아여야 프롬프트 캐시가 걸린다. 4과목이 같은 `SYSTEM` 접두를 쓰므로
          1시간 안에 이어 돌리면 접두가 캐시 읽기로 전환된다(provider.py 실측).
        """
        raw = body.get("keys") or [k for k, _ in theory.keys()]
        keys: List[str] = []
        for k in raw:
            k = str(k or "").strip()
            if not theory.no_of(k):
                raise HTTPException(
                    400, f"알 수 없는 요약노트 키: {k!r} "
                         f"({' | '.join(x for x, _ in theory.keys())})")
            if k not in keys:          # 같은 과목을 두 번 돌리지 않는다
                keys.append(k)
        if not keys:
            raise HTTPException(400, "집필할 과목이 없습니다.")

        if busy := registry.running(KIND):
            raise HTTPException(
                409, f"이론 집필이 이미 돌고 있습니다 (job {busy['id'][:8]}).")

        # ★ 문항 집필 중이면 막는다. 이유는 머리말에 있다.
        if not bool(body.get("allow_while_authoring")):
            if a := registry.running(AUTHORING_KIND):
                raise HTTPException(
                    409, f"문항 집필이 돌고 있습니다 (job {a['id'][:8]}). "
                         f"이론은 m01~m{rounds_expected():02d} 전체를 병합해 만드는 것이 "
                         f"규약이므로, 회차가 다 찬 뒤에 부르십시오. 지금 있는 회차로 "
                         f"만들려면 allow_while_authoring: true 로 부르십시오.")

        redo = bool(body.get("redo"))
        todo = [k for k in keys if redo or not theory.is_done(k)]
        skipped = [k for k in keys if k not in todo]
        if not todo:
            raise HTTPException(
                400, f"고르신 {len(skipped)}과목이 모두 이미 있습니다. "
                     f"다시 만들려면 redo: true 로 부르십시오.")

        model = (body.get("model") or DEFAULT_MODEL).strip()
        effort = (body.get("effort") or "").strip() or None
        rounds = theory.available_rounds(paths.book_dir())

        note = " · ".join(
            [f"{len(todo)}과목", f"소스 {len(rounds)}회차",
             f"모델 {model or '기본(CLI)'}"]
            + ([f"{len(skipped)}과목은 이미 있어 건너뜀"] if skipped else []))
        job = registry.create(KIND, f"이론 {len(todo)}과목", list(todo), note=note)

        if skipped:
            registry.log(job, f"이미 있는 {len(skipped)}과목은 건너뜁니다: "
                              f"{', '.join(skipped)}  (다시 만들려면 redo)",
                         force=True)
        # ★ 회차가 모자란 것을 조용히 넘기지 않는다. 나중에 "왜 m09 내용이 없지" 를
        #   물을 때 짚을 곳이 있어야 한다.
        if len(rounds) < rounds_expected():
            registry.log(
                job, f"★ 소스가 {len(rounds)}회차뿐입니다({', '.join(rounds) or '없음'}). "
                     f"규약은 m01~m{rounds_expected():02d} 전체 병합입니다 — 남은 회차를 "
                     f"집필한 뒤 redo 로 다시 부르십시오.", force=True)

        def work(j: Dict[str, Any]) -> None:
            import shutil
            total = 0.0
            # ★ 읽을 것만 담은 폴더를 **잡이 한 번** 만들어 4과목이 나눠 쓴다.
            #   과목마다 새로 만들면 `cwd` 가 매번 달라져 프롬프트 캐시 접두가 갈린다
            #   (theory.draft_theory 의 `view` 머리말). 실측 차이가 4배다.
            view = theory.source_view(paths.book_dir())
            try:
                _run_all(j, view)
            finally:
                shutil.rmtree(view, ignore_errors=True)

        def _run_all(j: Dict[str, Any], view: str) -> None:
            total = 0.0
            for key in todo:
                if j.get("cancel_requested"):
                    registry.item(j, key, status="skipped", error="취소됨")
                    continue
                no = theory.no_of(key)
                registry.update(j, current=key)
                registry.item(j, key, status="running")
                registry.log(j, f"[{key}] {no}과목 · {theory.subjects().get(no, '')} 집필 시작",
                             force=True)
                try:
                    res = theory.draft_theory(
                        key=key, book_dir=paths.book_dir(), model=model, effort=effort,
                        view=view,
                        on_activity=lambda s, j=j, k=key: registry.log(j, f"[{k}] {s}"))
                except Exception as e:            # noqa: BLE001
                    # ★ 한 과목이 죽어도 남은 과목은 간다. 여기서 예외를 내면 이미
                    #   만든 과목의 잡 상태까지 error 로 덮인다.
                    registry.item(j, key, status="error",
                                  error=f"{type(e).__name__}: {e}")
                    registry.log(j, f"[{key}] (문제) {type(e).__name__}: {e}", force=True)
                    continue
                total += res.cost_usd
                for w in res.warnings:
                    registry.log(j, f"[{key}] (주의) {w}", force=True)
                if res.ok:
                    # ★ 대주제·소주제 수를 남긴다 — "원고가 몇 번까지 있나" 를 사람이
                    #   묻는다(2026-08-12). 기존 원고는 대주제 5~7 · 소주제 0~3 이었다.
                    registry.log(j, f"[{key}] 합격 · 대주제 {res.h2_count}개 · "
                                    f"소주제 {res.h3_count}개 · 문번 {res.refs}곳 · "
                                    f"{res.html_bytes:,}바이트 · {res.turns}턴 · "
                                    f"{res.seconds / 60:.1f}분 · ${res.cost_usd:.3f}",
                                 force=True)
                    registry.item(j, key, status="done",
                                  output=(res.written or [""])[0],
                                  seconds=round(res.seconds, 1))
                else:
                    for pr in res.problems:
                        registry.log(j, f"[{key}] (문제) {pr}", force=True)
                    # ★ 검증에 걸리면 파일을 쓰지 않았다(theory.draft_theory 참조).
                    #   `03/` 이 곧 발행 원천이라 잘못된 것을 남길 수 없다.
                    registry.log(j, f"[{key}] 파일을 쓰지 않았습니다 — "
                                    f"기존 요약노트는 그대로입니다.", force=True)
                    registry.item(j, key, status="error",
                                  seconds=round(res.seconds, 1),
                                  error=(res.problems or ["검증 실패"])[0])
            registry.log(j, f"합계 ${total:.3f} — 구독이라 청구는 없지만 "
                            f"사용량의 대리 지표입니다.", force=True)
            registry.log(j, "★ 발행되는 것은 `03/*.html` 입니다. `#/summary` 에서 "
                            "검수한 뒤 발행하십시오.", force=True)
            registry.finish(j, "done", result={"cost_usd": round(total, 4)})

        registry.spawn(job, work)
        return {"job": job["id"], "keys": todo, "skipped": skipped,
                "model": model, "rounds": rounds}

    return router
