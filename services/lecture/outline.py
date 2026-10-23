# -*- coding: utf-8 -*-
"""해설 모아 노트 구조화 — 이론 요약 노트의 **앞 단계**.

    [해설 모으기]   _rounds/m??.json 의 해설을 과목별로 모은다      (모델 없음 · 즉시)
                    → 03/_outline/<key>.collect.json
    [노트 구조화]   모은 해설을 과목 → 항목 → 상세로 묶고 중복을 정돈한다 (Claude)
                    → 03/_outline/<key>.json  +  <key>.md (사람이 읽는 판)

왜 나눴나
  예전 이론 집필(`authoring/theory.py`)은 해설 모으기와 요약노트 쓰기를 **한 호출**에
  묶었다. 그래서 "어떤 개념이 몇 번 나왔고 무엇이 겹치는지" 를 사람이 보지 못한 채
  완성본이 나왔다. 구조를 먼저 꺼내 두면 목차를 사람이 검토할 수 있고, 요약노트
  집필은 그 목차를 따른다(theory.source_view 가 이 파일을 함께 넘긴다).

★ 출처는 **우리 모의고사 회차+번호**(예 m03-12)만 쓴다. 기출(01/)은 읽지 않는다 —
  요약노트에 기출 인용이 새어 나가면 안 된다는 규칙(theory.py source_view)과 같다.
★ 계층 규약: FastAPI 를 import 하지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from collections import Counter, OrderedDict
from typing import Any, Callable, Dict, List, Optional

from core.atomic_io import atomic_write_json, atomic_write_text
from services.book import paths

from .common import check_key, outline_dir, subject

_TAG = re.compile(r"<[^>]+>")


def collect_path(key: str) -> str:
    return os.path.join(outline_dir(), f"{check_key(key)}.collect.json")


def outline_path(key: str) -> str:
    return os.path.join(outline_dir(), f"{check_key(key)}.json")


def outline_md_path(key: str) -> str:
    return os.path.join(outline_dir(), f"{check_key(key)}.md")


def _rounds() -> List[Dict[str, Any]]:
    d = os.path.join(paths.book_dir(), "_rounds")
    out = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if re.fullmatch(r"m\d{2}\.json", fn):
            try:
                with open(os.path.join(d, fn), encoding="utf-8") as f:
                    doc = json.load(f) or {}
                doc.setdefault("round_code", fn[:-5])
                out.append(doc)
            except (OSError, ValueError):
                continue
    return out


def _plain(s: str) -> str:
    """해설의 그림 줄·태그를 걷어낸 글. 모델에게는 글만 준다(그림은 따로 센다)."""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s or "")
    s = re.sub(r"<svg\b.*?</svg>", "", s, flags=re.S)
    return re.sub(r"[ \t]+\n", "\n", _TAG.sub("", s)).strip()


# ── 해설 모으기 ─────────────────────────────────────────────────────────────
def collect(key: str) -> Dict[str, Any]:
    """이 과목의 해설을 모은다. 결과를 파일로 남기고 요약을 돌려준다."""
    s = subject(key)
    no = int(s["no"])
    items = []
    for d in _rounds():
        rc = d.get("round_code")
        for q in d.get("questions") or []:
            try:
                if int(q.get("subject_no") or 0) != no:
                    continue
                qn = int(q.get("question_no") or 0)
            except (TypeError, ValueError):
                continue
            exp = _plain(str(q.get("explanation") or ""))
            if not exp:
                continue
            items.append({
                "ref": f"{rc}-{qn:02d}",
                "tags": [str(t) for t in (q.get("tags") or []) if t],
                "difficulty": q.get("difficulty") or "",
                "explanation": exp,
                "has_figure": bool(q.get("assets")) or "<svg" in str(q.get("explanation") or ""),
            })
    if not items:
        raise ValueError(f"{s['no']}과목 해설이 없습니다 — _rounds/ 가 비어 있거나 과목 번호가 맞지 않습니다.")
    tags = Counter(t for it in items for t in it["tags"][:1])
    groups: "OrderedDict[str, List[str]]" = OrderedDict()
    for it in items:
        groups.setdefault((it["tags"] or ["(태그 없음)"])[0], []).append(it["ref"])
    doc = {"key": key, "subject_no": no, "subject": s["name"],
           "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "n": len(items), "rounds": len({i["ref"].split("-")[0] for i in items}),
           "chars": sum(len(i["explanation"]) for i in items),
           "top_tags": tags.most_common(40),
           "groups": [{"tag": t, "refs": r} for t, r in groups.items()],
           "items": items}
    os.makedirs(outline_dir(), exist_ok=True)
    atomic_write_json(collect_path(key), doc, indent=1)
    return summary(key)


def summary(key: str) -> Dict[str, Any]:
    """화면용 요약 — 모은 것·구조화한 것의 개수만."""
    out: Dict[str, Any] = {"key": key, "collected": None, "outline": None}
    try:
        with open(collect_path(key), encoding="utf-8") as f:
            c = json.load(f)
        out["collected"] = {k: c[k] for k in ("n", "rounds", "chars", "collected_at")}
        out["collected"]["top_tags"] = c.get("top_tags", [])[:12]
    except (OSError, ValueError, KeyError):
        pass
    try:
        with open(outline_path(key), encoding="utf-8") as f:
            o = json.load(f)
        topics = o.get("topics") or []
        out["outline"] = {"topics": len(topics),
                          "items": sum(len(t.get("items") or []) for t in topics),
                          "refs": len({r for t in topics for i in t.get("items") or []
                                       for r in i.get("refs") or []}),
                          "made_at": o.get("made_at"), "cost_usd": o.get("cost_usd"),
                          "approved": bool(o.get("approved"))}
    except (OSError, ValueError):
        pass
    return out


def read_outline(key: str) -> Optional[Dict[str, Any]]:
    try:
        with open(outline_path(key), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ── 노트 구조화 (Claude) ────────────────────────────────────────────────────
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["topics"],
    "properties": {"topics": {"type": "array", "minItems": 2, "items": {
        "type": "object", "additionalProperties": False, "required": ["title", "items"],
        "properties": {
            "title": {"type": "string"},
            "items": {"type": "array", "minItems": 1, "items": {
                "type": "object", "additionalProperties": False,
                "required": ["title", "points", "refs"],
                "properties": {
                    "title": {"type": "string"},
                    "points": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "refs": {"type": "array", "items": {"type": "string"}},
                    "traps": {"type": "array", "items": {"type": "string"}},
                }}},
        }}}},
}

SYSTEM = """당신은 자격시험 문제집의 이론 노트 편집자다. 우리 모의고사 해설을 모아
과목 → 항목 → 상세의 노트 구조로 정돈한다. 새 사실을 지어내지 않는다 — 해설에 있는 것만 쓴다."""


def _prompt(s: Dict[str, Any], c: Dict[str, Any]) -> str:
    return f"""■ 이번 과목: {s['no']}과목 · {s['name']}
