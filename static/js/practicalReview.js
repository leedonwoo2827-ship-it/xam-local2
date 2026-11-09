/* 실기 OCR 검수 — 왼쪽 메뉴 「OCR 검수」 가 실기 폴더에서 여는 화면.
 *
 * ★ **필기 OCR 검수(ocr.js)와 같은 화면**이다 — 정답·보기만 뺐다(2026-11-08 지시:
 *   "필기랑 정답이랑 보기를 제외하고는 동일하게"). 같은 CSS(ocr.css 의 oc-*), 같은 2층 구조:
 *     #/practical-review               위층 패널: 회차별 쪽 현황판(칸 색 = 대조완료)
 *     #/practical-review/:src/:page    아래층 바탕: 좌 스캔 / (판독 메모) / 우 카드
 *     #/practical-round?r=N            회차 묶음 — 문항 하나에 지시사항과 정답을 짝지어 대조
 *   머리줄 · 단축키(Ctrl+S 저장 · Ctrl+Enter 확정 · Alt+←/→ 쪽) · 카드 머리(문항·묶음·배점 ·
 *   대조완료 · 저장 · 그림 추가 · 삭제) · 미리보기 · 확정(MD 저장)이 필기와 같다.
 *   카드 안만 다르다: 보기(①~④)·정답 번호 대신
 *     문제 쪽: 발문=지시 문장 · 지문=세부 지시사항 · 지정 함수 · 셀 영역 · 자산(자료 표 · 그림)
 *     정답 쪽: 수식 · 대화상자 설정값 · 코드 · 풀이 절차 · 결과 그림
 *   확정은 01/practical/{회차}-{묶음}-{번호}.md (+ .json) — 필기 01/*.md 와 섞지 않는다.
 */
"use strict";

import { $, api, el, escapeHtml, renderMarkdown, toast, confirmModal, stateClass } from "./util.js";
import { getPref, setPref } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const KINDS = ["문제", "정답", "기타"];
const ANS_KINDS = ["수식", "설정", "코드", "절차", "그림"];
const PART_NAME = { 1: "기본작업", 2: "계산작업", 3: "분석작업", 4: "기타작업" };

const S = {
  ctx: null, root: null,
  src: "", pages: [],           // 판독된 쪽(page_table 행)
  page: 0, draft: null, dirty: false,
  scanPage: 0, pendingBox: null, pendingPage: 0,
  showScan: true, showMemo: false, zoom: 1,
  round: 0, rdata: null,
};

const isRound = (ctx) => (ctx.path || "").startsWith("/practical-round");

export const meta = {
  title: (ctx) => (ctx.panel ? "OCR 검수 · 페이지 (실기)"
    : isRound(ctx) ? "OCR 검수 · 회차 묶음 (실기)"
    : `OCR 검수 · ${ctx.args[0] || ""} p.${ctx.args[1] || ""}`),
  subtitle: (ctx) => (ctx.panel
    ? "쪽을 고르면 그 쪽을 검수합니다. 스캔 뜨기·판독은 왼쪽 큰 버튼 [＋ 실기 OCR] 에서 합니다."
    : isRound(ctx) ? "문항 하나에 지시사항과 정답(여러 쪽에 흩어진 조각)을 짝지어 대조합니다. 고치는 것은 쪽 화면에서."
    : "좌 스캔 / 우 문항 카드. 확정하면 01/practical/{회차}-{묶음}-{번호}.md 로 기록됩니다."),
  actions: (ctx) => (ctx.panel
    ? [actionBtn("회차 묶음 보기", () => ctx.navigate("/practical-round"), { iconName: "grid" })]
    : isRound(ctx)
      ? [actionBtn("← 페이지 목록", () => ctx.navigate("/practical-review"), { iconName: "folder" })]
      : [
        actionBtn("← 페이지 목록", () => ctx.navigate("/practical-review"), { iconName: "folder" }),
        actionBtn("◀ 이전", () => gotoPage(-1), { id: "pr-prev-btn" }),
        pageLabel(ctx),
        actionBtn("다음 ▶", () => gotoPage(1), { id: "pr-next-btn" }),
        actionBtn("판독메모 펴기", () => toggleMemo(), { iconName: "file", id: "pr-memo-btn" }),
        actionBtn("스캔 숨기기", () => toggleScan(), { iconName: "panelRight", id: "pr-scan-btn" }),
        zoomControl(),
        actionBtn("＋ 문제 추가", () => addItem()),
        actionBtn("초안 저장", () => saveDraft()),
        actionBtn("초안 삭제", () => deleteDraft(), { iconName: "close" }),
        actionBtn("확정(MD 저장)", () => finalize(), { primary: true, iconName: "check" }),
      ]),
};

function pageLabel(ctx) {
  const s = el("span", "oc-pglabel");
  s.id = "oc-pglabel";
  s.textContent = `${ctx.args[0] || ""} p.${ctx.args[1] || ""}`;
  return s;
}

function zoomControl() {
  const w = el("label", "oc-zoom");
  w.title = "스캔 이미지 확대";
  w.appendChild(el("span", null, "확대"));
  const r = el("input");
  r.type = "range"; r.min = "0.4"; r.max = "3"; r.step = "0.1";
  r.value = String(S.zoom);
  r.addEventListener("input", () => {
    S.zoom = Number(r.value);
    setPref("prZoom", S.zoom);
    const img = $("#oc-scan");
    if (img) img.style.width = (S.zoom * 100) + "%";
  });
  w.appendChild(r);
  return w;
}

export async function mount(root, ctx) {
  S.ctx = ctx;
  S.root = root;
  S.showScan = getPref("prShowScan", true);
  S.showMemo = getPref("prShowMemo", false);
  S.zoom = Number(getPref("prZoom", 1)) || 1;
  await loadTable();
  if (ctx.panel) return mountList(root, ctx);
  if (isRound(ctx)) {
    S.round = Number(ctx.params.get("r")) || 0;
    return drawRound();
  }
  return mountWork(root, ctx);
}

async function loadTable() {
  const ov = await api("/api/practical/overview");
  const s = (ov.srcs || []).find((x) => x.read > 0) || (ov.srcs || [])[0];
  S.src = s ? s.src : "";
  S.pages = s ? s.pages.filter((r) => r.read) : [];
}

