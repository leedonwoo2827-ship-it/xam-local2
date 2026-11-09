/* 구조화 MD로 정리 (실기) — 확정본 01/practical/{RR}-{P}-{NN} 문항을 보고 고른다.
 *
 * ★ 필기 scan.js 와 같은 2층 구조(2026-11-09 지시: 메뉴는 남기되 실기로 동작):
 *     #/practical-scan       위층 패널: 확정본 문항 목록(색 = 대조완료)
 *     #/practical-scan/:id   아래층 바탕: 그 문항의 원고(MD) 미리보기 + 원본 쪽으로 가기
 * ★ 고치는 곳은 OCR 검수다 — 실기 확정본은 OCR 검수 [확정]이 회차째 다시 쓴다. 여기서 MD 를
 *   손으로 고치면 다음 확정에 덮인다. 그래서 이 화면은 보고 · 찾고 · 검수 쪽으로 보내는 데까지.
 */
"use strict";

import { $, api, el, stateClass } from "./util.js";
import { getPref, setPref } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";
import { practicalMdHtml } from "./practicalMd.js";

const PART = { 1: "기본작업", 2: "계산작업", 3: "분석작업", 4: "기타작업" };
const S = { list: null, filters: { unverified: false, q: "" }, ctx: null };

export const meta = {
  title: (ctx) => (ctx.panel ? "확정본 문항 (실기)" : `구조화 MD로 정리 · ${ctx.args[0] || ""}`),
  subtitle: (ctx) => (ctx.panel
    ? "고르면 이 창이 닫히고 아래 바탕에서 열립니다. 색 = 대조완료."
    : "01/practical 확정본 원고입니다. 고치는 곳은 OCR 검수 — [원본 쪽에서 고치기]."),
  actions: (ctx) => (ctx.panel ? [] : [
    actionBtn("← 문항 목록", () => ctx.navigate("/practical-scan"), { iconName: "folder" }),
    actionBtn("◀ 이전", () => step(-1)),
    actionBtn("다음 ▶", () => step(1)),
  ]),
};

export async function mount(root, ctx) {
  S.ctx = ctx;
  Object.assign(S.filters, getPref("prScanFilters", {}) || {});
  return ctx.panel ? mountList(root, ctx) : mountWork(root, ctx);
}

/* ══════════ 위층: 목록 ══════════ */
async function mountList(root, ctx) {
  root.innerHTML = `
    <div class="qz-bar">
      <button class="chip" id="ps-unver" type="button">미대조만</button>
      <div class="search-box">
        <span data-icon="search" data-icon-size="14"></span>
        <input id="ps-q" type="search" placeholder="id(01-2-03) · 발문 검색" />
      </div>
      <span class="qz-bar-note muted" id="ps-count"></span>
    </div>
    <div class="sc-list" id="ps-list"></div>`;
  hydrateIcons(root);
  const unv = $("#ps-unver");
  unv.classList.toggle("on", S.filters.unverified);
  unv.addEventListener("click", () => {
    S.filters.unverified = !S.filters.unverified;
    unv.classList.toggle("on", S.filters.unverified);
    setPref("prScanFilters", S.filters);
    refresh(ctx);
  });
  const input = $("#ps-q");
  input.value = S.filters.q || "";
  let t = null;
  input.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => { S.filters.q = input.value; setPref("prScanFilters", S.filters); refresh(ctx); }, 250);
  });
  await refresh(ctx);
  input.focus();
}

async function load() {
  const qs = new URLSearchParams();
  if (S.filters.unverified) qs.set("unverified", "1");
  if (S.filters.q) qs.set("q", S.filters.q);
  S.list = await api("/api/practical/items?" + qs.toString());
}

