#!/usr/bin/env node
/**
 * TB4 usability probe (E4 evidence): drives admin-mcp.html / admin-rag-upload.html
 * in a real browser and asserts the TB4 UX affordances the work order demands:
 *   - 顶部功能说明卡 present
 *   - 「新增 Server」分步引导：5 步、可推进、可回退、步骤条高亮
 *   - 空态引导文案（非白板）—— 恒有半：先摘空态实渲染并截图，再断言引导块+关键文案
 *   - 工具列表健康徽标存在
 *   - RAG 五 tab 各有说明卡
 *   - 无 token → 跳登录；student token → 被拒（E4 守卫项）
 * Playwright forbidden (AGENTS.md) — reuses scripts/gates/_shared.mjs createBrowser (CDP).
 *
 * Usage: EDU_GATE_TOKEN=<jwt> node scripts/tb4-ux-probe.mjs
 */
import { createBrowser, DEFAULT_BASE, writeJson, ensureDir } from "./gates/_shared.mjs";
import path from "node:path";

const BASE = process.env.EDU_GATE_BASE || DEFAULT_BASE;
const OUT = path.resolve("test-reports/tb4");
const TOKEN = process.env.EDU_GATE_TOKEN || "";
const STUDENT_TOKEN = process.env.EDU_GATE_STUDENT_TOKEN || "";

const results = [];
function check(page, name, pass, detail) {
  results.push({ page, name, pass: Boolean(pass), detail: String(detail ?? "") });
  console.log(`  [${pass ? "PASS" : "FAIL"}] ${page} · ${name}: ${detail}`);
}

const browser = await createBrowser({});
const evaluate = (expr) => browser.cdp.evaluate(expr);

async function run(pageName, fn) {
  await browser.navigate(`${BASE}/${pageName}`);
  await browser.waitForReady(async () => evaluate("document.body.innerText.length"));
  await fn(pageName);
}

/**
 * 截「空态」实证：用 CDP Fetch 把 /api/* 列表接口 fulfill 成空壳，
 * 触发页面的空态分支，截图并回读 DOM 文案。
 * 关键顺序：先在 about:blank 用 Network.setExtraHTTPHeaders 注入 admin 身份，
 * 再 Fetch.enable（只 mock 列表接口，放行 /api/auth/me），最后才导航。
 */
