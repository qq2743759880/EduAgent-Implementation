// 页面真实渲染验收（headless Chrome + CDP，零依赖）
// 用法: node verify_pages_cdp.mjs <chromeExe> <outDir>
import { spawn, execSync } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const CHROME = process.argv[2] || "D:\\tool\\chrom\\Application\\chrome.exe";
const OUT = process.argv[3] || "page-verify";
const PORT = 9223;
const BASE = process.env.VERIFY_FE_BASE || "http://127.0.0.1:3322";
const API = process.env.VERIFY_API_BASE || "http://127.0.0.1:9988";
mkdirSync(OUT, { recursive: true });

// 1. 真实登录拿 token
const login = await fetch(API + "/api/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "adm02test", password: "Test@123456" }),
}).then(r => r.json());
if (login.code !== 0) { console.error("LOGIN FAIL", login); process.exit(1); }
const { access_token, refresh_token } = login.data;
console.log("token OK");

// 2. 启动 headless chrome
const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${process.env.TEMP}\\edu-verify-profile`,
  "--headless=new", "--window-size=1440,900", "--hide-scrollbars=false",
  "--no-first-run", "--disable-extensions", "--no-default-browser-check",
  "about:blank",
], { stdio: "ignore" });
await new Promise(r => setTimeout(r, 3000));

// 3. 拿 page target
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

// 4. 先到登录页注入 token（localStorage 同源）
await send("Page.navigate", { url: BASE + "/login-register.html" });
await sleep(2500);
await send("Runtime.evaluate", { expression: `
  localStorage.setItem("edu:auth:token", ${JSON.stringify(access_token)});
  localStorage.setItem("edu:auth:refresh", ${JSON.stringify(refresh_token)});
  "token injected";` });

const PAGES = [
  ["login-register.html?x=1", "login"],       // 登录页（无 token 也不会跳走）
  ["dashboard.html", "student-dashboard"],
  ["courses.html", "courses"],
  ["course-detail.html?id=1", "course-detail"],
  ["chat.html", "chat"],
  ["admin-dashboard.html", "admin-dashboard"],
  ["admin-courses.html", "admin-courses"],
  ["admin-course-detail.html?id=1", "admin-course-detail"],
  ["admin-mcp.html", "admin-mcp"],
  ["admin-rag-upload.html", "admin-rag"],
  ["admin-users.html", "admin-users"],
  ["admin-questions.html", "admin-questions"],
];

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
    hasVScroll: document.documentElement.scrollHeight > innerHeight,
    btnCount: document.querySelectorAll("button").length,
    demoCtrl: !!document.querySelector(".demo-ctrl"),
  }))()`, returnByValue: true });
  const info = evalr?.result?.result?.value || {};
  const shot = await send("Page.captureScreenshot", { format: "png" });
  if (shot?.result?.data) writeFileSync(path.join(OUT, name + ".png"), Buffer.from(shot.result.data, "base64"));
  const errs = consoleErrors.filter(e => !/favicon|DevTools/.test(e));
  results.push({ name, ...info, errors: errs.slice(0, 5) });
  console.log(`\n== ${name} ==`);
  console.log(`  url=${info.url} title=${(info.title||"").slice(0,40)}`);
  console.log(`  viewport=${info.winW}x${info.winH} content=${info.bodyW}x${info.bodyH} vscroll=${info.hasVScroll} h1=${(info.h1||"").slice(0,30)} btns=${info.btnCount} demoCtrl=${info.demoCtrl}`);
  if (errs.length) console.log("  ⚠ console:", JSON.stringify(errs, null, 1));
}

writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
console.log("\nDONE. screenshots in", OUT);
ws.close(); proc.kill();
process.exit(0);
