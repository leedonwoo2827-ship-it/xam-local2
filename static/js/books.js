/* 작업 폴더 — 품목 전환 = 폴더 권한
 *
 * ★ UX 규칙대로 목록이니 위층 패널이다.  #/books
 *   Claude Code 데스크탑처럼 OS 네이티브 폴더 선택창으로 권한을 주고, 고른 폴더만 쓴다.
 *
 * ★ 폴더를 바꾸면 /book 정적 마운트도 서버에서 같이 갈린다(books_routes 의 rebind).
 *   안 갈면 폴더는 바뀌는데 mp4·이미지·PDF 가 옛 폴더에서 나온다.
 */
"use strict";

import { $, api, el, escapeHtml, toast, confirmModal, formModal } from "./util.js";
import { icon, hydrateIcons } from "./icons.js";
import { actionBtn } from "./panel.js";

const B = { data: null, busy: false };

/* 폴더가 어느 단계까지 왔는지. "완성된 책" 만 쓸 수 있으면 안 된다 —
 * #1 로 01/ 만 만들고 #2 를 돌리기 직전인 폴더가 정상적인 작업 상태다. */
const STAGE = {
  empty: { label: "빈 폴더", tone: "idle" },
  raw:   { label: "00/ 원본 PDF", tone: "info" },
  scan:  { label: "01/ 기출까지", tone: "info" },
  edit:  { label: "02/ 문항까지", tone: "" },
  video: { label: "05/ 영상까지", tone: "ok" },
};

export const meta = {
  title: "작업 폴더",
  subtitle: "이 앱이 읽고 쓸 폴더를 지정합니다. 고르면 그 품목으로 전환됩니다.",
  actions: () => [
    actionBtn("폴더 추가", () => pickAndAdd(), { primary: true, iconName: "plus", id: "bk-add" }),
    actionBtn("다시 스캔", () => refresh(), { iconName: "refresh" }),
  ],
};

export async function mount(root, ctx) {
  root.innerHTML = `
    <div class="bk-list" id="bk-list"><div class="empty">불러오는 중…</div></div>
    <div id="bk-conn" hidden></div>
    <div class="field-hint" id="bk-note"></div>
  `;
  hydrateIcons(root);
  await refresh();
  drawConn();          // ★ 폴더 목록을 막지 않는다 — 기다리지 않고 따로 채운다
}

/* ── 연결 — 집필이 무슨 자격으로 나가는지 ──────────────────────────────────
 *
 * ★ 여기에 둔다. 폴더를 고르는 화면이 곧 "이 앱이 무엇을 쓰는가" 를 정하는 자리고,
 *   문항 집필 화면까지 들어가야만 보이면 **로그인이 안 된 것을 집필을 누른 뒤에야**
 *   알게 된다. 과목 하나가 10~20분짜리라 그때 알면 늦다.
 * ★ 모델을 부르지 않는다(`/status` 는 무료·즉시). 화면을 열 때마다 과금될 수 없다.
 */
async function drawConn() {
  const box = $("#bk-conn");
  if (!box) return;
  // 집필 라우트가 없는 서버(옛 프로세스)면 조용히 접는다 — 폴더 화면의 본업이 아니다.
  const st = await api("/api/authoring/status").catch(() => null);
  if (!st) { box.hidden = true; return; }

  const on = st.installed && st.credentials;
  const rows = [];
  rows.push(kv("CLI", st.installed
    ? `<code>${escapeHtml(st.path || "")}</code>`
    : `<b class="bad">찾지 못했습니다</b> — Claude Code 를 설치하거나 `
      + `<code>CLAUDE_CLI</code> 로 실행 파일 경로를 지정하십시오.`));
  rows.push(kv("로그인", st.credentials
    ? `있습니다 <span class="muted">(~/.claude/.credentials.json · 구독 OAuth)</span>`
    : `<b class="bad">없습니다</b> — Claude Code 에서 한 번 로그인하십시오.`));
  // ★ 켜져 있으면 반드시 말해 준다. 이 앱은 자식 환경에서 비워 무력화하지만,
  //   "왜 내 계정에 안 찍히지" 를 물을 때 짚을 곳이 필요하다.
  if (st.api_key_env) {
    rows.push(kv("주의", `<b class="bad">ANTHROPIC_API_KEY 가 설정돼 있습니다.</b> `
      + `이 앱은 무시하고 구독 로그인으로 나가지만, 다른 도구는 이 키로 과금될 수 있습니다.`));
  }

  box.hidden = false;
  box.innerHTML = `
    <div class="section-label">연결</div>
    <div class="bk-conn-card">
      <span class="badge ${on ? "ok" : "err"}">${
        on ? "Claude Code 로그인됨" : st.installed ? "로그인 필요" : "CLI 없음"}</span>
      <div class="kvs">${rows.join("")}</div>
      <div class="field-hint">API 키를 쓰지 않습니다. <b>이 PC 의 구독 로그인</b>으로 나가므로
        사용량과 한도가 사람별로 갈립니다.</div>
    </div>`;
}