async function refresh(ctx) {
  const box = $("#ps-list");
  try { await load(); } catch (e) {
    if (box) { box.innerHTML = ""; box.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message)); }
    return;
  }
  const d = S.list;
  const cnt = $("#ps-count");
  if (cnt) cnt.textContent = (d.filtered === d.count ? `전체 ${d.count}문항` : `${d.filtered} / ${d.count}문항`)
    + `  ·  대조완료 ${d.verified} / ${d.count}` + (d.count - d.verified ? `  ·  남은 ${d.count - d.verified}` : "  ·  완료");
  box.innerHTML = "";
  if (!d.items.length) {
    box.appendChild(el("div", "empty", d.count ? "조건에 맞는 문항이 없습니다."
      : "확정본이 없습니다 — OCR 검수에서 회차를 확정하세요."));
    return;
  }
  for (const it of d.items) {
    const row = el("div", "sc-row " + stateClass(1, it.verified ? 1 : 0));
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    const head = el("div", "sc-row-head");
    head.appendChild(el("span", "sc-row-id", it.id));
    if (it.error) head.appendChild(el("span", "badge err", "읽기 실패"));
    else {
      head.appendChild(el("span", "sc-row-subj", `${String(it.round).padStart(2, "0")}회 문제${it.part} ${PART[it.part] || ""}`
        + (it.head ? " · 묶음 머리" : ` · ${it.no}번`)));
      if (it.points != null) head.appendChild(el("span", "badge", `${it.points}점`));
      const marks = el("span", "sc-row-marks");
      if (it.figures) marks.appendChild(el("span", "qz-mark fig", `그림 ${it.figures}`));
      if (!it.has_answer) marks.appendChild(el("span", "qz-mark todo", "정답 없음"));
      for (const f of it.flags || []) marks.appendChild(el("span", "qz-mark todo", f));
      marks.appendChild(el("span", "qz-mark " + (it.verified ? "" : "todo"), it.verified ? "대조완료" : "미대조"));
      head.appendChild(marks);
    }
    row.appendChild(head);
    row.appendChild(el("div", "sc-row-body", it.error || it.preview || ""));
    const go = () => ctx.navigate("/practical-scan/" + encodeURIComponent(it.id));
    row.addEventListener("click", go);
    row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    box.appendChild(row);
  }
}

/* ══════════ 아래층: 문항 보기 ══════════ */
async function mountWork(root, ctx) {
  const id = decodeURIComponent(ctx.args[0] || "");
  const page = el("div", "page");
  root.appendChild(page);
  let r;
  try { r = await api("/api/practical/item/" + encodeURIComponent(id)); } catch (e) {
    page.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message));
    return;
  }
  const j = r.json || {};
  const pages = [...new Set([...(j.problems || []).map((p) => p.page).filter(Boolean), ...((j.answer || {}).pages || [])])].sort((a, b) => a - b);
  const card = el("div", "card");
  const head = el("div", "qz-foot");
  head.appendChild(el("b", null, `${id} · ${String(j.round).padStart(2, "0")}회 문제${j.part} ${PART[j.part] || ""}`
    + (j.head ? " · 묶음 머리" : ` · ${j.no}번`)));
  head.appendChild(el("span", "status-chip" + (j.verified ? " ok" : ""), j.verified ? "대조완료" : "미대조"));
  for (const f of j.flags || []) head.appendChild(el("span", "status-chip err", f));
  for (const p of pages) {
    const b = el("button", "btn sm", `p.${p} 원본 쪽에서 고치기`);
    b.type = "button";
    b.addEventListener("click", () => ctx.navigate(`/practical-review/${encodeURIComponent(r.src)}/${p}`));
    head.appendChild(b);
  }
  card.appendChild(head);
  card.appendChild(el("div", "field-hint", r.path));
  const body = el("div", "pr-page md-body");
  body.style.cssText = "max-width:900px;line-height:1.7;font-size:15px";
  body.innerHTML = practicalMdHtml(r.md, "01");
  card.appendChild(body);
  page.appendChild(card);
}

async function step(d) {
  if (!S.list) { try { await load(); } catch (_) { return; } }
  const ids = (S.list.items || []).map((x) => x.id);
  const cur = decodeURIComponent(S.ctx.args[0] || "");
  const i = ids.indexOf(cur);
  const nx = ids[i + d];
  if (nx) S.ctx.navigate("/practical-scan/" + encodeURIComponent(nx));
}

