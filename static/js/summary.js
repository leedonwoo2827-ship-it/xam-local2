/* 화면 ④ 요약노트 검수 — 좌 .md 편집 / 우 즉시 미리보기, 패널에 발행될 .html
 *
 * 미리보기가 둘인 것은 의도다.
 *   왼쪽 renderMarkdown : **지금 타이핑하는 것**
 *   패널 iframe        : **실제로 발행될 산출물(.html)**
 * 우리는 .md 만 고치므로 그 둘은 갈라진다. 그 사실을 배너로 못박는다.
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, renderMarkdown, fmtBytes, fmtSec } from "./util.js";
import { icon, hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";
import { pollJob, fireJobChanged } from "./store.js";

const S = { list: null, key: null, rec: null, dirty: false, th: null, job: null };

export const meta = {
  // ★ 사이드바 라벨과 같아야 한다. 레일은 "이론 요약 노트 제작" 인데 화면 제목이
  //   "요약노트 검수" 면 같은 곳인지 사람이 확신하지 못한다.
  title: (ctx) => (ctx.panel ? `발행될 HTML · ${ctx.args[0]}` : "이론 요약 노트 제작"),
  subtitle: (ctx) => (ctx.panel
    ? "이 파일이 실제로 사이트에 올라갑니다. 왼쪽 .md 편집과는 별개입니다."
    : "우리 모의고사 해설을 모아 과목별로 만듭니다. 발행되는 것은 .html 입니다."),
  actions: (ctx) => (ctx.panel ? [] : [
    // ★ 이론을 앱 안에서 만든다. 이 화면이 03/ 을 다루는 곳이므로 여기에 둔다 —
    //   화면을 새로 만들면 "요약노트가 두 군데" 가 되고, 사람이 어디서 고치는지 잃는다.
    actionBtn("이론 집필", () => startTheory(), { iconName: "bulb" }),
    // ★ 화면마다 보는 폴더가 다르다(01·02·03·05·06). 어느 자리인지 눌러서 바로
    //   확인할 수 있어야 한다 — 여는 것만이 아니라 **그 파일을 골라 놓고** 연다.
    actionBtn("폴더 열기", () => openFolder(), { iconName: "folder" }),
    actionBtn("발행될 HTML 보기", () => {
      if (S.key) location.hash = "#/preview/" + encodeURIComponent(S.key);
    }, { iconName: "external" }),
    actionBtn("저장", () => save(), { primary: true, iconName: "check" }),
  ]),
};

export async function mount(root, ctx) {
  if (ctx.panel) return mountPanel(root, ctx);

  const page = el("div", "page");
  page.innerHTML = `
    <div class="quick-row" id="sm-tabs"></div>
    <div id="sm-theory"></div>
    <div id="sm-drift"></div>
    <div class="sm-split">
      <div>
        <div class="qz-label" id="sm-label">03/summary_* — 편집</div>
        <textarea class="md-edit" id="sm-md"></textarea>
        <div class="qz-foot">
          <button class="btn primary" id="sm-save" type="button">저장 (Ctrl+S)</button>
          <button class="btn" id="sm-revert" type="button">되돌리기</button>
          <span class="field-hint qz-foot-hint" id="sm-hint"></span>
        </div>
      </div>
      <div>
        <div class="qz-label">지금 타이핑하는 내용의 미리보기</div>
        <div class="card preview" id="sm-prev"></div>
      </div>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  try {
    S.list = await api("/api/summary");
  } catch (e) {
    root.innerHTML = "";
    root.appendChild(el("div", "empty", "요약노트를 불러오지 못했습니다: " + e.message));
    return;
  }
  renderTabs();
  // ★ 이론 상태는 실패해도 화면을 죽이지 않는다. 이 계층이 미탑재일 수 있다
  //   (claude-agent-sdk 가 없으면 라우트가 안 붙는다 — app.py 머리말).
  loadTheory();
  $("#sm-save").addEventListener("click", () => save());
  $("#sm-revert").addEventListener("click", () => {
    if (!S.rec) return;
    $("#sm-md").value = S.rec.md;
    S.dirty = false;
    updateHint();
    renderPreview();
  });
  const ta = $("#sm-md");
  ta.addEventListener("input", () => { S.dirty = true; updateHint(); renderPreview(); });
  document.addEventListener("keydown", onKey);

  // ★ **있는 파일**을 고른다. 예전에는 `.md` 만 찾다가 없으면 items[0] 로 떨어졌는데,
  //   03/ 이 비면 그 items[0] 이 폴백 한글 키(`분석기획`)여서 열기가 404 로 죽고
  //   화면에 빨간 토스트만 남았다. 없으면 아예 열지 않는다 — 그때는 위 배너가
  //   [이론 집필] 을 누르라고 말한다.
  const exists = S.list.items.filter((i) => i.html_exists || i.md_exists);
  const first = ctx.args[0] || (exists[0] || {}).key;
  if (first) await open(first);
}

function renderTabs() {
  const box = $("#sm-tabs");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  S.list.items.forEach((it) => {
    // ★ 파일 키(`sql-1`)가 아니라 사람이 읽는 이름을 띄운다. 과목이 여러 편으로
    //   나뉘면 키만 보고는 어느 편인지 모른다(2026-08-20).
    const b = el("button", "chip" + (S.key === it.key ? " on" : ""),
                 it.label || it.key);
    b.type = "button";
    b.title = `${it.key} · ${it.md_path} · ${fmtBytes(it.md_bytes)}`;
    // ★ .md 가 없어도 막지 않는다 — .html 을 직접 고친다(그게 발행되는 파일이다).
    //   예전에는 여기서 disabled 라서, #2 가 .html 만 만든 회차는 요약노트를 아예
    //   고칠 수 없었다.
    if (!it.md_exists && !it.html_exists) {
      b.disabled = true; b.title = "03/ 에 이 과목 파일이 없습니다.";
    } else if (!it.md_exists) {
      b.title = ".md 가 없어 .html 을 직접 고칩니다 (발행되는 파일입니다).";
    }
    b.addEventListener("click", () => open(it.key));
    box.appendChild(b);
  });
  if (S.list.index_url) {
    const a = el("a", "chip", "색인 HTML");
    a.href = S.list.index_url;
    a.target = "_blank";
    a.rel = "noopener";
    box.appendChild(a);
  }
}

/* ══ 이론 집필 ══════════════════════════════════════════════════════════════
 * 03/ 이 **비어 있어도** 이 화면은 열려야 한다 — 그때 여기서 만드는 것이 목적이다.
 *
 * ★ 03/ 이 비면 `paths.summary_keys()` 가 한글 폴백 키를 돌려준다
 *   (`constants.py` 가 "이 책에서는 틀린 값" 이라고 적어 뒀다). 그래서 탭이
 *   `분석기획`·`탐색`… 으로 보이고 전부 비활성이다. 이론을 만들면 폴더에서 실제 키
 *   (`planning`·`explore`…)를 읽어 저절로 맞는다. 그 사실을 아래 배너가 말한다.
 */
