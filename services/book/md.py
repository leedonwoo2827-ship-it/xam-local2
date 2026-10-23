"""02/mNN-KK.md 렌더러 · 파서 — 바이트 단위로 원본을 재현해야 한다.

이 240개 파일은 원격 Claude 세션에서 만들어졌고 로컬에 생성 스크립트가 없다.
렌더러가 한 글자라도 어긋나면 한 문항을 저장할 때 나머지 239개까지 조용히 바뀐다.
그래서 services/book/verify.py 의 왕복 검증(240/240 바이트 동일)을 통과하기
전에는 저장 경로를 열지 않는다.

실측한 형식 (02/m01-01.md 1095 bytes / 02/m01-02.md 1216 bytes):
  · 개행 LF 전용, BOM 없음, EOF 는 개행 하나로 끝난다
  · front matter 18키, 순서 고정
  · tags 만 인라인 flow 목록  `tags: [데이터거버넌스, 조직관리]`
  · 각 `## ` 섹션 앞에 빈 줄 하나
  · 보기는 `"① "` 접두 4줄, 사이 빈 줄 없음
  · 그림이 있으면 맨 끝에 빈 줄 하나 + `![{name} 참고 그림](assets/{name}.svg)`

PyYAML 로 덤프하지 않고 손으로 조립한다. 기본 덤퍼는 인라인 flow 목록도, 한글
무인용부호 스칼라도, 이 키 순서도 그대로 내지 못한다.
"""
from __future__ import annotations

import os
import re

import yaml

from core.constants import ANSWER_GLYPHS
from services.book import derive

# front matter 키 순서 — 이 순서가 곧 파일 형식이다. 바꾸면 240개가 전부 달라진다.
FM_ORDER = (
    "id", "round", "round_label", "subject", "subject_no", "question_no",
    "answer", "answer_index", "difficulty", "tags", "derived_from",
    "has_figure", "has_sql", "has_table",
    "authored_by", "verified", "reviewed", "needs_review",
)

# 인라인 flow 목록으로 내보낼 키. 01/ 의 source_pages 는 블록 목록이지만
# 우리가 쓰는 02/ 에는 tags 뿐이다.
FM_FLOW_LIST = ("tags",)

SECTION_QUESTION = "## 문제"
SECTION_PASSAGE = "## 지문"
SECTION_CHOICES = "## 보기"
SECTION_EXPLAIN = "## 해설"

# YAML 무인용부호 스칼라로 낼 수 없는 값 — 조용히 깨진 YAML 을 내보내지 않기 위한 가드.
_UNSAFE_SCALAR = re.compile(r"^[\s>|@`%*&!\[\]{}#,'\"]|:\s|\s#|[\n\r\t]|\s$")


def _scalar(value: str, key: str) -> str:
    s = str(value)
    if _UNSAFE_SCALAR.search(s):
        raise ValueError(
            f"front matter 값이 YAML 무인용부호 스칼라로 안전하지 않습니다 "
            f"(key={key!r}, value={s!r}). 원본 240개는 전부 안전한 값이라 "
            f"이 오류는 입력이 잘못됐다는 뜻입니다."
        )
    return s


