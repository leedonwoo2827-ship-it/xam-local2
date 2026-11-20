# -*- coding: utf-8 -*-
"""1급 엑셀 분석작업의 **외부 데이터 원본**(〈렌터카.accdb〉의 〈대여내역〉 테이블 · 〈농산물.xlsx〉 …)을 만든다.

  06/practical/mNN/<원본 파일>   ·  07/mNN/files/<원본 파일>   ·  06/practical/mNN/external_excel.json(장부 · 검증)

★ 2026-11-20 종합반 세션 요청: 원고가 외부 원본을 참조하는데 파일이 없었다(수험자 실습 파일로도 필요).
★ 원고에 원본 레코드 표(「참고: 외부 원본 … 자료」 그림)가 있으면 그것을 쓴다. 없으면 Claude 가 피벗 결과(<그림>)와
  **정확히 맞는** 원본 레코드를 짓고, 앱이 그 레코드로 피벗을 직접 계산해 그림의 숫자와 대조한다(안 맞으면 한 번 더).
★ 테이블 이름은 지시문의 이름 그대로(피벗 녹화 대본이 그 이름을 고른다). accdb 는 DAO, xlsx 는 엑셀(보이지 않게).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from core.atomic_io import atomic_write_text
from services.book import paths
from services.practical import author as pa

REF_RE = re.compile(r"[<〈]([\w가-힣]+\.(?:accdb|xlsx))[>〉]\s*(?:의|파일의)?\s*[<〈'‘]?([\w가-힣$]+)?")


def find_refs(m: int) -> List[Tuple[dict, str, str]]:
    """(문항, 파일, 테이블) — 1교시 원고에서 외부 원본을 쓰는 문항."""
    out = []
    for f in sorted(os.listdir(pa.round_dir(m))):
        if not re.fullmatch(rf"{m:02d}-\d-\d\d\.json", f):
            continue
        with open(os.path.join(pa.round_dir(m), f), encoding="utf-8") as fh:
            it = json.load(fh)
        text = " ".join(it.get("instructions") or [])
        mt = REF_RE.search(text)
        if mt and "외부" in text:
            out.append((it, mt.group(1), (mt.group(2) or "").rstrip("$")))
    return out


SYSTEM = """당신은 컴활 1급 실기 엑셀 「분석작업 — 외부 데이터 원본 피벗 테이블」 문항의 **원본 데이터 파일**을 만드는 사람입니다.
문항(지시사항 · 피벗 결과 <그림> 표 · 모범답안)을 받고, 그 피벗 결과가 **숫자 하나 틀리지 않고** 나오는 원본 테이블 레코드를 씁니다.

- 열(columns): 지시사항·그림에 나오는 필드는 모두, 이름 그대로. 형식은 text · number · date · currency 중 하나.
  날짜 필드는 "YYYY-MM-DD". 그룹(연·분기·월·숫자 구간)이 걸리는 필드는 그 그룹에 맞는 값으로 고르게 퍼뜨린다.
- 레코드는 20~40개. 피벗의 칸마다 1~3개 레코드가 들어가게(합계면 나눠 더해 맞추고, 평균이면 평균이 맞게).
  빈 칸(값 없음)인 조합에는 레코드를 두지 않는다. 필터가 걸리는 문항이면 걸러지는 레코드도 조금 둔다.
- pivot 에 이 피벗을 다시 계산하는 데 필요한 정의를 적는다: rows(행 필드) · cols(열 필드) · values(값 필드와 집계 sum|avg|count|max|min)
  · group(그룹: field, kind=year|quarter|month|year_quarter|number, number 면 start·end·step) · filter(필드: 값 목록, 없으면 생략).
- 출력은 지정한 JSON 하나뿐입니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "columns": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "type": {"type": "string", "enum": ["text", "number", "date", "currency"]}},
            "required": ["name", "type"]}},
        "rows": {"type": "array", "items": {"type": "array", "items": {"type": ["string", "number", "null"]}}},
        "pivot": {"type": "object", "properties": {
            "rows": {"type": "array", "items": {"type": "string"}},
            "cols": {"type": "array", "items": {"type": "string"}},
            "values": {"type": "array", "items": {"type": "object", "properties": {
                "field": {"type": "string"}, "agg": {"type": "string"}}}},
            "group": {"type": "object"},
            "filter": {"type": "object"}}},
    },
    "required": ["columns", "rows", "pivot"],
}


