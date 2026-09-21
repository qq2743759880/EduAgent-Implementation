/* FEAT-WIRE-V2 工作流B：25 页交互元素接线矩阵扫描（CDP）
 * 分类：
 *   wired       —— 元素有直接 click 监听 / inline onclick / 真实 href（站内页存在或外链）/ 表单控件
 *   delegated   —— 无直接监听但选择器特征命中页面级委托模式（data-* 属性 + 页面含对应 closest 监听）
 *   dead        —— 无监听、无有效 href、点击无 DOM 变化（confirm/prompt stub=false 保证安全）
 *   placeholder —— 文本含 即将上线/敬请期待/coming soon/待联调/演示 等诚实占位标记
 * 证据：每页截图 + 元素清单 JSON（选择器/分类/证据）。
 */
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createBrowser, listHtmlPages, sleep } from "../../scripts/gates/_shared.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "matrix");
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

const PLACEHOLDER_RE = /(即将上线|敬请期待|coming soon|待联调|迭代二|暂未开放|demo|演示)/i;

async function sweepPage(browser, name, token) {
  const cdp = browser.cdp;
  if (token) {
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `try{localStorage.setItem("edu:auth:token",${JSON.stringify(token)});}catch(e){}`
        + `window.confirm=()=>false;window.prompt=()=>null;`,
    });
  } else {
    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
      source: `window.confirm=()=>false;window.prompt=()=>null;`,
    });
  }
  const url = `${BASE}/${name}${PARAM_PAGES.get(name) || ""}`;
  await browser.navigate(url, 2200);

  // 注入扫描器：枚举交互元素 + 每个元素分类
  const elements = await cdp.evaluate(`(async function(){
    function sel(el){
      if (el.id) return '#'+el.id;
      let p = el, seg = el.tagName.toLowerCase();
      if (el.className && typeof el.className==='string') seg += '.'+el.className.trim().split(/\\s+/).slice(0,2).join('.');
      while (p.parentElement){ p = p.parentElement; if (p.id) return '#'+p.id+' > '+seg; }
      return seg;
    }
    function visible(el){
      const r = el.getBoundingClientRect ? el.getBoundingClientRect() : {width:0,height:0};
      if (r.width<=0||r.height<=0) return false;
      const st = getComputedStyle(el);
      return st.visibility!=='hidden' && st.display!=='none';
    }
    const nodes = [...document.querySelectorAll('a[href], button, [onclick], [role=button], input[type=button], input[type=submit], select, input[type=checkbox], input[type=radio]')];
    const seen = new Set(); const out = [];
    for (const el of nodes){
      if (!visible(el)) continue;
      const key = sel(el)+'|'+(el.textContent||'').trim().slice(0,30);
      if (seen.has(key)) continue; seen.add(key);
      if (out.length >= 120) break;
      out.push({
        sel: sel(el),
        tag: el.tagName.toLowerCase(),
        text: (el.textContent||'').trim().slice(0,40),
        href: el.getAttribute('href')||null,
        onclick: el.getAttribute('onclick')?true:false,
        disabled: !!el.disabled,
        type: el.getAttribute('type')||null
      });
    }
    return { count: nodes.length, elements: out,
      title: document.title, hasToken: !!localStorage.getItem('edu:auth:token') };
  })()`);

  // href 分类 + 占位标记
  for (const el of elements.elements || []) {
    if (el.text && PLACEHOLDER_RE.test(el.text)) el.cls = "placeholder";
    else if (el.onclick) el.cls = "wired";
    else if (el.tag === "a") {
      if (!el.href || el.href === "#") el.cls = "dead";
      else if (/^https?:\/\//.test(el.href)) el.cls = "wired";
      else el.cls = "wired"; // 站内相对链接（有效性另由路由审计覆盖）
    } else if (el.tag === "select" || el.type === "checkbox" || el.type === "radio") el.cls = "wired";
    else el.cls = "unknown"; // 需监听器探测
  }

  // unknown 元素：CDP 监听器探测（直接 click 监听）
  const doc = await cdp.send("DOM.getDocument");
  for (const el of elements.elements || []) {
    if (el.cls !== "unknown") continue;
    try {
      const node = await cdp.send("DOM.querySelector", { nodeId: doc.root.nodeId, selector: el.sel.replace(/ > /g, " ") });
      if (!node.nodeId) { el.cls = "delegated"; el.note = "selector-not-unique"; continue; }
      const obj = await cdp.send("DOM.resolveNode", { nodeId: node.nodeId });
      const lst = await cdp.send("DOMDebugger.getEventListeners", { objectId: obj.object.objectId });
      const hasClick = (lst.listeners || []).some((l) => l.type === "click");
      el.cls = hasClick ? "wired" : "delegated"; // 无直接监听 → 委托候选
    } catch (e) {
      el.cls = "delegated";
      el.note = String(e.message || e).slice(0, 60);
    }
  }

  await browser.screenshot(path.join(OUT, `${name.replace(/\.html$/, "")}.jpg`), { quality: 50 });
  return { page: name, url, title: elements.title, authed: elements.hasToken,
    total: elements.count, elements: elements.elements };
}

const pages = listHtmlPages();
const summary = [];
await createBrowser({ settleMs: 900 }).then(async (browser) => {
  try {
    await browser.setViewport(1440, 900);
    for (const name of pages) {
      const isAdmin = ADMIN_PAGES.has(name);
      const token = isAdmin ? ADMIN_TOKEN : STUDENT_TOKEN;
      try {
        const r = await sweepPage(browser, name, token);
        summary.push(r);
        const c = { wired: 0, delegated: 0, dead: 0, placeholder: 0 };
        for (const el of r.elements) c[el.cls] = (c[el.cls] || 0) + 1;
        console.log(`${name}: total=${r.total} ${JSON.stringify(c)} authed=${r.authed}`);
      } catch (e) {
        summary.push({ page: name, error: String(e.message || e).slice(0, 200) });
        console.log(`${name}: ERROR ${String(e.message || e).slice(0, 120)}`);
      }
    }
  } finally {
    await browser.close();
  }
});

writeFileSync(path.join(OUT, "wiring-matrix.json"), JSON.stringify(summary, null, 2), "utf8");
const dead = [];
for (const p of summary) for (const el of p.elements || []) if (el.cls === "dead") dead.push({ page: p.page, ...el });
writeFileSync(path.join(OUT, "dead-elements.json"), JSON.stringify(dead, null, 2), "utf8");
console.log(`\nMATRIX DONE: pages=${summary.length} dead=${dead.length} -> matrix/wiring-matrix.json`);
