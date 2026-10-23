/* 화면 ③ 발행 — axexam 절차를 순서대로 강제한다
 *
 * 이 화면은 '버튼 하나' 가 아니다. 실수하면 되돌릴 수 없는 절차가 둘 있다.
 *   1) build_check.py 를 --book/--pd 없이 부르면 라이브 SQLD 를 덮어쓴다.
 *      pr_key 가 겹치고 pr_id 는 보존되므로 회원 오답노트 밑에 엉뚱한 문제가 앉는다.
 *   2) 임포트는 서버에 드라이런도 트랜잭션도 없다.
 * 그래서 카드 5장으로 순서를 못박고, 실행할 명령을 그대로 보여준다.
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, fmtBytes } from "./util.js";
import { pollJob, fireJobChanged, getPref, setPref } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { donut, stackedBar } from "./charts.js";
import { actionBtn } from "./panel.js";

const P = { pre: null, env: null, problems: null, ftp: null, checklist: null,
            ytmap: null, polling: false };

/* ★ 발행은 **2단계**다 (2026-08-25 운영 결정).
 *
 *     #/publish/problems   1차 «문제집»  — 문항만 본다. 영상을 기다리지 않는다.
 *     #/publish/video      2차 «해설영상» — 렌더·유튜브까지 끝난 뒤
 *     #/publish            (옛 주소) = 2차와 같다
 *
 *   화면은 하나다. 게이트의 **범위**만 다르다 — 범위별로 다른 화면을 만들면
 *   1차에서 통과한 것이 2차에서 다른 이유로 막힌다(`validate.SCOPES` 머리말과 같은 규약).
 */
function scopeFromHash() {
  return /#\/publish\/problems/.test(location.hash) ? "problems" : "all";
}

export const meta = {
  title: () => (scopeFromHash() === "problems"
    ? "etest 발행 — 문제집 (1차)" : "해설영상 발행 (2차)"),
  subtitle: () => (scopeFromHash() === "problems"
    ? "문항만 먼저 내보냅니다. 영상·요약노트는 2차에서 봅니다."
    : "슬라이드·렌더·유튜브까지 끝난 뒤 — 영상 링크를 붙여 마저 내보냅니다."),
  actions: () => [
    actionBtn("사전점검 다시", () => refresh(), { iconName: "refresh" }),
    actionBtn("06/ 폴더 열기", () => openOut(), { iconName: "folder" }),
  ],
};

export async function mount(root, ctx) {
  /* ★ 영상 매핑은 **2차에만** 둔다(2026-08-26 지시).
   *
   *   1차(문제집)를 낼 때는 아직 영상이 없다 — mp4 도 유튜브 링크도 없는 단계다.
   *   그런데 카드가 1차 화면에 있으니 「링크 0 / 100」 이 붉게 떠서, 지금 해야 할
   *   일처럼 보이고 실제로 그래서 1차를 미루셨다. 발행이 2단계인 이유가 바로
   *   영상을 기다리지 않으려는 것인데 화면이 반대로 말하고 있었다.
   *
   *   번호는 그 화면에 **실제로 있는 카드**로만 매긴다 — 1차에서 ②를 건너뛰고
   *   ③으로 가면 사람이 빠진 단계를 찾는다.
   */
  const video = scopeFromHash() !== "problems";
  const cards = [
    ["사전점검", "pb-pre"],
    ...(video ? [["영상 매핑 — 링크를 여기 넣습니다", "pb-ytmap"]] : []),
    ["빌드 — axexam scripts/build_check.py", "pb-build"],
    ["problems.json 검증 (임포트 드라이런)", "pb-problems"],
    ["웹 소스 올리기 — PHP·화면이 바뀔 때만", "pb-ftp"],
    ["전체 순서 — 0.x 는 앱에서, 1번부터는 서버에서", "pb-server"],
  ];
  const NO = "①②③④⑤⑥⑦";
  const page = el("div", "page");
  page.innerHTML = cards.map(([t, id], i) =>
    `<div class="card"><div class="card-title">${NO[i]} ${escapeHtml(t)}</div>`
    + `<div id="${id}"></div></div>`).join("");
  root.appendChild(page);
  hydrateIcons(page);
  await refresh();
}

async function refresh() {
  const set = (id, msg) => { const b = $(id); if (b) b.innerHTML = `<div class="empty">${msg}</div>`; };

  /* ★ 도착하는 대로 그린다 — 전부 기다리지 않는다.
   *
   *   사전점검은 720문항을 훑어 6초가 걸리고 나머지는 0.1초 안이다. 예전에는
   *   Promise.allSettled 로 여섯 개를 묶어 기다린 뒤 한 번에 그려서, **6초 동안
   *   화면이 통째로 비어 있었다.** 업로드 카드(0.0초)까지 사전점검을 기다린 것이다.
   *   빈 화면은 "고장" 처럼 보이고, 실제로 그렇게 오해했다.
   */
  const one = (url, key, render, msg) => {
    if (msg) set(msg[0], msg[1]);
    return api(url)
      .then((v) => { P[key] = v; })
      .catch((e) => { P[key] = { error: e.message }; })
      .then(() => { try { render(); } catch (err) { console.error(err); } });
  };

  await Promise.all([
    one("/api/publish/env", "env", renderBuild, ["#pb-build", "빌드 환경 확인 중…"]),
    // 1차에는 매핑 카드가 없다 — 부르지도 않는다.
    ...($("#pb-ytmap")
      ? [one("/api/publish/ytmap", "ytmap", renderYtmap, ["#pb-ytmap", "매핑 확인 중…"])]
      : []),
    one("/api/publish/problems", "problems", renderProblems,
        ["#pb-problems", "problems.json 확인 중…"]),
    // 체크리스트도 발행 단계마다 다르다 — 1차에 「영상 올리기」 가 뜨면 안 된다.
    one(`/api/publish/checklist?scope=${scopeFromHash()}`, "checklist", renderServer, null),
    // 업로드 카드는 사전점검과 무관하다 — 먼저 뜬다.
    Promise.resolve().then(() => renderStage()),
    // 가장 느린 것을 마지막에 둔다(순서는 무관하지만 읽는 사람에게 의도가 보인다).
    one(`/api/publish/preflight?scope=${scopeFromHash()}`, "pre", renderPre,
        ["#pb-pre", "점검 중…"]),
  ]);
}

/* ── ① 사전점검 ────────────────────────────────────── */
function renderPre() {
  const box = $("#pb-pre");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.pre;
  if (d.error) {
    box.appendChild(el("div", "empty", d.error));
    return;
  }

  const head = el("div", "qz-head");
  const total = d.groups.reduce((a, g) => a + g.checks.length, 0);
  const passed = d.groups.reduce((a, g) => a + g.checks.filter((c) => c.ok).length, 0);
  const st = el("div", "qz-head-stat");
  st.appendChild(donut(Math.round((passed / Math.max(1, total)) * 100), { label: "통과", size: 76 }));
  const t = el("div");
  t.appendChild(el("div", "stat-value", `${passed} / ${total}`));
  t.appendChild(el("div", "muted",
    d.errors ? `오류 ${d.errors}건 · 경고 ${d.warnings}건` : `경고 ${d.warnings}건`));
  st.appendChild(t);
  head.appendChild(st);

  const bars = el("div", "qz-head-bars");
  bars.appendChild(stackedBar([
    { label: "통과", value: passed, seq: 4 },
    { label: "경고", value: d.warnings, seq: 2 },
    { label: "오류", value: d.errors, seq: 3 },
  ]));
  const c = d.counts;
  bars.appendChild(el("div", "muted",
    `문항 ${c.questions} (검수 ${c.reviewed}) · 회차 ${c.rounds} · 과목 ${c.subjects} · `
    + `그림 ${c.figures} · 영상 ${c.videos} · pd=${d.pd}`));
  head.appendChild(bars);
  box.appendChild(head);

  /* ★ 범위 밖 그룹은 **막지 않는다** — 세지 않으므로 오류·경고 수에 안 들어간다.
   *   그런데 화면은 그것을 말해 주지 않아서, 1차인데 「유튜브 ID 전부 입력됨 · 오류」
   *   가 붉게 떠 있었다. 머리글은 「오류 0」 인데 줄은 오류라, 빌드를 눌러도 되는지
   *   사람이 판단할 수 없다(2026-08-26 질문). 미룬 것은 미뤘다고 적는다.
   */
  d.groups.forEach((g) => {
    const out = !!g.out_of_scope;
    const wrap = el("div", "pb-group" + (out ? " pb-later" : ""));
    const title = el("div", "qz-label",
      out ? `${g.label} — 2차에서 봅니다`
          + (g.pending ? ` · 남은 것 ${g.pending}` : " · 준비됨")
          : `${g.label} — 오류 ${g.errors} · 경고 ${g.warnings}`);
    wrap.appendChild(title);
    const list = el("div", "pb-check");
    g.checks.forEach((chk) => {
      // 범위 밖이면 못 지킨 줄도 「나중」 으로 — 지금 막는 것이 아니다.
      const tone = chk.ok ? "ok" : out ? "idle" : chk.level === "error" ? "err" : "warn";
      const row = el("div", "item " + tone);
      row.appendChild(icon(chk.ok ? "check" : out ? "clock" : chk.level === "error" ? "alert" : "bulb", 13));
      const mid = el("div");
      mid.appendChild(el("span", null, chk.label));
      if (chk.detail && !chk.ok) mid.appendChild(el("div", "muted", chk.detail));
      row.appendChild(mid);
      row.appendChild(el("span", "muted",
        chk.ok ? "" : out ? "2차" : chk.level === "error" ? "오류" : "경고"));
      list.appendChild(row);
    });
    wrap.appendChild(list);
    box.appendChild(wrap);
  });
}

