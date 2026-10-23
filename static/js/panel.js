/* 부유 패널 — 베이스 레이어 위에 스킬·앱 창이 살짝 떠 있는 구조.
 *
 * 왜 이렇게 하나: 예전에는 화면을 옮길 때마다 본문을 통째로 갈아치웠다. 그래서 문서를
 * 생성하는 중에 스킬 목록을 열어 보면 폴링이 끊기고 채팅 이력이 날아갔다. 패널은 베이스를
 * 언마운트하지 않고 그 위에 뜨기 때문에 작업 상태가 그대로 살아 있다.
 *
 * 패널 안은 다시 2열이다 — 좌측 이너 레일(자기 그룹의 화면 목록) + 우측 콘텐츠.
 */
"use strict";

import { $, el, html, escapeHtml } from "./util.js";
import { icon, iconHtml } from "./icons.js";

let layer = null;      // #panel-layer
let onClose = null;    // 닫힘을 셸에 알리는 콜백
let lastFocus = null;  // 열기 직전 포커스 — 닫을 때 되돌려 준다
let bound = false;

/** 패널 그룹 정의. 이너 레일 항목은 전부 기존 해시 라우트를 그대로 가리킨다. */
/* 패널은 "보고 닫는" 표면만 맡는다. 미저장 텍스트를 든 화면은 바탕에 둔다 —
 * 패널은 Esc·스크림 클릭으로 닫히도록 설계돼 있어 편집이 날아간다. */
export const GROUPS = {
  books: {
    title: "작업 폴더",
    subtitle: "이 앱이 읽고 쓸 폴더를 지정합니다.",
    sections: [],
  },
  ocr: {
    title: "OCR 검수 · 페이지",
    subtitle: "00/ 의 PDF → [PDF 렌더] 로 스캔을 뜨고 → [스캔 판독] 으로 읽습니다. 고르면 아래 작업창에서 열립니다.",
    sections: [],
  },
  scan: {
    title: "OCR 본문",
    subtitle: "고르면 아래 작업창에서 열립니다. 01/*.md 를 쓰는 단계입니다.",
    sections: [],
  },
  questions: {
    title: "문항",
    subtitle: "고르면 아래 작업창에서 열립니다. _rounds · 02/ · 05/lesson 을 함께 쓰니다.",
    sections: [],
  },
  video: {
    title: "영상 번들",
    subtitle: "고르면 아래 작업창에서 열립니다. 이 창을 닫어도 렌더 폴링은 살아 있습니다.",
    sections: [],
  },
  summary: {
    title: "요약노트 원본",
    subtitle: "발행에 실제로 쓰이는 .html 입니다.",
    sections: [],
  },
};

/* ── 셸 골격 ──────────────────────────────────────── */
function ensureLayer() {
  if (layer) return layer;
  layer = $("#panel-layer");
  layer.appendChild(html(`
    <div class="panel-scrim" data-panel-dismiss></div>
  `));
  layer.appendChild(html(`
    <section class="panel" role="dialog" aria-modal="true" aria-labelledby="panel-title">
      <nav class="panel-rail" id="panel-rail" aria-label="화면 목록"></nav>
      <div class="panel-main">
        <header class="panel-head">
          <div>
            <h2 id="panel-title"></h2>
            <p id="panel-sub"></p>
          </div>
          <div class="panel-actions" id="panel-actions"></div>
          <button class="panel-close" id="panel-close" type="button"
                  title="닫기 (Esc)" aria-label="닫기">${iconHtml("close", 16)}</button>
        </header>
        <div class="panel-body" id="panel-body" tabindex="-1"></div>
      </div>
    </section>
  `));
  bindOnce();
  return layer;
}

function bindOnce() {
  if (bound) return;
  bound = true;
  $("#panel-close").addEventListener("click", () => requestClose());
  layer.addEventListener("click", (e) => {
    if (e.target.hasAttribute("data-panel-dismiss")) requestClose();
  });
  document.addEventListener("keydown", (e) => {
    if (isOpen() && e.key === "Escape") { e.preventDefault(); requestClose(); }
  });
}

/* 스크림 뒤 베이스로 포커스가 새지 않게 베이스 전체를 inert 로 만든다.
 * 직접 Tab 을 가로채는 방식은 못 쓴다 — 크롬은 스크롤 가능한 div(.table-wrap 등)에도
 * tabindex 없이 포커스를 주기 때문에 "마지막 요소"를 코드로 맞출 수가 없다.
 * inert 는 그 안의 모든 것을 포커스·클릭 대상에서 빼므로 Tab 이 자연히 패널 안에서만 돈다. */
function setBaseInert(on) {
  // ★ v2: `.app` 전체가 아니라 레일·바탕만 잠근다. 우측 채팅(.chat)은 패널이 떠 있어도
  //   써야 한다 — 목록 창을 띄워 둔 채 그 목록에 대해 묻는 것이 채팅의 주된 쓰임이다.
  for (const node of document.querySelectorAll(".app > .rail, .app > .content")) {
    if (on) node.setAttribute("inert", "");
    else node.removeAttribute("inert");
  }
}

export function isOpen() { return !!layer && !layer.hidden; }

/** 닫기 요청 — 실제 닫기는 셸(라우터)이 해시를 되돌리며 처리한다. */
function requestClose() {
  if (onClose) onClose();
}

