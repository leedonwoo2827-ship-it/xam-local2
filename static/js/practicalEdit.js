/* 문항 교정 (실기) — 실기 집필 결과(02/practical/mNN) 문항 하나를 고치고 「교정 완료」를 찍는다.
 *
 * ★ 필기 questions.js 와 같은 2층 구조(2026-11-09 계획 승인):
 *     #/practical-edit        위층 패널: 문항 목록(색 = 교정 완료) · 회차 고르기 · 검색(함수 이름도)
 *     #/practical-edit/:id    아래층 바탕: 왼쪽 고치는 칸 / 오른쪽 원고 미리보기
 * ★ 저장하면 문항 파일 · 묶음 원본(part{P}.json) · MD 를 함께 다시 쓴다(author.save_item).
 *   시트 자료(sheets)는 **묶음 공용**이라 고치면 같은 묶음의 문항 전부에 들어간다.
 * ★ 「교정 완료」는 누르는 즉시 저장한다 — 체크만 하고 저장을 잊으면 진행 현황이 거짓말을 한다(OCR 검수와 같다).
 */
"use strict";

import { $, api, el, toast, stateClass } from "./util.js";
import { getPref, setPref } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";
import { practicalMdHtml } from "./practicalMd.js";

const PART = { 1: "기본작업", 2: "계산작업", 3: "분석작업", 4: "기타작업" };
const S = { ctx: null, list: null, f: { round: 0, q: "", unreviewed: false }, cur: null, dirty: false };

export const meta = {
  title: (ctx) => (ctx.panel ? "실기 문항 교정" : `문항 교정 · ${ctx.args[0] || ""}`),
  subtitle: (ctx) => (ctx.panel
    ? "고르면 이 창이 닫히고 아래 바탕에서 열립니다. 색 = 교정 완료."
    : "실기 집필 원고(02/practical)입니다. 저장하면 MD 가 다시 써집니다."),
  actions: (ctx) => (ctx.panel ? [] : [
    actionBtn("← 문항 목록", () => leave("/practical-edit"), { iconName: "folder" }),
    actionBtn("◀ 이전", () => step(-1)),
    actionBtn("다음 ▶", () => step(1)),
    actionBtn("저장", () => save(), { primary: true, iconName: "check" }),
  ]),
};

export async function mount(root, ctx) {
  S.ctx = ctx;
  Object.assign(S.f, getPref("prEditFilters", {}) || {});
  return ctx.panel ? mountList(root, ctx) : mountWork(root, ctx);
}

async function load() {
  const qs = new URLSearchParams();
  if (S.f.round) qs.set("round", S.f.round);
  if (S.f.q) qs.set("q", S.f.q);
  if (S.f.unreviewed) qs.set("unreviewed", "1");
  S.list = await api("/api/practical/edit/items?" + qs.toString());
}

/* ══════════ 위층: 목록 ══════════ */
async function mountList(root, ctx) {
  root.innerHTML = `
    <div class="qz-bar">
      <select class="input" id="pe-round" style="width:auto"><option value="0">전체 회차</option>
        ${Array.from({ length: 20 }, (_, i) => `<option value="${i + 1}">${String(i + 1).padStart(2, "0")}회</option>`).join("")}</select>
      <button class="chip" id="pe-unrev" type="button">미교정만</button>
      <div class="search-box"><span data-icon="search" data-icon-size="14"></span>
        <input id="pe-q" type="search" placeholder="id · 발문 · 업무 영역 · 함수(VLOOKUP)" /></div>
      <span class="qz-bar-note muted" id="pe-count"></span>
    </div>
    <div class="sc-list" id="pe-list"></div>`;
  hydrateIcons(root);
  const save = () => setPref("prEditFilters", S.f);
  const sel = $("#pe-round");
  sel.value = String(S.f.round || 0);
  sel.addEventListener("change", () => { S.f.round = Number(sel.value); save(); refresh(ctx); });
  const un = $("#pe-unrev");
  un.classList.toggle("on", S.f.unreviewed);
  un.addEventListener("click", () => { S.f.unreviewed = !S.f.unreviewed; un.classList.toggle("on", S.f.unreviewed); save(); refresh(ctx); });
  const q = $("#pe-q");
  q.value = S.f.q || "";
  let t = null;
  q.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { S.f.q = q.value; save(); refresh(ctx); }, 250); });
  await refresh(ctx);
  q.focus();
}