/* ── ② 영상 매핑 ────────────────────────────────────
 *
 * 발행에서 손이 가장 많이 가는 칸이다. 번들이 72개라 손으로 쓰면 오타가 난다.
 * 빌더에 `--init-youtube-map` 이 있는데 앱이 노출하지 않아 명령줄을 따로 열어야 했다.
 *
 * ★ `sec` 은 **시작 초**다(영상 길이가 아니다). check.js 가 `&start=` 로 쓴다.
 *   길이를 넣으면 모든 영상이 끝에서 시작한다.
 */
function fmtSec(n) {
  const m = Math.floor((n || 0) / 60);
  return `${m}:${String((n || 0) % 60).padStart(2, "0")}`;
}

/* 붙여넣은 드라이브 주소에서 **폴더 ID** 만 꺼낸다. 못 알아보면 빈 문자열.

 * ★ 세 가지 모양을 다 받는다 — 사람이 어디서 복사해 오는지 정해져 있지 않다:
 *     https://drive.google.com/drive/folders/<ID>?usp=drive_link   주소창
 *     https://drive.google.com/open?id=<ID>                        옛 공유 주소
 *     <ID>                                                         ID 만 복사
 * ★ 파일 주소(`/file/d/<ID>/view`)는 **일부러 받지 않는다.** 그건 폴더가 아니라
 *   영상 한 편이고, 그것을 FOLDER_ID 에 넣으면 스크립트가 "File not found" 로만
 *   죽어서 무엇이 틀렸는지 안 보인다. 빈 값으로 두어 화면이 말하게 한다.
 */
const FOLDER_URL_RE = /(?:\/folders\/|[?&]id=)([A-Za-z0-9_-]{10,})/;

function folderId(s) {
  const t = (s || "").trim();
  if (!t) return "";
  const m = FOLDER_URL_RE.exec(t);
  if (m) return m[1];
  return /^[A-Za-z0-9_-]{10,}$/.test(t) ? t : "";
}


/* 드라이브 폴더에서 (파일명 | 파일ID | 크기) 를 뽑는 앱스 스크립트.
 *
 * ★ 100편의 링크를 손으로 옮길 수는 없다. script.google.com 에 붙여 한 번 돌리면
 *   시트가 생기고, 그것을 TSV 로 내려받아 위 칸에 붙이면 된다.
 * ★ 화면 안에 둔다 — 밖에 적어 두면 품목마다 다시 찾아야 한다(2026-08-26 요청).
 * ★ 개수(EXPECT)와 이름을 **이 품목의 값으로** 채워서 낸다. 상수로 두면 다음 품목에서
 *   조용히 틀린 숫자를 검증하게 된다.
 */
function appsScriptBox(d) {
  const title = (d && d.pd) || "영상";
  const expect = (d && d.bundles) || 0;
  const code = [
    "/** ${TITLE} 폴더의 mp4 를 시트에 (파일명 | 파일ID | 크기) 로 적는다.",
    " *",
    " *  독립 스크립트(script.google.com)에서도, 시트에 붙인 스크립트에서도 돈다 —",
    " *  쓸 시트를 _시트() 가 알아서 고른다.",
    " *  실행: 편집기의 ▶ 실행, 함수는 「링크목록」. 실행 로그에 시트 URL 이 찍힌다.",
    " */",
    "",
    "const FOLDER_ID = '${FOLDER}';",
    "const SHEET_NAME = '링크목록';",
    "const SS_TITLE = '${TITLE} 링크목록';",
    "const EXPECT = ${EXPECT};                  // 이 품목의 번들 수",
    "",
    "",
    "function onOpen() {",
    "  // 시트에 붙인 경우에만 메뉴가 뜬다. 독립 스크립트에선 아무 일도 안 한다.",
    "  try {",
    "    SpreadsheetApp.getUi().createMenu('링크')",
    "      .addItem('링크목록 뽑기', '링크목록').addToUi();",
    "  } catch (e) {}",
    "}",
    "",
    "",
    "function 링크목록() {",
    "  const folder = DriveApp.getFolderById(FOLDER_ID);",
    "",
    "  // 폴더를 '링크가 있는 모든 사용자'로 열어 둔다. 안의 파일이 이 설정을 물려받는다.",
    "  // ★ 로그인 없이 누구나 재생·다운로드할 수 있다는 뜻이다.",
    "  folder.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);",
    "",
    "  const rows = [];",
    "  const it = folder.getFiles();",
    "  while (it.hasNext()) {",
    "    const f = it.next();",
    "    const name = f.getName();",
    "    if (!/\\.mp4$/i.test(name)) continue;   // mp4 만",
    "    rows.push([name, f.getId(), Math.round(f.getSize() / 1048576) + ' MB']);",
    "  }",
    "  rows.sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);",
    "",
    "  // 같은 이름이 둘이면 옛 파일이 안 지워진 것 — 앱에 엉뚱한 ID 가 들어간다.",
    "  const seen = {}, dup = [];",
    "  rows.forEach(r => { if (seen[r[0]]) dup.push(r[0]); seen[r[0]] = 1; });",
    "",
    "  const ss = _시트();",
    "  const sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);",
    "  sh.clear();",
    "  sh.getRange(1, 1, rows.length + 1, 3).setNumberFormat('@');   // ID 가 숫자로 변형되는 것 방지",
    "  sh.getRange(1, 1, 1, 3).setValues([['파일명', '파일ID', '크기']])",
    "    .setFontWeight('bold').setBackground('#eeeeee');",
    "  if (rows.length) sh.getRange(2, 1, rows.length, 3).setValues(rows);",
    "  sh.setFrozenRows(1);",
    "  sh.autoResizeColumns(1, 3);",
    "",
    "  let msg = 'mp4 ' + rows.length + '개 (' + EXPECT + '개여야 합니다)';",
    "  if (rows.length !== EXPECT) {",
    "    msg += '\\n\\n⚠ 개수가 다릅니다. 적으면 업로드가 덜 끝난 것,'",
    "         + ' 많으면 옛 파일이 안 지워진 것입니다.';",
    "  }",
    "  if (dup.length) msg += '\\n\\n⚠ 이름이 겹치는 파일: ' + dup.join(', ');",
    "",
    "  Logger.log(msg);",
    "  Logger.log('시트: ' + ss.getUrl() + '#gid=' + sh.getSheetId());",
    "  try { SpreadsheetApp.getUi().alert(msg); } catch (e) {}",
    "  return msg;",
    "}",
    "",
    "",
    "/** 쓸 스프레드시트를 고른다 — 실행마다 새 시트가 쌓이지 않게 ID 를 기억한다. */",
    "function _시트() {",
    "  const active = SpreadsheetApp.getActiveSpreadsheet();",
    "  if (active) return active;",
    "",
    "  const props = PropertiesService.getScriptProperties();",
    "  const saved = props.getProperty('SHEET_ID');",
    "  if (saved) {",
    "    try { return SpreadsheetApp.openById(saved); } catch (e) {}",
    "  }",
    "  const ss = SpreadsheetApp.create(SS_TITLE);",
    "  props.setProperty('SHEET_ID', ss.getId());",
    "  Logger.log('새 스프레드시트를 만들었습니다 — ' + ss.getUrl());",
    "  return ss;",
    "}",
  ].join(String.fromCharCode(10))
    .split("${TITLE}").join(title)
    .split("${EXPECT}").join(String(expect));
  const det = el("details", "pb-more");
  det.appendChild(el("summary", null,
    `드라이브 링크 ${expect}개 뽑기 — 앱스 스크립트`));
  const wrap = el("div");
  wrap.appendChild(el("div", "field-hint",
    "script.google.com → 새 프로젝트 → 아래를 통째로 붙여넣고 [링크목록] 실행 → "
    + "실행 기록의 주소를 열면 시트 → 파일 → 다운로드 → 탭으로 구분된 값(.tsv) → "
    + "그 파일을 위 「좌표 TXT」 자리에 끌어다 놓으십시오. 첫 실행 때 드라이브 권한을 한 번 묻습니다."));

  /* 폴더 주소를 붙이면 코드의 FOLDER_ID 를 채워서 낸다.
   *
   * ★ 왜. 이 상자에서 사람이 고칠 것은 그 한 줄뿐인데, 그 한 줄 때문에 절차가
   *   「복사 → 붙여넣기 → 그 줄 찾기 → 주소에서 ID 만 잘라 넣기」 가 된다. 잘라내다
   *   `?usp=drive_link` 를 함께 넣으면 스크립트가 폴더를 못 찾는데, 오류는
   *   "File not found" 뿐이라 그게 원인인지 화면에서 보이지 않는다. 자를 일을 없앤다.
   * ★ 품목별로 기억한다. 폴더는 품목마다 다르고 한 폴더를 여러 번 쓴다.
   *   품목은 매핑 파일 이름에서 읽는다(`youtube_map.<pd>.json`) — 서버에 값을
   *   더 달지 않으려고 그렇게 한다. */
  const pd = (/youtube_map\.(.+)\.json$/.exec((d && d.path) || "") || [])[1] || "";
  const PREF = "ytmapFolder" + (pd ? "." + pd : "");

  const fin = el("input");
  fin.type = "text";
  fin.className = "pb-folder";
  fin.placeholder = "드라이브 폴더 주소를 붙여넣으십시오 — "
    + "https://drive.google.com/drive/folders/…";
  fin.value = getPref(PREF, "") || "";
  wrap.appendChild(fin);

  const say = el("div", "field-hint");
  wrap.appendChild(say);

  const pre = el("pre", "pb-cmd");
  wrap.appendChild(pre);

  function paint() {
    const raw = fin.value.trim();
    const id = folderId(raw);
    pre.textContent = code.split("${FOLDER}").join(id || "여기에_폴더_ID");
    if (!raw) {
      say.className = "field-hint";
      say.textContent = "주소를 붙이면 아래 코드의 FOLDER_ID 가 채워집니다. "
        + "비워 두면 그 한 줄만 직접 고치십시오.";
    } else if (id) {
      say.className = "field-hint";
      say.textContent = `폴더 ID ${id} — 아래 코드에 넣었습니다. 그대로 복사하십시오.`;
    } else {
      say.className = "field-hint bad";
      say.textContent = "이 주소에서 폴더 ID 를 찾지 못했습니다 — 드라이브에서 폴더를 연 "
        + "주소창의 drive.google.com/drive/folders/… 를 통째로 붙여넣으십시오.";
    }
    setPref(PREF, raw);
  }
  fin.addEventListener("input", paint);
  paint();

  const b = el("button", "btn sm", "코드 복사");
  b.type = "button";
  b.addEventListener("click", async () => {
    // 화면에 보이는 것을 그대로 복사한다 — `code` 를 쓰면 자리표시자가 따라간다.
    try { await navigator.clipboard.writeText(pre.textContent); toast("복사했습니다."); }
    catch (e) { toast("복사하지 못했습니다 — 직접 긁어 가세요.", "err"); }
  });
  wrap.appendChild(b);
  det.appendChild(wrap);
  return det;
}


