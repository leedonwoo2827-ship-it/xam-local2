/* 슬라이드 — 굽고, PPTX 로 만들고, 장수를 확정하고, 그림파일로 뽑는다.
 *
 * ★ 왜 이 화면이 생겼는가(2026-08-20). 05/ 를 만드는 입구가 `tools/bake_all.py` 뿐이었다.
 *   앱에는 버튼이 없어서, 새 책은 영상 화면에서 100번들이 `broken` 으로 뜨고
 *   [미완성만 렌더] 는 「렌더할 번들이 없습니다」 로 끝났다 — 사람이 다음에 무엇을
 *   눌러야 하는지 알 방법이 없었다.
 *
 * ★ 무엇이 바뀌었나(2026-08-24). **슬라이드의 진실이 PPTX 로 옮겨 왔다.**
 *   전에는 `deck.html` 을 Chromium 으로 캡처한 것이 영상의 슬라이드였다. 지금은
 *   `vendor/exam2deck` 이 좌표를 재서 pptx 를 그리고, PowerPoint 로 뽑은 PNG 가
 *   영상으로 간다. deck.html 은 **변환기의 입력**과 미리보기로만 남는다.
 *
 *       ① 굽기 → ② PPTX → ③ 장수 확정 → ④ 이미지 → (영상 화면에서 렌더)
 *
 * ★ 바닥의 띠(`sl-dock`)가 **다음에 누를 것 하나**를 말한다. 네 단계를 사람이
 *   외우게 하지 않는다 — 화면이 지금 어디인지 알고 있으므로 화면이 말해야 한다.
 *
 * ★ 미리보기는 여전히 **새 탭**이다. 슬라이드가 1920×1080 고정이라 앱 셸(레일 248px)
 *   안에서는 축소돼 보이고, 그러면 "실제로 넘치는가" 를 눈으로 판단할 수 없다.
 */
"use strict";

import { $, api, el, escapeHtml, toast, confirmModal } from "./util.js";
import { pollJob } from "./store.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const S = {
  list: null,        // /api/render/bundles
  deck: null,        // /api/render/slides/status
  rd: "",            // ③에서 보고 있는 회차
  imgRd: "",         // ④에서 보고 있는 회차 — ③과 따로 논다(③을 안 고치고 ④만 쓰는 일이 잦다)
  table: null,       // /api/render/slides/pages
  dirty: false,      // ③의 표를 고쳤는가
  job: null,
};

export const meta = {
  title: () => "슬라이드",
  subtitle: () => "구워서 PPTX 로 만들고, 장수를 확정해 그림파일로 뽑습니다.",
  actions: () => [
    actionBtn("폴더 열기", () => openTarget({}), { iconName: "folder" }),
    actionBtn("미리보기 (새 탭)", () => window.open("/slide/", "_blank"),
              { iconName: "grid" }),
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
  ],
};

