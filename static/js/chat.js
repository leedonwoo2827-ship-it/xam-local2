/* 우측 채팅 패널 (v2) — Claude 가 앱 기능을 도구로 부르고, 쓰기는 사람이 승인한다
 *
 * ★ 라우트가 아니다. 부팅 때 **한 번만** 마운트한다(shell.js). 그래서 가운데 화면을
 *   옮겨도 대화·스트리밍·승인 대기가 그대로 산다 — 2층 구조에서 바탕이 언마운트되지
 *   않는 것과 같은 이유다.
 * ★ 부유 패널이 열려도 이 컬럼은 inert 가 아니다(panel.js setBaseInert 가 .rail ·
 *   .content 만 잠근다). 목록 창을 띄워 둔 채 "이거 왜 노랗지?" 를 물을 수 있어야 한다.
 *
 * ★ 기본 화면은 채팅이 아니라 **작업 현황판**이다(사용자 지시 2026-10-24) — 지금 하는 일 ·
 *   고친 뒤 반영할 것 · 다음에 할 일. 모델을 부르지 않는다(/api/chat/status). 시장조사처럼
 *   진짜 대화가 필요할 때만 [대화] 를 누르거나 입력창에 쓰면 채팅으로 바뀐다. 실전에서는
 *   렌더를 CLI 로 돌리기도 해서, 현황판은 render_all.bat 도 잡아 보여 준다.
 *
 * 서버와는 커서 폴링(0.7초)으로 만난다 — 잡 모델과 같은 방식. 이벤트 종류는
 * services/chat/session.py 머리말에 있다.
 */
"use strict";

import { $, api, el, escapeHtml, renderMarkdown, toast } from "./util.js";
import { iconHtml, hydrateIcons } from "./icons.js";

const POLL_MS = 700;
const KEY_SID = "xam.chat.sid";
const KEY_FOLD = "xam.chat";
const KEY_MODE = "xam.chat.mode";
const STATUS_MS = 8000;

const S = { sid: "", cursor: 0, busy: false, timer: 0, curText: null, curRaw: "",
            tools: new Map(), root: null, log: null, input: null, mode: "status", stTimer: 0 };

