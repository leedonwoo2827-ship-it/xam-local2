/* 과정 정의 — 새 과정의 시험정보(`exams/<id>.json`) 를 세우는 자리.
 *
 * ★ 왜 이 화면이 «만드는» 화면이 아닌가 (2026-09-07).
 *
 *   이 단계의 핵심은 폼을 채우는 게 아니라 **시행처 공고와 최근 출제경향을 읽는
 *   일**이다. 그런데 이 앱이 띄우는 Claude 세션은 `WebFetch`·`WebSearch` 가
 *   막혀 있다 — `services/authoring/provider.py` 의 `disallowed_tools` 에
 *   박혀 있고, 그건 실수가 아니라 결정이다(집필은 재현 가능해야 한다).
 *
 *   그래서 여기에 입력 폼을 두면 **사람이 공고를 손으로 옮겨 적는 화면**이 된다.
 *   숫자를 옮기다 틀리면 집필이 그 값으로 몇 시간을 돌고, 틀린 문제집이 나온
 *   뒤에야 안다. 그건 이 파일이 존재하는 이유(`examspec.py` 머리말)와 정면으로
 *   어긋난다.
 *
 *   그래서 이 화면은 **가지 않는다 — 보낸다.** 무엇을 시켜야 하는지 프롬프트로
 *   적어 주고, 돌아온 JSON 을 받아 검산하고 저장한다. 사람이 옮겨 적을 것이 없다.
 *
 * ★ 이 화면이 실제로 하는 일은 셋이다.
 *     ① 어디 가서 무엇을 시킬지 알려 준다  — 프롬프트 [복사]
 *     ② 돌아온 JSON 을 받는다             — 붙여넣기 / 파일
 *     ③ 지금 등록된 과정의 상태를 보여 준다 — 오류 · 확인 여부 · [확인 처리]
 *
 *   ①이 이 화면의 본체다. 그게 없으면 "여기서 뭘 하라는 거지" 로 끝나고,
 *   결국 매번 담당자가 물어보러 온다. 그러면 다른 사람은 이 앱을 못 쓴다.
 */
"use strict";

