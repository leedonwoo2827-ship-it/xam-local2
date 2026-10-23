# -*- coding: utf-8 -*-
"""기출 풀(`01/`) 훑기 — **화면에 "OCR 검수 회차" 로 나오는 값.**

집필할 회차 수를 사람이 맨손으로 정하면 안 된다. 기준이 기출 회차 수다 —
원 집필 프롬프트가 그렇게 잡아 뒀다:

    `01/` 에 01-* · 02-* · 03-* **240문항**이 있다.
    720문항이므로 **한 기출당 3회 파생**이 되지만, 같은 기출에서 파생한 3문항은
    서로 다른 회차 · 다른 하위개념 · 다른 난이도로 갈라 놓을 것.

즉 자사 회차 수 = 기출 회차 수 × 배수. 실제 구성이 3회차 × 3 = 9회차였다.
화면은 그 배수만 고르게 한다(2026-08-10 요청).

★ **과목별 문항수도 센다.** 이것이 배수의 실제 이유다(2026-08-10) —
  *"과목별 문항수를 유지해야 해서 그렇습니다. 증폭하다보면 과목이 섞이거나 과목내
  나와야 하는 정도가 꼬일수도 있어서요."*

  실측: 기출 3회차가 **모두 과목당 20문항 × 4과목 = 80문항** 이고, 우리 회차 구성과
  같은 모양이다. 그래서 배수 증폭이 과목별 문항수를 그대로 보존한다.

  ★ 과목이 섞이는 것은 **구조적으로 불가능**하다 — 집필 단위가 과목 1개(20문항)이고,
    `schema.part_schema()` 가 그 과목의 `question_no`·`subject_no` 만 enum 으로 허용하며,
    `draft._validate()` 가 `subject_no_for(question_no)` 로 교차 확인한다. 세 겹이다.

★ 회차는 파일 이름(`NN-MM.md`)에서, 과목은 프론트매터 `subject_no` 에서 뽑는다.
  242개 머리 14줄을 읽는 데 **0.04초**다(실측) — 화면을 느리게 하지 않는다.
"""
from __future__ import annotations

import glob
import os
import re
from typing import Any, Dict, List

from . import cost

# `01-01.md` · `03-80.md` — 앞이 회차, 뒤가 문항. `_index.json` 같은 것은 제외한다.
_NAME = re.compile(r"^(\d{1,2})-(\d{1,3})$")


_SUBJ_NO = re.compile(r"^subject_no:\s*(\d+)\s*$", re.M)


def survey(book_dir: str) -> Dict[str, Any]:
    """기출 회차 목록 · 문항 수 · **과목별 문항수.**"""
    d = os.path.join(book_dir, "01")
    per: Dict[str, int] = {}
    by_subject: Dict[str, int] = {}
    per_round_subject: Dict[str, Dict[str, int]] = {}

    for p in sorted(glob.glob(os.path.join(d, "*.md"))):
        m = _NAME.match(os.path.basename(p)[:-3])
        if not m:
            continue
        rd = m.group(1)
        per[rd] = per.get(rd, 0) + 1
        # 프론트매터 머리만 읽는다 — 본문까지 읽을 이유가 없다.
        try:
            with open(p, encoding="utf-8") as f:
                head = "".join(next(f, "") for _ in range(16))
        except OSError:
            continue
        if sm := _SUBJ_NO.search(head):
            s = sm.group(1)
            by_subject[s] = by_subject.get(s, 0) + 1
            per_round_subject.setdefault(rd, {})
            per_round_subject[rd][s] = per_round_subject[rd].get(s, 0) + 1

    rounds = sorted(per)
    subs = sorted(by_subject)
    # ★ 과목별 문항수가 회차마다 같은가. 다르면 증폭 시 과목 비율이 흔들린다 —
    #   화면이 그것을 말해야 사람이 결정할 수 있다.
    shapes = {tuple(sorted(per_round_subject.get(r, {}).items())) for r in rounds}
    return {
        "dir": d,
        "exists": os.path.isdir(d),
        "rounds": rounds,                          # 예: ["01","02","03"]
        "per_round": {k: per[k] for k in rounds},
        "n_rounds": len(rounds),
        "n_items": sum(per.values()),
        "subjects": subs,                          # 예: ["1","2","3","4"]
        "by_subject": {k: by_subject[k] for k in subs},
        "per_round_subject": per_round_subject,
        # 회차마다 과목 구성이 같으면 True — 증폭이 비율을 보존한다
        "uniform": len(shapes) <= 1 and bool(rounds),
        "per_subject_each": (sorted(per_round_subject.get(rounds[0], {}).items())
                             if rounds else []),
    }


