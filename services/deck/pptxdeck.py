# -*- coding: utf-8 -*-
r"""회차 하나 → 번들마다 `source/deck.pptx` + `source/pages.json` + 씬 다시 매기기.

    _rounds/mNN.json
      └ bake                → 05/<b>/source/lesson_<b>.json · deck.html
           ↓ rounddeck.write_round
      <book>/_deck-export/NN회.html
           ↓ vendor/exam2deck  (part_size = 시험정보의 problems_per_bundle)
      <book>/04-2/NN회_강의_LO-HI.pptx  +  05/<b>/source/pages.json
           ↓ bake.write_script(bundle, pages.json 의 metas)
      05/<b>/script/<b>_script.json

★ **장 나눔의 진실이 여기로 옮겨 온다.** 지금까지는 `deck.html` 의 `.slide` 수가
  씬 수였다. 변환기는 원본의 과분할을 되붙여 다시 쪼개므로 그 수가 달라진다
  (SQLD 01회: 원본 145장 → 112장). 그래서 씬을 **여기서 다시 매긴다** — 안 하면
  이미지와 음성이 한 장씩 밀린 영상이 나온다.

★ 편(Part) i ↔ 번들 `mNN-(i+1)`. 변환기의 `part_size` 와 앱의
  `video.problems_per_bundle` 이 같은 수라서 1:1 이다. **어긋나면 멈춘다** —
  조용히 밀리는 것이 가장 나쁘다.

★ `deck.html` 은 없어지지 않는다. 미리보기(`/slide/`)와 이 변환기의 **입력**으로
  남는다. 다만 씬의 근거는 더 이상 아니다.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_json
from services.book import paths
from services.deck import rounddeck
from services.render import bake

_APP = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(_APP, "vendor", "exam2deck", "assets",
                        "pptx_template_exam.pptx")


# ── 시험정보에서 오는 값 ────────────────────────────────────────────────────
# ★ 코드에 박으면 SQLD 영상에 빅분기 값이 조용히 나간다(`bake.py` 머리말과 같은 규약).
def _spec() -> Dict[str, Any]:
    try:
        from services.authoring import parts
        return parts.active() or {}
    except Exception:                                        # noqa: BLE001
        return {}


def _deck_spec() -> Dict[str, Any]:
    d = _spec().get("deck")
    return d if isinstance(d, dict) else {}


def spec_scale() -> float:
    """글자 배율. 1.0 = 발문 16pt · 보기 12.5pt · 해설 10pt."""
    try:
        v = float(_deck_spec().get("pptx_scale") or 1.0)
    except (TypeError, ValueError):
        v = 1.0
    return max(0.5, min(3.0, v))


def spec_repeat_opts() -> bool:
    v = _deck_spec().get("repeat_opts")
    return True if v is None else bool(v)


def exam_label() -> str:
    return str(_spec().get("label") or "").strip() or "자격시험"


# ── 편 ↔ 번들 ───────────────────────────────────────────────────────────────
def bundle_for(round_code: str, part_index: int) -> str:
    """편 번호(0-base) → 번들 코드. `m01` + 0 → `m01-1`."""
    no = paths.parse_round_code(round_code)
    if no is None:
        raise ValueError(f"회차 코드가 아닙니다: {round_code}")
    return "m%02d-%d" % (no, part_index + 1)


# ── Page[] → metas ──────────────────────────────────────────────────────────
def metas_from_pages(pages: List[Any]) -> List[Dict[str, Any]]:
    """변환기의 `Page` 목록 → `bake.build_script()` 가 먹는 `metas`.

    `Page.kind` 는 `"cover"|"problem"|"answer"` 로 이미 같은 어휘를 쓴다.
    한 문항의 같은 종류 장들은 **연이어** 나오므로 이어지는 묶음이 곧 `page/pages` 다.
    """
    out: List[Dict[str, Any]] = []
    i = 0
    while i < len(pages):
        p = pages[i]
        key = (p.kind, int(getattr(p, "q_no", 0) or 0))
        j = i
        while j < len(pages):
            q = pages[j]
            if (q.kind, int(getattr(q, "q_no", 0) or 0)) != key:
                break
            j += 1
        n = j - i
        for k in range(n):
            out.append({
                "kind": p.kind,
                "number": None if p.kind == "cover" else key[1],
                "page": k + 1, "pages": n,
            })
        i = j
    return out


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1048576)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def page_rows(pages: List[Any]) -> List[Dict[str, Any]]:
    """문항별 장수 표의 재료 — 문제 n장 · 해설 m장 · 배율 · 채움(문제/해설 따로).

    ★ **채움을 문제 면과 해설 면으로 가른다**(2026-09-10 지시). 전에는 그 문항의
      모든 장을 통째로 평균냈다 — 문제 2장·해설 1장이면 셋을 섞은 값 하나가
      나왔고, 그래서 *"이게 문제편을 채운건지 뭔지를 몰라서"* 가 되었다.

      사람이 보는 것은 **문제 면**이다. 해설 면은 낭독을 따라 빠르게 넘어가므로
      비어도 크게 상관이 없다. 그래서 `fill` 은 문제 면 값으로 두고(인쇄표도 이
      열쇠를 읽는다), 해설은 `fill_a` 로 따로 낸다.
    """
    rows: Dict[int, Dict[str, Any]] = {}
    for p in pages:
        if p.kind == "cover":
            continue
        no = int(getattr(p, "q_no", 0) or 0)
        r = rows.setdefault(no, {"no": no, "problem": 0, "answer": 0,
                                 "scale": 1.0, "_fill_p": [], "_fill_a": []})
        if p.kind in ("problem", "answer"):
            r[p.kind] += 1
        r["scale"] = round(float(getattr(p, "scale", 1.0) or 1.0), 3)
        if getattr(p, "budget_px", 0) and p.kind in ("problem", "answer"):
            key = "_fill_p" if p.kind == "problem" else "_fill_a"
            r[key].append(p.used_px / p.budget_px)
    out = []
    for no in sorted(rows):
        r = rows[no]
        fp, fa = r.pop("_fill_p"), r.pop("_fill_a")
        r["fill"] = round(sum(fp) / len(fp), 3) if fp else 0.0      # 문제 면
        r["fill_a"] = round(sum(fa) / len(fa), 3) if fa else 0.0    # 해설 면
        out.append(r)
    return out


# ── 문항별 장수 지정 (③의 표) ───────────────────────────────────────────────
# ★ 사람이 확정하는 자리는 **여기**다. PowerPoint 에서 장을 합치는 것이 아니다 —
#   숫자를 고쳐야 씬·낭독·이미지가 같이 따라온다.

def read_want(round_code: str) -> Dict[int, Dict[str, int]]:
    """`_deck-export/NN회.pages.json` → {문번: {"problem": n, "answer": m}}.

    ☑(`lock`) 을 찍은 문항만 지킨다. 안 찍은 줄은 변환기 판단을 다시 따른다 —
    발문이 바뀌었는데 옛 장수에 묶여 잘리는 일이 없게.
    """
    p = paths.round_pages_json(round_code)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[int, Dict[str, int]] = {}
    for r in doc.get("questions") or []:
        if not r.get("lock"):
            continue
        try:
            no = int(r["no"])
        except (KeyError, TypeError, ValueError):
            continue
        w = {}
        for k in ("problem", "answer"):
            try:
                v = int(r.get(k) or 0)
            except (TypeError, ValueError):
                v = 0
            if v > 0:
                w[k] = v
        if w:
            out[no] = w
    return out


def save_pages_table(round_code: str, rows: List[Dict[str, Any]],
                     book: str = "") -> Dict[str, Any]:
    """③의 표를 저장한다. 다음 [다시 만들기] 가 이 값을 지킨다."""
    clean = []
    for r in rows:
        try:
            no = int(r["no"])
        except (KeyError, TypeError, ValueError):
            continue
        def _n(k):
            try:
                return max(1, min(9, int(r.get(k) or 1)))
            except (TypeError, ValueError):
                return 1
        clean.append({"no": no, "problem": _n("problem"),
                      "answer": _n("answer"), "lock": bool(r.get("lock"))})
    clean.sort(key=lambda x: x["no"])
    with paths.using_book(book):
        p = paths.round_pages_json(round_code)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        atomic_write_json(p, {
            "version": "1.0", "round": round_code,
            "_": "☑(lock) 을 찍은 문항만 지킨다. 안 찍은 줄은 변환기 판단을 따른다.",
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "questions": clean,
        }, indent=2, trailing_newline=True)
    return {"round": round_code, "saved": len(clean),
            "locked": sum(1 for r in clean if r["lock"]),
            "path": paths.rel(p)}


def pages_table(round_code: str, book: str = "") -> Dict[str, Any]:
    """③의 표 — 방금 만든 결과 + 사람이 찍어 둔 ☑ 를 합쳐서 준다."""
    with paths.using_book(book):
        want_doc: Dict[int, Dict[str, Any]] = {}
        p = paths.round_pages_json(round_code)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    for r in (json.load(f).get("questions") or []):
                        want_doc[int(r["no"])] = r
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                want_doc = {}

        rows: List[Dict[str, Any]] = []
        missed: List[Dict[str, Any]] = []
        for b in bundles_of(round_code):
            gp = paths.bundle_pages(b)
            if not os.path.isfile(gp):
                continue
            try:
                with open(gp, encoding="utf-8") as f:
                    doc = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            missed.extend(doc.get("page_missed") or [])
            for q in doc.get("questions") or []:
                w = want_doc.get(int(q["no"])) or {}
                rows.append({
                    "no": int(q["no"]), "bundle": b,
                    # ★ 화면에도 **파일 이름**을 준다(2026-09-10 지시). 검수는
                    #   PowerPoint 를 열어 놓고 하는데 `m01-2` 는 그 창 어디에도
                    #   안 보인다 — 종이표가 2026-08-25 에 같은 이유로 바뀌었다.
                    "file": os.path.splitext(paths.pptx_name(b))[0],
                    "problem": int(q.get("problem") or 0),
                    "answer": int(q.get("answer") or 0),
                    "scale": q.get("scale") or 1.0,
                    "fill": q.get("fill") or 0.0,        # 문제 면
                    "fill_a": q.get("fill_a") or 0.0,    # 해설 면
                    "lock": bool(w.get("lock")),
                    "want_problem": int(w.get("problem") or 0),
                    "want_answer": int(w.get("answer") or 0),
                })
        rows.sort(key=lambda x: x["no"])
        bad = {(int(m["no"]), m["kind"]) for m in missed}
        for r in rows:
            r["missed"] = [k for k in ("problem", "answer")
                           if (r["no"], k) in bad]
        return {"round": round_code, "questions": rows,
                "slides": sum(r["problem"] + r["answer"] for r in rows),
                "missed": missed,
                "scale": spec_scale()}


# ── 코드펜스 오용 찾기 ──────────────────────────────────────────────────────
# ★ 왜 있나(2026-08-25 실측). SQLD 01회 30번의 `ㄱ.ㄴ.ㄷ.ㄹ.` 보기나열이 문항
#   데이터에서 ```text 펜스로 싸여 있었다. 그러면 **코드블록**으로 간다 —
#   검은 바탕 · 고정폭 · 10pt(본문 지문은 11pt, 발문은 16pt)라서 "폰트가 작게
#   나온다" 로 보이고, Consolas 에 한글이 없어 자모가 두부(▯)로 나갔다.
#
#   글꼴은 렌더러에서 고쳤지만(`pptx_render._set_font` 의 `a:ea`), **코드가 아닌 것을
#   코드로 싸 둔 것 자체가 원인**이다. 그건 데이터에서 고쳐야 하므로 여기서는
#   **찾아서 이름을 불러 준다** — 다음 빌드에서 리포트에 뜬다.
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
# 한국어 **문장**으로 끝나는 줄인가. `…된다.` `…있다.` `…무엇인가?`
SENTENCE_END = re.compile(r"[가-힣][.?!]\s*$")
# 이 아래면 한글이 없다시피 한 것 — 코드다.
PROSE_HANGUL = 0.30
# 줄의 이만큼이 문장으로 끝나면 글이다.
PROSE_LINES = 0.40
# 문장으로 안 끝나도 한글이 이만큼이면 글이다(표 설명·항목 나열).
PROSE_HANGUL_SURE = 0.60


def looks_like_prose(text: str) -> bool:
    """코드박스에 든 글인가.

    ★ **낱말로 가르지 않는다.** 처음에는 `SELECT`·`JOIN` 같은 코드 낱말이 있으면
      코드로 봤는데, SQLD 는 한글 문장 안에 `Hash Join` 이 그냥 들어간다 —
      정작 신고된 01회 30번(`ㄱ. … 해시 테이블(Build Input)이 된다.`)을 놓쳤다.
      **글의 모양**으로 가른다: 한글이 얼마나 되는가, 줄이 문장으로 끝나는가.
    """
    lines = [l for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return False
    han = len(HANGUL.findall(text)) / max(1, len(text))
    if han < PROSE_HANGUL:
        return False
    ends = sum(1 for l in lines if SENTENCE_END.search(l.rstrip())) / len(lines)
    return ends >= PROSE_LINES or han >= PROSE_HANGUL_SURE


def code_blocks_that_are_prose(parts) -> List[Dict[str, Any]]:
    """코드블록인데 한글 문장인 것 — 문항 번호와 첫 줄을 돌려준다."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for part in parts:
        for pg in part.pages:
            for b in pg.blocks:
                if b.kind != "pre":
                    continue
                text = "\n".join(b.paras or [])
                if not text.strip():
                    continue
                if not looks_like_prose(text):
                    continue
                key = (int(getattr(pg, "q_no", 0) or 0), text[:30])
                if key in seen:
                    continue
                seen.add(key)
                out.append({"no": key[0], "kind": pg.kind,
                            "head": text.strip().splitlines()[0][:60]})
    return sorted(out, key=lambda x: x["no"])