async function refresh(ctx) {
  const box = $("#pe-list");
  try { await load(); } catch (e) {
    if (box) { box.innerHTML = ""; box.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message)); }
    return;
  }
  const d = S.list;
  const c = $("#pe-count");
  if (c) c.textContent = `${d.filtered} / ${d.count}문항 · 교정 완료 ${d.reviewed} / ${d.count}`;
  box.innerHTML = "";
  if (!d.items.length) {
    box.appendChild(el("div", "empty", d.count ? "조건에 맞는 문항이 없습니다." : "아직 실기 집필 결과가 없습니다 — 「실기 문제 집필」 에서 쓰세요."));
    return;
  }
  for (const it of d.items) {
    const row = el("div", "sc-row " + stateClass(1, it.reviewed ? 1 : 0));
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    const head = el("div", "sc-row-head");
    head.appendChild(el("span", "sc-row-id", it.id));
    head.appendChild(el("span", "sc-row-subj", `${String(it.round).padStart(2, "0")}회 문제${it.part} ${PART[it.part] || ""} · ${it.no === 0 ? "묶음 머리" : it.no + "번"}`));
    if (it.points != null) head.appendChild(el("span", "badge", `${it.points}점`));
    const marks = el("span", "sc-row-marks");
    for (const f of (it.functions || []).slice(0, 4)) marks.appendChild(el("span", "qz-mark", f));
    if (it.figures) marks.appendChild(el("span", "qz-mark fig", `그림 ${it.figures}`));
    marks.appendChild(el("span", "qz-mark " + (it.reviewed ? "" : "todo"), it.reviewed ? "교정 완료" : "미교정"));
    head.appendChild(marks);
    row.appendChild(head);
    row.appendChild(el("div", "sc-row-body", it.preview || ""));
    const go = () => ctx.navigate("/practical-edit/" + encodeURIComponent(it.id));
    row.addEventListener("click", go);
    row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    box.appendChild(row);
  }
}

/* ══════════ 아래층: 고치기 ══════════ */
const lines = (v) => String(v || "").split("\n").map((s) => s.trimEnd()).filter((s) => s.trim() !== "");
const pretty = (v) => JSON.stringify(v ?? [], null, 1);

function area(label, value, rows, onInput, hint) {
  const w = el("label", "field");
  w.style.cssText = "display:block;margin:10px 0";
  w.appendChild(el("div", "field-label", label));
  const ta = el("textarea", "input");
  ta.rows = rows;
  ta.value = value;
  ta.style.cssText = "width:100%;font-family:inherit;line-height:1.55";
  ta.addEventListener("input", () => { onInput(ta.value); markDirty(); });
  w.appendChild(ta);
  if (hint) w.appendChild(el("div", "field-hint", hint));
  return w;
}

function jsonArea(label, value, rows, onOk, hint) {
  const w = area(label, pretty(value), rows, (v) => {
    try { onOk(JSON.parse(v)); w.querySelector("textarea").style.outline = ""; }
    catch (_) { w.querySelector("textarea").style.outline = "2px solid #c33"; }
  }, hint);
  w.querySelector("textarea").style.fontFamily = "Consolas, monospace";
  w.querySelector("textarea").style.fontSize = "12px";
  return w;
}

function markDirty() { S.dirty = true; const s = $("#pe-status"); if (s) s.textContent = "저장 안 됨"; }

async function mountWork(root, ctx) {
  const id = decodeURIComponent(ctx.args[0] || "");
  const page = el("div", "page");
  root.appendChild(page);
  try { S.cur = await api("/api/practical/edit/item/" + encodeURIComponent(id)); } catch (e) {
    page.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message));
    return;
  }
  S.dirty = false;
  draw(page);
}

