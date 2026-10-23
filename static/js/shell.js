/* 셸 — 2층 해시 라우터, 좌측 레일(접기), 최근 작업, 전역 단축키
 *
 * 라우터가 2층인 이유: 사전점검·잡 로그·HTML 미리보기는 작업 본문 위에 뜨는 부유
 * 패널이다. 패널을 열고 닫아도 베이스는 언마운트되지 않으므로, 24번들 렌더(최대
 * 두 시간)의 2초 폴링과 문항 에디터의 미저장 텍스트가 살아 있다.
 *
 *   layer "base"  → #view 를 갈아치운다  (/questions /video /publish /summary)
 *   layer "panel" → 패널을 띄운다        (/precheck/:code /job/:id /preview/:key)
 */
"use strict";

import { $, $$, el, toast } from "./util.js";
import { getBook, getJobs, getVersion } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { openPanel, closePanel, isOpen as panelOpen, setCloseHandler, setActions } from "./panel.js";

const view = $("#view");

/* ── 라우트 테이블 ──────────────────────────────────
 * 일하는 화면은 전부 바탕(base)이다. 패널은 "보고 닫는" 표면만 맡는다 —
 * 미저장 텍스트를 든 화면을 패널에 두면 Esc·스크림 클릭에 편집이 날아간다.
 */
const routes = [
  // 바탕(아래층) — 실제로 일하는 화면
  { re: /^\/home$/,             nav: "",   layer: "base",  load: () => import("./home.js") },
  // OCR 검수(도구 #1) — 페이지 단위. 좌 OCR 원문 / 우 문제 카드 / 스캔 드래그.
  { re: /^\/ocr\/([^/]+)\/(\d+)$/, nav: "oc", layer: "base", load: () => import("./ocr.js") },
  // OCR 실행 — PDF 고르고 돌리는 **바탕** 화면. 로그가 아래로 흐르므로 패널이 아니다.
  { re: /^\/ocr-run$/, nav: "oc", layer: "base", load: () => import("./ocrrun.js") },
  { re: /^\/scan\/(.+)$/,       nav: "sc", layer: "base",  load: () => import("./scan.js") },
  // 과정 정의 — 시험정보(exams/<id>.json). 스캔이 없어도 여는 화면이라 입구 쪽이다.
  { re: /^\/exams$/,            nav: "ed", layer: "base",  load: () => import("./examdef.js") },
  { re: /^\/questions\/(.+)$/,  nav: "q",  layer: "base",  load: () => import("./questions.js") },
  { re: /^\/video\/(.+)$/,      nav: "v",  layer: "base",  load: () => import("./video.js") },
  // 일괄 렌더의 진행·터미널. 목록(패널)에서 시작하면 여기로 온다 — 작업은 바탕에서.
  { re: /^\/render\/(.+)$/,     nav: "v",  layer: "base",  load: () => import("./video.js") },
  // 집필 — **바탕이다.** 파트 하나가 10분씩 가고 진행 로그를 보며 기다리는 화면이라
  // 패널에 두면 Esc·스크림 클릭에 닫히고, 돌던 잡의 진행을 놓친다.
  { re: /^\/authoring$/,        nav: "a",  layer: "base",  load: () => import("./authoring.js") },
  { re: /^\/authoring\/(.+)$/,  nav: "a",  layer: "base",  load: () => import("./authoring.js") },
  // ★ 발행은 2단계다 — 화면은 하나이고 **게이트의 범위**만 다르다.
  //   `/publish` 는 옛 주소라 2차와 같게 둔다(북마크·「발행 이력」 링크가 그걸 쓴다).
  { re: /^\/publish\/problems$/, nav: "p",  layer: "base",  load: () => import("./publish.js") },
  { re: /^\/publish\/video$/,    nav: "p2", layer: "base",  load: () => import("./publish.js") },
  { re: /^\/publish$/,          nav: "p2", layer: "base",  load: () => import("./publish.js") },
  { re: /^\/slides$/,           nav: "sl", layer: "base",  load: () => import("./slides.js") },
  { re: /^\/summary$/,          nav: "s",  layer: "base",  load: () => import("./summary.js") },
  { re: /^\/summary\/(.+)$/,    nav: "s",  layer: "base",  load: () => import("./summary.js") },

  // 부유 패널(위층) — 고르는 곳
  { re: /^\/books$/,     nav: "",   layer: "panel", group: "books",     load: () => import("./books.js") },
  { re: /^\/ocr$/,       nav: "oc", layer: "panel", group: "ocr",       load: () => import("./ocr.js") },
  { re: /^\/scan$/,      nav: "sc", layer: "panel", group: "scan",      load: () => import("./scan.js") },
  { re: /^\/questions$/, nav: "q",  layer: "panel", group: "questions", load: () => import("./questions.js") },
  { re: /^\/video$/,     nav: "v",  layer: "panel", group: "video",     load: () => import("./video.js") },

  { re: /^\/precheck\/(.+)$/, nav: "v", layer: "panel", group: "video",   load: () => import("./video.js") },
  { re: /^\/job\/(.+)$/,      nav: "v", layer: "panel", group: "video",   load: () => import("./video.js") },
  { re: /^\/preview\/(.+)$/,  nav: "s", layer: "panel", group: "summary", load: () => import("./summary.js") },
];

