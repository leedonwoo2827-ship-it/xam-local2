/* OCR 검수 (도구 #1) — 페이지 단위. 초안을 대조·수정해 01/*.md 로 확정한다.
 *
 * ★ 이 앱의 UX 핵심 — 목록은 패널(위층), 작업은 바탕(아래층).
 *     #/ocr             위층 패널: 페이지 목록 (고르는 곳)
 *     #/ocr/:src/:page  아래층 바탕: 그 페이지 작업 (일하는 곳)
 *   패널에서 고르면 패널이 닫히고 바탕이 그 페이지로 열린다.
 *
 * ★ 미저장 텍스트는 전부 바탕에 있다. 패널은 Esc·스크림 클릭으로 닫히므로
 *   편집 화면을 패널에 두면 안 된다.
 *
 * 원본은 260730-ocr/app/static/index.html 이다. 한 화면(헤더+대시보드+검수)을
 * 두 레이어로 갈랐고, 기능은 그대로 옮겼다 — 좌 OCR 원문 / 우 문제 카드 /
 * 스캔 이미지 드래그로 그림 영역 지정 / 자산 토큰 / 미리보기(수식 렌더) /
 * 정답키줄 반영 / 초안 저장 / 확정(MD 저장).
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, stateClass } from "./util.js";
import { getPref, setPref } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const CIRC = ["①", "②", "③", "④", "⑤"];
const DIFFS = ["하", "중", "상"];

const S = {
  overview: null,        // 패널이 쓰는 페이지 목록
  cur: null,             // {src, page}
  draft: null,           // 지금 편집 중인 초안
  dirty: false,
  pendingBox: null,      // 스캔에서 드래그한 [x,y,w,h] (원본 픽셀)
  scanPage: 0,           // 스캔 보기가 지금 **어느 면**을 띄우고 있나
  pendingPage: 0,        // 그 드래그가 어느 면의 좌표인가
  ctx: null,
  showScan: false,
  hideOcr: false,
  zoom: 0.9,
};

export const meta = {
  title: (ctx) => (ctx.panel ? "OCR 검수 · 페이지"
    : `OCR 검수 · ${ctx.args[0] || ""} p.${ctx.args[1] || ""}`),
  subtitle: (ctx) => (ctx.panel
    ? "왼쪽 큰 버튼으로 실행합니다 — [＋ OCR] 이 스캔을 뜨고 [OCR 실행] 이 읽습니다. 여기 [OCR 검수] 는 확정 상태를 검산합니다."
    : "좌 OCR 원문 / 우 문제 카드. 확정하면 01/{회차}-{문항}.md 로 기록됩니다."),
  actions: (ctx) => (ctx.panel
    ? [
      // ★ 툴바에는 **검수만** 둔다. 실행 계열(렌더·판독)은 좌측 상단 **큰 버튼**이다 —
      //   초심자가 툴바의 작은 버튼을 주 동작으로 읽지 못하고, 검수 화면에 실행 버튼이
      //   같이 보이면 무엇을 눌러야 하는지 흐려진다(2026-08-18 지시:
      //   "OCR 검수를 누르면 OCR 실행은 안보여야").
      actionBtn("OCR 검수", () => runVerify(), { iconName: "check" }),
    ]
    : [
      actionBtn("← 페이지 목록", () => S.ctx.navigate("/ocr"), { iconName: "folder" }),
      // ★ 페이지 이동은 버튼으로도 있어야 한다. 원본 도구의 헤더가 그랬고,
      //   단축키(Alt+←/→)만 두면 있는 줄 모른다. 사이의 표시가 '지금 어디' 다.
      actionBtn("◀ 이전", () => gotoPage(-1), { id: "oc-prev-btn" }),
      pageLabel(ctx),
      actionBtn("다음 ▶", () => gotoPage(1), { id: "oc-next-btn" }),
      actionBtn("OCR원문 접기", () => toggleOcr(), { iconName: "file", id: "oc-ocr-btn" }),
      actionBtn("스캔 보기", () => toggleScan(), { iconName: "panelRight", id: "oc-scan-btn" }),
      zoomControl(),
      actionBtn("＋ 문제 추가", () => addQuestion()),
      actionBtn("초안 저장", () => saveDraft()),
      actionBtn("초안 삭제", () => deleteDraft(), { iconName: "close" }),
      actionBtn("확정(MD 저장)", () => finalize(), { primary: true, iconName: "check" }),
    ]),
};

/** 헤더 가운데의 '지금 어디' 표시. 원본 도구의 `bdae1.pdf p.1 · 1회` 자리다. */
function pageLabel(ctx) {
  const s = el("span", "oc-pglabel");
  s.id = "oc-pglabel";
  s.textContent = `${ctx.args[0] || ""} p.${ctx.args[1] || ""}`;
  return s;
}

/** 같은 소스의 이전/다음 페이지로. 목록의 페이지 배열을 기준으로 움직인다. */
async function gotoPage(delta) {
  if (!S.cur) return;
  const pages = (S.draft && S.draft._meta && S.draft._meta.pages) || [];
  const i = pages.indexOf(S.cur.page);
  const next = i >= 0 ? pages[i + delta] : null;
  if (!next) {
    toast(delta > 0 ? "이 소스의 마지막 페이지입니다." : "첫 페이지입니다.");
    return;
  }
  // ★ 이동 전에 여기서 묻는다. 해시가 바뀌면 셸이 바탕을 다시 마운트해 버려서
  //   그 뒤에 물어도 이미 화면이 비워진 상태다.
  if (S.dirty && !(await confirmModal({
    title: "저장하지 않은 편집을 버릴까요?",
    body: `<b>${escapeHtml(S.cur.src)} p.${S.cur.page}</b> 의 편집 내용이 사라집니다.`,
    ok: "버리고 이동", cancel: "머무르기", danger: true,
  }))) return;
  S.dirty = false;
  S.ctx.navigate(`/ocr/${encodeURIComponent(S.cur.src)}/${next}`);
}

/** 스캔 확대 슬라이더. 스캔을 켰을 때만 쓸모가 있지만 자리를 옮기면 찾지 못하므로
 *  원본 도구처럼 헤더에 둔다(원본: `확대` range 0.4~2.0). */
function zoomControl() {
  const w = el("label", "oc-zoom");
  w.title = "스캔 이미지 확대";
  w.appendChild(el("span", null, "확대"));
  const r = el("input");
  r.type = "range";
  r.min = "0.4";
  r.max = "2";
  r.step = "0.1";
  r.value = String(S.zoom);
  r.addEventListener("input", () => {
    S.zoom = Number(r.value);
    setPref("ocrZoom", S.zoom);
    const img = $("#oc-scan");
    if (img) img.style.width = (S.zoom * 100) + "%";
  });
  w.appendChild(r);
  return w;
}

export async function mount(root, ctx) {
  S.ctx = ctx;
  /* ★ 좌측 상단 **큰 버튼**이 부를 함수를 걸어 둔다(`shell.js` 의 PRIMARY).
     초심자가 툴바의 작은 버튼을 주 동작으로 읽지 못해서, 같은 동작을 큰 버튼으로도
     낸다 — 로직은 여기 하나뿐이고 두 자리에서 같은 것을 부른다. */
  window.XAM_PRIMARY = Object.assign(window.XAM_PRIMARY || {}, {
    render: () => runRender(),
    read: () => runRead(),
  });
  return ctx.panel ? mountList(root, ctx) : mountWork(root, ctx);
}

/* ══════════ 위층: 패널 — 페이지 목록 (첨부 1번 화면) ══════════ */
async function mountList(root, ctx) {
  root.innerHTML = `
    <div class="oc-head" id="oc-head"></div>
    <div class="oc-dash" id="oc-dash"><div class="empty">불러오는 중…</div></div>
  `;
  await refreshOverview(ctx);
}

async function refreshOverview(ctx) {
  const dash = $("#oc-dash");
  try {
    // ★ 캐시하지 않는다. Claude Code 창에서 새 초안을 만들면 패널만 다시 열어도
    //   나타나야 한다.
    S.overview = await api("/api/ocr/overview");
  } catch (e) {
    dash.innerHTML = "";
    dash.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message));
    return;
  }
  renderHead();
  renderDash(ctx);
}

