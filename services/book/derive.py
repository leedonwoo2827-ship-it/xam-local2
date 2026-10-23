"""파생 규칙 — _rounds 의 원천 값에서 계산되는 것들.

_rounds/mNN.json 은 최소한만 들고 있다. 02/*.md 와 05/lesson 이 필요로 하는
나머지 필드는 전부 여기서 만든다. 규칙이 흩어지면 세 산물이 조용히 어긋난다.

★ has_sql / has_table 은 _rounds 에 없다(실측 240문항 전부 false).
  그래서 파생하지 않고 기존 02/*.md 에서 읽어 **보존**하는 것이 기본이다.
  md 가 없을 때만 추정하고, 추정값은 UI 에 그렇다고 표시한다.
"""
from __future__ import annotations

import re

from core.constants import ANSWER_GLYPHS, KOR_NUM

# 정답 낭독문의 접두어. 실측 240문항 전부 이 형태를 쓴다.
#   "정답은 일 번입니다. 데이터 거버넌스의 세 가지 구성요소는 …"
SPEECH_PREFIX_RE = re.compile(r"^정답은\s*(일|이|삼|사|오)\s*번입니다\.\s*")
SPEECH_LOOSE_RE = re.compile(r"^정답은\s*(일|이|삼|사|오)\s*번")

_KOR_TO_INDEX = {v: k for k, v in KOR_NUM.items()}

# has_sql / has_table 추정 — md 가 없을 때만 쓰는 폴백이다.
_SQL_RE = re.compile(r"```sql|\bSELECT\b|\bFROM\b|\bWHERE\b|\bGROUP\s+BY\b|\bJOIN\b", re.I)
_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$", re.M)


def answer_glyph(answer_index: int) -> str:
    """0 → '①'. 02/*.md 의 `answer` 와 05/lesson 의 `answer` 가 이 값이다."""
    i = int(answer_index)
    if not 0 <= i < len(ANSWER_GLYPHS):
        raise ValueError(f"answer_index 범위 밖: {answer_index}")
    return ANSWER_GLYPHS[i]


def glyph_index(glyph: str) -> int | None:
    i = ANSWER_GLYPHS.find((glyph or "").strip())
    return i if i >= 0 else None


def has_figure(question: dict) -> bool:
    """_rounds 의 assets 유무. 이것만은 확실한 파생이다."""
    return bool(question.get("assets"))


def asset_names(question: dict) -> list[str]:
    """_rounds 의 assets → 확장자 없는 이름 목록. 순서 보존."""
    out = []
    for a in question.get("assets") or []:
        name = (a.get("name") if isinstance(a, dict) else str(a)) or ""
        name = name[:-4] if name.endswith(".svg") else name
        if name:
            out.append(name)
    return out


def asset_filenames_in(text: str) -> list:
    """이 **문자열 안**의 그림 참조 → 파일명 목록. 순서를 지킨다.

    ★ `asset_filenames(question)` 는 문항 전체를 본다. 지문에 있던 것만
      알아야 하는 자리가 있어(슬라이드의 문제 면) 따로 둔다.
    """
    import re

    out = []
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", str(text or "")):
        n = m.group(1).strip().split("/")[-1]
        if n and n not in out:
            out.append(n)
    return out


def asset_filenames(question: dict) -> list[str]:
    """05/lesson 의 assets 형식 — 파일명 배열이다(인라인 SVG 가 아니다)."""
    return [f"{n}.svg" for n in asset_names(question)]


# _rounds 의 explanation 은 그림이 있는 문항이면 본문 끝에 마크다운 이미지 줄을
# 품고 있다. 02/*.md 는 그걸 그대로 쓰지만 05/lesson 의 explanation 은 **떼어낸**
# 형태다(실측). assets 필드가 그 정보를 따로 들고 있어서 중복이기 때문이다.
_INLINE_FIG_RE = re.compile(r"\s*!\[[^\]]*\]\(assets/[^)]*\)")


def strip_inline_figures(text: str) -> str:
    """마크다운 이미지 줄을 걷어낸다. 05/lesson 의 explanation 형식."""
    return _INLINE_FIG_RE.sub("", text or "").rstrip()


# 강조 표기 — 도구 #2 가 lesson 에 넣을 때 손질하고, 그 손질이 회차마다 다르다.
#   실측: m01 은 `**가장 어려운**` → `<b>가장 어려운</b>`, m03 은 강조를 **제거**.
# 우리는 어느 쪽으로도 재현하지 않는다(재현할 규칙이 없다). 드리프트 비교에서만
# 양쪽을 벗겨 내용이 정말 다른지 본다.
_EMPHASIS_RE = re.compile(r"\*\*(.+?)\*\*|</?b>", re.S)


def normalize_emphasis(text) -> str:
    """`**…**` 과 `<b>…</b>` 를 벗긴 평문. 드리프트 비교 전용 — 저장에는 쓰지 않는다."""
    if not isinstance(text, str):
        return text
    return _EMPHASIS_RE.sub(lambda m: m.group(1) or "", text)


def inline_figure_names(text: str) -> list[str]:
    """본문에 인라인된 그림 파일명(확장자 제외). 에디터의 미리보기용."""
    out = []
    for m in re.finditer(r"!\[[^\]]*\]\(assets/([^)]*)\)", text or ""):
        f = m.group(1)
        out.append(f[:-4] if f.endswith(".svg") else f)
    return out


