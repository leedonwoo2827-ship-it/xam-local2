# -*- coding: utf-8 -*-
"""실기 문제 집필 — 확정본(01/practical) 을 바탕으로 **새 회차**를 쓴다.

  02/practical/m{NN}/{NN}-{P}-{NN}.md     사람이 읽는 원고(문제 · 정답 & 해설 · 그림 자리)
  02/practical/m{NN}/{NN}-{P}-{NN}.json   구조(시트 자료 · 지시사항 · 모범답안 · 그림 설계)
  02/practical/m{NN}/part{P}.json         묶음 하나를 쓴 원본 응답(이어하기 단위)

★ 필기 집필(services/authoring)과 **따로 둔다**(2026-11-09 지시: 실기는 탭을 분리). 필기는
  보기 ①~④ · 정답 번호를 쓰고, 실기는 시트 자료 · 작업 지시 · 모범답안(수식·대화상자 절차)을 쓴다.

★ 바탕 회차 = (m - 1) % 5 + 1. 원본 5회를 두 번씩 쓴다(m01~m05, m06~m10). 같은 바탕을 쓰는 두
  회차가 닮지 않게, 뒤 회차(m06~)는 함수 조합·조건까지 바꾼다.

★ 그림: 원본 그림은 출판사 저작물이라 **쓰지 않는다**(2026-11-09 지시: "새로 만들어야 합니다").
  집필은 그림마다 **그릴 수 있는 설계**(표라면 열·행 값, 차트라면 종류·계열·서식, 대화상자라면
  항목·값)를 남기고, 원고에는 그 자리에 표(가능하면) 또는 그림 자리 표시를 둔다. 실제 그림은
  다음 단계(엑셀로 파일을 만들고 캡처)에서 이 설계로 그린다.

묶음(문제1~4) 하나가 한 번의 호출이다 — 회차 10개 × 4 = 40번. 중간에 멈춰도 쓴 묶음은 남고,
다시 누르면 남은 묶음부터 잇는다.
"""
from __future__ import annotations

import glob
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_text
from services.book import paths

PART_NAME = {1: "기본작업", 2: "계산작업", 3: "분석작업", 4: "기타작업"}
N_SOURCE = 5


def src_dir() -> str:
    return os.path.join(paths.book_dir(), "01", "practical")


def out_root() -> str:
    return os.path.join(paths.book_dir(), "02", "practical")


def round_dir(m: int) -> str:
    return os.path.join(out_root(), f"m{m:02d}")


def source_round(m: int) -> int:
    return (int(m) - 1) % N_SOURCE + 1


