/* 문항 집필 — 이 앱에서 유일하게 모델을 부르는 화면.
 *
 * 도구 #2(클로드 데스크탑)를 대신한다. **API 키가 없다** — 집필자 각자의 Claude Code
 * 구독 로그인으로 나가므로, 사용량과 한도가 사람별로 갈린다.
 *
 * 네 단계가 한 화면에서 끝난다:
 *   ① 집필(과목 단위) → ② 스테이징 확인 → ③ _rounds 반입 → ④ 02/·04/ 파생
 *
 * ★ 바탕(base) 화면이다. 파트 하나가 10분씩 가므로 패널에 두면 Esc·스크림 클릭에
 *   닫히고 돌던 잡의 진행을 놓친다.
 */
import { $, api, confirmModal, el, escapeHtml, toast } from "./util.js";
import { hydrateIcons } from "./icons.js";
// ★ `actionBtn` 은 `panel.js` 에 있다(`icons.js` 가 아니다 — 그렇게 잘못 넣어 화면이
//   통째로 안 떴다: "does not provide an export named 'actionBtn'").
import { actionBtn } from "./panel.js";
// ★ 잡 폴링을 손으로 만들지 않는다. `store.pollJob` 은 ① 일시적 통신 실패로 폴링을
//   끊지 않고 ② 그리기 예외로 화면이 얼지 않게 감싸 준다. 렌더·발행이 쓰는 것과
//   같은 것을 써야 로그 커서 규약도 갈리지 않는다.
import { fireJobChanged, pollJob } from "./store.js";

/* 서버가 준 문구만 보여 준다. `String(e)` 는 "Error: " 를 앞에 달아 한국어 문장을
 * 어색하게 만들고, 문구가 없으면 아무것도 안 남는다. */
const emsg = (e) => (e && e.message) || String(e || "요청에 실패했습니다.");

/* ★ 배수와 기준을 **기출 회차별로** 들고 있다. 전역 하나가 아니다 —
 *   SQLD 는 7회 OCR 중 여섯을 ×3, 마지막을 ×2 로 해서 20회차 × 50문항 = 1,000제를
 *   맞춘다(2026-08-10). 전역 배수로는 마지막 행만 다르게 할 수 없다. */
const MULT_BY_ROW = {};     // { "01": 3, … "07": 2 }
const MODE_BY_ROW = {};     // { "01": "exam" | "derive", … }
/* ★ 행 선택. 기본은 전부 켜짐 — 처음 열면 '모두 집필' 이 자연스럽다.
 *   끄는 이유가 실제로 있다: "1회→3회를 집필하는 경우도 있으니까"(2026-08-10) —
 *   기출 1회차만 먼저 돌려 보고 결과를 확인한 뒤 나머지를 돌린다. */
const PICK_BY_ROW = {};     // { "01": true, … }
let DEFAULT_MULT = 3;       // 처음 열었을 때 각 행의 값
let PLAN = null;            // /api/authoring/plan 응답
let EXAMS = [];             // /api/authoring/exams — 시험정보 목록
let EXAM = "";              // 고른 시험정보 id
/* ★ 시험정보를 고르고 [불러오기] 를 눌러야 아래가 뜬다.
 *   전에는 열자마자 아무거나(오류 없는 첫 번째) 골라 두고 회차 표를 그렸다.
 *   그래서 「시험정보 = SQL 개발자」인데 회차가 80문항(빅분기 크기)으로 뜨는
 *   화면이 만들어졌다 — 작업 폴더는 빅분기이고 시험정보만 SQLD 였던 것이다.
 *   그대로 [실행] 을 누르면 몇 시간과 수십 달러가 엉뚱한 규격으로 나간다.
 *   고르는 것과 불러오는 것을 사람의 손짓 두 번으로 갈라 둔다. */
let LOADED = false;         // [불러오기] 를 눌렀는가

const multOf = (r) => (r in MULT_BY_ROW ? MULT_BY_ROW[r] : DEFAULT_MULT);

/** 시험정보 목록을 받아 `EXAMS`·`EXAM` 을 채운다.
 *  돌려주는 값 = **작업 폴더에서 시험정보를 정했는가**. 그때만 계획을 자동으로
 *  그린다(`refresh`) — 사람이 다른 품목을 고르면 [불러오기] 를 요구한다. */
async function loadExams() {
  const r = await api("/api/authoring/exams").catch(() => ({ items: [] }));
  EXAMS = r.items || [];
  // ★ 기본 선택은 **작업 폴더의 품목**이다(서버가 `active` 로 준다).
  //   목록의 첫 번째를 고르면 폴더와 다른 품목이 조용히 잡힌다 — 그건 막아야 한다.
  //   반대로 늘 비워 두면 새로고침마다 다시 고르게 되고, 그 사이 화면이 규격을
  //   몰라 진행 칩이 엉뚱한 문항범위로 뜬다(2026-08-20 실측: `12회 41~60번`).
  //   폴더가 진실이므로 그것을 고른 것으로 본다. 표는 여전히 [불러오기] 뒤에 뜬다.
  let fromFolder = false;
  if (!EXAM && r.active && EXAMS.some((e) => e.id === r.active)) {
    EXAM = r.active;
    fromFolder = true;
  }
  return fromFolder;
}

/** 기출 회차 목록과 규격. 배수는 화면이 행별로 들고 있으므로 여기서는 목록만 받는다. */
async function loadPlan() {
  const spec = (PLAN && PLAN.rows ? PLAN.rows : []).map(
    (r) => `${r.pool_round}:${multOf(r.pool_round)}`).join(",");
  // ★ 고른 시험정보를 **서버에 넘긴다.** 안 넘기면 서버가 `exams/` 의 첫 번째로
  //   회차 크기·과목 수를 잡는다 — 화면이 SQLD 인데 계산은 빅분기로 갔다.
  PLAN = await api(`/api/authoring/plan?spec=${encodeURIComponent(spec)}`
    + `&exam=${encodeURIComponent(EXAM)}`)
    .catch((e) => ({ error: emsg(e), codes: [], rows: [], pool: {} }));
  // 처음 로드면 기본 배수를 각 행에 심는다
  for (const r of PLAN.rows || []) {
    if (!(r.pool_round in MULT_BY_ROW)) MULT_BY_ROW[r.pool_round] = DEFAULT_MULT;
    if (!(r.pool_round in MODE_BY_ROW)) MODE_BY_ROW[r.pool_round] = "exam";
    if (!(r.pool_round in PICK_BY_ROW)) PICK_BY_ROW[r.pool_round] = true;
  }
  return PLAN;
}

export const meta = {
  title: "문항 집필",
  subtitle: "Claude Code 구독으로 회차를 집필합니다 — API 키 없음, 각자 계정으로 나갑니다.",
  actions: () => [
    actionBtn("상태 새로고침", () => refresh(), { iconName: "refresh" }),
  ],
};

