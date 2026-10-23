/* 요약반 · 종합반 강의 노트 (v2) — #/lecture/:kind[/:key]
 *
 *   왼쪽  단계표   ①자막 ②낭독 ③SVG(요약반) / ④n배 ②낭독 ③SVG(종합반) → 노트 빌드 → 듣기 검수
 *                  '사람' 배지 = 승인해야 다음 단계가 열린다
 *   가운데 장 목록 — 누르면 그 자리에서 자막·낭독·도식을 고치고 ▶ 로 듣는다
 *   위     [원고 HTML] [듣기 검수 화면] [노트 빌드]
 *
 * ★ 도식(SVG)은 <img src="data:image/svg+xml"> 로만 그린다. 모델이 만든 SVG 를 innerHTML 로
 *   넣으면 그 안의 스크립트·이벤트 속성이 앱 권한으로 돈다. 이미지로 넣으면 실행되지 않는다.
 * ★ 우측 채팅도 같은 API 를 부른다 — "1과목 ③ 실행해 줘" 와 [이 단계 실행] 은 같은 일이다.
 */
"use strict";

import { $, api, el, escapeHtml, toast, confirmModal } from "./util.js";
import { pollJob } from "./store.js";
import { actionBtn } from "./panel.js";

const KIND_LABEL = { summary: "요약반 강의 노트", full: "종합반 강의 노트" };
// ★ 세 노트의 역할 — 사용자 지시 원문(2026-10-24)을 그대로 화면에 둔다.
//   이론 요약 노트 = 텍스트 위주 / 요약반 = 슬라이드마다 표·SVG 의무(이미지화 영상) /
//   종합반 = 슬라이드 양을 증폭(종합반 영상덱의 롱폼 · 이후 미노출 종합본 HTML · 초단기서 핵심요약 HTML)
const KIND_SUB = {
  summary: "슬라이드마다 표와 SVG 가 의무로 들어가, 추후 이미지화 영상을 만드는 데 기여합니다. "
    + "이론 요약 노트를 장마다 자막·낭독·도식이 붙은 1배 원고로 만듭니다.",
  full: "슬라이드의 양을 증폭시켜, 추후 종합반 영상덱에서 기존에 생산된 모든 산물과 함께 다량의 롱폼을 만드는 데 기여합니다. "
    + "(이후 미노출 종합본 HTML, 문제편을 제외한 초단기서 핵심요약 HTML 까지 만듭니다.)",
};

const S = { kind: "summary", key: "", data: null, open: "", root: null, ctx: null };

export const meta = {
  title: (ctx) => KIND_LABEL[ctx.args[0]] || "강의 노트",
  subtitle: (ctx) => KIND_SUB[ctx.args[0]] || "",
  actions: (ctx) => [
    actionBtn("원고 HTML", () => S.key && window.open(`/api/lecture/${S.kind}/${S.key}/html`, "_blank"),
              { iconName: "external" }),
    actionBtn("듣기 검수 화면", () => S.key && window.open(`#/listen/${S.kind}/${S.key}`, "_blank"),
              { iconName: "play" }),
    actionBtn("노트 빌드", () => runStage("build"), { primary: true, iconName: "package" }),
  ],
};

export async function mount(root, ctx) {
  S.root = root; S.ctx = ctx;
  S.kind = ctx.args[0] === "full" ? "full" : "summary";
  const page = el("div", "page lc-page");
  root.appendChild(page);
  const list = await api(`/api/lecture/${S.kind}`);
  S.key = ctx.args[1] || (list.items.find((i) => i.exists) || list.items[0] || {}).key || "";
  const tabs = el("div", "lc-tabs");
  list.items.forEach((it) => {
    const a = el("a", "lc-tab" + (it.key === S.key ? " on" : ""));
    a.href = `#/lecture/${S.kind}/${it.key}`;
    a.innerHTML = `${it.no}과목 · ${escapeHtml(it.name)} <b>${it.exists ? (it.slides || 0) + "장" : "없음"}</b>`;
    tabs.appendChild(a);
  });
  page.appendChild(tabs);
  page.appendChild(el("div", "lc-body", ""));
  await reload();
}