/* ══════════ 위층: 패널 — 회차별 쪽 현황판 (필기 renderDash 와 같은 모양) ══════════ */
function mountList(root, ctx) {
  root.innerHTML = `<div class="oc-head" id="oc-head"></div><div class="oc-dash" id="oc-dash"></div>`;
  const head = $("#oc-head");
  const dash = $("#oc-dash");
  if (!S.pages.length) {
    dash.appendChild(el("div", "empty", "판독한 쪽이 없습니다 — 왼쪽 [＋ 실기 OCR] 에서 스캔을 뜨고 판독하세요."));
    return;
  }
  const line = el("div", "oc-book");
  line.appendChild(el("b", null, `${S.src}.pdf`));
  line.appendChild(el("span", "muted", " → 01/practical/"));
  head.appendChild(line);
  const n = S.pages.reduce((a, r) => a + (r.kind === "정답" ? r.n_answers : r.n_items), 0);
  const v = S.pages.reduce((a, r) => a + (r.n_verified || 0), 0);
  const chips = el("div", "vd-env");
  chips.appendChild(el("span", "status-chip", `판독 ${S.pages.length}쪽`));
  chips.appendChild(el("span", "status-chip" + (n && v >= n ? " ok" : ""), `대조완료 ${v}/${n}`));
  head.appendChild(chips);

  const byRound = new Map();
  for (const p of S.pages) {
    const k = p.round == null ? "미분류" : String(p.round);
    if (!byRound.has(k)) byRound.set(k, []);
    byRound.get(k).push(p);
  }
  const keys = [...byRound.keys()].sort((a, b) =>
    a === "미분류" ? 1 : b === "미분류" ? -1 : Number(a) - Number(b));
  for (const k of keys) {
    const block = el("div", "oc-round");
    block.appendChild(el("h3", null, k === "미분류" ? "미분류(회차 모름)" : `${k}회`));
    const grid = el("div", "oc-grid");
    for (const p of byRound.get(k)) {
      const cnt = p.kind === "정답" ? p.n_answers : p.n_items;
      const ver = p.n_verified || 0;
      const cell = el("button", "oc-cell " + (cnt ? stateClass(cnt, ver, true) : stateClass(1, 1, true)));
      cell.type = "button";
      cell.appendChild(el("span", "oc-cell-id st-title", `${p.src}-${String(p.page).padStart(3, "0")}`));
      const unit = p.kind === "정답" ? "답" : "문";
      cell.appendChild(el("small", null,
        cnt ? (ver >= cnt ? `${cnt}${unit} · ✓${ver}` : ver ? `${cnt}${unit} · ✓${ver}/${cnt}` : `${cnt}${unit}`)
          : p.kind === "기타" ? "기타" : "표지·이어짐"));
      if (p.kind === "정답") cell.appendChild(el("span", "qz-mark", "정답"));
      cell.title = `${p.kind || "?"} 쪽` + (cnt ? ` · ${cnt}개 · 대조완료 ${ver}개` : "");
      cell.addEventListener("click", () => ctx.navigate(`/practical-review/${encodeURIComponent(p.src)}/${p.page}`));
      grid.appendChild(cell);
    }
    block.appendChild(grid);
    dash.appendChild(block);
  }
}

/* ══════════ 아래층: 바탕 — 쪽 작업 (필기 mountWork 와 같은 틀) ══════════ */
async function mountWork(root, ctx) {
  const page = el("div", "page oc-page");
  page.innerHTML = `
    <div class="oc-work" id="oc-work">
      <div class="oc-split" id="oc-split" title="끌어서 스캔 폭 조절 · 더블클릭: 기본 폭"></div>
      <div class="oc-pane oc-img" id="oc-imgpane">
        <div class="oc-pagenav" id="oc-pagenav">
          <button class="btn sm" id="oc-pgprev" type="button">◀ 앞 면</button>
          <b id="oc-scanpg"></b>
          <span class="status-chip" id="oc-armed" hidden></span>
          <button class="btn sm" id="oc-pgnext" type="button">다음 면 ▶</button>
          <span class="muted" id="oc-pghint"></span>
        </div>
        <div class="oc-imgwrap" id="oc-imgwrap">
          <img id="oc-scan" alt="스캔 페이지" />
          <div class="oc-sel" id="oc-sel"></div>
        </div>
      </div>
      <div class="oc-pane oc-ocr" id="oc-ocrpane">
        <div class="oc-pane-head"><span>판독 메모</span><span class="muted" id="oc-ocrmeta"></span></div>
        <textarea id="oc-ocrtext" spellcheck="false" placeholder="판독이 남긴 메모 — 회차 표기 유무, 이어지는 문항 등"></textarea>
      </div>
      <div class="oc-pane oc-edit" id="oc-editpane">
        <div class="oc-toolbar" id="pr-toolbar"></div>
        <div class="field-hint" id="oc-hint">
          이미지에서 드래그 → 영역 선택 후, 원하는 카드의 [그림 추가] 클릭.
          번호 오름차순으로 저장됩니다.
        </div>
        <div id="oc-qlist"></div>
      </div>
    </div>`;
  root.appendChild(page);
  hydrateIcons(page);
  bindDrag();
  bindSplit();
  $("#oc-pgprev").addEventListener("click", () => showScanPage(S.scanPage - 1));
  $("#oc-pgnext").addEventListener("click", () => showScanPage(S.scanPage + 1));
  $("#oc-ocrtext").addEventListener("input", (e) => { if (S.draft) { S.draft.notes = e.target.value; markDirty(); } });
  if (!S.keyBound) { S.keyBound = true; document.addEventListener("keydown", onKey); }
  await openPage(decodeURIComponent(ctx.args[0]), Number(ctx.args[1]));
}

function applyLayout() {
  const w = $("#oc-work");
  if (!w) return;
  w.classList.toggle("showscan", S.showScan);
  w.classList.toggle("noocr", !S.showMemo);
  const b1 = $("#pr-memo-btn");
  if (b1 && b1.lastChild) b1.lastChild.textContent = S.showMemo ? "판독메모 접기" : "판독메모 펴기";
  const b2 = $("#pr-scan-btn");
  if (b2 && b2.lastChild) b2.lastChild.textContent = S.showScan ? "스캔 숨기기" : "스캔 보기";
  const img = $("#oc-scan");
  if (img) img.style.width = (S.zoom * 100) + "%";
  placeSplitBar();
}
function toggleScan() { S.showScan = !S.showScan; setPref("prShowScan", S.showScan); applyLayout(); }
function toggleMemo() { S.showMemo = !S.showMemo; setPref("prShowMemo", S.showMemo); applyLayout(); }

async function openPage(src, n) {
  let d;
  try { d = await api(`/api/practical/page/${encodeURIComponent(src)}/${n}`); }
  catch (e) { toast(e.message, "err"); return; }
  S.src = src;
  S.page = n;
  S.draft = d.read || { page_kind: "기타", problem_items: [], answer_entries: [] };
  S.draft.problem_items = S.draft.problem_items || [];
  S.draft.answer_entries = S.draft.answer_entries || [];
  S.draft.problem_items.forEach((x) => ensureAssets(x, n));
  S.draft.answer_entries.forEach((x) => ensureAssets(x, n));
  S.dirty = false;
  $("#oc-ocrtext").value = S.draft.notes || "";
  $("#oc-ocrmeta").textContent = `${src}.pdf p.${n}`;
  S.scanPage = n;
  $("#oc-scan").src = d.scan;
  syncPageNav();
  syncHead();
  toolbar();
  applyLayout();
  renderCards();
  status("불러옴", true);
}

function row() { return S.pages.find((r) => r.page === S.page) || {}; }
function pageKind() { return row().kind || S.draft.page_kind; }