def guess_has_sql(question: dict) -> bool:
    text = " ".join([
        question.get("question") or "",
        " ".join(question.get("choices") or []),
        question.get("explanation") or "",
    ])
    return bool(_SQL_RE.search(text))


def guess_has_table(question: dict) -> bool:
    text = "\n".join([
        question.get("question") or "",
        question.get("explanation") or "",
    ])
    return len(_TABLE_RE.findall(text)) >= 2


def n_choices(question: dict) -> int:
    return len(question.get("choices") or [])


# ── 낭독문 정답번호 교차검증 ────────────────────────────────────────────────
def speech_answer_index(speech: str) -> int | None:
    """낭독문이 말하는 정답 번호. 접두어가 없으면 None."""
    m = SPEECH_LOOSE_RE.match((speech or "").strip())
    if not m:
        return None
    return _KOR_TO_INDEX.get(m.group(1))


def check_speech(question: dict) -> dict | None:
    """낭독문 정답번호와 보기 정답이 어긋나면 경고를 낸다.

    정답을 다른 보기로 옮기면 이 검사가 반드시 걸린다. 이걸 놓치면 렌더된 영상이
    "정답은 삼 번입니다" 라고 말하는데 화면의 정답은 ② 인 상태로 발행된다.
    """
    speech = question.get("explanation_speech") or ""
    if not speech.strip():
        return {
            "code": "speech_missing",
            "level": "warn",
            "text": "해설 낭독문이 비어 있습니다. 영상 내레이션이 만들어지지 않습니다.",
        }
    said = speech_answer_index(speech)
    if said is None:
        return {
            "code": "speech_no_prefix",
            "level": "info",
            "text": "낭독문이 '정답은 N 번입니다.' 로 시작하지 않습니다. 형식을 확인하세요.",
        }
    want = int(question.get("answer_index", -1))
    if said != want:
        return {
            "code": "speech_answer",
            "level": "error",
            "text": (f"낭독문 정답({KOR_NUM.get(said, '?')} 번)이 "
                     f"보기 정답({answer_glyph(want)})과 다릅니다."),
            "said_index": said,
            "want_index": want,
        }
    return None


def rewrite_speech_prefix(speech: str, answer_index: int) -> str:
    """정답이 바뀌었을 때 낭독문 접두어만 갈아 끼운다. 본문은 건드리지 않는다.

    접두어가 없으면 새로 붙이지 않는다 — 사람이 쓴 다른 형식일 수 있고, 조용히
    문장을 고치는 것보다 경고로 남기는 쪽이 안전하다.
    """
    s = speech or ""
    kor = KOR_NUM.get(int(answer_index))
    if kor is None:
        return s
    m = SPEECH_PREFIX_RE.match(s.strip())
    if m:
        return f"정답은 {kor} 번입니다. " + s.strip()[m.end():]
    m2 = SPEECH_LOOSE_RE.match(s.strip())
    if m2:
        return f"정답은 {kor} 번" + s.strip()[m2.end():]
    return s


# ── 검증 ────────────────────────────────────────────────────────────────────
def validate_question(question: dict) -> list[str]:
    """저장 전 최소 검증. 여기서 막지 못하면 발행 사전점검까지 흘러간다."""
    errs: list[str] = []
    q = (question.get("question") or "").strip()
    if not q:
        errs.append("문제문이 비어 있습니다.")

    choices = question.get("choices") or []
    if len(choices) != 4:
        errs.append(f"보기는 4개여야 합니다 (현재 {len(choices)}개).")
    for i, c in enumerate(choices):
        if not (c or "").strip():
            errs.append(f"{i + 1}번 보기가 비어 있습니다.")
        if ANSWER_GLYPHS[0] in (c or "") or (c or "").strip()[:1] in ANSWER_GLYPHS:
            errs.append(f"{i + 1}번 보기에 ①②③④ 글리프가 들어 있습니다. "
                        "보기 본문만 넣으세요 — 글리프는 렌더할 때 붙습니다.")

    ai = question.get("answer_index")
    if not isinstance(ai, int) or not 0 <= ai < max(1, len(choices)):
        errs.append(f"정답 번호가 범위를 벗어났습니다: {ai}")

    if not (question.get("explanation") or "").strip():
        errs.append("해설이 비어 있습니다.")

    diff = question.get("difficulty")
    if diff not in ("상", "중", "하"):
        errs.append(f"난이도는 상·중·하 중 하나여야 합니다 (현재 {diff!r}).")

    sn = question.get("subject_no")
    if not isinstance(sn, int) or sn < 1:
        # ★ 문자열이면 build_check.py 가 subjects: [] 를 내고 전 행 sj_no=0 이 된다.
        #   그런데 '과목 N종' 리포트 줄은 이걸 검증하지 못한다(다른 코드 경로).
        errs.append(f"subject_no 는 1 이상의 정수여야 합니다 (현재 {sn!r}). "
                    "문자열이면 웹의 과목 필터가 통째로 깨집니다.")

    if not (question.get("subject") or "").strip():
        errs.append("과목명이 비어 있습니다.")

    return errs
