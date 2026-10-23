/* 해설 모아 노트 구조화 (v2) — #/outline[/:key]
 *
 * 이론 요약 노트의 앞 단계. 우리 모의고사 해설을 과목별로 모으고(즉시), Claude 가
 * 과목 → 항목 → 상세로 묶어 중복을 정돈한다. 사람이 이 목차를 보고 승인하면
 * [이론 요약 노트] 집필이 그 목차를 따른다(theory.source_view 가 함께 넘긴다).
 */
"use strict";

import { api, el, escapeHtml, toast, renderMarkdown } from "./util.js";
import { pollJob } from "./store.js";
import { actionBtn } from "./panel.js";

const S = { root: null, key: "", items: [] };

export const meta = {
  title: "해설 모아 노트 구조화",
  subtitle: "우리 모의고사 해설을 과목 → 항목 → 상세로 모으고 중복을 정돈합니다. 승인한 목차를 이론 요약 노트가 따릅니다.",
  actions: () => [
    actionBtn("전 과목 해설 모으기", () => collectAll(), { iconName: "download" }),
    actionBtn("노트 빌드 — 전 과목 구조화", () => structure(S.items.map((i) => i.key)), { primary: true, iconName: "sparkles" }),
  ],
};

export async function mount(root, ctx) {
  S.root = root;
  S.key = ctx.args[0] || "";
  const page = el("div", "page ol-page");
  root.appendChild(page);
  page.appendChild(el("div", "ol-list", ""));
  page.appendChild(el("div", "lc-log", ""));
  page.appendChild(el("div", "ol-view", ""));
  await reload();
}

async function reload() {
  const d = await api("/api/outline");
  S.items = d.items;
  if (!S.key && S.items.length) S.key = (S.items.find((i) => i.outline) || S.items[0]).key;
  const list = S.root.querySelector(".ol-list");
  list.innerHTML = "";
  S.items.forEach((it) => {
    const c = it.collected, o = it.outline;
    const card = el("div", "card ol-card" + (it.key === S.key ? " on" : "")
      + (o && o.approved ? " state-done" : o ? " state-part" : ""));
    card.innerHTML = `<div class="ol-h"><b>${it.no}과목 · ${escapeHtml(it.name)}</b>
        ${o && o.approved ? '<span class="lc-chip s-approved">승인됨</span>' : ""}</div>
      <div class="muted">해설 ${c ? `${c.n}개 · ${c.rounds}회차 · ${c.chars.toLocaleString()}자` : "아직 안 모음"}</div>
      <div class="muted">구조 ${o ? `대단원 ${o.topics} · 소단원 ${o.items} · 출처 ${o.refs}${o.cost_usd ? ` · $${o.cost_usd}` : ""}` : "아직 없음"}</div>`;
    const row = el("div", "row");
    row.appendChild(small("모으기", () => collect(it.key)));
    row.appendChild(small("구조화 (Claude)", () => structure([it.key]), true));
    if (o) row.appendChild(small(o.approved ? "승인 취소" : "목차 승인", () => approve(it.key, !o.approved)));
    card.appendChild(row);
    card.addEventListener("click", (e) => { if (!e.target.closest("button")) { S.key = it.key; reload(); } });
    list.appendChild(card);
  });
  await show();
}

function small(label, fn, primary = false) {
  const b = el("button", "btn sm" + (primary ? " primary" : ""), label);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}

async function show() {
  const view = S.root.querySelector(".ol-view");
  view.innerHTML = "";
  if (!S.key) return;
  const d = await api(`/api/outline/${S.key}`);
  const card = el("div", "card md ol-md");
  if (d.md) {
    const o = d.outline || {};
    if ((o.missing_refs || []).length) {
      card.appendChild(el("div", "lc-fixnote", `어느 항목에도 안 들어간 해설 ${o.missing_refs.length}개: ${o.missing_refs.slice(0, 12).join(", ")}`));
    }
    const body = el("div");
    body.innerHTML = renderMarkdown(d.md);
    card.appendChild(body);
  } else if (d.summary.collected) {
    const c = d.summary.collected;
    card.innerHTML = `<h3>모은 해설 — 많이 나온 개념</h3><p class="muted">${c.n}개 해설 · 아직 구조화하지 않았습니다.</p>`
      + `<ul>${(c.top_tags || []).map(([t, n]) => `<li>${escapeHtml(t)} <b>${n}</b></li>`).join("")}</ul>`;
  } else {
    card.innerHTML = `<p class="muted">[모으기] 를 누르면 이 과목의 해설을 회차마다 모읍니다. 모델을 부르지 않습니다.</p>`;
  }
  view.appendChild(card);
}

async function collect(key) {
  try { await api(`/api/outline/${key}/collect`, { method: "POST" }); toast("모았습니다."); S.key = key; reload(); }
  catch (e) { toast(e.message, "err"); }
}

async function collectAll() {
  for (const it of S.items) {
    try { await api(`/api/outline/${it.key}/collect`, { method: "POST" }); }
    catch (e) { toast(`${it.no}과목: ${e.message}`, "err"); }
  }
  toast("전 과목 해설을 모았습니다.");
  reload();
}

async function structure(keys) {
  try {
    const job = await api("/api/outline/structure", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keys }),
    });
    const box = S.root.querySelector(".lc-log");
    box.classList.add("on");
    const lines = [];
    const fin = await pollJob(job.id, (j) => {
      (j.log && j.log.lines || []).forEach((l) => lines.push(typeof l === "string" ? l : (l.line || l.text || "")));
      box.textContent = lines.slice(-8).join("\n") || j.label;
    });
    toast(fin && fin.status === "done" ? "구조화를 마쳤습니다." : "실패했습니다", fin && fin.status === "done" ? "" : "err");
    reload();
  } catch (e) { toast(e.message, "err"); }
}

async function approve(key, on) {
  try {
    await api(`/api/outline/${key}/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on }),
    });
    reload();
  } catch (e) { toast(e.message, "err"); }
}