function renderYtmap() {
  const box = $("#pb-ytmap");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.ytmap;
  if (!d || d.error) {
    box.appendChild(el("div", "empty", "매핑 상태를 읽지 못했습니다: " + (d?.error || "")));
    return;
  }

  const chips = el("div", "vd-env");
  chips.appendChild(el("span", "status-chip " + (d.exists ? "ok" : "bad"),
    d.exists ? `매핑 파일 있음` : "매핑 파일 없음"));
  chips.appendChild(el("span", "status-chip " + (d.empty ? "bad" : "ok"),
    `링크 ${d.filled} / ${d.bundles}`));
  if (d.theory_total) {
    chips.appendChild(el("span",
      "status-chip " + (d.theory_filled < d.theory_total ? "bad" : "ok"),
      `이론 ${d.theory_filled} / ${d.theory_total}`));
  }
  if (d.provider) chips.appendChild(el("span", "status-chip", `provider=${d.provider}`));
  const leaky = (d.items || []).filter((i) => i.leaky && i.id);
  if (leaky.length) {
    chips.appendChild(el("span", "status-chip bad", `공개 유출 위험 ${leaky.length}개`));
  }
  box.appendChild(chips);

  if (leaky.length) {
    const w = el("div", "qz-warn err");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null,
      `${leaky.slice(0, 6).map((i) => i.bundle).join(", ")} — provider 가 drive/link/file 인데 `
      + "min_level 이 1 입니다. 링크가 videos.js(정적 파일)에 구워져 누구나 내려받습니다. "
      + "링크 자체가 접근 권한이라 그게 곧 유출입니다 — min_level 을 5 로 두세요."));
    box.appendChild(w);
  }

  const acts = el("div", "qz-foot");
  const mk = el("button", "btn " + (d.exists ? "" : "primary"),
    d.exists ? "빠진 번들 채우기" : "영상 매핑 만들기");
  mk.type = "button";
  mk.addEventListener("click", () => syncYtmap());
  acts.appendChild(mk);
  if (d.exists) {
    const open = el("button", "btn", "매핑 파일 열기");
    open.type = "button";
    open.addEventListener("click", async () => {
      try { await api("/api/publish/ytmap/open", { method: "POST" }); }
      catch (e) { toast(e.message, "err"); }
    });
    acts.appendChild(open);
  }
  /* ★ 2차의 첫 일은 「영상 100편을 올려 둔다」 인데, mp4 가 05/<번들>/draft/ 로
   *   100곳에 흩어져 있다. 탐색기 검색으로 긁어모으라고 적어 두었지만 드래그가
   *   실수하기 쉽고 세기도 어렵다 — 한 폴더로 모아 준다.
   * ★ 복사가 아니라 **하드링크**다. 100편이면 2GB 인데 자리를 먹지 않는다. */
  const gat = el("button", "btn primary", "영상 한 폴더로 모으기");
  gat.type = "button";
  gat.title = "05/<번들>/draft/*.static.mp4 를 <작업폴더>/_videos/ 로 모읍니다 "
    + "(하드링크 — 자리를 먹지 않습니다). 그 폴더째 드라이브에 올리시면 됩니다.";
  gat.addEventListener("click", async () => {
    gat.disabled = true;
    try {
      const r = await api("/api/publish/gather-videos", { method: "POST" });
      toast(`${r.total - r.missing}편을 모았습니다 `
        + `(링크 ${r.linked} · 복사 ${r.copied}`
        + (r.missing ? ` · 없음 ${r.missing}` : "") + `) — ${r.dir}`,
        r.missing ? "warn" : "ok");
      await api("/api/publish/open", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ which: "videos" }),
      }).catch(() => {});
    } catch (e) {
      toast("모으지 못했습니다: " + e.message, "err");
    } finally { gat.disabled = false; }
  });
  acts.appendChild(gat);
  acts.appendChild(el("span", "field-hint qz-foot-hint",
    "공유 URL 을 그대로 id 에 붙여넣어도 됩니다 — 빌더가 ID 만 뽑습니다. "
    + "이미 넣은 링크는 다시 눌러도 지워지지 않습니다."));
  box.appendChild(acts);
  if (d.path) box.appendChild(el("pre", "pb-cmd", d.path));
  box.appendChild(appsScriptBox(d));

  if (d.extra && d.extra.length) {
    box.appendChild(el("div", "field-hint",
      `매핑에만 있는 번들 ${d.extra.length}개(05/ 에 없음): ${d.extra.slice(0, 8).join(", ")} — `
      + "예전 회차라면 남겨도 되고, 지워도 빌드에 영향이 없습니다."));
  }

  // 이론 강의 표 — 과목 수만큼(보통 2~4줄)이라 번들 표보다 위에 둔다.
  // 회차 영상과 달리 레벨 제한이 없다. 링크는 공개 theory.js 에 실린다.
  if (d.theory_total) {
    const th = el("table", "tbl");
    th.innerHTML = `<thead><tr><th>과목</th><th>요약노트</th><th>버튼 이름</th>
      <th>링크</th></tr></thead>`;
    const thb = el("tbody");
    (d.theory || []).forEach((t) => {
      const tr = el("tr", t.id ? "" : "state-todo");
      tr.appendChild(el("td", null, `${t.sub}과목 · ${t.name || ""}`));
      tr.appendChild(el("td", "muted", `summary_${t.key}.html`));
      tr.appendChild(el("td", "muted", t.label || ""));
      const link = el("td");
      link.appendChild(el("span", "status-chip " + (t.id ? "ok" : ""),
        t.id ? (t.provider === "drive" ? "드라이브" : t.provider) : "비어 있음"));
      tr.appendChild(link);
      thb.appendChild(tr);
    });
    th.appendChild(thb);
    const thw = el("div", "tbl-wrap");
    thw.appendChild(th);
    box.appendChild(el("div", "field-hint", "이론 탭 — 과목별 강의 1개씩."));
    box.appendChild(thw);
    box.appendChild(el("div", "field-hint",
      "★ 이론 링크에는 min_level 이 없습니다 — 공개 theory.js 에 실려 누구나 받습니다. "
      + "회차 영상처럼 레벨로 가릴 통로(api/videos.php)가 이론 탭에는 없습니다."));
  }

  // 번들 표 — 링크 유무와 문항 시작점을 함께 본다.
  const tbl = el("table", "tbl");
  tbl.innerHTML = `<thead><tr><th>번들</th><th>문항</th><th>길이</th>
    <th>링크</th><th>시작</th><th>레벨</th><th>문항 시작점</th></tr></thead>`;
  const tb = el("tbody");
  (d.items || []).forEach((i) => {
    const tr = el("tr", i.id ? "" : "state-todo");
    tr.appendChild(el("td", null, i.bundle));
    tr.appendChild(el("td", "muted", i.label || ""));
    tr.appendChild(el("td", "muted", i.length ? fmtSec(i.length) : "—"));
    const link = el("td");
    link.appendChild(el("span", "status-chip " + (i.id ? "ok" : ""),
      i.id ? (i.provider === "drive" ? "드라이브" : i.provider) : "비어 있음"));
    tr.appendChild(link);
    tr.appendChild(el("td", "muted", i.sec ? fmtSec(i.sec) : "처음"));
    tr.appendChild(el("td", "muted", i.min_level ? String(i.min_level) : "공개"));
    // 문항별 시작 초 — 강사가 "N번은 몇 분" 을 바로 볼 수 있게 펼쳐 둔다.
    const st = el("td", "muted");
    st.textContent = (i.starts || []).map((s) => `${s.number}번 ${fmtSec(s.startSec)}`).join(" · ");
    tr.appendChild(st);
    tb.appendChild(tr);
  });
  tbl.appendChild(tb);
  const wrap = el("div", "tbl-wrap");
  wrap.appendChild(tbl);
  box.appendChild(wrap);

  /* 붙여넣기·드롭 — 번들이 72개(SQLD 100개)라 목록을 옮겨 붙이다 사고가 난다.
   *
   * ★ 넣기 전에 판정을 보여 준다. 예전에는 누르는 즉시 파일이 바뀌었고 백업도 없어서
   *   잘못 넣으면 되돌릴 방법이 없었다. 지금은 preview → 표 → 반입 → (되돌리기) 다.
   *   같은 ID 가 두 자리에 붙었으면 서버가 dup 로 잡고 여기서 [반입] 을 막는다.
   */
  const tEmpty = (d.theory_total || 0) - (d.theory_filled || 0);
  const pd = el("details", "pb-paste");
  pd.open = d.empty > 0 || tEmpty > 0;
  pd.appendChild(el("summary", null, `링크 넣기 (${d.empty + tEmpty}개 비어 있음)`));
  pd.appendChild(el("div", "field-hint",
    "번들코드와 링크가 같은 줄에 있으면 됩니다 — 파일명·URL·따옴표 섞여도 잡습니다. "
    + "예: m01-1.static.mp4  https://drive.google.com/file/d/1AbC.../view"));
  if (d.theory_total) {
    pd.appendChild(el("div", "field-hint",
      "이론 강의도 같은 칸에 넣습니다. 렌더 파일명이 그대로 통하고 「2과목」·「t3」 도 됩니다. "
      + "예: 1summary-planning.mp4  https://drive.google.com/file/d/1AbC.../view"));
  }

  const ta = el("textarea");
  ta.rows = 8;
  ta.placeholder = "m01-1.static.mp4  https://drive.google.com/file/d/1AbC.../view";
  ta.style.width = "100%";

  // 드롭 영역 — TXT 를 떨어뜨리거나 눌러 고른다. 둘 다 같은 통로다(브라우저가 읽어
  // 텍스트로 보낸다). 그래서 서버에 multipart 를 붙일 필요가 없다.
  const drop = el("div", "pb-drop",
    "좌표 TXT 를 여기에 끌어다 놓거나, 눌러서 고르십시오");
  const fi = el("input");
  fi.type = "file";
  fi.accept = ".txt,.csv,.tsv,.md,text/plain";
  fi.multiple = true;
  fi.hidden = true;

  const pv = el("div", "pb-plan");
  let plan = null;

  const btnPv = el("button", "btn", "판정 보기");
  btnPv.type = "button";
  const btnGo = el("button", "btn primary", "이대로 반입");
  btnGo.type = "button";
  btnGo.disabled = true;
  const btnUndo = el("button", "btn", "되돌리기");
  btnUndo.type = "button";

  async function preview() {
    const text = ta.value.trim();
    pv.innerHTML = "";
    plan = null;
    btnGo.disabled = true;
    if (!text) return;
    try {
      plan = await api("/api/publish/ytmap/preview", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
    } catch (e) {
      pv.appendChild(el("div", "qz-warn err", e.message));
      return;
    }
    renderPlan();
  }

  function renderPlan() {
    pv.innerHTML = "";
    const c = plan.counts || {};
    const dupIds = (plan.dup && plan.dup.ids) || [];
    const dupTargets = (plan.dup && plan.dup.targets) || [];
    const rows = plan.rows || [];

    const bits = [];
    if (c.new) bits.push(`새로 채움 ${c.new}`);
    if (c.replace) bits.push(`갈아끼움 ${c.replace}`);
    if (c.same) bits.push(`이미 같음 ${c.same}`);
    pv.appendChild(el("div", "qz-label",
      bits.join(" · ") || "알아볼 수 있는 줄이 없습니다."));

    // ★ 여기가 이 화면의 이유다 — 같은 것이 두 자리에 붙으면 파일을 봐도 어느 쪽이
    //   이겼는지 알 수 없다. 그래서 경고가 아니라 차단이다.
    if (dupIds.length || dupTargets.length) {
      const lines = dupIds.map((x) =>
        `같은 링크가 ${x.targets.join(" · ")} 에 붙었습니다 (${x.id.slice(0, 18)}…)`)
        .concat(dupTargets.map((x) =>
          `${x.target} 에 서로 다른 링크가 ${x.ids.length}개 왔습니다`));
      pv.appendChild(el("div", "qz-warn err",
        "목록이 어긋났습니다 — 반입할 수 없습니다.\n" + lines.join("\n")));
    }
    if (plan.unknown && plan.unknown.length) {
      pv.appendChild(el("div", "qz-warn",
        `05/ 에 없는 번들 ${plan.unknown.length}개는 건너뜁니다: `
        + plan.unknown.slice(0, 8).join(", ")));
    }
    if (plan.unknown_theory && plan.unknown_theory.length) {
      pv.appendChild(el("div", "qz-warn",
        `03/ 에 없는 과목 ${plan.unknown_theory.join("·")} 는 건너뜁니다.`));
    }
    if (plan.skipped && plan.skipped.length) {
      pv.appendChild(el("div", "field-hint",
        `알아보지 못한 줄 ${plan.skipped_total}개 — 예: ${plan.skipped[0]}`));
    }

    if (rows.length) {
      const t = el("table", "tbl");
      t.innerHTML = `<thead><tr><th>자리</th><th>이름</th><th>지금</th>
        <th>새로</th><th>판정</th></tr></thead>`;
      const tb = el("tbody");
      const VER = { new: ["새로 채움", "ok"], replace: ["갈아끼움", "warn"],
                    same: ["이미 같음", ""] };
      rows.forEach((r) => {
        const tr = el("tr", r.verdict === "same" ? "state-todo" : "");
        tr.appendChild(el("td", null, r.kind === "theory"
          ? `${r.target}과목` : r.target));
        tr.appendChild(el("td", "muted", r.label || ""));
        tr.appendChild(el("td", "muted", r.now_id
          ? r.now_id.slice(0, 18) + "…" : "비어 있음"));
        tr.appendChild(el("td", "muted", r.new_id.slice(0, 18) + "…"));
        const v = VER[r.verdict] || ["", ""];
        const cell = el("td");
        cell.appendChild(el("span", "status-chip " + v[1], v[0]));
        tr.appendChild(cell);
        tb.appendChild(tr);
      });
      t.appendChild(tb);
      const w = el("div", "tbl-wrap");
      w.appendChild(t);
      pv.appendChild(w);
    }

    btnGo.disabled = !rows.length || dupIds.length > 0 || dupTargets.length > 0;
  }

  async function addFiles(list) {
    const parts = [];
    for (const f of list || []) parts.push(await f.text());
    // ★ 같은 파일을 다시 고를 수 있게 반드시 비운다.
    fi.value = "";
    if (!parts.length) return;
    const cur = ta.value.replace(/\s+$/, "");
    ta.value = (cur ? cur + "\n" : "") + parts.join("\n");
    await preview();
  }

  drop.addEventListener("click", () => fi.click());
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("over");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", async (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    await addFiles(e.dataTransfer && e.dataTransfer.files);
  });
  fi.addEventListener("change", (e) => addFiles(e.target.files));
  btnPv.addEventListener("click", () => preview());

  btnGo.addEventListener("click", async () => {
    const text = ta.value.trim();
    if (!text) { toast("반입할 내용이 없습니다."); return; }
    try {
      const r = await api("/api/publish/ytmap/paste", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const nt = r.matched_theory?.length || 0;
      const bits = [`${r.matched.length}개 채움`];
      if (nt) bits.push(`이론 ${nt}개`);
      if (r.overwrote?.length) bits.push(`${r.overwrote.length}개 교체`);
      if (r.unknown?.length) bits.push(`모르는 번들 ${r.unknown.length}개`);
      if (r.unknown_theory?.length) {
        bits.push(`03/ 에 없는 과목 ${r.unknown_theory.join("·")}`);
      }
      if (r.skipped?.length) bits.push(`건너뜀 ${r.skipped.length}줄`);
      if (r.backup) bits.push("되돌릴 수 있습니다");
      toast(bits.join(" · "), (r.matched.length || nt) ? "" : "err");
      ta.value = "";
      pv.innerHTML = "";
      plan = null;
      btnGo.disabled = true;
      await refresh();
    } catch (e) { toast("채우지 못했습니다: " + e.message, "err"); }
  });

  btnUndo.addEventListener("click", async () => {
    const ok = await confirmModal({
      title: "직전 반입을 되돌릴까요?",
      body: `<div style="text-align:left;line-height:1.7">
        매핑 파일을 <code>.bak</code> 와 <b>맞바꿉니다</b> — 한 번 더 누르면 다시
        돌아옵니다.<br>
        <span class="dim">되돌린 뒤에는 빌드를 다시 해야 서버에 반영됩니다.</span></div>`,
      ok: "되돌리기", cancel: "그대로",
    });
    if (!ok) return;
    try {
      await api("/api/publish/ytmap/restore", { method: "POST" });
      toast("되돌렸습니다.");
      await refresh();
    } catch (e) { toast("되돌리지 못했습니다: " + e.message, "err"); }
  });

  pd.appendChild(ta);
  pd.appendChild(drop);
  pd.appendChild(fi);
  const pfoot = el("div", "qz-foot");
  pfoot.appendChild(btnPv);
  pfoot.appendChild(btnGo);
  pfoot.appendChild(btnUndo);
  pfoot.appendChild(el("span", "field-hint qz-foot-hint",
    "[판정 보기] 는 파일을 고치지 않습니다. 무엇이 갈아끼워지는지 확인한 뒤 "
    + "[이대로 반입] 을 누르십시오."));
  pd.appendChild(pfoot);
  pd.appendChild(pv);
  box.appendChild(pd);

  box.appendChild(el("div", "field-hint",
    "★ 문항 시작점은 review.json 에서 계산한 값입니다(영상 시간축 기준). "
    + "지금 웹은 번들 하나에 시작점 하나(sec)만 씁니다 — 문항별로 뛰려면 "
    + "웹·빌더 스키마를 늘려야 합니다(추후)."));
}