function draw(page) {
  const j = S.cur.json;
  const P = S.patch = {};
  page.innerHTML = "";
  const grid = el("div");
  grid.style.cssText = "display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px;align-items:start";
  const left = el("div", "card");
  const right = el("div", "card");
  right.style.cssText = "position:sticky;top:8px;max-height:calc(100vh - 140px);overflow:auto";

  const head = el("div", "qz-foot");
  head.appendChild(el("b", null, `${S.cur.id} · ${String(j.round).padStart(2, "0")}회 문제${j.part} ${PART[j.part] || ""} · ${j.no === 0 ? "묶음 머리" : j.no + "번"}`));
  const pts = el("input", "input");
  pts.type = "number"; pts.value = j.points ?? ""; pts.style.width = "70px"; pts.title = "배점";
  pts.addEventListener("input", () => { P.points = pts.value === "" ? null : Number(pts.value); markDirty(); });
  head.append(el("span", "muted", "배점"), pts);
  const chk = el("label", "oc-chk");
  const cb = el("input");
  cb.type = "checkbox"; cb.checked = !!j.reviewed;
  cb.addEventListener("change", async () => { P.reviewed = cb.checked; markDirty(); await save(true); });
  chk.append(cb, el("span", null, "교정 완료"));
  head.appendChild(chk);
  const st = el("span", "muted"); st.id = "pe-status"; st.textContent = j.reviewed ? "교정 완료" : "";
  head.appendChild(st);
  left.appendChild(head);
  left.appendChild(el("div", "field-hint", `업무 영역: ${j.scenario || "—"} · 바탕 ${String(j.source_round || "").padStart(2, "0")}회 · 함수: ${(j.functions || []).join(", ") || "—"}`));

  left.appendChild(area("발문", j.lead || "", 2, (v) => { P.lead = v.trim(); }));
  left.appendChild(area("지시사항 (한 줄에 하나 · 그림 자리는 {{f-1}} 한 줄)", (j.instructions || []).join("\n"), 7,
    (v) => { P.instructions = lines(v); }));
  const a = JSON.parse(JSON.stringify(j.answer || {}));
  left.appendChild(area("모범답안 제목", a.title || "", 1, (v) => { a.title = v.trim(); P.answer = a; }));
  left.appendChild(area("모범답안 절차 (한 줄에 하나 · 그림은 {{f-N}} 줄)", (a.steps || []).join("\n"), 10,
    (v) => { a.steps = lines(v); P.answer = a; }));
  left.appendChild(jsonArea("수식 (계산작업) — [{cell, formula, fill}]", a.formulas || [], 4, (v) => { a.formulas = v; P.answer = a; }));
  left.appendChild(jsonArea("결과값 — {셀: 값} (실습파일 검증에 씁니다)", a.results || {}, 4, (v) => { a.results = v; P.answer = a; }));
  left.appendChild(jsonArea("그림 설계 — [{id, kind table|chart|dialog, caption, columns, rows, chart, desc}]", j.figures || [], 8,
    (v) => { P.figures = v; }));
  // ★ 제공 차트(2026-11-12 녹화 회신) — 차트 문항은 지시를 적용하기 전 차트가 문제 파일에 있어야 한다
  if (j.given_chart || /차트/.test(j.sheet || "")) {
    left.appendChild(jsonArea("제공 차트 (지시 적용 전) — {range, type, title, legend}", j.given_chart || {}, 3,
      (v) => { P.given_chart = v; }, "문제 파일에 이 차트를 그립니다. 「원형으로 변경」이면 원형이 아닌 종류, 「7월 계열 추가」면 7월이 빠진 범위."));
  }
  left.appendChild(jsonArea("시트 자료 (묶음 공용 — 고치면 같은 묶음 문항 전부에 들어갑니다)", j.sheets || [], 10,
    (v) => { P.sheets = v; }, "표마다 anchor(머리글 행) · columns · rows(계산 칸은 \"=D4*E4\" 수식) · title_cell(제목 셀) · styles([{range, font_color, fill}]) · input(수험자가 입력하는 표: all·body·data — 문제 파일에서 비움)."));

  right.appendChild(el("div", "card-title", "원고 미리보기 (저장하면 갱신)"));
  const prev = el("div", "pr-page md-body");
  prev.id = "pe-prev";
  prev.style.cssText = "line-height:1.7;font-size:14px";
  prev.innerHTML = practicalMdHtml(S.cur.md, "m" + String(j.round).padStart(2, "0"));
  right.appendChild(prev);
  grid.append(left, right);
  page.appendChild(grid);
}

async function save(quiet) {
  if (!S.cur) return false;
  const body = Object.assign({}, S.patch || {});
  if (!Object.keys(body).length) { if (!quiet) toast("바뀐 것이 없습니다."); return true; }
  try {
    S.cur = await api("/api/practical/edit/item/" + encodeURIComponent(S.cur.id), {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    S.dirty = false;
    S.patch = {};
    const prev = $("#pe-prev");
    if (prev) prev.innerHTML = practicalMdHtml(S.cur.md, "m" + String(S.cur.json.round).padStart(2, "0"));
    const st = $("#pe-status");
    if (st) st.textContent = S.cur.json.reviewed ? "교정 완료 · 저장됨" : "저장됨";
    if (!quiet) toast(`${S.cur.id} 저장했습니다.`);
    return true;
  } catch (e) { toast("저장하지 못했습니다: " + e.message, "err"); return false; }
}

async function leave(to) {
  if (S.dirty && !(await save(true))) return;
  S.ctx.navigate(to);
}

async function step(d) {
  if (S.dirty && !(await save(true))) return;
  if (!S.list) { try { await load(); } catch (_) { return; } }
  const ids = (S.list.items || []).map((x) => x.id);
  const i = ids.indexOf(S.cur ? S.cur.id : "");
  const nx = ids[i + d];
  if (nx) S.ctx.navigate("/practical-edit/" + encodeURIComponent(nx));
}
