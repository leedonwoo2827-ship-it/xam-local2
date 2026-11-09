/* HTML 문제집 제작 (실기) — 회차마다 시험지 · 모범답안 해설 · 실습파일 · 대본을 07/mNN 에 굽고,
 * 종합본 영상용 녹화 대본(조작 단계 → lesson.yaml)을 뽑는다.
 *
 * ★ 실기 폴더에서 왼쪽 「HTML 문제집 제작」 이 여기로 온다(2026-11-09 계획). 필기 ebook.js 는 그대로.
 * ★ 실습파일은 1부 빌드 결과(06/practical)를 복사한다 — 빌드를 먼저 하세요.
 * ★ 녹화 대본: 종합본 영상 재정립(longform 대시보드 + 생산 허브 데스크톱 녹화)의 입력.
 *   허브의 엑셀 녹화 프로필은 허브 저장소 작업이라 아직 없다 — 여기서는 입력 모양만 맞춘다.
 */
"use strict";

import { $, api, el, toast, escapeHtml } from "./util.js";
import { pollJob } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const R = { ov: null, rounds: "1-10", busy: false, live: false };

export const meta = {
  title: () => "HTML 문제집 제작 (실기)",
  subtitle: () => "시험지 · 모범답안 해설(HTML·PDF) · 실습파일 · 대본 → 07/mNN · 종합본 녹화 대본",
  actions: () => [
    actionBtn("폴더 열기", () => openDir(0), { iconName: "folder" }),
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
  ],
};

