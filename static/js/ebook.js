/* HTML 문제집 제작 — 회차마다 1단 시험지(HTML·PDF) + 자막·음성·발음 대본을 07/ 에 굽는다.
 *
 * ★ 3부의 영상·이북은 이 앱이 아니라 해설북(haeseolbook)이 만든다. 여기서는 그쪽이
 *   먹는 입력만 만든다 — 시험지 PDF · 정답표 · 문항별 대본(script/qNN.json).
 *   대본은 시험지 HTML 안에도 `<script id="xam-script">` 로 숨겨 넣는다.
 */
"use strict";

import { api, el, toast } from "./util.js";
import { actionBtn } from "./panel.js";

const S = { st: null, pick: new Set(), busy: false, ans: null };

export const meta = {
  title: () => "HTML 문제집 제작",
  subtitle: () => "1단 시험지와 자막·음성·발음 대본을 굽습니다. 영상·이북은 해설북에서 만듭니다.",
  actions: () => [
    actionBtn("폴더 열기", () => openDir(""), { iconName: "folder" }),
    actionBtn("새로고침", () => load(), { iconName: "refresh" }),
  ],
};

let ROOT = null;

export async function mount(root) {
  ROOT = el("div", "page");
  root.appendChild(ROOT);
  await load();
}

async function load() {
  try {
    S.st = await api("/api/ebook/status");
  } catch (e) {
    ROOT.innerHTML = "";
    ROOT.appendChild(el("div", "empty", e.message));
    return;
  }
  render();
}

