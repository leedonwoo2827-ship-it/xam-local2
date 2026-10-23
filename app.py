"""XAM LOCAL — 문제은행 로컬 운영 콘솔.

도구 #1(exam-ocr-tool, 원격 산출) 과 #3(chodangi-mp4-forge, 로컬) 의 산물을
검수하고, axexam(그누보드5 웹) 파이프라인을 안전하게 호출해 웹으로 넘긴다.

이 파일은 페이지 HTML 과 정적 마운트만 담당한다. API 는 전부 routes/ 에 있다.
"""
import mimetypes
import os


def register_static_mime_types() -> None:
    """일부 Windows 환경의 잘못된 레지스트리 MIME 매핑을 덮어쓴다.

    .js  — text/javascript 가 아니면 ES 모듈이 화면만 뜨고 동작하지 않는다.
    .vtt — 레지스트리에 없으면 octet-stream 이 되고 브라우저가 <track> 을
           **오류 없이 조용히** 버린다(자막만 안 나온다). 가장 찾기 어려운 증상.
    """
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("application/javascript", ".mjs")
    mimetypes.add_type("text/vtt", ".vtt")
    mimetypes.add_type("video/mp4", ".mp4")
    # 씬별 음성 미리듣기 — 이게 없으면 <audio> 가 octet-stream 을 받고 조용히 안 울린다.
    mimetypes.add_type("audio/wav", ".wav")
    mimetypes.add_type("image/png", ".png")
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("application/json", ".json")


register_static_mime_types()

from dotenv import load_dotenv

# utf-8-sig: 메모장으로 저장한 .env 의 BOM 때문에 첫 키가 깨지는 흔한 문제 방지.
load_dotenv(encoding="utf-8-sig")

import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core import lan
from core.constants import (
    APP_NAME, APP_VERSION, AXEXAM_DIR, BASE_DIR, BOOK_DIR, ENGINE_DIR,
    DATA_DIR, JOBS_DIR, PD_CODE, PD_LABEL, PORT, PUBLISH_DIR, STATIC_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=APP_NAME,
    description="문제은행 로컬 운영 콘솔 — 문항 교정 · 영상 검수 · 발행",
    version=APP_VERSION,
)


# ========= 사내망 공유 — 보기 전용 게이트 =========
# 규칙과 그 근거는 core/lan.py 의 모듈 주석에 있다. 요약:
#   루프백 → 전부 허용 (내 화면은 지금과 똑같다)
#   그 밖  → GET/HEAD 만. 나머지는 403.
#
# ★ 미들웨어를 조건부로 달지 않는다. `if 사내망모드:` 로 감싸면 `--host 0.0.0.0`
#   으로 직접 띄웠을 때(lan.bat 을 안 쓰고) 게이트가 없는 채로 열린다.
#   항상 달아 둔다 — 루프백만 열려 있으면 이 미들웨어는 아무 일도 하지 않는다.
@app.middleware("http")
async def _readonly_for_lan(request: Request, call_next):
    if request.method not in lan.READ_METHODS and not lan.lan_writable(request.method, request.url.path):
        host = request.client.host if request.client else None
        if not lan.is_local(host):
            # 화면에 그대로 뜨는 문구다. 왜 막혔는지·누가 풀 수 있는지를 담는다 —
            # "403" 만 보면 앱이 고장난 줄 안다.
            return JSONResponse(
                status_code=403,
                content={"detail": "보기 전용으로 공유된 화면입니다. "
                                   "저장·빌드·렌더는 이 PC(운영자 화면)에서만 됩니다."},
            )
    return await call_next(request)


@app.get("/api/mode")
async def api_mode(request: Request):
    """이 요청자가 쓰기를 할 수 있는가. 화면 상단 배너가 이걸 보고 결정한다.

    ★ 서버가 판정해야 한다. 브라우저가 자기 주소로 추측하면 틀린다 —
      운영자도 사내망 IP 로 접속할 수 있고(북마크·다른 기기), 그때는 실제로
      보기 전용이 맞다. 판정 기준을 게이트와 **같은 함수**로 둬서 갈리지 않게 한다.
    """
    host = request.client.host if request.client else None
    local = lan.is_local(host)
    return {"readonly": not local, "client": host or "", "pd": PD_CODE, "book": PD_LABEL}