async function captureEmptyState(pageName, shots, emptyRe) {
  const cdp = browser.cdp;
  const LIST_RE = emptyRe || /\/api\/(mcp\/(servers|tools|logs)|rag\/(collections|presets|audit|tasks|partitions))/;
  try {
    // 1) 身份：G9 的 auth/me 默认 mock 若走 Student，守卫会跳走；这里改走真实 /api/auth/me
    await cdp.send("Network.enable", {});
    await cdp.send("Network.setExtraHTTPHeaders", { headers: { Authorization: `Bearer ${TOKEN}` } });
    await browser.navigate(`${BASE}/login-register.html`); // 触发 localStorage 写入需页面内 setItem，这里用头注入即可
    await new Promise((r) => setTimeout(r, 300));
    // 2) 只 mock 列表接口，auth/me 放行
    await cdp.send("Fetch.enable", {
      patterns: [
        { urlPattern: "*://127.0.0.1:*/api/*", requestStage: "Request" },
        { urlPattern: "*://localhost:*/api/*", requestStage: "Request" },
      ],
    });
  } catch (e) {
    console.log(`  [WARN] ${pageName} · empty-state-capture: 初始化失败 ${e.message}`);
    return { ok: false, blocks: 0, texts: [] };
  }

  let intercepted = 0;
  const onPaused = async (params) => {
    const { requestId, request } = params;
    try {
      if (request.method === "OPTIONS") {
        await cdp.send("Fetch.fulfillRequest", {
          requestId,
          responseCode: 204,
          responseHeaders: [
            { name: "Access-Control-Allow-Origin", value: "*" },
            { name: "Access-Control-Allow-Headers", value: "*" },
            { name: "Access-Control-Allow-Methods", value: "GET,POST,PUT,PATCH,DELETE,OPTIONS" },
          ],
        });
        return;
      }
      if (/\/api\/auth\//.test(request.url) || !LIST_RE.test(request.url)) {
        await cdp.send("Fetch.continueRequest", { requestId });
        return;
      }
      intercepted += 1;
      const body = JSON.stringify({ code: 0, message: "ok", data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 } });
      await cdp.send("Fetch.fulfillRequest", {
        requestId,
        responseCode: 200,
        responsePhrase: "OK",
        responseHeaders: [
          { name: "Content-Type", value: "application/json; charset=utf-8" },
          { name: "Access-Control-Allow-Origin", value: "*" },
          { name: "Cache-Control", value: "no-store" },
        ],
        body: Buffer.from(body, "utf8").toString("base64"),
      });
    } catch { /* ignore */ }
  };

  cdp.on("Fetch.requestPaused", onPaused);
  try {
    await browser.navigate(`${BASE}/${pageName}`);
    await browser.waitForReady(async () => evaluate("document.body.innerText.length"));
    await new Promise((r) => setTimeout(r, 1500));
    const url = await evaluate("location.href");
    await evaluate(`localStorage.removeItem("edu:auth:token");localStorage.removeItem("edu:auth:refresh");true`);
    for (const s of shots) {
      if (s.scroll) {
        await evaluate(`(function(){var e=document.querySelector("${s.scroll}");if(e)e.scrollIntoView({block:"center"});return true})()`);
        await new Promise((r) => setTimeout(r, 250));
      }
      try {
        await browser.screenshot(path.join(OUT, "shots", s.file), { quality: 82 });
      } catch (e) {
        console.log(`  [WARN] ${pageName} · screenshot ${s.file}: ${e.message}`);
      }
      if (s.click && s.click !== "#nullBtnNoop") {
        await evaluate(`(function(){var b=document.querySelector("${s.click}");if(b)b.click();return true})()`);
        await new Promise((r) => setTimeout(r, 700));
      }
    }
    const last = shots[shots.length - 1];
    const info = await evaluate(`(function(){
      var b=document.querySelectorAll("${last.selector || ".tb4-empty"}");
      var t=[];for(var i=0;i<b.length;i++)t.push(b[i].innerText.replace(/\\s+/g," ").trim());
      return {count:b.length,texts:t.slice(0,4)};
    })()`);
    return { ok: true, intercepted, url, blocks: info.count, texts: info.texts };
  } finally {
    cdp.off("Fetch.requestPaused", onPaused);
    try { await cdp.send("Fetch.disable", {}); } catch { /* ignore */ }
    try { await cdp.send("Network.setExtraHTTPHeaders", { headers: {} }); } catch { /* ignore */ }
  }
}

