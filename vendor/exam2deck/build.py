# -*- coding: utf-8 -*-
"""파싱 → 분할 → 도식 → PPTX 를 한 줄로 묶은 진입점.

CLI(`tools/html2deck.py`)와 웹 스튜디오(`services/studio/pipeline.py`)가 **같은 함수**를
쓴다. 두 경로가 각자 조립하면 한쪽에서만 고쳐지는 버그가 생긴다 — 원본 덱 렌더러도
미리보기와 베이크가 같은 함수를 쓴다는 규약을 지고 있었다(`preview.py` 머리말).
"""
from __future__ import annotations

import os
import re
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import (layout, metrics, parse_html, parse_theory, pptx_render,
               svg_raster, template_spec)
from .ir import Doc, Page, Round


@dataclass
class Options:
    exam: str = ""              # 자격증명 (간지 eyebrow)
    # ★ **파일을 쪼개는 단위**다. 간지 사이가 아니다(2026-08-21 사용자 정정:
    #   "간지는 10문제마다 파일을 쪼갤거기 때문에 파일 앞에만 나오면 됩니다").
    #   전에는 한 파일 안에 간지를 8장 흩어 넣었는데, 10문항짜리 파일 8개에
    #   간지가 각각 맨 앞 1장씩 오는 것이 맞다. 0 이면 쪼개지 않는다.
    part_size: int = 10
    repeat_opts: bool = True    # 해설 면에 보기를 다시 넣는가
    # 전체 글자 배율. **모든 장이 같은 값을 쓴다** — 장마다 고르지 않는다
    #   (`layout.GROW_LADDER` 머리말의 정정). 1.0 = 발문 16pt · 보기 12pt · 해설 10pt.
    scale: float = layout.DEFAULT_SCALE
    template: Optional[str] = None
    fig_cache: str = ""         # 도식 PNG 캐시 폴더
    # ★ 문항별 장수 지정 (xam-local 이 더한 것). {문번: {"problem": n, "answer": m}}
    #   사람이 화면에서 ± 로 정한 값이다. 못 맞춘 문항은 `page_missed` 에 남는다 —
    #   조용히 자연 장수로 돌아가면 화면이 거짓말을 하게 된다.
    page_want: Dict[int, Dict[str, int]] = field(default_factory=dict)


# ★ 지시문에서 옵션을 읽는다. 웹 화면에는 옵션 칸이 없고 「추가 지시」 한 칸뿐이라,
#   거기에 `exam=빅데이터분석기사 part=10 no-opts` 처럼 적으면 먹게 한다.
#   못 알아본 말은 무시한다 — 사람이 자유롭게 쓰는 칸이다.
_TOKENS = {
    "exam": re.compile(r"(?:exam|자격증명)\s*[=:]\s*([^\s,]+)"),
    "part": re.compile(r"(?:part|part_size|간지)\s*[=:]\s*(\d+)"),
    # 전체 글자 배율. 1.0 = 기본(발문 16pt · 보기 12pt · 해설 10pt).
    "scale": re.compile(r"(?:scale|배율|크기)\s*[=:]\s*([\d.]+)"),
}


def options_from_instruction(text: str, base: Optional[Options] = None) -> Options:
    o = base or Options()
    t = text or ""
    m = _TOKENS["exam"].search(t)
    if m:
        o.exam = m.group(1)
    m = _TOKENS["part"].search(t)
    if m:
        o.part_size = int(m.group(1))
    m = _TOKENS["scale"].search(t)
    if m:
        try:
            o.scale = max(0.5, min(3.0, float(m.group(1))))
        except ValueError:
            pass
    if re.search(r"no-?opts|보기\s*생략|보기\s*없", t):
        o.repeat_opts = False
    return o