export async function mount(root, ctx) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card">
      <div class="card-title">연결</div>
      <div id="au-conn"><div class="empty">확인 중…</div></div>
    </div>
    <div class="card">
      <div class="card-title">① 집필 — 한 번의 호출이 한 과목 안에서 끝납니다</div>
      <div id="au-plan"><div class="empty">확인 중…</div></div>
    </div>
    <div class="card">
      <div class="card-title">② 진행</div>
      <div id="au-job"><div class="empty">돌고 있는 집필이 없습니다.</div></div>
    </div>
    <div class="card">
      <div class="card-title">③ 반입 · ④ 파생</div>
      <div id="au-next"><div class="empty">확인 중…</div></div>
    </div>
    <div class="card">
      <div class="card-title">시험정보 관리 — 매년·개정마다 여기서 고칩니다</div>
      <div id="au-exams"><div class="empty">확인 중…</div></div>
    </div>
  `;
  root.appendChild(page);
  hydrateIcons(page);
  await refresh();
}

/* ── 그리기 ───────────────────────────────────────────────────────────── */
async function refresh() {
  const st = await api("/api/authoring/status").catch((e) => ({ error: emsg(e) }));
  drawConn(st);
  const fromFolder = await loadExams();
  await loadPlan();
  // ★ 시험정보가 **작업 폴더에서 온 것**이면 계획도 바로 그린다.
  //
  //   [불러오기] 를 한 번 눌러야 하게 둔 이유는 「화면이 고른 것과 다른 품목으로
  //   조용히 계획이 잡히는 것」을 막기 위해서였다(SQLD 를 고르고 빅분기 회차가
  //   뜬 일이 있었다). 그런데 시험정보를 **폴더에서** 정하면 그 어긋남이 구조적으로
  //   생기지 않는다 — 폴더가 진실이다. 그래서 그때만 자동으로 그린다.
  //   사람이 콤보박스로 **다른** 품목을 고르면 여전히 [불러오기] 를 요구한다.
  if (fromFolder) LOADED = true;
  // ★ 화면을 새로 열어도 돌고 있는 잡에 다시 붙는다. 안 붙이면 20분짜리 집필이
  //   진행 중인데 화면은 "돌고 있는 집필이 없습니다" 라고 말한다.
  if (st && st.running_job) attach(st.running_job);
  await drawRound();
  await drawExams();
}

function drawConn(st) {
  const box = $("#au-conn");
  if (!box) return;
  if (st.error) { box.innerHTML = `<div class="empty">${escapeHtml(st.error)}</div>`; return; }

  const rows = [];
  rows.push(kv("CLI", st.installed
    ? `<code>${escapeHtml(shortPath(st.path))}</code>`
    : `<b class="bad">찾지 못했습니다</b> — Claude Code 를 설치·로그인하거나 ` +
      `<code>CLAUDE_CLI</code> 환경변수로 실행 파일 경로를 지정하십시오.`));
  rows.push(kv("로그인", st.credentials
    ? `있습니다 <span class="dim">(~/.claude/.credentials.json · 구독 OAuth)</span>`
    : `<b class="bad">없습니다</b> — Claude Code 에서 한 번 로그인하십시오.`));
  rows.push(kv("작업 폴더", `<code>${escapeHtml(st.book || "")}</code>`));
  // ★ 켜져 있으면 반드시 말해 준다. 앱은 자식 환경에서 빈 값으로 덮어 무력화하지만,
  //   "왜 내 계정에 안 찍히지" 를 물을 때 짚을 곳이 필요하다.
  if (st.api_key_env) {
    rows.push(kv("주의", `<b class="bad">ANTHROPIC_API_KEY 가 설정돼 있습니다.</b> ` +
      `앱은 이것을 무력화하고 구독 로그인으로 나가지만, 다른 도구는 이 키로 ` +
      `과금될 수 있습니다.`));
  }
  box.innerHTML = `<div class="kvs">${rows.join("")}</div>
    <div class="row" style="margin-top:12px">
      <button class="btn" id="au-ping" type="button">연결 시험 (약 $0.25)</button>
      <span class="dim">시험도 실제 호출입니다 — 호출당 최소 비용이 붙습니다.</span>
    </div>`;
  $("#au-ping").onclick = async (e) => {
    e.target.disabled = true; e.target.textContent = "부르는 중…";
    const r = await api("/api/authoring/ping", { method: "POST" }).catch((x) => ({ ok: 0, message: emsg(x) }));
    toast(r.message || (r.ok ? "연결됨" : "실패"), r.ok ? "ok" : "err");
    e.target.disabled = false; e.target.textContent = "연결 시험 (약 $0.25)";
  };
}

async function drawRound() {
  const plan = $("#au-plan"), next = $("#au-next");
  if (!plan) return;

  const P = PLAN || {};
  if (P.error || !(P.rows || []).length) {
    plan.innerHTML = `<div class="empty" style="text-align:left">
      <b>집필 계획을 불러올 수 없습니다.</b><br>
      <span class="dim">${escapeHtml(P.error || "기출(01/) 이 비어 있습니다.")}</span><br><br>
      파이썬 라우트를 새로 추가했으면 <b>run.bat 을 다시 띄워야</b> 합니다 —
      브라우저 <code>Ctrl+F5</code> 는 화면만 새로 고치고 서버는 그대로입니다.
    </div>`;
    if (next) next.innerHTML = `<div class="empty">계획이 잡히면 여기가 채워집니다.</div>`;
    return;
  }

  /* ★ 행은 **기출(OCR 검수) 회차**다. 요청한 형태 그대로:
   *
   *     OCR 검수 회차 1   × 3   [ ] 대표문제를 연습문제로
   *     ...
   *     OCR 검수 회차 7   × 2   [ ] 대표문제를 연습문제로
   *                                    총 20회차 · 1,000문항        [실행]
   *
   * ★ 배수가 **행별**이다. 전역 하나로는 안 된다 — SQLD 는 7회 OCR 중 여섯을 ×3,
   *   마지막을 ×2 로 해서 20회차 × 50문항 = 1,000제를 맞춘다(2026-08-10).
   * ★ 자사 회차 코드(m01…)는 보여주지 않는다. "m10은 뭐에요?" 를 물으셨고, 필요한
   *   정보는 총 몇 회차가 되는지뿐이다.
   * ★ 기준도 행별이다. 기본은 시험기준, 체크하면 그 회차만 대표문제 변형.
   */
  const opts = (sel) => [0, 1, 2, 3, 4, 5].map(
    (n) => `<option value="${n}"${n === sel ? " selected" : ""}>${n ? "× " + n : "안 함"}</option>`
  ).join("");

  const modeSel = (r) => (P.modes || []).map((m) =>
    `<option value="${m.id}"${MODE_BY_ROW[r] === m.id ? " selected" : ""}>${
      escapeHtml(m.label)}</option>`).join("");

  const rows = (P.rows || []).map((r, i) => {
    const m = multOf(r.pool_round);
    const on = PICK_BY_ROW[r.pool_round] !== false;
    return `<tr${on ? "" : ' style="opacity:.45"'}>
      <td style="white-space:nowrap">
        <input type="checkbox" class="au-pick" data-r="${escapeHtml(r.pool_round)}"
               ${on ? "checked" : ""}>
        <b>OCR 검수 회차 ${i + 1}</b> <span class="dim">${r.pool_items}문항</span></td>
      <td style="white-space:nowrap">
        <select class="au-mult" data-r="${escapeHtml(r.pool_round)}">${opts(m)}</select>
        <span class="dim">= ${m}회차</span></td>
      <td><select class="au-mode" data-r="${escapeHtml(r.pool_round)}"
            style="min-width:220px">${modeSel(r.pool_round)}</select></td>
    </tr>`;
  }).join("");

  // 총계는 **켜진 행만** 센다 — 끈 행을 세면 예상 비용이 거짓말을 한다.
  const nR = (P.rows || []).reduce(
    (a, r) => a + (PICK_BY_ROW[r.pool_round] !== false ? multOf(r.pool_round) : 0), 0);
  const perRound = P.round_size || null;      // 없으면 아래에서 화면이 막는다
  // ★ 서버가 준 **과목당 실측**을 여기서 켜진 회차 수에 곱한다. 예전에는 화면이
  //   `nR * 6.9` 로 자체 상수를 곱했고, 서버는 또 다른 상수를 썼다 — 두 값이 서로
  //   달랐고 실측이 나오자 둘 다 두 배쯤 틀린 것으로 드러났다(2026-08-10).
  const est = scaleEst(P.est, nR, partCount(P) || 0, perRound || 0);
  // ── 시험정보 콤보 + 관리 창 링크 ───────────────────────────────────────
  // ★ 시험은 매년·개정마다 바뀐다. 회차당 문항수·과목 구성이 여기서 온다 —
  //   빅분기 80문항 4과목, SQLD 50문항 2과목(10:40). 코드가 아니라 파일이다.
  const ex = (EXAMS || []).map((e) => {
    const bad = !e.ok ? " ✕" : (!e.confirmed ? " ⚠" : "");
    return `<option value="${escapeHtml(e.id)}"${e.id === EXAM ? " selected" : ""}>${
      escapeHtml(e.label)}${bad}</option>`;
  }).join("");
  const cur = (EXAMS || []).find((e) => e.id === EXAM);

  /* ★ 기출 회차 크기와 시험정보가 어긋나면 **말한다.**
   *   실측(2026-08-19 캡처): 시험정보는 SQL 개발자(50문항)인데 회차가 80문항으로
   *   떴다. 작업 폴더가 빅분기(`ocr-output-260730`)였던 것이다. 그대로 실행하면
   *   50문항 규격으로 80문항 기출을 증폭하는 일이 몇 시간 돈다. */
  const poolSize = (P.rows || [])[0]?.pool_items || 0;
  const sizeClash = cur && poolSize && cur.round_size
    && Number(cur.round_size) !== Number(poolSize);

  plan.innerHTML = `
    <div class="row" style="gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap">
      <span class="dim">시험정보</span>
      <select id="au-exam">
        <option value=""${EXAM ? "" : " selected"}>— 고르십시오 —</option>
        ${ex}</select>
      <button class="btn${EXAM && !LOADED ? " primary" : ""}" id="au-exam-load"
        type="button" ${EXAM ? "" : "disabled"}>불러오기</button>
      <a href="#" id="au-exam-jump">관리 ↓</a>
      ${cur ? `<span class="dim">회차 ${cur.round_size}문항 ·
        과목 ${(cur.subjects || []).map((s) => s.count).join("/")}</span>
        ${LOADED && (P.part_labels || []).length
          ? `<span class="dim">· 한 회차 ${P.part_labels.length}번 호출
              <span title="${escapeHtml(P.part_labels.join(" / "))}">(${
                escapeHtml(P.part_labels.join(" / "))})</span></span>` : ""}` : ""}
      ${cur && !cur.ok ? `<b class="bad">이 시험정보는 오류가 있어 집필에 쓸 수 없습니다</b>`
        : cur && !cur.confirmed ? `<b class="warn">확인되지 않은 값입니다
          ${cur.checked_at ? "(확인 " + escapeHtml(cur.checked_at) + ")" : "(확인일 없음)"}</b>`
        : ""}
    </div>
    ${!EXAM ? `<div class="empty" style="text-align:left">
        <b>시험정보를 고르십시오.</b><br>
        <span class="dim">회차당 문항수·과목 구성이 그 파일에서 옵니다 —
          고르지 않은 채로 회차를 보여 주면 어느 규격으로 집필되는지 알 수 없습니다.</span>
      </div>`
      : !LOADED ? `<div class="empty" style="text-align:left">
        <b>${escapeHtml(cur ? cur.label : EXAM)}</b> 로 계획을 잡으려면
        위 <b>[불러오기]</b> 를 누르십시오.
      </div>`
      /* ★ 서버가 이 폴더의 시험정보를 못 찾았다. 예전에는 이 자리에서 빅분기
       *   규격(80문항·4파트)으로 조용히 떨어져 «그럴듯한» 계획을 그렸고, 그 옆
       *   [실행] 이 몇 시간과 수십 달러를 썼다. 숫자 대신 사실을 그린다. */
      : (P.exam_missing || !P.round_size || !P.part_count)
      ? `<div class="empty" style="text-align:left;border-color:#d64545">
        <b class="bad">이 작업 폴더의 시험정보를 찾지 못했습니다.</b><br>
        <span class="dim">집필은 회차당 문항수·과목 구성을 그 파일에서 받습니다 —
          없으면 <b>어느 규격으로 집필될지 알 수 없어</b> 계획을 그리지 않습니다.<br>
          폴더의 <code>_book.json</code> 의 <code>pd</code> 와 같은
          <code>pd_id</code> 를 가진 <code>exams/*.json</code> 이 있어야 합니다 —
          <b>[과정 정의]</b> 화면에서 만드십시오.</span>
      </div>` : `
    ${sizeClash ? `<div class="empty" style="text-align:left;border-color:#f0b429">
        <b class="warn">시험정보와 기출이 맞지 않습니다.</b><br>
        <span class="dim">시험정보 <b>${escapeHtml(cur.label)}</b> 는 회차
          <b>${cur.round_size}문항</b> 인데, 작업 폴더의 기출 회차는
          <b>${poolSize}문항</b> 입니다. 작업 폴더가 다른 품목일 수 있습니다 —
          확인하고 실행하십시오.</span>
      </div>` : ""}
    <table class="tbl"><tbody>${rows}</tbody></table>
    <div class="row" style="justify-content:flex-end;align-items:center;gap:14px;margin-top:12px">
      <span class="dim">총 <b>${nR}회차</b> · <b>${(nR * perRound).toLocaleString()}문항</b>
        ${P.remaining_count != null && P.remaining_count < nR * partCount(P)
          ? `<b class="warn">· 남은 ${P.remaining_count}파트만 집필</b>` : ""}
        · 예상 <b>${money(est.usd)} · ${hours(est.minutes)}</b>
        <span title="${escapeHtml(est.note)}">(문항당 ${perItem(est)})</span></span>
      ${(P.overwrites || []).length
        ? `<b class="bad">이미 있는 회차를 덮습니다</b>` : ""}
      <button class="btn primary" id="au-go" type="button" ${nR ? "" : "disabled"}>실행</button>
    </div>
    <div class="field-hint" style="text-align:right">${escapeHtml(est.note)}</div>`}`;

  // ★ 아래가 안 그려졌으면 그 안의 위젯도 없다. `$("#au-go")` 가 null 인 채로
  //   `.onclick` 을 달면 거기서 멈춰 시험정보 콤보까지 죽는다.
  plan.querySelectorAll(".au-mult").forEach((s2) => {
    s2.onchange = () => { MULT_BY_ROW[s2.dataset.r] = Number(s2.value); drawRound(); };
  });
  plan.querySelectorAll(".au-mode").forEach((sel) => {
    sel.onchange = () => { MODE_BY_ROW[sel.dataset.r] = sel.value; };
  });
  plan.querySelectorAll(".au-pick").forEach((cb) => {
    cb.onchange = () => { PICK_BY_ROW[cb.dataset.r] = cb.checked; drawRound(); };
  });
  // ★ 고르는 것만으로는 아래가 뜨지 않는다. 고르면 오히려 **비운다** —
  //   앞 시험정보로 잡힌 표가 남아 있으면 그것이 새 시험정보의 계획으로 읽힌다.
  $("#au-exam").onchange = (e) => {
    EXAM = e.target.value;
    LOADED = false;
    drawRound();
  };
  const load = $("#au-exam-load");
  if (load) load.onclick = async () => {
    if (!EXAM) return;
    load.disabled = true;
    load.textContent = "불러오는 중…";
    await loadPlan();          // 고른 시험정보를 서버에 넘겨 규격을 다시 받는다
    LOADED = true;
    await drawRound();
  };
  const jump = $("#au-exam-jump");
  if (jump) jump.onclick = (e) => {
    e.preventDefault();
    const t = $("#au-exams");
    if (t) t.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const go = $("#au-go");
  if (go) go.onclick = () => start();

  await drawNext();
}

/** ③ 반입 · ④ 파생 — 스테이징이 찬 회차만 보여준다. */
async function drawNext() {
  const next = $("#au-next");
  if (!next) return;
  const codes = ((PLAN || {}).codes || []);
  if (!codes.length) { next.innerHTML = `<div class="empty">아직 없습니다.</div>`; return; }
  const rows = [];
  for (const c of codes) {
    const d = await api(`/api/authoring/round/${c}`).catch(() => null);
    if (!d || !d.ready_items) continue;
    rows.push(`<tr><td><b>${Number(c.slice(1))}회차</b></td>
      <td>${d.ready_items}문항 대기</td>
      <td>${(d.blocked || []).length
        ? `<b class="bad">${escapeHtml(d.blocked[0])}</b>` : `<span class="ok">합격</span>`}</td>
      <td><button class="btn au-merge" data-r="${c}" type="button">반입</button>
          <button class="btn au-derive" data-r="${c}" type="button">파생</button></td></tr>`);
  }
  next.innerHTML = rows.length
    ? `<table class="tbl"><tbody>${rows.join("")}</tbody></table>
       <pre class="job-log" id="au-out" hidden></pre>`
    : `<div class="empty">집필이 끝나면 여기에 반입·파생 버튼이 생깁니다.</div>`;
  next.querySelectorAll(".au-merge").forEach((b) => {
    b.onclick = () => post("/api/authoring/merge", { round: b.dataset.r });
  });
  next.querySelectorAll(".au-derive").forEach((b) => {
    b.onclick = () => post("/api/authoring/derive", { round: b.dataset.r });
  });
}

/* ── 집필 시작 · 진행 ─────────────────────────────────────────────────── */
async function start() {
  /* ★ 켜진 행만 돌린다. 회차마다 **기준이 다를 수 있으므로** 회차별로 보낸다 —
   *   `[{round:"m10", mode:"exam"}, …]`. 전역 mode 하나였던 것을 고쳤다:
   *   기출 1회차는 시험기준 변형으로, 2회차는 대표문제 변형으로 갈 수 있어야 한다. */
  const items = [];
  for (const r of (PLAN.rows || [])) {
    if (PICK_BY_ROW[r.pool_round] === false) continue;
    const mode = MODE_BY_ROW[r.pool_round] || "exam";
    for (const c of r.targets) items.push({ round: c, mode });
  }
  if (!items.length) { toast("집필할 회차를 고르십시오.", "err"); return; }

  /* ★ 여기서 계획을 **다시 받는다** (2026-09-08).
   *
   *   `PLAN` 은 화면을 열 때 잡은 값이다. 한 번 돌리고 중단한 뒤 다시 누르면
   *   그 값이 낡아서 확인창이 「아직 안 된 60파트」라고 묻는다 — 실제로는 5파트가
   *   이미 만들어져 있고 서버는 55파트만 돈다(실측). 서버가 옳게 돌더라도
   *   **묻는 말이 틀리면 사람이 계획을 잘못 읽는다.**
   *   싼 호출이다(모델을 안 부른다). 묻기 전에 사실을 맞춘다. */
  await loadPlan();

  // ★ 총계 줄과 **같은 값**을 쓴다. 예전엔 확인창이 자기 상수로 다시 곱해서
  //   같은 화면의 두 숫자가 서로 달랐다($62 와 $71).
  const nParts = partCount(PLAN);
  if (!nParts || !PLAN.round_size) {
    toast("시험정보를 찾지 못해 집필할 수 없습니다 — [과정 정의] 에서 만드십시오.", "err");
    return;
  }
  // ★ **실제로 돌 파트 수**로 묻는다. `회차 × 파트` 로 물었더니 「60회」라고 묻고
  //   29번만 돌았고, 그 차이 때문에 사람이 계획을 잘못 읽었다(2026-08-20).
  const nCall = PLAN.remaining_count != null
    ? PLAN.remaining_count : items.length * nParts;
  const done = items.length * nParts - nCall;
  const e = scaleEst(PLAN.est, nCall / nParts, nParts, PLAN.round_size);
  if (!window.confirm(
      `${items.length}회차 중 아직 안 된 ${nCall}파트를 집필합니다.\n`
      + (done > 0 ? `이미 합격한 ${done}파트는 건너뜁니다.\n` : "")
      + `예상 ${hours(e.minutes)} · 약 ${money(e.usd)} 상당의 구독 사용량입니다.\n`
      + `문항당 ${perItem(e)} — ${e.note}\n\n진행하시겠습니까?`)) return;

  const r = await api("/api/authoring/draft", { method: "POST", body: { items } })
    .catch((e) => ({ error: emsg(e) }));
  if (r.error) { toast(r.error, "err"); return; }
  attach(r.job);          // 로그 커서는 pollJob 이 들고 있다
}

let ATTACHED = "";      // 같은 잡에 폴링을 두 번 붙이지 않는다

async function attach(jobId) {
  if (!jobId || ATTACHED === jobId) return;
  ATTACHED = jobId;
  LOGBUF.length = 0;
  // ★ 3초. 과목 하나가 10~20분씩 가는데 1초로 두면 폴링만 1,200번이다.
  //   그래도 화면이 죽어 보이지 않는 이유는 모델의 도구 사용이 로그로 흐르기 때문이다.
  const done = await pollJob(jobId, drawJob, { interval: 3000 });
  ATTACHED = "";
  // 레일의 '최근 작업' 과 다른 화면이 듣는 신호. 안 쏘면 집필이 끝나도 목록이 옛것이다.
  fireJobChanged({ kind: "authoring", id: jobId, status: done && done.status });
  await drawRound();                    // 과목 상태를 다시 그린다
}

/* ══ 시험정보 관리 ═════════════════════════════════════════════════════════
 * ★ 게시판 형태로 **집필 화면 밑에** 둔다(2026-08-10 지시). 별도 창으로 빼지 않는다 —
 *   집필하다가 "이 회차당 문항수 맞나?" 를 확인하는 흐름이 끊기지 않아야 한다.
 *
 *   상단 : JSON 가져오기 (파일 · 붙여넣기)
 *   행 옆 : JSON 내보내기
 *
 * ★ 가져오기는 **검증을 통과하지 않으면 저장되지 않는다**(examspec.save). 과목 문항수
 *   합이 회차 문항수와 다른 JSON 을 받아들이면, 집필이 그 값으로 수 시간 돌고
 *   틀린 문제집이 나온 뒤에 안다.
 */
async function drawExams() {
  const box = $("#au-exams");
  if (!box) return;
  const r = await api("/api/authoring/exams").catch((e) => ({ error: emsg(e), items: [] }));
  const items = r.items || [];

  const rows = items.map((e) => {
    const badge = !e.ok ? `<b class="bad">오류 ${e.errors.length}건</b>`
      : e.confirmed ? `<span class="ok">확인됨</span>`
      : `<b class="warn">미확인</b>`;
    const subs = (e.subjects || []).map((s) => `${s.no}과목 ${s.count}`).join(" · ");
    return `<tr>
      <td><b>${escapeHtml(e.label)}</b>
        <div class="dim small"><code>${escapeHtml(e.id)}</code>
          ${e.pd_id ? " · 품목 " + escapeHtml(e.pd_id) : ""}
          ${e.spec_version ? " · v" + e.spec_version : ""}</div></td>
      <td class="dim">회차 <b>${e.round_size ?? "-"}</b>문항 · 파트 ${e.part_size ?? "-"}
        <div class="small">${escapeHtml(subs)}</div></td>
      <td>${badge}
        <div class="dim small">${e.checked_at ? "확인 " + escapeHtml(e.checked_at)
          : "확인일 없음"}${e.effective_from ? " · 적용 " + escapeHtml(e.effective_from) : ""}</div>
        ${(e.errors || []).slice(0, 2).map((x) =>
          `<div class="small bad">${escapeHtml(x)}</div>`).join("")}
        ${(e.warnings || []).slice(0, 2).map((x) =>
          `<div class="small dim">${escapeHtml(x)}</div>`).join("")}</td>
      <td style="white-space:nowrap">
        <button class="btn${e.confirmed ? "" : " primary"} au-ex-conf"
          data-id="${escapeHtml(e.id)}" data-on="${e.confirmed ? "0" : "1"}"
          type="button">${e.confirmed ? "미확인으로" : "확인 처리"}</button>
        <button class="btn au-ex-dl" data-id="${escapeHtml(e.id)}" type="button">JSON 내보내기</button>
      </td>
    </tr>`;
  }).join("");

  box.innerHTML = `
    <div class="row" style="gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
      <button class="btn" id="au-ex-imp" type="button">JSON 가져오기 (파일)</button>
      <button class="btn" id="au-ex-paste" type="button">붙여넣기로 가져오기</button>
      <input type="file" id="au-ex-file" accept=".json,application/json" hidden>
      <span class="dim">검증을 통과하지 않으면 저장되지 않습니다 —
        과목 문항수 합이 회차 문항수와 달라도 거절합니다.</span>
    </div>
    ${items.length ? `<table class="tbl"><tbody>${rows}</tbody></table>`
      : `<div class="empty">${escapeHtml(r.error || "exams/ 에 시험정보가 없습니다.")}</div>`}
    <div class="dim small" style="margin-top:8px">
      폴더 <code>${escapeHtml(r.dir || "exams/")}</code> ·
      매년 또는 시험이 개정될 때 이 파일을 고치고 <code>revision.checked_at</code> 을 채웁니다.
    </div>
    <pre class="job-log" id="au-ex-out" hidden></pre>`;

  /* ★ 「공고 확인」 버튼은 **두었다가 걷어냈다**(2026-08-19).

     앱이 띄우는 Claude 세션은 비대화형이라 `WebFetch`/`WebSearch` 승인을 받을 수
     없다 — 실행하면 「도구가 없습니다」 로 끝난다. 승인을 우회하도록 설정을 건드리는
     것은 이 앱이 할 일이 아니다.

     그래서 공고 대조는 **사람이 밖에서** 한다: `[JSON 내보내기]` 로 꺼내
     Claude 데스크탑에 주고, 시행처 페이지(`reference.official_url`)와 대조한 뒤
     여기서 `[확인 처리]` 를 누른다. 켜는 손짓이 사람 것이라는 원칙은 그대로다. */
  /* ★ 확인/미확인 — `revision.confirmed` 를 사람이 누른다.

     코드는 이 값을 알 수 없다. 「회차 50문항 · 2과목 10:40」 이 **올해 시행처 공고와
     같은가** 는 공고를 봐야 아는 것이라, 검증은 오류가 아니라 경고로만 남긴다.
     그래서 경고가 지워지지 않고 사람은 무엇을 해야 할지 모르는 자리가 됐다.

     ★ 누르기 전에 **무엇을 보증하는지** 먼저 보여 준다. 그냥 켜는 버튼이면
       아무도 공고를 안 보고 켜고, 그 순간 이 값은 뜻을 잃는다. */
  box.querySelectorAll(".au-ex-conf").forEach((b2) => {
    b2.onclick = async () => {
      const id = b2.dataset.id;
      const on = b2.dataset.on === "1";
      const e = items.find((x) => x.id === id) || {};
      const subs = (e.subjects || []).map((s) => `${s.no}과목 ${s.count}문항`).join(" · ");
      const ok = await confirmModal(on ? {
        title: `${e.label || id} — 시행처 공고와 같습니까?`,
        body: `<div style="text-align:left;line-height:1.7">
          아래 값이 <b>올해 공고와 같은지</b> 확인하셨다는 표시입니다.
          집필은 이 값으로 몇 시간을 돕니다.
          <ul style="margin:10px 0 10px 18px">
            <li>회차 <b>${e.round_size ?? "-"}문항</b> · 파트 <b>${e.part_size ?? "-"}문항</b></li>
            <li>${escapeHtml(subs || "과목 없음")}</li>
          </ul>
          누르면 <code>revision.confirmed = true</code> 이고
          <code>checked_at</code> 에 <b>오늘 날짜</b>가 박힙니다.
          <br><span class="dim">시험이 개정되면 다시 미확인으로 돌리십시오 —
          작년에 확인한 값은 올해 아무 뜻이 없습니다.</span></div>`,
        ok: "확인했습니다", cancel: "아직입니다",
      } : {
        title: `${e.label || id} — 미확인으로 되돌릴까요?`,
        body: `개정 공고를 아직 못 보셨다면 이쪽이 맞습니다.
          집필 화면에 <b>확인되지 않은 값입니다</b> 경고가 다시 뜹니다.`,
        ok: "미확인으로", cancel: "그대로",
      });
      if (!ok) return;
      const r2 = await api(`/api/authoring/exams/${encodeURIComponent(id)}/confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: on }),
      }).catch((err) => ({ error: emsg(err) }));
      if (r2.error) { toast(r2.error, "err"); return; }
      toast(on ? `확인 처리했습니다 — ${r2.checked_at}` : "미확인으로 되돌렸습니다.");
      await drawExams();
      // ★ `EXAMS` 를 **다시 받아야** 한다. 위 집필 줄은 그 캐시로 그려지므로,
      //   빼먹으면 관리 표는 「확인됨」인데 위는 「확인되지 않은 값입니다」로 남는다
      //   (실측 2026-08-19). 같은 값이 두 자리에서 다르게 보이면 어느 쪽도 못 믿는다.
      await loadExams();
      await drawRound();
    };
  });

  // 내보내기 — 서버 응답의 doc 을 그대로 파일로 내린다(왕복 손실 0).
  box.querySelectorAll(".au-ex-dl").forEach((b) => {
    b.onclick = async () => {
      const id = b.dataset.id;
      const g = await api(`/api/authoring/exams/${encodeURIComponent(id)}`)
        .catch((e) => ({ error: emsg(e) }));
      if (g.error) { toast(g.error, "err"); return; }
      const blob = new Blob([JSON.stringify(g.doc, null, 2) + "\n"],
                            { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${id}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    };
  });

  const send = async (id, doc) => {
    const out = $("#au-ex-out");
    const res = await api(`/api/authoring/exams/${encodeURIComponent(id)}`,
                          { method: "PUT", body: { doc } })
      .catch((e) => ({ error: emsg(e) }));
    if (out) {
      out.hidden = false;
      out.textContent = res.error
        ? "가져오기 실패\n" + res.error
        : "가져왔습니다: " + res.path +
          ((res.warnings || []).length ? "\n\n주의\n  - " + res.warnings.join("\n  - ") : "");
    }
    toast(res.error ? "가져오기 실패" : "가져왔습니다.", res.error ? "err" : "ok");
    if (!res.error) { await drawExams(); await loadExams(); await drawRound(); }
  };

  const parse = (txt) => {
    let doc;
    try { doc = JSON.parse(txt); }
    catch (e) { toast("JSON 을 읽을 수 없습니다: " + e.message, "err"); return null; }
    if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
      toast("JSON 최상위가 객체가 아닙니다.", "err"); return null;
    }
    // ★ id 는 JSON 안에 있어야 한다. 파일명에서 추측하면 다른 시험정보를 덮는다.
    if (!doc.id) { toast("JSON 에 id 가 없습니다.", "err"); return null; }
    return doc;
  };

  $("#au-ex-imp").onclick = () => $("#au-ex-file").click();
  $("#au-ex-file").onchange = async (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    const doc = parse(await f.text());
    e.target.value = "";
    if (doc) await send(doc.id, doc);
  };
  $("#au-ex-paste").onclick = async () => {
    const txt = window.prompt("시험정보 JSON 을 붙여넣으십시오.");
    if (!txt) return;
    const doc = parse(txt);
    if (doc) await send(doc.id, doc);
  };
}

