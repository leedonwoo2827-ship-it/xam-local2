# vendor/exam2deck — 출처와 고친 곳

`https://github.com/leedonwoo2827-ship-it/exambookhtml2slide` (로컬 `D:\00work\260821-exambookhtml2slide`)
의 `services/exam2deck/` 을 **@ aae8b5a (2026-08-21) 기준**으로 가져왔다.
`vendor/chodangi` 와 같은 규약이다 — **패치가 아니라 코드다.** 고친 곳은 아래 표에 적고,
되살릴 일이 생기면 원본 저장소에서 가져온다.

가져온 것

    ir.py parse_html.py parse_theory.py metrics.py layout.py
    pptx_render.py svg_raster.py build.py template_spec.py __init__.py
    assets/pptx_template_exam.pptx      로고 없는 빈 판 (tools/make_exam_template.py 가 만든다)

같이 가져온 도구: `tools/verify_deck.py` (원본 HTML ↔ PPTX 글자 대조)

## 이 앱에서 고친 곳

| # | 자리 | 왜 |
|---|---|---|
| 1 | `parse_html.parse_file` — `cont_answer` 판정 | 머리도 배지도 없는 **이어지는 장**을 전부 문제 면 파서로 보내고 있었다. 해설이 2장으로 갈리면 2장째의 `div.expl` 이 `unknown["problem/expl"]` 로 세어지고 **버려졌다**(SQLD 20회차 실측 105건 — 해설 뒷부분이 통째로 사라짐). 앞 문항이 어디까지 왔는지로 가른다. |
| 2 | `parse_html.parse_file` — 이어지는 장의 도식 | `Question.figure` 는 자리가 하나뿐이라, 이어지는 해설 장이 도식을 또 들고 오면 버려졌다. `expl` 흐름에 넣는다(`_answer_page` 가 그대로 흘려 준다). |
| 3 | `layout._fit` / `_force_pages` / `_problem_pages` / `_answer_pages` 의 `budget_scale` | **문항별 장수 지정**(화면의 ± 표). 줄일 때는 배율을 내리고, 늘릴 때는 예산을 깎는다. 못 맞추면 자연 장수로 되돌리고 보고한다. |
| 4 | `build.Options.page_want` / `Built.page_missed` | 위 3 을 CLI·앱이 넘기는 통로. |

## 이 앱이 이 엔진을 부르는 자리

    services/deck/rounddeck.py   05/*/source/deck.html 를 회차 하나로 합친다 (입력)
    services/deck/pptxdeck.py    build.build_pages() → 편마다 pptx + pages.json
    services/deck/slideimg.py    pptx → images/slide_NN.png (PowerPoint COM)

## 숫자가 어긋나면 (2026-08-24 대조함)

`layout.py` 의 캔버스 값은 `services/deck/theme.py` 를 베껴 온 것이다. 오늘 대조 결과
**전부 같다**:

    SLIDE 1920×1080 · PAD 40 · CARD_PAD 20 · SAFETY 12 · SAFE 948 · INNER_W 1800
    TS 2.67 / SS 2.40 · dense 2.30 / 2.05 · FIGURE_MAX_RATIO 0.62

`theme.py` 나 `slidecss.py` 의 기하가 바뀌면 여기가 조용히 어긋난다. 바뀔 때 같이 본다.

`layout.TYPE_PT` 는 CSS 를 베낀 것이 **아니다** — PPTX 쪽의 독립된 크기표다
(배율 1.0 = 발문 16pt · 보기 12.5pt · 해설 10pt). CSS 와 맞출 값이 아니다.

## xam-local v2 (2026-10-24)

| 파일 | 고친 것 |
|---|---|
| `layout.py` `pages_for_topic` | `_fit` 이 `build(st, 예산배율)` 로 부르게 바뀐 뒤 이론 쪽 람다만 인자 하나로 남아 TypeError. 둘째 인자를 받고 버린다. 요약반·종합반 강의 노트의 [노트 빌드] 가 이 경로를 처음 쓴다. |