def source_items(rnd: int, part: int) -> List[dict]:
    """확정본에서 그 회차 · 그 묶음의 문항(머리 포함) — 번호 순."""
    out = []
    for f in sorted(glob.glob(os.path.join(src_dir(), f"{rnd:02d}-{part}-*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        md = f[:-5] + ".md"
        d["_md"] = open(md, encoding="utf-8").read() if os.path.isfile(md) else ""
        out.append(d)
    return out


def sources_ready() -> Dict[int, int]:
    """확정본 회차별 문항 파일 수."""
    got: Dict[int, int] = {}
    for f in glob.glob(os.path.join(src_dir(), "*.json")):
        m = re.match(r"(\d{2})-\d-\d{2}\.json$", os.path.basename(f))
        if m:
            got[int(m.group(1))] = got.get(int(m.group(1)), 0) + 1
    return dict(sorted(got.items()))


# ── 지시 ──────────────────────────────────────────────────────────────────
SYSTEM = """당신은 컴퓨터활용능력 2급 실기(스프레드시트 실무, MS Office 2021 엑셀) 문제집의 집필자입니다.
출판사 기출 풀이집을 판독한 「바탕 문항」을 받아, **같은 출제 유형·같은 난이도의 새 문항**을 씁니다.
결과는 자사 모의고사 원고로 출판·배포됩니다. 저작권상 바탕의 표면을 옮겨 오면 안 됩니다.

[반드시 바꿀 것 — 표면 전부]
- 업무 영역(시나리오)과 시트 자료 전체: 표 제목, 열 이름, 행 데이터(이름·코드·날짜·수량·금액), 행 수
- 셀 주소 · 영역, 조건 값, 서식 값(글꼴·크기·색·표시 형식), 이름 정의 이름, 메모 문구, 필터·정렬 기준
- 문장 표현. 지시 순서도 자연스러운 범위에서 바꿔도 됩니다.
- 함수: 같은 회차 안의 뒤 회차(지시에 「변형 강도: 강」)는 같은 범주의 **다른 함수 조합**을 씁니다
  (예: INDEX+MATCH → VLOOKUP/HLOOKUP, SUMIF → SUMIFS/DSUM, IF+AND → IF+OR, ROUND → ROUNDUP/TRUNC 등).
  「변형 강도: 중」 이면 함수 조합은 같게 두되 인수·조건·영역을 모두 바꿉니다.

[유지할 것 — 시험 형식]
- 묶음 번호·문항 번호·배점, 문항이 다루는 엑셀 기능의 종류(데이터 입력 / 셀 서식 / 조건부 서식 / 고급 필터 /
  수식 / 부분합 / 피벗 테이블 / 시나리오 / 데이터 표 / 통합 / 정렬 / 매크로 / 차트 등)
- 시트 이름 규칙: '기본작업-1', '기본작업-2', '계산작업', '분석작업-1', '매크로작업', '차트작업' 처럼 시험 형식 그대로
- 지시문 문체(「~하시오.」), 원문자 ① ② … 세부 지시, ▶ 보조 지시, (각 N점)·(N점) 표기
- 컴활 2급 출제 범위 안의 함수·기능만 씁니다. 엑셀 2021 메뉴 이름을 씁니다([홈]-[스타일]-[셀 스타일] 등).

[정확해야 할 것]
- 시트 자료와 수식·결과가 **서로 맞아야** 합니다. 수식은 실제로 그 자료에 넣으면 의도한 결과가 나와야 하고,
  조건에 맞는 행이 0개가 되거나 전부가 되는 시시한 자료를 만들지 마십시오(필터·조건부 서식은 일부만 걸리게).
- 계산작업의 각 결과 칸은 자료에서 직접 계산한 값을 answer.results 에 적으십시오(셀 주소별). 반올림·표시 형식까지.
- 셀 주소는 sheets 의 표 배치(anchor·열 수·행 수)와 정확히 맞아야 합니다.
- ★ 주어진 표에서 **다른 칸으로 계산되는 칸**(금액 = 단가×수량, 합계, 적용요금, 순이익 등)은 값이 아니라
  「=D4*E4」·「=SUM(F4:F11)」 같은 **수식 문자열**로 rows 에 적으십시오. 특히 시나리오·데이터 표·목표값 찾기
  문항의 결과 셀은 반드시 변경 셀을 (직·간접) 참조하는 수식이어야 합니다 — 값만 있으면 결과가 바뀌지 않습니다.
  수험자가 직접 입력하는 칸(계산작업 답 칸 등)은 비워 둡니다.
- anchor 는 표 **머리글 행**입니다. 지시에 적는 범위(예: 피벗 원본 [B4:J17])의 첫 행이 머리글 행과 같아야 합니다.
- 표 제목을 특정 셀에 두어야 하면(예: 「차트 제목은 [B2] 셀과 연동」) title_cell 에 그 셀을 적습니다.
  제목에 「(제목은 [A1] 셀…)」 같은 메모를 섞지 마십시오. 원본 그림의 열 머리(A·B·C…)·행 번호는 자료가 아닙니다.
- 기본작업-1(「자료를 주어진 대로 입력하시오」)처럼 수험자가 **입력하는** 표에는 input 을 적습니다:
  "all"(빈 시트에 전부 입력) · "body"(제목만 미리 있음) · "data"(제목·머리글이 미리 있고 자료 행만 입력).
  문제 파일에는 그 부분이 비고, 정답 파일에만 들어갑니다.
- 「글꼴 색이 빨강인 행을 위로」 처럼 지시가 쓰는 서식(글꼴 색·채우기·굵게)은 표의 styles 에
  [{"range":"D4","font_color":"빨강"}] 처럼 적어 문제 파일에 들어가게 하십시오.
- 차트작업 문항은 given_chart 에 **지시 ①~⑤ 를 적용하기 전의 제공 차트**를 적습니다
  ({"range":"B3:C9","type":"묶은 세로 막대형","title":null}) — 바꿀 종류·추가/제거할 계열·바꿀 제목이 지시 전 상태여야
  수험자가 지시대로 고칠 수 있습니다(예: 「원형으로 변경」이면 원형이 아닌 형식, 「'7월' 계열 추가」면 7월이 빠진 범위).

[그림 — 새로 설계]
- 바탕의 그림(결과 화면·차트·대화상자)은 쓰지 않습니다. 대신 figures 에 **새로 그릴 설계**를 적습니다.
  · kind "table": 시트의 한 영역을 보여 주는 그림(입력할 자료, 결과 표, 부분합·피벗 결과) — columns·rows 에 실제 값
  · kind "chart": 차트 결과 — chart 에 종류·데이터 범위·계열·제목·축·범례·서식을 적습니다
  · kind "dialog": 대화상자·설정 화면 — desc 에 항목과 값을 적습니다
- 지문(instructions)이나 해설(steps) 안에서 그림이 놓일 자리에 그림 id 를 **한 줄로만** {{f-1}} 처럼 둡니다.
- 바탕에 그림이 있던 자리에는 같은 성격의 새 그림을 둡니다. 바탕 그림 파일이 필요하면 Read 로 열어 무엇을
  보여 주었는지만 확인하십시오(값·모양을 베끼지 마십시오).

[모범답안 — 바탕 해설의 형식을 따라]
- answer.title: 「① 셀 스타일 지정」 처럼 흰 원문자 + 짧은 제목
- answer.steps: 풀이 절차를 한 줄에 하나. 수식 문제는 「[D26] 셀에 =… 을 입력한다.」 + 함수 설명 줄들,
  서식·기능 문제는 메뉴 경로와 대화상자에서 고를 값. 필요한 그림은 {{f-N}} 줄로.
- answer.formulas: 수식 문제면 {cell, formula} (첫 결과 셀 기준, 채우기 범위가 있으면 fill 에 영역)

묶음 머리(no=0: 묶음 전체에 걸친 그림·표만 있는 항목)가 바탕에 있으면 새 회차에도 no=0 으로 씁니다.
출력은 지정한 JSON 스키마 하나뿐입니다."""

FIG = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "kind": {"type": "string", "enum": ["table", "chart", "dialog"]},
        "caption": {"type": "string"},
        "sheet": {"type": "string"},
        "anchor": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "rows": {"type": "array", "items": {"type": "array", "items": {"type": ["string", "number", "null"]}}},
        "chart": {"type": "object"},
        "desc": {"type": "string"},
    },
    "required": ["id", "kind", "caption"],
}
TABLE = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "anchor": {"type": "string"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "rows": {"type": "array", "items": {"type": "array", "items": {"type": ["string", "number", "null"]}}},
        "note": {"type": "string"},
        "title_cell": {"type": "string"},
        "input": {"type": "string", "enum": ["all", "body", "data"]},
        "styles": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["anchor", "columns", "rows"],
}
ITEM = {
    "type": "object",
    "properties": {
        "no": {"type": "integer"},
        "points": {"type": ["integer", "null"]},
        "sheet": {"type": "string"},
        "lead": {"type": "string"},
        "instructions": {"type": "array", "items": {"type": "string"}},
        "figures": {"type": "array", "items": FIG},
        "answer": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "formulas": {"type": "array", "items": {"type": "object"}},
                "results": {"type": "object"},
            },
            "required": ["title", "steps"],
        },
        "functions": {"type": "array", "items": {"type": "string"}},
        "given_chart": {"type": "object"},
        "changed": {"type": "string"},
    },
    "required": ["no", "lead", "instructions", "answer"],
}
SCHEMA = {
    "type": "object",
    "properties": {
        "scenario": {"type": "string"},
        "sheets": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"},
                           "tables": {"type": "array", "items": TABLE}},
            "required": ["name", "tables"]}},
        "items": {"type": "array", "items": ITEM},
    },
    "required": ["scenario", "sheets", "items"],
}