# ========= 라우터 =========
# 각 계층은 독립적으로 미탑재일 수 있다. 하나가 없어도 앱은 뜬다 —
# 특히 BOOK 경로가 틀렸을 때 그걸 고칠 화면이 남아 있어야 한다.
_ROUTERS = (
    ("routes.books_routes", "setup_books_routes", "작업 폴더"),
    ("routes.book_routes", "setup_book_routes", "BOOK 개요"),
    # 집필 — 유일하게 LLM 을 부르는 계층. claude-agent-sdk 가 없으면 여기만 빠지고
    # 나머지 화면은 그대로 뜬다(위 try/except 가 그 목적이다).
    ("routes.authoring_routes", "setup_authoring_routes", "집필(구독 OAuth)"),
    # 이론(03/ 요약노트) — 집필과 같은 프로바이더를 쓰지만 산출물이 과목별이라
    # 라우트를 나눴다. 기본 모델이 Fable 이다(theory_routes 머리말).
    ("routes.theory_routes", "setup_theory_routes", "이론 요약노트"),
    ("routes.ocr_routes", "setup_ocr_routes", "OCR 검수(페이지 단위)"),
    ("routes.scan_routes", "setup_scan_routes", "구조화 MD"),
    ("routes.question_routes", "setup_question_routes", "문항 교정"),
    ("routes.verify_routes", "setup_verify_routes", "바이트 충실도 검증"),
    ("routes.render_routes", "setup_render_routes", "영상 렌더"),
    ("routes.render_routes", "setup_job_routes", "잡 조회"),
    ("routes.publish_routes", "setup_publish_routes", "발행"),
    ("routes.summary_routes", "setup_summary_routes", "요약노트"),
    # v2 — 우측 채팅 패널. claude-agent-sdk 가 없으면 이것만 빠진다.
    ("routes.chat_routes", "setup_chat_routes", "채팅(구독 OAuth)"),
    # v2 — 이론 묶음: 해설 모아 노트 구조화 · 요약반/종합반 강의 노트 · 듣기 검수
    ("routes.lecture_routes", "setup_lecture_routes", "이론 노트·듣기 검수"),
)


@app.on_event("shutdown")
def _close_chats() -> None:
    """채팅마다 붙잡아 둔 claude CLI 자식 프로세스를 닫는다 — 안 닫으면 고아로 남는다."""
    try:
        from services.chat import session as _chat
        _chat.shutdown()
    except Exception:                                            # noqa: BLE001
        pass

for _mod, _factory, _label in _ROUTERS:
    try:
        _m = __import__(_mod, fromlist=[_factory])
        app.include_router(getattr(_m, _factory)())
    except (ImportError, AttributeError):
        logger.warning("%s 미탑재 — %s API 비활성", _mod, _label)

# ========= 정적 파일 =========
class _NoCacheStatic(StaticFiles):
    """앱 코드는 캐시하지 않는다.

    ★ ES 모듈은 브라우저가 아주 공격적으로 캐시한다. util.js 를 고쳐도 이미 열린 탭은
      예전 모듈을 계속 써서, 새로 추가한 export 를 "does not provide an export named …"
      로 거부한다. 실제로 그 사고가 났다 — 파일도 서버도 정상인데 화면만 깨져서
      원인이 코드에 있는 줄 알게 된다.

      로컬 단일 사용자 앱이라 캐시로 얻을 게 없다. 폰트만 예외로 둔다(1.2MB, 안 바뀜).
    """

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        if path.replace("\\", "/").startswith("fonts/"):
            resp.headers["Cache-Control"] = "public, max-age=604800"
        else:
            resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp


app.mount("/static", _NoCacheStatic(directory=STATIC_DIR), name="static")

# BOOK 트리를 읽기 전용으로 그대로 노출한다 — mp4 · vtt · svg · deck.html 미리보기용.
# ★ Range 처리를 직접 구현하지 않는다. starlette 의 FileResponse 가 이미
#   206 Partial Content / Accept-Ranges / 416 을 낸다. mp4 드래그 탐색이 공짜로 된다.
#
# ★ 이 마운트는 부팅 시점의 경로에 묶인다. 작업 폴더를 바꾸면 반드시 같이 갈아야
#   한다 — 안 갈면 폴더는 바뀌는데 영상·그림이 옛 폴더에서 나온다.
#   그래서 항상 만들어 두고(없는 폴더라도), rebind_book() 으로 경로를 교체한다.
def _initial_book_dir() -> str:
    try:
        from services.book import books
        return books.active_path()
    except Exception:
        return BOOK_DIR


