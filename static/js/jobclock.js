/* 잡 초시계 — 2부 화면(구조화 · 강의 노트 단계)의 경과 · 진행 · 남은 시간
 *
 * ★ 1초마다 흐른다. 폴링(2초)에 묶으면 숫자가 튀고, 몇 분씩 안 바뀌는 화면은
 *   "멈췄나" 로 읽힌다(summary.js 초시계와 같은 이유).
 * ★ 시작 시각은 서버의 `started_at` — 화면을 다시 열어도 0 으로 돌아가지 않는다.
 * ★ host 는 상자 또는 상자를 돌려주는 함수 — 다시 그리는 화면은 함수로 넘긴다.
 * ★ 진행은 잡 항목(과목)이 둘 이상이면 그것으로, 하나뿐이면 로그의 `[i/n]` 으로 센다.
 * ★ 남은 시간은 이번 잡 실측으로 낸다. 아직 끝난 것이 없으면 `hintSec`(이전 실측)
 *   을 "보통 약 N" 으로만 보여 준다 — 지어낸 숫자를 남은 시간이라고 하지 않는다.
 */
"use strict";

import { fmtSec } from "./util.js";

const STEP = /\[(\d+)\/(\d+)\]/;

export function jobClock(host, { unit = "개", hintSec = 0 } = {}) {
  const st = { job: null, lines: [], t0: 0, lastDone: -1, doneAt: 0, timer: null };

  function progress() {
    const j = st.job || {};
    if ((j.total_count || 0) > 1) return [j.done_count || 0, j.total_count];
    for (let i = st.lines.length - 1; i >= 0; i--) {
      const m = STEP.exec(st.lines[i]);
      if (m) return [+m[1], +m[2]];
    }
    return [0, 0];
  }

  function draw() {
    const j = st.job;
    if (!j) return;
    // 화면이 다시 그려지면(단계 클릭 등) 상자가 새로 생긴다 — 매번 새로 찾는다.
    const box = typeof host === "function" ? host() : host;
    const running = ["running", "queued"].includes(j.status);
    const end = running ? Date.now() : (Date.parse(j.finished_at || "") || Date.now());
    const el = Math.max(0, (end - st.t0) / 1000);
    const [done, total] = progress();
    if (done !== st.lastDone) { st.lastDone = done; st.doneAt = el; }

    let eta = "";
    if (!running) eta = "—";
    else if (done > 0 && total > done) {
      const per = st.doneAt / done;
      const left = per * total - el;
      eta = left > 5 ? `약 <b>${fmtSec(left)}</b> 남음 <span class="dim">(${unit}당 ${fmtSec(per)} 실측)</span>`
        : "곧 끝납니다";
    } else if (hintSec && total) {
      eta = `<span class="dim">보통 약 ${fmtSec(hintSec * total)} (${unit}당 ${fmtSec(hintSec)} · 이전 실측)</span>`;
    } else {
      eta = `<span class="dim">첫 ${unit}이 끝나면 계산합니다</span>`;
    }
    if (!running) stop();
    if (!box || !box.isConnected) return;
    const pct = total ? Math.round((done / total) * 100) : 0;
    const big = "font-size:20px;font-variant-numeric:tabular-nums";
    box.innerHTML = `<div class="row" style="gap:18px;align-items:baseline;flex-wrap:wrap">
        <div><span class="dim small">경과</span> <b style="${big}">${fmtSec(el)}</b></div>
        ${total ? `<div><span class="dim small">진행</span> <b style="font-size:20px">${done}/${total}</b>
          <span class="dim">(${pct}%)</span></div>` : ""}
        <div><span class="dim small">남은 시간</span> ${eta}</div>
      </div>
      ${total ? `<div class="bar" style="margin:8px 0 4px"><span style="width:${pct}%"></span></div>` : ""}`;
  }

  function stop() {
    if (st.timer) { clearInterval(st.timer); st.timer = null; }
  }

  return {
    update(job, lines) {
      st.job = job;
      st.lines = lines || [];
      if (!st.t0) st.t0 = Date.parse(job.started_at || "") || Date.now();
      if (!st.timer && ["running", "queued"].includes(job.status)) st.timer = setInterval(draw, 1000);
      draw();
    },
    stop,
  };
}