const kv = (k, v) => `<div class="kv"><span class="kv-k">${escapeHtml(k)}</span>`
                   + `<span class="kv-v">${v}</span></div>`;

async function refresh() {
  try {
    B.data = await api("/api/books");
  } catch (e) {
    const box = $("#bk-list");
    if (box) {
      box.innerHTML = "";
      box.appendChild(el("div", "empty", "불러오지 못했습니다: " + e.message));
    }
    return;
  }
  render();
}

function render() {
  const box = $("#bk-list");
  if (!box) return;
  box.innerHTML = "";

  // ★ 최근에 등록한 폴더가 위로 온다. `data/books.json` 은 **추가한 순서**라
  //   그대로 그리면 방금 넣은 폴더가 맨 아래 — 목록이 스크롤 상자라 화면 밖에
  //   앉는다(실측 2026-09-07: ADSP 를 등록했는데 위의 죽은 폴더 둘에 가렸다).
  // ★ 뒤집는 것은 **여기 화면뿐**이다. 서버 순서는 그대로 둔다 — 첫 실행 화면이
  //   `items[0]` 을 '.env 의 기본값' 으로 쓰기 때문이다(static/js/home.js).
  B.data.items.slice().reverse().forEach((it) => {
    const card = el("div", "bk" + (it.active ? " on" : "") + (it.usable ? "" : " bad"));

    const ico = el("span", "icon-box" + (it.active ? "" : it.usable ? "" : " err"));
    ico.appendChild(icon("folder", 16));
    card.appendChild(ico);

    const mid = el("div", "bk-mid");
    const name = el("div", "bk-name");
    name.appendChild(el("span", null, it.label || "(이름 없음)"));
    if (it.active) name.appendChild(el("span", "badge brand", "사용 중"));
    if (!it.exists) name.appendChild(el("span", "badge err", "폴더 없음"));
    else if (!it.usable) name.appendChild(el("span", "badge warn", "작업할 것이 없음"));
    else name.appendChild(el("span", "badge " + STAGE[it.stage].tone, STAGE[it.stage].label));
    mid.appendChild(name);
    mid.appendChild(el("div", "bk-path", it.path));

    // 회차 — _rounds 스캔값이라 3회든 21회든 그대로 뜬다
    const nums = el("div", "bk-nums");
    // ★ pd 는 발행 때 어느 라이브 품목을 덮어쓸지 정하는 값이다. 추측하지 않는다.
    if (!it.pd) {
      const b = el("span", "badge warn", "품목 코드 없음");
      b.title = "발행할 때 --pd 로 나가는 값입니다. 정해 두지 않으면 발행만 막힙니다.";
      nums.appendChild(b);
    } else {
      const b = el("span", "badge " + (it.pd_confirmed ? "" : "warn"), `pd=${it.pd}`);
      if (!it.pd_confirmed) b.title = "폴더 안 _book.json 에 굳어 있지 않은 값입니다.";
      nums.appendChild(b);
    }
    nums.appendChild(el("span", "badge " + (it.rounds.length ? "" : "idle"),
      `${it.rounds.length}회차`));
    nums.appendChild(el("span", "badge " + (it.questions ? "" : "idle"),
      `${it.questions || 0}문항`));
    const st = it.stages || {};
    if ((st["01"] || {}).md) nums.appendChild(el("span", "badge", `기출 ${st["01"].md}`));
    if ((st["05"] || {}).bundles) {
      const b = st["05"];
      nums.appendChild(el("span", "badge " + (b.mp4 === b.bundles ? "ok" : "warn"),
        `영상 ${b.mp4}/${b.bundles}`));
    }
    if ((st["06"] || {}).files) nums.appendChild(el("span", "badge info", `발행물 ${st["06"].files}`));
    mid.appendChild(nums);

    if (it.rounds.length) {
      const rl = el("div", "bk-rounds");
      it.rounds.forEach((r) => {
        rl.appendChild(el("span", "bk-round",
          `${r.code} ${r.label || ""} ${r.questions}문`.trim()));
      });
      mid.appendChild(rl);
    }
    // 과목명 — 이 폴더가 어느 책인지 판단하는 근거. 폴더 이름은 근거가 못 된다.
    if ((it.subjects || []).length) {
      mid.appendChild(el("div", "field-hint", "과목: " + it.subjects.join(" · ")));
    }
    // ── OCR 판독 폴더 ──
    // BOOK 밖에 있고 Claude Code 창과 이 앱이 같이 쓰는 폴더라서 따로 지정한다.
    // 지정이 없으면 BOOK 이름에서 유도한 값을 쓴다 — 그게 뭔지 보여 줘야 한다.
    const ocr = el("div", "field-hint" + (it.ocr_ok ? "" : " bad"));
    ocr.appendChild(el("span", null,
      (it.ocr ? "판독 폴더(지정): " : "판독 폴더(유도): ")
      + (it.ocr_effective || "(없음)")
      + (it.ocr_ok ? "" : "  ← data\\raw_pages 가 없습니다")));
    mid.appendChild(ocr);

    if (it.error) mid.appendChild(el("div", "field-hint bad", it.error));
    card.appendChild(mid);

    const acts = el("div", "bk-acts");
    if (!it.active) {
      const use = el("button", "btn sm primary", "이 폴더 쓰기");
      use.type = "button";
      use.disabled = !it.usable;
      use.title = it.usable ? "" : "빈 폴더입니다. 00/ 에 원본 PDF 를 넣거나, 01/ · _rounds/ 가 있는 폴더를 고르세요.";
      use.addEventListener("click", (e) => { e.stopPropagation(); select(it); });
      acts.appendChild(use);
    }
    const ren = el("button", "btn sm", "이름·품목");
    ren.type = "button";
    ren.title = "표시 이름과 품목 코드(pd)를 고칩니다.";
    ren.addEventListener("click", (e) => { e.stopPropagation(); editMeta(it); });
    acts.appendChild(ren);

    const ocrBtn = el("button", "btn sm" + (it.ocr_ok ? "" : " warn"), "판독 폴더");
    ocrBtn.type = "button";
    ocrBtn.title = "도구 #1 의 스캔 PNG · 초안 JSON 이 있는 폴더를 지정합니다.";
    ocrBtn.addEventListener("click", (e) => { e.stopPropagation(); pickOcr(it); });
    acts.appendChild(ocrBtn);

    const open = el("button", "btn sm", "폴더 열기");
    open.type = "button";
    open.addEventListener("click", (e) => { e.stopPropagation(); openFolder(it.path); });
    acts.appendChild(open);

    if (B.data.items.length > 1) {
      const del = el("button", "btn sm", "목록에서 빼기");
      del.type = "button";
      del.addEventListener("click", (e) => { e.stopPropagation(); remove(it); });
      acts.appendChild(del);
    }
    card.appendChild(acts);

    if (!it.active && it.usable) {
      card.style.cursor = "pointer";
      card.addEventListener("click", () => select(it));
    }
    box.appendChild(card);
  });

  // 폴더 추가 카드
  const add = el("div", "bk-add");
  add.setAttribute("role", "button");
  add.tabIndex = 0;
  const ai = el("span", "icon-box");
  ai.appendChild(icon("plus", 16));
  add.appendChild(ai);
  const am = el("div");
  am.appendChild(el("b", null, "폴더 추가"));
  am.appendChild(el("div", "bk-path", "탐색기로 골라서 권한을 줍니다"));
  add.appendChild(am);
  add.addEventListener("click", () => pickAndAdd());
  add.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickAndAdd(); }
  });
  box.appendChild(add);

  const note = $("#bk-note");
  if (note) {
    note.innerHTML =
      "· <b>새 문제집을 시작하려면</b> 빈 폴더를 하나 만들고 그 안에 <code>00</code> 폴더를 "
      + "만들어 원본 PDF 를 넣으세요. 그 <b>바깥 폴더</b>를 고르면 됩니다 — "
      + "<code>00</code> 폴더 자체를 고르는 게 아닙니다.<br>"
      + "· 폴더를 지정하면 <code>_rounds/*.json</code> 을 스캔해 <b>회차 수를 자동으로 인식</b>합니다. "
      + "3회차든 9회차든 21회차든, 초기에 1~2회차만 있어도 그대로 뜹니다.<br>"
      + "· <b>완성된 책만 쓸 수 있는 게 아닙니다.</b> <code>01/</code> 만 있는 폴더 — #1 을 돌리고 "
      + "#2 를 돌리기 직전 — 도 정상적인 작업 상태이고, '구조화 MD로 정리' 화면이 됩니다.<br>"
      + "· <code>pd</code> 는 발행할 때 <code>--pd</code> 로 나가 <b>어느 라이브 품목을 덮어쓸지</b> "
      + "정합니다. 그래서 <b>폴더 이름으로 추측하지 않습니다</b> — 모르면 비워 두세요. "
      + "편집·렌더는 그대로 되고 발행만 막힙니다. 확정한 값만 폴더 안 "
      + "<code>_book.json</code> 에 남아 폴더를 옮겨도 따라옵니다.<br>"
      + "· 어느 책인지는 <b>과목명</b>으로 판단하세요. 폴더 이름은 근거가 못 됩니다.<br>"
      + "· 전환하면 모든 화면과 <b>렌더·빌드 대상</b>이 그 폴더로 바뀝니다. "
      + "두 품목의 데이터는 섞이지 않습니다.";
  }
}