async function syncYtmap() {
  try {
    const r = await api("/api/publish/ytmap/sync", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: P.ytmap?.provider || "drive" }),
    });
    const bits = [];
    if (r.added?.length) bits.push(`번들 ${r.added.length}개`);
    if (r.added_theory?.length) bits.push(`이론 ${r.added_theory.length}과목`);
    toast(bits.length ? bits.join(" · ") + " 추가했습니다." : "이미 다 있습니다.");
    await refresh();
  } catch (e) {
    toast("매핑을 만들지 못했습니다: " + e.message, "err");
  }
}

/* ── ③ 빌드 ────────────────────────────────────────── */
function renderBuild() {
  const box = $("#pb-build");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const e = P.env;
  if (!e) { box.appendChild(el("div", "empty", "빌드 환경을 확인할 수 없습니다.")); return; }

  const chips = el("div", "vd-env");
  const chip = (ok, text, title) => {
    const c = el("span", "status-chip " + (ok ? "ok" : "bad"));
    c.appendChild(icon(ok ? "check" : "alert", 13));
    c.appendChild(el("span", null, text));
    if (title) c.title = title;
    return c;
  };
  chips.appendChild(chip(e.cloned, "axexam 클론됨", e.script));
  // ★ 이 배지는 '없어도 정상' 이다. 경고(빨강)로 두면 매번 뭔가 잘못된 것처럼 보인다.
  //
  //   상류 빌더는 `--youtube-map` 플래그가 없고, 대신 `--pd` 로
  //   `data/youtube_map.<pd>.json` 을 스스로 고른다(더 나은 방식이라 그대로 쓴다).
  //   그래서 '미적용' 이 맞는 상태다 — 옆의 youtube_map.<pd>.json 배지가 실제 상태다.
  chips.appendChild(chip(true,
    e.patch_youtube_map ? "--youtube-map 플래그 있음" : "품목별 매핑 (--pd 로 자동 선택)",
    e.patch_youtube_map
      ? "빌더가 그 플래그를 받아 명령에 넣습니다."
      : "상류 빌더는 --pd 로 data/youtube_map.<pd>.json 을 스스로 고릅니다. "
        + "플래그가 없는 것이 정상이며, 품목별로 갈려 SQLD 와 겹치지 않습니다."));
  chips.appendChild(chip(e.youtube_map_exists, `youtube_map.${e.pd}.json`, e.youtube_map));
  box.appendChild(chips);

  if (!e.cloned) {
    const warn = el("div", "qz-warn err");
    warn.appendChild(icon("alert", 15));
    warn.appendChild(el("span", null,
      `axexam 저장소가 없습니다. 다음을 실행하세요:\n`
      + `git clone https://github.com/leedonwoo2827-ship-it/axexam "${e.axexam}"`));
    box.appendChild(warn);
  }

  // ★ 품목 코드가 없으면 명령 자체를 만들지 않는다. 상수로 되돌리면 엉뚱한 품목을 덮어쓴다.
  if (e.pd_ok === false) {
    const warn = el("div", "qz-warn err");
    warn.appendChild(icon("alert", 15));
    warn.appendChild(el("span", null, e.pd_error || "품목 코드(pd)가 정해지지 않았습니다."));
    box.appendChild(warn);
    const go = el("button", "btn sm", "작업 폴더 열기");
    go.type = "button";
    go.addEventListener("click", () => { location.hash = "#/books"; });
    box.appendChild(go);
    return;
  }

  // ★ 실행할 명령을 그대로 보여준다. --book 과 --pd 가 눈에 보여야 한다.
  box.appendChild(el("div", "qz-label", "실행할 명령"));
  const cmd = el("pre", "pb-cmd", e.command);
  box.appendChild(cmd);
  const note = el("div", "field-hint");
  note.innerHTML = "★ <b>--book</b> 과 <b>--pd</b> 는 항상 명시합니다. 둘 다 기본값이 "
    + "SQLD 라서, 하나라도 빠지면 라이브 SQLD 문제은행을 덮어씁니다.";
  box.appendChild(note);

  const acts = el("div", "qz-foot");
  const btn = el("button", "btn primary", "빌드 실행");
  btn.type = "button";
  btn.disabled = !e.cloned;
  btn.addEventListener("click", () => startBuild(false));
  acts.appendChild(btn);
  acts.appendChild(el("span", "field-hint qz-foot-hint",
    `출력: ${e.out}  ·  problems.json: ${e.problems_json}`));
  box.appendChild(acts);

  const prog = el("div");
  prog.id = "pb-build-prog";
  box.appendChild(prog);
  const log = el("pre", "log-pane");
  log.id = "pb-build-log";
  log.hidden = true;
  box.appendChild(log);
}

