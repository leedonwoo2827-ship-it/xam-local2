# -*- coding: utf-8 -*-
"""강의 노트 단계 실행 — ①자막 ②낭독 ③SVG ④n배 (Claude) · 노트 빌드 (결정론).

★ 호출 단위는 **대단원(h2) 하나**다. 장 하나씩 부르면 호출당 하네스 접두 비용($0.25,
  provider.py 머리말)이 장 수만큼 붙고, 과목 통째로 부르면 출력 상한에 잘린다.
  대단원은 장 3~12개라 그 사이다. 대단원이 끝날 때마다 저장하므로 끊겨도 이어서 돈다
  (이미 채운 장은 건너뛴다 — redo 를 켜면 다시 쓴다).
★ 모델은 파일을 쓰지 않는다. 받은 dict 를 여기서 검사한 뒤 원천 JSON 에 넣는다.
★ 계층 규약: FastAPI 를 import 하지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

from core.atomic_io import atomic_write_json, atomic_write_text
from services.book import paths

from . import notes as N
from .common import DEFAULT_FACTOR, kind_dir

Log = Callable[[str], None]
_TAG = re.compile(r"<[^>]+>")


def _plain_body(html: str, keep_svg: bool = False) -> str:
    """모델에게 보여 줄 몸통 — 그림은 '[그림: aria-label]' 한 줄로 줄인다(토큰 절약)."""
    s = html or ""
    if not keep_svg:
        s = re.sub(r"<svg\b[^>]*?(?:aria-label=\"([^\"]*)\")?[^>]*>.*?</svg>",
                   lambda m: f"[그림: {m.group(1) or '도식'}]", s, flags=re.S)
    s = re.sub(r"</(p|li|tr|h\d)>", "\n", s)
    s = re.sub(r"<(td|th)\b[^>]*>", " | ", s)
    return re.sub(r"\n{3,}", "\n\n", _TAG.sub("", s)).strip()


def _exam_label() -> str:
    from services.authoring import parts
    return str((parts.active() or {}).get("label") or "자격시험")


def _terms() -> Dict[str, str]:
    """이 앱의 발음 사전 하나 — vendor/chodangi/config/pronunciation_map.yaml (backplate 것 합쳐 300여 개).
    ★ 사전 여러 개를 거치지 않는다(사용자 지시 2026-10-24: 여기에 300여 개를 두는 것이 목표).
    ★ 발음대본은 이 앱에서 끝낸다 — 사전이 data-read 글자에 직접 들어가야 하류가 그대로 읽는다."""
    try:
        from services.render import lexicon
        return dict(lexicon.read().get("rules") or {})
    except Exception:                                        # noqa: BLE001
        from services.authoring import parts
        d = (parts.active() or {}).get("speech_dict") or {}
        return d if isinstance(d, dict) else {}


def _author(log: Log, model: str = "", effort: Optional[str] = None):
    from services.authoring.provider import ClaudeAuthor
    # 읽을 파일이 없다 — 필요한 것은 전부 프롬프트에 있다. 빈 임시 폴더를 cwd 로 준다.
    cwd = tempfile.mkdtemp(prefix="lecture-")
    a = ClaudeAuthor(cwd=cwd, model=model, effort=effort, on_activity=log, max_turns=12)
    return a, cwd


# ── 스키마 ──────────────────────────────────────────────────────────────────
def _schema(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["slides"],
            "properties": {"slides": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": list(item), "properties": item}}}}


S_SAY = _schema({"id": {"type": "string"}, "say": {"type": "string"}})
S_READ = _schema({"id": {"type": "string"}, "read": {"type": "string"}})
S_FIG = _schema({"id": {"type": "string"}, "svg": {"type": "string"}})
S_EXPAND = _schema({"base": {"type": "string"}, "title": {"type": "string"},
                    "body": {"type": "string"}, "say": {"type": "string"},
                    "svg": {"type": "string"}})

SYSTEM = """당신은 {시험} 이론 강의의 원고 작가다. 슬라이드 한 장(h3)마다 강사가 소리 내어 읽을 대본을 쓴다.
원천은 우리 요약노트뿐이다. 요약노트에 없는 사실을 지어내지 않는다. 문체는 「~입니다」 강의체, 한국어."""


# ── ① 자막대본 ─────────────────────────────────────────────────────────────
def _p_say(doc, sec, todo) -> str:
    rows = [f"### {sl['id']} · {sl['title']}\n{_plain_body(sl['body'])}" for sl in todo]
    return f"""■ {doc['title']} — 대단원 「{sec['title']}」
