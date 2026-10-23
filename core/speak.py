# -*- coding: utf-8 -*-
"""**아라비아 숫자를 소리대로.** 발음 대본 전용 — 자막은 건드리지 않는다.

★ 왜 필요한가. TTS 는 글자를 그대로 읽는다. `19장` 을 그대로 주면 판마다
  「일구장」·「열아홉장」으로 갈리고, 한 문장에 숫자가 여러 번 나오면 읽다가
  씹힌다. 손으로 고칠 수는 있지만 한 장에 열 군데씩 나오면 반드시 몇 개를
  놓친다 — 그래서 규칙으로 한다.

★ **모델을 부르지 않는다.** 순수 규칙이다. 문장을 다시 쓰는 위험을 질 이유가 없다.

★ 자막(`narration`)과 발음(`narration_text`)이 서로 다른 표기를 갖는 것은 이 앱의
  원래 설계다 — 화면에는 `2007년 3월`, 소리는 「이천칠 년 삼 월」.

출처: `leedonwoo2827-ship-it/summary-showcase` 의 `core/honorific.py`.
같은 사람이 같은 TTS(voicewright/Supertonic)를 쓰면서 실측으로 다듬은 규칙이라
새로 쓰지 않고 옮겨 왔다. 말투 변환(`~한다`→`~합니다`)은 가져오지 않았다 —
이 프로젝트의 낭독문은 집필 단계에서 이미 `~입니다` 로 나온다.
"""
from __future__ import annotations

import re

_SINO_D = "영일이삼사오육칠팔구"
_SINO_U = ["", "십", "백", "천"]
_SINO_G = ["", "만", "억", "조", "경"]

# 고유어로 세는 단위 — `3개`는 「삼 개」가 아니라 「세 개」다.
# ★ `분`·`초`·`년`·`월`·`퍼센트`는 한자어로 센다. 넣으면 오히려 틀린다.
#
# ★★ `번` 을 **뺐다.** showcase 에는 들어 있지만 이 프로젝트에서는 틀린다 —
#    시험 문제에서 `번` 은 세는 말이 아니라 **번호**다. `정답은 2번입니다` 를
#    「두 번」으로 읽으면 안 되고 「이 번」이어야 한다. 엔진의 발음사전도 `번` 을
#    한자어 쪽에 넣어 두었다(`voicewright/pronunciation.py` 의 `_SINO_TIGHT_UNITS`
#    — "문제·보기 번호" 라고 적혀 있다). 실측으로 10개 씬이 「두 번/세 번/네 번」이
#    되어 잡았다.
_NATIVE_UNIT = ("개", "명", "차례", "살", "가지", "군데", "곳", "마리",
                "시간", "달", "권")
_NATIVE = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉",
           "열", "열한", "열두", "열세", "열네", "열다섯", "열여섯", "열일곱",
           "열여덟", "열아홉", "스무"]


