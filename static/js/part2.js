/* 2부 현황판 — 행 = 묶음(과목) · 열 = 해설 구조화 · 이론 요약 · 요약반 · 종합반.
 *
 * ★ 2026-11-10 지시: "2부를 대시보드처럼 4칸으로" · "앞에 체크박스를 둬서 세로로도 진행하고 순차(1-4) 진행도".
 *   - 행 앞 체크박스 = 돌릴 묶음, 열 머리 체크박스 = 돌릴 단계. 다 고르면 전체 진행(구조화 → 이론 → 요약반 → 종합반).
 *   - 한 잡(/api/part2-auto)이 단계 순서대로 돈다. 이미 승인된 목차·있는 요약노트·승인된 강의 단계는 건너뛴다
 *     (「이미 된 것도 다시」 를 켜면 구조화·이론은 다시 만든다).
 *   - 칸을 누르면 그 단계의 상세 화면(고치는 곳)으로 간다. 이 화면은 보고 · 고르고 · 돌리는 곳이다.
 *   - 화면을 떠났다 와도 돌고 있는 잡의 로그·타이머가 다시 붙는다.
 */
"use strict";

import { $, api, el, toast, escapeHtml, confirmModal } from "./util.js";
import { pollJob, getPref, setPref } from "./store.js";
import { actionBtn } from "./panel.js";
import { jobClock } from "./jobclock.js";

const COLS = [
  { key: "outline", label: "해설 구조화", href: (k) => `#/outline/${k}` },
  { key: "theory", label: "이론 요약 노트", href: (k) => `#/summary/${k}` },
  { key: "summary", label: "요약반 강의 노트", href: (k) => `#/lecture/summary/${k}` },
  { key: "full", label: "종합반 강의 노트", href: (k) => `#/lecture/full/${k}` },
];
const S = { root: null, data: null, rows: new Set(), cols: new Set(COLS.map((c) => c.key)), watching: null };

export const meta = {
  title: () => "2부 현황판",
  subtitle: () => "행 = 묶음 · 열 = 단계. 체크한 칸만 돌립니다 — 다 체크하면 구조화 → 이론 → 요약반 → 종합반 전체 진행.",
  actions: () => [
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
    actionBtn("체크한 것 진행", () => run(), { primary: true, iconName: "sparkles" }),
  ],
};

export async function mount(root) {
  S.root = root;
  const saved = getPref("part2Cols", null);
  if (Array.isArray(saved) && saved.length) S.cols = new Set(saved);
  const page = el("div", "page");
  page.innerHTML = `<div class="card"><div id="p2-board"><div class="empty">불러오는 중…</div></div>
      <div class="qz-foot" id="p2-opts"></div></div>
    <div class="card"><div class="card-title">진행</div><div class="lc-clock" id="p2-clock"></div>
      <pre class="log-pane" id="p2-log" style="max-height:34vh">돌고 있는 작업이 없습니다.</pre></div>`;
  root.appendChild(page);
  await load();
  if (S.data?.running?.id) follow(S.data.running.id);
}

async function load() {
  try { S.data = await api("/api/part2/board"); } catch (e) { toast("불러오지 못했습니다: " + e.message, "err"); return; }
  if (!S.rows.size) (S.data.rows || []).forEach((r) => S.rows.add(r.key));
  draw();
}

const TONE = { approved: "#dff3e4", done: "#fff3c4", partial: "#fff3c4", todo: "#fff", running: "#e3ecff", error: "#fde2e1" };

function runningCell(key, col) {
  const r = S.data?.running;
  if (!r) return "";
  const hit = (list) => (list || []).some((u) => {
    const [k, a] = String(u).split(":");
    return k === key && ((a || "outline") === col);
  });
  return hit(r.running) ? "running" : hit(r.errors) ? "error" : "";
}

