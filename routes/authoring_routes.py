"""/api/authoring — 앱 안에서 집필한다. **API 키 없음** · 집필자 각자의 구독 OAuth.

흐름 — 네 단계가 한 화면에서 끝난다:

    집필(파트 단위) → 스테이징(data/authoring/) → 반입(_rounds/) → 파생(02/·04/)

★ 계층 규약: 이 파일은 JSON 만 돌려준다(페이지 HTML 은 app.py 만). 무거운 일은
  `services/authoring/*` 이 하고 여기서는 배선과 잡 관리만 한다.

★ 집필은 **잡**이다. 파트 1개가 1~3분, 회차 1개(8파트)는 20분쯤 간다. 요청-응답으로
  두면 브라우저가 먼저 끊고, 사람은 "멈췄다" 고 읽는다 — 렌더에서 이미 겪은 것이다.

★ 동시 실행을 막는다. 파트를 두 개 같이 돌리면 프롬프트 캐시 접두가 갈려 비용이
  4배가 되고(실측 $0.066 → $0.257), 구독 한도도 같이 태운다.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException

# ★ `BOOK_DIR` 을 **모듈 상수로 잡지 않는다.** 그것은 `.env` 의 첫 실행 기본값이고,
#   실제로 쓰는 폴더는 작업 폴더 화면에서 고른 것이다(`paths.book_dir()`).
#   상수로 잡아 두니 폴더를 SQLD 로 바꿔도 화면이 시작할 때의 빅분기를 계속 읽었다
#   — 집필 화면에 SQLD 시험정보와 빅분기 회차가 함께 뜬 원인이다(2026-08-19).
from datetime import date

# ★ `parts` 로 들여오면 안 된다 — `start_draft` 안에 **파트 번호 목록**이라는
#   지역 변수 `parts` 가 있어서 모듈이 가려진다. 그 상태로 `parts.require()` 를
#   부르면 리스트에서 메서드를 찾아 500 이 난다(2026-08-19 실측: 「서버 내부 오류」).
from services.authoring import (cost, derive, draft, examspec, merge, pool,
                                 provider)
from services.authoring import parts as examparts
# ★ 라우트 인자 이름이 `spec` 이라 모듈을 그 이름으로 두면 가려진다 — 별칭으로 받는다.
from services.authoring import spec as authspec
from services.jobs import registry
from services.book import paths

KIND = "authoring"

# 연속 몇 번 헛발질하면 멈출 것인가. 3 인 이유: 1~2회는 일시적 과부하(529)로도
# 나므로 그때 멈추면 멀쩡한 실행을 죽인다. 3회 연속이면 한도·인증 쪽이다.
STALL_LIMIT = 3


def _round_ok(code: str) -> str:
    code = (code or "").strip()
    if not (len(code) == 3 and code[0] == "m" and code[1:].isdigit()):
        raise HTTPException(400, "회차코드는 m01 ~ m99 형태여야 합니다.")
    return code


def _derive_hint(book_dir: str, limit: int = 24) -> str:
    """기출 파일명 목록. **내용은 넣지 않는다** — 모델이 Read 로 필요한 것만 읽는다.

    240문항을 프롬프트에 부으면 접두가 거대해지고 파트마다 그 값을 다시 태운다.
    실측: 문항 1개에 `Read:01/01-01.md` 1회로 끝났다.
    """
    import glob
    import os
    names = sorted(os.path.basename(p)[:-3]
                   for p in glob.glob(os.path.join(book_dir, "01", "*.md"))
                   if not os.path.basename(p).startswith("_"))
    if not names:
        return ""
    head = names[:limit]
    more = f" … 외 {len(names) - len(head)}개 (`01/` 를 Glob 으로 훑어도 된다)" \
        if len(names) > len(head) else ""
    return ", ".join(head) + more


def setup_authoring_routes() -> APIRouter:
    router = APIRouter(prefix="/api/authoring", tags=["authoring"])

    # ── 상태 ────────────────────────────────────────────────────────────────
    @router.get("/status")
    async def status():
        """★ 모델을 부르지 않는다(무료·즉시). 화면을 열 때마다 $0.25 를 태울 수 없다."""
        st = provider.status()
        job = registry.running(KIND)
        return {**st, "book": paths.book_dir(),
                "running_job": job["id"] if job else None,
                # ★ 시험정보에서 온다 — 상수가 아니다(품목마다 다르다).
                "part_size": examparts.part_size(examparts.active()),
                "parts": draft.n_parts(),
                "round_size": draft.round_size(),
                "part_labels": [draft.part_label(i)
                                for i in range(1, draft.n_parts() + 1)]}

    @router.post("/ping")
    async def ping():
        """실제로 한 번 불러 본다. ★ 약 $0.25 가 든다 — 버튼을 눌렀을 때만."""
        ok, msg = provider.ClaudeAuthor().ping()
        return {"ok": ok, "message": msg}

    # ── 시험정보 ────────────────────────────────────────────────────────────
    # ★ 시험은 매년·개정마다 바뀐다. 코드에 박아 두면 개정마다 코드를 고쳐야 하고
    #   SME 가 할 수 없다. 파일로 두고 화면에서 고치고 주고받게 한다.
    @router.get("/exams")
    async def exams():
        # ★ 작업 폴더의 품목을 함께 준다. 화면이 그것을 기본 선택으로 쓴다 —
        #   「고르십시오」로 비워 두면 새로고침마다 다시 고르게 되고, 목록 첫 번째를
        #   기본으로 두면 폴더와 다른 품목이 조용히 잡힌다. 폴더가 진실이다.
        return {"dir": examspec.EXAMS_DIR, "items": examspec.listing(),
                "active": (examparts.active() or {}).get("id") or ""}

    @router.get("/exams/{exam_id}")
    async def exam_get(exam_id: str):
        """내보내기도 이 응답을 그대로 쓴다 — 화면이 JSON 을 파일로 내려 준다."""
        try:
            d = examspec.load(exam_id)
        except (OSError, ValueError) as e:
            raise HTTPException(404, str(e))
        errs, warns = examspec.validate(d)
        return {"id": exam_id, "doc": d, "errors": errs, "warnings": warns}

    @router.put("/exams/{exam_id}")
    async def exam_put(exam_id: str, body: Dict[str, Any] = Body(...)):
        """가져오기. ★ 검증을 통과하지 않으면 쓰지 않는다."""
        doc = body.get("doc") if isinstance(body.get("doc"), dict) else body
        try:
            r = examspec.save(exam_id, doc)
        except (OSError, ValueError) as e:
            raise HTTPException(400, str(e))
        # ★ 캐시를 버린다. `parts.active()` 의 캐시 키는 `_book.json` 의 mtime 이라,
        #   시험정보 파일만 새로 만들면 **키가 그대로**다 — 서버가 「이 폴더엔
        #   시험정보가 없다」를 계속 들고 있는다(`parts.invalidate` 머리말이 바로
        #   이 호출을 요구한다).
        # ★ 그냥 「옛 규격으로 돈다」로 끝나지 않는다. 실측 2026-09-08:
        #     active() = None  →  draft._pd() 가 .env 의 PD_CODE(bigdata)로 떨어짐
        #                      →  스테이징을 data/authoring/bigdata/ 에서 읽음
        #                      →  ADsP 화면이 빅분기 9회차·36파트를 「이미 합격」으로
        #                         세고, [실행] 이 그 위에 이어 쓰려 했다.
        examparts.invalidate()
        return r

    @router.post("/exams/{exam_id}/confirm")
    async def exam_confirm(exam_id: str, body: Dict[str, Any] = Body(default={})):
        """★ 「확인했다」 를 사람이 누른 기록.

        `revision.confirmed` 는 코드가 알 수 없는 값이다 — 이 파일의 회차 문항수·과목
        구성이 **시행처 공고와 같은가** 는 사람이 공고를 보고 판단한다. 그래서 검증이
        오류가 아니라 경고로 남기고, 여기서 사람의 손짓으로 바꾼다.

        누른 날짜를 `checked_at` 에 박는다 — 「언제 기준의 값인가」 가 이 값의 전부다.
        해마다 개정되므로 작년에 확인한 true 는 올해 아무 뜻이 없다.
        """
        try:
            d = examspec.load(exam_id)
        except (OSError, ValueError) as e:
            raise HTTPException(404, str(e))
        on = bool(body.get("confirmed", True))
        rev = dict(d.get("revision") or {})
        rev["confirmed"] = on
        # 확인일은 **누른 날**이다. 끌 때는 남겨 둔다 — 언제까지 유효했는지가 단서다.
        if on:
            rev["checked_at"] = date.today().isoformat()
            if body.get("checked_by"):
                rev["checked_by"] = str(body["checked_by"])[:80]
            if body.get("source_url"):
                rev["source_url"] = str(body["source_url"])[:400]
        d["revision"] = rev
        try:
            r = examspec.save(exam_id, d)
        except (OSError, ValueError) as e:
            raise HTTPException(400, str(e))
        examparts.invalidate()          # 위 exam_put 의 주석 참조
        r["confirmed"] = on
        r["checked_at"] = rev.get("checked_at") or ""
        return r

    @router.get("/plan")
    async def plan(multiple: int = 0, start: str = "", spec: str = "",
                   exam: str = ""):
        """기출 회차 × 배수 → 만들 회차 목록. 화면의 표가 이걸 그린다.

        ★ 배수는 **행별**이다. `spec="01:3,02:3,03:2"` 로 받는다 — SQLD 는 7회 OCR 중
          여섯을 ×3, 마지막을 ×2 로 해서 20회차 × 50문항 = 1,000제를 맞춘다.
          전역 `multiple` 은 처음 열 때(아직 행별 값이 없을 때)만 쓴다.

        ★ 회차당 문항수는 **시험정보 파일**에서 온다(코드가 아니다). 빅분기 80,
          SQLD 50 — 매년·개정마다 바뀌므로 코드에 박을 수 없다.
        """
        per: Dict[str, int] = {}
        for tok in (spec or "").split(","):
            if ":" in tok:
                k, _, v = tok.partition(":")
                if k.strip() and v.strip().isdigit():
                    per[k.strip()] = int(v)
        try:
            p = pool.plan_rounds(paths.book_dir(), multiple or 3, start, per_round=per)
        except ValueError as e:
            raise HTTPException(400, str(e))

        p["modes"] = [{"id": m, "label": authspec.MODE_LABEL[m]} for m in authspec.MODES]
        # 회차 규격 — 화면이 총 문항수를 계산하는 근거
        try:
            d = examspec.load(exam) if exam else None
        except (OSError, ValueError):
            d = None
        if d is None:
            # ★ 폴백은 **작업 폴더의 품목**이다. 「목록의 첫 번째」로 떨어지면
            #   SQLD 폴더를 열어 놓고 빅분기 규격이 나온다 — 진행 칩이 `1~20 / 21~40 /
            #   41~60` 으로 떴다(2026-08-20 실측). 폴더가 진실이다.
            d = examparts.active()
        # ★ 여기서 되돌림값을 쓰지 않는다 (2026-09-08).
        #
        #   전에는 `or 80` · `or 20` 이었다. 빅분기 규격이다. 이 화면은 「읽기 화면은
        #   되돌림값으로 견딘다」 는 규칙의 예외다 — **바로 옆에 [실행] 이 있고**,
        #   그 버튼이 몇 시간과 수십 달러를 쓴다. 그럴듯한 숫자를 보여 주면 사람은
        #   그것을 근거로 누른다(실측: ADsP 폴더에서 「80문항 · 4파트」가 떴다).
        #
        #   못 찾으면 **비워서 준다.** 화면이 「시험정보가 없습니다」를 그리고
        #   실행을 막는다. 숫자가 없는 것이 틀린 숫자보다 낫다.
        p["exam"] = (d or {}).get("id") or ""
        p["exam_missing"] = d is None
        p["round_size"] = ((d or {}).get("round") or {}).get("size") or None
        p["part_size"] = ((d or {}).get("round") or {}).get("part_size") or None
        # ★ 과목 수는 **시험정보에서** 나온다. 빅분기 80/20 = 4과목, SQLD 50/25 = 2과목.
        #   화면이 `part_count` 를 읽는데 서버가 그 키를 준 적이 없어 늘 4 로 떨어지고
        #   있었다 — 빅분기라 우연히 맞았을 뿐이다(2026-08-10).
        # ★ 파트는 **과목에서** 만든다 — 나눗셈이 아니다(`services/authoring/parts.py`).
        #   전에는 회차÷상한 이었고, SQLD 는 그 값이 2 인데 실제 집필은 4파트를
        #   돌려 없는 문항 61~80 을 부르려 했다(2026-08-19 실측).
        # 시험정보가 없으면 파트도 지어내지 않는다 — `parts_of(None)` 은 빅분기
        # 규격(1~80번 4파트)을 만들어 낸다. 그건 읽기 화면용 되돌림값이다.
        _ps = examparts.parts_of(d) if d else []
        p["part_count"] = len(_ps) or None
        p["part_labels"] = [examparts.label(d, x["index"]) for x in _ps]
        # 예상 소모량을 여기서 다시 잡는다. `plan_rounds` 는 시험정보를 모르고
        # 기본 4과목으로 계산한다 — 과목 수가 다른 시험이면 그 값이 틀린다.
        p["est"] = cost.estimate(p["n_rounds"], part_count=p["part_count"] or 0)
        p["est_cost_usd"] = p["est"]["usd"]
        p["est_minutes"] = p["est"]["minutes"]
        p["est_note"] = p["est"]["note"]
        return p

    @router.get("/round/{code}")
    async def round_state(code: str):
        """파트별 상태 + 반입 가능 여부. 화면의 표가 이걸 그린다."""
        code = _round_ok(code)
        staged = draft.list_staged(code)
        items, blocked = merge.collect_ready(code)
        return {
            "round": code, "parts": staged,
            "ready_items": len(items), "blocked": blocked,
            "rounds_path": merge.rounds_path(paths.book_dir(), code),
            "local_edits": derive.guard_local_edits(paths.book_dir(), code),
            "staged_cost_usd": round(
                sum(float(p.get("cost_usd") or 0) for p in staged), 4),
        }

    # ── 집필 (잡) ───────────────────────────────────────────────────────────
    @router.post("/draft")
    async def start_draft(body: Dict[str, Any] = Body(...)):
        """파트 몇 개를 **연달아** 집필한다.

        ★ 연달아가 중요하다. 1시간 안에 같은 접두로 다시 부르면 33,682토큰이 캐시
          읽기로 전환돼 비용이 $0.257 → $0.066 로 떨어진다(실측). 사이를 벌리면
          매번 캐시를 새로 만든다.
        """
        # ★ 회차마다 **기준이 다를 수 있다.** 화면이 회차별로 보낸다:
        #     items = [{"round": "m10", "mode": "exam"}, {"round": "m11", "mode": "derive"}]
        #   전역 `mode` 하나였던 것을 고쳤다 — 기출 1회차는 시험기준으로, 2회차는
        #   연습문제화로 갈 수 있어야 한다(2026-08-10).
        raw = body.get("items")
        if not raw:
            # 옛 형태 호환: rounds[] + mode 하나
            rs = body.get("rounds") or ([body["round"]] if body.get("round") else [])
            m0 = (body.get("mode") or "exam").strip()
            raw = [{"round": x, "mode": m0} for x in rs]
        items: List[Dict[str, str]] = []
        for it in raw:
            rc = _round_ok(str((it or {}).get("round") or ""))
            md = (str((it or {}).get("mode") or "exam")).strip()
            if md not in authspec.MODES:
                raise HTTPException(400, f"집필 기준이 올바르지 않습니다: {md} "
                                         f"({' | '.join(authspec.MODES)})")
            items.append({"round": rc, "mode": md})
        if not items:
            raise HTTPException(400, "집필할 회차가 없습니다.")
        # 같은 회차가 두 번 오면 뒤엣것이 앞엣것을 덮는다 — 조용히 두 번 돌리지 않는다.
        seen: Dict[str, str] = {}
        for it in items:
            seen[it["round"]] = it["mode"]
        items = [{"round": k, "mode": v} for k, v in seen.items()]

        parts: List[int] = [int(x) for x in (body.get("parts") or [])]
        if not parts:
            parts = list(range(1, draft.n_parts() + 1))
        bad = [p for p in parts if not 1 <= p <= draft.n_parts()]
        if bad:
            raise HTTPException(400, f"파트 번호가 1~{draft.n_parts()} 밖입니다: {bad}")

        # ★ 시험정보가 없으면 **시작하지 않는다.** 없으면 빅분기 규격(80문항·4파트)으로
        #   조용히 돌아 1,000문항이 틀린 규격으로 만들어진다 — 되돌림값이 하필
        #   그럴듯한 값이라 아무 신호도 나지 않는다(`parts.require` 머리말).
        try:
            examparts.require()
        except examparts.NoExamSpec as e:
            raise HTTPException(409, str(e)) from e

        if (busy := registry.running(KIND)):
            raise HTTPException(
                409, f"집필이 이미 돌고 있습니다 (job {busy['id'][:8]}). "
                     "동시에 돌리면 프롬프트 캐시가 갈려 비용이 4배가 됩니다.")

        model = (body.get("model") or "").strip()
        effort = (body.get("effort") or "").strip() or None
        # ★ 실행 순서를 여기서 확정한다 — **회차 안의 과목을 연달아** 돌린다.
        #   회차를 바깥 루프에 두는 이유: 한 회차의 4과목이 같은 시스템 프롬프트 접두를
        #   쓰므로 1시간 캐시가 걸린다(실측 $3.6 → $1.4). 과목을 바깥에 두면 매번 갈린다.
        #
        # ★ **이미 합격한 과목은 건너뛴다.** 이것이 없으면 30/36 에서 끊긴 잡을 다시
        #   돌릴 때 이미 만든 30과목을 또 태운다(실측 $44). 7시간짜리 작업은 반드시
        #   중간에 끊긴다고 보고 만들어야 한다 — 구독 한도·서버 재시작·정전.
        #   `redo: true` 로 부르면 전부 다시 만든다.
        redo = bool(body.get("redo"))
        # ★ 회차 4과목이 다 끝나면 **반입·파생까지 자동으로** 간다. 9회차면 사람이
        #   버튼을 18번 눌러야 하는데, 그 7시간 동안 아무도 화면을 안 본다.
        #   자동으로 둬도 되는 근거: ① `build.py --round mNN` 은 **그 회차만** 만든다
        #   (책 전체 렌더가 아니다) ② 모델을 안 부르므로 한도를 안 먹는다
        #   ③ 덮어쓰기 위험은 `guard_local_edits` 가 막는다 — 걸리면 건너뛰고
        #   버튼을 사람에게 남긴다.
        auto = body.get("auto_derive")
        auto = True if auto is None else bool(auto)
        todo: List[tuple] = []
        skipped: List[str] = []
        for it in items:
            for p in parts:
                if not redo and draft.is_done(it["round"], p):
                    skipped.append(f"{it['round']}-p{p}")
                    continue
                todo.append((it["round"], p, it["mode"]))
        if not todo:
            raise HTTPException(
                400, f"고르신 {len(skipped)}과목이 모두 이미 집필돼 있습니다. "
                     "반입·파생으로 넘어가시거나, 다시 만들려면 "
                     "`data/authoring/` 의 해당 회차 폴더를 지우십시오.")
        keys = [f"{rc}-p{p}" for rc, p, _ in todo]
        codes = [it["round"] for it in items]
        label = (f"집필 {codes[0]}" if len(codes) == 1
                 else f"집필 {codes[0]}~{codes[-1]} ({len(codes)}회차)")
        modes_used = sorted({it["mode"] for it in items})
        job = registry.create(
            KIND, label, keys,
            note=" · ".join([authspec.MODE_LABEL.get(m, m) for m in modes_used]
                            # ★ 파트 크기가 파트마다 다를 수 있다(과목을 쪼갠 경우).
                            #   `len × 상수` 로 세면 SQLD 에서 문항수가 틀린다.
                            + [f"{len(todo)}파트",
                               f"{sum(len(draft.part_numbers(i)) for i in todo)}문항"
                               if all(isinstance(i, int) for i in todo) else ""]
                            + ([f"{len(skipped)}과목은 이미 있어 건너뜀"] if skipped else [])))
        # 연습문제화가 하나라도 있으면 기출 목록을 준비한다(시험기준 회차는 안 쓴다).
        hint = _derive_hint(paths.book_dir()) if "derive" in modes_used else ""
        # ★ 건너뛴 것을 조용히 넘기지 않는다. 사람이 "9회차 시켰는데 왜 20과목만
        #   도나" 를 물을 때 짚을 곳이 있어야 한다.
        if skipped:
            registry.log(job, f"이미 합격한 {len(skipped)}과목은 건너뜁니다: "
                              + ", ".join(skipped[:12])
                              + (f" 외 {len(skipped) - 12}개" if len(skipped) > 12 else "")
                              + "  (전부 다시 만들려면 redo 로 부르십시오)", force=True)

        def finish_round(j: Dict[str, Any], rc: str) -> None:
            """회차 하나가 다 찼으면 반입 → 파생까지 간다.

            ★ **절대 예외를 밖으로 내지 않는다.** 여기서 죽으면 남은 회차의 집필까지
              같이 죽는다 — 몇 시간짜리 모델 호출을 파생 실패로 잃을 수는 없다.
            ★ 조건이 안 맞으면 조용히 넘기지 않고 이유를 로그에 남긴다. 사람이
              나중에 "왜 02 가 안 생겼지" 를 물을 때 짚을 곳이 있어야 한다.
            """
            try:
                staged = draft.list_staged(rc)
                ok_n = sum(1 for s in staged if s.get("exists") and s.get("ok"))
                if ok_n < draft.n_parts():
                    bad = [draft.part_label(s["part"]) for s in staged
                           if not (s.get("exists") and s.get("ok"))]
                    registry.log(j, f"[{rc}] 반입 보류 — {draft.n_parts()}파트 중 "
                                    f"{ok_n}파트만 합격했습니다 ({', '.join(bad)}). "
                                    f"실패한 파트를 다시 돌린 뒤 화면에서 반입하십시오.",
                                 force=True)
                    return

                m = merge.merge_round(book_dir=paths.book_dir(), round_code=rc)
                registry.log(j, f"[{rc}] 반입 완료 — {m.get('total')}문항 → "
                                f"{m.get('path')}", force=True)

                edits = derive.guard_local_edits(paths.book_dir(), rc)
                if edits:
                    registry.log(j, f"[{rc}] 파생 건너뜀 — `02/` 에 더 새로운 파일이 "
                                    f"{len(edits)}개 있습니다. 파생하면 그 교정이 "
                                    f"되돌아갑니다. 화면에서 확인 후 직접 파생하십시오.",
                                 force=True)
                    return

                d = derive.derive_round(paths.book_dir(), rc)
                if d.get("ok"):
                    registry.log(j, f"[{rc}] 파생 완료 — 02/ · 04/ 가 만들어졌습니다.",
                                 force=True)
                else:
                    registry.log(j, f"[{rc}] 파생 실패 — "
                                    f"{(d.get('err') or d.get('out') or '')[:400]}\n"
                                    f"집필은 계속합니다. 화면에서 직접 파생하십시오.",
                                 force=True)
            except Exception as e:                     # noqa: BLE001
                registry.log(j, f"[{rc}] 반입·파생 중 오류 — {type(e).__name__}: {e}\n"
                                f"집필은 계속합니다. 화면에서 직접 하십시오.", force=True)

        def work(j: Dict[str, Any]) -> None:
            total_cost = 0.0
            # ★ 헛발질이 이어지면 멈춘다. 구독 **주간 한도**에 걸리면 모든 호출이
            #   즉시 실패하는데, 브레이크가 없으면 남은 35과목을 몇 초 만에 줄줄이
            #   실패로 돌아 놓고 "36개 중 35개 실패" 라는 화면을 남긴다. 사람은
            #   그걸 보고 뭐가 깨진 줄 안다 — 실제로는 그냥 한도다.
            #
            # ★ 비용으로 가른다. **모델을 못 부른 실패는 비용이 0 이다**(한도·인증·
            #   네트워크). 문항이 모자라거나 검증에 걸린 것은 이미 돈이 나갔으므로
            #   0 이 아니다 — 그런 것은 다음 과목에서 잘 될 수 있으니 계속 간다.
            stalled = 0
            for idx, (rc, p, md) in enumerate(todo):
                key = f"{rc}-p{p}"
                if j.get("cancel_requested"):
                    # ★ `skipped` 가 아니다 — 그 말은 「할 일이 없어 건너뜀」이고
                    #   진행률에 들어간다. 이건 **안 한** 것이다(registry 머리말).
                    registry.item(j, key, status="canceled", error="중단됨")
                    continue
                nums = draft.part_numbers(p)
                registry.update(j, current=key)
                registry.item(j, key, status="running")
                registry.log(j, f"[{key}] {nums[0]}~{nums[-1]}번 집필 시작", force=True)

                res = draft.draft_part(
                    round_code=rc, part_index=p, book_dir=paths.book_dir(),
                    derive_hint=(hint if md == "derive" else ""), mode=md,
                    round_index=codes.index(rc) + 1, round_total=len(codes),
                    model=model, effort=effort,
                    # ★ 모델이 무엇을 읽고 있는지 흘린다. 과목 1개가 10~20분씩 가는데
                    #   화면이 한 글자도 안 바뀌면 멈춘 것으로 보인다.
                    on_activity=lambda s, j=j, k=key: registry.log(j, f"[{k}] {s}"))
                total_cost += res.cost_usd

                for w in res.warnings:
                    registry.log(j, f"[{key}] (주의) {w}", force=True)
                if res.ok:
                    stalled = 0
                    registry.log(j, f"[{key}] 합격 · {len(res.items)}문항 · "
                                    f"{res.turns}턴 · {res.seconds / 60:.1f}분 · "
                                    f"${res.cost_usd:.3f}", force=True)
                    registry.item(j, key, status="done", output=res.path,
                                  seconds=round(res.seconds, 1))
                else:
                    for pr in res.problems:
                        registry.log(j, f"[{key}] (문제) {pr}", force=True)
                    registry.item(j, key, status="error", output=res.path,
                                  seconds=round(res.seconds, 1),
                                  error=(res.problems or ["검증 실패"])[0])
                    stalled = stalled + 1 if res.cost_usd <= 0 else 0
                    if stalled >= STALL_LIMIT:
                        why = (res.problems or ["원인을 알 수 없습니다"])[0]
                        registry.log(
                            j, f"연속 {stalled}회 모델을 부르지 못해 멈춥니다 — {why}\n"
                               f"구독 한도에 걸렸을 가능성이 큽니다. "
                               f"Claude 사용량 화면에서 한도와 재설정 시각을 확인하십시오.\n"
                               f"★ 여기까지 만든 것은 날아가지 않습니다. 합격한 과목은 "
                               f"`data/authoring/` 에 파일로 남아 있고, 한도가 풀린 뒤 "
                               f"같은 회차로 다시 [실행] 하면 **끝난 과목은 건너뛰고 "
                               f"남은 것부터** 이어서 갑니다.", force=True)
                        for rc2, p2, _ in todo[idx + 1:]:
                            registry.item(j, f"{rc2}-p{p2}", status="canceled",
                                          error="앞선 과목이 연속 실패해 포기")
                        registry.log(j, f"합계 ${total_cost:.3f}", force=True)
                        registry.finish(j, "error",
                                        error=f"모델 호출 연속 실패 — {why}",
                                        result={"cost_usd": round(total_cost, 4)})
                        return

                # ── 회차 경계 ──────────────────────────────────────────────
                # ★ 이 회차의 마지막 과목이었으면 반입·파생까지 간다. 회차를 바깥
                #   루프에 두었으므로(캐시 때문) 다음 항목의 회차가 다르면 경계다.
                if auto and (idx + 1 >= len(todo) or todo[idx + 1][0] != rc):
                    finish_round(j, rc)

            registry.log(j, f"합계 ${total_cost:.3f} — 구독이라 청구는 없지만 "
                            f"사용량의 대리 지표입니다.", force=True)
            registry.finish(j, "done", result={"cost_usd": round(total_cost, 4)})

        registry.spawn(job, work)
        return {"job": job["id"], "items": items, "parts": parts,
                "todo": len(todo), "skipped": skipped}

    # ── 반입 ────────────────────────────────────────────────────────────────
    @router.post("/merge")
    async def do_merge(body: Dict[str, Any] = Body(...)):
        """스테이징 → `_rounds/mNN.json`. 검증에 걸린 파트가 하나라도 있으면 멈춘다."""
        code = _round_ok(body.get("round") or "")
        return merge.merge_round(book_dir=paths.book_dir(), round_code=code,
                                 dry_run=bool(body.get("dry_run")))

    # ── 파생 ────────────────────────────────────────────────────────────────
    @router.post("/derive")
    async def do_derive(body: Dict[str, Any] = Body(...)):
        """`_rounds` → `02/`·`04/`. ★ 덮어쓰기다 — 로컬 교정이 있으면 막는다."""
        code = _round_ok(body.get("round") or "")
        out = derive.derive_round(paths.book_dir(), code,
                                  dry_run=bool(body.get("dry_run")),
                                  force=bool(body.get("force")))
        out["validate"] = derive.validate_round(paths.book_dir(), code)
        return out

    return router
