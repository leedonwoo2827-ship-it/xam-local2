# -*- coding: utf-8 -*-
"""1부 빌드(2교시 액세스) — 액세스 집필 결과로 **실습파일(.accdb) · 외부 데이터 · 검증**을 만든다.

  06/practical/mNN/mNN_문제.accdb        문제1 이 설계한 테이블·필드·레코드·관계(지시 적용 전 상태) + 미리 주는 쿼리
  06/practical/mNN/mNN_정답.accdb        문제 파일 + 정답 쿼리(원고의 SQL 을 그 이름으로 저장)
  06/practical/mNN/<외부 데이터 파일>     가져오기·연결 문제가 쓰는 파일(.xlsx · .txt · .csv)
  06/practical/mNN/verify_access.json     정답 SQL 을 실제 액세스 엔진(DAO)에서 돌려 원고의 결과 행과 대조

★ 액세스 창을 띄우지 않는다 — DAO(DAO.DBEngine.120)로 파일만 만든다(2026-11-19: 사용자가 PC 를 쓰는 중).
★ 폼·보고서·매크로는 화면 설계가 필요해 아직 만들지 않는다 — verify 의 「사람 작업」 목록으로 남긴다.
★ 검증은 거짓 통과를 만들지 않는다: 매개 변수 값을 지문에서 못 찾으면 「사람 확인」, 결과가 다르면 「다름」.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import json
import os
import re
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from core.atomic_io import atomic_write_text
from services.book import paths
from services.practical import author_access as aa

# DAO 상수
DB_BOOLEAN, DB_BYTE, DB_INTEGER, DB_LONG, DB_CURRENCY, DB_SINGLE, DB_DOUBLE, DB_DATE = 1, 2, 3, 4, 5, 6, 7, 8
DB_TEXT, DB_MEMO = 10, 12
DB_AUTOINCR, DB_HYPERLINK = 16, 32768
REL_DONT_ENFORCE, REL_UPDATE_CASCADE, REL_DELETE_CASCADE = 2, 256, 4096
DB_LANG_KOREAN = ";LANGID=0x0412;CP=949;COUNTRY=0"


def out_dir(m: int) -> str:
    return os.path.join(paths.book_dir(), "06", "practical", f"m{m:02d}")


# ── 필드 형식 ──────────────────────────────────────────────────────────────
def _num_type(props: dict) -> int:
    size = str((props or {}).get("필드 크기") or (props or {}).get("field_size") or "")
    if "Double" in size or "실수(Double)" in size:
        return DB_DOUBLE
    if "Single" in size:
        return DB_SINGLE
    if "바이트" in size or "Byte" in size:
        return DB_BYTE
    if size.startswith("정수") and "Long" not in size:
        return DB_INTEGER
    return DB_LONG


def dao_type(f: dict) -> Tuple[int, int, int]:
    """(형식, 크기, 속성) — 한글·영문 형식 이름을 받는다."""
    t = str(f.get("type") or "").replace(" ", "").lower()
    props = f.get("props") or {}
    if "일련" in t or "autonumber" in t:
        return DB_LONG, 0, DB_AUTOINCR
    if "긴텍스트" in t or "메모" in t or "longtext" in t or "memo" in t:
        return DB_MEMO, 0, 0
    if "하이퍼링크" in t or "hyperlink" in t:
        return DB_MEMO, 0, DB_HYPERLINK
    if "텍스트" in t or "text" in t:
        return DB_TEXT, int(f.get("size") or 255), 0
    if "통화" in t or "currency" in t:
        return DB_CURRENCY, 0, 0
    if "날짜" in t or "date" in t:
        return DB_DATE, 0, 0
    if "yes" in t or "예/아니" in t or "boolean" in t:
        return DB_BOOLEAN, 0, 0
    if "숫자" in t or "number" in t:
        return _num_type(props), 0, 0
    return DB_TEXT, int(f.get("size") or 255), 0


FIELD_PROPS = {  # 원고 속성 이름 → (DAO 이름, 형식) — 형식 None 은 Field 내장 속성
    "형식": ("Format", 10), "입력 마스크": ("InputMask", 10), "캡션": ("Caption", 10),
    "유효성 검사 규칙": ("ValidationRule", None), "유효성 검사 텍스트": ("ValidationText", None),
    "기본값": ("DefaultValue", None), "필수": ("Required", None), "빈 문자열 허용": ("AllowZeroLength", None),
}
YES = ("예", "yes", "true", "1", "y")


def _apply_field_props(fld, props: dict, warns: List[str], where: str) -> None:
    for k, v in (props or {}).items():
        spec = FIELD_PROPS.get(k)
        if not spec or v in (None, ""):
            continue
        name, ptype = spec
        try:
            if name in ("Required", "AllowZeroLength"):
                setattr(fld, name, str(v).strip().lower() in YES)
            elif ptype is None:
                setattr(fld, name, str(v))
            else:
                fld.Properties.Append(fld.CreateProperty(name, ptype, str(v)))
        except Exception as e:                                   # noqa: BLE001
            warns.append(f"{where} {k}={v}: {e}")


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$")


def _value(v: Any, ftype: int) -> Any:
    if v is None or (isinstance(v, str) and v.strip() == "" and ftype != DB_TEXT and ftype != DB_MEMO):
        return None
    if ftype == DB_DATE and isinstance(v, str) and DATE_RE.match(v.strip()):
        s = v.strip().replace("T", " ")
        fmt = "%Y-%m-%d %H:%M:%S" if s.count(":") == 2 else ("%Y-%m-%d %H:%M" if ":" in s else "%Y-%m-%d")
        # ★ 시간대 없는 datetime 을 넘기면 pywin32 가 지역 시각 → UTC 로 바꿔 9시간 밀려 저장된다
        #   (2026-11-19 실측: 2026-09-01 → 2026-08-31 15:00). UTC 로 표시해 벽시계 값 그대로 넣는다.
        return dt.datetime.strptime(s, fmt).replace(tzinfo=dt.timezone.utc)
    if ftype == DB_BOOLEAN:
        return str(v).strip().lower() in YES or v is True
    if ftype in (DB_LONG, DB_INTEGER, DB_BYTE) and isinstance(v, str):
        try:
            return int(v.replace(",", ""))
        except ValueError:
            return v
    if ftype in (DB_DOUBLE, DB_SINGLE, DB_CURRENCY) and isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            return v
    return v


# ── 문제 DB ────────────────────────────────────────────────────────────────
def _engine():
    import win32com.client as w
    return w.Dispatch("DAO.DBEngine.120")


def make_problem_db(path: str, db_doc: dict, given_queries: List[dict], warns: List[str]) -> Dict[str, Any]:
    if os.path.exists(path):
        os.remove(path)
    db = _engine().CreateDatabase(path, DB_LANG_KOREAN)
    made = {"tables": [], "rows": 0, "relationships": 0, "queries": []}
    types: Dict[str, Dict[str, int]] = {}
    try:
        for t in db_doc.get("tables") or []:
            name = t["name"]
            td = db.CreateTableDef(name)
            types[name] = {}
            keys = []
            for f in t.get("fields") or []:
                ftype, size, attr = dao_type(f)
                fld = td.CreateField(f["name"], ftype, size) if size else td.CreateField(f["name"], ftype)
                if attr:
                    try:
                        fld.Attributes = fld.Attributes | attr
                    except Exception as e:                       # noqa: BLE001
                        warns.append(f"{name}.{f['name']} 속성: {e}")
                if ftype in (DB_TEXT, DB_MEMO):
                    try:
                        fld.AllowZeroLength = True
                    except Exception:                            # noqa: BLE001
                        pass
                td.Fields.Append(fld)
                types[name][f["name"]] = ftype
                if f.get("key"):
                    keys.append(f["name"])
            if keys:
                idx = td.CreateIndex("PrimaryKey")
                idx.Primary = True
                for k in keys:
                    idx.Fields.Append(idx.CreateField(k))
                td.Indexes.Append(idx)
            db.TableDefs.Append(td)
            # 속성(형식·입력 마스크·…)은 붙인 뒤에 — 지시 적용 전 상태
            tdo = db.TableDefs(name)
            for f in t.get("fields") or []:
                if f.get("props"):
                    _apply_field_props(tdo.Fields(f["name"]), f["props"], warns, f"{name}.{f['name']}")
            # 레코드
            cols = [f["name"] for f in t.get("fields") or []]
            auto = {f["name"] for f in t.get("fields") or [] if dao_type(f)[2] & DB_AUTOINCR}
            rs = db.OpenRecordset(name)
            for r in t.get("rows") or []:
                try:
                    rs.AddNew()
                    for c, v in zip(cols, r):
                        if c in auto:
                            continue
                        val = _value(v, types[name][c])
                        if val is not None:
                            rs.Fields(c).Value = val
                    rs.Update()
                    made["rows"] += 1
                except Exception as e:                           # noqa: BLE001
                    try:
                        rs.CancelUpdate()
                    except Exception:                            # noqa: BLE001
                        pass
                    warns.append(f"{name} 레코드 {r[:3]}…: {e}")
            rs.Close()
            made["tables"].append(name)
        # 관계(문제 파일에 이미 있는 것)
        for i, rel in enumerate(db_doc.get("relationships") or []):
            try:
                t1, f1 = str(rel.get("from") or "").split(".", 1)
                t2, f2 = str(rel.get("to") or "").split(".", 1)
                attr = 0
                if not rel.get("integrity", True):
                    attr |= REL_DONT_ENFORCE
                if rel.get("cascadeUpdate"):
                    attr |= REL_UPDATE_CASCADE
                if rel.get("cascadeDelete"):
                    attr |= REL_DELETE_CASCADE
                r = db.CreateRelation(f"rel{i + 1}_{t1}_{t2}", t1, t2, attr)
                fld = r.CreateField(f1)
                fld.ForeignName = f2
                r.Fields.Append(fld)
                db.Relations.Append(r)
                made["relationships"] += 1
            except Exception as e:                               # noqa: BLE001
                warns.append(f"관계 {rel.get('from')}→{rel.get('to')}: {e}")
        # 미리 주는 쿼리
        for q in list(db_doc.get("queries") or []) + list(given_queries or []):
            if q.get("name") and q.get("sql"):
                try:
                    db.CreateQueryDef(q["name"], q["sql"])
                    made["queries"].append(q["name"])
                except Exception as e:                           # noqa: BLE001
                    warns.append(f"쿼리 {q.get('name')}: {e}")
    finally:
        db.Close()
    return made


# ── 외부 데이터 ──────────────────────────────────────────────────────────────
def make_external(od: str, ext: List[dict], warns: List[str]) -> List[str]:
    out = []
    for e in ext or []:
        name = os.path.basename(str(e.get("file") or "").strip())
        if not name:
            continue
        p = os.path.join(od, name)
        cols, rows = e.get("columns") or [], e.get("rows") or []
        try:
            if name.lower().endswith((".xlsx", ".xls")):
                _write_xlsx(p, e.get("sheet") or "Sheet1", cols, rows)
            else:
                delim = "\t" if name.lower().endswith(".txt") and "\t" in str(e.get("note") or "") else ","
                with open(p, "w", encoding="cp949", newline="", errors="replace") as fh:
                    w = csv.writer(fh, delimiter=delim)
                    w.writerow(cols)
                    w.writerows(rows)
            out.append(name)
        except Exception as ex:                                  # noqa: BLE001
            warns.append(f"외부 데이터 {name}: {ex}")
    return out


def _write_xlsx(path: str, sheet: str, cols: List[str], rows: List[list]) -> None:
    """엑셀(보이지 않게)로 만든다 — openpyxl 이 없다."""
    import win32com.client as w
    xl = w.DispatchEx("Excel.Application")
    xl.Visible = False
    xl.DisplayAlerts = False
    try:
        wb = xl.Workbooks.Add()
        ws = wb.Worksheets(1)
        ws.Name = sheet[:31]
        data = [list(cols)] + [list(r) + [None] * (len(cols) - len(r)) for r in rows]
        for i, r in enumerate(data, 1):
            for j, v in enumerate(r[:len(cols)], 1):
                if v is not None:
                    ws.Cells(i, j).Value = v
        if os.path.exists(path):
            os.remove(path)
        wb.SaveAs(path, 51)
        wb.Close(False)
    finally:
        xl.Quit()


# ── 정답 쿼리 · 검증 ─────────────────────────────────────────────────────────
SQL_RE = re.compile(r"^\s*(SELECT|UPDATE|INSERT|DELETE|TRANSFORM|PARAMETERS)\b", re.I)
NAME_RE = re.compile(r"[〈<]([^〉>]+)[〉>]")


def _sql_of(it: dict) -> str:
    for b in it.get("boxes") or []:
        t = str(b.get("text") or "").strip()
        if SQL_RE.match(t):
            return t
    return ""


def _query_name(it: dict, tables: set) -> str:
    """지문의 〈이름〉 중 테이블이 아닌 마지막 것 — 「…〈설치현황조회〉 매개 변수 쿼리를 작성하시오」."""
    names = [n.strip() for n in NAME_RE.findall(it.get("lead") or "")]
    cand = [n for n in names if n not in tables]
    return cand[-1] if cand else ""


def _norm(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "year") and hasattr(v, "month"):
        try:
            return f"{v.year:04d}-{v.month:02d}-{v.day:02d}" + (
                f" {v.hour:02d}:{v.minute:02d}" if getattr(v, "hour", 0) or getattr(v, "minute", 0) else "")
        except Exception:                                        # noqa: BLE001
            return str(v)
    if isinstance(v, bool):
        return "예" if v else "아니요"
    if isinstance(v, float):
        return f"{round(v, 2):g}"
    s = str(v).strip().replace(",", "") if isinstance(v, str) and re.fullmatch(r"-?[\d,]+(\.\d+)?", str(v).strip()) else str(v).strip()
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".")[0]
    if re.fullmatch(r"-?\d+\.\d+", s):
        s = f"{round(float(s), 2):g}"
    if isinstance(v, str) and DATE_RE.match(s):
        s = s[:10] if s[11:] in ("", "00:00", "00:00:00") else s
    return s


def _read(rs) -> Tuple[List[str], List[list]]:
    cols = [rs.Fields(i).Name for i in range(rs.Fields.Count)]
    rows = []
    while not rs.EOF:
        rows.append([rs.Fields(i).Value for i in range(rs.Fields.Count)])
        rs.MoveNext()
    rs.Close()
    return cols, rows


def _compare(got_cols, got_rows, want: dict) -> Tuple[bool, str]:
    wc = [str(c) for c in want.get("columns") or []]
    if not wc:
        return False, "원고에 결과(columns)가 없습니다"
    idx = {c: i for i, c in enumerate(got_cols)}
    miss = [c for c in wc if c not in idx]
    if miss:
        return False, f"열이 없습니다: {miss} (엔진 결과 열 {got_cols})"
    def wnorm(x):   # 원고가 형식(yyyy-mm)대로 적은 날짜 「2026-09」 → 엔진 값 「2026-09-01」
        s = _norm(x)
        return s + "-01" if re.fullmatch(r"\d{4}-\d{2}", s) else s
    g = sorted(tuple(_norm(r[idx[c]]) for c in wc) for r in got_rows)
    w = sorted(tuple(wnorm(x) for x in (list(r) + [None] * (len(wc) - len(r)))[:len(wc)]) for r in want.get("rows") or [])
    if g == w:
        return True, f"{len(g)}행 일치"
    only_g = [r for r in g if r not in w][:3]
    only_w = [r for r in w if r not in g][:3]
    return False, f"엔진 {len(g)}행 · 원고 {len(w)}행 — 엔진에만 {only_g} · 원고에만 {only_w}"


PARAM_HINT = re.compile(r"(?:입력란에|입력값|입력하면|입력 예)[^'\"‘“]*['\"‘“]([^'\"’”]+)['\"’”]")


def _param_value(it: dict) -> Optional[str]:
    text = " ".join([str(f.get("desc") or "") for f in it.get("figures") or []] + list(it.get("instructions") or []))
    m = PARAM_HINT.search(text)
    return m.group(1) if m else None


def verify_item(prob_db: str, it: dict, sql: str) -> Dict[str, Any]:
    """문제 DB 의 복사본에서 정답 SQL 을 돌려 원고의 결과와 대조한다(원본은 건드리지 않는다)."""
    want = (it.get("answer") or {}).get("result") or {}
    tmp = os.path.join(tempfile.gettempdir(), f"xam_verify_{os.getpid()}.accdb")
    shutil.copyfile(prob_db, tmp)
    db = _engine().OpenDatabase(tmp)
    try:
        head = sql.lstrip().split(None, 1)[0].upper()
        qd = db.CreateQueryDef("", sql)
        if qd.Parameters.Count:
            val = _param_value(it)
            if val is None:
                return {"status": "사람 확인", "note": "매개 변수 값을 지문에서 찾지 못했습니다"}
            for i in range(qd.Parameters.Count):
                qd.Parameters(i).Value = val
        action = head in ("UPDATE", "INSERT", "DELETE") or re.search(r"\bINTO\b", sql, re.I) and head == "SELECT"
        if not action:
            cols, rows = _read(qd.OpenRecordset())
            ok, note = _compare(cols, rows, want)
            return {"status": "일치" if ok else "다름", "note": note}
        qd.Execute()
        # 실행 뒤 대상 테이블을 읽어 대조(업데이트 · 추가 · 삭제 · 테이블 만들기)
        m = (re.search(r"\bINTO\s+\[?([^\s\]\(]+)", sql, re.I) or re.search(r"^\s*UPDATE\s+\[?([^\s\]]+)", sql, re.I)
             or re.search(r"\bFROM\s+\[?([^\s\];]+)", sql, re.I))
        if not m:
            return {"status": "사람 확인", "note": "실행은 됐지만 대상 테이블을 못 찾았습니다"}
        cols, rows = _read(db.OpenRecordset(f"SELECT * FROM [{m.group(1)}]"))
        ok, note = _compare(cols, rows, want)
        return {"status": "일치" if ok else "다름", "note": f"{m.group(1)} — {note}"}
    except Exception as e:                                       # noqa: BLE001
        return {"status": "오류", "note": f"{type(e).__name__}: {str(e)[:300]}"}
    finally:
        db.Close()
        try:
            os.remove(tmp)
        except OSError:
            pass


def _load_parts(m: int) -> Dict[int, dict]:
    out = {}
    for p in (1, 2, 3, 4):
        f = os.path.join(aa.round_dir(m), f"part{p}.json")
        if os.path.isfile(f):
            with open(f, encoding="utf-8") as fh:
                out[p] = json.load(fh)
    return out


def build_round(m: int) -> Dict[str, Any]:
    db_doc = aa.load_db(m)
    if not db_doc:
        raise FileNotFoundError(f"{m:02d}회 액세스 DB 설계(db.json)가 없습니다 — 액세스 집필 문제1 을 먼저.")
    parts = _load_parts(m)
    od = out_dir(m)
    os.makedirs(od, exist_ok=True)
    warns: List[str] = []
    given_q, todo = [], []
    for p, d in parts.items():
        g = d.get("given") or {}
        given_q += [q for q in g.get("queries") or [] if q.get("name") and q.get("sql")]
        for k, label in (("forms", "폼"), ("reports", "보고서"), ("macros", "매크로")):
            for o in g.get(k) or []:
                todo.append(f"문제{p} {label} 〈{o.get('name') or '?'}〉 — 문제 파일에 지시 전 상태로 만들 것")
    prob = os.path.join(od, f"m{m:02d}_문제.accdb")
    made = make_problem_db(prob, db_doc, given_q, warns)
    ext = make_external(od, db_doc.get("external") or [], warns)

    # 정답 파일 = 문제 파일 + 정답 쿼리
    ans = os.path.join(od, f"m{m:02d}_정답.accdb")
    shutil.copyfile(prob, ans)
    tables = {t["name"] for t in db_doc.get("tables") or []}
    checks, saved = [], []
    adb = _engine().OpenDatabase(ans)
    try:
        for p, d in sorted(parts.items()):
            for it in d.get("items") or []:
                sql = _sql_of(it)
                key = f"{p}-{it.get('no')}"
                if not sql:
                    if p in (2, 3):
                        todo.append(f"문제{key} — 폼·보고서·이벤트 프로시저: 정답 파일에 사람이 반영")
                    continue
                qn = _query_name(it, tables) or f"정답_{p}_{it.get('no')}"
                try:
                    adb.CreateQueryDef(qn, sql)
                    saved.append(qn)
                except Exception as e:                           # noqa: BLE001
                    warns.append(f"정답 쿼리 {qn}: {e}")
                r = verify_item(prob, it, sql)
                checks.append({"item": key, "query": qn, **r})
    finally:
        adb.Close()

    n_ok = sum(1 for c in checks if c["status"] == "일치")
    info = {"round": m, "built_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "problem_db": os.path.basename(prob), "answer_db": os.path.basename(ans), "external": ext,
            "tables": made["tables"], "rows": made["rows"], "relationships": made["relationships"],
            "given_queries": made["queries"], "answer_queries": saved, "checks": checks,
            "human_todo": todo, "warnings": warns,
            "summary": f"테이블 {len(made['tables'])} · 레코드 {made['rows']} · 정답 쿼리 {len(saved)} · "
                       f"검증 일치 {n_ok}/{len(checks)} · 사람 작업 {len(todo)} · 경고 {len(warns)}"}
    atomic_write_text(os.path.join(od, "verify_access.json"), json.dumps(info, ensure_ascii=False, indent=1, default=str))
    return info