/* ── OS 네이티브 폴더 선택창 → 등록 ── */
async function pickAndAdd() {
  if (B.busy) return;
  B.busy = true;
  const btn = $("#bk-add");
  if (btn) btn.disabled = true;
  toast("폴더 선택창을 띄웠습니다. 창이 안 보이면 작업 표시줄을 확인하세요.");
  try {
    const r = await api("/api/books/pick", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!r.picked) { toast("취소했습니다."); return; }

    const sc = r.scan || {};
    if (!sc.usable) {
      await confirmModal({
        title: "이 폴더에는 작업할 것이 없습니다",
        body: `<pre class="pb-cmd">${escapeHtml(r.picked)}</pre><br>`
          + "이 폴더 안이 비어 있습니다. <b>새 문제집이면</b> 여기에 <code>00</code> 폴더를 "
          + "만들어 원본 PDF 를 넣고 다시 고르세요 — 그게 시작 상태입니다.<br>"
          + "<b>이미 진행 중이면</b> <code>01/</code> 에 문항 md 가 있거나 "
          + "<code>_rounds/</code> 가 있는 폴더입니다.<br>"
          + "<span class='muted'>고를 것은 <code>00</code> 폴더가 아니라 그것을 "
          + "<b>담고 있는 바깥 폴더</b>입니다.</span>",
        ok: "닫기", cancel: "",
      });
      return;
    }

    // ★ pd 를 폴더 이름으로 추측하지 않는다. 모르면 사람에게 묻는다.
    const st = sc.stages || {};
    const where = { empty: "빈 폴더", raw: "00/ 원본 PDF", scan: "01/ 기출까지",
                    edit: "02/ 문항까지", video: "05/ 영상까지" }[sc.stage] || sc.stage;
    const subj = (sc.subjects || []).length
      ? `과목 <b>${escapeHtml(sc.subjects.join(" · "))}</b><br>` : "";
    const got = await formModal({
      title: "이 폴더에 권한을 줄까요?",
      body: `<pre class="pb-cmd">${escapeHtml(r.picked)}</pre><br>`
        + `단계 <b>${escapeHtml(where)}</b> · 회차 <b>${(sc.rounds || []).length}</b> · `
        + `문항 <b>${sc.questions || 0}</b>`
        + (st["00"] && st["00"].pdf ? ` · 원본 PDF <b>${st["00"].pdf}</b>` : "")
        + (st["01"] ? ` · 기출 md <b>${st["01"].md || 0}</b>` : "")
        + (st["05"] && st["05"].bundles ? ` · 영상 번들 <b>${st["05"].bundles}</b>` : "")
        + `<br>${subj}<br>이 앱은 지정한 폴더만 읽고 씁니다.`,
      fields: [
        { name: "label", label: "표시 이름", value: r.label || "", required: true },
        { name: "pd", label: "품목 코드 (pd) — 모르면 비워 두세요",
          value: r.pd || "", placeholder: "bigdata",
          pattern: "^[a-z0-9\\-]{1,20}$",
          patternMsg: "소문자·숫자·하이픈 20자 이내입니다.",
          hint: r.pd
            ? "폴더 안 <code>_book.json</code> 에서 읽은 값입니다."
            : "<b>발행 대상</b>입니다. 틀리면 그 품목의 라이브 문제은행을 덮어씁니다 — "
              + "비워 두면 발행만 막히고 편집·렌더는 그대로 됩니다." },
      ],
      ok: "권한 주고 추가", cancel: "취소",
    });
    if (!got) return;

    const added = await api("/api/books/add", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: r.picked, label: got.label, pd: got.pd }),
    });
    toast(`추가했습니다 — ${added.label}`
      + (added.pd ? ` (pd=${added.pd})` : " · 품목 코드는 발행 전에 정하세요"));
    await refresh();
  } catch (e) {
    toast("폴더를 추가하지 못했습니다: " + e.message, "err");
  } finally {
    B.busy = false;
    const b = $("#bk-add");
    if (b) b.disabled = false;
  }
}

