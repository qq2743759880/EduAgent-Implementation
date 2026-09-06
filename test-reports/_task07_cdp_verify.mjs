// task07 chat.html 独立实证 v2（headless Chrome + CDP，零依赖，非 Playwright）
// 用法: node _task07_cdp_verify.mjs
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";

const CHROME = "D:\\tool\\chrom\\Application\\chrome.exe";
const PORT = 9228;
const FE = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000";
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok, detail }); console.log((ok ? "PASS" : "FAIL") + " | " + name + " | " + detail); };

// 1. 学生登录拿 token
const login = await fetch(API + "/api/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "user000001", password: "Test@123456" }),
}).then(r => r.json());
if (login.code !== 0) { console.error("LOGIN FAIL", login); process.exit(1); }
const token = login.data.access_token;
check("backend-login", true, "student token ok");

// 2. 启动 headless chrome
const proc = spawn(CHROME, [
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${process.env.TEMP}\\edu-task07-profile`,
  "--headless=new", "--window-size=1440,900", "--no-first-run",
  "--disable-extensions", "--no-default-browser-check", "about:blank",
], { stdio: "ignore" });
await new Promise(r => setTimeout(r, 3000));
const cleanup = () => { try { proc.kill(); } catch (e) {} };
process.on("exit", cleanup);

const list = await fetch(`http://127.0.0.1:${PORT}/json/list`).then(r => r.json());
const page = list.find(t => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let mid = 0; const pending = new Map();
const consoleErrors = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled" && m.params.type === "error")
    consoleErrors.push(m.params.args.map(a => a.value ?? a.description ?? "").join(" ").slice(0, 200));
  if (m.method === "Runtime.exceptionThrown")
    consoleErrors.push("EXC: " + (m.params.exceptionDetails?.exception?.description || m.params.exceptionDetails?.text || "").slice(0, 200));
};
const send = (method, params = {}) => new Promise((res) => {
  const id = ++mid; pending.set(id, res);
  ws.send(JSON.stringify({ id, method, params }));
});
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const evalJs = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.result?.exceptionDetails) return { __err: (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text || "").slice(0, 200) };
  return r.result?.result?.value;
};

await send("Runtime.enable");
await send("Page.enable");

// 3. 打开 chat.html → 注入 token → 重载（真实页面加载路径）
await send("Page.navigate", { url: FE + "/chat.html" });
await sleep(1500);
await evalJs(`localStorage.setItem("edu:auth:token", ${JSON.stringify(token)}); "tok"`);
await send("Page.navigate", { url: FE + "/chat.html" });
await sleep(2500);

// 4. 断言：真实会话列表渲染（demo 假数据被替换）
const sessCount = await evalJs(`document.querySelectorAll("#sideList .sess").length`);
const sessIds = await evalJs(`Array.from(document.querySelectorAll("#sideList .sess")).map(b=>b.dataset.id).slice(0,3).join(",")`);
check("real-sessions-rendered", sessCount > 0 && sessIds.includes("s_"), `count=${sessCount} ids=${sessIds}`);
const demoLeak = await evalJs(`document.getElementById("stage").textContent.includes("反向传播")`);
check("demo-data-replaced", !demoLeak, "stage 无演示假消息");
const ctxHidden = await evalJs(`getComputedStyle(document.getElementById("ctxTag")).display==="none"`);
check("fake-ctx-hidden", ctxHidden, "静态假上下文徽标已隐藏");

// 5. 切换会话 → 历史真实渲染
const firstId = await evalJs(`document.querySelector("#sideList .sess").dataset.id`);
await evalJs(`document.querySelector("#sideList .sess[data-id='${firstId}']").click(); "clicked"`);
await sleep(1200);
const histMsgs = await evalJs(`document.querySelectorAll("#stage .msg").length`);
const activeOn = await evalJs(`document.querySelector("#sideList .sess.on")?.dataset.id === "${firstId}"`);
check("session-switch-history", activeOn, `first=${firstId} msgs=${histMsgs}`);

// 6. 新建会话 A（真实 POST）→ 空态诚实
const baseCount = await evalJs(`document.querySelectorAll("#sideList .sess").length`);
await evalJs(`document.getElementById("newSession").click(); "new"`);
await sleep(1200);
const cntA = await evalJs(`document.querySelectorAll("#sideList .sess").length`);
const idA = await evalJs(`document.querySelector("#sideList .sess.on")?.dataset.id`);
const emptyShown = await evalJs(`!!document.querySelector("#stage .empty")`);
check("create-session", cntA === baseCount + 1 && idA && emptyShown, `list ${baseCount}->${cntA} A=${idA} empty=${emptyShown}`);

