/* 화면 ② 영상 제작·검수 — 목록은 위, 실행은 바닥
 *
 * UX 규칙: 위에 번들 목록이 떠 있고, 행을 누르면 바닥이 그 번들의 실행 판으로 열린다.
 *   바닥 = 슬라이드 + 씬 목록 + 씬별 자막·낭독 + 음성 재생.
 *
 * ★ 렌더는 동시에 하나만. chodangi 의 munje/chNN 스크래치가 exist_ok=True 라서 같은
 *   cid 두 프로세스가 서로를 덮어쓰고, Chromium·TTS·ffmpeg 가 자원을 다 쓴다.
 * ★ 자막 시각: review.json 의 timebase 로 가른다. "video" 면 startSec 이 이미 crossfade
 *   를 반영한 값이라 그대로 쓰고, 표식이 없으면 옛 번들이라 씬순번×crossfade 를 뺀다.
 * ★ 로그 스트림은 화면에 두지 않는다 — 터미널은 서버 창(run.bat) 하나다.
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, fmtBytes, fmtSec } from "./util.js";
import { pollJob, fireJobChanged, getPref, setPref } from "./store.js";
import { icon, hydrateIcons } from "./icons.js";
import { stackedBar } from "./charts.js";
import { actionBtn } from "./panel.js";

const STATUS_KO = { done: "완료", stale: "재렌더 필요", missing: "미생성", broken: "1:1 깨짐" };
const STATUS_TONE = { done: "ok", stale: "warn", missing: "idle", broken: "err" };
const KIND_KO = { cover: "표지", section: "과목", problem: "문제", answer: "해설",
                  countdown: "생각할 시간", gap: "여백" };

const V = { env: null, list: null, sel: new Set(), bundle: null, data: null,
            scene: null, polling: false, audio: null, beat: null };

export const meta = {
  title: (ctx) => (ctx.panel ? panelTitle(ctx) : `영상 제작·검수 · ${ctx.args[0] || ""}`),
  subtitle: (ctx) => (ctx.panel ? "" :
    "슬라이드·음성·자막을 확인하고 고칩니다. 렌더는 동시에 하나만."),
  actions: (ctx) => {
    if (ctx.panel && ctx.path === "/video") return [
      // ★ 굽기가 **렌더보다 앞**이다. 05/ 가 없으면 렌더할 것이 아예 없다 —
      //   전에는 입구가 CLI(`tools/bake_all.py`) 뿐이라 100번들이 `broken` 으로
      //   뜨고 [미완성만 렌더] 는 「렌더할 번들이 없습니다」 로 끝났다(2026-08-20).
      actionBtn("슬라이드 굽기", () => startBake("unbaked"), { iconName: "grid" }),
      actionBtn("미완성만 렌더", () => startRender("missing"), { iconName: "play" }),
      actionBtn("전체 렌더", () => startRender("all"), { iconName: "film" }),
    ];
    if (ctx.panel) return [];
    if (ctx.path.startsWith("/render/")) return [
      actionBtn("번들 목록", () => (location.hash = "#/video"), { iconName: "film" }),
      actionBtn("새로고침", () => refresh(), { iconName: "refresh" }),
    ];
    return [
      // 목록은 좌측 레일에서 연다 — 여기 또 두지 않는다.
      actionBtn("사전점검", () => (location.hash = "#/precheck/" + (V.bundle || "")),
        { iconName: "check" }),
      actionBtn("새로고침", () => refresh(), { iconName: "refresh" }),
    ];
  },
};

function panelTitle(ctx) {
  if (ctx.path.startsWith("/precheck/")) return `사전점검 · ${ctx.args[0]}`;
  if (ctx.path.startsWith("/job/")) return "렌더 로그";
  return "영상";
}

/* ★ 이 앱의 UX 핵심 — 목록은 패널(위층), 작업은 바탕(아래층).
 *     #/video        → 위층 패널: 번들 목록 (고르는 곳)
 *     #/video/:code  → 아래층 바탕: 그 번들의 작업 화면 (일하는 곳)
 *   패널을 닫아도 바탕은 언마운트되지 않으므로 렌더 폴링이 살아 있다.
 */
export async function mount(root, ctx) {
  if (ctx.panel) {
    if (ctx.path.startsWith("/precheck/")) return mountPrecheck(root, ctx);
    if (ctx.path.startsWith("/job/")) return mountJobPanel(root, ctx);
    return mountList(root, ctx);
  }
  // #/render/:jobId — 일괄 렌더 진행·터미널. 목록에서 [전체 렌더] 를 누르면 여기로 온다.
  if (ctx.path.startsWith("/render/")) return mountRun(root, ctx);
  return mountWork(root, ctx);
}

/* ══════════ 위층: 패널 — 번들 목록 ══════════ */
async function mountList(root, ctx) {
  root.innerHTML = `
    <div class="qz-bar"><span class="qz-bar-note muted" id="vd-envline"></span></div>
    <div class="table-wrap"><table class="data" id="vd-table"></table></div>
  `;
  await refresh(ctx);
}

/* ══════════ 아래층: 바탕 — 일괄 렌더 진행·터미널 ══════════
 * ★ 렌더 진행판이 바탕에 있어야 하는 이유가 둘이다.
 *   1) 패널은 Esc·스크림 클릭으로 닫히고, 닫히면 마크업이 사라진다. 24번들 2시간을
 *      폴링할 표면이 못 된다. (예전에는 목록 패널에서 렌더를 시작하면서 바탕 카드
 *      #vd-run-card 를 건드려 null.hidden 으로 터졌다.)
 *   2) 2층 라우터는 패널을 열고 닫아도 바탕을 언마운트하지 않는다 — 폴링이 살아 있다.
 */
async function mountRun(root, ctx) {
  const jobId = ctx.args[0];
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card" id="vd-run-card">
      <div class="card-title">렌더 진행</div>
      <div class="term-bar" id="vd-beatbar">
        <span class="term-dot"></span>
        <span id="vd-heartbeat">연결 중…</span>
      </div>
      <div id="vd-prog"></div>
    </div>
    <div class="card">
      <div class="card-title">번들 현황</div>
      <div class="table-wrap"><table class="data" id="vd-table"></table></div>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  try {
    [V.env, V.list] = await Promise.all([
      api("/api/render/env"), api("/api/render/bundles"),
    ]);
    renderTable();
  } catch (e) {
    toast("번들 상태를 불러오지 못했습니다: " + e.message, "err");
  }

  // 이미 끝난 잡이어도 마지막 상태와 로그 전문을 보여준다 — 원인을 봐야 한다.
  //
  // ★ 여기서 로그를 그리면 안 된다. pollJob 이 커서 0 부터 다시 받아 첫 틱에 같은 줄을
  //   또 붙인다(실제로 "[make] m01-1 시작" 이 두 번 찍혔다). 진행률만 즉시 그려서
  //   빈 화면을 피하고, 로그는 폴링 한 곳에서만 쓴다 — 끝난 잡도 첫 틱에 전문이 온다.
  try {
    const job = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    renderProgress(job);
    attachJob(jobId, job);
  } catch (e) {
    const box = $("#vd-prog");
    if (box) box.appendChild(el("div", "empty", "이 작업을 찾을 수 없습니다: " + e.message));
  }
}

/* ══════════ 본 화면 ══════════ */
/* ══════════ 아래층: 바탕 — 번들 작업 판 ══════════ */
async function mountWork(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card" id="vd-run-card" hidden>
      <div class="card-title">렌더 진행</div>
      <div id="vd-prog"></div>
    </div>
    <div id="vd-work"><div class="empty">불러오는 중…</div></div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  try {
    [V.env, V.list] = await Promise.all([
      api("/api/render/env"), api("/api/render/bundles"),
    ]);
  } catch (e) {
    toast("번들 상태를 불러오지 못했습니다: " + e.message, "err");
  }
  await openBundle(ctx.args[0]);

  // 진행 중인 렌더가 있으면 폴링을 다시 붙인다(화면 이동 후 복귀).
  try {
    const d = await api("/api/jobs?limit=5&kind=render");
    const live = (d.jobs || []).find((j) => j.status === "running" || j.status === "queued");
    if (live) attachJob(live.id);
  } catch (e) { /* 잡 계층 없으면 무시 */ }
}

async function refresh(ctx) {
  try {
    [V.env, V.list] = await Promise.all([
      api("/api/render/env"), api("/api/render/bundles"),
    ]);
  } catch (e) {
    toast("번들 상태를 불러오지 못했습니다: " + e.message, "err");
    return;
  }
  if ($("#vd-table")) { renderEnvLine(); renderTable(ctx); }
  if ($("#vd-work") && V.bundle) await openBundle(V.bundle);
}