async function startBuild(force) {
  const e = P.env;
  const ok = await confirmModal({
    title: "이 명령으로 빌드할까요?",
    body: `<pre class="pb-cmd">${escapeHtml(e.command)}</pre>`
      + `<br>품목 <b>${escapeHtml(e.pd)}</b> · BOOK <b>${escapeHtml(e.book)}</b><br><br>`
      + "이 두 값이 맞는지 확인하세요. 잘못된 pd 로 빌드하면 다른 품목의 문제은행을 "
      + "덮어쓰게 되고 되돌릴 수 없습니다.",
    ok: "빌드 실행", cancel: "취소",
  });
  if (!ok) return;

  try {
    const job = await api("/api/publish/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope: scopeFromHash(),
                             force_ignore_warnings: !!force }),
    });
    attachBuild(job.id);
  } catch (err) {
    if (err.status === 409) {
      const again = await confirmModal({
        title: "빌드를 시작하지 않았습니다",
        body: `<pre class="pb-cmd">${escapeHtml(err.message)}</pre>`
          + (err.message.includes("경고")
            ? "<br>경고만 남았다면 확인 후 진행할 수 있습니다."
            : "<br>오류는 우회할 수 없습니다. 먼저 고치세요."),
        ok: err.message.includes("경고") ? "경고 무시하고 진행" : "닫기",
        cancel: err.message.includes("경고") ? "취소" : "",
      });
      if (again && err.message.includes("경고")) return startBuild(true);
    } else {
      toast("빌드를 시작하지 못했습니다: " + err.message, "err");
    }
  }
}