/* 표시 이름은 이 앱 안에서만 쓰는 값이라 자유롭게 바꿔도 된다.
 * pd 는 다르다 — 발행 때 --pd 로 나가서 어느 라이브 품목을 덮어쓸지 정한다. */
async function editMeta(it) {
  const subj = (it.subjects || []).length
    ? `이 폴더의 과목은 <b>${escapeHtml(it.subjects.join(" · "))}</b> 입니다.<br>`
    : "";
  const r = await formModal({
    title: "이름·품목 고치기",
    body: `<pre class="pb-cmd">${escapeHtml(it.path)}</pre><br>${subj}`
      + "표시 이름은 이 앱 안에서만 씁니다. <b>품목 코드는 발행 대상</b>이라 "
      + "틀리면 그 품목의 라이브 문제은행을 덮어씁니다 — 되돌릴 수 없습니다.",
    fields: [
      { name: "label", label: "표시 이름", value: it.label, required: true,
        hint: "레일 아래 칩과 목록에 보이는 이름입니다." },
      { name: "pd", label: "품목 코드 (pd)", value: it.pd,
        placeholder: "bigdata",
        pattern: "^[a-z0-9\\-]{1,20}$",
        patternMsg: "소문자·숫자·하이픈 20자 이내입니다. 언더바는 쓸 수 없습니다.",
        hint: "서버 <code>ex_product.pd_id</code> 와 같은 값. 비워 두면 발행만 막히고 "
          + "편집·렌더는 그대로 됩니다." },
    ],
    ok: "저장", cancel: "취소",
  });
  if (!r) return;

  if (r.pd && r.pd !== it.pd) {
    const ok = await confirmModal({
      title: "발행 대상을 바꿉니다",
      body: `품목 코드를 <b>${escapeHtml(it.pd || "(없음)")}</b> → `
        + `<b>${escapeHtml(r.pd)}</b> 로 바꿉니다.<br><br>`
        + `다음 발행은 <code>--pd ${escapeHtml(r.pd)}</code> 로 나가고, `
        + `<code>pr_key</code> 가 겹치는 행을 UPDATE 합니다. `
        + "그 품목이 맞는지 확인하세요.",
      ok: "바꾸기", cancel: "취소", danger: true,
    });
    if (!ok) return;
  }

  try {
    const d = await api("/api/books/meta", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: it.path, label: r.label, pd: r.pd }),
    });
    toast(d.wrote_book_json
      ? `저장했습니다 — 폴더의 _book.json 에도 pd=${d.pd} 를 남겼습니다.`
      : "저장했습니다.");
    window.dispatchEvent(new CustomEvent("xam:book-changed", { detail: { path: it.path } }));
    await refresh();
  } catch (e) {
    toast("고치지 못했습니다: " + e.message, "err");
  }
}