function renderHead() {
  const box = $("#oc-head");
  if (!box) return;
  const d = S.overview;
  const info = d.info || {};
  box.innerHTML = "";

  if (!d.exists) {
    box.appendChild(el("div", "empty",
      d.error || "OCR 판독 폴더를 찾을 수 없습니다."));
    // ★ 새 문제집이면 이 폴더는 **아직 없는 게 정상**이다. 좌측 [＋ OCR] 의
    //   [PDF 렌더] 가 이 폴더를 만든다(그 라우트만 판독 폴더를 요구하지 않는다).
    //   예전 문구는 "지정하거나 .env 를 채우세요" 뿐이라, 처음 쓰는 사람은 아직
    //   존재하지도 않는 폴더를 고르라는 말로 읽고 거기서 멈춘다.
    box.appendChild(el("div", "field-hint",
      "<b>새 문제집이면 정상입니다</b> — 좌측 <b>[＋ OCR]</b> 의 [PDF 렌더] 가 "
      + "이 폴더를 만듭니다. 00/ 에 원본 PDF 를 넣어 두었는지만 확인하세요.<br>"
      + "이미 판독해 둔 폴더가 따로 있으면 좌하단 작업 폴더 패널에서 지정하거나 "
      + ".env 의 XAM_OCR 을 채우세요."));
    return;
  }

  const line = el("div", "oc-book");
  line.appendChild(el("b", null, info.title || "(제목 없음)"));
  line.appendChild(el("span", "muted", " → " + (info.stage_dir || "")));
  box.appendChild(line);

  const chips = el("div", "vd-env");
  const nPages = (d.pages || []).length;
  chips.appendChild(chip(`총 ${nPages}p`));
  const fin = Object.entries(d.finalized || {})
    .map(([k, v]) => `${k}회 ${v}`).join(", ");
  chips.appendChild(chip(fin ? `확정 ${fin}` : "확정 없음", fin ? "ok" : ""));
  if (info.questions_per_round) chips.appendChild(chip(`회차당 ${info.questions_per_round}문`));
  (info.srcs || []).forEach((s) => {
    chips.appendChild(chip(`${s.src} ${s.pages}p${s.role === "해설" ? " · 해설" : ""}`,
      s.role === "해설" ? "warn" : ""));
  });
  box.appendChild(chips);

  // ★ 확정 게이트 상태를 목록에서부터 보여 준다 — 막혀 있는 걸 확정 눌러 보고
  //   알게 되면 이미 한참 편집한 뒤다.
  if (d.gate && !d.gate.ok) {
    const warn = el("div", "empty");
    warn.appendChild(el("b", null, "확정이 막혀 있습니다. "));
    warn.appendChild(el("span", null, d.gate.message || ""));
    box.appendChild(warn);
  }
}

function chip(text, tone) {
  return el("span", "status-chip " + (tone || ""), text);
}


function renderDash(ctx) {
  const dash = $("#oc-dash");
  if (!dash) return;
  dash.innerHTML = "";
  const pages = (S.overview && S.overview.pages) || [];
  if (!pages.length) {
    dash.appendChild(el("div", "empty",
      "렌더된 스캔 페이지가 없습니다. 좌측 [＋ OCR] 에서 [PDF 렌더] 를 누르세요."));
    return;
  }

  // 회차별로 묶는다. 회차를 아직 판독하지 않은 페이지는 '미분류' 로 모인다.
  // ★ 회차 수를 하드코딩하지 않는다 — 초안에 있는 회차를 그대로 쓴다.
  const byRound = new Map();
  for (const p of pages) {
    const k = p.round == null ? "미분류" : String(p.round);
    if (!byRound.has(k)) byRound.set(k, []);
    byRound.get(k).push(p);
  }
  const keys = [...byRound.keys()].sort((a, b) => {
    if (a === "미분류") return 1;
    if (b === "미분류") return -1;
    return Number(a) - Number(b);
  });

  for (const k of keys) {
    const block = el("div", "oc-round");
    block.appendChild(el("h3", null,
      k === "미분류" ? "미분류(회차 판독 전)" : `${k}회`));
    const grid = el("div", "oc-grid");
    for (const p of byRound.get(k)) {
      // ★ 색은 **대조완료 기준**이다. 예전에는 "초안에 문항이 있으면" 초록이라서,
      //   판독만 됐고 아무것도 대조하지 않은 회차도 완료처럼 보였다. 이 화면은
      //   '빠진 것을 찾는' 화면이라 미대조는 색을 빼는 게 맞다.
      const n = p.n_questions || 0;
      const v = p.n_verified || 0;
      // app.css 의 상태 3색 규칙을 그대로 쓴다 — 화면마다 색을 새로 정하지 않는다.
      // 이어지는 면은 '완료' 색으로 둔다 — 앞 면이 그 내용을 이미 가져갔다
      const cell = el("button", "oc-cell "
        + (p.continuation ? stateClass(1, 1, true) : stateClass(n, v, p.has_draft)));
      cell.type = "button";
      cell.appendChild(el("span", "oc-cell-id st-title",
        `${p.src}-${String(p.page).padStart(3, "0")}`));
      // 이어지는 면은 문항 0개가 정상이다 — 미완으로 보이면 안 된다
      const note = n
        ? (v >= n ? `${n}문 · ✓${v}` : v > 0 ? `${n}문 · ✓${v}/${n}` : `${n}문`)
        : p.continuation ? "이어짐" : p.has_draft ? "초안" : "·";
      cell.appendChild(el("small", null, note));
      cell.title = n
        ? `문항 ${n}개 · 대조완료 ${v}개` + (v >= n ? "" : ` · 남은 ${n - v}개`)
        : p.continuation
          ? "앞 면에서 시작한 문항의 뒷부분입니다 — 그 문항이 이 쪽까지 갖고 있습니다."
          : "판독된 문항이 없습니다.";
      if (p.role === "해설") cell.appendChild(el("span", "qz-mark", "해설"));
      // ★ 고르면 패널이 닫히고 바탕이 열린다
      cell.addEventListener("click", () =>
        ctx.navigate(`/ocr/${encodeURIComponent(p.src)}/${p.page}`));
      grid.appendChild(cell);
    }
    block.appendChild(grid);
    dash.appendChild(block);
  }
}

