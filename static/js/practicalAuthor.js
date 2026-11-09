/* 실기 문제 집필 — 확정본(01/practical) 을 바탕으로 새 회차(02/practical/mNN)를 쓴다.
 *
 * ★ 필기 「문항 집필」 과 탭을 나눈다(2026-11-09 지시). 필기는 보기·정답 번호, 실기는
 *   시트 자료 · 작업 지시 · 모범답안 · 그림 설계를 쓴다.
 * ★ 버튼은 사람이 누른다. 묶음(문제1~4) 하나가 한 번의 호출이고, 멈춰도 쓴 묶음은 남는다 —
 *   다시 누르면 남은 묶음부터 잇는다.
 */
"use strict";

import { $, api, el, toast, escapeHtml } from "./util.js";
import { pollJob } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const PART = { 1: "기본작업", 2: "계산작업", 3: "분석작업", 4: "기타작업" };
const R = { ov: null, live: false, rounds: "1-10" };

export const meta = {
  title: () => "실기 문제 집필",
  subtitle: () => "확정본 1~5회 → 새 회차 원고(02/practical/) — 자료·지시사항·모범답안·그림 설계",
  actions: () => [actionBtn("새로고침", () => load(), { iconName: "refresh" })],
};

export async function mount(root) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card">
      <div class="card-title">① 바탕 — OCR 검수에서 확정한 회차</div>
      <div id="pa-src"><div class="empty">불러오는 중…</div></div>
    </div>
    <div class="card">
      <div class="card-title">② 집필 — 회차마다 문제1~4 묶음을 차례로 씁니다</div>
      <div id="pa-run"></div>
    </div>
    <div class="card" id="pa-logcard" hidden>
      <div class="card-title">진행</div>
      <div class="vd-env" id="pa-head"></div>
      <pre class="log-pane" id="pa-log" style="max-height:40vh"></pre>
    </div>
    <div class="card">
      <div class="card-title">③ 쓴 회차 — 문항을 누르면 원고를 봅니다</div>
      <div id="pa-rows"></div>
      <div id="pa-view"></div>
    </div>`;
  root.appendChild(page);
  hydrateIcons(page);
  await load();
  if (R.ov?.running && !R.live) follow(R.ov.running);
}

async function load() {
  try {
    R.ov = await api(`/api/practical/author/overview?rounds=${encodeURIComponent(R.rounds)}`);
  } catch (e) {
    const b = $("#pa-src");
    if (b) { b.innerHTML = ""; b.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message)); }
    return;
  }
  renderSrc(); renderRun(); renderRows();
}

function renderSrc() {
  const box = $("#pa-src");
  if (!box) return;
  box.innerHTML = "";
  const s = R.ov.sources || {};
  const ks = Object.keys(s);
  box.appendChild(el("pre", "pb-cmd", R.ov.src_dir || ""));
  box.appendChild(el("div", "or-row", ks.length
    ? ks.map((k) => `${String(k).padStart(2, "0")}회 ${s[k]}문항`).join(" · ")
    : "확정본이 없습니다 — OCR 검수에서 회차를 확정하세요."));
}

function renderRun() {
  const box = $("#pa-run");
  if (!box) return;
  box.innerHTML = "";
  const form = el("div", "qz-foot");
  const inp = el("input", "input");
  inp.value = R.rounds;
  inp.placeholder = "만들 회차 — 예: 1-10";
  inp.style.minWidth = "200px";
  inp.addEventListener("change", () => { R.rounds = inp.value.trim() || "1-10"; load(); });
  const ow = el("label", "muted");
  const cb = el("input");
  cb.type = "checkbox";
  ow.append(cb, document.createTextNode(" 이미 쓴 묶음도 다시 쓰기(덮어씀)"));
  const btn = el("button", "btn primary", "집필 실행");
  btn.type = "button";
  btn.disabled = R.live;
  btn.addEventListener("click", () => start(inp.value.trim() || "1-10", cb.checked));
  form.append(inp, btn, ow);
  box.appendChild(form);
  box.appendChild(el("div", "field-hint",
    "바탕 회차 = (회차−1)%5+1 — 01~05회는 함수 조합을 유지하고 표면을 새로, 06~10회는 함수 조합까지 바꿉니다. "
    + "묶음 하나에 몇 분 걸립니다(10회 = 40묶음). 창을 닫아도 서버에서 계속 돕니다. "
    + "그림은 새로 그릴 설계(표 값·차트 설정·대화상자 값)로 남고, 실제 그림은 다음 단계에서 엑셀로 그립니다."));
}

function renderRows() {
  const box = $("#pa-rows");
  if (!box) return;
  box.innerHTML = "";
  const t = el("table", "data-table");
  t.innerHTML = `<thead><tr><th>회차</th><th>바탕</th>${[1, 2, 3, 4].map((p) => `<th>${p} ${PART[p]}</th>`).join("")}<th>문항</th><th>비용</th></tr></thead>`;
  const tb = el("tbody");
  for (const r of R.ov.rows || []) {
    const tr = el("tr");
    tr.innerHTML = `<td><b>${String(r.round).padStart(2, "0")}회</b></td><td class="muted">${String(r.source_round).padStart(2, "0")}회</td>`
      + [1, 2, 3, 4].map((p) => `<td>${r.parts[p] ? '<span class="status-chip ok">완료</span>' : '<span class="muted">—</span>'}</td>`).join("")
      + `<td></td><td class="muted">${r.cost_usd ? "$" + r.cost_usd : ""}</td>`;
    const cell = tr.children[6];
    for (const stem of r.stems || []) {
      const [m, p, n] = stem.split("-").map(Number);
      const a = el("button", "btn sm", `${p}-${n === 0 ? "머리" : n}`);
      a.type = "button";
      a.addEventListener("click", () => view(m, p, n));
      cell.appendChild(a);
    }
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  box.appendChild(t);
}

async function view(m, p, n) {
  const box = $("#pa-view");
  if (!box) return;
  try {
    const r = await api(`/api/practical/author/item?round=${m}&part=${p}&no=${n}`);
    box.innerHTML = `<div class="field-hint">${escapeHtml(r.path)}</div>`;
    const pre = el("pre", "pb-cmd", r.md);
    pre.style.cssText = "white-space:pre-wrap;max-height:70vh;overflow:auto;font-size:14px;line-height:1.6";
    box.appendChild(pre);
    box.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { toast("원고를 열지 못했습니다: " + e.message, "err"); }
}

function logLine(text) {
  const c = $("#pa-logcard");
  if (c) c.hidden = false;
  const pre = $("#pa-log");
  if (!pre) return;
  pre.appendChild(el("span", null, text + "\n"));
  pre.scrollTop = pre.scrollHeight;
}

async function start(rounds, overwrite) {
  let job;
  try {
    job = await api("/api/practical/author", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rounds, overwrite }),
    });
  } catch (e) {
    toast("집필을 시작하지 못했습니다: " + e.message, "err");
    logLine("[집필] 시작 실패 — " + e.message);
    return;
  }
  logLine(`[집필] 시작 — ${job.total_count || "?"}묶음`);
  await follow(job);
}

async function follow(job) {
  R.live = true;
  renderRun();
  const head = $("#pa-head");
  const badge = el("span", "status-chip", "진행 중");
  const prog = el("span", "status-chip", "");
  const stop = el("button", "btn sm", "멈추기");
  stop.type = "button";
  stop.addEventListener("click", async () => {
    try { await api(`/api/jobs/${job.id}/cancel`, { method: "POST" }); toast("지금 묶음을 마치고 멈춥니다."); }
    catch (e) { toast("멈추지 못했습니다: " + e.message, "err"); }
  });
  logLine("");
  if (head) { head.innerHTML = ""; head.append(badge, prog, stop); }
  let seen = 0;
  const final = await pollJob(job.id, (j) => {
    prog.textContent = `${j.done_count || 0} / ${j.total_count || 0}` + (j.current ? ` · ${j.current}` : "");
    (j.log?.lines || []).forEach((l) => logLine(l.trimEnd()));
    if ((j.done_count || 0) !== seen) { seen = j.done_count || 0; load(); }
  });
  R.live = false;
  const bad = final?.status === "error";
  badge.textContent = bad ? "오류" : "완료";
  badge.className = "status-chip " + (bad ? "err" : "ok");
  stop.remove();
  toast(bad ? "집필이 중단됐습니다." : "집필을 마쳤습니다.", bad ? "err" : "");
  await load();
}
