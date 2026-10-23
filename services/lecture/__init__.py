"""이론 노트 4단 (v2).

    해설 모아 노트 구조화   _rounds 해설 → 03/_outline/<key>.json·md      (outline.py)
    이론 요약 노트          03/summary_<key>.html  — 기존 services/authoring/theory.py
    요약반 강의 노트        03-2/ — ①자막 ②낭독 ③SVG = 1배 원고 + 듣기 검수
    종합반 강의 노트        03-3/ — 요약반 노트를 ④ n배로 + 듣기 검수

강의 노트의 원고 HTML 은 lecture-composer · summaryhtml2videoscripthtml 의 규약
(h3 = 한 장, data-say 자막 · data-read 낭독)을 그대로 따른다. 영상(mp4)은 이 앱에서
만들지 않는다 — 원고와 렌더 키트까지가 이 앱의 몫이고, 굽기는 다른 PC 에서 한다.
"""