/* ══════════ 아래층: 바탕 — 페이지 작업 (첨부 2번 화면) ══════════ */
async function mountWork(root, ctx) {
  /* ★ 스캔을 **기본으로 펴 둔다.** 페이지를 눌러 들어왔는데 판독 전이면 OCR 원문도
     문제 카드도 비어서 화면에 아무것도 없다 — 그 상태에서 유일하게 볼 것이 스캔이다
     (2026-08-18: "현황판을 클릭하면 body가 나오는걸로"). 접어 둔 적이 있으면
     그 선택을 존중한다. */
  S.showScan = getPref("ocrShowScan", true);
  S.hideOcr = getPref("ocrHideOcr", false);
  S.zoom = Number(getPref("ocrZoom", 0.9)) || 0.9;

  const page = el("div", "page");
  page.innerHTML = `
    <div class="oc-work" id="oc-work">
      <div class="oc-pane oc-img" id="oc-imgpane">
        <div class="oc-pagenav" id="oc-pagenav">
          <button class="btn sm" id="oc-pgprev" type="button">◀ 앞 면</button>
          <b id="oc-scanpg"></b>
          <span class="status-chip" id="oc-armed" hidden></span>
          <button class="btn sm" id="oc-pgnext" type="button">다음 면 ▶</button>
          <span class="muted" id="oc-pghint"></span>
        </div>
        <div class="oc-imgwrap" id="oc-imgwrap">
          <img id="oc-scan" alt="스캔 페이지" />
          <div class="oc-sel" id="oc-sel"></div>
        </div>
      </div>
      <div class="oc-pane oc-ocr" id="oc-ocrpane">
        <div class="oc-pane-head">
          <span>OCR 원문 (페이지 판독)</span>
          <span class="muted" id="oc-ocrmeta"></span>
        </div>
        <textarea id="oc-ocrtext" spellcheck="false"
          placeholder="이 페이지의 판독 원문. 오른쪽 카드로 분할·정리하세요."></textarea>
      </div>
      <div class="oc-pane oc-edit" id="oc-editpane">
        <div class="oc-toolbar">
          <label>회차 <input id="oc-round" type="number" min="1" /></label>
          <label>정답키줄 <input id="oc-key" type="text"
            placeholder="정답 01③ 02④ …" /></label>
          <button class="btn sm" id="oc-applykey" type="button">정답키→문제 반영</button>
          <span class="muted" id="oc-status"></span>
        </div>
        <div class="field-hint" id="oc-hint">
          이미지에서 드래그 → 영역 선택 후, 원하는 문제의 [그림 추가] 클릭.
          문항번호 오름차순으로 저장됩니다.
        </div>
        <div id="oc-qlist"></div>
      </div>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  bindDrag();
  bindPageNav();
  $("#oc-applykey").addEventListener("click", applyKey);
  document.addEventListener("keydown", onKey);
  applyLayout();

  await open(ctx.args[0], Number(ctx.args[1]), ctx);
}

function applyLayout() {
  const w = $("#oc-work");
  if (!w) return;
  w.classList.toggle("showscan", S.showScan);
  w.classList.toggle("noocr", S.hideOcr);
  const b1 = $("#oc-ocr-btn");
  if (b1 && b1.lastChild) b1.lastChild.textContent = S.hideOcr ? "OCR원문 펴기" : "OCR원문 접기";
  const b2 = $("#oc-scan-btn");
  if (b2 && b2.lastChild) b2.lastChild.textContent = S.showScan ? "스캔 숨기기" : "스캔 보기";
  const img = $("#oc-scan");
  if (img) img.style.width = (S.zoom * 100) + "%";
}

/* ★ 스캔 보기의 **면 넘기기.**
 *   해설 그림이 다음 면에 있는 문항이 있다(발문·보기는 이 면, 그림은 다음 면).
 *   지금까지는 이 면만 띄웠으니 그 그림을 지정할 방법이 아예 없었다.
 *   ★ 넘긴 면에서 드래그하면 좌표와 **함께 그 면 번호**를 기억한다 — 좌표만
 *     들고 가면 확정 때 이 면에서 같은 자리를 잘라 엉뚱한 그림이 실린다.
 */
function showScanPage(n) {
  const img = $("#oc-scan");
  if (!img || !S.cur) return;
  S.scanPage = Math.max(1, Number(n) || S.cur.page);
  img.src = `/api/ocr/scan/${encodeURIComponent(S.cur.src)}/${S.scanPage}`;
  // 면을 넘기면 그 전 드래그는 버린다 — 다른 면의 좌표를 물려주면 조용히 틀린다.
  S.pendingBox = null;
  S.pendingPage = 0;
  const sel = $("#oc-sel");
  if (sel) sel.style.display = "none";
  syncPageNav();
}

function syncPageNav() {
  if (!S.cur) return;
  const own = Number(S.cur.page);
  // ★ 툴바에도 `oc-pglabel` 이 있다. 같은 id 를 쓰면 `querySelector` 가 먼저 만난
  //   쪽에만 써서 두 라벨의 글씨가 서로 자리를 바꾼다(실측: 툴바가 p.56, 스캔
  //   머리가 「2.pdf p.55 · 7회」). 스캔 창 라벨은 `oc-scanpg` 다.
  const lab = $("#oc-scanpg");
  if (lab) lab.textContent = `p.${S.scanPage}`;
  const hint = $("#oc-pghint");
  if (hint) {
    hint.textContent = S.scanPage === own ? "이 문항의 면"
      : `다른 면 — 여기서 드래그하면 그림이 p.${S.scanPage} 좌표로 남습니다`;
    hint.classList.toggle("warn", S.scanPage !== own);
  }
  // ★ 드래그가 살아 있는지 화면이 말해야 한다. 안 보이면 사람은 눌러 보고
  //   거절당하는 것으로만 알게 된다 — 그게 「스캔을 켜라」 는 엉뚱한 안내였다.
  const arm = $("#oc-armed");
  if (arm) {
    arm.hidden = !S.pendingBox;
    if (S.pendingBox) {
      arm.className = "status-chip ok";
      arm.textContent = `영역 선택됨 p.${S.pendingPage || own}` +
        ` ${S.pendingBox[2]}×${S.pendingBox[3]} → 문항의 [영역지정] 을 누르세요`;
    }
  }
  const prev = $("#oc-pgprev");
  if (prev) prev.disabled = S.scanPage <= 1;
}

function bindPageNav() {
  const prev = $("#oc-pgprev"), next = $("#oc-pgnext");
  if (prev) prev.addEventListener("click", () => showScanPage(S.scanPage - 1));
  if (next) next.addEventListener("click", () => showScanPage(S.scanPage + 1));
}

function toggleScan() {
  S.showScan = !S.showScan;
  setPref("ocrShowScan", S.showScan);
  applyLayout();
}

function toggleOcr() {
  S.hideOcr = !S.hideOcr;
  setPref("ocrHideOcr", S.hideOcr);
  applyLayout();
}

async function open(src, page, ctx) {
  if (S.dirty && !(await confirmModal({
    title: "저장하지 않은 편집을 버릴까요?",
    body: `<b>${escapeHtml(S.cur ? S.cur.src + " p." + S.cur.page : "")}</b> 의 편집 내용이 사라집니다.`,
    ok: "버리고 이동", cancel: "머무르기", danger: true,
  }))) return;

  S.cur = { src, page };
  const box = $("#oc-qlist");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    S.draft = await api(`/api/ocr/draft/${encodeURIComponent(src)}/${page}`);
  } catch (e) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", "초안을 불러오지 못했습니다: " + e.message));
    return;
  }
  S.dirty = false;
  const m = S.draft._meta || {};
  S.scanPage = Number(page);
  $("#oc-scan").src = m.scan || "";
  syncPageNav();
  $("#oc-round").value = S.draft.round ?? "";
  $("#oc-key").value = S.draft.answer_key_line ?? "";
  $("#oc-ocrtext").value = S.draft.ocr_text || "";
  $("#oc-ocrmeta").textContent = `${m.source_pdf || src} p.${page}`
    + (m.role === "해설" ? " · 해설" : "");
  const h1 = $(".page-head h1");
  if (h1) h1.textContent = `OCR 검수 · ${src} p.${page}`;
  // 헤더 표시를 실제 값으로 채운다 — 원본 파일명 · 페이지 · 회차 · 몇/몇 번째.
  const lab = $("#oc-pglabel");
  if (lab) {
    const pages = m.pages || [];
    const i = pages.indexOf(page);
    lab.textContent = `${m.source_pdf || src} p.${page}`
      + (S.draft.round ? ` · ${S.draft.round}회` : "")
      + (i >= 0 ? `  (${i + 1}/${pages.length})` : "");
    lab.title = m.source_pdf || src;
  }
  const prev = $("#oc-prev-btn");
  const next = $("#oc-next-btn");
  const pages = m.pages || [];
  const i = pages.indexOf(page);
  if (prev) prev.disabled = i <= 0;
  if (next) next.disabled = i < 0 || i >= pages.length - 1;

  /* ★ 판독 전 페이지는 **스캔을 강제로 펴 준다.** 문제 카드도 OCR 원문도 비어 있어서
     그대로 두면 빈 화면이 뜬다 — 접어 둔 기록(pref)이 남아 있으면 기본값만으로는
     안 펴진다. 볼 것이 있는 페이지에서는 사람의 선택을 그대로 존중한다.
     pref 를 덮어쓰지 않는다 — 이 페이지에서만 펴는 것이다. */
  const empty = !(S.draft.questions || []).length && !(S.draft.ocr_text || "").trim();
  if (empty && m.has_scan) S.showScan = true;

  applyLayout();
  renderQuestions();
  status(m.has_scan ? "불러옴" : "불러옴 (스캔 이미지 없음)");
}

function status(text, ok) {
  const s = $("#oc-status");
  if (!s) return;
  s.textContent = text || "";
  s.classList.toggle("ok", !!ok);
}

function markDirty() {
  S.dirty = true;
  status("저장하지 않은 편집이 있습니다.");
}

/* ── 자산 ── */
function nextAssetId(q, prefix) {
  const A = q.assets || {};
  let n = 1;
  while (A[prefix + "-" + n]) n++;
  return prefix + "-" + n;
}

function figSrc(q, a) {
  if (a.bbox) {
    const [x, y, w, h] = a.bbox;
    // ★ `a.page` 가 있으면 **그 면**에서 자른다(해설 그림이 다음 면인 문항).
    const pg = Number(a.page) || S.cur.page;
    return `/api/ocr/crop?src=${encodeURIComponent(S.cur.src)}&page=${pg}`
      + `&x=${x}&y=${y}&w=${w}&h=${h}`;
  }
  if (a.path) return "/api/ocr/figure/" + encodeURIComponent(a.path.split("/").pop());
  return "";
}

const ASSET_KINDS = [
  ["addt", "＋표", "t", () => ({ type: "table", title: "", md: "" })],
  ["addb", "＋SQL박스", "b", () => ({ type: "sql", text: "" })],
  ["addx", "＋텍스트", "x", () => ({ type: "text", text: "" })],
  ["addm", "＋수식", "m", () => ({ type: "latex", text: "" })],
  ["addp", "＋그림", "p", () => ({ type: "figure", note: "figure" })],
];

function assetsBox(q, i) {
  const box = el("div", "oc-assets");
  const head = el("div", "oc-assets-head");
  head.appendChild(el("span", null, "자산(표/SQL박스/그림)"));
  ASSET_KINDS.forEach(([act, label]) => {
    const b = el("button", "btn sm", label);
    b.type = "button";
    b.addEventListener("click", () => addAsset(i, act));
    head.appendChild(b);
  });
  head.appendChild(el("span", "field-hint",
    "토큰 {{t-1}} 을 발문·선지·해설에 넣으면 그 위치에 펼쳐집니다 · 인라인 수식은 본문에 $…$ 로 직접"));
  box.appendChild(head);

  const ids = Object.keys(q.assets || {});
  if (!ids.length) {
    box.appendChild(el("span", "field-hint", "자산 없음"));
    return box;
  }
  ids.forEach((id) => {
    const a = q.assets[id];
    const row = el("div", "oc-asset");
    const bar = el("div", "oc-asset-bar");
    const tok = el("button", "oc-tok", `{{${id}}}`);
    tok.type = "button";
    tok.title = "지문에 토큰 삽입";
    tok.addEventListener("click", () => insertToken(i, id));
    bar.appendChild(tok);
    bar.appendChild(el("span", "badge", a.type || ""));
    const del = el("button", "btn sm", "✕");
    del.type = "button";
    del.title = "이 자산 삭제";
    del.addEventListener("click", () => delAsset(i, id));
    bar.appendChild(del);
    row.appendChild(bar);

    if (a.type === "table") {
      row.appendChild(input(a.title || "", "표 제목(없으면 비움)",
        (v) => { a.title = v; markDirty(); }));
      row.appendChild(area(a.md || "",
        "| 열1 | 열2 |\n| --- | --- |\n| 값 | 값 |   (셀 줄바꿈은 <br>)",
        (v) => { a.md = v; markDirty(); }, 3, true));
    } else if (a.type === "sql" || a.type === "box") {
      row.appendChild(area(a.text || "", "SELECT … (코드박스)",
        (v) => { a.text = v; markDirty(); }, 3, true));
    } else if (a.type === "text") {
      row.appendChild(area(a.text || "", "설명 텍스트 (줄바꿈은 <br>)",
        (v) => { a.text = v; markDirty(); }, 2, true));
    } else if (a.type === "latex") {
      row.appendChild(area(a.text || "",
        "디스플레이 수식 LaTeX ($$ 없이 본문만, 예: Z = \\dfrac{X-\\mu}{\\sigma})",
        (v) => { a.text = v; markDirty(); }, 2, true));
    } else if (a.type === "figure") {
      const fr = el("div", "oc-figrow");
      const src = figSrc(q, a);
      if (src) {
        const img = el("img");
        img.src = src;
        fr.appendChild(img);
      } else {
        fr.appendChild(el("span", "muted", "영역 미지정"));
      }
      const setb = el("button", "btn sm", "영역지정(드래그 후)");
      setb.type = "button";
      setb.addEventListener("click", () => setFigBox(i, id));
      fr.appendChild(setb);
      // ★ 다른 면의 그림이면 **말한다.** 안 보이면 다음에 그 자리를 다시
      //   드래그해 이 면 좌표로 덮어써 버린다.
      if (a.page && S.cur && Number(a.page) !== Number(S.cur.page)) {
        const gob = el("button", "btn sm", `p.${a.page} 보기`);
        gob.type = "button";
        gob.title = "이 그림이 있는 면으로 스캔을 넘깁니다";
        gob.addEventListener("click", () => {
          if (!S.showScan) toggleScan();
          showScanPage(Number(a.page));
        });
        fr.appendChild(el("span", "status-chip info", `다른 면 p.${a.page}`));
        fr.appendChild(gob);
      }
      fr.appendChild(input(a.note || "", "설명",
        (v) => { a.note = v; markDirty(); }));
      row.appendChild(fr);
    }
    box.appendChild(row);
  });
  return box;
}

function addAsset(i, act) {
  const q = S.draft.questions[i];
  q.assets = q.assets || {};
  const kind = ASSET_KINDS.find((k) => k[0] === act);
  const id = nextAssetId(q, kind[2]);
  const a = kind[3]();
  if (a.type === "figure" && S.pendingBox) {
    a.bbox = S.pendingBox;
    stampFigPage(a);
    S.pendingBox = null;
    $("#oc-sel").style.display = "none";
  }
  q.assets[id] = a;
  // 자산은 기본적으로 지문에 배치한다 — 발문과 분리되는 자리다.
  q.jimun = (q.jimun || "").replace(/\s*$/, "") + "\n\n{{" + id + "}}";
  markDirty();
  renderQuestions();
}

function insertToken(i, id) {
  const q = S.draft.questions[i];
  q.jimun = (q.jimun || "").replace(/\s*$/, "") + "\n\n{{" + id + "}}";
  markDirty();
  renderQuestions();
  status(`지문에 {{${id}}} 삽입 — 필요하면 선지/해설로 옮기세요`);
}

function delAsset(i, id) {
  const q = S.draft.questions[i];
  delete (q.assets || {})[id];
  const tok = new RegExp("\\{\\{" + id + "\\}\\}", "g");
  q.stem = (q.stem || "").replace(tok, "").replace(/\n{3,}/g, "\n\n").trim();
  q.jimun = (q.jimun || "").replace(tok, "").replace(/\n{3,}/g, "\n\n").trim();
  q.explanation = (q.explanation || "").replace(tok, "").trim();
  q.choices = (q.choices || []).map((c) => (c || "").replace(tok, ""));
  markDirty();
  renderQuestions();
}

/* ★ 문항의 면과 **같으면 새기지 않는다.** 344문항 전부가 같은 면이고,
 *   여기에 `page` 를 넣기 시작하면 이미 확정한 초안과 바이트가 갈린다.
 *   `finalize.fig_page()` 가 없을 때를 문항의 면으로 읽는다 — 그것이 기본값이다. */
function stampFigPage(a) {
  const pg = Number(S.pendingPage) || 0;
  if (pg && S.cur && pg !== Number(S.cur.page)) a.page = pg;
  else delete a.page;
  S.pendingPage = 0;
}

function setFigBox(i, id) {
  if (!S.pendingBox) {
    // ★ 없는 것이 무엇인지 **그대로** 말한다. 스캔이 켜져 있는데도 「스캔을
    //   켜세요」 라고 해서, 사람이 앱이 상태를 잘못 안다고 읽었다(실측 2026-08-19).
    if (!S.showScan) {
      toggleScan();                       // 꺼져 있으면 꾸짖지 않고 켜 준다
      toast("스캔을 켰습니다 — 그림을 감싸도록 드래그한 뒤 다시 누르세요.");
    } else {
      toast("드래그한 영역이 없습니다 — 왼쪽 스캔에서 그림을 감싸도록"
        + " 드래그한 뒤 다시 누르세요.", "err");
    }
    return;
  }
  const a = S.draft.questions[i].assets[id];
  a.bbox = S.pendingBox;
  stampFigPage(a);
  S.pendingBox = null;
  $("#oc-sel").style.display = "none";
  markDirty();
  renderQuestions();
}

/* ── 입력 위젯 ── */
function input(value, placeholder, onInput) {
  const t = el("input");
  t.type = "text";
  t.value = value || "";
  t.placeholder = placeholder || "";
  t.addEventListener("input", () => onInput(t.value));
  return t;
}

function area(value, placeholder, onInput, rows, mono) {
  const t = el("textarea");
  t.rows = rows || 2;
  t.value = value || "";
  t.placeholder = placeholder || "";
  t.spellcheck = false;
  if (mono) t.classList.add("mono");
  const grow = () => {
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight + 2, 480) + "px";
  };
  t.addEventListener("input", () => { onInput(t.value); grow(); });
  requestAnimationFrame(grow);
  return t;
}

function labeled(text, node) {
  const w = el("div", "oc-field");
  w.appendChild(el("label", "qz-label", text));
  w.appendChild(node);
  return w;
}

/* ── 문제 카드 ── */
function renderQuestions() {
  const box = $("#oc-qlist");
  if (!box) return;
  box.innerHTML = "";
  const qs = S.draft.questions || [];
  if (!qs.length) {
    box.appendChild(el("div", "empty",
      "이 페이지에 판독된 문제가 없습니다. Claude Code 창에서 판독하거나 "
      + "상단 [＋ 문제 추가] 로 직접 만드세요."));
    return;
  }
  qs.forEach((q, i) => box.appendChild(qCard(q, i)));
}

function qCard(q, i) {
  const card = el("div", "oc-q" + (q.verified ? " verified" : ""));

  const head = el("div", "oc-q-head");
  head.appendChild(numField("문항", q.question_no, (v) => {
    q.question_no = v; markDirty();
  }, 56));
  head.appendChild(numField("과목", q.subject_no, (v) => {
    q.subject_no = v; markDirty();
  }, 46));

  head.appendChild(selField("정답", CIRC, q.answer, (v) => {
    q.answer = v;
    q.answer_index = v ? CIRC.indexOf(v) : null;
    markDirty();
  }));
  head.appendChild(selField("난이도", DIFFS, q.difficulty, (v) => {
    q.difficulty = v; markDirty();
  }));

  const spacer = el("div", "oc-spacer");
  head.appendChild(spacer);

  const chk = el("label", "oc-chk");
  const cb = el("input");
  cb.type = "checkbox";
  cb.checked = !!q.verified;
  cb.addEventListener("change", () => onVerify(i, cb.checked));
  chk.appendChild(cb);
  chk.appendChild(el("span", null, "대조완료"));
  head.appendChild(chk);

  const save = el("button", "btn sm primary", "저장");
  save.type = "button";
  save.title = "이 문항만 확정 (초안 저장 + MD 기록)";
  save.addEventListener("click", () => saveOne(i));
  head.appendChild(save);

  const addfig = el("button", "btn sm", "그림 추가");
  addfig.type = "button";
  addfig.addEventListener("click", () => addAsset(i, "addp"));
  head.appendChild(addfig);

  const del = el("button", "btn sm", "삭제");
  del.type = "button";
  del.addEventListener("click", () => {
    S.draft.questions.splice(i, 1);
    markDirty();
    renderQuestions();
  });
  head.appendChild(del);
  card.appendChild(head);

  card.appendChild(labeled("발문(문제)",
    area(q.stem, "발문(질문 문장)", (v) => { q.stem = v; markDirty(); }, 3)));
  card.appendChild(labeled("지문(자료 — 표/그림/SQL박스는 {{t-1}} 토큰으로 여기 배치)",
    area(q.jimun, "지문 자료 위치. 자산을 추가하면 여기에 {{t-1}} 토큰이 들어갑니다(발문과 분리)",
      (v) => { q.jimun = v; markDirty(); }, 2)));

  const ch = el("div", "oc-choices");
  for (let c = 0; c < 4; c++) {
    const row = el("div", "oc-choice");
    row.appendChild(el("span", "oc-glyph", CIRC[c]));
    row.appendChild(area((q.choices || [])[c] || "",
      "선지 (표/그림/SQL이면 {{t-1}} 토큰)",
      (v) => {
        q.choices = q.choices || ["", "", "", ""];
        q.choices[c] = v;
        markDirty();
      }, 1));
    ch.appendChild(row);
  }
  card.appendChild(ch);

  card.appendChild(assetsBox(q, i));

  const det = el("details");
  det.open = true;
  det.appendChild(el("summary", null, "해설(선택)"));
  det.appendChild(area(q.explanation, "해설 (참고 표/그림도 {{t-1}} 토큰으로)",
    (v) => { q.explanation = v; markDirty(); }, 3));
  card.appendChild(det);

  const foot = el("div", "oc-q-foot");
  const pv = el("button", "btn sm", "👁 미리보기");
  pv.type = "button";
  const pvBox = el("div", "oc-preview");
  pvBox.hidden = true;
  pv.addEventListener("click", () => {
    if (pvBox.hidden) {
      pvBox.innerHTML = `<div class="oc-pv-qno">${q.question_no ?? ""}</div>`
        + mdToHtml(questionToMd(q));
      pvBox.hidden = false;
      pv.textContent = "✕ 미리보기 닫기";
      typesetMath(pvBox);
    } else {
      pvBox.hidden = true;
      pv.textContent = "👁 미리보기";
    }
  });
  foot.appendChild(pv);
  foot.appendChild(el("span", "field-hint",
    "← 마크다운 몰라도 실제 렌더된 문제를 확인"));
  card.appendChild(foot);
  card.appendChild(pvBox);
  return card;
}

function numField(label, value, onInput, width) {
  const w = el("label", "oc-inline");
  w.appendChild(el("span", null, label));
  const t = el("input");
  t.type = "number";
  t.min = "1";
  t.value = value ?? "";
  // ★ 폭을 박아 둔다. number 입력의 기본 폭이 넓어서 머리줄이 두 줄로 접히고,
  //   그러면 [저장]·[그림 추가]·[삭제] 가 카드마다 다른 줄에 앉는다.
  t.style.width = (width || 56) + "px";
  t.addEventListener("input", () =>
    onInput(t.value === "" ? null : Number(t.value)));
  w.appendChild(t);
  return w;
}

function selField(label, options, value, onChange) {
  const w = el("label", "oc-inline");
  w.appendChild(el("span", null, label));
  const s = el("select");
  s.appendChild(el("option", null, ""));
  options.forEach((o) => {
    const op = el("option", null, o);
    op.value = o;
    if (value === o) op.selected = true;
    s.appendChild(op);
  });
  s.addEventListener("change", () => onChange(s.value));
  w.appendChild(s);
  return w;
}

function addQuestion() {
  S.draft.questions = S.draft.questions || [];
  const last = S.draft.questions[S.draft.questions.length - 1];
  const nextNo = last && last.question_no
    ? last.question_no + 1 : S.draft.questions.length + 1;
  S.draft.questions.push({
    question_no: nextNo,
    round: Number($("#oc-round").value) || S.draft.round,
    subject_no: null, stem: "", jimun: "",
    choices: ["", "", "", ""], answer: "", difficulty: "",
    explanation: "", assets: {},
  });
  markDirty();
  renderQuestions();
}

/* ── 정답키줄 ── */
function applyKey() {
  const line = $("#oc-key").value;
  S.draft.answer_key_line = line;
  const map = {};
  const re = /(\d{1,2})\s*([①②③④⑤])/g;
  let m;
  while ((m = re.exec(line))) map[Number(m[1])] = m[2];
  let n = 0;
  for (const q of S.draft.questions || []) {
    if (q.question_no in map) {
      q.answer = map[q.question_no];
      q.answer_index = CIRC.indexOf(q.answer);
      n++;
    }
  }
  markDirty();
  renderQuestions();
  status(`정답키 ${n}문항 반영됨`, true);
}

/* ── 스캔 드래그 → bbox ── */
function bindDrag() {
  const wrap = $("#oc-imgwrap");
  const img = $("#oc-scan");
  const sel = $("#oc-sel");
  let sx = 0, sy = 0, drag = false;

  wrap.addEventListener("mousedown", (e) => {
    if (e.target !== img) return;
    const r = img.getBoundingClientRect();
    sx = e.clientX - r.left;
    sy = e.clientY - r.top;
    drag = true;
    sel.style.display = "block";
    sel.style.left = sx + "px";
    sel.style.top = sy + "px";
    sel.style.width = "0";
    sel.style.height = "0";
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    const r = img.getBoundingClientRect();
    const cx = e.clientX - r.left, cy = e.clientY - r.top;
    sel.style.left = Math.min(sx, cx) + "px";
    sel.style.top = Math.min(sy, cy) + "px";
    sel.style.width = Math.abs(cx - sx) + "px";
    sel.style.height = Math.abs(cy - sy) + "px";
  });
  window.addEventListener("mouseup", () => {
    if (!drag) return;
    drag = false;
    const r = img.getBoundingClientRect();
    // 화면에서 잰 좌표를 원본 픽셀로 되돌린다 — 확대 배율이 섞이면 크롭이 틀어진다.
    const scale = img.naturalWidth / r.width;
    const x = parseFloat(sel.style.left), y = parseFloat(sel.style.top);
    const w = parseFloat(sel.style.width), h = parseFloat(sel.style.height);
    if (w < 8 || h < 8) { sel.style.display = "none"; return; }
    S.pendingBox = [Math.round(x * scale), Math.round(y * scale),
      Math.round(w * scale), Math.round(h * scale)];
    S.pendingPage = S.scanPage || (S.cur ? S.cur.page : 0);
    const other = S.cur && S.pendingPage !== Number(S.cur.page);
    status(`영역 선택됨 ${S.pendingBox.join(",")}`
      + (other ? ` · p.${S.pendingPage} 의 좌표` : "")
      + " → 문제의 [그림 추가]");
    syncPageNav();
  });
}

/* ── 저장 · 확정 ── */
function collect() {
  const d = S.draft;
  d.round = Number($("#oc-round").value) || null;
  d.answer_key_line = $("#oc-key").value;
  d.ocr_text = $("#oc-ocrtext").value;
  return d;
}

async function saveDraft(quiet) {
  const d = collect();
  const body = { ...d };
  delete body._meta;
  try {
    await api(`/api/ocr/draft/${encodeURIComponent(S.cur.src)}/${S.cur.page}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    S.dirty = false;
    if (!quiet) status("초안 저장됨", true);
    return true;
  } catch (e) {
    toast("초안 저장 실패: " + e.message, "err");
    return false;
  }
}