_book_dir_now = _initial_book_dir()
if not os.path.isdir(_book_dir_now):
    logger.warning("BOOK 경로가 없습니다 — /book 은 빈 폴더를 가리킵니다: %s", _book_dir_now)
    os.makedirs(os.path.join(DATA_DIR, "_nobook"), exist_ok=True)
    _book_static = StaticFiles(directory=os.path.join(DATA_DIR, "_nobook"))
else:
    _book_static = StaticFiles(directory=_book_dir_now)
app.mount("/book", _book_static, name="book")


def rebind_book(path: str) -> bool:
    """/book 마운트를 새 폴더로 갈아 끼운다.

    StaticFiles 는 directory 와 all_directories 를 들고 있으므로 둘 다 바꿔야 한다
    (lookup_path 가 all_directories 를 훑는다). 마운트를 새로 만들지 않는 이유는
    app.router.routes 를 런타임에 재배치하면 다른 라우트 순서까지 흔들리기 때문이다.
    """
    if not os.path.isdir(path):
        logger.warning("/book 교체 실패 — 폴더가 없습니다: %s", path)
        return False
    try:
        _book_static.directory = path
        _book_static.all_directories = _book_static.get_directories(path, None)
        logger.info("/book → %s", path)
        return True
    except Exception:
        logger.exception("/book 마운트 교체 실패")
        return False


# ========= 페이지 =========
@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/home")
async def home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ── 인쇄본 ────────────────────────────────────────────────────────────────
# ★ 여기(app.py)에 두는 이유: 이 프로젝트는 **페이지 HTML 을 app.py 만** 낸다
#   (routes/ 는 JSON·파일전송 전용). 그래서 그리는 일은 services/export 가 하고
#   app.py 는 그 문자열을 HTML 로 내보내기만 한다.
#
# ★ 파일을 굽지 않는다. 열 때마다 지금 데이터로 그린다 — 고친 뒤 다시 굽는 것을
#   잊고 낡은 종이로 검수하는 사고를 이 프로젝트에서 이미 겪었다(업로드 폴더).
def _print_page(fn, *a):
    from fastapi.responses import HTMLResponse
    try:
        return HTMLResponse(fn(*a))
    except (FileNotFoundError, ValueError) as e:
        # 조용히 빈 문서를 내지 않는다. 왜 못 그렸는지 화면이 말해야 한다.
        return HTMLResponse(status_code=409, content=(
            '<!DOCTYPE html><meta charset="utf-8">'
            '<body style="font:14px/1.8 sans-serif;padding:26px;max-width:680px">'
            "<h2>인쇄본을 만들 수 없습니다</h2><pre style=\"white-space:pre-wrap;"
            'background:#f6f7f4;padding:12px;border-radius:6px">'
            + __import__("html").escape(str(e)) +
            "</pre><p><a href=\"/print/\">← 인쇄본 목록</a></p></body>"))


@app.get("/print/")
async def print_index():
    from services.export import printdoc
    return _print_page(printdoc.index_html)


@app.get("/print/questions")
async def print_questions(rd: int | None = None):
    from services.export import printdoc
    return _print_page(printdoc.questions_html, rd)


@app.get("/print/lesson")
async def print_lesson(b: str | None = None):
    from services.export import printdoc
    return _print_page(printdoc.lesson_html, b)


@app.get("/print/summary")
async def print_summary(k: str | None = None):
    """이론 요약노트 인쇄본 — 발행되는 그 HTML 그대로. `?k=<과목키>` 면 그 과목만."""
    from services.export import printdoc
    return _print_page(printdoc.summary_html, k)


@app.get("/print/slides")
async def print_slides(rd: str | None = None):
    """슬라이드 장수표 인쇄본 — **회차 하나가 한 쪽**이다.

    PowerPoint 100편을 넘겨 보며 "이 문항은 줄였다" 를 종이에 체크하는 자리다.
    `?rd=m03` 이면 그 회차만.
    """
    from services.export import printdoc
    return _print_page(printdoc.slides_html, rd)


# ── 슬라이드 미리보기 ───────────────────────────────────────────────────────
# ★ `def` 다. `async def` 가 아니다 — 나중에 ?fit=1 이 Chromium 으로 실제 높이를 재게
#   되는데 `sync_playwright()` 는 asyncio 루프가 도는 스레드에서 죽는다. `def` 면
#   FastAPI 가 스레드풀에서 돌린다. (`deck_capture` 에서 이미 겪은 함정이다.)
#
# ★ 파일을 굽지 않는다. 요청마다 지금 데이터로 그린다 — `/print/` 와 같은 패턴이고,
#   그래서 미리보기와 베이크가 **같은 함수**를 쓴다는 규약이 유지된다.
@app.get("/slide/")
def slide_index():
    from services.deck import preview
    return _print_page(preview.index_html)


