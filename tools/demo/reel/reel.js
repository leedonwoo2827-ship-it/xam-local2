/* 쇼릴 타임라인 — CSS 전환을 쓰지 않고 t(초)로 모든 상태를 계산한다.
 * 그래야 녹화기가 프레임마다 __seek(t) 로 멈춰 찍을 때 같은 입력 = 같은 영상이 된다.
 *
 *   tl(el, [{a: 시작, b: 끝, from: {...}, to: {...}, ease}])
 *   속성: o(투명도) · x · y(px) · s(배율) · r(도) · w(%) · blur(px) · draw(SVG 선 0→1)
 */
"use strict";

const TRACKS = [];
const EASE = {
  out: (k) => 1 - Math.pow(1 - k, 3),
  inout: (k) => (k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  back: (k) => { const c = 1.70158; return 1 + (c + 1) * Math.pow(k - 1, 3) + c * Math.pow(k - 1, 2); },
  lin: (k) => k,
};

function tl(sel, steps) {
  const els = typeof sel === "string" ? document.querySelectorAll(sel) : [sel];
  els.forEach((el) => TRACKS.push({ el, steps }));
}

function stagger(sel, start, gap, step) {
  document.querySelectorAll(sel).forEach((el, i) => {
    const d = start + i * gap;
    tl(el, (Array.isArray(step) ? step : [step]).map((s) => ({ ...s, a: s.a + d, b: s.b + d })));
  });
}

function val(steps, t, key, base) {
  let v = base;
  for (const s of steps) {
    if (!(key in (s.to || {}))) continue;
    const from = key in (s.from || {}) ? s.from[key] : v;
    if (t <= s.a) { if (v === base) v = from; break; }
    const k = Math.min(1, (t - s.a) / Math.max(.001, s.b - s.a));
    v = from + (s.to[key] - from) * (EASE[s.ease || "out"])(k);
    if (t < s.b) break;
  }
  return v;
}

window.__seek = (t) => {
  for (const { el, steps } of TRACKS) {
    const o = val(steps, t, "o", 1), x = val(steps, t, "x", 0), y = val(steps, t, "y", 0);
    const s = val(steps, t, "s", 1), r = val(steps, t, "r", 0), bl = val(steps, t, "blur", 0);
    el.style.opacity = o;
    el.style.transform = `translate(${x}px, ${y}px) scale(${s}) rotate(${r}deg)`;
    el.style.filter = bl ? `blur(${bl}px)` : "";
    const w = val(steps, t, "w", -1);
    if (w >= 0) el.style.width = w + "%";
    // SVG 선 그리기 — <path pathLength="1" stroke-dasharray="1"> 에 draw 0→1
    const dr = val(steps, t, "draw", -1);
    if (dr >= 0) el.style.strokeDashoffset = String(1 - dr);
  }
  document.documentElement.style.setProperty("--t", t);
};

window.__ready = () => document.fonts.ready.then(() => true);
