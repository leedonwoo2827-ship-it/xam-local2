# -*- coding: utf-8 -*-
"""슬라이드 CSS — 기하만. 색은 사이트 토큰(`tokens.css`)에서 온다.

★ **불문율: 모든 선택자가 `.slide` 로 시작한다.**
  `.slide .qcard`(0,2,0) vs `.qcard`(0,1,0) — 누가 실수로 `check.css` 를 링크해도
  순서가 아니라 **특이도**로 슬라이드가 이긴다. "특이도 싸움" 의 답이 이 한 줄이다.

★ 사이트 CSS 를 `@import` 하지 않는다. 실패 모드가 파일에 있다 —
  `check.css:56 .expl{display:none}`(해설이 통째로 안 보이는 빈 슬라이드) ·
  `check.css:47 img.fig{max-width:520px}`(1920 캔버스에서 도식이 520px 로 캡) ·
  `@media(max-width:920/760/640)` × `_deck.js` 의 `body.style.zoom`(미리보기와 캡처가
  달라진다) · `style.css:10-13` 이 카페24 트래픽 때문에 `@font-face` 를 **일부러**
  제거해 둔 것(`file://` 캡처가 CDN 에 못 닿아 Pretendard 없이 찍힌다).

★ 클래스명은 **사이트 것으로 통일**했다(`check.js:281-296`). 지금은 공짜다 —
  deck.html 은 통째로 재생성된다. 나중엔 불가능하다. 그러면 사이트 수정을 슬라이드로
  옮기는 일이 기계적이 된다(값이 아니라 선택자만 다르다).
"""
from __future__ import annotations

from . import theme

# ── 그림 위치 ───────────────────────────────────────────────────────────────
# ★★ 요구: **그림은 화면 최상단부터 꽉 차야 한다** (2026-08-10 지시).
#   홍보 덱은 그림이 밑에 있어도 되지만 풀이는 전부 보여야 한다.
#
#   showcase-agent `render/slides.py:140-145` 에서 그림이 내려가 있던 원인 2개:
#     ① `<header>` → `<h2>` → `h2::after`(52×3px 밑줄 + margin-top:14px)
#        → `.s{padding:5vh}` 가 그림 위 자리를 먼저 먹는다
#     ② `.cols` 안이 `.txt` 먼저 · media 나중이라, 1열로 접히면 텍스트 뒤로 간다
#
#   ②는 `axexam/web/exam/assets/features.css:99` 의 `order:2` 와 **같은 결함**이다
#   (데스크톱 2단 배치의 DOM 순서가 쌓인 배치로 누출). 거긴 `order:-1` 로 고쳤다.
#
# ★ 이 요구는 "보기 4개 반드시 다 보여야 한다" 와 **상충한다.** 그림을 상단에 꽉
#   채우면 보기가 밀려 나간다. 해소책은 정해져 있다 — 그림을 키우지 말고
#   **페이지를 쪼갠다.** 그래서 셋이 한 묶음이다:
#     · 그림을 상단 띠로            → `order:-1` + head 띠 축소(밑줄 없음)
#     · 그림 높이 상한 `--fig-max`  → 없으면 도식이 안내문으로 **교체**된다
#     · 넘치면 분할, 분할도 안 되면 그 번들만 실패


