"""인쇄용 문서 — 문항 인쇄본 · 슬라이드 대본 인쇄본.

왜 필요한가
────────────────────────────────────────────────────────────────────────────
화면 검수는 한 문항씩 본다. 그런데 **회차 전체를 훑어야 잡히는 오류**가 따로 있다 —
같은 개념이 두 번 나오는 것, 정답 분포가 한쪽으로 쏠린 것, 난이도가 앞뒤로 튀는 것.
그건 종이로 봐야 보인다. 그리고 다른 사람에게 검수를 부탁할 때 앱을 띄우게 할 수는 없다.

왜 파일을 만들지 않는가
────────────────────────────────────────────────────────────────────────────
`06/` 처럼 산출물을 굽지 않고 **요청할 때마다 지금 데이터로 그린다.**
파일로 두면 고친 뒤 다시 굽는 것을 잊고, 낡은 종이를 들고 검수하게 된다.
이 프로젝트에서 이미 그 사고를 겪었다(업로드 폴더가 옛 빌드였던 일).
브라우저에서 Ctrl+P 로 PDF 를 만드는 것이 인쇄 경로다 — 별도 라이브러리가 없다.

무엇을 어디서 읽는가
────────────────────────────────────────────────────────────────────────────
  문항        `06/pd/<pd>/problems.json`   빌드 산출물. 서버에 올린 것과 **같은 것**이다.
                                           02/*.md 를 다시 파싱하지 않는 이유가 이것이다 —
                                           종이와 서버가 갈리면 검수가 무의미해진다.
  그림        `06/pd/<pd>/figs/*.svg`      `/book` 마운트로 그대로 띄운다.
  슬라이드·대본 `05/<번들>/script/<번들>_script.json`
                                           씬마다 heading(화면에 나오는 제목)과
                                           narration(읽는 말)이 짝으로 있다. 이 둘을
                                           나란히 두는 것이 '슬라이드 최종텍스트' 다.

★ 수식은 로컬 MathJax(`static/vendor/tex-svg.js`)로 그린다. 인터넷 없이 인쇄된다.
"""

from __future__ import annotations

import html
import json
import os
import re

from services.book import paths

# ─────────────────────────────────────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────────────────────────────────────

_CIRCLE = "①②③④⑤⑥⑦⑧⑨⑩"


def _h(s) -> str:
    return html.escape("" if s is None else str(s))


def _pd_label() -> str:
    """이 인쇄본이 어느 문제집인지 — **상수가 아니다.**

    ★ `core.constants.PD_LABEL` 은 `.env` 의 `XAM_PD_LABEL` 이라 작업 폴더를 바꿔도
      따라오지 않는다. 실측(2026-08-21): 활성 폴더가 SQLD 인데 대본 인쇄본 제목이
      '빅데이터분석기사 필기' 로 찍혔다. 인쇄해서 나눠 주는 종이에 다른 자격증 이름이
      박히는 자리다. 시험정보(`exams/<pd>.json`) → 폴더 메타 → 상수 순으로 본다.
    """
    try:
        from services.authoring import parts
        spec = parts.active() or {}
        v = str(spec.get("label") or "").strip()
        if v:
            return v
    except Exception:
        pass
    try:
        from services.book import books
        v = str((books.active_meta() or {}).get("label") or "").strip()
        if v:
            return v
    except Exception:
        pass
    from core.constants import PD_LABEL
    return PD_LABEL


def _pd_code() -> str:
    """활성 품목 코드. `paths.problems_json()` 과 **같은 출처**를 쓴다.

    이 값이 어긋나면 문항 인쇄본의 그림 경로(`/book/06/pd/<pd>/figs/`)가 다른 품목을
    가리켜 그림이 통째로 안 나온다.
    """
    try:
        from services.book import books
        v = str((books.active_meta() or {}).get("pd") or "").strip()
        if v:
            return v
    except Exception:
        pass
    from core.constants import PD_CODE
    return PD_CODE


def _load_problems() -> list[dict]:
    """`06/pd/<pd>/problems.json` 의 문항 목록.

    ★ 여기서 실패하면 빈 목록이 아니라 **예외**를 낸다. 인쇄물이 조용히 0문항으로
      나오면 사람이 "아직 안 만들었나" 로 읽고 원인을 찾지 못한다.
    """
    p = paths.problems_json()
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"problems.json 이 없습니다: {p}\n"
            "발행 화면 ③ [빌드 실행] 을 먼저 하십시오 — 인쇄본은 빌드 산출물을 읽습니다."
        )
    d = json.load(open(p, encoding="utf-8"))
    if isinstance(d, dict):
        d = d.get("problems") or []
    if not isinstance(d, list):
        raise ValueError(f"problems.json 형식을 알 수 없습니다: {p}")
    return d


def _fig_url(name: str) -> str:
    """그림 URL. `/book` 은 BOOK 폴더 루트를 가리킨다(app.py 의 마운트)."""
    return "/book/06/pd/" + _pd_code() + "/figs/" + name