const HOME = routes[0];   // 바헉의 기본 — 패널을 지우면 여기로 돌아온다

function parseHash() {
  const raw = (location.hash || "#/home").slice(1) || "/home";
  const [path, qs] = raw.split("?");
  const params = new URLSearchParams(qs || "");
  for (const rt of routes) {
    const m = path.match(rt.re);
    if (m) return { path, rt, args: m.slice(1).map(decodeURIComponent), params };
  }
  return { path: "/home", rt: HOME, args: [], params };
}

let baseToken = 0;      // 레이어별로 취소 토큰을 따로 둬야 경쟁 상태가 안 생긴다
let panelToken = 0;
let basePath = null;

export function navigate(path) {
  if (location.hash === "#" + path) render();
  else location.hash = path;
}

/* ── 렌더 ─────────────────────────────────────────── */
async function render() {
  const { path, rt, args, params } = parseHash();
  $$("#side-nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === rt.nav));
  // 큰 버튼은 화면이 바뀔 때마다 다시 정한다 — 지금 화면의 주 동작이어야 한다.
  try { renderPrimary(path); } catch (e) { /* 부팅 중이면 아직 없다 */ }

  if (rt.layer === "panel") {
    if (!basePath) await mountBase(HOME, "/home", [], new URLSearchParams());
    await mountPanel(rt, path, args, params);
    return;
  }

  if (panelOpen()) closePanel();

  // 이미 이 화면이 바탕에 떠 있으면 다시 마운트하지 않는다.
  // 이게 2층 구조의 존재 이유다 — 재마운트하면 폴링과 입력이 날아간다.
  if (path === basePath && view.firstElementChild) {
    view.focus({ preventScroll: true });
    return;
  }
  await mountBase(rt, path, args, params);
}

async function mountBase(rt, path, args, params) {
  const token = ++baseToken;
  view.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const mod = await rt.load();
    if (token !== baseToken) return;
    view.innerHTML = "";
    basePath = path;
    const ctx = { args, params, path, navigate };
    await mod.mount(view, ctx);
    // 제목·부제·액션 줄은 셸이 만든다. 패널에서든 바탕에서든 같은 계약이라
    // 화면을 다른 레이어로 옮겨도 모듈을 고칠 필요가 없다.
    if (mod.meta) applyBaseHead(mod, ctx);
  } catch (e) {
    console.error(e);
    if (token !== baseToken) return;
    view.innerHTML = "";
    basePath = path;
    view.appendChild(el("div", "empty", "화면을 불러오지 못했습니다: " + e.message));
  }
  view.focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
}

async function mountPanel(rt, path, args, params) {
  const token = ++panelToken;
  const host = openPanel({ group: rt.group, path: rt.railPath || path });
  host.body.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const mod = await rt.load();
    if (token !== panelToken) return;
    host.body.innerHTML = "";
    const ctx = { args, params, path, navigate, panel: host };
    if (mod.meta) {
      host.setHead(resolve(mod.meta.title, ctx) || "", resolve(mod.meta.subtitle, ctx));
      setActions(mod.meta.actions ? mod.meta.actions(ctx) : []);
    }
    await mod.mount(host.body, ctx);
  } catch (e) {
    console.error(e);
    if (token !== panelToken) return;
    host.body.innerHTML = "";
    host.body.appendChild(el("div", "empty", "화면을 불러오지 못했습니다: " + e.message));
  }
  host.focusBody();
}

