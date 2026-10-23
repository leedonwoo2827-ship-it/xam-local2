"""영상 매핑 파일(`data/youtube_map.<pd>.json`) 만들기·동기화.

빌더에 `--init-youtube-map` 이 있지만 앱이 노출하지 않아서, 사람이 72줄을 손으로
쓰거나 명령줄을 따로 열어야 했다. 발행 절차에서 **가장 손이 많이 가는 칸**이라
화면에 붙인다.

★ `id` 는 **절대 건드리지 않는다.** 이 파일은 사람이 채우는 입력이다.
  다시 눌러도 안전해야 한다 — 번들이 늘면 빈 항목만 추가하고, 이미 채운 ID 는 남긴다.
  (빌더의 init 은 "이미 있으면 아무것도 안 함" 이라 회차가 늘어난 뒤에는 쓸 수 없다.)

★ 이름이 youtube_map 이지만 유튜브 전용이 아니다. `_provider` 로 갈린다 —
  drive(구글 드라이브)·youtube·vimeo·file·link. 드라이브로 시작해 나중에 유튜브로
  옮길 수 있다: 항목별 `provider` 가 파일 전역 `_provider` 를 이긴다.

★ 두 종류를 한 파일에서 다룬다. `videos` 는 **회차 번들**(m01-1 … 72개), `theory` 는
  **과목별 이론 강의**(1 … 4)다. 발행 때 챙길 파일을 늘리지 않으려고 같은 파일에 둔다
  (빌더 `build_check.theory_videos()` 가 읽는다).
  이론 쪽은 `min_level` 이 없다 — 링크가 공개 `theory.js` 에 실린다.
"""
from __future__ import annotations

import json
import os
import re

from core import atomic_io
from services.book import paths
from services.publish import buildcheck

# 빌더 `PROVIDERS` 와 같아야 한다. 모르는 값을 쓰면 화면이 유튜브로 오인해
# 빈 iframe 이 뜨고 원인이 안 보인다(빌더도 그래서 죽인다).
PROVIDERS = ("youtube", "drive", "vimeo", "file", "link")


def path() -> str:
    return buildcheck.youtube_map_path()


def _label(bundle: str) -> str:
    """`m01-1` → `1회 1~10번`. 빌더 `_bundles()` 의 라벨 규칙을 따른다.

    문제 번호 범위는 05/lesson 에서 읽는다 — 상수로 두면 chunk 가 바뀔 때 어긋난다.
    """
    m = re.match(r"m(\d+)-(\d+)$", bundle)
    rn = int(m.group(1)) if m else 0
    part = int(m.group(2)) if m else 0
    nums: list[int] = []
    lp = paths.bundle_lesson(bundle)
    try:
        with open(lp, encoding="utf-8") as f:
            doc = json.load(f)
        for b in doc.get("blocks") or []:
            n = b.get("number")
            if isinstance(n, int):
                nums.append(n)
    except (OSError, ValueError):
        pass
    if nums:
        return f"{rn}회 {min(nums)}~{max(nums)}번"
    return f"{rn}회 {part}부" if part else f"{rn}회"