async function select(it) {
  if (it.active) return;
  const ok = await confirmModal({
    title: "이 폴더로 전환할까요?",
    body: `<b>${escapeHtml(it.label)}</b> (pd=<code>${escapeHtml(it.pd)}</code>)<br>`
      + `<pre class="pb-cmd">${escapeHtml(it.path)}</pre><br>`
      + "모든 화면과 <b>렌더·빌드 대상</b>이 이 폴더로 바뀝니다.",
    ok: "전환", cancel: "취소",
  });
  if (!ok) return;
  try {
    const r = await api("/api/books/select", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: it.path }),
    });
    toast(`${it.label} 로 전환했습니다.`
      + (r.remounted ? "" : " (경고: /book 마운트가 갱신되지 않았습니다 — 재시작하세요)"),
      r.remounted ? "" : "err");
    // 셸의 품목 칩과 진행률을 다시 읽는다
    window.dispatchEvent(new CustomEvent("xam:book-changed", { detail: { path: it.path } }));
    await refresh();
  } catch (e) {
    toast("전환하지 못했습니다: " + e.message, "err");
  }
}

async function remove(it) {
  const ok = await confirmModal({
    title: "목록에서 뺄까요?",
    body: `<b>${escapeHtml(it.label)}</b><br><pre class="pb-cmd">${escapeHtml(it.path)}</pre><br>`
      + "폴더와 파일은 그대로 남습니다. 이 앱의 목록에서만 사라집니다.",
    ok: "빼기", cancel: "취소", danger: true,
  });
  if (!ok) return;
  try {
    await api("/api/books/remove", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: it.path }),
    });
    toast("목록에서 뺐습니다.");
    window.dispatchEvent(new CustomEvent("xam:book-changed", {}));
    await refresh();
  } catch (e) {
    toast("빼지 못했습니다: " + e.message, "err");
  }
}