import { $, $$, api, el, escapeHtml, toast, confirmModal, formModal } from "./util.js";
import { hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const S = {
  exams: null,      // /api/authoring/exams
  book: null,       // /api/books 의 활성 항목
};

export const meta = {
  title: () => "과정 정의",
  subtitle: () =>
    "새 과정의 시험정보를 세웁니다 — 공고·출제경향 대조는 Claude Code 창에서 합니다.",
  actions: () => [
    actionBtn("JSON 받기 (붙여넣기)", () => paste(), { primary: true, iconName: "file" }),
    actionBtn("파일로 받기", () => $("#ed-file") && $("#ed-file").click(), { iconName: "folder" }),
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
  ],
};

export async function mount(root) {
  const page = el("div", "page");
  page.innerHTML = `
    <div class="card">
      <div class="card-title">① 어디서 만드나 — <b>Claude Code 창</b>에서 만듭니다</div>
      <div id="ed-why"></div>
    </div>

    <div class="card">
      <div class="card-title">② 무엇을 시키나 — 아래를 그대로 복사해 붙여 넣으세요</div>
      <div id="ed-prompt"><div class="empty">불러오는 중…</div></div>
    </div>

    <div class="card">
      <div class="card-title">③ 등록된 과정</div>
      <div id="ed-list"><div class="empty">불러오는 중…</div></div>
    </div>

    <input type="file" id="ed-file" accept=".json,application/json" hidden>
  `;
  root.appendChild(page);
  hydrateIcons(page);

  const f = $("#ed-file", page);
  if (f) f.addEventListener("change", onFile);

  await load();
}

/* ── 불러오기 ─────────────────────────────────────────────────────────── */
async function load() {
  const [ex, bk] = await Promise.all([
    api("/api/authoring/exams").catch((e) => ({ error: String(e.message || e), items: [] })),
    api("/api/books").catch(() => ({ items: [] })),
  ]);
  S.exams = ex;
  S.book = (bk.items || []).find((x) => x.active) || null;
  drawWhy();
  drawPrompt();
  drawList();
}

/* ── ① 왜 여기가 아닌가 ───────────────────────────────────────────────── */
function drawWhy() {
  const box = $("#ed-why");
  if (!box) return;
  box.innerHTML = `
    <div class="field-hint" style="line-height:1.75">
      이 단계는 <b>시행처 공고와 최근 출제경향을 읽는 일</b>입니다. 이 앱이 띄우는
      Claude 세션은 <b>웹을 못 봅니다</b> — 집필 결과가 사람마다 달라지지 않도록
      <code>WebFetch</code>·<code>WebSearch</code> 를 일부러 막아 두었습니다
      (<code>services/authoring/provider.py</code>).<br>
      그래서 여기에 입력칸을 두면 <b>사람이 공고를 손으로 옮겨 적는 화면</b>이 됩니다.
      한 자리만 틀려도 집필이 그 값으로 몇 시간을 돌고, <b>틀린 문제집이 나온 뒤에</b>
      압니다.<br><br>
      <b>그래서 이렇게 하십시오 — Claude Code 창(이 앱을 띄운 그 대화)으로 가서,
      아래 ②의 글을 그대로 붙여 넣고 JSON 을 만들어 달라고 하십시오.</b>
      돌아온 JSON 은 위 <b>[JSON 받기]</b> 로 여기에 넣으면 됩니다 —
      과목 문항수 합이 회차 문항수와 다르면 <b>저장이 거부됩니다</b>.
    </div>`;
}

/* ── ② 시킬 말 ────────────────────────────────────────────────────────── */
/* ★ 대강만 적는다. 여기서 문장을 완벽하게 만들려 들면 시험이 개정될 때마다 이
 *   화면을 고쳐야 한다. 사람이 읽고 자기 과정에 맞게 고쳐 쓰는 것이 전제다. */
function promptText() {
  const b = S.book || {};
  const pd = (b.pd || "").trim();
  const known = (S.exams && S.exams.items || []).map((x) => x.id);
  const base = known.includes("sqld") ? "sqld" : (known[0] || "sqld");
  return [
    `새 과정의 시험정보 JSON 을 만들어 주세요.`,
    ``,
    `- 과정 이름: (여기에 적으세요 — 예: ADsP 데이터분석 준전문가)`,
    `- 품목 코드(pd): ${pd || "(아직 없음 — 발행 대상 품목 코드)"}`,
    `- 작업 폴더: ${b.path || "(작업 폴더를 먼저 지정하세요)"}`,
    ``,
    `해 주실 일:`,
    ``,
    `1. 시행처 공고를 웹에서 찾아 읽고 다음을 확정해 주세요.`,
    `   - 회차당 문항수, 과목 구성(번호 · 이름 · 과목별 문항수), 보기 수`,
    `   - 공고 표의 숫자를 그대로 쓰고, 블로그·요약글이 공고와 다르면 공고를 따르세요.`,
    ``,
    `2. 최근 회차의 출제경향을 검색해 정리해 주세요. ★ 이게 핵심입니다.`,
    `   - 가장 최근에 시행된 회차까지 반영해 주세요. 올해 것이 빠지면 안 됩니다.`,
    `   - 어느 과목·단원의 비중이 늘고 줄었는지`,
    `   - 새로 들어온 주제, 사라진 주제`,
    `   - 자주 나오는 함정, 헷갈리는 개념 짝(오답쌍)`,
    `   - 그 결과를 난도 배분과 과목별 계획에 반영해 주세요.`,
    ``,
    `3. 이 값이 언제까지 유효한지 정해 주세요. ★ 빼먹기 쉬운데 중요합니다.`,
    `   - 다음 개편이 예상되는 시점을 찾아, 그 직전 날짜를`,
    `     revision.effective_until 에 YYYY-MM-DD 로 넣어 주세요.`,
    `   - 한 번 정한 이 파일로 열몇 회차를 집필합니다. 개편된 뒤에도 낡은 기준이`,
    `     그대로 통과하면, 아무도 안 틀렸는데 결과가 틀립니다.`,
    ``,
    `4. 스캔이 있으면 그것도 같이 보세요. (없으면 건너뛰세요 — 조사만으로도 됩니다)`,
    `   - 01/ 의 문항을 세어 과목 구성이 공고와 맞는지 대조해 주세요.`,
    `   - 어긋나면 공고를 따르고, 어긋났다는 사실을 알려 주세요.`,
    ``,
    `5. exams/${base}.json 을 본떠서 같은 구조로 만들어 주세요.`,
    `   - 난도 루브릭 · 함정 · 오답쌍 · 발음 사전은 이 과정에 맞게 다시 써 주세요.`,
    `   - 베낀 채로 두면 다른 시험의 기준으로 집필됩니다.`,
    ``,
    `6. 마지막에 반드시 확인해 주세요.`,
    `   - 과목 문항수의 합 == round.size (다르면 앱이 저장을 거부합니다)`,
    `   - revision.source_url 에 근거가 된 공고 주소`,
    `   - revision.checked_at 에 확인한 날짜`,
    `   - revision.effective_until 에 언제까지 유효한지`,
    ``,
    `다 되면 JSON 전문을 보여 주세요. 제가 앱의 [JSON 받기] 로 넣겠습니다.`,
  ].join("\n");
}

function drawPrompt() {
  const box = $("#ed-prompt");
  if (!box) return;
  const txt = promptText();
  box.innerHTML = `
    <pre class="pb-cmd" id="ed-ptext" style="white-space:pre-wrap">${escapeHtml(txt)}</pre>
    <div class="row" style="gap:8px;align-items:center;margin-top:9px;flex-wrap:wrap">
      <button class="btn primary" id="ed-copy" type="button">이 글 복사</button>
      <span class="dim">복사해서 <b>Claude Code 창</b>에 붙여 넣으세요.
        과정 이름은 직접 채우십시오 — 추측하면 안 되는 값입니다.</span>
    </div>`;
  const b = $("#ed-copy");
  if (b) {
    b.onclick = async () => {
      try {
        await navigator.clipboard.writeText(txt);
        toast("복사했습니다 — Claude Code 창에 붙여 넣으세요.");
      } catch {
        // ★ 클립보드는 권한·컨텍스트에 따라 막힌다. 실패해도 길을 남긴다.
        const p = $("#ed-ptext");
        if (p) {
          const r = document.createRange();
          r.selectNodeContents(p);
          const sel = window.getSelection();
          sel.removeAllRanges();
          sel.addRange(r);
        }
        toast("복사가 막혀 있어 글을 선택해 두었습니다 — Ctrl+C 를 누르세요.", "err");
      }
    };
  }
}

/* ── ③ 등록된 과정 ────────────────────────────────────────────────────── */
/* ★ 「언제까지 유효한가」 를 상태 옆에 붙인다. 확인일만 보이면 «작년에 확인한
 *   true» 가 올해도 확인된 값처럼 읽힌다 — 이 파일 하나로 열몇 회차를 집필하므로
 *   그 착각의 대가가 회차 수만큼 곱해진다. */
function untilBadge(e) {
  const u = (e.effective_until || "").trim();
  if (!u) return `<span class="badge warn">유효기간 없음</span>`;
  const d = new Date(u + "T23:59:59");
  if (!isNaN(d) && d < new Date()) {
    return `<span class="badge err">${escapeHtml(u)} 까지 — 지났습니다</span>`;
  }
  return `<span class="badge">~${escapeHtml(u)}</span>`;
}

function drawList() {
  const box = $("#ed-list");
  if (!box) return;
  const r = S.exams || {};
  const items = r.items || [];
  const activePd = ((S.book || {}).pd || "").trim();

  if (!items.length) {
    box.innerHTML = `<div class="empty">${escapeHtml(r.error
      || "아직 등록된 과정이 없습니다 — 위 ②를 복사해 Claude Code 창에서 만드세요.")}</div>`;
    return;
  }

  const rows = items.map((e) => {
    const badge = !e.ok ? `<b class="bad">오류 ${e.errors.length}건</b>`
      : e.confirmed ? `<span class="ok">확인됨</span>`
      : `<b class="warn">미확인</b>`;
    const subs = (e.subjects || []).map((s) => `${s.no}. ${s.name} ${s.count}`).join(" · ");
    // ★ 지금 작업 폴더의 품목과 같은 과정을 표시해 준다 — 목록이 길어지면
    //   "내가 지금 쓰는 게 어느 것인가" 가 안 보인다.
    const mine = activePd && e.pd_id === activePd;
    return `<tr${mine ? ' class="on"' : ""}>
      <td><b>${escapeHtml(e.label)}</b>${mine ? ' <span class="badge">지금 폴더</span>' : ""}
        <div class="dim small"><code>${escapeHtml(e.id)}</code>
          ${e.pd_id ? " · 품목 " + escapeHtml(e.pd_id) : " · <b class='warn'>품목 코드 없음</b>"}
          ${e.spec_version ? " · v" + e.spec_version : ""}</div></td>
      <td class="dim">회차 <b>${e.round_size ?? "-"}</b>문항 · 파트 상한 ${e.part_size ?? "-"}
        <div class="small">${escapeHtml(subs)}</div></td>
      <td>${badge} ${untilBadge(e)}
        <div class="dim small">${e.checked_at ? "확인 " + escapeHtml(e.checked_at)
          : "확인일 없음"}</div>
        ${(e.errors || []).slice(0, 3).map((x) =>
          `<div class="small bad">${escapeHtml(x)}</div>`).join("")}
        ${(e.warnings || []).slice(0, 2).map((x) =>
          `<div class="small dim">${escapeHtml(x)}</div>`).join("")}</td>
      <td style="white-space:nowrap">
        <button class="btn sm${e.confirmed ? "" : " primary"} ed-conf"
          data-id="${escapeHtml(e.id)}" data-on="${e.confirmed ? "0" : "1"}"
          type="button">${e.confirmed ? "미확인으로" : "확인 처리"}</button>
        <button class="btn sm ed-dl" data-id="${escapeHtml(e.id)}" type="button">JSON 꺼내기</button>
      </td>
    </tr>`;
  }).join("");

  box.innerHTML = `
    <table class="tbl"><tbody>${rows}</tbody></table>
    <div class="dim small" style="margin-top:9px">
      폴더 <code>${escapeHtml(r.dir || "exams/")}</code> ·
      <b>고칠 때도 같은 길입니다</b> — 개정되면 ②를 다시 복사해 Claude Code 창에서
      고친 JSON 을 받아 [JSON 받기] 로 덮어쓰세요.
    </div>`;

  $$(".ed-conf", box).forEach((b) => { b.onclick = () => confirmOne(b, items); });
  $$(".ed-dl", box).forEach((b) => { b.onclick = () => exportOne(b.dataset.id); });
}

/* ★ 「확인했다」 는 사람만 아는 값이다 — 이 값이 공고와 같은지는 공고를 봐야 안다.
 *   그래서 누르기 전에 무엇을 보증하는지 먼저 보여 준다. 그냥 켜는 버튼이면
 *   아무도 공고를 안 보고 켜고, 그 순간 이 값은 뜻을 잃는다. */
async function confirmOne(btn, items) {
  const id = btn.dataset.id;
  const on = btn.dataset.on === "1";
  const e = items.find((x) => x.id === id) || {};
  const subs = (e.subjects || []).map((s) => `${s.no}과목 ${s.count}문항`).join(" · ");

  if (on) {
    const got = await formModal({
      title: `${e.label || id} — 시행처 공고와 같습니까?`,
      body: `<div style="text-align:left;line-height:1.7">
        아래 값이 <b>올해 공고와 같은지</b> 확인하셨다는 표시입니다.
        집필은 이 값으로 몇 시간을 돕니다.
        <ul style="margin:10px 0 10px 18px">
          <li>회차 <b>${e.round_size ?? "-"}문항</b> · 파트 상한 <b>${e.part_size ?? "-"}</b></li>
          <li>${escapeHtml(subs || "과목 없음")}</li>
        </ul></div>`,
      fields: [
        { name: "source_url", label: "근거가 된 공고 주소",
          placeholder: "https://www.dataq.or.kr/…",
          hint: "나중에 「무엇을 보고 확인했나」 를 되짚을 유일한 단서입니다." },
        { name: "effective_until", label: "언제까지 유효합니까? (YYYY-MM-DD)",
          value: (e.effective_until || ""), placeholder: "2027-03-31",
          hint: "다음 개편이 예상되는 회차의 <b>직전 날짜</b>입니다. "
            + "이 파일 하나로 열몇 회차를 집필하므로, 지난 뒤에도 통과하면 "
            + "낡은 기준으로 계속 쓰게 됩니다." },
        { name: "checked_by", label: "확인한 사람 (선택)", value: "" },
      ],
      ok: "확인했습니다", cancel: "취소",
    });
    if (!got) return;
    try {
      const r = await api(`/api/authoring/exams/${encodeURIComponent(id)}/confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true, ...got }),
      });
      toast(`확인 처리했습니다 — ${r.checked_at || ""}`);
    } catch (err) { toast("실패: " + err.message, "err"); return; }
  } else {
    const ok = await confirmModal({
      title: "미확인으로 되돌립니까?",
      body: "집필 화면이 다시 경고를 띄웁니다. 확인일은 지우지 않습니다 — "
        + "언제까지 유효했는지가 단서입니다.",
      ok: "되돌리기", cancel: "취소",
    });
    if (!ok) return;
    try {
      await api(`/api/authoring/exams/${encodeURIComponent(id)}/confirm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: false }),
      });
      toast("미확인으로 되돌렸습니다.");
    } catch (err) { toast("실패: " + err.message, "err"); return; }
  }
  await load();
}