/* ── 화면 맥락 — 지금 무엇을 보고 있는지를 메시지에 붙인다 ── */
function screenContext() {
  const h = location.hash || "#/home";
  const ctx = { route: h };
  let m;
  if ((m = h.match(/^#\/questions\/([^/?]+)/))) ctx.question = decodeURIComponent(m[1]);
  if ((m = h.match(/^#\/(?:video|render|precheck)\/([^/?]+)/))) ctx.bundle = decodeURIComponent(m[1]);
  if ((m = h.match(/^#\/(?:summary|outline)\/([^/?]+)/))) ctx.subject = decodeURIComponent(m[1]);
  // 강의 노트·듣기 검수는 #/lecture/<summary|full>/<과목> — 두 번째 칸이 과목이다
  if ((m = h.match(/^#\/(?:lecture|listen)\/(summary|full)(?:\/([^/?]+))?/))) {
    ctx.note = m[1] === "full" ? "종합반 강의 노트" : "요약반 강의 노트";
    if (m[2]) ctx.subject = decodeURIComponent(m[2]);
  }
  const book = $("#su-name"), team = $("#su-team");
  if (book) ctx.book = book.textContent.trim();
  if (team && team.textContent.trim() !== "—") ctx.pd = team.textContent.trim();
  // 가운데 화면에서 고른 글 — "이 문장 왜 이래?" 같은 질문의 대상
  const sel = String(window.getSelection ? window.getSelection() : "").trim();
  if (sel && !S.root.contains(window.getSelection().anchorNode)) ctx.selection = sel.slice(0, 1500);
  return ctx;
}

function ctxLabel(ctx) {
  const bits = [ctx.note, ctx.question && `문항 ${ctx.question}`, ctx.bundle && `번들 ${ctx.bundle}`,
                ctx.subject && `과목 ${ctx.subject}`].filter(Boolean);
  return bits.length ? bits.join(" · ") : ctx.route.replace(/^#\//, "") || "home";
}

/* ── 마크다운 — util 의 것에 코드블록·링크만 더한다 (전부 이스케이프 뒤에 조립) ── */
function md(text) {
  const parts = String(text || "").split(/```/);
  let out = "";
  parts.forEach((p, i) => {
    if (i % 2) {
      const body = p.replace(/^[^\n]*\n/, "");
      out += `<pre class="ch-code">${escapeHtml(body)}</pre>`;
    } else {
      out += renderMarkdown(p);
    }
  });
  return out.replace(/(^|[\s(>])(https?:\/\/[^\s<)]+)/g,
    (_, pre, url) => `${pre}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
}

/* ── 그리기 ── */
function scrollEnd() {
  const near = S.log.scrollHeight - S.log.scrollTop - S.log.clientHeight < 140;
  if (near) S.log.scrollTop = S.log.scrollHeight;
}

function addUser(e) {
  const b = el("div", "ch-msg ch-user");
  b.appendChild(el("div", "ch-bubble", e.text));
  if (e.ctx) {
    const c = el("div", "ch-ctx", e.ctx.split("\n")[0].replace(/^화면:\s*/, ""));
    c.title = e.ctx;
    b.appendChild(c);
  }
  S.log.appendChild(b);
  S.curText = null;
}

function textBlock() {
  if (!S.curText) {
    S.curText = el("div", "ch-msg ch-bot md");
    S.curRaw = "";
    S.log.appendChild(S.curText);
  }
  return S.curText;
}

function addText(t) {
  const b = textBlock();
  S.curRaw += t;
  b.innerHTML = md(S.curRaw);
}

function addTool(e) {
  S.curText = null;
  const row = el("div", "ch-tool");
  row.innerHTML = `<span class="ch-dot"></span><b>${escapeHtml(e.label || e.name)}</b>`
    + `<span class="ch-brief">${escapeHtml(e.brief || "")}</span>`;
  row.dataset.t0 = String(Date.now());
  S.tools.set(e.id, row);
  S.log.appendChild(row);
}

function toolDone(e) {
  const row = S.tools.get(e.id);
  if (!row) return;
  row.classList.add(e.error ? "is-err" : "is-done");
  const sec = Math.max(0, Math.round((Date.now() - Number(row.dataset.t0)) / 1000));
  if (sec >= 2) row.appendChild(el("span", "ch-sec", `${sec}초`));
}

function addApprove(e) {
  S.curText = null;
  const card = el("div", "ch-approve");
  card.id = `ch-ap-${e.id}`;
  card.innerHTML = `
    <div class="ch-ap-head">${iconHtml("key", 14)}<span>실행 승인이 필요합니다</span></div>
    <div class="ch-ap-why">${escapeHtml(e.why || "")}</div>
    <code class="ch-ap-call">${escapeHtml(e.method)} ${escapeHtml(e.path)}</code>`;
  const body = e.body && Object.keys(e.body).length ? JSON.stringify(e.body, null, 1) : "";
  if (body) {
    const det = el("details", "ch-ap-body");
    det.appendChild(el("summary", null, "보낼 내용"));
    det.appendChild(el("pre", null, body));
    card.appendChild(det);
  }
  const acts = el("div", "ch-ap-acts");
  const no = el("button", "btn sm", "거절");
  const ok = el("button", "btn sm primary", "승인하고 실행");
  no.type = ok.type = "button";
  const send = async (yes) => {
    let note = "";
    if (!yes) note = (window.prompt("거절 사유 (선택) — Claude 에게 그대로 전해집니다", "") || "").trim();
    ok.disabled = no.disabled = true;
    try {
      await api(`/api/chat/${S.sid}/approve`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: e.id, ok: yes, note }),
      });
    } catch (err) {
      toast(err.message, "err");
      ok.disabled = no.disabled = false;
    }
  };
  no.addEventListener("click", () => send(false));
  ok.addEventListener("click", () => send(true));
  acts.append(no, ok);
  card.appendChild(acts);
  S.log.appendChild(card);
}

function settleApprove(e, yes) {
  const card = document.getElementById(`ch-ap-${e.id}`);
  if (!card) return;
  card.classList.add(yes ? "is-ok" : "is-no");
  const acts = card.querySelector(".ch-ap-acts");
  if (acts) acts.replaceWith(el("div", "ch-ap-res", yes ? "승인함" : `거절함${e.note ? " — " + e.note : ""}`));
}

function addNote(cls, text) {
  S.curText = null;
  S.log.appendChild(el("div", `ch-note ${cls}`, text));
}

function apply(e) {
  switch (e.t) {
    case "user": addUser(e); break;
    case "seg": S.curText = null; break;
    case "delta": case "text": addText(e.text); break;
    case "tool": addTool(e); break;
    case "tool_done": toolDone(e); break;
    case "approve": addApprove(e); break;
    case "approved": settleApprove(e, true); break;
    case "denied": settleApprove(e, false); break;
    case "navigate": if (location.hash !== e.route) location.hash = e.route; break;
    case "info": addNote("", e.text); break;
    case "error": addNote("is-err", errText(e)); break;
    case "done":
      S.curText = null;
      if (e.cost) addNote("ch-cost", `$${e.cost.toFixed(3)} · ${Math.round((e.ms || 0) / 100) / 10}초`);
      break;
  }
}

function errText(e) {
  if (e.kind === "QuotaExceeded") return "Claude 사용 한도에 걸렸습니다. 잠시 뒤 다시 보내 주세요.";
  if (e.kind === "NotAuthenticated") return "Claude Code 로그인이 필요합니다. 터미널에서 claude 를 한 번 실행해 로그인하세요.";
  return `오류: ${e.text || ""}`;
}

/* ── 폴링 ── */
async function poll() {
  clearTimeout(S.timer);
  if (!S.sid) return;
  try {
    const d = await api(`/api/chat/${S.sid}/events?since=${S.cursor}`);
    d.events.forEach(apply);
    S.cursor = d.next;
    setBusy(d.busy);
    if (d.events.length) scrollEnd();
    $("#ch-title").textContent = d.title || "새 대화";
  } catch (_) { /* 일시 실패는 무시 — 다음 틱에 다시 */ }
  S.timer = setTimeout(poll, S.busy ? POLL_MS : POLL_MS * 4);
}

function setBusy(b) {
  S.busy = !!b;
  S.root.classList.toggle("is-busy", S.busy);
  $("#ch-send").hidden = S.busy;
  $("#ch-stop").hidden = !S.busy;
}

async function openSession(sid) {
  S.sid = sid; S.cursor = 0; S.curText = null; S.tools.clear();
  S.log.innerHTML = "";
  try { localStorage.setItem(KEY_SID, sid); } catch (_) {}
  await poll();
  if (!S.log.children.length) emptyHint();
  S.log.scrollTop = S.log.scrollHeight;
}

function emptyHint() {
  const box = el("div", "ch-empty");
  box.innerHTML = `<div class="ch-empty-t">무엇을 할까요?</div>`;
  const ex = ["지금 책 상태를 한눈에 정리해 줘",
              "이 문항 해설이 어디서 오는지 파일과 줄로 짚어 줘",
              "SQLD 인강 시장 현황을 최근 자료로 조사해 줘",
              "1과목 이론 원고를 자막대본 단계부터 만들어 줘"];
  ex.forEach((t) => {
    const b = el("button", "ch-chip", t);
    b.type = "button";
    b.addEventListener("click", () => { S.input.value = t; S.input.focus(); });
    box.appendChild(b);
  });
  S.log.appendChild(box);
}

async function newSession() {
  const d = await api("/api/chat/sessions", { method: "POST" });
  await openSession(d.sid);
  S.input.focus();
}

async function send() {
  const text = S.input.value.trim();
  if (!text || S.busy) return;
  if (S.mode === "status") await enterChat();
  if (!S.sid) await newSession();
  const empty = S.log.querySelector(".ch-empty");
  if (empty) empty.remove();
  S.input.value = "";
  autosize();
  setBusy(true);
  try {
    await api(`/api/chat/${S.sid}/send`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, ctx: screenContext() }),
    });
  } catch (err) {
    toast(err.message, "err");
    S.input.value = text;
    setBusy(false);
  }
  poll();
}

async function stop() {
  try { await api(`/api/chat/${S.sid}/interrupt`, { method: "POST" }); } catch (_) {}
}

async function showList() {
  const d = await api("/api/chat/sessions");
  const menu = $("#ch-list");
  menu.innerHTML = "";
  if (!d.items.length) menu.appendChild(el("div", "ch-list-empty", "대화가 없습니다."));
  d.items.forEach((it) => {
    const row = el("button", "ch-list-row" + (it.sid === S.sid ? " is-on" : ""));
    row.type = "button";
    row.innerHTML = `<span class="ch-list-t">${escapeHtml(it.title)}</span>`
      + `<span class="ch-list-m">${escapeHtml((it.updated || "").replace("T", " ").slice(5, 16))}</span>`;
    row.addEventListener("click", () => { menu.hidden = true; openSession(it.sid); });
    menu.appendChild(row);
  });
  menu.hidden = !menu.hidden;
}

function autosize() {
  S.input.style.height = "auto";
  S.input.style.height = Math.min(220, S.input.scrollHeight) + "px";
}

function updateCtxChip() {
  const chip = $("#ch-ctxchip");
  if (chip) chip.textContent = ctxLabel(screenContext());
}

export function toggleChat(force) {
  const fold = force !== undefined ? force : document.body.dataset.chat !== "collapsed";
  document.body.dataset.chat = fold ? "collapsed" : "open";
  try { localStorage.setItem(KEY_FOLD, document.body.dataset.chat); } catch (_) {}
  if (!fold) setTimeout(() => S.input && S.input.focus(), 50);
}

/* ── 마운트 (shell.js 가 한 번 부른다) ── */
export async function mountChat(root) {
  S.root = root;
  root.innerHTML = `
    <div class="ch-head">
      <button class="ch-iconbtn" id="ch-fold" type="button" title="채팅 접기 (Ctrl+J)">${iconHtml("panelRight", 16)}</button>
      <button class="ch-titlebtn" id="ch-titlebtn" type="button" title="대화 목록">
        <span id="ch-title">새 대화</span>${iconHtml("chevronDown", 14)}</button>
      <button class="ch-modebtn" id="ch-mode" type="button" title="작업 현황 ↔ 대화">대화</button>
      <button class="ch-iconbtn" id="ch-new" type="button" title="새 대화">${iconHtml("plus", 16)}</button>
      <div class="ch-list" id="ch-list" hidden></div>
    </div>
    <div class="ch-log" id="ch-log" aria-live="polite"></div>
    <div class="ch-foot">
      <div class="ch-box">
        <textarea id="ch-input" rows="1" placeholder="필요할 때만 — 시장조사·질문·실행 요청 (Enter)"></textarea>
        <div class="ch-bar">
          <span class="ch-ctxchip" id="ch-ctxchip" title="메시지에 함께 붙는 지금 화면"></span>
          <button class="ch-send" id="ch-send" type="button" title="보내기">${iconHtml("send", 15)}</button>
          <button class="ch-send ch-stop" id="ch-stop" type="button" title="중단" hidden><span class="ch-sq"></span></button>
        </div>
      </div>
      <div class="ch-foot-note">쓰기·실행은 승인 카드를 눌러야 진행됩니다 · 업로드는 IP 허브</div>
    </div>
    <button class="ch-rail" id="ch-rail" type="button" title="채팅 열기 (Ctrl+J)">${iconHtml("sparkles", 18)}<span>Claude</span></button>`;
  hydrateIcons(root);
  S.log = $("#ch-log", root);
  S.input = $("#ch-input", root);

  S.input.addEventListener("input", autosize);
  S.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });
  $("#ch-send", root).addEventListener("click", send);
  $("#ch-stop", root).addEventListener("click", stop);
  $("#ch-new", root).addEventListener("click", async () => { await enterChat(true); });
  $("#ch-mode", root).addEventListener("click", () => (S.mode === "status" ? enterChat() : showStatus()));
  $("#ch-titlebtn", root).addEventListener("click", showList);
  $("#ch-fold", root).addEventListener("click", () => toggleChat(true));
  $("#ch-rail", root).addEventListener("click", () => toggleChat(false));
  document.addEventListener("click", (e) => {
    const m = $("#ch-list");
    if (m && !m.hidden && !e.target.closest("#ch-list, #ch-titlebtn")) m.hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && (e.key === "j" || e.key === "J")) { e.preventDefault(); toggleChat(); }
  });
  window.addEventListener("hashchange", () => { updateCtxChip(); if (S.mode === "status") renderStatus(); });
  document.addEventListener("selectionchange", () => {
    clearTimeout(S.selT); S.selT = setTimeout(updateCtxChip, 250);
  });

  let fold = "";
  try { fold = localStorage.getItem(KEY_FOLD) || ""; } catch (_) {}
  document.body.dataset.chat = fold === "collapsed" ? "collapsed" : "open";
  updateCtxChip();

  let mode = "";
  try { mode = localStorage.getItem(KEY_MODE) || ""; } catch (_) {}
  if (mode === "chat") await enterChat();
  else showStatus();
}

/* ── 모드 전환 ── */
async function enterChat(fresh = false) {
  S.mode = "chat";
  try { localStorage.setItem(KEY_MODE, "chat"); } catch (_) {}
  clearTimeout(S.stTimer);
  S.root.classList.remove("is-status");
  $("#ch-mode").textContent = "현황";
  if (fresh) { await newSession(); return; }
  let sid = "";
  try { sid = localStorage.getItem(KEY_SID) || ""; } catch (_) {}
  if (sid) {
    try {
      await api(`/api/chat/${sid}/events?since=0`);     // 지워진 대화면 404 로 여기서 떨어진다
      await openSession(sid);
      return;
    } catch (_) { /* 지워진 대화 — 빈 화면으로 */ }
  }
  S.sid = "";
  S.log.innerHTML = "";
  emptyHint();
}

function showStatus() {
  S.mode = "status";
  try { localStorage.setItem(KEY_MODE, "status"); } catch (_) {}
  clearTimeout(S.timer);
  S.root.classList.add("is-status");
  $("#ch-mode").textContent = "대화";
  $("#ch-title").textContent = "작업 현황";
  S.log.innerHTML = "";
  renderStatus();
}

/* ── 작업 현황판 — 지금 하는 일 · 반영할 것 · 다음에 할 일 ── */
async function renderStatus() {
  clearTimeout(S.stTimer);
  if (S.mode !== "status") return;
  let d;
  try { d = await api(`/api/chat/status?route=${encodeURIComponent(location.hash || "#/home")}`); }
  catch (_) { S.stTimer = setTimeout(renderStatus, STATUS_MS); return; }
  if (S.mode !== "status") return;
  const box = el("div", "st-board");
  const sec = (title, cls, rows, empty) => {
    const s = el("div", `st-sec ${cls}`);
    s.appendChild(el("div", "st-h", title));
    if (!rows.length) s.appendChild(el("div", "st-empty", empty));
    rows.forEach((r) => s.appendChild(r));
    box.appendChild(s);
  };
  sec("지금 하는 일", "st-now", (d.now || []).map((j) => {
    const r = el(j.id ? "a" : "div", "st-row st-job");
    if (j.id) r.href = `#/job/${encodeURIComponent(j.id)}`;
    const pct = j.total ? ` · ${j.done}/${j.total}` : "";
    r.innerHTML = `<span class="ch-dot"></span><span class="st-t">${escapeHtml(j.label || "")}${pct}</span>`
      + (j.detail || j.current ? `<span class="st-d">${escapeHtml(j.detail || j.current || "")}</span>` : "");
    return r;
  }), "돌고 있는 작업이 없습니다.");
  if ((d.reflect || []).length) {
    sec("고친 뒤 반영할 것", "st-reflect", d.reflect.map((n) => link(n)), "");
  }
  sec("다음에 할 일", "st-next", (d.next || []).map((n) => link(n)), "지금 할 일이 없습니다.");
  S.log.innerHTML = "";
  S.log.appendChild(box);
  S.stTimer = setTimeout(renderStatus, (d.now || []).length ? 3000 : STATUS_MS);
}

function link(n) {
  const a = el("a", "st-row" + (n.here ? " st-here" : ""));
  a.href = n.route || "#/home";
  a.innerHTML = `<span class="st-arrow">→</span><span class="st-t">${escapeHtml(n.text)}</span>`;
  return a;
}