/* ══ 진행 ══════════════════════════════════════════════════════════════════
 * ★ **이 화면의 핵심이다**(2026-08-10 지시): *"생각보다 오래 걸린다는 것도 잘 알고
 *   있습니다. 그 진행률과 함께 시간이 지나가는 것을 계속 보여주는 게 이 프로그램의
 *   핵심입니다."*
 *
 * 그래서 세 가지를 **따로** 돌린다:
 *   ① 초시계 — 1초마다 화면만 갱신한다. 폴링(3초)에 묶으면 시간이 3초씩 튄다.
 *     시간이 매끄럽게 흐르지 않으면 "멈췄나" 로 읽힌다 — 그게 정확히 피하려는 것이다.
 *   ② 진행률 — 끝난 과목 수. 서버가 세는 값을 그대로 쓴다.
 *   ③ 지금 하는 일 — 모델의 도구 사용 로그. 과목 하나가 10~20분인데 이것이 없으면
 *     10분 동안 화면에 아무 변화가 없다.
 *
 * ★ 남은 시간은 **실측된 것으로만** 추정한다. 끝난 과목이 없으면 "측정 중" 이라고
 *   말하고 숫자를 지어내지 않는다 — 틀린 ETA 는 없는 것보다 나쁘다.
 */
const LOGBUF = [];
let TICKER = null;         // 1초 초시계 (표시 전용)
let JOB0 = 0;              // 이 잡을 화면에서 보기 시작한 시각
let ITEM0 = 0;             // 지금 과목이 시작된 시각
let ITEMKEY = "";
let LASTJOB = null;

