/* 실기 OCR — 작업형(컴활 엑셀·액세스) 트랙의 입구.
 *
 * ★ 필기 OCR(ocrrun.js)과 화면을 나눈 이유: 필기는 「문제문 + 보기 + 정답 번호」 를 읽지만,
 *   실기는 「지시사항 + 결과 그림 + 실습 파일」 이고 정답이 수식·코드·대화상자 설정값이다.
 *   필기의 ② 판독을 실기 쪽에 돌리면 보기를 찾느라 엉뚱하게 읽는다.
 *
 *   ① 스캔 뜨기   — 필기와 같은 /api/ocr/render (PDF → 페이지 이미지는 시험 종류와 무관)
 *   ② 실기 판독   — 쪽마다 문제/정답 종류·회차·문항(또는 정답)을 읽는다. 쪽 범위를 고를 수 있다
 *   ③ 검수        — 별도 화면(practicalReview.js). 필기처럼 실행과 검수를 나눈다
 *
 * ★ 버튼은 사람이 누른다(2026-11-08 지시). 이 화면이 스스로 판독을 시작하지 않는다.
 */
"use strict";

import { $, api, el, toast } from "./util.js";
import { pollJob } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const R = { plan: null, ov: null, live: false, view: null };

export const meta = {
  title: () => "실기 OCR",
  subtitle: () => "작업형(엑셀·액세스) — 스캔 뜨기 → 실기 판독 → 검수",
  actions: () => [
    actionBtn("필기 OCR 로", () => (location.hash = "#/ocr-run"), { iconName: "folder" }),
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
  ],
};

export async function mount(root) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card">
      <div class="card-title">① 스캔 뜨기 — 00/ 의 PDF 를 페이지 이미지로</div>
      <div id="pr-render"><div class="empty">불러오는 중…</div></div>
    </div>
    <div class="card">
      <div class="card-title">② 실기 판독 — 쪽마다 문제/정답 · 회차 · 지시사항(또는 정답)을 읽습니다</div>
      <div id="pr-read"><div class="empty">불러오는 중…</div></div>
    </div>
    <div class="card" id="pr-logcard" hidden>
      <div class="card-title">진행</div>
      <div class="vd-env" id="pr-head"></div>
      <pre class="log-pane" id="pr-log" style="max-height:40vh"></pre>
    </div>
    <div class="card">
      <div class="card-title">③ 검수 — 문항마다 지시사항과 정답을 짝지어 봅니다</div>
      <div id="pr-next"></div>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);
  await load();
  // 화면을 다시 열었을 때 돌고 있는 판독이 있으면 다시 붙는다
  if (R.ov?.running && !R.live) follow(R.ov.running);
}

async function load() {
  try {
    [R.plan, R.ov] = await Promise.all([api("/api/ocr/render/plan"), api("/api/practical/overview")]);
  } catch (e) {
    const b = $("#pr-render");
    if (b) { b.innerHTML = ""; b.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message)); }
    return;
  }
  renderStep1();
  renderStep2();
  renderNext();
}

function renderNext() {
  const box = $("#pr-next");
  if (!box) return;
  box.innerHTML = "";
  // PDF 가 여럿이면 읽은 쪽을 모두 더한다(검수 화면이 PDF 를 모두 보여 준다)
  const all = R.ov?.srcs || [];
  const s = all.length ? { read: all.reduce((a, x) => a + (x.read || 0), 0) } : null;
  const foot = el("div", "qz-foot");
  const b = el("button", "btn primary", "검수로 →");
  b.type = "button";
  b.disabled = !s || !s.read;
  b.addEventListener("click", () => (location.hash = "#/practical-review"));
  foot.appendChild(b);
  foot.appendChild(el("span", "field-hint qz-foot-hint",
    s && s.read ? `판독한 ${s.read}쪽을 문항 카드로 봅니다. 왼쪽 메뉴 「OCR 검수」 도 같은 화면입니다.`
      : "② 판독을 먼저 하세요."));
  box.appendChild(foot);
}

