"""시험문제 덱 HTML → 강의용 PPTX.

들어오는 것은 `xam-lo`(D:\00work\260803-xam-lo/services/deck) 가 뽑은
`_deck-export/*.html` 이다. 그 HTML 은 이미 1920×1080 슬라이드로 쪼개져 있지만,
**그 분할을 그대로 쓰지 않는다** — 되붙여 원본 문항을 복원하고 우리 예산으로 다시 쪼갠다.
이유는 `layout.py` 머리말에 적었다(요약: 원본 분할기는 한글 1자를 1.0em 으로 넉넉히
재서 일찍 쪼개고, 그래서 장마다 아래가 비었다).

  parse_html.parse_file()  →  ir.Round        (요소 인벤토리 그대로, DOM 순서 보존)
  layout.paginate_round()  →  [ir.Page]       (예산 기반 재분할 + 간지 삽입)
  pptx_render.render()     →  .pptx           (네이티브 도형 + 도식만 PNG)

LLM 은 이 경로에 개입하지 않는다. 본문(발문·보기·정답·해설)은 원문 그대로 나간다.
"""
