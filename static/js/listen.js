/* 듣기 검수 (v2) — #/listen/:kind/:key
 *
 * 여러 사람이 각자 자리에서 같은 과목을 듣고 장마다 [OK] · [고칠 곳] 을 남기는 화면.
 * 사내망에서는 `lan.bat` 으로 띄운 운영자 PC 에 http://<IP>:8871/#/listen/… 로 들어온다.
 * 보기 전용 공유에서도 이 판정 한 줄만은 저장된다(core/lan.py LAN_WRITABLE).
 *
 *   Space 재생/멈춤 · J 다음 · K 이전 · O OK(다음으로) · F 고칠 곳
 *
 * ★ 이름은 이 브라우저에만 둔다(localStorage). 로그인이 없는 사내 도구라, 판정 기록에
 *   남는 이름이 곧 누가 들었는가다.
 * ★ 소리는 영상과 같은 엔진으로 서버가 굽는다 — 처음 듣는 장은 20초 안팎 걸린다.
 *   운영자가 [미리듣기 미리 굽기] 를 해 두면 바로 나온다.
 */
"use strict";

import { api, el, escapeHtml, toast, formModal } from "./util.js";

const KEY_NAME = "xam.listen.name";
const S = { kind: "", key: "", doc: null, slides: [], i: 0, name: "", mine: {}, sum: null, root: null, audio: null };

export const meta = {
  title: "듣기 검수",
  subtitle: () => `${S.name ? S.name + " 님 · " : ""}Space 재생 · J 다음 · K 이전 · O 괜찮음 · F 고칠 곳`,
};

export async function mount(root, ctx) {
  S.root = root;
  S.kind = ctx.args[0] === "full" ? "full" : "summary";
  S.key = ctx.args[1];
  try { S.name = localStorage.getItem(KEY_NAME) || ""; } catch (_) {}
  if (!S.name) {
    const v = await formModal({ title: "검수자 이름", body: "판정 기록에 이 이름이 남습니다.",
      fields: [{ name: "name", label: "이름", required: true }], ok: "시작" });
    S.name = ((v && v.name) || "").trim() || "익명";
    try { localStorage.setItem(KEY_NAME, S.name); } catch (_) {}
  }
  const d = await api(`/api/lecture/${S.kind}/${S.key}`);
  if (!d.exists) { root.appendChild(el("div", "empty", "노트가 없습니다.")); return; }
  S.doc = d.doc;
  S.slides = d.doc.sections.flatMap((sec) => sec.slides.map((sl) => ({ ...sl, sec: sec.title })));
  const page = el("div", "page ls-page");
  page.innerHTML = `<div class="ls-top"><b>${escapeHtml(d.doc.title)}</b>
      <span class="muted">${S.kind === "full" ? "종합반" : "요약반"} · ${S.slides.length}장</span>
      <span class="ls-prog" id="ls-prog"></span>
      <button class="btn sm" id="ls-who" type="button">이름 바꾸기</button></div>
    <div class="ls-dots" id="ls-dots"></div>
    <div class="ls-card" id="ls-card"></div>`;
  root.appendChild(page);
  page.querySelector("#ls-who").addEventListener("click", () => {
    try { localStorage.removeItem(KEY_NAME); } catch (_) {}
    location.reload();
  });
  S.audio = new Audio();
  S.audio.preload = "auto";
  document.addEventListener("keydown", onKey);
  await refresh();
  const first = S.slides.findIndex((s) => S.mine[s.id] !== "ok");
  go(first < 0 ? 0 : first);
}

async function refresh() {
  S.sum = await api(`/api/lecture/${S.kind}/${S.key}/reviews?reviewer=${encodeURIComponent(S.name)}`);
  S.mine = S.sum.mine || {};
  const by = {};
  (S.sum.slides || []).forEach((r) => { by[r.id] = r; });
  S.by = by;
  const dots = document.getElementById("ls-dots");
  if (!dots) return;
  dots.innerHTML = "";
  S.slides.forEach((sl, i) => {
    const m = S.mine[sl.id];
    const d = el("button", "ls-dot" + (m === "ok" ? " ok" : m === "fix" ? " fix" : m === "stale" ? " stale" : "") + (i === S.i ? " cur" : ""));
    d.type = "button";
    d.title = `${sl.id} ${sl.title}`;
    d.addEventListener("click", () => go(i));
    dots.appendChild(d);
  });
  const mineOk = S.slides.filter((s) => S.mine[s.id] === "ok").length;
  document.getElementById("ls-prog").textContent =
    `내 OK ${mineOk}/${S.slides.length} · 전체 완료 ${S.sum.done}/${S.sum.total} (${S.sum.need}명씩)`;
}