const fmtDur = (ms) => {
  const s = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), ss = s % 60;
  return h ? `${h}시간 ${String(m).padStart(2, "0")}분 ${String(ss).padStart(2, "0")}초`
           : `${m}분 ${String(ss).padStart(2, "0")}초`;
};

function startTicker() {
  if (TICKER) return;
  // 표시 전용 타이머다 — 잡 폴링은 store.pollJob 이 한다.
  TICKER = setInterval(() => {
    const el2 = $("#au-elapsed");
    if (!el2) { stopTicker(); return; }
    el2.textContent = fmtDur(Date.now() - JOB0);
    const it = $("#au-item-elapsed");
    if (it && ITEM0) it.textContent = fmtDur(Date.now() - ITEM0);
    const eta = $("#au-eta");
    if (eta && LASTJOB) eta.innerHTML = etaHtml(LASTJOB);
  }, 1000);
}
function stopTicker() { if (TICKER) { clearInterval(TICKER); TICKER = null; } }

/** 남은 시간 — **실측으로만** 계산한다. 어느 실측인지 반드시 밝힌다.
 *
 * ★ 첫 과목이 끝나기 전에도 숫자를 보여 준다. 예전엔 `—` 였는데, 그 구간이
 *   12분이고 그동안 화면의 `0/36` 이 한 칸도 안 움직인다 — SME 는 그걸 멈춘
 *   것으로 읽는다("SME분들은 예민해서", 2026-08-10).
 * ★ 그렇다고 숫자를 지어내지는 않는다. 서버가 **지난 실행의 실측**(스테이징에
 *   쌓인 과목당 평균)을 주므로 그것을 쓰고, 출처를 화면에 적는다. 첫 과목이
 *   끝나는 순간 이번 잡의 실측으로 갈아탄다.
 */
