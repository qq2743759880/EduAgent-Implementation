// W1-C1 单飞 refresh 自检：并发 N 个 401 → 只发 1 次 /api/auth/refresh（Promise 复用）
// 直接加载真实 edu-api.js（node 环境 shim），用 fetch 门计数真实网络调用。
// 运行：node selfcheck-singleflight-refresh.mjs
import fs from "node:fs";
import vm from "node:vm";

const base = fs.readFileSync(new URL("../edu-frontend/public/edu-api.js", import.meta.url), "utf8");

// ---- 浏览器环境 shim（窗口 IIFE 依赖）----
const storage = {};
const localStorage = {
  getItem: (k) => (k in storage ? storage[k] : null),
  setItem: (k, v) => { storage[k] = String(v); },
  removeItem: (k) => { delete storage[k]; },
};
let __redirected = false;
const location = {
  pathname: "/admin-courses.html",
  search: "",
  origin: "http://localhost:3000",
};
Object.defineProperty(location, "href", { set: () => { __redirected = true; }, get: () => "/login-register.html" });
Object.defineProperty(location, "replace", { value: () => { __redirected = true; } });
const documentShim = {
  createElement: () => ({ style: {}, set textContent(v) {}, }),
  body: { appendChild: () => {} },
  getElementById: () => null,
};
const matchMedia = () => ({ matches: false });
const requestAnimationFrame = (f) => { try { f(); } catch (e) {} };

// ---- 网络门：数真实 refresh 请求；数据 API 前 data401Left 次返回 401 ----
let data401Left = 5;    // 并发 5 个数据请求一律先 401
let refreshCalls = 0;    // 真实 /api/auth/refresh 次数（本次断言核心）
function fetch(url, opts) {
  const u = String(url);
  if (u.indexOf("/api/auth/refresh") >= 0) {
    refreshCalls++;
    return Promise.resolve({
      status: 200, ok: true,
      text: () => Promise.resolve(JSON.stringify({ code: 0, data: { access_token: "NEW_AT", refresh_token: "NEW_RT", expires_in: 3600, token_type: "bearer", user: {} } })),
    });
  }
  if (data401Left > 0) { data401Left--; return Promise.resolve({ status: 401, ok: false, text: () => Promise.resolve(JSON.stringify({ code: 40111, message: "expired" })) }); }
  return Promise.resolve({ status: 200, ok: true, text: () => Promise.resolve(JSON.stringify({ code: 0, data: { ok: true } })) });
}

// 打到全局供 edu-api.js 裸引用（window/document/localStorage/location/fetch…）
const windowObj = { location, document: documentShim, matchMedia };
for (const [k, v] of Object.entries({ window: windowObj, document: documentShim, localStorage, location, fetch, matchMedia, requestAnimationFrame })) {
  Object.defineProperty(globalThis, k, { value: v, configurable: true, writable: true });
}

// 预置登录态（有 refresh_token）
storage["edu:auth:token"] = "OLD_AT";
storage["edu:auth:refresh"] = "RT_1";

vm.runInThisContext(base + ";", { filename: "edu-api.js" });
const EAPI = windowObj.EAPI;
if (!EAPI || typeof EAPI.get !== "function") { console.error("FAIL: edu-api.js 未导出 EAPI"); process.exit(1); }

// ---- 并发 5 个数据请求，各自先吃到 401 再走单飞 refresh + 重放 ----
const results = await Promise.all(
  Array.from({ length: 5 }, () => EAPI.get("/api/data"))
);
results.forEach((r) => {
  if (!r || r.ok !== true) { console.error("FAIL: 重放结果异常", r); process.exit(1); }
});

console.log("并发 5 请求全部成功（refresh 后各重放一次拿到 200）:", results.length === 5 ? "PASS" : "FAIL");
console.log("实际 /api/auth/refresh 调用次数 =", refreshCalls, "(期望 1)");
console.log("重放后存储 access =", storage["edu:auth:token"], "(期望 NEW_AT)");
console.log("重放后存储 refresh =", storage["edu:auth:refresh"], "(期望 NEW_RT)");

// 断言：并发 N=5 次 401 只发 1 次 refresh
if (refreshCalls !== 1) { console.error("FAIL: refresh 应只发 1 次，实际", refreshCalls); process.exit(1); }
if (storage["edu:auth:token"] !== "NEW_AT") { console.error("FAIL: access 未更新"); process.exit(1); }
if (storage["edu:auth:refresh"] !== "NEW_RT") { console.error("FAIL: refresh 未滑动续期"); process.exit(1); }

// 再验「无 refresh_token → 跳过 refresh 直登登录跳转」
storage["edu:auth:token"] = "AT2";
delete storage["edu:auth:refresh"];
data401Left = 1; // 下一次数据请求返回 401，触发 refresh 判定
const pre = refreshCalls;
try { await EAPI.get("/api/data"); } catch (e) { /* 401 → 无 refresh_token → handleUnauthorized 抛错 */ }
if (refreshCalls !== pre || __redirected !== true) {
  console.error("FAIL: 无 refresh_token 时应跳过 refresh 并跳登录");
  process.exit(1);
}
console.log("无 refresh_token 场景：跳过 refresh(次数不变)、触发跳登录 — PASS");
console.log("\nALL PASS: 单飞 refresh 仅触发 1 次，重放一次并滑动续期，缺 refresh_token 降级跳登录");