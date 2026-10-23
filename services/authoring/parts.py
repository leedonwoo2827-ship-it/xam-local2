"""파트 나누기 — **과목이 단위**다. 큰 과목만 쪼갠다.

★ 왜 이 파일이 생겼는가 (2026-08-19)

  `draft.py` 에 `PART_SIZE = 20` · `ROUND_SIZE = 80` 이 상수로 박혀 있었다. 빅분기는
  80문항 4과목 × 20 이라 우연히 딱 맞았다 — 파트 하나가 과목 하나였고, 화면 제목도
  「과목 하나가 한 번의 호출입니다」였다.

  SQLD 는 50문항 · 1과목 10 · 2과목 40 이다. 그런데 집필 경로는 시험정보를 읽지 않고
  저 상수를 그대로 썼다. 실측하면 이렇게 된다:

      파트 1 → 문항  1 ~ 20        파트 3 → 문항 41 ~ 60   ← 51~60 은 없다
      파트 2 → 문항 21 ~ 40        파트 4 → 문항 61 ~ 80   ← 통째로 없다

  없는 문항번호로 집필을 부르는 것이다. 시험정보의 `part_size` 는 **집필 화면의 산술에만**
  닿고 있었고(예상 비용·파트 수 표시), 실제 호출에는 닿지 않았다.

★ 사람이 정할 값을 없앤다

  전에는 `round.part_size` 를 사람이 골라야 했다. 25 로 두면 「파트가 과목 경계를
  넘습니다」 경고가 뜨고, 10 으로 두면 사라지는데 — 왜 10 인지는 과목 구성을 보고
  나눗셈을 해 봐야 안다. 정할 이유가 사람에게 있지 않다.

  과목 구성(`subjects`)이 이미 답을 갖고 있다. 그래서 파트를 **과목에서 만든다**:

      과목마다 그 과목의 문항을 파트로 만들고, 한 파트가 `part_size` 를 넘으면 쪼갠다.
      파트가 과목 경계를 넘는 일은 **구조적으로 생기지 않는다.**

  이제 `part_size` 는 나눗수가 아니라 **한 호출의 상한**이다. 그 뜻이면 사람이 고를
  값이 맞다 — 「한 번에 몇 문항까지 쓰게 할까」 는 응답 길이와 잘림의 문제다.

  결과:
      빅분기 80(20·20·20·20) · 상한 20 → 4파트. **지금과 똑같다.**
      SQLD   50(10·40)       · 상한 20 → 3파트: 1과목 10 / 2과목 20 / 2과목 20
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

DEFAULT_PART_SIZE = 20
DEFAULT_ROUND_SIZE = 80


def _subjects(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for s in spec.get("subjects") or []:
        try:
            n = int(s.get("count") or 0)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            out.append({"no": int(s.get("no") or len(out) + 1),
                        "name": str(s.get("name") or ""), "count": n})
    return out


def round_size(spec: Optional[Dict[str, Any]]) -> int:
    """회차 문항수. 과목 합이 있으면 **그것이 정답**이다 — 검증이 둘의 일치를 이미 요구한다."""
    if not spec:
        return DEFAULT_ROUND_SIZE
    subs = _subjects(spec)
    if subs:
        return sum(s["count"] for s in subs)
    try:
        return int((spec.get("round") or {}).get("size") or DEFAULT_ROUND_SIZE)
    except (TypeError, ValueError):
        return DEFAULT_ROUND_SIZE


def part_size(spec: Optional[Dict[str, Any]]) -> int:
    """한 호출의 **상한**. 나눗수가 아니다."""
    try:
        n = int(((spec or {}).get("round") or {}).get("part_size") or 0)
    except (TypeError, ValueError):
        n = 0
    return n if n > 0 else DEFAULT_PART_SIZE


def parts_of(spec: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """파트 목록. 각 항목은 `{index, subject_no, subject_name, numbers, of_subject}`.

    ★ 과목 안에서만 쪼갠다. 한 파트의 `subject_no` 는 늘 하나다 — 과목별 출제 지침과
      난이도 배분이 파트 단위로 들어가기 때문이다(두 과목이 섞이면 어느 지침을
      받아야 할지가 없다).

    ★ 쪼갤 때는 **고르게** 나눈다. 40문항을 상한 20으로 쪼개면 20+20 이고, 30문항이면
      15+15 다(20+10 이 아니다). 한 파트만 얄팍하면 그 파트의 난이도 배분이 흔들린다.
    """
    subs = _subjects(spec or {})
    cap = part_size(spec)
    if not subs:
        # 과목 정보가 없으면 회차를 상한으로 균등 분할한다(옛 동작과 같다).
        total = round_size(spec)
        n = max(1, -(-total // cap))
        out = []
        lo = 1
        for i in range(n):
            hi = min(total, lo + cap - 1)
            out.append({"index": i + 1, "subject_no": 0, "subject_name": "",
                        "numbers": list(range(lo, hi + 1)), "of_subject": (i + 1, n)})
            lo = hi + 1
        return out

    out: List[Dict[str, Any]] = []
    start = 1
    for s in subs:
        n_here = max(1, -(-s["count"] // cap))          # 이 과목을 몇 조각으로
        base, rest = divmod(s["count"], n_here)          # 고르게
        lo = start
        for k in range(n_here):
            size = base + (1 if k < rest else 0)
            hi = lo + size - 1
            out.append({
                "index": len(out) + 1,
                "subject_no": s["no"], "subject_name": s["name"],
                "numbers": list(range(lo, hi + 1)),
                "of_subject": (k + 1, n_here),
            })
            lo = hi + 1
        start += s["count"]
    return out


def n_parts(spec: Optional[Dict[str, Any]]) -> int:
    return len(parts_of(spec))


def part_numbers(spec: Optional[Dict[str, Any]], part_index: int) -> List[int]:
    ps = parts_of(spec)
    if not 1 <= int(part_index) <= len(ps):
        raise ValueError(f"파트 번호는 1~{len(ps)} 입니다: {part_index}")
    return list(ps[int(part_index) - 1]["numbers"])


def subject_no_for(spec: Optional[Dict[str, Any]], number: int) -> int:
    """문항번호 → 과목 번호. 경계는 과목 문항수의 누적이다."""
    acc = 0
    for s in _subjects(spec or {}):
        acc += s["count"]
        if int(number) <= acc:
            return s["no"]
    return 0


def label(spec: Optional[Dict[str, Any]], part_index: int) -> str:
    """사람이 읽는 파트 이름 — 「2과목 (1/2) · 11~30번」."""
    ps = parts_of(spec)
    if not 1 <= int(part_index) <= len(ps):
        return f"파트 {part_index}"
    p = ps[int(part_index) - 1]
    ns = p["numbers"]
    k, tot = p["of_subject"]
    head = (f"{p['subject_no']}과목" if p["subject_no"] else f"파트 {p['index']}")
    if tot > 1:
        head += f" ({k}/{tot})"
    return f"{head} · {ns[0]}~{ns[-1]}번"


# ── 활성책 → 시험정보 ───────────────────────────────────────────────────────
def spec_for_book(book_dir: str) -> Optional[Dict[str, Any]]:
    """책 폴더의 `_book.json` 의 `pd` 로 `exams/*.json` 을 찾는다.

    ★ 폴더가 진실이다. 화면에서 고른 시험정보가 아니라 **이 회차를 담은 폴더**의
      품목으로 정해야 한다 — 화면은 SQLD 인데 작업 폴더가 빅분기인 상태가 실제로
      있었다(2026-08-19). 그때 폴더 기준이면 빅분기 규격으로 돌아 사람이 알아챈다.
    """
    import json

    from services.authoring import examspec

    pd = ""
    try:
        with open(os.path.join(book_dir, "_book.json"), encoding="utf-8") as f:
            pd = str((json.load(f) or {}).get("pd") or "").strip()
    except (OSError, ValueError):
        pd = ""
    if not pd:
        return None
    for e in examspec.listing():
        if not e.get("ok"):
            continue
        try:
            d = examspec.load(e["id"])
        except (OSError, ValueError):
            continue
        if str(d.get("pd_id") or "").strip() == pd:
            return d
    return None

# ── 활성 시험정보 (캐시) ────────────────────────────────────────────────────
_CACHE: Dict[str, Any] = {"key": None, "spec": None}


def active() -> Optional[Dict[str, Any]]:
    """지금 작업 폴더의 시험정보. 폴더가 바뀌면 다시 읽는다.

    ★ 상수를 쓰던 자리를 이 함수로 바꿨다. 캐시 키에 `_book.json` 의 mtime 을
      넣는다 — 품목을 바꿔 저장했는데 앱이 옛 규격으로 계속 도는 것이 가장 나쁘다.
    """
    from services.book import paths

    bd = paths.book_dir()
    try:
        mt = os.path.getmtime(os.path.join(bd, "_book.json"))
    except OSError:
        mt = 0
    key = f"{bd}|{mt}"
    if _CACHE["key"] != key:
        _CACHE["key"] = key
        _CACHE["spec"] = spec_for_book(bd)
    return _CACHE["spec"]


def invalidate() -> None:
    """시험정보 캐시를 버린다. **`exams/<pd>.json` 을 고친 쪽이 부른다.**

    ★ 캐시 키가 `_book.json` 의 mtime 이라, 시험정보 파일만 고치면 키가 그대로다 —
      앱이 옛 규격으로 계속 돈다. 발음 사전을 화면에서 고쳤는데 대본이 안 바뀌는
      일이 실제로 있었다(2026-08-26).
    """
    _CACHE["key"] = None
    _CACHE["spec"] = None


def subjects_map() -> Dict[int, str]:
    """과목번호 → 과목명. 옛 `schema.SUBJECTS` 를 대신한다."""
    return {s["no"]: s["name"] for s in _subjects(active() or {})}


def theory_units() -> tuple:
    """요약노트 단위 — `(키, 과목번호, (1, 1), 문항범위)`. **과목당 하나.**

    ★ 편 나누기를 걷어냈다(2026-08-20). 슬라이드 원고를 만드는 일은
      `summaryhtml2videoscripthtml` 이 맡고, 그 앱은 **해설요약 HTML 한 개**를
      받아 원문의 `h2`/`h3` 를 목차로 쓴다. 우리가 판을 세거나 분량을 맞출 이유가
      없어졌다 — 그 앱의 말대로 「목표가 짧으면 개념을 버리고, 길면 물을 붓는다」.

    ★ 짝의 모양(`(1, 1)`·범위)은 남긴다. 부르는 자리가 그 모양을 이미 쓴다.
    """
    out = []
    acc = 0
    for s_ in ((active() or {}).get("subjects") or []):
        cnt = int(s_.get("count") or 0)
        if cnt <= 0:
            continue
        lo, hi = acc + 1, acc + cnt
        acc += cnt
        key = str(s_.get("key") or "").strip()
        if key:
            out.append((key, int(s_.get("no") or 0), (1, 1), (lo, hi)))
    return tuple(out)
def subject_keys() -> tuple:
    """(요약노트 키, 과목번호) 짝 — 시험정보의 `subjects[].key` 에서.

    ★ 전에는 `theory.KEYS` 에 빅분기 4개가 박혀 있었다
      (`planning`·`explore`·`modeling`·`interpret`). SQLD 는 2과목이고 이름이 달라서,
      그대로 두면 요약노트 화면이 없는 과목 넷을 내놓고 파일 이름도 빅분기 것이 된다.

    ★ 키는 **아스키**여야 한다. `03/summary_<key>.html` 이 발행 파일명이고,
      한글이면 발행 빌더가 `summary_koN.html` 로 치환해 버린다.
      키가 없는 과목은 건너뛴다 — 이름을 지어내면 발행본과 어긋난다.
    """
    out = []
    for s_ in _subjects(active() or {}):
        # `_subjects` 는 no·name·count 만 남기므로 원본에서 key 를 다시 읽는다
        pass
    for s_ in ((active() or {}).get("subjects") or []):
        k = str(s_.get("key") or "").strip()
        if k and int(s_.get("count") or 0) > 0:
            out.append((k, int(s_.get("no") or 0)))
    return tuple(out)


class NoExamSpec(Exception):
    """작업 폴더의 품목에 맞는 시험정보가 없다 — **돈 쓰는 일을 시작하기 전에** 멈춘다."""


def require() -> Dict[str, Any]:
    """시험정보를 **반드시** 얻는다. 없으면 멈춘다.

    ★ 왜 조용한 되돌림값을 쓰지 않는가.

      못 찾으면 `round_size()` 가 80, `n_parts()` 가 4를 낸다 — 빅분기 규격이다.
      SQLD 폴더의 `_book.json` 이 어긋나 있으면 그 상태로 20회차가 돌고,
      1,000문항이 「50문항 시험을 80문항 규격으로」 만들어진 뒤에 알게 된다.
      되돌리는 값이 하필 **그럴듯한 값**이라 아무 신호도 나지 않는다.

      그래서 **읽기 화면은 되돌림값으로 견디고, 집필·굽기는 여기서 멈춘다.**
    """
    d = active()
    if d:
        return d
    from services.book import paths

    bd = paths.book_dir()
    pd = ""
    try:
        import json

        with open(os.path.join(bd, "_book.json"), encoding="utf-8") as f:
            pd = str((json.load(f) or {}).get("pd") or "").strip()
    except (OSError, ValueError):
        pd = ""
    raise NoExamSpec(
        f"작업 폴더의 시험정보를 찾지 못했습니다 — 폴더 {bd} · 품목 "
        f"{pd or '(없음)'}. `exams/*.json` 중 `pd_id` 가 이 품목인 것이 있어야 "
        "합니다(문항 집필 화면 하단 「시험정보 관리」). 지금 진행하면 회차·과목 "
        "구성이 다른 품목의 값으로 잡힙니다.")
