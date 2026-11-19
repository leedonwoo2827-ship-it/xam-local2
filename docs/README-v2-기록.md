# XAM LOCAL v2 — IP 허브의 모체: 증폭한 모원고 한 벌에서 교재와 영상이 모두 나온다

> **이 앱의 자리.** 사업계획서 프로세스에서 **XAM 의 앞부분**이다 — 기출을 OCR 해 여러 배로 증폭한
> **모원고(母原稿) 한 벌**에서 교재 원고와 영상이 모두 나오게 하는 종합 에이전트 도구 — **IP 허브의 모체**다. 이 앱이 전부가 아니다: 영상반 도구 ·
> 실습 게임 같은 무료 제공 앱들과 함께 결과물이 **IP 허브로 모인다.** 기출 OCR → 문항 집필·교정 → 해설을 모은 이론 노트 →
> 요약반·종합반 강의 원고 → 여러 사람의 듣기 검수까지가 여기서 끝나고, 그다음은
> 다른 도구가 그대로 받는다(아래 「다음 도구가 받는 것」).
>
> **이 앱이 만드는 것 — 세 부분**
>
> | 부 | 무엇 | 메뉴 묶음 |
> |---|---|---|
> | **1부 · 문항** | 기출 OCR → 과정 정의 → 문항 집필·교정 → **1부 빌드**(문제집) | 위 |
> | **2부 · 이론 노트** | 이론 HTML · 요약반 영상을 만들 수 있는 HTML · 종합반 영상을 만들 수 있는 HTML | 가운데(금색) |
> | **3부 · 해설영상** | 문제 HTML 을 잘라 증폭해 만든 영상 **전체** — 슬라이드 · 해설 자막대본 · 음성대본 · **렌더링** | 아래 |
>
> - **사이트 업로드·공개만 IP 허브**(`261014-local-moodle`, :8800)가 맡는다(1부·3부 빌드가 만든 06/ 을 가져간다).
> - 메뉴 이름: 「06/ 빌드」 대신 **1부 빌드**(문제집) · **3부 빌드**(해설영상)라 부른다.
> - 2부의 영상(요약 영상 · 종합반 강의)은 다른 도구가 그 HTML 을 받아 굽는다(hyper-close-frame ·
>   lecture-composer). **3부 해설영상은 이 앱에서 렌더링까지 끝낸다**(CPU 를 오래 쓰므로 다른 PC 의
>   CLI 렌더로 돌리기도 한다 — tools/render_all.bat).
> - ★ **목표: 발음대본(낭독 · `data-read`)은 이 앱에서 다 완료한다.** 하류(hyper-close-frame ·
>   lecture-composer · chodangi)는 받은 발음대본을 고치지 않고 그대로 읽는다. 그래서 낭독을 만들고
>   (② 낭독대본) · 여러 사람이 듣고(듣기 검수) · 지적을 반영하는 일이 모두 여기 있다. 문제풀이
>   번들의 발음도 영상 화면의 장면별 발음 칸에서 여기서 끝낸다.

```
setup.bat        (1회 — venv · constraints.txt 고정 버전 · chromium · claude CLI 확인)
run.bat          → http://127.0.0.1:8871/        (구버전 8870 과 동시에 띄울 수 있다)
lan.bat          → 사내망 공유. 남들은 보기 전용 + 듣기 검수 판정만 가능
```

## ★ v2 에서 바뀐 것 (2026-10-24 · 이전: `D:\00work\260803-xam-lo`)

저장소: **https://github.com/leedonwoo2827-ship-it/xam-local2** (공개). v1 은 공개 저장소 `xam-local` 에
남아 있고 이 저장소의 `xam-local-v1` 원격으로 이어 두었다. `axexam/`(그누보드 웹 소스)은 v1 때부터
공개 저장소에 subtree 로 들어 있던 것이다 — 비밀값은 넣지 않는다(`.env`·`data/`·`_docs/` 는 git 밖).

| | v1 (260803-xam-lo) | v2 (이 폴더) |
|---|---|---|
| 가동 | 외부 폴더 몇 곳(260729-new 등)을 가리킴 | **이 폴더 하나로 돈다.** 구버전은 3개월 뒤 지운다 |
| 오른쪽 | 없음 | **Claude 채팅 컬럼** — 시장조사 · 최근 현황 · 수정 위치 파악 · 앱 기능 실행(승인 카드) |
| 이론 | 요약노트 한 화면 | **이론 묶음 4단** — 해설 모아 노트 구조화 → 이론 요약 노트 → 요약반 강의 노트 → 종합반 강의 노트 |
| 검수 | 운영자 혼자 | **여러 사람 듣기 검수**(LAN) — 장마다 OK 인원 · 지적 · 반영 |
| 발행 | 빌드 → FTP 목록 → 서버 체크리스트 | 1부·3부 빌드(06/)·검증은 그대로. **사이트 업로드만** IP 허브 [가져오기] |
| 패키지 버전 | 그때그때 최신 | `constraints.txt` 로 검증된 버전 고정 |

### 좌측 메뉴

```
OCR 검수 · 구조화 MD로 정리 · 과정 정의 · 문항 집필 · 문항 교정 · 1부 빌드(문제집)
════ 이론 묶음 (금색 · 들여쓰기) ═════════════════════════════════
    해설 모아 노트 구조화 · 이론 요약 노트 · 요약반 강의 노트 · 종합반 강의 노트
══════════════════════════════════════════════════════════════
문항 슬라이드 제작 · 영상 제작·검수 · 인쇄본 · 3부 빌드(해설영상)
```

이론 메뉴는 문항 슬라이드·영상과 상관없이 따로 누른다(앞 노트만 있으면 된다).
메뉴마다 그 노트의 **[노트 빌드]** 가 있다. 위·아래 묶음의 슬라이드·영상은 **문항** 것이다.

### 세 노트의 역할 (사용자 지시 원문)

| 노트 | 폴더 | 역할 |
|---|---|---|
| **이론 요약 노트** | `03/summary_<과목>.html` | **텍스트 위주.** 웹 요약노트(S) |
| **요약반 강의 노트** | `03-2/` | 슬라이드에 **의무적으로 표와 SVG** 가 들어가서, 추후 **이미지화 영상**을 만드는 데 기여한다 |
| **종합반 강의 노트** | `03-3/` | 슬라이드의 **양을 증폭**시켜서, 추후 종합반 영상덱에 기존 생산된 모든 산물을 모아 함께 **다량의 롱폼**을 만드는 데 기여한다. 이후 미노출 종합본 HTML 을 만들고, 문제편을 제외한 초단기서의 핵심요약 HTML 까지 만든다 |

그 앞 단계 **해설 모아 노트 구조화**(`03/_outline/`)는 우리 모의고사 해설을 과목 → 항목 → 상세로
모으고 중복을 정돈한다. 사람이 목차를 승인하면 이론 요약 노트 집필이 그 목차를 따른다.

### 강의 노트 단계

```
요약반  ① 자막대본 → ② 낭독대본 → ③ SVG 추가 슬라이드 → 노트 빌드 → 듣기 검수(2명)
종합반  ④ 내용 n배 확장 → ② 낭독(새 장) → ③ SVG(새 장) → 노트 빌드 → 듣기 검수
                          ↑ 승인된 요약반 노트가 입력이다
```

- '사람' 단계는 **승인해야 다음이 열린다.** 빈 장이 하나라도 있으면 승인되지 않는다
  (요약반 ③ = 모든 장에 표 아니면 그림).