아래 장마다 data-say(대본)를 쓴다. 대본은 그대로 **자막**이 되고 TTS 로 읽힌다.

■ 규칙
- 한 장 6~10문장, 250~450자. 그 장의 몸통(아래 글·표·그림)을 말로 풀어 설명한다.
- 정의 → 왜 그런가 → 시험에서 갈리는 자리(함정) 순서. '항상'·'반드시' 같은 함정 표현을 짚는다.
- 표를 칸 단위로 읽지 않는다. 그림은 "그림에서 보듯" 처럼 가리키며 핵심만 말한다.
- 마지막 문장은 다음 장으로 잇는 말("다음 장에서는 …을 보겠습니다"). 대단원의 마지막 장은 정리 한 문장.
- 기호·괄호·영문 약어는 써도 된다(발음은 다음 단계가 고친다). 이모지·마크다운 금지.

■ 장 목록
{chr(10).join(rows)}

slides 에 위 장 전부를 같은 id 로 돌려준다."""


# ── ② 낭독대본 ─────────────────────────────────────────────────────────────
def _p_read(doc, sec, todo, base) -> str:
    rows = [f"### {sl['id']}\n자막: {sl['say']}\n기계 변환: {base[sl['id']]}" for sl in todo]
    return f"""■ {doc['title']} — 대단원 「{sec['title']}」 낭독대본(data-read)
자막은 맞춤법대로 둔다. 낭독은 **TTS 가 소리 나는 대로** 적은 글이다. 뜻은 자막과 같다.

■ 규칙
- 아래 '기계 변환' 은 숫자·기호를 이미 소리로 바꾼 것이다. 이를 고쳐 최종 낭독을 쓴다.
- 영문 약어·용어: 실제 강사가 읽는 소리로(SQL → 에스큐엘, DBMS → 디비엠에스, R → 알).
- 기호: = → 은/는, ÷ → 나누기, → → 에서, % → 퍼센트, () 안 영문 병기는 뺀다.
- 된소리·연음은 TTS 가 틀리게 읽는 자리만 고친다(예: 결정자 → 결쩡자, 함수 종속 그대로).
- 문장 수·순서·뜻을 바꾸지 않는다. 자막과 똑같이 읽혀도 되는 장은 read 를 빈 문자열로.

■ 장 목록
{chr(10).join(rows)}

slides 에 위 장 전부를 같은 id 로 돌려준다."""


# ── ③ SVG 추가 슬라이드 ────────────────────────────────────────────────────
def _p_fig(doc, sec, todo) -> str:
    rows = [f"### {sl['id']} · {sl['title']}\n{_plain_body(sl['body'])}\n대본: {sl.get('say', '')[:500]}"
            for sl in todo]
    return f"""■ {doc['title']} — 대단원 「{sec['title']}」 장마다 도식(SVG) 하나
아래 장들은 표나 그림이 없다. 장마다 그 장의 핵심을 보여 주는 인라인 SVG 를 하나씩 그린다.

■ 규칙
- <svg viewBox="0 0 W H" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="한 문장 설명" …> 로 시작.
  W 는 480~640, H 는 160~300. width/height 속성은 넣지 않는다.
- 글자는 font-family="sans-serif", 12~15px, 한 상자에 12자 이내. 색은 #1b1f19 글씨, 강조 #c41c0b, 보조 #0f7355, 면 #f3f1e6.
- 개념 관계(포함·흐름·비교·계층·표 모양)를 도형과 화살표로. 대본에 나오는 말과 같은 용어를 쓴다.
- <script>·<foreignObject>·외부 이미지·애니메이션 금지. 화살표는 <marker> 로(id 는 장 id 를 붙여 겹치지 않게).

