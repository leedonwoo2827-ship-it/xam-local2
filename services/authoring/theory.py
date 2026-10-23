# -*- coding: utf-8 -*-
"""요약노트(이론) 집필 — `03/summary_<key>.html` 과목당 1개, 총 4개.

★ 발행되는 것은 **`.html`** 이다. `axexam/scripts/build_check.py::build_theory()` 가
  `03/summary_*.html` 만 읽어 `theory_content.js` 로 굽는다 — `.md` 는 읽지 않는다.
  그래서 이 모듈의 원천은 `.html` 이고, `.md` 는 검수 화면(`#/summary`)이 고칠 수
  있게 같이 남기는 사본이다. (`summary_routes.py` 머리말이 같은 함정을 적어 뒀다:
  ".md 수정은 웹에 반영되지 않는다".)

★ **HTML 계약을 모델에게 맡기지 않는다.** 빌더가 정규식으로 파싱하므로 한 글자만
  어긋나도 이론 탭이 조용히 비거나 과목 번호가 99 로 떨어진다. 실제 파서다:

      <h1[^>]*>([^<]*)</h1>            ← h1 **안에 태그가 있으면 못 읽는다**
      (\\d+)\\s*과목\\s*[·:\\-—\\s]*(.*)   ← "1과목 · 빅데이터 분석 기획" 꼴
      <body[^>]*>(.*?)</body>          ← body 태그가 **문자열로** 있어야 한다
      <style[^>]*>(.*?)</style>        ← 여러 개면 이어 붙인다

  그래서 모델은 **본문 조각과 CSS 만** 낸다. `<html>`·`<head>`·`<body>`·`<h1>` 조립은
  `render_html()` 이 한다. 모델이 틀릴 수 있는 표면을 줄이는 것이 목적이다.

★ 빌더는 상대 `src`/`href` 앞에 `theory/` 를 붙이고, CSS 의 `body` 선택자를 `:host`
  로 바꾼다(shadow DOM 에 넣기 때문이다). 그래서
    · 외부 참조(http · // · CDN 폰트)를 **금지**한다. 금지가 없으면 모델이 폰트를
      넣고 그것이 `theory/https:...` 로 망가진다.
    · 그림은 **인라인 SVG** 로만 받는다. `03/assets/` 를 만들지 않는다 — 문항 쪽
      `02/assets` 와 달리 여기서는 파일을 늘릴 이유가 없다.

★ 개행은 `paths.to_disk()` 한 곳을 지난다. `03/*` 는 LF 규약이다(atomic_io 머리말).
  직접 `atomic_write_text` 를 부르면 안 된다 — 그 함수는 개행을 정하지 않는다.

★ 분량 하한을 **스키마에 넣지 않는다.** 문항 집필에서 그것 때문에 무한루프가 났다
  (schema.py 머리말 · 2026-08-12 m09-p1). 상한만 스키마로 막고 하한은 아래
  `validate()` 가 problems 로 잡는다 — 한 번에 다시 쓰는 양이 요약노트 1개뿐이라
  문항 쪽보다 싸지만, 규칙을 두 군데서 다르게 두면 다음 사람이 헷갈린다.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.book import paths

from .errors import ProviderError
from .provider import ClaudeAuthor
from .schema import subjects

# ── 과목 ↔ 파일 키 ──────────────────────────────────────────────────────────
# ★ 키는 **이 PC 의 실제 파일명 규약**이다. 업로드본은 한글 키로 못박아 뒀고
#   (`분석기획`·`탐색`…) 그것 때문에 요약노트 화면이 404 를 냈다
#   (`paths.summary_keys()` 머리말). ascii 로 가면 빌더의 한글 파일명 치환
#   (`summary_koN.html`)도 아예 안 탄다.
# ★ 과목 키는 **시험정보에서** 온다(`subjects[].key`). 전에는 빅분기 4개가
#   여기 박혀 있었다(`planning`·`explore`·`modeling`·`interpret`). SQLD 는 2과목이고
#   이름이 달라서, 그대로 두면 요약노트가 없는 과목 넷을 내놓고 발행 파일명도
#   빅분기 것이 된다(2026-08-19).
#   함수다 — 작업 폴더를 바꾸면 즉시 따라야 한다.
def keys() -> Tuple[Tuple[str, int], ...]:
    """(편 키, 과목번호) — **편 단위**다. 과목 하나가 여러 편일 수 있다.

    ★ SQLD 2과목은 3편(`sql-1`·`sql-2`·`sql-3`)이다. 한 편 = 한 호출 = 한 영상.
      1편뿐인 과목은 편 번호를 붙이지 않는다(`datamodel`·`planning`).
    """
    from services.authoring import parts

    return tuple((k, no) for k, no, _pt, _rng in parts.theory_units())


def unit_label(key: str) -> str:
    """편 이름 — 「1과목」 · 「2과목 1편」. **짧게** 쓴다(2026-08-20 지시).

    ★ 과목 이름과 문항 범위를 붙이지 않는다. 탭·체크박스·문서에 같은 말이
      길게 반복되면 읽히지 않는다. 1편뿐인 과목은 「편」 을 아예 안 붙인다.
      범위는 필요한 자리에서만 따로 보여 준다(`unit_range_label`).
    """
    u = unit_of(key)
    if not u:
        return str(key)
    no, (i, n), _rng = u
    return f"{no}과목" if n <= 1 else f"{no}과목 {i}편"


def unit_range_label(key: str) -> str:
    """「문항 25~37번」 — 확인창처럼 범위를 알려야 하는 자리에서만 쓴다."""
    u = unit_of(key)
    if not u:
        return ""
    _no, _pt, (lo, hi) = u
    return f"문항 {lo}~{hi}번"


def unit_of(key: str):
    """편 키 → `(과목번호, (편, 전체), (문항 lo, hi))`. 없으면 None."""
    from services.authoring import parts

    for k, no, pt, rng in parts.theory_units():
        if k == str(key):
            return no, pt, rng
    return None


def key_of(no: int) -> str:
    """과목번호 → 그 과목의 **첫 편** 키. 과목이 여러 편이면 첫 편이 대표다."""
    for k, n in keys():
        if int(n) == int(no):
            return k
    return ""


def no_of(key: str) -> int:
    return dict(keys()).get(str(key), 0)

# ★ 모델이 낼 수 있는 최대 분량. **상한만 건다**(위 머리말). 실측 근거: 업로드본
#   `theory_content.js` 가 4과목 합쳐 81KB 였다 → 과목당 약 20KB. 60KB 면 3배
#   여유이고, 그래도 출력 토큰 상한(64,000)에 한참 못 미친다.
BODY_MAX = 60000
CSS_MAX = 4000
# 하한은 problems 로 본다. "빈 껍데기가 발행되는 것"만 막는 값이다.
BODY_MIN = 1200


def theory_schema() -> Dict[str, Any]:
    """모델이 낼 것 — **본문 조각과 CSS 만.** 문서 골격은 우리가 조립한다."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["body_html", "css", "headings"],
        "properties": {
            # ★ h1 을 넣지 말라고 스키마로는 못 막는다 → validate() 가 잡는다.
            "body_html": {"type": "string", "maxLength": BODY_MAX},
            "css": {"type": "string", "maxLength": CSS_MAX},
            # 목차. 화면이 "무엇이 담겼나" 를 한 줄로 보여 줄 근거이고,
            # 사람이 과목이 뒤바뀌지 않았는지 눈으로 확인하는 값이다.
            "headings": {"type": "array", "items": {"type": "string"},
                         "minItems": 3, "maxItems": 24},
        },
    }