# ★ 해설 안에 **글로 박혀 있는** 그림 줄. `![제목](assets/mNN-QQ-키워드-답.svg)`
#   집필 규약(services/authoring/spec.py)이 두 판을 만든다 — 지문 판은 답이 되는
#   자리를 가리고, 해설 판은 채운다. 가린 판만 `figures_json` 에 들어가고 채운 판은
#   해설 본문에 인라인으로 남는다(axexam 의 build_check 가 인라인된 것을 빼기
#   때문이다). 웹은 마크다운을 렌더하니 그림이 나오지만, 인쇄본은 `_h()` 로
#   이스케이프만 해서 `![](assets/…-답.svg)` 라는 글자가 그대로 찍혔다.
#   실측(2026-09-15, ADsP 750문항): 66문항이 이 상태였다 — 정답 그림이 통째로 빠진
#   채 검수 종이가 나갔다는 뜻이다.
_MD_IMG = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def _rich(text) -> str:
    """이스케이프하되, 인라인 그림 줄만 `<img>` 로 살린다.

    ★ 이스케이프가 기본이다. 마크다운을 여기서 전부 해석하지 않는다 — 해설에는
      사람이 쓴 `**`·백틱이 섞여 있고, 그걸 렌더하기 시작하면 종이와 웹이 갈린다.
      그림만 예외인 이유는 **빠지면 문항이 성립하지 않기 때문**이다.
    """
    t = "" if text is None else str(text)
    out, at = [], 0
    for m in _MD_IMG.finditer(t):
        out.append(_h(t[at:m.start()]))
        name = os.path.basename(m.group(2))
        alt = m.group(1) or name
        out.append(f'<img src="{_h(_fig_url(name))}" alt="{_h(alt)}">')
        at = m.end()
    out.append(_h(t[at:]))
    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# 인쇄 CSS — 두 문서가 같은 것을 쓴다
# ─────────────────────────────────────────────────────────────────────────────

