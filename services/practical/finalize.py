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


def _md(rnd: int, it: Dict[str, Any], figs: List[str], afigs: List[str]) -> str:
    p0 = (it["problems"] or [{}])[0]
    out = [f"# {rnd:02d}회 문제{it['part']}-{it['no']}"
           + (f" ({p0.get('points')}점)" if p0.get("points") is not None else ""), ""]
    for p in it["problems"]:
        out += [f"**{p.get('lead') or ''}**", ""]
        # ★ 적힌 줄을 **그대로** 쓴다 — 목록 기호(- )나 ▶ 를 앱이 덧붙이지 않는다(2026-11-08 지시:
        #   "강제로는 제가 넣을 테니 기본값은 빼 주세요"). 원문자 항목 아래 딸린 ▶ 줄만 들여쓴다.
        #   줄 끝 공백 두 칸 = 마크다운 줄바꿈.  지정 함수는 JSON 에만 둔다(본문에 줄을 만들지 않는다).
        under = False
        for s in (p.get("instructions") or []):
            s = str(s).strip()
            if s[:1] and ("①" <= s[0] <= "⑳" or "❶" <= s[0] <= "❿"):
                under = True
            elif not s.startswith(("▶", "※")):
                under = False
            out.append(("&emsp;" if under and s.startswith(("▶", "※")) else "") + s + "  ")
        out.append("")
        if p.get("figure_table"):
            out += [p["figure_table"].strip(), ""]
    out += [f"![그림]({f})" for f in figs] + ([""] if figs else [])
    a = it.get("answer")
    out += ["## 정답", ""]
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
        if a["steps"]:
            out += ["", "### 풀이 절차", ""] + [f"{i}. {s}" for i, s in enumerate(a["steps"], 1)]
        out += [""] + [f"![결과]({f})" for f in afigs]
    return "\n".join(out).rstrip() + "\n"


def finalize_round(src: str, rnd: int) -> dict:
    data = review.round_items(src, rnd)
    os.makedirs(out_dir(), exist_ok=True)
    wrote, skipped = [], []
    for it in data["items"]:
        if not it["problems"] or not it["part"] or not it["no"]:
            skipped.append(f"{it['part']}-{it['no']} ({', '.join(it['flags']) or '문제 없음'})")
            continue
        stem = f"{rnd:02d}-{it['part']}-{it['no']:02d}"
        figs = []
        for k, p in enumerate(it["problems"]):
            if p.get("figure_bbox"):
                figs.append(_crop(src, int(p.get("figure_page") or p["page"]), p["figure_bbox"],
                                  f"{stem}-q{k + 1}.png"))
        afigs = []
        for k, f in enumerate((it.get("answer") or {}).get("figures") or []):
            afigs.append(_crop(src, f["page"], f["bbox"], f"{stem}-a{k + 1}.png"))
        doc = {"round": rnd, "part": it["part"], "no": it["no"], "source_pdf": f"{src}.pdf",
               "problems": it["problems"], "answer": it.get("answer"), "flags": it["flags"],
               "verified": it.get("verified", False), "figures": figs, "answer_figures": afigs}
        atomic_write_text(os.path.join(out_dir(), stem + ".json"), json.dumps(doc, ensure_ascii=False, indent=2))
        atomic_write_text(os.path.join(out_dir(), stem + ".md"), _md(rnd, it, figs, afigs))
        wrote.append(stem)
    return {"round": rnd, "dir": out_dir(), "wrote": wrote, "skipped": skipped}