export async function mount(root) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card"><div class="card-title">① 굽기 — 시험지·해설 HTML/PDF · 실습파일 · 문항 대본</div><div id="px-run"></div></div>
    <div class="card"><div class="card-title">② 종합본 녹화 대본 — 모범답안을 녹화 조작 단계로(문항마다 Claude 1회)</div><div id="px-rec"></div></div>
    <div class="card" id="px-logcard" hidden><div class="card-title">진행</div><div class="vd-env" id="px-head"></div>
      <pre class="log-pane" id="px-log" style="max-height:30vh"></pre></div>
    <div class="card"><div class="card-title">③ 회차별 결과</div><div id="px-rows"></div></div>`;
  root.appendChild(page);
  hydrateIcons(page);
  await load();
  if (R.ov?.running && !R.live) follow(R.ov.running);
}

async function load() {
  try { R.ov = await api(`/api/practical/ebook/overview?rounds=${encodeURIComponent(R.rounds)}`); }
  catch (e) { toast("불러오지 못했습니다: " + e.message, "err"); return; }
  renderRun(); renderRec(); renderRows();
}

function renderRun() {
  const box = $("#px-run"); if (!box) return;
  box.innerHTML = "";
  const f = el("div", "qz-foot");
  const inp = el("input", "input");
  inp.value = R.rounds; inp.style.minWidth = "200px";
  inp.addEventListener("change", () => { R.rounds = inp.value.trim() || "1-10"; load(); });
  const btn = el("button", "btn primary", R.busy ? "굽는 중…" : "굽기 실행");
  btn.type = "button"; btn.disabled = R.busy;
  btn.addEventListener("click", async () => {
    R.busy = true; renderRun();
    try {
      const r = await api("/api/practical/ebook", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rounds: inp.value.trim() || "1-10" }) });
      const bad = (r.built || []).filter((x) => x.error || (x.pdf_errors || []).length);
      toast(`${(r.built || []).length}회 구웠습니다` + (bad.length ? ` · 문제 ${bad.length}회` : ""), bad.length ? "err" : "");
    } catch (e) { toast("굽지 못했습니다: " + e.message, "err"); }
    R.busy = false; await load();
  });
  f.append(inp, btn);
  box.appendChild(f);
  box.appendChild(el("div", "field-hint", "회차당 10초 안팎(PDF 2개). 1부 빌드를 먼저 하면 실습파일과 새 그림이 같이 들어갑니다."));
}

function renderRec() {
  const box = $("#px-rec"); if (!box) return;
  box.innerHTML = "";
  const f = el("div", "qz-foot");
  const inp = el("input", "input");
  inp.value = "6-10"; inp.style.minWidth = "200px"; inp.title = "종합본은 6~10회(사용자 결정 2026-11-09)";
  const ow = el("label", "muted"); const cb = el("input"); cb.type = "checkbox";
  ow.append(cb, document.createTextNode(" 이미 뽑은 문항도 다시"));
  const btn = el("button", "btn primary", "녹화 대본 뽑기");
  btn.type = "button"; btn.disabled = R.live;
  btn.addEventListener("click", () => startRec(inp.value.trim() || "6-10", cb.checked));
  f.append(inp, btn, ow);
  box.appendChild(f);
  box.appendChild(el("div", "field-hint",
    "07/mNN/rec/ 에 문항마다 조작 단계(actions.json)와 녹화 허브용 lesson.yaml 을 씁니다. "
    + "종합본(6~10회)이 기본입니다. 문항 하나에 30초~1분, 10회(120문항)면 1~2시간입니다."));
}

function renderRows() {
  const box = $("#px-rows"); if (!box) return;
  box.innerHTML = "";
  const t = el("table", "data-table");
  t.innerHTML = "<thead><tr><th>회차</th><th>집필</th><th>1부 빌드</th><th>굽기</th><th>실습파일</th><th>녹화 대본</th><th></th></tr></thead>";
  const tb = el("tbody");
  for (const r of R.ov.rows || []) {
    const b = r.ebook || {};
    const tr = el("tr");
    tr.innerHTML = `<td><b>${String(r.round).padStart(2, "0")}회</b></td>`
      + `<td>${r.written ? '<span class="status-chip ok">완료</span>' : "—"}</td>`
      + `<td>${r.built ? '<span class="status-chip ok">완료</span>' : "—"}</td>`
      + `<td class="muted">${escapeHtml(b.built_at || "—")}${(b.pdf_errors || []).length ? ' <span class="status-chip err">PDF 실패</span>' : ""}</td>`
      + `<td class="muted">${(b.files || []).map(escapeHtml).join("<br>") || (b.built_at ? '<span class="status-chip warn">없음 — 1부 빌드 먼저</span>' : "")}</td>`
      + `<td class="muted">${r.rec ? r.rec + "문항" : "—"}</td><td></td>`;
    if (b.built_at) {
      const o = el("button", "btn sm", "폴더"); o.type = "button";
      o.addEventListener("click", () => openDir(r.round));
      const p = el("a", "btn sm", "인쇄본"); p.href = `/print/practical?rd=${r.round}`; p.target = "_blank";
      tr.lastChild.append(o, p);
    }
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  box.appendChild(t);
}

async function openDir(round) {
  try { await api(`/api/practical/ebook/open?round=${round || 0}`, { method: "POST" }); }
  catch (e) { toast("폴더를 열지 못했습니다: " + e.message, "err"); }
}

function logLine(text) {
  const c = $("#px-logcard"); if (c) c.hidden = false;
  const pre = $("#px-log"); if (!pre) return;
  pre.appendChild(el("span", null, text + "\n")); pre.scrollTop = pre.scrollHeight;
}

async function startRec(rounds, overwrite) {
  let job;
  try {
    job = await api("/api/practical/actions", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rounds, overwrite }) });
  } catch (e) { toast("시작하지 못했습니다: " + e.message, "err"); return; }
  logLine(`[녹화 대본] 시작 — ${job.total_count || "?"}문항`);
  await follow(job);
}

async function follow(job) {
  R.live = true; renderRec();
  const head = $("#px-head");
  const badge = el("span", "status-chip", "진행 중");
  const prog = el("span", "status-chip", "");
  const stop = el("button", "btn sm", "멈추기"); stop.type = "button";
  stop.addEventListener("click", async () => {
    try { await api(`/api/jobs/${job.id}/cancel`, { method: "POST" }); toast("지금 문항을 마치고 멈춥니다."); }
    catch (e) { toast("멈추지 못했습니다: " + e.message, "err"); }
  });
  if (head) { head.innerHTML = ""; head.append(badge, prog, stop); }
  logLine("");
  const final = await pollJob(job.id, (j) => {
    prog.textContent = `${j.done_count || 0} / ${j.total_count || 0}` + (j.current ? ` · ${j.current}` : "");
    (j.log?.lines || []).forEach((l) => logLine(l.trimEnd()));
  });
  R.live = false;
  const bad = final?.status === "error";
  badge.textContent = bad ? "오류" : "완료"; badge.className = "status-chip " + (bad ? "err" : "ok"); stop.remove();
  toast(bad ? "중단됐습니다." : "녹화 대본을 다 뽑았습니다.", bad ? "err" : "");
  await load();
}