const resolve = (v, ctx) => (typeof v === "function" ? v(ctx) : v);

/** meta → 바탕 화면의 제목 줄. 모듈이 만든 .page 맨 앞에 끼워 넣어 폭이 정확히 맞는다. */
function applyBaseHead(mod, ctx) {
  const page = view.querySelector(".page");
  if (!page) return;
  const head = el("div", "page-head");
  const left = el("div");
  left.appendChild(el("h1", null, resolve(mod.meta.title, ctx) || ""));
  const sub = resolve(mod.meta.subtitle, ctx);
  if (sub) left.appendChild(el("p", null, sub));
  head.appendChild(left);

  const actions = (mod.meta.actions ? mod.meta.actions(ctx) : []).filter(Boolean);
  if (actions.length) {
    const box = el("div", "head-actions");
    actions.forEach((n) => box.appendChild(n));
    head.appendChild(box);
  }
  page.insertBefore(head, page.firstChild);
}

/* 패널 닫기는 언제나 바탕 라우트로 돌아간다. history.back() 을 쓰면 안 된다 —
 * 이너 레일로 옮겨 다녔다면 바로 이전 기록도 또 다른 패널이라서, 닫히는 대신
 * 한 칸 되돌아간 것처럼 보인다. 닫기는 "레이어를 벗는" 동작이다. */
setCloseHandler(() => navigate(basePath || "/home"));

/* ── 좌측 레일 접기 ───────────────────────────────── */
const RAIL_KEY = "xam.rail";
function applyRail(state) {
  document.body.dataset.rail = state;
  const btn = $("#rail-toggle");
  if (btn) btn.setAttribute("aria-label", state === "collapsed" ? "메뉴 펼치기" : "메뉴 접기");
}
function toggleRail() {
  const next = document.body.dataset.rail === "collapsed" ? "expanded" : "collapsed";
  localStorage.setItem(RAIL_KEY, next);
  applyRail(next);
}
applyRail(localStorage.getItem(RAIL_KEY) === "collapsed" ? "collapsed" : "expanded");

/* ── 사이드바 머리 — 품목 · 검수 진행률 ───────────────
 * 240문항 중 몇 개를 검수했는지가 이 앱에서 가장 중요한 숫자다. 어느 화면에
 * 있어도 보이도록 레일에 박아 둔다. */
export async function renderBrandStatus() {
  const [v, book] = await Promise.all([getVersion(), getBook(true)]);

  // ★ 칩은 **활성 폴더의 표시 이름**을 보여야 한다.
  //   예전에는 `v.pd_label`(= .env 의 XAM_PD_LABEL 상수)을 썼다. 그래서
  //   작업 폴더 카드에서 이름을 "빅분기" 로 고쳐도 칩은 계속 상수를 보여 주고,
  //   폴더를 아직 지정하지 않은 첫 실행에도 이미 어느 품목이 정해진 것처럼 보였다.
  //   book.pd_label 은 /api/book/info 가 활성 폴더의 books.json 에서 읽어 준다.
  $("#su-name").textContent = book.first_run
    ? "폴더를 지정하세요"
    : (book.pd_label || book.pd || "품목 미설정");
  const team = $("#su-team");
  if (!book.exists) {
    // ★ "경로 오류" 로 뭉개면 안 된다. 경로가 정상인데 아직 01/ 단계인 경우와
    //   폴더 자체가 없는 경우는 사람이 할 일이 완전히 다르다.
    //   01/ 만 있는 폴더는 **정상 작업 상태**다(#2 가 02/ 를 만들기 전).
    const scanOnly = (book.stages && (book.stages["01"] || {}).md) || 0;
    team.textContent = scanOnly ? `01/ 단계 · 기출 ${scanOnly}개` : "폴더를 지정하세요";
    team.classList.toggle("bad", !scanOnly);
    team.title = book.error || "";
    return;
  }
  team.classList.remove("bad");
  team.title = "";
  team.textContent = `검수 ${book.reviewed} / ${book.total}`;
}