# ── 피벗 다시 계산 · 그림과 대조 ──────────────────────────────────────────────
def _num(v) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").replace(",", "").replace("원", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _grp(v, g: dict) -> List[str]:
    """그룹 키 — 날짜(연·분기·월) · 숫자 구간."""
    kind = str(g.get("kind") or "")
    if kind == "number":
        x = _num(v)
        if x is None:
            return [str(v)]
        st, step = float(g.get("start") or 0), float(g.get("step") or 1)
        lo = st + ((x - st) // step) * step
        return [f"{lo:g}-{lo + step - 1:g}"]
    try:
        d = dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return [str(v)]
    q = f"{(d.month - 1) // 3 + 1}사분기"
    return {"year": [f"{d.year}년"], "quarter": [q], "month": [f"{d.month}월"],
            "year_quarter": [f"{d.year}년", q]}.get(kind, [str(v)])


def compute(cols: List[dict], rows: List[list], pv: dict) -> List[float]:
    """피벗의 모든 칸 · 부분합 · 총합 숫자(대조용) — 행·열 조합마다 집계."""
    names = [c["name"] for c in cols]
    idx = {n: i for i, n in enumerate(names)}
    g = pv.get("group") or {}
    flt = pv.get("filter") or {}
    recs = []
    for r in rows:
        r = list(r) + [None] * (len(names) - len(r))
        if any(str(r[idx[k]]) not in [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in flt.items() if k in idx):
            continue
        recs.append(r)

    def key(r, fields):
        out = []
        for fld in fields:
            if fld not in idx:
                continue
            out += _grp(r[idx[fld]], g) if g.get("field") == fld else [str(r[idx[fld]])]
        return tuple(out)

    nums: List[float] = []
    for vd in pv.get("values") or []:
        fld, agg = vd.get("field"), str(vd.get("agg") or "sum").lower()
        if fld not in idx:
            continue
        buckets: Dict[Tuple, List[float]] = defaultdict(list)
        rf, cf = pv.get("rows") or [], pv.get("cols") or []
        for r in recs:
            x = _num(r[idx[fld]]) if agg != "count" else 1.0
            if x is None:
                continue
            rk, ck = key(r, rf), key(r, cf)
            for i in range(len(rk) + 1):                     # 칸 · 행 부분합 · 총합 모두
                for j in range(len(ck) + 1):
                    buckets[(rk[:i], ck[:j])].append(x)
        for xs in buckets.values():
            v = {"sum": sum(xs), "count": len(xs), "max": max(xs), "min": min(xs)}.get(agg, sum(xs) / len(xs))
            nums.append(round(v, 2))
    return nums


def check(figure_rows: List[list], nums: List[float]) -> Tuple[int, List[float]]:
    """그림의 숫자 중 계산 결과에 없는 것."""
    have = set(nums) | {round(x) for x in nums} | {round(x, 1) for x in nums}
    miss = []
    for r in figure_rows or []:
        if r and isinstance(r[0], int):                  # 「행」 열(엑셀 행 번호)은 값이 아니다
            r = r[1:]
        for v in r:
            x = _num(v)
            if x is None or abs(x) < 1e-9:
                continue
            if x not in have and round(x) not in have and round(x, 1) not in have:
                miss.append(x)
    return len(miss), miss[:8]


def _figs(it: dict) -> Tuple[Optional[dict], Optional[dict]]:
    """(원본 자료 그림, 피벗 결과 그림)."""
    src = res = None
    for f in it.get("figures") or []:
        if f.get("kind") != "table":
            continue
        cap = str(f.get("caption") or "")
        if "외부 원본" in cap or "원본" in cap and "자료" in cap:
            src = f
        elif res is None:
            res = f
    return src, res


def make_source(it: dict, file: str, table: str, model: str = "", log=print) -> Dict[str, Any]:
    src, res = _figs(it)
    if src and src.get("columns") and src.get("rows"):
        cols = [{"name": c, "type": "text"} for c in src["columns"]]
        rows = src["rows"]
        for k, c in enumerate(cols):                       # 형식 짐작
            vals = [r[k] for r in rows if k < len(r) and r[k] not in (None, "")]
            if vals and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(v)) for v in vals):
                c["type"] = "date"
            elif vals and all(_num(v) is not None for v in vals):
                c["type"] = "number"
        return {"columns": cols, "rows": rows, "pivot": {}, "from": "원고 원본 표", "miss": None}
    from services.authoring.provider import ClaudeAuthor
    prompt = ("파일: " + file + " · 테이블: " + table + "\n\n문항(JSON):\n```json\n"
              + json.dumps({k: it.get(k) for k in ("lead", "instructions", "figures", "answer")}, ensure_ascii=False)[:20000]
              + "\n```")
    last, best = None, None
    for attempt in range(2):
        author = ClaudeAuthor(model=model, cwd=pa.round_dir(int(it["round"])), max_turns=6)
        got = author.structured(system=SYSTEM, prompt=prompt + (f"\n\n앞선 시도의 레코드로 계산하니 그림의 숫자 {last} 가 나오지 않았습니다. 고쳐 다시 쓰십시오." if last else ""),
                                schema=SCHEMA)
        nums = compute(got["columns"], got["rows"], got.get("pivot") or {})
        n, miss = check((res or {}).get("rows") or [], nums)
        log(f"    시도 {attempt + 1}: 레코드 {len(got['rows'])} · 그림 숫자 중 안 맞음 {n} {miss}")
        if n == 0:
            return dict(got, **{"from": "Claude(피벗 결과에 맞춤)", "miss": 0})
        if best is None or n < best[0]:                   # 더 잘 맞은 시도를 남긴다
            best = (n, got, miss)
        last = miss
    n, got, miss = best
    return dict(got, **{"from": "Claude(피벗 결과에 맞춤)", "miss": n, "miss_values": miss,
                        "note": "그림 숫자 일부가 안 맞음 — 계산 필드(예: 마진·1인당금액)이거나 그림의 평균 요약이 서로 맞지 않는 경우"})


