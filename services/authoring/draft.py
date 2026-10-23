# -*- coding: utf-8 -*-
"""파트 1개(보통 10문항) 집필 → 검증 → **스테이징에 저장.**

★ 모델 출력이 `_rounds/` 에 직접 닿지 않는다. 여기까지가 스테이징이고, 반입은
  `merge.py` 가 한다. 그래야 검증에 걸린 파트가 이미 검수된 문항을 덮지 못한다.
  (같은 이유로 `provider.py` 는 `Write`/`Edit` 를 금지한다 — 모델에게 파일을 쓸
  통로가 애초에 없다.)

★ 스키마가 못 잡는 것을 여기서 잡는다. `output_format` 은 **모양**만 본다:
    · question_no ↔ subject_no 조합 (스키마는 각각의 enum 만 본다)
    · 번호 중복·누락
    · 낭독에 마크다운 누출
    · 낭독에 `그/느/드/르` 발음체 누출 (자막에 그대로 나가는 사고)
    · 정답 위치 편중
  전부 "통과했는데 나중에 사람이 읽고서야 아는" 종류다.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.atomic_io import atomic_write_json
from core.constants import DATA_DIR

from .errors import ProviderError
from .provider import ClaudeAuthor
from .schema import part_schema, subject_no_for, subjects
from .spec import difficulty_plan, part_prompt, system

# ★ 집필 단위는 **과목(20문항)** 이다. 번들(10문항)이 아니다.
#
#   처음 10 으로 두었다가 고쳤다. 이유가 두 개다:
#   ① 번들과 맞출 필요가 없다 — `build.py` 는 회차를 통째로 만들고, 10문항 번들로
#      쪼개는 것은 그 뒤 단계다. 집필 단위가 번들 경계를 따라야 할 제약이 없다.
#   ② 10 으로 자르면 파트 1(1~10번)과 파트 2(11~20번)가 **둘 다 1과목**인데 서로를
#      못 본다 → 같은 하위개념이 두 번 나온다. 과목 하나를 한 호출에 담으면 모델이
#      그 안에서 난이도·하위주제를 스스로 배분한다.
#
#   분량 상한을 걸었기 때문에 20문항도 한 응답에 들어간다(문항당 약 900자).
#   상한 없이 두면 20 × 2,900자여서 안 됐다 — 그것이 처음 10 을 고른 실제 이유였다.
# ★ 회차·파트 크기는 **시험정보 파일**에서 온다(`services/authoring/parts.py`).
#   아래 둘은 시험정보를 못 읽을 때의 되돌림값이다 — 빅분기 값이라 옛 동작과 같다.
#   전에는 이 둘이 상수였고, SQLD(50문항)에 그대로 쓰여 없는 문항 61~80 을 집필하려
#   했다(2026-08-19 실측). 새 값을 여기 박지 말 것 — 품목마다 다르다.
PART_SIZE = 20          # 되돌림값. 실제 상한은 parts.part_size(spec)
ROUND_SIZE = 80         # 되돌림값. 실제 회차 크기는 parts.round_size(spec)

# ── 분량 기준 ───────────────────────────────────────────────────────────────
# ★ 검증된 회차(m01 80문항)의 **실측 중앙값**이다. 프롬프트 문서의 "3~4배" 라는
#   비율 표현이 아니라 이 절대값이 기준이다 — 비율은 화면과 낭독이 같이 부풀면
#   그대로여서 아무것도 막지 못한다(실제로 통과했다).
EX_LO, EX_HI, EX_MAX = 160, 260, 320        # 화면 해설 (m01 중앙값 166자)
SP_LO, SP_HI, SP_MAX = 340, 450, 520        # 낭독     (m01 중앙값 356자)
CHARS_PER_SEC = 5.5                          # 한국어 낭독 환산(speed 1.05 기준)


# ── 스테이징 경로 ───────────────────────────────────────────────────────────
def _pd() -> str:
    """지금 작업 폴더의 품목 코드. 스테이징을 품목별로 가르는 데 쓴다.

    ★ 되돌림값으로 **다른 품목의 이름을 쓰지 않는다** (2026-09-08).

      전에는 시험정보를 못 찾으면 `.env` 의 `PD_CODE` 로 떨어졌다. 그 값은 이 PC 를
      처음 세울 때 적은 품목(여기서는 `bigdata`)이고 **지금 연 폴더와 아무 상관이
      없다.** 실측: ADsP 폴더를 열었는데 시험정보 캐시가 낡아 있어 이 함수가
      `bigdata` 를 냈고, 집필 화면이 `data/authoring/bigdata/` 의 9회차 36파트를
      「이미 합격」으로 세었다. 그 상태로 [실행] 하면 ADsP 집필이 빅분기 스테이징에
      섞이고, 남의 파트를 건너뛴다.

      그래서 순서를 이렇게 둔다:
        1) 시험정보의 `pd_id`      — 정상 경로
        2) 작업 폴더의 `_book.json` 의 `pd` — 시험정보가 아직 없어도 폴더는 안다
        3) `unknown`               — 여기까지 오면 **아무 폴더와도 안 섞인다**

      `.env` 는 더 이상 보지 않는다. 섞이는 것보다 비어 있는 편이 낫다.
    """
    try:
        from services.authoring import parts

        pd = str((parts.active() or {}).get("pd_id") or "").strip()
        if pd:
            return pd
    except Exception:                                        # noqa: BLE001
        pass
    # 시험정보가 아직 없는 새 문제집 — 폴더가 아는 값을 쓴다.
    try:
        import json as _json

        from services.book import paths as _paths

        with open(os.path.join(_paths.book_dir(), "_book.json"),
                  encoding="utf-8") as f:
            pd = str((_json.load(f) or {}).get("pd") or "").strip()
        if pd:
            return pd
    except Exception:                                        # noqa: BLE001
        pass
    return "unknown"


def staging_dir(round_code: str) -> str:
    """`data/authoring/<품목>/<회차>/`. 책 폴더 밖에 둔다 — 검증 전 산출물이 책에
    섞이면 `scan`·`verify` 가 그것을 진짜 문항으로 세기 시작한다.

    ★ **품목별로 가른다.** 전에는 `data/authoring/<회차>/` 였다. 회차 코드가
      `m01`~`m09` 로 품목마다 같아서, 빅분기로 집필해 둔 스테이징이 SQLD 를 열어도
      「1회차 60문항 대기 합격」 으로 보였다(2026-08-19 실측). 그 상태로 [반입] 을
      누르면 **빅분기 문항이 SQLD 회차로 들어간다** — 과목명·문항수가 다르니 뒤
      단계에서 걸리겠지만, 걸리기 전에 `_rounds/` 가 덮인다.
    """
    return os.path.join(DATA_DIR, "authoring", _pd(), round_code)


def staging_path(round_code: str, part_index: int) -> str:
    return os.path.join(staging_dir(round_code), f"{round_code}-p{part_index}.json")


# ── 결과 ────────────────────────────────────────────────────────────────────
@dataclass
class PartResult:
    round_code: str
    part_index: int
    numbers: List[int]
    items: List[Dict[str, Any]] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)   # 반입을 막는 것
    warnings: List[str] = field(default_factory=list)   # 사람이 볼 것
    cost_usd: float = 0.0
    turns: int = 0
    path: str = ""
    # ★ 걸린 시간과 기준을 같이 남긴다. 비용만 남기면 "얼마 드나" 는 답해도
    #   "몇 시간 걸리나" 는 매번 상수로 어림잡게 된다 — 실제로 그 상수가 세 군데에
    #   서로 다른 값으로 박혀 있었다(2026-08-10). 기준(mode)도 같이 남기는 이유:
    #   시험기준은 기출을 안 읽어 2턴에 끝나고, 연습문제화는 읽어서 훨씬 비싸다.
    #   둘을 섞어 평균 내면 어느 쪽에도 안 맞는 값이 나온다.
    seconds: float = 0.0
    mode: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems and len(self.items) == len(self.numbers)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "round": self.round_code, "part": self.part_index,
            "numbers": self.numbers, "n": len(self.items),
            "ok": self.ok, "problems": self.problems, "warnings": self.warnings,
            "cost_usd": round(self.cost_usd, 4), "turns": self.turns,
            "seconds": round(self.seconds, 1), "mode": self.mode,
            "path": self.path,
        }


# ── 파트 범위 ───────────────────────────────────────────────────────────────
def part_numbers(part_index: int, part_size: int = 0) -> List[int]:
    """파트 번호(1-based) → 문항번호 목록.

    ★ 파트는 **과목에서** 만든다 — 한 파트가 두 과목을 걸치지 않는다.
      `parts.parts_of()` 에 그 이유가 적혀 있다. `part_size` 인자는 옛 호출부를
      위해 남겨 두었고, 주면 그 값을 상한으로 본다.
    """
    from services.authoring import parts as _P

    spec = _P.active()
    if part_size:
        spec = dict(spec or {})
        spec["round"] = {**(spec.get("round") or {}), "part_size": int(part_size)}
    return _P.part_numbers(spec, part_index)


def n_parts(part_size: int = 0) -> int:
    from services.authoring import parts as _P

    spec = _P.active()
    if part_size:
        spec = dict(spec or {})
        spec["round"] = {**(spec.get("round") or {}), "part_size": int(part_size)}
    return _P.n_parts(spec)


def round_size() -> int:
    """회차 문항수 — 시험정보에서."""
    from services.authoring import parts as _P

    return _P.round_size(_P.active())


def part_label(part_index: int) -> str:
    """사람이 읽는 파트 이름 — 「2과목 (1/2) · 11~30번」."""
    from services.authoring import parts as _P

    return _P.label(_P.active(), part_index)


# ── 검증 ────────────────────────────────────────────────────────────────────
# 낭독에 있으면 안 되는 것. 마크다운은 TTS 가 그대로 읽는다("별표 별표").
_MD_IN_SPEECH = [("**", "굵게 표시"), ("`", "백틱"), ("![", "그림 링크"),
                 ("](", "링크"), ("- ", "불릿")]

# ★ 발음체 누출. 시험지 표기는 `ㄱㄴㄷㄹ` 이고, 자모 이름 낭독은 렌더 단계의
#   발음사전이 한다. 집필이 `그/드/르` 를 쓰면 **자막에도 그것이 나간다.**
#   기존 9회차에서 실제로 그렇게 됐다(회차당 8~9건).
#   경계를 좁게 잡는다 — "그리고" · "느낌" · "드러난다" 를 잡으면 안 된다.
_SPEECH_JAMO = re.compile(r"(?<![가-힣])(그|느|드|르|므)(?=\s*[,·)]|입니다|이고|와|과)")


def _validate(items: List[Dict[str, Any]], numbers: List[int]) -> tuple[List[str], List[str]]:
    problems: List[str] = []
    warns: List[str] = []

    got = [int(it.get("question_no", 0)) for it in items]
    missing = sorted(set(numbers) - set(got))
    extra = sorted(set(got) - set(numbers))
    dup = sorted({n for n in got if got.count(n) > 1})
    if missing:
        problems.append(f"빠진 문항번호: {missing}")
    if extra:
        problems.append(f"범위 밖 문항번호: {extra} (이 파트는 {numbers[0]}~{numbers[-1]})")
    if dup:
        problems.append(f"중복 문항번호: {dup}")

    for it in items:
        no = it.get("question_no")
        tag = f"{no}번"

        # 과목 — 번호에서 파생되는 값이다. 어긋나면 웹의 과목 필터가 틀린다.
        try:
            want = subject_no_for(int(no))
        except (TypeError, ValueError):
            continue
        if int(it.get("subject_no", 0)) != want:
            problems.append(f"{tag}: subject_no={it.get('subject_no')} "
                            f"인데 번호상 {want} 과목입니다")
        if it.get("subject") != subjects().get(want):
            problems.append(f"{tag}: subject 문자열이 '{subjects().get(want)}' 가 "
                            f"아닙니다 (요약노트 <h1> 과 일치해야 성적표 링크가 붙습니다)")

        # 낭독 — 여기가 자막으로도 나간다
        sp = str(it.get("explanation_speech") or "")
        for mark, ko in _MD_IN_SPEECH:
            if mark in sp:
                problems.append(f"{tag}: 낭독에 {ko}({mark}) 가 있습니다 — "
                                f"TTS 가 그대로 읽습니다")
        if m := _SPEECH_JAMO.search(sp):
            problems.append(f"{tag}: 낭독에 발음체 '{m.group(1)}' 가 있습니다 — "
                            f"`ㄱㄴㄷㄹ` 원문으로 쓰십시오(자막에 그대로 나갑니다)")
        if not sp.startswith("정답은"):
            warns.append(f"{tag}: 낭독이 '정답은 N번입니다.' 로 시작하지 않습니다")

        # ★ 분량 — **절대 길이로 본다. 비율로 보면 안 된다.**
        #   처음엔 "낭독이 화면의 N배" 로 검사했는데 그것이 거꾸로였다: 화면과 낭독이
        #   같이 5배로 부풀면 비율은 그대로여서 통과한다. 실제로 그렇게 통과했고
        #   (화면 919자 · 낭독 1552자, 비율 1.79배) 그건 편당 47분이다.
        #   기준은 검증된 m01 의 실측 중앙값이다 — 화면 166자 · 낭독 356자 → 편 10.8분.
        ex = str(it.get("explanation") or "")
        if len(ex) > EX_MAX:
            warns.append(f"{tag}: 화면 해설 {len(ex)}자 — 목표 {EX_LO}~{EX_HI}자를 "
                         f"넘겼습니다(슬라이드 수가 늘고 편이 길어집니다)")
        elif len(ex) < EX_LO:
            # ★ 이 경고가 스키마의 하한을 대신한다. 하한을 스키마에 두었더니 한 문항의
            #   미달이 20문항 전량 재생성을 불러 무한루프가 됐다(schema.py 머리말).
            #   낭독 쪽에는 아래에 같은 경고가 이미 있었다 — 화면 쪽만 비어 있었다.
            warns.append(f"{tag}: 화면 해설 {len(ex)}자뿐입니다 — 목표 {EX_LO}~{EX_HI}자")
        if len(sp) > SP_MAX:
            warns.append(f"{tag}: 낭독 {len(sp)}자 ≈ {len(sp)/CHARS_PER_SEC:.0f}초 — "
                         f"목표 {SP_LO}~{SP_HI}자(문항당 90초)를 넘겼습니다")
        elif len(sp) < SP_LO:
            warns.append(f"{tag}: 낭독 {len(sp)}자뿐입니다 — 목표 {SP_LO}~{SP_HI}자")

        # 보기가 서로 같으면 정답이 둘이 된다
        ch = [str(c).strip() for c in (it.get("choices") or [])]
        if len(set(ch)) != len(ch):
            problems.append(f"{tag}: 보기 중 같은 것이 있습니다 {ch}")

        # ★ 그림 링크 ↔ `assets` 대응. 스키마는 둘을 **각각만** 본다 — 해설 문자열과
        #   assets 배열이 서로 맞는지는 아무도 안 봤다.
        #
        #   m06 에서 실제로 깨졌다(2026-08-12 확인). 3과목 7문항이 해설에
        #   `![…](assets/m06-43-정보이득.svg)` 를 썼는데 `assets` 배열에 그 SVG 가
        #   없다 → `02/assets/` 에 파일이 안 생기고 **사이트에서 깨진 이미지 7개**가
        #   된다. 발행한 뒤에야 드러나는 종류다.
        #
        #   `schema.py` 가 "그림 0개로 나오는 회귀" 는 못박아 뒀지만 **부분적으로
        #   비는 경우**가 비어 있었다. 0개는 눈에 띄고 7개는 안 띈다.
        names = {str((a or {}).get("name") or "") for a in (it.get("assets") or [])}
        # ★ **지문도 본다.** 조건 그림(ERD·테이블 구조)은 지문에 놓이므로,
        #   해설만 훑으면 그 그림이 「안 쓰인 자산」 으로 잡히고 깨진 링크를 못 잡는다.
        _where = ex + "\n" + str(it.get("passage") or "")
        linked = set(re.findall(r"\]\(assets/([^)]+?)\.svg\)", _where))
        if miss := sorted(linked - names):
            problems.append(f"{tag}: 본문이 그림 {miss} 을 링크하는데 assets 에 그 SVG 가 "
                            f"없습니다 — 사이트에서 깨진 이미지가 됩니다")
        # 반대쪽은 경고다. 그림을 넣고 안 쓴 것은 낭비지 고장이 아니다.
        if unused := sorted(names - linked):
            warns.append(f"{tag}: assets 의 {unused} 이 본문에서 쓰이지 않습니다")

    # 정답 위치 편중 — 파트 단위로는 표본이 작으므로 경고만
    if items:
        ai = [int(it.get("answer_index", -1)) for it in items]
        for k in range(4):
            if ai.count(k) > max(2, len(items) // 2):
                warns.append(f"정답이 {k+1}번에 {ai.count(k)}개 몰렸습니다")
    return problems, warns


# ── 집필 ────────────────────────────────────────────────────────────────────
def draft_part(*, round_code: str, part_index: int, book_dir: str,
               part_size: int = 0,          # 0 = 시험정보의 상한을 쓴다
               derive_hint: str = "",
               mode: str = "derive",
               round_index: int = 0, round_total: int = 0,
               model: str = "", effort: Optional[str] = None,
               on_activity: Optional[Callable[[str], None]] = None) -> PartResult:
    """파트 1개를 집필해 스테이징에 저장한다. 검증 실패도 **저장한다.**

    ★ 실패한 것도 저장하는 이유: $0.25~ 를 이미 썼다. 버리면 사람이 무엇이 틀렸는지
      볼 수 없고 다시 부르는 수밖에 없다. 저장해 두고 `merge` 가 막는다.
    """
    numbers = part_numbers(part_index, part_size)
    subj_nos = sorted({subject_no_for(n) for n in numbers})
    plans = difficulty_plan(n_parts(part_size))
    ask = plans[min(part_index - 1, len(plans) - 1)]

    author = ClaudeAuthor(model=model, effort=effort, cwd=book_dir,
                          on_activity=on_activity)
    prompt = part_prompt(round_code=round_code, numbers=numbers,
                         subject_nos=subj_nos, difficulty_ask=ask,
                         derive_hint=("" if mode == "exam" else derive_hint),
                         mode=mode,
                         round_index=round_index, round_total=round_total)

    res = PartResult(round_code=round_code, part_index=part_index, numbers=numbers,
                     mode=mode)
    # ★ 벽시계가 아니라 단조시계다. 집필 하나가 10~20분씩 가는데 그 사이 시스템
    #   시각이 바뀌면(NTP 보정·서머타임) 음수 초가 남는다.
    t0 = time.monotonic()
    try:
        # ★ 시스템 프롬프트도 **품목마다 다르다** — 시험정보에서 조립한다.
        got = author.structured(system(), prompt, part_schema(subj_nos, numbers))
        res.items = list(got.get("items") or [])
    except ProviderError as e:
        res.problems.append(str(e))
    finally:
        # ★ 실패해도 계량은 기록한다. 실패분에도 요금이 나간다 —
        #   답변초안 화면에서 같은 것을 이미 겪었다(실패분 비용을 따로 보여 준다).
        res.cost_usd = author.last_cost_usd
        res.turns = author.last_turns
        res.seconds = time.monotonic() - t0

    if res.items:
        p, w = _validate(res.items, numbers)
        res.problems += p
        res.warnings += w

    res.path = staging_path(round_code, part_index)
    atomic_write_json(res.path, {
        "round": round_code, "part": part_index, "numbers": numbers,
        "ok": res.ok, "problems": res.problems, "warnings": res.warnings,
        "cost_usd": round(res.cost_usd, 4), "turns": res.turns,
        "seconds": round(res.seconds, 1), "mode": res.mode,
        "items": res.items,
    }, indent=2, trailing_newline=True)
    return res


def is_done(round_code: str, part_index: int) -> bool:
    """이 과목이 **이미 합격으로** 스테이징에 있는가.

    ★ 7시간짜리 잡이 30/36 에서 끊겼을 때(구독 한도·서버 재시작·정전) 처음부터
      다시 돌리면 이미 만든 30과목을 또 태운다 — 실측으로 $44 다. 스테이징은
      과목이 끝나는 즉시 파일로 남으므로, 그 파일을 보고 건너뛰면 된다.
    ★ 합격한 것만 센다. 실패로 남은 파트는 다시 만들어야 하니 건너뛰면 안 된다.
    """
    import json
    p = staging_path(round_code, part_index)
    if not os.path.isfile(p):
        return False
    try:
        with open(p, encoding="utf-8") as f:
            return bool(json.load(f).get("ok"))
    except (OSError, ValueError):
        return False        # 읽을 수 없으면 없는 것으로 보고 다시 만든다


def list_staged(round_code: str) -> List[Dict[str, Any]]:
    """스테이징에 무엇이 있는가. 화면이 파트별 상태를 그린다."""
    import json
    d = staging_dir(round_code)
    out: List[Dict[str, Any]] = []
    for i in range(1, n_parts() + 1):
        p = staging_path(round_code, i)
        row: Dict[str, Any] = {"part": i, "numbers": part_numbers(i), "exists": False}
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    d0 = json.load(f)
                row.update(exists=True, ok=bool(d0.get("ok")),
                           n=len(d0.get("items") or []),
                           problems=d0.get("problems") or [],
                           warnings=d0.get("warnings") or [],
                           cost_usd=d0.get("cost_usd") or 0,
                           seconds=d0.get("seconds") or 0,
                           mode=d0.get("mode") or "")
            except (OSError, ValueError) as e:
                row.update(exists=True, ok=False, problems=[f"파일을 읽을 수 없습니다: {e}"])
        out.append(row)
    return out