function stampRound(q) {
  q.round = q.round || Number($("#oc-round").value) || S.draft.round;
  if (!q.round_label && S.draft.round_label) q.round_label = S.draft.round_label;
  return q;
}

async function saveOne(i) {
  const q = stampRound(S.draft.questions[i]);
  if (!q.round || !q.question_no) {
    toast("회차와 문항번호를 채우세요.", "err");
    return;
  }
  if (!(await saveDraft(true))) return;
  try {
    const r = await api("/api/ocr/finalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src: S.cur.src, page: S.cur.page, questions: [q] }),
    });
    status(`저장됨${q.verified ? " ✓대조완료" : ""}: `
      + ((r.saved || []).join(", ") || "바뀐 내용 없음"), true);
  } catch (e) {
    handleErr(e);
  }
}

async function onVerify(i, checked) {
  const q = S.draft.questions[i];
  q.verified = checked;
  markDirty();
  renderQuestions();
  if (!q.round && !Number($("#oc-round").value)) {
    status("회차가 없어 확정하지 않았습니다 (초안만 기록).");
    await saveDraft(true);
    return;
  }
  await saveOne(i);
}

async function finalize() {
  if (!(await saveDraft(true))) return;
  const qs = (S.draft.questions || []).map(stampRound);
  const bad = qs.filter((q) => !q.round || !q.question_no);
  if (bad.length) {
    toast("회차 또는 문항번호가 없는 문제가 있습니다.", "err");
    return;
  }
  try {
    const r = await api("/api/ocr/finalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src: S.cur.src, page: S.cur.page, questions: qs }),
    });
    status(`확정 ${(r.saved || []).length}건 기록`
      + ((r.unchanged || []).length ? ` · 변경없음 ${r.unchanged.length}` : ""), true);
    toast(`확정했습니다 — ${(r.saved || []).length}개 파일 기록`);
  } catch (e) {
    handleErr(e);
  }
}