# ★ flow 목록 항목을 언제 따옴표로 감싸는가 — **YAML 규격으로 정한다.**
#
#   ☠ 여기를 **품목 하나를 보고 정하지 않는다.** 처음에는 빅분기 720문항에서 따옴표
#     쓴 태그가 `"R&R"` 뿐이라 "`&` 가 있으면 감싼다" 로 잡았다. SQLD 를 붙이자
#     `M:N 관계` 같은 태그 7건이 매번 불일치로 떴고, 그 때문에 발행이 막혔다
#     (2026-08-25). 눈앞의 데이터에서 규칙을 뽑으면 다음 품목에서 또 깨진다.
#
#   그래서 반대로 잡는다 — **맨글자로 둬도 YAML 이 안전한 것만 안 감싸고, 나머지는
#   전부 감싼다.** 안전의 정의는 품목이 아니라 YAML 이 준다:
#
#       · 첫 글자가 지시문자(`- ? : , [ ] { } # & * ! | > ' " % @ \``)가 아니다
#       · 안에 flow 지시문자(`, [ ] { } :`)·주석표시(`#`)·따옴표가 없다
#       · 앞뒤에 공백이 없고 빈 값이 아니다
#
#   실측은 **규칙을 정하는 데 쓰지 않고, 기존 파일을 안 바꾼다는 확인에만** 쓴다.
#   2026-08-25 기준 빅분기 720 + SQLD 1,000 = 1,720파일 · 태그 5,424개에 대해
#   이 규칙의 출력이 파일과 **5,424/5,424 일치**한다(불일치 0). 즉 규칙을 넓혀도
#   지금 나가는 바이트는 한 글자도 달라지지 않는다.
_FLOW_INDICATOR_FIRST = "-?:,[]{}#&*!|>'\"%@`"
# `&` 는 첫 글자가 아니면 YAML 상 안전하지만 여기서는 **안전하지 않다고 본다.**
# 품목 때문이 아니라 **쓰는 사람이 둘**이기 때문이다 — 도구 #2 가 쓴 파일이
# `"R&R"` 처럼 감싸므로, 우리가 안 감싸면 그 파일과 왕복 검증이 어긋난다.
_FLOW_UNSAFE = re.compile(r"""[,\[\]{}:#&'"]""")
_FLOW_FIRST_BAD = re.compile("^[" + re.escape(_FLOW_INDICATOR_FIRST) + "]")


def _flow_safe(s: str) -> bool:
    """맨글자로 둬도 되는가. 하나라도 걸리면 감싼다(보수적으로)."""
    return bool(s) and s == s.strip()         and not _FLOW_FIRST_BAD.match(s) and not _FLOW_UNSAFE.search(s)


# 감싸도 담을 수 없는 값 — 줄바꿈·탭·따옴표는 한 줄 flow 목록에 못 넣는다.
_FLOW_IMPOSSIBLE = re.compile(r"""[
	"]""")


def _flow_item(value: str, key: str) -> str:
    """flow 목록 항목 하나. 안전하면 맨글자로, 아니면 따옴표로 감싼다.

    ★ 감쌀 수 있는 값은 `_scalar` 의 가드에 걸지 않는다. 그 가드는 **맨글자로 낼
      때** 깨진 YAML 이 나가는 것을 막는 것인데, 감싸면 깨지지 않기 때문이다.
      전에는 `[`·`,` 가 든 태그가 저장 자체를 예외로 막았다 — 감싸면 되는 값이었다.
    """
    s = str(value)
    if _FLOW_IMPOSSIBLE.search(s):
        raise ValueError(
            f"flow 목록에 넣을 수 없는 값입니다 — 줄바꿈·탭·따옴표는 담지 못합니다 "
            f"(key={key!r}, value={s!r}).")
    return s if _flow_safe(s) else f'"{s}"' 


def _fm_line(key: str, value) -> str:
    if isinstance(value, bool):
        return f"{key}: {'true' if value else 'false'}\n"
    if isinstance(value, int):
        return f"{key}: {value}\n"
    if key in FM_FLOW_LIST:
        items = [_flow_item(v, key) for v in (value or [])]
        return f"{key}: [{', '.join(items)}]\n"
    # ★ **빈 문자열은 `""` 로 낸다** — 위 `"R&R"` 과 같은 종류의 2바이트 문제다.
    #
    #   YAML 로는 `key:` 와 `key: ""` 가 둘 다 되지만, `02/*.md` 를 쓰는 사람이 **둘**이다:
    #   이 앱(문항 저장)과 vendor 의 `build.py`(파생). 표기가 갈리면 파생을 돌릴 때마다
    #   왕복 검증이 720건 전부 불일치로 뜨고, 발행 사전점검이 `q.md_sync` error 로 막힌다.
    #   실제로 그렇게 막혔다(2026-08-13).
    #
    #   어느 쪽으로 맞출지는 **파일에서 되맞춘다**(이 저장소의 규칙). 720개 전수에서
    #   빈 값은 `derived_from: ""` 뿐이고 값 없이 빈 키는 **하나도 없다** →
    #   "빈 문자열이면 감싼다" 가 관측과 정확히 일치한다.
    s = _scalar(value, key)
    return f'{key}: ""\n' if s == "" else f"{key}: {s}\n"


