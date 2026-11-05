"""왕복 검증 — 렌더러가 원본을 바이트 단위로 재현하는지 확인한다.

02/*.md 240개와 _index.json / difficulty_stats.json, 그리고 05 lesson 24개는
원격 Claude 세션에서 만들어졌고 로컬에 생성 스크립트가 없다. 우리 렌더러가 한
글자라도 어긋나면, 한 문항을 저장할 때 나머지가 조용히 바뀐다.

**이 검증이 전부 통과하기 전에는 저장 경로를 열지 않는다.** (계획 Phase 1)

디스크에 아무것도 쓰지 않는다 — 메모리에서 렌더하고 원본과 비교만 한다.

CLI:
    venv\\Scripts\\python -m services.book.verify
"""
from __future__ import annotations

import difflib
import json
import os

from services.book import index as bindex, jsonio, lesson, md, paths, rounds


def _read(path: str) -> str | None:
    """개행 변환 없이 읽는다 — CRLF/LF 차이를 놓치면 검증의 의미가 없다."""
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def _rendered(path: str, text: str) -> str:
    """렌더러 출력을 '그 파일에 실제로 들어갈 바이트' 로 맞춘다.

    렌더러는 LF 로만 조립한다(내용이 원천). 개행은 paths.to_disk() 한 곳에서만
    정하고, 저장 경로도 같은 함수를 쓴다 — 검증과 저장이 갈리면 검증이 무의미하다.
    """
    return paths.to_disk(path, text)


def _first_diff(a: str, b: str) -> dict:
    """어디서 처음 갈라지는지 — 사람이 고칠 수 있는 형태로 알려준다."""
    for i, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            line = a[:i].count("\n") + 1
            return {
                "at_char": i,
                "at_line": line,
                "expected": repr(a[max(0, i - 20):i + 20]),
                "got": repr(b[max(0, i - 20):i + 20]),
            }
    return {
        "at_char": min(len(a), len(b)),
        "at_line": a[:min(len(a), len(b))].count("\n") + 1,
        "expected": repr(a[len(b):len(b) + 40]) if len(a) > len(b) else "",
        "got": repr(b[len(a):len(a) + 40]) if len(b) > len(a) else "",
        "note": "길이가 다릅니다(한쪽이 더 깁니다).",
    }


def verify_md() -> dict:
    """02/*.md 240개."""
    ok, fail, missing = 0, [], []
    for rc, meta, q in rounds.all_questions():
        qid = paths.qid(int(meta["round"]), int(q["question_no"]))
        path = paths.q_md(qid)
        original = _read(path)
        if original is None:
            missing.append(qid)
            continue
        try:
            flags = md.read_flags(path)
            rendered = _rendered(path, md.render(q, meta, flags))
        except Exception as e:
            fail.append({"id": qid, "error": f"{type(e).__name__}: {e}"})
            continue
        if rendered == original:
            ok += 1
        else:
            fail.append({
                "id": qid,
                "path": paths.rel(path),
                "bytes_expected": len(original.encode("utf-8")),
                "bytes_rendered": len(rendered.encode("utf-8")),
                **_first_diff(original, rendered),
            })
    return {"kind": "02/*.md", "total": ok + len(fail) + len(missing),
            "ok": ok, "fail": fail[:20], "fail_count": len(fail),
            "missing": missing[:20], "missing_count": len(missing)}


def verify_rounds() -> dict:
    """_rounds/mNN.json — 집필 원천. 저장할 때마다 **파일 전체**를 다시 쓴다.

    ★ 이 그룹이 왜 필요한가: 업로드본은 이걸 검증하지 않았고, 서식을 indent=2 로
      못박아 뒀다. 실측은 260730 이 indent=1 이라서, 문항 하나를 저장하면 111KB
      원천이 118KB 로 통째로 재작성된다 — 80문항 서식이 전부 바뀌고 `.bak` 으로도
      무엇이 사람의 수정이었는지 분간이 안 된다. 나머지 그룹과 같은 등급의 게이트다.
    """
    ok, fail = 0, []
    for rc in paths.round_codes():
        path = paths.rounds_json(rc)
        r = jsonio.roundtrip(path)
        if r.get("ok"):
            ok += 1
        else:
            fail.append({"id": rc, "path": paths.rel(path), **r})
    return {"kind": "_rounds/*.json", "total": ok + len(fail),
            "ok": ok, "fail": fail[:20], "fail_count": len(fail),
            "missing": [], "missing_count": 0}