function handleErr(e) {
  if (e.status === 409) {
    confirmModal({
      title: "확정을 막았습니다",
      body: escapeHtml(e.message),
      ok: "닫기", cancel: "",
    });
    return;
  }
  toast("실패: " + e.message, "err");
}

/* ── 검증 · 렌더 (패널 액션) ── */
async function runVerify() {
  try {
    const d = await api("/api/ocr/verify");
    const r = d.refinalize || {};
    const rounds = d.rounds || [];
    let body = `<p>초안 → <code>01/*.md</code> 확정 왕복 <b>${r.same} / ${r.total}</b> 바이트 일치`
      + (r.new_count ? ` · 미확정 ${r.new_count}` : "")
      + (r.differ_count ? ` · <b>불일치 ${r.differ_count}</b>` : "") + "</p>";
    for (const x of rounds) {
      body += `<p><b>${escapeHtml(x.src)} ${String(x.round).padStart(2, "0")}회</b> — `
        + `문항 ${x.count}${x.total ? "/" + x.total : ""}`
        + (x.problems.length ? ` · 경고 ${x.problems.length}건` : " · 경고 없음") + "</p>";
      if (x.problems.length) {
        body += "<ul>" + x.problems.slice(0, 12)
          .map((p) => `<li>${escapeHtml(p)}</li>`).join("") + "</ul>";
      }
    }
    confirmModal({
      title: r.ok ? "검증 통과" : "검증 실패 — 확정이 막혀 있습니다",
      body, ok: "닫기", cancel: "",
    });
  } catch (e) {
    toast("검증 실패: " + e.message, "err");
  }
}