def front_matter(fm: dict) -> str:
    """dict → front matter 본문(구분선 제외). 누락 키는 오류로 낸다."""
    missing = [k for k in FM_ORDER if k not in fm]
    if missing:
        raise ValueError(f"front matter 키 누락: {missing}")
    return "".join(_fm_line(k, fm[k]) for k in FM_ORDER)


def build_front_matter(question: dict, round_meta: dict, flags: dict) -> dict:
    """_rounds 의 질문 + 회차 메타 + 보존 플래그 → front matter dict.

    flags 는 기존 md 에서 읽어 온 값이다 — has_sql / has_table / authored_by /
    verified / reviewed / needs_review 는 _rounds 에 없어서 보존해야 한다.
    """
    round_no = int(round_meta["round"])
    qno = int(question["question_no"])
    return {
        "id": f"m{round_no:02d}-{qno:02d}",
        "round": round_no,
        "round_label": round_meta["round_label"],
        "subject": question["subject"],
        "subject_no": int(question["subject_no"]),
        "question_no": qno,
        "answer": derive.answer_glyph(question["answer_index"]),
        "answer_index": int(question["answer_index"]),
        "difficulty": question["difficulty"],
        "tags": list(question.get("tags") or []),
        "derived_from": question.get("derived_from") or "",
        "has_figure": derive.has_figure(question),
        "has_sql": bool(flags.get("has_sql", False)),
        "has_table": bool(flags.get("has_table", False)),
        "authored_by": flags.get("authored_by") or "claude",
        "verified": bool(flags.get("verified", True)),
        "reviewed": bool(flags.get("reviewed", False)),
        "needs_review": bool(flags.get("needs_review", True)),
    }


def table_md(table) -> str:
    """_rounds 의 `table` 필드 → 마크다운 표. 실측(260723 m04) 형식.

        {"columns": ["담당","출고량"], "rows": [["도현",90], …]}
          | 담당 | 출고량 |
          | --- | --- |
          | 도현 | 90 |
    """
    if not isinstance(table, dict):
        return ""
    cols = [str(c) for c in (table.get("columns") or [])]
    if not cols:
        return ""
    lines = ["| " + " | ".join(cols) + " |",
             "| " + " | ".join("---" for _ in cols) + " |"]
    for row in table.get("rows") or []:
        # ★ null 셀은 문자열 "None" 으로 나간다 — 원 생성기가 str(cell) 을 그대로
        #   썼고, 실측 파일에 `| P02 | D2 | None |` 로 박혀 있다. 빈칸으로
        #   '고쳐 주면' 5문항이 어긋난다. 여기서 예쁘게 만들 자리가 아니다.
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def passage_parts(question: dict) -> list[str]:
    """`## 지문` 을 이루는 조각들. 없으면 빈 목록(섹션 자체를 내지 않는다).

    ★ 두 책이 지문을 서로 **다른 필드**에 담는다. 어느 한쪽만 보면 다른 책이 깨진다.
      · 260730(빅분기) — `passage` 에 그림 줄 하나. `sql`·`table` 필드가 없다.
      · 260723(SQLD)   — `passage` 는 null 이고 `table`·`sql` 필드에 자료가 있다.
        그림은 `question` 본문에 인라인돼 있다. 실측 순서는 **표 → SQL** 이고
        둘 사이에 빈 줄이 없다(m04-12).
    """
    parts = []
    p = (question.get("passage") or "").strip()
    if p:
        parts.append(p)
    t = table_md(question.get("table"))
    if t:
        parts.append(t)
    sql = (question.get("sql") or "").strip()
    if sql:
        parts.append("```sql\n" + sql + "\n```")
    return parts


PIPE = chr(124)
# 이스케이프된 파이프(`\|`)는 셀 내용이다 — 구분자로 세지 않는다.
_CELL_SPLIT = re.compile(r"(?<!\\)\|")