_CSS = """
/* ★ 글자 크기의 단일 손잡이 — `--fs`.
   아래의 모든 크기는 **em** 이다. 예전에는 `@media print` 에서 body 만 11.5pt 로
   키우고 해설·표·SQL·태그는 px 로 박아 뒀다. 그래서 인쇄하면 발문·보기만 11.5pt 고
   해설은 13px(=9.75pt), 태그는 11px(=8.25pt) 로 나왔다 — 종이에서 제일 오래 읽는
   해설이 제일 작았다. em 으로 묶어 두면 이 한 줄만 바꿔도 전부 같이 자란다.
   화면과 인쇄가 같은 값을 쓰는 것도 일부러다(보이는 대로 나와야 한다). */
:root{--ink:#151812;--mute:#666;--line:#d8dcd4;--box:#f6f7f4;--ok:#0f7355;--hi:#8a4b00;
  --fs:12pt}
*{box-sizing:border-box}
body{margin:0;padding:22px 26px 40px;color:var(--ink);background:#fff;
  font:var(--fs)/1.72 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:1.5em;margin:0 0 3px}
.sub{color:var(--mute);font-size:.93em;margin:0 0 18px}

/* 도구막대는 화면 전용이라 px 로 둔다 — 글자 손잡이를 따라 커지면 안 된다 */
.toolbar{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);
  padding:9px 0 11px;margin:0 0 18px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.toolbar a,.toolbar button{padding:5px 11px;border:1px solid var(--line);border-radius:5px;
  background:#fff;color:var(--ink);text-decoration:none;font:inherit;font-size:12.5px;cursor:pointer}
.toolbar a.on,.toolbar button.on{background:var(--ink);border-color:var(--ink);color:#fff;font-weight:700}
.toolbar .sp{margin-left:auto;color:var(--mute);font-size:12px}
.toolbar .ctl{display:flex;gap:3px;align-items:center;font-size:12px;color:var(--mute);
  border:1px solid var(--line);border-radius:6px;padding:3px 7px}
.toolbar .ctl button{padding:3px 8px;font-size:12px}

/* 회차·번들 표제 — 새 장으로 시작한다 */
.part{page-break-before:always;break-before:page;border-top:2px solid var(--ink);
  margin:26px 0 14px;padding-top:9px}
/* ★ `:first-of-type` 을 쓰면 안 된다. body 의 첫 div 는 도구막대라서 이 규칙이
   한 번도 맞은 적이 없고, 1회차까지 새 장으로 밀려 표지만 있는 빈 장이 생겼다.
   첫 표제는 파이썬이 표시해 준다. */
.part.first{page-break-before:auto;break-before:auto;margin-top:0}
.part h2{font-size:1.2em;margin:0}
.part .m{color:var(--mute);font-size:.9em}

/* ★ 한 문항이 페이지에 걸쳐 잘리면 종이 검수가 안 된다 */
.q{page-break-inside:avoid;break-inside:avoid;margin:0 0 15px;padding:0 0 13px;
  border-bottom:1px solid var(--line)}
.q:last-child{border-bottom:0}

/* ★ 쪽당 문항 수 — 도구막대에서 고른다.
   기본은 '자동'(넣을 수 있는 만큼). 종이에 적색펜으로 고쳐 오는 검수라면 2문항이
   편하고, 문항마다 길게 쓰려면 1문항이다. 강제로 끊는 것은 여기서만 한다. */
body.pp1 .qs>.q,
body.pp2 .qs>.q:nth-child(2n){page-break-after:always;break-after:page}
body.pp1 .qs>.q:last-child,
body.pp2 .qs>.q:last-child{page-break-after:auto;break-after:auto}

.qh{display:flex;gap:8px;align-items:baseline;margin:0 0 5px;flex-wrap:wrap}
.qh .no{font-weight:800;font-size:1.1em}
.qh .tag{font-size:.82em;color:var(--mute);border:1px solid var(--line);
  border-radius:3px;padding:0 5px;white-space:nowrap}
.qh .tag.d{border-color:var(--hi);color:var(--hi)}
.qh .key{font:.85em/1.6 ui-monospace,Consolas,monospace;color:var(--mute)}
.psg{background:var(--box);border:1px solid var(--line);border-radius:5px;
  padding:8px 10px;margin:0 0 7px;white-space:pre-wrap}
.qt{margin:0 0 7px}
pre.sql{background:var(--box);border:1px solid var(--line);border-radius:5px;
  padding:8px 10px;margin:0 0 7px;font:.92em/1.6 ui-monospace,Consolas,monospace;
  white-space:pre-wrap}
table.tb{border-collapse:collapse;margin:0 0 7px;font-size:.95em}
table.tb th,table.tb td{border:1px solid var(--line);padding:4px 8px}
table.tb th{background:var(--box)}
/* ★ 그림도 글자를 따라 커진다(em). px 로 두면 글자만 커지고 그림 속 글씨는
   그대로라, 그림 설명이 본문보다 작아지는 자리가 다시 생긴다. */
.fig{margin:0 0 7px}
.fig img{max-width:76%;max-height:16em}
ol.ch{margin:0 0 7px;padding:0;list-style:none}
ol.ch li{margin:0 0 2px;padding-left:1.4em;position:relative}
ol.ch li .c{position:absolute;left:0;font-weight:700}
ol.ch li.a{font-weight:700}
ol.ch li.a::after{content:"  ← 정답";color:var(--ok);font-size:.85em;font-weight:700}
.ex{background:#f2f7f4;border-left:3px solid var(--ok);border-radius:0 5px 5px 0;
  padding:7px 10px;margin:5px 0 0;white-space:pre-wrap;font-size:.96em}
.ex b{color:var(--ok)}
/* ★ 해설 안에 인라인으로 들어온 '답이 채워진 판'. 지문 판(.fig)보다 조금 작게 둔다 —
   같은 그림을 두 번 보는 자리라 크기가 같으면 어느 쪽이 답인지 한눈에 안 갈린다.
   `display:block` 이 아니면 pre-wrap 줄바꿈과 겹쳐 글자 옆에 붙는다. */
.psg img,.qt img,.ex img{display:block;max-width:64%;max-height:14em;margin:6px 0 2px}

/* 슬라이드 대본
   ★ 열 비율의 근거: 화면(heading)은 '3번 문제' 처럼 짧고 읽는 말(narration)은 길다.
     1:1.25 로 두면 heading 쪽에 빈 공간이 남아 그만큼 페이지가 늘어난다 → .38:1.62.
     번호 열은 두 자리면 충분하다(22px → 18px). 열 간격도 9px → 6px.

   ★ 행 높이(padding:7px)는 **줄이지 않는다.** 검수자가 적색펜으로 ㄱ·ㄴ·ㄷ 같은 표시를
     손으로 적어 온다 — 줄 사이에 쓸 자리가 없으면 종이 검수 자체가 안 된다.
     페이지를 줄이는 것은 열 폭과 빈 줄 접기로 한다(가로는 남고 세로는 필요하다). */
.sc{page-break-inside:avoid;break-inside:avoid;display:grid;
  grid-template-columns:18px minmax(70px,.38fr) 1.62fr;gap:6px;padding:7px 0;
  border-bottom:1px solid var(--line);align-items:start}
.sc .n{color:var(--mute);font-size:.8em;text-align:right;padding-top:2px}
.sc .hd{font-weight:700}
.sc .hd .k{display:block;color:var(--mute);font-size:.78em;font-weight:400}
.sc .nr{white-space:pre-wrap}
.sc.nocap{background:#fbfbf8}
.sc.nocap .hd::after{content:" (캡처 안 함)";color:var(--mute);font-size:.78em;font-weight:400}

/* ★ 읽는 말이 없는 씬(gap·countdown)은 **한 줄로 접는다.**
   내용이 없는데 정상 행 높이를 먹어서, 번들 하나에 그런 줄이 10개 넘으면 그것만으로
   페이지가 한 장씩 늘어난다. 접어도 정보는 다 남는다(번호·제목·종류). */
.sc.thin{grid-template-columns:18px 1fr;padding:3px 0;font-size:.85em;
  color:var(--mute);background:transparent}
.sc.thin .hd{font-weight:400;display:flex;gap:7px;align-items:baseline}
.sc.thin .hd .k{display:inline;font-size:.9em}
.sc.thin .hd::after{content:none}

.schead{display:grid;grid-template-columns:18px minmax(70px,.38fr) 1.62fr;gap:6px;
  border-bottom:2px solid var(--ink);padding:0 0 4px;font-size:.85em;color:var(--mute)}

/* ★ '조밀 모드' 는 두지 않는다.
   한 장에 2쪽으로 얹는 것은 인쇄 대화상자가 하는 일이고, 사용자가 그때 정한다.
   여기서 미리 줄여 두면 축소가 두 번 겹쳐서 읽을 수 없게 된다.
   페이지를 줄이는 것은 열 비율과 빈 줄 접기로 이미 했다 — 그건 한 쪽 인쇄에서도
   이득이라 항상 켠다. */

@media print{
  body{padding:0}
  .toolbar{display:none}
  .q,.sc{border-bottom-color:#bbb}
  a{color:inherit;text-decoration:none}
  /* ★ 용지 페이지 번호는 **CSS 로 못 넣는다.** `@page{ @bottom-center{
     content:counter(page) } }` 은 Paged Media 규격이지만 Chrome·Edge 가 구현하지
     않았다(2026-08-20 확인). 넣어도 아무것도 안 나온다.
     → 인쇄 대화상자의 **「머리글 및 바닥글」을 켜면** 브라우저가 넣어 준다.
       URL·날짜도 같이 들어가는 것이 그 옵션의 값이다. 화면 위 안내가 그렇게 적어 둔다. */
  @page{size:A4;margin:14mm 12mm}
}
"""


def _page(title: str, toolbar: str, body: str, mathjax: bool = True) -> str:
    """공통 껍데기.

    ★ MathJax 는 `pre`·`code` 를 건드리지 않게 제외한다. SQL 박스 안의 `$` 를
      수식으로 먹으면 쿼리가 통째로 사라진다(실제로 겪은 종류의 사고다).
    """
    mj = ""
    if mathjax:
        mj = """
<script>
window.MathJax = {
  tex: { inlineMath: [['$','$'],['\\\\(','\\\\)']], displayMath: [['$$','$$'],['\\\\[','\\\\]']] },
  options: { skipHtmlTags: ['script','noscript','style','textarea','pre','code'] },
  svg: { fontCache: 'global' }
};
</script>
<script src="/static/vendor/tex-svg.js" id="MathJax-script"></script>
"""
    return (
        "<!DOCTYPE html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
        f"<title>{_h(title)}</title>\n<style>{_CSS}</style>{mj}</head><body>\n"
        f"{toolbar}\n{body}\n</body></html>\n"
    )


