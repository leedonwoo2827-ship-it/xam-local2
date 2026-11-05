"""교재 정답·해설편 — 여러 회차의 정답과 해설을 문제편과 **분리해 한 권으로 모은다.**

왜 필요한가
────────────────────────────────────────────────────────────────────────────
교재(인쇄·한글)는 문제편(`07/<mNN>/exam.html`, 1단 46배판)과 정답·해설편으로 나뉜다.
문제편 옆에 해설을 두면 풀기 전에 답이 보이므로, 해설은 책 뒤에 회차 순서로 모은다.
과목(20문항)마다 유튜브 해설 영상 한 편이 있어 그 첫머리에 QR 을 둔다.

무엇을 어디에 쓰는가 — `07/_textbook/`
────────────────────────────────────────────────────────────────────────────
  answers_<첫>-<끝>.html   1단 46배판 · 회차마다 새 쪽 · 빠른 정답표 → 과목별(QR) → 문항별 해설
  answers_<첫>-<끝>.pdf    위 HTML 을 Chromium 으로 인쇄한 것
  assets/*.svg             해설 그림
  videos.json              {"m01-p1": "https://youtu.be/…"} — 과목 영상 주소(해설북 스튜디오가 올린 뒤 채운다).
                           주소가 없는 과목은 QR 자리에 「영상 준비 중」 칸을 둔다(판면이 바뀌지 않게).

★ 판형·글꼴·그림 처리는 문제편(ebookexam)과 같은 것을 쓴다 — 두 책이 한 교재로 묶이므로.
"""

from __future__ import annotations

import json
import os
import re
import time

from core.atomic_io import atomic_write_text
from services.export import ebookexam as ex

CIRCLE = ex._CIRCLE


def textbook_dir() -> str:
    return os.path.join(ex.ebook_dir(), "_textbook")


