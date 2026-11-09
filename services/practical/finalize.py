# -*- coding: utf-8 -*-
"""실기 확정 — 검수한 회차를 **문항마다 한 파일**로 굳힌다.

  01/practical/{RR}-{P}-{NN}.md    사람이 읽는 원고(지시사항 · 자료 표 · 그림 · 정답)
  01/practical/{RR}-{P}-{NN}.json  다음 단계(변형 생성기)가 읽는 구조
  01/practical/images/…png         스캔에서 자른 그림

★ 필기의 `01/{RR}-{NN}.md` 와 **다른 폴더**에 둔다. 필기 쪽 도구(스캔 정리·게이트·집필)는
  01/*.md 를 보기·정답이 있는 문항으로 읽는다 — 섞이면 거기서 깨진다.

★ 확정은 **쪽이 아니라 회차를 다시 쓴다.** 한 문항의 지시사항과 정답이 여러 쪽에 흩어져
  있어서, 정답 쪽 하나를 고쳐도 그 문항 파일이 바뀌어야 한다. 묶는 규칙은 review.py.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

from core.atomic_io import atomic_write_text
from services.book import paths
from services.ocr import project
from services.practical import review


def out_dir() -> str:
    return os.path.join(paths.book_dir(), "01", "practical")


def _crop(src: str, page: int, bbox: list, name: str) -> str:
    from PIL import Image
    d = os.path.join(out_dir(), "images")
    os.makedirs(d, exist_ok=True)
    x, y, w, h = bbox
    with Image.open(project.scan_png(src, page)) as im:
        im.crop((x, y, x + w, y + h)).save(os.path.join(d, name), format="PNG")
    return f"images/{name}"


BLOCK_RE = re.compile(r"\{\{(b-\d+)\}\}")


def _asset_md(asset: dict, img: str) -> List[str]:
    if asset.get("type") == "table":
        return [(asset.get("md") or "").strip(), ""]
    if img:
        return [f"![{asset.get('note') or '그림'}]({img})", ""]
    return []


def _lines_md(lines: List[str], token_re, lookup) -> List[str]:
    """줄을 인쇄된 그대로 쓰고, 이름표 줄은 그 자리에 자산을 펼친다.
    원문자 항목 아래 딸린 ▶ 줄만 들여쓴다. 앱이 기호를 덧붙이지 않는다."""
    out, under, used = [], False, set()
    for raw in lines or []:
        s = str(raw).strip()
        text = token_re.sub("", s).strip()
        if text[:1] and ("\u2460" <= text[0] <= "\u2473" or "\u2776" <= text[0] <= "\u277f"):
            under = True
        elif text and not text.startswith(("▶", "※")):
            under = False
        for k, part in enumerate(token_re.split(s)):
            if k % 2 == 1:
                used.add(part)
                out += [""] + lookup(part)
            elif part.strip():
                out.append(("&emsp;" if under and part.strip().startswith(("▶", "※")) else "")
                           + part.strip() + "  ")
    return out, used


def _md(rnd: int, it: Dict[str, Any], stem: str, src: str) -> tuple:
    """문항 하나의 원고 + 그린 그림 목록."""
    from services.practical.review import TOKEN_RE
    imgs: List[str] = []
    p0 = (it["problems"] or [{}])[0]
    out = [f"# {rnd:02d}회 문제{it['part']}-{it['no']}"
           + (f" ({p0.get('points')}점)" if p0.get("points") is not None else ""), ""]
    for qi, p in enumerate(it["problems"]):
        assets = p.get("assets") or {}
        cache: Dict[str, str] = {}

        def look(aid, assets=assets, cache=cache, qi=qi):
            a = assets.get(aid)
            if not a:
                return [f"({{{{{aid}}}}} — 없는 자산)", ""]
            img = ""
            if a.get("type") == "figure" and a.get("bbox"):
                img = cache.get(aid) or _crop(src, int(a["page"]), a["bbox"], f"{stem}-q{qi + 1}-{aid}.png")
                cache[aid] = img
                imgs.append(img)
            return _asset_md(a, img)

        out += [f"**{p.get('lead') or ''}**", ""]
        body, used = _lines_md(p.get("instructions") or [], TOKEN_RE, look)
        out += body + [""]
        for aid in assets:                      # 이름표가 없는 자산은 맨 끝에
            if aid not in used:
                out += look(aid)
    a = it.get("answer")
    out += ["## 정답", ""]
    aimgs: List[str] = []
    if not a:
        out += ["(정답 없음)", ""]
    else:
        for f in a["formulas"]:
            out.append(f"- `{(f.get('cell') + ' : ') if f.get('cell') else ''}{f['formula']}`")
        if a["settings"]:
            out += ["", "| 대화상자 | 항목 | 값 |", "|---|---|---|"]
            out += [f"| {s.get('dialog') or ''} | {s.get('field') or ''} | {(s.get('value') or '').replace('|', chr(92) + '|')} |"
                    for s in a["settings"]]
        if a["code"]:
            out += ["", "```vb", a["code"], "```"]
        blocks = a.get("blocks") or []

        def blook(bid):
            b = blocks[int(bid[2:])] if int(bid[2:]) < len(blocks) else None
            if not b:
                return []
            img = ""
            if b.get("type") == "figure" and b.get("bbox"):
                img = _crop(src, int(b["page"]), b["bbox"], f"{stem}-a{bid[2:]}.png")
                aimgs.append(img)
            return _asset_md(b, img)

        if a["steps"]:
            out += ["", "### 풀이 절차", ""]
            body, _ = _lines_md(a["steps"], BLOCK_RE, blook)
            out += body
        for i, b in enumerate(blocks):
            if b.get("tail"):
                out += [""] + blook(f"b-{i}")
    return "\n".join(out).rstrip() + "\n", imgs, aimgs


def finalize_round(src: str, rnd: int) -> dict:
    data = review.round_items(src, rnd)
    os.makedirs(out_dir(), exist_ok=True)
    wrote, skipped = [], []
    for it in data["items"]:
        if not it["problems"] or not it["part"] or not it["no"]:
            skipped.append(f"{it['part']}-{it['no']} ({', '.join(it['flags']) or '문제 없음'})")
            continue
        stem = f"{rnd:02d}-{it['part']}-{it['no']:02d}"
        md, figs, afigs = _md(rnd, it, stem, src)
        doc = {"round": rnd, "part": it["part"], "no": it["no"], "source_pdf": f"{src}.pdf",
               "problems": it["problems"], "answer": it.get("answer"), "flags": it["flags"],
               "verified": it.get("verified", False), "figures": figs, "answer_figures": afigs}
        atomic_write_text(os.path.join(out_dir(), stem + ".json"), json.dumps(doc, ensure_ascii=False, indent=2))
        atomic_write_text(os.path.join(out_dir(), stem + ".md"), md)
        wrote.append(stem)
    return {"round": rnd, "dir": out_dir(), "wrote": wrote, "skipped": skipped}
