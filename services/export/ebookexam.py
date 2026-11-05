"""이북 시험지 — 회차마다 1단 시험지(HTML·PDF) + 자막·음성·발음 대본.

왜 필요한가
────────────────────────────────────────────────────────────────────────────
3부의 영상과 이북은 이 앱이 아니라 **해설북**(github haeseolbook)이 만든다.
그쪽은 「원문 PDF + 정답표 + 문항별 대본」 만 있으면 된다:

  원문 PDF      tools/pipeline/render.py · regions.py --columns 1 --answers <json>
  정답표        {"1": 3, ...}  (1-기반)
  문항별 대본   studio 의 script/qNN.json — 이 파일이 있으면 s1(Claude 대본) 을 건너뛴다

우리 `_rounds/mNN.json` 에는 문제·보기·정답·해설·해설 낭독문이 이미 있다.
그래서 여기서는 **변환만** 한다 — Claude 를 다시 부르지 않는다.

무엇을 어디에 쓰는가 — `07/<mNN>/`
────────────────────────────────────────────────────────────────────────────
  exam.html         1단 46배판(188×257mm) 시험지 — 교재 인쇄와 이북 페이지가 같은 판면을 쓴다. 정답·해설은 **보이지 않는다**(regions.py 가 문항 번호로
                    영역을 찾으므로 시험지에는 문항만 있어야 한다).
                    ★ 대본 전체를 `<script type="application/json" id="xam-script">` 로
                      **숨겨 넣는다.** 화면·인쇄에는 안 나오고, 파일 하나만 넘겨도 대본이
                      따라간다(2026-10-31 요청).
  exam.pdf          위 HTML 을 Chromium 으로 인쇄한 것
  exam.hwpx         위 HTML 을 한글 문서로(tools/html2hwpx · 07/_textbook/template.hwpx 양식)
  answers.json      정답표
  script/qNN.json   해설북 s1 형식 + 줄마다 `tts`(우리 발음 사전 적용본)
  script.html       사람이 보는 대본 검수지 — 자막 | 음성 | 발음
  assets/*.svg      그 회차가 쓰는 그림

★ 품목 이름을 박지 않는다 — 머리글은 `printdoc._pd_label()` 과 같은 출처를 쓴다.
"""

from __future__ import annotations

import html
import json
import os
import re
import time

from core.atomic_io import atomic_write_text
from core.speak import to_speech
from services.book import paths

_CIRCLE = "①②③④⑤⑥⑦⑧⑨⑩"

# 판형 — 46배판(4·6배판, 188×257mm). 교재(인쇄)와 이북(해설북 페이지 이미지)이 이 PDF 하나를 같이 쓴다.
# 여백: 위·아래 15mm, 좌·우 15mm (제본 쪽 여유는 인쇄소 앉힘에서 준다).
PAGE = {"w": "188mm", "h": "257mm", "top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"}

# 해설북 `studio/script.py` 의 검사 기준. 바뀌면 여기도 바꾼다.
MAX_SAY = 80
SAY_HARD = int(MAX_SAY * 1.6)
TOTAL_MIN, TOTAL_MAX = 150, 700
CAP_MAX = 40


def _h(s) -> str:
    return html.escape("" if s is None else str(s))


def ebook_dir() -> str:
    return paths.ebook_dir()


def round_dir(rc: str) -> str:
    return os.path.join(ebook_dir(), rc)


# ─────────────────────────────────────────────────────────────────────────────
# 읽기
# ─────────────────────────────────────────────────────────────────────────────

def _load_round(rc: str) -> dict:
    p = paths.rounds_json(rc)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _label() -> str:
    from services.export.printdoc import _pd_label
    return _pd_label()


def _terms() -> dict:
    from services.render.bake import _speech_terms
    return _speech_terms()


# ─────────────────────────────────────────────────────────────────────────────
# 작은 마크다운 — 지문에 실제로 나오는 것만 (굵게 · 표 · 코드 블록 · 그림)
# ─────────────────────────────────────────────────────────────────────────────

_MD_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(t: str, figs: dict) -> str:
    out, at = [], 0
    for m in _MD_IMG.finditer(t):
        out.append(_inline_text(t[at:m.start()]))
        name = os.path.basename(m.group(2))
        figs[name] = True
        out.append(f'<img src="assets/{_h(name)}" alt="{_h(m.group(1) or name)}">')
        at = m.end()
    out.append(_inline_text(t[at:]))
    return "".join(out)


def _inline_text(t: str) -> str:
    s = _h(t)
    s = _BOLD.sub(r"<b>\1</b>", s)
    s = _CODE.sub(r"<code>\1</code>", s)
    return s


