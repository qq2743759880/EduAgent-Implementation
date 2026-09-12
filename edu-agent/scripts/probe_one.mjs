// 单页精简探针: node probe_one.mjs <wsPort> <path> — 登录注入+9s 等待+正文快照
const PORT = process.argv[2], ROUTE = process.argv[3];
const BASE = "http://127.0.0.1:3000", API = "http://127.0.0.1:8000";
const login = await fetch(API + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: process.argv[4]||"user000001", password: process.argv[5]||"Test@123456" }) }).then(r => r.json());
const tok = login.data.access_token;
const page = (await fetch(`http://127.0.0.1:${PORT}/json/list`).then(r => r.json())).find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let mid = 0; const pend = new Map(); const errs = [];
ws.onmessage = ev => { const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") errs.push((m.params.exceptionDetails?.exception?.description || "").slice(0, 150)); };
const send = (m, p = {}) => new Promise(res => { const id = ++mid; pend.set(id, res); ws.send(JSON.stringify({ id, method: m, params: p })); });
await send("Runtime.enable"); await send("Page.enable");
await send("Page.navigate", { url: BASE + "/login-register.html" });
await new Promise(r => setTimeout(r, 2000));
await send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token",${JSON.stringify(tok)});1` });
await send("Page.navigate", { url: BASE + "/" + ROUTE });
await new Promise(r => setTimeout(r, 9000));
const r = await send("Runtime.evaluate", { expression: `document.body.innerText.replace(/\\n+/g," | ").slice(0,500)`, returnByValue: true });
console.log("URL:", ROUTE);
console.log("BODY:", r?.result?.result?.value);
console.log("ERRORS:", JSON.stringify(errs.filter(e => !/favicon/.test(e))));
ws.close(); process.exit(0);