■ 장 목록
{chr(10).join(rows)}

slides 에 위 장 전부를 같은 id 로, svg 에 SVG 전문을 넣어 돌려준다."""


def _svg_ok(svg: str) -> str:
    """검사 통과면 정리한 SVG, 아니면 빈 문자열."""
    s = (svg or "").strip()
    if not s.startswith("<svg") or "<script" in s.lower() or "foreignobject" in s.lower():
        return ""
    try:
        ET.fromstring(s)
    except ET.ParseError:
        return ""
    return s


# ── ④ n배 확장 ─────────────────────────────────────────────────────────────
def _p_expand(doc, sec, todo, factor) -> str:
    extra = max(1, int(factor) - 1)
    rows = [f"### {sl['id']} · {sl['title']}\n몸통:\n{_plain_body(sl['body'])}\n대본: {sl.get('say', '')}"
            for sl in todo]
    return f"""■ {doc['title']} — 대단원 「{sec['title']}」 종합반용 {factor}배 확장
요약반 장 하나 뒤에 **새 장 {extra}개씩**을 덧붙여, 같은 개념을 {factor}배 분량으로 가르친다.

■ 새 장에 넣을 것 (장마다 하나를 골라)
- 개념 풀이: 정의를 다른 말로 다시, 왜 그렇게 정의하는지
- 예시: 구체적인 표·값·상황으로 따라가기(계산 문제는 한 단계씩)
- 비교: 헷갈리는 짝과 나란히
- 오답 함정: 시험이 말을 바꾸는 방식과 판별법

■ 규칙
- base 에 원래 장 id, title 에 새 장 제목(짧게), body 에 슬라이드 몸통 HTML(<p>·<ul><li>·<table> 만, 3~6항목).
- say 는 그 새 장의 대본(250~450자, 「~입니다」체, 마지막 문장은 다음 장으로 잇기).
- svg 는 그 장에 도식이 도움이 되면 인라인 SVG(규칙: viewBox 480~640×160~300, sans-serif, 스크립트 금지), 아니면 빈 문자열.
  body 에 표가 없고 svg 도 비면 안 된다 — 장마다 표 아니면 그림 하나.
- 요약노트에 없는 새 사실을 지어내지 않는다. 예시의 값은 만들어도 된다.

■ 원래 장 목록
{chr(10).join(rows)}