# ── 프롬프트 ────────────────────────────────────────────────────────────────
# ★ 회차별 값을 넣지 않는다 — 프롬프트 캐시 접두가 고정이어야 4과목 연달아 돌릴 때
#   33,682토큰이 캐시 읽기로 전환된다(provider.py 실측). 과목 번호는 아래
#   `theory_prompt()` 쪽에만 둔다.
SYSTEM_TEMPLATE = """{머리}

■ ★ 아래 예시의 **개념 이름은 형식을 보이기 위한 것**이다
예시에 나온 용어(엔트로피·층화추출 같은 것)가 이 시험에 없으면, **이 시험의 개념으로
바꿔 읽는다.** 예시를 보고 시험에 없는 개념을 이론에 넣지 않는다.
무엇이 이 시험의 개념인지는 **해설에 실제로 나온 것**이 정한다 — 그것만 쓴다.

■ 무엇을 만드는가
**요약 이론**의 본문 HTML 조각이다. 해설 모음집이 아니다.

**해설에서 시험에 나오는 키워드만 뽑아 그 키워드를 이론으로 설명한다.**
순서가 이렇다:

  ① 이 과목 문항의 해설을 **전부** 훑어 **시험에 나오는 키워드**를 뽑는다.
     키워드 = 용어 · 개념 · 공식 · 분류 이름.{키워드예시}
  ② 같은 키워드가 여러 문항에 흩어져 있다 — **키워드 하나로 합친다.**
     항목 하나에 문번이 여러 개 붙는 것이 정상이고 그것이 목표다.
  ③ 합친 키워드를 **일정한 차례**로 늘어놓는다.
  ④ 각 키워드 **제목 옆에 근거 문번**을 둔다.
  ⑤ 각 키워드를 **정의 → 의미 → 성질·범위 → 언제 쓰나** 로 설명한다. 그 키워드를
     처음 보는 사람이 읽고 무엇인지 알 수 있어야 한다.
     ★ 키워드 하나에 **설명할 것이 많다.** 계산값 목록으로 그 자리를 채우지 말 것.

     ✗ 나쁨 — 엔트로피가 무엇인지가 없다. 계산 결과만 있다:
         <h3>2.1. 엔트로피와 정보이득 <span class="q">모의 …</span></h3>
         <ul><li>자주 쓰이는 값: 8:8 → 1.000, 4:4 → 1.000, 순수 노드 → 0.</li>
             <li>6:2 → −0.75log₂0.75 − 0.25log₂0.25 = 0.811.</li>
             <li>1:2 → 0.918, 1:5 → 0.650, 2:8 → 0.722.</li>
             <li>계산 예(부모 8:8, 자식 둘 다 6:2): … 정보이득 = 0.189.</li></ul>

     ✓ 좋음 — 개념을 설명하고 예는 하나:
         <h3>2.1. 엔트로피 <span class="q">모의 …</span></h3>
         <p>어떤 노드에 섞여 있는 정도(불순도)를 정보량으로 잰 값이다.</p>
         <ul>
           <li>E = −Σ p·log₂p. 로그 밑이 2 이므로 단위가 비트다.</li>
           <li>한 종류만 있으면 0, 두 종류가 반씩이면 1 로 **최대**가 된다.
               섞일수록 커진다.</li>
           <li>노드를 나눌 기준을 고를 때 쓴다 — 나눈 뒤 불순도가 가장 많이 줄어드는
               기준을 택한다.</li>
           <li>예: 8:8 로 반씩 섞인 노드는 1.000, 6:2 는 0.811 이다.</li>
         </ul>
         <h3>2.2. 정보이득 <span class="q">모의 …</span></h3>
         <p>나누기 전 엔트로피에서 나눈 뒤 엔트로피를 뺀 감소량이다.</p>
         <ul>
           <li>정보이득 = 부모 엔트로피 − 자식 엔트로피의 **가중평균**.</li>
           <li>가중치는 자식 노드에 들어간 **자료 수 비율**이다. 단순평균이 아니다.</li>
           <li>클수록 잘 나눈 기준이다.</li>
         </ul>

     ★ 숫자 예시는 개념 설명에 **딱 하나**만 붙인다. 계산 연습은 문제 학습에서 한다 —
       이 문서가 할 일이 아니다.

★ **문항의 수치·상황·보기는 키워드를 찾는 재료일 뿐 옮겨 적는 대상이 아니다.**
  문항 10개가 같은 공식을 묻는다면 그 공식을 **한 번** 설명하고 문번 10개를 옆에
  모은다 — 문항 10개의 계산을 10줄로 늘어놓는 것이 아니다.
  숫자가 필요하면 **예시 하나**만 든다.

■ ★★ 판단 기준 하나 — **이 노트를 그대로 슬라이드로 옮겨 강의한다**
소주제(`<h3>`) **하나가 슬라이드 한 장**이다. 이 문서가 곧 강의 자료가 된다.
망설여질 때는 이 하나만 물으면 된다 — **"이걸 슬라이드에 띄우고 말로 설명할 수
있는가?"** 아니면 넣지 않는다.

{판수}

  · 한 소주제는 **3~6줄**이다. 소주제 하나가 슬라이드 한 장이 된다.
  · 제목만 봐도 그 장에서 무엇을 말할지 알아야 한다.
  · 계산값을 늘어놓은 목록은 슬라이드가 되지 않는다 — 강의에서 읽을 말이 없다.
  · "함정 ①②③" 같은 딱지도 슬라이드에 띄울 것이 아니다. 말로 설명할 내용을 쓴다.

■ ★★ 시각물 — **필수가 아니다.** 있는 것을 살리고, 없는 것을 지어내지 않는다

이 문서를 슬라이드로 만드는 일은 **다음 앱**이 한다. 그 앱은 장마다 시각물을
스스로 채우고(원문에 표·그림이 있으면 그것을 쓰고, 없으면 만든다), 목차도 이
문서의 `h2`/`h3` 를 그대로 쓴다. 그래서 **모든 장에 그림을 붙일 필요가 없다.**

  · ★ **해설에 이미 있는 그림은 살린다.** 문항 해설의 `assets` SVG 는 그 개념을
    설명하려고 만든 것이다 — 그 개념을 다루는 장에 인라인 `<svg>` 로 그대로 넣는다.
    버리면 이미 만든 것을 다시 만들게 되고, 다시 만든 것은 원본과 어긋난다.
  · ★ **표는 표로 쓴다.** 비교·분류·장단점·구문 대응은 `<table>` 이 가장 읽힌다.
    다음 앱이 그 표를 그 장의 시각물로 쓴다 — 표를 잘 쓰면 그림 만들 일이 줄고
    내용도 정확해진다.
  · **없는 그림을 지어내지 않는다.** 장을 채우려고 상자 하나에 낱말 하나 넣은
    도식을 그리지 마라 — 그런 장은 다음 앱이 판단해 채운다.
  · SVG 를 넣을 때만: `viewBox` 를 넣고 `width`/`height` 는 넣지 않는다.
    외부 폰트·이미지·스크립트를 참조하지 않는다(문서는 자체완결이어야 한다).

■ 누가 언제 읽는가 — 이것이 문체를 정한다
읽는 시점이 **두 번**이다.

  ① **공부를 처음 시작할 때.** 이 과목을 아무것도 모르는 사람이 첫 교재로 읽는다.
     그래서 용어를 **정의부터** 쓴다. 앞에서 정의하지 않은 말을 뒤에서 쓰지 않는다.
     약어는 처음 나올 때 풀어 쓴다(예: `DDL` — Data Definition Language).
  ② **시험 직전 최종정리할 때.** 같은 사람이 다 배운 뒤 한 번에 훑는다.
     그래서 **짧고 구조가 보여야** 한다. 제목만 따라 읽어도 과목 전체가 잡혀야 하고,
     한 항목은 눈에 한 번에 들어와야 한다.

이 둘을 같이 만족시키는 방법은 정해져 있다 — **개념 하나를 짧게, 정의부터, 빠짐없이.**
길게 풀어 쓰면 ②가 죽고, 정의를 건너뛰면 ①이 죽는다.

성적표에서 "이 과목 정답률이 낮다" 는 링크를 타고 다시 오는 문서이기도 하다.
그 사람이 원하는 것은 개념이고, 문항 목록이 아니다.

■ 절대 규칙 — 어기면 발행 파서가 깨진다
  · `<h1>` 을 쓰지 말 것. 제목은 앱이 붙인다.
  · `<html>` `<head>` `<body>` `<script>` `<link>` `<iframe>` 을 쓰지 말 것.
  · 외부 참조 금지 — `http://` `https://` `//` 로 시작하는 src·href 를 쓰지 말 것.
    웹폰트·CDN·외부 이미지 전부 금지다. 문서는 자체완결이어야 한다.
  · 그림이 필요하면 **인라인 `<svg>`** 로 직접 그릴 것. 파일 참조는 없다.
  · 제목 계층은 `<h2>`(대주제) → `<h3>`(소주제) 로만 간다. `<h2>` 는 "1. 데이터 정제"
    처럼 번호를 붙인다.
  · ★ **과목 이름·편 번호를 본문에 쓰지 말 것.** 「2과목」 「2편」 「SQL 기본 및 활용」
    같은 제목을 만들지 않는다 — 앱이 문서 위에 붙인다. 본문은 **바로 `1. …` 부터**
    시작한다(2026-08-20 지시).
  · **출처 줄을 쓰지 말 것.** 문서 맨 아래 "출처: …" 한 줄은 앱이 붙인다.
  · ★ **"기출" 이라는 말을 쓰지 말 것.** 독자가 확인할 수 없는 시험을 가리키면 안 된다.
  · ★ 근거 문번은 **개념 하나마다** `<span class="q">모의 N회 M번</span>` 으로 붙인다.
    대괄호·색·크기는 앱 CSS 가 입힌다. 여러 개념을 한 문단에 몰아넣으면 붙일 자리가
    없어지므로 `<ul><li>` 를 기본으로 쓴다.

■ 내용
  · ★★ **개념을 설명한다. 문항의 계산을 나열하지 않는다.** 이것이 제일 중요하다.
    같은 개념을 묻는 문항이 5개면, 그 개념을 **한 번 설명**하고 문번 5개를 제목 옆에
    모은다. 문항 5개의 숫자를 5줄로 늘어놓는 것이 아니다.

    ✗ 나쁨 — 문항마다 한 줄. 읽는 사람이 ROI 가 무엇인지 알 수 없다:
        <h3>18.1. ROI = 순편익 ÷ 투자비용 <span class="q">모의 …</span></h3>
        <ul>
          <li>(4억 − 2.5억) ÷ 2.5억 = 60%</li>
          <li>(3억 − 2억) ÷ 2억 = 50% / (9억 − 6억) ÷ 6억 = 50%</li>
          <li>매출 12억 × 공헌이익률 25% = … → 1억/2억 = 50%</li>
          <li>투자비 = 구축 3억 + 운영 1억 = 4억, 순효과 5억 → (5−4)/4 = 25%</li>
        </ul>

    ✓ 좋음 — 개념·용어·계산법을 설명하고, 예시는 **하나**:
        <h3>18.1. 투자수익률(ROI) <span class="q">모의 …</span></h3>
        <p>투자한 돈에 비해 얼마를 남겼는지 나타내는 비율이다.</p>
        <ul>
          <li><b>순편익</b> = 총편익 − 총비용. 편익 자체가 아니라 <b>차액</b>이다.</li>
          <li><b>투자비용</b> = 구축비 + 운영비. 운영비는 산정 기간 전체를 넣는다.</li>
          <li>ROI = 순편익 ÷ 투자비용. 예: 순편익 1.5억, 투자비용 2.5억 → 60%.</li>
        </ul>

  · 근거는 **우리 모의고사 해설뿐**이다. 해설에 없는 것을 지어내 채우지 말 것.
    분량을 늘리려고 일반론을 붙이면 그것이 어느 문항의 근거도 아니게 된다.
  · ★ **옳은 문장으로 쓴다.** 문항은 {지선다}지선다이므로 해설에는 "정답인 진술" 과
    "왜 틀렸는지" 가 같이 있다. 이론 노트에는 **옳은 진술**을 서술로 적는다 —
    "①은 틀리다" 같은 보기 번호 이야기를 옮기지 않는다. 보기 번호는 이 문서에서
    아무것도 가리키지 않는다(문항이 옆에 없다).
    ✗ 나쁨: "②가 정답이다. ①은 층화추출이 아니라 군집추출이다."
    ✓ 좋음: "층화추출은 층으로 나눈 뒤 각 층에서 뽑는다. 군집을 통째로 뽑는 것은
            군집추출이다."
  · ★ **"함정" · "단골" · "출제 포인트" 같은 시험 요령을 쓰지 말 것.** 이 문서는
    개념을 설명하는 이론이다. 무엇이 맞는지만 담백하게 적는다.
  · **중복 제거가 핵심이다.** 같은 개념이 10문항에 나오면 항목은 **하나**이고,
    문번 10개를 그 옆에 모아 적는다. 같은 설명을 열 번 늘어놓는 것이 아니다.
  · 차례는 **그 개념이 처음 나온 문번 순**으로 한다. 그러면 다시 만들어도 같은
    순서가 나오고, 수험생이 어디를 보는지 잃지 않는다.
  · ★ **개조식으로 쓴다.** 문장을 완결하지 않아도 된다 — 명사로 끝내도 되고,
    "~이다" 로 끝내도 된다. 한 줄에 한 가지. 수식어를 덜어낸다.
    예: "엔트로피 — 노드에 섞인 정도를 정보량으로 잰 값. 단위는 비트."
    긴 서술은 영상 대본이 맡는다. 이 노트는 최종정리 때 눈으로 훑는 것이 목적이다.
  · ★ **이것만 봐도 무엇이 시험에 나오는지 보여야 한다.** 그러려면 두 가지가 필요하다.
      ① **문항이 실제로 물은 각도**를 설명에 담는다. 교과서 일반론으로 채우면
         무엇이 나올지 알 수 없다. 예: 정보이득은 "자식 엔트로피의 **가중**평균을
         뺀다" 가 물어진 각도이므로, 그 구분을 설명 안에 넣는다.
      ② 중요도는 **제목 옆 문번 개수**가 말한다. 9문항에서 나온 키워드와 1문항에서
         나온 키워드가 한눈에 갈린다 — 그것이 "무엇이 많이 나오는가" 다.
    ★ 그렇다고 "함정 ①②③" 처럼 **따로 딱지를 붙이지 않는다.** 구분해야 할 내용을
      설명 문장 안에 자연스럽게 넣는다(아래 금지 항목 참조).
  · 계산·판정 공식은 해설에 유도가 있으면 그것을 살린다 — 정의만 적지 말 것.
  · 표가 맞는 것은 표로(`<table>`). 비교·분류·장단점이 그렇다.
  · 헷갈리는 짝은 나란히 둔다.{혼동쌍}
  · ★ **표의 행은 "개념" 이다. 절대 "문항" 이 아니다.**
    문항마다 한 행을 만들면 그것은 요약이 아니라 나열이고, 같은 값이 계속 반복된다.
    ✗ 나쁨 — 문항이 행이 되어 같은 계산이 7번 반복된다:
        | 문항 | Cov | σx·σy | r | R² |
        | 모의 1회 24번 | −12 | 5×8 | −0.30 | 0.09 |
        | 모의 3회 27번 |  24 | 5×8 |  0.60 | 0.36 |
        | 모의 5회 23번 | −18 | 6×5 | −0.60 | 0.36 |   ← 아래 세 행이 전부 같다
        | 모의 7회 32번 | −18 | 6×5 | −0.60 | 0.36 |
        | 모의 9회 26번 | −18 | 6×5 | −0.60 | 0.36 |
    ✓ 좋음 — 계산은 **한 번** 보여 주고, 문번은 제목 옆 도형에 모은다:
        <h3>4.3. 상관계수와 결정계수 <span class="q">모의 1회 24번 · 3회 27번 ·
            5회 23번 · 6회 24번 · 7회 32번 · 9회 26번</span></h3>
        <p>r = Cov / (σx·σy). 예: Cov −18, σx·σy = 6×5 = 30 → r = −0.60, R² = 0.36.</p>
    · 계산 예시가 필요하면 **대표 하나**만 든다. 값만 다른 같은 계산을 여러 번 싣지 않는다.
    · `문항` 을 표의 머리(열 이름)로 쓰지 말 것.

■ CSS
`css` 에는 이 문서에만 쓰는 최소한만 담는다. 앱이 기본 스타일을 먼저 깔아 준다.
`body` 선택자는 발행 때 `:host` 로 치환되므로 그대로 써도 된다.
"""