async function reload() {
  const body = S.root.querySelector(".lc-body");
  if (!S.key) { body.innerHTML = `<div class="empty">이 책에 과목이 없습니다 — 과정 정의를 확인하세요.</div>`; return; }
  S.data = await api(`/api/lecture/${S.kind}/${S.key}`);
  body.innerHTML = "";
  if (!S.data.exists) return body.appendChild(emptyState());
  const grid = el("div", "lc-grid");
  grid.appendChild(stepper());
  const main = el("div", "lc-main");
  main.appendChild(stageBar());
  main.appendChild(el("div", "lc-log", ""));
  main.appendChild(slideList());
  grid.appendChild(main);
  body.appendChild(grid);
}

/* ── 노트가 아직 없을 때 ── */
function emptyState() {
  const box = el("div", "card lc-empty");
  const subj = S.data.subject || {};
  if (S.kind === "summary") {
    box.innerHTML = `<h3>${subj.no}과목 요약반 노트가 아직 없습니다</h3>
      <p class="muted">${S.data.summary_ready
        ? "이론 요약 노트를 장(h3) 단위로 잘라 노트 뼈대를 만듭니다. 모델을 부르지 않습니다."
        : "먼저 [이론 요약 노트] 를 만들어야 합니다 — 이 노트는 그 요약노트에서 시작합니다."}</p>`;
    const b = el("button", "btn primary", "노트 만들기");
    b.disabled = !S.data.summary_ready;
    b.addEventListener("click", () => init({}));
    box.appendChild(b);
  } else {
    box.innerHTML = `<h3>${subj.no}과목 종합반 노트가 아직 없습니다</h3>
      <p class="muted">승인된 요약반 노트(자막·낭독·SVG)를 복사해 시작합니다. 배수만큼 장을 늘리는 것은 다음의 「내용 n배 확장」 단계입니다.</p>`;
    const row = el("div", "row");
    const sel = el("select", "lc-factor");
    [2, 3, 4, 5].forEach((n) => { const o = el("option", null, `${n}배`); o.value = n; if (n === 3) o.selected = true; sel.appendChild(o); });
    const b = el("button", "btn primary", "노트 만들기");
    b.addEventListener("click", () => init({ factor: Number(sel.value) }));
    row.append(sel, b);
    box.appendChild(row);
  }
  return box;
}