async function runRender() {
  let plan;
  try {
    plan = await api("/api/ocr/render/plan");
  } catch (e) {
    toast("렌더 계획을 읽지 못했습니다: " + e.message, "err");
    return;
  }
  const lines = (plan.log || []).map((l) => `<li>${escapeHtml(l.trim())}</li>`).join("");
  const go = await confirmModal({
    title: "00/ 의 PDF 를 페이지 이미지로 렌더할까요?",
    body: `<p><code>${escapeHtml(plan.pdf_dir || "")}</code></p><ul>${lines}</ul>`
      + "<p class='muted'>이미 렌더된 소스는 건너뜁니다. 내용이 같은 중복 PDF 도 건너뜁니다.</p>",
    ok: "렌더", cancel: "취소",
  });
  if (!go) return;
  try {
    const r = await api("/api/ocr/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    toast(`렌더 완료 — ${r.pages}페이지`);
    await refreshOverview(S.ctx);
  } catch (e) {
    toast("렌더 실패: " + e.message, "err");
  }
}


/* 이 페이지 초안 삭제 — 잘못 읽힌 면을 처음부터 다시 읽히려는 용도.
 *
 * ★ 확정본(01/*.md)은 건드리지 않는다. 초안은 중간 산출물이고 확정본이 결과물이다 —
 *   지워도 이미 확정한 문항은 남는다. 그 사실을 확인창에 적는다(안 적으면 확정까지
 *   지워지는 줄 알고 못 누른다).
 * ★ `.bak` 을 남긴다. 사람이 손본 초안일 수도 있다.
 */
async function deleteDraft() {
  if (!S.cur) return;
  const n = (S.draft?.questions || []).length;
  const ok = await confirmModal({
    title: `${S.cur.src} p.${S.cur.page} 의 초안을 지울까요?`,
    body: (n ? `<p>문항 <b>${n}개</b>가 이 초안에 있습니다.</p>` : "<p>이 초안에는 문항이 없습니다.</p>")
      + "<p class='muted'>확정본(<code>01/*.md</code>)은 지우지 않습니다 — 이미 확정한 문항은 남습니다."
      + " <code>.bak</code> 을 남기므로 되돌릴 수 있습니다.</p>"
      + "<p class='muted'>지운 뒤 이 면은 미판독으로 돌아갑니다. [스캔 판독] 을 누르면 다시 읽습니다.</p>",
    ok: "초안 삭제", cancel: "취소", danger: true,
  });
  if (!ok) return;
  try {
    const r = await api(
      `/api/ocr/draft/${encodeURIComponent(S.cur.src)}/${S.cur.page}`,
      { method: "DELETE" });
    if (!r.removed) { toast(r.reason || "지울 초안이 없습니다."); return; }
    S.dirty = false;
    toast(`초안을 지웠습니다 (${r.backup} 남김).`);
    S.ctx.navigate("/ocr");
  } catch (e) {
    toast("지우지 못했습니다: " + e.message, "err");
  }
}

/* ── 판독 ────────────────────────────────────────────────────────────────
 *
 * 스캔 이미지를 읽어 초안을 만든다. 전에는 이 일을 사람이 Claude Code 창에 말로
 * 시켰다(`services/ocr/readpage.py` 머리말 참조).
 *
 * ★ 잡으로 돈다 — 실측 한 장 43초다. 151장이면 두 시간에 가깝다. 그래서 확인창에
 *   **몇 장인지와 대략 얼마나 걸리는지**를 먼저 보여 준다. 눌러 놓고 기다리는 사람이
 *   "멈췄나" 를 의심하지 않게, 시작한 뒤에는 잡 로그로 넘긴다.
 */
async function runRead() {
  const d = S.overview;
  if (!d || !d.exists) { toast("판독 폴더가 없습니다.", "err"); return; }

  /* 소스(PDF)별로 묶어 **체크박스로 고르게** 한다.
   *
   * ★ 전에는 확인창이 "첫 소스의 미판독 전부" 를 통째로 잡았다. 소스가 둘이면 한 번에
   *   하나만 되고, 몇 장인지도 시작한 뒤에야 보였다(2026-08-18: "pdf갯수를 불러와서
   *   거기에 체크박스를 넣을 순없나").
   * ★ 이어지는 면(`continuation`)은 대상에서 뺀다 — 문항 0개가 정상이라 넣으면 매번
   *   다시 읽는다.
   */
  const groups = new Map();
  for (const p of d.pages || []) {
    if (!groups.has(p.src)) groups.set(p.src, { all: [], todo: [] });
    const g = groups.get(p.src);
    g.all.push(p);
    if (!p.n_questions && !p.continuation) g.todo.push(p.page);
  }
  const live = [...groups.entries()].filter(([, g]) => g.todo.length);
  if (!live.length) { toast("판독할 페이지가 없습니다 — 이미 다 읽었습니다."); return; }

  const box = el("div");
  const picked = new Map();
  for (const [src, g] of live) {
    const row = el("label", "oc-pick");
    row.style.display = "flex";
    row.style.gap = "8px";
    row.style.alignItems = "baseline";
    row.style.margin = "6px 0";
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = true;
    picked.set(src, cb);
    row.appendChild(cb);
    const lo = g.todo[0], hi = g.todo[g.todo.length - 1];
    row.appendChild(el("b", null, `${src}.pdf`));
    row.appendChild(el("span", null,
      `미판독 ${g.todo.length}장 (p.${lo}~${hi}) · 전체 ${g.all.length}장`));
    row.appendChild(el("span", "muted", `· 대략 ${Math.max(1, Math.round(g.todo.length * 45 / 60))}분`));
    box.appendChild(row);
  }
  const total = live.reduce((n, [, g]) => n + g.todo.length, 0);
  box.appendChild(el("div", "field-hint",
    `한 장에 40~60초입니다. 이미 판독된 페이지와 '이어짐' 면은 건너뜁니다. `
    + `중간에 취소할 수 있고, 읽은 페이지는 남습니다.`));

  const go = await confirmModal({
    title: `판독할 PDF 를 고르세요 (미판독 ${total}장)`,
    bodyNode: box,
    ok: "판독 시작", cancel: "취소",
  });
  if (!go) return;

  const srcs = [...picked.entries()].filter(([, cb]) => cb.checked).map(([src]) => src);
  if (!srcs.length) { toast("고른 PDF 가 없습니다."); return; }

  // 잡은 소스 단위다 — 고른 것을 순서대로 하나씩 띄운다(첫 잡으로 이동한다).
  let firstId = null;
  for (const src of srcs) {
    try {
      const job = await api("/api/ocr/read", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ src }),
      });
      firstId = firstId || job.id;
      toast(`${src}.pdf 판독을 시작했습니다.`);
      break;      // 동시에 하나만 돈다 — 나머지는 끝난 뒤 다시 누르면 된다
    } catch (e) {
      toast(`${src}.pdf 를 시작하지 못했습니다: ` + e.message, "err");
    }
  }
  if (firstId) location.hash = "#/job/" + firstId;
}

