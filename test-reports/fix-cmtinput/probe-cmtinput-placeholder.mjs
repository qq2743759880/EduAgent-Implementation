// 独立取证探针：TO-EXEC-FIX-CMTINPUT
// 目的：直接量测 #cmtInput 的 ::placeholder 实际计算色 + 对比度，
// 并在同一次页面加载内做 A/B（挂 class / 摘 class），证明「绿」来自令牌色生效，
// 而不是元素被隐藏/未被采样。
// 复用门禁同一套 Chrome 驱动与同一套 WCAG 对比度算法（scripts/gates/_shared.mjs）。
import { createBrowser } from "../../scripts/gates/_shared.mjs";

const URL_TARGET = process.env.PROBE_URL || "http://127.0.0.1:3322/community-post.html?post_id=96";

const EXPR = `(() => {
  const el = document.getElementById("cmtInput");
  if (!el) return { error: "missing #cmtInput" };
  const cs = getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  const parse = (value) => {
    const n = value.match(/[\\d.]+/g)?.map(Number) || [];
    return n.length < 3 ? [0, 0, 0, 1] : [n[0], n[1], n[2], n[3] ?? 1];
  };
  const blend = (f, b) => {
    const a = f[3] + b[3] * (1 - f[3]);
    if (!a) return [255, 255, 255, 1];
    return [0, 1, 2].map((i) => (f[i] * f[3] + b[i] * b[3] * (1 - f[3])) / a).concat(a);
  };
  const backgroundFor = (node) => {
    const layers = [];
    let cur = node;
    while (cur && cur.nodeType === 1) { layers.push(parse(getComputedStyle(cur).backgroundColor)); cur = cur.parentElement; }
    let color = [255, 255, 255, 1];
    for (let i = layers.length - 1; i >= 0; i -= 1) color = blend(layers[i], color);
    return color;
  };
  const lum = (c) => {
    const ch = c.slice(0, 3).map((v) => v / 255).map((v) => (v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4));
    return .2126 * ch[0] + .7152 * ch[1] + .0722 * ch[2];
  };
  const ratio = (fg, bg) => { const a = lum(blend(fg, bg)); const b = lum(bg); return (Math.max(a, b) + .05) / (Math.min(a, b) + .05); };
  const measure = () => {
    const ph = getComputedStyle(el, "::placeholder");
    const bg = backgroundFor(el);
    return {
      classes: el.className,
      placeholderColor: ph.color,
      placeholderOpacity: ph.opacity,
      backgroundStack: bg.map((v) => Math.round(v * 100) / 100),
      contrastRatio: Math.round(ratio(parse(ph.color), bg) * 100) / 100,
      geometry: {
        width: Math.round(rect.width * 100) / 100,
        height: Math.round(rect.height * 100) / 100,
        padding: cs.padding, border: cs.border, borderRadius: cs.borderRadius,
        minHeight: cs.minHeight, fontSize: cs.fontSize, fontFamily: cs.fontFamily.split(",")[0],
        lineHeight: cs.lineHeight, boxShadow: cs.boxShadow.slice(0, 60),
      },
      visible: cs.visibility !== "hidden" && cs.display !== "none" && rect.width > 0 && rect.height > 0,
      disabled: el.disabled,
      placeholderText: el.placeholder,
      commentsVisible: getComputedStyle(document.getElementById("comments")).visibility,
      commentItems: document.querySelectorAll("#cList .c-item").length,
      cListText: (document.getElementById("cList")?.innerText || "").trim().slice(0, 60),
    };
  };
  const withClass = measure();
  el.classList.remove("clay-input");
  void el.offsetHeight; // force reflow
  const withoutClass = measure();
  el.classList.add("clay-input");
  void el.offsetHeight;
  return { url: location.href, withClass, withoutClass };
})()`;

const browser = await createBrowser({ chrome: process.env.EDU_GATE_CHROME || null, settleMs: 3000 });
try {
  await browser.setViewport(1440, 900);
  await browser.navigate(URL_TARGET, 4000);
  const result = await browser.cdp.evaluate(EXPR);
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
}
