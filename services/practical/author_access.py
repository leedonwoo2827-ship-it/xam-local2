# -*- coding: utf-8 -*-
"""실기 문제 집필 — 2교시 액세스(컴활1급). 확정본(01/practical-access) 을 바탕으로 **새 회차**를 쓴다.

  02/practical-access/m{NN}/db.json              그 회차의 DB 설계(문제1 이 정한다 — 테이블·필드·레코드·관계·외부 데이터)
  02/practical-access/m{NN}/part{P}.json         묶음 하나를 쓴 원본 응답(이어하기 단위)
  02/practical-access/m{NN}/{NN}-{P}-{NN}.json   문항 구조(지시 · 모범답안 · SQL/VBA 코드박스 · 그림 설계)
  02/practical-access/m{NN}/{NN}-{P}-{NN}.md     사람이 읽는 원고

★ 엑셀 집필(author.py)과 다른 점 — **한 회차의 문제1~4 가 DB 하나를 같이 쓴다.** 묶음마다 따로 쓰면
  테이블이 어긋나므로 문제1(DB구축)이 DB 를 설계하고, 문제2~4 는 그 DB 를 받아 그 위에 쓴다
  (문제 파일에 미리 있어야 할 폼·보고서·쿼리는 given 에 설계로 남긴다 — accdb 빌더가 읽는다).
★ 바탕 회차 배분 · 변형 강도 · 난도 규칙은 엑셀과 같다(author.source_round · is_strong, 시험정보 author.round_map).
★ 그림: 원본 그림(출판사 저작물)은 쓰지 않는다. 쿼리는 SQL + 결과 행, 폼·보고서는 속성 값으로 정답을 남긴다.
"""
from __future__ import annotations

import glob
import json
import os
import threading
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_text
from services.book import paths
from services.practical import author as pa

SESSION = 2


def part_names() -> Dict[int, str]:
    for s in pa._spec().get("sessions") or []:
        if int(s.get("no") or 0) == SESSION:
            return {int(x["no"]): str(x.get("name") or "") for x in s.get("subjects") or [] if x.get("no")}
    return {1: "DB구축", 2: "입력 및 수정 기능 구현", 3: "조회 및 출력 기능 구현", 4: "처리 기능 구현"}


def src_dir() -> str:
    return os.path.join(paths.book_dir(), "01", "practical-access")


def out_root() -> str:
    return os.path.join(paths.book_dir(), "02", "practical-access")


def round_dir(m: int) -> str:
    return os.path.join(out_root(), f"m{m:02d}")


