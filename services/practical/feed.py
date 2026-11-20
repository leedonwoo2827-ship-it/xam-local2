# -*- coding: utf-8 -*-
"""실기 집필 결과(02/practical/mNN) → 2부(이론 노트)가 먹는 `_rounds` 모양.

★ 2부(해설 모아 노트 구조화 · 이론 요약 노트 · 요약반/종합반)는 필기 `_rounds/mNN.json` 의
  `questions[{subject_no, question_no, explanation, tags, assets}]` 를 읽는다. 실기는 그 파일이
  없다 — 이 모듈이 같은 모양을 **즉석에서** 만들어 준다(파일로 쓰지 않는다. 진실은 02/practical).

  subject_no  = 묶음(1 기본작업 · 2 계산작업 · 3 분석작업 · 4 기타작업)
  question_no = **회차 안 일련번호**(문제1-1 → 1 … 문제4-2 → 12). 묶음 문항수는 시험정보에서.
                이론 쪽의 「과목 = 번호 구간」 규칙(theory_units)이 그대로 맞는다.
  explanation = 발문 + 지시사항 + 모범답안(제목·절차·수식) — 그림 이름표는 그림 설명으로 바꾼다
  tags        = 쓰인 함수(계산작업) 또는 기능 이름(서식·필터·부분합 …)

★ 출처는 우리 집필 회차뿐이다 — 확정본(01/practical, 출판사 판)은 읽지 않는다(필기와 같은 규칙).
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, List

TOK = re.compile(r"\{\{(f-\d+)\}\}")
BOX = re.compile(r"\{\{([ck]-\d+)\}\}")     # 박스 c · 코드박스 k (1급 집필)

# 기능 낱말 — 계산작업이 아닌 묶음은 함수가 없어서 이것으로 태그를 단다(먼저 걸린 것부터)
FEATURES = [
    "고급 필터", "자동 필터", "조건부 서식", "사용자 지정 표시 형식", "셀 스타일", "이름 정의", "메모",
    "텍스트 나누기", "선택하여 붙여넣기", "부분합", "피벗 테이블", "피벗 차트", "시나리오", "목표값 찾기",
    "데이터 표", "통합", "정렬", "중복된 항목 제거", "데이터 유효성 검사", "매크로", "차트", "테두리",
    "병합하고 가운데 맞춤", "행 높이", "열 너비", "윗주", "하이퍼링크", "페이지 설정", "인쇄 영역",
    "데이터 입력", "사용자 정의 함수", "배열 수식", "프로시저", "폼", "외부 데이터", "페이지 레이아웃",
    # 2교시 액세스
    "기본 키", "입력 마스크", "유효성 검사 규칙", "조회 속성", "관계 설정", "참조 무결성", "가져오기", "연결 테이블",
    "조건부 서식", "하위 폼", "컨트롤 원본", "탭 순서", "이벤트 프로시저", "보고서", "그룹화", "누적 합계",
    "업데이트 쿼리", "매개 변수 쿼리", "크로스탭 쿼리", "테이블 만들기 쿼리", "추가 쿼리", "삭제 쿼리",
    "불일치 검색", "요약 쿼리", "하위 질의", "쿼리",
]


def _offsets(spec: Dict[str, Any]) -> Dict[int, int]:
    """묶음 번호 → 그 묶음 앞까지의 문항 수(회차 안 일련번호의 시작점)."""
    out, acc = {}, 0
    for s in spec.get("subjects") or []:
        out[int(s.get("no") or 0)] = acc
        acc += int(s.get("count") or 0)
    return out


def _fig_text(f: Dict[str, Any]) -> str:
    cap = f.get("caption") or ""
    if f.get("kind") == "table" and f.get("columns"):
        return f"(표: {cap} — 열 {', '.join(map(str, f['columns'][:10]))})"
    return f"({'차트' if f.get('kind') == 'chart' else '대화상자'}: {cap}{' — ' + f['desc'] if f.get('desc') else ''})"


def _box_text(b: Dict[str, Any]) -> str:
    t = str(b.get("text") or "").rstrip()
    return ("(코드)\n" + t) if b.get("code", True) else t


def _lines(lines: List[str], figs: Dict[str, dict], boxes: Dict[str, dict] = None) -> List[str]:
    out = []
    for s in lines or []:
        s = str(s)
        s = BOX.sub(lambda m: _box_text((boxes or {})[m.group(1)]) if m.group(1) in (boxes or {}) else "", s)
        s = TOK.sub(lambda m: _fig_text(figs[m.group(1)]) if m.group(1) in figs else "", s).strip()
        if s:
            out.append(s)
    return out


def tags_of(it: Dict[str, Any]) -> List[str]:
    fn = [str(x).upper() for x in it.get("functions") or [] if x]
    if fn:
        return fn
    text = " ".join([it.get("lead") or ""] + list(it.get("instructions") or [])
                    + list((it.get("answer") or {}).get("steps") or []))
    got = [w for w in FEATURES if w in text]
    if not got and re.search(r"주어진 대로 입력|자료를 입력", text):
        got = ["데이터 입력"]
    return got[:4] or ["(기능 미상)"]


def explanation_of(it: Dict[str, Any]) -> str:
    figs = {f.get("id"): f for f in it.get("figures") or []}
    boxes = {b.get("id"): b for b in it.get("boxes") or [] if b.get("id")}
    a = it.get("answer") or {}
    parts = [f"[문제] {it.get('lead') or ''}"] + _lines(it.get("instructions") or [], figs, boxes)
    parts += [f"[모범답안] {a.get('title') or ''}"] + _lines(a.get("steps") or [], figs, boxes)
    for f in a.get("formulas") or []:
        if isinstance(f, dict) and f.get("formula"):
            parts.append(f"수식 {f.get('cell') or ''}: {f['formula']}" + (f" (채우기 {f['fill']})" if f.get("fill") else ""))
    return "\n".join(p for p in parts if p.strip())


def rounds(book_dir: str) -> List[Dict[str, Any]]:
    """02/practical/mNN (+ 1급 2교시 02/practical-access/mNN) → [{round_code, round_label, questions[…]}] (회차 순).

    ★ 2교시 묶음은 2부 쪽 번호로 이어 매긴다(parts.part2_subjects — 문제1 DB구축 → 묶음 5 …)."""
    from services.authoring import parts
    spec = parts.active() or {}
    p2 = parts.part2_subjects(spec)
    off = _offsets({"subjects": p2})
    names = {int(s.get("no") or 0): str(s.get("name") or "") for s in p2}
    # (교시, 교시 안 묶음) → 2부 묶음 번호
    to_no = {(int(s.get("session") or 1), int(s.get("session_part") or s.get("no") or 0)): int(s.get("no") or 0) for s in p2}
    root = os.path.join(book_dir, "02", "practical")
    out = []
    for d in sorted(glob.glob(os.path.join(root, "m[0-9][0-9]"))):
        rc = os.path.basename(d)
        qs = []
        files = [(1, f) for f in sorted(glob.glob(os.path.join(d, f"{rc[1:]}-[0-9]-[0-9][0-9].json")))]
        d2 = os.path.join(book_dir, "02", "practical-access", rc)
        files += [(2, f) for f in sorted(glob.glob(os.path.join(d2, f"{rc[1:]}-[0-9]-[0-9][0-9].json")))]
        for sess, f in files:
            try:
                with open(f, encoding="utf-8") as fh:
                    it = json.load(fh)
            except (OSError, ValueError):
                continue
            part, no = int(it.get("part") or 0), int(it.get("no") or 0)
            if not part or not no:            # 묶음 머리(no=0)는 문항이 아니다
                continue
            label = f"문제{part}-{no}"
            if sess != 1:
                if (sess, part) not in to_no:
                    continue
                label = f"{sess}교시 문제{part}-{no}"     # 회차 안 번호는 시험지 그대로(2교시 문제1-1)
                part = to_no[(sess, part)]
            qs.append({
                "subject_no": part, "subject": names.get(part, ""),
                "question_no": off.get(part, 0) + no,
                "label": label,
                "difficulty": "", "tags": tags_of(it),
                "explanation": explanation_of(it),
                "assets": [],                 # 실기 그림은 SVG 가 아니다(설계·PNG) — 이론에 넘기지 않는다
                "points": it.get("points"),
            })
        if qs:
            qs.sort(key=lambda q: q["question_no"])
            out.append({"round_code": rc, "round_label": f"모의 {int(rc[1:])}회", "questions": qs})
    return out