slides 에 새 장만(원래 장 하나당 {extra}개, 원래 순서대로) 돌려준다."""


# ── 실행 ────────────────────────────────────────────────────────────────────
def run(kind: str, key: str, stage: str, *, log: Log, cancelled: Callable[[], bool],
        redo: bool = False, sections: Optional[List[int]] = None,
        model: str = "", effort: Optional[str] = None) -> Dict[str, Any]:
    doc = N.load(kind, key)
    if not doc:
        raise ValueError("노트가 없습니다 — 먼저 [노트 만들기] 를 누르세요.")
    view = {s["stage"]: s for s in N.stage_view(doc)}
    if stage not in view:
        raise ValueError(f"이 노트에는 「{stage}」 단계가 없습니다.")
    if not view[stage]["open"]:
        raise ValueError(f"앞 단계가 승인되지 않아 「{view[stage]['label']}」 를 열 수 없습니다.")
    if stage == "build":
        return build(doc, log=log)
    if stage == "listen":
        raise ValueError("듣기 검수는 실행하는 단계가 아닙니다 — 검수 화면에서 듣고 OK 합니다.")

    system = SYSTEM.replace("{시험}", _exam_label())
    author, cwd = _author(log, model, effort)
    total = 0.0
    changed = 0
    try:
        N.set_stage(doc, stage, "running")
        N.save(doc)
        for si, sec in enumerate(doc["sections"]):
            if sections and si not in sections:
                continue
            if cancelled():
                log("취소했습니다 — 여기까지 저장했습니다.")
                break
            n = _section(doc, sec, stage, author, system, redo, log)
            changed += n
            total += author.last_cost_usd if n else 0.0
            if n:
                N.save(doc)
                log(f"[{si + 1}/{len(doc['sections'])}] {sec['title']} — {n}장 · "
                    f"${author.last_cost_usd:.3f}")
        if stage == "say":
            _h1(doc)
        if stage == "read":
            from core.speak import to_speech
            h1 = doc["h1"]
            h1["read"] = h1.get("read") or _diff(h1.get("say"), to_speech(h1.get("say") or "", _terms()))
            h1["outro_read"] = h1.get("outro_read") or _diff(
                h1.get("outro_say"), to_speech(h1.get("outro_say") or "", _terms()))
        prev = (doc.get("stages") or {}).get(stage, {})
        N.set_stage(doc, stage, "done", cost_usd=round(float(prev.get("cost_usd") or 0) + total, 4),
                    note=f"{changed}장")
        N.save(doc)
        N.write_html(doc)
    except Exception:
        N.set_stage(doc, stage, "error")
        N.save(doc)
        raise
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
    return {"changed": changed, "cost_usd": round(total, 4)}


def _diff(a: Optional[str], b: str) -> str:
    return "" if (b or "") == (a or "") else b


def _h1(doc) -> None:
    """여는 말·닫는 말 — 대단원 제목으로 짓는다(모델을 부르지 않는다)."""
    t = [s["title"] for s in doc["sections"]]
    lst = ", ".join(t[:4]) + (" 등" if len(t) > 4 else "")
    doc["h1"]["say"] = (f"{doc['title']} 입니다. {lst} 순으로 살펴보겠습니다. "
                        "장마다 개념을 하나씩 짚고, 시험에서 어디가 갈리는지 함께 보겠습니다.")
    doc["h1"]["outro_say"] = (f"여기까지 {doc['title']} 이었습니다. {t[0]}에서 시작해 {t[-1]}까지 왔습니다. "
                              "헷갈렸던 장은 다시 돌려 보시기 바랍니다.")


def _section(doc, sec, stage, author, system, redo, log) -> int:
    from core.speak import to_speech

    if stage == "say":
        todo = [s for s in sec["slides"] if redo or not s.get("say")]
        if not todo:
            return 0
        got = author.structured(system, _p_say(doc, sec, todo), S_SAY)
        by = {g["id"]: g["say"].strip() for g in got["slides"] if g.get("say", "").strip()}
        for s in todo:
            if s["id"] in by:
                s["say"] = by[s["id"]]
                s["read"] = ""            # 자막이 바뀌면 낭독은 다시 만든다
        _missing(todo, by, log)
        return len(by)

    if stage == "read":
        todo = [s for s in sec["slides"] if s.get("say") and (redo or not s.get("read_done"))]
        if not todo:
            return 0
        base = {s["id"]: to_speech(s["say"], _terms()) for s in todo}
        got = author.structured(system, _p_read(doc, sec, todo, base), S_READ)
        by = {g["id"]: g.get("read", "").strip() for g in got["slides"]}
        for s in todo:
            r = by.get(s["id"]) or base[s["id"]]
            s["read"] = "" if r == s["say"] else r
            s["read_done"] = True
        return len(todo)

    if stage == "fig":
        todo = [s for s in sec["slides"] if (redo and s.get("fig")) or not N.has_visual(s)]
        if not todo:
            return 0
        got = author.structured(system, _p_fig(doc, sec, todo), S_FIG)
        n = 0
        for g in got["slides"]:
            svg = _svg_ok(g.get("svg", ""))
            for s in todo:
                if s["id"] == g.get("id") and svg:
                    s["fig"] = svg
                    n += 1
        bad = [s["id"] for s in todo if not s.get("fig") and not N.has_visual(s)]
        if bad:
            log(f"(주의) 도식을 못 받았거나 SVG 가 깨진 장: {', '.join(bad)} — 다시 실행하면 그 장만 돕니다.")
        return n

    if stage == "expand":
        factor = int(doc.get("factor") or DEFAULT_FACTOR)
        base_ids = {s["id"] for s in sec["slides"] if s.get("base") == s["id"]}
        grown = {s["base"] for s in sec["slides"] if s.get("base") != s["id"]}
        todo = [s for s in sec["slides"] if s["id"] in base_ids and (redo or s["id"] not in grown)]
        if not todo:
            return 0
        if redo:
            sec["slides"] = [s for s in sec["slides"] if s.get("base") == s["id"]
                             or s["base"] not in {t["id"] for t in todo}]
        got = author.structured(system, _p_expand(doc, sec, todo, factor), S_EXPAND)
        out: List[Dict[str, Any]] = []
        new_by: Dict[str, List[Dict[str, Any]]] = {}
        for g in got["slides"]:
            if g.get("base") in base_ids and g.get("say", "").strip():
                new_by.setdefault(g["base"], []).append(g)
        for s in sec["slides"]:
            out.append(s)
            if s.get("base") != s["id"]:
                continue
            for j, g in enumerate(new_by.get(s["id"], [])):
                out.append({"id": f"{s['id']}-{chr(ord('b') + j)}", "base": s["id"],
                            "title": g["title"].strip() or s["title"], "qref": "",
                            "body": g.get("body", "").strip(), "say": g["say"].strip(),
                            "read": "", "fig": _svg_ok(g.get("svg", ""))})
        sec["slides"] = out
        return sum(len(v) for v in new_by.values())
    raise ValueError(f"알 수 없는 단계: {stage}")


def incomplete(doc: Dict[str, Any], stage: str) -> List[str]:
    """이 단계가 아직 못 채운 장 id — 승인 전에 본다."""
    sl = N.slides(doc)
    if stage == "say":
        return [s["id"] for s in sl if not s.get("say")]
    if stage == "read":
        return [s["id"] for s in sl if s.get("say") and not s.get("read_done")]
    if stage == "fig":
        return [s["id"] for s in sl if not N.has_visual(s)]
    if stage == "expand":
        grown = {s.get("base") for s in sl if s.get("base") != s["id"]}
        return [s["id"] for s in sl if s.get("base") == s["id"] and s["id"] not in grown]
    return []


def _missing(todo, by, log) -> None:
    miss = [s["id"] for s in todo if s["id"] not in by]
    if miss:
        log(f"(주의) 대본을 못 받은 장: {', '.join(miss)} — 다시 실행하면 그 장만 돕니다.")


# ── 노트 빌드 ───────────────────────────────────────────────────────────────
def deck_dir(kind: str, key: str) -> str:
    return os.path.join(paths.book_dir(), "04-2", "lecture", kind, key)


def build(doc: Dict[str, Any], *, log: Log) -> Dict[str, Any]:
    """원고 HTML → html2deck PPTX(대단원마다) + 장별 자막·낭독 목록 + 안내문.

    ★ mp4 는 만들지 않는다. 요약반 원고는 다른 PC 에서 이미지화한 뒤 hyper-close-frame
      (HyperFrames)으로 렌더링하고, 종합반 원고는
      lecture-composer 가 영상으로 굽는다(다른 PC). PPTX 는 html2deck 의 두 번째 갈래로
      강의 슬라이드가 필요할 때 쓴다.
    """
    from vendor.exam2deck import build as e2d
    from vendor.exam2deck import svg_raster

    kind, key = doc["kind"], doc["key"]
    html = N.write_html(doc)
    log(f"원고 HTML: {html}")
    out = deck_dir(kind, key)
    if os.path.isdir(out):
        shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    opt = e2d.Options(exam=_exam_label(), part_size=1,
                      fig_cache=os.path.join(kind_dir(kind), "_figcache"))
    with svg_raster.Raster(opt.fig_cache) as raster:
        b = e2d.build_pages(html, opt, raster)
        rep = e2d.build_file(html, out, opt, raster)
    # 페이지 → 장(data-id). 토픽 첫 장에만 heading 이 붙고 h3 순서가 유지된다.
    sl = [s for s in N.slides(doc)]
    rows, ti = [], -1
    for part in b.parts:
        for pi, pg in enumerate(part.pages, 1):
            if pg.kind == "cover":
                rows.append({"file": part.stem + ".pptx", "page": pi, "id": "", "cover": True,
                             "say": "", "read": ""})
                continue
            if pg.heading:
                ti += 1
            s = sl[ti] if 0 <= ti < len(sl) else {}
            first = bool(pg.heading)
            rows.append({"file": part.stem + ".pptx", "page": pi, "id": s.get("id", ""),
                         "say": s.get("say", "") if first else "",
                         "read": N.spoken(s) if first else "", "cont": not first})
    atomic_write_json(os.path.join(out, "narration.json"),
                      {"kind": kind, "key": key, "title": doc["title"], "html": os.path.basename(html),
                       "h1": doc.get("h1"), "pages": rows}, indent=1)
    if ti + 1 != len(sl):
        log(f"(주의) 덱의 장 수({ti + 1})와 노트의 장 수({len(sl)})가 다릅니다 — narration.json 의 대응을 확인하세요.")
    shutil.copyfile(html, os.path.join(out, os.path.basename(html)))
    atomic_write_text(os.path.join(out, "RENDER.txt"), _render_txt(doc, html))
    kit = _longform_kit(doc, html) if kind == "full" else ""
    N.set_stage(doc, "build", "done", note=f"PPTX {len(rep.get('files', []))}개 · {rep.get('size_kb', 0)}KB",
                hash=N.content_hash(doc))
    N.save(doc)
    log(f"PPTX {len(rep.get('files', []))}개 → {out}")
    if kit:
        log(f"lecture-composer 입력 키트 → {kit}")
    return {"html": html, "deck_dir": out, "files": rep.get("files", []), "kit": kit}


def _render_txt(doc, html) -> str:
    name = os.path.basename(html)
    if doc["kind"] == "summary":
        how = (f"요약반(요약 영상 M) — 다른 PC 에서 장마다 이미지화한 뒤 hyper-close-frame(HyperFrames)으로\n"
               f"  렌더링한다. https://github.com/leedonwoo2827-ship-it/hyper-close-frame\n"
               f"  입력: {name}  (h3 = 한 장 · data-say 자막 · data-read 낭독)\n")
    else:
        how = (f"종합반(종합반 강의 L) — lecture-composer 의 jobs/<잡>/input/ 에\n"
               f"  _longform-kit/<품목>/ 의 notes · rounds · scripts 를 그대로 복사한 뒤 s1 plan 부터.\n")
    return ("XAM LOCAL v2 — 렌더 키트 (영상은 다른 PC 에서 굽는다)\n\n" + how +
            "\n같이 든 것 (덱은 영상과 따로인 별도 산물이다 — 요약반이면 요약덱)\n"
            "  *.pptx          html2deck 강의 슬라이드(대단원마다 한 파일)\n"
            "  narration.json  덱 페이지 → 장 id · 자막 · 낭독 대응표\n")


def _longform_kit(doc, html) -> str:
    """lecture-composer jobs/<잡>/input 과 같은 배치: notes/ · rounds/ · scripts/."""
    from services.book.paths import active_pd
    pd = active_pd() or "book"
    root = os.path.join(paths.book_dir(), "_longform-kit", pd)
    for sub in ("notes", "rounds", "scripts"):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    s = doc["subject_no"]
    src_note = paths.summary_html(doc["key"])
    if os.path.isfile(src_note):
        shutil.copyfile(src_note, os.path.join(root, "notes", f"{s:02d}-summary_{doc['key']}.html"))
    rd = os.path.join(paths.book_dir(), "_rounds")
    for fn in sorted(os.listdir(rd)) if os.path.isdir(rd) else []:
        if re.fullmatch(r"m\d{2}\.json", fn):
            shutil.copyfile(os.path.join(rd, fn), os.path.join(root, "rounds", fn))
    shutil.copyfile(html, os.path.join(root, "scripts", os.path.basename(html)))
    return root