def system() -> str:
    """요약노트 시스템 프롬프트. **품목마다 다르다** — 시험정보에서 조립한다.

    ★ 전에는 첫 줄이 「당신은 빅데이터분석기사 필기 문제집의…」 였고 키워드 예시도
      빅분기 용어(DIKW·VIF·정밀도)였다. SQLD 요약노트를 그 프롬프트로 만들면 시험에
      없는 개념이 이론에 섞인다 — 「시험에 나오는 대로 맞춘다」 에 어긋난다.
    """
    from services.authoring import parts

    d = parts.active() or {}
    label = str(d.get("label") or "").strip() or "자격시험"
    head = f"당신은 {label} 문제집의 요약노트(이론) 집필자다."

    # 키워드 예시 — 이 시험의 오답쌍에서 낱개 용어를 뽑아 쓴다. 없으면 예시를 생략한다.
    # ★ `↔` 로만 쪼갠다. 공백으로 쪼개면 `INNER JOIN` 이 `INNER`·`JOIN` 으로 갈려
    #   예시가 낱말 부스러기가 된다(실측).
    words: list = []
    for pair in (d.get("distractor_pairs") or []):
        for w in str(pair).split("↔"):
            w = w.strip().strip("()·,.").strip()
            if 1 < len(w) <= 18 and w not in words:
                words.append(w)
    ex = f" (예: {', '.join(words[:7])})" if words else ""

    pairs = [str(x) for x in (d.get("distractor_pairs") or [])][:2]
    dup = f" 예: {' , '.join(pairs)}." if pairs else ""
    n = int(d.get("choices") or 4)
    return (SYSTEM_TEMPLATE.replace("{머리}", head)
            .replace("{키워드예시}", ex)
            .replace("{혼동쌍}", dup)
            .replace("{지선다}", str(n)))


