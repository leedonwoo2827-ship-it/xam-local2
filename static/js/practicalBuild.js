/* 1부 빌드 (실기) — 실습파일(문제·정답 xlsx) · 그림 · 검증.
 *
 * ★ 사용자 결정(2026-11-09): 실기 폴더에서는 「1부 빌드」 가 이 화면이다. 필기의 e-test 발행(객관식 전제)은 숨긴다.
 *   엑셀로 시트 자료를 깔아 문제 파일을 만들고, 모범답안 수식을 넣어 재계산한 정답 파일을 만든 뒤
 *   집필이 적은 결과값과 대조한다. 그림 설계는 PNG 로 새로 그려 원고에 넣는다.
 * ★ 「사람 확인」 = 서식·필터·피벗·차트처럼 값으로 대조할 수 없는 문항. 통과로 세지 않는다.
 */
"use strict";

import { $, api, el, toast, escapeHtml } from "./util.js";
import { pollJob } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const R = { ov: null, live: false, rounds: "1-10" };
const TONE = { "통과": "ok", "불일치": "err", "검증 불가(2019)": "warn", "사람 확인": "", "시트 없음": "err" };

export const meta = {
  title: () => "1부 빌드 (실기)",
  subtitle: () => "실습파일(문제·정답 xlsx) · 그림 · 검증 → 06/practical/",
  actions: () => [
    actionBtn("폴더 열기", () => openDir(0), { iconName: "folder" }),
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
  ],
};

