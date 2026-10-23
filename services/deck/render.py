# -*- coding: utf-8 -*-
"""lesson JSON → 슬라이드 HTML. **이 앱의 유일한 슬라이드 HTML 생성기.**

미리보기와 베이크가 **같은 함수**를 쓴다:

    미리보기 : HTMLResponse( render_deck(lesson) )
    베이크   : deck.html.write_text( render_deck(lesson) )   ← 같은 문자열

showcase-agent `render/slides.py` 머리말이 그 이유를 이미 적어 뒀다 —
*"셋이 갈라지면 OK 한 면과 나가는 면이 달라진다."* 그 결론을 그대로 가져왔다.

★ CSS 를 **인라인으로** 심는다. 링크하지 않는다 — 캡처가 `file://` 로 열리므로
  (`deck_capture.py:42`) 상대경로 CSS 는 번들 안에 복사돼야 하고, 그 복사가 낡으면
  조용히 옛 모양으로 찍힌다. `bundle.py:963-976` 의 chmod/PermissionError 방어 코드가
  전부 그 복사 때문에 생긴 것이다.

★ 수식(MathJax)을 넣지 않는다. `/static/vendor/tex-svg.js` 는 http 경로라 `file://`
  에서 안 뜨고, 옆에 복사하면 캡처가 타이포셋을 기다려야 한다(`networkidle` +
  `fonts.ready` 로 부족하고 `MathJax.startup.document.state()` 폴링이 필요하다).
  미리보기에만 켜면 **슬라이드에 없는 수식을 미리보기가 보여준다** — 그게 더 나쁘다.
"""
from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List, Optional

from . import paginate, theme
from .slidecss import slide_css

CIRCLED = "①②③④⑤"


def esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