def theory_prompt(*, subject_no: int, rounds: List[str], key: str = "") -> str:
    """이 과목 하나를 쓰라는 지시. 읽을 파일을 **경로로** 준다.

    ★ 문항을 프롬프트에 통째로 넣지 않는다. 한 과목이 회차당 20문항이고 9회차면
      180문항이다 — 접두가 거대해지고 캐시가 무의미해진다. 모델이 필요한 것만
      읽는 편이 싸다(provider.py 가 Read/Grep/Glob 을 허용하는 이유다).

    ★ **`01/` 기출을 읽으라고 하지 않는다.** 문항 집필(`spec.py`)은 기출을 읽지만
      요약노트는 다르다 — 읽으면 본문에 "기출 3회 12번" 같은 인용이 새어 나온다.
      요약노트는 우리 문제집을 사는 사람이 보는 문서이고, 거기서 가리킬 수 있는 것은
      **우리가 만든 9회 모의고사뿐**이다(2026-08-12 지시). 읽을 파일 목록에서
      아예 빼는 것이 금지 문구보다 확실하다 — 없는 것은 인용할 수 없다.
    """
    # ★ 과목 이름·문항 범위를 시험정보에서. 상수식은 빅분기에서만 맞았다.
    from services.authoring import parts as _P

    _spec = _P.active()
    name = subjects().get(subject_no, "")
    lo, hi, _acc = 0, 0, 0
    for _s in (_spec or {}).get("subjects") or []:
        _c = int(_s.get("count") or 0)
        if _c > 0:
            if int(_s.get("no") or 0) == subject_no:
                lo, hi = _acc + 1, _acc + _c
                break
            _acc += _c
    # ★ 읽을 파일이 **하나**다. 편마다 그 편의 문항만 모아 둔 파일을
    #   `source_view()` 가 만든다 — 회차 파일 20개를 훑던 것이 이 한 줄로 줄었다.
    src = (f"  · _rounds/{key}.json   ← 이 편의 문항만 모아 둔 파일 (여기만 읽는다)"
           if key else "  · (없음)")
    # ★ v2 — 구조화 노트가 있으면 목차를 그것으로 정한다(해설 모아 노트 구조화 단계).
    try:
        from services.lecture import outline as _O
        if key and os.path.isfile(_O.outline_path(key)):
            src += ("\n" f"  · _outline/{key}.json  ← 사람이 검토한 노트 구조. **h2·h3 목차와 순서를 "
                     f"이것대로** 쓰고, 각 소단원의 points·traps 를 빠짐없이 담는다")
    except Exception:                                        # noqa: BLE001
        pass

    # ★★ **분량 목표를 걸지 않는다**(2026-08-20). 어제 넣었던 「목표 판 수」·「편 범위」·
    #   「판마다 그림」 을 다 걷어냈다.
    #
    #   슬라이드 원고를 만드는 일은 `summaryhtml2videoscripthtml` 이 맡는다. 그 앱의
    #   규약이 이렇다 — 목차는 **우리가 낸 `h2`/`h3` 가 이미 목차**이고, 시각물은
    #   **그 앱이 장마다 채운다**(원문에 표가 있으면 그것을 쓰고, 없으면 만든다).
    #   그리고 **분량 목표를 안 건다**: 「목표가 짧으면 개념을 버리고, 길면 물을 붓는다.」
    #   시험 범위가 분량이다.
    #
    #   그러니 우리가 할 일은 하나로 돌아간다 — **해설에서 개념을 뽑아 중복 없이,
    #   정의부터, 빠짐없이.** 판을 세거나 그림을 그릴 이유가 없다.
    goal = ""
    return f"""■ 이번에 쓸 것: **{subject_no}과목 · {name}**
{goal}

■ 읽을 파일 — **cwd 에 이것뿐이다.** 다른 자료는 없다
{src}
  이 과목 문항(번호 {lo}~{hi}번)의 해설만 회차 전부에서 모아 둔 파일이다.
  `items` 배열의 필드: `round` · `question_no` · `difficulty` · `tags`
  · `explanation`(해설 본문) · `assets`.
  ★ 해설을 **하나도 빠뜨리지 말 것.** Grep 으로 훑고 Read 로 확인한다.
  ★★ `assets` 는 `[{{"name": …, "svg": "<svg …>"}}]` 다 — **집필이 이미 만든 그림**이다.
    그 개념을 다루는 장에 `svg` 문자열을 **그대로 붙여** 넣는다(고쳐 그리지 말 것).
    그림이 있는 문항은 소수다(실측 50문항 중 7개) — 있는 것만 쓰면 된다.

■ ★ 근거 문번은 **제목 옆에** 단다 — 두 층 모두. 이것이 이 문서의 핵심이다
  · 붙는 자리는 **제목 글자 뒤, 제목 태그 안**이다. 본문 문장에는 붙이지 않는다.
  · `<h2>` = 대주제. 번호는 `6.` 꼴. **그 아래 소주제의 문번을 모조리 모아** 붙인다.
  · `<h3>` = 소주제. 번호는 `6.1.` 꼴. **그 소주제의 문번만** 붙인다.

        <h2>6. 표본추출·시각화 <span class="q">모의 2회 31번 · 5회 33번 · 6회 34번 ·
            8회 36번 · 9회 38번</span></h2>
        <h3>6.1. 단순임의추출 <span class="q">모의 2회 31번</span></h3>
        <p>모든 표본이 뽑힐 확률이 같다.</p>
        <h3>6.2. 계통추출 <span class="q">모의 5회 33번 · 8회 36번</span></h3>
        <p>일정 간격으로 뽑는다. 주기성이 있으면 편향된다.</p>

  · **소주제를 잘게 쪼갠다.** `<h3>` 하나가 개념 하나다. 여러 개념을 한 소주제에
    몰아넣으면 제목 옆 문번이 어느 개념의 것인지 알 수 없게 된다.
    ✗ 나쁨: `<h3>6.1. 표본추출 방법</h3>` 아래에 6가지를 한꺼번에
    ✓ 좋음: `6.1. 단순임의추출` · `6.2. 층화추출` · `6.3. 계통추출` … 로 나눈다
  · 표기는 **`<span class="q">모의 N회 M번</span>`** 이다. 대괄호·색·크기는 앱의 CSS 가
    입힌다 — 직접 `[ ]` 를 넣거나 style 을 붙이지 말 것.
    `_rounds/m03.json` 의 45번 → `<span class="q">모의 3회 45번</span>`.
    같은 개념이 여러 문항에 있으면 **모의 3회 45번 · 7회 12번 · 9회 8번** 처럼 잇는다.
    ★ **"모의" 를 반드시 붙인다.** 이 문제집에는 회차 번호가 같은 꼴인 다른 자료가
      있어서, 그냥 "3회 45번" 이라고 쓰면 독자가 어느 것인지 알 수 없다.
  · **문번 없는 `<h3>` 이 있으면 안 된다.** 근거가 없다는 뜻이고, 해설에 없는 것을
    채워 넣었다는 뜻이다.
  · **"기출" 이라는 말을 쓰지 말 것.** "기출 3회", "실제 시험에서는", "작년 시험"
    같은 표현 전부 금지다. 우리 문제집 안에 없는 것을 가리키면 독자가 확인할 수 없다.
  · 문항 발문을 길게 옮기지 말고, **해설의 내용**을 정리한다.

■ 내는 것
  body_html : 본문 조각. `<h2>` 로 시작한다. `<h1>` 은 넣지 않는다.
  css       : 이 문서용 최소 CSS. 없으면 빈 문자열.
  headings  : body_html 에 넣은 `<h2>` 제목들을 순서대로.

■ 확인
{subject_no}과목 문항이 실제로 다루는 범위를 넘지 말 것. 다른 과목 내용을 끌어오면
수험생이 성적표 링크를 타고 와서 엉뚱한 것을 읽는다.
"""


# ── 검증 ────────────────────────────────────────────────────────────────────
# ★ 빌더가 깨지는 것들. 전부 "통과했는데 발행한 뒤에야 아는" 종류다.
_BANNED_TAGS = ("<h1", "<html", "<head", "<body", "</body", "<script", "<link",
                "<iframe", "<!doctype")
