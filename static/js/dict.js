/* 발음 사전 (v2) — #/dict
 *
 * backplate-studio 의 [발음 사전] 을 이 앱으로 가져왔다(사전 318개도 합쳤다 — 단행본·시험요약
 * 위주라 이 앱의 문항 영상·강의 노트 용어는 여기서 더 쌓는다).
 *
 *   왼쪽  아직 없는 말   문항 번들 낭독 + 요약반·종합반 강의 노트 자막에 나오는데 사전에 없는 영문.
 *                        많이 나온 순. 지금 어떻게 읽히는지(낱자 음역)와 나온 자리를 같이 보인다.
 *   오른쪽 사전          **이 앱 사전 하나**(pronunciation_map.yaml · 300여 개가 목표) — 기본.
 *                        품목 사전(exams/<pd>.json)은 기존 문항 영상용으로 뒤 탭에 남긴다.
 *
 * ★ 발음대본은 이 앱에서 끝낸다. 여기 넣은 말은 ② 낭독대본(강의 노트)과 문항 영상 합성에
 *   그대로 걸린다. 자막에는 걸리지 않는다(자막은 원문).
 * ★ 바닥 화면이다 — 입력칸이 있는 화면은 Esc 로 닫히는 패널에 두지 않는다.
 */
"use strict";

import { api, el, escapeHtml, toast } from "./util.js";
import { pollJob } from "./store.js";

const S = { root: null, d: null, scope: "common", filter: "", recent: [], plan: null };

export const meta = {
  title: "발음 사전",
  subtitle: "영문을 한국어 소리로 — 여기 넣으면 낭독대본과 영상 합성에 그대로 반영됩니다. 자막은 원문 그대로입니다.",
};

export async function mount(root) {
  S.root = root;
  const page = el("div", "page dc-page");
  page.innerHTML = `<div class="card dc-flow"></div><div class="dc-grid"><div class="card dc-miss"></div><div class="card dc-dict"></div></div>`;
  root.appendChild(page);
  await reload();
}

async function reload() {
  S.d = await api("/api/render/lexicon?notes=1");
  drawFlow();
  drawMissing();
  drawDict();
}

/* ── 넣기 → 적용 → 재굽기 ── */
function drawFlow() {
  const box = S.root.querySelector(".dc-flow");
  box.innerHTML = "";
  const head = el("div", "dc-h");
  head.innerHTML = `<b>① 넣기 → ② 적용 → ③ 재굽기</b><span class="muted">${S.recent.length
    ? `이번에 넣은 말 ${S.recent.length}개: ${escapeHtml(S.recent.slice(-8).join(", "))}` : "넣은 말이 없으면 사전 전체로 적용합니다"}</span>`;
  box.appendChild(head);
  const row = el("div", "dc-add");
  const ap = el("button", "btn sm primary", "② 적용 — 강의 노트 낭독에 넣기");
  ap.type = "button";
  ap.addEventListener("click", applyDict);
  const rb = el("button", "btn sm", "③ 재굽기 — 미리듣기 · 문항 씬 음성");
  rb.type = "button";
  rb.disabled = !S.plan;
  rb.addEventListener("click", rebake);
  row.append(ap, rb);
  if (S.plan) {
    const n = S.plan.notes.reduce((a, x) => a + x.ids.length, 0);
    row.appendChild(el("span", "muted", `낭독이 바뀐 장 ${n}개 · 다시 구울 문항 씬 ${S.plan.scenes.length}개`));
  }
  box.appendChild(row);
  box.appendChild(el("div", "lc-log", ""));
}

async function applyDict() {
  try {
    S.plan = await api("/api/lecture/dict/apply", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ terms: S.recent }) });
    const n = S.plan.notes.reduce((a, x) => a + x.ids.length, 0);
    toast(`적용했습니다 — 낭독이 바뀐 장 ${n}개, 다시 구울 문항 씬 ${S.plan.scenes.length}개`);
    drawFlow();
  } catch (e) { toast(e.message, "err"); }
}

async function rebake() {
  if (!S.plan) return;
  try {
    const job = await api("/api/lecture/dict/rebake", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(S.plan) });
    const log = S.root.querySelector(".dc-flow .lc-log");
    log.classList.add("on");
    const lines = [];
    const fin = await pollJob(job.id, (j) => {
      (j.log && j.log.lines || []).forEach((l) => lines.push(typeof l === "string" ? l : (l.line || l.text || "")));
      log.textContent = lines.slice(-6).join("\n") || j.label;
    });
    toast(fin && fin.status === "done" ? "다시 구웠습니다. 바뀐 장은 듣기 검수에서 다시 들어 주세요." : "실패했습니다", fin && fin.status === "done" ? "" : "err");
    S.recent = []; S.plan = null;
    drawFlow();
  } catch (e) { toast(e.message, "err"); }
}

