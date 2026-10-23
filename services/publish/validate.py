"""발행 사전점검 — 실측 기반 규칙.

error 는 우회 불가, warn 만 force_ignore_warnings 로 통과시킨다.

이 점검은 읽기 전용이고 그 자체로 유용하다. 그래서 발행 화면에서 가장 먼저 만들고
가장 위에 둔다 — 무엇이 아직 준비되지 않았는지가 한 화면에서 보여야 한다.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET

from core.constants import AXBUILD_DIR, AXEXAM_DIR, PD_CODE
from services.book import index as bindex, lesson, md, paths, rounds, shape, verify
from services.render import bundles as rbundles

# pd 코드 검증 — _boot.php / exam_lib/problem.php 의 정규식과 같아야 한다.
import re
_PD_RE = re.compile(r"^[a-z0-9\-]{1,20}$")
# pr_key 검증 — ex_valid_key() / ex_valid_pr_key() 의 정규식. 어긋나면 채점이
# 조용히 0점이 된다(오류가 아니라 무응답 처리).
_PR_KEY_RE = re.compile(r"^m\d{2}-\d{1,2}#\d{1,3}$")


def _want_bundles() -> int:
    """이 폴더가 내야 하는 번들 수 — 회차 수를 폴더에서 읽는다.

    ★ 상수 24 로 고정하면 21회차 SQLD 나 1회차만 들어온 신규 책에서 항상 실패한다.
    """
    return len(paths.all_bundles())


def _chk(gid: str, cid: str, level: str, label: str, ok: bool, detail: str = "") -> dict:
    return {"group": gid, "id": cid, "level": level, "label": label,
            "ok": bool(ok), "detail": detail}


def _difficulty_target(n_r: int):
    """(목표 개수, 허용치) — 시험정보의 `difficulty.round_target` 을 회차 문항수에 맞춘다.

    ★ 시험정보 값은 **그 시험의 회차 문항수 기준**이다(빅분기 80, SQLD 50).
      실제 회차가 그보다 적거나 많을 수 있으므로 비율로 바꿔 다시 곱한다.
    """
    try:
        from services.authoring import parts

        d = parts.active() or {}
        rt = ((d.get("difficulty") or {}).get("round_target") or {})
        base = parts.round_size(d) or 0
        if rt and base > 0:
            tgt, tol = {}, {}
            for k in ("상", "중", "하"):
                v = rt.get(k)
                lo, hi = (v if isinstance(v, (list, tuple)) and len(v) == 2 else (v, v))
                mid = (float(lo) + float(hi)) / 2 / base
                half = max(0.02, (float(hi) - float(lo)) / 2 / base)
                tgt[k] = round(n_r * mid)
                tol[k] = max(3, round(n_r * half))
            return tgt, tol
    except Exception:                                        # noqa: BLE001
        pass
    # 되돌림 — 빅분기 실측 비율
    return ({"상": round(n_r * .375), "중": round(n_r * .55), "하": round(n_r * .0875)},
            {"상": max(4, round(n_r * .05)), "중": max(6, round(n_r * .08)),
             "하": max(3, round(n_r * .04))})


def check_questions() -> list[dict]:
    out: list[dict] = []
    items = bindex.cached_items()
    docs = rounds.load_all()

    # 회차별 80문항 · 결번 없음
    for rc in paths.round_codes():
        doc = docs.get(rc)
        if not doc:
            out.append(_chk("questions", f"q.round.{rc}", "error",
                            f"{rc} 회차 파일 존재", False,
                            f"_rounds/{rc}.json 이 없습니다."))
            continue
        qs = doc.get("questions") or []
        nos = [int(q.get("question_no", 0)) for q in qs]
        # ★ 기대 문항 수를 상수로 두지 않는다. 회차마다 다를 수 있고(집필 중인
        #   마지막 회차), 책마다 다르다(빅분기 80 · SQLD 50). 이 회차의 실제 수를
        #   기준으로 "1..N 결번·중복 없음" 만 본다 — 그게 실제로 검사할 값이다.
        n = len(qs)
        out.append(_chk("questions", f"q.count.{rc}", "error",
                        f"{rc} 문항 있음", n > 0, f"현재 {n}개"))
        out.append(_chk("questions", f"q.gaps.{rc}", "error",
                        f"{rc} 번호 1~{n} 결번·중복 없음",
                        n > 0 and sorted(nos) == list(range(1, n + 1)),
                        f"중복 {len(nos) - len(set(nos))}개 · "
                        f"번호 {min(nos) if nos else 0}~{max(nos) if nos else 0}"))

    # 보기 4개 · 정답 범위 · subject_no 정수
    bad_choices = [i["id"] for i in items if i["n_choices"] != 4]
    out.append(_chk("questions", "q.choices_4", "error", "모든 문항 보기 4개",
                    not bad_choices, ", ".join(bad_choices[:10])))

    bad_ans = [i["id"] for i in items
               if not isinstance(i["answer_index"], int)
               or not 0 <= i["answer_index"] < i["n_choices"]]
    out.append(_chk("questions", "q.answer_range", "error", "정답 번호 범위 정상",
                    not bad_ans, ", ".join(bad_ans[:10])))

    bad_subj = [i["id"] for i in items
                if not isinstance(i["subject_no"], int) or i["subject_no"] < 1]
    out.append(_chk("questions", "q.subject_no_int", "error",
                    "subject_no 가 1 이상의 정수",
                    not bad_subj,
                    (", ".join(bad_subj[:10]) + " — 문자열이면 웹의 과목 필터가 "
                     "통째로 깨집니다(build_check 의 과목 N종 리포트는 이걸 못 잡습니다).")
                    if bad_subj else ""))

    # 과목 — 개수를 못박지 않는다(SQLD 는 2과목, 빅분기는 4과목).
    # 검사할 값은 "과목이 하나로 뭉개지지 않았는가" 다. 실제 사고가 그것이었다:
    # subject_no 가 문자열이면 웹의 subjects 가 빈 배열이 되고 전 행 sj_no=0 이 된다.
    subjects = sorted({(i["subject_no"], i["subject"]) for i in items})
    out.append(_chk("questions", "q.subject_count", "error",
                    f"과목 {len(subjects)}종 (2종 이상)", len(subjects) >= 2,
                    " / ".join(f"{n}:{s}" for n, s in subjects)
                    + ("  ← 과목이 1종이면 subject 폴백 버그입니다."
                       if len(subjects) < 2 else "")))

    # ★ 미검수 — **경고**다(오류가 아니다).
    #
    #   검수는 이 앱의 존재 이유이지만, 막아야 할 대상은 "깨진 데이터" 다.
    #   미검수는 데이터가 멀쩡한데 사람이 아직 안 본 것이라, 오류로 두면
    #   **검수 전에는 발행 자체를 못 한다.** 실제로 720문항을 앞에 두고 막혔다 —
    #   영상·링크·빌드가 다 준비됐는데 오류 하나로 절차가 서 버렸다.
    #
    #   경고로 두면 빌드가 한 번 더 묻는다("경고 N건이 있습니다. 확인한 뒤 다시 누르면
    #   진행합니다"). 그 한 번이 필요한 마찰의 전부다 — 모르고 지나칠 수는 없고,
    #   알고 결정하면 나갈 수 있다.
    unrev = [i["id"] for i in items if not i["reviewed"]]
    out.append(_chk("questions", "q.needs_review", "warn", "미검수 문항 없음",
                    not unrev,
                    (f"{len(unrev)}문항이 아직 미검수입니다 (예: {', '.join(unrev[:5])}). "
                     "발행은 됩니다 — 검수 전 상태로 나간다는 것만 알고 진행하세요. "
                     "회차 단위로 검수하고 부분 임포트로 올리면 나눠서 갈 수 있습니다.")
                    if unrev else ""))

    # 그림 파일
    miss_svg = []
    for i in items:
        if not i["has_figure"]:
            continue
        rc = paths.round_code(i["round"])
        q = rounds.question_of(docs.get(rc) or {}, i["question_no"])
        for name in ((q and [a.get("name") for a in (q.get("assets") or [])]) or []):
            name = (name or "").removesuffix(".svg")
            p = paths.q_svg(name)
            if not name or paths.size(p) == 0:
                miss_svg.append(f"{i['id']}:{name}")
    out.append(_chk("questions", "q.figure_svg", "error", "그림 SVG 전부 존재",
                    not miss_svg, ", ".join(miss_svg[:10])))

    # 바이트 충실도 — 02/md 와 05/lesson 이 _rounds 와 일치하는가
    v = verify.run_all()
    # 위치 언팩을 쓰지 않는다 — 그룹이 늘면(실제로 _rounds 가 늘었다) 조용히 깨진다.
    g = v["by_kind"]
    rnd_g, md_g, idx_g, les_g = g["rounds"], g["md"], g["index"], g["lesson"]
    out.append(_chk("questions", "q.rounds_format", "error",
                    "_rounds/*.json 서식 재현 가능 (저장이 파일 전체를 다시 쓴다)",
                    rnd_g["fail_count"] == 0 and rnd_g["total"] > 0,
                    "; ".join(f"{f['id']}: {f.get('error', '')}"
                              for f in rnd_g["fail"][:4])))
    out.append(_chk("questions", "q.md_sync", "error", "02/*.md 가 _rounds 와 일치",
                    md_g["fail_count"] == 0 and md_g["missing_count"] == 0,
                    f"불일치 {md_g['fail_count']}건 · 없음 {md_g['missing_count']}건"))
    out.append(_chk("questions", "q.lesson_sync", "error",
                    "05/lesson 이 _rounds 와 일치 (본문이 웹에 가는 경로)",
                    les_g["fail_count"] == 0 and les_g["missing_count"] == 0,
                    f"불일치 {les_g['fail_count']}건 · 없음 {les_g['missing_count']}건"))
    out.append(_chk("questions", "q.index_sync", "error",
                    "02/_index.json · difficulty_stats.json 최신",
                    idx_g["ok"] == idx_g["total"],
                    "재색인 버튼으로 고칠 수 있습니다."))

    # ── warn ──
    for rc in paths.round_codes():
        rows = [i for i in items if paths.round_code(i["round"]) == rc]
        if not rows:
            continue
        dist = {}
        for r in rows:
            dist[r["answer"]] = dist.get(r["answer"], 0) + 1
        # 정답 균형은 그 회차의 실제 문항 수 기준이다.
        want = len(rows) // 4
        ok = all(abs(dist.get(g, 0) - want) <= 2 for g in "①②③④")
        out.append(_chk("questions", f"q.answer_balance.{rc}", "warn",
                        f"{rc} 정답 분포 각 {want}±2", ok,
                        " ".join(f"{g}{dist.get(g, 0)}" for g in "①②③④")))
        ddist = {}
        for r in rows:
            ddist[r["difficulty"]] = ddist.get(r["difficulty"], 0) + 1
        # 목표 난이도 비율을 **그 회차 문항 수에 비례**해 잡는다. 24/44/12 로 못박으면
        # 80문항 회차만 맞고 50문항 책에서는 늘 경고가 뜬다.
        #
        # ★ 목표 비율은 **시험정보에서** 온다 — `difficulty.round_target` 이 정본이다.
        #   여기 박아 두면 품목마다 갈린다: 빅분기는 상 28~32(37%)인데 SQLD 는
        #   상 12~16(28%)이다. 상수로 두면 SQLD 20회차 전부 경고가 뜨고, 항상 뜨는
        #   경고는 읽지 않게 되어 정말 편중된 회차도 같이 지나간다.
        #   시험정보를 못 읽으면 옛 비율(빅분기 실측)로 떨어진다.
        n_r = len(rows)
        tgt, tol = _difficulty_target(n_r)
        ok_d = all(abs(ddist.get(k, 0) - tgt[k]) <= tol[k] for k in tgt)
        out.append(_chk("questions", f"q.difficulty_mix.{rc}", "warn",
                        f"{rc} 난이도 "
                        + " · ".join(f"{k}{tgt[k]}±{tol[k]}" for k in ("상", "중", "하")),
                        ok_d, " ".join(f"{k}{v}" for k, v in ddist.items())))

    # 고아 SVG
    used = set()
    for rc, meta, q in rounds.all_questions():
        for a in q.get("assets") or []:
            n = (a.get("name") if isinstance(a, dict) else str(a)) or ""
            used.add((n if n.endswith(".svg") else n + ".svg"))
    orphan = []
    adir = paths.q_assets_dir()
    if os.path.isdir(adir):
        orphan = [f for f in sorted(os.listdir(adir))
                  if f.endswith(".svg") and f not in used]
    out.append(_chk("questions", "q.orphan_svg", "warn", "쓰이지 않는 SVG 없음",
                    not orphan, ", ".join(orphan[:10])))

    # SVG 파싱
    bad_svg = []
    if os.path.isdir(adir):
        for f in sorted(os.listdir(adir)):
            if not f.endswith(".svg"):
                continue
            try:
                root = ET.parse(os.path.join(adir, f)).getroot()
                if not root.tag.endswith("svg"):
                    bad_svg.append(f)
            except Exception:
                bad_svg.append(f)
    out.append(_chk("questions", "q.svg_wellformed", "warn", "SVG 파싱 정상",
                    not bad_svg, ", ".join(bad_svg[:10])))

    # 낭독문 정답번호
    from services.book import derive
    bad_speech = []
    for rc, meta, q in rounds.all_questions():
        r = derive.check_speech(q)
        if r and r["code"] == "speech_answer":
            bad_speech.append(paths.qid(int(meta["round"]), int(q["question_no"])))
    out.append(_chk("questions", "q.speech_answer", "warn",
                    "낭독문 정답번호가 보기 정답과 일치", not bad_speech,
                    ", ".join(bad_speech[:10])))

    drift = lesson.speech_drift()
    out.append(_chk("questions", "q.speech_drift", "warn",
                    "05 lesson 낭독문이 _rounds 와 동일", not drift,
                    (", ".join(d["id"] for d in drift[:6])
                     + " — TTS 손질로 보입니다. 낭독문을 직접 고치지 않는 한 유지됩니다.")
                    if drift else ""))
    return out


def check_videos() -> list[dict]:
    out: list[dict] = []
    rows = rbundles.scan_all()
    by_code = {r["code"]: r for r in rows}

    per = ", ".join(f"{rc} {paths.bundles_in_round(rc)}개"
                    for rc in paths.round_codes())
    out.append(_chk("videos", "v.bundle_count", "error",
                    f"번들 {_want_bundles()}개 ({per})",
                    len(rows) == _want_bundles(), f"현재 {len(rows)}개"))

    broken = [r["code"] for r in rows if not r["ok_1to1"]]
    out.append(_chk("videos", "v.deck_scene_1to1", "error",
                    "deck 슬라이드 = 캡처 씬 (1:1)", not broken,
                    ", ".join(broken[:10])))

    no_mp4 = [r["code"] for r in rows if not r["mp4"]["exists"]]
    out.append(_chk("videos", "v.mp4_exists", "error", "mp4 전부 존재", not no_mp4,
                    ", ".join(no_mp4[:10])))

    small = [f"{r['code']}({r['mp4']['bytes']}B)" for r in rows
             if r["mp4"]["exists"] and r["mp4"]["bytes"] < 1024 * 1024]
    out.append(_chk("videos", "v.mp4_size", "error", "mp4 크기 1MB 이상", not small,
                    ", ".join(small[:10])))

    no_vtt, bad_vtt = [], []
    for r in rows:
        if not r["vtt"]["exists"]:
            no_vtt.append(r["code"])
            continue
        try:
            with open(paths.bundle_vtt(r["code"]), encoding="utf-8") as f:
                if not f.readline().startswith("WEBVTT"):
                    bad_vtt.append(r["code"])
        except OSError:
            bad_vtt.append(r["code"])
    out.append(_chk("videos", "v.vtt_exists", "error", "자막(.ko.vtt) 전부 존재",
                    not no_vtt, ", ".join(no_vtt[:10])))
    out.append(_chk("videos", "v.vtt_header", "error", "자막 첫 줄이 WEBVTT",
                    not bad_vtt, ", ".join(bad_vtt[:10])))

    no_rv = [r["code"] for r in rows if not r["review"]["exists"]]
    out.append(_chk("videos", "v.review_exists", "error", "review.json 전부 존재",
                    not no_rv, ", ".join(no_rv[:10])))
    zero = [r["code"] for r in rows
            if r["review"]["exists"] and not (r["review"]["total_seconds"] or 0) > 0]
    out.append(_chk("videos", "v.review_duration", "error", "영상 길이 > 0",
                    not zero, ", ".join(zero[:10])))

    # ── warn ──
    not_ftyp = []
    for r in rows:
        if not r["mp4"]["exists"]:
            continue
        try:
            with open(paths.bundle_mp4(r["code"]), "rb") as f:
                if b"ftyp" not in f.read(16):
                    not_ftyp.append(r["code"])
        except OSError:
            not_ftyp.append(r["code"])
    out.append(_chk("videos", "v.mp4_playable", "warn", "mp4 헤더에 ftyp 박스",
                    not not_ftyp, ", ".join(not_ftyp[:10])))

    stale = [r["code"] for r in rows if r["status"] == "stale"]
    out.append(_chk("videos", "v.mp4_fresh", "warn",
                    "mp4 가 deck·lesson 보다 새롭다", not stale,
                    (", ".join(stale) + " — 문항이나 deck 을 고친 뒤 아직 렌더하지 "
                     "않았습니다. 문항 데이터만 넘길 거면 무시해도 됩니다.")
                    if stale else ""))

    mismatch = [r["code"] for r in rows
                if r["review"]["slides"] is not None and r["review"]["slides"] != r["scenes"]]
    out.append(_chk("videos", "v.review_slides", "warn", "review 슬라이드 수 = 씬 수",
                    not mismatch, ", ".join(mismatch[:10])))
    return out


def check_youtube() -> list[dict]:
    """영상 매핑 — mp4 를 서버에 올리지 않고 외부 링크(드라이브·유튜브)로 나간다.

    ★ 파일 위치는 **한 곳에서만 정한다** — `ytmap.path()`(= buildcheck.youtube_map_path()).
      빌더가 앱 안으로 들어와 그 `ROOT` 가 이 저장소라, 매핑도 이 앱의 `data/` 에 있다.
      예전에는 이 함수가 `_ref/axexam/data/` 를 봤다. 그래서 빌드 카드 배지(옳은 경로)와
      사전점검(틀린 경로)이 서로 다른 파일을 보고 한쪽만 "없음" 이라고 했다.

    ★ 품목별로 파일이 갈리는 것은 **빌더가 원래 하는 일**이다(`youtube_map_path(pd_id)`).
      번들 키(m01-1…)가 SQLD 와 겹치기 때문인데, 상류가 이미 해결해 두었으므로
      패치는 필요 없다. 예전 문구에 "axexam 패치 1번이 필요합니다" 가 남아 있었다.
    """
    from services.publish import ytmap
    out: list[dict] = []
    path = ytmap.path()

    if not os.path.isfile(path):
        out.append(_chk("youtube", "y.map_exists", "error", "영상 매핑 파일 존재", False,
                        f"{path} 가 없습니다 — 발행 화면의 [영상 매핑 만들기] 를 누르면 "
                        f"번들 {_want_bundles()}개 골격이 생깁니다(라벨·길이까지 채웁니다)."))
        return out

    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        out.append(_chk("youtube", "y.map_parse", "error", "유튜브 매핑 파싱", False, str(e)))
        return out

    # 실측 스키마: {"_note":…, "_provider":"youtube", "videos": {"m01-1": {id,label,sec}, …}}
    entries = doc.get("videos") or {}
    want = set(paths.all_bundles())
    missing_keys = sorted(want - set(entries))
    empty = sorted(k for k, v in entries.items()
                   if k in want and not (v or {}).get("id"))
    out.append(_chk("youtube", "y.keys", "error", f"번들 {_want_bundles()}개 항목 존재",
                    not missing_keys, ", ".join(missing_keys[:10])))
    out.append(_chk("youtube", "y.ids", "error", "유튜브 ID 전부 입력됨",
                    not empty,
                    (f"{len(empty)}개 비어 있음: {', '.join(empty[:8])} — "
                     "영상을 유튜브에 올리고 URL 의 v= 값을 넣어야 합니다.")
                    if empty else ""))
    return out


def check_summaries() -> list[dict]:
    out: list[dict] = []
    missing = [k for k in paths.summary_keys() if not os.path.isfile(paths.summary_html(k))]
    out.append(_chk("summaries", "s.four_files", "error",
                    f"요약노트 HTML {len(paths.summary_keys())}종 존재", not missing,
                    ", ".join(missing)))
    no_md = [k for k in paths.summary_keys() if not os.path.isfile(paths.summary_md(k))]
    out.append(_chk("summaries", "s.md_pair", "warn", "요약노트 .md 짝 존재",
                    not no_md, ", ".join(no_md)))
    stale = [k for k in paths.summary_keys()
             if os.path.isfile(paths.summary_md(k))
             and paths.mtime(paths.summary_html(k)) < paths.mtime(paths.summary_md(k))]
    out.append(_chk("summaries", "s.html_fresh", "warn",
                    ".html 이 .md 보다 새롭다", not stale,
                    (", ".join(stale) + " — .md 를 고쳤지만 .html 은 다시 만들어지지 "
                     "않았습니다. 발행되는 것은 .html 입니다.") if stale else ""))
    out.append(_chk("summaries", "s.index", "warn", "summary_index.html 존재",
                    os.path.isfile(paths.summary_index_html())))
    return out


def _active_pd() -> str:
    """지금 작업 폴더의 품목 코드. 없으면 빈 문자열(상수로 되돌리지 않는다)."""
    try:
        from services.publish import buildcheck
        return buildcheck.active_pd()
    except Exception:                                        # noqa: BLE001
        return ""


def check_server() -> list[dict]:
    """서버 전제 — 우리가 확인할 수 있는 것만. 나머지는 체크리스트로 넘긴다."""
    out: list[dict] = []
    # ★ 품목은 **활성 폴더**에서 읽는다. `core.constants.PD_CODE` 는 .env 기본값이라
    #   SQLD 폴더로 작업해도 「pd=bigdata」 로 통과한다 — 형식 검사가 다른 품목의
    #   코드를 보고 OK 를 내는 셈이다(2026-08-26).
    pd = _active_pd()
    out.append(_chk("server", "p.pd_format", "error",
                    f"품목 코드 형식 (pd={pd or '없음'})", bool(pd and _PD_RE.match(pd)),
                    "소문자·숫자·하이픈 20자 이내. 언더바는 안 됩니다. "
                    "비어 있으면 작업 폴더의 _book.json 에 pd 가 없는 것입니다."))

    keys, dup = [], []
    seen = set()
    for b in paths.all_bundles():
        lo, hi = paths.bundle_range(b)
        for n in range(lo, hi + 1):
            k = f"{b}#{n}"
            keys.append(k)
            if k in seen:
                dup.append(k)
            seen.add(k)
    bad = [k for k in keys if not _PR_KEY_RE.match(k)]
    out.append(_chk("server", "p.pr_key_format", "error",
                    "pr_key 가 서버 정규식을 통과", not bad,
                    (", ".join(bad[:6]) + " — ex_valid_key() 를 통과하지 못하면 "
                     "채점이 오류 없이 0점이 됩니다.") if bad else ""))
    out.append(_chk("server", "p.pr_key_unique", "error", "pr_key 중복 없음",
                    not dup, ", ".join(dup[:6]))),

    # ★ **빌더를 본다. 참고용 클론이 아니다.**
    #   전에는 `AXEXAM_DIR`(`_ref/axexam`)의 build_check.py 를 error 로 봤는데,
    #   그 폴더는 웹 소스를 들여다볼 때만 쓰는 자리다 — `core/constants.py` 가
    #   "발행 빌드에는 **필요하지 않다**" 라고 못박아 두었고, 빌더는 2026-08-04 에
    #   subtree 로 저장소 안(`AXBUILD_DIR`)에 들어왔다. 그래서 멀줦한 폴더에서
    #   발행이 「axexam 저장소 클론됨」 error 로 막혔다(2026-08-25 실측).
    builder = os.path.join(AXBUILD_DIR, "build_check.py")
    out.append(_chk("server", "p.axbuild", "error", "발행 빌더 있음",
                    os.path.isfile(builder),
                    f"{builder} 가 없습니다 — axexam subtree 가 빠졌습니다."))
    out.append(_chk("server", "p.axexam", "warn", "axexam 웹 소스 클론(선택)",
                    os.path.isfile(os.path.join(AXEXAM_DIR, "scripts",
                                                "build_check.py")),
                    f"{AXEXAM_DIR} 에 없습니다 — 발행에는 필요 없고, PHP·web/ 원본을 "
                    "들여다볼 때만 씁니다."))

    # 디스크 여유 — 06/ 산출물은 작지만(mp4 를 안 담는다) 그래도 확인한다.
    try:
        import shutil
        free = shutil.disk_usage(paths.book_dir()).free
        out.append(_chk("server", "p.disk_free", "warn", "디스크 여유 1GB 이상",
                        free > 1024 ** 3, f"{free / 1024 ** 3:.1f} GB"))
    except Exception:
        pass
    return out


GROUP_LABELS = {
    "questions": "문항",
    "videos": "영상",
    "youtube": "유튜브 매핑",
    "summaries": "요약노트",
    "server": "서버 전제",
}


# ★ **발행은 2단계다** (2026-08-25 운영 결정).
#
#     1차 «문제집»  문항이 준비되면 먼저 나간다. 영상·요약노트를 기다리지 않는다.
#     2차 «영상»    슬라이드 → 렌더 → 유튜브 업로드가 끝난 뒤 마저 나간다.
#
#   전에는 게이트가 하나여서, 영상이 한 편이라도 없으면 **문항까지 못 나갔다.**
#   임포트는 DELETE 를 하지 않으므로(`problem.php`) 1차를 먼저 올려도 2차가 덮어쓴다.
#   빌더도 영상 없이 도는 것을 이미 전제한다(`build_check.py`: "없으면 영상 없음").
#
#   범위마다 **무엇을 보는가**만 다르다. 검사 자체는 하나뿐이다 — 범위별로 다른
#   검사를 쓰면 1차에서 통과한 것이 2차에서 다른 이유로 막힌다.
SCOPES = {
    "problems": ("문제집 (1차)", ("questions", "server")),
    "all": ("전체 (2차 — 영상까지)", ("questions", "videos", "youtube",
                                     "summaries", "server")),
}
DEFAULT_SCOPE = "all"


def scope_groups(scope: str) -> tuple:
    return SCOPES.get(scope, SCOPES[DEFAULT_SCOPE])[1]


def run(scope: str = DEFAULT_SCOPE) -> dict:
    if not paths.exists():
        return {"ok": False, "error":
                f"이 작업 폴더에는 아직 문항이 없습니다: {paths.book_dir()}"
                " — _rounds/ 와 02/ 가 있는 폴더로 전환하세요."}

    if scope not in SCOPES:
        scope = DEFAULT_SCOPE
    want = scope_groups(scope)

    checks = (check_questions() + check_videos() + check_youtube()
              + check_summaries() + check_server())
    groups = []
    for gid, label in GROUP_LABELS.items():
        rows = [c for c in checks if c["group"] == gid]
        # ★ 범위 밖 그룹은 **지우지 않고 세지만 않는다.** 화면이 "2차에 무엇이
        #   남았는지" 를 같이 보여줘야 사람이 다음을 안다.
        if gid not in want:
            groups.append({
                "key": gid, "label": label, "checks": rows,
                "errors": 0, "warnings": 0, "out_of_scope": True,
                "pending": sum(1 for c in rows if not c["ok"]),
            })
            continue
        groups.append({
            "key": gid, "label": label, "checks": rows,
            "errors": sum(1 for c in rows if c["level"] == "error" and not c["ok"]),
            "warnings": sum(1 for c in rows if c["level"] == "warn" and not c["ok"]),
        })
    errors = sum(g["errors"] for g in groups)
    warnings = sum(g["warnings"] for g in groups)
    items = bindex.cached_items()
    return {
        "ok": errors == 0,
        "scope": scope,
        "scope_label": SCOPES[scope][0],
        "scopes": [{"key": k, "label": v[0]} for k, v in SCOPES.items()],
        "pending_next": sum(g.get("pending", 0) for g in groups
                            if g.get("out_of_scope")),
        "errors": errors,
        "warnings": warnings,
        "groups": groups,
        "counts": {
            "questions": len(items),
            "reviewed": sum(1 for i in items if i["reviewed"]),
            "videos": _want_bundles(),
            "figures": sum(1 for i in items if i["has_figure"]),
            "subjects": len({i["subject_no"] for i in items}),
            "rounds": len({i["round"] for i in items}),
        },
        "pd": _active_pd() or PD_CODE,
    }