def _length(bundle: str) -> int:
    """렌더된 영상의 **전체 길이**(초). 화면에 보여 주기만 한다.

    ★ 이 값을 매핑의 `sec` 에 넣으면 안 된다. `sec` 은 길이가 아니라 **시작 초**다 —
      axexam 의 `check.js` 가 `embedUrl()` 에서 `"&start=" + (v.sec|0)` 로 쓴다.
      길이를 넣으면 모든 영상이 끝에서 시작해 빈 화면처럼 보인다.
      (실제로 그렇게 채우려다 잡았다. 필드 이름만 보고 길이라고 읽기 쉽다.)
    """
    p = os.path.join(paths.bundle_dir(bundle), "review.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return 0
    for k in ("totalSeconds", "videoSec", "durSec"):
        v = d.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return int(round(v))
    return 0


def _question_starts(bundle: str) -> list[dict]:
    """문항별 시작 초 — `review.json` 의 슬라이드에서 뽑는다.

    아직 웹으로 나가지 않는다. `check.js` 의 `sec` 은 **번들 하나에 시작점 하나**라서,
    문항별로 뛰려면 웹·빌더 스키마를 늘려야 한다(추후 과제).
    여기서는 화면에 보여 주고, 그때가 오면 이 값을 쓴다.

    시간축은 이미 영상 기준으로 맞춰져 있다(`timebase: "video"`) — 2026-08-03 에
    crossfade 겹침 보정을 넣었다. 그래서 `startSec` 을 그대로 시크에 쓸 수 있다.
    """
    bdir = paths.bundle_dir(bundle)
    # 문항번호는 review.json 에 없다 — script.json 의 씬이 들고 있다(`number`·`kind`).
    # 둘은 `image` 로 맞붙는다(같은 슬라이드 파일명).
    starts: dict[str, float] = {}
    try:
        with open(os.path.join(bdir, "review.json"), encoding="utf-8") as f:
            for s in json.load(f).get("slides") or []:
                img, st = s.get("image"), s.get("startSec")
                if img and isinstance(st, (int, float)):
                    starts[img] = st
    except (OSError, ValueError):
        return []

    scenes: list[dict] = []
    try:
        import glob
        cand = glob.glob(os.path.join(bdir, "script", "*_script.json"))
        if not cand:
            return []
        with open(cand[0], encoding="utf-8") as f:
            scenes = json.load(f).get("scenes") or []
    except (OSError, ValueError):
        return []

    out: list[dict] = []
    for sc in scenes:
        # 문항의 '시작' 은 문제가 뜨는 슬라이드다(정답·카운트다운이 아니라).
        if sc.get("kind") != "problem":
            continue
        n = sc.get("number")
        st = starts.get(sc.get("image"))
        if not isinstance(n, int) or st is None:
            continue
        if not out or out[-1]["number"] != n:
            out.append({"number": n, "startSec": int(round(st))})
    return out


def subjects() -> list[dict]:
    """03/ 요약노트에서 **과목 번호·이름**을 읽는다 — 이론 영상의 키가 이 번호다.

    번호를 상수로 두지 않는 이유는 요약노트 키와 같다(`paths.summary_keys()` 참조):
    과목 수·이름은 책마다 사람이 정한다. 빅분기는 4과목이지만 SQLD 는 2과목이다.

    판정 규칙은 빌더 `build_check.build_theory()` 안의 `subject_of()` 와 **같아야 한다** —
    갈리면 화면에는 1과목 버튼이 뜨는데 빌드가 2과목에 붙이는 식이 된다.
    번호를 못 읽은 파일(빌더의 99과목)은 이론 영상 대상이 아니라 버린다.
    """
    out: list[dict] = []
    for key in paths.summary_keys():
        try:
            with open(paths.summary_html(key), encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        m = (re.search(r"<h1[^>]*>([^<]*)</h1>", raw)
             or re.search(r"<title>([^<]*)</title>", raw))
        mm = re.search(r"(\d+)\s*과목\s*[·:\-—\s]*(.*)", (m.group(1) if m else "").strip())
        if not mm:
            continue
        out.append({"sub": int(mm.group(1)), "name": mm.group(2).strip(" —-·"), "key": key})
    out.sort(key=lambda x: x["sub"])
    return out


def _theory_entry(theory: dict, sub: int) -> dict:
    """`theory` 에서 과목 항목을 꺼낸다. 빌더가 `t1` 표기도 받으므로 여기도 받는다."""
    return dict(theory.get(str(sub)) or theory.get(f"t{sub}") or {})


def prov_file(raw: dict, prov: str) -> str:
    """파일 전역 provider — 항목에 provider 가 없을 때 적용되는 값."""
    return prov or raw.get("_provider") or "youtube"


def _pd_label() -> str:
    """사람이 읽는 품목 이름 — 화면이 앱스 스크립트 코드에 박아 낸다.

    ★ 없으면 코드가 `SS_TITLE = '영상 링크목록'` 으로 나간다. 품목이 둘 이상이면
      드라이브에 같은 이름의 시트가 쌓여 어느 것이 어느 문제집인지 알 수 없다.
      `appsScriptBox()` 머리말이 "이 품목의 값으로 채워서 낸다" 고 적어 둔 그 값이다.
    """
    try:
        from services.authoring import parts
        return str((parts.active() or {}).get("label") or "").strip()
    except Exception:                                        # noqa: BLE001
        return ""


def read() -> dict:
    """현재 매핑 상태. 파일이 없어도 예외를 내지 않는다."""
    p = path()
    bundles = paths.all_bundles()
    raw: dict = {}
    exists = os.path.isfile(p)
    if exists:
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f) or {}
        except (OSError, ValueError) as e:
            return {"exists": True, "path": p, "error": f"읽을 수 없습니다: {e}",
                    "provider": "", "items": [], "bundles": len(bundles)}

    videos = raw.get("videos") or {}
    items = []
    for b in bundles:
        e = videos.get(b) or {}
        prov = (e.get("provider") or raw.get("_provider") or "youtube")
        lv = int(e.get("min_level") or 0)
        items.append({
            "bundle": b,
            "id": (e.get("id") or "").strip(),
            "label": e.get("label") or _label(b),
            "sec": e.get("sec") or 0,             # 시작 초 (길이가 아니다)
            "length": _length(b),                 # 실제 영상 길이 — 보여주기만
            "provider": prov,
            "min_level": lv,
            # 링크 자체가 접근 권한인 provider 가 공개로 나가면 유출이다.
            "leaky": prov in ("drive", "link", "file") and lv <= 1,
            "starts": _question_starts(b),        # 문항별 시작 초 (아직 웹에 안 나감)
            "missing": b not in videos,
        })
    extra = [k for k in videos if k not in set(bundles)]
    filled = sum(1 for i in items if i["id"])

    # 이론 강의 — 과목 목록은 03/ 에서, 링크는 `theory` 에서. 둘 다 없으면 빈 목록이다
    # (요약노트가 없는 품목에서는 이 칸을 아예 그리지 않는다).
    tr = raw.get("theory") or {}
    theory = []
    for s in subjects():
        e = _theory_entry(tr, s["sub"])
        theory.append({
            "sub": s["sub"], "name": s["name"], "key": s["key"],
            "id": (e.get("id") or "").strip(),
            "label": e.get("label") or f"{s['sub']}과목 이론 강의",
            "provider": e.get("provider") or raw.get("_provider") or "youtube",
            "missing": not e,
        })
    return {
        "exists": exists, "path": p,
        "pd": _pd_label(),
        "provider": raw.get("_provider") or ("youtube" if exists else ""),
        "bundles": len(bundles), "filled": filled,
        "empty": len(bundles) - filled,
        "missing": [i["bundle"] for i in items if i["missing"]],
        "extra": extra,          # 매핑에는 있는데 05/ 에는 없는 번들(예전 회차)
        "items": items,
        "theory": theory,
        "theory_total": len(theory),
        "theory_filled": sum(1 for t in theory if t["id"]),
    }


_BUNDLE_RE = re.compile(r"\bm(\d{1,2})-(\d{1,2})\b")
# 드라이브·유튜브 ID 는 10자 이상의 영숫자·`-`·`_` 다. URL 이든 맨 ID 든 이걸로 잡는다.
_ID_RE = re.compile(r"[A-Za-z0-9_-]{10,}")
# URL 안에서 ID 가 앉는 자리들 — 이게 있으면 우선한다(파일명이 먼저 잡히는 것을 막는다).
_URL_ID_RE = re.compile(
    r"(?:/file/d/|[?&]id=|youtu\.be/|[?&]v=|/embed/|/shorts/|/d/)([A-Za-z0-9_-]{10,})")
# 이론 줄에서 과목을 가리키는 표기들. 렌더 파일명(`1summary-planning.mp4`)이 먼저다 —
# 사람이 파일 목록을 그대로 붙여넣기 때문이다.
_SUMKEY_RE = re.compile(r"summary[-_]([A-Za-z0-9]+)", re.I)
_SUBNUM_RE = re.compile(r"\b(\d{1,2})\s*과목|\bt(\d{1,2})\b|\b(\d{1,2})summary\b", re.I)


def _id_in_line(s: str, drop: re.Pattern | None = None) -> str:
    """한 줄에서 ID 또는 URL 을 뽑는다. 못 찾으면 빈 문자열.

    URL 안의 ID 자리를 먼저 본다. 없으면 `drop`(번들코드·과목표기)과 미디어 파일명을
    지운 뒤 남는 토큰에서 찾는다 — 안 지우면 파일명 조각이 ID 로 잡힌다.
    URL 은 **그대로** 돌려준다. 빌더가 provider 를 보고 ID 를 뽑으므로 여기서 깎지 않는다.
    """
    m = _URL_ID_RE.search(s)
    if m:
        return next((t for t in s.split() if m.group(1) in t), m.group(1)).strip()
    rest = drop.sub(" ", s) if drop else s
    # `\w*` 로는 `1summary-planning.mp4` 의 앞부분이 남아 ID 후보가 된다 → `\S*` 로 통째로.
    rest = re.sub(r"\S*\.(mp4|mov|mkv|webm)\b", " ", rest, flags=re.I)
    cands = [t for t in _ID_RE.findall(rest) if not t.isdigit()]
    return max(cands, key=len).strip() if cands else ""


def _theory_sub(s: str, by_key: dict[str, int]) -> int:
    """이론 줄이 가리키는 과목 번호. 못 알아보면 0.

    파일명 키(`summary_planning`)를 03/ 의 실제 키와 맞춰 보는 것이 가장 안전하다 —
    번호는 렌더 파일명 앞자리(`1summary-`)에 붙어 있을 뿐이고 책마다 다를 수 있다.
    """
    m = _SUMKEY_RE.search(s)
    if m and m.group(1).lower() in by_key:
        return by_key[m.group(1).lower()]
    m = _SUBNUM_RE.search(s)
    if m:
        return int(next(g for g in m.groups() if g))
    return 0


def _write(p: str, doc: dict) -> None:
    """매핑 파일을 저장한다 — **그 파일이 쓰던 개행을 그대로 다시 쓴다.**

    ★ 개행을 상수로 두면 안 된다. 실측으로 두 품목이 갈린다 —
      `youtube_map.sqld-2627.json` 은 CRLF, `youtube_map.bigdata.json` 은 LF 다.
      한쪽에 맞춰 굳히면 다른 쪽이 저장 한 번에 전 줄이 바뀌고, 그러면 무엇을
      고쳤는지 diff 로 볼 수 없다(그게 이 파일에서 제일 알고 싶은 것이다).
      `core.atomic_io` 머리말이 같은 이유로 같은 규칙을 적어 두었다.
    """
    nl = atomic_io.file_newline(p) or atomic_io.LF
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    atomic_io.atomic_write_text(p, atomic_io.with_newline(text, nl))


def _swap_bytes(p: str, data: bytes) -> None:
    """바이트를 원자적으로 갈아 끼운다 — 되돌리기가 바이트 단위여야 하기 때문이다."""
    tmp = f"{p}.tmp.{os.getpid()}"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _verdict(now: str, new: str) -> str:
    """이 줄이 무엇을 하는가 — 새로 채움 / 갈아끼움 / 이미 같음."""
    if not now:
        return "new"
    return "same" if now == new else "replace"


def _dups(rows: list[dict]) -> dict:
    """붙여넣기 사고의 두 가지 모양.

    ★ 이 검사가 왜 필요한가
      파서가 한 줄 안에서 번들코드와 ID 를 함께 찾으므로 "한 줄 밀림" 은 이미 막혀
      있다. 남는 실수는 **목록을 잘못 옮겨 붙이는 것**이고, 그건 늘 이 두 모양으로
      나타난다. 영상이 엉뚱한 회차에 붙으면 영상을 봐야 알 수 있어서 되돌리기가 비싸다.

      ids      같은 ID 가 두 자리 이상에 붙었다 — 한 영상이 두 번들일 수는 없다.
      targets  같은 자리에 서로 다른 ID 가 두 번 왔다 — 어느 쪽이 이길지 보이지 않는다.

    같은 줄을 두 번 붙여넣은 것(자리도 ID 도 같다)은 사고가 아니라서 세지 않는다.
    """
    by_id: dict[str, list[str]] = {}
    by_target: dict[str, list[str]] = {}
    for r in rows:
        by_id.setdefault(r["new_id"], []).append(r["target"])
        ids = by_target.setdefault(r["target"], [])
        if r["new_id"] not in ids:
            ids.append(r["new_id"])
    return {
        "ids": [{"id": k, "targets": sorted(set(v))}
                for k, v in by_id.items() if len(set(v)) > 1],
        "targets": [{"target": k, "ids": v}
                    for k, v in by_target.items() if len(v) > 1],
    }


def parse_text(text: str) -> dict:
    """붙여넣은 목록의 판정 — **아무것도 쓰지 않는다.**

    ★ 파싱과 쓰기를 나눈 이유
      예전에는 파싱한 결과를 그대로 파일에 썼고 백업도 없었다. 그래서 무엇이 바뀌는지
      누르기 전에 볼 수 없었고, 잘못 넣으면 되돌릴 방법이 없었다. 번들이 72개(SQLD 는
      100개)라 그 위험이 실질적이다. 넣기 전에 보고, 넣은 뒤 되돌릴 수 있어야 한다.

    한 줄에서 **번들코드**(m01-1)와 **ID/URL** 을 각각 찾아 맞춘다. 그래서 형식이
    느슨해도 된다 — 아래 전부 같은 결과가 된다:

        m01-1.static.mp4    1AbCdEf...
        m01-1  https://drive.google.com/file/d/1AbCdEf.../view?usp=sharing
        "m01-1.static.mp4","1AbCdEf..."
        m01-1 -> https://youtu.be/dQw4w9WgXcQ

    **이론 강의**도 같은 칸에서 받는다. 번들코드가 없으면 과목 표기를 찾는다 —
    렌더 파일명이 그대로 통한다(`_theory_sub()`):

        1summary-planning.mp4  https://drive.google.com/file/d/1AbCdEf.../view
        2과목  https://drive.google.com/file/d/...
        t3 -> https://youtu.be/dQw4w9WgXcQ

    둘 다 아닌 줄은 건너뛰고 그 줄을 돌려준다(조용히 버리지 않는다).
    URL 을 그대로 싣는다 — 빌더가 provider 를 보고 ID 를 뽑으므로 여기서 깎지 않는다.
    """
    p = path()
    if not os.path.isfile(p):
        raise ValueError("매핑 파일이 없습니다 — [영상 매핑 만들기] 를 먼저 누르세요.")
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    videos: dict = raw.get("videos") or {}
    theory: dict = raw.get("theory") or {}
    known = set(paths.all_bundles())
    subs = subjects()
    by_key = {s["key"].lower(): s["sub"] for s in subs}
    name_of = {s["sub"]: s["name"] for s in subs}

    rows: list[dict] = []
    skipped: list[str] = []
    unknown: list[str] = []
    unknown_theory: list[int] = []

    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        mb = _BUNDLE_RE.search(s)
        if not mb:
            # 번들이 아니면 이론 줄인지 본다. 과목 표기도 없으면 건너뛴다.
            sub = _theory_sub(s, by_key)
            if not sub:
                skipped.append(s[:80])
                continue
            if sub not in name_of:
                unknown_theory.append(sub)
                continue
            vid = _id_in_line(s, _SUBNUM_RE)
            if not vid:
                skipped.append(s[:80])
                continue
            now = (_theory_entry(theory, sub).get("id") or "").strip()
            rows.append({"kind": "theory", "target": str(sub),
                         "label": f"{sub}과목 · {name_of[sub]}",
                         "now_id": now, "new_id": vid,
                         "verdict": _verdict(now, vid), "line": s[:80]})
            continue
        bundle = f"m{int(mb.group(1)):02d}-{int(mb.group(2))}"
        if bundle not in known:
            unknown.append(bundle)
            continue
        vid = _id_in_line(s, _BUNDLE_RE)
        if not vid:
            skipped.append(s[:80])
            continue
        e = videos.get(bundle) or {}
        now = (e.get("id") or "").strip()
        rows.append({"kind": "bundle", "target": bundle,
                     "label": e.get("label") or _label(bundle),
                     "now_id": now, "new_id": vid,
                     "verdict": _verdict(now, vid), "line": s[:80]})

    counts = {"new": 0, "replace": 0, "same": 0}
    for r in rows:
        counts[r["verdict"]] += 1
    return {
        "path": p, "rows": rows, "counts": counts, "dup": _dups(rows),
        "unknown": sorted(set(unknown)),
        "unknown_theory": sorted(set(unknown_theory)),
        "skipped": skipped[:10], "skipped_total": len(skipped),
    }


def apply_text(text: str, *, force: bool = False) -> dict:
    """판정대로 `id` 를 채운다. **쓰기 전에 `.bak` 를 남긴다.**

    `force` 없이는 `dup` 가 있으면 쓰지 않는다 — 그 상태로 쓰면 어느 쪽이 이겼는지
    파일을 봐도 알 수 없다.
    """
    plan = parse_text(text)
    d = plan["dup"]
    if not force and (d["ids"] or d["targets"]):
        bits = []
        for x in d["ids"][:3]:
            bits.append("ID {}… → {}".format(x["id"][:16], "·".join(x["targets"])))
        for x in d["targets"][:3]:
            bits.append("{} 에 ID {}개".format(x["target"], len(x["ids"])))
        raise ValueError("같은 것이 두 자리에 붙었습니다 — 목록을 확인하세요.\n"
                         + "\n".join(bits))
    if not plan["rows"]:
        raise ValueError("알아볼 수 있는 줄이 없습니다. 한 줄에 번들코드(m01-1)와 "
                         "ID/URL 이 함께 있어야 합니다.")

    p = plan["path"]
    with open(p, encoding="utf-8") as f:
        raw = json.load(f)
    videos: dict = raw.get("videos") or {}
    theory: dict = raw.get("theory") or {}
    name_of = {s["sub"]: s["name"] for s in subjects()}

    filled, t_filled, overwrote = [], [], []
    for r in plan["rows"]:
        if r["verdict"] == "replace":
            overwrote.append(r["target"] if r["kind"] == "bundle"
                             else r["target"] + "과목")
        if r["kind"] == "theory":
            sub = int(r["target"])
            e = _theory_entry(theory, sub)
            e["id"] = r["new_id"]
            e.setdefault("label", f"{sub}과목 · {name_of.get(sub, '')} 강의")
            # `t1` 로 적혀 있던 항목은 정규 키로 옮긴다 — 두 표기가 같이 남으면
            # 빌더가 둘 다 읽어 나중 것이 이긴다(어느 쪽이 이겼는지 보이지 않는다).
            theory.pop(f"t{sub}", None)
            theory[str(sub)] = e
            t_filled.append(sub)
        else:
            e = dict(videos.get(r["target"]) or {})
            e["id"] = r["new_id"]
            e.setdefault("label", _label(r["target"]))
            e.setdefault("sec", 0)
            videos[r["target"]] = e
            filled.append(r["target"])

    raw["videos"] = videos
    if theory:
        raw["theory"] = theory
    backed = atomic_io.backup_sibling(p)
    _write(p, raw)

    st = read()
    st["matched"] = sorted(set(filled))
    st["matched_theory"] = sorted(set(t_filled))
    st["overwrote"] = sorted(set(overwrote))
    st["unknown"] = plan["unknown"]
    st["unknown_theory"] = plan["unknown_theory"]
    st["skipped"] = plan["skipped"]
    st["backup"] = (p + ".bak") if backed else ""
    return st


def fill_from_text(text: str) -> dict:
    """붙여넣은 목록으로 `id` 를 한 번에 채운다 — 판정한 뒤 바로 쓴다."""
    return apply_text(text)


def restore() -> dict:
    """직전 반입을 되돌린다 — `.bak` 와 현재 파일을 **맞바꾼다.**

    맞바꾸는 이유: 되돌린 뒤 "아니 그게 맞았다" 가 되면 한 번 더 눌러 돌아올 수
    있어야 한다. 한쪽으로만 복원하면 되돌리기 자체가 되돌릴 수 없는 동작이 된다.
    """
    p = path()
    b = p + ".bak"
    if not os.path.isfile(b):
        raise ValueError(f"되돌릴 것이 없습니다 — {b} 가 없습니다.")
    # ★ 바이트로 다룬다. 텍스트로 읽으면 파이썬이 CRLF 를 LF 로 접어 버려서
    #   "되돌렸는데 파일이 원본과 다르다" 가 된다(실측: SQLD 매핑이 CRLF).
    with open(b, "rb") as f:
        prev = f.read()
    cur = b""
    if os.path.isfile(p):
        with open(p, "rb") as f:
            cur = f.read()
    _swap_bytes(p, prev)
    if cur:
        _swap_bytes(b, cur)
    st = read()
    st["restored"] = True
    return st


def sync(provider: str = "") -> dict:
    """없으면 만들고, 있으면 빠진 항목만 채운다. **id 는 보존한다.**

    번들(`videos`)과 이론 강의(`theory`) 둘 다 만든다. 이론은 03/ 요약노트에서 읽은
    과목만 — 요약노트가 없는 품목이면 `theory` 키 자체를 만들지 않는다.

    provider 를 주면 파일 전역 `_provider` 를 그 값으로 바꾼다(빈 값이면 유지).
    """
    prov = (provider or "").strip()
    if prov and prov not in PROVIDERS:
        raise ValueError(f"모르는 provider: {prov} — {', '.join(PROVIDERS)} 중 하나여야 합니다. "
                         "모르는 값을 쓰면 화면이 유튜브로 오인해 빈 재생창이 뜹니다.")

    bundles = paths.all_bundles()
    if not bundles:
        raise ValueError(f"05/ 에 번들이 없습니다: {paths.book_dir()} — 먼저 #2 로 05/ 를 만드세요.")

    p = path()
    raw: dict = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f) or {}
        except ValueError as e:
            raise ValueError(f"기존 매핑이 깨져 있어 덮어쓰지 않았습니다: {e}") from e

    videos: dict = dict(raw.get("videos") or {})
    added, touched = [], []
    for b in bundles:
        e = dict(videos.get(b) or {})
        new = b not in videos
        if new:
            added.append(b)
        # id 는 손대지 않는다. label·sec 은 비어 있을 때만 채운다.
        if not (e.get("id") or "").strip():
            e["id"] = e.get("id") or ""
        if not e.get("label"):
            e["label"] = _label(b)
            if not new:
                touched.append(b)
        # ★ sec 은 **시작 초**다(길이가 아니다). 기본 0 — 처음부터 재생.
        #   사람이 넣은 값이 있으면 그대로 둔다.
        e.setdefault("sec", 0)
        # 드라이브·link·file 은 링크 자체가 접근 권한이라 공개로 나가면 유출이다.
        # min_level 을 안 적었으면 5(강사)로 둔다 — 빌더가 lv<=1 이면 videos.js 에 굽는다.
        prov = (e.get("provider") or prov_file(raw, prov)).strip()
        if prov in ("drive", "link", "file") and not e.get("min_level"):
            e["min_level"] = 5
        videos[b] = {"id": e.get("id", ""), "label": e.get("label", ""),
                     "sec": e.get("sec", 0),
                     **({"provider": e["provider"]} if e.get("provider") else {}),
                     **({"min_level": e["min_level"]} if e.get("min_level") else {})}

    # 이론 강의 — 03/ 요약노트가 있는 과목만. **id 는 번들과 똑같이 보존한다.**
    # 요약노트가 없는 품목에서는 키를 만들지 않는다(빈 `theory` 를 남기지 않는다).
    theory_in: dict = dict(raw.get("theory") or {})
    theory: dict = {}
    t_added = []
    for s in subjects():
        k = str(s["sub"])
        e = _theory_entry(theory_in, s["sub"])
        if not e:
            t_added.append(s["sub"])
        theory[k] = {"id": e.get("id", ""),
                     "label": e.get("label") or f"{s['sub']}과목 · {s['name']} 강의",
                     **({"provider": e["provider"]} if e.get("provider") else {})}
    # ★ `min_level` 을 넣지 않는다. 이론 링크는 공개 `theory.js` 에 실리고
    #   api/videos.php 같은 통로가 이론 탭에는 없다 — 넣으면 지켜지는 척만 한다.

    out = {
        "_note": ("수동 관리 파일 — 빌드가 덮어쓰지 않는다. "
                  "id 에 공유 URL 을 그대로 붙여넣어도 된다(빌더가 ID 만 뽑는다)."),
        "_provider": prov or raw.get("_provider") or "youtube",
        **({"theory": theory} if theory else {}),
        "videos": videos,
    }
    for k, v in raw.items():           # 사람이 손으로 넣은 다른 키는 남긴다
        if k not in out:
            out[k] = v

    _write(p, out)

    st = read()
    st["added"] = added
    st["added_theory"] = t_added
    st["updated"] = sorted(set(touched))
    return st
