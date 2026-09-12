// task19 渲染矩阵补跑:13-15 页(主跑 13 页遇 ERR_CACHE_READ_FAILURE 卡死,新会话新 profile 重试)
// 用法: node scripts/verify_pages_task19_retry.mjs
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const CHROME = "D:\\tool\\chrom\\Application\\chrome.exe";
const OUT = "page-verify-task19";
const PORT = 9231, BASE = "http://127.0.0.1:3000", API = "http://127.0.0.1:8000";
mkdirSync(OUT, { recursive: true });

const atok = await (async () => {
  const j = await fetch(API + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ account: "adm02test", password: "Test@123456" }) }).then((r) => r.json());
  if (j.code !== 0) throw new Error("login fail");
  return j.data.access_token;
})();
console.log("admin token ok");

spawn(CHROME, [`--remote-debugging-port=${PORT}`,
  `${process.env.TEMP}\\edu-verify-task19-r2`, "--headless=new", "--window-size=1440,900",
  "--no-first-run", "--disable-extensions", "--disable-application-cache", "about:blank"], { stdio: "ignore" });
let up = false;
for (let i = 0; i < 12 && !up; i++) {
  await new Promise((r) => setTimeout(r, 1500));
  try { await fetch(`http://127.0.0.1:${PORT}/json/version`); up = true; } catch {}
}
if (!up) { console.error("chrome never came up"); process.exit(1); }
const page = (await fetch(`http://127.0.0.1:${PORT}/json/list`).then((r) => r.json())).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let mid = 0; const pend = new Map(); const errs = [];
ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errs.push("EXC:" + (m.params.exceptionDetails?.exception?.description || "").slice(0, 200));
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") errs.push("LOG:" + m.params.entry.text.slice(0, 200)); };
const send = (method, params = {}, timeoutMs = 15000) => new Promise((res) => {
  const id = ++mid; pend.set(id, res);
  setTimeout(() => { if (pend.has(id)) { pend.delete(id); res(null); } }, timeoutMs);
  ws.send(JSON.stringify({ id, method, params }));
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await send("Runtime.enable"); await send("Log.enable"); await send("Page.enable");

const PAGES = [
  ["admin-questions.html", "13-admin-questions"],
  ["admin-rag-upload.html", "14-admin-rag-upload"],
  ["admin-mcp.html", "15-admin-mcp"],
];
for (const [route, name] of PAGES) {
  errs.length = 0;
  await send("Page.navigate", { url: BASE + "/login-register.html" });
  await sleep(1500);
  await send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token",${JSON.stringify(atok)});localStorage.setItem("edu:auth:refresh","x");1` });
  await send("Page.navigate", { url: `${BASE}/${route}` });
  const deadline = Date.now() + 26000;
  let i = {};
  while (Date.now() < deadline) {
    await sleep(3000);
    const r = await send("Runtime.evaluate", { expression: `(() => ({url:location.href, h1:(document.querySelector("h1")||{}).textContent||"",
      sh:document.documentElement.scrollHeight, wh:innerHeight, btns:document.querySelectorAll("button").length,
      mockHint:/演示数据|MOCK/.test(document.body.innerText)}))()`, returnByValue: true });
    i = r?.result?.result?.value || {};
    if (i.h1 && i.h1 !== "加载中…" && i.sh >= i.wh) break;
  }
  const real = errs.filter((e) => !/favicon|DevTools/i.test(e));
  const redirected = !String(i.url || "").includes(route.split("?")[0]);
  const pass = real.length === 0 && i.sh >= i.wh && !redirected && !!i.h1;
  console.log(`== ${name} == ${pass ? "PASS" : "CHECK"}  h1="${(i.h1 || "").slice(0, 24)}" content=${i.sh} viewport=${i.wh} btns=${i.btns} errors=${real.length} url=${String(i.url || "").slice(-48)}`);
  if (real.length) console.log("   errs:", JSON.stringify(real.slice(0, 3)));
  const shot = await send("Page.captureScreenshot", { format: "png" });
  if (shot?.result?.data) writeFileSync(path.join(OUT, name + ".png"), Buffer.from(shot.result.data, "base64"));
  else console.log("   (screenshot unavailable)");
}
console.log("RETRY DONE");
ws.close(); process.exit(0);