function etaHtml(j) {
  const done = j.done_count || 0;
  const total = j.total_count || 0;
  if (!total || done >= total) return `<span class="dim">—</span>`;

  if (done) {
    const per = (Date.now() - JOB0) / done;        // 과목 하나에 걸린 실측 평균
    return `약 <b>${fmtDur((total - done) * per)}</b> 남음
      <span class="dim">(이번 잡 실측 · 과목당 ${fmtDur(per)})</span>`;
  }

  // 아직 한 과목도 안 끝났다 — 지난 실측으로 어림잡는다.
  const e = (PLAN || {}).est || {};
  const perMs = (e.per_part_minutes || 0) * 60000;
  if (!perMs) return `<span class="dim">첫 과목이 끝나면 계산됩니다</span>`;
  // 지금 과목에 이미 쓴 시간을 뺀다 — 안 빼면 숫자가 12분 동안 안 움직여서
  // 고쳐야 할 바로 그 증상이 그대로 남는다.
  const left = Math.max(0, total * perMs - (ITEM0 ? Date.now() - ITEM0 : 0));
  return `약 <b>${fmtDur(left)}</b> 남음
    <span class="dim">(지난 실측 ${e.samples || 0}과목 기준 · 과목당
    ${fmtDur(perMs)} — 첫 과목이 끝나면 이번 잡 실측으로 바뀝니다)</span>`;
}