async function loadTheory() {
  try {
    S.th = await api("/api/theory/status");
  } catch (e) {
    // 이 계층은 미탑재일 수 있다(claude-agent-sdk 없음). 화면을 죽이지 않는다.
    S.th = { unavailable: e.message };
  }
  renderTheory();
  // ★ 화면을 다시 열었을 때 이미 돌고 있으면 그것에 붙는다. 안 붙으면 진행 중인
  //   작업이 화면에서 사라져 "멈춘 것" 으로 보인다(렌더에서 이미 겪은 것이다).
  if (S.th && S.th.running_job && !S.job) attach(S.th.running_job);
}

/* ── 초시계 ─────────────────────────────────────────────────────────────────
 * ★ 폴링(2초)에 묶으면 시간이 2초씩 튄다. 매끄럽게 흐르지 않으면 "멈췄나" 로
 *   읽힌다 — 과목 하나가 10분씩 가는 화면에서 그게 정확히 피하려는 것이다.
 *   `authoring.js` 가 같은 이유로 같은 구조를 쓴다(그쪽 머리말 참조).
 * ★ 시작 시각은 **서버의 `started_at`** 을 쓴다. 화면을 다시 열었을 때 0 으로
 *   돌아가면 안 된다 — 이미 20분 돌아간 잡이 방금 시작한 것처럼 보인다.
 * ★ 남은 시간은 **실측된 것으로만** 낸다. 끝난 과목이 없으면 숫자를 지어내지 않고
 *   그렇다고 말한다 — 틀린 ETA 는 없는 것보다 나쁘다.
 */
