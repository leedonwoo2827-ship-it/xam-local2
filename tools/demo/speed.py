# -*- coding: utf-8 -*-
"""영상 배속 — 음높이는 그대로 두고 빠르게(atempo). 자막(.srt)도 같은 비율로 줄인다.

    venv\\Scripts\\python tools\\demo\\speed.py <입력.mp4> 1.05 [1.1 …]

결과: <입력>_x1.05.mp4 · .srt
"""
from __future__ import annotations

import os
import re
import subprocess
import sys


def main() -> int:
    src = os.path.abspath(sys.argv[1])
    stem = os.path.splitext(src)[0]
    for f in sys.argv[2:]:
        k = float(f)
        out = f"{stem}_x{f}.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                        "-filter_complex", f"[0:v]setpts=PTS/{k}[v];[0:a]atempo={k}[a]",
                        "-map", "[v]", "-map", "[a]", "-r", "30",
                        "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-c:a", "aac", "-b:a", "160k",
                        "-movflags", "+faststart", out], check=True)
        srt = stem + ".srt"
        if os.path.isfile(srt):
            def g(m):
                h, mi, s, ms = map(int, m.groups())
                t = int(round((h * 3600000 + mi * 60000 + s * 1000 + ms) / k))
                return f"{t // 3600000:02d}:{t // 60000 % 60:02d}:{t // 1000 % 60:02d},{t % 1000:03d}"
            text = open(srt, encoding="utf-8-sig").read().replace("\r\n", "\n")
            open(f"{stem}_x{f}.srt", "w", encoding="utf-8-sig", newline="\r\n").write(
                re.sub(r"(\d\d):(\d\d):(\d\d),(\d\d\d)", g, text))
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