function drawJob(j) {
  const box = $("#au-job");
  if (!box) return;
  LASTJOB = j;
  if (j.log && j.log.lines) LOGBUF.push(...j.log.lines);
  // ★ 시작 시각은 **서버가 준 것**을 쓴다. `Date.now()` 로 잡으면 화면을 다시 열 때마다
  //   경과가 0 부터 시작해서, 15분째 돌고 있는 잡이 "0분" 으로 보인다.
  if (!JOB0) {
    // ★ 서버의 `now_iso()` 는 `2026-08-10T14:21:05` — **타임존 표기가 없다.**
    //   같은 PC 면 브라우저가 로컬 시각으로 읽어 맞지만, 사내망으로 다른 기기에서
    //   보면 시차만큼 틀어진다(KST↔UTC 면 9시간). 그러면 경과가 "9시간" 이나
    //   음수로 뜨고, 그건 시계가 없는 것보다 나쁘다 — 사람이 화면을 안 믿게 된다.
    //   그래서 **말이 되는 값일 때만** 쓴다.
    const t = j.started_at ? Date.parse(j.started_at) : NaN;
    const gap = Date.now() - t;
    JOB0 = (Number.isFinite(t) && gap >= -60e3 && gap < 24 * 3600e3) ? t : Date.now();
  }
  // 과목이 바뀌면 그 과목의 초시계를 다시 잡는다
  if (j.current && j.current !== ITEMKEY) { ITEMKEY = j.current; ITEM0 = Date.now(); }

  const running = ["running", "queued"].includes(j.status);
  /* ★ 「끝났다」와 「중단했다」를 가른다 (2026-09-08).
   *
   *   `status:"done"` 만 보고 그리면 일시정지로 마감된 잡도 완료로 읽힌다.
   *   실측: 5파트를 만들고 멈춘 잡이 「60/60 (100%) done」 으로 떴고, 7시간짜리
   *   집필이 41분에 끝난 줄 알았다. 서버에서 `skipped` 를 done_count 에서
   *   뺐지만(`services/jobs/registry.py`), **이미 저장된 기록은 그대로**다 —
   *   그 기록의 done_count 는 60 이다. 그래서 화면은 **저장된 숫자를 믿지 않고
   *   파트 상태에서 직접 센다.** `skipped` 는 옛 이름, `canceled` 는 새 이름이고
   *   둘 다 「안 한 것」이다. */
  const st = Object.values(j.items || {});
  const nDone = st.filter((v) => ["done", "error"].includes(v.status)).length;
  const nStop = st.filter((v) => ["canceled", "skipped"].includes(v.status)).length;
  const doneN = st.length ? nDone : (j.done_count || 0);
  const totalN = j.total_count || st.length || 0;
  const pct = totalN ? Math.round((doneN / totalN) * 100) : 0;
  const stopped = !running && (nStop > 0 || (totalN && doneN < totalN));
  /* ★ 칩 이름은 **회차 + 문항범위** 다. `m01 1과목` 이 아니라 `1회 1~20`.
   *   자사 회차 코드(m01…)를 사람에게 보이지 않는 것은 계획 표에서 이미 정한
   *   규칙인데("m10은 뭐에요?", 2026-08-10) 진행 칩만 옛 형태로 남아 있었다.
   *   "1과목" 도 지웠다 — 어느 과목인지보다 **몇 번 문항인지**가 훨씬 쓸모 있다
   *   (요청 그대로: "1회 1~10.. 1회 11~20... 이런식으로").
   *   ★ 범위를 **화면이 계산하지 않는다.** `(p-1)*part_size+1 ~ p*part_size` 로
   *   지어냈더니 SQLD(part_size 25)에서 `12회 51~75` 가 됐다 — 50문항 시험에 75번은
   *   없다(2026-08-20 실측). 파트는 **과목에서** 만들어져 크기가 파트마다 다르다
   *   (1과목 10 / 2과목 20 / 2과목 20). 서버가 준 `part_labels` 를 쓴다. */
  const labels = (PLAN && PLAN.part_labels) || [];
  const items = Object.entries(j.items || {}).map(([k, v]) => {
    // ★ `canceled` 는 «안 한» 것이다 — `dim` 으로 떨어지게 둔다(done 색을 주면
    //   중단한 잡이 다 끝난 것처럼 보인다).
    const cls = v.status === "done" ? "ok" : v.status === "error" ? "bad"
      : v.status === "running" ? "warn" : "dim";
    const p = Number(String(k).split("-p")[1] || 0);
    const n = Number(String(k).split("-p")[0].replace(/^m/, "")) || 0;
    // 서버 라벨은 「1과목 · 1~10번」 꼴이다 — 회차를 앞에 붙이고 문항범위만 남긴다.
    const lab = labels[p - 1] || "";
    const rng = lab.includes("·") ? lab.split("·").pop().trim() : lab;
    const nm = (p && n) ? `${n}회 ${rng || "p" + p}` : k;
    return `<span class="chip ${cls}" title="${escapeHtml(k + " · " + (v.error || v.status))}">${
      escapeHtml(nm)}</span>`;
  }).join(" ");

  // 지금 하는 일 — 로그 마지막 줄에서 뽑는다. 도구 사용이 여기로 흐른다.
  const nowDoing = [...LOGBUF].reverse().find((l) => !/^합계/.test(l)) || "";

  box.innerHTML = `
    <div class="row" style="gap:18px;align-items:baseline;flex-wrap:wrap">
      <div><span class="dim small">경과</span>
        <b id="au-elapsed" style="font-size:20px;font-variant-numeric:tabular-nums">
          ${fmtDur(Date.now() - JOB0)}</b></div>
      <div><span class="dim small">진행</span>
        <b style="font-size:20px">${doneN}/${totalN}</b>
        <span class="dim">(${pct}%)</span>
        ${stopped ? `<b class="warn">· ${totalN - doneN}파트 남음</b>` : ""}</div>
      <div><span class="dim small">남은 시간</span> <span id="au-eta">${etaHtml(j)}</span></div>
      <div class="dim small" style="margin-left:auto">
        <code>${escapeHtml(j.id.slice(0, 8))}</code>
        ${stopped ? `<b class="warn">중단됨</b>` : escapeHtml(j.status)}</div>
    </div>
    <div class="bar" style="margin:10px 0"><span style="width:${pct}%"></span></div>
    <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:8px">${items}</div>
    ${j.current ? `<div class="kvs">
      ${kv("지금", `<b>${escapeHtml(j.current)}</b> ·
        <span id="au-item-elapsed" style="font-variant-numeric:tabular-nums">
          ${fmtDur(Date.now() - (ITEM0 || Date.now()))}</span> 경과`)}
      ${kv("하는 일", `<span class="dim">${escapeHtml(nowDoing)}</span>`)}
    </div>` : ""}
    ${stopped && !j.error ? `<div class="empty" style="text-align:left;border-color:#f0b429">
      <b class="warn">중단된 집필입니다 — 아직 다 만들어지지 않았습니다.</b><br>
      <span class="dim"><b>${doneN}파트</b>가 만들어졌고
        <b>${totalN - doneN}파트</b>가 남았습니다.
        위 <b>[실행]</b> 을 다시 누르면 <b>끝난 파트는 건너뛰고</b> 남은 것부터 갑니다.</span>
    </div>` : ""}
    ${j.error ? `<div class="kvs">${kv("오류", `<b class="bad">${escapeHtml(j.error)}</b>`)}</div>` : ""}
    ${running ? `<div class="row" style="margin-top:10px">
      <button class="btn pause" id="au-cancel" type="button">⏸ 일시정지</button>
      <span class="dim">돌고 있는 파트는 끝까지 갑니다 — 그 뒤만 멈춥니다.
        <b>합격한 파트는 남습니다</b>. 나중에 [실행] 을 다시 누르면 멈춘 자리부터
        이어 갑니다(끝난 파트는 건너뜁니다).</span>
    </div>` : ""}
    ${!running && j.status !== "done" ? `<div class="row" style="margin-top:10px">
      <button class="btn primary" id="au-resume" type="button">이어서 실행</button>
      <span class="dim">멈춘 자리부터 남은 파트만 집필합니다. 세션 한도로 멈췄다면
        사용량 화면에서 <b>현재 세션</b>이 리셋된 뒤에 누르십시오 — 주간 %가 아닙니다.</span>
    </div>` : ""}
    <pre class="job-log">${escapeHtml(LOGBUF.slice(-140).join("\n"))}</pre>`;

  // 로그를 끝으로 붙여 둔다 — 새 줄이 위로 밀려 안 보이면 흐르는 느낌이 사라진다.
  const lg = box.querySelector(".job-log");
  if (lg) lg.scrollTop = lg.scrollHeight;

  if (running) startTicker(); else stopTicker();

  const c = $("#au-cancel");
  if (c) c.onclick = async () => {
    c.disabled = true;
    await api(`/api/jobs/${j.id}/cancel`, { method: "POST" }).catch(() => {});
    // ★ 「취소」 가 아니라 「일시정지」 다. 만든 것은 `data/authoring/<품목>/` 에
    //   파일로 남고, 다시 [실행] 하면 끝난 파트를 건너뛴다 — 잃는 것이 없다.
    //   이름이 「취소」 였을 때 사람이 누르기를 망설였다(2026-08-20).
    toast("일시정지했습니다 — 만든 파트는 남습니다. 나중에 [이어서 실행].", "");
  };
  // ★ 멈춘 잡에서 바로 이어 갈 수 있게. 계획을 다시 고르게 하면 그 사이에
  //   설정이 어긋난다(실측: 21회차·m11~m30 계획이 그렇게 잡혔다).
  const rs = $("#au-resume");
  if (rs) rs.onclick = () => { rs.disabled = true; start(); };
}