# ── 마크다운(아주 좁게) ─────────────────────────────────────────────────────
# ★ escape 를 먼저 하고 그 뒤에 허용한 것만 되살린다. 순서를 뒤집으면 `<script>` 가
#   그대로 남는다. `exam/lib/md.php` 의 `ex_md_html()` 과 같은 규칙이다.
_IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def md_inline(s: str) -> str:
    out = esc(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`([^`]+?)`", r"<code>\1</code>", out)
    return out


# ★ 파이프 표. 이것이 없으면 지문이 **원문 그대로** 찍힌다 — 2026-08-12 실측:
#   m01-1 의 45번 지문이 `| 구분 | 질병 발생 | … |---|---|` 로 화면에 나갔다.
#   `_rounds` 의 지문·해설에 마크다운 표가 들어 있는데 슬라이드 렌더러가 `**굵게**` 와
#   `` `코드` `` 만 처리하고 있었다. 표로 그리면 **세로 높이도 크게 줄어든다.**
#
# ★ 한 줄로 이어진 표도 받는다. 집필 출력이 `|a|b| |---|---| |1|2|` 처럼 줄바꿈 없이
#   오는 경우가 있었다(위 45번이 그랬다). 그래서 `|` 로 나누기 전에 구분 행을 찾아
#   행 경계를 복원한다.
_TABLE_SEP = re.compile(r"^[\s|:\-]+$")


def _split_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_table(s: str) -> Optional[str]:
    """마크다운 파이프 표 → `<table>`. 표가 아니면 None."""
    text = str(s or "").strip()
    if text.count("|") < 4:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 한 줄로 뭉친 경우 — 구분 행(`---`)을 기준으로 열 수를 알아내 다시 자른다.
    if len(lines) == 1:
        # ★ 빈 칸을 먼저 걷어낸다. 행 경계의 `| |` 가 빈 토큰을 하나 만들고, 그것을
        #   세면 열 수가 1 늘어난다(실측: 4열 표가 5열로 잡혀 칸이 어긋났다).
        #   빈 칸이 있는 표를 한 줄로 쓰면 복원할 수 없다 — 그건 줄바꿈이 있어야 한다.
        cells = [c for c in _split_row(lines[0]) if c]
        seps = [i for i, c in enumerate(cells) if _TABLE_SEP.match(c)]
        if not seps or seps[0] < 1:
            return None
        ncol = seps[0]
        body = [c for c in cells if not _TABLE_SEP.match(c)]
        lines = ["|" + "|".join(body[i:i + ncol]) + "|"
                 for i in range(0, len(body), ncol)]
    rows = [_split_row(ln) for ln in lines]
    rows = [r for r in rows if not all(_TABLE_SEP.match(c or "-") for c in r)]
    if len(rows) < 2:
        return None
    head, *body = rows
    th = "".join(f"<th>{md_inline(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r) + "</tr>"
                  for r in body)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def _walk(src: str, emit) -> None:
    """마크다운 지문 → 블록. 만들 때마다 `emit(html)` 을 부른다.

    ★★ 코드펜스를 **먼저** 떼어 낸다. 이 함수가 그것을 몰라 SQL 이 글자로 흘렀다 —
      화면에 펜스가 그대로 찍히고 본문은 문단으로 쪼개져 표 아래로 새어 나갔다
      (2026-08-20 실측 · SQLD 14·19번). SQLD 는 거의 모든 문항이 SQL 이라 치명적이다.
      빅분기는 SQL 이 없어 드러나지 않았을 뿐이다.
    ★ 펜스 안은 글자 그대로다(escape). 인라인 마크다운을 적용하면 `*`·`_` 가
      들어간 SQL 이 깨진다.
    """
    holes: List[str] = []

    def _keep(m):
        body = html.escape(m.group(2).strip("\n"))
        holes.append('<pre class="code">' + body + '</pre>')
        return "\n\n\x00" + str(len(holes) - 1) + "\x00\n\n"

    src = re.sub(r"```([A-Za-z0-9_+-]*)\n([\s\S]*?)```", _keep, str(src or ""))

    for part in re.split(r"\n\s*\n", src):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"\x00(\d+)\x00", part)
        if m:
            emit(holes[int(m.group(1))])
        elif tbl := md_table(part):
            emit(tbl)
        else:
            emit('<p>' + '<br>'.join(
                md_inline(ln) for ln in part.split("\n") if ln.strip()) + '</p>')


def md_paras(s: str) -> str:
    """빈 줄로 문단을 나눈다. 조각 만들기는 `_walk` 가 한다 — `md_blocks` 와 같은 값이다."""
    out: List[str] = []
    _walk(str(s or ""), out.append)
    return "".join(out)


def md_blocks(s: str) -> List[str]:
    """`md_paras` 와 **같은 조각**을 목록으로 돌려준다.

    ★ 왜 따로 두는가. 지문을 장 사이로 흘리려면 조각이 필요한데, `md_paras` 가
      이미 조각을 만들어 `join` 으로 붙인다. 그 결과 문자열을 정규식으로 다시
      쪼개려 했더니 되돌리지 못했다(2026-08-20: 5조각이 1조각으로 돌아왔다).
      **만든 자리에서 그대로 내주는 것**이 맞다 — 두 함수가 같은 값을 보므로
      화면과 분할이 갈릴 수 없다.
    """
    out: List[str] = []
    _walk(str(s or ""), out.append)
    return out


def strip_images(s: str) -> str:
    """지문에서 인라인 그림 줄을 뺀다 — 그림은 `assets` 가 따로 들고 있어 중복이다."""
    return _IMG.sub("", str(s or "")).strip()


# ★ `ㄱ. ㄴ. ㄷ. ㄹ.` 항목 앞에서 줄을 바꾼다(2026-08-12 지시: "ㄱ. ㄴ. ㄷ. ㄹ. 앞에
#   엔터가 있어야 해요"). 집필 출력은 이것들을 **한 줄로 이어** 쓴다 — 실측:
#     "ㄱ. 고객 관계형 … 테이블 ㄴ. 웹 서버가 … 로그 ㄷ. 매장에 … 영상 ㄹ. 센서 …"
#   한 줄로 붙어 있으면 어디서 항목이 갈리는지 눈으로 못 찾는다. 세로도 오히려
#   더 먹는다(긴 한 문단이 4줄로 접히는 것보다 4항목 4줄이 짧다).
#
# ★ 문장 첫머리의 `ㄱ.` 은 건드리지 않는다(이미 줄 시작이다). 그리고 자모 뒤에
#   **마침표나 가운뎃점이 붙은 것만** 잡는다 — "그" 로 시작하는 낱말과 섞이지 않게.
# ★ 같은 줄 안의 공백만 잡는다. `\s+` 였더니 **빈 줄까지** 먹어서
#   문단 경계가 사라졌다 — 표 문단과 `ㄱㄴㄷㄹ` 문단이 한 문단이 되고, `md_table`
#   이 `ㄱ. …` 을 표 행으로 삼켰다(2026-08-20 실측 SQLD 10번: ㄱ 이 표 셀 안에
#   들어가고 ㄴㄷㄹ 은 사라졌다).
_JAMO_ITEM = re.compile(r"(?<=\S)[ \t]+(?=[ㄱ-ㅎ]\s*[.·)]\s)")


def br_jamo(s: str) -> str:
    return _JAMO_ITEM.sub("\n", str(s or ""))


# ── 슬라이드 1장 ────────────────────────────────────────────────────────────
def _head(no: Optional[int], subject: str, difficulty: str, total: int) -> str:
    """머리 — **번호와 난도만.** 첫 장에만 붙는다.

    ★ 과목 칩을 뺐다(2026-08-12 지시: "시작은 번호 난도"). 과목은 회차·편 번호로
      이미 정해져 있어 장마다 되풀이할 값이 아니고, 칩 하나가 세로를 먹는다.
    """
    bits = []
    if no is not None:
        bits.append(f'<span class="qnum">{esc(no)}번</span>')
    if difficulty:
        bits.append(f'<span class="pill pill-orange">{esc(difficulty)}</span>')
    return f'<div class="s-head">{"".join(bits)}</div>'


def _foot(i: int, total: int, title: str) -> str:
    """푸터 — **페이지 번호만.** 끝 장에만 붙는다.

    ★ 제목 줄("모의고사 01회 — 문제 풀이 (1/8)")을 뺐다(2026-08-12 지시: "그 줄이
      없어야 합니다"). 회차·편은 영상 템플릿이 아는 값이고, 캡처한 흰 면 안에서
      되풀이할 이유가 없다. `title` 인자는 호출부를 안 바꾸려고 남겨 둔다.
    """
    return f'<div class="s-foot"><span></span><span>{i} / {total}</span></div>'


def _figure(assets: List[str], asset_dir: str,
            inline_dir: Optional[str] = None) -> str:
    """그림. ★ 카드 안 **첫 자리**에 온다 — CSS `order:-1` 이 위치를 정한다.

    DOM 순서로 강제하지 않는 이유: 분할이 블록 목록을 재배열하므로 DOM 순서를
    믿을 수 없다. CSS 로 못박으면 어느 페이지에서든 그림이 위로 온다.

    ★ `inline_dir` 을 주면 SVG 를 **파일에서 읽어 통째로 심는다.** 베이크가 그렇게
      쓴다. 이유는 캡처가 `05/<번들>/source/deck.html` 을 `file://` 로 열기 때문이다
      — 그때 `src="assets/x.svg"` 는 `source/assets/x.svg` 를 가리키고 그런 폴더는
      없다. 그림이 조용히 안 뜬 채로 72편이 구워진다.
      ★ 번들 안으로 **복사하지 않는다.** `slidecss.py` 머리말이 그 실패를 적어 뒀다:
        "그 복사가 낡으면 조용히 옛 모양으로 찍힌다."
      미리보기는 `inline_dir` 없이 `/book` 마운트로 실제 파일을 가리킨다.
    """
    if not assets:
        return ""
    out = []
    for a in assets:
        name = str(a)
        if inline_dir:
            p = os.path.join(inline_dir, name if name.lower().endswith(".svg")
                             else f"{name}.svg")
            try:
                with open(p, encoding="utf-8") as f:
                    svg = f.read()
            except OSError:
                # ★ 조용히 넘기지 않는다. 그림이 빠진 것을 화면에서 알아야 한다.
                out.append(f'<div class="trunc-note">그림 파일을 찾지 못했습니다: '
                           f'{esc(os.path.basename(p))}</div>')
                continue
            # `<?xml ...?>` 선언과 DOCTYPE 은 인라인에서 쓸 수 없다.
            svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
            svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg, flags=re.I)
            out.append(svg.strip())
        else:
            src = f"{asset_dir}/{name}" if asset_dir else name
            out.append(f'<img class="fig" src="{esc(src)}" alt="">')
    return f'<figure class="diagram">{"".join(out)}</figure>'


def _choices(choices: List[str], answer_index: Optional[int], reveal: bool) -> str:
    """보기 4개. ★ 반드시 다 보인다 — 개수를 줄이거나 접지 않는다."""
    if not choices:
        return ""
    lis = []
    for i, c in enumerate(choices):
        cls = "opt correct" if (reveal and answer_index == i) else "opt"
        mark = CIRCLED[i] if i < len(CIRCLED) else str(i + 1)
        lis.append(f'<div class="{cls}"><span class="cn">{mark}</span>'
                   f'<span>{md_inline(c)}</span></div>')
    return f'<div class="opts">{"".join(lis)}</div>'


# ── 분할 ────────────────────────────────────────────────────────────────────
def _card(pieces_html: str, *, head: str, foot: str, cls: str) -> str:
    """슬라이드 한 장. `cls` 에 이어짐 표시(`cont-top`/`cont-bottom`)가 붙는다.

    ★ 머리·푸터를 **카드 안**에 넣는다(2026-08-12 지시: "시작도 슬라이드 기준
      최상단부터 해도 되고"). 전에는 카드 밖의 띠였고, `.slide` 이 그 자리를
      `--slide-head(50) + --slide-foot(44) + gap(24) = 118px` 로 **모든 장에서**
      잡아 두었다 — 머리도 푸터도 없는 중간 장까지 그랬다.
      안으로 넣으면 그 118px 이 내용으로 돌아오고, 없는 장은 아무 자리도 안 쓴다.
    """
    return (f'<section class="slide content{cls}" style="{theme.style_attr(True)}">'
            f'<div class="qcard">{head}{pieces_html}{foot}</div></section>')


# ★ 장수 상한을 넘으면 **글자를 조여** 담는다 — 더 쪼개지 않는다.
#   규칙(2026-08-12 지시): 해설은 **1바닥**, 문제는 최대 **2바닥**.
#   `.dense` 는 이미 있던 변형이다(`slidecss.py`: `--ts:2.30; --ss:2.05`).
#   글자 크기가 2.67 → 2.30 이므로 높이가 약 0.86배가 되고, 같은 예산에 1/0.86 ≈
#   1.16배가 들어간다. 그것으로 안 되면 그대로 둔다 — 더 조이면 영상에서 안 읽힌다.
DENSE_GAIN = 2.67 / 2.30


def _paged(pieces: List[paginate.Piece], *, first_i: int, total: int, title: str,
           head: str, cap: int = 0, want_foot: bool = True) -> List[str]:
    """조각들을 페이지로 쪼개고 **이어짐 규약**대로 머리·푸터·테두리를 켜고 끈다.

    규약(2026-08-12 사용자 확정):

        첫 장   상단 테두리 O · 머리 O · 하단 테두리 X · 푸터 X
        중간 장 상단 테두리 X · 머리 X · 하단 테두리 X · 푸터 X
        끝 장   상단 테두리 X · 머리 X · 하단 테두리 O · 푸터 O

    한 장으로 끝나면 넷 다 O — 지금까지와 같다.

    ★ 머리·푸터를 **빼는 것만으로는 안 된다.** 빼면 그 자리가 빈 채로 남아 카드가
      위아래로 뜬다. 그래서 `cont-top`/`cont-bottom` 클래스가 CSS 에서 그 띠를
      0 으로 접고 테두리를 없앤다.
    """
    pages = paginate.pack(pieces)
    dense = ""
    # ★ 조여 다시 담는 조건을 **넓혔다**(2026-08-20). 전에는 상한(`cap`) 을 넘을
    #   때만 조였는데, 문제 면 상한이 5장이 되면서 4장까지는 안 조이게 됐다.
    #   그 결과 장마다 아래가 크게 비었다 — 표 하나만 있는 장, 보기만 있는 장.
    #   **장수가 줄어들면** 조인 판을 쓴다. 줄지 않으면 원래대로 둔다(글자를
    #   괜히 작게 만들지 않는다).
    if len(pages) > 1:
        tight = paginate.pack(pieces,
                              paginate.BUDGET * DENSE_GAIN,
                              paginate.BUDGET_CONT * DENSE_GAIN)
        if len(tight) < len(pages):
            pages, dense = tight, " dense"
    n = len(pages)
    out: List[str] = []
    for k, pg in enumerate(pages):
        first, last = (k == 0), (k == n - 1)
        cls = dense
        if not first:
            cls += " cont-top"
        if not last:
            cls += " cont-bottom"
        out.append(_card(
            pg.html,
            head=(head if first else ""),
            # ★ 면마다 다르다(2026-08-12 지시): 문제 면은 페이지 번호를 안 쓰고,
            #   해설 면은 번호·난도를 안 쓴다. 그래서 머리·푸터를 각각 껐다 켠다.
            foot=(_foot(first_i + k, total, title) if (last and want_foot) else ""),
            cls=cls))
    return out


def _wrap_passage(blk: str) -> str:
    return f'<div class="passage">{blk}</div>'


def _splitter_for(blk: str, wrap=_wrap_passage):
    """이 블록을 쪼개는 함수. 표는 행으로, 코드는 줄로. 그 밖은 None.

    ★ `wrap` 을 함께 들고 다닌다. 쪼갠 조각도 `.passage` 감싸개를 써야 한다 —
      안 감싸면 그 쪽만 글자 크기·색이 달라진다.
    """
    if "<table" in blk:
        return lambda room, b=blk: _split_table(b, room, wrap)
    if "<pre" in blk:
        return lambda room, b=blk: _split_pre(b, room, wrap)
    return None


def _split_table(blk: str, room: float, wrap=_wrap_passage):
    """표를 행으로 쪼갠다. **머리(`<thead>`)는 두 쪽 모두에** 붙인다.

    ★ 머리를 안 붙이면 뒤쪽이 열 이름 없는 숫자 덩이가 된다 — 그건 표가 아니다.
    """
    m = re.search(r"<tbody>([\s\S]*?)</tbody>", blk)
    if not m:
        return None
    rows = re.findall(r"<tr>[\s\S]*?</tr>", m.group(1))
    if len(rows) < 4:                      # 3행 이하는 쪼개도 이득이 없다
        return None
    per = paginate.h_table(1)
    fit = int(max(0.0, room - paginate.h_table(1) - paginate.PASSAGE_PAD) // per)
    if fit < 2 or fit >= len(rows) - 1:    # 한 행만 남기거나 다 담기면 뜻이 없다
        return None

    def _mk(rs):
        body = "<tbody>" + "".join(rs) + "</tbody>"
        return blk[:m.start()] + body + blk[m.end():]

    a, b = _mk(rows[:fit]), _mk(rows[fit:])
    return (paginate.Piece(wrap(a), _block_h(a)),
            paginate.Piece(wrap(b), _block_h(b),
                           splitter=_splitter_for(b, wrap)))


def _split_pre(blk: str, room: float, wrap=_wrap_passage):
    """코드 박스를 줄로 쪼갠다."""
    m = re.search(r"(<pre[^>]*>)([\s\S]*?)(</pre>)", blk)
    if not m:
        return None
    lines = m.group(2).split("\n")
    if len(lines) < 6:
        return None
    per = paginate.h_table(1)
    fit = int(max(0.0, room - paginate.PASSAGE_PAD) // per)
    if fit < 3 or fit >= len(lines) - 2:
        return None
    o, c = m.group(1), m.group(3)
    a = blk[:m.start()] + o + "\n".join(lines[:fit]) + c + blk[m.end():]
    b = blk[:m.start()] + o + "\n".join(lines[fit:]) + c + blk[m.end():]
    return (paginate.Piece(wrap(a), _block_h(a)),
            paginate.Piece(wrap(b), _block_h(b),
                           splitter=_splitter_for(b, wrap)))


def _block_h(blk: str) -> float:
    """블록 하나의 높이. 표는 **행 수**로, 그 밖은 글자 수로 잰다."""
    if "<table" in blk:
        return paginate.h_table(blk.count("<tr>")) + paginate.PASSAGE_PAD
    if "<pre" in blk:
        # 코드는 줄 수로 잰다 — 글자 수로 재면 짧은 줄이 많은 SQL 이 낮게 나온다.
        n = blk.count(chr(10)) + 1
        return paginate.h_table(n) + paginate.PASSAGE_PAD
    return paginate.h_passage(blk)


def problem_slide(p: Dict[str, Any], *, i: int, total: int, title: str,
                  subject: str, asset_dir: str,
                  inline_dir: Optional[str] = None) -> List[str]:
    """문제 면 — 발문 + (지문) + 보기 4개. 정답을 아직 안 밝힌다.

    ★ **여러 장을 돌려준다.** 안전선을 넘으면 쪼갠다(`_paged`).
    """
    # ★★ 지문의 그림을 **살린다**(2026-08-20). 전에는 `strip_images` 로 떼어 냈다 —
    #   「문제 면에는 그림을 넣지 않는다(정답 노출 방지)」 가 옛 규약이었다.
    #
    #   규약이 바뀌었다: **지문의 그림은 답을 가리고, 해설의 그림은 온전하게.**
    #   그림이 문제의 조건인 문항이 있다 — ERD 를 보고 관계를 묻는 문항은 그림을
    #   빼면 문항이 성립하지 않는다. 실측(SQLD m01 5번): 지문에 ERD 가 들어 있는데
    #   슬raid 가 그것을 지워 「[학원 강좌 모델]」 한 줄만 남았다.
    #
    #   답을 가리는 일은 **집필**이 한다(`authoring/spec.py` 의 두 판 규약).
    #   렌더러는 집필이 지문에 둔 것을 그대로 보여 준다.
    passage = str(p.get("passage") or "").strip()
    chs = list(p.get("choices") or [])
    two_col = len(chs) == 4

    pieces: List[paginate.Piece] = []
    q_html = f'<div class="q">{md_inline(p.get("question"))}</div>'
    pieces.append(paginate.Piece(q_html, paginate.h_question(q_html), sticky=True))
    if passage:
        # ★ `ㄱ. ㄴ. ㄷ. ㄹ.` 앞에서 줄을 바꾼다(`br_jamo` 머리말).
        inner = md_paras(br_jamo(passage))
        # ★★ 지문을 **블록마다 조각으로** 쪼갠다 — 한 덩이로 두면 넘친 만큼 잘린다.
        #
        #   실측(2026-08-20 · SQLD m01-1): 표가 둘이거나 표+SQL 인 지문이 문제 면
        #   2장에 안 담기는데, 지문이 `Piece` 하나라 `pack` 이 나눌 수 없어 넘친
        #   부분이 **그냥 사라졌다** — 14번은 SQL 이 통째로 안 보이고 ```sql 만
        #   글자로 남았고, 12·16번은 둘째 표가 잘렸다.
        #
        #   조각으로 나누면 `pack` 이 남는 자리만큼 담고 나머지를 다음 장으로 흘린다.
        #   지우지 않고 **이어 보이게** 하는 것이 목표다(2026-08-20 지시).
        blks = md_blocks(br_jamo(passage))
        for bi, blk in enumerate(blks):
            # ★ 표·코드 **바로 앞의 짧은 문단**은 이름표다(「[SALES]」). `sticky` 로
            #   두면 다음 조각과 같은 장에 간다 — 이름표만 남고 표가 넘어가는 일을 막는다.
            nxt = blks[bi + 1] if bi + 1 < len(blks) else ""
            lab = (blk.startswith("<p")
                   and len(re.sub(r"<[^>]+>", "", blk)) <= 40
                   and nxt.startswith(("<table", "<pre")))
            pieces.append(paginate.Piece(
                f'<div class="passage">{blk}</div>', _block_h(blk),
                with_next=lab, splitter=_splitter_for(blk)))
    # ★★ 지문이 가리킨 그림을 **여기** 그린다(`passage_assets`). 해설 그림과 다른
    #   것이다 — 어디에 있었는지가 집필의 판단이고, 렌더러는 그것을 지킨다.
    pa = list(p.get("passage_assets") or [])
    if pa:
        fig = _figure(pa, asset_dir, inline_dir)
        if fig:
            # ★ `inflow` — 흐름 안에 둔다. 안 붙이면 `order:-1` 이 그림을 카드 맨 위로
            #   올려 번호·난도 머리보다 위에 뜬다(실측 5번).
            fig = fig.replace('class="diagram"', 'class="diagram inflow"', 1)
            pieces.append(paginate.Piece(fig, paginate.h_figure()))

    if chs:
        pieces.append(paginate.Piece(
            _choices(chs, p.get("answer_index"), reveal=False),
            paginate.h_choices(chs, two_col)))

    # ★ 보기 4개는 **한 줄(1×4)** 이다(2026-08-12 지시). 전에는 2×2 였다.
    #   16:9 는 가로가 남으므로 한 줄이 공짜이고, 세로 한 줄을 벌어 그림까지 한 장에
    #   당긴다. 4개가 아니면(3개·5개) 한 단으로 세로로 쌓는다.
    cls = " ch4" if two_col else ""
    head = _head(p.get("number"), subject, p.get("difficulty") or "", total)
    # ★ 문제 면 장수 상한을 **풀었다**(2026-08-20 지시: "문제페이지가 더 나와도
    #   됩니다. 2페이지보다 더" · "54321 할때까지 균일하게 넘어가면 되").
    #
    #   2장으로 묶어 두니 표가 둘이거나 표+SQL 인 지문이 담기지 않고 **넘친 만큼
    #   잘렸다** — 둘째 표가 사라지고 SQL 이 안 보였다(실측 SQLD 12·14·16·19번).
    #   장수가 늘어도 시간은 어긋나지 않는다: 첫 장만 낭독하고 이어지는 장은
    #   `CONT_SECONDS`(4초)씩 고르게 넘어가며, **마지막 장 위에** 5→1 카운트다운이
    #   얹힌다(`bake.build_script`). 그래서 「54321 할 때까지 균일하게」 가 성립한다.
    #
    #   그래도 상한을 아주 없애지는 않는다 — 5장을 넘기면 문항 하나가 화면을
    #   너무 오래 먹으므로, 그때는 글자를 조여 담아 본다(`DENSE_GAIN`).
    # ★ 문제 면은 **하단 페이지 번호를 쓰지 않는다**(2026-08-12 지시).
    return [s.replace('class="slide content', f'class="slide content{cls}', 1)
            for s in _paged(pieces, first_i=i, total=total, title=title,
                            head=head, cap=5, want_foot=False)]


def answer_slide(p: Dict[str, Any], *, i: int, total: int, title: str,
                 subject: str, asset_dir: str,
                 inline_dir: Optional[str] = None) -> List[str]:
    """해설 면 — 정답 배지 + 보기(정답 표시) + 해설.

    ★★ **그림이 여기에 온다.** 문제 면이 아니다 — 실측으로 `_rounds` 26/26 문항의
      그림 참조가 `explanation` 안에만 있다. 이유는 정답 노출 방지다(앞선 집필 대화의
      사용자 정정). 그러니 도식은 해설과 함께 보여야 맞다.

    ★ 보기는 여기에 다시 넣지 않는다. 실측 근거(Chromium 1920×1080, 7번들 140장):
      보기를 반복하면 228px 을 먹어 **예산 652px 의 35%** 가 사라지고, 25장에서 보기가
      카드 밖으로 밀려났다. `bundle.py` 도 같은 결론을 적어 뒀다 —
      *"이어지는 해설 페이지엔 보기 4개를 반복하지 않는다."*

    ★ 그래서 배지에 **정답 보기의 글자까지** 넣는다. 번호만 있으면(정답 ③) 시청자가
      앞 화면을 기억해야 하고, 영상은 되돌려 볼 수 없다.

    ★ **여러 장을 돌려준다.** 해설이 길면 문단 단위로 쪼갠다(`_expl_blocks`).
    """
    ai = p.get("answer_index")
    chs = list(p.get("choices") or [])
    mark = CIRCLED[ai] if isinstance(ai, int) and 0 <= ai < len(CIRCLED) else "?"
    text = md_inline(chs[ai]) if isinstance(ai, int) and 0 <= ai < len(chs) else ""
    badge = (f'<div class="answer-badge">정답 {mark}'
             f'{f" &nbsp;{text}" if text else ""}</div>')
    pieces: List[paginate.Piece] = []
    pieces.append(paginate.Piece(badge, paginate.h_badge(), sticky=True))

    # ★★ **1단으로 흐른다**(2026-08-20 지시: 「1단을 넣으셔도 될거 같아요」).
    #
    #   전에는 그림이 있으면 「그림 옆에 해설」 2단을 **한 조각**으로 묶었다.
    #   그 조각은 쪼갤 수 없어서, 그림이 둘이거나 해설이 길면 한 장에 밀어 넣다가
    #   **겹쳐 그려졌다** — 그림 두 개가 포개지고 글자가 그 위에 올라앉았다
    #   (2026-08-20 실측 m01-5 RIGHT OUTER JOIN 문항).
    #
    #   1단은 겹칠 자리가 없다. 그림도 해설도 각자 조각이라 넘치면 다음 장으로
    #   흐른다. 문제 면과 같은 규칙이 되어 판단할 것이 하나 줄었다.
    for name in (list(p.get("assets") or []) or []):
        one = _figure([name], asset_dir, inline_dir)
        if one:
            # ★ `inflow` — 카드 첫 자리로 끌어올리지 않는다. 배지 다음이 그림 자리다.
            one = one.replace('class="diagram"', 'class="diagram inflow"', 1)
            pieces.append(paginate.Piece(one, paginate.h_figure()))
    pieces.extend(_expl_blocks(p.get("explanation")))

    head = _head(p.get("number"), subject, p.get("difficulty") or "", total)
    # ★ 해설은 **1바닥**이다(2026-08-12 지시, 여러 번). 넘으면 글자를 조인다.
    # ★ 해설 면은 **상단 문번·난도를 쓰지 않는다**(2026-08-12 지시). 바로 앞 장이
    #   그 문항의 문제 면이므로 번호를 되풀이할 이유가 없다.
    return _paged(pieces, first_i=i, total=total, title=title, head="", cap=1)


def _expl_blocks(text: Any) -> List[paginate.Piece]:
    """해설을 문단·표 단위 조각으로. 각 조각이 따로 다음 장으로 넘어갈 수 있다.

    ★ `<div class="expl">` 로 각각을 감싼다. 한 번만 감싸면 조각이 갈릴 때 여는
      태그와 닫는 태그가 서로 다른 장에 남는다 — 그러면 그 장의 HTML 이 깨진다.
    """
    out: List[paginate.Piece] = []
    for part in re.split(r"\n\s*\n", str(text or "")):
        part = part.strip()
        if not part:
            continue
        if tbl := md_table(part):
            html = f'<div class="expl">{tbl}</div>'
            out.append(paginate.Piece(html, paginate.h_table(tbl.count("<tr>"))))
        else:
            html = f'<div class="expl"><p>{md_inline(part)}</p></div>'
            out.append(paginate.Piece(html, paginate.h_expl(part)))
    return out


def cover_slide(lesson: Dict[str, Any], *, total: int, numbers: List[int]) -> str:
    """표지. ★ 화면에도 문항 범위를 넣는다 — 낭독만 바꾸면 그림과 소리가 어긋난다."""
    rng = (f"{numbers[0]}번부터 {numbers[-1]}번까지" if len(numbers) > 1
           else (f"{numbers[0]}번" if numbers else ""))
    pi, pt = lesson.get("part_index"), lesson.get("part_total")
    part = f"{pt}편 중 {pi}편" if pi and pt else ""
    lead = " · ".join(x for x in (rng, part) if x)
    return (f'<section class="slide cover" style="{theme.style_attr(False)}">'
            f'<div class="eyebrow">{esc(lesson.get("subject") or "")}</div>'
            f'<h1>{esc(lesson.get("title") or lesson.get("chapter") or "")}</h1>'
            f'{f"<p class=lead>{esc(lead)}</p>" if lead else ""}'
            f'</section>')


# ── 덱 전체 ─────────────────────────────────────────────────────────────────
def build_slides(lesson: Dict[str, Any], *, asset_dir: str = "assets",
                 inline_dir: Optional[str] = None) -> List[str]:
    """문항당 문제 면 1장 + 해설 면 1장. 표지 1장.

    ★ **분할이 붙었다**(2026-08-12). 문항당 장수가 고정이 아니다 — 안전선을 넘는
      내용은 다음 장으로 넘어간다(`paginate.pack`). 그래서 장수를 미리 알 수 없고,
      푸터의 `i / total` 을 채우려면 **두 번 만들어야** 한다. 만드는 값이 싸므로
      (문자열 조립뿐) 그 편이 total 을 어림잡는 것보다 정확하다.

    ★ 높이는 Chromium 이 아니라 **추정**으로 잰다(`paginate` 머리말). 실제 넘침은
      캡처 단계가 `overflow` 로 잡아 준다 — 두 겹이다.
    """
    blocks = list(lesson.get("blocks") or [])
    probs = [b for b in blocks if b.get("kind") == "problem"]
    numbers = [int(b.get("number") or 0) for b in probs if b.get("number")]
    subject = lesson.get("subject") or ""
    title = lesson.get("title") or lesson.get("chapter") or ""

    return [h for h, _m in build_pages(lesson, asset_dir=asset_dir,
                                       inline_dir=inline_dir)]


def build_pages(lesson: Dict[str, Any], *, asset_dir: str = "assets",
                inline_dir: Optional[str] = None
                ) -> List[tuple]:
    """`[(html, meta), …]`. **베이크가 script 를 만들 때 쓴다.**

    ★ 덱과 script 를 **한 목록에서** 만들어야 한다. 따로 세면 분할 때 개수가 갈리고,
      그러면 렌더 드라이버가 `deck 슬라이드 ≠ 캡처 씬` 으로 그 자리에서 멈춘다
      (`bundles.py` 의 `ok_1to1`). 드라이버 주석도 같은 것을 적어 뒀다 —
      "페이지 분할로 슬라이드가 늘면 씬·narration_text 도 같이 늘어야 합니다."

    meta = {"kind": "cover"|"problem"|"answer", "number": int|None,
            "page": 이 면의 몇 번째 장(1부터), "pages": 이 면의 총 장수}
    """
    blocks = list(lesson.get("blocks") or [])
    probs = [b for b in blocks if b.get("kind") == "problem"]
    numbers = [int(b.get("number") or 0) for b in probs if b.get("number")]
    subject = lesson.get("subject") or ""
    title = lesson.get("title") or lesson.get("chapter") or ""

    def once(total: int) -> List[tuple]:
        out: List[tuple] = [(cover_slide(lesson, total=total, numbers=numbers),
                             {"kind": "cover", "number": None,
                              "page": 1, "pages": 1})]
        i = 2
        for p in probs:
            no = p.get("number")
            for face, fn in (("problem", problem_slide), ("answer", answer_slide)):
                kw = dict(i=i, total=total, title=title, subject=subject,
                          asset_dir=asset_dir)
                # ★ 문제 면도 그림을 그린다(지문이 가리킨 것) — `inline_dir` 이 필요하다.
                #   전에는 해설에만 넘겼고, 그래서 문제 면 그림이 `file://` 에서 안 떴다.
                kw["inline_dir"] = inline_dir
                got = fn(p, **kw)
                for k, s in enumerate(got):
                    out.append((s, {"kind": face, "number": no,
                                    "page": k + 1, "pages": len(got)}))
                    i += 1
        return out

    return once(len(once(0)))


def render_deck(lesson: Dict[str, Any], *, tokens_css: str = "",
                asset_dir: str = "assets", fit: bool = False,
                inline_dir: Optional[str] = None) -> str:
    """덱 HTML 한 장. 미리보기와 베이크가 이 문자열을 공유한다.

    ★ **미리보기 전용 장치를 두지 않는다**(2026-08-12 실측으로 되돌린 결정).
      전에는 상단에 sticky 안내 바(`.gl-bar`)와 경계 적색선을 얹고 "캡처는 `.slide`
      하나씩 element screenshot 을 찍으므로 찍히지 않는다"고 적어 두었다. **틀렸다.**
      element screenshot 은 그 요소의 화면 영역을 찍으므로 위에 겹쳐 그려진 sticky 바가
      **그대로 들어간다.** 실측(`ch12_02_problem.png`):

          y=0        (238,242,247)  ← 1px, 높이가 1081 로 튀던 원인
          y=1..36    ( 30, 38, 55)  ← `.gl-bar` 의 #1e2637 그대로
          y=37~      (255,255,255)  ← 여기서부터 진짜 슬라이드

      적색선(`box-shadow:inset`)도 요소 자신이 그리는 것이라 같이 찍힌다 — 저 검은 띠
      아래에 깔려 안 보였을 뿐이다. 그래서 둘 다 **없앴다.** 캡처 시점에 CSS 로 숨기는
      방법도 있지만, 미리보기와 캡처가 같은 문자열을 공유하는 것이 이 파일의 규약이므로
      **애초에 안 넣는 것**이 규약을 지키는 길이다.
    """
    slides = build_slides(lesson, asset_dir=asset_dir, inline_dir=inline_dir)
    body_cls = "fit" if fit else ""
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{esc(lesson.get('title') or '슬라이드')}</title>
<style>{tokens_css}
{slide_css()}
/* ★ 슬라이드를 틈 없이 죽 이어 놓는다. 이 컨테이너 말고는 **아무것도 얹지 않는다** —
   위에 얹은 것은 element screenshot 에 그대로 들어간다(위 docstring 의 실측). */
.deck{{ display:flex; flex-direction:column; align-items:center;
        gap:0; padding:0; }}
</style></head>
<body class="{body_cls}">
<div class="deck" id="deck" data-generator="xam-local 0.1"
     data-safe-line="{theme.safe_line(True)}"
     data-slides="{len(slides)}">
{''.join(slides)}
</div></body></html>"""