function syncHead() {
  const r = row();
  const i = S.pages.findIndex((x) => x.page === S.page);
  const lab = $("#oc-pglabel");
  if (lab) {
    lab.textContent = `${S.src}.pdf p.${S.page}` + (r.round ? ` · ${r.round}회` : "")
      + (r.kind ? ` · ${r.kind}` : "") + (i >= 0 ? `  (${i + 1}/${S.pages.length})` : "");
  }
  const prev = $("#pr-prev-btn"), next = $("#pr-next-btn");
  if (prev) prev.disabled = i <= 0;
  if (next) next.disabled = i < 0 || i >= S.pages.length - 1;
}

async function gotoPage(delta) {
  const i = S.pages.findIndex((x) => x.page === S.page);
  const nx = i >= 0 ? S.pages[i + delta] : null;
  if (!nx) { toast(delta > 0 ? "마지막 쪽입니다." : "첫 쪽입니다."); return; }
  if (S.dirty && !(await confirmModal({
    title: "저장하지 않은 편집을 버릴까요?",
    body: `<b>${escapeHtml(S.src)} p.${S.page}</b> 의 편집 내용이 사라집니다.`,
    ok: "버리고 이동", cancel: "머무르기", danger: true,
  }))) return;
  S.dirty = false;
  S.ctx.navigate(`/practical-review/${encodeURIComponent(S.src)}/${nx.page}`);
}

function onKey(e) {
  if (!location.hash.startsWith("#/practical-review/")) return;
  if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) { e.preventDefault(); saveDraft(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); finalize(); return; }
  if (e.altKey && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
    e.preventDefault(); gotoPage(e.key === "ArrowRight" ? 1 : -1);
  }
}
window.addEventListener("beforeunload", (e) => {
  if (S.dirty && location.hash.startsWith("#/practical-review/")) { e.preventDefault(); e.returnValue = ""; }
});

/* 편집면 위 줄 — 필기의 「회차 · 정답키줄」 자리에 「회차 · 쪽 종류」 */
function toolbar() {
  const t = $("#pr-toolbar");
  t.innerHTML = "";
  const r = row();
  const rl = el("label");
  rl.append(document.createTextNode("회차 "));
  const rnd = el("input");
  rnd.type = "number"; rnd.min = "1"; rnd.id = "oc-round";
  rnd.value = r.round || "";
  rnd.title = r.round_by ? `회차: ${r.round_by}` : "";
  rnd.addEventListener("change", () => saveMap({ round: Number(rnd.value || 0) }));
  rl.appendChild(rnd);
  const kl = el("label");
  kl.append(document.createTextNode("쪽 종류 "));
  const kind = el("select");
  for (const k of KINDS) {
    const o = el("option", null, k); o.value = k;
    if (k === pageKind()) o.selected = true;
    kind.appendChild(o);
  }
  kind.addEventListener("change", () => saveMap({ kind: kind.value }));
  kl.appendChild(kind);
  const list = pageKind() === "정답" ? S.draft.answer_entries : S.draft.problem_items;
  const done = list.filter((x) => x.verified).length;
  const prog = el("span", "status-chip" + (list.length && done === list.length ? " ok" : ""), `대조완료 ${done}/${list.length}`);
  const st = el("span", "muted", "");
  st.id = "oc-status";
  t.append(rl, kl, prog, st);
}

function status(text, ok) {
  const s = $("#oc-status");
  if (s) { s.textContent = text; s.className = ok ? "muted" : "warn"; }
}
function markDirty() { S.dirty = true; status("저장 안 됨", false); }

async function saveMap(patch) {
  try {
    await api("/api/practical/pagemap", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({ src: S.src, page: S.page }, patch)),
    });
    toast(`p.${S.page} 고쳤습니다.`);
    await loadTable();
    syncHead(); toolbar(); renderCards();
  } catch (e) { toast("저장하지 못했습니다: " + e.message, "err"); }
}

function sortItems() {
  const key = (x) => (Number(x.part) || 99) * 1000 + (Number(x.no) || 999);
  S.draft.problem_items.sort((a, b) => key(a) - key(b));
}