let TICK = null, JOB0 = 0, ITEM0 = 0, ITEMKEY = "", LASTJOB = null;

/* ★ 버튼을 매 초 다시 만들지 않는다 — `innerHTML` 을 갈아치우면 리스너가 날아가서,
   1초마다 다시 걸어야 한다. 그래서 위임(delegation)으로 한 번만 건다. */
let CANCEL_BOUND = false;

function bindCancel(job) {
  if (CANCEL_BOUND) return;
  CANCEL_BOUND = true;
  document.addEventListener("click", async (e) => {
    const b = e.target.closest && e.target.closest("#sm-th-cancel");
    if (!b) return;
    const j = LASTJOB;
    if (!j || !j.id) return;
    b.disabled = true;
    await api(`/api/jobs/${j.id}/cancel`, { method: "POST" }).catch(() => {});
    toast("일시정지했습니다 — 끝난 편은 남습니다.", "");
  });
}

function startTick() {
  stopTick();
  TICK = setInterval(() => {
    const box = $("#sm-th-clock");
    // 화면을 떠났으면 스스로 멈춘다 — 안 하면 타이머가 세션 끝까지 남는다.
    if (!box) { stopTick(); return; }
    box.innerHTML = clockHtml(LASTJOB);
  }, 1000);
}

function stopTick() {
  if (TICK) { clearInterval(TICK); TICK = null; }
}

/* ★ 집필 화면(`authoring.js` 의 `drawJob`)과 **같은 모양**으로 낸다.
   편 하나가 10~15분이라 화면이 오래 안 바뀐다 — 숫자가 작으면 멈춘 것으로 보인다.
   경과·진행을 20px 로 키우고 `tabular-nums` 로 자릿수를 고정한다(2026-08-20 지시). */
/* 편 키(`sql-1`) 대신 읽는 이름(`2과목 1편`). 키만 보고는 어느 편인지 모른다. */
function curLabel(job) {
  const it = ((S.th && S.th.items) || []).find((i) => i.key === job.current);
  return (it && it.label) || job.current || "";
}

function clockHtml(job) {
  if (!job) return "";
  const done = Object.values(job.items || {}).filter((v) => v.status === "done");
  const secs = done.map((v) => v.seconds || 0).filter((s) => s > 0);
  const total = job.total_count || (S.th && (S.th.items || []).length) || 1;
  const pct = total ? Math.round((done.length / total) * 100) : 0;

  let eta = `<span class="dim">첫 편이 끝나면 남은 시간을 계산합니다</span>`;
  if (secs.length && done.length < total) {
    const per = secs.reduce((a, b) => a + b, 0) / secs.length;
    eta = `약 <b>${fmtSec(per * (total - done.length))}</b> 남음`
      + ` <span class="dim">(이번 잡 실측 · 편당 ${fmtSec(per)})</span>`;
  } else if (secs.length) {
    eta = `<span class="dim">—</span>`;
  }

  const big = "font-size:20px;font-variant-numeric:tabular-nums";
  return `<div class="row" style="gap:18px;align-items:baseline;flex-wrap:wrap">
      <div><span class="dim small">경과</span>
        <b style="${big}">${fmtSec((Date.now() - JOB0) / 1000)}</b></div>
      <div><span class="dim small">진행</span>
        <b style="font-size:20px">${done.length}/${total}</b>
        <span class="dim">(${pct}%)</span></div>
      <div><span class="dim small">남은 시간</span> ${eta}</div>
    </div>
    <div class="bar" style="margin:10px 0"><span style="width:${pct}%"></span></div>
    ${job.current ? `<div class="kvs"><div class="kv">
      <span class="k">지금</span><span class="v"><b>${escapeHtml(curLabel(job))}</b>
      ${ITEM0 ? ` · <span style="font-variant-numeric:tabular-nums">`
        + `${fmtSec((Date.now() - ITEM0) / 1000)}</span> 경과` : ""}</span>
    </div></div>` : ""}
    ${["running", "queued"].includes(job.status) ? `<div class="row" style="margin-top:10px">
      ${job.cancel_requested
        ? `<b class="warn">⏸ 정지 요청됨</b>
           <span class="dim">지금 편(<b>${escapeHtml(curLabel(job))}</b>)이 끝나면 멈춥니다.
             편 하나가 10~15분이라 <b>바로 멈추지 않습니다</b> — 중간에 끊으면 그 편이
             통째로 날아가기 때문입니다. 지금 끄고 싶으면 서버 창을 닫으십시오
             (그 편만 잃고 끝난 편은 남습니다).</span>`
        : `<button class="btn pause" id="sm-th-cancel" type="button">⏸ 일시정지</button>
           <span class="dim">돌고 있는 편은 끝까지 갑니다 — 그 뒤만 멈춥니다.
             <b>끝난 편은 파일로 남습니다</b>. 다시 [이론 집필] 을 누르면 남은 편만
             고르면 됩니다.</span>`}
    </div>` : ""}`;
}