- 원천은 `03-2/<과목>.json` · `03-3/<과목>.json` 이다. 원고 HTML 은 [노트 빌드] 가 여기서 굽는다 —
  HTML 을 직접 고치면 다음 빌드가 덮는다.
- 원고 HTML 은 lecture-composer · summaryhtml2videoscripthtml 규약 그대로다:
  `h3` = 한 장, `data-id` · `data-say`(자막·대본) · `data-read`(소리 나는 대로, 다를 때만),
  `h1` 의 `data-say/read/outro-*`. 파일명도 실물과 같다 — `1summary-<과목>_원고.html` · `…_원고x3.html`.
- Claude 호출은 **대단원(h2) 하나 = 한 번**. 끊겨도 이어서 돈다(채운 장은 건너뜀). 실측(adsp 2과목 첫 대단원 4장):
  ① $0.18 · ② $0.16 · ③ $0.32.

### 노트 빌드 — 다음 도구가 받는 것

| 노트 | 빌드 결과 | 받는 곳 |
|---|---|---|
| 해설 구조화 | `03/_outline/<과목>.json · .md` | 이론 요약 노트 집필 |
| 요약반 | `03-2/<n>summary-<과목>_원고.html` + `04-2/lecture/summary/<과목>/` (html2deck PPTX 대단원별 · `narration.json` · `RENDER.txt`) | 다른 PC 에서 이미지화 → **hyper-close-frame**(HyperFrames)로 렌더링 → 요약 영상(M) |
| 종합반 | `03-3/<n>summary-<과목>_원고x<N>.html` + 위와 같은 덱 + `_longform-kit/<품목>/{notes,rounds,scripts}` | lecture-composer `jobs/<잡>/input/` → 종합반 강의(L) |

★ **덱과 영상은 따로다.** html2deck PPTX(요약반이면 **요약덱**, 종합반이면 종합반 덱)는 그 자체로
별도 산물이고, 영상은 원고 HTML 에서 따로 만든다(요약 영상 = 이미지화 → hyper-close-frame,
종합반 강의 = lecture-composer). 덱을 캡처해 영상을 만드는 것이 아니다.

### 듣기 검수 (여러 사람)

- 소리는 **영상과 같은 엔진·목소리**(vendor/chodangi 의 voicewright)로 서버가 굽는다 → `_audio/<과목>/<id>.<hash>.mp3`.
  처음 듣는 장은 20초 안팎. [미리듣기 미리 굽기] 를 해 두면 바로 나온다.
- `lan.bat` 으로 띄우고 검수자는 `http://<PC-IP>:8871/#/listen/summary/<과목>` 로 들어온다.
  이름을 한 번 적고 Space 듣기 · O 괜찮음 · F 고칠 곳 · J/K 이동.
- 기록은 `_review/<과목>.jsonl` 에 **덧붙이기만** 한다. OK 는 **그 소리(hash)에 대한 OK** — 낭독을
  고치면 그 장의 OK 는 낡고 다시 들어야 한다. 필요 인원(기본 2명)을 채우고 지적이 0 이어야 승인된다.
- ★ LAN 보기 전용의 **유일한 예외**가 이 판정 POST 하나다(`core/lan.lan_writable`). 지적 반영·장 편집은 운영자 PC 에서만.

### 오른쪽 채팅

**v2 에서 붙인 이유** — 시장조사 · 최근 현황 파악 · **IP 허브가 조사한 시험후기 · 정오표를 반영할 자리 찾기** ·
고칠 위치를 파일과 줄로 짚기. 평소에는 채팅이 아니라 **작업 현황판**(지금 하는 일 · 고친 뒤 반영할 것 ·
다음에 할 일)이고, 실행은 승인 카드를 눌러야 진행된다.

- 대화마다 `claude` CLI 하나를 붙잡아 둔다(구독 OAuth, API 키 없음). `data/chat/<sid>.json` 에 남고 이어 쓴다.
- 도구: `Read/Grep/Glob`(책 폴더 + 앱 소스) · `WebSearch/WebFetch`(시장조사) · 앱 도구 `api_get`(자유) ·
  `api_call`(**승인 카드**) · `navigate`(가운데 화면 이동). `Bash/Write/Edit` 는 없다 — 파일은 앱 API 로만 바뀐다.
- 앱 도구는 앱 자신의 REST 를 루프백으로 부른다 → 화면 버튼과 같은 게이트(409/423 · require_pd · 렌더 1개)를 지난다.
- 메시지마다 지금 화면(문항 id · 번들 · 노트 · 과목 · 선택한 글)이 붙는다. `Ctrl+J` 접기.
- ★ `claude.cmd`(npm 래퍼)는 SDK 가 실행을 거부한다 — `find_cli()` 가 네이티브 `claude.exe` 를 고른다.

### IP 허브 쪽에서 할 일 (이 저장소 밖)

- `hub/sources.py` 의 xamlo 수집 목록에 `03-2/*` · `03-3/*` · `03/_outline/*` · `04-2/lecture/**` · `_longform-kit/**` 추가.
- 업로드(FTP · 서버 임포트 · 유튜브 링크)는 허브의 [가져오기] 다음 단계로.

관련 GitHub 저장소 정리: `_context/깃허브_저장소_정리.txt`. 시연 영상 메모: `tools/demo/NOTES.md`.

---

# (이하 v1 문서 — 운영 지식은 그대로 유효하다. 발행 절차만 v2 에서 줄었다)

# XAM LOCAL — 문제은행 로컬 운영 콘솔