def is_block_choice(text: str) -> bool:
    """이 보기를 `①` 단독 줄 + 빈 줄 + 본문 형태로 써야 하는가.

    도구 #1 의 `qmodel._body_tokens` 가 쓰는 판정과 같아야 한다 — 두 단계(01/·02/)가
    같은 문항을 다르게 쓰면 대조가 무의미해진다.
    """
    ex = (text or "").lstrip()
    if not ex:
        return False
    if "\n" in ex or ex[:2] in ("**", "``", "!["):
        return True
    # ★ 파이프로 시작해도 **표가 아니면** 블록형이 아니다.
    #   SQL 문자열 결합 연산자 `||` 가 보기 하나로 오는 문항이 있다(SQLD 12번).
    #   블록형으로 쓰면 글리프만 한 줄 남고 값이 아래로 떨어져 보기가 두 줄로 갈린다.
    #   표 판정: 양끝 파이프를 뗀 뒤 **칸 하나라도 내용이 있으면** 표다.
    #   ★ '칸이 둘 이상' 을 요구하면 **1열 표**가 깨진다 — 보기가 1열 표인
    #     문항이 있다(SQLD 20번: `| MAX(COL1) |` / `|---|` / `| 2 |`).
    if ex.startswith(PIPE):
        return any(c.strip() for c in _CELL_SPLIT.split(ex.strip(PIPE)))
    return False


def render(question: dict, round_meta: dict, flags: dict) -> str:
    """문항 하나 → 02/mNN-KK.md 전문."""
    fm = build_front_matter(question, round_meta, flags)

    choices = question.get("choices") or []
    if len(choices) > len(ANSWER_GLYPHS):
        raise ValueError(f"보기가 너무 많습니다: {len(choices)}")

    out = ["---\n", front_matter(fm), "---\n"]
    out.append("\n" + SECTION_QUESTION + "\n")
    out.append((question.get("question") or "").strip() + "\n")
    # ★ `## 지문` — 업로드본에는 이 섹션이 아예 없었다(02/ 에는 지문이 없다고 본 것).
    #   그래서 260730 은 240개 중 15개, 260723 은 300개 중 26개가 통째로 빠졌다.
    #   조각 구성은 passage_parts() 참고 — 책마다 담는 필드가 다르다.
    parts = passage_parts(question)
    if parts:
        out.append("\n" + SECTION_PASSAGE + "\n")
        out.append("\n".join(parts) + "\n")
    out.append("\n" + SECTION_CHOICES + "\n")
    for i, c in enumerate(choices):
        ex = (c or "").strip()
        if is_block_choice(ex):
            # ★ 블록형 보기 — 글리프만 한 줄, 빈 줄, 그리고 블록. 뒤에 빈 줄 하나.
            #   실측(260723 SQLD, 38문항): 보기가 SQL 코드블록·표·그림인 문항이
            #   이 형식이다. 업로드본은 항상 `① {text}` 한 줄로 봤고 그래서
            #   300문항 중 38개가 어긋났다. 도구 #1 의 `_body_tokens` 와 같은 규칙이다.
            out.append(f"{ANSWER_GLYPHS[i]}\n\n{ex}\n\n")
        else:
            out.append(f"{ANSWER_GLYPHS[i]} {ex}\n")
    out.append("\n" + SECTION_EXPLAIN + "\n")
    # ★ 그림 줄을 여기서 붙이지 않는다.
    #   실측: _rounds 의 explanation 자체가 이미 `\n\n![{name} 참고 그림](assets/…)` 로
    #   끝난다. assets[] 는 SVG 본문(파일로 쓸 내용)만 들고 있는 별개 필드다.
    #   붙이면 이미지 줄이 두 번 나온다(첫 검증에서 76문항이 이걸로 걸렸다).
    #   axexam 의 build_check.py 도 같은 전제다 —
    #   `figures = sorted(asset_field - inl_q - inl_e)` 로 인라인된 것을 빼므로
    #   이 문항들의 figures_json 은 빈 배열이고 마크다운 렌더가 그림을 그린다.
    out.append((question.get("explanation") or "").strip() + "\n")

    return "".join(out)


