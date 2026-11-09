# -*- coding: utf-8 -*-
"""실기 판독 — 스캔 PNG 한 장을 읽어 `data/practical/read/<src>_pNNN.json` 을 쓴다.

  00/*.pdf ──[스캔 뜨기: services/ocr/pdfrender]──▶ data/raw_pages/<src>/page_NNN.png
                                   └──[실기 판독: 여기]──▶ data/practical/read/<src>_pNNN.json

★ 한 장이 **문제 쪽인지 정답·해설 쪽인지도 모델이 적는다.** 처음엔 회차 표지(검은 띠)를
  픽셀로 찾아 쪽을 나누려 했지만, 실측(컴활2급 5회분 62쪽)에서 표지 7곳만 잡히고
  01회 표지 두 곳과 05회 문제 표지가 흐려 빠졌다. 사람이 고칠 표(③)를 두고, 처음
  값은 판독이 낸다.

★ 필기 판독(services/ocr/readpage)과 같은 원칙 — 모델은 파일을 쓰지 않고, 확실하지
  않은 것을 지어내지 않으며, 쪽을 걸친 문항은 시작한 쪽이 갖는다.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Callable, Dict, Optional

from core.atomic_io import atomic_write_text
from services.authoring.provider import ClaudeAuthor
from services.ocr import project

KINDS = ("문제", "정답", "기타")

SYSTEM = """당신은 컴퓨터활용능력 **실기** 문제집 스캔 페이지를 판독합니다.

실기 문제는 보기를 고르는 문제가 아닙니다. 수험자가 엑셀·액세스 파일에서 **작업**을 하고,
정답은 수식·대화상자 설정값·VBA 코드·작업 절차입니다.

주어진 PNG 를 Read 로 읽고, 먼저 이 쪽이 어떤 쪽인지 정한 뒤 그에 맞게 담습니다.

■ 쪽 종류(`page_kind`)
- `문제`  : 「문제 1 기본작업(20점)」처럼 문제 묶음과 번호 붙은 지시사항이 있는 쪽.
            시험지 표지(유의사항·암호·프로그램명)도 `문제` 로 둔다 — 문항은 없어도 된다.
- `정답`  : 「정답 & 해설」 쪽. 결과 화면 캡처, 수식, 대화상자 캡처, 풀이 절차가 있는 쪽.
- `기타`  : 위 둘이 아닌 쪽(목차·광고·빈 쪽).

■ 회차(`round`)
- 쪽에 「상시 공략 문제 03회」「정답 & 해설 | 03회」처럼 **회차가 인쇄돼 있을 때만** 숫자로 적는다.
- 인쇄돼 있지 않으면 null. 앞 쪽에서 이어받는 것은 앱이 한다 — 추측하지 않는다.

■ `문제` 쪽 → `problem_items`
문항 하나 = 번호 붙은 지시 하나(「1. '기본작업-1' 시트에 다음의 자료를 입력하시오.(5점)」).
- `part` / `part_name` / `part_points`: 속한 묶음(문제 1 / 기본작업 / 20). 쪽 위에 묶음 머리가
  없으면 앞에서 이어진 묶음 번호를 적고 `part_name` 은 비워도 된다.
- `no`: 묶음 안의 번호(1, 2, 3…). `lead`: 번호 줄의 문장 그대로. `points`: 배점(없으면 null).
- `sheet`: 작업할 시트 이름(인쇄돼 있을 때). 액세스면 테이블·폼·쿼리 이름.
- `instructions`: 세부 지시를 **한 줄에 하나씩, 인쇄된 그대로 — 줄머리 기호까지.**
  `①` `②` … 로 시작하면 `① [A1:G1] 영역은 …` 처럼 원문자를 그대로 두고, `▶` 로 시작하면
  `▶ [표시 예] : 8500 → 8,500L` 처럼 ▶ 를 그대로 둔다. 기호가 없는 줄은 기호 없이 둔다.
  ★ 기호를 바꾸거나 통일하지 않는다 — 원문자 항목 아래 딸린 ▶ 줄이 있어서 기호가 곧 위계다
    (실측 2급 01회 기본작업-2: ①~⑤ 지시 아래 ③ 에만 「▶ [표시 예]」 가 딸렸다).
