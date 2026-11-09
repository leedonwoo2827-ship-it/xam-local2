# -*- coding: utf-8 -*-
"""3부 HTML 문제집(실기) — 회차마다 시험지 · 모범답안 해설 · 실습파일을 07/mNN/ 에 굽는다.

  07/mNN/exam.html · exam.pdf        실기 시험지(묶음별 지시사항 + 그림, 보기 없음) — 46배판 1단
  07/mNN/answers.html · answers.pdf  모범답안 해설(제목 · 절차 · 수식 · 그림)
  07/mNN/files/*.xlsx                실습파일(1부 빌드 결과 06/practical/mNN 을 복사)
  07/mNN/assets/*.png                그 회차 그림(1부 빌드가 새로 그린 PNG)
  07/mNN/script/qNN.json             문항별 대본(문제 읽기 read · 풀이 solve — 자막·음성·발음)
  07/mNN/items.json                  문항·배점표(필기의 answers.json 자리 — 실기는 정답 번호가 없다)

★ 필기 ebookexam.py 는 그대로 둔다(local3 와 같은 상태 유지). 판형·PDF 인쇄·자막 접기는 그것을 빌려 쓴다.
★ 대본의 solve 는 모범답안 절차를 그대로 읽는 초벌이다 — 종합본 영상은 녹화 조작 단계(actions.py)가 따로 만든다.
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import shutil
import time
from typing import Any, Dict, List

from core.atomic_io import atomic_write_text
from core.speak import speak_cells, to_speech
from services.book import paths
from services.export import ebookexam as EX
from services.practical import author as pa

TOK = re.compile(r"\{\{(f-\d+)\}\}")
CIRC = re.compile(r"^[①-⑳❶-❿]")


def _h(s) -> str:
    return html.escape("" if s is None else str(s))


def out_dir(m: int) -> str:
    return os.path.join(paths.ebook_dir(), f"m{m:02d}")


def _spec() -> dict:
    from services.authoring import parts
    return parts.active() or {}


def load_items(m: int) -> List[dict]:
    rows = []
    for f in sorted(glob.glob(os.path.join(pa.round_dir(m), f"{m:02d}-[0-9]-[0-9][0-9].json"))):
        with open(f, encoding="utf-8") as fh:
            rows.append(json.load(fh))
    rows.sort(key=lambda j: (int(j.get("part") or 0), int(j.get("no") or 0)))
    return rows


def _stem(j: dict) -> str:
    return f"{int(j['round']):02d}-{int(j['part'])}-{int(j.get('no') or 0):02d}"


# ── 본문 조각 ─────────────────────────────────────────────────────────────
def _fig(j: dict, fid: str, figs: Dict[str, dict], used: set) -> str:
    used.add(fid)
    f = figs.get(fid) or {}
    name = f"{_stem(j)}-{fid}.png"
    src = os.path.join(pa.round_dir(int(j["round"])), "images", name)
    cap = f.get("caption") or ""
    if os.path.isfile(src):
        # PNG 는 2배 해상도로 그렸다(인쇄 선명도) — 표시 폭은 절반으로
        wd = ""
        try:
            from PIL import Image
            with Image.open(src) as im:
                wd = f' width="{im.size[0] // 2}"'
        except Exception:                                    # noqa: BLE001
            pass
        return f'<figure><img src="assets/{_h(name)}" alt="{_h(cap)}"{wd}></figure>'
    if f.get("kind") == "table" and f.get("columns"):
        head = "".join(f"<th>{_h(c)}</th>" for c in f["columns"])
        body = "".join("<tr>" + "".join(f"<td>{_h(v)}</td>" for v in (r or [])) + "</tr>" for r in f.get("rows") or [])
        return f'<figure><table class="t"><tr>{head}</tr>{body}</table></figure>'
    return f'<div class="figph">〔그림 {_h(fid)} — {_h(cap)}〕</div>'


def _lines_html(lines: List[str], j: dict, figs: Dict[str, dict], used: set) -> str:
    out, under = [], False
    for raw in lines or []:
        s = str(raw).strip()
        mt = TOK.fullmatch(s)
        if mt:
            out.append(_fig(j, mt.group(1), figs, used))
            continue
        if CIRC.match(s):
            under = True
        elif s and not s.startswith(("▶", "※")):
            under = False
        cls = "sub" if under and s.startswith(("▶", "※")) else ""
        s2 = TOK.sub(lambda m_: _fig(j, m_.group(1), figs, used), _h(s))
        out.append(f'<p class="{cls}">{s2}</p>')
    return "".join(out)


CSS = """body{font:10.5pt/1.65 'Malgun Gothic',sans-serif;color:#111;background:#fff;margin:0}
.head{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid #222;margin-bottom:10px}
.head h1{font-size:15pt;margin:0 0 4px}.head .m{color:#555}
h2.part{font-size:12pt;margin:16px 0 6px;padding:3px 8px;background:#eef1f5;border-left:4px solid #335}
h2.brk{break-before:page}
.q{margin:0 0 14px;break-inside:auto}
.q .lead{font-weight:700;margin:0 0 4px}
.q p{margin:2px 0}.q p.sub{padding-left:1.6em}
figure{margin:6px 0;break-inside:avoid}figure img{max-width:100%;height:auto}
table.t{border-collapse:collapse;font-size:9pt}table.t td,table.t th{border:1px solid #999;padding:2px 6px}table.t th{background:#eee}
.figph{border:1px dashed #999;color:#666;padding:6px;margin:6px 0;font-size:9pt}
.ans{margin:0 0 16px;break-inside:auto}.ans .t{font-weight:700;margin:6px 0 4px}
.fx{font-family:Consolas,monospace;font-size:9.5pt;background:#f6f6f2;padding:4px 8px;margin:4px 0}
.files{font-size:9pt;color:#444;margin:4px 0 12px}"""


def _doc(title: str, head_right: str, body: str) -> str:
    return ("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
            f"<title>{_h(title)}</title><style>{CSS}{EX._page_css()}</style></head><body>"
            f'<div class="head"><h1>{_h(title)}</h1><span class="m">{_h(head_right)}</span></div>'
            + body + "</body></html>\n")


def exam_html(m: int, items: List[dict], files: List[str]) -> str:
    spec = _spec()
    names = {int(s.get("no") or 0): s for s in spec.get("subjects") or []}
    body, last = [], None
    if files:
        body.append(f'<div class="files">실습파일: {", ".join(_h(f) for f in files if "문제" in f) or _h(files[0])}</div>')
    for j in items:
        p = int(j.get("part") or 0)
        if p != last:
            s = names.get(p) or {}
            pts = f" ({s.get('points')}점)" if s.get("points") else ""
            body.append(f'<h2 class="part{" brk" if last else ""}">문제{p} {_h(s.get("name") or "")}{pts}</h2>')
            last = p
        figs = {f.get("id"): f for f in j.get("figures") or []}
        used: set = set()
        no = int(j.get("no") or 0)
        lead = j.get("lead") or ""
        q = [f'<div class="q" data-no="{p}-{no}">']
        if no:
            q.append(f'<p class="lead">{no}. {_h(lead)}</p>')
        q.append(_lines_html(j.get("instructions") or [], j, figs, used))
        # 지시사항 쪽 그림만(정답 쪽 그림은 해설로) — 이름표가 지시사항에 없던 그림은 넣지 않는다
        q.append("</div>")
        body.append("".join(q))
    label = spec.get("label") or ""
    right = f"모의 {m}회 · {spec.get('time_minutes') or ''}분 · {spec.get('total_points') or 100}점"
    return _doc(f"{label} 모의 {m}회", right, "".join(body))


def answers_html(m: int, items: List[dict]) -> str:
    spec = _spec()
    names = {int(s.get("no") or 0): s.get("name") for s in spec.get("subjects") or []}
    body, last = [], None
    for j in items:
        p, no = int(j.get("part") or 0), int(j.get("no") or 0)
        if p != last:
            body.append(f'<h2 class="part{" brk" if last else ""}">문제{p} {_h(names.get(p) or "")}</h2>')
            last = p
        a = j.get("answer") or {}
        figs = {f.get("id"): f for f in j.get("figures") or []}
        used: set = set()
        # 지시사항 이름표로 쓰인 그림은 해설에서 다시 넣지 않는다
        for s in j.get("instructions") or []:
            for mt in TOK.finditer(str(s)):
                used.add(mt.group(1))
        out = [f'<div class="ans" data-no="{p}-{no}">']
        out.append(f'<p class="t">{"문제" + str(p) + "-" + str(no) + " " if no else ""}{_h(a.get("title") or "")}</p>')
        out.append(_lines_html(a.get("steps") or [], j, figs, used))
        for fid in figs:
            if fid not in used:
                out.append(_fig(j, fid, figs, used))
        out.append("</div>")
        body.append("".join(out))
    label = spec.get("label") or ""
    return _doc(f"{label} 모의 {m}회 — 모범답안 · 해설", "정답 & 해설", "".join(body))


# ── 대본(초벌) ────────────────────────────────────────────────────────────
def _say(s: str) -> str:
    s = TOK.sub("", str(s or ""))
    s = re.sub(r"^[①-⑳❶-❿▶※]\s*", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


def script_for(j: dict, terms: dict) -> dict:
    p, no = int(j.get("part") or 0), int(j.get("no") or 0)
    a = j.get("answer") or {}

    def line(s):
        d = EX._line(s, terms)
        d["tts"] = to_speech(speak_cells(s), terms)
        return d

    read = [line(x) for t in [j.get("lead") or ""] + list(j.get("instructions") or [])
            for x in EX._sentences(_say(t)) if x]
    solve = [line(x) for t in list(a.get("steps") or [])
             for x in EX._sentences(_say(t)) for x in EX._split_long(x) if x]
    return {"no": f"{p}-{no}", "chapter_title": f"문제{p}-{no} · {_say(a.get('title') or '')}",
            "subject": p, "read": read, "solve": solve,
            "keywords": [str(f) for f in (j.get("functions") or [])][:6],
            "solution_md": "\n".join([f"**{a.get('title') or ''}**", ""] + [_say(s) for s in a.get("steps") or []])}


# ── 굽기 ──────────────────────────────────────────────────────────────────
def build_round(m: int, pdf: bool = True) -> dict:
    items = [j for j in load_items(m)]
    if not items:
        raise FileNotFoundError(f"{m:02d}회 집필 결과가 없습니다.")
    od = out_dir(m)
    for sub in ("assets", "files", "script"):
        os.makedirs(os.path.join(od, sub), exist_ok=True)
    # 그림 · 실습파일 복사
    for f in glob.glob(os.path.join(pa.round_dir(m), "images", "*.png")):
        shutil.copyfile(f, os.path.join(od, "assets", os.path.basename(f)))
    files = []
    bdir = os.path.join(paths.book_dir(), "06", "practical", f"m{m:02d}")
    for f in sorted(glob.glob(os.path.join(bdir, "*.xlsx"))):
        shutil.copyfile(f, os.path.join(od, "files", os.path.basename(f)))
        files.append(os.path.basename(f))
    qs = [j for j in items if int(j.get("no") or 0)]
    terms = EX._terms()
    for j in qs:
        s = script_for(j, terms)
        atomic_write_text(os.path.join(od, "script", f"q{int(j['part'])}-{int(j['no']):02d}.json"),
                          json.dumps(s, ensure_ascii=False, indent=1))
    atomic_write_text(os.path.join(od, "items.json"), json.dumps(
        [{"id": _stem(j), "part": j.get("part"), "no": j.get("no"), "points": j.get("points"),
          "title": (j.get("answer") or {}).get("title") or ""} for j in qs], ensure_ascii=False, indent=1))
    ex = os.path.join(od, "exam.html")
    an = os.path.join(od, "answers.html")
    atomic_write_text(ex, exam_html(m, items, files))
    atomic_write_text(an, answers_html(m, items))
    errs = []
    if pdf:
        for h in (ex, an):
            e = EX._print_pdf(h, h[:-5] + ".pdf")
            if e:
                errs.append(f"{os.path.basename(h)}: {e}")
    info = {"round": m, "questions": len(qs), "files": files, "pdf_errors": errs,
            "missing_xlsx": not files, "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    atomic_write_text(os.path.join(od, "_build.json"), json.dumps(info, ensure_ascii=False, indent=1))
    return info


def status(rounds: List[int]) -> List[dict]:
    rows = []
    for m in rounds:
        b = {}
        bp = os.path.join(out_dir(m), "_build.json")
        if os.path.isfile(bp):
            try:
                with open(bp, encoding="utf-8") as fh:
                    b = json.load(fh)
            except (OSError, ValueError):
                b = {}
        rows.append({"round": m, "written": all(pa.part_done(m, p) for p in (1, 2, 3, 4)),
                     "built": bool(os.path.isfile(os.path.join(paths.book_dir(), "06", "practical", f"m{m:02d}", "verify.json"))),
                     "ebook": b,
                     "rec": len(glob.glob(os.path.join(out_dir(m), "rec", "*.lesson.yaml")))})
    return rows


# ── 인쇄본(/print/practical) ───────────────────────────────────────────────
def print_html(rd: int = 0) -> str:
    """구운 시험지·해설을 한 장으로 — 그림은 /api/practical/img 로 다시 건다. rd 가 없으면 회차 목록."""
    spec = _spec()
    if not rd:
        rows = []
        for d in sorted(glob.glob(os.path.join(paths.ebook_dir(), "m[0-9][0-9]"))):
            m = int(os.path.basename(d)[1:])
            if os.path.isfile(os.path.join(d, "exam.html")):
                rows.append(f'<li><a href="/print/practical?rd={m}">모의 {m}회 — 시험지 + 모범답안</a></li>')
        if not rows:
            raise FileNotFoundError("아직 구운 회차가 없습니다 — 「HTML 문제집 제작」 에서 굽기를 먼저 하세요.")
        return _doc(f"{spec.get('label') or ''} 인쇄본", "실기", "<ul>" + "".join(rows) + "</ul>")
    d = out_dir(int(rd))
    parts_html = []
    for name in ("exam.html", "answers.html"):
        p = os.path.join(d, name)
        if not os.path.isfile(p):
            raise FileNotFoundError(f"{int(rd):02d}회를 아직 굽지 않았습니다 — 「HTML 문제집 제작」 에서 굽기를 먼저 하세요.")
        with open(p, encoding="utf-8") as fh:
            h = fh.read()
        body = h.split("<body>", 1)[-1].rsplit("</body>", 1)[0]
        parts_html.append(body.replace('src="assets/', f'src="/api/practical/img/m{int(rd):02d}/'))
    return ("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
            f"<title>{_h(spec.get('label') or '')} 모의 {int(rd)}회 인쇄본</title>"
            f"<style>{CSS}{EX._page_css()}.split{{break-before:page}}</style></head><body>"
            + parts_html[0] + '<div class="split"></div>' + parts_html[1] + "</body></html>\n")