const STATUS_KO = { done: "완료", running: "진행 중", queued: "대기", error: "오류" };

export async function renderRecent() {
  const box = $("#side-recent");
  const jobs = await getJobs(12);
  box.innerHTML = "";
  if (!jobs.length) {
    box.appendChild(el("div", "side-empty", "아직 작업이 없습니다."));
    return;
  }
  jobs.forEach((j) => {
    const a = el("a", "recent-item");
    a.href = j.kind === "publish" ? "#/publish" : `#/job/${encodeURIComponent(j.id)}`;
    a.title = `${j.label || j.kind} · ${STATUS_KO[j.status] || j.status}`;
    a.appendChild(el("span", "ri-dot " + (j.status === "done" ? "done" : j.status || "ready")));
    a.appendChild(el("span", "ri-name", j.label || j.kind));
    box.appendChild(a);
  });
}


/* ── 부팅 ─────────────────────────────────────────── */
hydrateIcons(document);

/* ── 큰 버튼 = 지금 화면의 주 동작 ─────────────────────
 * 화면마다 사람이 제일 먼저 눌러야 하는 것이 다르다. OCR 화면에서 「다음 미검수 문항」이
 * 큰 버튼이면, 정작 해야 할 [PDF 렌더]·[OCR 실행] 은 툴바의 작은 버튼으로 밀린다.
 * 초심자는 그것을 주 동작으로 읽지 못한다(2026-08-18 지시).
 *
 * ★ 동작은 **그 화면 모듈이 이미 가진 것**을 부른다 — 로직을 여기 복제하지 않는다.
 *   화면이 window 에 걸어 둔 함수를 쓴다(`XAM_PRIMARY`).
 */
const PRIMARY = {
  // ★ 주황은 **기본이 ＋ OCR** 이다 — 이 앱의 시작점이 OCR 이고, 큰 버튼이 주 동작이어야
  //   초심자가 무엇부터 누를지 안다(2026-08-18 지시). 누르면 PDF 목록·체크박스·실행·로그가
  //   한 화면에 있다("실행버튼 누르면 밑으로 쭈욱").
  //   ★ 「다음 미검수 문항」은 **없앴다**(2026-08-18 지시: "맨날 미검수 문항이 없데…
  //     그리고 필요가 없어"). 큐가 비어 있을 때가 대부분이라 큰 버튼이 늘 헛돌았다.
  //     문항을 도는 화면에는 그 화면 안에 「다음 미검수 →」 버튼이 이미 있다
  //     (`questions.js`) — 거기서만 쓰면 된다.
  "/ocr-run": [{ label: "← OCR 검수로", icon: "folder", key: "goto-ocr" }],
};

