# -*- coding: utf-8 -*-
"""액세스 실습파일에 **폼 · 보고서**를 넣는다 — 집필이 남긴 설계(partP.json 의 given)로.

  문제 파일: 「지시 적용 전」 상태의 폼·보고서(레코드 원본 · 구역 · 컨트롤 · 그룹 · 지시 전 속성)
  정답 파일: 그 위에 원고의 정답 속성(answer.props)과 이벤트 프로시저(코드박스의 Private Sub …)

★ 액세스를 **보이지 않게** 띄워(Access.Application, Visible=False) 디자인 보기로 만든다 — 사용자가 PC 를 쓰는 중이다.
★ 설계는 집필마다 표기가 조금씩 다르다(record_source · recordSource · properties · props …) — 아는 것만 읽고
  모르는 것은 경고로 남긴다(거짓 완성을 만들지 않는다). 컨트롤 배치는 설계에 좌표가 없어 구역별로 차례로 놓는다.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

AC_FORM, AC_REPORT = 2, 3
AC_DESIGN = 1
AC_SAVE_YES = 1
CTRL = {"레이블": 100, "텍스트 상자": 109, "명령 단추": 104, "확인란": 106, "콤보 상자": 111, "목록 상자": 110,
        "하위 폼/하위 보고서": 112, "하위 폼": 112, "하위 보고서": 112, "옵션 그룹": 107, "토글 단추": 122,
        "label": 100, "textbox": 109, "commandbutton": 104, "checkbox": 106, "combobox": 111, "listbox": 110, "subform": 112}
SECTION = {"본문": 0, "폼 머리글": 1, "보고서 머리글": 1, "폼 바닥글": 2, "보고서 바닥글": 2,
           "페이지 머리글": 3, "페이지 바닥글": 4, "detail": 0, "formheader": 1, "formfooter": 2,
           "pageheader": 3, "pagefooter": 4, "reportheader": 1, "reportfooter": 2}
YES = ("예", "yes", "true", "1", "y")


def _get(o: dict, *keys, default=None):
    for k in keys:
        for src in (o, o.get("properties") or {}, o.get("props") or {}):
            if isinstance(src, dict) and src.get(k) not in (None, ""):
                return src[k]
    return default


def _bool(v) -> bool:
    return str(v).strip().lower() in YES or v is True


def _view(v) -> Optional[int]:
    s = str(v or "")
    if "연속" in s or "continuous" in s.lower():
        return 1
    if "데이터시트" in s or "datasheet" in s.lower():
        return 2
    if "단일" in s or "single" in s.lower():
        return 0
    return None


def _scroll(v) -> Optional[int]:
    s = str(v or "")
    if "없음" in s or "neither" in s.lower():
        return 0
    if "가로" in s and "세로" in s or "both" in s.lower():
        return 3
    if "가로" in s:
        return 1
    if "세로" in s:
        return 2
    return None


def _running(v) -> Optional[int]:
    s = str(v or "")
    if "그룹" in s:
        return 1
    if "모두" in s or "전체" in s:
        return 2
    if "아니" in s or s.strip() in ("0", "no"):
        return 0
    return None


# 속성 이름(원고) → (액세스 속성, 값 변환)
PROP = {
    "레코드 원본": ("RecordSource", str), "기본 보기": ("DefaultView", _view), "탐색 단추": ("NavigationButtons", _bool),
    "스크롤 막대": ("ScrollBars", _scroll), "레코드 선택기": ("RecordSelectors", _bool), "구분 선": ("DividingLines", _bool),
    "추가 가능": ("AllowAdditions", _bool), "삭제 가능": ("AllowDeletions", _bool), "편집 가능": ("AllowEdits", _bool),
    "필터": ("Filter", str), "정렬 기준": ("OrderBy", str), "캡션": ("Caption", str),
    "컨트롤 원본": ("ControlSource", str), "형식": ("Format", str), "중복 내용 숨기기": ("HideDuplicates", _bool),
    "누적 합계": ("RunningSum", _running), "탭 인덱스": ("TabIndex", int), "탭 정지": ("TabStop", _bool),
    "사용 가능": ("Enabled", _bool), "잠금": ("Locked", _bool), "표시": ("Visible", _bool), "행 원본": ("RowSource", str),
    "바운드 열": ("BoundColumn", int), "열 개수": ("ColumnCount", int), "열 너비": ("ColumnWidths", str),
    "기본값": ("DefaultValue", str), "입력 마스크": ("InputMask", str), "반복 실행 구역": ("RepeatSection", _bool),
    "페이지 바꿈": ("ForceNewPage", lambda v: 1 if "구역 전" in str(v) else 2 if "구역 후" in str(v) else 3 if "전/후" in str(v) else 0),
    "글꼴 크기": ("FontSize", int), "글꼴 두께": ("FontWeight", lambda v: 700 if "굵게" in str(v) or str(v) == "700" else 400),
    "control_source": ("ControlSource", str), "format": ("Format", str), "running_sum": ("RunningSum", _running),
    "hide_duplicates": ("HideDuplicates", _bool), "tab_index": ("TabIndex", int), "row_source": ("RowSource", str),
}


def _set(obj, key: str, val, warns: List[str], where: str) -> bool:
    spec = PROP.get(key)
    if not spec:
        return False
    name, conv = spec
    try:
        v = conv(val)
        if v is None:
            return False
        setattr(obj, name, v)
        return True
    except Exception as e:                                   # noqa: BLE001
        warns.append(f"{where} {key}={val}: {str(e)[:120]}")
        return False


# ── 열고 닫기 ──────────────────────────────────────────────────────────────
class Access:
    def __init__(self, path: str):
        import pythoncom
        import win32com.client as w
        pythoncom.CoInitialize()
        self.app = w.DispatchEx("Access.Application")
        try:
            self.app.Visible = False
        except Exception:                                    # noqa: BLE001
            pass
        try:
            self.app.AutomationSecurity = 1                  # msoAutomationSecurityLow — 매크로 경고 없이
        except Exception:                                    # noqa: BLE001
            pass
        self.app.OpenCurrentDatabase(path)

    def close(self):
        try:
            self.app.CloseCurrentDatabase()
        except Exception:                                    # noqa: BLE001
            pass
        try:
            self.app.Quit()
        except Exception:                                    # noqa: BLE001
            pass


def _layout():
    pos: Dict[int, Tuple[int, int]] = {}

    def nxt(sec: int, w: int = 1600, h: int = 300) -> Tuple[int, int]:
        x, y = pos.get(sec, (200, 100))
        if x + w > 10000:
            x, y = 200, y + h + 80
        pos[sec] = (x + w + 100, y)
        return x, y
    return nxt


def _split_labels(c: dict) -> List[dict]:
    """「lblA·lblB」 + 「A / B」 처럼 한 줄에 여러 레이블을 적은 설계를 나눈다."""
    names = re.split(r"[·,]", str(c.get("name") or ""))
    caps = [x.strip() for x in str(c.get("caption") or "").split(" / ")]
    if len(names) > 1 and len(caps) == len(names):
        return [dict(c, name=n.strip(), caption=cp) for n, cp in zip(names, caps)]
    return [c]


def _section_no(name: str, groups: Dict[str, int], warns: List[str], where: str) -> Optional[int]:
    s = str(name or "").strip()
    if s in SECTION:
        return SECTION[s]
    key = s.replace(" ", "").lower()
    if key in SECTION:
        return SECTION[key]
    m = re.match(r"(.+?)\s*(머리글|바닥글)", s)
    if m and m.group(1).strip() in groups:
        i = groups[m.group(1).strip()]
        return 5 + 2 * i + (0 if m.group(2) == "머리글" else 1)
    warns.append(f"{where}: 모르는 구역 「{s}」 — 본문에 놓음")
    return 0


def _groups_of(o: dict) -> List[str]:
    """보고서 그룹 필드 — grouping / sections(「X 머리글」) 에서."""
    out: List[str] = []
    g = o.get("grouping") or o.get("grouping_initial") or []
    if isinstance(g, str):
        g = [g]
    for x in g:
        f = x.get("field") if isinstance(x, dict) else str(x)
        f = re.sub(r"\s*(머리글|바닥글).*$", "", str(f or "")).strip()
        if f and f not in out:
            out.append(f)
    for s in o.get("sections") or []:
        m = re.match(r"(.+?)\s*(머리글|바닥글)", str(s))
        if m:
            f = m.group(1).strip()
            if f not in ("폼", "보고서", "페이지") and f not in out:
                out.append(f)
    return out


def make_object(acc: Access, kind: str, o: dict, warns: List[str]) -> Optional[str]:
    """폼(kind=form) 또는 보고서(kind=report) 하나를 만들어 이름으로 저장한다."""
    app = acc.app
    name = str(o.get("name") or "").strip().strip("〈〉<>")
    if not name:
        return None
    where = f"{'폼' if kind == 'form' else '보고서'} 〈{name}〉"
    obj = app.CreateForm() if kind == "form" else app.CreateReport()
    tmp = obj.Name
    rs = _get(o, "record_source", "recordSource", "레코드 원본", "source")
    if rs:
        _set(obj, "레코드 원본", rs, warns, where)
    for k in ("기본 보기", "탐색 단추", "스크롤 막대", "레코드 선택기", "구분 선"):
        v = _get(o, k)
        if v is not None:
            _set(obj, k, v, warns, where)
    dv = o.get("default_view") or o.get("defaultView")
    if dv:
        _set(obj, "기본 보기", dv, warns, where)
    groups: Dict[str, int] = {}
    if kind == "report":
        try:                                                 # 보고서 머리글·바닥글을 켠다(제목 레이블 자리)
            app.RunCommand(37)                               # acCmdReportHdrFtr
        except Exception:                                    # noqa: BLE001
            pass
        for i, f in enumerate(_groups_of(o)):
            try:
                app.CreateGroupLevel(tmp, f, True, True)
                groups[f] = i
            except Exception as e:                           # noqa: BLE001
                warns.append(f"{where} 그룹 「{f}」: {str(e)[:100]}")
    else:
        try:                                                 # 폼 머리글·바닥글을 켠다(머리글 컨트롤 자리)
            app.RunCommand(36)                               # acCmdFormHdrFtr
        except Exception:                                    # noqa: BLE001
            pass
    nxt = _layout()
    for c0 in o.get("controls") or []:
        for c in _split_labels(c0):
            ct = CTRL.get(str(c.get("type") or "").strip()) or CTRL.get(str(c.get("type") or "").replace(" ", "").lower())
            if not ct:
                warns.append(f"{where}: 모르는 컨트롤 종류 「{c.get('type')}」 — 건너뜀")
                continue
            sec = _section_no(c.get("section"), groups, warns, where)
            x, y = nxt(sec, 1000 if ct == 100 else 1600)
            try:
                ctl = app.CreateControl(tmp, ct, sec, "", "", x, y, 1000 if ct == 100 else 1600, 300) if kind == "form" \
                    else app.CreateReportControl(tmp, ct, sec, "", "", x, y, 1000 if ct == 100 else 1600, 300)
            except Exception as e:                           # noqa: BLE001
                warns.append(f"{where} {c.get('name')}: 만들지 못함 — {str(e)[:100]}")
                continue
            nm = str(c.get("name") or "").strip()
            if nm and not nm.startswith("("):
                try:
                    ctl.Name = nm
                except Exception as e:                       # noqa: BLE001
                    warns.append(f"{where} 이름 {nm}: {str(e)[:80]}")
            if c.get("caption") and ct in (100, 104, 122):
                try:
                    ctl.Caption = str(c["caption"])
                except Exception:                            # noqa: BLE001
                    pass
            src = c.get("control_source") or c.get("source")
            if src and ct not in (100, 104) and "언바운드" not in str(src):
                _set(ctl, "컨트롤 원본", src, warns, f"{where} {nm}")
            for k, v in list((c.get("props") or {}).items()) + list((c.get("properties") or {}).items()) + \
                    [(k, c[k]) for k in ("format", "running_sum", "hide_duplicates", "tab_index", "row_source") if k in c]:
                _set(ctl, k, v, warns, f"{where} {nm}")
    t = AC_FORM if kind == "form" else AC_REPORT
    app.DoCmd.Close(t, tmp, AC_SAVE_YES)
    try:
        app.DoCmd.Rename(name, t, tmp)
    except Exception as e:                                   # noqa: BLE001
        warns.append(f"{where} 이름 바꾸기: {str(e)[:100]}")
        return tmp
    return name


# ── 정답 반영 ──────────────────────────────────────────────────────────────
SUB_RE = re.compile(r"Private\s+Sub\s+(\w+?)_(\w+)\s*\(", re.I)


def apply_answers(acc: Access, made: Dict[str, str], items: List[dict], warns: List[str]) -> int:
    """정답 속성(answer.props)과 이벤트 프로시저(코드박스)를 폼·보고서에 반영한다."""
    app, n = acc.app, 0
    by_obj: Dict[str, List[Tuple[str, Any]]] = {}
    for it in items:
        a = it.get("answer") or {}
        for p in a.get("props") or []:
            obj = str(p.get("object") or "").strip().strip("〈〉<>")
            if obj in made:
                by_obj.setdefault(obj, []).append(("prop", p))
        for b in it.get("boxes") or []:
            t = str(b.get("text") or "")
            if SUB_RE.search(t):
                objs = [o for o in (it.get("objects") or []) if o in made] or [o for o in made if o in (it.get("lead") or "")]
                if objs:
                    by_obj.setdefault(objs[0], []).append(("code", t))
    for obj, ops in by_obj.items():
        kind = made[obj]
        t = AC_FORM if kind == "form" else AC_REPORT
        try:
            (app.DoCmd.OpenForm if kind == "form" else app.DoCmd.OpenReport)(obj, AC_DESIGN)
            o = app.Forms(obj) if kind == "form" else app.Reports(obj)
        except Exception as e:                               # noqa: BLE001
            warns.append(f"정답 〈{obj}〉 열기: {str(e)[:100]}")
            continue
        for what, x in ops:
            if what == "prop":
                ctl_name = str(x.get("control") or "").strip()
                prop = str(x.get("property") or "").strip()
                target = o
                gm = re.match(r"(그룹화|정렬)\s*기준\s*(.+)", ctl_name) or re.match(r"(그룹화|정렬)\s*기준", prop)
                if kind == "report" and gm:                  # 그룹화·정렬 기준 — 그룹 수준을 더한다
                    fld = (gm.group(2) if gm.lastindex and gm.lastindex >= 2 else str(x.get("value") or "")).strip()
                    try:
                        app.CreateGroupLevel(obj, fld, gm.group(1) == "그룹화", gm.group(1) == "그룹화")
                        n += 1
                    except Exception as e:                   # noqa: BLE001
                        warns.append(f"정답 〈{obj}〉 {gm.group(0)}: {str(e)[:80]}")
                    continue
                sm = re.match(r"(.+?)\s*(머리글|바닥글)$", ctl_name)
                if kind == "report" and sm and sm.group(1) not in ("페이지", "보고서"):   # 그룹 머리글·바닥글 구역 속성
                    try:
                        idx = None
                        for i in range(10):
                            try:
                                if str(o.GroupLevel(i).ControlSource) == sm.group(1).strip():
                                    idx = i
                                    break
                            except Exception:            # noqa: BLE001
                                break
                        if idx is None:
                            raise ValueError("그룹 없음")
                        target = o.Section(5 + 2 * idx + (0 if sm.group(2) == "머리글" else 1))
                    except Exception as e:                   # noqa: BLE001
                        warns.append(f"정답 〈{obj}〉 구역 {ctl_name}: {str(e)[:80]}")
                        continue
                elif ctl_name and ctl_name not in (obj, "폼", "보고서", "(폼)", "(보고서)"):
                    try:
                        target = o.Controls(ctl_name)
                    except Exception:                        # noqa: BLE001
                        if prop in ("캡션", "글꼴 크기", "글꼴 두께") and ctl_name.lower().startswith("lbl"):
                            try:                             # 정답에서 새로 만드는 레이블(「lbl제목 을 추가하시오」)
                                c = (app.CreateControl if kind == "form" else app.CreateReportControl)(
                                    obj, 100, 1, "", "", 200, 100, 4000, 400)
                                c.Name = ctl_name
                                target = c
                            except Exception as e:           # noqa: BLE001
                                warns.append(f"정답 〈{obj}〉 {ctl_name} 만들기: {str(e)[:80]}")
                                continue
                        else:
                            warns.append(f"정답 〈{obj}〉 컨트롤 {ctl_name} 없음 — 사람 작업")
                            continue
                if _set(target, prop, x.get("value"), warns, f"정답 〈{obj}〉 {ctl_name}"):
                    n += 1
            else:
                try:
                    o.HasModule = True
                    o.Module.AddFromString(x)
                    n += 1
                except Exception as e:                       # noqa: BLE001
                    warns.append(f"정답 〈{obj}〉 코드: {str(e)[:100]}")
        app.DoCmd.Close(t, obj, AC_SAVE_YES)
    return n


def add_ui(path: str, parts: Dict[int, dict], answer: bool, warns: List[str]) -> Dict[str, Any]:
    """문제(answer=False) 또는 정답(answer=True) 파일에 폼·보고서를 넣는다."""
    acc = Access(path)
    made: Dict[str, str] = {}
    try:
        for p in (2, 3, 4):
            g = (parts.get(p) or {}).get("given") or {}
            for kind, key in (("form", "forms"), ("report", "reports")):
                for o in g.get(key) or []:
                    nm = str(o.get("name") or "").strip().strip("〈〉<>")
                    if not nm or nm in made:
                        continue
                    try:
                        got = make_object(acc, kind, o, warns)
                        if got:
                            made[got] = kind
                    except Exception as e:                   # noqa: BLE001
                        warns.append(f"{kind} 〈{nm}〉: {str(e)[:160]}")
        applied = 0
        if answer:
            items = [it for p in (2, 3) for it in (parts.get(p) or {}).get("items") or []]
            applied = apply_answers(acc, made, items, warns)
    finally:
        acc.close()
    return {"forms": [k for k, v in made.items() if v == "form"],
            "reports": [k for k, v in made.items() if v == "report"], "applied": applied}