def _toolbar(links: list[tuple[str, str, bool]], note: str, extra: str = "") -> str:
    """`extra` 는 그 문서에만 있는 손잡이다(문항 인쇄본의 글자 크기·쪽당 문항).

    대본 인쇄본에는 넣지 않는다 — 거기서 쪽당 문항은 뜻이 없다.
    """
    out = ['<div class="toolbar">']
    out.append('<button type="button" onclick="window.print()">인쇄 · PDF 저장</button>')
    for href, label, on in links:
        out.append(f'<a class="{"on" if on else ""}" href="{_h(href)}">{_h(label)}</a>')
    out.append(extra)
    out.append(f'<span class="sp">{_h(note)}</span>')
    # ★ 페이지 번호는 브라우저가 넣는다. CSS 로는 안 된다(위 `@page` 머리말) —
    #   그래서 「어디를 켜야 하는지」 를 이 자리에서 말해 준다. 종이로 검수할 때
    #   번호가 없으면 「뒤쪽 어디」 밖에 못 짚는다(2026-08-20 요청).
    out.append('<span class="sp" style="color:#a15c00">'
               '용지 페이지 번호 — 인쇄 대화상자에서 '
               '<b>「머리글 및 바닥글」</b> 을 켜십시오'
               '(Chrome·Edge: 「설정 더보기」 안에 있습니다). '
               'CSS 로는 넣을 수 없습니다.</span>')
    out.append('</div>')
    return "".join(out)


# ★ 문항 인쇄본에만 붙는 손잡이. 고른 값은 localStorage 에 남는다 — 검수는 여러 번
#   나눠 인쇄하는 일이라, 열 때마다 다시 고르게 하면 인쇄본마다 크기가 달라진다.
#
#   왜 서버가 아니라 브라우저에 두는가: 이 값은 **인쇄하는 사람**의 취향이고 책의
#   속성이 아니다. 종이를 받는 사람마다 다르다(돋보기 쓰는 검수자가 있다).
_QCTL = """
<span class="ctl">글자
  <button type="button" data-fs="11pt">11</button>
  <button type="button" data-fs="12pt">12</button>
  <button type="button" data-fs="13pt">13</button>
  <button type="button" data-fs="14pt">14</button></span>
<span class="ctl">쪽당
  <button type="button" data-pp="auto">자동</button>
  <button type="button" data-pp="2">2문항</button>
  <button type="button" data-pp="1">1문항</button></span>
<script>
(function(){
  var B = document.body;
  function save(k, v){ try { localStorage.setItem(k, v); } catch (e) {} }
  function load(k, d){ try { return localStorage.getItem(k) || d; } catch (e) { return d; } }
  function mark(a, v){
    document.querySelectorAll('[data-' + a + ']').forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-' + a) === v);
    });
  }
  function fs(v){ B.style.setProperty('--fs', v); mark('fs', v); save('xam.print.fs', v); }
  function pp(v){
    B.classList.remove('pp1', 'pp2');
    if (v === '1' || v === '2') B.classList.add('pp' + v);
    mark('pp', v); save('xam.print.pp', v);
  }
  document.querySelectorAll('[data-fs]').forEach(function(b){
    b.onclick = function(){ fs(b.getAttribute('data-fs')); };
  });
  document.querySelectorAll('[data-pp]').forEach(function(b){
    b.onclick = function(){ pp(b.getAttribute('data-pp')); };
  });
  fs(load('xam.print.fs', '12pt'));
  pp(load('xam.print.pp', 'auto'));
})();
</script>
"""


# ─────────────────────────────────────────────────────────────────────────────
# ① 문항 인쇄본
# ─────────────────────────────────────────────────────────────────────────────

def rounds() -> list[int]:
    return sorted({int(p.get("rd_no") or 0) for p in _load_problems()} - {0})


def _table_html(tj) -> str:
    """`table_json` → 표. 형식이 여러 가지라 방어적으로 읽는다."""
    if not tj:
        return ""
    t = tj
    if isinstance(t, str):
        try:
            t = json.loads(t)
        except (ValueError, TypeError):
            return ""
    rows = None
    if isinstance(t, dict):
        rows = t.get("rows") or t.get("data") or t.get("body")
        head = t.get("head") or t.get("header") or t.get("columns")
    else:
        rows, head = t, None
    if not isinstance(rows, list) or not rows:
        return ""
    out = ['<table class="tb">']
    if isinstance(head, list) and head:
        out.append("<tr>" + "".join(f"<th>{_h(c)}</th>" for c in head) + "</tr>")
    for r in rows:
        cells = r if isinstance(r, list) else [r]
        out.append("<tr>" + "".join(f"<td>{_h(c)}</td>" for c in cells) + "</tr>")
    out.append("</table>")
    return "".join(out)


