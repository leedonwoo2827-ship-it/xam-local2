"""BOOK 트리의 모든 경로 템플릿 — 여기 한 곳에서만 조립한다.

BOOK 은 도구 #1 이 원격 세션에서 만들어 동기화해 준 외부 트리다. 경로 규칙이
코드 여러 군데에 흩어지면 책이 하나 더 생겼을 때 반드시 한 곳을 빠뜨린다.
"""
from __future__ import annotations

import contextlib
import os
import threading
import re
from typing import Iterator

from core import atomic_io
from core.constants import (
    BOOK_DIR, FALLBACK_QUESTIONS_PER_ROUND, QUESTIONS_PER_BUNDLE, SUMMARY_KEYS,
)

# ── 식별자 ──────────────────────────────────────────────────────────────────
QID_RE = re.compile(r"^m(\d{2})-(\d{2})$")           # m01-07
BUNDLE_RE = re.compile(r"^m(\d{2})-(\d{1,2})$")      # m01-1
ROUND_RE = re.compile(r"^m(\d{2})$")                 # m01


# ★ **이 스레드에서만** 다른 책을 보게 하는 자리. 작업 폴더를 바꾸지 않고 다른
#   품목을 검사·변환해야 할 때가 있다(강의덱 검증, 일괄 변환). 전역 상태를 바꾸면
#   그 사이 화면을 열어 둔 사람이 엉뚱한 책을 보게 되므로 스레드 지역으로 둔다.
_LOCAL = threading.local()


def book_dir() -> str:
    """지금 쓰는 BOOK 경로.

    ★ .env 의 XAM_BOOK 은 '첫 실행 기본값' 이고, 실제로는 작업 폴더 화면에서 고른
      폴더(data/books.json 의 active)를 쓴다. 그래서 상수가 아니라 함수다 —
      이 모듈의 모든 경로 함수가 이걸 거치므로 폴더 전환이 즉시 반영된다.
      books 모듈을 못 불러오는 상황(초기 부팅·순환 import)에서는 상수로 떨어진다.
    """
    forced = getattr(_LOCAL, "book", "")
    if forced:
        return forced
    try:
        from services.book import books
        return books.active_path()
    except Exception:
        return BOOK_DIR


@contextlib.contextmanager
def using_book(path: str):
    """이 블록 안에서만 `book_dir()` 이 `path` 를 돌려준다 (이 스레드 한정).

        with paths.using_book(r"D:/00work/ocr-output-260723"):
            pptxdeck.build_round("m01")

    빈 문자열이면 아무것도 하지 않는다 — 호출부가 `book or ""` 를 그냥 넘길 수 있게.
    """
    if not path:
        yield
        return
    prev = getattr(_LOCAL, "book", "")
    _LOCAL.book = path
    try:
        yield
    finally:
        _LOCAL.book = prev


def exists() -> bool:
    """BOOK 이 쓸 수 있는 상태인가 — _rounds 와 02 가 다 있어야 한다.

    01/ 만 있는 폴더(#1 을 돌리고 #2 를 돌리기 직전)는 False 다. 문항 교정·영상·발행은
    못 하지만 '구조화 MD로 정리' 화면은 된다 — 그 화면은 scan_exists() 를 본다.
    """
    return os.path.isdir(os.path.join(book_dir(), "_rounds")) and \
           os.path.isdir(os.path.join(book_dir(), "02"))


def scan_exists() -> bool:
    """01/ 기출 md 가 있는가 — '구조화 MD로 정리' 화면의 전제."""
    return os.path.isdir(os.path.join(book_dir(), "01"))


