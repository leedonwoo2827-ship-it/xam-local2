# -*- coding: utf-8 -*-
"""집필 소모량 추정 — **상수가 아니라 실측에서 읽는다.**

★ 왜 만들었나. 같은 추정치가 세 군데에 서로 다른 상수로 박혀 있었다(2026-08-10):

      pool.py        회차당 3.60 + 1.44×3 = $7.92 · 44분
      authoring.js   회차당 6.9  (총계 줄)
      authoring.js   회차당 6.9  (실행 확인창)

  세 값이 서로 안 맞는 것도 문제지만, 진짜 문제는 **셋 다 틀렸다**는 것이다.
  첫 실측이 과목당 $1.749 · 12분 08초 · 2턴 으로 나왔다 — 상수의 절반이다.
  시험기준(`exam`)은 기출을 안 읽어 2턴에 끝나는데, 상수는 기출을 읽는
  연습문제화(`derive`) 기준으로 잡혀 있었다.

★ 그래서 상수를 고치지 않는다. 고쳐도 다음 실측에서 또 틀린다. 스테이징에 이미
  파트마다 `cost_usd`·`seconds`·`mode` 가 남으므로, **그것을 평균 낸다.**

★ 냉시동과 캐시를 나누지 않는다. 회차 하나가 1냉시동 + 3캐시로 굴러가므로,
  완주한 과목들을 그냥 평균 내면 그 비율이 저절로 반영된다. 나누면 "이 과목이
  냉시동이었나" 를 사후에 맞혀야 하는데, 스테이징 기록만으로는 알 수 없다
  (1시간 캐시라 회차 사이 간격에 달렸다).

★ 표본이 적을 때를 화면이 알아야 한다. `samples` 를 같이 돌려주고, 화면이
  "실측 1과목 기준" 이라고 밝힌다 — 첫 과목만 있으면 그건 냉시동 하나뿐이라
  실제보다 비싸게 잡힌다.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List

from core.constants import DATA_DIR

from .draft import PART_SIZE, n_parts, round_size

# ── 폴백 상수 ───────────────────────────────────────────────────────────────
# 실측이 하나도 없을 때만 쓴다(새 PC·새 품목). 기출을 읽는 연습문제화 기준의
# 보수적인 값이다 — 빗나가면 실제가 더 싸다. 시험기준은 이보다 훨씬 싸게 끝난다.
FALLBACK_USD = 1.98         # 과목(20문항)당
FALLBACK_SEC = 11 * 60      # 과목당 11분

_MIN_USD = 0.01             # 이보다 싼 기록은 실패·중단으로 보고 표본에서 뺀다


def _samples(mode: str = "") -> List[Dict[str, Any]]:
    """스테이징에 쌓인 파트 기록. `mode` 를 주면 그 기준만 센다.

    ★ 실패한 파트도 센다. 실패분에도 요금이 나갔고, 다시 돌리면 또 나간다 —
      추정에서 빼면 실제보다 싸게 잡힌다.
    ★ `seconds`·`mode` 는 2026-08-10 에 추가했다. 그 전 기록에는 없으므로
      비용만 있는 기록도 받아들이고, 시간은 그런 표본을 빼고 평균 낸다.
    """
    out: List[Dict[str, Any]] = []
    # ★ 경로가 한 단계 모자랐다 (2026-09-08 실측).
    #
    #   스테이징은 `data/authoring/<품목>/<회차>/<파트>.json` 다. 그런데 이 패턴은
    #   `authoring/*/*.json` 이라 `authoring/adsp-26/*.json` 을 찾았고, 그 자리엔
    #   회차 폴더만 있어서 **표본이 늘 0** 이었다. 품목별로 가른 2026-08-19 변경
    #   때 함께 못 고친 자리다 — 그 전에는 `authoring/<회차>/<파트>.json` 이라
    #   이 패턴이 맞았다.
    #   결과: SQLD 20회차를 돌린 뒤에도 화면이 「아직 실측이 없어 보수적인
    #   기본값」($0.099/문항)을 계속 말했다. 예상이 실제보다 크게 나온다.
    #
    # ★ **지금 품목만** 센다. 파트 크기가 품목마다 다르다(빅분기 20문항,
    #   ADsP 10·10·15·15) — 섞으면 과목당 평균이 뜻을 잃는다. 새 품목이면
    #   표본이 0 이고, 그때는 폴백 상수를 쓰는 것이 맞다.
    from .draft import _pd

    pat = os.path.join(DATA_DIR, "authoring", _pd(), "*", "*.json")
    for p in glob.glob(pat):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        usd = float(d.get("cost_usd") or 0)
        if usd < _MIN_USD:
            continue
        if mode and (d.get("mode") or "") and d.get("mode") != mode:
            continue
        out.append({"usd": usd,
                    "sec": float(d.get("seconds") or 0),
                    "mode": d.get("mode") or "",
                    "n": len(d.get("items") or [])})
    return out


def per_part(mode: str = "") -> Dict[str, Any]:
    """과목(20문항) 하나의 예상 비용·시간.

    돌려주는 것:
        usd·sec      과목당
        per_item_usd 문항당 — 화면이 물어본 값이다("문제당 평균 고정비")
        samples      평균에 쓴 실측 과목 수 (0 이면 폴백 상수)
        measured     실측인가
    """
    rows = _samples(mode)
    if not rows:
        # ★ 파트당 문항수는 **시험정보에서** 온다. `PART_SIZE`(20)는 빅분기 값이라
        #   ADsP(파트 10·10·15·15 → 평균 12.5)에서는 문항당 단가를 싸게 잡는다.
        try:
            per = round_size() / max(1, n_parts())
        except Exception:                                    # noqa: BLE001
            per = PART_SIZE
        return {"usd": FALLBACK_USD, "sec": FALLBACK_SEC,
                "per_item_usd": FALLBACK_USD / max(1, per),
                "samples": 0, "measured": False, "mode": mode}

    usd = sum(r["usd"] for r in rows) / len(rows)
    timed = [r["sec"] for r in rows if r["sec"] > 0]
    sec = (sum(timed) / len(timed)) if timed else FALLBACK_SEC
    # 문항당은 **실제로 나온 문항 수**로 나눈다. 20문항을 시켰는데 17개만 오면
    # 문항당 단가는 그만큼 비싼 것이 맞다.
    items = sum(r["n"] for r in rows) or (len(rows) * PART_SIZE)
    return {"usd": usd, "sec": sec,
            "per_item_usd": sum(r["usd"] for r in rows) / items,
            "samples": len(rows), "measured": True, "mode": mode}


def estimate(n_rounds: int, mode: str = "", part_count: int = 0) -> Dict[str, Any]:
    """회차 N개의 예상 소모량. `pool.plan_rounds` 와 화면이 같이 쓴다.

    ★ 한 곳에서만 계산한다. 화면이 따로 곱하면 또 갈린다 — 실제로 확인창과
      총계 줄이 서로 다른 값을 내고 있었다.
    """
    parts = part_count or n_parts()
    p = per_part(mode)
    n_calls = max(0, int(n_rounds)) * parts
    return {
        "n_calls": n_calls,
        # ★ 회차 크기는 시험정보에서 — 상수(80)면 SQLD 예상 문항수가 1.6배로 뜬다.
        "n_items": max(0, int(n_rounds)) * round_size(),
        "usd": round(p["usd"] * n_calls, 2),
        "minutes": int(round(p["sec"] * n_calls / 60)),
        "per_part_usd": round(p["usd"], 3),
        "per_part_minutes": round(p["sec"] / 60, 1),
        "per_item_usd": round(p["per_item_usd"], 4),
        "samples": p["samples"],
        "measured": p["measured"],
        "note": (f"실측 {p['samples']}과목 평균입니다 "
                 f"(과목당 ${p['usd']:.2f} · {p['sec'] / 60:.0f}분)."
                 if p["measured"] else
                 "아직 실측이 없어 보수적인 기본값으로 잡았습니다 — "
                 "한 과목만 돌려 보면 실측으로 바뀝니다."),
    }