export async function mount(root) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card">
      <div class="card-title">① 굽기 — <code>_rounds</code> · <code>02/</code> → <code>05/</code></div>
      <div id="sl-bake"><div class="empty">불러오는 중…</div></div>
    </div>

    <div class="card">
      <div class="card-title">② 슬라이드(PPTX) 만들기 — <code>04-2/NN회_강의_LO-HI.pptx</code></div>
      <div id="sl-make"><div class="empty">불러오는 중…</div></div>
    </div>

    <div class="card">
      <div class="card-title">③ 장수 확정 — 문항마다 문제 몇 장 · 해설 몇 장</div>
      <div id="sl-pages"><div class="empty">②를 먼저 돌리세요.</div></div>
    </div>

    <div class="card">
      <div class="card-title">④ 그림파일 뽑기 — <code>05/&lt;번들&gt;/images/slide_NN.png</code></div>
      <div id="sl-img"><div class="empty">불러오는 중…</div></div>
    </div>

    <div class="card" id="sl-jobcard" hidden>
      <div class="card-title">진행</div>
      <div id="sl-clock"></div>
      <pre class="job-log" id="sl-log" style="max-height:40vh"></pre>
    </div>

    <div class="card">
      <div class="card-title">눈으로 보기 — 넘침·분할</div>
      <div class="field-hint">
        슬라이드는 1920×1080 고정이라 이 앱 창 안에서는 축소돼 보입니다.
        그래서 <b>새 탭</b>으로 엽니다 — 축소된 화면으로는 넘침을 판단할 수 없습니다.
        <br>PPTX 를 만든 뒤에는 <b>PowerPoint 로 여는 것</b>이 진짜 화면입니다
        (영상은 그 파일에서 그대로 뽑습니다).
      </div>
      <div class="qz-foot">
        <a class="btn" href="/slide/" target="_blank" rel="noopener">deck.html 미리보기</a>
        <a class="btn" href="/slide/?fit=1" target="_blank" rel="noopener">안전선 켜고 보기</a>
      </div>
    </div>

    <div class="sl-dock" id="sl-dock" hidden></div>`;
  root.appendChild(page);
  hydrateIcons(page);
  await load();
}

/* ── 불러오기 ──────────────────────────────────────────────────────────── */
async function load() {
  try {
    [S.list, S.deck] = await Promise.all([
      api("/api/render/bundles"),
      api("/api/render/slides/status"),
    ]);
  } catch (e) {
    const b = $("#sl-bake");
    if (b) { b.innerHTML = ""; b.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message)); }
    return;
  }
  if (!S.rd) {
    // 아직 pptx 가 없는 첫 회차를 기본으로 연다 — 사람이 다음에 볼 자리다.
    const rs = S.deck.rounds || [];
    S.rd = (rs.find((r) => r.pptx && r.pptx < r.bundles.length) || rs.find((r) => r.pptx)
            || rs[0] || {}).round || "";
  }
  await loadTable();
  renderAll();
  for (const kind of ["bake", "slides", "slideimg"]) {
    try {
      const r = await api(`/api/jobs?kind=${kind}&limit=1`);
      const j = (r.jobs || [])[0];
      if (j && ["running", "queued"].includes(j.status)) { attach(j.id, kind); return; }
    } catch { /* 목록을 못 읽어도 버튼은 누를 수 있다 */ }
  }
}

async function loadTable() {
  S.table = null; S.dirty = false;
  if (!S.rd) return;
  try {
    S.table = await api(`/api/render/slides/pages?rd=${encodeURIComponent(S.rd)}`);
  } catch { S.table = null; }
}

function renderAll() { renderBake(); renderMake(); renderPages(); renderImg(); renderDock(); }

/* ── 회차 상태 요약 ────────────────────────────────────────────────────── */
function rounds() { return (S.deck && S.deck.rounds) || []; }

function totals() {
  const rs = rounds();
  const t = { rounds: rs.length, bundles: 0, pptx: 0, images: 0, touched: 0, slides: 0 };
  rs.forEach((r) => {
    t.bundles += r.bundles.length; t.pptx += r.pptx;
    t.images += r.images; t.touched += r.touched; t.slides += r.slides;
  });
  return t;
}

/* ── ① 굽기 ────────────────────────────────────────────────────────────── */
function renderBake() {
  const box = $("#sl-bake");
  if (!box) return;
  box.innerHTML = "";
  const rows = (S.list && S.list.items) || [];
  if (!rows.length) {
    box.appendChild(el("div", "empty",
      "번들이 없습니다 — 회차(_rounds)가 있어야 번들이 잡힙니다."));
    return;
  }
  const n = { broken: 0, missing: 0, stale: 0, done: 0 };
  rows.forEach((b) => { n[b.status] = (n[b.status] || 0) + 1; });

  box.appendChild(chips([
    [`전체 ${rows.length}번들`, ""],
    n.broken ? [`아직 안 구움 ${n.broken}`, "warn"] : null,
    n.missing ? [`구웠고 영상 없음 ${n.missing}`, "info"] : null,
    n.stale ? [`영상이 낡음 ${n.stale}`, "info"] : null,
    n.done ? [`영상까지 완료 ${n.done}`, "ok"] : null,
  ]));
  box.appendChild(hint(
    "굽기는 모델을 부르지 않습니다 — 돈이 들지 않고 번들당 몇 초입니다. "
    + "여기서 나오는 deck.html 이 ②의 입력입니다."));

  const foot = el("div", "qz-foot");
  foot.appendChild(btn(n.broken ? `아직 안 구운 ${n.broken}번들 굽기` : "안 구운 번들 없음",
    () => startBake("unbaked", n.broken), { primary: !!n.broken, disabled: !n.broken || !!S.job }));
  foot.appendChild(btn(`전체 ${rows.length}번들 다시 굽기`,
    () => startBake("all", rows.length), { disabled: !!S.job }));
  box.appendChild(foot);
}

/* ── ② PPTX 만들기 ─────────────────────────────────────────────────────── */
function renderMake() {
  const box = $("#sl-make");
  if (!box) return;
  box.innerHTML = "";
  const rs = rounds();
  if (!rs.length) { box.appendChild(el("div", "empty", "회차가 없습니다.")); return; }
  const t = totals();

  box.appendChild(chips([
    [`회차 ${t.rounds} · 번들 ${t.bundles}`, ""],
    [`PPTX ${t.pptx}/${t.bundles}`, t.pptx === t.bundles ? "ok" : (t.pptx ? "info" : "warn")],
    [`장 ${t.slides}`, ""],
    t.touched ? [`손질됨 ${t.touched}`, "info"] : null,
  ]));
  box.appendChild(hint(
    `글자 배율 <b>${S.deck.scale}</b> — 시험정보(<code>exams/&lt;pd&gt;.json</code> 의 `
    + "<code>deck.pptx_scale</code>)에서 옵니다. 올리면 장 수가 늘고 채움이 오릅니다. "
    + "넘침이 0 인 선에서 고르십시오."));

  const foot = el("div", "qz-foot");
  const sel = el("select", "box sl-sel");
  sel.innerHTML = `<option value="all">전체 ${rs.length}회차</option>`
    + rs.map((r) => `<option value="${r.round}">${escapeHtml(r.round)}`
      + ` — pptx ${r.pptx}/${r.bundles.length}</option>`).join("");
  foot.appendChild(sel);

  const scale = el("input", "box sl-sel");
  scale.type = "number"; scale.step = "0.1"; scale.min = "0.5"; scale.max = "3";
  scale.value = S.deck.scale; scale.style.width = "84px";
  scale.title = "글자 배율. 비워 두면 시험정보 값을 씁니다.";
  foot.appendChild(el("span", "field-hint", "배율"));
  foot.appendChild(scale);

  foot.appendChild(btn("슬라이드 만들기", () => startSlides(sel.value, scale.value),
                       { primary: true, disabled: !!S.job }));
  // ★ 만든 직후 **그 자리에서** 열 수 있어야 한다. pptx 는 번들 폴더 안에 흩어져
  //   있으므로(회차당 5개 폴더) 회차 단위로 한꺼번에 연다.
  const rdOf = () => (sel.value === "all" ? (S.rd || (rs[0] || {}).round) : sel.value);
  foot.appendChild(btn("PowerPoint 로 열기", () => {
    const rd = rdOf();
    if (rd) openTarget({ rd });
  }, { disabled: !t.pptx }));
  foot.appendChild(btn("폴더 열기", () => openTarget({ which: "folder" }),
                       { disabled: !t.pptx }));
  foot.appendChild(el("span", "field-hint qz-foot-hint",
    "회차를 하나로 합쳐 넘기고, 편마다 pptx 를 그린 뒤 씬(대본)을 그 장 나눔에 "
    + "맞춰 다시 매깁니다. 손질해 둔 pptx 는 덮어씁니다."));
  box.appendChild(foot);
}

/* ── ③ 장수 확정 ───────────────────────────────────────────────────────── */
function renderPages() {
  const box = $("#sl-pages");
  if (!box) return;
  box.innerHTML = "";
  const rs = rounds();
  if (!rs.length) { box.appendChild(el("div", "empty", "회차가 없습니다.")); return; }

  const head = el("div", "qz-foot");
  const sel = el("select", "box sl-sel");
  sel.innerHTML = rs.map((r) => `<option value="${r.round}"${r.round === S.rd ? " selected" : ""}>`
    + `${escapeHtml(r.round)}</option>`).join("");
  sel.addEventListener("change", async () => {
    if (S.dirty && !(await confirmModal({
      title: "고친 것을 버릴까요?", body: "저장하지 않은 장수 변경이 있습니다.",
      ok: "버리고 이동", cancel: "취소", danger: true,
    }))) { sel.value = S.rd; return; }
    S.rd = sel.value; await loadTable(); renderPages(); renderDock();
  });
  head.appendChild(sel);
  box.appendChild(head);

  const t = S.table;
  if (!t || !(t.questions || []).length) {
    box.appendChild(el("div", "empty",
      "이 회차는 아직 PPTX 가 없습니다 — ②를 먼저 돌리세요."));
    return;
  }

  // ★ 셋째 줄은 **채움 읽는 법**이다(2026-09-10 요청). 숫자만 보고는 얼마가
  //   좋은 것인지 알 수 없어서, 실측에서 자주 나오는 세 눈금을 적어 둔다.
  const base = Number(S.deck.scale) || 1;
  box.appendChild(hint(
    "기본값은 방금 만든 결과입니다. <b>±</b> 로 고치고 <b>☑</b> 를 찍으면 그 문항은 "
    + "다음에 만들 때도 그 장수를 지킵니다. ☑ 를 안 찍은 줄은 변환기 판단을 다시 따릅니다."
    + `<br>줄이면 그 문항만 글자가 작아집니다 — <b>배율</b> 칸이 이 덱의 `
    + `<b>${base.toFixed(2)}</b> 보다 작아지면 그 뜻입니다(1.00 은 코드 기본 크기이고, `
    + "이 덱은 그보다 크게 씁니다). 못 맞춘 문항은 빨갛게 뜨고 자연 장수로 "
    + "돌아갑니다(잘라 내지 않습니다)."
    + "<br><b>채움</b> 은 그 장을 얼마나 썼는가입니다 — 앞칸이 <b>문제 면</b>, "
    + "뒤칸이 해설 면입니다. 보실 곳은 앞칸입니다. "
    + "<b>0.40</b> 이면 아래가 절반 넘게 비고 · <b>0.70</b> 이면 알맞고 · "
    + "<b>0.95</b> 면 꽉 찬 것입니다(1.00 을 넘으면 넘침)."));

  const wrap = el("div", "tbl-wrap");
  wrap.style.cssText = "max-height:44vh;overflow:auto";
  const tb = el("table", "data sl-tbl");
  tb.innerHTML = `<thead><tr>
      <th>문항</th><th>파일</th><th>문제</th><th>해설</th>
      <th>배율</th><th>채움<span class="dim small"> 문제</span></th>
      <th class="dim">채움<span class="small"> 해설</span></th>
      <th>고정</th><th></th>
    </tr></thead>`;
  const body = el("tbody");
  t.questions.forEach((q) => body.appendChild(pageRow(q)));
  tb.appendChild(body);
  wrap.appendChild(tb);
  box.appendChild(wrap);

  const foot = el("div", "qz-foot");
  // ★ **붉은 버튼은 한 번 누르고 지나가는 것이다**(2026-09-10 지시). 그래서 ③에는
  //   붉은 버튼이 없다 — 여기는 회차를 넘겨 가며 ± 로 장수를 표시하고 저장하기를
  //   15번 되풀이하는 **작업대**다. 파이프라인을 한 칸 밀어 주는 붉은 버튼은
  //   ②「슬라이드 만들기(전체 15회차)」 쪽에 하나 있으면 된다.
  //
  //   ★ 저장만 해도 **글자가 줄어드는 것은 그대로다.** 조이기는 pptx 를 만들 때
  //     일어나므로, 나중에 전체를 만들 때 똑같이 일어난다. 저장은 그 시점을
  //     미룰 뿐이지 면제해 주지 않는다.
  foot.appendChild(btn("이 장수로 저장", () => savePages(), { disabled: !!S.job }));
  foot.appendChild(btn("저장하고 다시 만들기", () => savePages(true),
                       { disabled: !!S.job }));
  // ★ 종이로 대조하는 자리 — PowerPoint 를 넘겨 보며 「확인」 칸에 체크한다.
  //   회차 하나가 한 쪽이라 20회차면 20쪽이다(2026-08-25 요청).
  foot.appendChild(btn("이 회차 인쇄",
    () => window.open(`/print/slides?rd=${encodeURIComponent(S.rd)}`, "_blank")));
  foot.appendChild(btn("전 회차 인쇄 (회차당 한 쪽)",
    () => window.open("/print/slides", "_blank")));
  const locked = t.questions.filter((q) => q.lock).length;
  foot.appendChild(el("span", "field-hint qz-foot-hint",
    `고정 ${locked}문항 · 이 회차 ${t.slides}장`
    + (t.missed && t.missed.length ? ` · 못 맞춘 지정 ${t.missed.length}건` : "")));
  box.appendChild(foot);
}

function pageRow(q) {
  const tr = el("tr");
  if (q.missed && q.missed.length) tr.classList.add("bad");
  tr.appendChild(el("td", null, `${q.no}번`));
  // ★ 번들 코드(`m01-2`) 가 아니라 **열 파일 이름**을 적는다 — PowerPoint 창에
  //   보이는 것이 그 이름이다(2026-09-10 지시, 종이표는 2026-08-25 에 같은 이유로).
  tr.appendChild(el("td", "dim small", q.file || q.bundle));
  tr.appendChild(stepCell(q, "problem"));
  tr.appendChild(stepCell(q, "answer"));

  // ★ 기준은 **이 덱의 배율**이다(시험정보 `deck.pptx_scale`, 지금 1.6). 전에는
  //   1.0 과 견주었는데 그러면 1.60 → 1.20 으로 조인 문항이 경고 없이 지나간다 —
  //   1.00 은 코드 기본 크기일 뿐 이 덱이 노리는 크기가 아니다(2026-09-10).
  const base = Number(S.deck.scale) || Number((S.table || {}).scale) || 1;
  const sc = el("td", null, Number(q.scale).toFixed(2));
  if (Number(q.scale) < base - 0.001) sc.classList.add("warn");
  tr.appendChild(sc);
  // ★ 채움 두 칸 — 앞이 **문제 면**, 뒤가 해설 면. 사람이 보는 것은 앞칸이다.
  //   해설은 낭독을 따라 넘어가므로 비어도 상관이 적다(2026-09-10 지시).
  //
  // ★ **한 장 줄일 수 있는 문항**을 앞칸에 붉게 표시한다. `채움 × 장수` 가 그
  //   문항의 내용 총량이므로, 그것이 `장수 − 1` 이하면 한 장이 통째로 남는다.
  //     2장 → 채움 0.50 미만 · 3장 → 0.67 미만
  //   1장짜리는 줄일 수 없으므로 아무리 비어도 표시하지 않는다(22번이 채움 0.38
  //   인데 1장인 경우 — 사용자 지적, 2026-09-10).
  //
  //   실측 분포: 문제 면이 2장인 207문항의 채움 중앙값이 0.58 이고 0.50 미만이
  //   19문항, 3장짜리는 9문항 전부가 걸린다 → 750문항 중 28개. 눈으로 볼 만한 수다.
  const np = Number(q.problem) || 0;
  const fp = Number(q.fill || 0);
  const fpTd = el("td", null, fp.toFixed(2));
  if (np > 1 && fp * np <= np - 1) {
    fpTd.classList.add("slack");
    // ★ 단정하지 않는다 — 조각이 통째로만 옮겨지므로 총량이 맞아도 실제로는
    //   안 줄 수 있다(2026-09-10 지적: "뒤에가 비어도 한 장으로 줄일 수는
    //   아닐 수도 있음"). 여기는 **볼 자리**를 가리키는 표시지 판정이 아니다.
    fpTd.title = `${np}장인데 내용은 ${(fp * np).toFixed(2)}장 분량입니다 — `
      + `한 장에 들어갈지 눈으로 보십시오.`;
  }
  tr.appendChild(fpTd);
  tr.appendChild(el("td", "dim", Number(q.fill_a || 0).toFixed(2)));

  const lockTd = el("td");
  const cb = el("input");
  cb.type = "checkbox"; cb.checked = !!q.lock;
  cb.addEventListener("change", () => { q.lock = cb.checked; S.dirty = true; renderDock(); });
  lockTd.appendChild(cb);
  tr.appendChild(lockTd);

  tr.appendChild(el("td", "dim small",
    (q.missed || []).map((k) => (k === "problem" ? "문제" : "해설") + " 지정 실패").join(" · ")));
  return tr;
}

function stepCell(q, key) {
  const td = el("td", "sl-step");
  const minus = btn("−", () => bump(q, key, -1, out), { small: true });
  const out = el("b", null, String(q[key]));
  const plus = btn("+", () => bump(q, key, +1, out), { small: true });
  td.appendChild(minus); td.appendChild(out); td.appendChild(plus);
  return td;
}

function bump(q, key, d, out) {
  const v = Math.max(1, Math.min(9, (q[key] || 1) + d));
  if (v === q[key]) return;
  q[key] = v; q.lock = true;              // 손으로 고쳤으면 고정한 것이다
  out.textContent = String(v);
  const cb = out.closest("tr").querySelector('input[type="checkbox"]');
  if (cb) cb.checked = true;
  S.dirty = true;
  renderDock();
}

async function savePages(thenBuild) {
  const t = S.table;
  if (!t) return;
  try {
    const r = await api(`/api/render/slides/pages?rd=${encodeURIComponent(S.rd)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ questions: t.questions }),
    });
    S.dirty = false;
    toast(`${r.locked}문항 고정으로 저장했습니다.`, "ok");
  } catch (e) {
    toast("저장하지 못했습니다: " + e.message, "err");
    return;
  }
  if (thenBuild) await startSlides(S.rd, "");
  else renderDock();
}