function renderTheory(job) {
  const box = $("#sm-theory");
  if (!box || !S.th) return;
  box.innerHTML = "";
  if (S.th.unavailable) return;

  // ★ 초시계 기준점. 과목이 바뀌면 그 과목 시계를 다시 잡는다.
  if (job) {
    LASTJOB = job;
    if (!JOB0) {
      const t = job.started_at ? Date.parse(job.started_at) : NaN;
      const gap = Date.now() - t;
      // 시계가 어긋난 PC 에서 음수·엉뚱한 값이 나오는 것을 막는다.
      JOB0 = (Number.isFinite(t) && gap >= -60e3 && gap < 24 * 3600e3) ? t : Date.now();
    }
    if (job.current && job.current !== ITEMKEY) { ITEMKEY = job.current; ITEM0 = Date.now(); }
  } else {
    stopTick();
    JOB0 = 0; ITEM0 = 0; ITEMKEY = ""; LASTJOB = null;
  }

  const have = (S.th.items || []).filter((i) => i.exists).length;
  const rounds = (S.th.rounds || []).length;
  const line = el("div", "qz-warn " + (job ? "info" : (have ? "info" : "warn")));
  line.appendChild(icon(job ? "clock" : (have ? "bulb" : "alert"), 15));

  let txt;
  if (job) {
    const done = Object.values(job.items || {}).filter((v) => v.status === "done").length;
    // ★ 단위는 「과목」 이 아니라 **편**이다. 상수 4 도 뺀다(품목마다 다르다).
    const _t = job.total_count || (S.th.items || []).length || 1;
    const _cur = (S.th.items || []).find((i) => i.key === job.current);
    txt = `이론 집필 중 — ${done}/${_t}편`
      + (job.current ? ` · 지금 ${_cur ? _cur.label : job.current}` : "");
  } else if (have === 0) {
    txt = `03/ 에 요약노트가 없습니다. 소스 ${rounds}회차로 `
      + `${(S.th.items || []).length}편을 만들 수 있습니다.`
      + ` 위 [이론 집필] 을 누르십시오. (지금 보이는 탭 이름은 폴백값입니다 —`
      + ` 만들면 실제 파일명으로 바뀝니다.)`;
  } else {
    // ★ "무엇을 눌러야 하나" 를 말한다. 4/4 가 있다는 사실만 알려 주면 사람이
    //   빈 편집기를 보고 멈춘다 — 실제로 그렇게 됐다(2026-08-12).
    txt = `03/ 에 ${have}/4 과목이 있습니다 · 소스 ${rounds}회차`
      + `  —  위 탭(${(S.th.items || []).filter((i) => i.exists).map((i) => i.label || i.key).join(" · ")})`
      + `을 눌러 본문을 열고, [발행될 HTML 보기] 로 실제 모양을 확인하십시오.`;
  }
  if (!job && !S.th.rounds_ready) {
    txt += `  ★ 규약은 m01~m${String(S.th.rounds_expected).padStart(2, "0")} 전체 병합입니다`
      + ` — 지금은 ${rounds}회차뿐입니다.`;
  }
  line.appendChild(el("span", null, txt));
  box.appendChild(line);

  // ★ 집필 중에는 아래 편집기를 숨긴다. 그때 편집기는 **아무것도 아니다** —
  //   파일이 아직 없거나 곧 덮어써지므로, 열어 둘 이유가 없고 사람이 거기서
  //   무엇을 해야 하나 헷갈린다(2026-08-12 지시: "생성때는 밑에 이거 안나오거나").
  const split = $(".sm-split");
  if (split) split.hidden = !!job;

  // ★ 진행 바는 `clockHtml` 안에 있다 — 여기서 또 만들면 바가 둘이 된다.
  //   `field-hint` 클래스도 빼야 한다. 그 클래스가 글씨를 작게 하니 20px 이 죽는다.
  if (job) {
    const clock = el("div");
    clock.id = "sm-th-clock";
    clock.innerHTML = clockHtml(job);
    box.appendChild(clock);
    bindCancel(job);
    startTick();
  }

  // 마지막 로그 몇 줄. 과목 하나가 10분씩 가는데 화면이 안 바뀌면 멈춘 것으로 보인다.
  if (job && job.log && job.log.lines && job.log.lines.length) {
    const pre = el("pre", "job-log");
    pre.textContent = job.log.lines.slice(-8).join("\n");
    box.appendChild(pre);
  }
}