/** 실행 환경은 카드 하나를 잡아먹을 값이 아니라 제목 옆 한 줄로 압축한다. */
function renderEnvLine() {
  const e = V.env, box = $("#vd-envline");
  if (!box) return;
  const c = V.list.counts;
  const bad = [];
  if (!e.python_ok) bad.push("chodangi python 없음");
  if (!e.driver_ok) bad.push("make_bundle_video.py 없음");
  box.innerHTML = "";
  box.appendChild(el("span", null,
    ` 완료 ${c.done || 0} · 재렌더 ${c.stale || 0} · 미생성 ${c.missing || 0}`
    + (c.broken ? ` · 1:1 깨짐 ${c.broken}` : "")));
  // ★ 그림파일이 모자란 번들은 렌더가 돌긴 돌지만 **다른 화면**이 나간다.
  //   개수를 여기서 미리 말해 둔다 — 표를 끝까지 내려보지 않아도 보이게.
  // ★ 고쳐 놓고 아직 안 돌린 번들 — 표를 안 훑어도 보이게 맨 위에서 말한다.
  const todo = (V.list.items || [])
    .filter((b) => b.speech_edited && b.status === "stale");
  if (todo.length) {
    const w = el("span", "badge warn",
      `고쳤는데 안 돌린 번들 ${todo.length}개 — 다시 렌더하세요`);
    w.title = todo.map((b) => b.code).join(" · ")
      + " — 체크해서 [선택 N개 렌더] 로 돌리면 됩니다.";
    box.appendChild(w);
  }
  const noImg = (V.list.items || []).filter((b) => !b.images_ready).length;
  if (noImg) {
    const w = el("span", "badge warn", `그림파일 불가 ${noImg}`);
    w.title = "이 번들은 deck.html 캡처로 폴백합니다 — "
      + "「슬라이드 제작 → ④ 그림파일 뽑기」를 먼저 돌리세요.";
    box.appendChild(w);
  }
  // 렌더가 돌고 있으면 어디서든 그 터미널로 갈 수 있어야 한다.
  if (e.busy) {
    const go = el("button", "badge brand", "렌더 진행 중 — 터미널 보기");
    go.type = "button";
    go.style.cursor = "pointer";
    go.addEventListener("click", async () => {
      try {
        const d = await api("/api/jobs?limit=5&kind=render");
        const live = (d.jobs || []).find((j) => j.status === "running" || j.status === "queued");
        location.hash = live ? "#/render/" + live.id : "#/video";
      } catch (err) { toast("작업을 찾지 못했습니다: " + err.message, "err"); }
    });
    box.appendChild(go);
  }
  if (bad.length) {
    const w = el("span", "badge err", bad.join(" · "));
    w.title = `${e.python}\n${e.driver}\n.env 의 XAM_CHODANGI 를 확인하세요.`;
    box.appendChild(w);
  }
}

function renderTable(ctx) {
  const t = $("#vd-table");
  t.innerHTML = `<thead><tr>
    <th style="width:28px"></th><th>번들</th><th>문항</th>
    <th>슬라이드/씬</th><th>이미지</th><th>길이</th><th>MP4</th><th>자막</th><th>상태</th><th></th>
  </tr></thead>`;
  const tb = el("tbody");
  V.list.items.forEach((b) => {
    const tr = el("tr");
    tr.style.cursor = "pointer";

    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = V.sel.has(b.code);
    cb.disabled = b.status === "broken";
    cb.addEventListener("click", (e) => e.stopPropagation());
    cb.addEventListener("change", () => {
      cb.checked ? V.sel.add(b.code) : V.sel.delete(b.code);
      updateSelAction();
    });
    tr.appendChild(td(cb));

    const name = el("td");
    name.appendChild(el("b", null, b.code));
    if (b.title) name.appendChild(el("div", "muted", b.title.slice(0, 46)));
    tr.appendChild(name);

    tr.appendChild(td(b.questions));
    const ratio = el("td");
    ratio.appendChild(el("span", b.ok_1to1 ? "" : "badge err",
      `${b.deck_slides < 0 ? "?" : b.deck_slides} / ${b.capture_scenes}`));
    ratio.appendChild(el("div", "muted", `전체 씬 ${b.scenes}`));
    tr.appendChild(ratio);

    tr.appendChild(imgCell(b));
    tr.appendChild(td(b.review.total_seconds ? fmtSec(b.review.total_seconds) : "—"));
    tr.appendChild(td(b.mp4.exists ? fmtBytes(b.mp4.bytes) : "—"));
    tr.appendChild(td(b.vtt.exists ? "있음" : "—"));

    const st = el("td");
    const badge = el("span", "badge " + STATUS_TONE[b.status], STATUS_KO[b.status]);
    if (b.reason) badge.title = b.reason;
    st.appendChild(badge);
    // ★ 사람이 고친 번들은 그 사실이 목록에서 보여야 한다. 고쳐도 mp4 는 그대로라
    //   「완료」 로 보이면 낡은 영상이 그대로 나간다.
    if (b.speech_edited) {
      const e = el("div", "muted", `손수정 ${b.speech_edited}씬`);
      e.title = "자막·발음을 고친 씬 수입니다. 「재렌더 필요」 면 다시 돌려야 반영됩니다.";
      st.appendChild(e);
    }
    tr.appendChild(st);

    const act = el("td", "vd-acts");
    act.appendChild(miniBtn("사전점검", (e) => {
      e.stopPropagation(); location.hash = "#/precheck/" + b.code;
    }));
    act.appendChild(miniBtn("렌더", (e) => {
      e.stopPropagation(); startRender([b.code]);
    }, { disabled: !b.ok_1to1 || !V.env.python_ok }));
    tr.appendChild(act);

    // ★ 행 전체가 클릭 대상 — 누르면 패널이 닫히고 바탕이 그 번들로 열린다
    tr.addEventListener("click", () => {
      if (ctx && ctx.navigate) ctx.navigate("/video/" + encodeURIComponent(b.code));
      else location.hash = "#/video/" + encodeURIComponent(b.code);
    });
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  updateSelAction();
}

/* ★ 그림파일 칸 — 「지금 렌더하면 무엇이 영상이 되는가」.
 *   슬라이드 화면에서 뽑은 PNG 가 지금 pptx · 씬과 맞을 때만 그대로 쓴다
 *   (`--reuse-images`). 어긋나면 deck.html 캡처로 폴백해 **확정한 화면과 다른**
 *   영상이 나간다 — 그 사실이 이 표 어디에도 안 보였다(2026-08-25).
 */
function imgCell(b) {
  const c = el("td");
  const ok = !!b.images_ready;
  const s = el("span", "badge " + (ok ? "ok" : "warn"), ok ? "가능" : "불가");
  s.title = ok
    ? `PowerPoint 로 뽑은 PNG ${b.images}장을 그대로 씁니다 (--reuse-images).`
    : (b.images
        ? `그림파일 ${b.images}장이 지금 pptx · 씨와 어긋납니다.`
        : "그림파일을 아직 안 뽑았습니다.")
      + " — 「슬라이드 제작 → ④ 그림파일 뽑기」를 먼저 돌리세요. "
      + "이대로 렌더하면 deck.html 캡처로 폴백합니다"
      + "(확정하신 화면과 다를 수 있습니다).";
  c.appendChild(s);
  return c;
}

const td = (v) => {
  const c = el("td");
  if (v instanceof Node) c.appendChild(v); else c.textContent = v;
  return c;
};

function miniBtn(label, fn, { disabled = false } = {}) {
  const b = el("button", "btn sm", label);
  b.type = "button";
  b.disabled = disabled;
  b.addEventListener("click", fn);
  return b;
}

function updateSelAction() {
  const head = $("#panel-actions") || $(".head-actions");
  if (!head) return;
  let btn = $("#vd-sel-btn");
  if (!V.sel.size) { if (btn) btn.remove(); return; }
  if (!btn) {
    btn = actionBtn("", () => startRender([...V.sel]),
      { primary: true, iconName: "play", id: "vd-sel-btn" });
    head.insertBefore(btn, head.firstChild);
  }
  btn.lastChild.textContent = `선택 ${V.sel.size}개 렌더`;
}

/* ══════════ 바닥: 실행 판 ══════════ */
async function openBundle(code) {
  V.bundle = code;
  setPref("vd.bundle", code);
  const box = $("#vd-work");
  if (!box) return;
  box.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    V.data = await api(`/api/render/bundles/${encodeURIComponent(code)}/scenes`);
  } catch (e) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", "씬을 불러오지 못했습니다: " + e.message));
    return;
  }
  V.scene = V.data.scenes.find((s) => !s.silent) || V.data.scenes[0] || null;
  renderWork();
}