/* ---------------- admin-mcp.html ---------------- */
await run("admin-mcp.html", async (p) => {
  const cards = await evaluate(`document.querySelectorAll(".tb4-what .tb4-wcard").length`);
  check(p, "top-explanation-cards", cards >= 3, `${cards} 张功能说明卡`);

  const guideText = await evaluate(
    `(function(){var e=document.querySelector(".tb4-what");return e?e.innerText.replace(/\\s+/g," ").slice(0,200):""})()`
  );
  check(p, "explains-what-and-how", /这个页面是什么/.test(guideText) && /三步上手/.test(guideText), guideText.slice(0, 80));

  // 分步引导：打开弹窗 → 初始第 1 步 → 下一步 → 第 2 步 → 上一步回第 1 步
  const stepFlow = await evaluate(`(function(){
    document.getElementById("addSrvBtn").click();
    var mdl=document.getElementById("mdl-server");
    function cur(){var li=document.querySelectorAll("#srvSteps li");for(var i=0;i<li.length;i++){if(li[i].classList.contains("cur"))return +li[i].getAttribute("data-step");}return -1;}
    function paneOn(){var ps=document.querySelectorAll("#mdl-server .step-pane");for(var j=0;j<ps.length;j++){if(ps[j].classList.contains("on"))return +ps[j].getAttribute("data-pane");}return -1;}
    var r={steps:document.querySelectorAll("#srvSteps li").length,modalOpen:mdl.style.display==="flex",first:cur(),firstPane:paneOn()};
    // 第 1 步填 code 才能推进
    document.getElementById("fCode").value="tb4-probe-srv";
    document.getElementById("srvNext").click();
    r.afterNext=cur(); r.paneAfterNext=paneOn();
    r.saveHiddenOnStep2=document.getElementById("srvMdlSave").style.display==="none";
    document.getElementById("srvPrev").click();
    r.afterPrev=cur();
    document.getElementById("srvMdlCancel").click();
    r.closed=mdl.style.display==="none";
    return r;
  })()`);
  check(p, "stepper-5-steps", stepFlow.steps === 5, `步骤条 ${stepFlow.steps} 步`);
  check(p, "stepper-opens-step1", stepFlow.modalOpen && stepFlow.first === 1 && stepFlow.firstPane === 1,
    `初始 step=${stepFlow.first} pane=${stepFlow.firstPane}`);
  check(p, "stepper-advances", stepFlow.afterNext === 2 && stepFlow.paneAfterNext === 2, `下一步 → step=${stepFlow.afterNext} pane=${stepFlow.paneAfterNext}`);
  check(p, "stepper-save-only-on-last", stepFlow.saveHiddenOnStep2 === true, `第 2 步隐藏「创建 Server」=${stepFlow.saveHiddenOnStep2}`);
  check(p, "stepper-goes-back", stepFlow.afterPrev === 1, `上一步 → step=${stepFlow.afterPrev}`);
  check(p, "stepper-closes", stepFlow.closed === true, `取消后弹窗关闭=${stepFlow.closed}`);

  // 步骤 1 缺 code 时不得推进（守卫有效性）
  const gate = await evaluate(`(function(){
    document.getElementById("addSrvBtn").click();
    document.getElementById("fCode").value="";
    document.getElementById("srvNext").click();
    var li=document.querySelectorAll("#srvSteps li"),cur=-1;
    for(var i=0;i<li.length;i++){if(li[i].classList.contains("cur"))cur=+li[i].getAttribute("data-step");}
    var err=document.getElementById("srvMdlErr");
    var r={cur:cur,errShown:err.style.display==="block",errText:(err.textContent||"").slice(0,60)};
    document.getElementById("srvMdlCancel").click();
    return r;
  })()`);
  check(p, "stepper-blocks-empty-code", gate.cur === 1 && gate.errShown, `仍停在第 ${gate.cur} 步，提示「${gate.errText}」`);

  // 工具列表健康徽标（.badge 内含 健康/异常/未检测 之一）
  const badge = await evaluate(`(function(){
    var b=document.querySelectorAll("#toolTable tbody .badge");
    var txt=[];for(var i=0;i<b.length;i++)txt.push(b[i].innerText.trim());
    return {count:b.length,uniq:txt.slice(0,5)};
  })()`);
  check(p, "tool-health-badges", badge.count > 0 && badge.uniq.every((t) => /健康|异常|未检测/.test(t)),
    `${badge.count} 个徽标，样例 ${JSON.stringify(badge.uniq)}`);
});

