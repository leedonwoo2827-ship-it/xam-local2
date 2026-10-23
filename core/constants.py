"""경로·버전·품목 코드 — 이 앱의 모든 절대 경로가 여기서만 결정된다.

BOOK 은 이 PC 밖의 외부 트리다(작업 폴더 화면에서 고른다). 하드코딩 기본값을
두되 .env 로 덮어쓸 수 있게 해야, 책이 하나 더 생겼을 때 코드를 안 고친다.
"""
from __future__ import annotations

import os

APP_VERSION = "0.1.0"
APP_NAME = "XAM LOCAL"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
PUBLISH_DIR = os.path.join(DATA_DIR, "publish")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")


def _env_path(key: str, default: str) -> str:
    """경로 환경변수 — 빈 문자열은 '미설정' 으로 보고 기본값을 쓴다."""
    v = (os.getenv(key) or "").strip().strip('"')
    return os.path.abspath(v) if v else os.path.abspath(default)


# ── 외부 트리 ────────────────────────────────────────────────────────────────
# BOOK: 도구 #1(exam-ocr-tool)이 원격 세션에서 만들어 동기화해 준 산출물 트리.
#       00/ 01/ 02/ 03/ 04/ 05/ 06/ _rounds/ 를 갖는다.
BOOK_DIR = _env_path("XAM_BOOK", r"D:\00work\ocr-output-260730")

# OCR: 도구 #1 의 판독 작업 폴더 (data/raw_pages · data/ocr_draft · data/answers).
# 비워 두면 BOOK 이름에서 유도한다 — ocr-output-260730 → 형제 폴더 260730-ocr.
# 판독은 Claude Code 창이 하고 이 앱은 그 초안을 검수·확정한다(같이 쓰는 폴더).
OCR_DIR = (os.getenv("XAM_OCR") or "").strip().strip('"')
OCR_DIR = os.path.abspath(OCR_DIR) if OCR_DIR else ""

# ENGINE: 도구 #3 렌더 엔진 — **이 저장소 안에 있다** (2026-08-03 내장).
#   make_bundle_video.py 를 이 폴더에서 cwd 로 실행한다. 절대 import(`from slides …`)
#   가 그대로 살도록 폴더째로 넣었고, 자막 시간축 수정 4건은 그 소스에 반영돼 있다.
#   외부 폴더(XAM_CHODANGI)를 가리키던 시절의 값은 이 PC 에 없는 경로였다.
ENGINE_DIR = os.path.join(BASE_DIR, "vendor", "chodangi")

# AXBUILD: 발행 빌더 — **이 저장소 안에 있다** (2026-08-03 내장).
#   axexam 의 scripts/{build_check,exam_meta}.py + 템플릿을 들여왔다.
#   06/ (정적 페이지 + problems.json) 을 만드는 것이 이 빌더다.
# axexam 을 git subtree 로 합쳤다(2026-08-04) — 빌더 사본을 두지 않고 상류를 그대로 쓴다.
AXBUILD_DIR = os.path.join(BASE_DIR, "axexam", "scripts")

# AXEXAM: 웹(그누보드5) 저장소. PHP·web/ 의 원본이다.
#   v2 부터 기본값은 이 저장소 안 subtree(axexam/) 다 — 슬라이드 색
#   (assets/present/tokens.css)도 여기서 읽는다. 외부 클론을 가리키지 않아야
#   구버전 폴더나 260729-new 가 지워져도 이 앱이 혼자 돈다.
AXEXAM_DIR = _env_path("XAM_AXEXAM", os.path.join(BASE_DIR, "axexam"))

# ── 품목 ────────────────────────────────────────────────────────────────────
# ★ build_check.py 의 --pd 기본값은 'sqld' 다. 우리가 이 값을 반드시 명시해야
#   라이브 SQLD 문제은행을 덮어쓰는 사고를 막는다. §7 참고.
PD_CODE = (os.getenv("XAM_PD") or "bigdata").strip()
PD_LABEL = (os.getenv("XAM_PD_LABEL") or "빅데이터분석기사 필기").strip()

SITE_BASE = (os.getenv("XAM_SITE") or "https://axexam.mycafe24.com").rstrip("/")
SITE_PATH = "/" + (os.getenv("XAM_SITE_PATH") or "exam").strip("/") + "/"

PORT = int(os.getenv("XAM_PORT") or "8871")   # v2 — 구버전(8870)과 동시에 띄울 수 있게

# ── 책의 형태 ────────────────────────────────────────────────────────────────
# ★ 회차 수·문항 수·과목 수는 **상수가 아니다.** 폴더에서 센다:
#     회차   services.book.paths.round_codes()      (_rounds/mNN.json 개수)
#     문항   services.book.shape.questions_per_round()
#     과목   services.book.shape.subject_count()
#     번들   services.book.paths.all_bundles()
#   여기 있던 ROUND_CODES=("m01","m02","m03") · TOTAL_QUESTIONS=240 ·
#   TOTAL_BUNDLES=24 · SUBJECT_COUNT=4 를 지웠다. 자사 회차가 m01~m09(720문항 ·
#   72번들)로 늘어날 예정이고, 그때 상수로 남아 있으면 사전점검이 "240개 기대" 를
#   들고 조용히 통과·실패한다.
#
# 아래 둘만 남는다 — 파이프라인 규약이라 책이 바뀌어도 같다.
QUESTIONS_PER_BUNDLE = 10        # 영상 번들 하나 = 10문항 (pr_key 규칙과 묶여 있다)

# 회차당 문항 수를 폴더에서 못 읽을 때의 마지막 폴백. 계산에 쓰지 말고
# "아직 아무것도 못 읽었다" 는 뜻으로만 쓴다.
FALLBACK_QUESTIONS_PER_ROUND = 80

# 요약노트 키 — 03/summary_{key}.html
# ★ 실제 키는 `services.book.paths.summary_keys()` 가 **폴더에서 읽는다.**
#   여기 값은 03/ 이 비어 있을 때의 마지막 폴백이다. 260730 의 실제 키는
#   planning · explore · modeling · interpret 이고, 이 상수를 그대로 쓰면
#   요약노트 화면이 404 를 내고 사전점검이 "4종 없음" 을 낸다.
SUMMARY_KEYS = ("분석기획", "탐색", "모델링", "결과해석")

# 잡 이력 보관 개수 / 로그 링버퍼 줄수
JOB_HISTORY = int(os.getenv("XAM_JOB_HISTORY") or "200")
LOG_TAIL = int(os.getenv("XAM_LOG_TAIL") or "400")

ANSWER_GLYPHS = "①②③④⑤"
KOR_NUM = {0: "일", 1: "이", 2: "삼", 3: "사", 4: "오"}
DIFFICULTIES = ("상", "중", "하")