/* ── ④ 이미지 ──────────────────────────────────────────────────────────── */
function renderImg() {
  const box = $("#sl-img");
  if (!box) return;
  box.innerHTML = "";
  const t = totals();
  const pp = (S.deck && S.deck.powerpoint) || {};

  box.appendChild(chips([
    [`이미지 ${t.images}/${t.bundles}번들`,
      t.images === t.bundles && t.bundles ? "ok" : (t.images ? "info" : "warn")],
    pp.ok ? [`PowerPoint ${pp.version}`, "ok"] : ["PowerPoint 없음", "warn"],
    t.touched ? [`손질됨 ${t.touched}`, "info"] : null,
  ]));

  if (!pp.ok) {
    box.appendChild(hint(
      escapeHtml(pp.why || "PowerPoint 를 쓸 수 없습니다.")
      + " — 이 단계는 <b>캡처로 대신하지 않습니다.</b> 확정한 화면과 다른 영상이 "
      + "나가기 때문입니다.", "qz-warn warn"));
  }
  box.appendChild(hint(
    "PowerPoint 로 <b>지금 그 파일</b>을 열어 장마다 1920×1080 PNG 로 뽑습니다. "
    + "손으로 고쳐 두셨으면 고친 그대로 나갑니다. 영상 렌더는 이 PNG 를 그대로 씁니다"
    + "(<code>--reuse-images</code>) — 캡처를 다시 하지 않습니다."));

  const foot = el("div", "qz-foot");
  const sel = el("select", "box sl-sel");
  sel.innerHTML = `<option value="all">전체 ${totals().bundles}번들</option>`
    + rounds().map((r) => `<option value="${r.round}">${escapeHtml(r.round)}`
      + ` — 이미지 ${r.images}/${r.bundles.length}</option>`).join("");
  // ★ ④는 ③과 **따로** 회차를 기억한다. ③을 손대지 않고 ④만 회차를 넘겨 가며
  //   뽑는 일이 잦은데, 밑의 표가 ③의 회차를 비추면 콤보와 표가 어긋나 보인다.
  if (!S.imgRd) S.imgRd = S.rd;
  if (S.imgRd !== "all" && !rounds().some((r) => r.round === S.imgRd)) S.imgRd = S.rd;
  sel.value = S.imgRd || "all";
  sel.addEventListener("change", () => { S.imgRd = sel.value; renderImg(); });
  foot.appendChild(sel);
  // ★ **고른 대상의 pptx 가 다 있어야 뽑는다.** 전에는 `!t.pptx` 만 봤다 — 책
  //   전체에 pptx 가 하나라도 있으면 눌렸다는 뜻이다. 그래서 5/75 인 상태에서
  //   「전체 75번들」 로 뽑으면 없는 pptx 를 열러 가서 70번들이 조용히 빈다.
  //   회차를 골랐으면 그 회차만 본다(그 회차는 다 만들어져 있으면 되고, 다른
  //   회차를 아직 안 만들었다고 막을 이유가 없다).
  const imgReady = S.imgRd === "all"
    ? (t.pptx >= t.bundles && t.bundles > 0)
    : (() => { const r = rounds().find((x) => x.round === S.imgRd);
               return !!r && r.pptx >= r.bundles.length; })();
  const imgWhy = !pp.ok ? "PowerPoint 를 찾지 못했습니다."
    : !imgReady ? (S.imgRd === "all"
        ? `pptx 가 ${t.pptx}/${t.bundles} 번들입니다 — ②를 먼저 끝내십시오.`
        : `${S.imgRd} 의 pptx 가 아직 다 없습니다 — ②를 먼저 돌리십시오.`)
    : "";
  const imgBtn = btn("그림파일 뽑기", () => startImg(S.imgRd),
                     { primary: true, disabled: !!S.job || !pp.ok || !imgReady });
  if (imgWhy) imgBtn.title = imgWhy;
  foot.appendChild(imgBtn);
  if (imgWhy) foot.appendChild(el("span", "field-hint", imgWhy));
  // ★ pptx 는 번들 폴더 안에 있다 — 한 회차가 5편이면 5개 폴더다. 하나씩 찾아
  //   들어가지 않게 회차 단위로 한꺼번에 연다(PowerPoint 가 창을 편마다 띄운다).
  foot.appendChild(btn("이 회차 PowerPoint 로 다 열기", () => {
    const rd = S.imgRd === "all" ? S.rd : S.imgRd;
    if (rd) openTarget({ rd });
  }, { disabled: !t.pptx }));
  box.appendChild(foot);
  box.appendChild(hint(
    "pptx 는 <b><code>04-2/</code> 한 폴더에</b> 다 모여 있습니다 — "
    + "<code>01회_강의_11-20.pptx</code> 처럼 이름이 좌표를 말합니다. "
    + "사본이 아니라 <b>원래 자리</b>입니다: 손질하신 그 파일에서 그림파일을 뽑습니다."));

  const shown = S.imgRd === "all"
    ? rounds().flatMap((r) => r.bundles)
    : ((rounds().find((r) => r.round === S.imgRd) || {}).bundles || null);
  if (!shown || !shown.length) return;
  const wrap = el("div", "tbl-wrap");
  wrap.style.cssText = "max-height:30vh;overflow:auto";
  const tb = el("table", "data");
  tb.innerHTML = `<thead><tr><th>번들</th><th>PPTX</th><th>장</th><th>채움</th>
      <th>손질</th><th>이미지</th><th></th></tr></thead>`;
  const body = el("tbody");
  shown.forEach((b) => {
    const tr = el("tr");
    tr.appendChild(el("td", null, b.bundle));
    tr.appendChild(el("td", b.pptx ? "ok" : "dim", b.pptx ? `${b.pptx_kb}KB` : "없음"));
    tr.appendChild(el("td", null, String(b.slides || "")));
    tr.appendChild(el("td", "dim", b.fill_median ? Number(b.fill_median).toFixed(2) : ""));
    tr.appendChild(el("td", b.slides_changed ? "bad" : (b.touched ? "warn" : "dim"),
      b.slides_changed ? "장수 바뀜" : (b.touched ? "손질됨" : "")));
    tr.appendChild(el("td", b.images ? (b.images_stale ? "warn" : "ok") : "dim",
      b.images ? (b.images_stale ? `낡음 ${b.images_count}` : `${b.images_count}장`) : "없음"));
    const act = el("td");
    act.appendChild(btn("PowerPoint", () => openTarget({ bundle: b.bundle, which: "pptx" }),
                        { small: true, disabled: !b.pptx }));
    act.appendChild(btn("이미지 폴더", () => openTarget({ bundle: b.bundle, which: "images" }),
                        { small: true, disabled: !b.images }));
    tr.appendChild(act);
    body.appendChild(tr);
  });
  tb.appendChild(body);
  wrap.appendChild(tb);
  box.appendChild(wrap);
}