async function startTheory() {
  if (!S.th || S.th.unavailable) {
    toast("이론 집필 계층이 없습니다: " + ((S.th && S.th.unavailable) || "상태 미확인"), "err");
    return;
  }
  if (S.job) { toast("이미 돌고 있습니다."); return; }

  const have = (S.th.items || []).filter((i) => i.exists);
  const rounds = (S.th.rounds || []).length;
  // ★ 과목 수는 **시험정보에서** 온다(서버가 `items` 로 준다). `|| 4` 로 떨어지면
  //   SQLD(2과목)인데 확인창이 「4과목을 집필할까요?」 라고 묻는다(2026-08-20 실측).
  const all = (S.th.items || []).length;
  // ★ 다 있으면 **다시 만들 것인지** 를 묻는다. 예전에는 그대로 POST 해서 서버가
  //   "모두 이미 있습니다" 로 400 을 냈다 — 사람은 버튼이 고장난 줄 안다.
  const redo = have.length >= all;
  const notes = [];
  // ★ 과목을 **고를 수 있게** 한다. 서버는 `keys` 를 받는데 화면이 안 보내서
  //   늘 전 과목이 돌았다. SQLD 2과목은 크기가 크게 다르다 — 1과목 200문항 ·
  //   2과목 800문항이라, 큰 쪽을 돌리기 전에 작은 쪽으로 확인해야 한다(2026-08-20).
  notes.push('<b>돌릴 편</b>을 고르십시오 — 편 하나가 호출 하나이고 영상 하나입니다.'
    + (S.th.items || []).map((i) => `<div style="margin:4px 0 0 6px">`
        + `<label><input type="checkbox" class="th-pick" value="${escapeHtml(i.key)}" checked> `
        + `<b>${escapeHtml(i.label || i.key)}</b>`
        + `<span class="dim"> · ${escapeHtml(i.range_label || "")}`
        + ` — ${escapeHtml(i.key)}.html</span>`
        + (i.exists ? ` <span class="warn">이미 있음 · 덮어씁니다</span>` : "")
        + `</label></div>`).join(""));
  notes.push(`소스 <b>${rounds}회차</b>의 해설에서 시험 키워드를 뽑아 과목별 요약 이론을`
    + ` 만듭니다.`);
  if (redo) {
    notes.push(`★ ${all}편이 <b>이미 있습니다.</b> 계속하면 <b>전부 다시 만들어 덮어씁니다</b>`
      + ` (기존 파일은 <code>.bak</code> 으로 남습니다).`);
  }
  if (!S.th.rounds_ready) {
    notes.push(`★ 규약은 m01~m${String(S.th.rounds_expected).padStart(2, "0")} 전체 병합입니다.`
      + ` 지금은 ${rounds}회차뿐이라 남은 회차를 집필한 뒤 다시 만들어야 합니다.`);
  }
  if (have.length) {
    notes.push(`이미 있는 ${have.length}편(${have.map((i) => i.label || i.key).join(" · ")})은`
      + ` <b>건너뜁니다.</b> 다시 만들려면 그 파일을 지우고 누르십시오.`);
  }
  if (S.th.authoring_running) {
    notes.push("★ 문항 집필이 돌고 있습니다 — 서버가 거절합니다. 끝난 뒤 누르십시오.");
  }
  notes.push("편당 10~15분쯤 걸립니다. 구독 한도를 씁니다.");

  if (!(await confirmModal({
    title: `이론 ${all}편을 집필할까요?`,
    body: notes.map((t) => `<p>${t}</p>`).join(""),
    ok: "집필 시작", cancel: "취소",
  }))) return;

  // ★ 모달이 닫히기 **전에** 읽어야 한다 — 닫히면 그 마크업이 사라진다.
  //   `confirmModal` 이 true 를 돌려준 직후가 그 자리다(모달 DOM 은 아직 있다).
  const picked = [...document.querySelectorAll(".th-pick")]
    .filter((c) => c.checked).map((c) => c.value);
  if (!picked.length) { toast("돌릴 과목을 고르십시오.", "err"); return; }

  let r;
  try {
    r = await api("/api/theory/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: picked }),
    });
  } catch (e) {
    toast("시작하지 못했습니다: " + e.message, "err");
    return;
  }
  toast(`이론 집필 시작 — ${r.keys.join(" · ")} (모델 ${r.model || "기본"})`);
  attach(r.job);
}