def _one_question(p: dict) -> str:
    n = int(p.get("pr_no") or 0)
    ai = p.get("answer_index")
    ai = int(ai) if isinstance(ai, int) or (isinstance(ai, str) and ai.isdigit()) else -1

    tags = []
    if p.get("sj_name"):
        tags.append(f'<span class="tag">{_h(p["sj_name"])}</span>')
    if p.get("difficulty"):
        tags.append(f'<span class="tag d">난이도 {_h(p["difficulty"])}</span>')
    for t in (p.get("tags_json") or []):
        if isinstance(t, str) and t:
            tags.append(f'<span class="tag">{_h(t)}</span>')
    # ★ 검수 표시를 인쇄물에 남긴다. 종이로 보는 목적의 절반이 '아직 안 본 것' 찾기다.
    if p.get("needs_review"):
        tags.append('<span class="tag d">검수 필요</span>')

    out = ['<div class="q">', '<div class="qh">',
           f'<span class="no">{n}.</span>', "".join(tags),
           f'<span class="key">{_h(p.get("pr_key"))}</span>', "</div>"]

    if p.get("passage"):
        out.append(f'<div class="psg">{_rich(p["passage"])}</div>')
    out.append(f'<div class="qt">{_rich(p.get("question"))}</div>')
    if p.get("sql_text"):
        out.append(f'<pre class="sql">{_h(p["sql_text"])}</pre>')
    out.append(_table_html(p.get("table_json")))
    for f in (p.get("figures_json") or []):
        if isinstance(f, str) and f:
            out.append(f'<div class="fig"><img src="{_h(_fig_url(f))}" alt="{_h(f)}"></div>')

    ch = p.get("choices_json") or []
    if isinstance(ch, str):
        try:
            ch = json.loads(ch)
        except (ValueError, TypeError):
            ch = []
    out.append('<ol class="ch">')
    for i, c in enumerate(ch):
        mark = _CIRCLE[i] if i < len(_CIRCLE) else str(i + 1)
        cls = " class=\"a\"" if i == ai else ""
        out.append(f'<li{cls}><span class="c">{mark}</span>{_h(c)}</li>')
    out.append("</ol>")

    if p.get("explanation"):
        out.append(f'<div class="ex"><b>해설</b> {_rich(p["explanation"])}</div>')
    out.append("</div>")
    return "".join(out)


def questions_html(rd: int | None = None) -> str:
    PD_CODE, PD_LABEL = _pd_code(), _pd_label()

    ps = _load_problems()
    rs = rounds()
    if rd:
        ps = [p for p in ps if int(p.get("rd_no") or 0) == int(rd)]

    links = [("/print/questions", "전체", rd is None)]
    for r in rs:
        links.append((f"/print/questions?rd={r}", f"{r}회", rd == r))
    links.append(("/print/", "← 목록", False))

    body = [f"<h1>{_h(PD_LABEL)} — 문항 인쇄본</h1>",
            f'<p class="sub">{_h(PD_CODE)} · {len(ps)}문항'
            + (f" · {rd}회차" if rd else f" · {len(rs)}회차 전체")
            + " · 정답과 해설이 함께 나옵니다 (검수용)</p>"]

    for r in ([rd] if rd else rs):
        rp = sorted([p for p in ps if int(p.get("rd_no") or 0) == r],
                    key=lambda x: int(x.get("pr_no") or 0))
        if not rp:
            continue
        nr = sum(1 for p in rp if p.get("needs_review"))
        # ★ 첫 회차만 표시한다 — CSS 의 `.part.first` 가 이걸 보고 새 장 밀기를 끈다.
        #   `:first-of-type` 으로는 안 된다(body 의 첫 div 는 도구막대다).
        first = " first" if not any('class="part' in b for b in body) else ""
        body.append(f'<div class="part{first}">'
                    f'<h2>{r}회차</h2>'
                    f'<div class="m">{len(rp)}문항'
                    + (f" · 검수 필요 {nr}건" if nr else "")
                    + "</div></div>")
        # ★ 문항을 감싼다 — '쪽당 2문항' 을 셀 기준이 있어야 한다. 회차마다 새로
        #   세므로 회차가 바뀌면 1번부터 다시 짝을 짓는다.
        body.append('<div class="qs">')
        body += [_one_question(p) for p in rp]
        body.append("</div>")

    note = ("Ctrl+P → 대상을 'PDF로 저장' · 용지 A4 · 배경 그래픽 켜기 · "
            "배율은 100% 로 두십시오(줄이면 위에서 고른 글자 크기가 무의미해집니다)")
    return _page(f"{PD_LABEL} 문항 인쇄본",
                 _toolbar(links, note, _QCTL), "".join(body))


# ─────────────────────────────────────────────────────────────────────────────
# ② 슬라이드 대본 인쇄본
# ─────────────────────────────────────────────────────────────────────────────

def bundles() -> list[str]:
    d = os.path.join(paths.book_dir(), "05")
    if not os.path.isdir(d):
        return []
    return sorted(n for n in os.listdir(d)
                  if re.fullmatch(r"m\d{2}-\d{1,2}", n)
                  and os.path.isdir(os.path.join(d, n)))


def _scenes(bundle: str) -> tuple[dict, list[dict]]:
    """그 번들의 대본. `script/<번들>_script.json` 이 정본이다.

    ★ `source/slides.json` 은 heading 만 있고 나레이션이 없다. 반대로 script 에는
      둘이 다 있다 — 그래서 script 를 읽는다. 이름이 비슷해 헷갈리는 자리다.
    """
    p = os.path.join(paths.book_dir(), "05", bundle, "script", f"{bundle}_script.json")
    if not os.path.isfile(p):
        return {}, []
    d = json.load(open(p, encoding="utf-8"))
    return d, (d.get("scenes") or [])


