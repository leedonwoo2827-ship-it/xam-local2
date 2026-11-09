# -*- coding: utf-8 -*-
"""종합본 영상 입력(실기) — 모범답안을 **녹화 가능한 조작 단계**로 뽑아 녹화 허브용 lesson.yaml 로 쓴다.

  07/mNN/rec/{NN}-{P}-{NN}.actions.json   조작 단계(구조) — 이 앱의 진실
  07/mNN/rec/{NN}-{P}-{NN}.lesson.yaml    IT-product-hub(261027) 의 lesson.yaml 모양에 맞춘 것

★ 종합본 영상 재정립(사용자 2026-11-09): longform 대시보드(261001) + 생산 허브의 데스크톱 녹화(261027).
  허브 녹화기는 pywinauto 로 앱을 직접 조작하며 단계마다 표시(marks)를 남긴다 — SQLD(DBeaver)에서 검증됐고
  엑셀 프로필은 아직 없다(허브 쪽 작업). 이 모듈은 **허브가 먹을 입력**만 만든다:
    steps[]{action, sheet, target, value|formula, menu_path[], accel, dialog{title, fields, ok}, say[], expected}
  action ∈ select · type_value · formula · fill · menu · dialog · key · format
★ 문항마다 Claude 한 번(구조화). 모범답안 절차를 **바꾸지 않고** 조작 단위로 쪼갠다 — 새 사실을 만들지 않는다.
"""
from __future__ import annotations

import glob
import json
import os
import threading
from typing import List, Optional

from core.atomic_io import atomic_write_text
from services.practical import author as pa