/* ── ① 스캔 뜨기 ─────────────────────────────────────────────────────── */
function renderStep1() {
  const box = $("#pr-render");
  if (!box) return;
  box.innerHTML = "";
  const p = R.plan || {};
  if (!p.exists) {
    box.appendChild(el("div", "empty", p.error || "00/ 에 PDF 가 없습니다."));
    return;
  }
  box.appendChild(el("pre", "pb-cmd", p.pdf_dir || ""));
  const done = new Map((R.ov?.srcs || []).map((s) => [String(s.src), s.total]));
  for (const it of p.items || []) {
    const row = el("div", "or-row");
    row.append(el("b", null, it.file || it.src));
    row.appendChild(el("span", "muted",
      done.has(String(it.src)) ? `→ 이미 뜸 · ${done.get(String(it.src))}쪽` : "→ 아직 안 뜸"));
    box.appendChild(row);
  }
  // 00/ 의 PDF 를 전부 떴으면 누를 일이 없다 — 단추를 잠근다(새 PDF 가 들어오면 다시 풀린다).
  const allDone = (p.items || []).length > 0
    && (p.items || []).every((it) => done.has(String(it.src)));
  const foot = el("div", "qz-foot");
  const btn = el("button", "btn primary", allDone ? "스캔 완료" : "스캔 뜨기 실행");
  btn.type = "button";
  btn.disabled = allDone;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    logLine("[스캔] 시작합니다 — 이미 뜬 PDF 는 건너뜁니다. 쪽이 많으면 몇 분 걸립니다.");
    try {
      const r = await api("/api/ocr/render", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
      });
      (r.log || []).forEach((l) => logLine(l.trimEnd()));
      logLine(`[스캔] 끝 — ${r.pages}쪽`);
      toast(`스캔 ${r.pages}쪽을 떴습니다.`);
      await load();
    } catch (e) {
      logLine("[스캔] 실패 — " + e.message);
      toast("스캔을 뜨지 못했습니다: " + e.message, "err");
    } finally {
      btn.disabled = allDone;
    }
  });
  foot.appendChild(btn);
  foot.appendChild(el("span", "field-hint qz-foot-hint", allDone
    ? "00/ 의 PDF 를 모두 떴습니다. 새 PDF 를 넣으면 다시 켜집니다."
    : "필기와 같은 작업입니다. 품목당 한 번이면 됩니다."));
  box.appendChild(foot);
}

/* ── ② 실기 판독 ─────────────────────────────────────────────────────── */
function renderStep2() {
  const box = $("#pr-read");
  if (!box) return;
  box.innerHTML = "";
  const srcs = R.ov?.srcs || [];
  if (!srcs.length) {
    box.appendChild(el("div", "empty", "뜬 스캔이 없습니다. 위 ① 을 먼저 누르세요."));
    return;
  }
  // ★ PDF 가 여럿이다(컴활1급 기출 1~4회 = PDF 4개). PDF 마다 체크박스 — 고른 것을 차례로 판독한다.
  //   서버 판독은 한 번에 하나라서(read.start 의 잠금) 화면이 앞 PDF 가 끝나면 다음 PDF 를 건다.
  const picks = [];
  for (const s of srcs) {
    const todo = s.total - s.read;
    const row = el("label", "or-row");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = todo > 0;
    cb.disabled = R.live;
    picks.push({ src: s.src, cb });
    row.append(cb, el("b", null, ` ${s.src}.pdf`), el("span", "muted",
      ` · 전체 ${s.total}쪽 · 판독 ${s.read}쪽 · 남은 ${todo}쪽`
      + (s.cost_usd ? ` · 지금까지 $${s.cost_usd}` : "")));
    box.appendChild(row);
  }

  const form = el("div", "qz-foot");
  const inp = el("input", "input");
  inp.placeholder = "쪽 범위 — 예: 1-15 (비우면 남은 쪽 전부 · 고른 PDF 모두에 같이 적용)";
  inp.style.minWidth = "280px";
  const ow = el("label", "muted");
  const cb = el("input");
  cb.type = "checkbox";
  ow.append(cb, document.createTextNode(" 이미 읽은 쪽도 다시 읽기(덮어씀)"));
  const btn = el("button", "btn primary", "판독 실행");
  btn.type = "button";
  btn.disabled = R.live;
  btn.addEventListener("click", () => {
    const list = picks.filter((p) => p.cb.checked).map((p) => p.src);
    if (!list.length) { toast("판독할 PDF 를 고르세요.", "err"); return; }
    startQueue(list, inp.value.trim(), cb.checked);
  });
  form.append(inp, btn, ow);
  box.appendChild(form);
  box.appendChild(el("div", "field-hint",
    "한 쪽에 40~60초쯤 걸립니다. 고른 PDF 를 위에서부터 차례로 읽습니다. "
    + "이 창을 닫으면 지금 PDF 까지만 서버에서 마저 돌고 다음 PDF 로는 넘어가지 않습니다 — 다시 열어 판독 실행을 누르면 남은 쪽부터 이어 갑니다."));
}