// 7. 会话 A 内真实 SSE 流式发送 → done 后 keepView
await evalJs(`(() => {
  const ii = document.getElementById("composerInput");
  ii.value = "只回答一个词：1+1等于几？";
  document.getElementById("sendBtn").click();
  return "sent";
})()`);
await sleep(800);
const streamingUi = await evalJs(`({
  q: getComputedStyle(document.getElementById("queueHint")).display !== "none",
  disabled: document.getElementById("sendBtn").disabled
})`);
check("streaming-state-honest", streamingUi.q === true && streamingUi.disabled === true, JSON.stringify(streamingUi));
let done = false, aiText = "";
for (let t = 0; t < 40; t++) {
  await sleep(1500);
  aiText = (await evalJs(`(document.getElementById("aiResp")||{textContent:""}).textContent`)) || "";
  const en = await evalJs(`document.getElementById("sendBtn").disabled`);
  if (!en && aiText && !aiText.includes("思考中")) { done = true; break; }
}
check("sse-stream-completed", done && aiText.length > 0, `len=${aiText.length} sample=${aiText.slice(0, 40)}`);
const cntAfterSend = await evalJs(`document.querySelectorAll("#sideList .sess").length`);
const keptActive = await evalJs(`document.querySelector("#sideList .sess.on")?.dataset.id === "${idA}"`);
const stageStill = await evalJs(`(document.getElementById("aiResp")||{textContent:""}).textContent.length > 0`);
check("done-keepview", cntAfterSend === cntA && keptActive && stageStill, `list=${cntAfterSend} active kept=${keptActive} content kept=${stageStill}`);

// 8. 删除会话 A（真实 DELETE，UI 点击 .del）
await evalJs(`document.querySelector('#sideList .sess[data-id="${idA}"] .del').click(); "del"`);
await sleep(1500);
const cntDel = await evalJs(`document.querySelectorAll("#sideList .sess").length`);
const aGone = await evalJs(`!document.querySelector('#sideList .sess[data-id="${idA}"]')`);
check("delete-session", cntDel === baseCount && aGone, `list ${cntA}->${cntDel} A removed=${aGone}`);

// 9. 流式中断降级：新会话 B 发送后立即派发 offline → failStream 诚实提示 + 保留已生成内容
await evalJs(`document.getElementById("newSession").click(); "newB"`);
await sleep(1500);
const idB = await evalJs(`document.querySelector("#sideList .sess.on")?.dataset.id`);
const sendRet = await evalJs(`(() => {
  const ii = document.getElementById("composerInput");
  ii.value = "用三句话介绍递归。";
  document.getElementById("sendBtn").click();
  return "sent2";
})()`);
console.log("  [dbg] send2 ret:", JSON.stringify(sendRet));
const trace = [];
for (let t = 0; t < 6; t++) {
  await sleep(700);
  trace.push(await evalJs(`({
    ai: (document.getElementById("aiResp")||{textContent:""}).textContent.length,
    dis: document.getElementById("sendBtn").disabled,
    q: getComputedStyle(document.getElementById("queueHint")).display !== "none"
  })`));
}
console.log("  [dbg] trace:", JSON.stringify(trace));
await evalJs(`window.dispatchEvent(new Event("offline")); "offline"`);
await sleep(800);
const offToast = await evalJs(`({show: document.getElementById("toast").style.display !== "none", msg: document.getElementById("toastMsg").textContent})`);
const reEnabled = await evalJs(`!document.getElementById("sendBtn").disabled`);
const partialKept = await evalJs(`(document.getElementById("aiResp")||{textContent:""}).textContent.length`);
check("offline-degrade", offToast.show && offToast.msg.includes("断开") && reEnabled, JSON.stringify(offToast) + ` partialKept=${partialKept}`);
// 清理：删除会话 B（API 直删）
if (idB) await fetch(API + "/api/chat/sessions/" + idB, { method: "DELETE", headers: { Authorization: "Bearer " + token } });

// 10. 会话/历史加载失败 → 诚实错误态 + 重试恢复（改 EAPI.BASE 指向不可达端口，不重载）
await evalJs(`EAPI.BASE = "http://127.0.0.1:59999"; document.getElementById("toast").style.display = "none"; "base-bad"`);
const sess2 = await evalJs(`document.querySelectorAll("#sideList .sess")[1]?.dataset.id`);
await evalJs(`document.querySelector("#sideList .sess[data-id='${sess2}']").click(); "switch-bad"`);
let errShown = false;
for (let t = 0; t < 12; t++) {   /* Chrome 对 refused 连接有重试退避，轮询至多 ~9s */
  await sleep(750);
  errShown = await evalJs(`!!document.querySelector("#stage .error-st")`);
  if (errShown) break;
}
const errTxt = await evalJs(`(document.querySelector("#stage .error-st .d")||{textContent:""}).textContent`);
check("history-error-state", errShown, `error-st 渲染: ${errTxt.slice(0, 60)}`);
await evalJs(`EAPI.BASE = "http://127.0.0.1:8000"; "base-ok"`);
const retryRet = await evalJs(`var b=document.getElementById("stageRetry"); b ? (b.click(), "retry") : "no-retry-btn"`);
console.log("  [dbg] retry:", JSON.stringify(retryRet));
await sleep(1500);
const recovered = await evalJs(`!document.querySelector("#stage .error-st")`);
check("error-retry-recovers", retryRet === "retry" && recovered, `retry=${retryRet} recovered=${recovered}`);

// 11. console 无 JS 异常（排除预期的网络错误日志）
const realErrors = consoleErrors.filter(e => !/ERR_CONNECTION_REFUSED|Failed to load resource|网络错误|EAPI|加载失败/.test(e));
check("console-no-js-errors", realErrors.length === 0, `total=${consoleErrors.length} real=${realErrors.length} ${realErrors.slice(0, 2).join(" || ")}`);

writeFileSync("task07-cdp-result.json", JSON.stringify({ results, consoleErrors }, null, 1), "utf-8");
const fails = results.filter(r => !r.ok).length;
console.log(fails === 0 ? "ALL PASS" : `${fails} FAIL`);
cleanup();
process.exit(fails === 0 ? 0 : 1);