■ 읽을 파일: collect.json (cwd 에 이것뿐이다) — 이 과목 해설 {c['n']}개, {c['rounds']}개 회차.
  items[].ref 가 출처(회차-번호), tags 가 집필 때 붙인 개념 태그다.

■ 할 일
1. 해설을 개념별로 묶는다. topics = 대단원(h2), items = 소단원(h3) 이 된다.
   대단원 6~12개, 대단원당 소단원 3~12개를 기준으로 하되 해설이 말하는 만큼만 만든다.
2. 순서: 정의 → 구분·비교 → 계산·적용 → 함정. 시험 범위의 흐름대로 대단원을 놓는다.
3. points: 그 소단원에서 수험생이 알아야 할 사실을 짧은 문장으로(2~6개). 여러 해설이 같은
   말을 하면 하나로 합친다(중복 정돈). 해설끼리 어긋나면 더 정확한 쪽을 쓰고 traps 에 적는다.
4. refs: 그 소단원의 근거가 된 해설의 ref 를 **전부** 적는다. 모든 ref 가 어딘가에 들어가야 한다.
5. traps: 해설에 나온 오답 함정(헷갈리는 쌍, '항상'·'반드시' 같은 말)을 짧게.
6. 기출·외부 자료를 인용하지 않는다. 출처는 ref 뿐이다.
"""


def structure(key: str, *, log: Callable[[str], None] = lambda s: None,
              model: str = "", effort: Optional[str] = None) -> Dict[str, Any]:
    from services.authoring.provider import ClaudeAuthor

    s = subject(key)
    if not os.path.isfile(collect_path(key)):
        collect(key)
    with open(collect_path(key), encoding="utf-8") as f:
        c = json.load(f)
    view = tempfile.mkdtemp(prefix="outline-src-")
    try:
        # 모델이 읽을 것은 이 한 파일뿐 — 01/(기출)에 상대경로로 닿지 않는다.
        shutil.copyfile(collect_path(key), os.path.join(view, "collect.json"))
        author = ClaudeAuthor(cwd=view, model=model, effort=effort, on_activity=log)
        log(f"[{key}] 해설 {c['n']}개를 구조화합니다")
        got = author.structured(SYSTEM, _prompt(s, c), SCHEMA)
    finally:
        shutil.rmtree(view, ignore_errors=True)

    all_refs = {i["ref"] for i in c["items"]}
    used = {r for t in got["topics"] for i in t["items"] for r in i.get("refs") or []}
    missing = sorted(all_refs - used)
    unknown = sorted(used - all_refs)
    doc = {"key": key, "subject_no": s["no"], "subject": s["name"],
           "made_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "cost_usd": round(author.last_cost_usd, 4),
           "approved": False, "missing_refs": missing, "unknown_refs": unknown,
           "topics": got["topics"]}
    atomic_write_json(outline_path(key), doc, indent=1)
    atomic_write_text(outline_md_path(key), to_markdown(doc))
    if missing:
        log(f"[{key}] (주의) 어느 항목에도 안 들어간 해설 {len(missing)}개: {', '.join(missing[:12])}")
    if unknown:
        log(f"[{key}] (주의) 없는 출처를 적었습니다: {', '.join(unknown[:12])}")
    log(f"[{key}] 대단원 {len(doc['topics'])}개 · 소단원 "
        f"{sum(len(t['items']) for t in doc['topics'])}개 · ${doc['cost_usd']:.3f}")
    return doc


def to_markdown(doc: Dict[str, Any]) -> str:
    out = [f"# {doc['subject_no']}과목 · {doc['subject']} — 노트 구조", ""]
    for i, t in enumerate(doc["topics"], 1):
        out.append(f"## {i}. {t['title']}")
        for j, it in enumerate(t["items"], 1):
            out.append(f"### {i}.{j}. {it['title']}")
            out += [f"- {p}" for p in it["points"]]
            for tr in it.get("traps") or []:
                out.append(f"- ⚠ {tr}")
            if it.get("refs"):
                out.append(f"> 출처: {' · '.join(it['refs'])}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def approve(key: str, on: bool = True) -> Dict[str, Any]:
    doc = read_outline(key)
    if not doc:
        raise ValueError("구조화한 노트가 없습니다.")
    doc["approved"] = bool(on)
    atomic_write_json(outline_path(key), doc, indent=1)
    return summary(key)
