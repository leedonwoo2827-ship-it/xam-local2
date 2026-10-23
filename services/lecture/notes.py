# -*- coding: utf-8 -*-
"""강의 노트 원천 JSON · 요약노트 파싱 · 원고 HTML 굽기.

원천은 `03-2/<key>.json`(요약반) · `03-3/<key>.json`(종합반) 이다. 화면이 고치는 것도,
단계(①자막 ②낭독 ③SVG ④n배)가 채우는 것도 이 JSON 이고, 원고 HTML 은 [노트 빌드] 가
여기서 다시 굽는다 — HTML 을 직접 고치면 다음 빌드가 덮는다.

    {kind, key, subject_no, subject, title, factor?, source_hash,
     h1: {say, read, outro_say, outro_read},
     sections: [{title, slides: [{id, title, qref, body, say, read, fig, base?}]}],
     stages: {say|read|fig|expand|build|listen: {status, at, cost_usd, note}}}

    slide.body  요약노트의 그 h3 밑 HTML(p·ul·table·svg) — 화면에 보이는 몸통
    slide.fig   ③ 이 새로 붙인 SVG(몸통에 표·그림이 없을 때만)
    slide.base  종합반의 늘린 장이 어느 장에서 나왔는지(q1-01-03-b → q1-01-03)

원고 HTML 규약은 lecture-composer 의 「원고 HTML 속성」 표를 그대로 따른다
(h1 data-say/read/outro, h3 data-id/say/read). 그래야 그 엔진과 하류 렌더러(hyper-close-frame 등)가 손대지
않고 받는다.

★ 계층 규약: FastAPI 를 import 하지 않는다.
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_json, atomic_write_text, backup_sibling
from services.book import paths

from .common import (DEFAULT_FACTOR, KINDS, check_kind, doc_path, h, html_path,
                     subject)

# 단계 순서 — 종류마다 다르다. 사람 승인이 필요한 단계는 HUMAN 에.
STAGES = {
    "summary": ["say", "read", "fig", "build", "listen"],
    "full": ["expand", "read", "fig", "build", "listen"],
}
STAGE_LABEL = {"say": "자막대본", "read": "낭독대본", "fig": "SVG 추가 슬라이드",
               "expand": "내용 n배 확장", "build": "노트 빌드", "listen": "듣기 검수"}
HUMAN = {"say", "read", "fig", "expand", "listen"}

_H = re.compile(r"<(h[123])\b[^>]*>(.*?)</\1>", re.S)
_QREF = re.compile(r"<label\b[^>]*class=\"q\"[^>]*>.*?</label>", re.S)
_TAG = re.compile(r"<[^>]+>")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def text_of(frag: str) -> str:
    return _html.unescape(_TAG.sub("", _QREF.sub("", frag or ""))).strip()


def has_visual(slide: Dict[str, Any]) -> bool:
    """이 장에 표나 그림이 이미 있는가 — 「장마다 표 아니면 그림 하나」 규약."""
    b = (slide.get("body") or "") + (slide.get("fig") or "")
    return "<svg" in b or "<table" in b or "<img" in b


# ── 요약노트 → 요약반 뼈대 ──────────────────────────────────────────────────
def parse_summary(key: str) -> Dict[str, Any]:
    """`03/summary_<key>.html` 을 h2(대단원) / h3(한 장) 로 자른다.

    ★ 출제이력 배지(label.q)는 버리지 않고 qref 로 따로 둔다. 원고 HTML 에 그대로
      다시 붙인다 — lecture-composer 실물도 h3 안에 그 배지를 달고 있다.
    """
    src = paths.summary_html(key)
    if not os.path.isfile(src):
        raise ValueError("이론 요약 노트가 아직 없습니다 — 먼저 [이론 요약 노트] 를 만드세요.")
    with open(src, encoding="utf-8") as f:
        raw = f.read()
    # ★ style·script·주석을 **먼저** 걷는다. 요약노트의 CSS 주석에 `<style>`·`<body>`·
    #   `<h3>` 라는 글자가 그대로 적혀 있어서, 걷기 전에 body 를 찾으면 주석 한가운데서
    #   본문이 시작되고 「h3 안에 넣어도 된다」 가 첫 장이 된다(adsp 1과목 실측 2026-10-24).
    body = re.sub(r"<(style|script)\b.*?</\1>|<!--.*?-->", "", raw, flags=re.S)
    m = re.search(r"<body\b[^>]*>(.*)</body>", body, re.S)
    if m:
        body = m.group(1)
    s = subject(key)
    title = ""
    sections: List[Dict[str, Any]] = []
    marks = list(_H.finditer(body))
    for i, mm in enumerate(marks):
        tag, inner = mm.group(1), mm.group(2)
        tail = body[mm.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        if tag == "h1":
            title = text_of(inner)
        elif tag == "h2":
            sections.append({"title": re.sub(r"^\s*\d+\.\s*", "", text_of(inner)), "slides": []})
        else:
            if not sections:
                sections.append({"title": title or s["name"], "slides": []})
            sec = sections[-1]
            q = _QREF.search(inner)
            sid = f"q{s['no']}-{len(sections):02d}-{len(sec['slides']) + 1:02d}"
            sec["slides"].append({
                "id": sid,
                "title": re.sub(r"^\s*[\d.]+\.?\s*", "", text_of(inner)),
                "qref": q.group(0) if q else "",
                "body": tail.strip(),
                "say": "", "read": "", "fig": "",
            })
    if not any(sec["slides"] for sec in sections):
        raise ValueError("요약노트에서 h3(장)을 찾지 못했습니다.")
    return {"kind": "summary", "key": key, "subject_no": s["no"], "subject": s["name"],
            "title": title or f"{s['no']}과목 · {s['name']}",
            "source_hash": h(raw), "created_at": _now(),
            "h1": {"say": "", "read": "", "outro_say": "", "outro_read": ""},
            "sections": sections, "stages": {}}


def from_summary_note(key: str, factor: int) -> Dict[str, Any]:
    """종합반 뼈대 = **승인된 요약반 노트**의 사본. ④ 가 여기에 장을 늘린다."""
    base = load("summary", key)
    if not base:
        raise ValueError("요약반 강의 노트가 없습니다 — 요약반부터 만드세요.")
    for st in ("say", "read", "fig"):
        if (base.get("stages") or {}).get(st, {}).get("status") != "approved":
            raise ValueError(f"요약반 노트의 「{STAGE_LABEL[st]}」 가 아직 승인되지 않았습니다.")
    doc = json.loads(json.dumps(base))
    doc.update(kind="full", factor=int(factor), created_at=_now(), stages={},
               source_hash=h(json.dumps(base["sections"], ensure_ascii=False)))
    for sec in doc["sections"]:
        for sl in sec["slides"]:
            sl["base"] = sl["id"]
    return doc


# ── 읽기 · 쓰기 ─────────────────────────────────────────────────────────────
def load(kind: str, key: str) -> Optional[Dict[str, Any]]:
    try:
        with open(doc_path(kind, key), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save(doc: Dict[str, Any]) -> None:
    p = doc_path(doc["kind"], doc["key"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if os.path.isfile(p):
        backup_sibling(p)
    doc["updated_at"] = _now()
    atomic_write_json(p, doc, indent=1)


def init(kind: str, key: str, *, factor: int = DEFAULT_FACTOR, redo: bool = False) -> Dict[str, Any]:
    check_kind(kind)
    if load(kind, key) and not redo:
        raise ValueError("이미 노트가 있습니다. 처음부터 다시 만들려면 redo 를 켜세요(지금 것은 .bak 로 남습니다).")
    doc = parse_summary(key) if kind == "summary" else from_summary_note(key, factor)
    save(doc)
    return doc


def slides(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [sl for sec in doc["sections"] for sl in sec["slides"]]


def find(doc: Dict[str, Any], sid: str) -> Dict[str, Any]:
    for sl in slides(doc):
        if sl["id"] == sid:
            return sl
    raise KeyError(sid)


def spoken(sl: Dict[str, Any]) -> str:
    """TTS 에 넣을 글 — 낭독이 있으면 낭독, 없으면 자막(뜻이 같고 소리도 같을 때)."""
    return (sl.get("read") or sl.get("say") or "").strip()


def set_stage(doc: Dict[str, Any], stage: str, status: str, **extra) -> None:
    st = doc.setdefault("stages", {}).setdefault(stage, {})
    st.update(status=status, at=_now(), **extra)


def stage_view(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """단계표 — 앞 단계가 승인돼야 다음 단계가 열린다."""
    out, open_ = [], True
    for st in STAGES[doc["kind"]]:
        cur = dict((doc.get("stages") or {}).get(st) or {})
        status = cur.get("status") or "todo"
        out.append({"stage": st, "label": STAGE_LABEL[st] if st != "expand"
                    else f"내용 {doc.get('factor', DEFAULT_FACTOR)}배 확장",
                    "human": st in HUMAN, "status": status, "open": open_,
                    "at": cur.get("at"), "cost_usd": cur.get("cost_usd"), "note": cur.get("note")})
        done = status == "approved" or (st == "build" and status == "done")
        open_ = open_ and done
    return out


def edit_slide(doc: Dict[str, Any], sid: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """사람이 고친 장. 고친 칸에 따라 그 단계의 승인을 '다시 볼 것' 으로 되돌린다."""
    sl = find(doc, sid)
    touched = []
    for k in ("say", "read", "fig", "title", "body"):
        if k in fields and fields[k] is not None and fields[k] != sl.get(k):
            sl[k] = str(fields[k])
            touched.append(k)
    if "say" in touched and "read" not in touched:
        # 자막이 바뀌면 그 장의 낭독은 다시 봐야 한다 — 상태판이 「② 낭독 다시」 로 띄운다.
        sl["read_done"] = False
    sl["edited_at"] = _now()
    return {"slide": sl, "touched": touched}


def content_hash(doc: Dict[str, Any]) -> str:
    """빌드 뒤에 원고가 바뀌었는지 — 장 내용과 여는 말만 본다(단계 기록은 빼고)."""
    return h(json.dumps([doc.get("h1"), doc.get("sections")], ensure_ascii=False, sort_keys=True))


def source_now(doc: Dict[str, Any]) -> str:
    """이 노트를 만든 원천의 **지금** 해시 — 만들 때의 source_hash 와 다르면 원천이 바뀐 것."""
    if doc["kind"] == "summary":
        try:
            with open(paths.summary_html(doc["key"]), encoding="utf-8") as f:
                return h(f.read())
        except OSError:
            return ""
    base = load("summary", doc["key"])
    return h(json.dumps(base["sections"], ensure_ascii=False)) if base else ""


# ── 원고 HTML ───────────────────────────────────────────────────────────────
_CSS = """body{font-family:Pretendard,"Malgun Gothic",sans-serif;max-width:860px;margin:32px auto;padding:0 20px;line-height:1.7;color:#1b1f19}
h1{font-size:26px}h2{font-size:21px;margin-top:2.2em;border-bottom:2px solid #e4e4d7;padding-bottom:.3em}
h3{font-size:17px;margin-top:1.8em}h3[data-base]{color:#5a4a20}
table{border-collapse:collapse;margin:.6em 0}td,th{border:1px solid #d8d8cc;padding:4px 8px}
.q{display:inline;margin-left:7px;font-size:.78em;font-weight:700;color:#94A3B8;background:#F1F5F9;border:1px solid #E2E8F0;border-radius:999px;padding:1px 8px}
.q>input{position:absolute;opacity:0;width:0;height:0}.q>.qn{display:none}.q>input:checked~.qn{display:inline;margin-left:6px;font-weight:400}
svg,img{max-height:240px;width:auto;max-width:100%;height:auto;display:block;margin:12px auto 10px}
*{max-width:100%}body{overflow-x:hidden;overflow-wrap:anywhere}"""


def _attr(v: str) -> str:
    return _html.escape(v or "", quote=True)


def render_html(doc: Dict[str, Any]) -> str:
    kind = doc["kind"]
    n_slides = len(slides(doc))
    says = sum(len(sl.get("say") or "") for sl in slides(doc))
    head = [
        "<!DOCTYPE html>", '<html lang="ko">', "<head>", '<meta charset="utf-8">',
        f"<title>{_html.escape(doc['title'])}</title>",
        f'<meta name="lecture" content="{doc["subject_no"]}과목 · {n_slides}장 · data-say {says}자">',
        "<!--",
        f"  {'요약반' if kind == 'summary' else '종합반'} 강의 원고 — XAM LOCAL v2 가 원천 JSON 에서 구웠다."
        " 이 파일을 직접 고치지 말 것(다음 빌드가 덮는다).",
        "  h3 하나 = 슬라이드 한 판. 그 밑의 p·li·table·svg 가 그 판의 몸통이다.",
        "  h3 의 data-say 가 그 장의 대본(자막), data-read 가 TTS 에 넣을 발음(다를 때만).",
        "-->", f"<style>{_CSS}</style>", "</head>", "<body>",
    ]
    h1 = doc.get("h1") or {}
    attrs = []
    for k, a in (("say", "data-say"), ("read", "data-read"),
                 ("outro_say", "data-outro-say"), ("outro_read", "data-outro-read")):
        if h1.get(k):
            attrs.append(f'\n    {a}="{_attr(h1[k])}"')
    out = head + [f"<h1{''.join(attrs)}>{_html.escape(doc['title'])}</h1>"]
    for i, sec in enumerate(doc["sections"], 1):
        out.append(f"<h2>{i}. {_html.escape(sec['title'])}</h2>")
        for sl in sec["slides"]:
            a = [f'data-id="{_attr(sl["id"])}"']
            if sl.get("say"):
                a.append(f'data-say="{_attr(sl["say"])}"')
            if sl.get("read") and sl["read"] != sl.get("say"):
                a.append(f'data-read="{_attr(sl["read"])}"')
            if sl.get("base") and sl["base"] != sl["id"]:
                a.append(f'data-base="{_attr(sl["base"])}"')
            out.append(f"<h3 {chr(10).join('    ' + x if j else x for j, x in enumerate(a))}>"
                       f"{_html.escape(sl['title'])}{sl.get('qref') or ''}</h3>")
            if sl.get("body"):
                out.append(sl["body"])
            if sl.get("fig"):
                out.append(sl["fig"])
    out += ["</body>", "</html>", ""]
    return "\n".join(out)


def write_html(doc: Dict[str, Any]) -> str:
    p = html_path(doc["kind"], doc["key"], int(doc.get("factor") or DEFAULT_FACTOR))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write_text(p, render_html(doc))
    return p


def overview(kind: str) -> List[Dict[str, Any]]:
    """화면 목록 — 과목마다 노트가 있는지, 몇 장인지, 단계가 어디까지 왔는지."""
    from .common import subjects

    out = []
    for s in subjects():
        d = load(kind, s["key"])
        row = {**s, "exists": bool(d), "summary_ready": os.path.isfile(paths.summary_html(s["key"]))}
        if d:
            sl = slides(d)
            row.update(slides=len(sl), say=sum(1 for x in sl if x.get("say")),
                       read=sum(1 for x in sl if x.get("read")),
                       visual=sum(1 for x in sl if has_visual(x)),
                       stages=stage_view(d), factor=d.get("factor"))
        out.append(row)
    return out


KIND_LABEL = {k: v[1] for k, v in KINDS.items()}
