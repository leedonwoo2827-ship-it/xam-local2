"""확정 게이트 + 회차 정합성 검증.

## 왜 게이트가 필요한가

`01/*.md` 를 쓰는 코드가 두 개가 됐다 — 이 패키지의 `finalize.py`(초안에서 확정)와
`services/book/scan.py`(확정된 md 를 한 문항씩 손보기). 둘이 바이트로 어긋나면
한쪽으로 저장할 때 다른 쪽이 만든 파일이 조용히 바뀐다.

    venv\\Scripts\\python -m services.ocr.checks              두 검사 다
    venv\\Scripts\\python -m services.ocr.checks --refinalize   확정 왕복만
    venv\\Scripts\\python -m services.ocr.checks --round        회차 정합성만

`refinalize` 는 **디스크에 아무것도 쓰지 않는다.** 모든 초안을 확정했을 때의 바이트를
계산해 지금 `01/*.md` 와 비교한다. 이게 통과하지 않으면 UI 의 `확정(MD 저장)` 을
막는다 — 통과하지 못하는 렌더러로 확정하면 이미 검수한 파일이 망가진다.
"""
from __future__ import annotations

import os
import re
from collections import Counter

from services.book import paths
from services.ocr import draft, finalize, project

TOKEN = re.compile(r"\{\{([A-Za-z]+-\d+)\}\}")
INLINE_MATH = re.compile(r"(?<!\\)\$[^$\n]+?(?<!\\)\$")
# static/js/ocr.js 의 CELLREF 와 같은 식 — 미리보기도 이것을 수식에서 뺀다
CELLREF = re.compile(r"(?<![A-Za-z0-9$])\$?[A-Z]{1,3}\$?\d{1,7}"
                     r"(?::\$?[A-Z]{1,3}\$?\d{1,7})?(?![A-Za-z0-9])")
CIRCLED = "①②③④⑤"
DIFFICULTIES = ("하", "중", "상")