# ── 본체 ────────────────────────────────────────────────────────────────────
def build_round(round_code: str, *, scale: Optional[float] = None,
                rebake: bool = False, book: str = "",
                log=None) -> Dict[str, Any]:
    """회차 하나를 통째로 처리한다. 반쯤 만들어진 상태가 남지 않게 한 번에 끝낸다."""
    say = log or (lambda *_a, **_k: None)
    with paths.using_book(book):
        return _build_round(round_code, scale=scale, rebake=rebake, say=say)


def _build_round(round_code: str, *, scale, rebake, say) -> Dict[str, Any]:
    from vendor.exam2deck import build as e2d
    from vendor.exam2deck import pptx_render, svg_raster

    # 1) deck.html 최신화
    if rebake:
        for b in bundles_of(round_code):
            say("[굽기] %s" % b)
            bake.bake_one(b)

    # 2) 회차 하나로 합치기
    merged = rounddeck.write_round(round_code)
    say("[합침] %s — 편 %d · 장 %d"
        % (merged["rel"], merged["parts"], merged["slides"]))

    # 3) 변환기
    per_bundle = _per_bundle()
    opt = e2d.Options(
        exam=exam_label(),
        part_size=per_bundle,
        repeat_opts=spec_repeat_opts(),
        scale=spec_scale() if scale is None else max(0.5, min(3.0, float(scale))),
        template=TEMPLATE if os.path.isfile(TEMPLATE) else None,
        fig_cache=paths.figcache_dir(),
        page_want=read_want(round_code),
    )
    spec = e2d.apply_template(opt)
    say("[규격] %s · 배율 %s%s"
        % (spec.get("source"), opt.scale,
           " · 장수 지정 %d문항" % len(opt.page_want) if opt.page_want else ""))

    with svg_raster.Raster(opt.fig_cache) as raster:
        built = e2d.build_pages(merged["path"], opt, raster)
    if built.unknown:
        # ★ 못 알아본 요소는 **버려진 내용**이다. 조용히 넘기지 않는다.
        say("[경고] 못 알아본 요소: %s" % built.unknown)

    n_parts = len(built.parts)
    want = max(1, int(math.ceil(_round_items() / float(per_bundle))))
    if n_parts != want:
        raise ValueError(
            "%s: 편이 %d개 나왔습니다 — 시험정보 기준 %d개여야 합니다"
            "(회차 %d문항 ÷ 편당 %d문항). 문항이 빠졌거나 "
            "`video.problems_per_bundle` 이 틀렸습니다."
            % (round_code, n_parts, want, _round_items(), per_bundle))

    # 4) 편마다 pptx + pages.json + script
    files: List[Dict[str, Any]] = []
    all_pages: List[Any] = []
    drifted: List[str] = []
    for part in built.parts:
        bundle = bundle_for(round_code, part.index)
        rng = paths.bundle_range(bundle)
        body = [p for p in part.pages if p.kind != "cover"]
        if rng and body:
            lo, hi = rng
            got = (min(int(p.q_no) for p in body), max(int(p.q_no) for p in body))
            if got != (lo, hi):
                raise ValueError(
                    "%s: 편↔번들이 어긋납니다 — 번들은 %d~%d번인데 편 %d 에는 "
                    "%d~%d번이 들어 있습니다."
                    % (bundle, lo, hi, part.index + 1, got[0], got[1]))

        out = paths.bundle_pptx(bundle)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        pptx_render.render(part.pages, out, template=opt.template)
        metas = metas_from_pages(part.pages)

        info = bake.write_script(bundle, metas)
        if info.get("speech_drifted"):
            drifted.append("%s:%s" % (bundle, info["speech_drifted"]))

        rep = e2d.report(bundle, part.pages)
        atomic_write_json(paths.bundle_pages(bundle), {
            "version": "1.0", "bundle": bundle, "round": round_code,
            "part_index": part.index, "label": part.label,
            "scale": opt.scale, "repeat_opts": opt.repeat_opts,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "pptx": os.path.basename(out), "pptx_sha256": _sha256(out),
            "slides": len(part.pages),
            "capture_scenes": info["capture"],
            "fill_median": rep["fill_median"], "fill_min": rep["fill_min"],
            "under_40pct": rep["under_40pct"], "overflow": rep["overflow"],
            "questions": page_rows(part.pages),
            "page_missed": [m for m in built.page_missed
                            if lo_hi_has(rng, m.get("no"))],
            "metas": metas,
        }, indent=2, trailing_newline=True)

        # ★ 하드 게이트. 셋이 같지 않으면 영상이 어긋난다.
        if not (len(part.pages) == len(metas) == info["capture"]):
            raise ValueError(
                "%s: 1:1 이 깨졌습니다 — pptx 장 %d · metas %d · 캡처 씬 %d"
                % (bundle, len(part.pages), len(metas), info["capture"]))

        all_pages.extend(part.pages)
        files.append({"bundle": bundle, "name": os.path.basename(out),
                      "rel": paths.rel(out), "label": part.label,
                      "slides": len(part.pages),
                      "size_kb": os.path.getsize(out) // 1024,
                      "fill_median": rep["fill_median"]})
        say("[편 %d/%d] %s  장 %3d  채움 %.2f  %dKB"
            % (part.index + 1, n_parts, bundle, len(part.pages),
               rep["fill_median"], files[-1]["size_kb"]))

    prose = code_blocks_that_are_prose(built.parts)
    if prose:
        say("[경고] 코드블록인데 한글 문장인 곳 %d건 — 문항 데이터의 ```` ``` ```` "
            "펜스를 지우면 지문으로 나갑니다(글자가 커지고 검은 바탕이 사라집니다): "
            % len(prose)
            + ", ".join("%s번 「%s…」" % (x["no"], x["head"][:24]) for x in prose[:6]))

    if built.page_missed:
        say("[경고] 장수를 못 맞춘 문항: %s"
            % ", ".join("%s번 %s %d→%d" % (m["no"], m["kind"], m["want"], m["got"])
                        for m in built.page_missed))

    rep = e2d.report(round_code, all_pages)
    rep.update(page_missed=built.page_missed, prose_code=prose,
               round=round_code, parts=n_parts, units=built.n_units,
               unknown_elements=built.unknown, files=files,
               scale=opt.scale, spec=spec.get("source", ""),
               source=merged["rel"], source_slides=merged["slides"],
               speech_drifted=drifted)
    if drifted:
        say("[경고] 발음 덮어쓰기를 못 쓴 씬: %s" % drifted)
    return rep