> ## ★ 2026-08-03 — 로컬 실측으로 고친 것 (먼저 읽는다)
>
> 이 저장소의 첫 판은 원격 세션에서 만들어졌고, **#1 을 추측으로 · #3 을 예전 버전
> 기준으로 · 일부 값을 짐작으로** 썼다. 이 PC 에서 왕복 검증을 돌리자
> `02/*.md 0/240` · `색인 0/2` · `05/lesson 0/24` 로 **전부 실패**했다.
> 원인 8건을 실측해 고쳤다. 규칙은 하나다 — **형식은 상수가 아니라 파일에서 되맞춘다.**
>
> | # | 첫 판의 전제 | 이 PC 의 실측 | 고친 곳 |
> |---|---|---|---|
> | 1 | `02/*.md` 는 LF 전용 | **CRLF.** `_rounds`·`03/` 은 LF — 한 트리 안에서 갈린다 | `core/atomic_io.file_newline` · `paths.to_disk` |
> | 2 | `02/` 에 `## 지문` 없음 | `passage`(빅분기 15문항) · `table`+`sql`(SQLD 26문항) | `md.passage_parts` |
> | 3 | lesson 블록에 `passage` 없음 | 지문 있는 문항에만, 그림 줄 뺀 값 | `lesson.block_from_rounds` |
> | 4 | `difficulty_stats` 정답순 = ①②③④ | **첫 등장 순서**(④ 60 부터) | `index.build_stats` |
> | 5 | `_rounds` = indent 2 | **indent 1.** SQLD 는 2, m04 만 LF, m05·m06 은 인라인 배열 | `services/book/jsonio.py` (신규) |
> | 6 | 보기는 항상 `① 본문` 한 줄 | 코드블록·표 보기는 `①` 단독 줄 + 빈 줄 + 블록 | `md.is_block_choice` |
> | 7 | 회차 3 · 문항 240 · 번들 24 · 과목 4 (상수) | SQLD 는 6회차·300문항·30번들·**2과목**. 자사는 곧 9회차 | `services/book/shape.py` (신규) |
> | 8 | 요약노트 키 = `분석기획·탐색·모델링·결과해석` | 실제는 `planning·explore·modeling·interpret` | `paths.summary_keys()` |
>
> 그리고 **도구 #1(OCR 검수)과 #3(영상 렌더 엔진), 발행 빌더가 모두 이 앱 안으로
> 들어왔다.** 밖에 남는 것은 **도구 #2(Claude Desktop 스킬)** 하나다.
>
> ```
> services/ocr/              ← #1  스캔 PDF → 초안 → 01/*.md 확정
> vendor/chodangi/           ← #3  deck.html → mp4 (자막 시간축 수정 반영)
> services/publish/axbuild/  ←     06/ + problems.json 빌더
> ```
>
> `.env` 의 `XAM_CHODANGI` 는 없어졌고 `XAM_AXEXAM` 은 웹 소스 참고용(선택)이다.
> 밖에 남는 의존성은 `ffmpeg` · Chromium · TTS 모델 뿐이다(§밖에 남는 것).
>
> ### 지금 이 폴더의 상태 (2026-08-03)
>
> `D:\00work\ocr-output-260730` 은 **`00/` + `01/` 만 있다.** 도구 #2 최종본으로
> 자사 9회분을 다시 만들 예정이라 `02~06`·`_rounds` 를 비웠다
> (기록: 그 폴더의 `_deleted-manifest-260803.txt`).
> 판독 초안은 `D:\00work\260730-ocr\data\` 에 그대로 있다 — #2 가 읽을 곳이다.
>
> **`01/` 만 있는 폴더는 정상적인 작업 상태다.** `OCR 검수` 와 `구조화 MD로 정리` 가
> 열리고, `문항 교정`·`영상`·`발행` 은 `_rounds/`·`02/` 가 생기면 열린다.
>
> 왕복 검증에 `_rounds/*.json` 그룹을 새로 넣었다. 문항 하나를 저장할 때마다 그
> 111KB 원천 파일이 통째로 다시 쓰이는데, 첫 판은 그걸 검증하지 않았다.
>
> **아직 열린 것 하나** — `ocr-output-260723`(SQLD) 의 `_rounds/m06.json` 은 만든
> writer 의 서식(짧으면 한 줄, 길면 블록)을 되맞추지 못했다. 게이트가 **닫힌 채**라
> SQLD 저장은 막혀 있다(데이터는 안전). 빅분기는 100% 통과한다.

## ★ UX 원칙 — 목록은 패널(위층), 작업은 바탕(아래층)

**이것이 이 앱 UX의 핵심이다. 어떤 화면을 새로 만들어도 반드시 이 규칙을 따른다.**

```
Layer 1  부유 패널   ← 목록. 고르는 곳.        #/scan  #/questions  #/video
   ↓ 항목을 누르면 패널이 닫히고
Layer 0  바탕        ← 작업. 일하는 곳.        #/scan/:id  #/questions/:id  #/video/:code
```

| 라우트 | 레이어 | 내용 |
|---|---|---|
| `#/home` | 바탕 | 파이프라인 4단계. 패널을 닫으면 여기로 돌아온다 |
| `#/books` | **패널** | 작업 폴더 목록 (좌하단 칩 클릭). 품목 전환 · 판독 폴더 지정 |
| `#/ocr` | **패널** | ★ OCR 검수 — 스캔 페이지 목록 (회차별) |
| `#/ocr/:src/:page` | 바탕 | 그 페이지 작업 — 좌 OCR 원문 / 우 문제 카드 · 스캔 드래그로 그림 |
| `#/scan` | **패널** | OCR 본문 목록 (확정된 01/*.md 를 한 문항씩) |
| `#/scan/:id` | 바탕 | 그 문항 정리 — 문제·지문·보기·해설 + 원문 PDF + 확정 |
| `#/questions` | **패널** | 문항 목록 (회차 필터) |
| `#/questions/:id` | 바탕 | 그 문항 교정 — 5파일 트랜잭션 |
| `#/video` | **패널** | 번들 목록 |
| `#/video/:code` | 바탕 | 그 번들 작업 — 씬·슬라이드·음성·자막 |
| `#/precheck/:code` `#/job/:id` `#/preview/:key` | 패널 | 보고 닫는 표면 |
| `#/publish` `#/summary` | 바탕 | 절차 화면 |

**왜 이 구조인가**
- 목록은 "고르는 곳" 이라서 뜨고 사라져야 한다. 바탕을 차지하면 작업 공간이 줄어든다.
- 패널을 열고 닫아도 **바탕은 언마운트되지 않는다**. 그래서 24번들 렌더(최대 두 시간)의
  2초 폴링과 에디터의 미저장 텍스트가 살아 있다. 이게 2층으로 나눈 실질적 이유다.
- 미저장 텍스트를 든 화면은 절대 패널에 두지 않는다 — 패널은 Esc·스크림 클릭으로 닫힌다.

**구현 지점**: `static/js/shell.js` 의 `routes` 테이블(`layer: "panel"` / `"base"`),
`static/js/panel.js` 의 `GROUPS`. 각 화면 모듈은 `mount(root, ctx)` 에서 `ctx.panel`
유무로 `mountList()` / `mountWork()` 를 갈라 쓴다.

**첫 화면은 바탕이다.** 앱을 켜면 `#/home` 이 뜬다 — 패널을 열어 두고 시작하지 않는다.
예전 기본값이 `#/scan` 이라, 작업 폴더를 고르지도 않았는데 "이미 스캔된 80문항 목록" 이
담긴 부유 창이 먼저 떠 있었다. 패널은 사람이 열어야 뜬다.
작업 폴더를 한 번도 지정하지 않았으면(`data/books.json` 없음) 그 바탕에서 **폴더 지정부터**
받는다(`.env` 값은 '제안' 으로만 보여 준다). 한 번 지정하면 그다음부터 그 폴더로 시작한다.

## ★ UX 원칙 2 — 상태 3색 규칙 (목록은 빠진 것이 눈에 걸려야 한다)

```
state-todo    아직 안 함 · 확인 필요   →  하얗게. 색을 주지 않는다   ← 여기가 '할 일'
state-part    하다 만 · 일부만 끝남    →  노랑
state-done    끝남 · 대조·검수 완료    →  청록 채움(--ok 계열)
state-empty   판정 불가 · 틀만 있음    →  점선
```

**안 한 쪽에 색을 주면 안 된다.** 목록은 훑는 화면이라, 모든 칸에 색이 있으면 어디가
남았는지 세어야 알 수 있다. 실제로 그 사고가 있었다 — OCR 페이지 카드가 "초안에 문항이
있으면 초록" 이어서, 판독만 하고 대조는 하나도 안 한 3회차가 완료한 1·2회차와 똑같이
초록이었다. 훑어도 할 일이 보이지 않았다.

색이 채워지는 방향이 진행도다 — 끝난 것은 늘고, 안 끝난 것은 하얗게 줄어든다.

**구현 지점**: 판정은 `static/js/util.js` 의 `stateClass(전체, 끝난것)` 하나,
색은 `static/css/app.css` 의 `§상태 3색 규칙` 한 곳. **새 목록을 만들 때 색을 새로
정하지 말고 이 클래스를 붙인다.** 화면마다 색을 정하면 같은 뜻이 화면마다 달라진다.
지금 쓰는 곳: OCR 페이지 카드(`.oc-cell`) · 구조화 MD 목록(`.sc-row`).


`https://axexam.mycafe24.com/exam/` (그누보드5 · PHP 8.4 · MariaDB) 에 두 번째 품목
**빅데이터분석기사 필기**(240문항 = 3회차 × 80, 4과목, 영상 24편)를 올리기 위한
로컬 단일 사용자 앱. 도구 #1·#3 의 산물을 검수하고 axexam 파이프라인을 안전하게 호출한다.

```
setup.bat        (1회)
run.bat          → http://127.0.0.1:8871/   (v2)
```

## 도구 4개의 관계

```
#1 OCR 검수           ★ 이 앱 안으로 들어왔다 → services/ocr/ · 화면 #/ocr
                        판독(스캔→초안)은 Claude Code 창이 하고, 검수·확정은 이 앱이 한다
#2 exambook-forge     Claude Code 스킬. deck.html · lesson JSON 집필   ← 유일하게 밖에 남는다
#3 chodangi-mp4-forge 로컬. deck.html → mp4          D:\00work\260724-chodangi-mp4
#4 XAM LOCAL          ← 이 앱. 검수 · 구동 · 발행
   axexam            웹(그누보드5). 로컬이 원본, 서버는 사본   D:\00work\260729-new
```

★ `.env.example` 의 경로 두 개는 이 PC 에 없다. 실제 위치는 위 표와 같다
  (`chodangi-mp4-forge-main` → `260724-chodangi-mp4`, `_ref\axexam` → `260729-new`).

### 도구 #1 — 이 앱 안의 OCR 검수

```
00/*.pdf  ──[이 앱: PDF 렌더]──►  <OCR폴더>/data/raw_pages/<stem>/page_NNN.png
                                          │
                          [Claude Code 창: 판독]  ← 늘 이 창에서 요청한다
                                          ▼
                                  data/ocr_draft/<stem>_pNNN.json
                                          │
                          [이 앱 #/ocr: 검수 · 확정]
                                          ▼
                                  01/{회차}-{문항}.md
```

`<OCR폴더>` 는 BOOK 밖이다(도구 #1 프로젝트 안 `data/`). BOOK 이름에서 유도하고
(`ocr-output-260730` → 형제 `260730-ocr`), `.env` 의 `XAM_OCR` 이나 작업 폴더
패널의 `판독 폴더` 버튼으로 바꾼다. **이 창과 앱이 같이 쓰는 폴더**라서 앱의 쓰기는
전부 원자적 + `.bak` 이고, 내용이 같으면 쓰지 않는다.

```
venv\Scripts\python -m services.ocr.pdfrender          00/*.pdf → 페이지 PNG (--dry 로 계획만)
venv\Scripts\python -m services.ocr.checks             ★ 확정 게이트 + 회차 정합성
venv\Scripts\python -m services.ocr.answers --check    분리형 교재 정답·해설 주입 (대조만)
```

`checks` 가 통과하지 않으면 화면의 `확정(MD 저장)` 이 409 로 막힌다 — 통과하지 못하는
렌더러로 확정하면 이미 검수해 둔 `01/*.md` 가 조용히 바뀐다.

## 운용 플랜 — 문제집 하나를 4일에 낸다

한 품목(1,000문항 · 20회차) 기준. **자동으로 이어지는 것은 집필 → `04/` 까지**이고,
번들·이론·영상은 사람이 눌러야 시작한다. 그것을 하루에 어떻게 나눠 넣는지가 이 표다.

| | 오전 | 오후 · 저녁 |
|---|---|---|
| **1일** | 집필 500문항 걸어 두고 일과 | 퇴근하며 남은 500문항 걸기 |
| **2일** | 이론 요약노트 만들어 **다른 PC 로 영상 작업 의뢰** | 슬라이드 제작 → 영상 제작·검수 시작, 밤에 보내기 |
| **3일** | 문제 영상 **발음 교정** | |
| **4일** | 이론 영상 납품 OK | |

★ **집필은 세션 창(5시간)에 걸린다.** 그래서 하루를 오전·퇴근 두 번으로 나눈다.
  한 번에 1,000문항을 걸면 중간에 멈추고, 멈춘 자리부터 다시 눌러야 한다(그건 된다 —
  합격한 파트는 건너뛴다). 주간 한도가 아니라 **세션**이므로 사용량 화면의 주간 %가
  낮아도 걸린다.

★ **이론은 회차가 다 모인 뒤에** 만든다. 회차별이 아니라 **과목별**이라
  `_rounds/*.json` 전체의 해설을 훑는다 — 절반만 있을 때 만들면 나머지가 빠진다.

★ **영상은 다른 PC 로 넘긴다.** 렌더는 모델을 부르지 않고 CPU·TTS 를 오래 물어서,
  같은 PC 에서 집필과 겹치면 둘 다 느려진다.

### 눌러야 하는 것 · 저절로 되는 것

```
[실행]  집필 ─자동→ 반입 ─자동→ 파생 ─→ 02/ · 04/
                                          ↑ 여기까지가 자동

[번들 굽기]   04/ → 05/          영상 제작·검수 화면
[슬라이드]    05/ 를 눈으로 확인   /slide/
[영상 렌더]   05/ → mp4
[이론]        _rounds/ → 03/summary_<과목키>.html   과목마다 1개
[발행]        사전점검 → 빌드 → FTP
```

한 회차의 파트가 하나라도 불합격이면 **반입이 통째로 보류된다** — 반쪽 회차를 만들지
않기 위해서다. 그 회차만 다시 [실행] 하면 된다.

## 데이터 흐름 — 이것만은 외워야 한다

```
_rounds/mNN.json  ──[문항 교정]──┬─► 02/mNN-KK.md + _index.json + difficulty_stats.json + 02/assets/*.svg
                                 └─► 05/mNN-K/source/lesson_mNN-K.json   ★ 본문이 웹에 가는 경로

02/ (과목·난이도·태그·검수상태) ─┐
05/*/source/lesson_*.json (본문)─┼─► axexam/scripts/build_check.py ─┬─► 06/ ──FTP──► /www/exam/
data/youtube_map.bigdata.json   ─┘                                  └─► 06/problems.json
                                                                          └─브라우저 업로드─► /adm/exam_import.php ─► ex_problem