function render() {
  const st = S.st;
  ROOT.innerHTML = "";
  const card = el("div", "card");
  card.appendChild(el("div", "card-title", `① 굽기 — _rounds → 07/ (${st.label || ""})`));

  const h = el("div", "field-hint");
  h.innerHTML = "회차마다 <code>exam.html</code>(1단 시험지, 대본을 안에 숨김) · <code>exam.pdf</code> · "
    + "<code>answers.json</code> · <code>script/qNN.json</code>(해설북 형식) · <code>script.html</code>(검수지) 를 만듭니다.<br>"
    + "정답·해설은 시험지에 보이지 않습니다. <b>검사</b> 열은 해설북의 대본 검사 기준(문장 길이·정답 문장·분량)을 미리 돌린 결과입니다.";
  card.appendChild(h);

  if (!st.rounds.length) {
    card.appendChild(el("div", "empty", "집필된 회차가 없습니다 — 1부 「문항 집필」 을 먼저 하세요."));
    ROOT.appendChild(card);
    return;
  }

  const bar = el("div", "row");
  bar.style.cssText = "gap:8px;margin:10px 0";
  const sel = S.pick.size;
  bar.appendChild(btn(sel ? `선택 ${sel}회차 굽기` : `전체 ${st.rounds.length}회차 굽기`,
    () => build([...S.pick]), { primary: true, disabled: S.busy }));
  bar.appendChild(btn("고친 회차만", () => build(st.rounds.filter((r) => !r.built_at || r.stale)
    .map((r) => r.round_code)), { disabled: S.busy }));
  if (S.busy) bar.appendChild(el("span", "muted", "굽는 중… (회차당 몇 초, PDF 포함)"));
  card.appendChild(bar);

  const t = el("table", "data");
  t.innerHTML = "<thead><tr><th></th><th>회차</th><th>문항</th><th>검사</th><th>PDF</th>"
    + "<th>구운 시각</th><th>보기</th></tr></thead>";
  const tb = el("tbody");
  st.rounds.forEach((r) => {
    const tr = el("tr");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = S.pick.has(r.round_code);
    cb.onchange = () => { cb.checked ? S.pick.add(r.round_code) : S.pick.delete(r.round_code); render(); };
    const td0 = el("td"); td0.appendChild(cb); tr.appendChild(td0);
    tr.appendChild(el("td", null, r.round_code));
    tr.appendChild(el("td", null, r.questions ? String(r.questions) : "—"));
    const chk = el("td");
    if (r.built_at) {
      chk.appendChild(chip(r.flagged ? `${r.flagged}문항 확인` : "통과", r.flagged ? "warn" : "ok"));
      if ((r.missing_figs || []).length) chk.appendChild(chip(`그림 ${r.missing_figs.length}개 없음`, "warn"));
    }
    tr.appendChild(chk);
    const pdf = el("td");
    if (r.built_at) pdf.appendChild(r.has_pdf ? chip("있음", "ok") : chip(r.pdf_error || "없음", "warn"));
    tr.appendChild(pdf);
    const when = el("td");
    when.textContent = r.built_at || "—";
    if (r.stale) when.appendChild(chip("원고가 더 새것", "warn"));
    tr.appendChild(when);
    const lk = el("td");
    if (r.built_at) {
      lk.appendChild(link("시험지", `/book/07/${r.round_code}/exam.html`));
      lk.appendChild(document.createTextNode(" · "));
      lk.appendChild(link("한글", `/book/07/${r.round_code}/exam.hwpx`));
      lk.appendChild(document.createTextNode(" · "));
      lk.appendChild(link("대본", `/book/07/${r.round_code}/script.html`));
      lk.appendChild(document.createTextNode(" · "));
      const o = el("a", null, "폴더");
      o.href = "#";
      o.onclick = (e) => { e.preventDefault(); openDir(r.round_code); };
      lk.appendChild(o);
    }
    tr.appendChild(lk);
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  card.appendChild(t);
  ROOT.appendChild(card);
  ROOT.appendChild(answersCard());
}

/* ② 교재 정답·해설편 — 문제편과 분리해 여러 회차를 한 권으로. 과목마다 해설 영상 QR */
function answersCard() {
  const card = el("div", "card");
  card.appendChild(el("div", "card-title", "② 교재 정답·해설편 — 07/_textbook/"));
  const h = el("div", "field-hint");
  h.innerHTML = "고른 회차(안 고르면 앞 5회차)의 <b>빠른 정답표 · 과목별 해설 영상 QR · 문항별 해설</b>을 46배판 한 권으로 모읍니다. "
    + "한글(.hwpx)도 같이 만들며 <code>07/_textbook/template.hwpx</code> 양식이 있으면 그 모양을 씁니다. "
    + "QR 주소는 <code>07/_textbook/videos.json</code>(해설북 스튜디오가 유튜브에 올리면 채움) — 없는 과목은 「영상 준비 중」 칸.";
  card.appendChild(h);
  const bar = el("div", "row");
  bar.style.cssText = "gap:8px;margin:10px 0;align-items:center";
  const picked = [...S.pick].sort();
  bar.appendChild(btn(picked.length ? `선택 ${picked.length}회차로 만들기` : "앞 5회차로 만들기", () => buildAnswers(picked),
    { primary: true, disabled: S.busy }));
  if (S.ans) {
    bar.appendChild(link("정답·해설편 보기", "/book/07/_textbook/" + S.ans.file.split(/[\/]/).pop()));
    if (S.ans.hwpx) bar.appendChild(link("한글(.hwpx)", "/book/07/_textbook/" + S.ans.hwpx.split(/[\/]/).pop()));
    if (S.ans.hwpx_error) bar.appendChild(chip(S.ans.hwpx_error, "warn"));
    if (S.ans.qr_missing && S.ans.qr_missing.length) bar.appendChild(chip(`QR 없음 ${S.ans.qr_missing.length}과목`, "warn"));
  }
  card.appendChild(bar);
  return card;
}

async function buildAnswers(rounds) {
  if (S.busy) return;
  S.busy = true;
  render();
  try {
    S.ans = await api("/api/ebook/answers", { method: "POST", body: { rounds } });
    toast(`${S.ans.rounds.length}회차 ${S.ans.questions}문항 정답·해설편을 만들었습니다`, "ok");
  } catch (e) {
    toast(e.message, "err");
  } finally {
    S.busy = false;
    render();
  }
}

async function build(rounds) {
  if (S.busy) return;
  S.busy = true;
  render();
  try {
    const r = await api("/api/ebook/build", { method: "POST", body: { rounds } });
    S.st = r;
    const err = r.results.filter((x) => x.error);
    const flag = r.results.reduce((n, x) => n + (x.flagged || 0), 0);
    toast(err.length ? `${err.length}회차 실패: ${err[0].error}`
                     : `${r.results.length}회차 구웠습니다` + (flag ? ` — 검사에 걸린 문항 ${flag}개` : ""),
          err.length ? "err" : "ok");
  } catch (e) {
    toast(e.message, "err");
  } finally {
    S.busy = false;
    render();
  }
}

async function openDir(rc) {
  try { await api("/api/ebook/open", { method: "POST", body: { round: rc } }); }
  catch (e) { toast(e.message, "err"); }
}

function chip(t, cls) { return el("span", "status-chip " + (cls || ""), t); }

function link(t, href) {
  const a = el("a", null, t);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}

function btn(label, fn, { primary, disabled } = {}) {
  const b = el("button", "btn" + (primary ? " primary" : ""), label);
  b.type = "button";
  b.disabled = !!disabled;
  b.addEventListener("click", fn);
  return b;
}