function attachBuild(jobId) {
  const log = $("#pb-build-log");
  log.hidden = false;
  log.textContent = "";
  if (P.polling) return;
  P.polling = true;
  pollJob(jobId, (job) => {
    renderBuildProgress(job);
    const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 24;
    (job.log?.lines || []).forEach((line) => {
      const cls = /ERROR|\[error\]|FAIL/.test(line) ? "lv-err"
        : /\[warn\]|warn /.test(line) ? "lv-warn"
        : /OK  |\[done\]/.test(line) ? "lv-ok" : "";
      log.appendChild(el("span", cls, line + "\n"));
    });
    if (atBottom) log.scrollTop = log.scrollHeight;
  }).then(async (final) => {
    P.polling = false;
    if (final) {
      const bad = final.status === "error";
      toast(bad ? `빌드 종료 — ${final.error || "검증 실패"}` : "빌드를 마쳤습니다.",
        bad ? "err" : "");
    }
    fireJobChanged({ id: jobId });
    await refresh();
  });
}

function renderBuildProgress(job) {
  const box = $("#pb-build-prog");
  if (!box) return;
  box.innerHTML = "";
  const labels = { build: "build_check.py 실행", assert: "리포트 어서션", problems: "problems.json 검증" };
  ["build", "assert", "problems"].forEach((k, i) => {
    const it = (job.items || {})[k] || {};
    const cls = it.status === "done" ? "done" : it.status === "running" ? "on"
      : it.status === "error" ? "err" : "";
    const row = el("div", "pb-step " + cls);
    row.appendChild(el("span", "n", String(i + 1)));
    const mid = el("div");
    mid.appendChild(el("span", null, labels[k]));
    if (it.error) mid.appendChild(el("div", "muted", it.error));
    row.appendChild(mid);
    box.appendChild(row);
  });
  (job.asserts || []).forEach((a) => {
    const row = el("div", "pb-check");
    const item = el("div", "item " + (a.ok ? "ok" : "err"));
    item.appendChild(icon(a.ok ? "check" : "alert", 13));
    const mid = el("div");
    mid.appendChild(el("span", null, a.label));
    if (a.detail && !a.ok) mid.appendChild(el("div", "muted", a.detail));
    item.appendChild(mid);
    item.appendChild(el("span", "muted", a.ok ? "" : "실패"));
    row.appendChild(item);
    box.appendChild(row);
  });
}

/* ── ③ problems.json ──────────────────────────────── */
function renderProblems() {
  const box = $("#pb-problems");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  renderPartial(box);
  const d = P.problems;
  if (!d) { box.appendChild(el("div", "empty", "확인할 수 없습니다.")); return; }

  const chips = el("div", "vd-env");
  const add = (ok, text, title) => {
    const c = el("span", "status-chip " + (ok ? "ok" : "bad"), text);
    if (title) c.title = title;
    chips.appendChild(c);
  };
  if (!d.count) {
    box.appendChild(el("div", "empty",
      d.errors?.[0] || "problems.json 이 아직 없습니다. "
      // 빌드 카드 번호는 발행마다 다르다 — 1차는 ②, 2차는 영상 매핑이 끼어 ③ 이다.
      + `${scopeFromHash() === "problems" ? "②" : "③"} 빌드를 먼저 실행하세요.`));
    return;
  }
  add(d.pd_id === (P.env?.pd), `pd_id = ${d.pd_id}`);
  add(d.count === 240, `문항 ${d.count}`);
  add(d.rounds === 3, `회차 ${d.rounds}`);
  add(d.subjects === 4, `과목 ${d.subjects}`, (d.subject_list || []).join("  "));
  chips.appendChild(el("span", "status-chip", fmtBytes(d.bytes)));
  box.appendChild(chips);

  const list = el("div", "pb-check");
  (d.errors || []).forEach((t) => {
    const row = el("div", "item err");
    row.appendChild(icon("alert", 13));
    row.appendChild(el("div", null, t));
    row.appendChild(el("span", "muted", "오류"));
    list.appendChild(row);
  });
  (d.warnings || []).forEach((t) => {
    const row = el("div", "item warn");
    row.appendChild(icon("bulb", 13));
    row.appendChild(el("div", null, t));
    row.appendChild(el("span", "muted", "경고"));
    list.appendChild(row);
  });
  if (!list.childElementCount) {
    const row = el("div", "item ok");
    row.appendChild(icon("check", 13));
    row.appendChild(el("div", null, "검증을 모두 통과했습니다."));
    row.appendChild(el("span"));
    list.appendChild(row);
  }
  box.appendChild(list);

  const exp = d.expected_report || {};
  const note = el("div", "field-hint");
  note.textContent = `임포트 리포트 기대값 — 신규 ${exp.new} · 갱신 ${exp.updated} · `
    + `변경없음 ${exp.unchanged} · 건너뜀 ${exp.skipped_edited} · 실패 ${exp.failed} · `
    + `회차 ${exp.rounds}행`;
  box.appendChild(note);
}

/* ── ④-b 부분 임포트 ─────────────────────────────────
 *
 * ★ 임포트는 DELETE 를 하지 않는다(problem.php:13) — 기존 행은 UPDATE 만 한다.
 *   그래서 고친 문항만 담아 올려도 나머지는 서버에 그대로 남는다.
 *
 *   용량(714KB → 2.6KB)보다 **확인**이 이득이다. 전체를 올리면 리포트가
 *   "갱신 1 · 변경없음 719" 로 나와서 내가 고친 것이 들어갔는지 알기 어렵다.
 */