function renderWork() {
  const d = V.data, info = d.info;
  const box = $("#vd-work");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = `
    <div class="card">
      <div class="card-title">${escapeHtml(d.bundle)} — 씬 ${d.count}개
        <span class="muted"> ${escapeHtml(d.title || "")} · 음성 ${escapeHtml(d.voice || "?")} · ${d.speed || 1}배</span>
      </div>
      <div class="vd-env" id="vd-w-chips"></div>
      <div id="vd-w-warn"></div>
      <div class="vd-work-split">
        <aside class="vd-scenes" id="vd-scenes"></aside>
        <section id="vd-stage"></section>
      </div>
    </div>
  `;

  const chips = $("#vd-w-chips");
  const chip = (text, tone, title) => {
    const c = el("span", "status-chip " + (tone || ""), text);
    if (title) c.title = title;
    return c;
  };
  chips.appendChild(chip(STATUS_KO[info.status], STATUS_TONE[info.status] === "ok" ? "ok"
    : STATUS_TONE[info.status] === "err" ? "bad" : "warn", info.reason || ""));
  chips.appendChild(chip(`슬라이드 ${info.deck_slides} / 캡처 씬 ${info.capture_scenes}`,
    info.ok_1to1 ? "ok" : "bad"));
  chips.appendChild(chip(`음성 ${info.audio}개`));
  chips.appendChild(chip(`이미지 ${info.images}개`));
  if (info.mp4.exists) chips.appendChild(chip(`mp4 ${fmtBytes(info.mp4.bytes)}`));
  chips.appendChild(chip(info.vtt.exists ? "자막 있음" : "자막 없음",
    info.vtt.exists ? "ok" : "warn"));

  // 자막 시각 드리프트 — 고친 뒤에 만든 번들(timebase="video")은 뜨지 않는다.
  if (!d.compensated && d.drift_sec > 1) {
    const w = el("div", "qz-warn warn");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null,
      `이 번들은 crossfade 보정 전에 만들어졌습니다 — mp4 에 구워진 자막이 최대 `
      + `${d.drift_sec}초 앞섭니다 (씬 경계마다 ${d.crossfade_sec}초). `
      + `아래 시크는 보정한 값을 쓰므로 검수는 정확합니다. `
      + `다시 렌더하면 자막 자체가 맞게 나옵니다.`));
    $("#vd-w-warn").appendChild(w);
  }

  renderSceneList();
  renderStage();
}

function renderSceneList() {
  const box = $("#vd-scenes");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  V.data.scenes.forEach((s) => {
    const row = el("div", "vd-scene" + (V.scene && V.scene.scene === s.scene ? " on" : "")
      + (s.silent ? " silent" : ""));
    row.appendChild(el("span", "vd-scene-no", String(s.scene).padStart(2, "0")));
    const mid = el("span", "vd-scene-t");
    mid.textContent = s.heading || KIND_KO[s.kind] || s.kind || "";
    if (s.silent) mid.textContent += " (무음)";
    row.appendChild(mid);
    row.appendChild(el("span", "vd-scene-d", s.dur_sec != null ? fmtSec(s.dur_sec) : "—"));
    row.addEventListener("click", () => {
      V.scene = s;
      $$("#vd-scenes .vd-scene").forEach((r) => r.classList.remove("on"));
      row.classList.add("on");
      renderStage();
    });
    box.appendChild(row);
  });
}

/* 바탕 실행 판의 순서 — 요청대로 고정한다.
 *   1) 자막 / 발음 2단
 *   2) 버튼들
 *   3) 자막 미리보기 (재생하면 그 시간의 큐가 뜬다)
 *   4) 자막 시간 · 자막 텍스트 (큐별 편집)
 *   5) 슬라이드
 *   6) 영상에서 확인
 */