def exam_from_book(html_path: str) -> str:
    """`_book.json` 의 `label` 을 자격증명으로 쓴다(있으면).

    덱 HTML 의 `<title>` 은 "모의고사 01회 — 문제 풀이" 까지고 자격증명이 없다.
    `_deck-export` 의 부모 폴더에 `_book.json` 이 있으면 거기서 가져온다.
    """
    import json
    d = os.path.dirname(os.path.abspath(html_path))
    for _ in range(3):
        p = os.path.join(d, "_book.json")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f).get("label", "") or ""
            except Exception:
                return ""
        d = os.path.dirname(d)
    return ""


def report(round_no: str, pages: List[Page]) -> Dict[str, Any]:
    """진단 리포트. 넘침·채움률이 여기서만 나온다 — 눈으로 보기 전에 숫자로 본다."""
    body = [p for p in pages if p.kind != "cover" and p.budget_px]
    fills = [p.used_px / p.budget_px for p in body]
    return {
        "round": round_no,
        "slides": len(pages),
        "cover": sum(1 for p in pages if p.kind == "cover"),
        "problem": sum(1 for p in pages if p.kind == "problem"),
        "answer": sum(1 for p in pages if p.kind == "answer"),
        "topic": sum(1 for p in pages if p.kind == "topic"),
        "fill_median": round(statistics.median(fills), 3) if fills else 0.0,
        "fill_min": round(min(fills), 3) if fills else 0.0,
        "under_40pct": sum(1 for f in fills if f < 0.40),
        "overflow": [{"q": p.q_no, "kind": p.kind,
                      "over_px": round(p.used_px - p.budget_px, 1)}
                     for p in body if p.used_px > p.budget_px],
        "scale_min": round(min((p.scale for p in body), default=1.0), 2),
        "scale_max": round(max((p.scale for p in body), default=1.0), 2),
    }


@dataclass
class Part:
    """산출 파일 하나. 간지 1장 + 그 편의 슬라이드들."""
    stem: str                       # 파일 이름(확장자 없이)
    pages: List[Page] = field(default_factory=list)
    label: str = ""                 # "1~10번" / "1. 정규화와 함수 종속"
    # ★ 이 편이 원본의 몇 번째인가. **파일 단위로 다시 만들 때 쓴다** —
    #   화면에서 파일마다 옵션을 고칠 수 있어야 한다는 요구(2026-08-21:
    #   "파일마다 채팅을 할수 있어야 해")를 이 번호 하나로 받는다.
    index: int = 0


@dataclass
class Built:
    kind: str = "exam"              # "exam" | "theory"
    title: str = ""                 # 회차명 또는 과목명
    parts: List[Part] = field(default_factory=list)
    unknown: Dict[str, int] = field(default_factory=dict)
    n_units: int = 0                # 문항 수 또는 토픽 수
    # 장수 지정을 못 맞춘 문항 (xam-local). 화면이 빨갛게 표시할 목록이다.
    page_missed: List[Dict[str, Any]] = field(default_factory=list)


def _safe(name: str) -> str:
    """파일명에 못 쓰는 글자만 바꾼다. 한글은 그대로 둔다."""
    return re.sub(r'[\/:*?"<>|]+', "_", name).strip() or "deck"