TYPE_KO = {"text": "짧은 텍스트", "number": "숫자", "date": "날짜/시간", "currency": "통화"}


def write_file(od: str, file: str, table: str, data: dict) -> str:
    from services.practical import build_access as ba
    p = os.path.join(od, file)
    if file.lower().endswith(".accdb"):
        fields = []
        for c in data["columns"]:
            f = {"name": c["name"], "type": TYPE_KO.get(c["type"], "짧은 텍스트")}
            if c["type"] == "number" and any(isinstance(r[i], float) and not float(r[i]).is_integer()
                                             for r in data["rows"] for i, cc in enumerate(data["columns"])
                                             if cc is c and i < len(r) and isinstance(r[i], float)):
                f["props"] = {"필드 크기": "실수(Double)"}
            if c["type"] == "text":
                f["size"] = 50
            fields.append(f)
        warns: List[str] = []
        ba.make_problem_db(p, {"tables": [{"name": table, "fields": fields, "rows": data["rows"]}]}, [], warns)
        if warns:
            raise RuntimeError("; ".join(warns[:3]))
    else:
        ba._write_xlsx(p, table or "Sheet1", [c["name"] for c in data["columns"]], data["rows"])
    return p


def build_round(m: int, model: str = "", log=print) -> Dict[str, Any]:
    od = os.path.join(paths.book_dir(), "06", "practical", f"m{m:02d}")
    os.makedirs(od, exist_ok=True)
    ledger = {"round": m, "files": []}
    seen = set()
    for it, file, table in find_refs(m):
        if file in seen:
            continue
        seen.add(file)
        log(f"  {m:02d}회 {file} 〈{table}〉 — 문제{it.get('part')}-{it.get('no')}")
        data = make_source(it, file, table, model=model, log=log)
        p = write_file(od, file, table, data)
        ed = os.path.join(paths.ebook_dir(), f"m{m:02d}", "files")
        if os.path.isdir(ed):
            shutil.copyfile(p, os.path.join(ed, file))
        ledger["files"].append({"file": file, "table": table, "item": f"{it.get('part')}-{it.get('no')}",
                                "from": data.get("from"), "records": len(data["rows"]),
                                "columns": [c["name"] for c in data["columns"]],
                                "pivot_check_miss": data.get("miss"), "miss_values": data.get("miss_values")})
    atomic_write_text(os.path.join(od, "external_excel.json"), json.dumps(ledger, ensure_ascii=False, indent=1, default=str))
    return ledger
