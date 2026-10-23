"""axexam 의 scripts/build_check.py 호출 + 산출물 검증.

★ --book 과 --pd 를 **항상** 명시한다. 둘 다 기본값이 SQLD 다
  (--book "D:/00work/ocr-output-260723", --pd "sqld"). 하나라도 빠지면 라이브 SQLD
  문제은행을 덮어쓴다 — pr_key 가 m01-1#1…m03-5#50 구간에서 겹치고, pr_id 가
  보존되므로 회원 오답노트 밑에 엉뚱한 문제가 들어앉는다. 되돌릴 수 없다.
  그래서 인자 없는 호출 경로를 이 모듈에 만들지 않는다.

★ 임포트 드라이런도 여기 있다. 서버 쪽 adm/exam_import.php 에는 드라이런이 없고
  트랜잭션도 없다. 분류 로직(약 15줄)을 로컬에서 재현해 무엇이 신규/갱신/건너뜀이
  될지 미리 보여준다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess

from core.constants import AXBUILD_DIR, AXEXAM_DIR, BASE_DIR, DATA_DIR
from services.book import paths
from services.jobs import registry

_PR_KEY_RE = re.compile(r"^m\d{2}-\d{1,2}#\d{1,3}$")


def builder_dir() -> str:
    """빌더가 있는 곳 — **axexam 저장소의 scripts/**.

    ★ 2026-08-04: axexam 을 git subtree 로 이 저장소 안(`axexam/`)에 합쳤다.
      그전에는 `services/publish/axbuild/` 에 **사본**을 두고 `ROOT` 한 줄만 고쳐
      썼는데, 사본이 있으면 어느 쪽을 고쳤는지 몰라 서버와 갈린다(원천이 둘).
      이제 상류 파일을 그대로 부른다 — `subtree pull` 로 갱신해도 충돌이 없다.

      그래서 빌더의 `ROOT`(= `parents[1]`)는 `axexam/` 을 가리키고,
      `data/youtube_map.<pd>.json` · `data/brand.json` 도 그 아래다.
      youtube_map_path() 가 같은 곳을 보게 맞춰 두었다.
    """
    return os.path.join(BASE_DIR, "axexam", "scripts")


def builder_script() -> str:
    return os.path.join(AXBUILD_DIR, "build_check.py")


def axexam_python() -> str:
    """빌더를 돌릴 파이썬 — **이 앱의 venv** 다.

    ★ 예전에는 axexam 저장소의 `.venv` 를 먼저 찾았다. 빌더가 안으로 들어왔으니
      우리 venv 하나로 돈다(의존성은 PyYAML 뿐이고 이미 있다).
    """
    import sys
    p = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
    return p if os.path.isfile(p) else sys.executable


def active_pd() -> str:
    """지금 고른 폴더의 품목 코드. 정해지지 않았으면 빈 문자열이다.

    ★ 상수(PD_CODE)를 그대로 넘기면 폴더를 바꿨을 때 **다른 품목의 문제은행을
      덮어쓴다**. pr_key 가 겹치고 pr_id 는 보존되므로 되돌릴 수 없다.

    ★ 비었을 때 PD_CODE 로 되돌리지 않는다. 그게 바로 "조용한 기본값" 함정이다 —
      품목을 못 정한 폴더를 그냥 bigdata 로 밀어 버린다. 빈 값을 그대로 내보내고
      require_pd() 로 발행을 막는다.
    """
    try:
        from services.book import books
        return (books.active_meta().get("pd") or "").strip()
    except Exception:
        return ""


def require_pd() -> str:
    """발행 경로에서만 쓴다 — pd 가 없으면 여기서 끊는다."""
    pd = active_pd()
    if not pd:
        raise ValueError(
            "이 작업 폴더에는 품목 코드(pd)가 정해지지 않았습니다.\n"
            "작업 폴더 화면에서 [이름·품목] 을 눌러 정한 뒤 발행하세요. "
            "품목 코드는 발행 때 --pd 로 나가서 어느 라이브 문제은행을 덮어쓸지 "
            "정하는 값이라 추측하지 않습니다.")
    return pd


def youtube_map_path() -> str:
    """품목 전용 매핑. 공용 youtube_map.json 은 SQLD 와 번들 키가 겹친다.

    ★ 빌더의 `ROOT` 아래 `data/` 다 — 즉 `axexam/data/`. 빌더가 `--pd` 로 이 파일을
      스스로 고르므로(`youtube_map_path(pd_id)`), 우리가 다른 곳을 보면 화면은
      "매핑 있음" 인데 빌드는 "영상 없음" 으로 조용히 지나간다. 한 곳만 본다.
    """
    return os.path.join(BASE_DIR, "axexam", "data", f"youtube_map.{active_pd()}.json")


def supports_youtube_map_flag() -> bool:
    """빌더가 `--youtube-map` 플래그를 받는가.

    ★ 지금 상류 빌더는 **이 플래그가 없다.** 대신 `--pd` 로
      `data/youtube_map.<pd>.json` 을 스스로 고른다(더 나은 방식이라 그대로 쓴다).
      그래서 이 함수는 보통 False 이고, 넘기지 않는 게 맞다. 플래그가 다시 생기면
      자동으로 넘어간다 — 버전을 가정하지 않는다.

    ★ **문자열 검색이 아니라 `add_argument` 정의를 본다.** 처음에는 파일 전체에서
      `"--youtube-map"` 을 찾았는데, 주석·독스트링에 그 글자가 있으면 True 가 되고
      빌드가 `unrecognized arguments` 로 죽는다. 실제로 그렇게 걸렸다 —
      내장할 때 붙인 주석 한 줄이 오탐을 만들었다.
      비슷한 이름(`--init-youtube-map`)도 있으니 정의를 정확히 맞춘다.
    """
    try:
        with open(builder_script(), encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return False
    return bool(re.search(r'add_argument\(\s*"--youtube-map"', src))


def env_info() -> dict:
    script = builder_script()
    return {
        "builder": AXBUILD_DIR,
        "axexam": AXEXAM_DIR,          # 웹 소스(참고용). 없어도 발행은 된다.
        "cloned": os.path.isfile(script),
        "script": script,
        "python": axexam_python(),
        "pd": active_pd(),
        "book": paths.book_dir(),
        "out": paths.out_dir(),
        "youtube_map": youtube_map_path(),
        "youtube_map_exists": os.path.isfile(youtube_map_path()),
        "youtube_map_flag": supports_youtube_map_flag(),
        "problems_json": paths.problems_json(),
    }


def build_args() -> list[str]:
    """실행할 명령 — 화면에도 이 문자열을 그대로 보여준다."""
    a = [axexam_python(), "build_check.py",
         # ★ 생략 금지. 그리고 상수가 아니라 **지금 고른 폴더·품목**을 넘긴다.
         #   둘 다 기본값이 SQLD 라서 하나만 빠지면 라이브 SQLD 를 덮어쓴다.
         "--book", paths.book_dir(),
         "--pd", require_pd(),
         "--api-base", "./api/",      # ApiDS 모드 + window.EXAM_PD 주입
         "--emit-json",
         "--prune"]                   # 예전 빌드의 mp4 정리 (영상은 유튜브로 나간다)
    if supports_youtube_map_flag():
        a += ["--youtube-map",
              os.path.join("data", f"youtube_map.{require_pd()}.json")]
    return a


def command_text() -> str:
    a = build_args()
    return " ".join(f'"{x}"' if " " in x else x for x in a)


# ── 빌드 잡 ─────────────────────────────────────────────────────────────────
def expected() -> dict:
    """이 폴더가 내야 하는 숫자 — 상수가 아니라 _rounds 스캔값이다.

    ★ 상수(240문항·3회차)로 어서션을 걸면 21회차 SQLD 나 1회차만 들어온 신규 책에서
      전부 실패한다. 회차 수·문항 수·과목 수를 폴더에서 읽는다.
    """
    from services.book import rounds as R
    docs = R.load_all()
    codes = sorted(docs)
    total = sum(len(docs[c].get("questions") or []) for c in codes)
    subs = {(q.get("subject") or "").strip()
            for c in codes for q in (docs[c].get("questions") or [])} - {""}
    # ★ 과목 수도 폴더값이다. 상수(4)로 떨어지면 SQLD(2과목)에서 "과목 4종" 을
    #   기대하고 어서션이 실패한다. 못 읽었으면 0 을 주고 호출자가 어서션을 건다.
    return {"rounds": len(codes), "questions": total,
            "subjects": len(subs), "codes": codes}


def assertions(exp: dict) -> list[tuple]:
    """빌드 stdout 에서 확인할 문장들 — 기대 숫자를 폴더에서 받는다."""
    return [
        ("문항 수", re.compile(rf"{exp['questions']}\s*문제")),
        ("회차 수", re.compile(rf"{exp['rounds']}\s*회")),
        ("과목 수", re.compile(rf"과목\s*{exp['subjects']}\s*종")),
        ("ApiDS 모드", re.compile(r"EXAM_API")),
    ]


def start(scope: str = "all") -> dict:
    """발행 빌드를 시작한다.

    ★ `scope="problems"` 는 **1차(문제집)** 다. 빌더는 그대로 돌고(영상이 없어도
      돈다 — `build_check.py`: "없으면 영상 없음"), **어서션에서 영상 몫만 뺀다.**
      빼는 것이 아니라 「2차에서 봅니다」로 표시한다 — 사라지면 사람이 2차에 무엇이
      남았는지 모른다.
    """
    require_pd()          # ★ 잡을 만들기 전에 끊는다
    env = env_info()
    if not env["cloned"]:
        # 빌더는 이 저장소 안에 있다 — 없다면 파일이 지워진 것이다(클론 문제가 아니다).
        raise FileNotFoundError(
            f"발행 빌더를 찾을 수 없습니다: {env['script']}\n"
            "axexam/scripts/ 가 저장소에 들어 있어야 합니다 "
            "(git subtree 로 합쳐져 있습니다).")

    label = "문제집 (1차)" if scope == "problems" else "전체 (2차)"
    job = registry.create("build", f"발행 빌드 · {label} · pd={active_pd()}", [],
                          steps=["build", "assert", "problems"])
    job["scope"] = scope
    job["build"] = {"command": command_text(), "pd": active_pd(),
                    "book": paths.book_dir(), "scope": scope}
    registry.spawn(job, _work)
    return job


def _work(job: dict) -> None:
    registry.item(job, "build", status="running")
    args = build_args()
    registry.log(job, f"[build] cwd={AXBUILD_DIR}", force=True)
    registry.log(job, f"[build] {command_text()}", force=True)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"     # 리포트가 한국어다
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(
        args, cwd=AXBUILD_DIR, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1)
    out_lines: list[str] = []
    for raw in proc.stdout:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        out_lines.append(line)
        registry.log(job, line)
    proc.stdout.close()
    rc = proc.wait()

    if rc != 0:
        registry.item(job, "build", status="error", error=f"종료코드 {rc}")
        registry.finish(job, "error", error=f"build_check.py 가 종료코드 {rc} 로 끝났습니다.")
        return
    registry.item(job, "build", status="done")

    # ── stdout 어서션 ──
    registry.item(job, "assert", status="running")
    blob = "\n".join(out_lines)
    asserts = []
    for label, rx in assertions(expected()):
        ok = bool(rx.search(blob))
        asserts.append({"label": label, "ok": ok, "pattern": rx.pattern})
    problems_only = job.get("scope") == "problems"
    for label, bad_rx, msg, stage2 in [
        ("SVG 누락 없음", re.compile(r"\[warn\]\s*SVG 못 찾음"),
         "빌드가 SVG 를 못 찾았습니다.", False),
        ("유튜브 ID 누락 없음", re.compile(r"\[warn\]\s*유튜브 ID 미입력"),
         "유튜브 ID 가 비어 있습니다 — 영상이 재생되지 않습니다.", True),
        ("STALE 잔여 없음", re.compile(r"\[STALE\]"),
         "예전 빌드의 mp4 가 남아 있습니다.", True),
    ]:
        hit = bool(bad_rx.search(blob))
        if stage2 and problems_only:
            # ★ 1차에서는 **판정하지 않는다.** 지우지도 않는다 — 2차에 남은 일이다.
            asserts.append({"label": label, "ok": True, "skipped": True,
                            "pattern": bad_rx.pattern,
                            "detail": ("2차(영상)에서 봅니다" if hit else "")})
            continue
        asserts.append({"label": label, "ok": not hit, "pattern": bad_rx.pattern,
                        "detail": msg if hit else ""})
    job["asserts"] = asserts
    failed = [a["label"] for a in asserts if not a["ok"]]
    registry.item(job, "assert", status="error" if failed else "done",
                  error=("어서션 실패: " + ", ".join(failed)) if failed else None)
    for a in asserts:
        mark = "SKIP" if a.get("skipped") else ("OK  " if a["ok"] else "FAIL")
        registry.log(job, f"[assert] {mark} {a['label']}"
                          + (f" — {a.get('detail')}" if a.get("detail") else ""), force=True)

    # ── problems.json 검증 + 임포트 드라이런 ──
    registry.item(job, "problems", status="running")
    res = validate_problems_json()
    job["problems"] = res
    registry.item(job, "problems", status="error" if not res["ok"] else "done",
                  error=None if res["ok"] else "; ".join(res["errors"][:3]))
    for e in res["errors"]:
        registry.log(job, f"[problems] ERROR {e}", force=True)
    for w in res["warnings"]:
        registry.log(job, f"[problems] warn  {w}", force=True)
    registry.log(job, f"[problems] pd_id={res.get('pd_id')} "
                      f"문항 {res.get('count')} · 회차 {res.get('rounds')} · "
                      f"과목 {res.get('subjects')}", force=True)

    ok = not failed and res["ok"]
    registry.finish(job, "done" if ok else "error",
                    error=None if ok else "빌드는 됐지만 검증에서 문제가 발견됐습니다.",
                    result={"problems_json": paths.problems_json(),
                            "out_dir": paths.out_dir()})


# ── problems.json 검증 (임포트 드라이런) ─────────────────────────────────────
def _content_hash(p: dict) -> str:
    """exam_lib/problem.php 가 비교하는 pr_hash 를 로컬에서 재현한다.

    build_check.py::_hash 와 같은 규칙 — 본문 7개 필드만 넣는다.
    ★ sj_name·sj_no·verified·needs_review 는 해시에 **없다**. 과목 매핑만 고치고
      재빌드하면 임포트가 '변경없음' 을 찍고 DB 에 도달하지 않는다. 강제 플래그가
      없으므로 첫 임포트 전에 과목을 확실히 맞춰야 한다.
    """
    payload = json.dumps([
        p.get("question") or "", p.get("passage") or "", p.get("sql_text") or "",
        p.get("table_json"), p.get("choices_json") or [], p.get("answer_index"),
        p.get("explanation") or "",
    ], ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def validate_problems_json(path: str | None = None) -> dict:
    """서버에 없는 드라이런을 로컬에서 한다.

    DB 에 접근할 수 없으므로 신규/갱신 분류는 하지 못한다. 대신 임포트가 **문서
    단위로 중단시키는 조건**과 행 단위로 실패시키는 조건을 전부 미리 검사한다.
    """
    path = path or paths.problems_json()
    errors: list[str] = []
    warnings: list[str] = []

    if not os.path.isfile(path):
        return {"ok": False, "path": path,
                "errors": [f"problems.json 이 없습니다: {path}. --emit-json 으로 빌드하세요."],
                "warnings": []}

    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        return {"ok": False, "path": path, "errors": [f"JSON 파싱 실패: {e}"], "warnings": []}

    pd_id = (doc.get("pd_id") or "").strip()
    want_pd = active_pd()
    if pd_id != want_pd:
        errors.append(f"pd_id 가 '{pd_id}' 입니다 — '{want_pd}' 여야 합니다. "
                      "다른 품목의 문제은행을 덮어쓸 수 있습니다.")
    if not re.match(r"^[a-z0-9\-]{1,20}$", pd_id):
        errors.append(f"pd_id 형식이 서버 정규식을 통과하지 못합니다: {pd_id!r}")

    exp = expected()
    problems = doc.get("problems") or []
    if len(problems) != exp["questions"]:
        errors.append(f"문항이 {len(problems)}개입니다 — {exp['questions']}개여야 합니다.")

    rounds_ = doc.get("rounds") or []
    if len(rounds_) != exp["rounds"]:
        errors.append(f"회차가 {len(rounds_)}개입니다 — {exp['rounds']}개여야 합니다.")
    # ★ 회차별 기대 문항 수도 그 회차의 _rounds 실측값이다. 상수 80 으로 두면
    #   50문항 책이나 집필 중인 마지막 회차에서 무조건 오류가 난다.
    from services.book import shape
    for r in rounds_:
        rc = f"m{int(r.get('rd_no') or 0):02d}"
        want = shape.questions_in_round(rc)
        got = int(r.get("rd_count", 0))
        if want and got != want:
            errors.append(f"{r.get('rd_no')}회 문항이 {got}개입니다 "
                          f"— _rounds/{rc}.json 기준 {want}개여야 합니다.")

    subjects = doc.get("subjects") or []
    if len(subjects) != exp["subjects"]:
        errors.append(f"subjects 가 {len(subjects)}개입니다 — {exp['subjects']}개여야 합니다. "
                      "02/*.md 의 subject_no 가 문자열이면 여기가 빈 배열이 됩니다.")
    if any(int(s.get("sj_no", 0)) < 1 for s in subjects):
        errors.append("subjects 에 sj_no 가 0 인 항목이 있습니다 — 과목 필터가 깨집니다.")

    seen, dup, bad_key, bad_ans, no_choices = set(), [], [], [], []
    sj_zero = 0
    for p in problems:
        k = p.get("pr_key") or ""
        if k in seen:
            dup.append(k)
        seen.add(k)
        if not _PR_KEY_RE.match(k):
            bad_key.append(k)
        ch = p.get("choices_json") or []
        if not ch:
            no_choices.append(k)
        ai = p.get("answer_index")
        n = int(p.get("n_choices") or len(ch) or 0)
        if ai is None or not isinstance(ai, int) or not 0 <= ai < max(1, n):
            bad_ans.append(k)
        if int(p.get("sj_no") or 0) < 1:
            sj_zero += 1
        if int(p.get("rd_no") or 0) <= 0 or int(p.get("pr_no") or 0) <= 0:
            errors.append(f"{k}: rd_no/pr_no 가 유효하지 않습니다.")

    if dup:
        errors.append(f"pr_key 중복 {len(dup)}건: {', '.join(dup[:5])} — "
                      "upsert 축이 겹치면 같은 문제가 새 행으로 들어갑니다.")
    if bad_key:
        errors.append(f"서버 정규식을 통과하지 못하는 pr_key {len(bad_key)}건: "
                      f"{', '.join(bad_key[:5])} — 채점이 오류 없이 0점이 됩니다.")
    if no_choices:
        errors.append(f"보기가 빈 문항 {len(no_choices)}건: {', '.join(no_choices[:5])}")
    if bad_ans:
        errors.append(f"정답 번호가 범위를 벗어난 문항 {len(bad_ans)}건: {', '.join(bad_ans[:5])}")
    if sj_zero:
        errors.append(f"sj_no 가 0 인 문항 {sj_zero}건 — 과목 필터가 통째로 깨집니다.")

    size = os.path.getsize(path)
    if size > 6 * 1024 * 1024:
        warnings.append(f"problems.json 이 {size / 1048576:.1f} MB 입니다 — "
                        "서버의 post_max_size 를 넘으면 요청이 통째로 버려집니다.")

    # ★ 그림은 **품목별 폴더** 아래다 — `06/pd/<pd>/figs/`. 옛 평면 자리(`06/figs`)를
    #   보던 탓에 169개가 다 있는데도 "없는 그림 169건" 이라고 경고했다(2026-08-25).
    figs_dir = paths.pd_figs_dir()
    fig_missing = []
    for p in problems:
        for f in (p.get("figures_json") or []):
            if not os.path.isfile(os.path.join(figs_dir, f)):
                fig_missing.append(f)
    if fig_missing:
        warnings.append(f"{paths.rel(figs_dir)} 에 없는 그림 {len(fig_missing)}건: "
                        f"{', '.join(fig_missing[:5])} — 웹에서 조용히 안 보입니다.")

    # ★ 기대값을 **문장에 박지 않는다.** 240문항·3회차는 빅분기 시절 숫자라, SQLD
    #   1,000문항 빌드에서도 "신규 240" 이라고 말했다(2026-08-25). 사람이 임포트
    #   리포트와 대조하는 값이므로 틀리면 있으나 마나다. 폴더값으로 낸다.
    warnings.append("서버에 드라이런이 없어 신규/갱신 분류는 임포트 화면의 리포트로만 "
                    f"확인할 수 있습니다. 기대값: 신규 {len(problems)} · 갱신 0 · "
                    f"건너뜀 0 · 실패 0 · 회차 {len(rounds_)}행.")

    return {
        "ok": not errors,
        "path": path,
        "bytes": size,
        "pd_id": pd_id,
        "count": len(problems),
        "rounds": len(rounds_),
        "subjects": len(subjects),
        "subject_list": [f"{s.get('sj_no')}:{s.get('sj_name')}" for s in subjects],
        "errors": errors,
        "warnings": warnings,
        "expected_report": {"new": len(problems), "updated": 0, "skipped_edited": 0,
                            "unchanged": 0, "failed": 0, "rounds": len(rounds_)},
    }
