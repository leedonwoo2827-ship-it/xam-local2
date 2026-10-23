# -*- coding: utf-8 -*-
"""시연 낭독 — supertonic3-tts 앱(별도 저장소)의 엔진으로 문장들을 wav 로 굽는다.

    <supertonic>\\.venv\\Scripts\\python tools\\demo\\tts_supertonic.py <in.json> <out_dir> [--app <supertonic 폴더>] [--voice F1]

in.json = [{"id": "c01", "read": "소리 나는 대로 적은 문장"}, …]
out_dir/<id>.wav 와 out_dir/durations.json({id: 초}) 을 쓴다.

★ 그 앱의 venv 로 실행한다(onnx 모델·발음사전이 그쪽에 있다). 앱 폴더를 cwd 로 잡아야
  설정의 상대경로(config/·assets/)가 풀린다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("inp")
    ap.add_argument("out_dir")
    ap.add_argument("--app", default=r"D:\00work\260910-무료TTS앱-슈퍼토닉3")
    ap.add_argument("--voice", default="F1")
    ap.add_argument("--speed", type=float, default=1.05)
    a = ap.parse_args()
    inp, out_dir = os.path.abspath(a.inp), os.path.abspath(a.out_dir)
    os.chdir(a.app)
    sys.path.insert(0, os.path.join(a.app, "src"))
    from supertonic_tts.audio_io import write_wav
    from supertonic_tts.engine import Engine

    with open(inp, encoding="utf-8") as f:
        rows = json.load(f)
    os.makedirs(out_dir, exist_ok=True)

    async def run():
        eng = await Engine.get()
        dur = {}
        for r in rows:
            wav = await eng.synth(r["read"], voice_code=a.voice, lang="ko", speed=a.speed)
            p = os.path.join(out_dir, f"{r['id']}.wav")
            write_wav(p, wav, eng.sample_rate)
            dur[r["id"]] = round(len(wav) / float(eng.sample_rate), 3)
            print(f"{r['id']} {dur[r['id']]:.2f}s", flush=True)
        return dur

    dur = asyncio.run(run())
    with open(os.path.join(out_dir, "durations.json"), "w", encoding="utf-8") as f:
        json.dump(dur, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