def existing_mock_rounds(book_dir: str) -> List[str]:
    """이미 만들어진 자사 회차(`_rounds/mNN.json`). 다음 코드를 정하는 근거다."""
    d = os.path.join(book_dir, "_rounds")
    if not os.path.isdir(d):
        return []
    out = []
    for p in glob.glob(os.path.join(d, "m*.json")):
        b = os.path.basename(p)[:-5]
        if re.fullmatch(r"m\d{2}", b):
            out.append(b)
    return sorted(out)


def _round_size() -> int:
    """회차당 문항수 — 시험정보에서. 못 찾으면 되돌림값(읽기용)이다."""
    from services.authoring import draft

    try:
        return int(draft.round_size()) or 0
    except Exception:                                        # noqa: BLE001
        return 0


def plan_rounds(book_dir: str, multiple: int, start: str = "",
                per_round: Dict[str, int] | None = None) -> Dict[str, Any]:
    """배수 → 만들 회차 코드 목록.

    ★ 시작 코드를 비워 두면 **이미 있는 회차 다음**부터 잡는다. 기존 회차를 덮는
      사고를 기본값에서 막는다(m01~m09 가 있으면 m10 부터).
    """
    survey_ = survey(book_dir)
    have = existing_mock_rounds(book_dir)
    # ★ 배수는 **행별**이다. `per_round={"01":3,"07":2}` 로 받는다 — SQLD 는 마지막
    #   기출 회차만 ×2 로 해서 1,000제를 맞춘다. 없으면 전역 배수를 모든 행에 쓴다.
    per = dict(per_round or {})
    mult_of = lambda r: int(per.get(r, max(1, int(multiple))))  # noqa: E731
    n = sum(mult_of(r) for r in (survey_["rounds"] or [""]))

    if start:
        if not re.fullmatch(r"m\d{2}", start):
            raise ValueError(f"시작 회차 코드가 올바르지 않습니다: {start} (m01 형태)")
        first = int(start[1:])
    else:
        # ★ 배수는 **총량**이다. 「이미 있는 회차 다음부터」 로 잡으면 안 된다.
        #
        #   실측(2026-08-20): m01~m10 을 만든 뒤 같은 화면에서 [실행] 하니 계획이
        #   `m11~m30` 으로 잡혔다. 6×3 + 1×2 = 20 은 **총 20회차**라는 뜻인데,
        #   20개를 *더* 만들어 30회차 1,500문항이 되는 계획이었다. 사람은 화면의
        #   「총 20회차 · 1,000문항」 을 보고 [확인] 을 눌렀다.
        #
        #   그래서 **늘 m01 부터** 잡는다. 이미 끝난 파트는 `draft.is_done` 이
        #   건너뛰므로 다시 만들지 않고, 덮을 것이 있으면 `overwrites` 로 화면이
        #   경고한다. 회차를 **더** 얹고 싶을 때만 `start` 를 준다.
        first = 1

    codes = [f"m{first + i:02d}" for i in range(n)]
    # ★ 「덮습니다」 는 **실제로 다시 만들 회차**만 센다. 계획이 늘 m01 부터
    #   잡으므로, 이미 다 끝난 회차까지 세면 화면이 빨간 경고를 늘 달고 있게 된다 —
    #   경고가 늘 켜져 있으면 아무 신호도 아니게 된다.
    from services.authoring import draft as _D

    def _will_redo(c: str) -> bool:
        try:
            return any(not _D.is_done(c, i) for i in range(1, _D.n_parts() + 1))
        except Exception:                                    # noqa: BLE001
            return True

    over = [c for c in codes if c in have and _will_redo(c)]
    # 실제로 돌 파트 수 — 화면의 확인창이 이 값을 쓴다(60회라고 묻고 29번 도는 일을 막는다).
    try:
        remaining = [f"{c}-p{i}" for c in codes
                     for i in range(1, _D.n_parts() + 1) if not _D.is_done(c, i)]
    except Exception:                                        # noqa: BLE001
        remaining = []

    # ── 기출 ↔ 자사 대응 ────────────────────────────────────────────────────
    # ★ 화면의 **행이 기출 회차**다(2026-08-10: *"ocr을 3회 했으니 행은 3개가 나옵니다"*).
    #   기출 회차 하나가 자사 회차 몇 개의 원천인지가 표로 보여야 한다.
    #
    # ★ 배분은 **블록**이다(2026-08-10 지시한 레이아웃 그대로):
    #     기출 1회 × 3 → m01, m02, m03
    #     기출 2회 × 3 → m04, m05, m06
    #     기출 3회 × 3 → m07, m08, m09
    #   처음 stride(기출1 → m01,m04,m07)로 만들었다가 고쳤다. 블록이 화면과 맞고,
    #   사람이 "이 줄을 돌리면 이 회차들이 나온다" 를 한눈에 읽는다.
    pool_rounds = survey_["rounds"] or [""]
    mapping: Dict[str, List[str]] = {}
    src_of: Dict[str, str] = {}
    cur = 0
    for r in pool_rounds:
        k = mult_of(r)
        blk = codes[cur:cur + k]
        cur += k
        mapping[r] = blk
        for c in blk:
            src_of[c] = r
    rows = [{
        "pool_round": r,
        "pool_items": survey_["per_round"].get(r, 0),
        "per_subject": sorted(survey_["per_round_subject"].get(r, {}).items()),
        "targets": mapping[r],
        "multiple": mult_of(r),
    } for r in pool_rounds]

    # ── 예상 소모량 ─────────────────────────────────────────────────────────
    # ★ 화면에 나와야 한다. 사용자가 그 이유를 말했다(2026-08-10): *"제 생각에는
    #   여기서 거의 토큰을 다 소모할겁니다."* 구독이라 청구는 없지만 **한도**가 있고,
    #   회차 9개를 무심코 누르면 하루치를 태울 수 있다.
    #
    # ★ 상수를 여기서 곱하지 않는다. `cost.estimate` 가 **스테이징의 실측**에서
    #   과목당 값을 뽑는다 — 예전엔 이 자리의 상수와 화면의 상수가 서로 달랐고,
    #   첫 실측($1.749·12분)이 나오자 셋 다 두 배쯤 틀린 것으로 드러났다.
    est = cost.estimate(len(codes))
    rows_mult = {r: mult_of(r) for r in pool_rounds}

    return {
        "pool": survey_,
        "existing": have,
        "multiple": max(1, int(multiple)),
        "codes": codes,
        "n_rounds": len(codes),
        # ★ 회차당 문항수는 **시험정보에서** 온다. 여기 80 이 박혀 있었다 —
        #   빅분기 규격이라 ADsP(50) · SQLD(50) 에서 총 문항수가 틀리게 나왔다.
        "n_items": len(codes) * _round_size(),
        # ★ 겹치면 조용히 덮지 않는다. 화면이 경고하고 사람이 결정한다.
        "overwrites": over,
        "remaining_parts": remaining,
        "remaining_count": len(remaining),
        # 예상 소모 — 구독 한도의 대리 지표. 정가 환산이고 청구가 아니다.
        # ★ `est` 를 통째로 넘긴다. 화면이 문항당 단가·표본 수까지 그대로 쓴다.
        "est": est,
        # 옛 키 — 화면이 아직 읽을 수 있으니 남긴다.
        "est_cost_usd": est["usd"],
        "est_minutes": est["minutes"],
        "est_note": est["note"],
        # 화면의 행 — 기출 회차 하나가 한 행이다
        "rows": rows,
        "source_of": src_of,
    }
