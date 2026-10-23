# -*- coding: utf-8 -*-
"""템플릿 pptx 의 **규격 슬라이드**를 읽는다.

★ 왜 필요한가. 템플릿은 지금까지 슬라이드 크기와 테마 글꼴만 실었고, 글자 크기·여백은
  전부 코드(`layout.TYPE_PT`)에 있었다. 그래서 파워포인트로 템플릿을 고쳐도 결과가
  안 바뀐다 — 사용자가 물었고(2026-08-21: "당사자가 저기 템플릿 폴더의 파워포인트를
  바꾸면 그렇게 들어가는거지?!") 답이 "아니오" 였다. 그것을 "예" 로 만든다.

★ 규약은 **표 한 개**다. 템플릿의 어느 슬라이드든 첫 칸이 `요소`, 둘째 칸이 `크기`
  인 표가 있으면 그 표를 읽는다.

      요소            크기
      발문            16
      보기            12
      해설            10
      …

  표를 고르는 이유: 파워포인트에서 숫자 칸만 눌러 고칠 수 있고, 도형 이름이나
  위치처럼 눈에 안 보이는 곳에 값을 숨기지 않는다. 규격이 화면에 그대로 보인다.

★ **모르는 이름은 무시하고, 없는 이름은 기본값을 쓴다.** 표를 지워도 앱은 돌아간다.
  규격 파일이 앱을 멈추게 하면 안 된다.

★ 여백·간격은 `cm` 로 적는다(파워포인트가 cm 로 보여 주므로). 글자만 pt 다.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

# 표의 첫 칸(사람이 읽는 이름) → 내부 열쇠
LABELS = {
    # 문제 덱
    "발문": "q",
    "보기": "opt4",
    "보기(1단)": "opt",
    "보기 1단": "opt",
    "지문": "passage",
    "표": "table",
    "해설": "expl",
    "코드": "pre",
    "문번": "head",
    "난도": "pill",
    "정답배지": "badge",
    "정답 배지": "badge",
    # 도식
    "도식 안 글자": "fig_text",
    "도식글자": "fig_text",
    # 이론 덱
    "이론 소제목": "head3",
    "이론 대단원칩": "eyebrow",
    "이론 항목": "bullets",
    # 표지
    "표지 위": "cover_eyebrow",
    "표지 제목": "cover_title",
    "표지 아래": "cover_lead",
}

# 글자가 아닌 것 — cm 로 적고 px 로 바꿔 쓴다
GEOM = {
    "여백": "pad_cm",          # 슬라이드 바깥 여백
    "요소 간격": "gap_cm",      # 블록 사이 기본 간격
}

CM_PER_PX = 33.867 / 1920      # 1920px = 33.867cm (13.333in)

_NUM = re.compile(r"-?[\d.]+")


def _num(s: str) -> Optional[float]:
    m = _NUM.search(s or "")
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def read(path: str) -> Dict[str, Any]:
    """템플릿에서 규격을 읽는다. 반환: `{"type_pt": {...}, "pad_px": …, "gap_px": …}`

    규격 표가 없으면 빈 dict 를 돌려준다 — 호출부가 기본값을 쓴다.
    """
    out: Dict[str, Any] = {}
    if not path or not os.path.isfile(path):
        return out
    try:
        from pptx import Presentation
        prs = Presentation(path)
    except Exception:
        return out

    type_pt: Dict[str, float] = {}
    for slide in prs.slides:
        for shp in slide.shapes:
            if not (getattr(shp, "has_table", False) and shp.has_table):
                continue
            tbl = shp.table
            if len(tbl.columns) < 2:
                continue
            head = [c.text.strip() for c in tbl.rows[0].cells]
            # 첫 행이 머리글이 아니어도 읽는다 — 사람이 머리글을 지울 수 있다.
            start = 1 if head and ("요소" in head[0] or "항목" in head[0]) else 0
            for row in list(tbl.rows)[start:]:
                cells = [c.text.strip() for c in row.cells]
                if len(cells) < 2 or not cells[0]:
                    continue
                name = re.sub(r"\s+", " ", cells[0])
                val = _num(cells[1])
                if val is None:
                    continue
                key = LABELS.get(name)
                if key:
                    type_pt[key] = val
                    continue
                g = GEOM.get(name)
                if g == "pad_cm":
                    out["pad_px"] = val / CM_PER_PX
                elif g == "gap_cm":
                    out["gap_px"] = val / CM_PER_PX
    if type_pt:
        out["type_pt"] = type_pt
    return out


def describe(spec: Dict[str, Any]) -> str:
    """리포트·화면에 남길 한 줄. 무엇이 템플릿에서 왔는지 보이게 한다."""
    if not spec:
        return "템플릿 규격 없음 — 내장 기본값을 씁니다"
    bits = []
    if spec.get("type_pt"):
        bits.append("글자 %d개" % len(spec["type_pt"]))
    if "pad_px" in spec:
        bits.append("여백 %.2fcm" % (spec["pad_px"] * CM_PER_PX))
    if "gap_px" in spec:
        bits.append("간격 %.2fcm" % (spec["gap_px"] * CM_PER_PX))
    return "템플릿 규격 적용 — " + " · ".join(bits)