- `functions`: 「AND, YEAR 함수 사용」처럼 **지정된 함수·연산자**만. 없으면 빈 배열.
- `ranges`: 지시에 나온 셀·영역 주소(`B3:B40`, `A30`) 그대로.
- `figure`: 결과 그림·입력 자료 표가 있으면 무엇인지 한 줄로(예: "입력할 자료 표 6행×6열",
  "피벗 테이블 결과 그림"). 표 자료는 `figure_table` 에 마크다운 표로 옮긴다(셀 안 `|` 는 `\\|`).
- `figures`: 이 문항에 딸린 **그림(표 캡처 · 결과 그림 · 차트)을 인쇄된 순서대로 모두**,
  각각 `{"bbox": [x, y, w, h], "note": "무엇인지"}` 로. bbox 는 페이지 PNG 의 **픽셀 좌표**(왼쪽 위 0,0)이고
  그림의 테두리를 넉넉히 감싼다. 좌표를 정할 수 없으면 bbox 를 빼고 note 만 둔다 — 사람이 영역을 지정한다.
- **그림의 자리 — 이름표:** `figures` 의 첫째는 `{{p-1}}`, 둘째는 `{{p-2}}` … 다. `instructions` 에서
  그 그림이 **인쇄된 자리에 이름표 한 줄**을 넣는다(그림 앞 줄과 뒤 줄 사이). 맨 끝에 있어도 넣는다.
  자료 표를 `figure_table` 로 옮겼으면 그 자리에는 `{{t-1}}` 을 넣는다(같은 표의 그림 이름표와 겹치지 않게
  둘 중 하나만 — 책처럼 보이려면 그림 `{{p-N}}` 을 쓴다).
- `spans_next`: 이 문항이 다음 쪽으로 이어지면 true — 다음 쪽의 나머지 지시까지 여기서 완성한다.
- 이 쪽의 **첫 문항이 앞 쪽에서 이어져 온 것이면 담지 않는다.** `notes` 에만 적는다.

■ `정답` 쪽 → `answer_entries`
정답·해설 하나 = 문제 번호 하나(「문제2 계산작업 01. 변경ID(B3)」).
- `part` / `no` / `title`: 어느 문항의 정답인지. `title` 은 번호 줄 **그대로, 번호 기호까지**
  (예: `❶ 자료 입력`, `① 변경ID(B3)`).
- `kind`: `수식` · `설정` · `코드` · `절차` · `그림` 중 정답의 주된 모양.
- `formulas`: 수식이 인쇄돼 있으면 `{"cell": "B3", "formula": "=IF(…)"}`. 배열 수식의 `{ }` 는
  그대로 둔다. **문자 하나 틀리지 않게** 옮긴다 — 이것이 정답이다.
- `settings`: 대화상자 캡처에서 **강조(굵은 상자)된 값**을 `{"dialog": "고급 필터",
  "field": "목록 범위", "value": "$A$3:$H$28"}` 로. 강조가 없어도 정답으로 보이는 입력값은 담는다.
- `code`: VBA·매크로 코드 본문(들여쓰기 유지).
- `steps`: 해설 문장을 **한 줄에 하나씩, 인쇄된 그대로 — 줄머리 기호(①②…, ▶)까지.** 요약하지 않는다.
  기호가 없는 줄은 기호 없이 둔다. 앱이 번호를 붙이지 않으므로 인쇄된 번호만 남는다.
- `figures`: 이 정답에 딸린 **캡처(결과 화면 · 대화상자 · 차트)를 인쇄된 순서대로 모두**,
  `{"bbox": [x, y, w, h], "note": "무엇인지"}` 로. 「정답」 표시가 붙은 결과 화면도 그림이다.
- **그림의 자리 — 이름표:** 첫째 그림은 `{{p-1}}`, 둘째는 `{{p-2}}` … `steps` 에서 그 그림이 **인쇄된
  자리에 이름표 한 줄**을 넣는다. 예: 결과 화면이 맨 위, 그 아래 설명 한 줄이면
  `["{{p-1}}", "[A3:F9] 셀까지 문제를 보고 오타 없이 작성한다."]`. 그림 사이사이 단계가 있으면
  `["② 1행 머리글에서 …", "{{p-2}}", "③ [A4:A5], … 클릭한다."]` 처럼 끼운다.