async function renderPartial(box) {
  if (!box) return;
  let d = null;
  try { d = await api("/api/publish/partial"); } catch (e) { return; }

  const wrap = el("details", "pb-partial");
  wrap.appendChild(el("summary", null,
    `부분 임포트 — 고친 것만 올리기 (전체 ${d.total}문항 · ${Math.round(d.bytes / 1024)}KB)`));
  wrap.appendChild(el("div", "field-hint",
    "임포트는 없는 문항을 지우지 않습니다 — 고친 회차·번들·문항만 담아 올리면 "
    + "나머지는 서버에 그대로 남습니다. 리포트가 '갱신 N' 만 찍혀 확인이 쉬워집니다."));

  const row = el("div", "qz-foot");
  const sel = el("select");
  Object.entries(d.rounds || {}).forEach(([rd, n]) => {
    const o = el("option", null, `${rd}회 (${n}문항)`);
    o.value = "r:" + rd;
    sel.appendChild(o);
  });
  Object.keys(d.bundles || {}).forEach((b) => {
    const o = el("option", null, `${b} (${d.bundles[b]}문항 · 영상 1편)`);
    o.value = "b:" + b;
    sel.appendChild(o);
  });
  row.appendChild(sel);

  const key = el("input");
  key.placeholder = "또는 문항 키 — m04-2#12 (쉼표로 여러 개)";
  key.style.minWidth = "250px";
  row.appendChild(key);

  const out = el("pre", "pb-cmd");
  out.hidden = true;

  const mk = el("button", "btn", "부분 파일 만들기");
  mk.type = "button";
  mk.addEventListener("click", async () => {
    const body = {};
    const ks = key.value.split(",").map((x) => x.trim()).filter(Boolean);
    if (ks.length) body.keys = ks;
    else if (sel.value.startsWith("r:")) body.rounds = [Number(sel.value.slice(2))];
    else if (sel.value.startsWith("b:")) body.bundles = [sel.value.slice(2)];
    try {
      const r = await api("/api/publish/partial", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      toast(`${r.picked}문항 · ${Math.round(r.bytes / 1024)}KB`);
      out.textContent = r.path + "\n기대 리포트: " + r.expect
        + "\n★ skip_edited 가 0 인지 확인하세요 — 0 이 아니면 그 문항을 전에 웹에서 "
        + "고친 것입니다(problem.php:18). 관리자 화면에서 '원본 복원' 을 누른 뒤 "
        + "다시 임포트해야 로컬 수정이 들어갑니다.";
      out.hidden = false;
    } catch (e) { toast(e.message, "err"); }
  });
  row.appendChild(mk);
  wrap.appendChild(row);
  wrap.appendChild(out);
  box.appendChild(wrap);
}

/* ── ⑤ 업로드 — 폴더 하나로 끝낸다 ────────────────────────────
 *
 * ★ 왜 파일 목록이 아니라 폴더를 만드는가
 *
 *   올릴 것이 로컬 두 곳에서 서버 세 곳으로 간다:
 *     06/              → /www/exam/
 *     axexam/web/exam/ → /www/exam/   (같은 자리에 섞인다)
 *     axexam/web/adm/  → /www/adm/    (/exam/ 밖!)
 *   이 매핑을 머릿속으로 하면서 FileZilla 를 쓰면 반드시 틀리고, **틀려도 업로드는
 *   성공한 것처럼 보인다** — 웹에서 증상이 엉뚱한 얼굴로 나타날 뿐이다.
 *
 *   그래서 앱이 서버와 똑같은 모양의 폴더(`_upload/`)를 만든다. 왼쪽에 그 폴더,
 *   오른쪽에 /www/ 를 놓고 통째로 끌어놓으면 끝. 다 올리면 [지우기].
 */
async function renderStage() {
  const box = $("#pb-ftp");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  let st = null;
  try { st = await api("/api/publish/stage"); } catch (e) { /* 아래에서 처리 */ }

  /* ★ 이 카드는 **문제집 내용물의 자리가 아니다**(2026-08-26 지적).
   *   문항·영상·요약노트·도식은 `06/_올릴것/` 에서 반입 화면(adm/exam_deploy.php)으로
   *   간다. 여기는 그 반입 화면을 **담고 있는 웹 소스 자체**(adm/ theme/ extend/
   *   index.php .htaccess)가 바뀌었을 때만 쓴다. 이름이 「업로드」 라 매번 눌러야
   *   하는 자리로 읽혔다. */
  const head = el("div", "field-hint");
  head.innerHTML = "<b>문제집 내용물은 여기가 아닙니다</b> — 문항·영상·요약노트·도식은 "
    + "<code>06/_올릴것/</code> 에서 <b>반입 화면</b>으로 갑니다.<br>"
    + "이 폴더는 <b>웹 소스(adm · theme · extend · index.php · .htaccess)가 바뀌었을 때만</b> "
    + "씁니다. 폴더 안이 이미 서버와 같은 모양이라, 통째로 <b>/www/</b> 에 올리면 됩니다.";
  box.appendChild(head);

  // ★ 빌드보다 낡았으면 크게 알린다. 파일 수만 보면 그럴듯해서 사람이 못 알아챈다 —
  //   실제로 빌드 10:21 · 폴더 08:58 인 채로 "다 만들어졌다" 로 보였고,
  //   그대로 올리면 새 videos.private.json 이 빠진다.
  if (st?.exists && st.stale) {
    const w = el("div", "qz-warn err");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null, (st.stale_text
      || "빌드가 이 폴더보다 새롭습니다 — 다시 만드세요.")
      + " (웹 소스를 올릴 때만 뜻이 있습니다 — 내용물만 바뀌었으면 그냥 두십시오.)"));
    box.appendChild(w);
  }

  const acts = el("div", "qz-foot");
  const mk = el("button", "btn primary",
    st?.exists ? (st.stale ? "★ 업로드 폴더 다시 만들기 (빌드가 더 새롭습니다)"
                           : "업로드 폴더 다시 만들기")
               : "업로드 폴더 만들기");
  mk.type = "button";
  mk.addEventListener("click", async () => {
    try {
      const r = await api("/api/publish/stage", { method: "POST" });
      toast(`${r.files}개 · ${(r.bytes / 1048576).toFixed(2)}MB — ${r.dir}`);
      await renderStage();
    } catch (e) { toast(e.message, "err"); }
  });
  acts.appendChild(mk);

  if (st?.exists) {
    const open = el("button", "btn", "폴더 열기");
    open.type = "button";
    open.addEventListener("click", async () => {
      try { await api("/api/publish/stage/open", { method: "POST" }); }
      catch (e) { toast(e.message, "err"); }
    });
    acts.appendChild(open);

    const del = el("button", "btn", "다 올렸습니다 — 지우기");
    del.type = "button";
    del.addEventListener("click", async () => {
      if (!(await confirmModal({
        title: "업로드 폴더를 지울까요?",
        body: "서버에 다 올렸다면 지워도 됩니다. 남겨 두면 다음에 무엇이 새것인지 "
          + "헷갈립니다. 언제든 다시 만들 수 있습니다.",
        ok: "지우기", cancel: "취소",
      }))) return;
      try {
        await api("/api/publish/stage/clear", { method: "POST" });
        toast("지웠습니다.");
        await renderStage();
      } catch (e) { toast(e.message, "err"); }
    });
    acts.appendChild(del);
  }
  box.appendChild(acts);

  if (st?.exists) {
    box.appendChild(el("div", "qz-label", "왼쪽 = 이 폴더"));
    box.appendChild(el("pre", "pb-cmd", st.dir));
    box.appendChild(el("div", "qz-label", "오른쪽 = 서버"));
    box.appendChild(el("pre", "pb-cmd", "/www/"));
    box.appendChild(el("div", "muted",
      `${st.files}개 · ${(st.bytes / 1048576).toFixed(2)}MB · 최상위: ${(st.tops || []).join("  ")}`));
  }

  box.appendChild(el("div", "field-hint",
    "올릴 때: 전송 유형 바이너리 · 문자셋 UTF-8 (요약노트 파일명이 한글입니다)."));
  box.appendChild(el("div", "field-hint",
    "★ problems.json 은 이 폴더에 넣지 않았습니다 — 관리자 화면(/adm/exam_import.php)에서 "
    + "올리거나 붙여넣습니다. .htaccess 가 .json 을 403 으로 막아서 FTP 로는 읽히지 않습니다."));
}