/* 空态引导：把 /api/mcp/* 三个列表接口 mock 成空，触发空态分支并截图取证 */
const mcpEmpty = await captureEmptyState(
  "admin-mcp.html",
  [
    { file: "admin-mcp-empty-servers.jpg", scroll: "#srvTable", selector: "#srvTable .tb4-empty" },
    { file: "admin-mcp-empty-tools.jpg", scroll: "#toolTable", selector: "#toolTable .tb4-empty" },
    { file: "admin-mcp-empty-logs.jpg", scroll: "#logBody", selector: "#logBody .tb4-empty" },
  ],
  /\/api\/mcp\/(servers|tools|call-log)/
);
const mcpAll = await evaluate(`(function(){
  var s=document.querySelectorAll("#srvTable .tb4-empty").length;
  var t=document.querySelectorAll("#toolTable .tb4-empty").length;
  var l=document.querySelectorAll("#logBody .tb4-empty").length;
  var txt=[];document.querySelectorAll("#srvTable .tb4-empty, #toolTable .tb4-empty, #logBody .tb4-empty").forEach(function(e){txt.push(e.innerText.replace(/\\s+/g," ").trim().slice(0,90));});
  return {srv:s,tool:t,log:l,total:s+t+l,texts:txt};
})()`);
check("admin-mcp.html", "empty-state-guidance", mcpEmpty.ok && mcpAll.total >= 3,
  `${mcpAll.total} 处空态引导块（Server=${mcpAll.srv} 工具=${mcpAll.tool} 日志=${mcpAll.log}）`);
check("admin-mcp.html", "empty-state-has-next-step",
  mcpAll.texts.some((t) => /新增 Server/.test(t)) && mcpAll.texts.some((t) => /发现工具|工具清单/.test(t)),
  `空态文案含下一步指引=${JSON.stringify(mcpAll.texts.map((t) => t.slice(0, 40)))}`);

/* ---------------- admin-rag-upload.html ---------------- */
await run("admin-rag-upload.html", async (p) => {
  const tabs = await evaluate(`(function(){
    var out={};
    var bs=document.querySelectorAll(".tabs .tab[data-tab]");
    for(var i=0;i<bs.length;i++){
      bs[i].click();
      var name=bs[i].getAttribute("data-tab");
      var panel=document.getElementById("rag-panel-"+name);
      var card=panel?panel.querySelector(".tab-what"):null;
      out[name]={hasCard:!!card,text:card?card.innerText.replace(/\\s+/g," ").slice(0,90):""};
    }
    return out;
  })()`);
  const names = Object.keys(tabs);
  const withCard = names.filter((k) => tabs[k].hasCard);
  check(p, "five-tabs", names.length === 5, `tabs=${names.join(",")}`);
  check(p, "every-tab-has-explanation", withCard.length === 5,
    `${withCard.length}/5 个 tab 有说明卡${withCard.length < 5 ? " 缺:" + names.filter((k) => !tabs[k].hasCard).join(",") : ""}`);
});

/* RAG 空态引导：mock 掉 collections / presets / audit 列表接口 */
const ragEmpty = await captureEmptyState(
  "admin-rag-upload.html",
  [
    { file: "admin-rag-empty-upload.jpg", scroll: "#fileList", selector: "#fileList .tb4-empty" },
    { file: "admin-rag-empty-collections.jpg", click: ".tabs .tab[data-tab=collections]", selector: "#ragColBody .tb4-empty" },
    { file: "admin-rag-empty-presets.jpg", click: ".tabs .tab[data-tab=presets]", selector: "#ragPresetBody .tb4-empty" },
    { file: "admin-rag-empty-audit.jpg", click: ".tabs .tab[data-tab=audit]", selector: "#ragAuditBody .tb4-empty" },
  ],
  /\/api\/(admin\/rag\/(collections|presets|audit-log)|knowledge\/(tasks|partitions))(\?|\/|$)/
);
const ragAll = await evaluate(`(function(){
  var ids=["ragColBody","ragPresetBody","ragAuditBody","taskBody","fileList"];
  var out={},total=0;
  ids.forEach(function(id){var e=document.getElementById(id);var n=e?e.querySelectorAll(".tb4-empty").length:0;out[id]=n;total+=n;});
  return {byId:out,total:total};
})()`);
check("admin-rag-upload.html", "empty-state-provided", ragEmpty.ok && ragAll.total > 0,
  `${ragAll.total} 处空态引导块 ${JSON.stringify(ragAll.byId)}`);

