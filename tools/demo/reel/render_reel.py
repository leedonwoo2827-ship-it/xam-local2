# -*- coding: utf-8 -*-
"""쇼릴(인트로·아웃트로) 렌더 — HTML 타임라인을 프레임마다 멈춰 찍어 mp4 로.

    venv\\Scripts\\python tools\\demo\\reel\\render_reel.py intro|outro [--voice M1] [--fps 30]

HTML 은 window.__seek(t) · window.DURATION · window.CUES([{t, read}]) 를 낸다(reel.js).
낭독은 supertonic3-tts(tools/demo/tts_supertonic.py)로 **먼저** 굽고 cue 의 t 에 얹는다.
★ supertonic 은 같은 문장도 구울 때마다 길이가 조금 다르다 — 타임라인을 손으로 맞추면 매번
  어긋난다. 그래서 앞 낭독이 안 끝났는데 다음 cue 가 오면 **그 자리에서 화면을 멈춰 기다린다**
  (설계 시각 → 실제 시각 지도를 만들어 프레임을 늘린다).
같은 입력 = 같은 영상(CSS 전환 없이 t 로만 계산하므로).
★ 글꼴을 앱 서버(:8871 /static/fonts)에서 받는다 — 서버가 떠 있어야 한다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=["intro", "outro"])
    ap.add_argument("--voice", default="M1")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--tts-app", default=r"D:\00work\260910-무료TTS앱-슈퍼토닉3")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    out = a.out or os.path.join(ROOT, "_context", f"XAM-LOCAL-v2-{a.name}_{a.voice}.mp4")
    from playwright.sync_api import sync_playwright

    work = tempfile.mkdtemp(prefix=f"reel-{a.name}-")
    frames = os.path.join(work, "f")
    os.makedirs(frames)
    url = "file:///" + os.path.join(HERE, f"{a.name}.html").replace("\\", "/")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.goto(url)
        pg.evaluate("window.__ready()")
        pg.wait_for_timeout(400)
        dur = float(pg.evaluate("window.DURATION"))
        cues = pg.evaluate("window.CUES || []")

        # 1) 낭독을 먼저 굽고 길이를 잰다
        durs, vdir = {}, os.path.join(work, "v")
        if cues and a.voice:
            rows = [{"id": f"r{i:02d}", "read": c["read"]} for i, c in enumerate(cues)]
            inp = os.path.join(work, "lines.json")
            json.dump(rows, open(inp, "w", encoding="utf-8"), ensure_ascii=False)
            py = os.path.join(a.tts_app, ".venv", "Scripts", "python.exe")
            subprocess.run([py, os.path.join(HERE, "..", "tts_supertonic.py"), inp, vdir, "--app", a.tts_app,
                            "--voice", a.voice], check=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            durs = json.load(open(os.path.join(vdir, "durations.json"), encoding="utf-8"))

        # 2) 멈춤 지도 — cue i 의 설계 시각에 앞 낭독이 안 끝났으면 그만큼 멈춘다
        holds, real, prev_end = [], [], 0.0
        for i, c in enumerate(cues):
            # 멈추는 자리는 그 장면이 시작되기 직전(scene) — 앞 장면이 다 자리 잡은 때다.
            # 장면이 움직이는 도중에 멈추면 화면이 얼어 보인다.
            at = float(c.get("scene", c["t"]))
            shift = sum(h for _t, h in holds)
            want = c["t"] + shift
            if durs and prev_end + 0.25 > want:
                holds.append((at - 1.0 / a.fps, prev_end + 0.25 - want))
                want = prev_end + 0.25
            real.append(want)
            prev_end = want + float(durs.get(f"r{i:02d}", 0))
        tail = max(0.0, prev_end + 0.6 - (dur + sum(h for _t, h in holds)))
        if tail:
            holds.append((max(0.0, dur - 1.2), tail))       # 마지막 낭독이 길면 끝나기 직전에 기다린다
        if holds:
            print("멈춤:", ", ".join(f"{t:.1f}초에 {h:.2f}초" for t, h in holds))

        # 3) 프레임 — 설계 시각을 따라가다 멈춤 지점에서 같은 장면을 더 찍는다
        hq = sorted(holds)
        i = 0
        step = 1.0 / a.fps
        t = 0.0
        while t < dur - 1e-6:
            pg.evaluate(f"__seek({t:.4f})")
            path = os.path.join(frames, f"{i:05d}.png")
            pg.screenshot(path=path)
            i += 1
            while hq and hq[0][0] <= t + 1e-6:
                for _k in range(int(round(hq[0][1] * a.fps))):
                    shutil.copyfile(path, os.path.join(frames, f"{i:05d}.png"))
                    i += 1
                hq.pop(0)
            t += step
        b.close()

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps), "-i", os.path.join(frames, "%05d.png")]
    filt, maps = [], ["-map", "0:v"]
    if cues and durs:
        for i, c in enumerate(cues):
            cmd += ["-i", os.path.join(vdir, f"r{i:02d}.wav")]
            ms = int(real[i] * 1000)
            filt.append(f"[{i + 1}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
        mix = "".join(f"[a{i}]" for i in range(len(cues)))
        filt.append(f"{mix}amix=inputs={len(cues)}:normalize=0,loudnorm=I=-16:TP=-1.5,apad[a]")
        cmd += ["-filter_complex", ";".join(filt)]
        maps = ["-map", "0:v", "-map", "[a]", "-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += maps + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(work, ignore_errors=True)
    print("영상:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