function renderPrimary(path) {
  const b1 = $("#btn-primary"), b2 = $("#btn-primary2");
  if (!b1 || !b2) return;
  /* ★ **지금 라우팅된 경로**로 판정한다. `basePath` 를 보면 안 된다 — OCR 목록은
     패널이라 바탕(`basePath`)은 `/home` 에 머문다. 그래서 `#/ocr` 에서도 큰 버튼이
     「다음 미검수 문항」으로 남았다(실측 2026-08-18). */
  const cur = path || (location.hash || "").replace(/^#/, "") || basePath || "";
  const spec = PRIMARY[cur.split("/").slice(0, 2).join("/")] || null;
  const set = (btn, lab, ico) => {
    $("#" + btn.id + "-label").textContent = lab;
    const i = $("#" + btn.id + "-icon");
    if (i) i.dataset.icon = ico;
    btn.hidden = false;
  };
  if (!spec) {
    // 기본값 — 이 앱은 OCR 에서 시작한다
    set(b1, "＋ OCR", "folder");
    b1.dataset.act = "goto-run";
    b2.hidden = true;
  } else {
    set(b1, spec[0].label, spec[0].icon);
    b1.dataset.act = spec[0].key;
    if (spec[1]) {
      set(b2, spec[1].label, spec[1].icon);
      b2.dataset.act = spec[1].key;
    } else {
      b2.hidden = true;
    }
  }
  hydrateIcons(document.getElementById("side-rail") || document);
}

async function runPrimary(act) {
  if (act === "goto-run") return navigate("/ocr-run");
  if (act === "goto-ocr") return navigate("/ocr");
  // 화면 모듈이 걸어 둔 함수 — 없으면 그 화면으로 먼저 데려간다.
  const fn = (window.XAM_PRIMARY || {})[act];
  if (typeof fn === "function") return fn();
  navigate("/ocr");
  toast("화면을 먼저 엽니다 — 다시 눌러 주세요.");
}

$("#btn-primary").addEventListener("click", (e) =>
  runPrimary(e.currentTarget.dataset.act || "goto-run"));
$("#btn-primary2").addEventListener("click", (e) =>
  runPrimary(e.currentTarget.dataset.act || ""));
$("#rail-toggle").addEventListener("click", toggleRail);
$("#brand-mark").addEventListener("click", () => {
  if (document.body.dataset.rail === "collapsed") toggleRail();
});
// 좌하단 칩 = 품목 전환 진입점. 누르면 작업 폴더 패널이 뜼다.
$("#side-user").addEventListener("click", () => navigate("/books"));

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && (e.key === "b" || e.key === "B")) {
    e.preventDefault(); toggleRail();
  }
});

window.addEventListener("hashchange", render);

/* ★ 첫 화면은 **바탕**이다. 부유 패널을 열어 두고 시작하지 않는다.
 *
 *   예전에는 `#/scan` 이 기본이라, 앱을 켜자마자 "이미 스캔된 80문항 목록" 이 담긴
 *   부유 창이 떠 있었다. 작업 폴더를 아직 고르지도 않았는데 어느 폴더의 결과인지
 *   모를 목록이 먼저 보이고, 그 창을 닫아야 바탕이 나온다 — 순서가 거꾸로다.
 *   패널은 "고르는 곳" 이므로 사람이 열어야 뜬다. */
if (!location.hash) location.hash = "#/home";
render();
renderBrandStatus();
renderRecent();
renderShareBanner();

/* 사내망에서 열었을 때 상단에 띄우는 띠.
 *
 * ★ 서버에 물어본다. 브라우저가 location.hostname 으로 추측하면 틀린다 —
 *   운영자도 사내망 IP 로 접속할 수 있고(다른 기기·북마크) 그때는 실제로 보기
 *   전용이 맞다. 판정은 게이트와 같은 함수(core/lan.is_local)가 한다.
 *
 * 이 띠가 없으면 동료가 [저장] 을 눌러 403 을 보고 "앱이 고장났다" 고 여긴다.
 * 실패를 설명하는 것보다 **누르기 전에 알리는 것**이 낫다.
 */
async function renderShareBanner() {
  let m;
  try {
    m = await (await fetch("/api/mode")).json();
  } catch { return; }               // 못 물어봤으면 아무것도 하지 않는다
  if (!m || !m.readonly) return;

  const b = el("div", "share-banner");
  b.appendChild(el("b", null, "보기 전용"));
  b.appendChild(el("span", null,
    " — 사내망으로 공유된 화면입니다. 둘러보실 수 있고, 저장·빌드·렌더는 "
    + "운영자 PC 에서만 됩니다."));
  document.body.insertAdjacentElement("afterbegin", b);
  // 띠가 헤더를 덮지 않게 본문을 그만큼 내린다(높이를 CSS 에 박지 않는다).
  document.body.style.paddingTop = b.offsetHeight + "px";
}

window.addEventListener("xam:job-changed", renderRecent);
window.addEventListener("xam:review-changed", renderBrandStatus);
// 폴더를 바꿀면 품목·진행률이 전부 달라진다.
window.addEventListener("xam:book-changed", async () => {
  await renderBrandStatus();
  await renderRecent();
});

// 전역 오류를 조용히 삼키지 않는다(로컬 앱이라 콘솔을 잘 안 본다)
window.addEventListener("unhandledrejection", (e) => {
  console.error(e.reason);
  toast("처리 중 오류: " + (e.reason?.message || e.reason), "err");
});
