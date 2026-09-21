/* REWORK P0-3 复查：对 no-effect 元素逐个按文本精确匹配重测 + 捕获 console 错误 */
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

const diff = JSON.parse(readFileSync(path.join(HERE, "matrix", "delegated-differential.json"), "utf8"));
const suspects = diff.results.filter((r) => r.cls === "no-effect");
const byPage = new Map();
for (const r of suspects) byPage.set(r.page, (byPage.get(r.page) || []).concat(r));

const results = [];
const browser = await createBrowser({ settleMs: 900 });
try {
  await browser.setViewport(1440, 900);
  const cdp = browser.cdp;
  await cdp.send("Runtime.enable");
  const consoleErrs = [];
  cdp.on("Runtime.consoleAPICalled", (p) => {
    if (p.type === "error") consoleErrs.push((p.args || []).map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 200));
  });
  cdp.on("Runtime.exceptionThrown", (p) => {
    const d = p.params || {};
    consoleErrs.push(((d.exceptionDetails && (d.exceptionDetails.exception?.description || d.exceptionDetails.text)) || "").slice(0, 200));
  });
  const netLog = [];
  cdp.on("Network.requestWillBeSent", (p) => netLog.push({ url: (p.request.url || "").slice(0, 120), method: p.request.method }));

  for (const [page, els] of byPage) {
    const token = ADMIN_PAGES.has(page) ? ADMIN_TOKEN : STUDENT_TOKEN;
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `try{localStorage.setItem("edu:auth:token",${JSON.stringify(token)});}catch(e){}` +
        `window.confirm=()=>false;window.prompt=()=>null;window.__mutCount=0;` +
        `(function(){function arm(){if(document.documentElement){new MutationObserver(m=>{window.__mutCount+=m.length;}).observe(document.documentElement,{subtree:true,childList:true,attributes:true,characterData:true});}else{setTimeout(arm,5);}}arm();})();`,
    });
    await browser.navigate(`${BASE}/${page}${PARAM_PAGES.get(page) || ""}`, 2500);

    for (const el of els) {
      consoleErrs.length = 0; netLog.length = 0;
      const before = { url: await ev(cdp, "location.href"), muts: await ev(cdp, "window.__mutCount") };
      const click = await ev(cdp, `(function(){
        // 文本优先精确匹配（修 sweep 首个匹配错位）
        let n = null;
        const scope = ${JSON.stringify(el.sel.split(" > ")[0])};
        const root = document.querySelector(scope) || document;
        const cand = [...root.querySelectorAll(${JSON.stringify(el.sel.split(" > ").slice(1).join(" > ") || "*")})];
        n = cand.find(x => (x.textContent||'').trim().slice(0,40) === ${JSON.stringify(el.text)})
         || cand.find(x => (x.textContent||'').trim().indexOf(${JSON.stringify(el.text.slice(0, 12))}) >= 0)
         || document.querySelector(${JSON.stringify(el.sel)});
        if (!n) return {ok:false, reason:'not-found'};
        const direct = (() => { try {
          // 检查自身/祖先 inline onclick
          let p = n; while (p) { if (p.getAttribute && p.getAttribute('onclick')) return 'inline-onclick'; p = p.parentElement; }
        } catch(e){} return null; })();
        n.scrollIntoView({block:'center'});
        n.click();
        return {ok:true, tag:n.tagName, text:(n.textContent||'').trim().slice(0,30), direct,
                disabled:n.disabled, ariaExpanded:n.getAttribute('aria-expanded')};
      })()`);
      await sleep(1000);
      const after = { url: await ev(cdp, "location.href"), muts: await ev(cdp, "window.__mutCount") };
      const net = netLog.filter((r) => !/(_next|turbopack|\.css|\.js|\.jpg|\.png|fonts|hmr)/.test(r.url));
      const cls = (click.ok && !click.disabled && ((after.muts - before.muts) > 0 || after.url !== before.url || net.length))
        ? "effect" : (click.ok ? (click.disabled ? "disabled-ok" : "still-no-effect") : "not-found");
      results.push({ page, sel: el.sel, text: el.text, click, mutDelta: after.muts - before.muts,
        navigated: after.url !== before.url, net: net.slice(0, 3), consoleErrs: consoleErrs.slice(0, 3), cls });
      console.log(`[${cls}] ${page} :: "${el.text.slice(0, 18)}" mut+${after.muts - before.muts} net=${net.length} err=${consoleErrs.length}`);
      if (after.url !== before.url) await browser.navigate(`${BASE}/${page}${PARAM_PAGES.get(page) || ""}`, 2200);
    }
  }
} finally {
  await browser.close();
}
writeFileSync(path.join(HERE, "matrix", "delegated-differential-pass2.json"), JSON.stringify({
  generated_at: new Date().toISOString(), results,
  summary: {
    effect: results.filter((r) => r.cls === "effect").length,
    still_no_effect: results.filter((r) => r.cls === "still-no-effect").length,
    disabled_ok: results.filter((r) => r.cls === "disabled-ok").length,
    not_found: results.filter((r) => r.cls === "not-found").length,
  },
}, null, 2), "utf8");
console.log("PASS2:", JSON.stringify({
  effect: results.filter((r) => r.cls === "effect").length,
  still_no_effect: results.filter((r) => r.cls === "still-no-effect").length,
  disabled_ok: results.filter((r) => r.cls === "disabled-ok").length}));

async function ev(cdp, expr) { return cdp.evaluate(expr); }