function go(i) {
  S.i = Math.max(0, Math.min(S.slides.length - 1, i));
  const sl = S.slides[S.i];
  const card = document.getElementById("ls-card");
  const r = S.by[sl.id] || {};
  card.innerHTML = `<div class="ls-sec">${escapeHtml(sl.sec)}</div>
    <div class="ls-h"><span class="lc-id">${escapeHtml(sl.id)}</span><h2>${escapeHtml(sl.title)}</h2></div>
    <div class="ls-vis" id="ls-vis"></div>
    <div class="ls-sub">${escapeHtml(sl.say || "(자막 없음)")}</div>
    ${sl.read ? `<details class="ls-read"><summary>낭독(소리 나는 대로)</summary>${escapeHtml(sl.read)}</details>` : ""}
    <div class="ls-acts">
      <button class="btn" id="ls-play" type="button">▶ 듣기 (Space)</button>
      <button class="btn primary" id="ls-ok" type="button">괜찮음 (O)</button>
      <button class="btn" id="ls-fix" type="button">고칠 곳 (F)</button>
      <span class="muted">OK ${(r.ok || []).map(escapeHtml).join(", ") || "아직 없음"}${(r.fixes || []).length ? ` · 지적 ${(r.fixes || []).length}` : ""}</span>
    </div>
    <div class="ls-fixes" id="ls-fixes"></div>`;
  const vis = document.getElementById("ls-vis");
  const svgs = ((sl.body || "").match(/<svg\b[\s\S]*?<\/svg>/g) || []).concat(sl.fig ? [sl.fig] : []);
  svgs.slice(0, 2).forEach((s) => {
    const img = el("img", "lc-fig");
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(s);
    vis.appendChild(img);
  });
  (r.fixes || []).forEach((f) => {
    document.getElementById("ls-fixes").appendChild(el("div", "ls-fixrow",
      `${f.reviewer}: ${f.memo || ""}${f.suggest ? " → 낭독 수정안 있음" : ""}`));
  });
  document.getElementById("ls-play").addEventListener("click", toggle);
  document.getElementById("ls-ok").addEventListener("click", () => judge("ok"));
  document.getElementById("ls-fix").addEventListener("click", () => judge("fix"));
  S.audio.pause();
  S.audio.src = `/api/lecture/${S.kind}/${S.key}/audio/${encodeURIComponent(sl.id)}`;
  refresh();
}

function toggle() {
  if (S.audio.paused) {
    const b = document.getElementById("ls-play");
    if (b) b.textContent = "불러오는 중…";
    S.audio.play().then(() => { if (b) b.textContent = "❚❚ 멈춤 (Space)"; })
      .catch(() => { if (b) b.textContent = "▶ 듣기 (Space)"; toast("소리를 불러오지 못했습니다", "err"); });
  } else {
    S.audio.pause();
    const b = document.getElementById("ls-play");
    if (b) b.textContent = "▶ 듣기 (Space)";
  }
}

async function judge(verdict) {
  const sl = S.slides[S.i];
  let memo = "", suggest = "";
  if (verdict === "fix") {
    const v = await formModal({ title: `${sl.id} 고칠 곳`, body: "어디가 어떻게 들렸는지 적어 주세요. 고친 낭독을 적으면 운영자가 그대로 반영할 수 있습니다.",
      fields: [{ name: "memo", label: "들린 문제", placeholder: "예: '결정자' 가 '결정짜' 로 들림" },
               { name: "suggest", label: "낭독 수정안(선택)", value: sl.read || sl.say || "" }], ok: "남기기" });
    if (!v) return;
    memo = v.memo || "";
    suggest = (v.suggest || "").trim() === (sl.read || sl.say || "").trim() ? "" : v.suggest || "";
  }
  try {
    await api(`/api/lecture/${S.kind}/${S.key}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer: S.name, id: sl.id, verdict, memo, suggest }),
    });
    S.mine[sl.id] = verdict;
    if (verdict === "ok") go(S.i + 1); else { toast("남겼습니다."); go(S.i); }
  } catch (e) { toast(e.message, "err"); }
}

function onKey(e) {
  if (!document.getElementById("ls-card")) { document.removeEventListener("keydown", onKey); return; }
  if (e.target.closest && e.target.closest("input, textarea, select, .side-chat, .modal, [role=dialog]")) return;
  const k = e.key.toLowerCase();
  if (k === " ") { e.preventDefault(); toggle(); }
  else if (k === "j") go(S.i + 1);
  else if (k === "k") go(S.i - 1);
  else if (k === "o") judge("ok");
  else if (k === "f") judge("fix");
}
