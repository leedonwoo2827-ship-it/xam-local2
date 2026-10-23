# -*- coding: utf-8 -*-
"""시험정보(`exams/*.json`) 읽기 · 검증 · 저장.

★ 왜 파일로 두는가 — 시험은 **매년, 그리고 개정될 때마다 바뀐다**(2026-08-10).
  회차당 문항수·과목 구성·난이도 분포를 코드에 박아 두면 개정마다 코드를 고쳐야 하고,
  그건 SME 가 할 수 없는 일이다. JSON 으로 빼면 화면에서 고치고 주고받을 수 있다.

★ 검증이 이 파일의 핵심이다. 값이 틀린 JSON 을 통과시키면 집필이 그것을 기준으로
  20~80회 돌고(수 시간·수십 달러), **틀린 문제집이 나온 뒤에** 안다.
  그래서 `validate()` 가 합을 검산한다 — 과목 문항수의 합 == 회차 문항수.

★ FastAPI 를 import 하지 않는다(services/* 규약).
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Dict, List, Tuple

from core.atomic_io import atomic_write_json, backup_sibling
from core.constants import BASE_DIR

EXAMS_DIR = os.path.join(BASE_DIR, "exams")
_ID = re.compile(r"^[a-z0-9][a-z0-9\-]{0,40}$")


def path_of(exam_id: str) -> str:
    if not _ID.fullmatch(exam_id or ""):
        raise ValueError(f"시험정보 id 가 올바르지 않습니다: {exam_id} "
                         "(영소문자·숫자·하이픈)")
    return os.path.join(EXAMS_DIR, f"{exam_id}.json")


def load(exam_id: str) -> Dict[str, Any]:
    p = path_of(exam_id)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"시험정보가 없습니다: {p}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def validate(d: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """(막는 것, 알려줄 것). 막는 것이 하나라도 있으면 집필에 쓰지 않는다."""
    errs: List[str] = []
    warns: List[str] = []

    for k in ("id", "label", "round", "subjects", "choices"):
        if not d.get(k):
            errs.append(f"필수 항목이 없습니다: {k}")
    if errs:
        return errs, warns

    rd = d.get("round") or {}
    size = int(rd.get("size") or 0)
    part = int(rd.get("part_size") or 0)
    subs = d.get("subjects") or []

    if size <= 0:
        errs.append("round.size 가 0 입니다.")
    if part <= 0:
        errs.append("round.part_size 가 0 입니다.")
    # ★ `part_size` 는 **나눗수가 아니라 한 호출의 상한**이다(2026-08-19).
    #   전에는 `size % part == 0` 을 오류로 막았는데, 그것은 파트를 회차에서 균등
    #   분할하던 때의 제약이다. 지금은 과목마다 그 과목 안에서 고르게 쪼개므로
    #   나머지가 남지 않는다 — SQLD 40문항을 상한 25로 주면 20+20 이 된다.

    # ★ 이 검산이 이 파일의 존재 이유다. 합이 틀리면 과목 비율이 조용히 어긋난다.
    tot = sum(int(s.get("count") or 0) for s in subs)
    if tot != size:
        errs.append(f"과목 문항수 합({tot}) 이 round.size({size}) 와 다릅니다 — "
                    f"{' + '.join(str(s.get('count')) for s in subs)}")

    nos = [int(s.get("no") or 0) for s in subs]
    if nos != list(range(1, len(subs) + 1)):
        errs.append(f"과목 번호가 1부터 연속이 아닙니다: {nos}")
    for s in subs:
        if not str(s.get("name") or "").strip():
            errs.append(f"{s.get('no')}과목 이름이 비었습니다 — 요약노트 "
                        f"<h1>N과목 · 이름</h1> 과 일치해야 성적표 링크가 붙습니다.")

    if int(d.get("choices") or 0) < 2:
        errs.append("choices 가 2 미만입니다.")

    ln = d.get("length") or {}
    for k in ("explanation", "explanation_speech"):
        b = ln.get(k) or {}
        t = b.get("target") or []
        if len(t) != 2 or not (b.get("min") and b.get("max")):
            warns.append(f"length.{k} 가 불완전합니다 — 분량을 강제할 수 없습니다.")
        elif not (b["min"] <= t[0] < t[1] <= b["max"]):
            errs.append(f"length.{k} 의 min/target/max 순서가 어긋납니다: "
                        f"{b['min']} ≤ {t[0]} < {t[1]} ≤ {b['max']}")

    # ★ 파트가 과목 경계를 넘는가. 동작은 하지만 처음 있는 일이므로 알려 준다.
    if part and subs:
        edges, acc = [], 0
        for s in subs:
            acc += int(s.get("count") or 0)
            edges.append(acc)
        # ★ 「파트가 과목 경계를 넘습니다」 경고를 없앴다(2026-08-19).
        #   `parts.parts_of()` 가 파트를 **과목에서** 만들도록 바뀌어, 한 파트가 두
        #   과목을 걸치는 일이 구조적으로 생기지 않는다. 남겨 두면 사람이 고칠 수 없는
        #   경고가 된다 — SQLD 에서 실제로 「part_size 를 몇으로 해야 하나」 를
        #   사람이 떠안았고, 그것은 과목 구성을 보면 코드가 아는 값이었다.
        del edges

    rev = d.get("revision") or {}

    # ★ 시험정보에는 **끝나는 날이 있다** (2026-09-07).
    #
    #   전에는 `checked_at`(언제 확인했나) 만 있었다. 그런데 이 파일이 담는 것은
    #   과목 구성뿐 아니라 **그 해의 출제경향**이고, 경향은 시험이 개편되면 통째로
    #   갈아엎힌다. 끝나는 날이 안 적혀 있으면 개편 뒤에도 낡은 기준이 그대로
    #   통과한다 — 아무도 안 틀렸는데 결과가 틀린다.
    #
    #   손해가 회차 수만큼 곱해지는 게 이 값의 무게다. 한 번 정한 시험정보로
    #   10~20회를 집필하기 때문이다(실제 계획: 5회 판독 → 15회 집필).
    #
    #   막지 않고 알린다 — 날짜 하나로 집필을 세우면, 개편 직후 급히 고쳐야 할 때
    #   고칠 길이 막힌다.
    until = str(rev.get("effective_until") or "").strip()
    if not until:
        warns.append("revision.effective_until 이 비었습니다 — 이 값이 언제까지 "
                     "유효한지 알 수 없습니다. 개편이 예상되는 회차의 직전 날짜를 "
                     "넣으십시오(YYYY-MM-DD).")
    else:
        try:
            if date.fromisoformat(until) < date.today():
                warns.append(f"유효 기간이 지났습니다 — 이 시험정보는 {until} 까지였습니다. "
                             "공고와 최근 출제경향을 다시 확인하고 갱신하십시오.")
        except ValueError:
            warns.append(f"revision.effective_until 이 날짜가 아닙니다: {until!r} "
                         "(YYYY-MM-DD 로 적으십시오)")

    if not rev.get("confirmed"):
        warns.append("revision.confirmed 가 false 입니다 — 시행처 공고로 확인되지 "
                     "않은 값입니다. 집필 전에 확인하십시오.")
    if not rev.get("checked_at"):
        warns.append("revision.checked_at 이 비었습니다 — 언제 확인한 값인지 알 수 없습니다.")
    return errs, warns


def listing() -> List[Dict[str, Any]]:
    """관리 화면과 집필 화면 콤보가 읽는 목록."""
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(EXAMS_DIR):
        return out
    for p in sorted(os.listdir(EXAMS_DIR)):
        if not p.endswith(".json"):
            continue
        eid = p[:-5]
        row: Dict[str, Any] = {"id": eid, "path": os.path.join(EXAMS_DIR, p)}
        try:
            d = load(eid)
        except (OSError, ValueError) as e:
            out.append({**row, "ok": False, "errors": [f"읽을 수 없습니다 — {e}"],
                        "label": eid})
            continue
        errs, warns = validate(d)
        rev = d.get("revision") or {}
        subs = d.get("subjects") or []
        out.append({
            **row,
            "ok": not errs,
            "errors": errs, "warnings": warns,
            "label": d.get("label") or eid,
            "label_short": d.get("label_short") or "",
            "pd_id": d.get("pd_id") or "",
            "round_size": (d.get("round") or {}).get("size"),
            "part_size": (d.get("round") or {}).get("part_size"),
            "subjects": [{"no": s.get("no"), "name": s.get("name"),
                          "count": s.get("count")} for s in subs],
            "confirmed": bool(rev.get("confirmed")),
            "checked_at": rev.get("checked_at") or "",
            "effective_from": rev.get("effective_from") or "",
            # 화면이 「언제까지 유효한가」 를 배지로 보여 준다 — 지났으면 붉게.
            "effective_until": rev.get("effective_until") or "",
            "spec_version": rev.get("spec_version"),
        })
    return out


def save(exam_id: str, doc: Dict[str, Any], *, allow_new: bool = True) -> Dict[str, Any]:
    """가져오기(붙여넣기·업로드)가 부르는 곳. **검증을 통과하지 않으면 쓰지 않는다.**"""
    p = path_of(exam_id)
    if not allow_new and not os.path.isfile(p):
        raise FileNotFoundError(f"없는 시험정보입니다: {exam_id}")
    if not isinstance(doc, dict):
        raise ValueError("JSON 최상위가 객체가 아닙니다.")
    if (doc.get("id") or exam_id) != exam_id:
        raise ValueError(f"파일 id({exam_id}) 와 JSON 의 id({doc.get('id')}) 가 다릅니다.")
    doc.setdefault("id", exam_id)

    errs, warns = validate(doc)
    if errs:
        # ★ 통과시키지 않는다. 틀린 값으로 집필이 수 시간 돌고 나서야 알게 된다.
        raise ValueError("시험정보가 검증을 통과하지 못했습니다:\n  - "
                         + "\n  - ".join(errs))
    os.makedirs(EXAMS_DIR, exist_ok=True)
    backup_sibling(p)
    atomic_write_json(p, doc, indent=2, trailing_newline=True)
    return {"ok": True, "id": exam_id, "path": p, "warnings": warns}