def lo_hi_has(rng, no) -> bool:
    try:
        return bool(rng) and rng[0] <= int(no) <= rng[1]
    except (TypeError, ValueError):
        return False


def bundles_of(round_code: str) -> List[str]:
    out = []
    for b in paths.all_bundles():
        parsed = paths.parse_bundle(b)
        if parsed and paths.round_code(parsed[0]) == round_code:
            out.append(b)
    return out


def _per_bundle() -> int:
    return bake._per_bundle()


def _round_items() -> int:
    return bake._round_items()


# ── 씬만 다시 매기기 ────────────────────────────────────────────────────────
def rescript_bundle(bundle: str) -> Dict[str, Any]:
    """pptx 는 그대로 두고 `pages.json` 의 metas 로 script 만 다시 쓴다.

    ★ 낭독 규칙(`bake.split_narration`)이나 발음 사전이 바뀌었을 때 쓴다. 슬라이드를
      다시 그릴 이유가 없으므로 pptx 를 건드리지 않는다 — 사람이 손질해 둔 것이 있으면
      그것도 살아 있는다.
    """
    gp = paths.bundle_pages(bundle)
    if not os.path.isfile(gp):
        raise FileNotFoundError(
            "%s: pages.json 이 없습니다 — 먼저 [슬라이드 만들기] 를 돌리세요." % bundle)
    with open(gp, encoding="utf-8") as f:
        doc = json.load(f)
    metas = doc.get("metas") or []
    info = bake.write_script(bundle, metas)
    if len(metas) != info["capture"]:
        raise ValueError("%s: 1:1 이 깨졌습니다 — metas %d · 캡처 씬 %d"
                         % (bundle, len(metas), info["capture"]))
    return info