def round_codes() -> list[str]:
    """이 폴더에 **실제로 있는** 회차 코드.

    ★ 상수로 두면 안 된다. 빅데이터는 3회차지만 SQLD 는 21회차이고, 어느 책이든
      처음에는 1~2회차만 들어온다. _rounds/mNN.json 을 세어서 만든다.
      _rounds 가 아직 없으면 빈 리스트다 — 호출자가 "아직 없음" 을 그려야 한다.
    """
    d = os.path.join(book_dir(), "_rounds")
    try:
        return sorted(f[:-5] for f in os.listdir(d)
                      if f.endswith(".json") and ROUND_RE.match(f[:-5]))
    except OSError:
        return []


def rel(path: str) -> str:
    """BOOK 상대경로로 되돌린다. _index.json 의 `path` 필드가 이 형식이다."""
    try:
        return os.path.relpath(path, book_dir()).replace("\\", "/")
    except ValueError:
        return path


# ── 식별자 파싱 · 조립 ──────────────────────────────────────────────────────
def qid(round_no: int, question_no: int) -> str:
    """(1, 7) → 'm01-07'. 02/*.md 의 id 이자 ex_problem.src_id 다."""
    return f"m{int(round_no):02d}-{int(question_no):02d}"


def parse_qid(value: str) -> tuple[int, int] | None:
    m = QID_RE.match((value or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def round_code(round_no: int) -> str:
    return f"m{int(round_no):02d}"


def parse_round_code(value: str) -> int | None:
    m = ROUND_RE.match((value or "").strip())
    return int(m.group(1)) if m else None


def bundle_of(round_no: int, question_no: int) -> str:
    """문항 → 그 문항이 실린 영상 번들. 번들은 10문항씩 묶여 있다.

    (1, 7)  → 'm01-1'
    (1, 10) → 'm01-1'
    (1, 11) → 'm01-2'
    (3, 80) → 'm03-8'
    """
    part = (int(question_no) - 1) // QUESTIONS_PER_BUNDLE + 1
    return f"m{int(round_no):02d}-{part}"


def bundle_range(bundle: str) -> tuple[int, int] | None:
    """'m01-3' → (21, 30). 번들이 담당하는 문항 번호 구간."""
    m = BUNDLE_RE.match((bundle or "").strip())
    if not m:
        return None
    part = int(m.group(2))
    lo = (part - 1) * QUESTIONS_PER_BUNDLE + 1
    return lo, lo + QUESTIONS_PER_BUNDLE - 1


def parse_bundle(bundle: str) -> tuple[int, int] | None:
    """'m01-3' → (round=1, part=3)."""
    m = BUNDLE_RE.match((bundle or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def bundles_in_round(round_code: str) -> int:
    """그 회차의 번들 수 — 문항 수에서 계산한다.

    ★ 상수(8)로 고정하면 안 된다. 빅데이터는 80문항/회차라 8개지만, 회차당 문항 수가
      다른 책이 오면(예: 50문항 → 5개) 있지도 않은 번들 3개를 '미생성' 으로 띄운다.
      _rounds 를 못 읽으면 상수로 떨어진다.
    """
    import json
    try:
        with open(rounds_json(round_code), encoding="utf-8") as f:
            n = len(json.load(f).get("questions") or [])
        if n:
            return -(-n // QUESTIONS_PER_BUNDLE)      # 올림
    except (OSError, ValueError):
        pass
    # 못 읽었을 때만 폴백. 상수 BUNDLES_PER_ROUND 는 지웠다(회차 수·문항 수는
    # 책마다 다르고 곧 늘어난다) — 규약 상수인 QUESTIONS_PER_BUNDLE 로만 계산한다.
    return -(-FALLBACK_QUESTIONS_PER_ROUND // QUESTIONS_PER_BUNDLE)


def all_bundles() -> list[str]:
    """이 폴더의 번들 코드.

    회차 수도 회차당 번들 수도 폴더에서 읽는다 — 3회차든 9회차든 21회차든 맞는다.
    """
    return [f"{rc}-{p}"
            for rc in round_codes()
            for p in range(1, bundles_in_round(rc) + 1)]


def all_qids() -> Iterator[str]:
    """이 폴더의 모든 문항 id.

    ★ 회차당 문항 수를 상수로 돌면 안 된다 — 회차마다 다를 수 있다(집필 중인
      마지막 회차가 30문항일 수 있다). 그 회차의 실제 문항 수를 센다.
    """
    from services.book import shape
    for rc in round_codes():
        rn = parse_round_code(rc)
        n = shape.questions_in_round(rc) or FALLBACK_QUESTIONS_PER_ROUND
        for qno in range(1, n + 1):
            yield qid(rn, qno)


# ── _rounds/ 집필 원천 ──────────────────────────────────────────────────────
def rounds_json(round_code_or_no) -> str:
    rc = round_code_or_no if isinstance(round_code_or_no, str) else round_code(round_code_or_no)
    return os.path.join(book_dir(), "_rounds", f"{rc}.json")


# ── 01/ 기출 OCR (읽기 전용) ────────────────────────────────────────────────
def source_md(source_id: str) -> str:
    """derived_from('01-09') → 01/01-09.md. 에디터의 기출 대조용."""
    return os.path.join(book_dir(), "01", f"{source_id}.md")


# ── 02/ 자사 문항 ───────────────────────────────────────────────────────────
def q_md(question_id: str) -> str:
    return os.path.join(book_dir(), "02", f"{question_id}.md")


def q_svg(asset_name: str) -> str:
    """asset_name 은 확장자 없는 이름('m01-02-dmz')이다."""
    name = asset_name if asset_name.endswith(".svg") else f"{asset_name}.svg"
    return os.path.join(book_dir(), "02", "assets", name)


def q_assets_dir() -> str:
    return os.path.join(book_dir(), "02", "assets")


def q_index() -> str:
    return os.path.join(book_dir(), "02", "_index.json")


def q_stats() -> str:
    return os.path.join(book_dir(), "02", "difficulty_stats.json")


# ── 03/ 요약노트 ────────────────────────────────────────────────────────────
def summary_dir() -> str:
    """요약노트 폴더. 화면이 '지금 보고 있는 자리' 를 띄우고 열어 줄 때 쓴다."""
    return os.path.join(book_dir(), "03")


def summary_html(key: str) -> str:
    return os.path.join(book_dir(), "03", f"summary_{key}.html")


def summary_md(key: str) -> str:
    return os.path.join(book_dir(), "03", f"summary_{key}.md")


def summary_index_html() -> str:
    return os.path.join(book_dir(), "03", "summary_index.html")


def summary_keys() -> tuple[str, ...]:
    """03/ 의 요약노트 키 — **폴더에서 읽는다.**

    ★ 업로드본은 `("분석기획","탐색","모델링","결과해석")` 로 못박아 뒀다. 이 PC 의
      실제 파일은 `summary_planning.html` · `explore` · `modeling` · `interpret` 다.
      그래서 요약노트 화면이 404 를 내고, 사전점검은 "요약노트 4종 없음" 을 냈다.
      키는 책마다 사람이 정하는 값이라 코드에 있을 값이 아니다.

    `.html` 우선, 없으면 `.md` 로 센다. 발행되는 것은 html 이다.
    """
    d = os.path.join(book_dir(), "03")
    found: list[str] = []
    for ext in (".html", ".md"):
        try:
            names = sorted(os.listdir(d))
        except OSError:
            break
        for f in names:
            if f.startswith("summary_") and f.endswith(ext) and f != "summary_index.html":
                k = f[len("summary_"):-len(ext)]
                if k and k not in found:
                    found.append(k)
        if found:
            break
    if found:
        return tuple(found)
    # ★ 아직 만든 파일이 없으면 **시험정보의 과목 키**로 답한다.
    #   상수 `SUMMARY_KEYS`(빅분기 4개)로 떨어지면, SQLD 폴더의 빈 `03/` 을 보고
    #   요약노트 화면이 「분석기획·탐색·모델링·결과해석」 넷을 내놓는다(2026-08-20 실측).
    #   만들기 **전에** 무엇을 만들지 말해야 하는 자리라 폴백이 곧 답이 된다.
    try:
        from services.authoring import parts

        # ★ **편** 단위다. 과목 하나가 여러 편일 수 있고(`theory_parts`),
        #   파일도 편마다 하나다(`summary_sql-1.html`). 과목 키로 답하면 탭과
        #   파일이 갈린다.
        keys = tuple(k for k, _no, _pt, _rng in parts.theory_units())
        if keys:
            return keys
    except Exception:                                        # noqa: BLE001
        pass
    return SUMMARY_KEYS


# ── 04/ 회차 lesson (읽기 전용 — build_check.py 가 읽지 않는다) ─────────────
def round_lesson(round_code_or_no) -> str:
    rc = round_code_or_no if isinstance(round_code_or_no, str) else round_code(round_code_or_no)
    return os.path.join(book_dir(), "04", f"lesson_{rc}.json")


# ── 05/ 영상 번들 ───────────────────────────────────────────────────────────
def bundle_dir(bundle: str) -> str:
    return os.path.join(book_dir(), "05", bundle)


def bundle_lesson(bundle: str) -> str:
    """★ 문제 본문이 실제로 웹에 가는 경로.

    axexam 의 build_check.py 는 문제문·보기·해설·정답을 이 파일에서만 읽는다.
    02/*.md 는 과목·난이도·태그·검수상태만 공급한다. 문항을 고칠 때 이 파일을
    같이 쓰지 않으면 수정이 웹에 전혀 반영되지 않는다.
    """
    return os.path.join(bundle_dir(bundle), "source", f"lesson_{bundle}.json")


def bundle_deck(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "source", "deck.html")


# ── 강의덱 PPTX (vendor/exam2deck) ──────────────────────────────────────────
# ★ 이 자리들은 `_deck-export/` 가 tools/deck_rounds.py 안에만 있던 것을 옮긴 것이다.
#   그 파일이 책 경로를 상수로 들고 있어서 폴더를 바꿔도 옛 책을 합쳤다.
#   `book=` 를 받는 이유는 하나 — 지금 고른 폴더가 아닌 책을 검증할 때가 있다.

def deck_export_dir(book: str = "") -> str:
    return os.path.join(book or book_dir(), "_deck-export")


def round_deck_html(round_code_or_no, book: str = "") -> str:
    """`<book>/_deck-export/NN회.html` — 회차 하나를 합친 변환기 입력."""
    rc = (round_code_or_no if isinstance(round_code_or_no, str)
          else round_code(int(round_code_or_no)))
    return os.path.join(deck_export_dir(book), f"{rc.lstrip('m')}회.html")


def round_pages_json(round_code_or_no, book: str = "") -> str:
    """문항별 장수 지정 — 사람이 화면에서 ± 로 고치는 값이 여기 남는다."""
    rc = (round_code_or_no if isinstance(round_code_or_no, str)
          else round_code(int(round_code_or_no)))
    return os.path.join(deck_export_dir(book), f"{rc.lstrip('m')}회.pages.json")


def figcache_dir(book: str = "") -> str:
    """도식 SVG → PNG 캐시. 해시 이름이라 회차끼리 공유된다."""
    return os.path.join(deck_export_dir(book), "_figcache")


def pptx_dir(book: str = "") -> str:
    """강의덱 pptx 가 **다 모여 있는 한 폴더** — `<book>/04-2/`.

    ★ 처음에는 번들 폴더 안(`05/<번들>/source/deck.pptx`)에 뒀다. 그게 자연스럽긴
      한데, 회차 하나가 5편이라 **100편이 100개 폴더에 흩어졌다.** PowerPoint 로
      검수하려면 폴더를 하나씩 들어가야 해서 실제로 못 쓸 UX 였다(2026-08-24 지시:
      "04-2 폴더를 만들고 거기다가 쭉 모을순없나요").

    ★ **사본을 모으지 않고 자리를 옮겼다.** 사본이면 사람이 손질한 것이 어느 쪽인지
      갈리고, 이미지를 뽑을 때 엉뚱한 파일에서 뽑는다. 여기가 유일한 자리다.

    ★ 이름은 변환기가 쓰던 것과 같다 — `01회_강의_11-20.pptx`. 파일 이름이 좌표를
      그대로 말해야 100개를 한 폴더에 놓고도 헷갈리지 않는다.
    """
    return os.path.join(book or book_dir(), "04-2")


def bundle_pptx(bundle: str) -> str:
    """이 번들의 슬라이드. **사람이 PowerPoint 로 여는 파일이고 진실이다.**"""
    return os.path.join(pptx_dir(), pptx_name(bundle))


def pptx_name(bundle: str) -> str:
    """`m01-2` → `01회_강의_11-20.pptx`."""
    parsed = parse_bundle(bundle)
    if not parsed:
        return f"{bundle}.pptx"
    rng = bundle_range(bundle)
    if not rng:
        return f"{parsed[0]:02d}회_강의_{parsed[1]}편.pptx"
    return f"{parsed[0]:02d}회_강의_{rng[0]:02d}-{rng[1]:02d}.pptx"


def bundle_pages(bundle: str) -> str:
    """pptx 가 낸 장 목록. 씬(script)·이미지가 이 목록에 맞춰진다."""
    return os.path.join(bundle_dir(bundle), "source", "pages.json")


def bundle_images_manifest(bundle: str) -> str:
    """images/ 가 어느 pptx 에서 나왔는지. 렌더가 `--reuse-images` 를 걸 근거."""
    return os.path.join(bundle_images_dir(bundle), "_source.json")


def bundle_script(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "script", f"{bundle}_script.json")


def bundle_review(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "review.json")


def bundle_mp4(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "draft", f"{bundle}.static.mp4")


def bundle_vtt(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "draft", f"{bundle}.ko.vtt")


def bundle_srt(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "subtitles", "subtitles.srt")


def bundle_images_dir(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "images")


def bundle_audio_dir(bundle: str) -> str:
    return os.path.join(bundle_dir(bundle), "audio")


# ── 06/ 발행 산출물 (axexam build_check.py 가 소유) ─────────────────────────
def out_dir() -> str:
    return os.path.join(book_dir(), "06")


def problems_json() -> str:
    """임포트할 problems.json — **`06/pd/<pd>/` 아래다.**

    ★ 예전에는 `06/problems.json`(평면)이었다. 빌더가 품목별로 갈라 두면서 자리가
      바뀌었는데 이 함수만 옛 자리를 보고 있었다. 그래서 사전점검의 problems.json
      검증과 FTP 목록의 '올리지 않을 것' 이 **없는 파일**을 가리켰다 — 조용히
      "검증할 것이 없음" 으로 지나간다(오류가 아니라 침묵이라 더 나쁘다).

      옛 평면 파일이 남아 있으면 그것도 인정한다 — 예전 빌드로 만든 폴더를 열었을 때
      화면이 갑자기 "없다" 고 하지 않게.
    """
    pd = ""
    try:
        from services.book import books
        pd = (books.active_meta().get("pd") or "").strip()
    except Exception:
        pd = ""
    if pd:
        per = os.path.join(out_dir(), "pd", pd, "problems.json")
        if os.path.isfile(per):
            return per
    flat = os.path.join(out_dir(), "problems.json")
    if os.path.isfile(flat):
        return flat
    # 아직 없을 때는 **지금 규약의 자리**를 돌려준다(빌드 후 여기 생긴다).
    return os.path.join(out_dir(), "pd", pd or "unknown", "problems.json")


def active_pd() -> str:
    """지금 작업 폴더의 품목 코드. 못 읽으면 빈 문자열."""
    try:
        from services.book import books
        return (books.active_meta().get("pd") or "").strip()
    except Exception:                                        # noqa: BLE001
        return ""


def pd_out_dir() -> str:
    """빌더가 내는 품목별 폴더 — `06/pd/<pd>/`.

    ★ 예전에는 `06/` 평면이었다. 품목이 둘이 되면서 빌더가 갈라 뒀는데, **검사하는
      쪽이 옛 자리를 계속 봤다.** `problems.json` 이 그래서 한 번 조용히 통과했고
      (`problems_json()` 머리말), `figs/` 도 같은 이유로 "06/figs 에 없는 그림
      169건" 이라는 거짓 경고를 냈다(2026-08-25). 자리를 묻는 곳을 여기 하나로 모은다.
    """
    pd = active_pd()
    if pd:
        per = os.path.join(out_dir(), "pd", pd)
        if os.path.isdir(per):
            return per
    return out_dir()


def pd_figs_dir() -> str:
    """문항 도식 SVG 가 실제로 놓이는 자리."""
    return os.path.join(pd_out_dir(), "figs")


# ── 파일 상태 ───────────────────────────────────────────────────────────────
def etag(path: str) -> str:
    """mtime_ns-size. BOOK 은 외부에서 다시 동기화될 수 있어서 저장 전에 대조한다."""
    try:
        st = os.stat(path)
        return f"{st.st_mtime_ns}-{st.st_size}"
    except FileNotFoundError:
        return "0-0"


def newline_for(path: str) -> str:
    """이 파일에 써야 하는 개행.

    ★ 상수가 아니다. 같은 BOOK 트리 안에서도 갈린다 — 실측(260730):
      02/*.md · 02/*.json · 04/ · 05/lesson = CRLF,  _rounds/*.json · 03/* = LF.
      만든 쪽이 Windows 텍스트 모드로 썼는지에 달렸을 뿐이라 규칙이 없다.

    1) 파일이 있으면 그 파일의 개행. (기존 266개가 이 경로로 그대로 보존된다)
    2) 없으면 **같은 폴더 · 같은 확장자 형제들의 다수결.** 회차가 m04~m09 로 늘 때
       새 파일이 형제들과 같은 규약으로 태어나야 한다. 여기서 LF 로 굳히면
       한 폴더 안에 두 규약이 섞인다.
    3) 형제도 없으면 LF.
    """
    nl = atomic_io.file_newline(path)
    if nl is not None:
        return nl

    d, name = os.path.dirname(path), os.path.basename(path)
    _, ext = os.path.splitext(name)
    lf = crlf = 0
    try:
        siblings = sorted(os.listdir(d))
    except OSError:
        return atomic_io.LF
    for f in siblings:
        if f == name or not f.endswith(ext) or f.endswith(".bak"):
            continue
        s = atomic_io.file_newline(os.path.join(d, f))
        if s == atomic_io.CRLF:
            crlf += 1
        elif s == atomic_io.LF:
            lf += 1
        if lf + crlf >= 8:          # 표본 8개면 충분하다. 240개를 다 열 이유가 없다.
            break
    return atomic_io.CRLF if crlf > lf else atomic_io.LF


def to_disk(path: str, text: str) -> str:
    """렌더러 출력(LF 기준) → 그 파일에 실제로 들어갈 바이트.

    렌더러는 LF 로만 조립하고(내용이 원천), 개행은 전부 이 한 곳을 지난다.
    왕복 검증도 저장도 같은 함수를 써야 둘이 갈리지 않는다.
    """
    return atomic_io.with_newline(text, newline_for(path))


def mtime(path: str) -> float:
    try:
        return os.stat(path).st_mtime
    except FileNotFoundError:
        return 0.0


def size(path: str) -> int:
    try:
        return os.stat(path).st_size
    except FileNotFoundError:
        return 0


def book_url(path: str) -> str:
    """BOOK 안의 파일 → 브라우저가 읽을 /book/... URL (mp4 · vtt · svg 미리보기)."""
    return "/book/" + rel(path)