def verify_index() -> dict:
    """02/_index.json · 02/difficulty_stats.json."""
    items = bindex.collect()
    results = []
    for path, text in ((paths.q_index(), bindex.render_index(items)),
                       (paths.q_stats(), bindex.render_stats(items))):
        original = _read(path)
        name = os.path.basename(path)
        if original is None:
            results.append({"file": name, "ok": False, "error": "파일이 없습니다."})
        elif original == text:
            results.append({"file": name, "ok": True})
        else:
            results.append({
                "file": name, "ok": False,
                "bytes_expected": len(original.encode("utf-8")),
                "bytes_rendered": len(text.encode("utf-8")),
                **_first_diff(original, text),
            })
    return {"kind": "02/_index.json + difficulty_stats.json",
            "total": len(results),
            "ok": sum(1 for r in results if r.get("ok")),
            "results": results}


def verify_lesson() -> dict:
    """05/<bundle>/source/lesson_<bundle>.json 24개.

    lesson 은 우리가 처음부터 렌더하지 않는다(section 블록·회차 메타는 도구 #2 의
    산물이다). 대신 **problem 블록만** _rounds 로 다시 만들어 넣고, 문서 전체를
    다시 직렬화했을 때 원본과 같은지 본다. 이게 저장 경로가 실제로 하는 일이다.
    """
    ok, fail, missing = 0, [], []
    by_round = rounds.load_all()
    for bundle in paths.all_bundles():
        path = paths.bundle_lesson(bundle)
        original = _read(path)
        if original is None:
            missing.append(bundle)
            continue
        parsed = paths.parse_bundle(bundle)
        rc = paths.round_code(parsed[0])
        doc = by_round.get(rc)
        if not doc:
            missing.append(bundle)
            continue

        lo, hi = paths.bundle_range(bundle)
        try:
            cur = json.loads(original)
            for qno in range(lo, hi + 1):
                q = rounds.question_of(doc, qno)
                if q is None:
                    raise ValueError(f"_rounds/{rc}.json 에 {qno}번 문항이 없습니다.")
                # keep_speech=True — 편집하지 않은 낭독문은 디스크 값을 지킨다.
                # 실측 드리프트 2건(m01-5 q42 · m02-5 q45)이 TTS 손질이라 되돌리면 안 된다.
                cur = lesson.render(cur, q, keep_speech=True)
            rendered = lesson.render_text(cur, bundle)
        except Exception as e:
            fail.append({"bundle": bundle, "error": f"{type(e).__name__}: {e}"})
            continue

        if rendered == original:
            ok += 1
        else:
            fail.append({
                "bundle": bundle,
                "path": paths.rel(path),
                "bytes_expected": len(original.encode("utf-8")),
                "bytes_rendered": len(rendered.encode("utf-8")),
                **_first_diff(original, rendered),
            })
    return {"kind": "05/*/source/lesson_*.json", "total": ok + len(fail) + len(missing),
            "ok": ok, "fail": fail[:20], "fail_count": len(fail),
            "missing": missing[:20], "missing_count": len(missing)}


def verify_assets() -> dict:
    """has_figure 인 문항의 SVG 가 디스크에 있고, _rounds 의 인라인 SVG 와 같은가.

    저장할 때 02/assets/*.svg 를 _rounds 의 문자열로 덮어쓰므로, 지금 두 값이
    다르면 첫 저장에서 그림이 바뀐다. 그 사실을 미리 알아야 한다.
    """
    from services.book import derive
    same, differ, missing, extra = 0, [], [], []
    used: set[str] = set()
    for rc, meta, q in rounds.all_questions():
        for asset in q.get("assets") or []:
            name = (asset.get("name") or "") if isinstance(asset, dict) else str(asset)
            name = name[:-4] if name.endswith(".svg") else name
            if not name:
                continue
            used.add(name + ".svg")
            path = paths.q_svg(name)
            disk = _read(path)
            svg = asset.get("svg") if isinstance(asset, dict) else None
            if disk is None:
                missing.append(name)
            elif svg is not None and disk.rstrip("\n") == svg.rstrip("\n"):
                same += 1
            else:
                differ.append({"name": name, "disk_bytes": len(disk.encode("utf-8")),
                               "rounds_bytes": len((svg or "").encode("utf-8"))})
    adir = paths.q_assets_dir()
    if os.path.isdir(adir):
        for f in sorted(os.listdir(adir)):
            if f.endswith(".svg") and f not in used:
                extra.append(f)
    return {"kind": "02/assets/*.svg", "total": same + len(differ) + len(missing),
            "ok": same, "differ": differ[:20], "differ_count": len(differ),
            "missing": missing[:20], "missing_count": len(missing),
            "orphan": extra[:20], "orphan_count": len(extra)}