async function init(body) {
  try {
    await api(`/api/lecture/${S.kind}/${S.key}/init`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    toast("노트를 만들었습니다.");
    location.reload();
  } catch (e) { toast(e.message, "err"); }
}

/* ── 단계표 ── */
function stepper() {
  const box = el("div", "lc-steps");
  S.data.stages.forEach((st, i) => {
    const row = el("button", `lc-st st-${st.status}` + (st.open ? "" : " locked") + (st.stage === S.stageSel ? " sel" : ""));
    row.type = "button";
    const done = st.status === "approved" || (st.stage === "build" && st.status === "done");
    row.innerHTML = `<span class="n">${done ? "✓" : i + 1}</span><span class="t">${escapeHtml(st.label)}</span>`
      + (st.human ? `<span class="tag">사람</span>` : "");
    row.title = statusText(st);
    row.addEventListener("click", () => { S.stageSel = st.stage; reload(); });
    box.appendChild(row);
  });
  const ls = S.data.listen || {};
  box.appendChild(el("div", "lc-steps-foot",
    `사람 = 승인해야 다음 단계가 열립니다 · 듣기 ${ls.done || 0}/${ls.total || 0}장 (${ls.need || 2}명씩)`));
  return box;
}

function statusText(st) {
  return { todo: "아직 안 함", running: "도는 중", done: "실행됨 — 확인 후 승인", approved: "승인됨", error: "오류" }[st.status] || st.status;
}

function currentStage() {
  const sts = S.data.stages;
  return sts.find((s) => s.stage === S.stageSel)
    || sts.find((s) => s.open && s.status !== "approved" && !(s.stage === "build" && s.status === "done"))
    || sts[sts.length - 1];
}

/* ── 지금 단계의 버튼 줄 ── */
function stageBar() {
  const st = currentStage();
  S.stageSel = st.stage;
  const bar = el("div", "lc-bar");
  bar.appendChild(el("b", "lc-bar-t", st.label));
  bar.appendChild(el("span", `lc-chip s-${st.status}`, statusText(st)));
  if (st.cost_usd) bar.appendChild(el("span", "muted", `$${Number(st.cost_usd).toFixed(2)}`));
  const acts = el("div", "lc-bar-acts");
  if (!st.open) {
    acts.appendChild(el("span", "muted", "앞 단계를 승인하면 열립니다"));
  } else if (st.stage === "listen") {
    acts.appendChild(btn("미리듣기 미리 굽기", () => bake()));
    acts.appendChild(btn("듣기 검수 화면 열기", () => window.open(`#/listen/${S.kind}/${S.key}`, "_blank")));
    acts.appendChild(btn("듣기 검수 승인", () => approve("listen"), true));
  } else if (st.stage === "build") {
    acts.appendChild(btn("노트 빌드", () => runStage("build"), true));
    if (st.status === "done") acts.appendChild(btn("빌드 폴더 열기", () => openDeck()));
  } else {
    acts.appendChild(btn(st.status === "todo" ? "이 단계 실행 (Claude)" : "남은 장 실행", () => runStage(st.stage), st.status === "todo"));
    if (st.status !== "todo") acts.appendChild(btn("전부 다시", () => runStage(st.stage, true)));
    if (st.human && st.status !== "todo") acts.appendChild(btn(st.status === "approved" ? "승인 취소" : "승인 → 다음 단계",
      () => approve(st.stage, st.status !== "approved"), st.status === "done"));
  }
  bar.appendChild(acts);
  return bar;
}

function btn(label, fn, primary = false) {
  const b = el("button", "btn sm" + (primary ? " primary" : ""), label);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
}

async function runStage(stage, redo = false) {
  if (!S.key) return;
  if (redo && !(await confirmModal({ title: "전부 다시", body: "이미 채운 장도 다시 씁니다. 지금 것은 .bak 로 남습니다.", ok: "다시 쓰기" }))) return;
  try {
    const job = await api(`/api/lecture/${S.kind}/${S.key}/stage`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stage, redo }),
    });
    watch(job.id);
  } catch (e) { toast(e.message, "err"); }
}

async function bake() {
  try {
    const job = await api(`/api/lecture/${S.kind}/${S.key}/tts`, { method: "POST" });
    watch(job.id);
  } catch (e) { toast(e.message, "err"); }
}

async function watch(id) {
  const box = S.root.querySelector(".lc-log");
  box.classList.add("on");
  box.textContent = "시작합니다…";
  const lines = [];
  const fin = await pollJob(id, (job) => {
    (job.log && job.log.lines || []).forEach((l) => lines.push(typeof l === "string" ? l : (l.line || l.text || "")));
    box.textContent = lines.slice(-8).join("\n") || job.label;
  });
  if (fin && fin.status === "done") toast("끝났습니다.");
  else if (fin) toast(fin.error || "실패했습니다", "err");
  reload();
}

async function approve(stage, on = true) {
  try {
    await api(`/api/lecture/${S.kind}/${S.key}/approve`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stage, on }),
    });
    toast(on ? "승인했습니다 — 다음 단계가 열렸습니다." : "승인을 취소했습니다.");
    S.stageSel = "";
    reload();
  } catch (e) { toast(e.message, "err"); }
}

async function openDeck() {
  try { await api(`/api/lecture/${S.kind}/${S.key}/open`, { method: "POST" }); } catch (e) { toast(e.message, "err"); }
}

