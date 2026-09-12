// 第二波页面渲染验收(_coupons/chat/community/achievements/dashboard)
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const CHROME = process.argv[2] || "D:\\tool\\chrom\\Application\\chrome.exe";
const OUT = process.argv[3] || "page-verify-w3";
const PORT = 9227, BASE = "http://127.0.0.1:3000", API = "http://127.0.0.1:8000";
mkdirSync(OUT, { recursive: true });

const login = await fetch(API + "/api/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "user000001", password: "Test@123456" }),
}).then(r => r.json());
if (login.code !== 0) { console.error("LOGIN FAIL"); process.exit(1); }
const tok = login.data.access_token;

let up = false;
try { await fetch(`http://127.0.0.1:${PORT}/json/version`); up = true; } catch {}
if (!up) {
  spawn(CHROME, [`--remote-debugging-port=${PORT}`,
    `${process.env.TEMP}\\edu-verify-w2`, "--headless=new", "--window-size=1440,900",
    "--no-first-run", "--disable-extensions", "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 10 && !up; i++) {
    await new Promise(r=>setTimeout(r,1500));
    try { await fetch(`http://127.0.0.1:${PORT}/json/version`); up = true; } catch {}
  }
}
if (!up) { console.error("chrome debug port never came up"); process.exit(1); }
const page = (await fetch(`http://127.0.0.1:${PORT}/json/list`).then(r => r.json())).find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let mid = 0; const pend = new Map(); const errs = [];
ws.onmessage = ev => { const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errs.push("EXC:" + (m.params.exceptionDetails?.exception?.description || "").slice(0, 200));
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") errs.push("LOG:" + m.params.entry.text.slice(0, 200)); };
const send = (method, params = {}) => new Promise(res => { const id = ++mid; pend.set(id, res); ws.send(JSON.stringify({ id, method, params })); });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await send("Runtime.enable"); await send("Log.enable"); await send("Page.enable");
await send("Page.navigate", { url: BASE + "/login-register.html" });
await sleep(2500);
await send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token",${JSON.stringify(tok)});localStorage.setItem("edu:auth:refresh","x");1` });

const PAGES = [["learning.html", "learning"], ["me.html", "me"],
  ["admin-dashboard.html", "admin-dashboard"], ["admin-users.html", "admin-users"],
  ["admin-questions.html", "admin-questions"], ["admin-courses-recycle-proto.html", "recycle-proto"]];
for (const [route, name] of PAGES) {
  errs.length = 0;
  await send("Page.navigate", { url: `${BASE}/${route}` });
  await sleep(9000);
  const r = await send("Runtime.evaluate", { expression: `(() => ({h1:(document.querySelector("h1")||{}).textContent||"", txt:document.body.innerText.slice(0,400),
    sh:document.documentElement.scrollHeight, wh:innerHeight, btns:document.querySelectorAll("button").length,
    mockHint:/演示数据|MOCK/.test(document.body.innerText)}))()`, returnByValue: true });
  const i = r?.result?.result?.value || {};
  const real = errs.filter(e => !/favicon|DevTools/.test(e));
  console.log(`== ${name} == h1=${(i.h1||"").slice(0,20)} content=${i.sh} viewport=${i.wh} btns=${i.btns} errors=${real.length}`);
  if (real.length) console.log("  ", JSON.stringify(real.slice(0, 3)));
  const shot = await send("Page.captureScreenshot", { format: "png" });
  if (shot?.result?.data) writeFileSync(path.join(OUT, name + ".png"), Buffer.from(shot.result.data, "base64"));
}
console.log("DONE");
ws.close(); process.exit(0);