# ── 문제 덱 ─────────────────────────────────────────────────────────────────
def _build_exam(html_path: str, opt: Options) -> Built:
    """문제 덱 → 편(Part) 목록.

    ★ **파일을 쪼갠다.** 한 파일 안에 간지를 흩어 넣지 않는다(2026-08-21 사용자
      정정). 10문항짜리 파일 8개에 간지가 각각 맨 앞 1장씩 온다 — 첨부한 참고
      이미지의 "5편 중 2편" 이 그 뜻이었다.
    """
    exam = opt.exam or exam_from_book(html_path)
    rnd, unknown = parse_html.parse_file(html_path, exam)
    qs = rnd.questions
    size = opt.part_size if opt.part_size > 0 else len(qs) or 1
    n_parts = max(1, math.ceil(len(qs) / size)) if qs else 0
    base = rnd.round_no or os.path.splitext(os.path.basename(html_path))[0]

    parts: List[Part] = []
    missed: List[Dict[str, Any]] = []
    for pi in range(n_parts):
        chunk = qs[pi * size:(pi + 1) * size]
        if not chunk:
            continue
        lo, hi = chunk[0].no, chunk[-1].no
        rng = f"{lo}번부터 {hi}번까지" if hi != lo else f"{lo}번"
        pages: List[Page] = [Page(
            kind="cover",
            cover_eyebrow=rnd.exam,
            cover_title=(f"{rnd.title} ({pi + 1}/{n_parts})"
                         if n_parts > 1 else rnd.title),
            cover_lead=(f"{rng} · {n_parts}편 중 {pi + 1}편"
                        if n_parts > 1 else rng),
            # ★ 간지도 본문과 같은 배율을 쓴다. 안 넘기면 `scale=1.4` 를 줬을 때
            #   본문만 커지고 표지는 그대로여서 한 파일 안에서 크기가 갈린다.
            scale=opt.scale,
            q_no=lo)]
        for q in chunk:
            want = opt.page_want.get(q.no) or opt.page_want.get(str(q.no))
            got = layout._pages_for(q, repeat_opts=opt.repeat_opts,
                                    scale=opt.scale, want=want)
            if want:
                have = {"problem": sum(1 for p in got if p.kind == "problem"),
                        "answer": sum(1 for p in got if p.kind == "answer")}
                for k in ("problem", "answer"):
                    if want.get(k) and int(want[k]) != have[k]:
                        missed.append({"no": q.no, "kind": k,
                                       "want": int(want[k]), "got": have[k]})
            pages.extend(got)
        stem = _safe(f"{base}_강의_{lo:02d}-{hi:02d}" if n_parts > 1
                     else f"{base}_강의")
        parts.append(Part(stem=stem, pages=pages, label=f"{lo}~{hi}번",
                          index=pi))
    return Built(kind="exam", title=base, parts=parts, unknown=unknown,
                 n_units=len(qs), page_missed=missed)


# ── 이론 덱 ─────────────────────────────────────────────────────────────────
def _build_theory(html_path: str, opt: Options) -> Built:
    """요약노트 → 편(Part) 목록. **대단원(h2) 단위로 쪼갠다.**

    ★ 문제 덱은 10문항이 한 편이다. 이론에는 문항이 없으므로 같은 자리를 대단원이
      맡는다 — 원본 규약이 *"h2/h3 가 이미 목차"* 라고 못박았으므로 h2 가 편의
      경계로 가장 자연스럽다. `--part-size 0` 이면 한 파일로 낸다.
    """
    exam = opt.exam or exam_from_book(html_path)
    doc, unknown = parse_theory.parse_file(html_path, exam)
    base = _safe(doc.title or os.path.splitext(os.path.basename(html_path))[0])

    # 대단원별로 묶는다. 순서는 원문 그대로다.
    groups: List[List] = []
    cur_key = object()
    for t in doc.topics:
        key = (t.chapter_no, t.chapter)
        if key != cur_key:
            groups.append([])
            cur_key = key
        groups[-1].append(t)
    if opt.part_size <= 0:
        groups = [doc.topics] if doc.topics else []

    n_parts = len(groups)
    parts: List[Part] = []
    for pi, group in enumerate(groups):
        if not group:
            continue
        chap = f"{group[0].chapter_no}. {group[0].chapter}".strip(" .")
        lo = f"{group[0].no} {group[0].title}".strip()
        hi = f"{group[-1].no} {group[-1].title}".strip()
        pages: List[Page] = [layout.doc_cover(
            doc, part=pi + 1, parts=n_parts, lo=lo, hi=hi)]
        pages[0].scale = opt.scale
        if n_parts > 1:
            pages[0].cover_title = f"{doc.title} — {chap}" if chap else doc.title
            pages[0].cover_lead = f"{len(group)}개 주제 · {n_parts}편 중 {pi + 1}편"
        for t in group:
            pages.extend(layout.pages_for_topic(t, doc.subject_no, opt.scale))
        stem = _safe(f"{base}_{group[0].chapter_no}_{group[0].chapter}_강의"
                     if n_parts > 1 else f"{base}_강의")
        parts.append(Part(stem=stem, pages=pages, label=chap or base,
                          index=pi))
    return Built(kind="theory", title=doc.title, parts=parts, unknown=unknown,
                 n_units=len(doc.topics))