function drawMissing() {
  const box = S.root.querySelector(".dc-miss");
  const c = S.d.candidates || [];
  box.innerHTML = `<div class="dc-h"><b>아직 없는 말</b><span class="muted">${c.length}종 · 문항 낭독 + 강의 노트 자막</span></div>`;
  if (!c.length) { box.appendChild(el("div", "empty", "사전에 없는 영문이 없습니다.")); return; }
  const list = el("div", "dc-list");
  c.slice(0, 200).forEach((it) => {
    const row = el("div", "dc-row");
    row.innerHTML = `<div class="dc-term"><b>${escapeHtml(it.term)}</b><span class="dc-n">${it.count}회</span></div>
      <div class="dc-now muted">지금: ${escapeHtml(it.now)}</div>
      <div class="dc-where muted">${escapeHtml(it.where || "")}</div>`;
    const f = el("div", "dc-add");
    const inp = el("input");
    inp.placeholder = "소리 (예: 크리스프)";
    const sel = el("select");
    [["common", "이 앱 사전"], ["product", "품목"]].forEach(([v, t]) => { const o = el("option", null, t); o.value = v; sel.appendChild(o); });
    const b = el("button", "btn sm primary", "넣기");
    b.type = "button";
    const go = () => save(it.term, inp.value, sel.value);
    b.addEventListener("click", go);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
    f.append(inp, sel, b);
    row.appendChild(f);
    list.appendChild(row);
  });
  box.appendChild(list);
}

function drawDict() {
  const box = S.root.querySelector(".dc-dict");
  const prod = (S.d.product || {}).rules || {};
  const common = S.d.rules || {};
  const rules = S.scope === "product" ? prod : common;
  box.innerHTML = `<div class="dc-h"><b>사전</b>
    <span class="dc-tabs">
      <button type="button" class="dc-tab ${S.scope === "common" ? "on" : ""}" data-s="common">이 앱 사전 ${Object.keys(common).length}</button>
      <button type="button" class="dc-tab ${S.scope === "product" ? "on" : ""}" data-s="product">품목(문항 영상) · ${escapeHtml((S.d.product || {}).label || "")} ${Object.keys(prod).length}</button>
    </span></div>
    <div class="muted dc-path">${escapeHtml(S.scope === "product" ? (S.d.product || {}).path || "" : S.d.path || "")}</div>`;
  box.querySelectorAll(".dc-tab").forEach((t) => t.addEventListener("click", () => { S.scope = t.dataset.s; drawDict(); }));
  const q = el("input", "dc-filter");
  q.placeholder = "찾기";
  q.value = S.filter;
  q.addEventListener("input", () => { S.filter = q.value; fill(); });
  const add = el("div", "dc-add");
  const k = el("input"); k.placeholder = "말 (예: DECODE)";
  const v = el("input"); v.placeholder = "소리 (예: 디코드)";
  const b = el("button", "btn sm primary", "추가");
  b.type = "button";
  b.addEventListener("click", () => save(k.value, v.value, S.scope));
  add.append(k, v, b);
  box.append(q, add);
  const tbl = el("div", "dc-table");
  box.appendChild(tbl);
  function fill() {
    tbl.innerHTML = "";
    const f = S.filter.trim().toLowerCase();
    Object.keys(rules).sort((a, b2) => a.localeCompare(b2)).forEach((key) => {
      if (f && !key.toLowerCase().includes(f) && !String(rules[key]).includes(f)) return;
      const row = el("div", "dc-trow");
      const val = el("input");
      val.value = rules[key];
      const ok = el("button", "btn sm", "고침");
      ok.type = "button";
      ok.addEventListener("click", () => save(key, val.value, S.scope));
      const del = el("button", "btn sm", "지움");
      del.type = "button";
      del.addEventListener("click", () => remove(key, S.scope));
      row.append(el("b", "dc-k", key), val, ok, del);
      tbl.appendChild(row);
    });
  }
  fill();
}

async function save(term, say, scope) {
  term = (term || "").trim(); say = (say || "").trim();
  if (!term || !say) { toast("말과 소리를 둘 다 적으세요.", "err"); return; }
  try {
    await api("/api/render/lexicon", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ term, say, scope }) });
    toast(`${term} → ${say} (${scope === "common" ? "이 앱 사전" : "품목"})`);
    if (!S.recent.includes(term)) S.recent.push(term);
    S.plan = null;
    reload();
  } catch (e) { toast(e.message, "err"); }
}

async function remove(term, scope) {
  try {
    await api("/api/render/lexicon", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ term, scope, remove: true }) });
    reload();
  } catch (e) { toast(e.message, "err"); }
}