function renderStage() {
  const stage = $("#vd-stage");
  const s = V.scene;
  stage.innerHTML = "";
  if (!s) {
    stage.appendChild(el("div", "empty", "씬을 고르세요."));
    return;
  }
  const pad = (n) => String(n).padStart(2, "0");
  // ★ 자막은 **원문**(narration)으로 쪼갠다. 발음(speech)은 숫자가 소리로 바뀌어
  //   있어서 그걸로 자막을 만들면 화면에 「이 번입니다」가 뜬다.
  const cueTexts = splitCues(s.narration, Math.max(1, s.cues.length));

  // ── 머리줄
  const head = el("div", "qz-ed-head");
  head.appendChild(el("span", "badge brand", `씬 ${pad(s.scene)}`));
  head.appendChild(el("span", "qz-ed-id", s.heading || KIND_KO[s.kind] || s.kind));
  head.appendChild(el("span", "badge", s.kind || ""));
  if (s.dur_sec != null) head.appendChild(el("span", "badge info", fmtSec(s.dur_sec)));
  if (s.silent) head.appendChild(el("span", "badge idle", "무음"));
  if (s.speech_edited) head.appendChild(el("span", "badge ok", "발음 손수정"));
  stage.appendChild(head);

  // ── 1) 자막 / 발음 2단
  const two = el("div", "vd-2col");

  const subCol = el("div");
  subCol.appendChild(el("label", "qz-label",
    "자막 — 화면에 뜨는 글자. 고치면 발음도 이 글에서 다시 만듭니다"));
  const subTa = el("textarea");
  subTa.id = "vd-subtitle";
  subTa.rows = 5;
  subTa.value = s.silent ? "" : cueTexts.join("\n");
  subTa.disabled = !!s.silent;
  subTa.addEventListener("input", () => { markStageDirty(); renderSubPreview(); });
  subCol.appendChild(subTa);
  subCol.appendChild(el("div", "field-hint", s.silent
    ? "무음 씬이라 자막이 없습니다."
    : "한 줄이 한 큐입니다. TTS 는 이 글을 읽지 않습니다 — 오른쪽 발음을 읽습니다."));
  two.appendChild(subCol);

  const narCol = el("div");
  narCol.appendChild(el("label", "qz-label",
    "발음 — TTS 가 실제로 읽는 글. 자막은 그대로 두고 여기만 고칩니다"));
  if (s.silent) {
    const info = el("div", "qz-warn info");
    info.appendChild(icon("bulb", 15));
    info.appendChild(el("span", null, s.kind === "countdown"
      ? `생각할 시간 ${s.countdown_seconds ?? 5}초 — 무음 구간입니다.`
      : `여백 ${s.gap_seconds ?? 2}초 — 무음 구간입니다.`));
    narCol.appendChild(info);
  } else {
    const narTa = el("textarea");
    narTa.id = "vd-narration";
    narTa.rows = 5;
    narTa.value = s.speech || "";
    narTa.addEventListener("input", () => { markStageDirty(); renderSpeechChips(); });
    narCol.appendChild(narTa);

    /* 숫자를 소리대로 — **이 칸 안에서만** 바꾼다. 자막에서 다시 만들지 않는다:
       발음 칸에는 손으로 고친 것이 이미 얹혀 있어서 다시 만들면 통째로 날아간다.
       (showcase 의 static/js/deck.js 가 같은 이유로 같은 규칙을 쓴다) */
    const nb = miniBtn("숫자를 소리대로", async () => {
      const before = narTa.value;
      if (!/\d/.test(before)) { toast("바꿀 숫자가 없습니다."); return; }
      try {
        const r = await api("/api/render/speak-numbers", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: before }),
        });
        if (r.text === before) { toast("바꿀 숫자가 없습니다."); return; }
        narTa.value = r.text;
        markStageDirty();
        renderSpeechChips();
        toast("바꿨습니다 — 읽어 보고 [발음 저장] 하세요.");
      } catch (e) { toast("바꾸지 못했습니다: " + e.message, "err"); }
    });
    nb.title = "2007년 → 이천칠 년 · 8.2% → 팔 쩜 이 퍼센트\n숫자만 바꿉니다";
    narCol.appendChild(nb);

    const chips = el("div", "qz-speech-check");
    chips.id = "vd-speech-chips";
    narCol.appendChild(chips);
  }

  // 음성 플레이어 — 발음의 결과물이라 이 칼럼에 둔다
  if (s.audio.exists) {
    narCol.appendChild(el("label", "qz-label",
      `음성 — audio/scene_${pad(s.scene)}.wav · ${fmtBytes(s.audio.bytes)}`));
    const a = el("audio", "vd-audio");
    a.id = "vd-audio-el";
    a.controls = true;
    a.preload = "metadata";
    a.src = s.audio.url;
    a.addEventListener("timeupdate", () => renderSubPreview(a.currentTime));
    a.addEventListener("seeked", () => renderSubPreview(a.currentTime));
    narCol.appendChild(a);
    V.audio = a;
  } else {
    narCol.appendChild(el("div", "empty", "이 씬의 음성 파일이 없습니다."));
    V.audio = null;
  }
  two.appendChild(narCol);
  stage.appendChild(two);

  // ── 2) 버튼들
  const foot = el("div", "qz-foot");
  const save = el("button", "btn primary", "자막+발음 저장");
  save.type = "button";
  save.id = "vd-save";
  save.disabled = true;
  save.title = "두 칸을 한꺼번에 05/" + V.bundle + "/script/" + V.bundle
    + "_speech.json 에 남깁니다 — 다시 구워도 지워지지 않습니다";
  save.addEventListener("click", () => saveSpeech());
  foot.appendChild(save);

  const resynth = el("button", "btn", "이 씬 재합성 (발음 반영)");
  resynth.type = "button";
  resynth.id = "vd-resynth";
  resynth.disabled = !!s.silent;
  resynth.title = "지금 발음 칸에 적힌 대로 이 씬 음성만 다시 만듭니다 (mp4 는 그대로)";
  resynth.addEventListener("click", () => resynthScene(resynth));
  foot.appendChild(resynth);


  const hint = el("span", "field-hint qz-foot-hint");
  hint.id = "vd-stage-hint";
  foot.appendChild(hint);
  stage.appendChild(foot);
  // 낡음은 씬을 열 때부터 보여야 한다 — 재합성한 뒤에만 뜨면 새로 고치면 사라진다
  V.staleScenes = (V.data && V.data.stale_scenes) || [];
  renderStaleNote(null);

  // ── 2.5) 용어 사전 — 되풀이되는 용어는 씬마다 고치지 말고 여기 한 줄로
  stage.appendChild(lexiconBox());

  // ── 3) 자막 미리보기
  const pv = el("div", "qz-field");
  pv.appendChild(el("label", "qz-label",
    "자막 미리보기 — 재생하면 그 시간의 큐가 뜹니다"));
  const stagePv = el("div", "vd-subpv");
  stagePv.id = "vd-subpv";
  pv.appendChild(stagePv);
  stage.appendChild(pv);

  // ── 4) 자막 시간 · 자막 텍스트
  const cue = el("div", "qz-field");
  cue.appendChild(el("label", "qz-label",
    `자막 시간 · 자막 텍스트 (${s.cues.length}개 큐)`));
  if (!s.cues.length) {
    cue.appendChild(el("div", "empty", s.silent
      ? "무음 씬이라 자막이 없습니다."
      : "이 씬의 큐가 review.json 에 없습니다."));
  } else {
    s.cues.forEach((c, i) => {
      const row = el("div", "vd-cue");
      row.dataset.i = String(i);
      row.appendChild(el("span", "vd-cue-t",
        `${fmtClock(c.start)} → ${fmtClock(c.end)}`));
      const ta = el("textarea");
      ta.rows = 1;
      ta.value = cueTexts[i] || "";
      ta.addEventListener("input", () => { markStageDirty(); syncSubtitleFromCues(); });
      row.appendChild(ta);
      row.appendChild(miniBtn("▶", () => {
        if (!V.audio) return;
        V.audio.currentTime = c.start || 0;
        V.audio.play();
      }));
      cue.appendChild(row);
    });
    cue.appendChild(el("div", "field-hint",
      "review.json 의 cues 는 시각만 들고 있어서 글자는 발음에서 잘라 보여줍니다. "
      + "자막을 발음과 다르게 쓰려면 분리해 저장해야 합니다 — "
      + "TTS 는 “아이알오아이”로 읽고 화면엔 “ROI”로 뜨게 하려면 이게 필요합니다."));
  }
  stage.appendChild(cue);

  // ── 5) 슬라이드
  const slide = el("div", "qz-field");
  slide.appendChild(el("label", "qz-label", "슬라이드 — " + (s.image.exists
    ? `images/slide_${pad(s.scene)}.png` : "이미지 없음")));
  if (s.image.exists) {
    const img = el("img", "vd-slide");
    img.src = s.image.url;
    img.alt = `씬 ${s.scene} 슬라이드`;
    img.loading = "lazy";
    slide.appendChild(img);
  } else {
    slide.appendChild(el("div", "empty", "이 씬의 슬라이드 이미지가 없습니다."));
  }
  stage.appendChild(slide);

  // ── 6) 영상에서 확인
  if (V.data.info.mp4.exists) {
    const card = el("div", "card");
    card.appendChild(el("div", "card-title", "영상에서 확인"));
    const v = el("video", "vd-video");
    v.id = "vd-video";
    v.controls = true;
    v.preload = "metadata";
    v.src = V.data.info.mp4.url;
    if (V.data.info.vtt.exists) {
      const tr = document.createElement("track");
      tr.src = V.data.info.vtt.url;
      tr.kind = "subtitles";
      tr.srclang = "ko";
      tr.label = "한국어";
      tr.default = true;
      v.appendChild(tr);
    }
    card.appendChild(v);
    card.appendChild(el("div", "field-hint",
      V.data.compensated
        ? "[영상에서 이 지점] 은 review.json 의 startSec 으로 그대로 이동합니다 "
          + "(이 번들은 crossfade 가 반영돼 있습니다)."
        : "[영상에서 이 지점] 은 crossfade 보정한 위치로 이동합니다 "
          + `(review.json 보다 약 ${V.data.drift_sec}초 늦은 지점).`));
    stage.appendChild(card);
  }

  renderSpeechChips();
  renderSubPreview();
}

/** 큐 편집 → 왼쪽 자막 전체 텍스트 동기화 */
function syncSubtitleFromCues() {
  const rows = $$("#vd-stage .vd-cue textarea");
  const ta = $("#vd-subtitle");
  if (!ta || !rows.length) return;
  ta.value = rows.map((r) => r.value).join("\n");
  renderSubPreview();
}

/** 자막 미리보기 — 영상 위에 뜨는 모습. 재생 위치의 큐를 띄운다. */
function renderSubPreview(atSec) {
  const box = $("#vd-subpv");
  const s = V.scene;
  if (!box || !s) return;
  const ta = $("#vd-subtitle");
  const lines = (ta ? ta.value : "").split("\n").filter((l) => l.trim());
  let idx = 0;
  if (atSec != null && s.cues.length) {
    const hit = s.cues.findIndex((c) => atSec >= (c.start || 0) && atSec < (c.end || 0));
    if (hit >= 0) idx = hit;
    else if (atSec >= (s.cues[s.cues.length - 1].end || 0)) idx = s.cues.length - 1;
  }
  box.innerHTML = "";
  if (!lines.length) {
    box.appendChild(el("div", "vd-subpv-empty",
      s.silent ? "무음 씬 — 자막 없음" : "자막이 비어 있습니다"));
    return;
  }
  box.appendChild(el("div", "vd-subpv-text", lines[Math.min(idx, lines.length - 1)]));
  const c = s.cues[idx];
  box.appendChild(el("div", "vd-subpv-meta", c
    ? `큐 ${idx + 1} / ${lines.length} · ${fmtClock(c.start)} → ${fmtClock(c.end)}`
    : `큐 ${idx + 1} / ${lines.length}`));

  // 큐 행 강조 — 지금 어느 줄이 뜨는지 표에서도 보인다
  $$("#vd-stage .vd-cue").forEach((r) => {
    r.classList.toggle("on", Number(r.dataset.i) === idx);
  });
}

/** 발음 검사 칩 — 낭독문을 고칠 때마다 갱신 */
function renderSpeechChips() {
  const box = $("#vd-speech-chips");
  const s = V.scene;
  if (!box || !s) return;
  const ta = $("#vd-narration");
  const built = speechCheck({ ...s, narration: (ta ? ta.value : s.narration) || "" });
  box.innerHTML = "";
  while (built.firstChild) box.appendChild(built.firstChild);
}

function speechCheck(s) {
  const KOR = ["일", "이", "삼", "사", "오"];
  const box = el("div", "qz-speech-check");
  const t = (s.narration || "").trim();
  const m = t.match(/^정답은\s*(일|이|삼|사|오)\s*번/);
  if (s.kind === "answer") {
    if (!m) {
      box.appendChild(el("span", "status-chip warn",
        "해설 씬인데 ‘정답은 N 번입니다.’ 로 시작하지 않습니다"));
    } else {
      box.appendChild(el("span", "status-chip ok", `낭독문 정답 ${m[1]} 번`));
    }
  }
  const chars = t.length;
  box.appendChild(el("span", "status-chip", `${chars}자`));
  if (chars && s.dur_sec) {
    box.appendChild(el("span", "status-chip",
      `${(chars / s.dur_sec).toFixed(1)}자/초`));
  }
  return box;
}