_EXTERNAL = re.compile(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', re.I)
_AT_IMPORT = re.compile(r"@import", re.I)

# ★ "기출" 은 problems 다 — 사용자가 표현 자체를 금지했다(2026-08-12). 문항 텍스트를
#   어느 정도 옮기는 것은 괜찮지만, 우리 문제집 밖의 시험을 가리키는 말은 안 된다.
#   독자가 확인할 수 없는 출처이고, 우리 9회차를 "N회 M번" 으로 부르는 것과 섞인다.
_PAST_EXAM = re.compile(r"기출")
# 같은 것을 우회하는 표현들. 이쪽은 경고다 — 문맥에 따라 정상일 수 있고
# (예: "실제 시험에서도 이 공식을 쓴다"), 사람이 보고 판단할 일이다.
_PAST_HINT = re.compile(r"작년\s*시험|지난\s*시험|실제\s*시험에서는|이전\s*회차\s*시험")

# ★ 문항 참조. **우리 모의고사 문번은 나와야 한다**(2026-08-12 지시). 막지 않는다.
#
#   다만 실측으로 확인한 함정이 있다: `01/` 기출이 **01·02·03회**이고 우리 모의고사가
#   **1~9회**다. 회차 번호가 같은 꼴이라 "3회 45번" 만으로는 어느 시험의 것인지
#   본문만 보고 알 수 없다. 그래서 "우리 것만 쓰라" 는 지시로는 독자 쪽 모호함이
#   안 풀린다 — 우리 것에 **"모의"** 를 붙이게 하는 것이 그것을 푸는 최소한이다.
#
#   ★ 표기가 없어도 **경고**다. problems 로 하면 표기 하나 때문에 요약노트 하나를
#     통째로 다시 쓴다(20분·$1.7). 그리고 새어 나온 것이 아니라 표기 문제라,
#     사람이 보고 고치면 되는 종류다. 이 판단은 문항 쪽에서 배운 것과 같다 —
#     하한 미달을 problems 로 걸었다가 무한루프가 났다(schema.py 머리말).
#
#   ★ 맨 "N번" 은 잡지 않는다. 보기 번호("정답은 4번")·목차 번호가 전부 그 꼴이고
#     그것들은 정상이다. **회차와 짝지어진 번호**만 본다.
_QREF_ANY = re.compile(r"\d+\s*회차?\s*(?:의\s*)?\d+\s*번")


def _bare_question_refs(text: str) -> List[str]:
    """회차+문번 참조 중 **"모의" 표기가 없는** 것들.

    ★ 참조 하나하나에 "모의" 를 요구하면 안 된다. 프롬프트가 "여러 개면
      `모의 3회 45번 · 7회 12번 · 9회 8번` 처럼 잇는다" 고 시키므로 **목록 앞에 한 번**
      쓰는 것이 정상이고, 그것이 읽기에도 맞다.

      처음 이 함수가 앞 8글자만 봤더니 4과목에서 2,189건이 "표기 없음" 으로 잡혔다
      (2026-08-12 실측: planning 627 · explore 547 · modeling 354 · interpret 661).
      전부 오탐이었다 — 모델은 지시대로 썼고 검사가 틀렸다. 경고가 이렇게 쏟아지면
      사람이 경고 자체를 안 보게 된다.

    ★ 그래서 `<span class="q">` 를 단위로 본다. 그 안의 참조는 **그 span 에 "모의" 가
      있으면 표기된 것**이다. span 밖(본문 문장 속)의 참조는 앞 8글자로 본다 —
      거기서는 목록이 아니라 단독 인용이므로 각자 표기가 필요하다.
    """
    out: List[str] = []
    spans = list(_Q_SPAN_FULL.finditer(text))
    for sp in spans:
        if "모의" not in sp.group(1):
            out.extend(_QREF_ANY.findall(sp.group(1)))
    # span 밖에 남은 부분만 따로 본다.
    rest, last = [], 0
    for sp in spans:
        rest.append(text[last:sp.start()])
        last = sp.end()
    rest.append(text[last:])
    for chunk in rest:
        for m in _QREF_ANY.finditer(chunk):
            if "모의" not in chunk[max(0, m.start() - 8):m.start()]:
                out.append(m.group(0))
    return out


# ★ 문번은 **제목 옆**에 붙는다(2026-08-12 지시: "제목옆에 붙이는거에요", "1.1. 마다",
#   "6. 표본추출·시각화 옆에 출처 모조리"). h2 는 아래 소주제 문번을 모조리, h3 는
#   자기 것만. 그래서 "문번이 있느냐" 가 아니라 **"제목마다 있느냐"** 를 봐야 한다.
_H_BLOCK = re.compile(r"<(h2|h3)\b[^>]*>(.*?)</\1>", re.I | re.S)
# ★ `span` 과 `label` 을 다 받는다. 조립 때 `fold_refs()` 가 span → label 로 바꾸므로,
#   이미 접힌 문서를 다시 검사해도 "문번이 없다" 로 오판하지 않아야 한다.
_Q_SPAN = re.compile(r"""<(?:span|label)\s+class\s*=\s*["']q["']""", re.I)
# 열고 닫는 것까지 — 안쪽 문자열을 봐야 하는 검사가 쓴다(`_bare_question_refs`).
_Q_SPAN_FULL = re.compile(r"""<span\s+class\s*=\s*["']q["']\s*>(.*?)</span>""",
                          re.I | re.S)


def _headings_without_ref(body: str) -> Dict[str, List[str]]:
    """문번이 안 붙은 제목. `leaf` 는 반드시 붙어야 하고 `branch` 는 모아 붙이는 편의다.

    ★ 규칙은 **"최하 번호체계마다"** 다(2026-08-12 지시). 소주제가 있는 대주제는
      소주제가 최하이고, 소주제가 없는 대주제는 **그 대주제 자신이 최하**다.
      그래서 "h3 만 본다" 로는 안 된다 — 기존 3과목 원고가 대주제 7개·소주제 0개
      였고, h3 만 보면 그런 원고가 문번 없이 통과한다.
    """
    hs = [(m.group(1).lower(), m.group(2)) for m in _H_BLOCK.finditer(body)]
    out: Dict[str, List[str]] = {"leaf": [], "branch": []}
    for i, (lvl, inner) in enumerate(hs):
        if _Q_SPAN.search(inner):
            continue
        # 다음 제목이 h3 면 이 h2 는 묶음(branch)이고, 아니면 자기가 최하다.
        is_leaf = lvl == "h3" or not (i + 1 < len(hs) and hs[i + 1][0] == "h3")
        title = re.sub(r"<[^>]+>", "", inner).strip()[:40]
        out["leaf" if is_leaf else "branch"].append(f"{lvl} {title}")
    return out


# ★ 문항이 표의 행이 된 것을 잡는다. 그러면 요약이 아니라 나열이 되고, 같은 값이
#   여러 행에 반복된다 — 2026-08-12 실측 두 건:
#     · 상관계수 표 7행 중 5행이 `r=−0.60 · R²=0.36` 으로 동일
#     · 표본크기 표 5행 중 3행이 `2,401명` 으로 동일
#   문번은 제목 옆 도형에 모여야 하고, 계산은 대표 하나만 보이면 된다.
_TABLE = re.compile(r"<table\b.*?</table>", re.I | re.S)
_ROW = re.compile(r"<tr\b.*?</tr>", re.I | re.S)
_CELL1 = re.compile(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", re.I | re.S)


def per_question_tables(body: str) -> List[str]:
    """행이 "개념" 이 아니라 "문항" 인 표들. 값은 그 표의 머리 첫 칸(40자)."""
    out: List[str] = []
    for t in _TABLE.finditer(body):
        tbl = t.group(0)
        rows = _ROW.findall(tbl)
        if len(rows) < 3:
            continue
        firsts = []
        for r in rows:
            c = _CELL1.search(r)
            if c:
                firsts.append(re.sub(r"<[^>]+>", " ", c.group(1)))
        if not firsts:
            continue
        head = firsts[0].strip()
        # 머리를 뺀 본문 행의 첫 칸이 절반 이상 문번이면 문항이 행이다.
        rest = firsts[1:]
        n_ref = sum(1 for x in rest if _QREF_ANY.search(x))
        if ("문항" in head and n_ref) or (rest and n_ref >= max(2, len(rest) // 2)):
            out.append(head[:40] or "(머리 없음)")
    return out


# ★ 표가 아니라 **목록**으로 문항을 나열한 것. 표 검사만으로는 못 잡는다 —
#   2026-08-12 실측: ROI 설명 자리에 문항 4개의 계산이 `<li>` 4줄로 늘어서 있었고,
#   각 줄에 문번 1개짜리 도형이 붙어 있었다. 읽는 사람은 ROI 가 무엇인지 모른다.
#   신호가 뚜렷하다: 한 목록 안에서 `<li>` 마다 **문번이 딱 하나**인 도형이 붙는다.
#   개념을 설명한 항목이면 문번이 여러 개 붙거나 아예 없다(제목에 모이므로).
_LIST = re.compile(r"<(ul|ol)\b.*?</\1>", re.I | re.S)
_LI = re.compile(r"<li\b.*?</li>", re.I | re.S)


# ★ 문번 도형 없이 **계산값만** 늘어놓은 줄도 잡아야 한다. 위 검사는 도형이 붙은
#   경우만 보므로, 2026-08-12 에 지적받은 엔트로피 항목을 놓쳤다 —
#     "자주 쓰이는 값: 8:8 → 1.000, 4:4 → 1.000 …"
#     "6:2 → −0.75log₂0.75 − 0.25log₂0.25 = 0.811."
#     "1:2 → 0.918, 1:5 → 0.650, 2:8 → 0.722."
#   엔트로피가 무엇인지는 없고 계산 결과만 있다. 판정은 **한글 비중**으로 한다:
#   설명 문장이면 한글이 절반을 넘고, 계산 나열이면 숫자·기호가 대부분이다.
_HANGUL = re.compile(r"[가-힣]")


def _numeric_dump(text: str) -> bool:
    t = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", text))
    if len(t) < 12:
        return False
    return len(_HANGUL.findall(t)) / len(t) < 0.30


def per_question_items(body: str) -> int:
    """개념 설명이 아니라 **문항·계산값을 늘어놓은** 목록의 개수.

    두 가지를 같이 본다 — 도형이 줄마다 붙은 것(문항 나열)과, 도형이 없어도 줄이
    숫자·기호뿐인 것(계산값 나열). 둘 다 "개념이 무엇인지" 를 남기지 않는다.
    """
    n = 0
    for m in _LIST.finditer(body):
        solo = dump = 0
        for li in _LI.findall(m.group(0)):
            hit = False
            for sp in _Q_SPAN_FULL.finditer(li):
                if len(_QREF_ANY.findall(sp.group(1))) == 1:
                    solo += 1
                    hit = True
                    break
            if not hit and _numeric_dump(_Q_SPAN_FULL.sub("", li)):
                dump += 1
        if solo >= 3 or dump >= 3:
            n += 1
    return n


def heading_counts(body: str) -> Tuple[int, int]:
    """(대주제 수, 소주제 수). "원고가 몇 번까지 있나" 를 화면·로그가 이 값으로 말한다."""
    hs = [m.group(1).lower() for m in _H_BLOCK.finditer(body)]
    return hs.count("h2"), hs.count("h3")


def validate(got: Dict[str, Any], subject_no: int) -> Tuple[List[str], List[str]]:
    """(problems, warnings). problems 가 있으면 파일을 쓰지 않는다."""
    problems: List[str] = []
    warns: List[str] = []

    body = str(got.get("body_html") or "")
    css = str(got.get("css") or "")
    heads = [str(h) for h in (got.get("headings") or [])]

    low = body.lower()
    for t in _BANNED_TAGS:
        if t in low:
            problems.append(
                f"본문에 {t}> 가 있습니다 — 문서 골격은 앱이 조립합니다. "
                f"이것이 들어가면 build_theory() 의 <body> 추출이 어긋납니다")
    if m := _EXTERNAL.search(body + css):
        problems.append(
            f"외부 참조가 있습니다({m.group(0)}) — 발행 때 상대경로 앞에 `theory/` 가 "
            f"붙어 깨집니다. 자체완결이어야 합니다")
    if _AT_IMPORT.search(css):
        problems.append("CSS 에 @import 가 있습니다 — 외부를 부르므로 금지입니다")

    # ★ 기출 인용. 프롬프트로 금지했지만 프롬프트는 지시일 뿐이다 — 실제로 새면
    #   발행된 뒤에 사람이 읽고서야 안다.
    hay = body + " " + " ".join(heads)
    if _PAST_EXAM.search(hay):
        n = len(_PAST_EXAM.findall(hay))
        problems.append(
            f"'기출' 이라는 표현이 {n}곳 있습니다 — 이 문서가 가리킬 수 있는 문항은 "
            f"우리 모의고사뿐입니다. 우리 회차는 'N회 M번' 으로 부르십시오")
    if m := _PAST_HINT.search(hay):
        warns.append(f"'{m.group(0)}' 라는 표현이 있습니다 — 우리 문제집 밖의 시험을 "
                     f"가리키는 것이면 고치십시오")

    # ★ 출처 줄은 앱이 붙인다. 모델이 쓰면 두 줄이 되고, 그 한 줄이 "기출 1~3회" 라고
    #   적히는 것이 애초의 문제였다(`source_line()` 머리말).
    if "출처:" in body or "출처 :" in body:
        problems.append("본문에 '출처:' 줄이 있습니다 — 출처는 앱이 붙입니다. "
                        "빼십시오")

    # ★ 근거 문번은 **있어야 한다.** 이 문서는 우리 해설을 모아 만드는 것이므로,
    #   문번이 하나도 없으면 무엇을 근거로 썼는지 확인할 수 없다(2026-08-12 지시:
    #   "우리모의고사 문번은 다 나와야 해요").
    # ★ 문번은 **본문만** 본다. `hay`(본문+목차)로 세면 같은 인용을 두 번 센다 —
    #   `headings` 는 본문 `<h2>` 를 옮겨 적은 목차이고, 거기서는 `<span class="q">` 가
    #   빠진 맨 텍스트가 되므로 "모의 표기 없음" 이 통째로 다시 잡힌다. 그러면 경고
    #   숫자가 실제의 두 배가 되고, 사람이 그 숫자를 못 믿게 된다.
    #   (`기출` 검사는 반대로 `hay` 가 맞다 — 목차에 있어도 새어 나간 것이다.)
    if not _QREF_ANY.search(body):
        problems.append("근거 문번이 하나도 없습니다 — 제목마다 "
                        "'<span class=\"q\">모의 N회 M번</span>' 을 달아야 합니다")
    elif bare := _bare_question_refs(body):
        warns.append(f"'모의' 표기가 없는 문번 참조 {len(bare)}건 {bare[:3]} — "
                     f"회차 번호가 같은 꼴인 다른 자료와 구별되지 않습니다")

    # ★ 제목마다 붙었는가. "문번이 있느냐" 로는 부족하다 — 한 곳에만 몰아 붙여도
    #   위 검사는 통과한다. 소주제는 problems, 대주제는 warnings 로 갈랐다:
    #   소주제에 근거가 없으면 그 개념이 어디서 왔는지 알 수 없고(요구사항 위반),
    #   대주제는 아래 것을 모아 붙이는 편의라 빠져도 읽는 데 지장이 없다.
    nores = _headings_without_ref(body)
    if nores["leaf"]:
        problems.append(
            f"문번이 안 붙은 **최하 제목** {len(nores['leaf'])}개: {nores['leaf'][:5]} — "
            f"제목 글자 뒤에 <span class=\"q\">모의 N회 M번</span> 을 넣으십시오")
    if nores["branch"]:
        warns.append(f"문번이 안 붙은 대주제 {len(nores['branch'])}개: "
                     f"{nores['branch'][:5]} — 그 아래 소주제 문번을 모아 붙이면 됩니다")

    # ★ 소주제가 너무 적으면 "잘게 쪼갠다" 가 안 지켜진 것이다. 기존 원고가 대주제
    #   5~7개에 소주제 0~3개였고, 그러면 최하 제목이 대주제라 문번 하나에 개념
    #   여러 개가 묶인다 — 그것을 피하려고 잘게 쪼개라고 한 것이다. 경고로 둔다:
    #   과목에 따라 개념 수가 다르므로 숫자로 잘라 불합격시킬 값이 아니다.
    # ★ 문항이 표의 행이 된 것. 요약이 아니라 나열이다(`per_question_tables` 머리말).
    if pq := per_question_tables(body):
        warns.append(f"표 {len(pq)}개의 행이 '문항' 입니다 {pq[:3]} — 표의 행은 개념이어야 "
                     f"합니다. 같은 계산이 문항마다 반복됩니다. 계산은 대표 하나만 "
                     f"보이고 문번은 제목 옆 도형에 모으십시오")
    # ★ 목록으로 문항을 나열한 것(`per_question_items` 머리말).
    if pi := per_question_items(body):
        warns.append(f"목록 {pi}개가 문항을 한 줄씩 나열합니다 — 개념을 설명하지 않고 "
                     f"문항의 계산만 늘어놓으면 읽는 사람이 그 개념이 무엇인지 알 수 "
                     f"없습니다. 설명 한 번 + 예시 하나로 줄이십시오")

    n_h2, n_h3 = heading_counts(body)
    if n_h3 < n_h2 * 2:
        warns.append(f"소주제가 {n_h3}개뿐입니다(대주제 {n_h2}개) — 개념 하나에 "
                     f"소주제 하나가 목표입니다. 문번이 뭉뚱그려졌는지 보십시오")

    if len(body) < BODY_MIN:
        problems.append(f"본문이 {len(body)}자뿐입니다 — 최소 {BODY_MIN}자. "
                        f"빈 껍데기가 발행되는 것을 막습니다")
    if not heads:
        problems.append("headings 가 비었습니다")

    # ★ h2 개수와 headings 개수가 갈리면 목차가 본문과 다른 것이다. 경고로 둔다 —
    #   내용은 멀쩡한데 목록만 어긋난 경우가 대부분이고, 사람이 보면 즉시 안다.
    n_h2 = len(re.findall(r"<h2[^>]*>", body, re.I))
    if n_h2 != len(heads):
        warns.append(f"본문의 <h2> 는 {n_h2}개인데 headings 는 {len(heads)}개입니다")
    if n_h2 < 3:
        warns.append(f"대주제가 {n_h2}개뿐입니다 — 과목 하나를 담기에 적습니다")

    # 과목이 뒤바뀐 것을 값싸게 잡는다. 다른 과목 이름이 제목에 박혀 있으면 의심이다.
    for no, nm in subjects().items():
        if no != subject_no and nm in " ".join(heads):
            warns.append(f"headings 에 다른 과목 이름('{nm}')이 있습니다 — "
                         f"과목이 섞였는지 확인하십시오")
    return problems, warns


# ── 조립 ────────────────────────────────────────────────────────────────────
# ★ 최소 기본 스타일. 발행 때 `body` → `:host` 로 치환되므로 body 에 건 것은
#   shadow root 에 걸린다. 그래서 폰트·색은 body 에, 요소는 요소에 건다.
_BASE_CSS = """
body { font-family: "Malgun Gothic", "맑은 고딕", sans-serif;
       line-height: 1.7; color: #1c2530; padding: 8px 4px 40px; }
p.part { margin: -10px 0 18px; color: #46605c; font-size: .95rem; }
h1 { font-size: 1.6rem; margin: 0 0 18px; padding-bottom: 10px;
     border-bottom: 3px solid #0f766e; color: #0f3f3a; }
h2 { font-size: 1.22rem; margin: 30px 0 10px; padding-left: 10px;
     border-left: 5px solid #0f766e; color: #0f3f3a; }
h3 { font-size: 1.04rem; margin: 18px 0 6px; color: #285e57; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: .95rem; }
th, td { border: 1px solid #cfd8dc; padding: 7px 9px; text-align: left;
         vertical-align: top; }
th { background: #e7f3f1; }
code { background: #f2f5f7; padding: 1px 5px; border-radius: 3px; }
svg { max-width: 100%; height: auto; display: block; margin: 12px 0; }
ul, ol { padding-left: 22px; }
li { margin: 3px 0; }
"""

# ★ 이 블록은 **모델 CSS 뒤에** 나간다. 앞에 두면 모델이 덮어쓴다 — 실측으로 planning
#   이 `.q{white-space:nowrap}` 을 넣어 두었다. 접기가 안 되면 가로 스크롤이 돌아오고
#   그러면 캡처를 못 쓴다. 그래서 이것만 순서로 이긴다.
_FOLD_CSS = """
/* ★ 근거 문번 — **접어 둔다.** 눌러야 번호가 보인다.
   왜 접는가: 한 개념이 9회차에 다 나오면 문번이 30개까지 붙는다. 그것을 제목 옆에
   펼쳐 두면 제목 한 줄이 화면을 넘어가고 **가로 스크롤바가 생긴다.** 이 원고는
   캡처해서 화면을 만드는 데 쓰므로 가로 스크롤이 있으면 못 쓴다(2026-08-12 지시).
   기본으로 보이는 것은 **횟수**다 — 그 개념이 몇 문항에서 나왔는지가 곧 중요도다.

   ★ JS 를 쓰지 않는다. 발행 파서(`build_check.build_theory`)는 `<style>` 과
     `<body>` 만 가져가 shadow root 에 innerHTML 로 넣는데, 그렇게 주입된
     `<script>` 는 **실행되지 않는다.** 그래서 label+checkbox 로 CSS 만으로 만든다.
     `<label>`·`<input>`·`<b>`·`<span>` 은 전부 phrasing 이라 `<h3>` 안에 넣어도 된다. */
.q { display: inline; margin-left: 6px; cursor: pointer; user-select: none;
     font-size: .84em; font-weight: 600; color: #0f766e;
     background: #e8f4f2; border: 1px solid #bfe0da; border-radius: 999px;
     padding: 1px 7px; white-space: nowrap; vertical-align: middle; }
.q:hover { background: #d7ebe7; }
.q > input { position: absolute; opacity: 0; width: 0; height: 0; }
.q > b::before { content: "\\25B8"; margin-right: 3px; font-weight: 400; }
.q > input:checked ~ b::before { content: "\\25BE"; }
/* 펼친 번호. ★ `nowrap` 을 풀어야 한다 — 30개가 한 줄로 나가면 접은 의미가 없다. */
.q > .qn { display: none; }
.q > input:checked ~ .qn { display: inline; margin-left: 6px; font-weight: 400;
                           color: #46605c; white-space: normal; }
/* ★ 그림 높이 상한. **폭만 막으면 안 된다** — 인라인 SVG 는 viewBox 비율대로 폭에
   맞춰 늘어나므로, 가로로 넓은 도식이 화면을 통째로 먹는다(2026-08-12 실측: 편향-분산
   그래프 하나가 세로 550px 을 차지했다). `width:auto` + `max-height` 로 비율을
   지키면서 높이로 자른다.

   ★ 240 → 300 으로 올렸다(2026-08-20). 「도식은 거들 뿐」 이라는 판단이 바뀌었다 —
     판 하나가 슬라이드 한 장(944×507)인데 불릿 다섯 줄만 있으면 아래 3분의 2가 빈다.
     제목 30 + 불릿 120 + 여백 40 ≈ 190 을 쓰고 남는 것이 약 310 이라 300 이 상한이다.
     그림이 화면의 절반을 채우는 것이 이제 **목표**다. */
svg, img { max-height: 300px; width: auto; max-width: 100%; height: auto;
           display: block; margin: 10px auto; }
figure { margin: 10px 0; text-align: center; }

/* ★ 어떤 경우에도 가로로 밀지 않는다. 캡처가 목적이므로 이것이 마지막 방어선이다. */
* { max-width: 100%; }
body { overflow-x: hidden; overflow-wrap: anywhere; }
table { table-layout: fixed; }
"""

# 위 두 블록에서 빠진 일반 규칙들(그림·표 기본)은 `_BASE_CSS` 가 계속 갖는다.


# ★ 출처 줄. **앱이 쓴다 — 모델이 쓰지 않는다.**
#
#   기존 파일(백업 260810)이 이렇게 적고 있었다:
#       출처: 기출 1~3회 + 자사 m01~m09 · 2과목 종합
#   여기서 "기출 1~3회" 를 빼는 것이 1번 요구사항이다(2026-08-12 지시). 그런데 이
#   줄을 모델에게 맡기면 지시를 아무리 적어도 다시 "기출" 을 쓸 수 있다 — 실제로
#   기존 4개 파일이 전부 그렇게 적혀 있다. **출처는 앱이 아는 사실**이다(어느 회차를
#   근거로 만들었는지 우리가 안다). 그래서 `<h1>` 과 같은 취급으로 여기서 조립한다.
#   서식(오른쪽 정렬 · 회색 13px)은 기존 파일 그대로 맞췄다.
#   ★ 그러다 **그 줄 자체가 필요 없다**는 결론이 났다(2026-08-12 지시: "문서 끝에
#     이거 인제 안적어도 됨. 너무 추상적"). 어느 회차에서 나왔는지는 **각 제목 옆
#     문번**이 이미 정확히 말한다 — 문서 끝의 한 줄 요약은 그보다 덜 정확하면서
#     자리만 차지한다. 그래서 앱도 쓰지 않는다.
#   ★ 모델이 쓰는 것은 계속 막는다(위 `validate` 의 "출처:" 검사). 앱이 안 쓰기로
#     한 것을 모델이 대신 쓰면 원점이다.


# ★ 본문에 있을 이유가 없는 조각들. 2026-08-12 에 `summary_modeling.html` 맨 아래
#   `]]>` 가 그대로 보였다 — 모델이 CDATA 조각을 남긴 것이다. HTML 본문에서 이 문자열은
#   아무 뜻도 없고 **화면에 글자로 찍힌다.** 검사로 잡아 사람에게 넘기는 것보다
#   조립할 때 걷어내는 것이 맞다 — `<h1>`·출처 줄과 같은 취급이다(앱이 문서를 만든다).
_JUNK = (
    re.compile(r"<!\[CDATA\[", re.I),
    re.compile(r"\]\]>"),
    re.compile(r"<!--\s*-->"),          # 빈 주석
    re.compile(r"^\s*```(?:html)?\s*$", re.M),   # 코드펜스 누출
)


def strip_junk(body_html: str) -> Tuple[str, int]:
    """CDATA·코드펜스 같은 누출 조각을 걷어낸다. (본문, 걷어낸 수)"""
    out, n = body_html, 0
    for pat in _JUNK:
        out, k = pat.subn("", out)
        n += k
    return out, n


def fold_refs(body_html: str) -> str:
    """`<span class="q">모의 1회 1번 · 2회 1번 …</span>` → **접힌 도형**으로 바꾼다.

        <label class="q"><input type="checkbox"><b>9</b><span class="qn">모의 …</span></label>

    ★ 보이는 것은 **횟수**다. 그 개념이 몇 문항에서 나왔는지가 중요도이고, 눌러야
      번호가 나온다. 제목 옆에 번호 30개를 펼쳐 두면 가로 스크롤이 생긴다
      (`_BASE_CSS` 의 `.q` 머리말 참조).

    ★ 모델 출력을 고치지 않고 **여기서** 바꾼다. 서식은 앱이 갖는 것이 규약이다
      (`<h1>`·출처 줄과 같은 취급). 모델에게 label/checkbox 마크업을 시키면 4과목이
      서로 다른 모양으로 나오고, 하나만 틀려도 그 과목만 안 접힌다.

    ★ 이미 `<label class="q">` 인 것은 건드리지 않는다 — 다시 조립해도 안전해야 한다.
    """
    def one(m: "re.Match[str]") -> str:
        inner = m.group(1)
        n = len(_QREF_ANY.findall(inner))
        if not n:
            return m.group(0)          # 문번이 아닌 내용이면 그대로 둔다
        return ('<label class="q"><input type="checkbox">'
                f'<b>{n}</b><span class="qn">{inner}</span></label>')

    return _Q_SPAN_FULL.sub(one, body_html)


def render_html(subject_no: int, body_html: str, css: str = "",
                key: str = "") -> str:
    """발행되는 `.html` 을 조립한다. **LF 로만 만든다** — 개행 변환은 `to_disk()`.

    ★ `<h1>{N}과목 · {이름}</h1>` 이 계약이다. 빌더의 `subject_of()` 가 이 한 줄로
      이론 탭의 순서와 라벨을 정한다. 이름은 시험정보의 과목명과 **정확히 같아야** 한다 —
      요약노트 <h1> 과 문항의 `subject` 문자열이 어긋나면 성적표 링크가 안 붙는다
      (draft.py `_validate` 가 문항 쪽에서 같은 것을 본다).

    ★ 문서 끝 "출처:" 줄은 **붙이지 않는다** — 위 머리말 참조.

    ★ 편(篇)을 `<h1>` 에 넣지 않는다. 빌더가 「N과목 · 」 **뒤를 탭 이름으로 그대로**
      쓰는데(`subject_of` 의 group 2), 「SQL 기본 및 활용 (2편)」 이 되면 문항의
      `subject` 문자열과 어긋나 성적표 링크가 끊긴다. 편은 `<title>` 과 h1 **아래**
      한 줄로 낸다 — 사람은 보고 빌더는 안 읽는다.
    """
    name = subjects().get(subject_no, "")
    u = unit_of(key) if key else None
    pt, rng = (u[1], u[2]) if u else ((1, 1), None)
    part_txt = f"{subject_no}과목 {pt[0]}편" if pt[1] > 1 else f"{subject_no}과목"
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="ko">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{part_txt} · {name}</title>",
        "<style>",
        _BASE_CSS.strip(),
        (css or "").strip(),
        # ★ 접기 규칙은 **맨 마지막**이다 — 모델 CSS 가 `.q` 를 덮어쓰는 것을 막는다
        #   (실측: planning 이 `.q{white-space:nowrap}` 을 넣었다).
        _FOLD_CSS.strip(),
        "</style>",
        "</head>",
        "<body>",
        # ★ 이 한 줄이 빌더와의 계약이다. 편을 붙이지 말 것(위 머리말).
        f"<h1>{subject_no}과목 · {name}</h1>",
        (f'<p class="part">{part_txt}</p>' if pt[1] > 1 else ""),
        # ★ 누출 조각을 걷어내고(`strip_junk`) 문번을 접는다(`fold_refs`).
        fold_refs(strip_junk(body_html.strip())[0]),
        "</body>",
        "</html>",
        "",
    ])


# ★ `.md` 를 **쓰지 않는다.**
#
#   처음에는 검수 화면용으로 "본문은 .html 에 있다" 는 안내문 `.md` 를 같이 썼다.
#   그것이 사고였다(2026-08-12 실측): `summary_routes._edit_target()` 은 `.md` 가
#   있으면 **그것을 먼저 연다.** 그래서 편집기가 66KB 본문이 아니라 1KB 안내문을
#   열었고, 사람은 거기서 고칠 수 있다고 믿게 된다 — `summary_routes.py` 머리말이
#   "고쳤는데 사이트에 반영이 안 된다 는 최악의 혼란" 이라고 적어 둔 바로 그것을
#   내가 만들어 놓은 것이다.
#
#   `.md` 가 없으면 그 함수가 `.html` 을 연다. 그리고 그 편이 **원천을 직접 고치는
#   것**이라 갈림(drift)이 없다 — 같은 함수의 머리말이 그렇게 적어 뒀다.
#   본문을 md 로 한 벌 더 두는 것도 답이 아니다. 두 벌이면 어느 쪽이 진짜인지
#   아무도 모른다.


# ── 결과 ────────────────────────────────────────────────────────────────────
@dataclass
class TheoryResult:
    key: str
    subject_no: int
    headings: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # ★ 원고가 몇 번까지 있는지 남긴다(2026-08-12 요청). 기존 원고는 대주제 5~7개에
    #   소주제가 0~3개였다 — 소주제가 없으면 "1.1 마다 문번" 을 붙일 자리가 없다.
    #   그래서 이 두 값이 규칙이 지켜졌는지 보는 눈금이 된다.
    h2_count: int = 0
    h3_count: int = 0
    refs: int = 0                 # 붙은 문번 참조 개수
    html_bytes: int = 0
    cost_usd: float = 0.0
    turns: int = 0
    seconds: float = 0.0
    model: str = ""
    written: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and self.html_bytes > 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key, "subject_no": self.subject_no,
            "subject": subjects().get(self.subject_no, ""),
            "ok": self.ok, "headings": self.headings,
            "problems": self.problems, "warnings": self.warnings,
            "h2_count": self.h2_count, "h3_count": self.h3_count,
            "refs": self.refs, "html_bytes": self.html_bytes,
            "cost_usd": round(self.cost_usd, 4), "turns": self.turns,
            "seconds": round(self.seconds, 1), "model": self.model,
            "written": self.written,
        }


def available_rounds(book_dir: str) -> List[str]:
    """`_rounds/` 에 실제로 있는 회차. 이론의 소스다.

    ★ 회차 수를 상수로 두지 않는다. 프롬프트 규약은 "m01~m09 전체를 병합" 이지만
      m09 가 아직 없을 때도 이 라우트가 돌아야 한다(대기 인원에게 이전 파일을
      넘기는 동안 m09 를 집필 중일 수 있다). 있는 것으로 만들고, 회차가 늘면
      다시 부르면 된다 — 이론은 회차별이 아니라 **과목별**이므로 덮어쓰기가 맞다.
    """
    d = os.path.join(book_dir, "_rounds")
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [n[:-5] for n in names
            if re.fullmatch(r"m\d{2}\.json", n)]


def source_view(book_dir: str) -> str:
    """모델에게 보여 줄 **읽을 것만 담은 폴더**를 임시로 만들고 그 경로를 준다.

    ★ 왜 필요한가 — 프롬프트로 "`01/` 을 열지 말라" 고 적는 것은 **부탁이지 차단이
      아니다.** `provider.py` 는 `cwd` 를 책 폴더로 주고 Read·Grep·Glob 을 허용하므로
      모델이 `00/`(원본 PDF)·`01/`(기출 240문항)을 그냥 읽을 수 있다. 읽으면 그
      문번이 요약노트에 새어 나온다 — 그것이 나오지 않는 것이 목표다(2026-08-12 지시:
      "기출을 다 막아야겠네요 · ocr을 다 막으세요").

      그래서 `_rounds/m??.json` 만 복사한 폴더를 만들어 그것을 `cwd` 로 준다.
      `01/` 은 **상대경로로 도달할 수 없는 곳**이 된다. 지시가 아니라 구조다.

    ★ 정직하게 남긴다: 절대경로(`D:\\00work\\ocr-output-260730\\01\\01-01.md`)로는
      여전히 읽을 수 있다. SDK 옵션에 경로 화이트리스트가 없다. 다만 프롬프트가 책
      경로를 알려 주지 않고 그런 폴더가 있다는 말도 하지 않으므로, 모델이 그것을
      찾아갈 이유가 없다. 남은 구멍은 출력 검사(`validate`)가 본다.

    ★ 복사한다(심볼릭 링크가 아니다). Windows 에서 링크는 관리자 권한이 필요하고,
      권한 없이 조용히 실패하면 **차단이 없는 채로 도는 것**이 최악이다. 2MB 다.
    """
    import json as _json
    import tempfile
    view = tempfile.mkdtemp(prefix="theory-src-")
    dst = os.path.join(view, "_rounds")
    os.makedirs(dst, exist_ok=True)

    # ★ 회차 파일을 그대로 복사하지 **않는다.** 편마다 필요한 문항만 모아 **한 파일**로 준다.
    #
    #   전에는 `_rounds/m01.json`~`m20.json` 을 통째로 복사했다. 파일 하나에 50문항
    #   (두 과목 전부)이 들어 있고 회차가 20개다. 1과목 요약노트는 그중 10문항×20 =
    #   200문항만 필요한데, 모델이 20개 파일을 열어 필요한 것을 골라야 한다.
    #   실측(2026-08-20): `m20.json` 을 일곱 번 다시 읽으며 25분이 지나도 안 끝났다.
    #   빅분기는 9회차라 견뎠던 것이 20회차에서 무너졌다.
    #
    #   그래서 편마다 `_rounds/<편키>.json` 하나를 만든다. 그 편의 문항번호 범위에
    #   드는 문항만, 이론에 필요한 필드만 담는다 — 열 파일이 하나이고 크기도 작다.
    docs = {}
    for rc in available_rounds(book_dir):
        try:
            with open(os.path.join(book_dir, "_rounds", f"{rc}.json"),
                      encoding="utf-8") as f:
                docs[rc] = _json.load(f) or {}
        except (OSError, ValueError):
            continue

    from services.authoring import parts as _P

    units = _P.theory_units()
    for key, _no, _pt, (lo, hi) in units:
        rows = []
        for rc, d in docs.items():
            for q in d.get("questions") or []:
                try:
                    qn = int(q.get("question_no") or 0)
                except (TypeError, ValueError):
                    continue
                if not (lo <= qn <= hi):
                    continue
                rows.append({
                    "round": d.get("round_label") or rc,
                    "question_no": qn,
                    "subject": q.get("subject") or "",
                    "difficulty": q.get("difficulty") or "",
                    "tags": q.get("tags") or [],
                    # ★ 이론은 **해설에서** 개념을 뽑는다. 발문·보기는 넣지 않는다 —
                    #   넣으면 파일이 세 배가 되고 모델이 문항을 베끼는 쪽으로 간다.
                    "explanation": q.get("explanation") or "",
                    # ★★ 해설의 **인라인 SVG 를 그대로 넘긴다.** 집필이 그 개념을
                    #   설명하려고 만든 그림이다 — 이론에서 다시 그리면 원본과
                    #   어긋나고, 버리면 이미 만든 것을 잃는다(2026-08-20 지시:
                    #   「만든건 잘 써줘」). 모델이 이 문자열을 그대로 붙여 쓴다.
                    "assets": [{"name": a.get("name") or "",
                                "svg": a.get("svg") or ""}
                               for a in (q.get("assets") or [])
                               if isinstance(a, dict) and a.get("svg")],
                })
        rows.sort(key=lambda r: (r["question_no"], str(r["round"])))
        with open(os.path.join(dst, f"{key}.json"), "w", encoding="utf-8") as f:
            _json.dump({"unit": key, "question_range": [lo, hi],
                        "n": len(rows), "items": rows},
                       f, ensure_ascii=False, indent=1)
        # ★ v2 — [해설 모아 노트 구조화] 결과가 있으면 함께 넘긴다. 사람이 검토한
        #   목차(대단원·소단원·출처)를 요약노트가 그대로 따르게 하려는 것이다.
        try:
            from services.lecture import outline as _O
            if os.path.isfile(_O.outline_path(key)):
                os.makedirs(os.path.join(view, "_outline"), exist_ok=True)
                import shutil as _sh
                _sh.copyfile(_O.outline_path(key), os.path.join(view, "_outline", f"{key}.json"))
        except Exception:                                    # noqa: BLE001
            pass
    return view


def is_done(key: str) -> bool:
    """이 과목 요약노트가 이미 있는가. 끊긴 잡을 다시 돌릴 때 건너뛴다."""
    p = paths.summary_html(key)
    try:
        return os.path.getsize(p) > 0
    except OSError:
        return False


# ── 집필 ────────────────────────────────────────────────────────────────────
def draft_theory(*, key: str, book_dir: str,
                 model: str = "", effort: Optional[str] = None,
                 view: Optional[str] = None,
                 on_activity: Optional[Callable[[str], None]] = None,
                 ) -> TheoryResult:
    """과목 1개 요약노트를 집필해 `03/` 에 쓴다.

    ★ 검증에 걸리면 **쓰지 않는다.** 문항 집필(`draft.py`)은 실패분도 스테이징에
      저장하지만 여기는 다르다 — 저장 위치가 곧 발행 원천(`03/`)이라 잘못된 것을
      쓰면 그대로 사이트에 나간다. 문항 쪽은 `_rounds/` 앞에 스테이징이 한 겹
      있어서 그 위험이 없었다.
    """
    if not no_of(key):
        raise ValueError(f"알 수 없는 요약노트 키: {key!r} "
                         f"({' | '.join(k for k, _ in keys())})")
    import shutil

    subject_no = no_of(key)
    rounds = available_rounds(book_dir)
    res = TheoryResult(key=key, subject_no=subject_no, model=model or "cli-default")

    # ★ cwd 가 책 폴더가 **아니다.** `_rounds` 만 담은 임시 폴더다 — 위 `source_view()`
    #   머리말 참조. 문항 집필(`draft.py`)은 기출을 읽어야 해서 책 폴더를 주지만
    #   요약노트는 우리 해설만 모으는 것이 1번 요구사항이다.
    #
    # ★ `view` 를 받으면 **그것을 쓰고 지우지 않는다.** 과목마다 폴더를 새로 만들면
    #   `cwd` 가 매번 달라져 프롬프트 캐시 접두가 갈린다 — provider.py 실측으로 그
    #   차이가 $0.257 → $0.066 이다. 잡이 하나 만들어 4과목에 넘겨 주면 같은 접두를
    #   쓴다. 지우는 책임도 만든 쪽에 있다.
    own_view = view is None
    if own_view:
        view = source_view(book_dir)
    # ★ 턴 상한을 올린다. 기본 40 은 문항 집필(파트 1개 = 2~3턴) 기준이다. 요약노트는
    #   9회차 파일을 Grep·Read 로 훑어야 해서 턴이 많다 — 2026-08-12 실측에서 interpret
    #   이 **42턴**을 썼다. 상한에 걸리면 12분·$3.6 을 쓰고 0줄을 받는다. 폭주는
    #   `_abort_reason` 의 벽시계 상한이 막으므로 여기서 턴으로 조일 이유가 없다.
    author = ClaudeAuthor(model=model, effort=effort, cwd=view,
                          max_turns=80, on_activity=on_activity)

    t0 = time.monotonic()
    got: Dict[str, Any] = {}
    try:
        got = author.structured(
            system(),
            theory_prompt(subject_no=subject_no, rounds=rounds, key=key),
            theory_schema())
    except ProviderError as e:
        res.problems.append(str(e))
    finally:
        res.cost_usd = author.last_cost_usd
        res.turns = author.last_turns
        res.seconds = time.monotonic() - t0
        # ★ **내가 만든 것만** 지운다. 잡이 넘겨 준 폴더를 지우면 다음 과목이
        #   빈 폴더를 보고 아무 해설도 못 읽는다.
        if own_view:
            shutil.rmtree(view, ignore_errors=True)

    if not got:
        return res

    res.headings = [str(h) for h in (got.get("headings") or [])]
    body = str(got.get("body_html") or "")
    res.h2_count, res.h3_count = heading_counts(body)
    res.refs = len(_QREF_ANY.findall(body))
    p, w = validate(got, subject_no)
    res.problems += p
    res.warnings += w
    if res.problems:
        return res

    html = render_html(subject_no, str(got.get("body_html") or ""),
                       str(got.get("css") or ""), key=key)
    hp = paths.summary_html(key)
    # ★ 개행은 `to_disk()` 한 곳을 지난다(atomic_io 머리말). 03/ 이 아직 없으면
    #   형제가 없어 LF 로 떨어지는데, 그것이 `03/*` 의 실측 규약이다.
    from core.atomic_io import atomic_write_text, backup_sibling
    backup_sibling(hp)
    atomic_write_text(hp, paths.to_disk(hp, html))
    res.written.append(paths.rel(hp))
    res.html_bytes = len(html.encode("utf-8"))
    return res