def slide_css() -> str:
    """덱에 **인라인으로** 심는다. 링크하지 않는다 —
    캡처가 `file://` 로 열리므로(`deck_capture.py:42`) 상대경로 CSS 는 번들 안에
    복사돼야 하고, 그 복사가 낡으면 조용히 옛 모양으로 찍힌다."""
    return f"""
/* ══ 슬라이드 기하 — 1920×1080 고정(캡처 결정성) ══════════════════════════ */
html,body{{ margin:0; padding:0; background:#eef2f7; }}
body{{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic",
       "맑은 고딕",system-ui,sans-serif; }}

.slide{{
  box-sizing:border-box;
  width:var(--slide-w); height:var(--slide-h);
  /* ★ `flex:0 0 var(--slide-w)` 를 쓰지 않는다. 옛 `_deck.css` 는 가로 필름스트립
     (`flex-direction:row`)이라 그 줄이 **폭**을 뜻했지만, 이 미리보기 컨테이너는
     `column` 이라 같은 줄이 **높이**로 들어간다 → 슬라이드가 1920px 높이가 된다.
     실측에서 정확히 그렇게 됐고(slide 1920), 넘침이 20장 전부 같은 값(876px)으로
     나와서 그것이 내용이 아니라 레이아웃 문제라는 것을 드러냈다.
     폭·높이를 이미 명시했으므로 플렉스는 관여하지 않게 둔다. */
  flex:none;
  padding:var(--slide-pad);
  display:flex; flex-direction:column;
  /* ★ 띠 간격을 **0 으로 두었다**. 머리·푸터가 카드 안으로 들어갔으므로(render.py
     `_card` 머리말) 카드 밖에 간격을 둘 형제가 없다. `theme.avail()` 도 더는 이
     값을 예산에서 빼지 않는다 — 한쪽만 바꾸면 파이썬과 DOM 이 어긋난다. */
  gap:0;
  background:var(--c-bg, #fff); color:var(--c-ink, #1e2637);
  overflow:hidden;              /* 넘침을 숨긴다 — 넘쳤는지는 measure 가 판정한다 */
  position:relative;
}}

/* ── 머리 띠 ── 얇게 유지한다. 여기가 두꺼워지면 그림이 그만큼 내려간다.
   ★ showcase-agent 의 `h2::after`(52×3px 밑줄 + margin-top:14px) 를 **넣지 않았다.**
     장식 3px + 여백 14px = 17px 이 그림 위로 들어가고, 그림을 최상단에 두라는
     요구와 정면으로 부딪힌다. 제목 구분은 글자 굵기로 낸다. */
/* ★ 카드 **안** 첫 줄이다. 띠 높이(`--slide-head`)로 고정하지 않는다 — 고정하면
   머리가 없는 장에서도 그 자리가 남고, 그것이 118px 을 모든 장에서 잃던 원인이다.
   내용 높이만큼만 쓰고 아래 간격만 둔다. */
.slide .s-head{{
  flex:0 0 auto;
  display:flex; align-items:center; gap:calc(8px * var(--ss));
  margin-bottom:calc(8px * var(--ss));
  font-size:calc(13px * var(--ts)); font-weight:800;
  color:var(--c-muted, #6b7688); letter-spacing:.02em;
}}
.slide .s-head .qnum{{ color:var(--c-blue, #2c5ce6); font-weight:900; }}
.slide .s-head .pill{{
  font-size:calc(11px * var(--ts)); font-weight:700; letter-spacing:0;
  padding:calc(2px * var(--ss)) calc(9px * var(--ss)); border-radius:999px;
  background:var(--c-soft, #f2f4f8); color:var(--c-body, #46536b);
  border:1px solid var(--c-line, #e3e8f0);
}}
.slide .s-head .pill-teal{{ background:#e6f6f4; color:#0d7d70; border-color:#bfe8e2; }}
.slide .s-head .pill-orange{{ background:#fdf0e6; color:#a75a12; border-color:#f6d9bd; }}

/* ── 본문 ── 남은 높이를 전부 쓴다.
   ★ `minmax(0,1fr)` 이 아니라 flex 다 — 한 열이므로 트랙 최소폭 문제가 없고,
     넘침 판정을 `scrollHeight` 로 단순하게 잴 수 있다. */
.slide .qcard{{
  flex:1 1 auto; min-height:0;
  /* ★ 간격 14px×2.4 = 33.6px 이었다. 자식이 3개면 간격만 67px 이고, 그것이
     652px 예산의 10% 다(실측). 10px 로 내려 24px 씩 쓰게 한다 — 슬라이드는
     여백보다 내용이 우선이고, 1080px 예산은 사이트보다 훨씬 빡빡하다. */
  display:flex; flex-direction:column; gap:calc(10px * var(--ss));
  padding:{theme.CARD_PAD}px;
  /* ★ 테두리와 둥근 모서리를 **없앴다**(2026-08-12 지시). 캡처한 흰 면이 그대로
     영상에 뜨므로, 박스 선이 있으면 영상 안에 액자가 하나 더 생긴다.
     `theme.CARD_BORDER` 를 0 으로 두었으니 이 줄이 0px 로 나간다 — 값을 두 곳에서
     정하지 않는다. */
  border:{theme.CARD_BORDER}px solid var(--c-line, #e3e8f0);
  border-radius:0; background:var(--c-paper, #fff);
}}

/* ── 이어지는 장 ── 한 문항이 여러 장으로 쪼개졌을 때 **한 카드가 이어지는 것처럼**
   보이게 한다. 규약은 사용자가 정했다(2026-08-12):

     첫 장   상단 테두리 O · 머리 O · 하단 테두리 X · 푸터 X
     중간 장 상단 테두리 X · 머리 X · 하단 테두리 X · 푸터 X
     끝 장   상단 테두리 X · 머리 X · 하단 테두리 O · 푸터 O

   ★ 머리·푸터를 HTML 에서 빼는 것만으로는 안 된다. `.slide` 이 그 자리를
     `--slide-head`/`--slide-foot` 로 잡아 두므로, 빼면 **빈 띠가 남아 카드가 뜬다.**
     그래서 여기서 그 띠를 0 으로 접는다. 둘이 한 묶음이다 — 한쪽만 하면 어긋난다.
   ★ 테두리를 없앤 뒤로는 이 클래스가 **자리(패딩)만** 접는다. 지울 선이 없다. */
.slide.cont-top{{ padding-top:0; }}
.slide.cont-top .qcard{{ padding-top:0; }}
.slide.cont-bottom{{ padding-bottom:0; }}
.slide.cont-bottom .qcard{{ padding-bottom:0; }}

/* ★★ 그림을 최상단으로 — DOM 순서와 무관하게 카드 첫 자리에 온다.
   `order:-1` 하나로 되는 이유: 형제 모두가 기본 order:0 이다.
   (텍스트를 먼저 보이려면 `.q{{order:2}}` 로 바꾸는 것이 아니라 이 줄을 지운다.) */
.slide figure.diagram{{
  order:-1;
  margin:0 0 calc(6px * var(--ss));
  flex:0 0 auto; align-self:stretch;
  display:flex; justify-content:center; align-items:flex-start;
}}
/* 도식은 인라인 SVG 라 `img.fig` 와 성격이 다르다 — 여기만 예외다.
   ★ `max-height` 는 필수다. 없으면 도식이 자기 페이지에서도 넘쳐
     `.trunc-note` 안내문으로 **교체**된다(사라진다). */
.slide figure.diagram svg{{
  width:100%; max-width:calc(1000px * var(--ss) / 2.4);
  height:auto; max-height:var(--fig-max);
}}
.slide img.fig{{
  display:block; margin:0 auto;
  max-width:100%; max-height:var(--fig-max); height:auto;
}}

/* ── 해설 면 2단 ── ★★ **더 쓰지 않는다**(2026-08-20). 아래 규칙은 남겨 두었지만
   `render.answer_slide` 이 `.ans-row` 를 만들지 않는다.

   왜 버렸는가. 「그림 옆에 해설」 2단은 **한 조각**이라 쪼갤 수 없었다. 그림이
   둘이거나 해설이 길면 한 장에 밀어 넣다가 **겹쳐 그려졌다** — 그림 두 개가
   포개지고 글자가 그 위에 올라앉았다(실측 m01 「RIGHT OUTER JOIN」·「중심 엔터티」).
   지시도 그랬다: 「1단을 넣으셔도 될거 같아요」.
   1단은 겹칠 자리가 없고, 그림·해설이 각자 조각이라 넘치면 다음 장으로 흐른다. */
.slide .ans-row{{
  display:flex; align-items:flex-start; gap:calc(16px * var(--ss));
}}
.slide .ans-row > .ans-fig{{ flex:0 0 44%; min-width:0; }}
.slide .ans-row > .ans-txt{{ flex:1 1 auto; min-width:0;
  display:flex; flex-direction:column; gap:calc(8px * var(--ss)); }}
/* 2단 안에서는 그림이 자기 칸 폭을 다 쓴다 — `order:-1` 은 여기서 의미가 없다. */
.slide .ans-row figure.diagram{{ margin:0; }}
/* ★★ 문제 면의 **지문 그림**은 흐름 안에 둔다. `order:-1` 은 그림을 카드 첫
   자리로 올리는데(해설 면에서는 그것이 맞다), 문제 면에서는 번호·난도 머리보다
   위로 올라가 버렸다(2026-08-20 실측 5번: ERD 가 「5번 중」 위에 떴다).
   지문 그림은 지문이 있던 자리에 있어야 한다. */
.slide figure.diagram.inflow{{ order:0; margin:calc(6px * var(--ss)) 0 0; }}
.slide .ans-row figure.diagram svg,
.slide .ans-row img.fig{{ width:100%; max-width:100%; max-height:none; }}

/* ── 발문 ── */
.slide .q{{
  font-size:calc(15px * var(--ts)); font-weight:700; line-height:1.5;
  color:var(--c-ink, #1e2637); margin:0;
}}
/* ★ 지문의 **겉 박스를 없앴다**(2026-08-20 지시: 「그냥 다 흐르게 두어요..
   박스에 박스를 넣어서 문제같은데」). 표와 코드는 자기 테두리를 갖는데 그것들을
   또 회색 박스로 감싸니 박스 안 박스가 됐고, 감싼 박스가 쪼갤 수 없는 한 덩이로
   보여 넘침이 더 심하게 드러났다. 이제 지문은 배경 없이 흐른다. */
.slide .passage{{
  font-size:calc(13.5px * var(--ts)); line-height:1.6;
  color:var(--c-body, #46536b);
  padding:0; background:none; border:0; border-radius:0;
  margin:calc(8px * var(--ss)) 0 0;
}}
.slide .passage:first-child{{ margin-top:0; }}
/* ★ 지문 조각이 잇달으면 **좁게** 붙인다. 조각마다 8px 을 주면 표 두 개와
   이름표가 각각 떨어져 지문이 흩어져 보인다 — 이름표와 표는 특히 붙어야 한다. */
.slide .passage + .passage{{ margin-top:calc(4px * var(--ss)); }}

/* ── 코드 박스 ── ★ SQL 이 글자로 흐르지 않게 박스로 그린다.
   `md_paras` 가 코드펜스를 `<pre class="code">` 로 만든다(2026-08-20). 전에는
   그 자리에 스타일이 없어 펜스가 글자로 찍히고 SQL 이 문단으로 새어 나갔다.
   ★ 등폭 글꼴에 `pre-wrap` 이다 — SQL 은 줄바꿈과 들여쓰기가 내용이므로
     `nowrap` 으로 두면 긴 줄이 화면을 넘고, `normal` 로 두면 줄이 뭉개진다. */
.slide pre.code{{
  font-family:"Consolas","D2Coding","Courier New",monospace;
  font-size:calc(12.5px * var(--ts)); line-height:1.55;
  color:var(--c-ink, #1e2637); background:#fff;
  border:1px solid var(--c-line, #e3e8f0); border-radius:calc(8px * var(--ss));
  padding:calc(10px * var(--ss)) calc(12px * var(--ss));
  margin:calc(8px * var(--ss)) 0 0; white-space:pre-wrap; overflow-wrap:anywhere;
}}
.slide .passage pre.code:first-child{{ margin-top:0; }}

/* ── 보기 ── ★ 4개가 반드시 다 보여야 한다.
   `.ch2` 는 2×2 로 접어 세로 564px 를 절반으로 만든다. 글자를 줄이지 않고 높이를
   버는 유일한 방법이다. **16:9 는 가로가 남고 사이트는 안 남는다** —
   사이트와 의도적으로 다른 유일한 자리다. */
.slide .opts{{ display:flex; flex-direction:column; gap:calc(8px * var(--ss)); margin:0; }}
.slide.ch2 .opts{{
  display:grid; grid-template-columns:1fr 1fr;
  gap:calc(8px * var(--ss)) calc(18px * var(--ss));
}}
/* ★ 1×4 — 보기 4개를 **한 줄**로(2026-08-12 지시). 2×2 가 세로 2줄을 쓰던 것을
   1줄로 만들어 그림까지 한 장에 당긴다. 16:9 는 가로가 남으므로 이것이 공짜다.
   ★ `minmax(0,1fr)` 이어야 한다. `1fr` 만 주면 긴 보기가 칸을 밀어 4칸이 안 맞는다. */
.slide.ch4 .opts{{
  display:grid; grid-template-columns:repeat(4, minmax(0, 1fr));
  gap:calc(10px * var(--ss));
}}
/* 한 줄에 4칸이면 칸이 좁다 — 번호와 글자를 위아래로 쌓아 폭을 번다. */
.slide.ch4 .opt{{
  flex-direction:column; gap:calc(3px * var(--ss));
  font-size:calc(13px * var(--ts)); line-height:1.35;
}}
/* ★ 보기 한 칸의 상하 패딩을 10px→6px 로 조였다. **실측 근거**: 10px×2.4 = 24px 이
   상하로 붙어 칸마다 48px, 2×2 두 줄이면 96px 이 패딩만으로 나간다. 예산 652px 의 15% 다.
   그 결과 발문에 83px 밖에 안 남아 **1줄만 들어갔고**, 발문이 2줄인 문항 25장에서
   보기가 카드 밖으로 밀려났다(7번들 70장 중). 글자 크기는 그대로 두고 여백만 줄인다 —
   1080p h.264 에서 뭉개지는 것은 글자이고, 여백은 뭉개질 것이 없다. */
.slide .opt{{
  display:flex; gap:calc(10px * var(--ss)); align-items:flex-start;
  font-size:calc(14px * var(--ts)); line-height:1.4;
  padding:calc(6px * var(--ss)) calc(12px * var(--ss));
  border:1px solid var(--c-line, #e3e8f0); border-radius:calc(10px * var(--ss));
  background:var(--c-paper, #fff);
}}
.slide .opt .cn{{ flex:0 0 auto; font-weight:800; color:var(--c-muted, #6b7688); }}
.slide .opt.correct{{
  border-color:var(--c-ok, #0f7355); background:var(--c-ok-bg, #e3f1ec);
}}
.slide .opt.correct .cn{{ color:var(--c-ok, #0f7355); }}

/* ── 정답 배지 · 해설 ── */
.slide .answer-badge{{
  align-self:flex-start; font-size:calc(13px * var(--ts)); font-weight:800;
  padding:calc(5px * var(--ss)) calc(14px * var(--ss)); border-radius:999px;
  background:var(--c-ok-bg, #e3f1ec); color:var(--c-ok, #0f7355);
}}
.slide .expl{{
  font-size:calc(13.5px * var(--ts)); line-height:1.7;
  color:var(--c-body, #46536b);
}}
/* ★ `white-space:pre-wrap` 을 쓰지 않는다 — 문단을 <p> 로 렌더하므로 블록 간격이
   맞다. pre-wrap 이면 원문 개행이 이중 간격이 된다(사이트에서 겪은 것). */
.slide .expl p{{ margin:0 0 calc(9px * var(--ss)); }}
.slide .expl p:last-child{{ margin-bottom:0; }}
.slide .expl b{{ color:var(--c-ink, #1e2637); }}

/* ── 표 ── 넓은 표가 트랙을 밀지 못하게 자기가 스크롤한다(캡처에선 잘리지 않게
   `overflow:hidden` + 폭 축소). */
.slide table{{
  border-collapse:collapse; width:100%;
  font-size:calc(12.5px * var(--ts));
}}
.slide table th, .slide table td{{
  border:1px solid var(--c-line, #e3e8f0);
  padding:calc(6px * var(--ss)) calc(10px * var(--ss)); text-align:left;
}}
.slide table th{{ background:var(--c-soft, #f2f4f8); font-weight:700; }}

/* ── 조밀 모드 ── 자르기 직전의 마지막 안전판. 1단만 둔다.
   (`dense2`(30px) 는 1080p h.264 에서 못 읽는다 — 거기까지 오면 lesson 을 고칠 신호다.) */
.slide.dense{{ --ts:2.30; --ss:2.05; }}

/* ── 발 줄 ── 카드 **안** 마지막 줄. 머리와 같은 이유로 높이를 고정하지 않는다.
   ★ `margin-top:auto` 로 카드 바닥에 붙인다 — 내용이 짧아도 페이지 번호가 중간에
     떠 있지 않게 한다. */
.slide .s-foot{{
  flex:0 0 auto; margin-top:auto; padding-top:calc(8px * var(--ss));
  display:flex; align-items:center; justify-content:flex-end;
  font-size:calc(11.5px * var(--ts)); color:var(--c-muted, #6b7688);
}}

/* ── 표지 ── */
.slide.cover{{ justify-content:center; align-items:flex-start;
  gap:calc(14px * var(--ss)); }}
.slide.cover .eyebrow{{
  font-size:calc(15px * var(--ts)); font-weight:800; letter-spacing:.04em;
  color:var(--c-blue, #2c5ce6);
}}
.slide.cover h1{{ font-size:calc(30px * var(--ts)); font-weight:900; margin:0;
  line-height:1.25; }}
.slide.cover .lead{{ font-size:calc(15px * var(--ts)); line-height:1.6;
  color:var(--c-body, #46536b); margin:0; max-width:62ch; }}

/* ── ?fit=1 진단 오버레이 ── 미리보기에서만 켠다.
   빨간 띠가 안전선이고, 넘친 만큼이 숫자로 얹힌다. 그 뒤 모든 단계의 검증이
   "이 화면에 빨간 게 없다" 로 통일된다. */
.fit .slide::after{{
  content:""; position:absolute; left:0; right:0;
  top:calc(var(--slide-pad) + var(--slide-head) + var(--slide-safe));
  height:3px; background:rgba(220,38,38,.85); pointer-events:none;
}}
.fit .slide[data-over]::before{{
  content:attr(data-over) "px 넘침";
  position:absolute; right:calc(var(--slide-pad)); top:calc(var(--slide-pad));
  background:#dc2626; color:#fff; font-size:26px; font-weight:800;
  padding:6px 14px; border-radius:8px; z-index:5;
}}
"""