/* ── 바닥 띠 — 다음에 누를 것 하나 ─────────────────────────────────────── */
function renderDock() {
  const dock = $("#sl-dock");
  if (!dock) return;
  const t = totals();
  const rows = (S.list && S.list.items) || [];
  const unbaked = rows.filter((b) => b.status === "broken").length;
  const pp = (S.deck && S.deck.powerpoint) || {};

  let step, why, act = null;
  if (S.job) {
    step = "돌고 있습니다"; why = "끝나면 다음 단계를 알려 드립니다.";
  } else if (S.dirty) {
    step = "③ 고친 장수를 저장하세요";
    why = "저장해야 다시 만들 때 그 장수를 지킵니다.";
    act = ["저장하고 다시 만들기", () => savePages(true)];
  } else if (unbaked) {
    step = `① 아직 안 구운 ${unbaked}번들이 있습니다`;
    why = "구워야 ②의 입력(deck.html)이 생깁니다.";
    act = [`${unbaked}번들 굽기`, () => startBake("unbaked", unbaked)];
  } else if (t.pptx < t.bundles) {
    step = `② PPTX 가 ${t.pptx}/${t.bundles} 번들입니다`;
    why = "회차마다 pptx 를 만들고 씬을 그 장 나눔에 맞춰 다시 매깁니다.";
    act = ["전체 슬라이드 만들기", () => startSlides("all", "")];
  } else if (t.images < t.bundles) {
    step = `④ 그림파일이 ${t.images}/${t.bundles} 번들입니다`;
    why = pp.ok ? "PowerPoint 로 열어 장마다 PNG 로 뽑습니다."
                : (pp.why || "PowerPoint 가 있어야 합니다.");
    if (pp.ok) act = ["전체 그림파일 뽑기", () => startImg("all")];
  } else {
    step = "슬라이드가 다 준비됐습니다";
    why = "이제 「영상 제작·검수」에서 렌더를 걸면 이 그림파일을 그대로 씁니다.";
    act = ["영상 화면으로", () => { location.hash = "#/video"; }];
  }

  dock.hidden = false;
  dock.innerHTML = "";
  const txt = el("div", "sl-dock-txt");
  txt.appendChild(el("b", null, step));
  txt.appendChild(el("span", "field-hint", why));
  dock.appendChild(txt);
  if (act) dock.appendChild(btn(act[0], act[1], { primary: true, disabled: !!S.job }));
}