/** review.json 의 cues 는 시각만 있으므로 낭독문을 큐 수만큼 나눠 보여준다. */
function splitCues(text, n) {
  const t = (text || "").trim();
  if (!t || n <= 0) return [];
  if (n === 1) return [t];
  // 문장 끝 → 쉼표 순으로 자른다 (voicewright.srt.split_into_cues 와 같은 취지)
  const parts = t.split(/(?<=[.!?。])\s+/).filter(Boolean);
  if (parts.length >= n) {
    const out = [];
    const per = Math.ceil(parts.length / n);
    for (let i = 0; i < n; i++) out.push(parts.slice(i * per, (i + 1) * per).join(" "));
    return out;
  }
  const per = Math.ceil(t.length / n);
  const out = [];
  for (let i = 0; i < n; i++) out.push(t.slice(i * per, (i + 1) * per));
  return out;
}

function fmtClock(sec) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

function markStageDirty() {
  const save = $("#vd-save"), re = $("#vd-resynth");
  if (save) save.disabled = false;
  if (re) re.disabled = false;
  const h = $("#vd-stage-hint");
  if (h) h.textContent = "저장하지 않은 수정이 있습니다.";
}

/* ── 발음 저장 · 씬 재합성 ────────────────────────────────────────────
 *
 * 자막(`narration`)과 발음(`narration_text`)을 **한 단추로** 같이 남긴다. 둘 다
 * `<번들>_speech.json` 으로 가고 bake 가 다시 구울 때 병합한다 — 재베이크·재렌더에
 * 지워지지 않는다.
 *
 * ★ 자막을 고치면 발음은 **고친 자막에서** 다시 만들어진다. 「다섯 행」 을 「5행」 으로
 *   고치면 소리도 그 글에서 나온다 — 발음 칸까지 손댔으면 그쪽이 이긴다.
 * ★ 자막을 원문 그대로 두면 자막 덮어쓰기는 남기지 않는다. 안 그러면 손대지 않은
 *   씬까지 「고침」 으로 표시되고, 원문이 바뀌어도 옛 자막에 묶인다.
 * ★ 렌더 단추는 여기 없다 — 목록에서 체크해 [선택 N개 렌더] 로 돈다. 고친 번들은
 *   목록이 「재렌더 필요」 로 집어 준다.
 */
async function saveSpeech() {
  const s = V.scene;
  const ta = $("#vd-narration");
  const subTa = $("#vd-subtitle");
  if (!s || !ta) return;
  const btn = $("#vd-save");
  if (btn) btn.disabled = true;
  try {
    const r = await api(
      `/api/render/bundles/${encodeURIComponent(V.bundle)}/speech`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        // ★ `from` 은 고칠 때의 자막 **원문**(대조용), `subtitle` 은 고친 자막이다.
        //   원문을 함께 보내야 나중에 "무엇을 왜 고쳤나" 를 읽어낼 수 있고,
        //   발문이 그 뒤에 바뀌면 bake 가 낡은 손수정을 안 쓰고 집어 준다.
        body: JSON.stringify({ scene: s.scene, text: ta.value,
                               subtitle: (subTa && !subTa.disabled ? subTa.value : ""),
                               from: s.narration_src || s.narration || "" }),
      });
    s.speech = ta.value;
    if (subTa && !subTa.disabled) s.narration = subTa.value;
    s.speech_edited = !r.removed;
    toast(r.removed
      ? "덮어쓰기를 지웠습니다 — 원문을 그대로 씁니다."
      : `자막·발음을 저장했습니다 (이 번들 ${r.count}개) — `
        + "[이 씬 재합성] 으로 들어 보세요.");
    const h = $("#vd-stage-hint");
    if (h) h.textContent = `05/${V.bundle}/ · 씬 ${s.scene}`;
    renderStage();
  } catch (e) {
    toast("저장하지 못했습니다: " + e.message, "err");
    if (btn) btn.disabled = false;
  }
}

async function resynthScene(btn) {
  const s = V.scene;
  const ta = $("#vd-narration");
  if (!s || !ta) return;
  const was = btn.textContent;
  btn.disabled = true;
  /* 초가 올라가는 것이 "살아 있다" 의 유일한 증거다 — 씬 하나가 10~90초다. */
  const t0 = Date.now();
  const tick = () => {
    const v = Math.floor((Date.now() - t0) / 1000);
    btn.textContent = `합성 중 · ${Math.floor(v / 60)}:${String(v % 60).padStart(2, "0")}`;
  };
  tick();
  const iv = setInterval(tick, 1000);
  try {
    const r = await api(
      `/api/render/bundles/${encodeURIComponent(V.bundle)}/resynth`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scene: s.scene, text: ta.value }),
      });
    toast(`씬 ${s.scene} 음성을 다시 만들었습니다 (${fmtSec(r.sec)}) — 들어 보세요.`);
    const a = $("#vd-audio-el");
    if (a) {
      // ★ 같은 이름에 다른 소리다 — 꼬리표를 붙여야 옛 소리가 다시 안 난다
      a.src = a.src.split("?")[0] + "?v=" + Date.now();
      a.load();
      a.play().catch(() => { /* 자동재생을 막는 브라우저면 누르면 된다 */ });
    }
    /* ★ 길이가 바뀌면 자막 시각이 밀리고 mp4 가 낡는다. 조용히 두면 어긋난 것이
       그대로 드라이브로 올라간다 — 화면이 말한다. */
    V.staleScenes = r.stale_scenes || [];
    renderStaleNote(r);
  } catch (e) {
    toast("다시 만들지 못했습니다: " + e.message, "err");
  } finally {
    clearInterval(iv);
    btn.textContent = was;
    btn.disabled = false;
  }
}

/* ── 용어 사전 ────────────────────────────────────────────────────────
 *
 * `vendor/chodangi/config/pronunciation_map.yaml` 을 여기서 고친다. 파일을 직접
 * 열어야 했던 것이 앱에 입구가 없었기 때문이다.
 *
 * ★ 씬 발음과 **어느 쪽이 싼가**가 이 칸의 존재 이유다. 한 용어가 여러 번들에
 *   나오면 씬마다 고치는 것은 그 횟수만큼 일이고, 사전은 한 줄이다. 그래서
 *   「사전에 없어 낱자로 읽히는 약어」를 빈도와 함께 보여 준다 — 빈 입력칸만 주고
 *   알아서 채우라고 하지 않는다.
 *
 * ★ 읽는 소리는 **채워 넣지 않는다.** 용어 읽는 법은 사람이 정할 일이다
 *   (2026-08-18 지시: "제가 수정하면서 규칙을 정해야 해요"). 화면은 지금 어떻게
 *   읽히는지만 보여 주고 빈칸을 둔다.
 */
/* 두 사전을 한 표로 — 어느 쪽 것인지 배지로 갈라 놓는다.
 * ★ 검색칸이 요점이다. 품목 사전만 210개라 눈으로 훑어서는 못 찾는다 —
 *   `DENSE_RANK` 를 찾다가 못 찾은 것이 이 표를 만든 이유다(2026-08-26).
 */
