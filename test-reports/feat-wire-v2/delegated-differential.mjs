/* REWORK P0-3：83 个 delegated 元素逐一 CDP 点击差分。
 * 每元素：点击前装 MutationObserver + 清网络记录 → 真实 click → 900ms 观测窗 →
 * 收集 DOM 变异数/网络请求/导航 → effect 分类。
 * 分类：effect（有变异/网络/导航）= wired；none = suspect-dead（待人工修）。
 * 安全：confirm/prompt stub=false；点击的是委托元素，页面行为与用户真实点击一致。
 */
import { writeFileSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createBrowser, sleep } from "../../scripts/gates/_shared.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.EDU_GATE_BASE || "http://127.0.0.1:3322";
const ADMIN_TOKEN = process.env.EDU_GATE_TOKEN || "";
const STUDENT_TOKEN = process.env.EDU_GATE_STUDENT_TOKEN || "";
const ADMIN_PAGES = new Set(["admin-dashboard.html", "admin-courses.html", "admin-course-detail.html",
  "admin-questions.html", "admin-question-detail.html", "admin-users.html", "admin-users-refine-proto.html",
  "admin-rag-upload.html", "admin-mcp.html", "admin-courses-recycle-proto.html", "coupons.html", "refund.html"]);
const PARAM_PAGES = new Map([
  ["admin-course-detail.html", "?id=1"],
  ["admin-question-detail.html", "?id=1"],
  ["course-detail.html", "?id=1"],
  ["community-post.html", "?post_id=96"],
  ["learning.html", "?cohort_id=2&series_id=1"],
]);

const matrix = JSON.parse(readFileSync(path.join(HERE, "matrix", "wiring-matrix.json"), "utf8"));
const byPage = new Map();
for (const p of matrix) {
  const els = (p.elements || []).filter((e) => e.cls === "delegated");
  if (els.length) byPage.set(p.page, els);
}

const results = [];
const browser = await createBrowser({ settleMs: 900 });
try {
  await browser.setViewport(1440, 900);
  const cdp = browser.cdp;
  // 收集网络请求
  const netLog = [];
  cdp.on("Network.requestWillBeSent", (p) => netLog.push({ url: (p.request.url || "").slice(0, 120), method: p.request.method }));

  for (const [page, els] of byPage) {
    const token = ADMIN_PAGES.has(page) ? ADMIN_TOKEN : STUDENT_TOKEN;
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `try{localStorage.setItem("edu:auth:token",${JSON.stringify(token)});}catch(e){}` +
        `window.confirm=()=>false;window.prompt=()=>null;window.__mutCount=0;` +
        `new MutationObserver(m=>{window.__mutCount+=m.length;}).observe(document.documentElement,{subtree:true,childList:true,attributes:true,characterData:true});`,
    });
    await browser.navigate(`${BASE}/${page}${PARAM_PAGES.get(page) || ""}`, 2500);

    for (const el of els) {
      const before = { url: await eval_(cdp, "location.href"), muts: await eval_(cdp, "window.__mutCount") };
      netLog.length = 0;
      const click = await eval_(cdp, `(function(){
        function find(){
          ${el.sel.startsWith("#") ? "" : ""}
          // 按 sweep 同款选择器找（id 优先；class 选择器取首个匹配）
          try { const n = document.querySelector(${JSON.stringify(el.sel)}); if (n) return n; } catch(e){}
          // 兜底：按文本找
          const cand=[...document.querySelectorAll('a[href],button,[onclick],[role=button],select')];
          return cand.find(x=>(x.textContent||'').trim().slice(0,40)===${JSON.stringify(el.text)}) || null;
        }
        const n=find();
        if(!n) return {ok:false, reason:'not-found'};
        n.scrollIntoView({block:'center'});
        n.click();
        return {ok:true, tag:n.tagName, text:(n.textContent||'').trim().slice(0,30)};
      })()`);
      await sleep(900);
      const after = { url: await eval_(cdp, "location.href"), muts: await eval_(cdp, "window.__mutCount") };
      const mutated = after.muts > before.muts;
      const navigated = after.url !== before.url;
      const net = netLog.filter((r) => !/(_next|turbopack|\.css|\.js|\.jpg|\.png|fonts|hmr)/.test(r.url));
      const cls = (click.ok && (mutated || navigated || net.length)) ? "effect" : (click.ok ? "no-effect" : "not-found");
      results.push({ page, sel: el.sel, text: el.text, click, mutated, mutDelta: after.muts - before.muts,
        navigated, net: net.slice(0, 4), cls });
      console.log(`[${cls}] ${page} :: ${el.sel} "${el.text.slice(0, 20)}" mut+${after.muts - before.muts} net=${net.length} nav=${navigated}`);
      // 若发生导航，回到原页继续
      if (navigated) {
        await browser.navigate(`${BASE}/${page}${PARAM_PAGES.get(page) || ""}`, 2200);
      }
    }
  }
} finally {
  await browser.close();
}

writeFileSync(path.join(HERE, "matrix", "delegated-differential.json"), JSON.stringify({
  generated_at: new Date().toISOString(), total: results.length,
  summary: {
    effect: results.filter((r) => r.cls === "effect").length,
    no_effect: results.filter((r) => r.cls === "no-effect").length,
    not_found: results.filter((r) => r.cls === "not-found").length,
  },
  results,
}, null, 2), "utf8");
console.log(`\nDIFFERENTIAL DONE: ${JSON.stringify({
  effect: results.filter((r) => r.cls === "effect").length,
  no_effect: results.filter((r) => r.cls === "no-effect").length,
  not_found: results.filter((r) => r.cls === "not-found").length })}`);

async function eval_(cdp, expr) {
  const r = await cdp.evaluate(expr);
  return r;
}