/* ── 잡 ────────────────────────────────────────────────────────────────── */
async function startBake(codes, n) {
  const ok = await confirmModal({
    title: "슬라이드를 구울까요?",
    body: `<b>${n}개 번들</b><br><br>`
      + "<code>05/</code> 에 deck.html · 대본 · lesson 을 만듭니다. "
      + "<b>PPTX 와 영상은 만들지 않습니다</b> — 그건 ②와 「영상 제작·검수」입니다.<br>"
      + "모델을 부르지 않아 <b>돈이 들지 않습니다</b>.",
    ok: "굽기 시작", cancel: "취소",
  });
  if (!ok) return;
  await post("/api/render/bake", { codes }, "bake");
}

async function startSlides(rounds_, scale) {
  const t = totals();
  const body = (rounds_ === "all" ? `전체 ${t.rounds}회차` : `${rounds_} 회차`)
    + "<br><br>편마다 <code>04-2/</code> 의 pptx 와 <code>pages.json</code> 을 만들고, "
    + "<b>대본의 씬을 그 장 나눔에 맞춰 다시 매깁니다.</b>"
    + (t.touched ? `<br><br><b class="warn">PowerPoint 에서 손질한 번들 ${t.touched}개가 `
                   + "있습니다 — 그 손질은 사라집니다.</b>" : "");
  const ok = await confirmModal({ title: "PPTX 를 만들까요?", body,
                                  ok: "만들기", cancel: "취소", danger: !!t.touched });
  if (!ok) return;
  const payload = { rounds: rounds_ === "all" ? "all" : [rounds_] };
  const s = parseFloat(scale);
  if (!Number.isNaN(s) && s > 0) payload.scale = s;
  await post("/api/render/slides", payload, "slides");
}