def lesson_html(bundle: str | None = None) -> str:
    PD_LABEL = _pd_label()

    bs = bundles()
    sel = (bundle or "").strip()

    # ★ 회차 단위도 받는다 — `?b=m01`. 번들은 10문항 단위라 한 회차가 5~8편이고,
    #   "1·2회만 뽑아서 들어 본다" 는 것이 실제 사용법이다. 편별로 누르면
    #   SQLD 는 10번, 빅분기는 16번을 눌러야 했다.
    if sel and re.fullmatch(r"m\d{2}", sel):
        show = [b for b in bs if b.startswith(sel + "-")]
    elif sel and sel in bs:
        show = [sel]
    elif sel:
        show = []
    else:
        show = bs

    rounds_ = sorted({b.split("-")[0] for b in bs})
    links = [("/print/lesson", "전체", sel == "")]
    for r in rounds_:
        links.append((f"/print/lesson?b={r}", r.replace("m", "") + "회", sel == r))
    for b in bs:
        links.append((f"/print/lesson?b={b}", b, sel == b))
    links.append(("/print/", "← 목록", False))

    n_sc = 0
    body = [f"<h1>{_h(PD_LABEL)} — 슬라이드 대본 인쇄본</h1>"]
    parts = []
    for b in show:
        meta, sc = _scenes(b)
        if not sc:
            parts.append(f'<div class="part"><h2>{_h(b)}</h2>'
                         '<div class="m">대본이 없습니다 — 이 번들은 아직 만들지 않았습니다.</div></div>')
            continue
        n_sc += len(sc)
        parts.append('<div class="part">'
                     f'<h2>{_h(b)} — {_h(meta.get("round") or "")}</h2>'
                     f'<div class="m">{len(sc)}씬 · 목소리 {_h(meta.get("voice") or "?")}'
                     f' · 속도 {_h(meta.get("speed") or "?")}</div></div>')
        parts.append('<div class="schead"><div>#</div><div>화면(슬라이드)</div>'
                     '<div>읽는 말(나레이션)</div></div>')
        for s in sc:
            cap = bool(s.get("capture", True))
            nr = (s.get("narration_text") or s.get("narration") or "").strip()
            # ★ 읽는 말이 없는 씬(gap·countdown)은 두 칸으로 접는다. 번들 하나에 그런
            #   줄이 10개 넘어서, 접기만 해도 페이지가 눈에 띄게 줄어든다.
            if nr == "":
                parts.append(
                    f'<div class="sc thin">'
                    f'<div class="n">{int(s.get("scene") or 0)}</div>'
                    f'<div class="hd">{_h(s.get("heading"))}'
                    f'<span class="k">{_h(s.get("kind"))}</span></div></div>')
                continue
            parts.append(
                f'<div class="sc{"" if cap else " nocap"}">'
                f'<div class="n">{int(s.get("scene") or 0)}</div>'
                f'<div class="hd">{_h(s.get("heading"))}'
                f'<span class="k">{_h(s.get("kind"))}</span></div>'
                f'<div class="nr">{_h(nr)}</div></div>')

    n_thin = sum(1 for b in show for s in _scenes(b)[1]
                 if not (s.get("narration_text") or s.get("narration") or "").strip())
    body.append(f'<p class="sub">{len(show)}번들 · {n_sc}씬 · '
                "왼쪽이 화면에 나오는 것, 오른쪽이 읽는 말입니다."
                + (f" 읽는 말이 없는 {n_thin}줄(gap·countdown)은 한 줄로 접었습니다."
                   if n_thin else "")
                + "</p>")
    body += parts

    note = "Ctrl+P → 'PDF로 저장' · 용지 A4 (2쪽·양면은 인쇄할 때 정하십시오)"
    return _page(f"{PD_LABEL} 슬라이드 대본", _toolbar(links, note), "".join(body))


# ─────────────────────────────────────────────────────────────────────────────
# ③ 목록
# ─────────────────────────────────────────────────────────────────────────────

# ── 슬라이드 장수표 인쇄본 ──────────────────────────────────────────────────
# ★ **종이로 대조하는 자리다.** PowerPoint 로 100편을 넘겨 보면서 "이 문항은 줄였다"
#   를 손으로 체크해야 하는데, 화면 표는 스크롤이라 옆에 둘 수 없다(2026-08-25 요청).
#   그래서 **회차 하나가 한 쪽**이다 — 20회차면 20쪽이 나온다.
#
# ★ 줄인 것을 눈에 걸리게 한다. 배율이 1.00 보다 작으면 그 문항만 글자가 작아졌다는
#   뜻이고, 그게 곧 "내가 줄인 것" 이다. `☑ 고정` 은 다음에 만들 때도 지킬 값이다.

_SLIDE_CSS = """
.sl-round{page-break-after:always}
.sl-round:last-child{page-break-after:auto}
.sl-head{display:flex;align-items:baseline;gap:12px;
         border-bottom:2px solid #333;padding-bottom:4px;margin:0 0 8px}
.sl-head h2{margin:0;font-size:15pt}
.sl-head .sum{margin-left:auto;font-size:9.5pt;color:#555}
.sl-tb{width:100%;border-collapse:collapse;font-size:10pt}
.sl-tb th,.sl-tb td{border-bottom:1px solid #ddd;padding:3px 5px;text-align:left}
.sl-tb th{background:#f2f2f2;font-weight:600;border-bottom:1px solid #999}
.sl-tb td.n{text-align:center;font-variant-numeric:tabular-nums}
.sl-tb tr.cut td{background:#fdf3e7}
.sl-tb tr.miss td{background:#fdeaea}
.sl-tb tr.fend td{border-bottom:1.6px solid #666}
.sl-tb td.rem{white-space:nowrap}
.sl-tb .tot{float:right;margin-left:10px}
.sl-note{font-size:9pt;color:#666;margin:6px 0 0}
"""


def slides_rounds() -> list[str]:
    """장수표가 있는 회차. `pages.json` 이 있는 번들이 하나라도 있으면 낸다."""
    from services.deck import pptxdeck
    out = []
    for rc in paths.round_codes():
        if any(os.path.isfile(paths.bundle_pages(b))
               for b in pptxdeck.bundles_of(rc)):
            out.append(rc)
    return out


def _pptx_stem(bundle: str) -> str:
    """번들 → PowerPoint 로 열 **파일 이름**(확장자 없이).

    ★ 종이에는 `m01-2` 가 아니라 파일명을 적는다(2026-08-25 요청). 검수는
      PowerPoint 를 열어 놓고 하는데, 번들 코드는 그 창 어디에도 안 보인다 —
      종이와 창을 맞추려면 파일 이름이 있어야 한다.
    """
    if not bundle:
        return ""
    try:
        return os.path.splitext(paths.pptx_name(bundle))[0]
    except Exception:                                        # noqa: BLE001
        return bundle