def source_items(rnd: int, part: int) -> List[dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(src_dir(), f"{rnd:02d}-{part}-*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        md = f[:-5] + ".md"
        d["_md"] = open(md, encoding="utf-8").read() if os.path.isfile(md) else ""
        out.append(d)
    return out


def sources_ready() -> Dict[int, int]:
    got: Dict[int, int] = {}
    for f in glob.glob(os.path.join(src_dir(), "*.json")):
        b = os.path.basename(f)
        if len(b) >= 2 and b[:2].isdigit():
            got[int(b[:2])] = got.get(int(b[:2]), 0) + 1
    return dict(sorted(got.items()))


def part_done(m: int, part: int) -> bool:
    return os.path.isfile(os.path.join(round_dir(m), f"part{part}.json"))


def load_db(m: int) -> Optional[dict]:
    f = os.path.join(round_dir(m), "db.json")
    if not os.path.isfile(f):
        return None
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


# ── 지시 ──────────────────────────────────────────────────────────────────
SYSTEM = """당신은 컴퓨터활용능력 1급 실기 **2교시(데이터베이스 실무, MS Office 2021 액세스)** 문제집의 집필자입니다.
출판사 기출 풀이집을 판독한 「바탕 문항」을 받아, **같은 출제 유형의 새 문항**을 씁니다.
결과는 자사 모의고사 원고로 출판·배포됩니다. 저작권상 바탕의 표면을 옮겨 오면 안 됩니다.

[반드시 바꿀 것 — 표면 전부]
- 업무 영역(시나리오), 테이블·필드·쿼리·폼·보고서·컨트롤·매크로 이름, 레코드 값, 조건 값, 서식 값, 메시지 문구, 외부 데이터 파일 이름
- 문장 표현. 「변형 강도: 강」 이면 같은 범주의 다른 기능·다른 함수 조합을 씁니다
  (예: 업데이트 쿼리 ↔ 테이블 만들기 쿼리, DLookup ↔ DCount, Filter ↔ RecordSource, In(하위 질의) ↔ Not In, Like ↔ InStr).

[유지할 것 — 시험 형식]
- 묶음 번호·문항 번호·배점, 문항이 다루는 기능의 종류
  · 문제1 DB구축: 필드 속성(기본 키·필드 크기·형식·입력 마스크·유효성 검사 규칙/텍스트·기본값·필수·인덱스·캡션),
    조회 속성(콤보 상자·행 원본·바운드 열·열 너비), 관계 설정(참조 무결성·관련 필드 모두 업데이트/삭제), 외부 데이터 가져오기·연결
  · 문제2 입력 및 수정: 폼 속성(레코드 원본·기본 보기·탐색 단추·스크롤 막대·구분 선), 컨트롤 원본 식, 탭 순서, 조건부 서식,
    하위 폼 연결, 매크로(OpenForm/OpenReport + Where 조건), 이벤트 프로시저
  · 문제3 조회 및 출력: 보고서(그룹화·정렬, 바닥글 요약 식, =Format(…), 페이지 번호 식, 누적 합계, 중복 내용 숨기기),
    조회 프로시저(Filter·FilterOn·RecordSource·FindFirst·RecordsetClone·DoCmd.OpenReport·MsgBox)
  · 문제4 처리 기능: 쿼리(업데이트 · 매개 변수 · 요약 · 크로스탭 · 테이블 만들기 · 추가 · 삭제 · 불일치 검색 · 하위 질의)
- 지시문 문체(「~하시오.」), 원문자 ① ② …, ▶ 보조 지시, (각 N점)·(N점) 표기, 〈테이블 이름〉 표기

[DB — 한 회차의 문제1~4 가 같은 DB 를 쓴다]
- 문제1 을 쓸 때 db 를 설계합니다: tables(이름 · fields[이름·데이터 형식·크기·키 여부] · rows[레코드 12~25개]),
  relationships(**문제 파일에 이미 있는** 관계 — 문제1 이 「관계를 설정하시오」 이면 그 관계는 빼고 정답에만),
  external(가져오기·연결할 외부 파일 — 파일 이름 · 시트/구분 · columns · rows).
  rows 는 문제2~4 의 쿼리·폼·보고서 조건이 **일부 레코드에만** 걸리도록 고르게 만듭니다(0건·전부가 되지 않게).
  필드 속성 문제에서 수험자가 바꿀 속성은 문제 파일의 초기값(fields 의 값)이 지시 전 상태여야 합니다.
- 문제2~4 는 받은 db 의 테이블·필드만 씁니다. 문제 파일에 **미리 있어야 할** 폼·보고서·쿼리·매크로는 given 에
  지시 적용 전 상태로 설계합니다(이름 · 레코드 원본 · 컨트롤[종류·이름·원본·위치 구역] · 속성).

[모범답안]
- answer.title: 「① 테이블 완성」 처럼 흰 원문자 + 짧은 제목
- answer.steps: 풀이 절차를 한 줄에 하나 — 속성 시트에서 고를 값은 「'형식' 속성: 통화」 처럼 속성 이름과 값을 그대로.
- 쿼리의 완성 SQL · 이벤트 프로시저 VBA 는 boxes 에 {"id": "k-1", "code": true, "text": "…"} 로 적고 steps 에 {{k-1}} 한 줄.
  들여쓰기는 스페이스 3칸. 식(「=Format(Date(),"yyyy-mm-dd")」)은 steps 줄 그대로.
- 쿼리 문항은 answer.result 에 **db 레코드로 실제 실행한 결과**(columns · rows)를 적습니다. 업데이트·테이블 만들기·추가 쿼리는
  바뀐 뒤 테이블의 해당 행. 매개 변수 쿼리는 지문의 예시 입력값으로.
- 폼·보고서 문항은 answer.props 에 [{object, control, property, value}] 로 정답 속성 값을 적습니다.

[그림 — 새로 설계]
- 바탕의 그림(결과 화면·대화상자·디자인 창)은 쓰지 않습니다. figures 에 **새로 그릴 설계**를 적습니다.
  · kind "table": 데이터시트·쿼리 결과 — columns·rows 에 실제 값
  · kind "dialog": 폼·보고서 화면, 매개 변수 입력 창, 메시지 상자, 관계 창 — desc 에 항목과 값
- 지문이나 해설 안 그림 자리에 {{f-1}} 한 줄. 바탕 그림 파일은 필요할 때만 Read 로 열어 무엇을 보여 줬는지만 확인합니다.

[난도]
- 난도는 **실제 시험(상시 시험) 수준**에 맞춥니다. 바탕 기출이 실제 시험을 옮긴 것이므로 그 수준이 기준입니다.
- 회차마다 일부러 쉽게 하거나 어렵게 하지 않습니다. 「변형 강도」 는 바꾸는 범위일 뿐 난도가 아닙니다.

묶음 머리(no=0)가 바탕에 있으면 새 회차에도 no=0 으로 씁니다. 출력은 지정한 JSON 스키마 하나뿐입니다."""

ROWS = {"type": "array", "items": {"type": "array", "items": {"type": ["string", "number", "boolean", "null"]}}}
FIELD = {"type": "object", "properties": {
    "name": {"type": "string"}, "type": {"type": "string"}, "size": {"type": ["integer", "null"]},
    "key": {"type": "boolean"}, "props": {"type": "object"}, "note": {"type": "string"}},
    "required": ["name", "type"]}
DB = {"type": "object", "properties": {
    "tables": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "fields": {"type": "array", "items": FIELD}, "rows": ROWS, "note": {"type": "string"}},
        "required": ["name", "fields", "rows"]}},
    "relationships": {"type": "array", "items": {"type": "object"}},
    "external": {"type": "array", "items": {"type": "object", "properties": {
        "file": {"type": "string"}, "sheet": {"type": "string"}, "columns": {"type": "array", "items": {"type": "string"}},
        "rows": ROWS, "note": {"type": "string"}}, "required": ["file", "columns", "rows"]}},
    "queries": {"type": "array", "items": {"type": "object"}}},
    "required": ["tables"]}