@app.get("/slide/bundle")
def slide_bundle(b: str | None = None, fit: str = ""):
    """번들 하나를 슬라이드로. `?fit=1` 이 안전선을 빨간 띠로 얹는다."""
    from services.deck import preview
    return _print_page(preview.bundle_html, b, bool(fit))


@app.get("/mock")
async def mock():
    """UI/UX 확정용 목업 모음. 확정되면 static/_mock/ 과 함께 지운다."""
    p = os.path.join(STATIC_DIR, "_mock", "index.html")
    if not os.path.isfile(p):
        return JSONResponse(status_code=404, content={"detail": "목업이 없습니다."})
    return FileResponse(p)


@app.get("/api/version")
async def version():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "port": PORT,
        # ★ 품목은 **작업 폴더에서** 읽는다. `.env` 의 `PD_CODE`·`PD_LABEL` 은
        #   첫 실행 기본값이라, SQLD 폴더를 열어 놓고 「빅데이터분석기사 필기」 가
        #   홈 카드에 떴다(2026-08-20 실측). 폴더가 진실이다.
        **_active_pd(),
        "book": _initial_book_dir(),
        "engine": ENGINE_DIR,
        "axexam": AXEXAM_DIR,
    }


def _active_pd() -> dict:
    """작업 폴더의 품목 코드·이름. 못 읽으면 `.env` 기본값으로 떨어진다."""
    try:
        from services.book import books

        m = books.active_meta() or {}
        pd = str(m.get("pd") or "").strip()
        label = str(m.get("label") or "").strip()
    except Exception:                                        # noqa: BLE001
        pd = label = ""
    # 시험정보에 정식 이름이 있으면 그것을 쓴다 — `_book.json` 의 label 은 약칭이다
    # (`SQLD`). 카드에는 「SQL 개발자 (SQLD)」 가 맞다.
    try:
        from services.authoring import parts

        d = parts.active() or {}
        if str(d.get("pd_id") or "").strip() == pd and d.get("label"):
            label = str(d["label"]).strip()
    except Exception:                                        # noqa: BLE001
        pass
    return {"pd": pd or PD_CODE, "pd_label": label or PD_LABEL}


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.exception_handler(500)
async def internal_error(request: Request, exc: Exception):
    logger.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류"})


def _bootstrap() -> None:
    os.makedirs(JOBS_DIR, exist_ok=True)

    # 작업 폴더 화면이 폴더를 바꿀 때 /book 마운트를 갈 수 있도록 콜백을 넘긴다.
    try:
        from routes import books_routes
        books_routes.set_rebind(rebind_book)
    except ImportError:
        logger.warning("routes.books_routes 미탑재 — 폴더 전환 시 /book 이 안 바뀝니다")

    os.makedirs(PUBLISH_DIR, exist_ok=True)

    # starlette 버전 경고 — mp4 탐색이 Range 지원에 달려 있다.
    try:
        import starlette
        parts = tuple(int(x) for x in starlette.__version__.split(".")[:2])
        if parts < (0, 40):
            logger.warning(
                "starlette %s — FileResponse Range 지원이 없을 수 있습니다. "
                "mp4 드래그 탐색이 안 되면 `pip install -U fastapi` 하십시오.",
                starlette.__version__,
            )
    except Exception:
        pass

    # ImportError 로 잡는다 — services.jobs 패키지는 있고 registry 모듈만 없을 때
    # 나오는 예외가 ModuleNotFoundError 가 아니라 ImportError 다.
    try:
        from services.jobs import registry
        restored, broken = registry.restore_history()
        if restored:
            logger.info("지난 작업 %d건 복원 (끊긴 작업 %d건 정리)", restored, broken)
    except ImportError:
        logger.warning("services.jobs.registry 미탑재 — 잡 이력 복원 생략")

    if not os.path.isdir(BOOK_DIR):
        logger.error("BOOK 경로를 찾을 수 없습니다: %s  (.env 의 XAM_BOOK 확인)", BOOK_DIR)


_bootstrap()
logger.info("%s %s — pd=%s  book=%s", APP_NAME, APP_VERSION, PD_CODE, BOOK_DIR)
logger.info("base=%s", BASE_DIR)