/** OCR 판독 폴더 지정 — OS 네이티브 선택창.
 *
 * BOOK 과 별개로 두는 이유: 판독 작업물(스캔 PNG · 초안 JSON)은 BOOK 트리 밖의
 * 도구 #1 프로젝트 안에 있고, 그 폴더는 Claude Code 창과 이 앱이 같이 쓴다.
 * 지정을 지우면 BOOK 이름에서 유도로 되돌아간다.
 */
async function pickOcr(it) {
  const go = await confirmModal({
    title: "판독 폴더를 지정할까요?",
    body: `<b>${escapeHtml(it.label || it.path)}</b><br>`
      + `지금 쓰는 값: <pre class="pb-cmd">${escapeHtml(it.ocr_effective || "(없음)")}</pre>`
      + (it.ocr ? "" : "<p class='muted'>이 값은 작업 폴더 이름에서 <b>유도</b>한 것입니다.</p>")
      + "<p>도구 #1 의 <code>data\\raw_pages</code> · <code>data\\ocr_draft</code> 가 "
      + "들어 있는 폴더를 고르세요. 판독도 이 앱이 합니다([스캔 판독]) — 그 초안을 "
      + "검수해 <code>01/</code> 로 확정합니다.</p>",
    ok: "폴더 고르기", cancel: it.ocr ? "지정 지우기" : "취소",
  });
  try {
    if (go) {
      const r = await api("/api/books/ocr", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: it.path, pick: true }),
      });
      if (r.cancelled) return;
      toast("판독 폴더를 지정했습니다.");
    } else if (it.ocr) {
      await api("/api/books/ocr", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: it.path, ocr: "" }),
      });
      toast("지정을 지웠습니다 — 작업 폴더 이름에서 유도합니다.");
    } else {
      return;
    }
    await refresh();
  } catch (e) {
    toast("판독 폴더 지정 실패: " + e.message, "err");
  }
}

async function openFolder(path) {
  try {
    await api("/api/books/open", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    toast("탐색기에서 열었습니다.");
  } catch (e) {
    toast("폴더를 열지 못했습니다: " + e.message, "err");
  }
}