def apply_template(opt: Options) -> Dict[str, Any]:
    """템플릿의 규격 슬라이드를 읽어 적용한다. **작업 시작마다 부른다.**

    ★ 템플릿이 없거나 규격 표가 없으면 내장 기본값으로 되돌린다. 웹 서버는 한
      프로세스에서 여러 작업을 돌리므로, 앞 작업의 규격이 남으면 다음 작업이
      조용히 다른 크기로 나온다.
    """
    spec = template_spec.read(opt.template or "")
    applied = layout.apply_spec(spec)
    applied["source"] = template_spec.describe(spec)
    return applied


def build_pages(html_path: str, opt: Options,
                raster: Optional[svg_raster.Raster] = None) -> Built:
    """HTML 하나 → 편 목록 (도식 PNG 까지 붙여서).

    ★ 파서는 **내용으로** 고른다. 파일명으로 고르면 안 된다 — 웹으로 올리면
      `deck__1summary_datamodel.html` 처럼 이름이 바뀌고, 실측에서 요약노트가
      문제 덱 파서로 들어가 0장짜리 pptx 가 나왔다.
    """
    b = (_build_theory(html_path, opt) if parse_theory.looks_like_theory(html_path)
         else _build_exam(html_path, opt))
    _attach_figures([p for part in b.parts for p in part.pages], raster, opt)
    return b


def _attach_figures(pages: List[Page], raster: Optional[svg_raster.Raster],
                    opt: Options) -> None:
    """페이지에 **실린** 도식만 래스터화한다.

    ★ 문항 전체를 미리 뽑지 않는다. 분할 결과에 따라 안 실리는 도식이 있을 수 있고,
      래스터화는 이 파이프라인에서 가장 느린 단계다(회차당 26장, 약 8초).
    """
    todo = [b for p in pages for b in p.blocks
            if b.kind == "figure" and b.svg and not b.img_path]
    if not todo:
        return
    if raster is not None:
        for b in todo:
            b.img_path = raster.png(b.svg) or ""
        return
    cache = opt.fig_cache or os.path.join(os.getcwd(), "_figcache")
    with svg_raster.Raster(cache) as rz:
        for b in todo:
            b.img_path = rz.png(b.svg) or ""


def build_file(html_path: str, out_dir: str, opt: Options,
               raster: Optional[svg_raster.Raster] = None,
               only_index: Optional[int] = None) -> Dict[str, Any]:
    """HTML 하나 → .pptx **여러 개**. 반환: 리포트(편 목록 포함).

    ★ `only_index` 를 주면 그 편 **하나만** 다시 만든다. 파일마다 옵션을 고치는
      화면이 이 인자를 쓴다 — 한 파일을 고치려고 80문항을 다시 그릴 이유가 없다.
    """
    spec = apply_template(opt)
    b = build_pages(html_path, opt, raster)
    os.makedirs(out_dir, exist_ok=True)
    files: List[Dict[str, Any]] = []
    all_pages: List[Page] = []
    for part in b.parts:
        if only_index is not None and part.index != only_index:
            continue
        out = os.path.join(out_dir, part.stem + ".pptx")
        pptx_render.render(part.pages, out, template=opt.template)
        all_pages.extend(part.pages)
        files.append({"name": os.path.basename(out), "path": out,
                      "label": part.label, "slides": len(part.pages),
                      "size_kb": os.path.getsize(out) // 1024,
                      "src": html_path, "part": part.index})
    rep = report(b.title, all_pages)
    rep.update(kind=b.kind, files=files, parts=len(b.parts),
               units=b.n_units, unknown_elements=b.unknown,
               size_kb=sum(f["size_kb"] for f in files),
               spec=spec.get("source", ""), type_pt=spec.get("type_pt", {}))
    return rep


def font_report() -> Dict[str, str]:
    return metrics.font_source()