async function attach(id) {
  S.job = id;
  const done = await pollJob(id, (job) => renderTheory(job));
  S.job = null;
  // ★ 끝나면 목록을 다시 읽는다. 03/ 이 생겼으면 `summary_keys()` 가 폴백 한글 키에서
  //   실제 키로 바뀌므로, 다시 안 읽으면 탭이 계속 비활성으로 남는다.
  let first = null;
  try {
    S.list = await api("/api/summary");
    renderTabs();
    first = (S.list.items.find((i) => i.html_exists || i.md_exists) || {}).key || null;
  } catch (e) { /* 탭 갱신 실패가 결과 표시를 막지 않는다 */ }
  await loadTheory();
  // ★ 첫 과목을 **열어 준다.** 안 열면 탭만 생기고 편집기가 빈 채로 남아
  //   "뭘 눌러야 하나" 가 된다. `S.key` 도 비어 있어서 [발행될 HTML 보기] 까지
  //   아무 반응이 없다 — 둘 다 이것 하나로 풀린다.
  if (first && !S.dirty) {
    try { await open(first); } catch (e) { /* 열기 실패가 결과 토스트를 막지 않는다 */ }
  }
  fireJobChanged({ kind: "theory", id });
  if (!done) { toast("폴링이 끝났습니다 — 화면을 새로 여시면 다시 붙습니다."); return; }
  const ok = Object.values(done.items || {}).filter((v) => v.status === "done").length;
  // ★ 성공에 kind 를 주지 않는다 — CSS 에 `.toast.ok` 가 없다(`.toast.err` 만 있다).
  if (done.status === "done" && ok) {
    toast(`이론 ${ok}과목을 만들었습니다. 탭에서 확인하십시오.`);
  } else {
    toast(`이론 집필이 끝났습니다 — 합격 ${ok}과목. 로그를 확인하십시오.`, "err");
  }
}

async function open(key) {
  if (S.dirty && !(await confirmModal({
    title: "저장하지 않은 편집을 버릴까요?",
    body: `<b>${escapeHtml(S.key || "")}</b> 의 편집 내용이 사라집니다.`,
    ok: "버리고 이동", cancel: "머무르기", danger: true,
  }))) return;

  try {
    S.rec = await api("/api/summary/" + encodeURIComponent(key));
  } catch (e) {
    toast("불러오지 못했습니다: " + e.message, "err");
    return;
  }
  S.key = key;
  S.dirty = false;
  history.replaceState(null, "", "#/summary/" + encodeURIComponent(key));
  $("#sm-md").value = S.rec.md;
  renderTabs();
  renderDrift();
  renderPreview();
  renderWhere();
  updateHint();
}

function renderDrift() {
  const box = $("#sm-drift");
  // ★ 화면을 떠난 뒤 비동기 응답이 도착하면 box 가 null 이다.
  if (!box) return;
  box.innerHTML = "";
  const it = S.list.items.find((i) => i.key === S.key);
  if (!it) return;
  // .md 를 고치면 반드시 뜬다. 그게 정상이고, 그래서 문구로 설명한다.
  const warn = el("div", "qz-warn " + (S.rec.drift ? "warn" : "info"));
  warn.appendChild(icon(S.rec.drift ? "alert" : "bulb", 15));
  warn.appendChild(el("span", null, S.rec.drift
    ? S.list.drift_text
    : "발행되는 것은 .html 입니다. .md 를 고치면 도구 #1/#2 에서 HTML 을 다시 만들어야 "
      + "사이트에 반영됩니다."));
  box.appendChild(warn);
}

function renderPreview() {
  const box = $("#sm-prev");
  if (!box) return;
  box.innerHTML = renderMarkdown($("#sm-md").value);
}