async function saveDraft(quiet) {
  sortItems();
  try {
    await api(`/api/practical/page/${encodeURIComponent(S.src)}/${S.page}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(S.draft),
    });
    S.dirty = false;
    await loadTable();
    syncHead(); toolbar(); renderCards();
    status("초안 저장됨", true);
    if (!quiet) toast(`p.${S.page} 저장했습니다.`);
    return true;
  } catch (e) { toast("저장하지 못했습니다: " + e.message, "err"); return false; }
}

async function deleteDraft() {
  if (!(await confirmModal({
    title: "이 쪽 판독 결과를 지울까요?",
    body: `<b>${escapeHtml(S.src)} p.${S.page}</b> 의 판독 결과가 사라집니다. [＋ 실기 OCR] 에서 이 쪽만 다시 판독할 수 있습니다. 확정본(01/practical)은 그대로입니다.`,
    ok: "지우기", cancel: "취소", danger: true,
  }))) return;
  try {
    await api(`/api/practical/page/${encodeURIComponent(S.src)}/${S.page}`, { method: "DELETE" });
    S.dirty = false;
    toast(`p.${S.page} 판독 결과를 지웠습니다.`);
    S.ctx.navigate("/practical-review");
  } catch (e) { toast("지우지 못했습니다: " + e.message, "err"); }
}

/* 확정 — 이 쪽이 속한 회차 전체를 01/practical/ 에 문항마다 다시 쓴다(지시사항과 정답이 여러 쪽에 흩어져 있어서) */
async function finalize(quiet) {
  if (S.dirty && !(await saveDraft(true))) return;
  try {
    const r = await api("/api/practical/finalize", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ src: S.src, page: S.page }),
    });
    status(`확정 ${r.wrote.length}문항 → 01/practical/`, true);
    if (!quiet) {
      toast(`${r.round}회 ${r.wrote.length}문항을 01/practical/ 에 기록했습니다.`
        + (r.skipped.length ? ` 건너뜀: ${r.skipped.join(", ")}` : ""), r.skipped.length ? "err" : "");
    }
  } catch (e) { toast("확정하지 못했습니다: " + e.message, "err"); }
}

function addItem() {
  if (pageKind() === "정답") {
    S.draft.answer_entries.push({ part: null, no: null, title: "", kind: "수식", formulas: [], settings: [], code: "", steps: [] });
  } else {
    S.draft.problem_items.push({ part: null, no: null, lead: "", points: null, instructions: [], functions: [], ranges: [] });
  }
  markDirty();
  renderCards();
}

/* ── 카드 ── */
function renderCards() {
  const box = $("#oc-qlist");
  if (!box) return;
  box.innerHTML = "";
  const kind = pageKind();
  if (kind === "정답") {
    if (!S.draft.answer_entries.length) box.appendChild(el("div", "empty", "이 쪽에 판독된 정답이 없습니다. 상단 [＋ 문제 추가] 로 직접 만드세요."));
    S.draft.answer_entries.forEach((a, i) => box.appendChild(ansCard(a, i)));
  } else if (kind === "문제") {
    if (!S.draft.problem_items.length) {
      box.appendChild(el("div", "empty", "이 쪽에 판독된 문항이 없습니다(시험지 표지·이어지는 쪽이면 정상). 상단 [＋ 문제 추가] 로 직접 만드세요."));
    }
    S.draft.problem_items.forEach((q, i) => box.appendChild(qCard(q, i)));
  } else {
    box.appendChild(el("div", "empty", "기타 쪽 — 문항도 정답도 없는 쪽입니다. 틀렸으면 위 「쪽 종류」 를 바꾸세요."));
  }
}

function area(value, placeholder, onInput, rows, mono) {
  const t = el("textarea");
  t.rows = rows || 2;
  t.value = value || "";
  t.placeholder = placeholder || "";
  t.spellcheck = false;
  if (mono) t.classList.add("mono");
  const grow = () => { t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight + 2, 480) + "px"; };
  t.addEventListener("input", () => { onInput(t.value); grow(); });
  requestAnimationFrame(grow);
  return t;
}
function input(value, placeholder, onInput) {
  const t = el("input");
  t.type = "text"; t.value = value || ""; t.placeholder = placeholder || "";
  t.addEventListener("input", () => onInput(t.value));
  return t;
}
function labeled(text, node) {
  const w = el("div", "oc-field");
  w.appendChild(el("label", "qz-label", text));
  w.appendChild(node);
  return w;
}
function numField(label, value, onInput, width) {
  const w = el("label", "oc-inline");
  w.appendChild(el("span", null, label));
  const t = el("input");
  t.type = "number"; t.min = "0"; t.value = value ?? ""; t.style.width = (width || 56) + "px";
  t.addEventListener("input", () => onInput(t.value === "" ? null : Number(t.value)));
  w.appendChild(t);
  return w;
}
function lines(v) { return (v || "").split("\n").map((s) => s.trim()).filter(Boolean); }

/* ══ 자산 — 필기와 같은 토큰 방식 ══════════════════════════════════════════
 * 자산마다 이름표가 있다: 자료 표 {{t-1}} · 그림 {{p-1}}. 지문(정답은 풀이 절차) 줄 사이에
 * 이름표 한 줄을 두면 **그 자리에** 펼쳐진다. 이름표를 두지 않은 자산은 맨 끝에 붙는다
 * (2026-11-09: "원숫자 2 다음에 나와야 한다든지 할 때 어떻게 하는 법이 있나요").
 * 옛 판독의 figure_table · figure_bbox 는 불러올 때 t-1 · p-1 로 옮긴다(이름표 없음 = 맨 끝). */
const TOKEN_RE = /\{\{([tp]-\d+)\}\}/g;

function ensureAssets(x, page) {
  x.assets = x.assets && typeof x.assets === "object" ? x.assets : {};
  if (x.figure_table) {
    x.assets[nextAssetId(x, "t")] = { type: "table", md: x.figure_table };
    delete x.figure_table;
  }
  if (x.figure_bbox) {
    const a = { type: "figure", bbox: x.figure_bbox, note: x.figure || "" };
    const pg = Number(x.figure_page) || 0;
    if (pg && pg !== Number(page)) a.page = pg;
    x.assets[nextAssetId(x, "p")] = a;
    delete x.figure_bbox;
    delete x.figure_page;
  }
}

function nextAssetId(x, prefix) {
  let n = 1;
  while ((x.assets || {})[`${prefix}-${n}`]) n += 1;
  return `${prefix}-${n}`;
}

function cropSrc(a, page) {
  const [bx, by, bw, bh] = a.bbox;
  const pg = Number(a.page) || Number(page) || S.page;
  return `/api/ocr/crop?src=${encodeURIComponent(S.src)}&page=${pg}&x=${bx}&y=${by}&w=${bw}&h=${bh}`;
}

/* 자산 하나를 보이는 모양으로 */
function assetNode(a, page) {
  const w = el("div");
  w.style.margin = "8px 0";
  if (a.type === "table") {
    w.className = "tbl-md";
    w.innerHTML = renderMarkdown(a.md || "");
    w.querySelectorAll("table").forEach((t) => t.classList.add("tbl"));
  } else if (a.type === "figure") {
    if (a.bbox) {
      const img = el("img");
      img.src = cropSrc(a, page);
      img.alt = a.note || "그림";
      img.style.cssText = "max-width:100%;border:1px solid var(--hairline);border-radius:6px";
      w.appendChild(img);
    } else {
      w.appendChild(el("div", "field-hint", "그림 영역 미지정"));
    }
  }
  return w;
}

/* 줄 목록 + 자산 → 화면. 이름표 줄은 그 자리에 자산을 펼치고, 남은 자산은 맨 끝에.
 * 인쇄된 기호를 그대로 쓰고, 원문자(①~⑳) 항목 아래 딸린 ▶ 줄만 들여쓴다(앱이 기호를 붙이지 않는다). */
const CIRCLED_RE = /^[\u2460-\u2473\u2776-\u277F]/;
function linesWithAssets(list, x, page, opts = {}) {
  const box = el("div");
  const assets = x.assets || {};
  const used = new Set();
  let under = false;
  (list || []).forEach((raw, idx) => {
    const s = String(raw || "").trim();
    const parts = s.split(TOKEN_RE);          // [글, id, 글, id, …]
    const textOnly = parts.filter((_, k) => k % 2 === 0).join("").trim();
    if (CIRCLED_RE.test(textOnly)) under = true;
    else if (textOnly && !textOnly.startsWith("▶") && !textOnly.startsWith("※")) under = false;
    const indent = under && (textOnly.startsWith("▶") || textOnly.startsWith("※"));
    parts.forEach((part, k) => {
      if (k % 2 === 1) {
        if (assets[part]) { box.appendChild(assetNode(assets[part], page)); used.add(part); }
        else box.appendChild(el("div", "field-hint", `{{${part}}} — 없는 자산`));
        return;
      }
      if (!part.trim()) return;
      const pEl = el("p", null, part.trim());
      pEl.style.margin = "6px 0";
      if (indent) pEl.style.paddingLeft = "1.6em";
      box.appendChild(pEl);
    });
  });
  Object.keys(assets).filter((id) => !used.has(id)).forEach((id) => box.appendChild(assetNode(assets[id], page)));
  return box;
}

/* 자산 상자 — 필기 「자산(표/SQL박스/그림)」 와 같은 모양. target: 이름표를 넣을 줄 목록 칸 이름 */
function assetsBox(x, target, targetLabel) {
  const box = el("div", "oc-assets");
  const head = el("div", "oc-assets-head");
  head.appendChild(el("span", null, "자산(자료 표/그림)"));
  const addT = el("button", "btn sm", "＋표");
  addT.type = "button";
  addT.addEventListener("click", () => {
    const id = nextAssetId(x, "t");
    x.assets[id] = { type: "table", md: "" };
    putToken(x, target, id);
    markDirty(); renderCards();
  });
  const addP = el("button", "btn sm", "＋그림");
  addP.type = "button";
  addP.addEventListener("click", () => addFigure(x, target));
  head.append(addT, addP);
  head.appendChild(el("span", "field-hint",
    `이름표 {{t-1}} · {{p-1}} 를 ${targetLabel} 줄 사이에 한 줄로 두면 그 자리에 펼쳐집니다 · 이름표가 없는 자산은 맨 끝에 붙습니다`));
  box.appendChild(head);

  const ids = Object.keys(x.assets || {});
  if (!ids.length) { box.appendChild(el("span", "field-hint", "자산 없음")); return box; }
  const placed = new Set();
  (x[target] || []).forEach((l) => String(l).replace(TOKEN_RE, (_, id) => { placed.add(id); return ""; }));
  ids.forEach((id) => {
    const a = x.assets[id];
    const row = el("div", "oc-asset");
    const bar = el("div", "oc-asset-bar");
    const tok = el("button", "oc-tok", `{{${id}}}`);
    tok.type = "button";
    tok.title = `${targetLabel} 칸에서 마지막으로 커서를 둔 자리에 이름표 한 줄 넣기`;
    tok.addEventListener("click", () => {
      putToken(x, target, id);
      markDirty(); renderCards();
      status(`${targetLabel}에 {{${id}}} 넣음`, false);
    });
    bar.appendChild(tok);
    bar.appendChild(el("span", "badge", a.type === "table" ? "자료 표" : "그림"));
    bar.appendChild(el("span", "muted", placed.has(id) ? "· 이름표 자리에 펼침" : "· 맨 끝에 붙음"));
    const del = el("button", "btn sm", "✕");
    del.type = "button";
    del.title = "이 자산 삭제 (이름표 줄도 지웁니다)";
    del.addEventListener("click", () => {
      delete x.assets[id];
      const tk = new RegExp("\\{\\{" + id + "\\}\\}", "g");
      x[target] = (x[target] || []).map((l) => String(l).replace(tk, "").trim()).filter(Boolean);
      markDirty(); renderCards();
    });
    bar.appendChild(del);
    row.appendChild(bar);
    if (a.type === "table") {
      row.appendChild(area(a.md || "", "| 코드 | 이름 | …", (v) => { a.md = v; markDirty(); }, 4, true));
    } else {
      const fr = el("div", "oc-figrow");
      if (a.bbox) { const img = el("img"); img.src = cropSrc(a, S.page); fr.appendChild(img); }
      else fr.appendChild(el("span", "muted", "영역 미지정"));
      const setb = el("button", "btn sm", "영역지정(드래그 후)");
      setb.type = "button";
      setb.addEventListener("click", () => {
        if (!takePending()) return;
        a.bbox = S.pendingBox;
        stampPage(a);
        clearPending();
        markDirty(); renderCards();
      });
      fr.appendChild(setb);
      if (a.page && Number(a.page) !== Number(S.page)) {
        const gob = el("button", "btn sm", `p.${a.page} 보기`);
        gob.type = "button";
        gob.addEventListener("click", () => { if (!S.showScan) toggleScan(); showScanPage(Number(a.page)); });
        fr.appendChild(el("span", "status-chip info", `다른 면 p.${a.page}`));
        fr.appendChild(gob);
      }
      fr.appendChild(input(a.note || "", "설명", (v) => { a.note = v; markDirty(); }));
      row.appendChild(fr);
    }
    box.appendChild(row);
  });
  return box;
}

/* 드래그한 영역이 있는지 — 없으면 무엇이 없는지 그대로 말한다(필기와 같은 문구) */
function takePending() {
  if (S.pendingBox) return true;
  if (!S.showScan) { toggleScan(); toast("스캔을 켰습니다 — 그림을 감싸도록 드래그한 뒤 다시 누르세요."); }
  else toast("드래그한 영역이 없습니다 — 왼쪽 스캔에서 그림을 감싸도록 드래그한 뒤 다시 누르세요.", "err");
  return false;
}
function stampPage(a) {
  const pg = Number(S.pendingPage) || 0;
  if (pg && pg !== Number(S.page)) a.page = pg; else delete a.page;
}
function clearPending() {
  S.pendingBox = null; S.pendingPage = 0;
  const sel = $("#oc-sel");
  if (sel) sel.style.display = "none";
  syncPageNav();
}

/* [그림 추가] — 드래그한 영역으로 그림 자산을 만들고 이름표를 맨 끝 줄에 넣는다(옮기면 그 자리로) */
/* ★ 이름표는 **커서 자리**에 넣는다(2026-11-09 지시: "그림 추가를 누르는 순간 마우스 커서가 있는데
 *   이름표가 바로 그 위치에 될 수는 없을까요" · "늘 맨 밑에 생긴다"). 카드의 지문(정답은 풀이 절차)
 *   칸을 기억해 두고, 버튼을 눌러 칸이 포커스를 잃어도 남아 있는 selectionStart 를 쓴다.
 *     빈 줄에 커서 → 그 줄이 이름표 / 글 줄에 커서 → 그 줄 바로 다음 줄 / 칸을 누른 적 없음 → 맨 끝
 *   WeakMap 이라 초안 JSON 에 섞이지 않는다. */
const TA = new WeakMap();      // 카드 데이터 → 이름표를 넣을 textarea
const CARET = new WeakMap();   // 카드 데이터 → 사람이 그 칸에 커서를 둔 적이 있는가
function trackCaret(x, ta) {
  TA.set(x, ta);
  ["focus", "click", "keyup", "select"].forEach((ev) => ta.addEventListener(ev, () => CARET.set(x, true)));
  return ta;
}
function putToken(x, target, id) {
  const tok = `{{${id}}}`;
  const ta = TA.get(x);
  if (!ta || !CARET.get(x)) {                 // 커서를 둔 적이 없으면 맨 끝
    x[target] = (x[target] || []).concat(tok);
    return;
  }
  const v = ta.value;
  const pos = Math.min(ta.selectionStart ?? v.length, v.length);
  const ls = v.lastIndexOf("\n", pos - 1) + 1;              // 커서 줄의 시작
  let le = v.indexOf("\n", pos); if (le < 0) le = v.length;  // 커서 줄의 끝
  const nv = v.slice(ls, le).trim() === ""
    ? v.slice(0, ls) + tok + v.slice(le)                     // 빈 줄 → 그 줄을 이름표로
    : v.slice(0, le) + "\n" + tok + v.slice(le);             // 글 줄 → 바로 다음 줄에
  x[target] = lines(nv);
}

function addFigure(x, target) {
  if (!takePending()) return;
  const id = nextAssetId(x, "p");
  const a = { type: "figure", bbox: S.pendingBox, note: "" };
  stampPage(a);
  x.assets[id] = a;
  putToken(x, target, id);
  clearPending();
  markDirty(); renderCards();
}

function headButtons(head, list, i, x) {
  head.appendChild(el("div", "oc-spacer"));
  // 대조완료 — 필기처럼 누르는 즉시 저장한다(체크만 하고 저장을 잊으면 진행 현황이 거짓말을 한다)
  const chk = el("label", "oc-chk");
  const cb = el("input");
  cb.type = "checkbox";
  cb.checked = !!x.verified;
  cb.addEventListener("change", async () => {
    x.verified = cb.checked;
    markDirty();
    if (await saveDraft(true)) await finalize(true);
  });
  chk.append(cb, el("span", null, "대조완료"));
  head.appendChild(chk);
  const save = el("button", "btn sm primary", "저장");
  save.type = "button";
  save.title = "저장 + 확정 (이 회차를 01/practical/ 에 다시 기록)";
  save.addEventListener("click", async () => { if (await saveDraft(true)) await finalize(); });
  head.appendChild(save);
  const fig = el("button", "btn sm", "그림 추가");
  fig.type = "button";
  fig.title = "스캔에서 드래그한 영역을 이 카드의 그림 자산으로 — 이름표를 옮기면 그 자리에 나옵니다";
  fig.addEventListener("click", () => addFigure(x, x.instructions !== undefined || list === S.draft.problem_items ? "instructions" : "steps"));
  head.appendChild(fig);
  const del = el("button", "btn sm", "삭제");
  del.type = "button";
  del.addEventListener("click", () => { list.splice(i, 1); markDirty(); renderCards(); });
  head.appendChild(del);
}

function idChip(x) {
  const c = el("b", "oc-qid", `${x.part ?? "?"}-${x.no ?? "?"}`);
  c.style.cssText = "font-size:20px;font-weight:800;min-width:2.6em";
  c.title = "묶음-문항 — 문제 카드와 정답 카드가 이 번호로 짝지어집니다";
  return c;
}
function refreshId(card, x) { const c = card.querySelector(".oc-qid"); if (c) c.textContent = `${x.part ?? "?"}-${x.no ?? "?"}`; }

function qCard(q, i) {
  const card = el("div", "oc-q" + (q.verified ? " verified" : ""));
  const head = el("div", "oc-q-head");
  head.appendChild(idChip(q));
  head.appendChild(numField("묶음", q.part, (v) => { q.part = v; markDirty(); refreshId(card, q); }, 46));
  head.appendChild(numField("문항", q.no, (v) => { q.no = v; markDirty(); refreshId(card, q); }, 56));
  head.appendChild(numField("배점", q.points, (v) => { q.points = v; markDirty(); }, 52));
  if (q.part && PART_NAME[q.part]) head.appendChild(el("span", "muted", PART_NAME[q.part]));
  headButtons(head, S.draft.problem_items, i, q);
  card.appendChild(head);

  card.appendChild(labeled("발문(지시 문장)", area(q.lead, "번호 줄의 문장 그대로", (v) => { q.lead = v; markDirty(); }, 2)));
  card.appendChild(labeled("지문(세부 지시사항 — 한 줄에 하나)",
    trackCaret(q, area((q.instructions || []).join("\n"), "인쇄된 그대로 — ① ② 원문자, ▶ 기호까지", (v) => { q.instructions = lines(v); markDirty(); }, 5))));
  card.appendChild(labeled("지정 함수 (쉼표로)",
    input((q.functions || []).join(", "), "AND, YEAR, RIGHT", (v) => {
      q.functions = v.split(",").map((s) => s.trim()).filter(Boolean); markDirty();
    })));
  card.appendChild(labeled("셀·영역 (쉼표로)",
    input((q.ranges || []).join(", "), "A3:H28, A30", (v) => {
      q.ranges = v.split(",").map((s) => s.trim()).filter(Boolean); markDirty();
    })));
  card.appendChild(labeled("그림 설명", input(q.figure, "입력할 자료 표 · 결과 그림 등", (v) => { q.figure = v; markDirty(); })));
  card.appendChild(assetsBox(q, "instructions", "지문"));
  if (q.note) card.appendChild(el("div", "field-hint", "메모: " + q.note));
  card.appendChild(previewFoot(() => previewProblem(q)));
  return card;
}

function ansCard(a, i) {
  const card = el("div", "oc-q" + (a.verified ? " verified" : ""));
  const head = el("div", "oc-q-head");
  head.appendChild(idChip(a));
  head.appendChild(numField("묶음", a.part, (v) => { a.part = v; markDirty(); refreshId(card, a); }, 46));
  head.appendChild(numField("문항", a.no, (v) => { a.no = v; markDirty(); refreshId(card, a); }, 56));
  const k = el("select");
  for (const x of ANS_KINDS) { const o = el("option", null, x); o.value = x; if (x === a.kind) o.selected = true; k.appendChild(o); }
  k.addEventListener("change", () => { a.kind = k.value; markDirty(); });
  const kl = el("label", "oc-inline"); kl.append(el("span", null, "종류"), k);
  head.appendChild(kl);
  headButtons(head, S.draft.answer_entries, i, a);
  card.appendChild(head);

  card.appendChild(labeled("제목", input(a.title, "문제2 계산작업 ❶ …", (v) => { a.title = v; markDirty(); })));
  // ★ 지금은 **풀이 절차 + 그림**만 펴 둔다(2026-11-09 지시: "그 부분만 활성화 — 그림을 캡처해서 넣어야
  //   해서… 수식·설정값은 일단 닫아 둡시다"). 줄 수를 제목에 적지 않는다 — 판독이 나눈 줄 수는 뜻이 없다.
  card.appendChild(labeled("풀이 절차 (한 줄에 하나 · 그림은 이름표 줄로)",
    trackCaret(a, area((a.steps || []).join("\n"), "한 줄에 하나", (v) => { a.steps = lines(v); markDirty(); }, 4))));
  card.appendChild(assetsBox(a, "steps", "풀이 절차"));
  const more = el("details");
  more.appendChild(el("summary", null, "수식 · 설정값 · 코드"));
  more.appendChild(labeled("수식 (한 줄에 하나 · 「셀 : 수식」)",
    area((a.formulas || []).map((f) => (f.cell ? f.cell + " : " : "") + f.formula).join("\n"),
      "D11 : =AVERAGEIFS(…)", (v) => {
        a.formulas = lines(v).map((s) => {
          const m = s.match(/^([A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?)\s*:\s*(.+)$/);
          return m ? { cell: m[1], formula: m[2] } : { formula: s };
        });
        markDirty();
      }, 3, true)));
  more.appendChild(labeled("설정값 (한 줄에 하나 · 「대화상자 › 항목 = 값」)",
    area((a.settings || []).map((s) => [s.dialog, s.field].filter(Boolean).join(" › ") + " = " + (s.value || "")).join("\n"),
      "고급 필터 › 목록 범위 = $A$3:$H$28", (v) => {
        a.settings = lines(v).map((s) => {
          const m = s.match(/^(.*?)\s*=\s*(.*)$/);
          if (!m) return { value: s };
          const [dlg, fld] = m[1].split("›").map((x) => x.trim());
          return { dialog: fld === undefined ? "" : dlg, field: fld === undefined ? dlg : fld, value: m[2] };
        });
        markDirty();
      }, 3)));
  more.appendChild(labeled("코드 (VBA·매크로)", area(a.code, "Sub …", (v) => { a.code = v; markDirty(); }, 3, true)));
  card.appendChild(more);
  if (a.note) card.appendChild(el("div", "field-hint", "메모: " + a.note));
  card.appendChild(previewFoot(() => previewAnswer(a)));
  return card;
}

/* ── 미리보기 — 문제지·해설에 실릴 모양 그대로 ── */
function previewFoot(make) {
  const wrap = el("div");
  const foot = el("div", "oc-q-foot");
  const pv = el("button", "btn sm", "👁 미리보기");
  pv.type = "button";
  const box = el("div", "oc-preview");
  box.hidden = true;
  pv.addEventListener("click", () => {
    if (box.hidden) {
      box.innerHTML = "";
      box.appendChild(make());
      box.hidden = false;
      pv.textContent = "✕ 미리보기 닫기";
    } else {
      box.hidden = true;
      pv.textContent = "👁 미리보기";
    }
  });
  foot.appendChild(pv);
  foot.appendChild(el("span", "field-hint", "← 고친 내용이 실제로 어떻게 보이는지 확인"));
  wrap.append(foot, box);
  return wrap;
}

function previewProblem(q) {
  const n = el("div");
  n.innerHTML = `<div class="oc-pv-qno">${q.part ?? "?"}-${q.no ?? "?"}</div>`
    + `<p><b>${escapeHtml(q.lead || "")}</b></p>`;
  n.appendChild(linesWithAssets(q.instructions, q, S.page));   // 적힌 줄 그대로 + 이름표 자리에 자산
  return n;
}

function previewAnswer(a) {
  const n = el("div");
  const h = [`<div class="oc-pv-qno">${a.part ?? "?"}-${a.no ?? "?"}</div>`,
    `<p><b>${escapeHtml(a.title || "")}</b></p>`];
  for (const f of a.formulas || []) {
    h.push(`<p><code>${escapeHtml((f.cell ? "[" + f.cell + "] " : "") + f.formula)}</code></p>`);
  }
  if ((a.settings || []).length) {
    h.push(`<table class="tbl"><tbody>` + a.settings.map((s) =>
      `<tr><td>${escapeHtml(s.dialog || "")}</td><td>${escapeHtml(s.field || "")}</td><td><b>${escapeHtml(s.value || "")}</b></td></tr>`).join("")
      + `</tbody></table>`);
  }
  if (a.code) h.push(`<pre class="pb-cmd">${escapeHtml(a.code)}</pre>`);
  n.innerHTML = h.join("");
  n.appendChild(linesWithAssets(a.steps, a, S.page));   // 번호를 붙이지 않는다 — 적힌 줄 그대로
  return n;
}

/* ── 스캔: 면 넘기기 · 드래그 · 폭 조절 (필기 ocr.js 와 같은 동작) ── */
function showScanPage(n) {
  const img = $("#oc-scan");
  if (!img) return;
  S.scanPage = Math.max(1, Number(n) || S.page);
  img.src = `/api/ocr/scan/${encodeURIComponent(S.src)}/${S.scanPage}`;
  S.pendingBox = null; S.pendingPage = 0;
  const sel = $("#oc-sel");
  if (sel) sel.style.display = "none";
  syncPageNav();
}

function syncPageNav() {
  const lab = $("#oc-scanpg");
  if (lab) lab.textContent = `p.${S.scanPage}`;
  const hint = $("#oc-pghint");
  if (hint) {
    hint.textContent = S.scanPage === S.page ? "이 쪽"
      : `다른 면 — 여기서 드래그하면 그림이 p.${S.scanPage} 좌표로 남습니다`;
    hint.classList.toggle("warn", S.scanPage !== S.page);
  }
  const arm = $("#oc-armed");
  if (arm) {
    arm.hidden = !S.pendingBox;
    if (S.pendingBox) {
      arm.className = "status-chip ok";
      arm.textContent = `영역 선택됨 p.${S.pendingPage} ${S.pendingBox[2]}×${S.pendingBox[3]} → 카드의 [영역지정]`;
    }
  }
  const prev = $("#oc-pgprev");
  if (prev) prev.disabled = S.scanPage <= 1;
}

function bindDrag() {
  const wrap = $("#oc-imgwrap"), img = $("#oc-scan"), sel = $("#oc-sel");
  let sx = 0, sy = 0, drag = false;
  wrap.addEventListener("mousedown", (e) => {
    if (e.target !== img) return;
    const r = img.getBoundingClientRect();
    sx = e.clientX - r.left; sy = e.clientY - r.top; drag = true;
    Object.assign(sel.style, { display: "block", left: sx + "px", top: sy + "px", width: "0", height: "0" });
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    const r = img.getBoundingClientRect();
    const cx = e.clientX - r.left, cy = e.clientY - r.top;
    Object.assign(sel.style, {
      left: Math.min(sx, cx) + "px", top: Math.min(sy, cy) + "px",
      width: Math.abs(cx - sx) + "px", height: Math.abs(cy - sy) + "px",
    });
  });
  window.addEventListener("mouseup", () => {
    if (!drag) return;
    drag = false;
    const r = img.getBoundingClientRect();
    const scale = img.naturalWidth / r.width;   // 화면 좌표 → 원본 픽셀
    const x = parseFloat(sel.style.left), y = parseFloat(sel.style.top);
    const w = parseFloat(sel.style.width), h = parseFloat(sel.style.height);
    if (w < 8 || h < 8) { sel.style.display = "none"; return; }
    S.pendingBox = [x, y, w, h].map((v) => Math.round(v * scale));
    S.pendingPage = S.scanPage;
    syncPageNav();
  });
}

function placeSplitBar() {
  const w = $("#oc-work"), bar = $("#oc-split");
  if (!w || !bar) return;
  const pct = Number(getPref("ocrScanW", 0)) || 0;
  if (pct) w.style.setProperty("--oc-scan-w", pct + "%"); else w.style.removeProperty("--oc-scan-w");
  const pane = $("#oc-imgpane");
  if (pane && S.showScan) bar.style.left = pane.offsetWidth + "px";
}

function bindSplit() {
  const w = $("#oc-work"), bar = $("#oc-split");
  if (!w || !bar) return;
  const place = () => {
    const pct = Number(getPref("ocrScanW", 0)) || 0;
    if (pct) w.style.setProperty("--oc-scan-w", pct + "%"); else w.style.removeProperty("--oc-scan-w");
    const pane = $("#oc-imgpane");
    if (pane) bar.style.left = pane.offsetWidth + "px";
  };
  place();
  setTimeout(place, 50);
  bar.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    bar.setPointerCapture(e.pointerId);
    bar.classList.add("drag"); w.classList.add("resizing");
    const r = w.getBoundingClientRect();
    const move = (ev) => {
      const pct = Math.min(85, Math.max(15, ((ev.clientX - r.left) / r.width) * 100));
      w.style.setProperty("--oc-scan-w", pct.toFixed(1) + "%");
      bar.style.left = $("#oc-imgpane").offsetWidth + "px";
    };
    const up = () => {
      bar.removeEventListener("pointermove", move);
      bar.classList.remove("drag"); w.classList.remove("resizing");
      setPref("ocrScanW", Math.round(($("#oc-imgpane").offsetWidth / w.clientWidth) * 1000) / 10);
    };
    bar.addEventListener("pointermove", move);
    bar.addEventListener("pointerup", up, { once: true });
  });
  bar.addEventListener("dblclick", () => { setPref("ocrScanW", 0); place(); });
}

/* ══════════ 회차 묶음 — 문항 하나에 지시사항과 정답을 짝지어 대조 ══════════ */
async function drawRound() {
  const page = el("div", "page");
  page.style.maxWidth = "none";
  page.innerHTML = `
    <div class="card"><div id="rv-rounds"><div class="empty">불러오는 중…</div></div></div>
    <div style="display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:14px;align-items:start">
      <div id="rv-items"></div>
      <div class="card" style="position:sticky;top:12px">
        <div class="card-title" id="rv-scantitle">스캔</div>
        <div id="rv-scan" class="empty">카드의 쪽 번호를 누르면 여기에 스캔이 뜹니다.</div>
      </div>
    </div>`;
  S.root.appendChild(page);
  try {
    const head = await api(`/api/practical/review?src=${encodeURIComponent(S.src)}`);
    if (!S.round && head.rounds.length) S.round = head.rounds[0].round;
    S.rdata = S.round ? await api(`/api/practical/review?src=${encodeURIComponent(S.src)}&round=${S.round}`) : head;
  } catch (e) { $("#rv-rounds").textContent = "불러오지 못했습니다: " + e.message; return; }

  const box = $("#rv-rounds");
  box.innerHTML = "";
  const rowEl = el("div", "qz-foot");
  rowEl.style.flexWrap = "wrap";
  for (const r of S.rdata.rounds || []) {
    const b = el("button", "btn" + (r.round === S.round ? " primary" : ""),
      `${String(r.round).padStart(2, "0")}회 · 문항 ${r.items} · 정답 ${r.answers}`);
    b.type = "button";
    b.addEventListener("click", () => S.ctx.navigate(`/practical-round?r=${r.round}`));
    rowEl.appendChild(b);
  }
  box.appendChild(rowEl);
  const items = S.rdata.items || [];
  const bad = items.filter((it) => it.flags.length).length;
  box.appendChild(el("div", "field-hint",
    `${String(S.round).padStart(2, "0")}회 — 문항 ${items.length}개`
    + (bad ? ` · 확인할 것 ${bad}개(빨간 표시) — 쪽 번호를 누르면 스캔, 고치는 것은 쪽 화면에서` : " · 표시된 문제 없음")));
  const list = $("#rv-items");
  for (const it of items) list.appendChild(roundCard(it));
}

function roundChip(p, label) {
  const b = el("button", "btn sm", `${label} p.${p}`);
  b.type = "button";
  b.title = "스캔 보기 · 더블클릭: 이 쪽 검수 화면으로";
  b.addEventListener("dblclick", () => S.ctx.navigate(`/practical-review/${encodeURIComponent(S.src)}/${p}`));
  b.addEventListener("click", () => {
    $("#rv-scantitle").textContent = `스캔 — p.${p}`;
    const box = $("#rv-scan");
    box.className = ""; box.innerHTML = "";
    const img = el("img");
    img.src = `/api/ocr/scan/${encodeURIComponent(S.src)}/${p}`;
    img.style.cssText = "width:100%;border:1px solid var(--hairline);border-radius:6px;max-height:82vh;object-fit:contain";
    box.appendChild(img);
  });
  return b;
}

function roundCard(it) {
  const c = el("div", "card");
  if (it.flags.length) c.style.borderLeft = "4px solid var(--brand)";
  const p0 = it.problems[0] || {};
  const head = el("div", "card-title");
  head.innerHTML = `문제${it.part || "?"}-${it.no || "?"} `
    + `<span class="muted">${escapeHtml(PART_NAME[it.part] || p0.part_name || "")}</span>`
    + (p0.points != null ? ` <span class="muted">· ${p0.points}점</span>` : "")
    + it.flags.map((f) => ` <span class="status-chip err">${escapeHtml(f)}</span>`).join("")
    + (it.verified ? ` <span class="status-chip ok">대조완료</span>` : "");
  c.appendChild(head);
  for (const p of it.problems) {
    const sec = el("div");
    sec.style.margin = "6px 0 10px";
    sec.innerHTML = `<div><b>${escapeHtml(p.lead || "")}</b></div>`

      + ((p.functions || []).length ? `<div class="muted">지정 함수: ${escapeHtml(p.functions.join(", "))}</div>` : "");
    ensureAssets(p, p.page);
    sec.appendChild(linesWithAssets(p.instructions, p, p.page));
    const tools = el("div", "qz-foot");
    tools.appendChild(roundChip(p.page, "문제"));
    sec.appendChild(tools);
    c.appendChild(sec);
  }
  const a = it.answer;
  const ans = el("div");
  ans.style.cssText = "border-top:1px solid var(--hairline);padding-top:8px";
  if (!a) {
    ans.appendChild(el("div", "muted", "정답 없음 — 정답 쪽의 종류·회차가 맞는지 쪽 화면에서 확인하세요."));
  } else {
    const h = [`<div class="muted">정답 · ${escapeHtml(a.kinds.join("/"))}</div>`];
    for (const f of a.formulas) h.push(`<div style="margin:3px 0"><code>${escapeHtml((f.cell ? f.cell + " : " : "") + f.formula)}</code></div>`);
    if (a.settings.length) {
      h.push(`<table class="tbl" style="margin:6px 0"><tbody>` + a.settings.map((s) =>
        `<tr><td class="muted">${escapeHtml(s.dialog || "")}</td><td>${escapeHtml(s.field || "")}</td><td><code>${escapeHtml(s.value || "")}</code></td></tr>`).join("")
        + `</tbody></table>`);
    }
    if (a.code) h.push(`<pre class="pb-cmd">${escapeHtml(a.code)}</pre>`);
    if (a.steps.length) {
      h.push(`<details><summary class="muted">풀이 절차</summary><div style="margin:4px 0 0 4px">`
        + a.steps.map((s) => `<p style="margin:4px 0">${escapeHtml(String(s).replace(/\{\{b-\d+\}\}/g, "(그림 — 아래)"))}</p>`).join("") + `</div></details>`);
    }
    ans.innerHTML = h.join("");
    for (const f of a.figures || []) {
      const [bx, by, bw, bh] = f.bbox;
      const img = el("img");
      img.src = `/api/ocr/crop?src=${encodeURIComponent(S.src)}&page=${f.page}&x=${bx}&y=${by}&w=${bw}&h=${bh}`;
      img.style.cssText = "max-width:100%;border:1px solid var(--hairline);border-radius:6px;margin-top:6px";
      ans.appendChild(img);
    }
    const tools = el("div", "qz-foot");
    a.pages.forEach((p) => tools.appendChild(roundChip(p, "정답")));
    ans.appendChild(tools);
  }
  c.appendChild(ans);
  return c;
}