/* 守卫：无 token → 跳登录；student token → 被拒（E4 第四项自验）
 *
 * 关键坑：scripts/gates/_shared.mjs::createBrowser 会注册一条
 * Page.addScriptToEvaluateOnNewDocument，在**每个新文档**里把 EDU_GATE_TOKEN
 * 写回 localStorage。所以「页内 removeItem 后再导航」必然被覆盖（实测 tokLen 又变 175）。
 * 正确做法：单独开一个干净浏览器（不传 EDU_GATE_TOKEN），再用
 * addScriptToEvaluateOnNewDocument 精确控制要种的身份。
 */
const GUARD_PAGES = ["admin-mcp.html", "admin-rag-upload.html"];

async function guardSuite(label, seedToken) {
  const K = ["EDU_GATE_TOKEN", "EDU_GATE_REFRESH_TOKEN", "EDU_GATE_STUDENT_TOKEN", "EDU_GATE_STUDENT_REFRESH_TOKEN"];
  const backup = {};
  for (const k of K) { backup[k] = process.env[k]; delete process.env[k]; }
  const gb = await createBrowser({});
  const gev = (x) => gb.cdp.evaluate(x);
  const source = seedToken
    ? `try { localStorage.setItem("edu:auth:token", ${JSON.stringify(seedToken)}); localStorage.setItem("edu:auth:refresh", ${JSON.stringify(seedToken)}); } catch {}`
    : `try { localStorage.removeItem("edu:auth:token"); localStorage.removeItem("edu:auth:refresh"); } catch {}`;
  await gb.cdp.send("Page.addScriptToEvaluateOnNewDocument", { source });

  const out = {};
  for (const pg of GUARD_PAGES) {
    const trace = [];
    await gb.navigate(`${BASE}/${pg}?__tb4g=${Date.now()}`);
    for (let i = 0; i < 14; i += 1) {
      await new Promise((r) => setTimeout(r, 400));
      const u = await gev("location.href");
      if (trace[trace.length - 1] !== u) trace.push(u);
      if (!/\/admin-(mcp|rag)/.test(u)) break;
    }
    out[pg] = {
      url: await gev("location.href"),
      trace: trace.map((u) => u.replace(BASE, "").split("?")[0]),
      tokenLen: await gev(`(localStorage.getItem("edu:auth:token")||"").length`),
    };
  }
  await gb.close();
  for (const k of K) { if (backup[k] != null) process.env[k] = backup[k]; }
  return out;
}

const guardNoTok = await guardSuite("no-token", "");
for (const pg of GUARD_PAGES) {
  check(pg, "guard-no-token-redirects", /login-register\.html/.test(guardNoTok[pg].url),
    `无 token（tokenLen=${guardNoTok[pg].tokenLen}）→ ${guardNoTok[pg].trace.join(" → ")}`);
}
if (STUDENT_TOKEN) {
  const guardStu = await guardSuite("student", STUDENT_TOKEN);
  for (const pg of GUARD_PAGES) {
    const u = guardStu[pg].url;
    const rejected = /login-register\.html/.test(u) || /dashboard\.html/.test(u);
    check(pg, "guard-student-rejected", rejected,
      `student（tokenLen=${guardStu[pg].tokenLen}）→ ${guardStu[pg].trace.join(" → ")}`);
  }
} else {
  for (const pg of GUARD_PAGES) {
    check(pg, "guard-student-rejected", false, "缺 EDU_GATE_STUDENT_TOKEN，未验证（环境门槛）");
  }
}

await browser.close();

ensureDir(path.join(OUT, "shots"));
const failed = results.filter((r) => !r.pass);
const report = {
  gate: "TB4 UX probe",
  generated_at: new Date().toISOString(),
  base: BASE,
  total: results.length,
  failed: failed.length,
  results,
};
const jsonPath = path.join(OUT, "tb4-ux-probe.json");
writeJson(jsonPath, report);
console.log(`\nTB4 UX Probe: ${failed.length === 0 ? "PASS" : "FAIL"}  checks=${results.length} failed=${failed.length}`);
console.log(`json=${jsonPath}`);
process.exit(failed.length === 0 ? 0 : 1);