GIVEN = {"type": "object", "properties": {
    "forms": {"type": "array", "items": {"type": "object"}},
    "reports": {"type": "array", "items": {"type": "object"}},
    "queries": {"type": "array", "items": {"type": "object"}},
    "macros": {"type": "array", "items": {"type": "object"}}}}
ITEM = {
    "type": "object",
    "properties": {
        "no": {"type": "integer"},
        "points": {"type": ["integer", "null"]},
        "lead": {"type": "string"},
        "instructions": {"type": "array", "items": {"type": "string"}},
        "figures": {"type": "array", "items": pa.FIG},
        "boxes": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "code": {"type": "boolean"}, "text": {"type": "string"}},
            "required": ["id", "text"]}},
        "objects": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "object", "properties": {
            "title": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
            "result": {"type": "object", "properties": {
                "columns": {"type": "array", "items": {"type": "string"}}, "rows": ROWS}},
            "props": {"type": "array", "items": {"type": "object"}}},
            "required": ["title", "steps"]},
        "functions": {"type": "array", "items": {"type": "string"}},
        "changed": {"type": "string"},
    },
    "required": ["no", "lead", "instructions", "answer"],
}


def schema(part: int) -> dict:
    props: Dict[str, Any] = {"scenario": {"type": "string"}, "items": {"type": "array", "items": ITEM}}
    req = ["scenario", "items"]
    if part == 1:
        props["db"] = DB
        req.append("db")
    else:
        props["given"] = GIVEN
    return {"type": "object", "properties": props, "required": req}