/* ── ④ FTP ────────────────────────────────────────── */
function renderFtp() {
  const box = $("#pb-ftp");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.ftp;
  if (d.error) {
    box.appendChild(el("div", "empty", d.error));
    return;
  }
  box.appendChild(el("div", "muted",
    `${d.out}  →  ${d.site}   ·   파일 ${d.totals.files}개 · ${fmtBytes(d.totals.bytes)}`));

  const grouped = {};
  d.upload.forEach((u) => {
    const top = u.path.includes("/") ? u.path.split("/")[0] + "/" : u.path;
    grouped[top] = grouped[top] || { n: 0, bytes: 0 };
    grouped[top].n += 1;
    grouped[top].bytes += u.bytes;
  });
  const tree = el("div", "pb-tree");
  Object.entries(grouped).forEach(([k, v]) => {
    const row = el("label");
    row.appendChild(icon(k.endsWith("/") ? "folder" : "file", 14));
    row.appendChild(el("span", null, k));
    row.appendChild(el("span", "sz", `${v.n}개 · ${fmtBytes(v.bytes)}`));
    tree.appendChild(row);
  });
  box.appendChild(el("div", "qz-label", "올릴 것"));
  box.appendChild(tree);

  if (d.skip.length) {
    box.appendChild(el("div", "qz-label", "올리지 않을 것"));
    const list = el("div", "pb-check");
    d.skip.forEach((s) => {
      const row = el("div", "item warn");
      row.appendChild(icon("alert", 13));
      const mid = el("div");
      mid.appendChild(el("span", null, s.path + (s.count ? ` (${s.count}개)` : "")));
      mid.appendChild(el("div", "muted", s.reason));
      row.appendChild(mid);
      row.appendChild(el("span", "muted", fmtBytes(s.bytes)));
      list.appendChild(row);
    });
    box.appendChild(list);
  }

  const acts = el("div", "qz-foot");
  const open = el("button", "btn primary", "06/ 폴더 열기");
  open.type = "button";
  open.addEventListener("click", openOut);
  acts.appendChild(open);
  acts.appendChild(el("span", "field-hint qz-foot-hint",
    "전송 유형 바이너리 · 동시 전송 2개 이하 · 파일명 인코딩 UTF-8 강제"));
  box.appendChild(acts);
}

async function openOut() {
  try {
    const r = await api("/api/publish/open", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ which: "out" }),
    });
    toast("탐색기에서 열었습니다: " + r.path);
  } catch (e) {
    toast("폴더를 열지 못했습니다: " + e.message, "err");
  }
}

/* ── ⑤ 서버 단계 ──────────────────────────────────── */
/* `where` 문자열 안의 http(s) 주소를 눌러서 열 수 있는 링크로 바꾼다.
 *
 * 정규식으로 URL 조각을 떼어내되, **텍스트는 el() 로만 넣는다** — innerHTML 로 조립하면
 * 경로에 들어 있는 `&`·`<` 가 깨지거나 주입 통로가 된다.
 * URL 끝에 붙은 문장부호(`.` `,` `)`)는 주소가 아니라 글이므로 떼어 되돌린다.
 */
const URL_RE = /https?:\/\/[^\s]+/g;

function linkify(text, cls) {
  const box = el("div", cls || "muted");
  const s = String(text == null ? "" : text);
  let last = 0;
  s.replace(URL_RE, (m, at) => {
    let url = m, tail = "";
    const trim = url.match(/[.,)\]]+$/);
    if (trim) { tail = trim[0]; url = url.slice(0, -tail.length); }
    if (at > last) box.appendChild(document.createTextNode(s.slice(last, at)));
    const a = el("a", "pb-link", url);
    a.href = url;
    a.target = "_blank";
    // 로컬 앱에서 외부 사이트를 여는 링크다 — 참조 정보를 넘기지 않는다.
    a.rel = "noopener noreferrer";
    box.appendChild(a);
    if (tail) box.appendChild(document.createTextNode(tail));
    last = at + m.length;
    return m;
  });
  if (last < s.length) box.appendChild(document.createTextNode(s.slice(last)));
  return box;
}

function renderServer() {
  const box = $("#pb-server");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  //   가드가 없으면 "Cannot set properties of null" 이 콘솔을 덮는다.
  if (!box) return;
  box.innerHTML = "";
  const d = P.checklist;
  if (!d) { box.appendChild(el("div", "empty", "체크리스트를 불러올 수 없습니다.")); return; }

  const note = el("div", "field-hint");
  // ★ 이 카드는 인수인계 문서다 — 처음 보는 사람이 이것만 읽고 할 수 있어야 한다.
  //   그래서 번호를 **실제 하는 순서**로 두고, 0.x(앱) 와 1~(서버) 를 갈라 둔다.
  note.textContent = "묶음 순서대로 하시면 됩니다. 「문제집 세팅」은 보통 첫 발행에만 "
    + "하고, 두 번째부터는 「업로드」만 반복합니다. "
    + "임포트는 1회용 관리자 토큰을 쓰기 때문에 스크립트로 부를 수 없습니다. "
    + "서버에서는 이력을 되읽을 수 없으므로(.htaccess 가 .json 을 403 으로 막습니다) "
    + "여기 체크 기록이 유일한 발행 이력입니다.";
  box.appendChild(note);

  // ★ 묶음이 바뀌면 머리글을 끼운다 — 매번 하는 일과 처음 한 번만 하는 일이
  //   한 줄로 이어져 있으면, 두 번째 발행에서 무엇을 건너뛸지 알 수 없다.
  let section = null;
  d.items.forEach((it, i) => {
    if (it.section && it.section !== section) {
      section = it.section;
      box.appendChild(el("div", "pb-section", it.section_label || ""));
    }
    const st = (d.state || {})[it.key] || {};
    const card = el("div", "pb-step " + (st.done ? "done" : ""));
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = !!st.done;
    cb.addEventListener("change", async () => {
      try {
        const r = await api("/api/publish/checklist", {
          method: "PUT", headers: { "Content-Type": "application/json" },
          // 기록은 품목·단계마다 따로 남는다 — 어느 발행의 기록인지 같이 보낸다.
          body: JSON.stringify({ key: it.key, done: cb.checked,
                                 scope: scopeFromHash() }),
        });
        d.state = r.state;
        card.classList.toggle("done", cb.checked);
        toast(cb.checked ? `완료로 기록했습니다 — ${it.label}` : "기록을 해제했습니다.");
      } catch (e) { toast("기록 실패: " + e.message, "err"); }
    });
    card.appendChild(cb);
    const mid = el("div");
    // ★ 자동 번호를 붙이지 않는다. 라벨이 이미 번호를 들고 있다(0.1 … 1 … 7).
    //   붙이면 "1. 0.1 앱을 띄우고…" 가 되어 어느 쪽이 순서인지 알 수 없다.
    //   번호를 라벨에 둔 이유: 0.x(앱) 와 1~(서버) 를 갈라야 하고, [나중] 항목처럼
    //   번호가 없는 것도 있다 — 위치로 매기는 번호로는 표현할 수 없다.
    mid.appendChild(el("b", null, it.label));
    // ★ `where` 는 대개 관리자 화면 주소다. 텍스트로만 두면 사람이 손으로 옮겨 적거나
    //   주소창에 다시 타이핑한다 — 실제로 그 단계에서 멈췄다. 눌러서 열게 한다.
    //   detail 은 링크로 만들지 않는다. 안에 파일 경로·SQL·★경고가 섞여 있어서
    //   링크가 되면 읽는 순서가 흐트러진다.
    mid.appendChild(linkify(it.where, "pb-where"));
    mid.appendChild(el("div", "muted", it.detail));
    /* ★ 긴 설명은 **접는다.** 단계마다 열 줄씩 적혀 있어 화면이 글로 덮였다 —
     *   품목마다 매번 하는 일이라 좌표와 넣을 값만 있으면 되고, 왜 그런지는 처음
     *   한 번만 읽으면 된다. 지우지는 않는다 — 지우면 다음 사람이 같은 함정에
     *   다시 빠진다(2026-08-26 지시). */
    if (it.more && it.more.trim()) {
      const det = el("details", "pb-more");
      det.appendChild(el("summary", null, "자세히"));
      det.appendChild(el("div", "muted", it.more));
      mid.appendChild(det);
    }
    if (it.sql) {
      const btn = el("button", "btn sm", "SQL 보기");
      btn.type = "button";
      btn.addEventListener("click", () => confirmModal({
        title: it.label,
        body: `<pre class="pb-cmd">${escapeHtml(it.sql)}</pre>`,
        ok: "닫기", cancel: "",
      }));
      mid.appendChild(btn);
    }
    if (st.at) mid.appendChild(el("div", "muted", `기록 ${st.at}`));
    card.appendChild(mid);
    box.appendChild(card);
  });
}