/* ── 공용 ─────────────────────────────────────────────────────────────── */
async function post(url, body) {
  const out = $("#au-out");
  if (out) { out.hidden = false; out.textContent = "부르는 중…"; }
  const r = await api(url, { method: "POST", body }).catch((e) => ({ error: emsg(e) }));
  if (out) out.textContent = render(r);
  if (r.ok === false || r.error) toast(r.error || "실패했습니다.", "err");
  else toast(body.dry_run ? "미리보기 완료" : "완료", "ok");
  drawRound();
}

function render(r) {
  // 서브프로세스 결과는 stdout 이 본문이다 — JSON 을 그대로 붓지 않는다.
  const bits = [];
  if (r.error) bits.push("오류: " + r.error);
  if (r.err) bits.push(r.err);
  if (r.out) bits.push(r.out);
  if (r.validate) bits.push("── validate.py ──\n" + (r.validate.out || r.validate.err || ""));
  if (!bits.length) bits.push(JSON.stringify(r, null, 2));
  return bits.join("\n");
}

/* ── 소모량 표시 ──────────────────────────────────────────────────────────
 * ★ 계산은 **서버가 실측에서** 한다(`services/authoring/cost.py`). 화면은 과목당
 *   값을 켜진 회차 수에 곱하기만 한다. 곱셈이 두 군데(총계 줄·확인창)에 있으므로
 *   함수 하나로 묶는다 — 따로 쓰다가 실제로 두 숫자가 갈렸다.
 */