/* ── 장 목록 ── */
function slideList() {
  const wrap = el("div", "lc-list");
  const ls = {};
  ((S.data.listen || {}).slides || []).forEach((r) => { ls[r.id] = r; });
  const need = (S.data.listen || {}).need || 2;
  S.data.doc.sections.forEach((sec, si) => {
    wrap.appendChild(el("div", "lc-sec", `${si + 1}. ${sec.title}`));
    sec.slides.forEach((sl) => {
      const row = el("div", "lc-row" + (sl.base && sl.base !== sl.id ? " grown" : "") + (S.open === sl.id ? " open" : ""));
      const head = el("button", "lc-row-h");
      head.type = "button";
      const l = ls[sl.id] || {};
      const vis = /<svg|<table|<img/.test((sl.body || "") + (sl.fig || ""));
      head.innerHTML = `<span class="lc-id">${escapeHtml(sl.id)}</span>`
        + `<span class="lc-title">${escapeHtml(sl.title)}</span>`
        + pill(sl.say, "자막") + pill(sl.read_done || sl.read, "낭독") + pill(vis, "도식")
        + `<span class="lc-ok ${l.done ? "done" : ""}" title="듣기 OK">${(l.ok || []).length}/${need}${(l.fixes || []).length ? ` · 지적 ${(l.fixes || []).length}` : ""}</span>`;
      head.addEventListener("click", () => { S.open = S.open === sl.id ? "" : sl.id; reload(); });
      row.appendChild(head);
      if (S.open === sl.id) row.appendChild(editor(sl, l));
      wrap.appendChild(row);
    });
  });
  return wrap;
}

function pill(on, label) {
  return `<span class="lc-pill ${on ? "on" : ""}">${label}</span>`;
}

function svgImg(svg) {
  const img = el("img", "lc-fig");
  img.alt = "도식";
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  return img;
}

function editor(sl, l) {
  const box = el("div", "lc-ed");
  const cols = el("div", "lc-ed-cols");
  const say = field("자막 (data-say) — 화면 자막이자 대본", sl.say);
  const read = field("낭독 (data-read) — 소리 나는 대로 · 비우면 자막을 그대로 읽습니다", sl.read);
  cols.append(say.wrap, read.wrap);
  box.appendChild(cols);

  const body = el("div", "lc-ed-body");
  const tmp = el("div", "lc-bodyhtml");
  tmp.innerHTML = (sl.body || "").replace(/<svg\b[\s\S]*?<\/svg>/g, "");   // 몸통 글·표 (그림은 아래 이미지로)
  tmp.querySelectorAll("script,iframe,object").forEach((n) => n.remove());
  body.appendChild(tmp);
  const svgs = ((sl.body || "").match(/<svg\b[\s\S]*?<\/svg>/g) || []).concat(sl.fig ? [sl.fig] : []);
  svgs.forEach((s) => body.appendChild(svgImg(s)));
  if (!svgs.length && !/<table/.test(sl.body || "")) body.appendChild(el("div", "muted", "이 장에는 아직 표·그림이 없습니다 — ③ SVG 단계가 붙입니다."));
  box.appendChild(body);

  const acts = el("div", "lc-ed-acts");
  const audio = el("audio");
  audio.controls = true;
  audio.preload = "none";
  const play = btn("▶ 미리듣기", () => {
    audio.src = `/api/lecture/${S.kind}/${S.key}/audio/${encodeURIComponent(sl.id)}?t=${Date.now()}`;
    play.textContent = "굽는 중…(처음엔 20초 안팎)";
    audio.play().catch(() => {});
  });
  audio.addEventListener("playing", () => { play.textContent = "▶ 미리듣기"; });
  audio.addEventListener("error", () => { play.textContent = "▶ 미리듣기"; toast("소리를 만들지 못했습니다", "err"); });
  const save = btn("저장", async () => {
    try {
      const r = await api(`/api/lecture/${S.kind}/${S.key}/slide/${encodeURIComponent(sl.id)}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ say: say.ta.value, read: read.ta.value }),
      });
      toast(r.touched.length ? `저장했습니다 (${r.touched.join(", ")})` : "바뀐 것이 없습니다.");
      reload();
    } catch (e) { toast(e.message, "err"); }
  }, true);
  acts.append(play, audio, save);
  if ((l.fixes || []).length) acts.appendChild(el("span", "lc-fixnote", `듣기 지적 ${(l.fixes || []).length}건 — 듣기 검수 화면에서 처리`));
  box.appendChild(acts);
  return box;
}

function field(label, value) {
  const wrap = el("label", "lc-field");
  wrap.appendChild(el("span", "lbl", label));
  const ta = el("textarea");
  ta.value = value || "";
  ta.rows = 7;
  wrap.appendChild(ta);
  return { wrap, ta };
}
