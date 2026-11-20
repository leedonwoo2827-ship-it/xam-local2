# -*- coding: utf-8 -*-
"""1부 빌드(1급 엑셀) — 문제·정답 파일을 **.xlsm** 으로 만들고 VBA(사용자 정의 함수 · 폼 · 단추 · 코드)를 넣는다.

  06/practical/mNN/mNN_문제.xlsm   폼(컨트롤 배치)과 시트의 명령 단추를 미리 둔다 — 코드는 없다(수험자가 쓴다)
  06/practical/mNN/mNN_정답.xlsm   위 + 사용자 정의 함수 모듈 · 폼 코드 · 단추 코드 · (있으면) 매크로 — 재계산해 함수 결과를 검증

★ 엑셀의 「VBA 프로젝트 개체 모델에 안전하게 액세스」(AccessVBOM=1)가 켜져 있어야 한다 — 꺼져 있으면 바로 알린다.
★ 코드는 원고의 코드박스(boxes, code=true)에서 프로시저 단위로 잘라 자리를 정한다:
    Function → 표준 모듈 · UserForm_* / 폼 컨트롤의 이벤트 → 그 폼 · 그 밖의 컨트롤 이벤트 → 단추가 놓인 시트
    · 이벤트가 아닌 Sub(매크로) → 표준 모듈. 폼 컨트롤은 설계(그림 설명) · 지시문 · 코드에 나온 이름으로 만든다.
★ 엑셀 창은 띄우지 않는다(build.py 와 같은 감싸개 _XL · 인증 실패 바로 알림).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from core.atomic_io import atomic_write_text
from services.practical import build as pb

XL_XLSM = 52
PROC_RE = re.compile(r"^[ \t]*(?:(Public|Private)\s+)?(Sub|Function)\s+([\w가-힣]+)\s*\(.*?^[ \t]*End\s+\2\b",
                     re.M | re.S | re.I)
CTL_RE = re.compile(r"\b((?:txt|cmb|lst|cmd|chk|opt|lbl|fra)[A-Za-z0-9_가-힣]+)")
CAP_RE = re.compile(r"['‘]([^'’(]+)\(((?:txt|cmb|lst|cmd|chk|opt|lbl)[A-Za-z0-9_가-힣]+)\)['’]")
FORM_RE = re.compile(r"[<〈]([^>〉]+)[>〉]\s*폼")
SHOW_RE = re.compile(r"([\w가-힣]+)\.Show\b")
PROGID = {"txt": "Forms.TextBox.1", "cmb": "Forms.ComboBox.1", "lst": "Forms.ListBox.1", "cmd": "Forms.CommandButton.1",
          "chk": "Forms.CheckBox.1", "opt": "Forms.OptionButton.1", "lbl": "Forms.Label.1", "fra": "Forms.Frame.1"}


def _codes(it: dict) -> List[str]:
    """정답 코드박스(틀만 있는 짧은 것은 빼고) — 같은 이름의 함수 틀과 완성본이 있으면 완성본."""
    out = []
    for b in it.get("boxes") or []:
        t = str(b.get("text") or "")
        if b.get("code", True) and re.search(r"\b(Sub|Function)\b", t):
            out.append(t)
    return out


def _procs(code: str) -> List[Tuple[str, str, str]]:
    """(종류 Sub|Function, 이름, 본문)."""
    return [(m.group(2).title(), m.group(3), m.group(0).strip("\n")) for m in PROC_RE.finditer(code)]


def _texts(it: dict) -> str:
    figs = " ".join(str(f.get("desc") or "") + " " + str(f.get("caption") or "") for f in it.get("figures") or [])
    return " ".join([it.get("lead") or ""] + list(it.get("instructions") or []) + [figs])


def plan_round(parts: List[dict]) -> Dict[str, Any]:
    """회차 원고에서 VBA 계획 — 모듈 · 폼(컨트롤) · 시트 단추 · 코드 자리."""
    plan = {"module": [], "forms": {}, "buttons": {}, "udf_items": []}
    for d in parts:
        for it in d.get("items") or []:
            procs: Dict[str, Tuple[str, str]] = {}
            for code in _codes(it):
                for kind, name, body in _procs(code):
                    old = procs.get(name)
                    if not old or len(body) > len(old[1]):   # 틀(짧은 것)보다 완성본(긴 것)
                        procs[name] = (kind, body)
            if not procs:
                continue
            text = _texts(it)
            caps = {c: cap.strip() for cap, c in CAP_RE.findall(text)}
            forms = [f.strip() for f in FORM_RE.findall(text)]
            for _k, body in procs.values():
                forms += SHOW_RE.findall(body)
            forms = [f for i, f in enumerate(forms) if f and f not in forms[:i] and not f.lower().startswith("userform")]
            all_code = "\n".join(b for _k, b in procs.values())
            # cmd입력_Click 같은 이벤트 이름은 컨트롤이 아니다
            ctrls = [c for c in dict.fromkeys(CTL_RE.findall(text + "\n" + all_code)) if "_" not in c]
            if any(k == "Function" for k, _b in procs.values()):
                plan["udf_items"].append(it)
            for name, (kind, body) in procs.items():
                ev = re.match(r"(.+?)_(Click|Change|DblClick|Initialize|Activate|AfterUpdate|BeforeUpdate|Exit|Enter)$", name)
                if kind == "Function" or not ev:
                    plan["module"].append(body)              # 사용자 정의 함수 · 매크로
                    continue
                obj = ev.group(1)
                if obj.lower() == "userform" and forms:
                    plan["forms"].setdefault(forms[0], {"controls": [], "code": [], "caps": {}})["code"].append(body)
                elif forms and obj in ctrls and not re.search(rf"\b{re.escape(obj)}\b.*\.Show|{re.escape(forms[0])}\.Show", body):
                    plan["forms"].setdefault(forms[0], {"controls": [], "code": [], "caps": {}})["code"].append(body)
                else:                                        # 시트의 단추 — 「대여관리」 단추가 폼을 띄운다
                    plan["buttons"][obj] = {"sheet": str(it.get("sheet") or ""), "caption": caps.get(obj) or obj[3:],
                                            "code": body}
            for f in forms:
                fd = plan["forms"].setdefault(f, {"controls": [], "code": [], "caps": {}})
                fd["caps"].update(caps)
                for c in ctrls:
                    if c not in plan["buttons"] and c not in fd["controls"]:
                        fd["controls"].append(c)
    return plan


# ── 엑셀 ───────────────────────────────────────────────────────────────────
def _open_excel():
    import pythoncom
    import win32com.client as w
    import win32gui
    pythoncom.CoInitialize()
    raw = w.DispatchEx("Excel.Application")
    cap = ""
    try:
        cap = win32gui.GetWindowText(int(raw.Hwnd))
    except Exception:                                        # noqa: BLE001
        pass
    if "인증 실패" in cap:
        raw.Quit()
        raise RuntimeError(f"엑셀이 「{cap}」 상태입니다 — 오피스 인증 뒤 다시.")
    xl = pb._XL(raw)
    xl.Visible = False
    xl.DisplayAlerts = False
    return xl


def _design_form(vbp, name: str, fd: dict, with_code: bool, warns: List[str]) -> None:
    comp = vbp.VBComponents.Add(3)                           # vbext_ct_MSForm
    try:
        comp.Name = name
    except Exception as e:                                   # noqa: BLE001
        warns.append(f"폼 이름 {name}: {str(e)[:80]}")
    try:
        comp.Properties("Caption").Value = name
        comp.Properties("Width").Value = 300
        comp.Properties("Height").Value = 60 + 26 * max(4, len(fd["controls"]))
    except Exception:                                        # noqa: BLE001
        pass
    des = comp.Designer
    y, btn_x = 12, 20
    inputs = [c for c in fd["controls"] if c[:3] in ("txt", "cmb", "lst", "chk", "opt")]
    buttons = [c for c in fd["controls"] if c[:3] == "cmd"]
    for c in inputs:
        cap = fd["caps"].get(c) or c[3:]
        try:
            lb = des.Controls.Add("Forms.Label.1", "lbl_" + c)
            lb.Caption, lb.Left, lb.Top, lb.Width, lb.Height = f"{cap} :", 12, y + 2, 70, 16
            ctl = des.Controls.Add(PROGID[c[:3]], c)
            ctl.Left, ctl.Top, ctl.Width = 90, y, 170
            ctl.Height = 60 if c[:3] == "lst" else 18
            y += 66 if c[:3] == "lst" else 26
        except Exception as e:                               # noqa: BLE001
            warns.append(f"폼 {name} 컨트롤 {c}: {str(e)[:80]}")
    y += 8
    for c in buttons:
        try:
            b = des.Controls.Add("Forms.CommandButton.1", c)
            b.Caption = fd["caps"].get(c) or c[3:]
            b.Left, b.Top, b.Width, b.Height = btn_x, y, 70, 24
            btn_x += 80
        except Exception as e:                               # noqa: BLE001
            warns.append(f"폼 {name} 단추 {c}: {str(e)[:80]}")
    if with_code and fd["code"]:
        comp.CodeModule.AddFromString("\n\n".join(fd["code"]))


def _add_button(wb, sheet: str, name: str, caption: str, code: Optional[str], warns: List[str]) -> str:
    """시트의 명령 단추 — ActiveX(시험장 방식)를 먼저, 막혀 있으면 양식 컨트롤 단추 + 매크로 연결.

    ★ 2026-11-20 실측: Microsoft 365 는 ActiveX 컨트롤을 기본으로 막는다(「개체를 삽입할 수 없습니다」).
      시험장 Office 2021 은 ActiveX 단추를 「디자인 모드에서 더블클릭」 해 코드를 쓴다 — 막히면 양식 단추로 대신하고
      정답 파일에서는 같은 코드를 표준 모듈의 Public Sub 로 두고 단추에 연결한다(동작은 같다).
    """
    try:
        ws = wb.Worksheets(sheet[:31])
    except Exception:                                        # noqa: BLE001
        ws = wb.Worksheets(wb.Worksheets.Count)
        warns.append(f"단추 {name}: 시트 「{sheet}」 없음 — 마지막 시트에 둠")
    used = ws.UsedRange
    anchor = ws.Cells(2, used.Column + used.Columns.Count + 1)
    try:
        ole = ws.OLEObjects().Add(ClassType="Forms.CommandButton.1", Left=anchor.Left, Top=anchor.Top, Width=90, Height=26)
        ole.Name = name
        ole.Object.Caption = caption
        if code:
            wb.VBProject.VBComponents(ws.CodeName).CodeModule.AddFromString(code)
        return "activex"
    except Exception:                                        # noqa: BLE001
        pass
    try:
        b = ws.Buttons().Add(anchor.Left, anchor.Top, 90, 26)
        b.Name = name
        b.Caption = caption
        if code:
            pub = re.sub(r"^\s*Private\s+Sub", "Public Sub", code, count=1, flags=re.I | re.M)
            mod = wb.VBProject.VBComponents.Add(1)
            mod.CodeModule.AddFromString(pub)
            b.OnAction = re.search(r"Sub\s+([\w가-힣]+)", pub).group(1)
        warns.append(f"단추 {name}: ActiveX 가 막혀 양식 컨트롤 단추로 넣음(시험장은 ActiveX)")
        return "form"
    except Exception as e:                                   # noqa: BLE001
        warns.append(f"단추 {name}: {str(e)[:100]}")
        return ""


def build_round_vba(m: int, log=lambda s: None) -> Dict[str, Any]:
    od = pb.out_dir(m)
    parts = pb.load_round(m)
    plan = plan_round(parts)
    warns: List[str] = []
    res: Dict[str, Any] = {"round": m, "forms": list(plan["forms"]), "buttons": list(plan["buttons"]),
                           "module_procs": len(plan["module"]), "udf": []}
    xl = _open_excel()
    try:
        for kind in ("문제", "정답"):
            src = os.path.join(od, f"m{m:02d}_{kind}.xlsx")
            if not os.path.isfile(src):
                raise FileNotFoundError(f"{os.path.basename(src)} 이 없습니다 — 1부 빌드를 먼저.")
            wb = xl.Workbooks.Open(src)
            try:
                vbp = wb.VBProject
                vbp.VBComponents.Count                       # AccessVBOM 이 꺼져 있으면 여기서 거부된다
            except Exception as e:                           # noqa: BLE001
                wb.Close(False)
                raise RuntimeError("엑셀 「VBA 프로젝트 개체 모델에 안전하게 액세스」 가 꺼져 있습니다 — 켠 뒤 다시.") from e
            answer = kind == "정답"
            for name, fd in plan["forms"].items():
                _design_form(vbp, name, fd, answer, warns)
            for name, bd in plan["buttons"].items():
                _add_button(wb, bd["sheet"], name, bd["caption"], bd["code"] if answer else None, warns)
            if answer and plan["module"]:
                mod = vbp.VBComponents.Add(1)                # 표준 모듈
                mod.CodeModule.AddFromString("\n\n".join(plan["module"]))
            dst = os.path.join(od, f"m{m:02d}_{kind}.xlsm")
            if os.path.exists(dst):
                os.remove(dst)
            wb.SaveAs(dst, XL_XLSM)
            if answer:                                       # 사용자 정의 함수 결과 검증
                xl.CalculateFull()
                for it in plan["udf_items"]:
                    try:
                        ws = wb.Worksheets(str(it.get("sheet") or "")[:31])
                        r = pb.check_item(ws, it)
                    except Exception as e:                   # noqa: BLE001
                        r = {"status": "오류", "fails": [str(e)[:100]]}
                    res["udf"].append({"no": f"{it.get('part', '')}-{it.get('no')}", "status": r.get("status"),
                                       "checked": r.get("checked"), "ok": r.get("ok"), "fails": (r.get("fails") or [])[:3]})
            wb.Close(False)
    finally:
        try:
            xl.Quit()
        except Exception:                                    # noqa: BLE001
            pass
    # verify.json 의 사용자 정의 함수 문항을 새 결과로 고친다 · .xlsx 는 치운다(1급은 .xlsm)
    vf = os.path.join(od, "verify.json")
    if os.path.isfile(vf):
        try:
            with open(vf, encoding="utf-8") as fh:
                v = json.load(fh)
            udf_by_no = {str(u["no"]).split("-")[-1]: u for u in res["udf"]}
            for item in v.get("items") or []:
                stem = str(item.get("id") or "")
                udf = next((u for u in res["udf"] if stem.endswith(f"-{int(str(u['no']).split('-')[-1]):02d}")
                            and str(item.get("sheet") or "") == next((str(i.get("sheet")) for i in plan["udf_items"]
                                                                       if str(i.get("no")) == str(u["no"]).split("-")[-1]), "")), None)
                if udf and item.get("status") == "불일치":
                    item["status"] = udf["status"]
                    item["vba"] = True
            v["vba"] = res
            atomic_write_text(vf, json.dumps(v, ensure_ascii=False, indent=1, default=str))
        except Exception as e:                               # noqa: BLE001
            warns.append(f"verify.json 갱신: {e}")
    for kind in ("문제", "정답"):
        x = os.path.join(od, f"m{m:02d}_{kind}.xlsx")
        if os.path.isfile(os.path.join(od, f"m{m:02d}_{kind}.xlsm")) and os.path.isfile(x):
            os.remove(x)
    res["warnings"] = warns
    n_ok = sum(1 for u in res["udf"] if u["status"] == "통과")
    res["summary"] = (f"폼 {len(plan['forms'])} · 시트 단추 {len(plan['buttons'])} · 모듈 프로시저 {len(plan['module'])} · "
                      f"함수 검증 통과 {n_ok}/{len(res['udf'])} · 경고 {len(warns)}")
    return res