function updateHint() {
  const h = $("#sm-hint");
  if (!h) return;
  const it = S.list.items.find((i) => i.key === S.key);
  h.textContent = (S.dirty ? "저장하지 않은 편집이 있습니다.  ·  " : "")
    + (it ? `${it.md_path} · ${fmtBytes(it.md_bytes)}` : "");
}

/* ══ 지금 어느 자리인가 ═════════════════════════════════════════════════════
 * ★ 이 앱은 화면마다 다른 폴더를 본다(01 판독 · 02 문항 · 03 요약노트 · 05 번들 ·
 *   06 발행). 편집기 위에 `03/summary_* — 편집` 같은 **상대경로**만 띄워 두면 책 폴더가
 *   여럿일 때(ocr-output-260730 · 260723) 어느 책인지 알 수 없다. 절대경로를 띄운다.
 */
function renderWhere() {
  const lab = $("#sm-label");
  if (!lab || !S.rec) return;
  lab.textContent = "";
  lab.appendChild(el("span", null,
    (S.rec.kind === "html" ? ".html 직접 편집" : ".md 편집") + " — "));
  const p = el("code", "sm-where", S.rec.abs_path || S.rec.edit_path || "");
  p.title = "누르면 탐색기에서 이 파일을 골라 놓고 엽니다.";
  p.addEventListener("click", () => openFolder());
  lab.appendChild(p);
}

/* 탐색기로 03/ 을 열고 지금 고치는 파일을 **선택**해 준다.
   폴더만 열면 03/ 에 파일이 8개라 다시 헷갈린다. */
async function openFolder() {
  try {
    // ★ body 는 **객체로** 넘긴다 — api() 가 JSON.stringify 와 Content-Type 을
    //   같이 붙인다(util.js:62-65). 문자열로 넘기면 raw 로 보고 헤더를 안 붙인다.
    const r = await api("/api/summary/open", {
      method: "POST",
      body: S.key ? { key: S.key } : {},
    });
    toast(r.selected ? `탐색기에서 열었습니다 — ${r.selected}` : `폴더를 열었습니다 — ${r.folder}`);
  } catch (e) {
    toast("폴더를 열지 못했습니다: " + e.message, "err");
  }
}

async function save() {
  if (!S.rec || !S.dirty) { toast("바뀐 내용이 없습니다."); return; }
  try {
    const r = await api("/api/summary/" + encodeURIComponent(S.key), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ md: $("#sm-md").value, etag: S.rec.etag }),
    });
    S.rec.md = $("#sm-md").value;
    S.rec.etag = r.etag;
    S.rec.drift = true;
    S.dirty = false;
    updateHint();
    renderDrift();
    toast(`저장했습니다 — ${r.written.join(" · ")}`);
    toast(r.warning);
    S.list = await api("/api/summary");
    renderTabs();
  } catch (e) {
    if (e.status === 409) {
      const again = await confirmModal({
        title: "저장하지 못했습니다",
        body: escapeHtml(e.message),
        ok: "최신 내용 다시 읽기", cancel: "머무르기",
      });
      if (again) { S.dirty = false; await open(S.key); }
    } else {
      toast("저장 실패: " + e.message, "err");
    }
  }
}

function onKey(e) {
  if (!location.hash.startsWith("#/summary")) return;
  if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); }
}

window.addEventListener("beforeunload", (e) => {
  if (S.dirty && location.hash.startsWith("#/summary")) { e.preventDefault(); e.returnValue = ""; }
});

/* ══ 패널: 발행될 HTML ════════════════════════════════ */
async function mountPanel(root, ctx) {
  const key = ctx.args[0];
  root.innerHTML = "";
  let url = null;
  try {
    const d = await api("/api/summary/" + encodeURIComponent(key));
    url = d.html_url;
  } catch (e) {
    root.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message));
    return;
  }
  const note = el("div", "field-hint");
  note.textContent = "03/summary_*.html — 이 파일이 06/theory/ 로 복사되어 사이트에 올라갑니다. "
    + "SVG 를 인라인으로 품고 있어 단독으로도 열립니다.";
  root.appendChild(note);
  const frame = el("iframe", "html-frame");
  frame.src = url;
  frame.loading = "lazy";
  root.appendChild(frame);
  const a = el("a", "btn sm", "새 창에서 열기");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  root.appendChild(a);
}