function lexTable(prod, common) {
  const wrap = el("div", "qz-field");
  const q = el("input");
  q.placeholder = "용어나 소리로 찾기 — 예: DENSE, 랭크";
  q.style.width = "100%";
  wrap.appendChild(q);

  const rows = [];
  Object.keys(prod.rules || {}).forEach((k) =>
    rows.push({ term: k, say: prod.rules[k], scope: "product" }));
  Object.keys(common.rules || {}).forEach((k) =>
    rows.push({ term: k, say: common.rules[k], scope: "common" }));

  const holder = el("div", "tbl-wrap");
  holder.style.cssText = "max-height:34vh;overflow:auto";
  wrap.appendChild(holder);
  const foot = el("div", "field-hint");
  wrap.appendChild(foot);

  const draw = () => {
    const needle = q.value.trim().toLowerCase();
    const hit = needle
      ? rows.filter((r) => r.term.toLowerCase().includes(needle)
                        || r.say.toLowerCase().includes(needle))
      : rows;
    holder.innerHTML = "";
    foot.textContent = needle
      ? `${hit.length}개 찾았습니다 (전체 ${rows.length}개)`
      : `전체 ${rows.length}개 — 품목 ${prod.count} · 공용 ${common.count}`;
    const tb = el("table", "tbl");
    tb.innerHTML = "<thead><tr><th>어디</th><th>용어</th><th>읽는 소리</th><th></th></tr></thead>";
    const body = el("tbody");
    hit.slice(0, 300).forEach((r) => {
      const tr = el("tr");
      tr.appendChild(el("td", null,
        el("span", "badge " + (r.scope === "product" ? "ok" : "idle"),
           r.scope === "product" ? "품목" : "공용")));
      tr.appendChild(el("td", null, r.term));
      const sayTd = el("td");
      const inp = el("input");
      inp.value = r.say;
      inp.style.width = "100%";
      sayTd.appendChild(inp);
      tr.appendChild(sayTd);
      const act = el("td");
      act.appendChild(miniBtn("고치기", async () => {
        if (!inp.value.trim()) { toast("읽는 소리를 비울 수 없습니다."); return; }
        try {
          await api("/api/render/lexicon", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ term: r.term, say: inp.value, scope: r.scope }),
          });
          toast(`«${r.term}» → «${inp.value.trim()}» 로 고쳤습니다.`);
          loadLexicon();
        } catch (e) { toast("고치지 못했습니다: " + e.message, "err"); }
      }));
      tr.appendChild(act);
      body.appendChild(tr);
    });
    tb.appendChild(body);
    holder.appendChild(tb);
    if (hit.length > 300) {
      // ★ 자른 것을 말한다. 조용히 300개만 보여 주면 "없다" 로 읽힌다.
      foot.textContent += " · 300개까지만 그렸습니다 — 검색칸으로 좁히세요";
    }
  };
  q.addEventListener("input", draw);
  draw();
  return wrap;
}

function lexiconBox() {
  const box = el("details", "pb-paste");
  box.appendChild(el("summary", null, "용어 사전 — 되풀이되는 용어는 여기 한 줄로"));
  const body = el("div");
  body.id = "vd-lex";
  body.appendChild(el("div", "field-hint", "불러오는 중…"));
  box.appendChild(body);
  box.addEventListener("toggle", () => { if (box.open) loadLexicon(); }, { once: true });
  return box;
}

async function loadLexicon() {
  const box = $("#vd-lex");
  if (!box) return;
  let d;
  try {
    const rn = (V.bundle || "").split("-")[0];      // m01-6 → m01 (이 회차만)
    d = await api(`/api/render/lexicon?round=${encodeURIComponent(rn)}`);
  } catch (e) {
    box.innerHTML = "";
    box.appendChild(el("div", "empty", "사전을 읽지 못했습니다: " + e.message));
    return;
  }
  box.innerHTML = "";
  if (d.error) {
    const w = el("div", "qz-warn err");
    w.appendChild(icon("alert", 15));
    w.appendChild(el("span", null, d.error));
    box.appendChild(w);
  }
  const prod = d.product || { rules: {}, count: 0, path: "", label: "" };

  /* ★ 사전이 둘이고 **거는 때가 다르다.** 어디에 넣을지가 결과를 가른다.
   *     품목 사전 : bake 가 대본을 쓸 때 — 대본에 한글로 박히고 화면에도 보인다.
   *     공용 사전 : 엔진이 합성 직전에 — 대본은 로마자 그대로, 소리만 바뀐다.
   *   품목 사전이 먼저 바꾼 낱말은 대본에 로마자가 안 남아 공용 사전에 안 걸린다. */
  box.appendChild(el("div", "field-hint",
    `품목 «${prod.label || "?"}» ${prod.count}개 · 공용 ${d.count}개. `
    + "품목 사전은 대본을 쓸 때, 공용 사전은 소리를 낼 때 걸립니다 — "
    + "둘 다 자막은 원문 그대로 두고 소리만 바꿉니다."));

  // 새 항목 — 어느 사전에 넣을지 고른다
  const add = el("div", "qz-foot");
  const scope = el("select", "box");
  scope.innerHTML = `<option value="product">품목 (${escapeHtml(prod.label || "")})</option>`
    + `<option value="common">공용 (모든 품목)</option>`;
  scope.style.width = "13rem";
  const term = el("input");
  term.placeholder = "용어 (예: DENSE_RANK)";
  term.style.width = "11rem";
  const say = el("input");
  say.placeholder = "읽는 소리";
  say.style.width = "12rem";
  add.append(scope, term, say, miniBtn("사전에 넣기", async () => {
    if (!term.value.trim() || !say.value.trim()) {
      toast("용어와 읽는 소리를 둘 다 넣으세요."); return;
    }
    try {
      const r = await api("/api/render/lexicon", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ term: term.value, say: say.value, scope: scope.value }),
      });
      toast(r.was ? `«${r.key}» 를 «${r.was}» → «${r.value}» 로 바꿨습니다.`
                  : `«${r.key}» → «${r.value}» 넣었습니다 (${r.count}개).`);
      loadLexicon();
    } catch (e) { toast("넣지 못했습니다: " + e.message, "err"); }
  }));
  box.appendChild(add);

  // ── 지금 들어 있는 것 — 찾을 수 있어야 고친다
  box.appendChild(lexTable(prod, d));

  // 후보 — 이 회차 낭독문에 있는데 사전에 없는 약어
  const c = d.candidates || [];
  if (!c.length) {
    box.appendChild(el("div", "field-hint",
      "이 회차의 대문자 약어는 모두 사전에 있습니다."));
    return;
  }
  box.appendChild(el("div", "field-hint",
    `이 회차 낭독문에 있는데 사전에 없는 약어 ${c.length}종 — 엔진이 낱자로 읽습니다. `
    + "맞으면 그대로 두고, 틀린 것만 채우세요."));
  const tbl = el("table", "tbl");
  tbl.innerHTML = "<thead><tr><th>용어</th><th>횟수</th><th>지금 읽는 소리</th>"
    + "<th>이렇게 읽어라</th><th></th></tr></thead>";
  const tb = el("tbody");
  c.forEach((x) => {
    const tr = el("tr");
    tr.appendChild(el("td", null, x.term));
    tr.appendChild(el("td", "muted", `${x.count}회`));
    tr.appendChild(el("td", "muted", x.now));
    const inp = el("input");
    inp.placeholder = "비우면 그대로";
    inp.style.width = "100%";
    inp.title = x.where;
    const cell = el("td");
    cell.appendChild(inp);
    tr.appendChild(cell);
    // ★ `el(tag, cls, txt)` 의 3번째는 **글자**다 — 요소를 주면 textContent 로
    //   들어가 「[object HTMLButtonElement]」 가 찍힌다(실측 2026-08-26).
    const actTd = el("td");
    actTd.appendChild(miniBtn("넣기", async () => {
      if (!inp.value.trim()) { toast("읽는 소리를 넣으세요."); return; }
      try {
        await api("/api/render/lexicon", {
          method: "POST", headers: { "Content-Type": "application/json" },
          // ★ 후보는 **품목 사전**으로 간다 — 대본에 박혀야 화면에도 보이고,
          //   공용에 넣으면 대본은 로마자 그대로라 무엇이 바뀌는지 안 보인다.
          body: JSON.stringify({ term: x.term, say: inp.value, scope: "product" }),
        });
        toast(`«${x.term}» → «${inp.value.trim()}» 넣었습니다.`);
        loadLexicon();
      } catch (e) { toast("넣지 못했습니다: " + e.message, "err"); }
    }));
    tr.appendChild(actTd);
    tb.appendChild(tr);
  });
  tbl.appendChild(tb);
  const wrap = el("div", "tbl-wrap");
  wrap.appendChild(tbl);
  box.appendChild(wrap);
}

function renderStaleNote(r) {
  const hint = $("#vd-stage-hint");
  if (!hint) return;
  const n = (V.staleScenes || []).length;
  const bits = [];
  if (r && r.shifted && r.was != null) {
    bits.push(`길이 ${fmtSec(r.was)} → ${fmtSec(r.sec)}`);
  }
  if (n) bits.push(`mp4 가 ${n}개 씬보다 낡았습니다 — 다 고치신 뒤 [이 번들 재렌더]`);
  hint.textContent = bits.length ? bits.join(" · ") : `05/${V.bundle}/ · 씬 ${V.scene?.scene}`;
  hint.classList.toggle("err", n > 0);
}

/* ══════════ 렌더 실행 ══════════ */
/* ★ 05/ 굽기 — deck.html · script · lesson 을 만든다. mp4 는 안 만든다.
   모델을 안 부르고 룰베이스 조립이라 100번들이 몇 분이다(돈이 안 든다). */