def _bundle_slides(bundle: str) -> int:
    """그 편의 **pptx 장 수**. PowerPoint 가 보여주는 수와 같다.

    ★ 표의 `합`(문제+해설)과 다르다 — 파일 앞에 간지가 한 장 더 있다. 종이에서
      "이 파일은 몇 장짜리" 를 보려면 간지를 포함한 실제 장 수여야 한다.
    """
    p = paths.bundle_pages(bundle)
    if not os.path.isfile(p):
        return 0
    try:
        with open(p, encoding="utf-8") as f:
            return int(json.load(f).get("slides") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _slide_round_html(rc: str) -> str:
    from services.deck import pptxdeck

    t = pptxdeck.pages_table(rc)
    qs = t.get("questions") or []
    if not qs:
        return ""
    cut = sum(1 for q in qs if float(q.get("scale") or 1) < 0.999)
    locked = sum(1 for q in qs if q.get("lock"))
    missed = sum(1 for q in qs if q.get("missed"))
    slides = t.get("slides") or 0

    out = ['<section class="sl-round">']
    out.append('<div class="sl-head">')
    out.append(f"<h2>{_h(rc)} 슬라이드 장수</h2>")
    out.append(f'<span class="sum">문항 {len(qs)} · 장 {slides} · '
               f'줄인 문항 {cut} · 고정 {locked}'
               + (f' · 지정 실패 {missed}' if missed else '') + "</span>")
    out.append("</div>")
    out.append('<table class="sl-tb"><thead><tr>'
               "<th>문항</th><th>파일</th>"
               "<th>문제</th><th>해설</th><th>합</th>"
               "<th>배율</th><th>채움</th><th>비고</th>"
               "</tr></thead><tbody>")
    for i, q in enumerate(qs):
        sc = float(q.get("scale") or 1)
        cls = ["miss"] if q.get("missed") else (["cut"] if sc < 0.999 else [])
        bundle = q.get("bundle") or ""
        nxt = qs[i + 1].get("bundle") if i + 1 < len(qs) else None
        last_of_file = bundle != nxt              # 이 편의 마지막 문항인가
        if last_of_file:
            cls.append("fend")
        note = []
        if q.get("missed"):
            note.append("지정 실패 — 자연 장수로 돌아감")
        elif sc < 0.999:
            note.append("줄여서 글자가 작아짐")
        if q.get("lock"):
            note.append("고정")
        # ★ 편의 **맨 끝 문항 행**에 그 파일의 총 장 수를 적는다(2026-08-25 요청).
        #   PowerPoint 를 열면 좌측 축소판이 몇 장인지 바로 보이는데, 종이에 그 수가
        #   없으면 대조할 기준이 없다. 간지 한 장이 포함된 실제 파일 장 수다.
        tail = ""
        if last_of_file:
            n = _bundle_slides(bundle)
            tail = (f'<b>이 파일 {n}장</b>' if n else "")
        p, a = int(q.get("problem") or 0), int(q.get("answer") or 0)
        out.append(
            f'<tr class="{" ".join(cls)}">'
            f'<td class="n">{q.get("no")}</td>'
            f'<td>{_h(_pptx_stem(bundle))}</td>'
            f'<td class="n">{p}</td><td class="n">{a}</td>'
            f'<td class="n">{p + a}</td>'
            f'<td class="n">{sc:.2f}</td>'
            f'<td class="n">{float(q.get("fill") or 0):.2f}</td>'
            f'<td class="rem">{_h(" · ".join(note))}'
            + (f'<span class="tot">{tail}</span>' if tail else "")
            + "</td></tr>")
    out.append("</tbody></table>")
    out.append('<p class="sl-note">색이 깔린 줄 = 장수를 줄인 문항(주황) · '
               "지정을 못 맞춘 문항(빨강). 편이 끝나는 줄에 그 파일의 총 장 수를 "
               "적었습니다(간지 1장 포함). 고칠 것은 앱의 ③ 장수 확정 표에서 "
               "± 로 고치십시오.</p>")
    out.append("</section>")
    return "".join(out)


def slides_html(rd: str | None = None) -> str:
    """장수표 인쇄본. `rd` 를 주면 그 회차만, 없으면 **전 회차(회차당 한 쪽)**."""
    codes = slides_rounds()
    if not codes:
        raise ValueError("장수표가 없습니다 — 「슬라이드」 화면에서 ② PPTX 만들기를 "
                         "먼저 돌리십시오.")
    if rd:
        rc = rd if str(rd).startswith("m") else paths.round_code(int(rd))
        if rc not in codes:
            raise ValueError(f"{rc}: 장수표가 없습니다.")
        codes = [rc]

    links = [("/print/slides", "전체", not rd)]
    links += [(f"/print/slides?rd={c}", c, rd == c) for c in slides_rounds()]
    label = _pd_label()
    body = "<style>" + _SLIDE_CSS + "</style>"
    body += "".join(_slide_round_html(c) for c in codes)
    note = (f"{len(codes)}회차 · 회차당 한 쪽" if len(codes) > 1
            else f"{codes[0]} 한 쪽")
    return _page(f"{label} 슬라이드 장수표",
                 _toolbar(links, note), body, mathjax=False)


# ③ 이론 요약노트 인쇄본
#
# ★ 요약노트는 이미 HTML 이라 브라우저로 열어 인쇄하면 된다. 그런데 인쇄본 목록에
#   단추가 없어서 파일을 찾아 열어야 했다(2026-08-26 지적). 다른 둘과 같은 자리에 둔다.
# ★ 다시 그리지 않는다 — `03/summary_<key>.html` 을 **그대로** 담는다. 발행되는 것이
#   그 파일이라, 인쇄본이 다르게 보이면 검수의 뜻이 없다.


def summary_keys() -> list[str]:
    return [k for k in paths.summary_keys()
            if os.path.isfile(paths.summary_html(k))]


def summary_html(key: str | None = None) -> str:
    """요약노트 인쇄본. `key` 가 없으면 있는 것을 차례로 이어 붙인다."""
    keys = [key] if key else summary_keys()
    if not keys:
        raise FileNotFoundError(
            '요약노트 HTML 이 없습니다 — 03/summary_<과목>.html 을 먼저 만드십시오.')
    parts = []
    for k in keys:
        fp = paths.summary_html(k)
        if not os.path.isfile(fp):
            raise FileNotFoundError('요약노트가 없습니다: ' + paths.rel(fp))
        with open(fp, encoding='utf-8') as f:
            raw = f.read()
        # ★ <body> 를 찾기 전에 **주석과 <style> 을 먼저 걷어낸다.**
        #   이 파일들의 설명글 안에 `<body>`·`<script>` 라고 **적혀** 있다. 그 글이
        #   HTML 주석이면 첫 줄만 남고(2026-08-26), CSS 주석이면 더 나쁘다 —
        #   `<body>` 부터 잘려 나온 조각에 `<script>` 라는 글자가 들어가고, 브라우저가
        #   그것을 진짜 script 로 읽어 **뒤의 본문을 통째로 삼킨다**(실측 2026-08-27 —
        #   요약노트 인쇄본이 한 줄만 나오고 백지였다).
        #   발행 쪽(`build_check.build_theory`)도 style 을 먼저 지우고 body 를 찾는다.
        #   같은 순서로 맞춘다 — 인쇄본과 웹이 갈리면 검수의 뜻이 없다.
        clean = re.sub(r'<!--.*?-->', '', raw, flags=re.S)
        # 그 파일의 <style> 은 살린다. 표·도식 모양이 거기서 온다.
        css = ''.join(re.findall(r'<style[^>]*>.*?</style>', clean, re.S | re.I))
        naked = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.S | re.I)
        # <body> 안만 꺼낸다 — <head> 의 <title> 은 페이지 껍데기가 이미 있다.
        m = re.search(r'<body[^>]*>(.*)</body>', naked, re.S | re.I)
        inner = m.group(1) if m else naked
        parts.append('<div class="part">' + css + inner + '</div>')
    PD_LABEL = _pd_label()
    links = [('/print/summary', '전체 %d과목' % len(summary_keys()), not key)]
    links += [('/print/summary?k=' + k, k, key == k) for k in summary_keys()]
    tb = _toolbar(links, '%d과목' % len(keys))
    return _page('%s 요약노트' % PD_LABEL, tb, ''.join(parts), mathjax=True)