/* ── 단축키 ── */
function onKey(e) {
  if (!location.hash.startsWith("#/ocr/")) return;
  if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
    e.preventDefault(); saveDraft(); return;
  }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault(); finalize(); return;
  }
  if (e.altKey && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
    // 헤더의 [◀ 이전]/[다음 ▶] 과 같은 함수를 쓴다 — 미저장 확인도 한 곳에서.
    e.preventDefault();
    gotoPage(e.key === "ArrowRight" ? 1 : -1);
  }
}

window.addEventListener("beforeunload", (e) => {
  if (S.dirty && location.hash.startsWith("#/ocr")) {
    e.preventDefault(); e.returnValue = "";
  }
});

/* ══════════ 미리보기 — MD 부분집합 → HTML + 수식 ══════════
 * 원본 도구의 렌더와 같은 결과를 낸다. 검수자가 마크다운을 몰라도 실제 문제
 * 모양을 볼 수 있어야 한다.
 */
function assetMd(q, id) {
  const a = (q.assets || {})[id];
  if (!a) return "{{" + id + "}}";
  if (a.type === "table") return (a.title ? `**${a.title}**\n\n` : "") + (a.md || "");
  if (a.type === "sql" || a.type === "box") return "```sql\n" + (a.text || "") + "\n```";
  if (a.type === "figure") {
    const s = figSrc(q, a);
    return s ? `![${a.note || ""}](${s})` : "";
  }
  if (a.type === "text") return "```text\n" + (a.text || "") + "\n```";
  if (a.type === "latex") return "$$\n" + (a.text || "") + "\n$$";
  return "";
}

function expandTokens(text, q) {
  return (text || "").replace(/\{\{([A-Za-z]+-\d+)\}\}/g, (m, id) => assetMd(q, id));
}

/** 이 보기를 `①` 단독 줄 + 빈 줄 + 본문으로 써야 하는가.
 *
 * ★ `services/book/md.py` 의 `is_block_choice()` 와 **같은 규칙**이어야 한다.
 *   갈리면 미리보기와 확정본이 다른 모양이 된다.
 * ★ 파이프로 시작해도 표가 아니면 블록형이 아니다 — SQL 문자열 결합 연산자
 *   `||` 가 보기 하나로 오는 문항이 있다(실측 SQLD 12번). 블록형으로 쓰면
 *   글리프만 한 줄 남고 값이 아래로 떨어져 보기가 두 줄로 갈린다.
 */
function isBlockChoice(ex) {
  const t = (ex || "").replace(/^\s+/, "");
  if (!t) return false;
  if (t.includes("\n")) return true;
  if (t.startsWith("**") || t.startsWith("```") || t.startsWith("![")) return true;
  if (t.startsWith("|")) return isTableLine(t);   // 표일 때만 블록형
  return false;
}

function questionToMd(q) {
  let s = "## 문제\n" + expandTokens(q.stem || "", q) + "\n\n";
  const jm = expandTokens(q.jimun || "", q);
  if (jm.trim()) s += "## 지문\n" + jm + "\n\n";
  s += "## 보기\n" + [0, 1, 2, 3].map((c) => {
    const ex = expandTokens((q.choices && q.choices[c]) || "", q);
    return isBlockChoice(ex) ? CIRC[c] + "\n\n" + ex : CIRC[c] + " " + ex;
  }).join("\n\n") + "\n\n";
  const ex = expandTokens(q.explanation || "", q);
  if (ex.trim()) s += "## 해설\n" + ex;
  return s;
}

const SQL_KW = new Set(("SELECT FROM WHERE AND OR NOT IN IS NULL LIKE INSERT INTO VALUES "
  + "UPDATE SET DELETE CREATE TABLE ALTER ADD COLUMN MODIFY DROP CONSTRAINT PRIMARY KEY "
  + "FOREIGN REFERENCES DEFAULT GROUP BY ORDER HAVING JOIN INNER LEFT RIGHT FULL OUTER "
  + "CROSS ON UNION ALL MINUS INTERSECT AS DISTINCT CASE WHEN THEN ELSE END OVER PARTITION "
  + "RANGE ROWS BETWEEN PRECEDING FOLLOWING UNBOUNDED CURRENT ROW CONNECT START WITH PRIOR "
  + "COMMIT ROLLBACK SAVEPOINT TRUNCATE GRANT REVOKE ROLLUP CUBE GROUPING SETS DESC ASC")
  .split(" "));