def _read(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _draft_is_newer(src_: str, page_: int, md_path: str) -> bool:
    """이 초안이 확정본보다 **나중에 고쳐졌는가.**

    ★ 게이트가 사람의 편집과 렌더러의 어긋남을 가리는 유일한 단서다.

      · 초안이 더 새롭다 → 확정한 뒤 사람이 고쳤다. 달라지는 것이 **당연하다.**
        (실측 2026-08-19: 25번 해설에 그림을 하나 넣었을 뿐인데 게이트가 전체
         확정을 막았다. 고친 면을 먼저 확정하지 않으면 빠져나갈 수 없었다.)
      · 초안이 더 낡았다 → 초안은 그대로인데 나오는 바이트가 달라졌다.
        렌더러가 어긋난 것이고, 이것이 게이트가 실제로 막아야 하는 것이다.

    시각을 못 읽으면 **막는 쪽**으로 답한다 — 모르는 채로 240개를 덮어쓰는 것보다 낫다.
    """
    try:
        return os.path.getmtime(draft.path_of(src_, page_)) > os.path.getmtime(md_path)
    except OSError:
        return False


# 사람의 검수 플래그. **게이트의 비교 대상이 아니다.**
#
# ★ 왜 빼는가 — 게이트가 지키려는 것은 "다시 확정하면 **검수한 내용**이 바뀌는가" 다.
#   그런데 이 셋은 확정·대조완료가 **바꾸라고 있는 값**이다. 같이 비교하면 정상 작업이
#   게이트를 켠다: p.3 을 확정(verified=false)한 뒤 대조완료를 체크하면 초안이
#   true 가 되어 불일치가 뜨고, 그걸 푸는 유일한 방법인 '다시 확정' 을 게이트가 막는다
#   — 빠져나갈 수 없는 자리였다(2026-08-18 실측, 사용자가 세 번 막혔다).
#
#   플래그만 다른 것은 `flag_only` 로 세어 따로 보여 준다. 내용이 다른 것만 막는다.
_FLAG_RE = re.compile(r"^(verified|reviewed|needs_review): .*$", re.M)


def _content(text: str) -> str:
    """검수 플래그를 지운 본문 — 게이트가 실제로 비교하는 것."""
    return _FLAG_RE.sub(lambda m: m.group(0).split(":")[0] + ": ~", text or "")


# ── 확정 왕복 (게이트) ──────────────────────────────────────────────────────
def refinalize(skip: tuple | None = None) -> dict:
    """모든 초안을 확정했을 때의 바이트 = 지금 01/*.md 인가.

    · same     이미 확정돼 있고 바이트가 같다            → 정상
    · new      아직 01/ 에 없다 (판독했지만 미확정)       → 정상. 게이트를 막지 않는다
    · differ   있는데 바이트가 다르다                     → ★ 게이트 실패

    `skip=(src, page)` 는 **그 면을 빼고** 본다 — 지금 확정하려는 면이다.
    """
    if not project.exists():
        return {"ok": False, "total": 0, "same": 0, "new": 0,
                "error": f"OCR 판독 폴더를 찾을 수 없습니다: {project.ocr_dir() or '(미지정)'}"}

    same, new, differ, errors = 0, [], [], []
    flag_only: list[str] = []
    skip_at = (str(skip[0]), int(skip[1])) if skip else None
    mine: list[str] = []          # 지금 확정하려는 면에서 달라지는 것
    edited: list[dict] = []       # 확정 뒤 사람이 고친 면 — 다시 확정하면 반영된다
    for src, page in draft.all_drafts():
        d = draft.load(src, page)
        for q in (d or {}).get("questions") or []:
            if not q.get("round") or not q.get("question_no"):
                continue
            try:
                path, text = finalize.render_for(q, src, page)
            except Exception as e:
                errors.append({"src": src, "page": page,
                               "question_no": q.get("question_no"),
                               "error": f"{type(e).__name__}: {e}"})
                continue
            cur = _read(path)
            if cur is None:
                new.append(os.path.basename(path)[:-3])
            elif cur == text:
                same += 1
            elif _content(cur) == _content(text):
                # 내용은 같고 검수 플래그만 다르다 — 확정이 바꿀 값이라 막지 않는다
                flag_only.append(os.path.basename(path)[:-3])
            else:
                i = next((i for i, (a, b) in enumerate(zip(cur, text)) if a != b),
                         min(len(cur), len(text)))
                # ★ 지금 확정하려는 면이면 막지 않는다 — 사람이 방금 고친 그 면이다.
                if skip_at and (str(src), int(page)) == skip_at:
                    mine.append(os.path.basename(path)[:-3])
                    continue
                # ★ 확정한 뒤 초안을 고쳤으면 달라지는 것이 당연하다 — 막지 않고 센다.
                if _draft_is_newer(src, page, path):
                    edited.append({"id": os.path.basename(path)[:-3],
                                   "src": src, "page": page})
                    continue
                differ.append({
                    "src": src, "page": page,
                    "id": os.path.basename(path)[:-3],
                    "path": paths.rel(path),
                    "at_char": i,
                    "at_line": cur[:i].count("\n") + 1,
                    "expected": repr(cur[max(0, i - 30):i + 30]),
                    "got": repr(text[max(0, i - 30):i + 30]),
                    "bytes_expected": len(cur.encode("utf-8")),
                    "bytes_rendered": len(text.encode("utf-8")),
                })

    total = same + len(new) + len(differ)
    return {
        "ok": not differ and not errors,
        "kind": "초안 → 01/*.md 확정 왕복",
        "total": total, "same": same,
        "new": new[:40], "new_count": len(new),
        "differ": differ[:20], "differ_count": len(differ),
        # 플래그만 다른 것 — 게이트를 막지 않는다. 다시 확정하면 맞춰진다.
        "flag_only": flag_only[:20], "flag_only_count": len(flag_only),
        # 지금 확정하려는 면에서 달라지는 것 — 막지 않고 **말한다.**
        "mine": mine[:20], "mine_count": len(mine),
        # 확정 뒤 초안을 고친 면 — 막지 않는다. 그 면에서 다시 확정하면 반영된다.
        "edited": edited[:40], "edited_count": len(edited),
        "errors": errors[:20], "error_count": len(errors),
        "gate": ("확정(MD 저장) 을 쓸 수 있습니다." if not differ and not errors else
                 "★ 확정을 막았습니다 — 지금 렌더러로 확정하면 이미 검수한 "
                 "01/*.md 가 바뀝니다."),
    }


def gate_ok(skip: tuple | None = None) -> tuple[bool, str]:
    """UI·라우터가 쓰는 짧은 형태.

    ★ `skip=(src, page)` — **지금 확정하려는 면은 빼고** 본다.

      확정은 그 면의 문항만 쓴다(`finalize_page`). 그런데 게이트가 전체를 보고 막아서,
      25번에 해설 그림을 하나 넣은 것이 26번 확정까지 막았다(2026-08-19 실측).
      사람이 방금 그 면을 고쳤으니 그 면이 달라지는 것은 **의도한 일**이다.
      게이트가 지켜야 하는 것은 그 면이 아니라, 손대지 않은 **다른 면**이 덩달아
      바뀌는 것이다 — 렌더러가 어긋난 신호이고, 그것만 막는다.
    """
    r = refinalize(skip)
    if r.get("error"):
        return False, r["error"]
    if r["ok"]:
        return True, ""
    parts = []
    if r["differ_count"]:
        parts.append(f"바이트 불일치 {r['differ_count']}건")
    if r["error_count"]:
        parts.append(f"렌더 오류 {r['error_count']}건")
    # ★ 어디가 문제인지 **여기서 말한다.** 앱만 쓰는 사람에게 CLI 명령을 안내하면
    #   막힌 채로 남는다 — 실제로 그랬다.
    where = ""
    if r.get("differ"):
        ds = r["differ"][:3]
        where = " 문제가 된 곳: " + ", ".join(
            f"{d['id']} ({d.get('src', '?')} p.{d.get('page', '?')} {d['at_line']}줄)"
            for d in ds) + ("…" if r["differ_count"] > len(ds) else "")
    return False, (
        f"확정을 막았습니다 ({' · '.join(parts)}) — 손대지 않은 다른 면의 "
        f"확정본이 바뀝니다.{where} 그 면을 열어 초안을 확인하시거나, "
        "바뀐 내용이 맞다면 그 면에서 다시 확정하세요.")


# ── 회차 정합성 ─────────────────────────────────────────────────────────────
def _texts(q: dict) -> list[str]:
    out = [q.get("stem") or "", q.get("jimun") or "", q.get("explanation") or ""]
    out += [c or "" for c in (q.get("choices") or [])]
    return out


def verify_round(src: str, round_no: int, *, total: int | None = None) -> dict:
    """한 회차의 초안이 앞뒤가 맞는가. 판독 직후 / 정답 병합 직후에 돌린다."""
    if total is None:
        total = project.questions_per_round()
    answers: dict[int, str] = {}
    for a in draft.load_answers(src, round_no):
        answers.update({int(k): v for k, v in (a.get("answers") or {}).items()})

    qs: dict[int, dict] = {}
    pages: dict[int, list[int]] = {}
    probs: list[str] = []
    for s, page in draft.all_drafts(src):
        d = draft.load(s, page) or {}
        for q in d.get("questions") or []:
            if int(q.get("round") or 0) != int(round_no):
                continue
            n = int(q.get("question_no") or 0)
            if n in qs:
                probs.append(f"{n}번: 중복 (p{page})")
            qs[n] = q
            pages.setdefault(page, []).append(n)

    if total:
        missing = sorted(set(range(1, total + 1)) - set(qs))
        if missing:
            probs.append(f"누락 문항: {missing}")
        extra = sorted(n for n in qs if not 1 <= n <= total)
        if extra:
            probs.append(f"범위 밖 문항: {extra}")

    bounds = project.subject_bounds()
    for n in sorted(qs):
        q = qs[n]
        ch = q.get("choices") or []
        if len(ch) < 2:
            probs.append(f"{n}번: 보기 {len(ch)}개")
        if not (q.get("stem") or "").strip():
            probs.append(f"{n}번: 발문 비어있음")
        if not (q.get("explanation") or "").strip():
            probs.append(f"{n}번: 해설 비어있음")

        a = q.get("answer") or ""
        # ★ `"" in CIRCLED` 는 True 다 — 빈 정답이 이 검사를 그냥 통과했다
        if not a or a not in CIRCLED:
            probs.append(f"{n}번: 정답기호 이상 {a!r}")
        elif n in answers and a != answers[n]:
            probs.append(f"{n}번: 정답 불일치 — 초안 {a} vs 정답표 {answers[n]}")
        if q.get("answer_index") != finalize.answer_to_index(a):
            probs.append(f"{n}번: answer_index 불일치")

        assets = q.get("assets") or {}
        used: set[str] = set()
        for t in _texts(q):
            used |= set(TOKEN.findall(t))
        for t in (a2.get("md") or a2.get("text") or "" for a2 in assets.values()):
            used |= set(TOKEN.findall(t))
        if used - set(assets):
            probs.append(f"{n}번: 정의 없는 토큰 {sorted(used - set(assets))}")
        if set(assets) - used:
            probs.append(f"{n}번: 미사용 자산 {sorted(set(assets) - used)}")

        want = next((s for hi, s in bounds if n <= hi), None) if bounds else None
        if want and q.get("subject_no") != want:
            probs.append(f"{n}번: 과목 {q.get('subject_no')} (문항번호 기준 {want})")

        for t in _texts(q):
            # 엑셀 절대참조($D$2:$D$6, $B3)의 $ 는 수식 짝이 아니다 — 세기 전에 뺀다
            if CELLREF.sub("", t).count("$") % 2:
                probs.append(f"{n}번: $ 개수 홀수 — 수식 짝 확인 필요")
                break

    latex = sorted(n for n, q in qs.items()
                   if any(INLINE_MATH.search(t) for t in _texts(q))
                   or any(a.get("type") == "latex"
                          for a in (q.get("assets") or {}).values()))
    return {
        "src": src, "round": int(round_no),
        "count": len(qs), "total": total,
        "pages": {str(p): len(v) for p, v in sorted(pages.items())},
        "answers": dict(sorted(Counter(q.get("answer") for q in qs.values()).items(),
                               key=lambda kv: str(kv[0]))),
        "subjects": dict(sorted(Counter(q.get("subject_no") for q in qs.values()).items(),
                                key=lambda kv: str(kv[0]))),
        "difficulty": dict(sorted(
            Counter(q.get("difficulty") for q in qs.values()).items(),
            key=lambda kv: DIFFICULTIES.index(kv[0]) if kv[0] in DIFFICULTIES else 9)),
        "latex": latex,
        "problems": probs,
        "ok": not probs,
    }


def verify_all_rounds() -> list[dict]:
    """초안에 등장하는 (src, 회차) 전부. ★ 회차 수를 하드코딩하지 않는다."""
    seen: dict[tuple[str, int], bool] = {}
    for src, page in draft.all_drafts():
        d = draft.load(src, page) or {}
        for q in d.get("questions") or []:
            rn = q.get("round")
            if rn:
                seen[(src, int(rn))] = True
        if d.get("round"):
            seen.setdefault((src, int(d["round"])), True)
    return [verify_round(src, rn) for src, rn in sorted(seen)]


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main() -> int:
    import argparse
    from dotenv import load_dotenv
    load_dotenv(".env", encoding="utf-8-sig")

    p = argparse.ArgumentParser(description="OCR 확정 게이트 · 회차 정합성 검증")
    p.add_argument("--refinalize", action="store_true", help="확정 왕복만")
    p.add_argument("--refinalize-dry", dest="refinalize", action="store_true",
                   help="--refinalize 와 같다 (쓰지 않는 것이 기본이다)")
    p.add_argument("--round", action="store_true", help="회차 정합성만")
    a = p.parse_args()
    both = not (a.refinalize or a.round)

    rc = 0
    print(f"BOOK: {paths.book_dir()}")
    print(f"OCR : {project.ocr_dir() or '(미지정)'}")
    print()

    if a.refinalize or both:
        r = refinalize()
        if r.get("error"):
            print("[error]", r["error"])
            return 2
        print(f"  초안 → 01/*.md 확정 왕복      "
              f"일치 {r['same']}/{r['total']}"
              + (f"  ·  미확정(신규) {r['new_count']}" if r["new_count"] else "")
              + (f"  ·  확정 뒤 고침 {r['edited_count']}" if r["edited_count"] else "")
              + (f"  ·  불일치 {r['differ_count']}" if r["differ_count"] else ""))
        for e in r["edited"]:
            print(f"  [edited] {e['id']}  ({e['src']} p.{e['page']}) "
                  f"— 그 면에서 다시 확정하면 반영됩니다")
        for d in r["differ"]:
            print(f"  [differ] {d['id']}  line {d['at_line']}")
            print(f"           기대={d['expected']}")
            print(f"           실제={d['got']}")
        for e in r["errors"]:
            print(f"  [error]  p{e['page']} {e['question_no']}번  {e['error']}")
        print(("  [ok] " if r["ok"] else "  [FAIL] ") + r["gate"])
        print()
        rc = rc or (0 if r["ok"] else 1)

    if a.round or both:
        for r in verify_all_rounds():
            print(f"[{r['src']} {r['round']:02d}회]  문항 {r['count']}"
                  + (f"/{r['total']}" if r["total"] else ""))
            print("  페이지별 :", "  ".join(f"p{k}={v}" for k, v in r["pages"].items()))
            print("  정답분포 :", r["answers"])
            print("  과목분포 :", r["subjects"])
            print("  난이도   :", r["difficulty"])
            print(f"  수식 문항 : {len(r['latex'])}개  {r['latex']}")
            if r["problems"]:
                print("  경고:")
                for x in r["problems"]:
                    print("   -", x)
                rc = rc or 1
            else:
                print("  경고: 없음")
            print()
    return rc


if __name__ == "__main__":
    raise SystemExit(_main())