async function startBake(codes) {
  const rows = (V.list && V.list.items) || [];
  const nAll = rows.length;
  const nTodo = rows.filter((b) => b.status === "broken").length;
  const n = codes === "all" ? nAll : codes === "unbaked" ? nTodo : codes.length;
  const label = codes === "all" ? `전체 ${nAll}개 번들`
    : codes === "unbaked" ? `아직 안 구운 ${nTodo}개 번들` : `${codes.length}개 번들`;
  if (!n) { toast("구울 번들이 없습니다 — 이미 다 구웠습니다.", "err"); return; }

  const ok = await confirmModal({
    title: "슬라이드를 구울까요?",
    body: `<b>${escapeHtml(label)}</b><br><br>`
      + "<code>05/</code> 에 슬라이드(deck.html) · 대본 · lesson 을 만듭니다. "
      + "<b>영상(mp4)은 만들지 않습니다</b> — 그건 [미완성만 렌더] 입니다.<br>"
      + "모델을 부르지 않아 <b>돈이 들지 않고</b>, 번들당 몇 초라 몇 분이면 끝납니다.<br>"
      + "1:1(슬라이드↔씬)이 깨진 번들은 그것만 건너뛰고 이유를 로그에 남깁니다.",
    ok: "굽기 시작", cancel: "취소",
  });
  if (!ok) return;

  let r;
  try {
    r = await api("/api/render/bake", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes }),
    });
  } catch (e) {
    toast("시작하지 못했습니다: " + e.message, "err");
    return;
  }
  toast(`슬라이드 굽기 시작 — ${n}번들`);
  location.hash = "#/job/" + r.id;
}

async function startRender(codes) {
  // ★ 개수를 상수로 쓰지 않는다. 회차 수는 폴더마다 다르다(3회차 24개 / 21회차 168개).
  const rows = (V.list && V.list.items) || [];
  const nAll = rows.length;
  const nTodo = rows.filter((b) => b.status === "missing" || b.status === "stale").length;
  const label = codes === "all" ? `전체 ${nAll}개 번들`
    : codes === "missing" ? `미완성·재렌더 필요 ${nTodo}개 번들`
    : `${codes.length}개 번들 (${codes.slice(0, 3).join(", ")}${codes.length > 3 ? " …" : ""})`;
  const n = codes === "all" ? nAll : codes === "missing" ? nTodo : codes.length;
  if (!n) { toast("렌더할 번들이 없습니다.", "err"); return; }

  const ok = await confirmModal({
    title: "영상을 렌더할까요?",
    body: `<b>${escapeHtml(label)}</b><br><br>`
      + `번들당 약 5분 — <b>합쳐서 약 ${Math.round(n * 5 / 60 * 10) / 10}시간</b> 걸립니다. `
      + "동시에 하나만 실행되며 순차로 진행합니다.<br>"
      + "도구 #3 이 Chromium·TTS·ffmpeg 를 모두 씁니다 — 그 사이 이 PC 는 느려집니다.",
    ok: "렌더 시작", cancel: "취소",
  });
  if (!ok) return;

  try {
    const job = await api("/api/render/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codes, stop_on_error: true }),
    });
    V.sel.clear();
    fireJobChanged({ id: job.id });
    toast("렌더를 시작했습니다.");
    // ★ 목록(패널)에서 시작했으면 패널을 닫고 바탕의 진행·터미널로 내려간다.
    //   패널 안에서 폴링을 붙이면 안 된다 — 패널이 닫히는 순간 표면이 사라진다.
    if (location.hash.replace(/^#/, "") !== "/render/" + job.id) {
      location.hash = "#/render/" + job.id;
    } else {
      attachJob(job.id, job);
    }
  } catch (e) {
    if (e.status === 400) {
      confirmModal({ title: "렌더를 시작하지 않았습니다",
        body: `<pre class="pb-cmd">${escapeHtml(e.message)}</pre>`, ok: "닫기", cancel: "" });
    } else {
      toast("렌더를 시작하지 못했습니다: " + e.message, "err");
    }
  }
}

function attachJob(jobId, initial) {
  const card = $("#vd-run-card");
  if (!card) return;          // 이 화면에는 진행판이 없다(목록 패널). 조용히 넘긴다.
  card.hidden = false;
  renderJobActions(jobId);
  // 폴링 루프는 하나만. 콜백이 매 틱마다 id 로 DOM 을 다시 찾으므로,
  // 화면을 갈아탄 뒤에도 같은 루프가 새 마크업에 그린다.
  if (V.polling) return;
  V.polling = true;
  // 이미 끝난 잡을 열어본 것뿐이면 완료 토스트를 띄우지 않는다.
  const wasLive = !initial || initial.status === "running" || initial.status === "queued";
  pollJob(jobId, (job) => renderProgress(job))
    .then(async (final) => {
      V.polling = false;
      // ★ final 이 null 이면 폴링이 상한에 걸려 스스로 포기한 것이다. 잡이 아직 돌고
      //   있으면 다시 붙는다 — 안 그러면 화면이 그 시점에 얼어붙고, 서버는 정상인데
      //   사람은 렌더가 멈춘 줄 안다(실제로 7시간 렌더에서 그랬다).
      if (!final) {
        try {
          const j = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
          if (j.status === "running" || j.status === "queued") {
            attachJob(jobId, j);
            return;
          }
        } catch (e) { /* 못 물으면 아래로 떨어져 마무리한다 */ }
      }
      if (final && wasLive) {
        const bad = final.status === "error";
        toast(bad ? `렌더가 끝났습니다 — ${final.error || "오류"}` : "렌더를 모두 마쳤습니다.",
          bad ? "err" : "");
      }
      fireJobChanged({ id: jobId });
      await refresh();
    });
}

function renderJobActions(jobId) {
  const card = $("#vd-run-card");
  if (!card) return;
  let bar = $("#vd-job-acts");
  if (!bar) {
    bar = el("div", "vd-env");
    bar.id = "vd-job-acts";
    card.insertBefore(bar, $("#vd-prog"));
  }
  bar.innerHTML = "";
  bar.appendChild(miniBtn("취소", async () => {
    const ok = await confirmModal({
      title: "렌더를 취소할까요?",
      body: "진행 중인 번들의 작업이 버려집니다. 이미 만들어진 mp4 는 그대로 남습니다.",
      ok: "취소하기", cancel: "계속 진행", danger: true,
    });
    if (!ok) return;
    try {
      await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
      toast("취소를 요청했습니다.");
    } catch (e) { toast("취소 실패: " + e.message, "err"); }
  }));
  // ★ 별도 콘솔 창은 두지 않는다. 터미널이 여러 개면 어디를 봐야 하는지 헷갈린다.
  //   서버 창(run.bat)이 유일한 터미널이고, 이 화면은 같은 줄을 그대로 비춘다.
  const a = el("a", "btn sm", "전체 로그 내려받기");
  a.href = `/api/jobs/${encodeURIComponent(jobId)}/log`;
  bar.appendChild(a);
}

function renderProgress(job) {
  const box = $("#vd-prog");
  if (!box) return;           // 화면이 갈렸다 — 폴링은 계속 돌아도 그릴 곳이 없다
  box.innerHTML = "";
  // ★ done_count 는 "대기가 아닌 것" 이라 실패·건너뜀까지 센다. 그대로 쓰면
  //   전부 실패한 잡도 "24 / 24" 로 나와 완료처럼 읽힌다. 내역을 그대로 낸다.
  const st = Object.values(job.items || {});
  const n = (s) => st.filter((v) => v.status === s).length;
  const okN = n("done"), errN = n("error"), skipN = n("skipped");
  const leftN = Math.max(0, (job.total_count || st.length) - okN - errN - skipN);
  // ★ 살아 있다는 표시. chodangi 는 deck 캡처·TTS 구간에서 몇 분씩 한 줄도 안 뱉는다.
  //   로그만 보고 있으면 멈춘 것처럼 보이므로, 경과 시간을 1초마다 스스로 센다.
  startHeartbeat(job);

  const head = el("div", "muted");
  head.textContent = `완료 ${okN} / ${job.total_count}`
    + (errN ? ` · 실패 ${errN}` : "") + (skipN ? ` · 건너뜀 ${skipN}` : "")
    + (leftN ? ` · 남음 ${leftN}` : "")
    + (job.current ? ` · 진행 중 ${job.current}` : "")
    + ` · ${{ running: "실행 중", queued: "대기", done: "끝남", error: "중단됨" }[job.status]
           || job.status}`;
  box.appendChild(head);

  const ol = el("ol", "prog");
  (job.targets || []).forEach((code, i) => {
    const it = (job.items || {})[code] || {};
    const cls = it.status === "done" ? "on" : it.status === "running" ? "busy"
      : it.status === "error" ? "err" : "";
    const li = el("li", "prog-row " + cls);
    li.dataset.stage = code;
    const mark = el("span", "prog-mark");
    mark.appendChild(el("span", "prog-num", String(i + 1)));
    li.appendChild(mark);
    const txt = el("div", "prog-text");
    txt.appendChild(el("b", null, code));
    const sub = el("span");
    if (it.status === "running" && it.scene_total) sub.textContent = `씬 ${it.scene_done}/${it.scene_total}`;
    else if (it.status === "running" && it.tts_total)
      sub.textContent = `${it.stage || "음성·자막 합성"} — ${it.tts_done}/${it.tts_total}`;
    else if (it.status === "running") sub.textContent = it.stage || "시작하는 중…";
    else if (it.status === "done") sub.textContent = it.seconds ? `완료 · ${fmtSec(it.seconds)} 소요` : "완료";
    else if (it.status === "error") sub.textContent = it.error || "오류";
    else if (it.status === "skipped") sub.textContent = it.error || "건너뜀";
    else sub.textContent = "대기";
    txt.appendChild(sub);
    li.appendChild(txt);
    if (it.status === "running" && it.scene_total) {
      const bar = el("div", "prog-bar");
      bar.appendChild(stackedBar([
        { label: "완료", value: it.scene_done, seq: 4 },
        { label: "남음", value: Math.max(0, it.scene_total - it.scene_done), seq: 1 },
      ]));
      li.appendChild(bar);
    }
    ol.appendChild(li);
  });
  box.appendChild(ol);
}