def index_html() -> str:
    PD_CODE, PD_LABEL = _pd_code(), _pd_label()

    try:
        ps = _load_problems()
        n_q, rs = len(ps), rounds()
        nr = sum(1 for p in ps if p.get("needs_review"))
        q_line = (f"{n_q}문항 · {len(rs)}회차"
                  + (f" · <b>검수 필요 {nr}건</b>" if nr else " · 검수 필요 0건"))
        q_ok = True
    except (FileNotFoundError, ValueError) as e:
        q_line, q_ok, rs = _h(str(e).splitlines()[0]), False, []

    bs = bundles()
    body = [f"<h1>{_h(PD_LABEL)} — 인쇄본</h1>",
            f'<p class="sub">{_h(PD_CODE)} · {_h(paths.book_dir())}<br>'
            "파일을 만들지 않습니다. 열 때마다 <b>지금 데이터</b>로 그립니다 — "
            "낡은 종이를 들고 검수할 일이 없습니다.</p>"]

    body.append('<div class="part"><h2>① 문항 인쇄본</h2>'
                f'<div class="m">{q_line}</div></div>')
    if q_ok:
        row = [f'<a href="/print/questions">전체 {len(rs)}회차</a>']
        row += [f'<a href="/print/questions?rd={r}">{r}회</a>' for r in rs]
        body.append('<div class="toolbar" style="position:static;border:0">'
                    + "".join(row) + "</div>")
        body.append('<p class="sub">문제 · 보기 · <b>정답</b> · 해설 · 난이도 · 태그가 '
                    '함께 나옵니다. 한 문항이 페이지에 걸쳐 잘리지 않게 잡아 뒀습니다.</p>')

    body.append('<div class="part" style="page-break-before:auto"><h2>② 슬라이드 대본 인쇄본</h2>'
                f'<div class="m">{len(bs)}번들</div></div>')
    if bs:
        row = [f'<a href="/print/lesson">전체 {len(bs)}번들</a>']
        row += [f'<a href="/print/lesson?b={b}">{b}</a>' for b in bs]
        body.append('<div class="toolbar" style="position:static;border:0;max-height:none">'
                    + "".join(row) + "</div>")
        body.append('<p class="sub">씬마다 <b>화면에 나오는 것</b>과 <b>읽는 말</b>을 '
                    '나란히 둡니다. 캡처하지 않는 씬(카운트다운 등)은 회색입니다.</p>')

    sk = summary_keys()
    body.append('<div class="part" style="page-break-before:auto">'
                '<h2>③ 이론 요약노트 인쇄본</h2>'
                f'<div class="m">{len(sk)}과목</div></div>')
    if sk:
        row = [f'<a href="/print/summary">전체 {len(sk)}과목</a>']
        row += [f'<a href="/print/summary?k={k}">{k}</a>' for k in sk]
        body.append('<div class="toolbar" style="position:static;border:0">'
                    + "".join(row) + "</div>")
        body.append('<p class="sub">발행되는 <b>그 HTML 그대로</b> 담습니다 — '
                    '인쇄본과 웹 화면이 다를 일이 없습니다. 브라우저 인쇄에서 '
                    '<b>PDF 로 저장</b>을 고르시면 됩니다.</p>')
    else:
        body.append('<p class="sub">03/summary_&lt;과목&gt;.html 이 없습니다 — '
                    '요약노트를 먼저 만드십시오.</p>')

    return _page(f"{PD_LABEL} 인쇄본", "", "".join(body), mathjax=False)
