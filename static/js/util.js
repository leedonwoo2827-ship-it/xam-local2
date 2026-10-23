/* 공용 유틸 — DOM 헬퍼, fetch 래퍼, 마크다운 렌더, 토스트 */
"use strict";

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, cls, txt) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
}

/** html`` 대신 쓰는 간단한 조립기: 문자열 HTML → 요소 */
export function html(str) {
  const t = document.createElement("template");
  t.innerHTML = str.trim();
  return t.content.firstElementChild;
}

export function escapeHtml(s) {
  return (s ?? "").toString()
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 서버 오류를 사람이 읽는 한 줄로.
 *
 * ★ FastAPI 의 422 는 `detail` 이 **배열**이다(`[{loc, msg, type}, …]`). 그걸 그대로
 *   Error() 에 넣으면 화면에 `[object Object]` 만 뜬다 — 실제로 그렇게 겪었고,
 *   진짜 원인(본문이 JSON 이 아니었다)이 통째로 가려졌다.
 */
function errText(body, status) {
  const d = body && body.detail;
  if (typeof d === "string" && d) return d;
  if (Array.isArray(d) && d.length) {
    return d.map((x) => {
      const at = (x.loc || []).filter((v) => v !== "body").join(".");
      return (at ? at + ": " : "") + (x.msg || JSON.stringify(x));
    }).join(" · ");
  }
  if (d) return JSON.stringify(d);
  if (typeof body === "string" && body.trim()) return body.trim().slice(0, 300);
  return `요청 실패 (${status})`;
}

/** JSON 요청. 실패 시 서버가 준 detail 을 담아 throw.
 *
 * ★ body 가 **객체면 여기서 JSON 으로 바꾼다.** 안 그러면 fetch 가 그 객체를
 *   `"[object Object]"` 라는 문자열로 보내고 서버는 422 를 낸다. 호출부마다
 *   `JSON.stringify` + `Content-Type` 을 손으로 붙이던 규약이라, 한 곳만 빼먹으면
 *   조용히 그렇게 됐다. 문자열·FormData 는 손대지 않으므로 옛 호출부는 그대로 돈다.
 */
export async function api(path, opts = {}) {
  const o = { cache: "no-store", ...opts };
  const b = o.body;
  const raw = typeof b === "string" || b instanceof FormData ||
              b instanceof Blob || b instanceof URLSearchParams ||
              b instanceof ArrayBuffer || ArrayBuffer.isView(b || 0);
  if (b != null && !raw) {
    o.body = JSON.stringify(b);
    o.headers = { "Content-Type": "application/json", ...(o.headers || {}) };
  }
  const r = await fetch(path, o);
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json().catch(() => ({})) : await r.text();
  if (!r.ok) {
    const err = new Error(errText(body, r.status));
    err.status = r.status;
    err.body = body;
    throw err;
  }
  return body;
}

/**
 * 접히는 우측 패널 — 왼쪽 레일과 같은 규칙으로 동작하게 만든다.
 * 상태는 요소의 .collapsed 클래스로 두고(부모 그리드가 :has() 로 폭을 줄인다),
 * 이 PC 에 기억해서 화면을 옮겨도 접힌 채로 남는다.
 *
 * @param {HTMLElement} drawer  .drawer 요소
 * @param {string} key          localStorage 키
 * @param {HTMLElement[]} toggles  누르면 접힘이 바뀌는 버튼들
 */
export function collapsible(drawer, key, toggles = []) {
  const apply = (collapsed) => {
    drawer.classList.toggle("collapsed", collapsed);
    toggles.forEach((b) => {
      const label = collapsed ? "패널 펼치기" : "패널 접기";
      b.title = label;
      b.setAttribute("aria-label", label);
      b.setAttribute("aria-expanded", String(!collapsed));
    });
  };
  apply(localStorage.getItem(key) === "off");

  const toggle = (force) => {
    const next = force != null ? force : !drawer.classList.contains("collapsed");
    localStorage.setItem(key, next ? "off" : "on");
    apply(next);
  };
  toggles.forEach((b) => b.addEventListener("click", () => toggle()));
  return { toggle, isCollapsed: () => drawer.classList.contains("collapsed") };
}

let toastTimer = null;
export function toast(msg, kind = "") {
  const t = $("#toast");
  if (!t) return;
  t.textContent = msg;
  t.className = "toast" + (kind ? " " + kind : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3600);
}

/* ── 초경량 마크다운 렌더 (원본 studio.js 의 렌더러를 그대로 옮김) ── */
function inline(s) {
  return escapeHtml(s)
    .replace(/&lt;br\s*\/?&gt;/gi, "<br>")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

export function renderMarkdown(md) {
  const lines = (md || "").split("\n");
  let out = "", inList = false, inTable = false;
  const closeList = () => { if (inList) { out += "</ul>"; inList = false; } };
  const closeTable = () => { if (inTable) { out += "</table>"; inTable = false; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      closeList(); closeTable();
      const lvl = m[1].length;
      out += `<h${lvl}>${inline(m[2])}</h${lvl}>`;
    } else if ((m = line.match(/^>\s?(.*)$/))) {
      // 03/summary_*.md 는 개념마다 끝에 `> 출처: 01-41 · 관련 자사: m01-41` 을 단다.
      // 이걸 평범한 <p> 로 만들면 본문과 출처가 구분되지 않는다.
      closeList(); closeTable();
      out += `<blockquote>${inline(m[1])}</blockquote>`;
    } else if (/^\s*[-*+]\s+/.test(line)) {
      closeTable();
      if (!inList) { out += "<ul>"; inList = true; }
      out += `<li>${inline(line.replace(/^\s*[-*+]\s+/, ""))}</li>`;
    } else if (/^\|.*\|$/.test(line)) {
      closeList();
      const cells = line.slice(1, -1).split("|").map((c) => c.trim());
      if (cells.every((c) => /^:?-+:?$/.test(c) || c === "")) continue;
      if (!inTable) { out += "<table>"; inTable = true; }
      out += "<tr>" + cells.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
    } else if (!line.trim()) {
      closeList(); closeTable();
    } else {
      closeList(); closeTable();
      out += `<p>${inline(line)}</p>`;
    }
  }
  closeList(); closeTable();
  return out;
}

/* ── 입력 모달 ──────────────────────────────────────────────────────────────
 * confirmModal 은 예/아니오만 돌려준다. 값을 받아야 하는 자리(품목 코드, 표시 이름)
 * 에 window.prompt 를 쓰면 무엇을 왜 묻는지 설명할 자리가 없다.
 *
 * fields: [{ name, label, value, hint, pattern, placeholder, required }]
 * @returns {Promise<Object|null>}  취소하면 null
 */
export function formModal({ title, body = "", fields = [], ok = "저장", cancel = "취소" }) {
  return new Promise((resolve) => {
    const overlay = $("#app-overlay");
    const modal = $("#app-modal");
    if (!overlay || !modal) { resolve(null); return; }

    modal.innerHTML = "";
    modal.appendChild(el("h2", null, title));
    if (body) {
      const p = el("p", "modal-sub");
      p.innerHTML = body;            // 호출자가 escapeHtml 로 조립한다
      modal.appendChild(p);
    }

    const form = el("form", "modal-form");
    const inputs = {};
    fields.forEach((f) => {
      const row = el("label", "field");
      row.appendChild(el("span", "field-label", f.label));
      // ★ 여러 줄을 받아야 하는 칸이 있다 — 「과정 정의」가 JSON 전문을 통째로
      //   붙여넣게 한다. 한 줄 input 이면 붙여넣기는 되지만 **보이지 않아서**
      //   맞게 들어갔는지 확인할 방법이 없다(2026-09-07).
      const multi = f.type === "textarea";
      const inp = el(multi ? "textarea" : "input");
      if (multi) inp.rows = f.rows || 12;
      else inp.type = "text";
      inp.value = f.value == null ? "" : String(f.value);
      if (f.placeholder) inp.placeholder = f.placeholder;
      inputs[f.name] = inp;
      row.appendChild(inp);
      if (f.hint) {
        const h = el("span", "field-hint");
        h.innerHTML = f.hint;
        row.appendChild(h);
      }
      const bad = el("span", "field-hint bad");
      bad.hidden = true;
      row.appendChild(bad);
      inp._bad = bad;
      form.appendChild(row);
    });
    modal.appendChild(form);

    const actions = el("div", "modal-actions");
    const btnOk = el("button", "btn primary", ok);
    btnOk.type = "submit";
    actions.appendChild(btnOk);
    const btnNo = cancel ? el("button", "btn", cancel) : null;
    if (btnNo) { btnNo.type = "button"; actions.appendChild(btnNo); }
    form.appendChild(actions);

    const lastFocus = document.activeElement;
    const done = (v) => {
      overlay.hidden = true;
      document.removeEventListener("keydown", onKey);
      overlay.removeEventListener("click", onBackdrop);
      if (lastFocus && lastFocus.focus) lastFocus.focus();
      resolve(v);
    };
    const submit = (e) => {
      if (e) e.preventDefault();
      let ok2 = true;
      const out = {};
      fields.forEach((f) => {
        const inp = inputs[f.name];
        const v = inp.value.trim();
        let msg = "";
        if (f.required && !v) msg = "값이 필요합니다.";
        else if (v && f.pattern && !new RegExp(f.pattern).test(v)) {
          msg = f.patternMsg || "형식이 맞지 않습니다.";
        }
        inp._bad.textContent = msg;
        inp._bad.hidden = !msg;
        if (msg) { ok2 = false; if (ok2 === false && !out._focused) inp.focus(); }
        out[f.name] = v;
      });
      if (ok2) done(out);
    };
    const onKey = (e) => { if (e.key === "Escape") { e.preventDefault(); done(null); } };
    const onBackdrop = (e) => { if (e.target === overlay) done(null); };

    form.addEventListener("submit", submit);
    if (btnNo) btnNo.addEventListener("click", () => done(null));
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", onBackdrop);

    overlay.hidden = false;
    const first = fields.length ? inputs[fields[0].name] : btnOk;
    first.focus();
    if (first.select) first.select();
  });
}

/* ── 확인 모달 ──────────────────────────────────────────────────────────────
 * window.confirm 을 쓰지 않는다. 미저장 편집을 버릴지 묻는 자리라서 무슨 파일이
 * 걸려 있는지 함께 보여줘야 하고, 기본 대화상자는 서체·색이 앱과 따로 논다.
 *
 * @returns {Promise<boolean>}
 */
export function confirmModal({ title, body = "", bodyNode = null, ok = "확인", cancel = "취소", danger = false }) {
  return new Promise((resolve) => {
    const overlay = $("#app-overlay");
    const modal = $("#app-modal");
    if (!overlay || !modal) { resolve(false); return; }

    modal.innerHTML = "";
    modal.appendChild(el("h2", null, title));
    // ★ `bodyNode` 는 **살아 있는 DOM** 이다 — 체크박스·입력칸을 넣을 때 쓴다.
    //   `body`(innerHTML)로는 이벤트와 참조가 끊긴다(실측: 판독 대상 고르기 창).
    if (bodyNode) {
      modal.appendChild(bodyNode);
    } else if (body) {
      const p = el("p", "modal-sub");
      p.innerHTML = body;          // 호출자가 escapeHtml 로 조립한다
      modal.appendChild(p);
    }
    const actions = el("div", "modal-actions");
    const btnOk = el("button", "btn primary" + (danger ? " danger" : ""), ok);
    btnOk.type = "button";
    actions.appendChild(btnOk);
    // cancel 이 빈 문자열이면 확인 버튼만 둔다(도움말처럼 '닫기' 하나로 끝나는 창).
    const btnNo = cancel ? el("button", "btn", cancel) : null;
    if (btnNo) { btnNo.type = "button"; actions.appendChild(btnNo); }
    modal.appendChild(actions);

    const lastFocus = document.activeElement;
    const done = (v) => {
      overlay.hidden = true;
      document.removeEventListener("keydown", onKey);
      overlay.removeEventListener("click", onBackdrop);
      if (lastFocus && lastFocus.focus) lastFocus.focus();
      resolve(v);
    };
    const onKey = (e) => {
      if (e.key === "Escape") { e.preventDefault(); done(false); }
      else if (e.key === "Enter" && e.target === btnOk) { /* 버튼이 처리 */ }
    };
    const onBackdrop = (e) => { if (e.target === overlay) done(false); };

    btnOk.addEventListener("click", () => done(true));
    if (btnNo) btnNo.addEventListener("click", () => done(false));
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", onBackdrop);

    overlay.hidden = false;
    btnOk.focus();
  });
}

/** 바이트 수 → 사람이 읽는 크기. mp4 가 16MB 단위라 MB 까지면 충분하다. */
export function fmtBytes(n) {
  if (n == null) return "—";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
  if (n < 1024 * 1024 * 1024) return (n / 1048576).toFixed(1) + " MB";
  return (n / 1073741824).toFixed(2) + " GB";
}

/** 초 → "5분 35초". review.json 의 totalSeconds 표시용. */
export function fmtSec(s) {
  if (s == null) return "—";
  const t = Math.round(s);
  const m = Math.floor(t / 60);
  return m ? `${m}분 ${t % 60}초` : `${t}초`;
}

/** 오늘 기준 D-day 문자열. (양수=남음) */
export function dday(dateStr) {
  const d = parseDate(dateStr);
  if (!d) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((d - today) / 86400000);
  return diff;
}

export function ddayLabel(diff) {
  if (diff == null) return "";
  if (diff === 0) return "D-DAY";
  return diff > 0 ? `D-${diff}` : `D+${-diff}`;
}

/** "2026-07-31" / "2026.7.31" / "20260731" / Date 직렬화 문자열을 관대하게 파싱 */
export function parseDate(v) {
  if (!v) return null;
  if (v instanceof Date) return isNaN(v) ? null : v;
  const s = String(v).trim();
  let m = s.match(/^(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})/);
  if (m) {
    const d = new Date(+m[1], +m[2] - 1, +m[3]);
    return isNaN(d) ? null : d;
  }
  const d = new Date(s);
  return isNaN(d) ? null : d;
}

export function fmtDate(v) {
  const d = parseDate(v);
  if (!d) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}


/* ══ 상태 3색 규칙 — 목록을 만드는 모든 화면이 이 함수를 쓴다 ══════════════════
 *
 * ★ 목적은 하나다 — **빠진 것이 눈에 걸려야 한다.**
 *
 *     state-done   전부 끝남    청록 채움
 *     state-part   하다 만      노랑
 *     state-todo   아직 안 함   **하얗게.** 색을 주지 않는다 = 여기가 '할 일'
 *     state-empty  판정 불가    점선(틀만 있음)
 *
 * 색을 안 한 쪽에 주면 안 되는 이유: 목록은 훑는 화면이다. 모든 칸에 색이 있으면
 * 어디가 남았는지 세어야 알 수 있다. 실제로 그 사고가 있었다 — OCR 페이지 카드가
 * "초안에 문항이 있으면 초록" 이라, 판독만 하고 대조는 하나도 안 한 회차가 완료한
 * 회차와 똑같이 초록이었다.
 *
 * 색 값은 app.css 의 §상태 3색 규칙 한 곳에만 있다. 새 목록을 만들 때 색을 새로
 * 정하지 말고 이 함수가 주는 클래스를 붙인다.
 *
 *   stateClass(전체, 끝난것)              → 비율로 판정
 *   stateClass(0, 0, hasSomething=false)  → 내용이 없으면 todo, 틀만 있으면 empty
 */
export function stateClass(total, done, hasSomething = true) {
  const n = Number(total) || 0;
  const v = Number(done) || 0;
  if (!n) return hasSomething ? "state-empty" : "state-todo";
  if (v >= n) return "state-done";
  return v > 0 ? "state-part" : "state-todo";
}