def _prev_same_base(m: int, part: int) -> List[str]:
    out = []
    for k in range(1, m):
        if pa.source_round(k) != pa.source_round(m):
            continue
        f = os.path.join(round_dir(k), f"part{part}.json")
        if not os.path.isfile(f):
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        objs = sorted({x for it in d.get("items") or [] for x in it.get("objects") or []})[:8]
        out.append(f"{k:02d}회 — 업무 영역 「{(d.get('scenario') or '')[:40]}」" + (f" · 개체 {', '.join(objs)}" if objs else ""))
    return out


def used_scenarios() -> List[str]:
    out = []
    for f in glob.glob(os.path.join(out_root(), "m*", "part1.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                s = (json.load(fh).get("scenario") or "").strip()
            if s:
                out.append(s[:40])
        except (OSError, ValueError):
            pass
    # 같은 회차 1교시(엑셀)의 업무 영역과도 겹치지 않게
    for f in glob.glob(os.path.join(pa.out_root(), "m*", "part*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                s = (json.load(fh).get("scenario") or "").strip()
            if s:
                out.append(s[:30])
        except (OSError, ValueError):
            pass
    return out[-60:]


def _prompt(m: int, part: int, src: List[dict]) -> str:
    s = pa.source_round(m)
    strong = pa.is_strong(m)
    prev = _prev_same_base(m, part)
    blocks = []
    for d in src:
        tag = f"{d['part']}-{d['no']}" if d.get("no") else f"{d['part']}-머리"
        blocks.append(f"### 바탕 {s:02d}회 문제{tag}\n\n{d.get('_md') or ''}".strip())
    db = load_db(m)
    used = used_scenarios()
    head = (f"새 회차: {m:02d}회 2교시(액세스) · 문제{part} {part_names().get(part, '')}\n"
            f"바탕: 확정본 {s:02d}회 2교시 문제{part} (아래 {len(src)}개 항목)\n"
            f"변형 강도: {'강 — 기능·함수 조합·조건까지 바꿉니다' if strong else '중 — 기능 조합은 같게, 나머지 표면은 전부 새로'}\n")
    if part == 1:
        head += ("이 회차의 DB 를 지금 설계합니다(db). 문제2~4 가 이 DB 를 그대로 씁니다 — 폼·보고서·쿼리 문제가 나올 수 있게\n"
                 "바탕 회차 전체(문제2~4 포함)의 쓰임새를 생각해 테이블을 고르십시오.\n")
        if used:
            head += f"이미 쓴 업무 영역(겹치지 않게): {', '.join(used)}\n"
        # 바탕의 문제2~4 도 보여 준다 — DB 가 그 문제들을 받칠 수 있어야 한다
        later = []
        for p in (2, 3, 4):
            for d in source_items(s, p):
                if d.get("no"):
                    later.append(f"- 문제{p}-{d['no']}: {((d.get('problems') or [{}])[0].get('lead') or '')[:120]}")
        if later:
            head += "바탕의 문제2~4(참고 — 이번에 쓰지 않음):\n" + "\n".join(later) + "\n"
    else:
        if not db:
            raise FileNotFoundError(f"{m:02d}회 DB 설계(db.json)가 없습니다 — 문제1 을 먼저 쓰십시오.")
        head += ("이 회차의 DB(문제1 이 설계 — 이 테이블·필드·레코드만 쓰십시오):\n```json\n"
                 + json.dumps(db, ensure_ascii=False)[:24000] + "\n```\n")
        gv = []
        for p in range(2, part):
            f = os.path.join(round_dir(m), f"part{p}.json")
            if os.path.isfile(f):
                with open(f, encoding="utf-8") as fh:
                    g = json.load(fh).get("given") or {}
                names = [o.get("name") for k in ("forms", "reports", "queries", "macros") for o in g.get(k) or [] if o.get("name")]
                if names:
                    gv.append(f"문제{p} 가 둔 개체: {', '.join(names)}")
        if gv:
            head += "\n".join(gv) + " — 다시 쓰면 같은 설계를 이어 쓰십시오.\n"
    if prev:
        head += "같은 바탕을 먼저 쓴 회차(이것들과도 업무 영역 · 기능 조합이 달라야 합니다):\n" + "\n".join(f"  - {x}" for x in prev) + "\n"
    return (head + "\n바탕 그림 파일은 현재 폴더의 images/ 아래에 있습니다(필요할 때만 Read).\n\n"
            + "\n\n".join(blocks)
            + f"\n\n바탕과 같은 개수({len(src)}개)·같은 번호·같은 배점으로 새 항목을 쓰십시오.")


# ── 쓰기 ──────────────────────────────────────────────────────────────────
def item_md(m: int, part: int, it: dict) -> str:
    figs = {f.get("id"): f for f in it.get("figures") or []}
    boxes = {b.get("id"): b for b in it.get("boxes") or [] if b.get("id")}
    used: set = set()
    head = (f"# {m:02d}회 2교시 문제{part} (묶음 머리)" if not it.get("no")
            else f"# {m:02d}회 2교시 문제{part}-{it['no']}" + (f" ({it['points']}점)" if it.get("points") else ""))
    out = [head, "", f"**{it.get('lead') or ''}**", ""]
    out += pa._lines(it.get("instructions") or [], figs, used, {}, boxes) + [""]
    a = it.get("answer") or {}
    a_lines = pa._lines(a.get("steps") or [], figs, used, {}, boxes)
    for fid, f in figs.items():
        if fid not in used:
            out += pa._fig_md(f)
    for bid, b in boxes.items():
        if bid not in used:
            out += pa._box_md(b)
    out += ["## 정답 & 해설", ""]
    if a.get("title"):
        out += [f"**{a['title']}**", ""]
    out += a_lines
    r = a.get("result") or {}
    if r.get("columns"):
        out += ["", "*실행 결과*", ""] + pa._md_table(r["columns"], r.get("rows") or [])
    if a.get("props"):
        out += ["", "*정답 속성*", ""] + pa._md_table(
            ["개체", "컨트롤", "속성", "값"],
            [[p.get("object"), p.get("control"), p.get("property"), p.get("value")] for p in a["props"]])
    return "\n".join(out).rstrip() + "\n"


def write_part(m: int, part: int, got: dict, cost: float) -> List[str]:
    d = round_dir(m)
    os.makedirs(d, exist_ok=True)
    got = dict(got, round=m, part=part, session=SESSION, source_round=pa.source_round(m), _cost_usd=round(cost, 4))
    if part == 1 and got.get("db"):
        atomic_write_text(os.path.join(d, "db.json"),
                          json.dumps(dict(got["db"], round=m, scenario=got.get("scenario")), ensure_ascii=False, indent=2))
    atomic_write_text(os.path.join(d, f"part{part}.json"), json.dumps(got, ensure_ascii=False, indent=2))
    wrote = []
    for it in got.get("items") or []:
        stem = f"{m:02d}-{part}-{int(it.get('no') or 0):02d}"
        doc = {"round": m, "session": SESSION, "part": part, "no": it.get("no"), "source_round": pa.source_round(m),
               "scenario": got.get("scenario"), **it}
        atomic_write_text(os.path.join(d, stem + ".json"), json.dumps(doc, ensure_ascii=False, indent=2))
        atomic_write_text(os.path.join(d, stem + ".md"), item_md(m, part, it))
        wrote.append(stem)
    return wrote


def write_one(m: int, part: int, *, model: str = "", effort: Optional[str] = None, on_activity=None) -> dict:
    from services.authoring.provider import ClaudeAuthor
    src = source_items(pa.source_round(m), part)
    if not src:
        raise FileNotFoundError(f"확정본이 없습니다: {pa.source_round(m):02d}회 2교시 문제{part}")
    author = ClaudeAuthor(model=model, effort=effort, cwd=src_dir(), on_activity=on_activity,
                          max_turns=12, max_buffer_size=32 * 1024 * 1024)
    got = author.structured(system=SYSTEM, prompt=_prompt(m, part, src), schema=schema(part))
    want = sorted(int(d.get("no") or 0) for d in src)
    have = sorted(int(it.get("no") or 0) for it in got.get("items") or [])
    if want != have:
        raise ValueError(f"문항 번호가 바탕과 다릅니다 — 바탕 {want} · 받은 {have}")
    if part == 1 and not (got.get("db") or {}).get("tables"):
        raise ValueError("문제1 인데 DB 설계(db.tables)가 비었습니다.")
    wrote = write_part(m, part, got, author.last_cost_usd)
    return {"wrote": wrote, "scenario": got.get("scenario") or "", "cost_usd": author.last_cost_usd}


# ── 잡 ────────────────────────────────────────────────────────────────────
_LOCK = threading.Lock()
STALL_LIMIT = 3


def status(rounds: List[int]) -> List[dict]:
    rows = []
    for m in rounds:
        d = round_dir(m)
        rows.append({"round": m, "source_round": pa.source_round(m),
                     "parts": {p: part_done(m, p) for p in part_names()},
                     "items": len(glob.glob(os.path.join(d, f"{m:02d}-*.md"))), "db": load_db(m) is not None})
    return rows


def start(rounds: List[int], *, overwrite: bool = False, model: str = "", effort: Optional[str] = None) -> dict:
    from services.jobs import registry
    keys = [(m, p) for m in rounds for p in part_names() if overwrite or not part_done(m, p)]
    if not keys:
        raise ValueError("쓸 묶음이 없습니다 — 이미 다 썼습니다(다시 쓰기를 켜면 덮어씁니다).")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("이미 액세스 집필이 돌고 있습니다 — 동시에 하나만 실행됩니다.")
    job = registry.create("practical-author-access",
                          f"실기 집필(2교시 액세스) · {rounds[0]:02d}~{rounds[-1]:02d}회 ({len(keys)}묶음)",
                          [f"m{m:02d}-a{p}" for m, p in keys])

    def work(j: dict) -> None:
        try:
            _run(j, keys, model=model, effort=effort)
        finally:
            _LOCK.release()

    registry.spawn(job, work)
    return job


def _run(job: dict, keys, *, model: str, effort: Optional[str]) -> None:
    from services.jobs import registry
    cost, fails, bad_rounds = 0.0, 0, set()
    for m, p in keys:
        if job.get("cancel_requested"):
            registry.log(job, "[취소] 사람이 멈췄습니다 — 다시 누르면 남은 묶음부터 잇습니다.", force=True)
            break
        key = f"m{m:02d}-a{p}"
        if m in bad_rounds:                       # 문제1(DB) 이 실패한 회차는 뒤 묶음을 건너뛴다
            registry.item(job, key, status="error", error="이 회차의 DB 설계(문제1)가 없어 건너뜀")
            continue
        registry.item(job, key, status="running")
        job["current"] = f"{m:02d}회 2교시 문제{p} {part_names().get(p, '')}"
        registry.log(job, f"[집필] {m:02d}회 2교시 문제{p} — 바탕 {pa.source_round(m):02d}회", force=True)
        try:
            r = write_one(m, p, model=model, effort=effort,
                          on_activity=lambda s, _k=key: registry.log(job, f"  {_k} {s}"))
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            if p == 1:
                bad_rounds.add(m)
            registry.item(job, key, status="error", error=f"{type(e).__name__}: {e}")
            registry.log(job, f"[실패] {key} — {e}", force=True)
            if fails >= STALL_LIMIT:
                registry.log(job, f"[중단] {STALL_LIMIT}묶음 연속 실패 — 로그인·한도를 확인하세요.", force=True)
                registry.finish(job, "error", error=f"{fails}묶음 연속 실패")
                return
            continue
        fails = 0
        cost += r["cost_usd"] or 0.0
        job["done_count"] = job.get("done_count", 0) + 1
        registry.item(job, key, status="done", output=f"{len(r['wrote'])}문항 · {r['scenario'][:30]}")
        registry.log(job, f"  → {len(r['wrote'])}문항 · {r['scenario'][:40]} (${r['cost_usd']:.2f})", force=True)
    registry.log(job, f"[완료] {job.get('done_count', 0)}묶음 · ${cost:.2f}", force=True)
    registry.finish(job, "done", result={"parts": job.get("done_count", 0), "cost_usd": round(cost, 2)})