def _prompt(m: int, part: int, src: List[dict], used: List[str]) -> str:
    s = source_round(m)
    strong = m > N_SOURCE
    blocks = []
    for d in src:
        tag = f"{d['part']}-{d['no']}" if d.get("no") else f"{d['part']}-머리"
        blocks.append(f"### 바탕 {s:02d}회 문제{tag}\n\n{d.get('_md') or ''}".strip())
    return (
        f"새 회차: {m:02d}회 · 문제{part} {PART_NAME[part]}\n"
        f"바탕: 확정본 {s:02d}회 문제{part} (아래 {len(src)}개 항목)\n"
        f"변형 강도: {'강 — 함수 조합·조건·자료 구조까지 바꿉니다' if strong else '중 — 함수 조합은 같게, 나머지 표면은 전부 새로'}\n"
        + (f"다른 회차·묶음에서 이미 쓴 업무 영역(겹치지 않게): {', '.join(used)}\n" if used else "")
        + f"\n바탕 그림 파일은 현재 폴더의 images/ 아래에 있습니다(필요할 때만 Read).\n\n"
        + "\n\n".join(blocks)
        + f"\n\n바탕과 같은 개수({len(src)}개)·같은 번호·같은 배점으로 새 항목을 쓰십시오."
    )


# ── 쓰기 ──────────────────────────────────────────────────────────────────
TOK = re.compile(r"\{\{(f-\d+)\}\}")