SYSTEM = """당신은 엑셀 실기 풀이 영상의 녹화 대본 작성자입니다. 주어진 문항의 모범답안 절차를 **녹화 프로그램이
그대로 따라 할 수 있는 조작 단계**로 쪼갭니다. 녹화 프로그램은 엑셀(Microsoft Office 2021 한국어판)을
자동으로 조작하며, 단계마다 화면을 녹화하고 내레이션(say)을 입힙니다.

규칙
- 모범답안 절차와 같은 결과가 나와야 합니다. 절차에 없는 작업을 더하지 마십시오. 순서를 바꾸지 마십시오.
- action 은 다음 중 하나입니다.
  · select      : 셀/영역 선택 — target 에 "A1" 또는 "A1:C5" (여러 영역은 "A4:A6,A7:A9")
  · type_value  : 선택한 셀에 값 입력 — value
  · formula     : 수식 입력 — target 셀, formula("=…"). 입력 후 Enter 까지 포함
  · fill        : 채우기(복사) — target 원본 셀, value 에 채울 영역
  · menu        : 리본 메뉴 — menu_path 에 한국어 리본 이름 순서(["홈","스타일","조건부 서식","새 규칙"]),
                  accel 에 Alt 키 순서(알면, 예 "Alt,H,L,N")
  · dialog      : 대화상자 설정 — dialog{title, fields{항목 이름: 값}, ok:"확인"}
  · key         : 바로 가기 키 — value 에 "Ctrl+1" 같은 키
  · format      : 셀 서식 대화상자 없이 끝나는 서식(리본 단추 하나) — menu_path 와 value
- sheet: 그 단계가 일어나는 시트 이름(문항의 시트).
- say: 그 단계에서 말할 내레이션 1~2문장(존댓말 「~합니다」). 셀 주소는 화면에 보이므로 말해도 되지만,
  **왜 그렇게 하는지**를 한마디 곁들입니다. 수식은 뜻으로 풀어 말합니다.
- expected: 그 단계 뒤 확인할 값이 있으면 {셀: 값}(모범답안 결과값에 있는 것만). 없으면 생략.
- 단계 수는 보통 3~15개. 너무 잘게(키 하나씩) 쪼개지 말고, 녹화에서 한 장면이 되는 단위로.
출력은 지정한 JSON 스키마 하나뿐입니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "intro_say": {"type": "string"},
        "steps": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["select", "type_value", "formula", "fill", "menu", "dialog", "key", "format"]},
                "sheet": {"type": "string"},
                "target": {"type": "string"},
                "value": {"type": "string"},
                "formula": {"type": "string"},
                "menu_path": {"type": "array", "items": {"type": "string"}},
                "accel": {"type": "string"},
                "dialog": {"type": "object"},
                "say": {"type": "array", "items": {"type": "string"}},
                "expected": {"type": "object"},
            },
            "required": ["action", "say"]}},
        "outro_say": {"type": "string"},
    },
    "required": ["steps"],
}


def rec_dir(m: int) -> str:
    from services.practical.ebook import out_dir
    return os.path.join(out_dir(m), "rec")


def _prompt(j: dict) -> str:
    a = j.get("answer") or {}
    return json.dumps({
        "문항": f"{int(j['round']):02d}회 문제{j['part']}-{j['no']}", "시트": j.get("sheet"),
        "발문": j.get("lead"), "지시사항": j.get("instructions"),
        "모범답안_제목": a.get("title"), "모범답안_절차": a.get("steps"),
        "수식": a.get("formulas"), "결과값": a.get("results"),
    }, ensure_ascii=False, indent=1)


def lesson_yaml(j: dict, got: dict) -> str:
    """허브 lesson.yaml 모양 — opening · blocks(단계) · summary. 엑셀 단계는 blocks[].steps 로 싣는다."""
    import yaml
    a = j.get("answer") or {}
    stem = f"{int(j['round']):02d}-{int(j['part'])}-{int(j['no']):02d}"
    doc = {
        "id": f"C2-{stem}", "slug": f"m{int(j['round']):02d}-{j['part']}-{int(j['no']):02d}",
        "title": f"모의 {int(j['round'])}회 문제{j['part']}-{j['no']} · {a.get('title') or ''}",
        "app": "excel", "workbook": f"m{int(j['round']):02d}_문제.xlsx", "sheet": j.get("sheet"),
        "opening": {"title": j.get("lead"), "say": got.get("intro_say") or j.get("lead")},
        "blocks": [{"num": i + 1, "title": (s.get("say") or [""])[0][:40], **{k: v for k, v in s.items() if v not in (None, "", [], {})}}
                   for i, s in enumerate(got.get("steps") or [])],
        "summary": {"say": got.get("outro_say") or ""},
    }
    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=120)


def write_one(m: int, stem: str, *, model: str = "", effort: Optional[str] = None, on_activity=None) -> dict:
    from services.authoring.provider import ClaudeAuthor
    import tempfile
    j = pa.read_item(stem)["json"]
    author = ClaudeAuthor(model=model, effort=effort, cwd=tempfile.mkdtemp(prefix="rec-"),
                          on_activity=on_activity, max_turns=4)
    got = author.structured(system=SYSTEM, prompt="다음 문항의 모범답안을 녹화 조작 단계로 쪼개십시오.\n\n" + _prompt(j),
                            schema=SCHEMA)
    d = rec_dir(m)
    os.makedirs(d, exist_ok=True)
    got["_cost_usd"] = round(author.last_cost_usd, 4)
    atomic_write_text(os.path.join(d, f"{stem}.actions.json"), json.dumps(got, ensure_ascii=False, indent=1))
    atomic_write_text(os.path.join(d, f"{stem}.lesson.yaml"), lesson_yaml(j, got))
    return {"steps": len(got.get("steps") or []), "cost_usd": author.last_cost_usd}


_LOCK = threading.Lock()


def start(rounds: List[int], overwrite: bool = False) -> dict:
    from services.jobs import registry
    keys = []
    for m in rounds:
        for f in sorted(glob.glob(os.path.join(pa.round_dir(m), f"{m:02d}-[0-9]-[0-9][0-9].json"))):
            stem = os.path.basename(f)[:-5]
            if stem.endswith("-00"):
                continue
            if overwrite or not os.path.isfile(os.path.join(rec_dir(m), f"{stem}.actions.json")):
                keys.append((m, stem))
    if not keys:
        raise ValueError("뽑을 문항이 없습니다 — 이미 다 뽑았거나 집필 결과가 없습니다.")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("이미 녹화 대본 뽑기가 돌고 있습니다.")
    job = registry.create("practical-actions", f"녹화 대본 · {len(keys)}문항", [s for _, s in keys])

    def work(jb: dict) -> None:
        cost, fails = 0.0, 0
        try:
            for m, stem in keys:
                if jb.get("cancel_requested"):
                    registry.log(jb, "[취소] 사람이 멈췄습니다 — 다시 누르면 남은 문항부터.", force=True)
                    break
                registry.item(jb, stem, status="running")
                jb["current"] = stem
                try:
                    r = write_one(m, stem, on_activity=lambda s, _k=stem: registry.log(jb, f"  {_k} {s}"))
                except Exception as e:                  # noqa: BLE001
                    fails += 1
                    registry.item(jb, stem, status="error", error=str(e))
                    registry.log(jb, f"[실패] {stem} — {e}", force=True)
                    if fails >= 3:
                        registry.finish(jb, "error", error="3문항 연속 실패")
                        return
                    continue
                fails = 0
                cost += r["cost_usd"] or 0
                jb["done_count"] = jb.get("done_count", 0) + 1
                registry.item(jb, stem, status="done", output=f"{r['steps']}단계")
                registry.log(jb, f"[녹화 대본] {stem} → {r['steps']}단계 (${r['cost_usd']:.2f})", force=True)
            registry.log(jb, f"[완료] ${cost:.2f}", force=True)
            registry.finish(jb, "done")
        finally:
            _LOCK.release()

    registry.spawn(job, work)
    return job