/* ★ 되돌림값을 두지 않는다 (2026-09-08). 전에는 `|| 80` · `|| 20` 이라 시험정보를
 *   못 찾으면 조용히 **빅분기 4파트**가 됐다 — 그 숫자가 그대로 [실행] 확인창의
 *   「36파트는 건너뜁니다」 로 갔다. 없으면 null 이고, 부르는 쪽이 막는다. */
const partCount = (P) => (P && P.part_count) || null;

function scaleEst(e, nRounds, nParts, perRound) {
  e = e || {};
  const calls = Math.max(0, nRounds) * Math.max(1, nParts);
  const usd = (e.per_part_usd || 0) * calls;
  return {
    usd,
    minutes: Math.round((e.per_part_minutes || 0) * calls),
    // 서버가 실측 문항당 단가를 준다. 없으면(폴백) 여기서 나눈다.
    per_item_usd: e.per_item_usd
      || (nRounds && perRound ? usd / (nRounds * perRound) : 0),
    note: e.note || "", measured: !!e.measured, samples: e.samples || 0,
  };
}

const money = (v) => "$" + (Number(v || 0) < 10
  ? Number(v || 0).toFixed(2) : Math.round(Number(v || 0)).toLocaleString());
const hours = (m) => {
  m = Math.max(0, Math.round(Number(m) || 0));
  if (m < 60) return `${m}분`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `${h}시간 ${r}분` : `${h}시간`;
};
// 문항당은 센트 단위라 소수 세 자리로 둔다 — $0.09 로 반올림하면 $0.087 과
// $0.094 가 같아 보이고, 1,000제에서 그 차이가 $7 이다.
const perItem = (e) => "$" + Number((e && e.per_item_usd) || 0).toFixed(3);

const kv = (k, v) => `<div class="kv"><span class="kv-k">${escapeHtml(k)}</span>` +
                     `<span class="kv-v">${v}</span></div>`;
const shortPath = (p) => {
  const s = String(p || "").replace(/\\/g, "/");
  const bits = s.split("/");
  return bits.length > 3 ? "…/" + bits.slice(-3).join("/") : s;
};
