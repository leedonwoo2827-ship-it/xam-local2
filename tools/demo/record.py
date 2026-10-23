# -*- coding: utf-8 -*-
"""시연 영상 녹화 — 앱 조작 장면만 (tools/demo/NOTES.md).

    venv\\Scripts\\python tools\\demo\\record.py [--port 8871] [--out _context\\XAM-LOCAL-v2-데모.mp4] [--voice F1]

--voice 를 주면 낭독을 입힌다: 자막 문구를 발음대로 바꿔 supertonic3-tts(별도 앱, 기본
D:\\00work\\260910-무료TTS앱-슈퍼토닉3)로 먼저 굽고, 녹화하면서 장면마다 그 낭독이 끝날
때까지 기다린 뒤, 자막이 뜬 시각에 각 음성을 얹어 합친다. 자막과 소리가 어긋나지 않는다.

Playwright 가 실제 앱을 조작하며 녹화한다. 화면 위에 얹는 것은 셋뿐이다:
  · 커서 점 + 클릭 물결(녹화에는 마우스가 안 찍힌다)
  · 왼쪽 위 작은 단계 라벨
  · 아래 자막 띠 — 메뉴 설명(사용자 지시 문구는 NOTES.md 원문 그대로)
자막은 시각을 재서 같은 이름의 .srt 로도 낸다. 녹화(webm)는 ffmpeg 로 1920×1080 mp4 로 바꾼다.

★ 앱을 바꾸지 않는다 — 읽고 누르기만 한다. 듣기 검수 판정만 실제로 남는다(시연 검수자 이름으로).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

W, H = 1600, 900

OVERLAY_JS = r"""
(() => {
  if (window.__demo) return;
  const css = document.createElement('style');
  css.textContent = `
  #dm-cur{position:fixed;z-index:99999;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
    background:rgba(196,28,11,.28);border:2px solid #c41c0b;pointer-events:none;transition:left .45s ease,top .45s ease}
  .dm-rip{position:fixed;z-index:99998;width:16px;height:16px;margin:-8px 0 0 -8px;border-radius:50%;
    border:3px solid #c41c0b;pointer-events:none;animation:dmrip .6s ease-out forwards}
  @keyframes dmrip{to{transform:scale(4);opacity:0}}
  #dm-step{position:fixed;z-index:99997;left:262px;top:10px;background:#1b1f19;color:#fffff3;font:700 13px Pretendard,sans-serif;
    padding:5px 12px;border-radius:999px;opacity:0;transition:opacity .3s}
  #dm-cap{position:fixed;z-index:99997;left:50%;bottom:26px;transform:translateX(-50%);max-width:1100px;
    background:rgba(27,31,25,.88);color:#fffff3;font:600 19px/1.55 Pretendard,sans-serif;padding:12px 22px;border-radius:12px;
    text-align:center;opacity:0;transition:opacity .35s}
  .dm-hl{outline:3px solid #c41c0b !important;outline-offset:3px;border-radius:8px}`;
  document.head.appendChild(css);
  const cur = Object.assign(document.createElement('div'), {id: 'dm-cur'});
  const step = Object.assign(document.createElement('div'), {id: 'dm-step'});
  const cap = Object.assign(document.createElement('div'), {id: 'dm-cap'});
  document.body.append(cur, step, cap);
  cur.style.left = '800px'; cur.style.top = '450px';
  window.__demo = {
    move(x, y) { cur.style.left = x + 'px'; cur.style.top = y + 'px'; },
    ripple(x, y) { const r = document.createElement('div'); r.className = 'dm-rip';
      r.style.left = x + 'px'; r.style.top = y + 'px'; document.body.appendChild(r); setTimeout(() => r.remove(), 700); },
    step(t) { step.textContent = t; step.style.opacity = t ? 1 : 0; },
    cap(t) { cap.textContent = t; cap.style.opacity = t ? 1 : 0; },
    hl(sel, on) { document.querySelectorAll('.dm-hl').forEach(n => n.classList.remove('dm-hl'));
      if (on && sel) { const n = document.querySelector(sel); if (n) n.classList.add('dm-hl'); } },
  };
})();
"""


# 자막 → 낭독(소리 나는 대로). 약어·기호는 강사가 읽는 소리로. 숫자는 core.speak 가 마저 바꾼다.
READ = [("XAM LOCAL v2", "엑스잼 로컬 브이투"), ("06/", "공육"), ("OCR", "오씨알"), ("SVG", "에스브이지"),
        ("HTML", "에이치티엠엘"), ("PPTX", "피피티엑스"), ("CLI", "씨엘아이"), ("IP 허브", "아이피 허브"),
        ("PC", "피씨"), ("OK", "오케이"), ("Space", "스페이스"), ("→", ", "), ("·", ", "), ("—", ", "),
        ("①", "일,"), ("②", "이,"), ("③", "삼,"), ("[", ""), ("]", ""), ("'", ""),
        ("O 괜찮음", "오 키는 괜찮음"), ("F 고칠 곳", "에프 키는 고칠 곳"), ("▶", "재생 단추")]


def to_read(text: str) -> str:
    out = text
    for a, b in sorted(READ, key=lambda x: -len(x[0])):
        out = out.replace(a, b)
    try:
        from core.speak import speak_numbers
        out = speak_numbers(out)
    except Exception:                                   # noqa: BLE001
        pass
    import re
    out = " ".join(out.split())
    # 「SVG 가」 처럼 띄어 쓴 조사는 붙여 읽는다 — 띄우면 TTS 가 조사 앞에서 쉰다.
    out = re.sub(r"(\S) (가|을|를|은|는|에서|까지|입니다)(?=[\s,.]|$)", r"\1\2", out)
    return re.sub(r"\s+,", ",", out)


class Demo:
    def __init__(self, page, base: str, voice: dict | None = None):
        self.p = page
        self.base = base
        self.t0 = time.monotonic()
        self.cues: list[tuple[float, float, str]] = []
        self._cap_at = None
        self._cap = ""
        self.voice = voice or {}          # 자막 → (wav, 초)
        self.said: list[tuple[float, str]] = []
        self._busy_until = 0.0

    def now(self) -> float:
        return time.monotonic() - self.t0

    def ov(self):
        self.p.evaluate(OVERLAY_JS)

    def go(self, hash_: str, wait: float = 2.0):
        self.p.evaluate(f"location.hash = {json.dumps(hash_)}")
        self.p.wait_for_timeout(int(wait * 1000))
        self.ov()

    def step(self, t: str):
        self.ov()
        self.p.evaluate(f"__demo.step({json.dumps(t)})")

    def cap(self, t: str, hold: float = 0.0):
        self.ov()
        # 낭독 모드: 앞 자막의 소리가 끝나기 전에는 다음 자막으로 넘어가지 않는다.
        left = self._busy_until - self.now()
        if left > 0:
            self.p.wait_for_timeout(int(left * 1000))
        if self._cap and self._cap_at is not None:
            self.cues.append((self._cap_at, self.now(), self._cap))
        self._cap, self._cap_at = t, (self.now() if t else None)
        self.p.evaluate(f"__demo.cap({json.dumps(t)})")
        if t and t in self.voice:
            wav, sec = self.voice[t]
            self.said.append((self.now(), wav))
            self._busy_until = self.now() + sec + 0.35
            hold = max(hold, min(sec + 0.35, 2.5))   # 나머지는 다음 동작과 겹쳐 흐른다
        if hold:
            self.p.wait_for_timeout(int(hold * 1000))

    def point(self, sel: str, click: bool = True, pause: float = 0.6, hl: bool = False):
        self.ov()
        el = self.p.locator(sel).first
        el.scroll_into_view_if_needed()
        b = el.bounding_box()
        if not b:
            return
        x, y = b["x"] + min(b["width"] / 2, 120), b["y"] + b["height"] / 2
        self.p.evaluate(f"__demo.move({x},{y})")
        if hl:
            # ★ :has-text 같은 Playwright 선택자는 querySelector 가 못 읽는다 — 로케이터로 직접 건다.
            el.evaluate("n => n.classList.add('dm-hl')")
        self.p.wait_for_timeout(550)
        if click:
            self.p.evaluate(f"__demo.ripple({x},{y})")
            self.p.mouse.click(x, y)
        self.p.wait_for_timeout(int(pause * 1000))
        if hl:
            el.evaluate("n => n.classList.remove('dm-hl')")

    def keys(self, k: str, pause: float = 0.8):
        self.p.keyboard.press(k)
        self.p.wait_for_timeout(int(pause * 1000))

    def wait(self, s: float):
        self.p.wait_for_timeout(int(s * 1000))

    def srt(self, path: str):
        self.cap("")
        def ts(t):
            ms = int(round(t * 1000))
            return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
        with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
            for i, (a, b, t) in enumerate(self.cues, 1):
                f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n\n")


def scenario(d: Demo, kind_key: str):
    """앱 조작 장면. 문구는 NOTES.md 의 사용자 원문을 그대로 쓴다."""
    key = kind_key
    d.go("#/home", 2.5)
    d.step("XAM LOCAL v2")
    d.cap("실전모의고사에서 하향식으로 강의 패키지를 만드는 출발점 — XAM LOCAL v2 입니다.", 2.5)
    d.cap("1부 문항, 2부 이론 노트, 3부 해설영상까지 — 세 부분을 이 앱에서 만듭니다.", 3.0)

    # 1. OCR
    d.step("1부 · OCR 검수")
    d.point('a[data-nav="oc"]', pause=1.8)
    d.cap("OCR 을 하는 이유는, 수식과 표 등 다양하게 작성된 것을 매핑하기 위해서이므로, "
          "복사가 가능한 텍스트는 다음 정리 프로세스를 더 정확하게 완료할 수 있습니다.", 5.5)
    d.keys("Escape", 1.0)

    # 2. 문항
    d.step("1부 · 문항 집필 · 교정")
    d.point('a[data-nav="q"]', pause=1.6)
    d.cap("자사 회차 문항을 교정합니다. 저장하면 다섯 파일이 함께 바뀌어 웹까지 그대로 갑니다.", 3.2)
    d.keys("Escape", 1.0)

    # 3. 해설 모아 노트 구조화
    d.step("2부 · 해설 모아 노트 구조화")
    d.point('a[data-nav="ol"]', pause=1.8)
    d.cap("우리 모의고사 해설을 과목 → 항목 → 상세로 모으고 중복을 정돈합니다.", 1.5)
    d.point(".ol-card:nth-child(2)", pause=1.6)
    d.p.mouse.wheel(0, 500)
    d.cap("사람이 이 목차를 승인하면, 이론 요약 노트가 그 목차를 따릅니다.", 3.0)

    # 4. 이론 요약 노트
    d.step("2부 · 이론 요약 노트")
    d.point('a[data-nav="s"]', pause=2.0)
    d.cap("이론 요약 노트는 텍스트 위주입니다.", 3.0)

    # 5. 요약반 강의 노트
    d.step("2부 · 요약반 강의 노트")
    d.go(f"#/lecture/summary/{key}", 2.5)
    d.point('a[data-nav="ls"]', click=False, pause=0.4)
    d.cap("요약반 강의 노트는 슬라이드에 의무적으로 표와 SVG 가 들어가서, 추후에 이미지화 영상을 만드는 데 기여합니다.", 4.5)
    d.point(".lc-steps", click=False, pause=0.3, hl=True)
    d.cap("① 자막대본 → ② 낭독대본 → ③ SVG 추가 슬라이드. '사람' 단계는 승인해야 다음이 열립니다.", 3.5)
    d.point(".lc-row:nth-of-type(2) .lc-row-h", pause=1.8)
    d.cap("장마다 자막과, 소리 나는 대로 적은 낭독이 나란히 있고, 도식이 붙습니다.", 3.0)
    d.p.mouse.wheel(0, 380)
    d.wait(1.5)
    d.point("text=▶ 미리듣기", pause=3.0)
    d.cap("▶ 를 누르면 영상과 같은 엔진·목소리로 그 장을 바로 들어 봅니다.", 2.5)
    d.p.mouse.wheel(0, -2000)
    d.point("button:has-text('노트 빌드')", click=False, pause=0.3, hl=True)
    d.cap("메뉴마다 그 노트의 [노트 빌드] — 원고 HTML · 강의 PPTX · 장별 자막·낭독 목록. 영상은 다른 PC 에서 이미지화 작업을 한 후 하이퍼프레임을 활용해 렌더링을 합니다.", 4.5)

    # 6. 듣기 검수
    d.step("2부 · 듣기 검수 — 여러 사람")
    d.go(f"#/listen/summary/{key}", 3.0)
    d.cap("듣기 검수는 여러 사람이 각자 자리에서 같은 과목을 듣고 장마다 OK · 고칠 곳을 남깁니다.", 3.0)
    d.point("#ls-play", pause=3.5)
    d.point("#ls-ok", pause=1.6)
    d.point("#ls-play", pause=2.5)
    d.point("#ls-ok", pause=1.6)
    d.cap("Space 듣기 · O 괜찮음 · F 고칠 곳. 낭독을 고치면 그 장의 OK 는 낡아 다시 들어야 합니다.", 3.5)

    # 7. 종합반
    d.step("2부 · 종합반 강의 노트")
    d.go(f"#/lecture/full/{key}", 2.5)
    d.cap("종합반 강의 노트는 슬라이드의 양을 증폭시켜서, 추후 종합반 영상덱에 기존에 생산된 모든 산물을 모아 "
          "함께 다량의 롱폼을 만드는 데 기여합니다.", 5.0)
    d.point(".lc-factor", click=False, pause=0.3, hl=True)
    d.cap("이후 미노출 종합본 HTML 을 만들고, 문제편을 제외한 초단기서의 핵심요약 HTML 까지 만듭니다.", 4.0)

    # 8. 해설영상 — 문항 슬라이드를 쪼갠 뒤 자막대본·발음대본
    d.step("3부 · 해설영상")
    d.point('a[data-nav="sl"]', pause=2.5)
    d.cap("3부 해설영상 — 문제 HTML 을 잘라 증폭한 영상 전체를 이 앱에서 만듭니다. 먼저 문항 슬라이드를 쪼갭니다.", 3.5)
    d.p.mouse.wheel(0, 700)
    d.wait(1.0)
    d.cap("장수를 확정하면 장마다 자막대본과 발음대본이 다시 나뉩니다. 문항이 여러 장이면 낭독을 장마다 나눠 읽습니다.", 3.0)
    d.go("#/video/m01-1", 3.0)
    d.point(".vd-scene:nth-child(3)", pause=2.0)
    d.point(".vd-2col", click=False, pause=0.3, hl=True)
    d.cap("영상 화면에서 씬마다 자막과 발음을 나란히 고치고, 그 씬만 다시 합성해 들어 봅니다.", 3.0)
    d.point("button:has-text('이 씬 재합성')", click=False, pause=0.3, hl=True)
    d.cap("발음대본은 이 앱에서 다 완료하는 것이 목표입니다. 그리고 렌더링까지 이 앱에서 합니다.", 3.0)

    # 9. 발음 사전 — 넣기 · 적용 · 재굽기
    d.step("발음 사전")
    d.point('a[data-nav="dc"]', pause=2.5)
    d.cap("흩어져 있던 발음 사전 300여 개를 이 앱 하나에 모았습니다.", 2.5)
    d.point(".dc-miss", click=False, pause=0.3, hl=True)
    d.cap("왼쪽은 문항 낭독과 강의 노트에 나오는데 아직 사전에 없는 말입니다. 많이 나온 순서입니다.", 3.0)
    d.point(".dc-flow", click=False, pause=0.3, hl=True)
    d.cap("사전에 넣고, 원고에 적용하고, 소리를 다시 굽는 것까지 여기서 끝냅니다.", 3.0)

    # 10. 오른쪽 — 작업 현황
    d.step("작업 현황 (오른쪽)")
    d.go(f"#/lecture/summary/{key}", 2.5)
    d.point(".st-board", click=False, pause=0.3, hl=True)
    d.cap("오른쪽은 평소 작업 현황입니다 — 지금 하는 일, 고친 뒤 반영할 것, 다음에 할 일. CLI 렌더도 잡아 보여 줍니다.", 4.5)
    d.point("#ch-mode", pause=1.2)
    d.cap("시장조사나 질문이 필요할 때만 대화로 바꿉니다. 실행은 승인 카드를 눌러야 진행됩니다.", 3.5)
    d.point("#ch-mode", pause=1.0)

    # 1부·3부 빌드
    d.step("1부 빌드 · 3부 빌드")
    d.point('a[data-nav="p"]', pause=2.5)
    d.p.mouse.wheel(0, 900)
    d.wait(1.0)
    d.cap("1부 빌드는 문제집을, 3부 빌드는 해설영상 링크까지 묶어 검토합니다. 사이트 업로드만 IP 허브가 가져가서 합니다.", 4.0)
    d.step("")
    d.cap("", 0.5)


class _Stub:
    """브라우저 없이 시나리오를 훑어 자막 문구만 모은다(낭독을 먼저 굽기 위해)."""
    def __init__(self):
        self.texts: list[str] = []

    @property
    def p(self):
        return self

    @property
    def mouse(self):
        return self

    def __getattr__(self, name):
        return lambda *a, **k: None

    def cap(self, t, hold=0.0):
        if t and t not in self.texts:
            self.texts.append(t)


def bake_voice(key: str, voice: str, app: str, work: str) -> dict:
    stub = _Stub()
    scenario(stub, key)
    rows = [{"id": f"c{i:02d}", "read": to_read(t), "text": t} for i, t in enumerate(stub.texts, 1)]
    os.makedirs(work, exist_ok=True)
    inp = os.path.join(work, "lines.json")
    with open(inp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    py = os.path.join(app, ".venv", "Scripts", "python.exe")
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_supertonic.py")
    subprocess.run([py, here, inp, work, "--app", app, "--voice", voice], check=True,
                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    with open(os.path.join(work, "durations.json"), encoding="utf-8") as f:
        dur = json.load(f)
    return {r["text"]: (os.path.join(work, f"{r['id']}.wav"), float(dur[r["id"]])) for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8871)
    ap.add_argument("--key", default="planning")
    ap.add_argument("--out", default=os.path.join("_context", "XAM-LOCAL-v2-데모.mp4"))
    ap.add_argument("--voice", default="", help="낭독 목소리(예: F1 = supertonic 여성1). 비우면 무음")
    ap.add_argument("--tts-app", default=r"D:\00work\260910-무료TTS앱-슈퍼토닉3")
    a = ap.parse_args()
    vwork = tempfile.mkdtemp(prefix="xam-demo-voice-")
    voice = bake_voice(a.key, a.voice, a.tts_app, vwork) if a.voice else {}
    from playwright.sync_api import sync_playwright

    base = f"http://127.0.0.1:{a.port}/"
    vid_dir = tempfile.mkdtemp(prefix="xam-demo-")
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H}, record_video_dir=vid_dir,
                            record_video_size={"width": W, "height": H})
        ctx.add_init_script("try{localStorage.setItem('xam.listen.name','시연 검수자');"
                            "localStorage.setItem('xam.chat.mode','status')}catch(e){}")
        page = ctx.new_page()
        t_page = time.monotonic()                  # 녹화는 페이지가 생길 때 시작한다
        page.goto(base + "#/home")
        page.wait_for_timeout(2500)
        d = Demo(page, base, voice)
        d.t0 = time.monotonic()
        lead = d.t0 - t_page
        try:
            scenario(d, a.key)
        finally:
            srt = os.path.splitext(a.out)[0] + ".srt"
            d.srt(srt)
            video = page.video.path()
            ctx.close()
            b.close()
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    # 앞의 첫 로딩(실측 lead 초)을 잘라 자막 시각(t0 기준)과 맞춘다.
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{lead:.3f}", "-i", video]
    filt = "[0:v]scale=1920:1080:flags=lanczos,fps=30[v]"
    maps = ["-map", "[v]"]
    if d.said:
        for _t, wav in d.said:
            cmd += ["-i", wav]
        parts = []
        for i, (t, _w) in enumerate(d.said, 1):
            ms = max(0, int(t * 1000))
            parts.append(f"[{i}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
        mix = "".join(f"[a{i}]" for i in range(1, len(d.said) + 1))
        filt += ";" + ";".join(parts) + f";{mix}amix=inputs={len(d.said)}:normalize=0,loudnorm=I=-16:TP=-1.5[a]"
        maps += ["-map", "[a]", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-filter_complex", filt] + maps + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                                               "-movflags", "+faststart", a.out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(vid_dir, ignore_errors=True)
    shutil.rmtree(vwork, ignore_errors=True)
    print("영상:", os.path.abspath(a.out))
    print("자막:", os.path.abspath(srt))


if __name__ == "__main__":
    sys.exit(main())