# ── 파서 ────────────────────────────────────────────────────────────────────
def parse(text: str) -> dict:
    """02/*.md → {"fm": dict, "question": str, "choices": [...], "explanation": str,
                  "assets": [name, ...]}

    front matter 는 PyYAML 로 읽는다(읽기는 관대해도 된다 — 쓰기만 엄격하다).
    """
    if not text.startswith("---"):
        raise ValueError("front matter 구분선(---)으로 시작하지 않습니다.")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("front matter 를 닫는 --- 를 찾지 못했습니다.")
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2]

    out = {"fm": fm, "question": "", "passage": "", "choices": [],
           "explanation": "", "assets": []}

    def section(name: str, nxt: str | None) -> str:
        i = body.find(name)
        if i < 0:
            return ""
        start = i + len(name)
        end = body.find(nxt, start) if nxt else len(body)
        if end < 0:
            end = len(body)
        return body[start:end].strip()

    # 문제는 지문이 있으면 거기서 끊긴다 — 없으면 보기까지.
    out["question"] = section(SECTION_QUESTION,
                              SECTION_PASSAGE if SECTION_PASSAGE in body
                              else SECTION_CHOICES)
    out["passage"] = section(SECTION_PASSAGE, SECTION_CHOICES)
    raw_choices = section(SECTION_CHOICES, SECTION_EXPLAIN)
    # ★ 블록형 보기(코드블록·표·그림)는 여러 줄에 걸친다. 글리프로 시작하지 않는
    #   줄은 **앞 보기에 이어 붙인다** — 새 보기로 세면 SQLD 의 한 문항이 보기
    #   20개로 읽히고, 정답 번호 검증이 통과해 버린다.
    #   빈 줄도 블록 안에서는 의미가 있어서 보존한다.
    for line in raw_choices.split("\n"):
        stripped = line.strip()
        if stripped and stripped[0] in ANSWER_GLYPHS:
            out["choices"].append(stripped[1:].strip())
        elif out["choices"]:
            out["choices"][-1] = (out["choices"][-1] + "\n" + line).strip("\n")
        elif stripped:
            out["choices"].append(stripped)
    out["choices"] = [c.strip("\n") for c in out["choices"]]

    # ★ 해설은 그림 줄을 **포함한 채로** 둔다. _rounds 의 explanation 이 그렇게
    #   생겼고, 여기서 떼어내면 왕복이 깨진다. 인라인된 파일명만 따로 보고한다.
    expl = section(SECTION_EXPLAIN, None)
    img_re = re.compile(r"!\[(?P<alt>[^\]]*)\]\(assets/(?P<file>[^)]+)\)")
    # 지문과 해설 양쪽을 본다 — 그림 줄은 두 곳 다에 온다(실측: 지문 15건).
    for m in img_re.finditer(out["passage"] + "\n" + expl):
        f = m.group("file")
        name = f[:-4] if f.endswith(".svg") else f
        if name not in out["assets"]:
            out["assets"].append(name)
    out["explanation"] = expl
    return out


def read_flags(md_path: str) -> dict:
    """기존 md 에서 보존해야 하는 플래그를 읽는다.

    ★ has_sql / has_table 은 _rounds 에 없다(실측 240문항 전부 false). 파일이
      있으면 그 값을 그대로 다시 쓴다. 없을 때만 추정하고, 추정했다는 사실을
      `estimated` 로 알려서 화면이 '추정' 배지를 달 수 있게 한다.
    """
    if os.path.isfile(md_path):
        try:
            fm = parse(open(md_path, encoding="utf-8").read())["fm"]
            return {
                "has_sql": bool(fm.get("has_sql", False)),
                "has_table": bool(fm.get("has_table", False)),
                "authored_by": fm.get("authored_by") or "claude",
                "verified": bool(fm.get("verified", True)),
                "reviewed": bool(fm.get("reviewed", False)),
                "needs_review": bool(fm.get("needs_review", True)),
                "source": "preserved",
            }
        except Exception:
            pass   # 손상된 md — 아래 추정으로 내려간다
    return {"source": "estimated"}


def flags_for(question: dict, md_path: str) -> dict:
    """보존 우선, 없으면 추정."""
    flags = read_flags(md_path)
    if flags.get("source") == "estimated":
        flags.update({
            "has_sql": derive.guess_has_sql(question),
            "has_table": derive.guess_has_table(question),
            "authored_by": "claude",
            "verified": True,
            "reviewed": False,
            "needs_review": True,
        })
    return flags
