# XAM local2 — 실기 문제집 · 실습파일 · 이론 노트 제작 앱

기출 실기 풀이집(스캔 PDF)을 OCR 해서, **저작권을 피해 회차를 새로 쓰고**, 그 원고로
**실습파일(문제·정답 엑셀) · HTML 문제집 · 이론 노트 · 강의 원고 · 녹화 대본**까지 만드는 로컬 웹 앱이다.

- **실기 전용**이다(엑셀 작업형. 컴활1급의 액세스는 다음에 붙인다). 필기는 [`xam-local3`](https://github.com/leedonwoo2827-ship-it/xam-local3)(포트 8873)에서 한다.
- 저장소 전체가 실기용이다 — `main` 과 `practical` 이 같은 코드다(필기를 local3 으로 옮긴 뒤 2026-11-19 에 맞춤). 포트 **8871**.
- 끝낸 품목: **컴퓨터활용능력 2급 실기 (com2p-27)** — 기출 5회 → 새 10회(1~5 책 후미 · 6~10 종합본).
- 영상은 실기 종합반(`261110-IT-product-longform-full-auto`)과 녹화 허브(`261027-new-IT-product-hub`)가 받아 간다(아래 「다음 도구」).

---

## 실행

```
git clone https://github.com/leedonwoo2827-ship-it/xam-local2.git
cd xam-local2
setup.bat        처음 한 번 — venv · 패키지 · Chromium(PDF 인쇄)
run.bat          http://127.0.0.1:8871/  (이 PC 전용)
```

준비물: 윈도우 · Python 3.12 · **Claude Code 로그인**(집필·2부 노트·녹화 대본이 각자의 구독으로 돈다, API 키 없음) ·
**엑셀 2019 이상(1부 빌드 필수 — 실습파일을 실제 엑셀로 만들고 재계산해 검증한다)** · 액세스(컴활1급부터).

> 코드를 바꾼 뒤에는 **run.bat 을 다시 켜야** 서버 쪽 변경이 반영된다(화면 쪽은 F5).
> 작업이 도는 중(집필·빌드·2부)에는 run.bat 을 끄지 않는다.

---

## 작업 순서 — 왼쪽 메뉴 그대로

### 1부 · 문항

| 메뉴 | 하는 일 | 결과 |
|---|---|---|
| **＋ 실기 OCR** | 스캔 뜨기 → 판독(Claude) | OCR 판독 폴더(`<날짜>-ocr/data/practical`) |
| OCR 검수 | 쪽마다 스캔과 대조해 고치고 대조완료 · 확정 | `01/practical/RR-P-NN.json·md` |
| 구조화 MD로 정리 | 확정한 기출 문항 목록 · MD 미리보기 | (읽기) |
| 과정 정의 | 시험정보 — 형식(작업형) · 묶음 · 배점 · 시험시간 · 프로그램 버전 · 출제 함수 · **바뀐 점(changes)** | `exams/<id>.json` |
| 실기 문제 집필 | 기출 바탕으로 새 회차(묶음 하나 = Claude 한 번). 6~10회는 함수 조합까지 바꿈 | `02/practical/mNN/` |
| 문항 교정 | 발문 · 지시 · 모범답안 · 수식 · 결과값 · 그림 설계 · **시트 자료** · 제공 차트 | 같은 곳(문항 JSON · partN.json · MD 동시 갱신) |
| 1부 빌드 | 엑셀로 **문제·정답 xlsx** 를 만들고 재계산 → 모범답안 결과값과 대조 · 그림 · **원천 점검** | `06/practical/mNN/` |

- **원천은 `02/practical` 의 JSON 이다.** 엑셀(06·07)을 손으로 고치면 다음 빌드에 덮인다 — 고칠 것은 「문항 교정」에서.
- 시트 자료 규칙: 계산 칸은 `"=D4*E4"` 수식 · `title_cell`(제목 셀) · `styles`(지시에 쓰는 글꼴 색·채우기) ·
  `input`(수험자가 입력하는 표 — 문제 파일에서 비움: `all`·`body`·`data`) · 차트 문항은 `given_chart`(지시 적용 전 제공 차트).
- **원천 점검**(빌드 때 자동, 1부 빌드 표의 「원천 점검 N」): 결과 셀 수식 · 변경 셀을 바꾸면 결과가 바뀌는지 · 제공 차트 1개 ·
  지시 범위 첫 행 = 표 머리글 · 「[X] 셀과 연동」 칸 · 색 기준 정렬의 색 · 열 머리 글자(A·B…) 섞임 · 제목 속 지시 메모 · 입력 문항 비우기.

### 2부 · 이론 노트 — 「2부 현황판」 하나

묶음(문제1~4) × 단계 표(해설 모아 구조화 → 이론 요약 노트 → 요약반 강의 노트 → 종합반 강의 노트(n배)).
행·열 체크박스로 고른 칸만 돌리고, 다 고르면 2부 끝까지 한 번에 간다. 칸을 누르면 그 단계 화면(듣기 검수 포함)이 열린다.
결과: `03/summary_<묶음>.html` · `03-2/` · `03-3/` · `04-2/lecture/{summary,full}/<묶음>/`.
실기 낭독 규칙: 셀 주소·범위는 읽는 말로(「A3:A10」→「에이삼부터 에이십」, `$A$1`→「절대 참조 에이일」).

### 3부 · HTML 문제집 제작

- **굽기** — 회차마다 `07/mNN/`: `exam.html·pdf`(시험지) · `answers.html·pdf`(모범답안 해설) · `files/`(실습파일, 06 에서 복사) · `assets/` · `script/`.
- **녹화 대본** — `07/mNN/rec/{NN-P-NN}.actions.json · .lesson.yaml`(1~10회 전부). 화면에 단추는 없고 `POST /api/practical/actions`.
  `expected` 는 정답 파일의 셀 값(못 보면 `{"text": 표시값}`).
- **인쇄본** — `/print/practical?rd=N`.

---

## 작업 폴더 (책 폴더)

좌하단 칩에서 고른다(`data/books.json`). 품목 코드 `pd` 는 폴더의 `_book.json` 이 정본이다(예: `{"pd": "com2p-27"}`).

```
<책 폴더>\
  00\                  원본 PDF (실기 풀이집 스캔)
  01\practical\        확정한 기출 문항 (OCR 검수 결과) RR-P-NN.json·md · images\
  02\practical\mNN\    집필한 회차 — partP.json(묶음 원본) · NN-P-NN.json·md · images\   ← 모든 산물의 원천
  06\practical\mNN\    1부 빌드 — mNN_문제.xlsx · mNN_정답.xlsx · verify.json
  07\mNN\              HTML 문제집 — exam · answers · files\ · assets\ · script\ · rec\
  03\  03-2\  03-3\    이론 요약 노트 · 요약반 · 종합반 강의 원고  (03\_outline\ = 해설 구조화)
  04-2\lecture\        강의 노트 빌드(PPTX · narration.json)
  _longform-kit\       실기 종합반이 가져갈 묶음
<날짜>-ocr\data\practical\   OCR 판독 작업 폴더 (쪽 그림 · 초안)
```

### 다른 PC(노트북)로 옮기기

| 무엇 | 어떻게 |
|---|---|
| 앱 코드 | 위 「실행」대로 `git clone` → `setup.bat` |
| **책 폴더** | **git 밖**이다. 통째 복사(`_backup-*` 폴더는 빼도 됨) → 앱의 작업 폴더 칩에서 고른다 |
| `.env` | git 밖. 복사하거나 `.env.example` 에서 새로 |
| 음성 모델 | `vendor/chodangi/assets/`(약 400MB, git 밖) — setup.bat 이 없으면 안내한다. 있는 PC 에서 복사 |
| 시험정보 · 발음 사전 | git 안(`exams/*.json`, `vendor/chodangi/config/pronunciation_map.yaml`) — 따로 옮길 것 없음 |

---

## 다음 도구가 받는 것

| 받는 곳 | 가져가는 것 |
|---|---|
| 실기 종합반 `261110-IT-product-longform-full-auto` (lecture-composer-practical) | `03*` 강의 원고 · `_longform-kit` · `07/mNN/` 문제집 · 녹화 결과 → 종합본 강의 영상 |
| 녹화 허브 `261027-new-IT-product-hub` | `07/mNN/rec/*.lesson.yaml` + `07/mNN/files/*_문제.xlsx` → 엑셀 자동 녹화. 원천 오류는 목록으로 돌려받아 **02 원고에 반영**(예: `tools/practical_migrate_261112.py`) |
| XAMpass `261113-moodlesite` | 결과물 폴더를 직접 읽는다(실기 단계 폴더) |

---

## 코드 구조 (요약)

```
app.py               FastAPI · 라우터 · /static · /book 마운트
routes/              JSON API — 실기는 practical_routes.py (/api/practical/*)
services/practical/  실기 — read(판독) · review/finalize(검수·확정) · author(집필·교정) · build(1부 빌드·원천 점검)
                     · ebook(HTML 문제집) · actions(녹화 대본) · feed(2부 입구)
services/authoring/  시험정보(examspec: format task/written 로 실기 판정) · 이론 노트
services/lecture/    2부 강의 노트 · 듣기 검수
services/render/     낭독 사전(lexicon) · 셀 주소 읽기(core/speak.py)
static/js/           화면마다 한 모듈 — practical*.js · part2.js · …
exams/               시험정보 JSON (com2-practical · com2-2027 · sqld · adsp · bdae-written)
tools/               practical_build_cli(서버 없이 1부 빌드) · practical_diff_xlsx(실습파일 칸 단위 대조) · practical_poc
vendor/chodangi/     렌더 엔진 · voicewright(TTS) — 음성 모델(assets)은 git 제외
data/                런타임(git 제외) — books.json · jobs/ · authoring/
```

## 설정 (`.env`)

`.env.example` 을 `.env` 로 복사해 쓴다. 대부분 비워 둬도 된다 — 작업 폴더는 화면에서 고른다.

| 키 | 쓰임 |
|---|---|
| `XAM_BOOK` · `XAM_OCR` | 첫 실행 때의 작업 폴더 · OCR 판독 폴더(비우면 책 이름에서 유도) |
| `XAM_PORT` | 기본 포트(run.bat 은 8871 로 덮어쓴다) |
| `CLAUDE_CLI` · `XAM_CHAT_MODEL` | claude.exe 경로 · 오른쪽 채팅 모델(비우면 자동) |

## 더 자세한 기록

- [`docs/README-v2-기록.md`](docs/README-v2-기록.md) — 이전 README 전체(v1·v2 운영 지식)
- [`PUBLISHING.md`](PUBLISHING.md) — 발행·수정 규칙
