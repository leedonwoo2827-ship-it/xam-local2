/* 해설 모아 노트 구조화 (v2) — #/outline[/:key]
 *
 * 이론 요약 노트의 앞 단계. 우리 모의고사 해설을 과목별로 모으고(즉시), Claude 가
 * 과목 → 항목 → 상세로 묶어 중복을 정돈한다. 사람이 이 목차를 보고 승인하면
 * [이론 요약 노트] 집필이 그 목차를 따른다(theory.source_view 가 함께 넘긴다).
 */
"use strict";

import { api, el, escapeHtml, toast, renderMarkdown, confirmModal } from "./util.js";
import { pollJob } from "./store.js";
import { actionBtn } from "./panel.js";
import { jobClock } from "./jobclock.js";

const S = { root: null, key: "", items: [] };

export const meta = {
  title: "해설 모아 노트 구조화",
  subtitle: "우리 모의고사 해설을 과목 → 항목 → 상세로 모으고 중복을 정돈합니다. 승인한 목차를 이론 요약 노트가 따릅니다.",
  actions: () => [
    actionBtn("전 과목 자동 진행", () => autoAll(), { primary: true, iconName: "sparkles" }),
  ],
};

export async function mount(root, ctx) {
  S.root = root;
  S.key = ctx.args[0] || "";
  const page = el("div", "page ol-page");
  root.appendChild(page);
  page.appendChild(el("div", "ol-list", ""));
  page.appendChild(el("div", "lc-clock", ""));
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
    card.innerHTML = `<div class="ol-h"><b>${it.label || it.no + "과목"} · ${escapeHtml(it.name)}</b>
        ${o && o.approved ? '<span class="lc-chip s-approved">승인됨</span>' : ""}</div>
      <div class="muted">해설 ${c ? `${c.n}개 · ${c.rounds}회차 · ${c.chars.toLocaleString()}자` : "아직 안 모음"}</div>
      <div class="muted">구조 ${o ? `대단원 ${o.topics} · 소단원 ${o.items} · 출처 ${o.refs}${o.cost_usd ? ` · $${o.cost_usd}` : ""}` : "아직 없음"}</div>`;
    const row = el("div", "row");
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
    card.innerHTML = `<p class="muted">[구조화] 를 누르면 이 과목의 해설을 회차마다 모은 뒤 목차로 정돈합니다.</p>`;
  }
  view.appendChild(card);
}

/* ★ [전 과목 자동 진행] — 2부 네 화면(구조화 · 이론 요약 · 요약반 · 종합반)이 같은 버튼·같은 확인창을 쓴다
 *   (2026-11-10 지시: "가급적 4개가 실행이 통일"). 해설 모으기 → 구조화 → 자동 승인까지. */
async function autoAll() {
  const items = S.items || [];
  const body = `<p>${items.map((i) => `<b>${escapeHtml(i.label || i.no + "과목")}</b>`).join(" · ")}을 돌립니다.
      단계마다 사람 대신 <b>자동 승인</b>합니다.</p>
    <p>해설 모으기 → 노트 구조화(Claude) → 승인</p>
    <p><label><input type="checkbox" id="ol-auto-all" checked> <b>이어서 2부 끝까지 한 번에</b> —
      이론 요약 노트 → 요약반 → 종합반
      <select id="ol-auto-factor">${[2, 3, 4, 5].map((n) => `<option value="${n}"${n === 3 ? " selected" : ""}>${n}배</option>`).join("")}</select></label></p>
    <p class="muted">구조화 묶음당 4~5분 · 이론 편당 10~15분 · 강의 노트는 묶음마다 동시에. 끝까지면 몇 시간 걸립니다.
      창을 닫아도 서버에서 계속 돌고, 중간에 멈춰도 끝난 단계는 남습니다.</p>`;
  if (!(await confirmModal({ title: "2부를 자동으로 진행할까요?", body, ok: "자동 진행 시작" }))) return;
  const all = !!(document.querySelector("#ol-auto-all") || {}).checked;
  const factor = +((document.querySelector("#ol-auto-factor") || {}).value || 3);
  if (!all) { structure(items.map((i) => i.key), true); return; }
  try {
    const job = await api("/api/part2-auto", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: items.map((i) => i.key), factor, full: true }),
    });
    toast("2부 자동 진행을 시작했습니다 — 진행은 이 화면과 요약반·종합반 화면에서 보입니다.");
    follow(job.id, "단계");
  } catch (e) { toast(e.message, "err"); }
}

async function follow(id, unit) {
  const box = S.root.querySelector(".lc-log");
  box.classList.add("on");
  const clock = jobClock(S.root.querySelector(".lc-clock"), { unit, hintSec: 260 });
  const lines = [];
  let seen = -1;
  const fin = await pollJob(id, (j) => {
    (j.log && j.log.lines || []).forEach((l) => lines.push(typeof l === "string" ? l : (l.line || l.text || "")));
    box.textContent = lines.slice(-8).join("\n") || j.label;
    clock.update(j, lines);
    if (j.done_count !== seen) { seen = j.done_count; reload(); }
  });
  toast(fin && fin.status === "done" ? "끝났습니다." : ((fin && fin.error) || "실패했습니다"), fin && fin.status === "done" ? "" : "err");
  reload();
}

async function structure(keys, autoApprove = false) {
  try {
    const job = await api("/api/outline/structure", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ keys, approve: autoApprove }),
    });
    const box = S.root.querySelector(".lc-log");
    box.classList.add("on");
    // 과목당 약 4분 20초 — 컴활2급 1과목 해설 400개 실측(2026-11-01)
    const clock = jobClock(S.root.querySelector(".lc-clock"), { unit: "과목", hintSec: 260 });
    const lines = [];
    const fin = await pollJob(job.id, (j) => {
      (j.log && j.log.lines || []).forEach((l) => lines.push(typeof l === "string" ? l : (l.line || l.text || "")));
      box.textContent = lines.slice(-8).join("\n") || j.label;
      clock.update(j, lines);
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
