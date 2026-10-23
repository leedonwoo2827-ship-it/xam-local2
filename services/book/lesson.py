"""05/<bundle>/source/lesson_<bundle>.json — ★ 문제 본문이 실제로 웹에 가는 경로.

axexam 의 scripts/build_check.py 는 문제문·보기·해설·정답을 **이 파일에서만**
읽는다(`collect()`). 02/*.md 는 과목·난이도·태그·verified/reviewed/needs_review
만 공급한다(`exam_meta.py::_MD_ONLY`).

그래서 문항을 고칠 때 02/*.md 만 쓰면 다음 빌드가 낡은 05 본문을 다시 내보내고,
pr_hash 가 그대로여서 임포트가 '변경없음' 을 찍는다 — 수정이 웹에 전혀 반영되지
않는다. 이 모듈이 그 구멍을 막는다.

실측 형식 (05/m01-1/source/lesson_m01-1.json, 14275 bytes):
  · json indent=2, ensure_ascii=False, **끝에 개행 없음**, LF 전용
  · blocks[] 는 kind="section" 과 kind="problem" 이 섞여 있다
  · problem 블록 키 순서:
      kind number type question [passage] choices answer answer_index
      explanation explanation_speech difficulty tags [assets]
    ★ passage 는 **_rounds 에 지문이 있는 문항에만** 나온다(실측 240 중 15개, 전부 m01).
      값은 explanation 과 같은 규칙으로 **인라인 그림 줄을 뺀** 형태다 — 15개 지문이
      모두 그림 한 줄이라서 실제 값은 전부 `""` 다. 그림은 assets 가 들고 있다.
      업로드본은 이 키를 아예 몰랐고, 그래서 24번들이 전부 왕복에서 어긋났다.
      "항상 `\"\"` 로 넣는다" 도 틀린다 — 나머지 225개에는 키가 없다.
  · number 는 **전역 문항번호**(1~80)다. 번들 안 순번이 아니다
  · assets 는 **파일명 배열**(["m01-02-dmz.svg"]) — _rounds 의 인라인 SVG 가 아니다
  · subject / subject_no / derived_from 은 여기 **없다**(그래서 과목이 02 에서만 온다)
"""
from __future__ import annotations

import json
import os

from core.atomic_io import atomic_write_text, backup_sibling
from services.book import derive, jsonio, paths

# problem 블록 키 순서 — 실측값. assets 는 있을 때만 맨 뒤에 붙는다.
BLOCK_ORDER = (
    "kind", "number", "type", "question", "passage", "choices",
    "answer", "answer_index",
    "explanation", "explanation_speech", "difficulty", "tags",
)


def load(bundle: str) -> dict:
    with open(paths.bundle_lesson(bundle), encoding="utf-8") as f:
        return json.load(f)


def problem_blocks(doc: dict) -> list[dict]:
    """kind=="problem" 인 블록만. build_check.collect() 와 같은 판정 규칙을 쓴다."""
    out = []
    for b in doc.get("blocks") or []:
        if b.get("kind") == "problem" or b.get("question"):
            out.append(b)
    return out


def block_index(doc: dict, question_no: int) -> int:
    """전역 문항번호로 blocks[] 안의 위치를 찾는다."""
    for i, b in enumerate(doc.get("blocks") or []):
        if (b.get("kind") == "problem" or b.get("question")) and \
                int(b.get("number", -1)) == int(question_no):
            return i
    return -1


# _rounds 의 필드 → lesson 블록의 키. 한 필드가 두 키를 움직이는 경우가 있다.
FIELD_TO_KEYS = {
    "question": ("question",),
    "passage": ("passage",),
    "choices": ("choices",),
    "answer_index": ("answer", "answer_index"),
    "explanation": ("explanation",),
    "explanation_speech": ("explanation_speech",),
    "difficulty": ("difficulty",),
    "tags": ("tags",),
    "assets": ("assets",),
}