async function startImg(codes) {
  await post("/api/render/slideimg", { codes }, "slideimg");
}

async function post(url, payload, kind) {
  let r;
  try {
    r = await api(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (e) { toast("시작하지 못했습니다: " + e.message, "err"); return; }
  attach(r.id, kind);
}

async function openTarget(payload) {
  try {
    const r = await api("/api/render/slides/open", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload) });
    if (r && r.count) toast(`${r.count}편을 PowerPoint 로 열었습니다.`, "ok");
  } catch (e) { toast("열지 못했습니다: " + e.message, "err"); }
}

function logLine(t) {
  const card = $("#sl-jobcard");
  if (card) card.hidden = false;
  const pre = $("#sl-log");
  if (!pre) return;
  pre.appendChild(el("span", null, t + "\n"));
  pre.scrollTop = pre.scrollHeight;
}

async function attach(jobId, kind) {
  S.job = jobId;
  renderAll();
  const card = $("#sl-jobcard");
  if (card) card.hidden = false;
  const t0 = Date.now();
  const clock = $("#sl-clock");
  const tick = setInterval(() => {
    if (!clock) return;
    const v = Math.floor((Date.now() - t0) / 1000);
    clock.innerHTML = `<span class="dim small">경과</span>
      <b style="font-size:20px;font-variant-numeric:tabular-nums">${
        Math.floor(v / 60)}:${String(v % 60).padStart(2, "0")}</b>`;
  }, 1000);

  const fin = await pollJob(jobId, (j) => {
    (j.log?.lines || []).forEach((l) => logLine(l.trimEnd()));
    if (clock && j.total_count) {
      clock.insertAdjacentHTML("beforeend",
        ` <span class="dim small" style="margin-left:14px">진행</span>
          <b style="font-size:20px">${j.done_count || 0}/${j.total_count}</b>`);
    }
  });
  clearInterval(tick);
  S.job = null;
  const r = (fin && fin.result) || {};
  const unit = kind === "slides" ? "회차" : "번들";
  toast(r.error ? `${r.ok}${unit} 됐고 ${r.error}${unit} 실패 — 로그를 보십시오.`
                : `${r.ok || 0}${unit} 끝났습니다.`,
        r.error ? "err" : "ok");
  await load();
}

/* ── 작은 것들 ─────────────────────────────────────────────────────────── */
/** 힌트 한 줄. `el()` 은 textContent 라 `<b>`·`<code>` 가 글자로 보인다. */
function hint(htmlStr, cls) {
  const d = el("div", cls || "field-hint");
  d.innerHTML = htmlStr;
  return d;
}

function chips(items) {
  const row = el("div", "row");
  row.style.cssText = "gap:8px;flex-wrap:wrap;margin-bottom:10px";
  items.filter(Boolean).forEach(([t, cls]) =>
    row.appendChild(el("span", "status-chip " + (cls || ""), t)));
  return row;
}

function btn(label, fn, { primary, small, disabled } = {}) {
  const b = el("button", "btn" + (primary ? " primary" : "") + (small ? " sm" : ""), label);
  b.type = "button";
  b.disabled = !!disabled;
  b.addEventListener("click", fn);
  return b;
}