async function exportOne(id) {
  try {
    const r = await api(`/api/authoring/exams/${encodeURIComponent(id)}`);
    const blob = new Blob([JSON.stringify(r.doc, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${id}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  } catch (e) { toast("꺼내지 못했습니다: " + e.message, "err"); }
}

/* ── 받기 — 붙여넣기 · 파일 ───────────────────────────────────────────── */
async function paste() {
  const got = await formModal({
    title: "JSON 받기",
    body: "Claude Code 창에서 만든 JSON 전문을 붙여 넣으세요. "
      + "<b>검증을 통과하지 않으면 저장되지 않습니다</b> — "
      + "과목 문항수 합이 회차 문항수와 달라도 거절합니다.",
    fields: [
      { name: "id", label: "파일 이름 (id)", required: true, placeholder: "adsp",
        pattern: "^[a-z0-9][a-z0-9\\-]{0,40}$",
        patternMsg: "영소문자·숫자·하이픈입니다.",
        hint: "<code>exams/&lt;id&gt;.json</code> 으로 저장됩니다. "
          + "<b>이미 있는 id 면 덮어씁니다</b>(바로 옆에 백업이 남습니다)." },
      { name: "doc", label: "JSON 전문", type: "textarea", required: true,
        placeholder: '{ "id": "adsp", … }' },
    ],
    ok: "검증하고 저장", cancel: "취소",
  });
  if (!got) return;
  await save(got.id.trim(), got.doc);
}

async function onFile(ev) {
  const f = ev.target.files && ev.target.files[0];
  ev.target.value = "";
  if (!f) return;
  const text = await f.text();
  // 파일 이름을 id 로 제안한다 — 사람이 다시 타이핑할 이유가 없다.
  const guess = f.name.replace(/\.json$/i, "").toLowerCase();
  const got = await formModal({
    title: `${f.name} 을 받습니다`,
    body: "검증을 통과하지 않으면 저장되지 않습니다.",
    fields: [
      { name: "id", label: "파일 이름 (id)", value: guess, required: true,
        pattern: "^[a-z0-9][a-z0-9\\-]{0,40}$",
        patternMsg: "영소문자·숫자·하이픈입니다." },
    ],
    ok: "검증하고 저장", cancel: "취소",
  });
  if (!got) return;
  await save(got.id.trim(), text);
}

async function save(id, text) {
  let doc;
  try {
    doc = JSON.parse(text);
  } catch (e) {
    // ★ 어디가 깨졌는지 말해 준다. "JSON 이 잘못됐습니다" 만으로는 못 고친다.
    toast("JSON 을 읽지 못했습니다 — " + e.message, "err");
    return;
  }
  try {
    const r = await api(`/api/authoring/exams/${encodeURIComponent(id)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doc }),
    });
    const w = (r.warnings || []).length;
    toast(`저장했습니다 — ${r.path || id}` + (w ? ` · 경고 ${w}건` : ""));
    if (w) {
      await confirmModal({
        title: "저장했지만 확인할 것이 있습니다",
        body: (r.warnings || []).map((x) => `· ${escapeHtml(x)}`).join("<br>"),
        ok: "닫기", cancel: "",
      });
    }
  } catch (e) {
    // 검증 실패는 여러 줄로 온다 — 토스트로는 다 안 보인다.
    await confirmModal({
      title: "저장하지 않았습니다",
      body: `<pre class="pb-cmd" style="white-space:pre-wrap">${escapeHtml(e.message)}</pre>`,
      ok: "닫기", cancel: "",
    });
    return;
  }
  await load();
}