■ 지어내지 않는다
- 인쇄돼 있지 않은 배점·함수·정답을 채우지 않는다. 빈 칸이 오답보다 낫다 — 사람이 검수한다.
- 읽을 수 없는 글자는 `?` 로 두고 `note` 에 적는다. 오식으로 보여도 고치지 않고 `note` 에 적는다.
"""

ITEM = {
    "type": "object",
    "properties": {
        "part": {"type": ["integer", "null"]},
        "part_name": {"type": "string"},
        "part_points": {"type": ["integer", "null"]},
        "no": {"type": "integer"},
        "lead": {"type": "string"},
        "points": {"type": ["integer", "null"]},
        "sheet": {"type": "string"},
        "instructions": {"type": "array", "items": {"type": "string"}},
        "functions": {"type": "array", "items": {"type": "string"}},
        "ranges": {"type": "array", "items": {"type": "string"}},
        "figure": {"type": "string"},
        "figure_table": {"type": "string"},
        "figures": {"type": "array", "items": {
            "type": "object",
            "properties": {"bbox": {"type": "array", "items": {"type": "integer"}},
                           "note": {"type": "string"}}}},
        "spans_next": {"type": "boolean"},
        "note": {"type": "string"},
    },
    "required": ["no", "lead", "instructions"],
}

ENTRY = {
    "type": "object",
    "properties": {
        "part": {"type": ["integer", "null"]},
        "no": {"type": ["integer", "null"]},
        "title": {"type": "string"},
        "kind": {"type": "string", "enum": ["수식", "설정", "코드", "절차", "그림"]},
        "formulas": {"type": "array", "items": {
            "type": "object",
            "properties": {"cell": {"type": "string"}, "formula": {"type": "string"}},
            "required": ["formula"]}},
        "settings": {"type": "array", "items": {
            "type": "object",
            "properties": {"dialog": {"type": "string"}, "field": {"type": "string"},
                           "value": {"type": "string"}},
            "required": ["value"]}},
        "code": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
        "figures": {"type": "array", "items": {
            "type": "object",
            "properties": {"bbox": {"type": "array", "items": {"type": "integer"}},
                           "note": {"type": "string"}}}},
        "note": {"type": "string"},
    },
    "required": ["title", "kind"],
}

SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "page_kind": {"type": "string", "enum": list(KINDS)},
        "round": {"type": ["integer", "null"]},
        "round_label": {"type": "string"},
        "problem_items": {"type": "array", "items": ITEM},
        "answer_entries": {"type": "array", "items": ENTRY},
        "notes": {"type": "string"},
    },
    "required": ["page_kind", "problem_items", "answer_entries"],
}


# ── 저장 위치 ────────────────────────────────────────────────────────────────
def base_dir() -> str:
    return os.path.join(project.ocr_dir(), "data", "practical")


def read_path(src: str, page: int) -> str:
    return os.path.join(base_dir(), "read", f"{src}_p{int(page):03d}.json")


def pagemap_path() -> str:
    return os.path.join(base_dir(), "pagemap.json")


def load(src: str, page: int) -> Optional[dict]:
    p = read_path(src, page)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def save(src: str, page: int, d: dict) -> str:
    p = read_path(src, page)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    atomic_write_text(p, json.dumps(d, ensure_ascii=False, indent=2))
    return p


def remove(src: str, page: int) -> bool:
    """이 쪽 판독 결과를 지운다 — 다시 판독하려는 것이다. 확정본(01/practical)은 그대로 둔다."""
    p = read_path(src, page)
    if os.path.isfile(p):
        os.remove(p)
        return True
    return False


def load_pagemap() -> dict:
    """사람이 고친 쪽 종류·회차. `{src: {"7": {"kind": "정답", "round": 1}}}`"""
    p = pagemap_path()
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def set_pagemap(src: str, page: int, *, kind: Optional[str], round_: Optional[int]) -> dict:
    d = load_pagemap()
    ent = d.setdefault(src, {}).setdefault(str(int(page)), {})
    if kind is not None:
        if kind not in KINDS:
            raise ValueError(f"쪽 종류는 {', '.join(KINDS)} 중 하나입니다.")
        ent["kind"] = kind
    if round_ is not None:
        ent["round"] = int(round_) if int(round_) > 0 else None
    os.makedirs(base_dir(), exist_ok=True)
    atomic_write_text(pagemap_path(), json.dumps(d, ensure_ascii=False, indent=2))
    return ent


def page_table(src: str) -> list[dict]:
    """쪽마다 종류·회차를 정한다 — 사람이 고친 값 > 판독이 본 값 > 앞 쪽에서 이어받기.

    회차는 표지 쪽에만 인쇄돼 있어 대부분의 쪽이 null 이다. 앞 쪽의 회차를 이어받는다.
    """
    pm = load_pagemap().get(src, {})
    out, cur_round = [], None
    for page in project.list_pages(src):
        d = load(src, page)
        man = pm.get(str(page), {})
        kind = man.get("kind") or (d or {}).get("page_kind") or ""
        seen = (d or {}).get("round")
        if "round" in man and man["round"]:
            rnd, how = man["round"], "사람"
        elif seen:
            rnd, how = seen, "인쇄"
        elif cur_round:
            rnd, how = cur_round, "이어받음"
        else:
            rnd, how = None, ""
        if rnd:
            cur_round = rnd
        out.append({
            "src": src, "page": page, "read": d is not None,
            "kind": kind, "kind_by": "사람" if man.get("kind") else ("판독" if d else ""),
            "round": rnd, "round_by": how,
            "n_items": len((d or {}).get("problem_items") or []),
            "n_answers": len((d or {}).get("answer_entries") or []),
            # 필기 현황판처럼 칸 색을 대조완료로 칠한다
            "n_verified": sum(1 for x in ((d or {}).get("problem_items") or [])
                              + ((d or {}).get("answer_entries") or []) if x.get("verified")),
            "notes": (d or {}).get("notes") or "",
            "cost_usd": (d or {}).get("_cost_usd"),
        })
    return out


# ── 판독 한 장 ───────────────────────────────────────────────────────────────
def read_one(src: str, page: int, *, model: str = "", effort: Optional[str] = None,
             on_activity: Optional[Callable[[str], None]] = None,
             overwrite: bool = False) -> dict:
    png = project.scan_png(src, int(page))
    if not os.path.isfile(png):
        raise FileNotFoundError(f"스캔 이미지가 없습니다: {png} — 먼저 ① 스캔 뜨기를 누르세요.")
    if load(src, page) is not None and not overwrite:
        return {"page": int(page), "skipped": True}

    try:
        from PIL import Image
        with Image.open(png) as im:
            size = im.size
    except Exception:                                        # noqa: BLE001
        size = (0, 0)
    nxt = project.scan_png(src, int(page) + 1)
    nxt = nxt if os.path.isfile(nxt) else ""
    author = ClaudeAuthor(model=model, effort=effort, cwd=os.path.dirname(png),
                          on_activity=on_activity, max_turns=8,
                          max_buffer_size=32 * 1024 * 1024)
    got = author.structured(
        system=SYSTEM,
        prompt=(f"다음 스캔 이미지를 판독하십시오.\n\n  {png}\n\n"
                + (f"이어지는 쪽(참고용 — 걸친 문항을 완성할 때만 봅니다):\n\n  {nxt}\n\n" if nxt else "")
                + f"이 쪽은 `{src}` 의 {page}쪽입니다. "
                + (f"이미지 크기는 {size[0]}×{size[1]} 픽셀입니다(figures 의 bbox 좌표계). " if size[0] else "")
                + "Read 로 이미지를 열어 보고, 그 안에 실제로 인쇄된 것만 담으십시오."),
        schema=SCHEMA)

    kind = got.get("page_kind") if got.get("page_kind") in KINDS else "기타"
    # 그림 좌표는 필기 판독과 같은 규칙으로 검증한다 — 못 믿을 값은 버린다(빈 칸이 낫다)
    from services.ocr.readpage import _bbox
    for x in (got.get("problem_items") or []) + (got.get("answer_entries") or []):
        # 판독의 표·그림을 자산(이름표)으로 — 검수 화면·확정과 같은 모양(t-1 · p-1 · p-2 …).
        # ★ 좌표가 못 믿을 값이면 **영역만 비운 자산**으로 남긴다 — 이름표 자리는 맞으니
        #   사람은 드래그 한 번으로 채운다(자산을 버리면 이름표 줄이 「없는 자산」 이 된다).
        assets = {}
        if x.get("figure_table"):
            assets["t-1"] = {"type": "table", "md": x.pop("figure_table")}
        figs = x.pop("figures", None) or []
        if not figs and x.get("figure_bbox"):              # 옛 모양(하나)도 받는다
            figs = [{"bbox": x.get("figure_bbox"), "note": x.get("figure") or ""}]
        x.pop("figure_bbox", None)
        for k, f in enumerate(figs, 1):
            a = {"type": "figure", "note": str((f or {}).get("note") or "")}
            bb = _bbox((f or {}).get("bbox"), size)
            if bb:
                a["bbox"] = bb
            assets[f"p-{k}"] = a
        if assets:
            x["assets"] = assets
    d = {
        "src": src, "page": int(page),
        "page_kind": kind,
        "round": got.get("round") or None,
        "round_label": str(got.get("round_label") or ""),
        "problem_items": got.get("problem_items") or [],
        "answer_entries": got.get("answer_entries") or [],
        "notes": str(got.get("notes") or ""),
        "_cost_usd": round(author.last_cost_usd, 4),
    }
    save(src, page, d)
    return {"page": int(page), "skipped": False, "kind": kind, "round": d["round"],
            "items": len(d["problem_items"]), "answers": len(d["answer_entries"]),
            "cost_usd": d["_cost_usd"], "notes": d["notes"]}


# ── 여러 장 — 잡으로 ─────────────────────────────────────────────────────────
_LOCK = threading.Lock()
STALL_LIMIT = 3


def start(src: str, pages: list[int], *, model: str = "",
          effort: Optional[str] = None, overwrite: bool = False) -> dict:
    from services.jobs import registry

    pages = [int(p) for p in pages]
    if not pages:
        raise ValueError("판독할 쪽이 없습니다.")
    if not _LOCK.acquire(blocking=False):
        raise RuntimeError("이미 실기 판독이 돌고 있습니다 — 동시에 하나만 실행됩니다.")
    label = f"실기 판독 · {src} p.{pages[0]}~{pages[-1]} ({len(pages)}장)"
    job = registry.create("practical-read", label, [f"{src}:{p}" for p in pages])
    job["options"] = {"src": src, "overwrite": overwrite}

    def work(j: dict) -> None:
        try:
            _run(j, src, pages, model=model, effort=effort, overwrite=overwrite)
        finally:
            _LOCK.release()

    registry.spawn(job, work)
    return job


def _run(job: dict, src: str, pages: list[int], *, model: str,
         effort: Optional[str], overwrite: bool) -> None:
    from services.jobs import registry

    cost, fails, n_items, n_ans = 0.0, 0, 0, 0
    for p in pages:
        if job.get("cancel_requested"):
            registry.log(job, "[취소] 사람이 멈췄습니다.", force=True)
            break
        key = f"{src}:{p}"
        registry.item(job, key, status="running")
        job["current"] = f"p.{p}"
        try:
            r = read_one(src, p, model=model, effort=effort, overwrite=overwrite,
                         on_activity=lambda s, _p=p: registry.log(job, f"  p.{_p} {s}"))
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            registry.item(job, key, status="error", error=f"{type(e).__name__}: {e}")
            registry.log(job, f"[실패] p.{p} — {e}", force=True)
            if fails >= STALL_LIMIT:
                registry.log(job, f"[중단] {STALL_LIMIT}장 연속 실패 — 로그인·한도를 확인하세요.",
                             force=True)
                registry.finish(job, "error", error=f"{fails}장 연속 실패")
                return
            continue
        fails = 0
        job["done_count"] = job.get("done_count", 0) + 1
        if r["skipped"]:
            registry.item(job, key, status="done", output="건너뜀(이미 판독됨)")
            registry.log(job, f"  p.{p} 건너뜀 — 이미 판독됨", force=True)
            continue
        cost += r["cost_usd"] or 0.0
        n_items += r["items"]
        n_ans += r["answers"]
        what = (f"문항 {r['items']}개" if r["kind"] == "문제"
                else f"정답 {r['answers']}개" if r["kind"] == "정답" else "기타 쪽")
        registry.item(job, key, status="done", output=f"{r['kind']} · {what}")
        registry.log(job, f"[판독] p.{p} → {r['kind']}"
                          + (f" {r['round']}회" if r.get("round") else "")
                          + f" · {what} (${r['cost_usd']:.2f})", force=True)
        if r.get("notes"):
            registry.log(job, f"      메모: {r['notes'][:160]}")

    registry.log(job, f"[완료] {job.get('done_count', 0)}장 · 문항 {n_items} · 정답 {n_ans} · "
                      f"${cost:.2f}", force=True)
    registry.finish(job, "done", result={"pages": job.get("done_count", 0),
                                         "items": n_items, "answers": n_ans,
                                         "cost_usd": round(cost, 2)})