def _videos() -> dict:
    p = os.path.join(textbook_dir(), "videos.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f) or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _qr(url: str, key: str, out_dir: str) -> str:
    """해설 영상 QR — assets/qr_<회차-과목>.png (인쇄·한글 둘 다 같은 그림). 주소가 없으면 같은 크기의 빈 칸"""
    if not url:
        return '<div class="qr none">영상 준비 중</div>'
    import segno
    name = f"qr_{key}.png"
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
    segno.make(url, error="m").save(os.path.join(out_dir, "assets", name), kind="png", scale=10, border=2)
    return f'<img class="qr" src="assets/{name}" alt="해설 영상 QR" style="width:22mm">'


def _parts(qs: list[dict]) -> list[dict]:
    """과목이 바뀌는 곳에서 나눈다 — [{part, subject, qs:[(no, q)]}]"""
    out: list[dict] = []
    for no, q in enumerate(qs, 1):
        sj = q.get("subject") or ""
        if not out or out[-1]["subject"] != sj:
            out.append({"part": len(out) + 1, "subject": sj, "qs": []})
        out[-1]["qs"].append((no, q))
    return out


def _quick(qs: list[dict]) -> str:
    """빠른 정답표 — 한 줄 10문항"""
    rows = []
    for at in range(0, len(qs), 10):
        chunk = list(enumerate(qs[at:at + 10], at + 1))
        rows.append("<tr>" + "".join(f"<th>{no}</th>" for no, _ in chunk) + "</tr>"
                    + "<tr>" + "".join(f"<td>{CIRCLE[int(q['answer_index'])]}</td>" for _, q in chunk) + "</tr>")
    return '<table class="quick">' + "".join(rows) + "</table>"


def _round_html(rc: str, d: dict, figs: dict, videos: dict, short: str, out_dir: str) -> tuple[str, list[dict]]:
    qs = sorted(d.get("questions") or [], key=lambda q: int(q.get("question_no") or 0))
    rl = d.get("round_label") or rc
    out = [f'<section class="round"><h2>{ex._h(rl)} <small>정답 및 해설</small></h2>', _quick(qs)]
    for p in _parts(qs):
        nos = p["qs"]
        key = f"{rc}-p{p['part']}"
        url = videos.get(key, "")
        out.append(
            f'<div class="sjhead"><div><h3 class="sjname">{ex._h(p["subject"])}</h3>'
            f'<div class="m">{nos[0][0]}~{nos[-1][0]}번 · 해설 영상 {ex._h(short)} {ex._h(rl)} {ex._h(p["subject"])}</div></div>'
            + _qr(url, key, out_dir) + '</div>')
        for no, q in nos:
            ans = CIRCLE[int(q["answer_index"])]
            tags = " · ".join(q.get("tags") or [])
            out.append(
                f'<div class="a"><div class="ah"><span class="no">{no}.</span><span class="ans">정답 {ans}</span>'
                + (f'<span class="tg">{ex._h(tags)}</span>' if tags else "")
                + f'</div><div class="ex">{ex._md(q.get("explanation") or "", figs)}</div></div>')
    out.append("</section>")
    return "".join(out), qs


_CSS = """
:root{--ink:#111;--mute:#666;--line:#cfcfcf;--box:#f5f5f2}
*{box-sizing:border-box}
html,body{background:#fff}
body{margin:0;padding:24px 28px;color:var(--ink);font:10pt/1.65 "Malgun Gothic","맑은 고딕",-apple-system,sans-serif}
.cover{border-bottom:2px solid var(--ink);padding:0 0 6px;margin:0 0 14px;display:flex;justify-content:space-between;align-items:flex-end}
.cover h1{font-size:1.5em;margin:0}.cover .m{color:var(--mute)}
.round+.round{break-before:page;page-break-before:always}
.round h2{font-size:1.35em;margin:0 0 8px;padding:0 0 4px;border-bottom:2px solid var(--ink)}
.round h2 small{font-size:.7em;color:var(--mute);font-weight:400;margin-left:6px}
table.quick{border-collapse:collapse;width:100%;margin:0 0 14px;font-size:.95em;table-layout:fixed}
table.quick th,table.quick td{border:1px solid #999;padding:2px 0;text-align:center}
table.quick th{background:var(--box);font-weight:700}
.sjhead{display:flex;justify-content:space-between;align-items:center;gap:12px;border:1px solid var(--line);
  border-radius:6px;padding:8px 12px;margin:14px 0 10px;break-inside:avoid;break-after:avoid}
.sjname{font-weight:800;font-size:1.1em;margin:0}.sjhead .m{color:var(--mute);font-size:.88em}
.qr{width:22mm;height:22mm;flex:none;display:block;margin:0;max-height:none}
.qr.none{border:1px dashed #999;display:grid;place-items:center;text-align:center;color:#888;font-size:.8em;line-height:1.3}
.a{break-inside:avoid;page-break-inside:avoid;margin:0 0 12px}
.ah{display:flex;gap:8px;align-items:baseline;margin:0 0 2px}
.ah .no{font-weight:800;min-width:2.2em}.ah .ans{font-weight:800}
.ah .tg{color:var(--mute);font-size:.85em}
.ex{margin-left:2.2em}.ex p{margin:0 0 4px}
pre.code{background:var(--box);border:1px solid var(--line);border-radius:4px;padding:6px 9px;margin:4px 0 6px;
  font:.9em/1.5 Consolas,ui-monospace,monospace;white-space:pre-wrap}
code{font-family:Consolas,ui-monospace,monospace;font-size:.92em}
table.tb{border-collapse:collapse;margin:4px 0 6px;font-size:.93em}
table.tb th,table.tb td{border:1px solid #999;padding:2px 7px}table.tb th{background:var(--box)}
img{display:block;max-width:80%;max-height:15em;margin:6px 0}
@media print{body{padding:0}}
"""


def build(rcs: list[str], pdf: bool = True) -> dict:
    """rcs = ["m01", …, "m05"] → 07/_textbook/answers_m01-m05.html(+pdf)"""
    out_dir = textbook_dir()
    os.makedirs(out_dir, exist_ok=True)
    videos = _videos()
    label = ex._label()
    short = label.split("(")[0].strip()
    figs: dict = {}
    body, all_qs, missing_qr = [], [], []
    for rc in rcs:
        d = ex._load_round(rc)
        html_part, qs = _round_html(rc, d, figs, videos, short, out_dir)
        body.append(html_part)
        all_qs += qs
        missing_qr += [f"{rc}-p{p['part']}" for p in _parts(qs) if f"{rc}-p{p['part']}" not in videos]
    name = f"answers_{rcs[0]}-{rcs[-1]}" if len(rcs) > 1 else f"answers_{rcs[0]}"
    span = f"{rcs[0][1:]}~{rcs[-1][1:]}회" if len(rcs) > 1 else f"{rcs[0][1:]}회"
    page = (
        "<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
        f"<title>{ex._h(label)} 모의고사 {span} 정답 및 해설</title>\n"
        f"<style>{_CSS}{ex._page_css()}</style></head><body>\n"
        f'<div class="cover"><h1>{ex._h(label)}</h1><span class="m">모의고사 {span} · 정답 및 해설</span></div>\n'
        + "\n".join(body) + "\n</body></html>\n")
    html_path = os.path.join(out_dir, name + ".html")
    atomic_write_text(html_path, page)
    missing_figs = ex._write_figs(out_dir, figs, all_qs)
    pdf_err = ex._print_pdf(html_path, os.path.join(out_dir, name + ".pdf")) if pdf else "건너뜀"
    hwpx = to_hwpx(html_path)
    book = combined(rcs, html_path, f"{ex._h(label)} 모의고사 {span}")
    return {"file": html_path, "hwpx": hwpx.get("out"), "hwpx_error": hwpx.get("error"), "rounds": rcs, "questions": len(all_qs), "missing_figs": missing_figs,
            "qr_missing": missing_qr, "pdf_error": pdf_err, "book_hwpx": book.get("out"), "book_error": book.get("error") or "",
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}


_BODY = re.compile(r"<body[^>]*>(.*)</body>", re.S)
_STYLE = re.compile(r"<style>(.*?)</style>", re.S)
_SCRIPT = re.compile(r"<script\b.*?</script>", re.S)


def combined(rcs: list[str], answers_html: str, title: str) -> dict:
    """교재 한 권 — 문제편 mAA~mBB(회차마다 새 쪽) 뒤에 정답·해설편을 이어 붙인 textbook_mAA-mBB.html → .hwpx

    회차 문제편은 07/<mNN>/exam.html 을 그대로 쓴다(먼저 「시험지 굽기」). 그림 주소만 ../<mNN>/assets/ 로 바꾼다.
    """
    out_dir = textbook_dir()
    styles, parts = [], []
    for rc in rcs:
        f = os.path.join(ex.round_dir(rc), "exam.html")
        if not os.path.isfile(f):
            return {"error": f"{rc} 문제편이 없습니다 — 먼저 회차 시험지를 구우세요"}
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        styles += _STYLE.findall(src)[:1]
        body = _SCRIPT.sub("", _BODY.search(src).group(1))
        body = body.replace('src="assets/', f'src="../{rc}/assets/')
        parts.append(f'<section style="break-before:page">{body}</section>')
    with open(answers_html, encoding="utf-8") as fh:
        ans = fh.read()
    styles += _STYLE.findall(ans)[:1]
    parts.append(f'<section style="break-before:page">{_SCRIPT.sub("", _BODY.search(ans).group(1))}</section>')
    name = f"textbook_{rcs[0]}-{rcs[-1]}" if len(rcs) > 1 else f"textbook_{rcs[0]}"
    page = ("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
            f"<title>{title} 문제 · 정답 및 해설</title>\n"
            f"<style>{styles[0] + styles[-1]}</style></head><body>\n"   # 문제편 CSS + 정답·해설편 CSS(쪽 나눔 규칙)
            + "\n".join(parts) + "\n</body></html>\n")
    path = os.path.join(out_dir, name + ".html")
    atomic_write_text(path, page)
    return to_hwpx(path)


def template_path() -> str:
    """교재 한글 양식 — 07/_textbook/template.hwpx 가 있으면 그 글꼴·스타일·바탕쪽으로, 없으면 변환기 기본 모양"""
    return os.path.join(textbook_dir(), "template.hwpx")


def to_hwpx(html_path: str) -> dict:
    """HTML → 같은 이름의 .hwpx (tools/html2hwpx — 표준 라이브러리만 쓰는 변환기)"""
    import importlib.util
    tool = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "html2hwpx", "html2hwpx.py")
    try:
        spec = importlib.util.spec_from_file_location("html2hwpx", os.path.abspath(tool))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        tpl = template_path()
        out = os.path.splitext(html_path)[0] + ".hwpx"
        if os.path.isfile(tpl):     # 양식은 재단 여유까지 든 판형이라 쪽 설정은 양식 그대로
            return mod.convert(html_path, out, page="keep", margin_mm=None, template=tpl, font=None)
        return mod.convert(html_path, out, page=(188, 257), margin_mm=15.0)
    except Exception as e:                                       # noqa: BLE001
        return {"error": f"HWPX 실패: {e}"}