def _is_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and len(s) > 1


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip()[1:-1].split("|")]


def _md(text: str, figs: dict) -> str:
    """문단 · `|표|` · ```코드``` · 그림. 나머지는 이스케이프된 글자 그대로."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out, buf, i = [], [], 0

    def flush():
        if buf:
            out.append("<p>" + "<br>".join(_inline(x, figs) for x in buf) + "</p>")
            buf.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            flush()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            out.append('<pre class="code">' + _h("\n".join(lines[i + 1:j])) + "</pre>")
            i = j + 1
            continue
        if _is_row(ln):
            flush()
            rows = []
            while i < len(lines) and _is_row(lines[i]):
                rows.append(lines[i])
                i += 1
            body = [r for r in rows if not re.fullmatch(r"\|[\s:\-|]+\|", r.strip())]
            has_head = len(rows) > 1 and re.fullmatch(r"\|[\s:\-|]+\|", rows[1].strip())
            t = ['<table class="tb">']
            for k, r in enumerate(body):
                tag = "th" if has_head and k == 0 else "td"
                t.append("<tr>" + "".join(f"<{tag}>{_inline_text(c)}</{tag}>"
                                          for c in _cells(r)) + "</tr>")
            t.append("</table>")
            out.append("".join(t))
            continue
        if not ln.strip():
            flush()
        else:
            buf.append(ln)
        i += 1
    flush()
    return "".join(out)


def _plain(text: str) -> str:
    """해설 글에서 그림 줄·마크다운 기호를 걷어 자막용 평문으로."""
    t = _MD_IMG.sub("", text or "")
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = t.replace("**", "").replace("`", "")
    return t


# ─────────────────────────────────────────────────────────────────────────────
# 대본 — `_rounds` 의 해설 낭독문 → 해설북 s1 형식
# ─────────────────────────────────────────────────────────────────────────────

_SENT = re.compile(r"(?<=[.!?다요])\s+")
_ANS_LEAD = re.compile(r"^\s*정답은\s*\d+\s*번")


def _sentences(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n\s*\n|\n", text or ""):
        for s in _SENT.split(para.strip()):
            s = s.strip()
            if s:
                out.append(s)
    return out


def _split_long(s: str) -> list[str]:
    """한 줄이 해설북 한도(SAY_HARD)를 넘으면 쉼표 자리에서 나눈다."""
    if len(s) <= SAY_HARD:
        return [s]
    pieces = re.split(r"(?<=,)\s+", s)
    if max(len(p) for p in pieces) > SAY_HARD:      # 쉼표가 없으면 띄어쓰기에서
        pieces = s.split(" ")
    parts, cur = [], ""
    for piece in pieces:
        if cur and len(cur) + 1 + len(piece) > MAX_SAY:
            parts.append(cur)
            cur = piece
        else:
            cur = (cur + " " + piece).strip()
    if cur:
        parts.append(cur)
    return parts


def _cap(say: str) -> str:
    """자막. 길면 자르지 않고 **두 줄로 접는다** — 말줄임은 뜻을 잃는다.

    접는 자리는 가운데에 가장 가까운 쉼표, 없으면 띄어쓰기다.
    """
    s = re.sub(r"\s+", " ", say).strip()
    if len(s) <= CAP_MAX:
        return s
    mid = len(s) // 2
    cands = [m.end() for m in re.finditer(r",\s", s)] or [m.start() for m in re.finditer(r" ", s)]
    if not cands:
        return s
    at = min(cands, key=lambda k: abs(k - mid))
    return s[:at].rstrip() + "\n" + s[at:].lstrip()


def _line(say: str, terms: dict) -> dict:
    return {"say": say, "cap": _cap(say), "tts": to_speech(say, terms)}


def script_for(q: dict, no: int, terms: dict) -> dict:
    ai = int(q.get("answer_index") or 0)
    ans_no = ai + 1
    mark = _CIRCLE[ai] if ai < len(_CIRCLE) else str(ans_no)

    stem = _plain(q.get("question") or "").strip()
    read = [_line(s, terms) for s in _split_long(re.sub(r"\s+", " ", stem))] if stem else []

    speech = q.get("explanation_speech") or _plain(q.get("explanation") or "")
    sents = _sentences(speech)
    lead = ""
    if sents and _ANS_LEAD.match(sents[0]):
        lead = sents.pop(0)
    solve = [_line(p, terms) for s in sents for p in _split_long(s)]

    # ★ 정답 문장은 낭독문의 첫 문장을 쓰되, 번호가 다르면 버리고 새로 쓴다(정답이 기준).
    #   한 줄 정리를 덧붙이지 않는다 — 해설 글(`explanation`)은 「~다」 체라 낭독과
    #   말투가 갈리고, 내용도 solve 첫 문장과 겹친다.
    ok_lead = lead and re.search(rf"정답은\s*{ans_no}\s*번", lead)
    say = f"따라서 정답은 {ans_no}번입니다." if not ok_lead else (
        lead if lead.startswith("따라서") else "따라서 " + lead)
    answer = [_line(say, terms)]

    tags = [t for t in (q.get("tags") or []) if isinstance(t, str) and t]
    sol = _MD_IMG.sub("", q.get("explanation") or "").strip()
    return {
        "no": no,
        "answers": [ans_no],
        "chapter_title": f"{no}번 · {tags[0]}" if tags else f"{no}번",
        "subject": q.get("subject") or "",
        "read": read,
        "solve": solve,
        "answer": answer,
        "keywords": tags[:4],
        "solution_md": f"**정답 {mark}**\n\n{sol}",
    }


def check(d: dict) -> list[str]:
    """해설북 `_validate` 와 같은 기준. 굽기는 멈추지 않고 화면에 띄운다."""
    bad = []
    for k in ("read", "solve", "answer"):
        if not d.get(k):
            bad.append(f"{k} 가 비었습니다")
        for ln in d.get(k) or []:
            if len(ln["say"]) > SAY_HARD:
                bad.append(f"{k} 문장이 깁니다({len(ln['say'])}자)")
    a = d["answers"][0]
    said = " ".join(ln["say"] for ln in d.get("answer") or [])
    if not re.search(rf"(?<!\d){a}\s*번", said):
        bad.append(f"정답 문장에 '{a}번'이 없습니다")
    total = sum(len(ln["say"]) for k in ("read", "solve", "answer") for ln in d.get(k) or [])
    if not TOTAL_MIN <= total <= TOTAL_MAX:
        bad.append(f"분량 {total}자 (기준 {TOTAL_MIN}~{TOTAL_MAX})")
    return bad


# ─────────────────────────────────────────────────────────────────────────────
# 시험지 HTML
# ─────────────────────────────────────────────────────────────────────────────

_EXAM_CSS = """
:root{--ink:#111;--mute:#666;--line:#cfcfcf;--box:#f5f5f2}
*{box-sizing:border-box}
html,body{background:#fff}
body{margin:0;padding:24px 28px;color:var(--ink);
  font:10.5pt/1.7 "Malgun Gothic","맑은 고딕",-apple-system,sans-serif}
.head{display:flex;justify-content:space-between;align-items:flex-end;
  border-bottom:2px solid var(--ink);padding:0 0 6px;margin:0 0 18px}
.head h1{font-size:1.45em;margin:0}
.head .m{color:var(--mute);font-size:.9em}
.sj{font-weight:800;font-size:1.05em;margin:18px 0 10px;padding:3px 0;line-height:1.7;
  border-bottom:1px solid var(--line)}
.sj.brk{break-before:page;page-break-before:always;margin-top:0}
.q{break-inside:avoid;page-break-inside:avoid;margin:0 0 20px}
.qt{display:flex;gap:6px;margin:0 0 6px}
.qt .no{font-weight:800;min-width:2.2em}
.qt p{margin:0}
.psg{border:1px solid var(--line);border-radius:4px;padding:8px 11px;margin:0 0 8px 2.2em}
.psg p{margin:0 0 6px}.psg p:last-child{margin:0}
.up .psg{margin:0 0 6px}
pre.code{background:var(--box);border:1px solid var(--line);border-radius:4px;
  padding:7px 10px;margin:4px 0 6px;font:.9em/1.55 Consolas,ui-monospace,monospace;white-space:pre-wrap}
code{font-family:Consolas,ui-monospace,monospace;font-size:.92em}
table.tb{border-collapse:collapse;margin:4px 0 6px;font-size:.93em}
table.tb th,table.tb td{border:1px solid #999;padding:3px 8px}
table.tb th{background:var(--box)}
img{display:block;max-width:80%;max-height:17em;margin:6px 0}
ol.ch{list-style:none;margin:0 0 0 2.2em;padding:0}
ol.ch li{padding-left:1.5em;position:relative;margin:0 0 2px}
ol.ch li .c{position:absolute;left:0}
@media print{body{padding:0}}
"""


def _page_css() -> str:
    return "@page{size:%s %s;margin:%s %s %s %s}" % (
        PAGE["w"], PAGE["h"], PAGE["top"], PAGE["right"], PAGE["bottom"], PAGE["left"])


_ABOVE = re.compile(r"^\s*(위|위의|상기)\s")


def _question_html(q: dict, no: int, figs: dict) -> str:
    out = ['<div class="q" data-no="%d">' % no]
    stem = _md(q.get("question") or "", figs)
    stem = stem[3:-4] if stem.startswith("<p>") and stem.count("<p>") == 1 else stem
    psg = (f'<div class="psg">{_md(q["passage"], figs)}</div>'
           if (q.get("passage") or "").strip() else "")
    # ★ 「위 도식의…」 처럼 발문이 지문을 **위**에서 가리키면 지문을 먼저 둔다.
    #   번호는 언제나 맨 앞이다 — regions.py 가 번호로 문항 영역을 찾는다.
    if psg and _ABOVE.match(_plain(q.get("question") or "")):
        out.append(f'<div class="qt"><span class="no">{no}.</span><div class="up">{psg}'
                   f'<p>{stem}</p></div></div>')
    else:
        out.append(f'<div class="qt"><span class="no">{no}.</span><div>{stem}</div></div>')
        out.append(psg)
    out.append('<ol class="ch">')
    for i, c in enumerate(q.get("choices") or []):
        mark = _CIRCLE[i] if i < len(_CIRCLE) else str(i + 1)
        out.append(f'<li><span class="c">{mark}</span>{_inline(str(c), figs)}</li>')
    out.append("</ol></div>")
    return "".join(out)


def _exam_html(meta: dict, qs: list[dict], hidden: dict, figs: dict) -> str:
    label, rl = _label(), meta.get("round_label") or meta.get("round_code")
    body, last_sj = [], None
    for no, q in enumerate(qs, 1):
        sj = q.get("subject") or ""
        if sj and sj != last_sj:
            # 둘째 과목부터 새 쪽 — 교재는 과목마다 새 쪽에서 시작하고, 이북·영상은 과목(20문항) 단위로 쪽을 자른다
            body.append(f'<h2 class="sj{" brk" if last_sj else ""}">{_h(sj)}</h2>')
            last_sj = sj
        body.append(_question_html(q, no, figs))
    # ★ 대본을 숨겨 넣는다. `</` 를 끊어 두어야 대본 글이 script 태그를 닫지 못한다.
    blob = json.dumps(hidden, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
        f"<title>{_h(label)} {_h(rl)}</title>\n<style>{_EXAM_CSS}{_page_css()}</style></head><body>\n"
        f'<div class="head"><h1>{_h(label)}</h1><span class="m">{_h(rl)} · {len(qs)}문항</span></div>\n'
        + "\n".join(body)
        + f'\n<script type="application/json" id="xam-script">{blob}</script>\n'
        "</body></html>\n"
    )


def _script_html(meta: dict, scripts: list[dict]) -> str:
    label, rl = _label(), meta.get("round_label") or meta.get("round_code")
    rows = []
    for d in scripts:
        bad = d.get("_check") or []
        rows.append(f'<h2>{_h(d["chapter_title"])} <small>정답 {d["answers"][0]}번</small>'
                    + (f' <span class="bad">{_h(" · ".join(bad))}</span>' if bad else "")
                    + "</h2><table><tr><th>부분</th><th>자막</th><th>음성</th><th>발음</th></tr>")
        for part in ("read", "solve", "answer"):
            for ln in d[part]:
                rows.append(f"<tr><td class=k>{part}</td><td>{_h(ln['cap'])}</td>"
                            f"<td>{_h(ln['say'])}</td><td>{_h(ln['tts'])}</td></tr>")
        rows.append("</table>")
    css = ("body{font:11pt/1.6 'Malgun Gothic',sans-serif;margin:20px;color:#111;background:#fff}"
           "h1{font-size:1.3em}h2{font-size:1.05em;margin:22px 0 6px}h2 small{color:#666;font-weight:400}"
           ".bad{color:#b3261e;font-size:.85em;font-weight:400}"
           "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 6px;"
           "vertical-align:top}th{background:#f3f3ef;text-align:left}td.k{color:#666;width:4em}"
           "tr{break-inside:avoid}")
    return ("<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
            f"<title>{_h(label)} {_h(rl)} 대본</title><style>{css}</style></head><body>"
            f"<h1>{_h(label)} {_h(rl)} — 자막 · 음성 · 발음</h1>" + "".join(rows) + "</body></html>\n")


# ─────────────────────────────────────────────────────────────────────────────
# 그림 · PDF
# ─────────────────────────────────────────────────────────────────────────────

def _write_figs(out_dir: str, figs: dict, qs: list[dict]) -> list[str]:
    inline = {}
    for q in qs:
        for a in q.get("assets") or []:
            if isinstance(a, dict) and a.get("name") and a.get("svg"):
                inline[a["name"] + ".svg"] = a["svg"]
    missing = []
    adir = os.path.join(out_dir, "assets")
    for name in figs:
        svg = inline.get(name)
        if svg is None:
            src = paths.q_svg(name)
            if os.path.isfile(src):
                with open(src, encoding="utf-8") as f:
                    svg = f.read()
        if svg is None:
            missing.append(name)
            continue
        os.makedirs(adir, exist_ok=True)
        atomic_write_text(os.path.join(adir, name), svg)
    return missing


def _print_pdf(html_path: str, pdf_path: str) -> str:
    """Chromium 으로 인쇄. 실패하면 이유를 돌려준다(HTML 은 이미 남아 있다).

    ★ sync_playwright 는 asyncio 루프 안에서 못 돈다 — 라우트는 `def` 로 둔다.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "playwright 가 없습니다"
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.goto("file:///" + html_path.replace("\\", "/"), wait_until="load")
            pg.pdf(path=pdf_path, width=PAGE["w"], height=PAGE["h"], print_background=True,
                   margin={k: PAGE[k] for k in ("top", "bottom", "left", "right")})
            b.close()
        return ""
    except Exception as e:                                       # noqa: BLE001
        return f"PDF 실패: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 굽기 · 상태
# ─────────────────────────────────────────────────────────────────────────────

def build_round(rc: str, pdf: bool = True) -> dict:
    d = _load_round(rc)
    qs = sorted(d.get("questions") or [], key=lambda q: int(q.get("question_no") or 0))
    meta = {k: v for k, v in d.items() if k != "questions"}
    terms = _terms()
    out_dir = round_dir(rc)
    os.makedirs(os.path.join(out_dir, "script"), exist_ok=True)

    scripts, bad_total = [], 0
    for no, q in enumerate(qs, 1):
        s = script_for(q, no, terms)
        bad = check(s)
        bad_total += bool(bad)
        atomic_write_text(os.path.join(out_dir, "script", f"q{no:02d}.json"),
                          json.dumps(s, ensure_ascii=False, indent=1))
        scripts.append({**s, "_check": bad})

    answers = {str(s["no"]): s["answers"][0] for s in scripts}
    atomic_write_text(os.path.join(out_dir, "answers.json"),
                      json.dumps(answers, ensure_ascii=False, indent=1))

    figs: dict = {}
    hidden = {"round_code": rc, "round_label": meta.get("round_label") or rc,
              "label": _label(), "answers": answers,
              "questions": [{k: v for k, v in s.items() if k != "_check"} for s in scripts]}
    html_path = os.path.join(out_dir, "exam.html")
    atomic_write_text(html_path, _exam_html(meta, qs, hidden, figs))
    missing = _write_figs(out_dir, figs, qs)
    atomic_write_text(os.path.join(out_dir, "script.html"), _script_html(meta, scripts))

    pdf_err = _print_pdf(html_path, os.path.join(out_dir, "exam.pdf")) if pdf else "건너뜀"
    # 교재(한글)용 — 07/_textbook/template.hwpx 양식이 있으면 그 모양으로
    from services.export.answerbook import to_hwpx
    hwpx = to_hwpx(html_path) if pdf else {"error": "건너뜀"}
    info = {"round_code": rc, "questions": len(qs), "flagged": bad_total,
            "missing_figs": missing, "pdf_error": pdf_err, "hwpx_error": hwpx.get("error") or "",
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    atomic_write_text(os.path.join(out_dir, "_build.json"),
                      json.dumps({**info, "flags": {s["no"]: s["_check"] for s in scripts if s["_check"]}},
                                 ensure_ascii=False, indent=1))
    return info


def status() -> dict:
    rows = []
    for rc in paths.round_codes():
        bj = os.path.join(round_dir(rc), "_build.json")
        info = {}
        if os.path.isfile(bj):
            try:
                with open(bj, encoding="utf-8") as f:
                    info = json.load(f)
            except (OSError, ValueError):
                info = {}
            if paths.mtime(paths.rounds_json(rc)) > paths.mtime(bj):
                info["stale"] = True
        info["has_pdf"] = os.path.isfile(os.path.join(round_dir(rc), "exam.pdf"))
        rows.append({"round_code": rc, **info})
    return {"dir": ebook_dir(), "label": _label(), "rounds": rows}