05/*/source/deck.html ──[#4]──► 05/*/source/deck.pptx ──[PowerPoint]──► 05/*/images/slide_NN.png
                                                                            │
                                              05/*/script/*_script.json ────┼──[#3]──► draft/*.static.mp4
                                              (씬을 pptx 장 나눔에 맞춰 씀)  ┘         └─[유튜브 수동]─► youtube_map
```

### ★ 슬라이드의 진실이 PPTX 로 옮겨 왔다 (2026-08-24)

전에는 `deck.html` 을 Chromium 으로 캡처한 것이 영상의 슬라이드였다. 지금은
`vendor/exam2deck` 이 **좌표를 재서** pptx 를 그리고, PowerPoint 로 뽑은 PNG 가
영상으로 간다. 바꾼 이유는 채움률이다 — `services/deck/paginate.py` 는 잘림을 막으려고
넉넉히 일찍 쪼갠다(캡처에서 잘리면 내용이 **사라진다**). 그 대가로 한 장이 높이 예산의
3할밖에 안 찼다. pptx 는 캡처가 아니라 좌표라서 재서 놓을 수 있다.

| | 전 | 후 |
|---|---|---|
| 장 나눔의 진실 | `deck.html` 의 `.slide` | `05/<번들>/source/pages.json` |
| 영상의 슬라이드 | Chromium 캡처 | PowerPoint 로 뽑은 PNG (`--reuse-images`) |
| `deck.html` 의 몫 | 전부 | 미리보기 + **변환기의 입력** |
| 씬(script) | `render.build_pages()` 의 metas | pptx 의 장 목록 (`bake.write_script`) |
| 문항이 여러 장일 때 낭독 | 첫 장만 읽고 뒷장은 조용한 4초 | **n등분해서 장마다** (쉬는 자리에서 자른다) |

★ 화면 순서는 `슬라이드` 메뉴의 ① 굽기 → ② PPTX → ③ 장수 확정 → ④ 그림파일 이고,
  바닥의 띠가 다음에 누를 것 하나를 말한다.

★ **장수는 PowerPoint 에서 합치지 않는다.** ③의 ± 표에서 고친다 —
  `_deck-export/NN회.pages.json` 에 남고, 씬·낭독·이미지가 같이 따라온다. pptx 를
  손으로 고치는 것은 되지만(고친 파일이 그대로 PNG 가 된다), **장 수가 바뀌면 멈춘다.**

★ 품목별 값은 `exams/<pd>.json` 의 `deck.pptx_scale`. SQLD 실측(2026-08-24):
  배율 1.0 → 채움 0.31 · 덜 찬 장 236 / 배율 **1.6** → 채움 0.61 · 덜 찬 장 25 · 넘침 0.

**★ `build_check.py` 는 문제 본문(문제문·보기·해설·정답)을 `05/*/source/lesson_*.json`
에서만 읽는다.** `02/*.md` 는 과목·난이도·태그·`verified`/`reviewed`/`needs_review` 만
공급한다. `02/` 만 고치면 다음 빌드가 낡은 `05/` 본문을 다시 내보내고 `pr_hash` 가
그대로여서 임포트가 `변경없음` 을 찍는다 — **수정이 웹에 전혀 반영되지 않는다.**
그래서 이 앱의 저장은 항상 다섯 곳을 함께 쓴다.

## 화면 4개

| 화면 | 라우트 | 하는 일 |
|---|---|---|
| 문항 교정 | `#/questions[/:id]` | 240문항 검수 큐 + 에디터. 저장 = 5파일 트랜잭션 |
| 영상 제작·검수 | `#/video` | 번들 24개 상태 · 1:1 사전점검 · 렌더 실행 · mp4 미리보기 |
| 발행 to XAMpass | `#/publish` | 사전점검 → 빌드 → 드라이런 → FTP 목록 → 서버 체크리스트 |
| 요약노트 검수 | `#/summary[/:key]` | `03/summary_*.md` 편집 (발행되는 건 `.html` — 배너로 경고) |

패널(부유 창): `#/precheck/:code` 사전점검 · `#/job/:id` 렌더 로그 · `#/preview/:key` 발행될 HTML.

### 문항 교정 단축키 — 240개를 도는 속도가 전부다

| 키 | 동작 |
|---|---|
| `Ctrl+Enter` | 저장 + 검수완료 + **다음 미검수로 이동** ← 핵심 루프 |
| `Ctrl+S` | 저장 |
| `Alt+1~4` | 정답을 그 보기로 |
| `Alt+Q/W/E` | 난이도 상/중/하 |
| `Alt+↓/↑` | 목록에서 다음/이전 문항 |
| `Ctrl+K` | 검색 · `Ctrl+B` 메뉴 접기 · `?` 도움말 |

## 저장하면 실제로 쓰는 파일

| # | 파일 | 내용 |
|---|---|---|
| 1 | `_rounds/mNN.json` | 집필 원천 |
| 2 | `02/mNN-KK.md` | front matter 18키 + 문제/보기/해설 |
| 3 | `02/assets/{name}.svg` | 인라인 SVG → 파일 |
| 4 | `02/_index.json`, `02/difficulty_stats.json` | 재계산 (md 는 다시 쓰지 않는다) |
| 5 | **`05/mNN-K/source/lesson_mNN-K.json`** | 본문이 웹에 가는 경로 |

`04/lesson_mNN.json` 과 `05/*/source/deck.html` 은 **쓰지 않는다**. deck 과 mp4 는
낡았다고 표시만 한다 — 다시 만드는 것은 #2/#3 의 일이다.

내용이 실제로 바뀐 파일만 쓰고, 모든 쓰기는 원자적(temp+fsync+`os.replace`) + `.bak` 형제다.

### 충돌 처리
`_rounds` · `02/md` · `05/lesson` 세 파일의 복합 etag 를 저장 시점에 다시 대조한다.
- **409** 화면을 연 뒤 디스크가 바뀌었다 → 다시 읽으라고 안내
- **423** 파일이 잠겨 있다(편집기에서 열어 둠) → 닫고 재시도
- **400** 검증 실패 (보기 개수 · 정답 범위 · `subject_no` 타입 …)

## 바이트 충실도 검증 — 저장 기능의 게이트

`02/*.md` 240개와 두 색인, `05/lesson` 24개는 원격 세션에서 만들어졌고 로컬에 생성
스크립트가 없다. 렌더러가 한 글자라도 어긋나면 한 문항 저장이 나머지를 손상시킨다.

```
venv\Scripts\python -m services.book.verify
```

```
  _rounds/*.json                 3/3        ★ 저장이 이 파일 전체를 다시 쓴다
  02/*.md                        240/240
  02/_index.json + stats         2/2
  05/*/source/lesson_*.json      24/24
  02/assets/*.svg                43/43     (참고용, 게이트 아님)
```

★ **숫자는 폴더에서 나온 값이다.** 회차가 m01~m09 로 늘면 같은 명령이
`9/9` · `720/720` · `72/72` 를 찍어야 한다. 숫자가 안 바뀌면 어딘가에 상수가
남아 있다는 뜻이다. SQLD 로 전환하면 `6/6` · `300/300` · `30/30` 이 된다.

**전부 통과하지 않으면 `PUT /api/questions/{id}` 가 409 로 막힌다.** 화면에서도 같은
검사를 `GET /api/verify/roundtrip` 으로 볼 수 있다.

재현해야 했던 실측 세부 (이 중 하나만 틀려도 240개가 달라진다):
- MD 는 LF 전용 · BOM 없음 · EOF 개행 하나. front matter 18키 순서 고정, `tags` 만 인라인 flow
- 그림 줄은 `assets[]` 가 아니라 **`_rounds` 의 `explanation` 안에** 이미 들어 있다
- 반대로 `05/lesson` 의 `explanation` 은 그 그림 줄을 **뺀** 형태다
- 두 색인 JSON 은 `indent=2, ensure_ascii=False`, **끝 개행 없음**
- `difficulty_stats.json` 의 키 순서는 **첫 등장 순서** — `overall` 은 전체, `by_round` 는 **회차별**
  (m01 하·상·중 / m02 중·하·상 / m03 하·중·상)
- `_index.json.round` 와 `subject_no` 는 **int** 여야 한다. 문자열이면 `problems.json` 의
  `subjects` 가 빈 배열이 되고 전 행 `sj_no=0` 이 되는데, `과목 N종` 리포트 줄은 이걸 못 잡는다
- `has_sql`/`has_table` 은 `_rounds` 에 없다(실측 240문항 전부 false) → 기존 md 에서 **보존**한다

### 알려진 드리프트 2건 (정상)
`m01-47` · `m02-47` 의 `05/lesson` 낭독문이 `_rounds` 와 다르다. `"알(R)이며"` 를
`"알이며"` 로 손질해 둔 것 — TTS 가 `(R)` 을 "괄호 알 괄호" 로 읽기 때문이다.
낭독문을 직접 편집하지 않는 한 lesson 쪽 손질을 유지한다.

## 자막 시각 — 두 시간축 (2026-08-02 해결)

한동안 자막이 영상보다 씬마다 0.6초씩 앞섰고, 42씬이면 **24.6초** 벌어졌다.
원인은 chodangi 안에서 같은 저장소의 두 코드가 서로 다른 시간축을 쓴 것이다.

```
voicewright/srt.py::merge_scene_cues    cursor += dur              오디오 길이 합
mp4maker/timeline.py::build_timeline    sum(dur) - N * crossfade   실제 영상 (xfade 로 겹침)
```

**고친 방식** — `make_bundle_video.CROSSFADE_SEC` 하나에서 세 곳으로 내려보낸다.
값이 두 군데로 갈리면 조용히 다시 어긋나므로, 상수는 반드시 한 개여야 한다.

| 받는 곳 | 무엇이 맞춰지나 |
|---|---|
| `app.synth.synthesize(crossfade=)` → `rebuild_chapter_srt` → `merge_scene_cues` | 통합 SRT · `.ko.vtt` |
| `python -m mp4maker --crossfade` | 실제 합성 (기본값도 0.6 이지만 명시한다) |
| `_finalize_bundle()` | `review.json` 의 `startSec` · `totalSeconds` |

**번들마다 시간축이 다르다.** `review.json` 에 표식을 남긴다.

- `"timebase": "video"` + `"crossfadeSec": 0.6` — 보정 완료. `startSec` 을 **그대로** 쓴다
- 키 없음 — 옛 번들. 읽는 쪽이 `startSec - 씬순서 × crossfade` 로 보정한다

`services/render/bundles.py::scenes()` 가 번들 단위로 이걸 보고 `mp4_start_sec` 를 정한다.
★ 표식을 안 보고 무조건 빼면 **보정한 번들을 또 보정해서 반대로 틀어진다.**
옛 번들과 새 번들이 한 폴더에 섞일 수 있으므로 폴더 단위로 판단하면 안 된다.

## 발행 절차

`#/publish` 가 이 순서를 강제한다.

1. **사전점검** — 규칙 48개. `error` 는 우회 불가, `warn` 만 확인 후 통과
2. **빌드** — 아래 명령. 화면에 그대로 보여주고 확인 모달을 띄운다
3. **problems.json 검증** — 서버에 없는 임포트 드라이런을 로컬에서 재현
4. ~~FTP 목록~~ — v2: IP 허브가 맡는다(아래)
5. ~~서버 체크리스트~~ — v2: IP 허브가 맡는다

```
_ref\axexam\.venv\Scripts\python.exe scripts\build_check.py
    --book        D:\00work\ocr-output-260730          ★ 생략 금지
    --pd          bigdata                              ★ 생략 금지
    --youtube-map data\youtube_map.bigdata.json        ★ 패치 1번 필요
    --api-base    ./api/
    --emit-json
    --prune
```

> ★ **`--book` 과 `--pd` 는 절대 생략하지 않는다.** 둘 다 기본값이 SQLD 다
> (`--book D:/00work/ocr-output-260723`, `--pd sqld`). 하나라도 빠지면 라이브 SQLD
> 문제은행을 덮어쓴다 — `pr_key` 가 `m01-1#1`…`m03-5#50` 구간에서 겹치고 `pr_id` 는
> 보존되므로 회원 오답노트 밑에 엉뚱한 문제가 들어앉는다. **되돌릴 수 없다.**
> 이 앱은 인자 없는 호출 경로를 코드에 두지 않는다.

빌드 리포트에서 확인할 것: `240문제 · 3회` · **`과목 4종`** · `EXAM_API = ./api/` ·
`SVG 못 찾음` 없음 · `STALE` 없음.
`과목 1종` 이면 subject 폴백 버그가 되살아난 것이다.

### ★ v2 — 4번 이후는 IP 허브가 한다

FTP 목록 · 업로드 폴더 · 서버 체크리스트(`ftplist.py` · `stage.py` · `data/publish/checklist.json`)를
지웠다. `#/publish` 는 ①사전점검 → ②(영상 매핑) → ③빌드 → ④problems.json 검증까지이고,
마지막 카드가 IP 허브로 안내한다. 허브는 `06/pd/<pd>/problems.json` · `problems.js` 와
`_rounds` · `02` · `05` 를 수집해서 공개 후보만 걸러 내보낸다(`hub/publish.py`).
서버 단계(ex_product 행 · 유튜브 · FTP · exam_import)의 순서와 함정은 v1 기록
(`git show 7b94d7b:README.md`)과 허브 문서에 있다.

## 자막 시간축 수정 4건 — 이제 소스에 반영돼 있다

★ **렌더 엔진이 이 앱 안으로 들어왔다** (`vendor/chodangi/`, 2026-08-03). 예전의
`tools/patch_chodangi.py` 는 지웠다 — 패치가 아니라 **코드**다. 어디를 왜 고쳤는지는
그 파일들의 주석에 그대로 있다.

| 무엇 | 어디 |
|---|---|
| 1 crossfade 보정 | `vendor/chodangi/voicewright/srt.py::merge_scene_cues` |
| 2 crossfade 전달 | `voicewright/batch.py` · `chodangi_app/synth.py` |
| 3 무음 씬 포함(오디오 기준 훑기) | `chodangi_app/synth.py::rebuild_chapter_srt` |
| 4 `CROSSFADE_SEC` 단일 상수 · `review.json` `timebase` · 진행 로그 · 스크래치 비우기 | `make_bundle_video.py` |
| 5 1:1 판정의 근거를 `source/pages.json` 으로 (2026-08-24) | `make_bundle_video.py::_count_pages_manifest` |

5번이 필요한 이유는 아래 「슬라이드의 진실이 PPTX 로 옮겨 왔다」 다. 강의덱을 쓰는
번들은 `deck.html` 의 `.slide` 수와 씬 수가 **일부러** 다르다.

반입 기준은 이 PC 의 `D:\00work\260724-chodangi-mp4` =
`chodangi-mp4-forge` **main @3ff1350 (07-31, 상류와 동기)** 였고, 그 복사본은
자막 시간축이 **미패치** 상태였다(`srt.py` 가 `cursor += dur`, `CROSSFADE_SEC` 없음).

자막이 영상보다 앞서는 버그 **두 개**였다. m01-1(46씬)에서 합쳐 83.6초 어긋났다.

1. **crossfade 미보정 — 27.0초.** 같은 저장소 안에서 두 코드가 서로 다른 시간축을 썼다.
   ```
   voicewright/srt.py::merge_scene_cues   cursor += dur              오디오 길이 합
   mp4maker/timeline.py::build_timeline   sum(dur) - N * crossfade   실제 영상(xfade 로 겹침)
   ```
2. **무음 씬 누락 — 56.6초 (더 크다).** `rebuild_chapter_srt` 가 씬을 `*_narration.srt`
   **파일 목록**으로 훑었다. 카운트다운·여백은 TTS 를 안 타서 SRT 가 없으니 통째로
   빠지고, 그 길이(5초×10 + 2초×10 = 70초)가 누적에서 사라지고 crossfade 를 뺄 씬
   순번도 25(진짜 44)로 작아졌다. → **오디오 기준**으로 훑고 큐만 비운다.

값이 두 군데로 갈리면 조용히 다시 어긋나므로 **상수는 하나**다.

```
make_bundle_video.CROSSFADE_SEC = 0.6
   ├→ synthesize → rebuild_chapter_srt → merge_scene_cues    통합 SRT · .ko.vtt
   ├→ python -m mp4maker --crossfade 0.6                     실제 합성
   └→ _finalize_bundle()                                     review.json startSec
```

덤으로 3) TTS·deck 캡처 진행 로그(그 구간이 번들당 몇 분인데 한 줄도 안 뱉었다),
4) 스크래치 비우고 시작(취소 뒤 남은 `munje/chNN` 을 다음 실행이 재사용했다).

**실측** — `startSec` 공식 46/46 일치 · `totalSeconds` 897.354 vs mp4 실제 897.842
(패치 전 924.354) · 씬44 자막 `-56.600초` → `+0.000초` · 마지막 큐 끝 895.954초 =
마지막 낭독 씬 끝.

## axexam 패치 3건 — 적용하지 않는다 (상류가 이미 더 낫게 해결했다)

★ 발행 **빌더**도 이 앱 안으로 들어왔다 (`services/publish/axbuild/`). 들여오면서
`tools/patch_axexam.py` 의 3건을 적용하려 했는데, 이 PC 의 axexam
(`D:\00work\260729-new`) 을 확인해 보니 **셋 다 이미 해결돼 있고 방식이 더 좋았다.**
그래서 패치를 적용하지 않고 도구를 지웠다 — 적용하면 되돌리는 셈이다.

| 패치가 하려던 것 | 상류의 현재 구현 |
|---|---|
| `--youtube-map` 플래그 신설 | `youtube_map_path(pd_id)` 가 `data/youtube_map.<pd>.json` 을 자동 선택 — 플래그 불필요 |
| `emit(DETAIL, "sqld.html")` → `{pd}.html` | `detail.html` 하나로 굽고 `?pd=` 로 품목을 가른다 |
| `detail_template.html` 파라미터화 | `{{BRAND}}` · `{{PD}}` 등으로 이미 전면 토큰화 |

빌더에서 고친 것은 **한 줄**이다 — `ROOT` 를 이 저장소 루트로 (`parents[1]` →
`parents[3]`). 위치가 `scripts/` 에서 `services/publish/axbuild/` 로 바뀌었기 때문이고,
안 고치면 `data/youtube_map.<pd>.json` 을 엉뚱한 곳에서 찾아 조용히 "영상 없음" 으로
빌드된다.

`buildcheck.build_args()` 는 `--youtube-map` 을 **빌더가 그 플래그를 받을 때만** 넘긴다.
버전을 가정하지 않으므로 상류가 어느 쪽이어도 동작한다.

**2차(미구현, 문서로만 남김)** — 역반영. 웹에서 고친 문항(`edited_by` 가 채워진 행)은
재임포트에서 건너뛰고 `02/` 와 어긋난 채 남는다. axexam 의 BACKLOG 도 "안 하면 언젠가
원본 복원이 낡은 내용을 되살린다" 고 경고하는데 코드는 0개다. 붙일 자리는 준비돼 있다 —
`adm/exam_export.php` 를 만들고, 이 앱의 5파일 저장 트랜잭션에 그 데이터를 흘려 넣으면
된다(`02/*.md` 만 쓰면 조용한 무동작이다).

## 구조

```
app.py            FastAPI · MIME shield · load_dotenv(utf-8-sig) · 라우터 · /static+/book 마운트
core/             constants.py (모든 경로) · atomic_io.py (개행 감지 포함)
routes/           ★ JSON/파일전송 전용. 페이지 HTML 은 app.py 만. Pydantic 없음
services/book/    paths shape jsonio derive md lesson rounds index store verify scan books
                    ← FastAPI import 금지.  shape=회차·문항·과목 개수(폴더 계산)
                                            jsonio=JSON 서식 되맞추기
services/ocr/     ★ 도구 #1 — project draft finalize pdfrender answers checks
services/render/  bundles precheck runner        (runner → vendor/chodangi 서브프로세스)
services/publish/ validate buildcheck ftplist  +  axbuild/ ★ 발행 빌더 내장
services/jobs/    jobstore registry
static/           index.html · css/{app,ocr}.css · vendor/tex-svg.js(수식)
                  js/{util icons charts panel shell store + 화면 6개(ocr 포함)}
services/deck/    render paginate slidecss theme preview  (deck.html — 미리보기·변환기 입력)
                  + rounddeck pptxdeck slideimg  ★ 강의덱: 회차 합침 → pptx → PNG
vendor/chodangi/  ★ 도구 #3 렌더 엔진 내장 — make_bundle_video · slides · voicewright
                  · mp4maker · chodangi_app · config · assets(TTS 395MB, git 제외)
vendor/exam2deck/ ★ 도구 #4 강의덱 변환기 내장 — deck HTML → pptx (좌표를 재서 그린다)
                  출처·고친 곳은 `vendor/exam2deck/_SOURCE.md`
data/             런타임 (git 제외) — books.json · jobs/ · publish/ · youtube_map.<pd>.json
_ref/axexam/      웹 소스 참고용(선택). 발행 빌드에는 필요 없다
```

### 밖에 남는 것 (의존성)

내장할 수 없는 것만 남는다. `setup.bat` 이 전부 확인한다.

| 무엇 | 왜 못 넣나 | 없으면 |
|---|---|---|
| `ffmpeg` (PATH) | 바이너리 | TTS 를 몇 분 돌린 뒤 **마지막 합성에서** 실패 |
| Chromium (playwright) | 바이너리 · 114MB | deck 캡처 불가 (`--no-audio` 도 못 씀) |
| `vendor/chodangi/assets/` | 395MB · git 실용성 | 음성 없음(`--no-audio` 로만 렌더) |
| PowerPoint | 상용 프로그램 | pptx → PNG 불가 = **영상 슬라이드를 못 만든다.** 캡처로 대신하지 않는다 |
| Pretendard (설치 글꼴) | 라이선스·용량 | 줄 수를 맑은 고딕으로 재서 "일찍 줄바꿈" 쪽으로 떨어진다 |
| 도구 #2 (Claude Desktop 스킬) | 저작 도구 | `05/` deck·lesson 을 만들 수 없다 |

프론트는 `aim-local`(`d:\00work\260801-aim redesign`) 구조를 이식했다. 3층 레이어
(베이스 / 부유 패널 / 모달), 2층 해시 라우터, `meta` + `mount(root, ctx)` 화면 모듈 계약,
스레드 + JSON 파일 + 2초 폴링 잡 모델. 프레임워크·번들러 없음.

퍼스널컬러만 **버밀리언 주홍**(`--brand #c41c0b`)으로 교체했고 리넨 3서피스는 유지했다.
브랜드가 빨강이 되면서 `--err` 를 딥 플럼(`#6b1d4a`)으로 옮겼다 — 정답/오답을 다루는
앱에서 브랜드색과 오류색이 같은 빨강이면 제품이 깨진다. 차트에는 `--c-ok` 를 따로 뒀다
(정답률을 빨강 램프로 칠하면 안 된다).

## 작업 폴더 — 품목 전환 = 폴더 권한

좌하단 칩을 누르면 작업 폴더 패널이 뜬다. Claude Code 데스크탑처럼 **OS 네이티브 폴더
선택창**으로 권한을 주고, 지정한 폴더만 읽고 쓴다.

- 폴더를 추가하면 `_rounds/*.json` 을 스캔해 **회차 수를 자동 인식**한다. 3회차든 9회차든
  21회차든, 초기에 1~2회차만 있어도 그대로 뜬다(하드코딩 없음).
- `pd` 코드와 품목명은 폴더 안 `_book.json` 에 남긴다 — 폴더를 옮겨도 따라오고, 발행할 때
  `--pd` 로 나간다.
- 등록 목록은 `data/books.json` (`active` + `items`).

**완성된 책만 쓸 수 있는 게 아니다.** 폴더는 단계로 구분한다 — `01/` 만 있는 폴더(#1 을
돌리고 #2 를 돌리기 직전)가 정상적인 작업 상태다.

| 단계 | 조건 | 되는 화면 |
|---|---|---|
| `01/ 기출까지` | `01/*.md` 존재 | 구조화 MD로 정리 |
| `02/ 문항까지` | `_rounds/` + `02/*.md` | + 문항 교정 · 요약노트 |
| `05/ 영상까지` | `05/` 번들 존재 | + 영상 제작·검수 · 발행 |

### ★ `pd` 는 추측하지 않는다

`pd` 는 발행 때 `--pd` 로 나가서 **어느 라이브 품목을 덮어쓸지** 정하는 값이다. 틀리면
`pr_key` 가 겹치는 행을 UPDATE 하고 `pr_id` 는 보존되므로, 회원 오답노트 밑에 엉뚱한
문제가 앉는다. 되돌릴 수 없다.

한 번 사고가 났다 — 폴더 이름 `260723` 을 `sqld` 로 추측했는데 그 폴더에는 빅데이터 책
**복사본**이 들어 있었고, 그 추측이 폴더의 `_book.json` 에까지 굳었다. 그대로 발행하면
라이브 SQLD 300문제를 덮어썼다. 그래서:

- **폴더 이름으로 pd 를 추측하는 코드를 지웠다.** `_book.json` 에 사람이 확정한 값만 읽는다.
- pd 를 모르면 **비워 둔다.** 편집·렌더는 그대로 되고 **발행만** 막힌다
  (`buildcheck.require_pd()` 가 잡을 만들기 전에 끊는다).
- `active_pd()` 는 비었을 때 상수로 되돌아가지 않는다 — 그 "조용한 기본값" 이 품목을 못 정한
  폴더를 그냥 `bigdata` 로 밀어 버린다.
- 폴더가 어느 책인지는 **과목명**으로 판단한다(패널에 표시). 폴더 이름은 근거가 못 된다.
- 표시 이름은 이 앱 안에서만 쓰는 값이라 `[이름·품목]` 에서 자유롭게 바꿔도 된다.

**전환하면 같이 바뀌는 것** — 이걸 빼먹으면 조용히 엉뚱한 책을 건드린다.

| 대상 | 어떻게 |
|---|---|
| 모든 경로 | `paths.book_dir()` 이 상수가 아니라 활성 폴더를 읽는다 |
| `/book` 정적 마운트 | `app.rebind_book()` 이 `StaticFiles.directory` + `all_directories` 를 갈아 끼운다 |
| 영상 렌더 | `runner._args()` 가 `--book paths.book_dir()` 을 넘긴다 |
| 발행 빌드 | `buildcheck` 가 `--book paths.book_dir() --pd require_pd()` 를 넘긴다 |
| 회차 목록 | `paths.round_codes()` 가 `_rounds/mNN.json` 을 센다 — 상수 아님 |
| 기대 숫자 | `buildcheck.expected()` 가 회차·문항·과목 수를 폴더에서 읽는다 |
| 단계별 개수 | `book_routes._count_files()` 가 활성 폴더에서 센다 |
| 문항 색인 캐시 | `index.invalidate()` |
| 셸 칩·진행률 | `xam:book-changed` 이벤트로 `store.js` 캐시까지 버린다 |

> ★ `/book` 마운트는 부팅 시점 경로에 묶인다. 안 갈아 끼우면 폴더는 바뀌는데 mp4·이미지·PDF
> 가 옛 폴더에서 나온다. 그리고 `--pd` 를 상수로 넘기면 **다른 품목의 문제은행을 덮어쓴다** —
> `pr_key` 가 겹치고 `pr_id` 는 보존되므로 되돌릴 수 없다.

## 설정 (`.env`)

`.env` 의 `XAM_BOOK` 은 **첫 실행 기본값**이다. 그 뒤로는 작업 폴더 화면에서 고른 폴더를 쓴다.

| 키 | 기본값 | 설명 |
|---|---|---|
| `XAM_BOOK` | `D:\00work\ocr-output-260723-sqld` | 산물 트리 (첫 실행 기본값) |
| `XAM_AXEXAM` | (비움 = 저장소 안 `axexam/`) | 웹 저장소. 슬라이드 색 tokens.css 도 여기서 |
| `XAM_CHAT_MODEL` | (비움 = CLI 기본) | 오른쪽 채팅의 모델 |
| `CLAUDE_CLI` | (비움 = 자동) | claude.exe 경로. npm 의 claude.cmd 는 SDK 가 거부한다 |
| `XAM_PD` | `bigdata` | `ex_product.pd_id` · URL 의 `?pd=` |
| `XAM_PORT` | `8871` | v2. 구버전 8870 과 동시 가동 |

## 알아 둘 것

- **렌더는 언제나 1개만.** chodangi 의 `munje/chNN` 스크래치가 `exist_ok=True` 라서 같은
  cid 두 프로세스가 서로의 `images/`·`clips/` 를 덮어쓴다. 게다가 Chromium·TTS·ffmpeg 가
  자원을 다 쓴다. 서버가 `threading.Lock` 비차단 획득 + 409 로 막는다.
- **`render.bat` 은 쓰지 않는다.** `chcp`·`pause`·드래그드롭 분기가 방해되고 BOOK 경로가
  하드코딩돼 있다. `make_bundle_video.py` 를 직접 부르며 `--book` 을 명시한다.
- **자식 프로세스에 `PYTHONIOENCODING=utf-8` 필수.** chodangi 의 로그 전문이 한국어라
  cp949 콘솔에서 죽는다.
- **`01/*.md` 는 CRLF, `02/*.md` 는 LF.** 우리는 `02/` 만 쓰지만 `01/` 을 파싱할 때 걸린다.
- **`pr_hash` 에 메타가 없다.** `sj_name`/`sj_no`/`verified`/`needs_review` 는 해시에서
  빠져 있다. 과목 매핑만 고치고 재빌드하면 임포트가 `변경없음` 을 찍고 DB 에 도달하지
  않는다. 강제 플래그가 없으므로 **첫 임포트 전에** 과목을 확실히 맞춰야 한다.
- **`pr_key` 형식은 절대 바꾸지 않는다.** `bundle + '#' + number` = `m01-1#7`.
  바뀌면 `pr_id` 가 갈려서 회원 오답노트·정답률 집계가 통째로 끊긴다.
- **mp4 Range 는 직접 구현하지 않았다.** starlette 의 `FileResponse` 가 206/416/
  `Accept-Ranges` 를 이미 낸다. `fastapi>=0.115` 를 못박아 뒀다.