def _md_table(cols: List[str], rows: List[list]) -> List[str]:
    if not cols:
        return []
    fmt = lambda v: "" if v is None else str(v).replace("|", "\\|").replace("\n", " ")
    out = ["| " + " | ".join(fmt(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for r in rows or []:
        r = list(r) + [""] * (len(cols) - len(r))
        out.append("| " + " | ".join(fmt(v) for v in r[:len(cols)]) + " |")
    return out


def _fig_md(f: dict, img: str = "") -> List[str]:
    cap = f.get("caption") or f.get("id")
    if img:                                     # 1부 빌드가 새로 그린 PNG 가 있으면 그것
        alt = str(cap).replace("[", "(").replace("]", ")")   # 「[H4:H15]」 같은 대괄호가 그림 줄을 깬다
        return [f"![{alt}]({img})", ""]
    if f.get("kind") == "table" and f.get("columns"):
        return [f"*〔그림 {f['id']}〕 {cap}*", ""] + _md_table(f["columns"], f.get("rows") or []) + [""]
    body = f.get("desc") or (json.dumps(f.get("chart"), ensure_ascii=False) if f.get("chart") else "")
    return [f"> 〔그림 {f['id']} · {'차트' if f.get('kind') == 'chart' else '대화상자'} — 새로 그릴 것〕 {cap}",
            *([f"> {body}"] if body else []), ""]


def _lines(lines: List[str], figs: Dict[str, dict], used: set, imgs: Optional[Dict[str, str]] = None) -> List[str]:
    out, under = [], False
    for raw in lines or []:
        s = str(raw).strip()
        m = TOK.fullmatch(s)
        if m:
            used.add(m.group(1))
            f = figs.get(m.group(1))
            out += [""] + (_fig_md(f, (imgs or {}).get(m.group(1), "")) if f else [f"({s} — 없는 그림)", ""])
            continue
        if s[:1] and "\u2460" <= s[0] <= "\u2473":
            under = True
        elif s and not s.startswith(("▶", "※")):
            under = False
        out.append(("&emsp;" if under and s.startswith(("▶", "※")) else "") + s + "  ")
    return out


def item_md(m: int, part: int, it: dict) -> str:
    figs = {f.get("id"): f for f in it.get("figures") or []}
    used: set = set()
    stem = f"{m:02d}-{part}-{int(it.get('no') or 0):02d}"
    imgs = {fid: f"images/{stem}-{fid}.png" for fid in figs
            if os.path.isfile(os.path.join(round_dir(m), "images", f"{stem}-{fid}.png"))}
    head = (f"# {m:02d}회 문제{part} (묶음 머리)" if not it.get("no")
            else f"# {m:02d}회 문제{part}-{it['no']}" + (f" ({it['points']}점)" if it.get("points") else ""))
    out = [head, "", f"**{it.get('lead') or ''}**", ""]
    out += _lines(it.get("instructions") or [], figs, used, imgs) + [""]
    a = it.get("answer") or {}
    a_lines = _lines(a.get("steps") or [], figs, used, imgs)
    for fid, f in figs.items():                 # 자리를 안 정한 그림은 지문 끝에
        if fid not in used:
            out += _fig_md(f, imgs.get(fid, ""))
    out += ["## 정답 & 해설", ""]
    if a.get("title"):
        out += [f"**{a['title']}**", ""]
    out += a_lines
    return "\n".join(out).rstrip() + "\n"


def write_part(m: int, part: int, got: dict, cost: float) -> List[str]:
    d = round_dir(m)
    os.makedirs(d, exist_ok=True)
    got = dict(got, round=m, part=part, source_round=source_round(m), _cost_usd=round(cost, 4))
    atomic_write_text(os.path.join(d, f"part{part}.json"), json.dumps(got, ensure_ascii=False, indent=2))
    wrote = []
    for it in got.get("items") or []:
        stem = f"{m:02d}-{part}-{int(it.get('no') or 0):02d}"
        doc = {"round": m, "part": part, "no": it.get("no"), "source_round": source_round(m),
               "scenario": got.get("scenario"), "sheets": got.get("sheets"), **it}
        atomic_write_text(os.path.join(d, stem + ".json"), json.dumps(doc, ensure_ascii=False, indent=2))
        atomic_write_text(os.path.join(d, stem + ".md"), item_md(m, part, it))
        wrote.append(stem)
    return wrote


def part_done(m: int, part: int) -> bool:
    return os.path.isfile(os.path.join(round_dir(m), f"part{part}.json"))


def used_scenarios() -> List[str]:
    out = []
    for f in glob.glob(os.path.join(out_root(), "m*", "part*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                s = (json.load(fh).get("scenario") or "").strip()
            if s:
                out.append(s[:40])
        except (OSError, ValueError):
            pass
    return out[-40:]


def write_one(m: int, part: int, *, model: str = "", effort: Optional[str] = None,
              on_activity=None) -> dict:
    from services.authoring.provider import ClaudeAuthor
    src = source_items(source_round(m), part)
    if not src:
        raise FileNotFoundError(f"확정본이 없습니다: {source_round(m):02d}회 문제{part}")
    author = ClaudeAuthor(model=model, effort=effort, cwd=src_dir(), on_activity=on_activity,
                          max_turns=12, max_buffer_size=32 * 1024 * 1024)
    got = author.structured(system=SYSTEM, prompt=_prompt(m, part, src, used_scenarios()), schema=SCHEMA)
    want = sorted(int(d.get("no") or 0) for d in src)
    have = sorted(int(it.get("no") or 0) for it in got.get("items") or [])
    if want != have:
        raise ValueError(f"문항 번호가 바탕과 다릅니다 — 바탕 {want} · 받은 {have}")
    wrote = write_part(m, part, got, author.last_cost_usd)
    return {"wrote": wrote, "scenario": got.get("scenario") or "", "cost_usd": author.last_cost_usd}


# ── 문항 교정 — 02/practical 문항 하나를 사람이 고친다 ─────────────────────
STEM_RE = re.compile(r"(\d{2})-(\d)-(\d{2})")
EDITABLE = ("points", "sheet", "lead", "instructions", "figures", "answer", "functions", "given_chart")


def list_items(rounds: Optional[List[int]] = None) -> List[dict]:
    rows = []
    for d in sorted(glob.glob(os.path.join(out_root(), "m[0-9][0-9]"))):
        m = int(os.path.basename(d)[1:])
        if rounds and m not in rounds:
            continue
        for f in sorted(glob.glob(os.path.join(d, f"{m:02d}-[0-9]-[0-9][0-9].json"))):
            stem = os.path.basename(f)[:-5]
            try:
                with open(f, encoding="utf-8") as fh:
                    j = json.load(fh)
            except (OSError, ValueError) as e:
                rows.append({"id": stem, "error": str(e)})
                continue
            rows.append({"id": stem, "round": m, "part": j.get("part"), "no": j.get("no"),
                         "points": j.get("points"), "reviewed": bool(j.get("reviewed")),
                         "figures": len(j.get("figures") or []), "scenario": (j.get("scenario") or "")[:60],
                         "functions": j.get("functions") or [], "preview": (j.get("lead") or "")[:160]})
    return rows


def _paths(stem: str) -> tuple:
    mt = STEM_RE.fullmatch(stem or "")
    if not mt:
        raise ValueError("문항 id 는 NN-P-NN 입니다.")
    m, p, n = int(mt.group(1)), int(mt.group(2)), int(mt.group(3))
    return m, p, n, os.path.join(round_dir(m), stem)


def read_item(stem: str) -> dict:
    m, p, n, base = _paths(stem)
    if not os.path.isfile(base + ".json"):
        raise FileNotFoundError("아직 쓰지 않은 문항입니다.")
    with open(base + ".json", encoding="utf-8") as fh:
        j = json.load(fh)
    md = open(base + ".md", encoding="utf-8").read() if os.path.isfile(base + ".md") else ""
    return {"id": stem, "json": j, "md": md, "path": base + ".md"}


def save_item(stem: str, patch: dict) -> dict:
    """고친 칸만 받아 문항 파일 · 묶음 원본(part{P}.json) · MD 를 함께 다시 쓴다.
    sheets(묶음 공용 시트 자료)를 받으면 그 묶음의 모든 문항 파일에 같이 넣는다."""
    m, p, n, base = _paths(stem)
    cur = read_item(stem)["json"]
    for k in EDITABLE:
        if k in patch:
            cur[k] = patch[k]
    if "reviewed" in patch:
        cur["reviewed"] = bool(patch["reviewed"])
    pj = os.path.join(round_dir(m), f"part{p}.json")
    part = {}
    if os.path.isfile(pj):
        with open(pj, encoding="utf-8") as fh:
            part = json.load(fh)
    if "sheets" in patch:
        part["sheets"] = patch["sheets"]
    for it in part.get("items") or []:
        if int(it.get("no") or 0) == n:
            for k in EDITABLE:
                if k in cur:
                    it[k] = cur[k]
            it["reviewed"] = cur.get("reviewed", False)
    if part:
        atomic_write_text(pj, json.dumps(part, ensure_ascii=False, indent=2))
    if "sheets" in patch:                       # 같은 묶음의 다른 문항 파일에도
        for f in glob.glob(os.path.join(round_dir(m), f"{m:02d}-{p}-[0-9][0-9].json")):
            with open(f, encoding="utf-8") as fh:
                o = json.load(fh)
            o["sheets"] = patch["sheets"]
            atomic_write_text(f, json.dumps(o, ensure_ascii=False, indent=2))
        cur["sheets"] = patch["sheets"]
    atomic_write_text(base + ".json", json.dumps(cur, ensure_ascii=False, indent=2))
    atomic_write_text(base + ".md", item_md(m, p, cur))
    return read_item(stem)


# ── 잡 ────────────────────────────────────────────────────────────────────
_LOCK = threading.Lock()
STALL_LIMIT = 3


def status(rounds: List[int]) -> List[dict]:
    rows = []
    for m in rounds:
        d = round_dir(m)
        parts = {p: part_done(m, p) for p in PART_NAME}
        stems = sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(d, f"{m:02d}-*.md")))
        n = len(stems)
        cost = 0.0
        for p in PART_NAME:
            f = os.path.join(d, f"part{p}.json")
            if os.path.isfile(f):
                try:
                    with open(f, encoding="utf-8") as fh:
                        cost += json.load(fh).get("_cost_usd") or 0
                except (OSError, ValueError):
                    pass
        rows.append({"round": m, "source_round": source_round(m), "parts": parts,
                     "items": n, "stems": stems, "cost_usd": round(cost, 2)})
    return rows


def start(rounds: List[int], *, overwrite: bool = False, model: str = "",
          effort: Optional[str] = None) -> dict:
    from services.jobs import registry
    keys = [(m, p) for m in rounds for p in PART_NAME if overwrite or not part_done(m, p)]
    if not keys:
        raise ValueError("쓸 묶음이 없습니다 — 이미 다 썼습니다(다시 쓰기를 켜면 덮어씁니다).")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("이미 실기 집필이 돌고 있습니다 — 동시에 하나만 실행됩니다.")
    job = registry.create("practical-author",
                          f"실기 집필 · {rounds[0]:02d}~{rounds[-1]:02d}회 ({len(keys)}묶음)",
                          [f"m{m:02d}-{p}" for m, p in keys])

    def work(j: dict) -> None:
        try:
            _run(j, keys, model=model, effort=effort)
        finally:
            _LOCK.release()

    registry.spawn(job, work)
    return job


def _run(job: dict, keys, *, model: str, effort: Optional[str]) -> None:
    from services.jobs import registry
    cost, fails = 0.0, 0
    for m, p in keys:
        if job.get("cancel_requested"):
            registry.log(job, "[취소] 사람이 멈췄습니다 — 다시 누르면 남은 묶음부터 잇습니다.", force=True)
            break
        key = f"m{m:02d}-{p}"
        registry.item(job, key, status="running")
        job["current"] = f"{m:02d}회 문제{p} {PART_NAME[p]}"
        registry.log(job, f"[집필] {m:02d}회 문제{p} {PART_NAME[p]} — 바탕 {source_round(m):02d}회", force=True)
        try:
            r = write_one(m, p, model=model, effort=effort,
                          on_activity=lambda s, _k=key: registry.log(job, f"  {_k} {s}"))
        except Exception as e:                                   # noqa: BLE001
            fails += 1
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