def block_from_rounds(question: dict, previous: dict | None = None) -> dict:
    """_rounds 의 질문만으로 조립한 problem 블록 (lesson 파일이 없을 때의 기준값).

    ★ 05/lesson 의 본문은 `_rounds` 와 **글자가 다르다.** 도구 #2 가 텍스트를
      한 번 손질해서 넣기 때문이고, 그 손질이 회차마다 일정하지도 않다. 실측:
        · 인라인 그림 줄 제거 — explanation · passage · question 세 곳 모두
          (m01 은 passage 에, m02·m03 은 question 안에 그림 줄이 있다)
        · 강조 표기 — m01 은 `**…**` → `<b>…</b>`, m03 은 아예 제거
      그래서 "_rounds 로 lesson 을 재생성한다" 는 전제 자체가 성립하지 않는다.
      아래 render() 가 **고친 필드만** 갈아 끼우는 이유다.
    """
    block = {
        "kind": "problem",
        "number": int(question["question_no"]),
        "type": (previous or {}).get("type") or "multiple_choice",
        # 그림 줄은 lesson 쪽에 두지 않는다 — assets 가 따로 들고 있어 중복이다.
        "question": derive.strip_inline_figures(question.get("question") or ""),
        "choices": [(c or "").strip() for c in (question.get("choices") or [])],
        "answer": derive.answer_glyph(question["answer_index"]),
        "answer_index": int(question["answer_index"]),
        "explanation": derive.strip_inline_figures(question.get("explanation") or ""),
        "explanation_speech": (question.get("explanation_speech") or "").strip(),
        "difficulty": question["difficulty"],
        "tags": list(question.get("tags") or []),
    }
    # passage 는 지문이 있는 문항에만, question 과 choices 사이에 낀다(실측 15개).
    raw_passage = (question.get("passage") or "").strip()
    if raw_passage:
        head = ("kind", "number", "type", "question")
        block = {**{k: block[k] for k in head},
                 "passage": derive.strip_inline_figures(raw_passage),
                 **{k: v for k, v in block.items() if k not in head}}

    names = derive.asset_filenames(question)
    if names:
        block["assets"] = names
    # ★★ **지문이 가리킨 그림**을 따로 남긴다. 그림 줄을 지우고 이름만 `assets` 로
    #   옮기면 「지문에 있었나 해설에 있었나」 가 사라진다 — 슬라이드가 전부 해설
    #   면에만 그렸고, ERD 를 보고 묻는 문항은 그림 없이 나갔다(2026-08-20 실측
    #   SQLD 2·5번: 「[주문 모델]」 한 줄만 남았다).
    #   집필 규약이 「지문의 그림은 답을 가리고, 해설의 그림은 온전하게」 이므로
    #   **어디에 있었는지가 내용**이다.
    pass_names = derive.asset_filenames_in(raw_passage) if raw_passage else []
    if pass_names:
        block["passage_assets"] = pass_names
    return block


def render_block(question: dict, previous: dict | None = None,
                 keep_speech: bool = False,
                 fields: set[str] | None = None) -> dict:
    """디스크 블록에 이번에 고친 필드만 반영한다.

    fields=None  → 전부 다시 만든다. lesson 파일에 그 블록이 없을 때만 쓴다.
    fields=set() → 아무것도 안 바꾼다. **왕복 검증이 쓰는 경로**다 —
                   "고치지 않으면 바이트가 그대로다" 를 주장하며, 도구 #2 의
                   텍스트 손질을 우리가 재현할 수 있는지는 주장하지 않는다.

    keep_speech: explanation_speech 를 디스크 값 그대로 둔다.
      ★ 실측 드리프트가 있다. m01-47 · m02-47 은 lesson 쪽 낭독문이 "…알이며…" 인데
        _rounds 는 "…알(R)이며…" 다. TTS 가 "(R)" 을 "괄호 알 괄호" 로 읽어서
        누군가 lesson 에서 손으로 고쳐 둔 것이다. 낭독문을 직접 건드리지 않았다면
        그 손질을 되돌리지 않는다.
    """
    fresh = block_from_rounds(question, previous)
    if previous is None or fields is None:
        return fresh

    block = dict(previous)                       # 키 순서·모르는 키까지 그대로
    touched = False
    for f in fields:
        for k in FIELD_TO_KEYS.get(f, ()):
            if k in fresh:
                if k not in block:
                    touched = True               # 새 키가 생겼다 → 자리를 잡아야 한다
                block[k] = fresh[k]
            elif k in block:
                # 값이 비어서 키 자체가 사라지는 경우(passage·assets)
                del block[k]
    if "explanation_speech" in fields and keep_speech:
        block["explanation_speech"] = previous.get("explanation_speech",
                                                   block.get("explanation_speech"))
    return _ordered(block) if touched else block


def _ordered(block: dict) -> dict:
    """키를 실측 순서로 정렬한다. 모르는 키는 뒤에 원래 상대순서로 남긴다.

    ★ 새로 생긴 키(지문을 처음 넣은 경우의 passage)를 dict 끝에 붙이면
      question 과 choices 사이가 아니라 tags 뒤에 앉는다. 그러면 그 파일만
      다른 순서가 되어 다음 왕복 검증이 실패한다.
    """
    canon = BLOCK_ORDER + ("assets",)
    out = {k: block[k] for k in canon if k in block}
    for k, v in block.items():
        if k not in out:
            out[k] = v
    return out


