# -*- coding: utf-8 -*-
"""용어 사전 — `vendor/chodangi/config/pronunciation_map.yaml` 을 앱에서 고친다.

**왜 앱에 붙이나.** 이 파일이 발음 고침의 **1차 자리**다. 한 줄 넣으면 72번들 전부에
걸리고 자막은 원문을 유지한다(엔진이 합성 직전에만 치환한다). 씬마다 손으로 고치는
것보다 훨씬 싸다 — 그런데 지금까지 앱에 입구가 없어서 파일을 직접 열어야 했다.

★ **헤더 주석을 보존한다.** 파일 머리에 동작 규칙이 적혀 있다(단어 경계·자막 미적용
  같은 것들). 통째로 다시 쓰면서 그것을 날리면 다음 사람이 규칙을 모른다.

★ 엔진은 이 파일을 **핫리로드**한다. 저장하면 다음 합성부터 바로 걸린다 —
  서버를 다시 띄울 필요가 없다.

★ 사전에 **없는** 대문자 약어는 엔진이 낱자로 음역한다(`spell_unknown_acronyms`).
  `MAE`→「엠에이이」처럼 맞는 것도 있지만 `CRISP`→「씨알아이에스피」처럼 틀리는 것도
  있다. `candidates()` 가 낭독문을 훑어 그 목록을 빈도와 함께 낸다 — 빈 화면을 주고
  "알아서 채우세요" 하지 않으려는 것이다.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re

from core.atomic_io import CRLF, LF, atomic_write_text, file_newline
from core.constants import ENGINE_DIR
from services.book import paths

MAP_PATH = os.path.join(ENGINE_DIR, "config", "pronunciation_map.yaml")

# 엔진의 판정과 **같아야 한다** — `voicewright/pronunciation.py` 의 `_ACRONYM_RE`.
_ACRONYM_RE = re.compile(r"(?<![A-Za-z])[A-Z]{2,}(?![A-Za-z])")
_LETTER = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프",
    "G": "지", "H": "에이치", "I": "아이", "J": "제이", "K": "케이", "L": "엘",
    "M": "엠", "N": "엔", "O": "오", "P": "피", "Q": "큐", "R": "알",
    "S": "에스", "T": "티", "U": "유", "V": "브이", "W": "더블유",
    "X": "엑스", "Y": "와이", "Z": "제트",
}

_DEFAULT_HEADER = """# voicewright 발음 사전
#
# 합성 직전에 텍스트의 약자·외래어를 한국어 발음으로 자동 치환합니다.
#
#   - 단어 경계 매칭 — 앞뒤에 라틴 글자가 붙지 않은 것만 잡는다
#   - SRT 자막에는 적용되지 않음 (자막에는 항상 원본 텍스트가 들어감)
#   - 새 항목 추가 후엔 즉시 반영 (서버 재시작 불필요)
"""


def spelled(word: str) -> str:
    """사전에 없을 때 엔진이 내는 소리 — 낱자 음역."""
    return "".join(_LETTER.get(c, c) for c in word)


def _split(raw: str) -> tuple[str, dict]:
    """(헤더 주석, rules). `rules:` 첫 줄을 경계로 가른다."""
    import yaml
    lines = raw.splitlines(keepends=True)
    idx = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("rules:")), None)
    header = ("".join(lines[:idx]).rstrip() + "\n") if idx is not None else ""
    if not header.strip():
        header = _DEFAULT_HEADER
    try:
        rules = (yaml.safe_load(raw) or {}).get("rules") or {}
    except Exception:                     # noqa: BLE001 — 깨진 파일은 빈 dict 로 읽고 알린다
        return header, {}
    return header, {str(k): str(v) for k, v in rules.items()}


def read() -> dict:
    if not os.path.isfile(MAP_PATH):
        return {"exists": False, "path": MAP_PATH, "rules": {}, "count": 0}
    raw = open(MAP_PATH, encoding="utf-8").read()
    header, rules = _split(raw)
    ok = bool(rules) or "rules:" not in raw
    return {"exists": True, "path": MAP_PATH, "rules": rules, "count": len(rules),
            "header_lines": len(header.splitlines()),
            "error": "" if ok else "rules 를 읽지 못했습니다 — YAML 이 깨졌는지 보세요."}


def _write(header: str, rules: dict) -> None:
    """키 정렬 순서로 다시 쓴다. 헤더는 그대로 얹는다.

    ★ 원자적으로 쓴다 — 이 파일이 깨지면 **전 품목의 발음이 통째로 사라진다**
      (엔진은 로드 실패 시 규칙 0개로 조용히 계속 돈다).
    """
    def q(s: str) -> str:
        s = str(s)
        # YAML 이 특수하게 읽는 첫 글자·구두점이 있으면 따옴표로 감싼다
        return json.dumps(s, ensure_ascii=False) if re.search(r"^[\s#&*!|>%@`\[\]{}-]|[:#]", s) else s

    body = "".join(f"  {q(k)}: {q(rules[k])}\n" for k in sorted(rules))
    text = header.rstrip("\n") + "\n\nrules:\n" + body
    # ★ 개행은 **그 파일이 쓰던 것을 그대로** 쓴다. 이 PC 의 이 파일은 CRLF 이고
    #   `core.autocrlf=true` 라, LF 로 내려쓰면 내용이 같아도 git 이 통째로
    #   "변경됨" 으로 본다(실측 — 사전을 안 고쳤는데 M 으로 떴다).
    #   개행을 정하는 것은 호출자의 일이다(`atomic_write_text` 는 문자열 그대로 쓴다).
    nl = file_newline(MAP_PATH) or CRLF
    atomic_write_text(MAP_PATH, text.replace("\n", nl) if nl != LF else text)


def save(key: str, value: str) -> dict:
    k, v = (key or "").strip(), (value or "").strip()
    if not k:
        raise ValueError("용어가 비어 있습니다.")
    if not v:
        raise ValueError("읽는 소리가 비어 있습니다 — 지우려면 [빼기] 를 쓰세요.")
    raw = open(MAP_PATH, encoding="utf-8").read() if os.path.isfile(MAP_PATH) else ""
    header, rules = _split(raw)
    if raw and not rules:
        raise ValueError("사전을 읽지 못했습니다 — 덮어쓰지 않았습니다. YAML 을 확인하세요.")
    was = rules.get(k)
    rules[k] = v
    _write(header, rules)
    return {"key": k, "value": v, "was": was, "count": len(rules)}


def remove(key: str) -> dict:
    k = (key or "").strip()
    raw = open(MAP_PATH, encoding="utf-8").read() if os.path.isfile(MAP_PATH) else ""
    header, rules = _split(raw)
    if k not in rules:
        raise ValueError(f"사전에 없습니다: {k}")
    was = rules.pop(k)
    _write(header, rules)
    return {"key": k, "was": was, "removed": True, "count": len(rules)}


# ── 품목 사전 (`exams/<pd>.json` 의 `speech_dict`) ─────────────────────────
#
# ★ 왜 여기 같이 두나(2026-08-26). 사전이 **넷**인데 화면에는 공용 하나만 나왔다.
#   `DENSE_RANK` 를 고치려고 이 박스를 열었는데 없어서 못 찾으셨다 — 그것은 품목
#   사전에 있다. 어디에 무엇이 있는지 사람이 외워야 하면 화면이 잘못된 것이다.
#
# ★ 두 사전은 **거는 때가 다르다.**
#     품목 사전 : `bake` 가 대본을 쓸 때 — 대본에 한글로 박힌다. 화면에도 보인다.
#     공용 사전 : 엔진이 합성 직전에 — 대본은 로마자 그대로고 소리만 바뀐다.
#   그래서 품목 사전이 먼저 바꾼 낱말은 **공용 사전에 걸리지 않는다.** 대본에
#   로마자가 안 남기 때문이다. 고칠 자리를 고를 때 이것이 갈림길이다.

def read_product() -> dict:
    """지금 작업 폴더가 쓰는 품목의 `speech_dict`. 없으면 빈 것.

    ★ 품목은 **폴더가 정한다**(`parts.active()` — `_book.json` 의 `pd`). 화면에서
      고른 것이 아니다. 파일은 `exams/<id>.json` 이고 YAML 이 아니라 JSON 이다.
    """
    try:
        from services.authoring import examspec, parts
        eid = str((parts.active() or {}).get("id") or "")
        path = examspec.path_of(eid) if eid else ""
        # ★ **파일을 곧바로 읽는다.** `parts.active()` 는 `_book.json` mtime 으로
        #   캐시돼서, 시험정보만 고치면 옛 값을 돌려준다 — 화면이 방금 넣은 항목을
        #   못 보여 주는 일이 그래서 생긴다.
        spec = examspec.load(eid) if eid else {}
    except Exception:                                        # noqa: BLE001
        spec, eid, path = {}, "", ""
    rules = {str(k): str(v) for k, v in (spec.get("speech_dict") or {}).items()}
    return {"rules": rules, "count": len(rules), "pd": eid,
            "label": str(spec.get("label") or eid), "path": path,
            "exists": bool(path and os.path.isfile(path))}


def _write_product(rules: dict) -> None:
    """`exams/<pd>.json` 의 `speech_dict` 블록만 바꿔 쓴다.

    ★ 파일 전체를 `json.dump` 로 다시 쓰지 않는다 — 키 순서와 들여쓰기가 그 파일의
      읽기 순서다. 블록만 갈아 끼우고, 깨진 것은 쓰지 않는다.
    """
    d = read_product()
    if not d["path"]:
        raise ValueError("지금 품목을 알 수 없습니다 — exams/<pd>.json 을 못 찾았습니다.")
    p = d["path"]
    raw = open(p, encoding="utf-8").read()
    nl = chr(10)
    lines = ["    %s: %s" % (json.dumps(k, ensure_ascii=False),
                             json.dumps(rules[k], ensure_ascii=False)) for k in rules]
    head, tail = '  "speech_dict": {', '  },'
    block = head + nl + ("," + nl).join(lines) + nl + tail
    if '"speech_dict"' in raw:
        i = raw.index(head)
        j = raw.index(nl + tail, i) + len(nl + tail)
        raw = raw[:i] + block + raw[j:]
    else:                                    # 없으면 맨 앞 키 앞에 넣는다
        i = raw.index("{") + 1
        raw = raw[:i] + nl + block + raw[i:]
    json.loads(raw)                          # 깨진 것을 쓰지 않는다
    atomic_write_text(p, raw)
    # ★ 캐시를 버린다 — 안 버리면 다음 굽기가 옛 사전을 쓴다.
    try:
        from services.authoring import parts
        parts.invalidate()
    except Exception:                                        # noqa: BLE001
        pass


def save_product(key: str, value: str) -> dict:
    k, v = (key or "").strip(), (value or "").strip()
    if not k:
        raise ValueError("용어가 비어 있습니다.")
    if not v:
        raise ValueError("읽는 소리가 비어 있습니다 — 지우려면 [빼기] 를 쓰세요.")
    d = read_product()
    rules = d["rules"]
    was = rules.get(k)
    rules[k] = v
    _write_product(rules)
    return {"key": k, "value": v, "was": was, "count": len(rules), "scope": "product"}


def remove_product(key: str) -> dict:
    k = (key or "").strip()
    d = read_product()
    rules = d["rules"]
    if k not in rules:
        raise ValueError(f"품목 사전에 없습니다: {k}")
    was = rules.pop(k)
    _write_product(rules)
    return {"key": k, "was": was, "removed": True, "count": len(rules), "scope": "product"}


def merged_rules() -> dict:
    """공용 + 품목 — 품목이 이긴다. 강의 노트의 ② 낭독대본이 이것으로 발음을 바꾼다
    (발음대본을 이 앱에서 끝내려면 사전이 data-read 글자에 **들어가야** 한다 — 하류
    렌더러는 그 글을 그대로 읽는다)."""
    out = dict(read().get("rules") or {})
    out.update(read_product().get("rules") or {})
    return out


# 강의 노트는 대소문자가 섞인 영문도 많다(Quick-Win · EdTech · Long Term View).
_LATIN_RE = re.compile(r"(?<![A-Za-z])[A-Za-z][A-Za-z0-9&+.-]*[A-Za-z0-9](?![A-Za-z])")


def candidates(prefix: str = "", notes: bool = False) -> list[dict]:
    """낭독문에 있는데 **사전에 없는** 대문자 약어. 빈도가 큰 것부터.

    `prefix` 로 회차를 좁힌다(`m01` → 1회 8번들).
    ★ v2: 품목 사전에 있는 것도 뺀다(전에는 공용만 봤다). `notes` 면 요약반·종합반
      강의 노트의 자막도 훑는다 — 대소문자 섞인 영문까지.
    """
    rules = merged_rules()
    hits: collections.Counter[str] = collections.Counter()
    where: dict[str, str] = {}
    pat = os.path.join(paths.book_dir(), "05", (prefix or "") + "*",
                       "script", "*_script.json")
    for sp in sorted(glob.glob(pat)):
        try:
            doc = json.load(open(sp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        bundle = os.path.basename(os.path.dirname(os.path.dirname(sp)))
        for s in doc.get("scenes") or []:
            # ★ **자막**(narration)을 본다. 발음(narration_text)에는 이미 손이 닿아
            #   있어서, 고친 것을 다시 후보로 올리게 된다.
            t = s.get("narration") or ""
            for m in _ACRONYM_RE.finditer(t):
                w = m.group(0)
                if w in rules:
                    continue
                hits[w] += 1
                where.setdefault(w, f"{bundle} 씬{s.get('scene')} … "
                                    + t[max(0, m.start() - 20):m.start() + len(w) + 12])
    if notes:
        for kind, folder in (("summary", "03-2"), ("full", "03-3")):
            for jp in sorted(glob.glob(os.path.join(paths.book_dir(), folder, "*.json"))):
                try:
                    doc = json.load(open(jp, encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                for sec in doc.get("sections") or []:
                    for sl in sec.get("slides") or []:
                        t = sl.get("say") or ""
                        for m in _LATIN_RE.finditer(t):
                            w = m.group(0).strip(".-")
                            if len(w) < 2 or w in rules or w.lower() in ("vs", "etc"):
                                continue
                            hits[w] += 1
                            where.setdefault(w, f"{'요약반' if kind == 'summary' else '종합반'} {sl.get('id')} … "
                                                + t[max(0, m.start() - 20):m.start() + len(w) + 12])
    return [{"term": w, "count": n, "now": spelled(w.upper()) if w.isupper() else "(그대로 읽힘)",
             "where": where[w]} for w, n in hits.most_common()]
