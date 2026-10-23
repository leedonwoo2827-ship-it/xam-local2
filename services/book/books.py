"""작업 폴더 — 여러 BOOK 을 지정해 두고 전환한다 (품목 전환 = 폴더 권한).

Claude Code 데스크탑이 폴더에 권한을 주는 방식을 그대로 따른다. OS 네이티브
폴더 선택창을 띄워 사용자가 고른 폴더만 쓴다. 로컬 단일 사용자 앱이라 비밀번호는
두지 않는다 — 권한의 단위는 "어느 폴더를 보여줄지" 다.

기억은 data/books.json 에 남긴다:
  {"active": "D:/00work/ocr-output-260730",
   "items": [{"path": ..., "pd": "bigdata", "label": "빅데이터분석기사 필기"}]}

★ 회차 수를 하드코딩하지 않는다. _rounds/*.json 을 스캔해서 세므로 3회차든 9회차든
  21회차든, 초기에 1~2회차만 있어도 그대로 뜬다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from core.atomic_io import atomic_write_json
from core.constants import BOOK_DIR, DATA_DIR, PD_CODE, PD_LABEL

STORE = os.path.join(DATA_DIR, "books.json")
STAGES = ("00", "01", "02", "03", "04", "05", "06")
_ROUND_RE = re.compile(r"^m(\d{2})\.json$")
# ex_product.pd_id 규칙 — 서버의 정규식과 같아야 한다.
_PD_RE = re.compile(r"^[a-z0-9\-]{1,20}$")


# ── 저장소 ──────────────────────────────────────────────────────────────────
def _load() -> dict:
    if os.path.isfile(STORE):
        try:
            with open(STORE, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("items"), list):
                return d
        except Exception:
            pass
    # 첫 실행 — .env 의 XAM_BOOK 을 기본 항목으로 넣어 준다
    return {"active": os.path.abspath(BOOK_DIR),
            "items": [{"path": os.path.abspath(BOOK_DIR), "pd": PD_CODE, "label": PD_LABEL}]}


def _save(d: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    atomic_write_json(STORE, d, indent=2)


def is_first_run() -> bool:
    """사람이 작업 폴더를 **한 번도 지정하지 않았는가.**

    `data/books.json` 이 있으면 지정한 적이 있다는 뜻이다. 없으면 `.env` 의
    `XAM_BOOK` 을 잠정값으로 쓰고 있을 뿐이다.

    ★ 이 구분이 필요한 이유: 첫 실행에 목록 패널이 자동으로 뜨면, 아직 아무 폴더도
      고르지 않았는데 "이미 스캔된 80문항" 이 담긴 부유 창이 먼저 보인다. 어느 폴더의
      결과인지도 모르는 목록을 닫아야 바탕이 나오니 순서가 거꾸로다.
      한 번 지정한 뒤에는 그 폴더가 그대로 먼저 뜬다 — 바꾸는 것도 언제든 된다.
    """
    return not os.path.isfile(STORE)


def active_path() -> str:
    """지금 쓰는 BOOK 경로. paths.book_dir() 이 이 값을 쓴다.

    첫 실행에도 `.env` 의 값으로 떨어진다 — 경로 조립이 빈 문자열로 깨지지 않게
    하는 안전판이다. "지정했는가" 는 is_first_run() 으로 따로 본다.
    """
    d = _load()
    p = d.get("active") or BOOK_DIR
    return os.path.abspath(p)


def active_meta() -> dict:
    p = active_path()
    for it in _load()["items"]:
        if os.path.normcase(it["path"]) == os.path.normcase(p):
            return dict(it)
    return {"path": p, "pd": PD_CODE, "label": PD_LABEL}


def active_ocr_path() -> str:
    """이 BOOK 에 딸린 OCR 판독 폴더(도구 #1 의 data/ 가 있는 곳). 미지정이면 빈 문자열.

    ★ BOOK 과 별개로 지정한다. 판독 작업물(스캔 PNG · 초안 JSON)은 BOOK 밖에 있고,
      Claude Code 창과 이 앱이 같이 쓰는 폴더다. 지정이 없으면 project.py 가
      BOOK 이름에서 유도한다 — 틀려도 "초안이 없다" 로 보일 뿐이라 안전하다.
    """
    for it in _load()["items"]:
        if os.path.normcase(it["path"]) == os.path.normcase(active_path()):
            v = (it.get("ocr") or "").strip()
            return os.path.abspath(v) if v else ""
    return ""


def _ocr_state(item: dict) -> tuple[str, bool]:
    """(실제로 쓰일 OCR 폴더, 그 폴더가 판독 폴더로 보이는가).

    지정이 없으면 BOOK 이름에서 유도한 값을 보여 준다 — 사람이 "이걸 쓸 것" 을
    확인하고 틀리면 고를 수 있게. `data/` 가 없으면 ok=False 다.
    """
    from core.constants import OCR_DIR
    p = (item.get("ocr") or "").strip() or OCR_DIR
    if not p:
        from services.ocr.project import derive_from_book
        p = derive_from_book(item["path"])
    return p, bool(p) and os.path.isdir(os.path.join(p, "data"))


def set_ocr_path(book_path: str, ocr_path: str) -> dict:
    """작업 폴더 항목에 OCR 폴더를 붙인다. 빈 문자열이면 지정을 지운다(유도로 되돌림)."""
    d = _load()
    target = os.path.normcase(os.path.abspath(book_path))
    hit = None
    for it in d["items"]:
        if os.path.normcase(os.path.abspath(it["path"])) == target:
            if ocr_path:
                it["ocr"] = os.path.abspath(ocr_path)
            else:
                it.pop("ocr", None)
            hit = it
            break
    if hit is None:
        raise ValueError(f"등록되지 않은 작업 폴더입니다: {book_path}")
    _save(d)
    return dict(hit)


# ── 폴더 스캔 ───────────────────────────────────────────────────────────────
def _count(path: str, suffix: str = "") -> int:
    if not os.path.isdir(path):
        return 0
    try:
        return sum(1 for f in os.listdir(path)
                   if (not suffix or f.endswith(suffix))
                   and os.path.isfile(os.path.join(path, f)))
    except OSError:
        return 0


def scan(path: str) -> dict:
    """폴더 하나의 현황 — 00~06 단계와 회차 목록."""
    path = os.path.abspath(path)
    out: dict[str, Any] = {"path": path, "exists": os.path.isdir(path)}
    if not out["exists"]:
        out["error"] = "폴더가 없습니다."
        out["rounds"] = []
        out["stages"] = {}
        return out

    # 회차 — _rounds/mNN.json 을 세어 동적으로 만든다
    rounds = []
    rdir = os.path.join(path, "_rounds")
    if os.path.isdir(rdir):
        for f in sorted(os.listdir(rdir)):
            m = _ROUND_RE.match(f)
            if not m:
                continue
            info = {"code": f[:-5], "round": int(m.group(1)), "questions": 0, "label": ""}
            try:
                with open(os.path.join(rdir, f), encoding="utf-8") as fh:
                    doc = json.load(fh)
                info["questions"] = len(doc.get("questions") or [])
                info["label"] = doc.get("round_label") or ""
            except Exception:
                info["error"] = "읽을 수 없습니다."
            rounds.append(info)

    stages = {}
    for st in STAGES:
        d = os.path.join(path, st)
        rec: dict[str, Any] = {"exists": os.path.isdir(d)}
        if st == "00":
            rec["pdf"] = _count(d, ".pdf")
        elif st in ("01", "02"):
            rec["md"] = _count(d, ".md")
            rec["assets"] = _count(os.path.join(d, "assets"), ".svg")
        elif st == "03":
            rec["html"] = _count(d, ".html")
            rec["md"] = _count(d, ".md")
        elif st == "04":
            rec["json"] = _count(d, ".json")
        elif st == "05":
            try:
                rec["bundles"] = len([x for x in os.listdir(d)
                                      if os.path.isdir(os.path.join(d, x))]) if rec["exists"] else 0
            except OSError:
                rec["bundles"] = 0
            # 렌더된 mp4 개수
            n = 0
            if rec["exists"]:
                for b in os.listdir(d):
                    mp4 = os.path.join(d, b, "draft", f"{b}.static.mp4")
                    if os.path.isfile(mp4):
                        n += 1
            rec["mp4"] = n
        elif st == "06":
            rec["files"] = _count(d)
        stages[st] = rec

    out["rounds"] = rounds
    out["stages"] = stages
    out["questions"] = sum(r.get("questions", 0) for r in rounds)
    out["subjects"] = _subjects(path, rounds)

    # ★ 어느 단계까지 온 폴더인지. "완성된 책" 만 쓸 수 있게 하면 안 된다 —
    #   #1 로 01/ 만 만들어 놓고 #2 를 돌리기 직전인 폴더가 정상적인 작업 상태다.
    # ★ 그 앞에 **00/ 에 원본 PDF 만 있는 폴더**가 있다. 새 문제집은 거기서 시작한다 —
    #   [PDF 렌더] 가 읽는 곳이 바로 이 폴더의 00/ 이기 때문이다
    #   (services/ocr/project.py 의 pdf_dir → book_dir()/00).
    #   예전에는 01/ 을 바깥 도구가 만들어 왔으므로 00/ 만 있는 폴더를 거절해도
    #   말이 됐다. 지금은 그 판독을 이 앱에서 하므로, 거절하면 **새 문제집을 등록할
    #   방법 자체가 없다** — 바깥 폴더를 골라도 "작업할 것이 없습니다" 가 뜨고,
    #   00/ 을 대신 골라도 그 안엔 pdf 뿐이라 똑같이 막힌다.
    has_raw = stages["00"]["pdf"] > 0
    has_scan = stages["01"]["md"] > 0
    has_edit = os.path.isdir(rdir) and stages["02"]["md"] > 0
    has_video = stages["05"]["bundles"] > 0
    out["can"] = {"ocr": has_raw, "scan": has_scan, "edit": has_edit,
                  "video": has_video, "publish": has_edit and has_video}
    out["stage"] = ("video" if has_video else "edit" if has_edit
                    else "scan" if has_scan else "raw" if has_raw else "empty")
    # 00/ 에 PDF 하나만 있어도 쓸 수 있다. 정말 빈 폴더일 때만 거절한다.
    out["usable"] = has_raw or has_scan or has_edit or os.path.isdir(rdir)
    return out


def _subjects(path: str, rounds: list) -> list[str]:
    """책을 식별하는 근거 — 과목명. pd 를 추측하지 않기 위해 사람에게 보여줄 값이다."""
    names: set[str] = set()
    rdir = os.path.join(path, "_rounds")
    for r in rounds:
        try:
            with open(os.path.join(rdir, r["code"] + ".json"), encoding="utf-8") as f:
                for q in (json.load(f).get("questions") or []):
                    s = (q.get("subject") or "").strip()
                    if s:
                        names.add(s)
        except Exception:
            continue
    if not names:      # _rounds 가 없으면 01/ 의 front matter 에서 긁는다
        try:
            d = os.path.join(path, "01")
            for f in sorted(os.listdir(d))[:400]:
                if not f.endswith(".md"):
                    continue
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    dashes = 0
                    for line in fh:
                        if line.startswith("subject:"):
                            names.add(line.split(":", 1)[1].strip())
                            break
                        # front matter 는 --- 두 줄 사이다. 닫는 --- 를 만나면 그만 읽는다.
                        # (파일마다 세어야 한다 — 누적 상태로 판단하면 두 번째 파일부터
                        #  여는 --- 에서 바로 끊겨 과목이 한 개만 잡힌다.)
                        if line.startswith("---"):
                            dashes += 1
                            if dashes >= 2:
                                break
        except OSError:
            pass
    return sorted(names)


def _guess(path: str) -> tuple[str, str]:
    """폴더 안 _book.json 에서 pd 와 품목명을 읽는다.

    ★ pd 를 폴더 이름으로 추측하지 않는다. pd 는 발행 때 --pd 로 나가서 **어느 라이브
      품목을 덮어쓸지** 정하는 값이다. 한 번 틀리면 그 품목의 pr_key 가 겹치는 행을
      UPDATE 하고 pr_id 는 보존되므로, 회원 오답노트 밑에 엉뚱한 문제가 앉는다.
      되돌릴 수 없다.

      실제로 그 사고가 났다. 폴더 이름 "260723" 을 sqld 로 추측했는데 그 폴더에는
      빅데이터 책 복사본이 들어 있었다. 그래서 이름 추측 표를 지웠다.

    반환한 pd 가 빈 문자열이면 **사람이 정해야 한다**. 라벨만 내용에서 만들어 준다.
    """
    meta = os.path.join(path, "_book.json")
    if os.path.isfile(meta):
        try:
            with open(meta, encoding="utf-8") as f:
                d = json.load(f)
            pd = (d.get("pd") or "").strip()
            if _PD_RE.match(pd):
                return pd, (d.get("label") or pd).strip()
        except Exception:
            pass
    return "", _label_from_content(path)


def guess_meta(path: str) -> tuple[str, str]:
    """라우터용 공개 이름. pd 가 빈 문자열이면 사람이 정해야 한다."""
    return _guess(path)


def _label_from_content(path: str) -> str:
    """내용에서 사람이 읽을 이름을 만든다 — pd 와 달리 틀려도 안전한 값이다."""
    for sub, key in (("_rounds", "round_label"), ("01", None)):
        d = os.path.join(path, sub)
        if not os.path.isdir(d):
            continue
        try:
            for f in sorted(os.listdir(d)):
                p = os.path.join(d, f)
                if key and f.endswith(".json"):
                    with open(p, encoding="utf-8") as fh:
                        v = (json.load(fh).get(key) or "").strip()
                    if v:
                        return v
                elif not key and f.endswith(".md"):
                    with open(p, encoding="utf-8") as fh:
                        for line in fh:
                            if line.startswith("round_label:"):
                                return line.split(":", 1)[1].strip()
                            if line.startswith("source_pdf:"):
                                return line.split(":", 1)[1].strip()
                    break
        except OSError:
            continue
    return os.path.basename(path.rstrip("\\/"))


def write_meta(path: str, pd: str, label: str) -> None:
    """폴더 안에 _book.json 을 남긴다 — 폴더를 옮겨도 품목이 따라온다.

    ★ 사람이 확정한 pd 만 여기까지 온다. 추측값을 적으면 그 추측이 폴더에 굳어서
      다음부터는 "_book.json 에 있으니 맞겠지" 로 통과해 버린다.
    """
    atomic_write_json(os.path.join(path, "_book.json"),
                      {"pd": pd, "label": label}, indent=2)


# ── 목록 · 추가 · 전환 ──────────────────────────────────────────────────────
def list_books() -> dict:
    d = _load()
    act = os.path.normcase(os.path.abspath(d.get("active") or ""))
    items = []
    for it in d["items"]:
        rec = scan(it["path"])
        rec["pd"] = it.get("pd") or ""
        rec["label"] = it.get("label") or _label_from_content(it["path"])
        rec["active"] = os.path.normcase(os.path.abspath(it["path"])) == act
        # OCR 판독 폴더 — 지정값과, 지정이 없을 때 유도되는 값을 함께 준다.
        # 화면이 "지정" 과 "유도" 를 구분해 보여야 한다(유도는 틀릴 수 있다).
        rec["ocr"] = it.get("ocr") or ""
        rec["ocr_effective"], rec["ocr_ok"] = _ocr_state(it)
        # pd 가 폴더 안 _book.json 에서 확인되는가. 아니면 발행을 막는다.
        rec["pd_confirmed"] = bool(rec["pd"]) and _guess(it["path"])[0] == rec["pd"]
        items.append(rec)
    return {"active": d.get("active"), "count": len(items), "items": items,
            # 아직 사람이 지정한 적이 없으면 화면이 '지정' 부터 요구한다.
            "first_run": is_first_run()}


def add(path: str, *, pd: str = "", label: str = "") -> dict:
    """폴더를 등록한다.

    pd 를 못 정하면 등록은 하되 pd 는 비워 둔다 — 편집·렌더는 pd 없이 되고,
    발행만 막힌다. 추측한 값을 넣는 것보다 비어 있는 게 안전하다.
    """
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        raise ValueError(f"폴더가 없습니다: {path}")
    info = scan(path)
    if not info["usable"]:
        raise ValueError(
            f"이 폴더에는 작업할 것이 없습니다: {path}\n"
            "새 문제집이면 그 폴더 안에 00 폴더를 만들고 원본 PDF 를 넣은 뒤 다시 고르세요. "
            "이미 진행 중이면 01/ 에 문항 md 가 있거나 _rounds/ 가 있는 폴더입니다.")

    g_pd, g_label = _guess(path)
    pd = (pd or g_pd).strip()
    label = (label or g_label).strip() or os.path.basename(path.rstrip("\\/"))
    if pd and not _PD_RE.match(pd):
        raise ValueError(f"품목 코드 형식이 잘못됐습니다: {pd!r} "
                         "(소문자·숫자·하이픈 20자 이내, 언더바 불가)")

    d = _load()
    for it in d["items"]:
        if os.path.normcase(it["path"]) == os.path.normcase(path):
            it["pd"] = pd or it.get("pd", "")
            it["label"] = label
            _save(d)
            return {"ok": True, "added": False, "path": path, "pd": it["pd"],
                    "label": label, "stage": info["stage"]}
    d["items"].append({"path": path, "pd": pd, "label": label})
    _save(d)
    if pd:                # ★ 확정된 pd 만 폴더에 굳힌다
        try:
            write_meta(path, pd, label)
        except OSError:
                          # 폴더가 읽기 전용일 수 있다 — 등록 자체는 유지한다
            pass
    return {"ok": True, "added": True, "path": path, "pd": pd,
            "label": label, "stage": info["stage"]}


def set_meta(path: str, *, pd: str | None = None, label: str | None = None) -> dict:
    """등록된 폴더의 품목 코드·표시 이름을 고친다.

    표시 이름은 이 앱 안에서만 쓰는 값이라 자유롭게 바꿔도 된다.
    pd 는 발행 대상을 정하는 값이므로, 바꾸면 폴더의 _book.json 까지 같이 쓴다.
    """
    path = os.path.abspath(path)
    d = _load()
    for it in d["items"]:
        if os.path.normcase(it["path"]) != os.path.normcase(path):
            continue
        if label is not None:
            it["label"] = label.strip() or it.get("label") or os.path.basename(path)
        if pd is not None:
            pd = pd.strip()
            if pd and not _PD_RE.match(pd):
                raise ValueError(f"품목 코드 형식이 잘못됐습니다: {pd!r} "
                                 "(소문자·숫자·하이픈 20자 이내, 언더바 불가)")
            it["pd"] = pd
        _save(d)
        wrote = False
        if it.get("pd"):
            try:
                write_meta(path, it["pd"], it["label"])
                wrote = True
            except OSError:
                pass
        return {"ok": True, "path": path, "pd": it.get("pd", ""),
                "label": it["label"], "wrote_book_json": wrote}
    raise ValueError("등록되지 않은 폴더입니다.")


def remove(path: str) -> dict:
    d = _load()
    path_n = os.path.normcase(os.path.abspath(path))
    before = len(d["items"])
    d["items"] = [i for i in d["items"]
                  if os.path.normcase(os.path.abspath(i["path"])) != path_n]
    if not d["items"]:
        raise ValueError("마지막 폴더는 지울 수 없습니다. 다른 폴더를 먼저 추가하세요.")
    if os.path.normcase(os.path.abspath(d.get("active") or "")) == path_n:
        d["active"] = d["items"][0]["path"]
    _save(d)
    return {"ok": True, "removed": before - len(d["items"]), "active": d["active"]}


def select(path: str) -> dict:
    path = os.path.abspath(path)
    d = _load()
    if not any(os.path.normcase(i["path"]) == os.path.normcase(path) for i in d["items"]):
        raise ValueError("먼저 폴더를 추가해야 합니다.")
    if not os.path.isdir(path):
        raise ValueError(f"폴더가 없습니다: {path}")
    d["active"] = path
    _save(d)
    return {"ok": True, "active": path, "meta": active_meta()}


# ── OS 네이티브 폴더 선택창 ─────────────────────────────────────────────────
_PS_SCRIPT = r"""
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$dlg = New-Object System.Windows.Forms.FolderBrowserDialog
$dlg.Description = '문제집 폴더를 고르세요 - 00/ 01/ _rounds/ 를 담는 바깥 폴더입니다 (00/ 안이 아닙니다)'
$dlg.ShowNewFolderButton = $false
if ($args.Count -gt 0 -and (Test-Path $args[0])) { $dlg.SelectedPath = $args[0] }
if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::Out.Write($dlg.SelectedPath)
}
"""


def pick_folder(start: str = "") -> str | None:
    """OS 네이티브 폴더 선택창을 띄우고 고른 경로를 돌려준다.

    tkinter 대신 PowerShell 의 FolderBrowserDialog 를 쓴다 — 파이썬 GUI 루프를
    서버 스레드에서 돌리지 않아도 되고, 윈도우 기본 대화상자가 그대로 뜬다.
    취소하면 None.
    """
    args = ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
            "-Command", _PS_SCRIPT]
    if start and os.path.isdir(start):
        args += ["-args", start]
    try:
        r = subprocess.run(args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
    except FileNotFoundError as e:
        raise RuntimeError("PowerShell 을 찾을 수 없어 폴더 선택창을 띄우지 못했습니다. "
                           "경로를 직접 입력해 주세요.") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("폴더 선택창이 5분 동안 응답하지 않아 취소했습니다.") from e
    out = (r.stdout or "").strip()
    return out or None
