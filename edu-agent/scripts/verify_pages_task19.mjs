// task19 A批收口 CDP 渲染矩阵:学生 8 页 + 管理 7 页 = 15 页
// 复用 verify_pages_w3/w3b 模式(CDP 仅用于渲染截图与 console 收集,零写操作)
// 用法: node scripts/verify_pages_task19.mjs [chrome路径] [输出目录]
import { spawn } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";

const CHROME = process.argv[2] || "D:\\tool\\chrom\\Application\\chrome.exe";
const OUT = process.argv[3] || "page-verify-task19";
const PORT = Number(process.env.CDP_PORT) || 9229, BASE = "http://127.0.0.1:3000", API = "http://127.0.0.1:8000";
mkdirSync(OUT, { recursive: true });

async function getTok(account, password) {
  const j = await fetch(API + "/api/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account, password }),
  }).then((r) => r.json());
  if (j.code !== 0 || !j.data?.access_token) throw new Error(`login fail ${account}: code=${j.code}`);
  return j.data.access_token;
}
const stok = await getTok("user000001", "Test@123456");
const atok = await getTok("adm02test", "Test@123456");
console.log(`tokens ok (student ${stok.length}B, admin ${atok.length}B)`);

let up = false;
try { await fetch(`http://127.0.0.1:${PORT}/json/version`); up = true; } catch {}
if (!up) {
  spawn(CHROME, [`--remote-debugging-port=${PORT}`,
    `${process.env.TEMP}\\edu-verify-task19`, "--headless=new", "--window-size=1440,900",
    "--no-first-run", "--disable-extensions", "about:blank"], { stdio: "ignore" });
  for (let i = 0; i < 10 && !up; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    try { await fetch(`http://127.0.0.1:${PORT}/json/version`); up = true; } catch {}
  }
}
if (!up) { console.error("chrome debug port never came up"); process.exit(1); }
const page = (await fetch(`http://127.0.0.1:${PORT}/json/list`).then((r) => r.json())).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let mid = 0; const pend = new Map(); const errs = [];
ws.onmessage = (ev) => { const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errs.push("EXC:" + (m.params.exceptionDetails?.exception?.description || "").slice(0, 200));
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") errs.push("LOG:" + m.params.entry.text.slice(0, 200)); };
const send = (method, params = {}) => new Promise((res) => { const id = ++mid; pend.set(id, res); ws.send(JSON.stringify({ id, method, params })); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
await send("Runtime.enable"); await send("Log.enable"); await send("Page.enable");

// 先导航到 login-register.html 清空 localStorage(登录页必须无 token 态)
await send("Page.navigate", { url: BASE + "/login-register.html" });
await sleep(2000);
await send("Runtime.evaluate", { expression: `localStorage.clear();1` });

const PAGES = [
  // 学生 8
  ["login-register.html", "01-login", null, 3500],
  ["courses.html", "02-courses", stok, 6000],
  ["course-detail.html?id=1", "03-course-detail", stok, 6000],
  ["dashboard.html", "04-dashboard", stok, 6000],
  ["learning.html", "05-learning", stok, 6000],
  ["me.html", "06-me", stok, 6000],
  ["achievements.html", "07-achievements", stok, 6000],
  ["chat.html", "08-chat", stok, 6000],
  // 管理 7(需 admin token,守卫三段会校验 /api/auth/me role)
  ["admin-dashboard.html", "09-admin-dashboard", atok, 8000],
  ["admin-courses.html", "10-admin-courses", atok, 8000],
  ["admin-course-detail.html?id=1", "11-admin-course-detail", atok, 8000],
  ["admin-users.html", "12-admin-users", atok, 8000],
  ["admin-questions.html", "13-admin-questions", atok, 8000],
  ["admin-rag-upload.html", "14-admin-rag-upload", atok, 8000],
  ["admin-mcp.html", "15-admin-mcp", atok, 8000],
];

const rows = [];
async function snapshot() {
  const r = await send("Runtime.evaluate", { expression: `(() => ({url:location.href, h1:(document.querySelector("h1")||{}).textContent||"",
    sh:document.documentElement.scrollHeight, wh:innerHeight, btns:document.querySelectorAll("button").length,
    hasLoginForm:!!document.querySelector("input[type=password]"),
    mockHint:/演示数据|MOCK/.test(document.body.innerText)}))()`, returnByValue: true });
  return r?.result?.result?.value || {};
}
for (const [route, name, tok, wait] of PAGES) {
  errs.length = 0;
  await send("Page.navigate", { url: BASE + "/login-register.html" });
  await sleep(1200);
  await send("Runtime.evaluate", { expression: tok ? `localStorage.setItem("edu:auth:token",${JSON.stringify(tok)});localStorage.setItem("edu:auth:refresh","x");1` : `localStorage.clear();1` });
  await send("Page.navigate", { url: `${BASE}/${route}` });
  // 轮询等待渲染就绪:h1 非空且非"加载中…",内容高度≥视口;最长 wait+18s
  const deadline = Date.now() + wait + 18000;
  let i = {};
  while (Date.now() < deadline) {
    await sleep(3000);
    try { i = await snapshot(); } catch { continue; }
    const ready = i.h1 && i.h1 !== "加载中…" && i.sh >= i.wh;
    if (ready) break;
  }
  const real = errs.filter((e) => !/favicon|DevTools/i.test(e));
  const redirected = !String(i.url || "").includes(route.split("?")[0]);
  const contentOk = i.sh >= i.wh; // 内容高度≥视口(有实际内容渲染)
  const pass = real.length === 0 && contentOk && !redirected && !!i.h1;
  rows.push({ name, route, pass, h1: i.h1, sh: i.sh, wh: i.wh, btns: i.btns, errN: real.length, errs: real.slice(0, 3), url: i.url, mockHint: i.mockHint });
  console.log(`== ${name} == ${pass ? "PASS" : "CHECK"}  h1="${(i.h1 || "").slice(0, 24)}" content=${i.sh} viewport=${i.wh} btns=${i.btns} errors=${real.length} url=${String(i.url || "").slice(-48)}${i.mockHint ? " [MOCK-WORD]" : ""}`);
  if (real.length) console.log("   errs:", JSON.stringify(real.slice(0, 3)));
  const shot = await send("Page.captureScreenshot", { format: "png" });
  if (shot?.result?.data) writeFileSync(path.join(OUT, name + ".png"), Buffer.from(shot.result.data, "base64"));
}
console.log("\n=== 渲染矩阵汇总 ===");
const passN = rows.filter((r) => r.pass).length;
rows.forEach((r) => console.log(`${r.pass ? "[PASS]" : "[CHECK]"} ${r.name} h1=${!!r.h1} content=${r.sh}/${r.wh} errors=${r.errN}`));
console.log(`汇总: PASS/OK ${passN}/${rows.length}(CHECK 项见上方逐条原因)`);
ws.close(); process.exit(0);
