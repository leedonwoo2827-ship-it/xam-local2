/* 바탕(아래층)의 기본 화면 — 패널을 닫으면 여기로 돌아온다.
 *
 * ★ 이 앱의 UX 핵심: 목록은 패널(위층), 작업은 바탕(아래층).
 *   그래서 바탕에는 항상 무언가가 깔려 있어야 한다. 아무것도 고르지 않은 상태가
 *   이 화면이다 — 파이프라인 4단계를 띄우고, 누르면 그 단계의 목록 패널이 열린다.
 */
"use strict";

import { $, api, el, toast } from "./util.js";
import { getBook, getVersion } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { donut } from "./charts.js";

export const meta = {
  title: "무엇을 할까요",
  subtitle: "목록은 위에 떠 있는 창에서 고르고, 작업은 이 바탕에서 합니다.",
};

const STEPS = [
  { nav: "sc", path: "/scan", icon: "folder", label: "구조화 MD로 정리",
    desc: "스캔한 OCR 본문을 01/*.md 로 확정합니다." },
  { nav: "q", path: "/questions", icon: "file", label: "문항 교정",
    desc: "_rounds · 02/ · 05/lesson 을 함께 갱신합니다." },
  { nav: "v", path: "/video", icon: "film", label: "영상 제작·검수",
    desc: "슬라이드 · 음성 · 자막을 확인하고 렌더합니다." },
  { nav: "p", path: "/publish", icon: "package", label: "1부 빌드",
    desc: "사전점검 → 빌드 → 검증. 업로드는 IP 허브가 가져갑니다." },
];

export async function mount(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card hm-head" id="hm-head"></div>
    <div class="grid grid-2" id="hm-steps"></div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  // ★ 아직 작업 폴더를 지정한 적이 없으면 **여기 바탕에서** 지정부터 받는다.
  //   부유 패널을 자동으로 띄우지 않는다 — 고르지도 않은 폴더의 스캔 목록이
  //   먼저 뜨는 것이 이 화면이 생긴 이유다.
  let state = null;
  try { state = await api("/api/books/active"); } catch (e) { /* 아래에서 처리 */ }
  if (state && state.first_run) {
    $("#hm-steps").hidden = true;
    await renderFirstRun(ctx, state);
    return;
  }

  renderSteps(ctx);
  await renderHead();
}

/** 첫 실행 — 작업 폴더 지정. 바탕에 카드 하나로 둔다. */
async function renderFirstRun(ctx, state) {
  const box = $("#hm-head");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  box.classList.add("hm-first");

  const h = el("div");
  h.appendChild(el("b", null, "작업 폴더를 먼저 지정하세요"));
  h.appendChild(el("p", "muted",
    "이 앱이 읽고 쓸 폴더입니다. 지정하면 다음부터는 그 폴더로 바로 시작하고, "
    + "좌하단 칩에서 언제든 바꿀 수 있습니다."));
  box.appendChild(h);

  // .env 의 XAM_BOOK 을 '제안' 으로 보여준다 — 등록된 것이 아니다.
  let scan = null;
  try {
    const d = await api("/api/books/");
    scan = (d.items || [])[0] || null;
  } catch (e) { /* 제안 없이 진행 */ }

  if (scan) {
    const sug = el("div", "hm-suggest");
    const top = el("div", "hm-suggest-head");
    top.appendChild(el("span", "muted", ".env 의 기본값"));
    const stage = { empty: "빈 폴더", raw: "00/ 원본 PDF", scan: "01/ 기출까지",
                    edit: "02/ 문항까지", video: "05/ 영상까지" }[scan.stage] || scan.stage;
    top.appendChild(el("span", "badge", stage));
    sug.appendChild(top);
    sug.appendChild(el("pre", "pb-cmd", scan.path));
    const facts = el("div", "vd-env");
    const st = scan.stages || {};
    facts.appendChild(el("span", "status-chip",
      `01/ ${(st["01"] || {}).md || 0}개`));
    facts.appendChild(el("span", "status-chip",
      `회차 ${(scan.rounds || []).length}`));
    if ((scan.subjects || []).length) {
      facts.appendChild(el("span", "status-chip", scan.subjects.join(" · ")));
    }
    sug.appendChild(facts);
    box.appendChild(sug);
  }

  const acts = el("div", "hm-first-acts");
  if (scan && scan.exists) {
    const use = el("button", "btn primary", "이 폴더로 시작");
    use.type = "button";
    use.addEventListener("click", () => confirmFolder(ctx, scan.path));
    acts.appendChild(use);
  }
  const pick = el("button", "btn", "다른 폴더 고르기");
  pick.type = "button";
  pick.addEventListener("click", () => pickFolder(ctx));
  acts.appendChild(pick);
  box.appendChild(acts);

  box.appendChild(el("div", "field-hint",
    "고른 폴더 안의 00/ 01/ 02/ … 만 읽고 씁니다. 판독 초안 폴더는 따로 지정합니다."));
}