def _sino4(n: int) -> str:
    """네 자리 이하 — 자리 하나씩. 앞자리 1 은 안 읽는다(`19`→`십구`)."""
    out = ""
    for p in range(3, -1, -1):
        d = (n // 10 ** p) % 10
        if d:
            out += ("" if (d == 1 and p) else _SINO_D[d]) + _SINO_U[p]
    return out


def sino(n: int) -> str:
    """한자어 수 읽기. `19`→`십구`, `100`→`백`, `2026`→`이천이십육`.

    만·억·조는 **네 자리씩 끊어** 읽는다. `12345`→`일만이천삼백사십오`.
    """
    n = int(n)
    if n < 0:
        return "마이너스 " + sino(-n)
    if n == 0:
        return "영"
    if n < 10000:
        return _sino4(n)
    parts: list[str] = []
    g = 0
    while n and g < len(_SINO_G):
        chunk = n % 10000
        if chunk:
            parts.append(_sino4(chunk) + _SINO_G[g])
        n //= 10000
        g += 1
    if n:                        # 경을 넘어가면 읽지 않는다 — 그럴 일이 없다
        return str(int(n)) + "".join(reversed(parts))
    return "".join(reversed(parts))


_NUM_RE = re.compile(r"(\d[\d,]*)(\.\d+)?")

# 읽는 법이 **하나뿐인** 기호만. 긴 것부터 — `%p` 가 `%` 보다 먼저 잡혀야 한다.
#
# ★ 수식 기호(`=` `−` `+` `×` `÷` `→` `±` `≈`)는 넣지 않았다. 낭독문에 42·20·11·8·9회
#   나오지만 읽는 법이 문맥마다 갈린다 — `=` 는 「는」·「은 …이다」·「같다」가 다 되고,
#   `−` 는 「마이너스」와 「빼기」가 다르다. 규칙으로 박으면 틀린 쪽이 30곳에 퍼진다.
#   사람이 발음 칸에서 고친 것을 `tools/learn_speech.py` 로 모아 본 뒤에 올린다.
_SYMBOL = (("%p", " 퍼센트 포인트"), ("%", " 퍼센트"))

# 소수점은 **「쩜」**이다 — 「점」이 아니다(2026-08-18 인쇄물 교정 지시).
# 집필이 이미 한글 수사로 써 놓은 소수(`이 점 육`)가 1,153곳이라 손으로는 못 잡는다.
# ★ 앞뒤가 **한글 수사일 때만** 바꾼다. 그냥 「점」은 점수·관점·시점처럼 다른 말이다.
_SINO_WORD = r"(?:영|일|이|삼|사|오|육|칠|팔|구|십|백|천|만)"
_DEC_POINT_RE = re.compile(rf"({_SINO_WORD})\s*점\s*({_SINO_WORD})")

# 자모 낱자 — 보기 기호로 쓰인다. TTS 에 낱자를 그대로 주면 읽지 못하고 씹는다.
# ★ 집필 규약이 "시험지 표기는 ㄱㄴㄷㄹ 이고 자모 이름 낭독은 렌더 단계가 한다" 인데
#   (`services/authoring/spec.py`) 그 렌더 단계가 없었다. 그래서 어떤 회차는 집필이
#   「기역」으로 써 주고 어떤 회차는 `ㄱ` 이 그대로 남아 갈렸다 — 64곳 25번들.
_JAMO = {"ㄱ": "기역", "ㄴ": "니은", "ㄷ": "디귿", "ㄹ": "리을", "ㅁ": "미음",
         "ㅂ": "비읍", "ㅅ": "시옷", "ㅇ": "이응", "ㅈ": "지읒", "ㅊ": "치읓",
         "ㅋ": "키읔", "ㅌ": "티읕", "ㅍ": "피읖", "ㅎ": "히읗"}
# ★ 경계를 보지 않는다. `ㄱ-ㅎ` 은 호환 자모 블록(U+3131~)이고 완성형 음절은 `가-힣`
#   (U+AC00~)이라 **서로 겹치지 않는다** — 낱자가 낱자로 쓰인 자리에만 매칭된다.
#   앞뒤 경계를 걸었더니 `ㄹ이 옳습니다`·`ㄷ이 틀린` 의 조사 `이` 가 lookahead 를
#   막아서 두 곳이 안 바뀌었다(실측).
# 범위(`ㄱ~ㄹ`)를 낱자보다 **먼저** 처리한다. 낱자로 먼저 바꾸면 「기역 물결 리을」이 된다.
_JAMO_RANGE_RE = re.compile(r"([ㄱ-ㅎ])\s*[~∼〜–—-]\s*([ㄱ-ㅎ])")
_JAMO_ONE_RE = re.compile(r"([ㄱ-ㅎ])")


def speak_jamo(text: str) -> str:
    """보기 기호 자모를 **이름으로** 바꾼다. `ㄱ`→`기역`, `ㄱ~ㄹ`→`기역부터 리을까지`."""
    def rng(m: "re.Match[str]") -> str:
        a, b = _JAMO.get(m.group(1)), _JAMO.get(m.group(2))
        return f"{a}부터 {b}까지{_MARK}" if a and b else m.group(0)

    out = _JAMO_RANGE_RE.sub(rng, text or "")
    # ★ 바꾼 끝에 표시를 남긴다 — 뒤에 온 조사를 붙이려고(`join_josa`).
    #   「ㄱ 은 옳습니다」가 「기역 은」으로 남아 턱턱 끊겼다(2026-08-26).
    return _JAMO_ONE_RE.sub(
        lambda m: (_JAMO[m.group(1)] + _MARK) if m.group(1) in _JAMO else m.group(0), out)


# 괄호 안이 **영문뿐**인 부가설명 — 낭독에서만 뺀다. 화면·자막에는 남는다.
# ★ 집필 규약에 "괄호 부가설명은 낭독에서 빼고 화면에만 남긴다" 가 있는데
#   (`services/authoring/spec.py`) 발문에는 걸리지 않았다 — 해설과 달리 낭독문이
#   따로 없고 `question` 을 그대로 읽기 때문이다. `'정보(Information)' 단계` 가
#   영어 단어로 읽혔다.
# ★ 한글이 든 괄호는 건드리지 않는다 — `(단, …)` 조건과 `(ㄱ)` 보기 기호가 그렇다.
#   `(소수점 넷째 자리에서 반올림)` 처럼 사람이 빼기로 한 것은 그 씬의 발음으로 뺀다.
_PAREN_LATIN_RE = re.compile(r"\s*\([^()가-힣ㄱ-ㅎㅏ-ㅣ]*[A-Za-z][^()가-힣ㄱ-ㅎㅏ-ㅣ]*\)")


# ── 조사 붙이기 ─────────────────────────────────────────────────────────────
#
# ★ 왜 필요한가(2026-08-26 지적). 자막은 로마자·숫자 뒤에 조사를 **띄어** 쓴다 —
#   `NULL 이 포함됩니다` · `S1 의 MGR` · `결과는 0 입니다`. 한글로만 쓰면 붙여 쓸
#   자리다. 그대로 두면 발음이 「널 이」·「에스원 의」·「영 입니다」가 되어 읽을 때
#   턱턱 끊긴다. 자연스러운 곳도 있지만 아닌 곳이 훨씬 많다는 것이 사용자 판단이다.
#
# ★ **바꾼 자리에서만** 붙인다. 온 문장에 걸면 「정답은 이 번입니다」의 `이`(숫자 2)를
#   앞말에 붙여 「정답은이 번입니다」로 만든다. 그래서 치환한 끝에 보이지 않는 표시를
#   두고, 그 표시 뒤에 온 조사만 당겨 붙인 뒤 표시를 지운다.
#
# ★ 조사 **모양도 새 소리에 맞춘다.** 자막의 조사는 영문 철자를 보고 고른 것이라
#   소리와 어긋난다 — `SELECT 은` 은 「셀렉트은」이 아니라 「셀렉트는」이어야 한다.
_MARK = ""

# 받침 있을 때 : 받침 없을 때
_PAIRS = {"은": "는", "이": "가", "을": "를",
          "과": "와", "으로": "로", "이나": "나",
          "이라고": "라고", "이며": "며",
          "이란": "란", "이야": "야", "이라": "라", "이라서": "라서",
          "이지만": "지만", "으로서": "로서", "으로써": "로써", "이고": "고"}
_HAS, _NO = dict(_PAIRS), {v: k for k, v in _PAIRS.items()}

# 모양이 하나뿐인 조사 — 붙이기만 한다
_PLAIN = ("의", "에서", "에게", "에", "도", "만",
          "부터", "까지", "처럼", "보다", "마다",
          "밖에", "입니다", "인")

_JOSA_RE = re.compile(
    "([가-힣])" + _MARK + r"[ 	]+("
    + "|".join(sorted(set(list(_HAS) + list(_NO) + list(_PLAIN)), key=len, reverse=True))
    + r")(?=[\s,.…!?)\]]|$)")


def _agree(syllable: str, josa: str) -> str:
    """앞 소리에 맞는 조사 모양. 받침이 있으면 `은/이/을/과/으로`, 없으면 `는/가/를/와/로`."""
    jong = (ord(syllable) - 0xAC00) % 28
    if josa in _PLAIN:
        return josa
    base = _NO.get(josa, josa)          # 받침 있을 때의 모양으로 통일
    if jong == 0:                       # 받침 없음
        return _HAS.get(base, base)
    if base == "으로" and jong == 8:   # ㅊㄱ 받침은 「로」
        return "로"
    return base


def join_josa(text: str) -> str:
    """치환 표시 뒤의 조사를 앞말에 붙이고 표시를 지운다."""
    out = _JOSA_RE.sub(lambda m: m.group(1) + _agree(m.group(1), m.group(2)), text or "")
    return out.replace(_MARK, "")


def spell_terms(text: str, terms: dict | None = None) -> str:
    """품목별 약어를 읽는 소리로 바꾼다 — **공용 규칙 위에 덧붙이는 층**이다.

    ★ 나눠 두는 이유(2026-08-19 지시):
        · 공용 사전(`pronunciation_map.yaml`)은 **된소리·소숫점·연도** 같은
          일반 규칙이다. 품목이 늘어도 같은 규칙이라 한곳에 둔다.
        · **약어는 시험마다 다르다.** `SQL`→에스큐엘 은 SQLD 의 것이고
          `RMSE`→알엠에스이 는 빅분기의 것이다. 그래서 `exams/<pd>.json` 의
          `speech_dict` 에 두고 여기서 덧붙인다.

    ★ 긴 것부터 바꾼다. `GROUP BY` 를 `GROUP` 보다 늦게 처리하면 앞부분만
      바뀌고 뒤가 남는다.
    ★ 자막에는 적용하지 않는다 — 이 함수는 발음 트랙만 지난다.
    """
    if not terms:
        return text or ""
    out = text or ""
    for k in sorted(terms, key=len, reverse=True):
        v = str(terms[k] or "").strip()
        if not k or not v:
            continue
        # ★★ 경계는 **숫자·로마자·밑줌만** 본다. 전에는 `가-힣` 도 들어 있어서
        #   **뒤에 한글 조사가 붙으면 사전을 건너뛰었다** — 한국말 문장에서는 그게 가장
        #   흔한 자리다. SQLD 대본 실재로 `NULL이` 667 · `SQL처럼` 562 ·
        #   `JOIN이므로` 102 … 모든 1,467곳이 생으로 남았다(2026-08-25 실재).
        # ★ `0-9A-Za-z` 는 지후다 — `NULLIF` 가 「널IF」 로 변하는 것을 그게 막는다.
        # ★ 밑줌(`_`)도 경계다 — `TEAM` 이 `TEAM_ID` 의 앞부분을 바꿔 `팀_ID` 가 되지 않게.
        out = re.sub(r"(?<![0-9A-Za-z_])" + re.escape(str(k))
                     + r"(?![0-9A-Za-z_])", lambda _m, _v=v: _v + _MARK, out)
    return out


def to_speech(text: str, terms: dict | None = None) -> str:
    """자막 원문 → **발음 대본.** bake 가 씬마다 이걸 통과시킨다.

    자막(`narration`)은 손대지 않는다 — 갈라지는 것은 `narration_text` 뿐이다.
    `terms` 는 그 품목의 약어 사전(`exams/<pd>.json` 의 `speech_dict`)이다.
    """
    # ★ 사전을 **두 번** 돌린다. `1TB`·`128MB`·`log2` 처럼 숫자가 바로 앞뒤에 붙으면
    #   경계 조건(`(?<![0-9A-Za-z_])`)에 막혀 1차에서 안 잡힌다. 숫자를 소리로 바꾸고
    #   나면 「일 TB」 가 되어 그때 잡힌다(실측 2026-08-26, 빅분기 대본 17곳).
    #   두 번 돌려도 안전하다 — 바뀐 값은 한글이라 다시 걸릴 키가 없다.
    out = spell_terms(_PAREN_LATIN_RE.sub("", text or ""), terms)
    out = spell_terms(speak_numbers(out), terms)
    return join_josa(speak_jamo(out))


def speak_numbers(text: str) -> str:
    """글 속의 아라비아 숫자를 소리대로 바꾼다.

        1960년대     → 천구백육십 년대
        2.0퍼센트    → 이 쩜 영 퍼센트
        3개          → 세 개
        8.2%         → 팔 쩜 이 %

    ★ **소수점은 「쩜」이다.** `2.0` 은 「이 쩜 영」이고 「이 점 영」이 아니다.
      소수부는 자리마다 하나씩 읽는다.

    ★ 숫자만 건드린다 — 문체도 띄어쓰기도 손대지 않는다.
    ★ 두 번 돌려도 같다(멱등). 바꾸고 나면 숫자가 남지 않는다.
    """
    src = text or ""
    for sym, said in _SYMBOL:
        src = src.replace(sym, said)
    src = re.sub(r" {2,}", " ", src)
    src = _DEC_POINT_RE.sub(r"\1 쩜 \2", src)

    def one(m: "re.Match[str]") -> str:
        head = m.group(1).replace(",", "")
        frac = m.group(2)
        tail = src[m.end():]

        # 뒤에 붙은 단위를 본다 — 고유어로 세는 것이 따로 있다
        unit = ""
        for u in _NATIVE_UNIT:
            if tail.startswith(u):
                unit = u
                break

        try:
            n = int(head)
        except ValueError:
            return m.group(0)

        if frac:
            digits = " ".join(_SINO_D[int(c)] for c in frac[1:])
            said = f"{sino(n)} 쩜 {digits}"
        elif unit and 1 <= n <= 20:
            said = _NATIVE[n]
        else:
            said = sino(n)

        # 단위가 바로 붙어 있으면 한 칸 띄운다 — 「천구백육십년」보다 잘 읽힌다
        nxt = tail[:1]
        return said + _MARK + (
            " " if nxt and not nxt.isspace() and nxt not in ",.·)]%" else "")

    return _NUM_RE.sub(one, src)