/** 셸이 "닫기를 눌렀을 때 무엇을 할지"를 등록한다. */
export function setCloseHandler(fn) { onClose = fn; }

/* ── 열기 / 닫기 ──────────────────────────────────── */

/**
 * 패널을 띄운다(이미 떠 있으면 내용만 갱신 — 이너 레일 이동 시 창이 다시 튀지 않는다).
 * @returns {{body: HTMLElement, rail: HTMLElement, setHead: Function}}
 */
export function openPanel({ group, path, title, subtitle }) {
  ensureLayer();
  const wasOpen = isOpen();
  if (!wasOpen) {
    lastFocus = document.activeElement;
    layer.hidden = false;
    document.body.style.overflow = "hidden";   // 배경 스크롤 잠금
    setBaseInert(true);
  }

  const g = GROUPS[group] || { title: title || "", subtitle: "", sections: [] };
  setHead(title || g.title, subtitle != null ? subtitle : g.subtitle);
  $("#panel-actions").innerHTML = "";
  renderRail(group, path);

  const body = $("#panel-body");
  body.innerHTML = "";
  body.scrollTop = 0;
  return { body, rail: $("#panel-rail"), setHead, setActions, focusBody: () => body.focus({ preventScroll: true }) };
}

export function closePanel() {
  if (!isOpen()) return;
  layer.hidden = true;
  $("#panel-body").innerHTML = "";
  document.body.style.overflow = "";
  setBaseInert(false);
  // inert 를 풀기 전에 포커스를 되돌리면 먹지 않으므로 순서를 지킨다
  if (lastFocus && lastFocus.isConnected) lastFocus.focus({ preventScroll: true });
  lastFocus = null;
}

export function setHead(title, subtitle) {
  $("#panel-title").textContent = title || "";
  const sub = $("#panel-sub");
  sub.textContent = subtitle || "";
  sub.hidden = !subtitle;
}

/** 패널 헤더 우측 액션 버튼들. 화면 모듈의 meta.actions() 가 돌려준 요소를 받는다. */
export function setActions(nodes) {
  const box = $("#panel-actions");
  box.innerHTML = "";
  (Array.isArray(nodes) ? nodes : [nodes]).filter(Boolean).forEach((n) => box.appendChild(n));
}

/* ── 이너 레일 ────────────────────────────────────── */
function renderRail(group, activePath) {
  const rail = $("#panel-rail");
  rail.innerHTML = "";
  const g = GROUPS[group];
  // 목록이 없으면 레일 칼럼을 아예 접는다(앱 피커는 카드 그리드가 곧 목록이다).
  // 스킬처럼 런타임에 채우는 경우도 있어서, setRailSections 가 다시 그릴 때 갱신된다.
  layer.querySelector(".panel").classList.toggle("no-rail", !g || !g.sections.length);
  if (!g) return;
  g.sections.forEach((sec) => {
    if (sec.label) rail.appendChild(el("div", "panel-rail-title", sec.label));
    sec.items.forEach((it) => {
      // 라우트가 있으면 링크(딥링크·새 탭이 되어야 한다), 없으면 화면 안에서만 쓰는 버튼.
      const cls = "panel-rail-item" + (it.path && it.path === activePath ? " active" : "");
      const node = it.path ? el("a", cls) : el("button", cls);
      if (it.path) node.href = "#" + it.path;
      else node.type = "button";
      node.appendChild(icon(it.icon || "file", 15));
      node.appendChild(el("span", "pr-label", it.label));
      if (it.count != null) node.appendChild(el("span", "pr-count", String(it.count)));
      rail.appendChild(node);
    });
  });
}

/**
 * 스킬 패널처럼 레일을 런타임에 채워야 하는 경우 — 항목을 갈아끼우고 다시 그린다.
 * items: [{ path, icon, label, count }]
 */
export function setRailSections(group, sections, activePath) {
  if (!GROUPS[group]) return;
  GROUPS[group].sections = sections;
  if (isOpen()) renderRail(group, activePath);
}

/** 레일 항목 목록. 해시를 바꾸지 않고 표시만 옮길 때 쓴다. */
export function railItems() {
  return Array.from($("#panel-rail").querySelectorAll(".panel-rail-item"));
}

/** 인덱스로 활성 항목을 옮긴다. */
export function markRailActive(index) {
  railItems().forEach((n, i) => n.classList.toggle("active", i === index));
}

/** 패널 헤더 액션용 버튼 헬퍼 — .btn.sm 규격을 한 곳에서 만든다. */
export function actionBtn(label, onClick, { primary = false, iconName = "", id = "" } = {}) {
  const b = el("button", "btn sm" + (primary ? " primary" : ""));
  b.type = "button";
  if (id) b.id = id;
  if (iconName) b.appendChild(icon(iconName, 13));
  b.appendChild(el("span", null, label));
  b.addEventListener("click", onClick);
  return b;
}

/** 링크형 액션(다운로드처럼 href 가 필요한 경우). */
export function actionLink(label, href, { iconName = "" } = {}) {
  const a = el("a", "btn sm");
  a.href = href;
  if (iconName) a.appendChild(icon(iconName, 13));
  a.appendChild(el("span", null, label));
  return a;
}

export { escapeHtml };