/* 고른 PDF 들을 차례로 — 하나 끝나면 다음. 오류·멈춤이면 거기서 선다. */
async function startQueue(list, pages, overwrite) {
  for (let i = 0; i < list.length; i++) {
    logLine(`[판독] ${i + 1}/${list.length} — ${list[i]}.pdf`);
    const ok = await startRead(list[i], pages, overwrite);
    if (ok === "skip") continue;
    if (!ok) { logLine("[판독] 여기서 멈춥니다 — 남은 PDF 는 다시 판독 실행을 누르면 이어 갑니다."); return; }
  }
  if (list.length > 1) toast(`PDF ${list.length}개 판독을 마쳤습니다.`);
}

function logCard() {
  const c = $("#pr-logcard");
  if (c) c.hidden = false;
  return $("#pr-log");
}

function logLine(text) {
  const pre = logCard();
  if (!pre) return;
  pre.appendChild(el("span", null, text + "\n"));
  pre.scrollTop = pre.scrollHeight;
}

async function startRead(src, pages, overwrite, textOnly = false) {
  let job;
  try {
    job = await api("/api/practical/read", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src, pages, overwrite, text_only: textOnly }),
    });
  } catch (e) {
    // 「판독할 쪽이 없습니다」 = 이 PDF 는 이미 다 읽음 — 다음 PDF 로 넘어간다
    if (/판독할 쪽이 없습니다/.test(e.message)) { logLine(`[판독] ${src}.pdf — 이미 다 읽었습니다. 건너뜁니다.`); return "skip"; }
    toast("판독을 시작하지 못했습니다: " + e.message, "err");
    logLine("[판독] 시작 실패 — " + e.message);
    return false;
  }
  logLine(`[판독] 시작 — ${src}.pdf ${job.total_count || "?"}쪽`);
  const final = await follow(job);
  // 멈추기를 눌렀으면 잡은 done 으로 끝나도 다음 PDF 로 넘어가지 않는다
  return final?.status === "done" && !final?.cancel_requested;
}

async function follow(job) {
  R.live = true;
  renderStep2();
  const head = $("#pr-head");
  const badge = el("span", "status-chip", "진행 중");
  const prog = el("span", "status-chip", "");
  const stop = el("button", "btn sm", "멈추기");
  stop.type = "button";
  stop.addEventListener("click", async () => {
    try { await api(`/api/jobs/${job.id}/cancel`, { method: "POST" }); toast("지금 쪽을 마치고 멈춥니다."); }
    catch (e) { toast("멈추지 못했습니다: " + e.message, "err"); }
  });
  logCard();
  if (head) { head.innerHTML = ""; head.append(badge, prog, stop); }
  const final = await pollJob(job.id, (j) => {
    prog.textContent = `${j.done_count || 0} / ${j.total_count || 0}` + (j.current ? ` · ${j.current}` : "");
    (j.log?.lines || []).forEach((l) => logLine(l.trimEnd()));
  });
  R.live = false;
  const bad = final?.status === "error";
  badge.textContent = bad ? "오류" : "완료";
  badge.className = "status-chip " + (bad ? "err" : "ok");
  stop.remove();
  toast(bad ? "판독이 중단됐습니다." : "판독을 마쳤습니다.", bad ? "err" : "");
  await load();
  return final;
}