function draw() {
  const box = $("#p2-board");
  if (!box) return;
  box.innerHTML = "";
  const t = el("table", "data-table");
  t.style.cssText = "width:100%;table-layout:fixed";
  const hr = el("tr");
  const allRows = el("input"); allRows.type = "checkbox";
  allRows.checked = (S.data.rows || []).every((r) => S.rows.has(r.key));
  allRows.title = "묶음 전부";
  allRows.addEventListener("change", () => { (S.data.rows || []).forEach((r) => (allRows.checked ? S.rows.add(r.key) : S.rows.delete(r.key))); draw(); });
  const th0 = el("th"); th0.style.width = "190px";
  th0.append(allRows, document.createTextNode(" 묶음"));
  hr.appendChild(th0);
  for (const c of COLS) {
    const th = el("th");
    const cb = el("input"); cb.type = "checkbox"; cb.checked = S.cols.has(c.key);
    cb.addEventListener("change", () => { cb.checked ? S.cols.add(c.key) : S.cols.delete(c.key); setPref("part2Cols", [...S.cols]); draw(); });
    th.append(cb, document.createTextNode(" " + c.label));
    hr.appendChild(th);
  }
  const thead = el("thead"); thead.appendChild(hr); t.appendChild(thead);
  const tb = el("tbody");
  for (const r of S.data.rows || []) {
    const tr = el("tr");
    const td0 = el("td");
    const cb = el("input"); cb.type = "checkbox"; cb.checked = S.rows.has(r.key);
    cb.addEventListener("change", () => { cb.checked ? S.rows.add(r.key) : S.rows.delete(r.key); draw(); });
    td0.append(cb, document.createTextNode(" "), el("b", null, `${r.label || r.no + "과목"} · ${r.name || ""}`));
    tr.appendChild(td0);
    for (const c of COLS) {
      const cell = r.cells[c.key] || { state: "todo", text: "" };
      const live = runningCell(r.key, c.key);
      const st = live || cell.state;
      const td = el("td");
      const on = S.rows.has(r.key) && S.cols.has(c.key);
      td.style.cssText = `background:${TONE[st] || "#fff"};cursor:pointer;padding:8px 10px;vertical-align:top;${on ? "outline:2px solid #c0392b;outline-offset:-3px;" : ""}`;
      td.title = "누르면 이 단계 화면으로";
      td.innerHTML = `<div style="font-weight:700">${live === "running" ? "◐ 진행 중" : live === "error" ? "✕ 오류"
        : st === "approved" ? "● 완료" : st === "todo" ? "○ 없음" : "◑ 일부"}</div>`
        + `<div class="muted" style="font-size:12px">${escapeHtml(cell.text || "")}${cell.slides ? ` · ${cell.slides}장` : ""}</div>`;
      td.addEventListener("click", () => { location.hash = c.href(r.key); });
      if (st === "approved" || st === "partial" || st === "done") {
        // ★ 완료(·일부)된 칸에는 결과 폴더 열기 단추(2026-11-10 지시)
        const ob = el("button", "btn sm", "폴더");
        ob.type = "button";
        ob.style.marginTop = "4px";
        ob.addEventListener("click", async (e) => {
          e.stopPropagation();
          try { await api(`/api/part2/open?col=${c.key}&key=${encodeURIComponent(r.key)}`, { method: "POST" }); }
          catch (er) { toast("폴더를 열지 못했습니다: " + er.message, "err"); }
        });
        td.appendChild(ob);
      }
      tr.appendChild(td);
    }
    tb.appendChild(tr);
  }
  t.appendChild(tb);
  box.appendChild(t);
  drawOpts();
}

function drawOpts() {
  const box = $("#p2-opts");
  if (!box) return;
  box.innerHTML = "";
  const f = el("select", "input"); f.id = "p2-factor"; f.style.width = "auto";
  f.innerHTML = [2, 3, 4, 5].map((n) => `<option value="${n}"${n === 3 ? " selected" : ""}>종합반 ${n}배</option>`).join("");
  const rl = el("label", "muted"); const rd = el("input"); rd.type = "checkbox"; rd.id = "p2-redo";
  rl.append(rd, document.createTextNode(" 이미 된 것도 다시(구조화·이론)"));
  const n = [...S.rows].length * [...S.cols].length;
  const btn = el("button", "btn primary", `체크한 ${n}칸 진행`);
  btn.type = "button"; btn.disabled = !n || !!S.watching;
  btn.addEventListener("click", () => run());
  box.append(btn, f, rl);
  box.appendChild(el("span", "field-hint qz-foot-hint",
    "단계는 언제나 구조화 → 이론 → 요약반 → 종합반 순서로 돕니다. 이미 된 칸은 건너뜁니다. 강의 노트는 묶음마다 동시에 돕니다."));
}

async function run() {
  const keys = (S.data?.rows || []).map((r) => r.key).filter((k) => S.rows.has(k));
  const stages = COLS.map((c) => c.key).filter((k) => S.cols.has(k));
  if (!keys.length || !stages.length) { toast("묶음과 단계를 하나 이상 체크하세요.", "err"); return; }
  const names = (S.data.rows || []).filter((r) => S.rows.has(r.key)).map((r) => r.label || r.key);
  const cl = COLS.filter((c) => S.cols.has(c.key)).map((c) => c.label);
  const redo = !!($("#p2-redo") || {}).checked;
  const factor = +(($("#p2-factor") || {}).value || 3);
  if (!(await confirmModal({
    title: "체크한 칸을 진행할까요?",
    body: `<p><b>${names.map(escapeHtml).join(" · ")}</b></p><p>${cl.map(escapeHtml).join(" → ")}</p>`
      + `<p class="muted">단계마다 사람 대신 자동 승인합니다.${redo ? " 구조화·이론은 이미 있어도 다시 만듭니다." : " 이미 된 칸은 건너뜁니다."}
         창을 닫아도 서버에서 계속 돌고, 중간에 멈춰도 끝난 단계는 남습니다.</p>`,
    ok: "진행 시작",
  }))) return;
  try {
    const job = await api("/api/part2-auto", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys, stages, factor, redo }) });
    toast("시작했습니다.");
    follow(job.id);
  } catch (e) { toast(e.message, "err"); }
}

async function follow(id) {
  if (S.watching === id) return;
  S.watching = id;
  drawOpts();
  const box = $("#p2-log");
  const clock = jobClock($("#p2-clock"), { unit: "단계" });
  const lines = [];
  let seen = -1;
  const fin = await pollJob(id, (j) => {
    (j.log && j.log.lines || []).forEach((l) => lines.push(typeof l === "string" ? l : (l.line || l.text || "")));
    if (box) box.textContent = lines.slice(-14).join("\n") || j.label;
    clock.update(j, lines);
    if (j.done_count !== seen) { seen = j.done_count; load(); }
  });
  S.watching = null;
  toast(fin && fin.status === "done" ? "끝났습니다." : ((fin && fin.error) || "멈췄습니다"), fin && fin.status === "done" ? "" : "err");
  load();
}
