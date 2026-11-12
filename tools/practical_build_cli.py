# -*- coding: utf-8 -*-
"""1부 빌드(실기)를 서버 없이 — 화면의 [빌드 실행] 과 같은 build_round 를 돈다.

  venv\\Scripts\\python tools\\practical_build_cli.py "D:\\00work\\ocr-ouput261108-com2-practical" 1,2,3
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.book import paths  # noqa: E402
from services.practical import build as pb  # noqa: E402


def main() -> int:
    book = sys.argv[1]
    rounds = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1,2,3,4,5,6,7,8,9,10").split(",")]
    with paths.using_book(book):
        for m in rounds:
            print(f"[빌드] {m:02d}회", flush=True)
            r = pb.build_round(m, log=lambda s: print(s, flush=True))
            print(f"  → {r.get('summary')} · 원천 점검 {len(r.get('source_checks') or [])} · 오류 {r.get('errors')}", flush=True)
            for c in r.get("source_checks") or []:
                print(f"    [{c['kind']}] {c['id']} {c['msg']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
