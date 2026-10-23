# -*- coding: utf-8 -*-
"""인트로 + 본편 + 아웃트로를 한 편으로 합친다.

    venv\\Scripts\\python tools\\demo\\join.py [--voice M1] [--name 남성1]

인트로는 앱 바탕색(리넨)으로 밝아지며 끝나고 아웃트로는 그 색에서 시작한다 — 본편과 그대로 잇는다.
세 파일의 해상도·fps·음성 형식을 하나로 맞춰 다시 인코딩한다(concat 필터). 자막(.srt)은 본편 것을
인트로 길이만큼 밀어 함께 낸다.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CTX = os.path.join(ROOT, "_context")


def dur(p: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def shift_srt(src: str, dst: str, sec: float) -> None:
    def f(m):
        h, mi, s, ms = map(int, m.groups())
        t = h * 3600000 + mi * 60000 + s * 1000 + ms + int(round(sec * 1000))
        return f"{t // 3600000:02d}:{t // 60000 % 60:02d}:{t // 1000 % 60:02d},{t % 1000:03d}"
    text = open(src, encoding="utf-8-sig").read()
    text = re.sub(r"(\d\d):(\d\d):(\d\d),(\d\d\d)", f, text)
    open(dst, "w", encoding="utf-8-sig", newline="\r\n").write(text.replace("\r\n", "\n"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="M1")
    ap.add_argument("--name", default="남성1")
    a = ap.parse_args()
    intro = os.path.join(CTX, f"XAM-LOCAL-v2-intro_{a.voice}.mp4")
    body = os.path.join(CTX, f"XAM-LOCAL-v2-데모_{a.name}.mp4")
    outro = os.path.join(CTX, f"XAM-LOCAL-v2-outro_{a.voice}.mp4")
    out = os.path.join(CTX, f"XAM-LOCAL-v2-완성_{a.name}.mp4")
    for p in (intro, body, outro):
        if not os.path.isfile(p):
            raise SystemExit(f"없음: {p}")
    norm = ("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
            "fps=30,format=yuv420p,setsar=1")
    filt = (f"[0:v]{norm}[v0];[1:v]{norm}[v1];[2:v]{norm}[v2];"
            "[0:a]aresample=48000,aformat=channel_layouts=stereo[a0];"
            "[1:a]aresample=48000,aformat=channel_layouts=stereo[a1];"
            "[2:a]aresample=48000,aformat=channel_layouts=stereo[a2];"
            "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", intro, "-i", body, "-i", outro,
                    "-filter_complex", filt, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", out], check=True)
    srt = os.path.splitext(body)[0] + ".srt"
    if os.path.isfile(srt):
        shift_srt(srt, os.path.splitext(out)[0] + ".srt", dur(intro))
    print("완성:", out, f"({dur(out):.1f}초 = 인트로 {dur(intro):.1f} + 본편 {dur(body):.1f} + 아웃트로 {dur(outro):.1f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
