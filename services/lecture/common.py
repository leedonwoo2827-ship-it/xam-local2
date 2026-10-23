# -*- coding: utf-8 -*-
"""강의 노트 공용 — 종류 · 경로 · 과목 목록 · 해시.

★ 계층 규약: FastAPI 를 import 하지 않는다.
★ 경로는 전부 `paths.book_dir()` 기준이다 — 작업 폴더를 바꾸면 따라 바뀐다.
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Dict, List, Tuple

from services.book import paths

# 종류 → (폴더, 화면 이름)
KINDS: Dict[str, Tuple[str, str]] = {
    "summary": ("03-2", "요약반 강의 노트"),
    "full": ("03-3", "종합반 강의 노트"),
}
DEFAULT_FACTOR = 3          # 종합반 배수 기본값 (lecture-composer 실물 x3 와 같다)
DEFAULT_LISTENERS = 2       # 듣기 검수 필요 인원 기본값


def check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"종류는 {', '.join(KINDS)} 중 하나입니다: {kind}")
    return kind


def check_key(key: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", key or ""):
        raise ValueError(f"과목 키가 올바르지 않습니다: {key}")
    return key


def subjects() -> List[Dict[str, object]]:
    """[{key, no, name}] — 시험정보(exams/<pd>.json)의 과목 순서 그대로."""
    from services.authoring import parts, theory

    names = parts.subjects_map()
    return [{"key": k, "no": int(no), "name": names.get(int(no), "")}
            for k, no in theory.keys()]


def subject(key: str) -> Dict[str, object]:
    for s in subjects():
        if s["key"] == key:
            return s
    raise ValueError(f"이 책에 없는 과목입니다: {key}")


def kind_dir(kind: str) -> str:
    return os.path.join(paths.book_dir(), KINDS[check_kind(kind)][0])


def doc_path(kind: str, key: str) -> str:
    """원천 JSON — 화면이 고치는 것은 이것이고, HTML 은 여기서 다시 굽는다."""
    return os.path.join(kind_dir(kind), f"{check_key(key)}.json")


def html_name(kind: str, key: str, factor: int = DEFAULT_FACTOR) -> str:
    """lecture-composer 실물과 같은 이름 — `1summary-datamodel_원고.html` · `…_원고x3.html`.

    ★ 앞의 숫자는 **과목 번호**다. IP 허브의 cards 수집과 lecture-composer 입력이 이
      모양을 이미 쓰고 있어서, 이름을 맞춰 두면 손으로 바꿔 붙일 일이 없다.
    """
    no = subject(key)["no"]
    tail = "_원고.html" if kind == "summary" else f"_원고x{int(factor)}.html"
    return f"{no}summary-{key}{tail}"


def html_path(kind: str, key: str, factor: int = DEFAULT_FACTOR) -> str:
    return os.path.join(kind_dir(kind), html_name(kind, key, factor))


def audio_dir(kind: str, key: str) -> str:
    return os.path.join(kind_dir(kind), "_audio", check_key(key))


def review_path(kind: str, key: str) -> str:
    return os.path.join(kind_dir(kind), "_review", f"{check_key(key)}.jsonl")


def outline_dir() -> str:
    return os.path.join(paths.book_dir(), "03", "_outline")


def h(text: str) -> str:
    """낭독 해시 — 듣기 검수의 OK 가 어느 소리에 대한 것인지 묶는다(8자)."""
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:8]
