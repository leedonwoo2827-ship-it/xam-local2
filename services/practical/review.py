# -*- coding: utf-8 -*-
"""실기 검수 — 쪽 단위 판독을 **문항 단위**로 묶는다.

판독은 쪽마다 하지만 사람이 보는 단위는 문항이다. 한 문항의 지시사항이 두 쪽에 걸치고,
정답·해설은 여러 쪽에 조각으로 나뉜다(실측 컴활2급 01회: 조건부 서식 정답이 p.7·p.8,
계산작업 정답이 p.9 의 결과 그림과 p.10 의 수식으로 갈렸다).

묶는 규칙
  - 회차는 `read.page_table()` 이 정한 값(사람이 고친 값 > 인쇄 > 이어받기)을 쓴다.
  - 묶음(part)이 비면 **같은 회차 앞 항목의 묶음**을 이어받는다.
  - 정답 조각에 번호(no)가 없으면 **바로 앞 정답의 이어짐**으로 본다.
  - 같은 (묶음, 번호)의 문제가 둘이면 합치지 않고 「번호 겹침」 으로 표시한다 —
    판독이 묶음을 잘못 붙인 경우다(실측 p.4 '분석작업-2' 가 문제4-2 로 읽혔다).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from services.practical import read as pread


TOKEN_RE = re.compile(r"\{\{([tp]-\d+)\}\}")


def assets_of(x: dict, page: int) -> Dict[str, dict]:
    """카드의 자산(이름표 → 자료 표/그림). 옛 판독의 figure_table · figure_bbox 도 t-1 · p-1 로 읽는다.

    화면(practicalReview.js 의 ensureAssets)과 같은 규칙이다. 그림의 쪽은 없으면 카드의 쪽.
    """
    out = {k: dict(v) for k, v in (x.get("assets") or {}).items() if isinstance(v, dict)}

    def nid(prefix: str) -> str:
        n = 1
        while f"{prefix}-{n}" in out:
            n += 1
        return f"{prefix}-{n}"

    if x.get("figure_table"):
        out[nid("t")] = {"type": "table", "md": x["figure_table"]}
    if x.get("figure_bbox"):
        out[nid("p")] = {"type": "figure", "bbox": x["figure_bbox"], "note": x.get("figure") or "",
                         "page": x.get("figure_page") or page}
    for a in out.values():
        if a.get("type") == "figure":
            a.setdefault("page", page)
            a["page"] = int(a.get("page") or page)
    return out


def _key(part: Optional[int], no: Optional[int]) -> Tuple[int, int]:
    return (int(part or 0), int(no or 0))


def round_items(src: str, rnd: int) -> Dict[str, Any]:
    rows = [r for r in pread.page_table(src) if r["read"] and r["round"] == rnd]
    probs: Dict[Tuple[int, int], List[dict]] = {}
    ans: Dict[Tuple[int, int], dict] = {}
    order: List[Tuple[int, int]] = []

    last_part: Optional[int] = None
    for r in rows:
        if r["kind"] != "문제":
            continue
        d = pread.load(src, r["page"]) or {}
        for idx, it in enumerate(d.get("problem_items") or []):
            part = it.get("part") or last_part
            last_part = part
            k = _key(part, it.get("no"))
            probs.setdefault(k, []).append(dict(it, part=part, page=r["page"], idx=idx,
                                                assets=assets_of(it, r["page"])))
            if k not in order:
                order.append(k)

    last_part, last_key = None, None
    for r in rows:
        if r["kind"] != "정답":
            continue
        d = pread.load(src, r["page"]) or {}
        for e in d.get("answer_entries") or []:
            part = e.get("part") or last_part
            if e.get("no") is None and last_key is not None:
                k = last_key                      # 번호 없는 조각 = 앞 정답의 이어짐
            else:
                k = _key(part, e.get("no"))
            last_part, last_key = (k[0] or part), k
            a = ans.setdefault(k, {"titles": [], "kinds": [], "formulas": [], "settings": [],
                                   "code": "", "steps": [], "notes": [], "pages": [], "figures": [],
                                   "blocks": [], "verified": True})
            a["verified"] = a["verified"] and bool(e.get("verified"))
            # ★ 정답 조각마다 이름표가 p-1 부터라 합치면 겹친다 — 합친 정답의 블록 번호 {{b-N}} 로 바꾼다.
            #   이름표가 없는 자산은 「맨 끝」 블록(tail)으로 남긴다.
            ea = assets_of(e, r["page"])
            remap: Dict[str, str] = {}
            for aid, asset in ea.items():
                remap[aid] = f"b-{len(a['blocks'])}"
                a["blocks"].append(dict(asset, tail=True))
            steps = []
            for line in e.get("steps") or []:
                def _sub(m):
                    b = remap.get(m.group(1))
                    if b is None:
                        return m.group(0)
                    a["blocks"][int(b[2:])]["tail"] = False
                    return "{{" + b + "}}"
                steps.append(TOKEN_RE.sub(_sub, str(line)))
            e = dict(e, steps=steps)
            if e.get("title"):
                a["titles"].append(pread.white_circled(e["title"]))
            if e.get("kind") and e["kind"] not in a["kinds"]:
                a["kinds"].append(e["kind"])
            for f in e.get("formulas") or []:
                if f not in a["formulas"]:
                    a["formulas"].append(f)
            a["settings"] += e.get("settings") or []
            if e.get("code"):
                a["code"] += ("\n" if a["code"] else "") + e["code"]
            a["steps"] += e.get("steps") or []
            if e.get("note"):
                a["notes"].append(e["note"])
            if r["page"] not in a["pages"]:
                a["pages"].append(r["page"])
            if k not in order:
                order.append(k)

    for a in ans.values():
        a["figures"] = [{"page": b["page"], "bbox": b["bbox"]} for b in a["blocks"]
                        if b.get("type") == "figure" and b.get("bbox")]

    items = []
    for k in sorted(order):
        ps = probs.get(k) or []
        a = ans.get(k)
        flags = []
        if not ps:
            flags.append("문제 없음")
        if len(ps) > 1:
            flags.append("번호 겹침")
        if not a:
            flags.append("정답 없음")
        elif not (a["formulas"] or a["settings"] or a["code"] or a["steps"]):
            flags.append("정답 내용 없음")
        if ps and ps[0].get("points") is None:
            flags.append("배점 없음")
        if k[0] == 0 or k[1] == 0:
            flags.append("번호 모름")
        # 문제 조각과 정답 조각이 **모두** 대조완료여야 문항이 대조완료다
        verified = bool(ps) and all(p.get("verified") for p in ps) and bool(a) and a["verified"]
        items.append({"part": k[0], "no": k[1], "problems": ps, "answer": a, "flags": flags,
                      "verified": verified})
    return {"src": src, "round": rnd, "items": items,
            "pages": [{"page": r["page"], "kind": r["kind"]} for r in rows]}


def fix_item(src: str, page: int, idx: int, *, part: Optional[int] = None,
             no: Optional[int] = None, points: Optional[int] = None,
             figure_bbox: Any = "keep") -> dict:
    """문제 하나의 묶음·번호·배점·그림 영역만 고친다 — 검수 카드에서 바로 푸는 길.

    `figure_bbox` 는 스캔에서 사람이 드래그한 `[x,y,w,h]`(원본 픽셀). None 이면 지운다.
    """
    d = pread.load(src, page)
    items = (d or {}).get("problem_items") or []
    if not (0 <= idx < len(items)):
        raise ValueError(f"p.{page} 에 {idx + 1}번째 문항이 없습니다.")
    it = items[idx]
    if part is not None:
        it["part"] = int(part)
    if no is not None:
        it["no"] = int(no)
    if points is not None:
        it["points"] = int(points) if int(points) > 0 else None
    if figure_bbox != "keep":
        if figure_bbox is None:
            it.pop("figure_bbox", None)
        else:
            from PIL import Image
            from services.ocr import project
            from services.ocr.readpage import _bbox
            with Image.open(project.scan_png(src, page)) as im:
                bb = _bbox(figure_bbox, im.size)
            if not bb:
                raise ValueError("그림 영역이 너무 작거나 페이지 밖입니다 — 다시 드래그하세요.")
            it["figure_bbox"] = bb
    d["_edited"] = True
    pread.save(src, page, d)
    return it


def rounds(src: str) -> List[dict]:
    out: Dict[int, dict] = {}
    for r in pread.page_table(src):
        if not r["read"] or not r["round"]:
            continue
        e = out.setdefault(r["round"], {"round": r["round"], "pages": 0, "items": 0, "answers": 0})
        e["pages"] += 1
        e["items"] += r["n_items"] if r["kind"] == "문제" else 0
        e["answers"] += r["n_answers"] if r["kind"] == "정답" else 0
    return [out[k] for k in sorted(out)]