def render(doc: dict, question: dict, keep_speech: bool = False,
           fields: set[str] | None = None) -> dict:
    """문서 사본에 문항 하나를 반영한다. 원본 dict 는 건드리지 않는다.

    fields 는 이번에 실제로 고친 _rounds 필드 집합이다. 넘기지 않으면
    `set()` — 즉 아무것도 바꾸지 않는다. ★ 기본을 '전부 재생성' 으로 두면
    한 문항을 저장할 때 그 번들 10문항의 본문이 도구 #2 의 손질을 잃는다.
    """
    out = dict(doc)
    blocks = list(doc.get("blocks") or [])
    i = block_index(doc, int(question["question_no"]))
    if i < 0:
        raise ValueError(
            f"lesson 에 {question['question_no']}번 문항 블록이 없습니다. "
            f"번들과 문항 번호가 어긋났습니다."
        )
    blocks[i] = render_block(question, blocks[i], keep_speech=keep_speech,
                             fields=set() if fields is None else fields)
    out["blocks"] = blocks
    return out


def speech_drift() -> list[dict]:
    """05 lesson 의 낭독문이 _rounds 와 다른 문항 목록.

    조용히 한쪽이 이기게 하지 않는다 — 어느 문항이 갈라져 있는지 화면에 보여주고,
    사용자가 낭독문을 실제로 고칠 때만 lesson 쪽을 덮어쓴다.
    """
    from services.book import rounds
    out = []
    by_round = rounds.load_all()
    for bundle in paths.all_bundles():
        parsed = paths.parse_bundle(bundle)
        if not parsed:
            continue
        doc_r = by_round.get(paths.round_code(parsed[0]))
        if not doc_r or not os.path.isfile(paths.bundle_lesson(bundle)):
            continue
        try:
            doc_l = load(bundle)
        except (OSError, json.JSONDecodeError):
            continue
        lo, hi = paths.bundle_range(bundle)
        for qno in range(lo, hi + 1):
            q = rounds.question_of(doc_r, qno)
            i = block_index(doc_l, qno)
            if q is None or i < 0:
                continue
            disk = doc_l["blocks"][i].get("explanation_speech") or ""
            src = (q.get("explanation_speech") or "").strip()
            if disk.strip() != src:
                out.append({
                    "id": paths.qid(parsed[0], qno),
                    "bundle": bundle,
                    "lesson": disk,
                    "rounds": src,
                })
    return out


def render_text(doc: dict, bundle: str | None = None) -> str:
    """lesson 전문. 서식(indent·개행·끝개행)은 그 파일에서 되맞춘다(jsonio).

    bundle 을 주면 그 번들 파일 기준, 없으면 실측 기본값(indent=2·끝개행 없음).
    """
    if bundle:
        return jsonio.render(paths.bundle_lesson(bundle), doc)
    return jsonio.dumps(doc, *jsonio.DEFAULT)


def save(bundle: str, doc: dict) -> bool:
    """내용이 실제로 바뀐 경우에만 쓴다. 바뀌었으면 True."""
    path = paths.bundle_lesson(bundle)
    text = jsonio.render(path, doc)
    if os.path.isfile(path):
        with open(path, encoding="utf-8", newline="") as f:
            if f.read() == text:
                return False
    backup_sibling(path)
    atomic_write_text(path, text)
    return True


def question_to_block_diff(bundle: str, question: dict) -> dict | None:
    """지금 디스크의 블록과 _rounds 의 질문이 어긋난 필드를 알려준다.

    드리프트 탐지용 — 사람이 lesson 을 직접 고쳤을 수도 있다.

    ★ 텍스트 필드(question·passage·explanation)는 **정규화해서** 비교한다.
      도구 #2 가 강조 표기를 손질해 넣기 때문이다(m01 은 `**…**` → `<b>…</b>`,
      m03 은 제거). 글자 그대로 비교하면 240문항 중 상당수가 매번 '드리프트' 로
      떠서 경고가 무의미해진다 — 정말로 값이 다른 것만 보이게 한다.
    """
    try:
        doc = load(bundle)
    except (OSError, json.JSONDecodeError):
        return {"error": "lesson 파일을 읽을 수 없습니다."}
    i = block_index(doc, int(question["question_no"]))
    if i < 0:
        return {"error": f"{question['question_no']}번 블록이 없습니다."}
    cur = doc["blocks"][i]
    want = block_from_rounds(question, cur)      # 비교는 '재생성했다면' 기준으로
    diff = {}
    TEXT = ("question", "passage", "explanation", "explanation_speech")
    for k in ("question", "passage", "choices", "answer", "answer_index",
              "explanation", "explanation_speech", "difficulty", "tags", "assets"):
        a, b = cur.get(k), want.get(k)
        if k in TEXT:
            a, b = derive.normalize_emphasis(a), derive.normalize_emphasis(b)
        if a != b:
            diff[k] = {"disk": cur.get(k), "rounds": want.get(k)}
    return diff or None