/* 심장박동 — 로그가 조용해도 1초마다 움직인다.
 *
 * chodangi 는 deck 캡처(Chromium)와 TTS 구간에서 몇 분씩 아무것도 출력하지 않는다.
 * 그동안 화면이 굳어 보이면 사람은 죽은 줄 알고 창을 닫는다. 서버를 더 자주 찌르는
 * 대신(폴링은 2초 그대로) 브라우저가 스스로 경과 시간을 센다.
 */
function startHeartbeat(job) {
  const live = job.status === "running" || job.status === "queued";
  if (V.beat) { clearInterval(V.beat); V.beat = null; }

  const cur = (job.items || {})[job.current] || {};
  const stage = cur.stage || (live ? "시작하는 중…" : "");
  const t0 = Date.parse(job.started_at || "") || Date.now();

  const paint = () => {
    const box = $("#vd-heartbeat");
    if (!box) { clearInterval(V.beat); V.beat = null; return; }
    if (!live) {
      box.textContent = { done: "끝남", error: "중단됨" }[job.status] || job.status;
      ($("#vd-beatbar") || box).classList.remove("on");
      return;
    }
    ($("#vd-beatbar") || box).classList.add("on");
    const sec = Math.max(0, Math.round((Date.now() - t0) / 1000));
    const prog = cur.tts_total ? ` · 음성 ${cur.tts_done}/${cur.tts_total}`
      : cur.scene_total ? ` · 씬 ${cur.scene_done}/${cur.scene_total}` : "";
    box.textContent = `${job.current || "준비 중"} · ${stage}${prog}`
      + ` · 전체 ${fmtSec(sec)} 경과 · 자세한 로그는 서버 창(run.bat)에서`;
  };
  paint();
  if (live) V.beat = setInterval(paint, 1000);
}


/* ══════════ 패널: 사전점검 ══════════ */
async function mountPrecheck(root, ctx) {
  const code = ctx.args[0];
  root.innerHTML = '<div class="empty">점검 중…</div>';
  let d;
  try {
    d = await api(`/api/render/bundles/${encodeURIComponent(code)}/precheck`);
  } catch (e) {
    root.innerHTML = "";
    root.appendChild(el("div", "empty", "점검 실패: " + e.message));
    return;
  }
  root.innerHTML = "";

  const head = el("div", "vd-env");
  head.appendChild(el("span", "status-chip " + (d.ok ? "ok" : "bad"),
    d.ok ? "1:1 정상" : "1:1 깨짐"));
  head.appendChild(el("span", "status-chip", `deck 슬라이드 ${d.deck_slides}`));
  head.appendChild(el("span", "status-chip", `캡처 씬 ${d.capture_scenes}`));
  head.appendChild(el("span", "status-chip", `전체 씬 ${d.scene_total}`));
  root.appendChild(head);

  d.messages.forEach((m) => {
    const box = el("div", "qz-warn " + (m.level === "error" ? "err"
      : m.level === "warn" ? "warn" : "info"));
    box.appendChild(icon(m.level === "error" ? "alert" : "bulb", 15));
    box.appendChild(el("span", null, m.text));
    root.appendChild(box);
  });

  const card = el("div", "card");
  card.appendChild(el("div", "card-title", "deck 슬라이드 ↔ 캡처 씬"));
  const cmp = el("div", "vd-cmp");
  cmp.appendChild(el("div", "hd", "deck.html"));
  cmp.appendChild(el("div", "hd", "script JSON (capture:true)"));
  d.rows.forEach((r) => {
    const bad = !r.ok;
    const a = el("div", "row" + (bad ? " bad" : ""));
    a.appendChild(el("span", "muted", String(r.i + 1)));
    a.appendChild(el("span", null, r.deck ?? "(없음)"));
    const b = el("div", "row" + (bad ? " bad" : ""));
    b.appendChild(el("span", "muted", r.scene_no != null ? String(r.scene_no) : "—"));
    b.appendChild(el("span", null, r.scene ?? "(없음)"));
    cmp.appendChild(a);
    cmp.appendChild(b);
  });
  card.appendChild(cmp);
  root.appendChild(card);
}

/* ══════════ 패널: 잡 로그 ══════════ */
async function mountJobPanel(root, ctx) {
  const jobId = ctx.args[0];
  root.innerHTML = "";

  /* ★ 살아 있다는 표시가 필요하다. 전에는 한 번 받아 그리고 끝이라, 판독처럼 장당
     40~60초씩 가는 잡은 **F5 를 눌러야** 새 줄이 보였다 — 사람은 멈춘 줄 안다
     (2026-08-18: "전자시계라도 넣어주세요").
     그래서 셋을 둔다: 경과 시계(1초) · 진행 카운터 · 로그 이어붙이기(폴링). */
  const head = el("div", "vd-env");
  const badge = el("span", "status-chip", "불러오는 중…");
  const clock = el("span", "status-chip info", "0:00");
  const prog = el("span", "status-chip", "");
  head.append(badge, clock, prog);
  root.appendChild(head);

  const pre = el("pre", "log-pane");
  pre.style.maxHeight = "60vh";
  root.appendChild(pre);
  const a = el("a", "btn sm", "전체 로그 내려받기");
  a.href = `/api/jobs/${encodeURIComponent(jobId)}/log`;
  root.appendChild(a);

  const t0 = Date.now();
  let live = true;
  const tick = () => {
    if (!live || !clock.isConnected) return;
    const v = Math.floor((Date.now() - t0) / 1000);
    clock.textContent = `${Math.floor(v / 60)}:${String(v % 60).padStart(2, "0")}`;
  };
  const iv = setInterval(tick, 1000);
  tick();

  const drawHead = (job) => {
    badge.textContent = `${job.label || job.kind || "작업"} · ${STATUS_KO[job.status] || job.status}`;
    badge.className = "status-chip " + (STATUS_TONE[job.status] || "");
    const done = job.done_count || 0, tot = job.total_count || 0;
    prog.textContent = tot ? `${done} / ${tot}` + (job.current ? ` · ${job.current}` : "") : "";
    if (job.status !== "running" && job.status !== "queued") {
      live = false;
      clearInterval(iv);
    }
  };
  const drawLogs = (job) => {
    // ★ 커서(log_from)는 pollJob 이 관리한다 — **받은 줄만** 이어붙인다.
    (job.log?.lines || []).forEach((l) => pre.appendChild(el("span", null, l + "\n")));
    pre.scrollTop = pre.scrollHeight;
  };

  try {
    const first = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
    drawHead(first);
    const alive = first.status === "running" || first.status === "queued";
    if (alive) {
      // ★ 여기서 로그를 그리지 않는다. pollJob 이 커서 0 부터 다시 받아 첫 틱에 같은
      //   줄을 또 붙인다(같은 사고가 mountRun 에서 이미 있었다 — 그 주석 참조).
      pollJob(jobId, (j) => { drawHead(j); drawLogs(j); }).then((f) => {
        live = false;
        clearInterval(iv);
        if (f) drawHead(f);
      });
    } else {
      drawLogs(first);          // 끝난 잡은 폴링이 없으니 여기서 한 번 그린다
    }
  } catch (e) {
    live = false;
    clearInterval(iv);
    pre.textContent = "로그를 불러오지 못했습니다: " + e.message;
  }
}
