# -*- coding: utf-8 -*-
r"""`04-2/NN회_강의_LO-HI.pptx` → `05/<번들>/images/slide_NN.png`.

**영상이 쓰는 슬라이드가 여기서 나온다.** pptx 는 한 폴더에 모여 있고(사람이 여는
자리), 그림파일은 번들 폴더로 간다(렌더가 읽는 자리).

★ 왜 PowerPoint COM 인가. 실제로 강의에서 열릴 프로그램이 PowerPoint 이고, 사람이
  ④에서 확정한 화면이 바로 그 화면이다. 다른 렌더러로 뽑으면 그 렌더러의 해석을
  보는 것이지 시청자가 볼 화면을 보는 것이 아니다(글꼴 대체·줄바꿈이 특히 갈린다).
  그래서 **캡처로 몰래 폴백하지 않는다** — 폴백하면 확정한 것과 다른 영상이 나간다.

★ 파일 이름은 **씬 번호**다. `slide_{si:02d}.png` 의 `si` 는 script 의 씬 번호이고,
  카운트다운·간격 씬은 캡처 대상이 아니므로 그 번호는 **비어 있다**(렌더가 Pillow 로
  만든다). 그래서 pptx 장 k 번째 → k 번째 `capture:true` 씬으로 붙인다.
  `deck_capture.capture_deck(deck, out, filenames)` 와 같은 자리에 끼우기 위해
  시그니처를 그것과 같은 모양으로 뒀다 — 둘은 서로 갈아 끼울 수 있어야 한다.

★ 열려 있는 PowerPoint 인스턴스를 잡으므로 **읽기 전용으로 열고 저장하지 않는다.**
  사람이 작업 중인 문서를 건드리면 안 된다.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from core.atomic_io import atomic_write_json
from services.book import paths
from services.deck import pptxdeck

SLIDE_W, SLIDE_H = 1920, 1080


class PowerPointMissing(RuntimeError):
    pass


def available() -> Dict[str, Any]:
    """PowerPoint COM 을 쓸 수 있는가. 화면이 버튼을 잠글 근거."""
    try:
        import win32com.client  # noqa: F401
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "why": "pywin32 가 없습니다 (%s)" % e.__class__.__name__}
    try:
        import pythoncom
        import win32com.client as win32
        pythoncom.CoInitialize()
        try:
            app = win32.Dispatch("PowerPoint.Application")
            return {"ok": True, "version": str(app.Version)}
        finally:
            pythoncom.CoUninitialize()
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False,
                "why": "PowerPoint 를 열 수 없습니다 — 설치돼 있어야 합니다 (%s)"
                       % e.__class__.__name__}


class Session:
    """PowerPoint 인스턴스 하나를 **배치 내내 붙잡는다.**

    ★ 왜 필요한가(실측 2026-08-24). 번들마다 `Dispatch` 하고 `Close` 하면, 마지막
      문서를 닫는 순간 PowerPoint 가 스스로 끝난다. 곧바로 다음 `Dispatch` 를 하면
      죽는 중인 인스턴스를 잡아 `PowerPoint.Application.Presentations` 에서 터진다 —
      100번들 중 23개가 그렇게 실패했다. 인스턴스를 하나 잡고 안 놓으면 없어지는
      문제다.

    ★ **사람이 열어 둔 PowerPoint 가 있으면 그것을 잡는다.** 그래서 우리가
      `Quit()` 하지 않는다 — 남의 작업 창을 닫는 셈이 된다. 우리 프로세스가
      끝나면 참조가 풀리고, 우리가 띄운 것이면 그때 스스로 닫힌다.
    """

    def __init__(self):
        self.app = None
        self._co = False

    def __enter__(self):
        try:
            import pythoncom
            import win32com.client as win32
        except Exception as e:                               # noqa: BLE001
            raise PowerPointMissing(
                "pywin32 가 없습니다. `pip install pywin32` 후 다시 시도하세요.") from e
        # ★ COM 은 STA 스레드가 필요하다. 잡 스레드에서 부르므로 여기서 초기화한다.
        pythoncom.CoInitialize()
        self._co = True
        try:
            self.app = win32.Dispatch("PowerPoint.Application")
        except Exception as e:                               # noqa: BLE001
            self.__exit__(None, None, None)
            raise PowerPointMissing(
                "PowerPoint 를 열 수 없습니다. 이 경로는 Windows + PowerPoint 가 "
                "있어야 합니다 — 캡처로 대신하지 않습니다(확정한 화면과 달라집니다).") from e
        return self

    def __exit__(self, *_exc):
        self.app = None
        if self._co:
            import pythoncom
            pythoncom.CoUninitialize()
            self._co = False

    def reconnect(self):
        """죽은 참조를 버리고 다시 잡는다. 한 번만 시도한다."""
        import win32com.client as win32
        self.app = win32.Dispatch("PowerPoint.Application")

    def slides(self, pptx: str, out_dir: str, filenames: List[str],
               width: int = SLIDE_W) -> List[str]:
        pptx = os.path.abspath(pptx)
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        # ReadOnly=True, Untitled=False, WithWindow=False
        try:
            pres = self.app.Presentations.Open(pptx, True, False, False)
        except Exception:                                    # noqa: BLE001
            self.reconnect()
            pres = self.app.Presentations.Open(pptx, True, False, False)
        saved: List[str] = []
        try:
            n = int(pres.Slides.Count)
            if n != len(filenames):
                raise ValueError(
                    "%s: 장이 %d개인데 붙일 씬은 %d개입니다 — 장을 합치거나 지우셨다면 "
                    "슬라이드 화면의 장수 표에서 ± 로 고쳐 주세요(그래야 음성·자막도 "
                    "같이 따라갑니다)." % (os.path.basename(pptx), n, len(filenames)))
            h = int(round(width * float(pres.PageSetup.SlideHeight)
                          / float(pres.PageSetup.SlideWidth)))
            for i in range(1, n + 1):
                dest = os.path.join(out_dir, filenames[i - 1])
                pres.Slides(i).Export(dest, "PNG", width, h)
                saved.append(dest)
        finally:
            pres.Close()
        return saved


def export(pptx: str, out_dir: str, filenames: List[str],
           width: int = SLIDE_W, session: "Session" = None) -> List[str]:
    """pptx 의 장들을 순서대로 PNG 로 뽑는다. `filenames[i]` = i번째 장의 파일명.

    반환: 저장한 경로 목록. 장 수와 `filenames` 수가 다르면 **예외** —
    부분 내보내기는 이미지↔음성 정렬을 조용히 깨뜨린다.

    ★ 여러 번들을 이어서 뽑을 때는 `Session` 을 만들어 넘긴다. 안 넘기면 이 호출
      하나를 위해 인스턴스를 잡았다 놓는다(위 `Session` 머리말 참조).
    """
    if session is not None:
        return session.slides(pptx, out_dir, filenames, width)
    with Session() as ss:
        return ss.slides(pptx, out_dir, filenames, width)


def capture_scene_index(bundle: str) -> List[int]:
    """script 의 `capture:true` 씬 번호. pptx 장 순서와 1:1 이어야 한다."""
    sp = paths.bundle_script(bundle)
    with open(sp, encoding="utf-8") as f:
        doc = json.load(f)
    return [int(s.get("scene", i)) for i, s in enumerate(doc.get("scenes") or [])
            if s.get("capture")]


def export_bundle(bundle: str, *, book: str = "", clean: bool = True,
                  session: "Session" = None, log=None) -> Dict[str, Any]:
    """번들 하나 — pptx → `images/slide_NN.png` + `images/_source.json`."""
    say = log or (lambda *_a, **_k: None)
    with paths.using_book(book):
        pptx = paths.bundle_pptx(bundle)
        if not os.path.isfile(pptx):
            raise FileNotFoundError(
                "%s: deck.pptx 가 없습니다 — 먼저 [슬라이드 만들기] 를 돌리세요."
                % bundle)
        cap = capture_scene_index(bundle)
        if not cap:
            raise ValueError("%s: script 에 캡처 씬이 없습니다." % bundle)

        img_dir = paths.bundle_images_dir(bundle)
        if clean and os.path.isdir(img_dir):
            # ★ 옛 캡처가 남아 있으면 씬 수가 줄었을 때 고아 PNG 가 남아, 렌더가
            #   그것을 재사용해 어긋난 영상이 나온다. 통째로 지우고 다시 넣는다.
            for fn in os.listdir(img_dir):
                if fn.startswith("slide_") and fn.endswith(".png"):
                    os.remove(os.path.join(img_dir, fn))

        names = ["slide_%02d.png" % si for si in cap]
        saved = export(pptx, img_dir, names, session=session)
        atomic_write_json(paths.bundle_images_manifest(bundle), {
            "version": "1.0", "bundle": bundle, "from": "pptx",
            "pptx": os.path.basename(pptx),
            "pptx_sha256": pptxdeck._sha256(pptx),
            "slides": len(saved), "width": SLIDE_W, "height": SLIDE_H,
            "scene_index": cap,
        }, indent=2, trailing_newline=True)
        say("[이미지] %s  %d장" % (bundle, len(saved)))
        return {"bundle": bundle, "ok": True, "slides": len(saved),
                "dir": paths.rel(img_dir), "scene_index": cap}


def images_ready(bundle: str) -> bool:
    """이 번들의 images/ 가 **지금 pptx 에서 나온 것**인가. 렌더가 재사용할 근거."""
    mf = paths.bundle_images_manifest(bundle)
    pptx = paths.bundle_pptx(bundle)
    if not (os.path.isfile(mf) and os.path.isfile(pptx)):
        return False
    try:
        with open(mf, encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, json.JSONDecodeError):
        return False
    if m.get("pptx_sha256") != pptxdeck._sha256(pptx):
        return False
    try:
        cap = capture_scene_index(bundle)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if list(m.get("scene_index") or []) != cap:
        return False
    d = paths.bundle_images_dir(bundle)
    return all(os.path.isfile(os.path.join(d, "slide_%02d.png" % si)) for si in cap)


def export_round(round_code: str, *, book: str = "", log=None,
                 session: "Session" = None) -> List[Dict[str, Any]]:
    with paths.using_book(book):
        codes = pptxdeck.bundles_of(round_code)
    return export_many(codes, book=book, log=log, session=session)


def export_many(bundles: List[str], *, book: str = "", log=None,
                session: "Session" = None) -> List[Dict[str, Any]]:
    """여러 번들 — **인스턴스 하나로** 뽑는다. 화면의 잡이 이걸 쓴다."""
    if session is not None:
        return [export_bundle(b, book=book, session=session, log=log)
                for b in bundles]
    with Session() as ss:
        return [export_bundle(b, book=book, session=ss, log=log)
                for b in bundles]
