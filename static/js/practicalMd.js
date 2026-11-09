/* 실기 원고 MD 보기 — 확정본(01/practical)·집필(02/practical/mNN) 공용.
 *
 * util.renderMarkdown 은 그림 줄(![..](images/x.png))과 &emsp; 를 모른다. 그림 줄만 떼어
 * /api/practical/img/{which}/{name} 로 바꿔 넣고, 나머지는 renderMarkdown 에 맡긴다.
 */
"use strict";

import { escapeHtml, renderMarkdown } from "./util.js";

const IMG = /^!\[(.*)\]\((images\/[^)\s]+|[^)\s]+\.(?:png|jpe?g|svg))\)\s*$/;   // 설명에 [ ] 가 있어도(옛 원고) 끝의 (파일) 로 잡는다

export function practicalMdHtml(md, which) {
  const out = [];
  let buf = [];
  const flush = () => { if (buf.length) { out.push(renderMarkdown(buf.join("\n"))); buf = []; } };
  for (const raw of String(md || "").replace(/&emsp;/g, "  ").split("\n")) {
    const m = raw.trim().match(IMG);
    if (m) {
      flush();
      const name = m[2].split("/").pop();
      out.push(`<figure class="pr-fig"><img src="/api/practical/img/${encodeURIComponent(which)}/${encodeURIComponent(name)}" alt="${escapeHtml(m[1])}" loading="lazy" style="max-width:100%;border:1px solid var(--line,#ddd)"><figcaption class="muted" style="font-size:12px">${escapeHtml(m[1])}</figcaption></figure>`);
    } else {
      buf.push(raw);
    }
  }
  flush();
  return out.join("");
}