async function confirmFolder(ctx, path) {
  try {
    await api("/api/books/confirm", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    window.dispatchEvent(new CustomEvent("xam:book-changed"));
    toast("작업 폴더를 지정했습니다.");
    ctx.navigate("/home");
    location.reload();
  } catch (e) {
    toast("지정 실패: " + e.message, "err");
  }
}

async function pickFolder(ctx) {
  try {
    const r = await api("/api/books/pick", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (r.cancelled || !r.picked) return;
    if (!(r.scan || {}).usable) {
      toast("빈 폴더입니다. 새 문제집이면 그 안에 00 폴더를 만들고 원본 PDF 를 넣은 뒤 다시 고르세요.", "err");
      return;
    }
    await confirmFolder(ctx, r.picked);
  } catch (e) {
    toast("폴더를 고르지 못했습니다: " + e.message, "err");
  }
}

function renderSteps(ctx) {
  const box = $("#hm-steps");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  STEPS.forEach((s) => {
    const card = el("div", "card hm-step");
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    const head = el("div", "hm-step-head");
    head.appendChild(icon(s.icon, 18));
    head.appendChild(el("b", null, s.label));
    card.appendChild(head);
    card.appendChild(el("p", "muted", s.desc));
    const hint = el("div", "field-hint",
      s.path === "/publish" ? "바탕에서 바로 열립니다" : "위에 목록 창이 뜹니다");
    card.appendChild(hint);
    const go = () => ctx.navigate(s.path);
    card.addEventListener("click", go);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
    });
    box.appendChild(card);
  });
}

async function renderHead() {
  const box = $("#hm-head");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  let v, book, scan;
  try {
    [v, book] = await Promise.all([getVersion(), getBook(true)]);
  } catch (e) {
    box.appendChild(el("div", "empty", "상태를 불러오지 못했습니다: " + e.message));
    return;
  }
  try { scan = await api("/api/scan"); } catch (e) { scan = null; }

  if (!book.exists) {
    const w = el("div", "qz-warn err");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null, book.error
      || "BOOK 을 찾을 수 없습니다. .env 의 XAM_BOOK 을 확인하세요."));
    box.appendChild(w);
    return;
  }

  const left = el("div", "qz-head-stat");
  left.appendChild(donut(book.total ? Math.round((book.reviewed / book.total) * 100) : null,
    { label: "검수", size: 78 }));
  const t = el("div");
  t.appendChild(el("div", "stat-value", `${book.reviewed} / ${book.total}`));
  t.appendChild(el("div", "muted", "문항 검수"));
  left.appendChild(t);
  box.appendChild(left);

  const info = el("div", "hm-facts");
  const fact = (label, value, title) => {
    const f = el("div", "hm-fact");
    f.appendChild(el("span", "muted", label));
    f.appendChild(el("b", null, value));
    if (title) f.title = title;
    return f;
  };
  info.appendChild(fact("품목", `${v.pd_label || v.pd}`, v.pd));
  info.appendChild(fact("회차", `${(book.rounds || []).length}회`,
    (book.rounds || []).map((r) => r.round_label).join(" / ")));
  if (scan) info.appendChild(fact("OCR 확정", `${scan.confirmed} / ${scan.count}`));
  const st = book.stages || {};
  info.appendChild(fact("영상 번들", `${(st["05"] || {}).bundles ?? "?"}개`));
  info.appendChild(fact("BOOK", book.book, book.book));
  box.appendChild(info);
}