function hlSql(code) {
  const re = /('(?:[^']|'')*')|(--[^\n]*)|([A-Za-z_][A-Za-z0-9_]*)|([\s\S])/g;
  let out = "", m;
  while ((m = re.exec(code))) {
    if (m[1]) out += `<span class="sql-st">${escapeHtml(m[1])}</span>`;
    else if (m[2]) out += `<span class="sql-cm">${escapeHtml(m[2])}</span>`;
    else if (m[3]) out += SQL_KW.has(m[3].toUpperCase())
      ? `<span class="sql-kw">${escapeHtml(m[3])}</span>` : escapeHtml(m[3]);
    else out += escapeHtml(m[4]);
  }
  return out;
}

function inl(s) {
  return escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/&lt;br\s*\/?&gt;/gi, "<br>");
}

/** 이 줄이 **진짜 표 행**인가.
 *
 * ★ `|` 로 시작하는지만 보면 안 된다. SQL 문자열 결합 연산자 `||` 가 **보기 하나**로
 *   오는 문항이 있다(실측 12번: `① =` `② ||` `③ &&` `④ -`). 그걸 표로 보면 빈 칸
 *   하나짜리 표가 렌더되고 **보기 내용이 사라진다** — 화면에 ② 아래 빈 상자만 남았다.
 *
 * 표라고 보는 조건: 양끝 파이프를 뗀 뒤 **칸 하나라도 내용이 있다.**
 *   ★ '칸이 둘 이상' 을 요구하면 **1열 표**가 깨진다 — 보기가 1열 표인 문항이 있다
 *     (실측 SQLD 20번: `| MAX(COL1) |` / `| --- |` / `| 2 |` 네 개가 보기다).
 *   `| a | b |`   → 표 (칸 2개, 내용 있음)
 *   `|---|---|`   → 표 (구분선)
 *   `||`          → 표 아님 (칸 1개, 내용 없음)
 *   `| |`         → 표 아님 (같은 이유 — 원문의 `| |` 도 보기다)
 */
function isTableLine(ln) {
  const t = (ln || "").trim();
  if (!t.startsWith("|")) return false;
  const cells = t.replace(/^\||\|$/g, "").split(/(?<!\\)\|/);
  return cells.some((c) => c.trim() !== "");
}

function renderTable(rows) {
  /* ★ `\|` 는 **셀 내용**이다 — 열 구분자가 아니다.
     SQL 문법에 파이프가 들어가는 표가 있다(실측 31번:
     `EXTRACT('YEAR' \| 'MONTH' \| 'DAY' from d)`). 그냥 split("|") 하면 한 셀이
     네 조각으로 갈라지고 백슬래시가 글자로 남는다 — 표 전체가 무너진다.
     이스케이프를 넣어도 화면이 그대로 쪼개서, 사람이 표를 포기하고 줄글로 풀었다. */
  const cells = rows.map((r) => r.trim().replace(/^\||\|$/g, "")
    .split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|")));
  const body = cells.filter((r, i) => !(i === 1 && r.every((c) => /^:?-+:?$/.test(c))));
  if (!body.length) return "";
  const head = body[0], rest = body.slice(1);
  return `<table class="tbl"><thead><tr>${head.map((c) => `<th>${inl(c)}</th>`).join("")}`
    + `</tr></thead><tbody>${rest.map((r) =>
      `<tr>${r.map((c) => `<td>${inl(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function mdToHtml(md) {
  const L = md.split("\n");
  let h = "", i = 0, sec = "";
  while (i < L.length) {
    const ln = L[i];
    if (ln.startsWith("```")) {
      const lang = ln.slice(3).trim();
      const code = [];
      i++;
      while (i < L.length && !L[i].startsWith("```")) { code.push(L[i]); i++; }
      i++;
      // ★ `text` 박스는 **산문**이라 수식을 조판한다. `sql` 박스는 코드라 안 한다.
      //
      //   MathJax 는 `pre`·`code` 를 건드리지 않도록 설정돼 있다(skipHtmlTags).
      //   그 설정은 SQL 박스 때문에 필요하다 — `'$100'` 같은 문자열이 수식으로
      //   먹히면 코드가 깨진다. 그런데 텍스트 박스까지 `pre` 로 내보내서, 설명
      //   문장 안의 `$X$`·`$Y$` 가 원문 그대로 남았다(발문 지문에서 실제로 걸렸다).
      //   → 텍스트 박스만 `div` 로 낸다. 줄바꿈은 CSS(white-space: pre-wrap)가 지킨다.
      //     MD 원문은 그대로 ```text 펜스다 — 화면에서만 다르게 조판한다.
      h += lang === "text"
        ? `<div class="code textbox">${inl(code.join("\n"))}</div>`
        : `<pre class="code">${hlSql(code.join("\n"))}</pre>`;
      continue;
    }
    // 디스플레이 수식은 한 덩어리로 묶어야 MathJax 가 읽는다(줄별 <p> 로 쪼개면 깨진다).
    if (ln.trim() === "$$") {
      const mm = [];
      i++;
      while (i < L.length && L[i].trim() !== "$$") { mm.push(L[i]); i++; }
      i++;
      h += `<p class="mathblock">$$${escapeHtml(mm.join("\n"))}$$</p>`;
      continue;
    }
    let m;
    if ((m = ln.match(/^(#{1,6})\s+(.*)$/))) {
      sec = m[2].trim();
      if (sec === "해설") h += `<h4>${inl(m[2])}</h4>`;
      i++; continue;
    }
    if ((m = ln.match(/^!\[(.*?)\]\((.*?)\)/))) {
      h += `<img src="${m[2]}">` + (m[1] ? `<div class="cap">${escapeHtml(m[1])}</div>` : "");
      i++; continue;
    }
    if (isTableLine(ln)) {
      const t = [];
      // ★ 진입은 엄격, **이어지는 행은 느슨**하다. 원본 표에 빈 행이 있다
      //   (실측 32번: `|   |   |`). 빈 행에서 끊으면 표가 둘로 갈린다.
      while (i < L.length && L[i].trim().startsWith("|")) { t.push(L[i]); i++; }
      h += renderTable(t); continue;
    }
    if (/^\d+\.\s/.test(ln)) {
      const it = [];
      while (i < L.length && /^\d+\.\s/.test(L[i])) { it.push(L[i].replace(/^\d+\.\s/, "")); i++; }
      h += "<ol>" + it.map((x) => `<li>${inl(x)}</li>`).join("") + "</ol>";
      continue;
    }
    if (ln.trim() === "") { i++; continue; }
    const isChoice = /^\s*[①②③④⑤]/.test(ln);
    const cls = isChoice ? "choice-line" : (sec === "문제" ? "qstem" : "");
    h += `<p${cls ? ` class="${cls}"` : ""}>${inl(ln)}</p>`;
    i++;
  }
  return h;
}

/* 수식 — MathJax SVG 로컬 번들. 수식이 있는 문항을 처음 미리볼 때만 로드한다.
 * MD 원문은 $K$ 그대로 두고 화면에서만 조판한다. */
let mjLoad = null;
function ensureMathJax() {
  if (mjLoad) return mjLoad;
  window.MathJax = {
    tex: {
      inlineMath: [["$", "$"], ["\\(", "\\)"]],
      displayMath: [["$$", "$$"], ["\\[", "\\]"]],
      processEscapes: true,
    },
    // 코드박스(SQL/text)는 건드리지 않는다 — pre/code 는 기본 제외 목록이다.
    options: {
      skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"],
      menuOptions: { settings: { inTabOrder: false } },
    },
    svg: { fontCache: "global" },
    startup: { typeset: false },
  };
  mjLoad = new Promise((res) => {
    const s = document.createElement("script");
    s.src = "/static/vendor/tex-svg.js";
    s.async = true;
    s.onload = () => res(true);
    s.onerror = () => {
      status("수식 렌더 번들이 없습니다 — $…$ 원문으로 표시합니다.");
      res(false);
    };
    document.head.appendChild(s);
  });
  return mjLoad;
}

function typesetMath(node) {
  if (!/\$|\\\(|\\\[/.test(node.textContent || "")) return;
  ensureMathJax().then((ok) => {
    if (ok && window.MathJax && window.MathJax.typesetPromise) {
      window.MathJax.typesetPromise([node]).catch(() => {});
    }
  });
}