def rescript_round(round_code: str, *, book: str = "", log=None) -> List[Dict[str, Any]]:
    say = log or (lambda *_a, **_k: None)
    out = []
    with paths.using_book(book):
        for b in bundles_of(round_code):
            info = rescript_bundle(b)
            out.append(info)
            say("[씬] %s  %d씬 (캡처 %d)" % (b, info["scenes"], info["capture"]))
    return out


# ── 화면이 읽는 상태 ────────────────────────────────────────────────────────
def bundle_status(bundle: str) -> Dict[str, Any]:
    """번들 하나의 강의덱 상태 — pptx 유무 · 장수 · 채움 · 손질 · 이미지."""
    pp, gp = paths.bundle_pptx(bundle), paths.bundle_pages(bundle)
    st: Dict[str, Any] = {"bundle": bundle, "pptx": False, "pages": False,
                          "slides": 0, "fill_median": 0.0, "touched": False,
                          "slides_changed": False, "images": False,
                          "images_stale": False, "built_at": ""}
    now = ""
    if os.path.isfile(pp):
        st["pptx"] = True
        st["pptx_kb"] = os.path.getsize(pp) // 1024
        now = _sha256(pp)
    if not os.path.isfile(gp):
        return st
    try:
        with open(gp, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return st
    st.update(pages=True, slides=int(doc.get("slides") or 0),
              fill_median=doc.get("fill_median") or 0.0,
              under_40pct=doc.get("under_40pct") or 0,
              overflow=len(doc.get("overflow") or []),
              scale=doc.get("scale") or 1.0,
              built_at=doc.get("built_at") or "",
              questions=doc.get("questions") or [])
    if st["pptx"]:
        st["touched"] = bool(doc.get("pptx_sha256")) and now != doc["pptx_sha256"]
        if st["touched"]:
            st["slides_changed"] = pptx_slide_count(pp) != st["slides"]
    mf = paths.bundle_images_manifest(bundle)
    if os.path.isfile(mf):
        try:
            with open(mf, encoding="utf-8") as f:
                m = json.load(f)
            st["images"] = True
            st["images_stale"] = m.get("pptx_sha256") != now
            st["images_count"] = len(m.get("scene_index") or [])
        except (OSError, json.JSONDecodeError):
            pass
    return st


def pptx_slide_count(path: str) -> int:
    from pptx import Presentation
    try:
        return len(Presentation(path).slides)
    except Exception:                                        # noqa: BLE001
        return -1


def round_status(round_code: str, book: str = "") -> Dict[str, Any]:
    with paths.using_book(book):
        rows = [bundle_status(b) for b in bundles_of(round_code)]
    return {"round": round_code, "bundles": rows,
            "pptx": sum(1 for r in rows if r["pptx"]),
            "slides": sum(r["slides"] for r in rows),
            "images": sum(1 for r in rows if r["images"]),
            "touched": sum(1 for r in rows if r["touched"])}