export async function mount(root) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card">
      <div class="card-title">① 빌드 — 집필이 끝난 회차를 엑셀로 만듭니다</div>
      <div id="pb-run"></div>
    </div>
    <div class="card" id="pb-logcard" hidden>
      <div class="card-title">진행</div>
      <div class="vd-env" id="pb-head"></div>
      <pre class="log-pane" id="pb-log" style="max-height:30vh"></pre>
    </div>
    <div class="card">
      <div class="card-title">② 회차별 결과 — 회차를 누르면 문항별 대조를 봅니다</div>
      <div id="pb-rows"></div>
      <div id="pb-detail"></div>
    </div>`;
  root.appendChild(page);
  hydrateIcons(page);
  await load();
  if (R.ov?.running && !R.live) follow(R.ov.running);
}

async function load() {
  try { R.ov = await api(`/api/practical/build/overview?rounds=${encodeURIComponent(R.rounds)}`); }
  catch (e) { toast("불러오지 못했습니다: " + e.message, "err"); return; }
  renderRun(); renderRows();
}

function renderRun() {
  const box = $("#pb-run");
  if (!box) return;
  box.innerHTML = "";
  const f = el("div", "qz-foot");
  const inp = el("input", "input");
  inp.value = R.rounds; inp.style.minWidth = "200px"; inp.placeholder = "회차 — 예: 1-10";
  inp.addEventListener("change", () => { R.rounds = inp.value.trim() || "1-10"; load(); });
  const btn = el("button", "btn primary", "빌드 실행");
  btn.type = "button"; btn.disabled = R.live;
  btn.addEventListener("click", () => start(inp.value.trim() || "1-10"));
  f.append(inp, btn);
  box.appendChild(f);
  box.appendChild(el("div", "field-hint",
    "회차당 20초 안팎. 엑셀이 화면 없이 뒤에서 열렸다 닫힙니다(그동안 엑셀 창을 건드리지 마세요). "
    + "집필(문제1~4)이 다 끝난 회차만 빌드합니다. 다시 누르면 덮어씁니다. "
    + "그림: 표는 표로, 차트는 엑셀이 실제로 그립니다. 대화상자는 아직 설계를 담은 카드입니다(엑셀 화면 캡처는 다음 판). "
    + "★ 1~10회는 이미 빌드돼 있습니다 — 「문항 교정」 에서 고친 회차만 다시 누르면 됩니다."));
}

function renderRows() {
  const box = $("#pb-rows");
  if (!box) return;
  box.innerHTML = "";
  const t = el("table", "data-table");
  t.innerHTML = "<thead><tr><th>회차</th><th>집필</th><th>빌드</th><th>대조</th><th>그림</th><th>파일</th><th></th></tr></thead>";
  const tb = el("tbody");
  for (const r of R.ov.rows || []) {
    const tr = el("tr");
    const sum = Object.entries(r.summary || {}).map(([k, v]) =>
      `<span class="status-chip ${TONE[k] || ""}">${escapeHtml(k)} ${v}</span>`).join(" ");
    tr.innerHTML = `<td><b>${String(r.round).padStart(2, "0")}회</b></td>`
      + `<td>${r.written ? '<span class="status-chip ok">완료</span>' : '<span class="muted">—</span>'}</td>`
      + `<td class="muted">${escapeHtml((r.built_at || "").replace("T", " "))}</td>`
      + `<td>${sum || '<span class="muted">—</span>'}${(r.errors || []).length ? ` <span class="status-chip err">오류 ${r.errors.length}</span>` : ""}</td>`
      + `<td class="muted">${r.figures || ""}</td><td class="muted">${(r.files || []).map(escapeHtml).join("<br>")}</td><td></td>`;
    const cell = tr.lastChild;
    if (r.built_at) {
      const b1 = el("button", "btn sm", "대조 보기"); b1.type = "button";
      b1.addEventListener("click", () => detail(r));
      const b2 = el("button", "btn sm", "폴더"); b2.type = "button";
      b2.addEventListener("click", () => openDir(r.round));
      cell.append(b1, b2);
    }
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  box.appendChild(t);
}

function detail(r) {
  const box = $("#pb-detail");
  if (!box) return;
  const rows = (r.items || []).map((it) => {
    const fails = (it.fails || []).map((f) => `${escapeHtml(f.cell)}: 집필 ${escapeHtml(String(f.want))} ≠ 엑셀 ${escapeHtml(String(f.got))}`).join("<br>");
    return `<tr><td><b>${escapeHtml(it.id)}</b></td><td>${escapeHtml(it.sheet || "")}</td>`
      + `<td><span class="status-chip ${TONE[it.status] || ""}">${escapeHtml(it.status)}</span></td>`
      + `<td class="muted">${it.checked ? `${it.ok}/${it.checked}칸` : ""}</td><td class="small">${fails}</td></tr>`;
  }).join("");
  box.innerHTML = `<h3 style="margin:16px 0 6px">${String(r.round).padStart(2, "0")}회 문항별 대조</h3>`
    + `<table class="data-table"><thead><tr><th>문항</th><th>시트</th><th>결과</th><th>칸</th><th>어긋난 곳</th></tr></thead><tbody>${rows}</tbody></table>`
    + ((r.errors || []).length ? `<div class="field-hint" style="color:#b33">${r.errors.map(escapeHtml).join("<br>")}</div>` : "");
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function openDir(round) {
  try { await api(`/api/practical/build/open?round=${round || 0}`, { method: "POST" }); }
  catch (e) { toast("폴더를 열지 못했습니다: " + e.message, "err"); }
}

function logLine(text) {
  const c = $("#pb-logcard"); if (c) c.hidden = false;
  const pre = $("#pb-log"); if (!pre) return;
  pre.appendChild(el("span", null, text + "\n"));
  pre.scrollTop = pre.scrollHeight;
}

async function start(rounds) {
  let job;
  try {
    job = await api("/api/practical/build", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rounds }),
    });
  } catch (e) { toast("빌드를 시작하지 못했습니다: " + e.message, "err"); return; }
  logLine(`[빌드] 시작 — ${job.total_count || "?"}회`);
  await follow(job);
}

async function follow(job) {
  R.live = true;
  renderRun();
  const head = $("#pb-head");
  const badge = el("span", "status-chip", "진행 중");
  const prog = el("span", "status-chip", "");
  if (head) { head.innerHTML = ""; head.append(badge, prog); }
  logLine("");
  const final = await pollJob(job.id, (j) => {
    prog.textContent = `${j.done_count || 0} / ${j.total_count || 0}` + (j.current ? ` · ${j.current}` : "");
    (j.log?.lines || []).forEach((l) => logLine(l.trimEnd()));
  });
  R.live = false;
  const bad = final?.status === "error";
  badge.textContent = bad ? "오류" : "완료";
  badge.className = "status-chip " + (bad ? "err" : "ok");
  toast(bad ? "빌드가 중단됐습니다." : "빌드를 마쳤습니다.", bad ? "err" : "");
  await load();
}
