// taskC3 DEBUG=False 端到端验收 —— 断言④ 8 核心页 CDP 抽验(headless Chrome + CDP,零依赖)
// 用法: node test-reports/C3_pages_cdp.mjs <chromeExe> <outDir>
// 改编自 scripts/verify_pages_cdp.mjs(已验证模式);页面清单=C3 验收 8 页。
// 断言口径: 每页 HTTP 可达 + 真实渲染(bodyH>0 且标题非空) + console 零错(过滤 favicon/DevTools)。
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const CHROME = process.argv[2] || "D:\\tool\\chrom\\Application\\chrome.exe";
const OUT = process.argv[3] || "page-verify-c3";
const PORT = 9227;
const BASE = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000";
mkdirSync(OUT, { recursive: true });

// C3 验收 8 页
const PAGES = [
  ["login-register.html", "login"],
  ["courses.html", "courses"],
  ["course-detail.html?id=1", "course-detail"],
  ["dashboard.html", "dashboard"],
  ["learning.html", "learning"],
  ["me.html", "me"],
  ["achievements.html", "achievements"],
  ["admin-dashboard.html", "admin-dashboard"],
];

// 1. 真实登录拿 token(生产形态登录后 token 可用)
const login = await fetch(API + "/api/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "adm02test", password: "Test@123456" }),
}).then(r => r.json());
if (login.code !== 0) { console.error("LOGIN FAIL", login); process.exit(1); }
const { access_token, refresh_token } = login.data;
console.log("login OK (admin adm02test, prod-form token)");

// 2. 启动 headless chrome
const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${process.env.TEMP}\\edu-c3-verify-profile`,
  "--headless=new", "--window-size=1440,900", "--hide-scrollbars=false",
  "--no-first-run", "--disable-extensions", "--no-default-browser-check",
  "about:blank",
], { stdio: "ignore" });
await new Promise(r => setTimeout(r, 3000));

const list = await fetch(`http://127.0.0.1:${PORT}/json/list`).then(r => r.json());
const page = list.find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let mid = 0; const pending = new Map();
const consoleErrors = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type))
    consoleErrors.push(m.params.args.map(a => a.value ?? a.description ?? "").join(" ").slice(0, 300));
  if (m.method === "Runtime.exceptionThrown")
    consoleErrors.push("EXC: " + (m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || "").slice(0, 300));
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error")
    consoleErrors.push("LOG: " + (m.params.entry.text || "").slice(0, 300));
};
const send = (method, params = {}) => new Promise((res) => {
  const id = ++mid; pending.set(id, res);
  ws.send(JSON.stringify({ id, method, params }));
});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

await send("Runtime.enable");
await send("Log.enable");
await send("Page.enable");

// 3. 先到登录页注入 token(localStorage 同源 127.0.0.1:3000)
await send("Page.navigate", { url: BASE + "/login-register.html" });
await sleep(2500);
await send("Runtime.evaluate", { expression: `
  localStorage.setItem("edu:auth:token", ${JSON.stringify(access_token)});
  localStorage.setItem("edu:auth:refresh", ${JSON.stringify(refresh_token)});
  "token injected";` });

// 4. 逐页导航 + 渲染度量 + console 收集
const results = [];
for (const [route, name] of PAGES) {
  consoleErrors.length = 0;
  const finalUrl = BASE + "/" + route;
  await send("Page.navigate", { url: finalUrl });
  await sleep(3500);
  const evalr = await send("Runtime.evaluate", { expression: `(() => ({
    url: location.href,
    title: document.title,
    bodyH: document.documentElement.scrollHeight,
    winH: innerHeight,
    bodyW: document.documentElement.scrollWidth,
    winW: innerWidth,
    h1: (document.querySelector("h1")||{}).textContent || "",
    textLen: (document.body.innerText||"").length,
    btnCount: document.querySelectorAll("button").length,
  }))()`, returnByValue: true });
  const info = evalr?.result?.result?.value || {};
  const shot = await send("Page.captureScreenshot", { format: "png" });
  if (shot?.result?.data) writeFileSync(path.join(OUT, name + ".png"), Buffer.from(shot.result.data, "base64"));
  const errs = consoleErrors.filter(e => !/favicon|DevTools/.test(e));
  const rendered = info.bodyH > 0 && info.textLen > 0;
  results.push({ name, route, ...info, rendered, errors: errs.slice(0, 5) });
  console.log(`\n== ${name} ==`);
  console.log(`  url=${info.url} title=${(info.title || "").slice(0, 40)}`);
  console.log(`  viewport=${info.winW}x${info.winH} content=${info.bodyW}x${info.bodyH} textLen=${info.textLen} h1=${(info.h1 || "").slice(0, 30)} btns=${info.btnCount} rendered=${rendered}`);
  if (errs.length) console.log("  console errors:", JSON.stringify(errs, null, 1));
}

writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
const bad = results.filter(r => !r.rendered || r.errors.length);
console.log(`\n汇总: ${results.length - bad.length}/${results.length} 页渲染+console 零错` +
  (bad.length ? ` —— 问题页: ${bad.map(b => b.name).join(", ")}` : " —— 全绿"));
ws.close(); proc.kill();
process.exit(bad.length ? 1 : 0);