def run_all() -> dict:
    """전체 왕복 검증. `ok` 가 True 여야 저장 경로를 열 수 있다."""
    if not paths.exists():
        return {"ok": False, "error":
                f"이 작업 폴더에는 아직 문항이 없습니다: {paths.book_dir()}"
                " — _rounds/ 와 02/ 가 있는 폴더로 전환하세요."}

    groups = [verify_rounds(), verify_md(), verify_index(), verify_lesson(),
              verify_assets()]
    rnd_g, md_g, idx_g, les_g, ast_g = groups
    drift = lesson.speech_drift()

    # assets 는 '통과해야 하는' 항목이 아니다 — 그림이 다르면 알려주기만 한다.
    blocking_ok = (
        rnd_g["fail_count"] == 0 and rnd_g["total"] > 0
        and md_g["fail_count"] == 0 and md_g["missing_count"] == 0
        and idx_g["ok"] == idx_g["total"]
        # ★ lesson 은 **없는 것**으로는 막지 않는다. 저장 경로(store.save)가 없는
        #   lesson 은 건너뛰므로 망가질 것이 없다. 새 문제집은 집필 직후 05/ 가 아직
        #   없어서(1부 빌드 전) 이 줄이 문항 교정 저장을 통째로 막았다(실측 2026-11-01
        #   컴활 m01: lesson 0/4). 있는데 어긋나는 것(fail)만 막는다.
        and les_g["fail_count"] == 0
    )
    return {
        "ok": blocking_ok,
        "book": paths.book_dir(),
        "groups": groups,
        # ★ 이름으로도 꺼낼 수 있게 같이 준다. groups 를 위치로 언팩하던 곳이
        #   있었고(`md_g, idx_g, les_g, ast_g = v["groups"]`), _rounds 그룹을
        #   더하자 그 한 줄이 500 을 냈다. 그룹을 또 늘릴 수 있으니 위치 언팩은
        #   쓰지 않는다.
        "by_kind": {
            "rounds": rnd_g, "md": md_g, "index": idx_g,
            "lesson": les_g, "assets": ast_g,
        },
        "speech_drift": drift,
        "summary": {
            "rounds": f"{rnd_g['ok']}/{rnd_g['total']}",
            "md": f"{md_g['ok']}/{md_g['total']}",
            "index": f"{idx_g['ok']}/{idx_g['total']}",
            "lesson": f"{les_g['ok']}/{les_g['total']}",
            "assets": f"{ast_g['ok']}/{ast_g['total']}",
            "speech_drift": len(drift),
        },
        "gate": ("저장 경로를 열 수 있습니다." if blocking_ok else
                 "★ 바이트 충실도 검증 실패 — 저장하면 원본이 손상됩니다. "
                 "렌더러를 고친 뒤 다시 검증하십시오."),
    }


def _main() -> int:
    import sys
    r = run_all()
    if r.get("error"):
        print("[error]", r["error"])
        return 2
    s = r["summary"]
    # ★ 기대 숫자를 문장에 박지 않는다 — 회차가 m01~m09 로 늘면 그대로 커진다.
    print(f"BOOK: {r['book']}")
    print(f"  _rounds/*.json                 {s['rounds']}")
    print(f"  02/*.md                        {s['md']}")
    print(f"  02/_index.json + stats         {s['index']}")
    print(f"  05/*/source/lesson_*.json      {s['lesson']}")
    print(f"  02/assets/*.svg                {s['assets']}  (참고용, 게이트 아님)")
    print()
    if r["speech_drift"]:
        print(f"  [drift] 낭독문이 _rounds 와 다른 문항 {len(r['speech_drift'])}건 "
              "— TTS 손질로 보입니다. 낭독문을 직접 고치지 않는 한 유지됩니다.")
        for d in r["speech_drift"]:
            print(f"          {d['id']} ({d['bundle']})")
        print()
    for g in r["groups"]:
        for f in (g.get("fail") or []):
            print(f"  [fail] {g['kind']}  {f.get('id') or f.get('bundle') or f.get('file')}")
            if f.get("error"):
                print(f"         {f['error']}")
            else:
                print(f"         line {f.get('at_line')}  기대={f.get('expected')}")
                print(f"                    실제={f.get('got')}")
        for r2 in (g.get("results") or []):
            if not r2.get("ok"):
                print(f"  [fail] {r2['file']}: {r2.get('error') or ('line ' + str(r2.get('at_line')))}")
                if r2.get("expected"):
                    print(f"         기대={r2['expected']}")
                    print(f"         실제={r2['got']}")
    print(("[ok] " if r["ok"] else "[FAIL] ") + r["gate"])
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(_main())
