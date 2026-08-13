#!/usr/bin/env node
/**
 * fx-task05 管理端写失败补测（task05-admin-write-fail-toast-test.mjs）
 *
 * 场景：kill 后端（真实网络失败）→ 浏览器在 /admin/courses 走「创建系列」写操作
 * 断言（R-7 审计闭环，component-contracts §3.5）：
 *  - toast 可见（全局 MutationCache 兜底：admin.ts 骨架抛 ApiError → query-client onError → toast.error）
 *  - 无 500 伪装成功（表单不提交、不出现成功提示/列表不回显假数据）
 *  - 浏览器 console 有错误日志（不静默）
 *
 * 对齐既有 task05-write-fail-toast-test.mjs L24-31 kill 模式（netstat + taskkill :8000）。
 * 鉴权：优先真实 admin 种子登录（env ADMIN_ACCOUNT/ADMIN_PASSWORD 或内置种子）；
 *       不可用则走 X-Force-Role: admin 路由注入（verify-task04-ui.mjs 模式）。
 * 注：kill 后不自动重启后端（与既有写失败脚本一致），跑完需由编排器重启 uvicorn。
 *
 * 前置：uvicorn :8000 运行中；前端 dev server :3000 运行中。
 * 运行：node scripts/task05-admin-write-fail-toast-test.mjs
 * 退出码：0 全过 / 1 断言失败 / 2 脚本异常 / 3 服务未就绪
 */
import { chromium } from "playwright";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = "http://localhost:3000";
const API = "http://127.0.0.1:8000";

/* ============ 就绪探测 ============ */
async function portUp(url, timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (r.ok || r.status < 500) return true;
    } catch { /* retry */ }
    await new Promise((res) => setTimeout(res, 700));
  }
  return false;
}
const [apiUp, webUp] = await Promise.all([portUp(`${API}/health`), portUp(`${BASE}/`)]);
if (!apiUp) {
  console.error(`[就绪探测] 后端 ${API} 未就绪 → exit 3（本脚本需要先启动后端再 kill 模拟失败）`);
  process.exit(3);
}
if (!webUp) {
  console.error(`[就绪探测] 前端 ${BASE} 未就绪 → exit 3`);
  process.exit(3);
}

const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok, extra });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  | " + extra : ""}`);
}

async function waitFor(cond, timeoutMs = 15000, stepMs = 100) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (cond()) return true;
    await new Promise((r) => setTimeout(r, stepMs));
  }
  return cond();
}

function killBackend() {
  const out = execSync('netstat -ano | findstr ":8000" | findstr LISTENING', { encoding: "utf8" });
  const pids = [...new Set(out.split(/\r?\n/).filter(Boolean).map((l) => l.trim().split(/\s+/).pop()).filter(Boolean))];
  for (const p of pids) {
    try { execSync(`taskkill /F /PID ${p}`, { stdio: "ignore" }); } catch { /* ignore */ }
  }
  return pids.length;
}

/* ============ 鉴权准备（真实 admin JWT 优先，X-Force 兜底） ============ */
let authMode = "xforce";
let adminJwt = null;
const ADMIN_SEEDS = [
  { account: process.env.ADMIN_ACCOUNT || undefined, password: process.env.ADMIN_PASSWORD || undefined },
  { account: "admin", password: "Admin@123" },
  { account: "admin", password: "admin123" },
  { account: "admin", password: "123456" },
].filter((s) => s.account && s.password);
for (const seed of ADMIN_SEEDS) {
  try {
    const r = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account: seed.account, password: seed.password }),
    });
    if (r.status === 200) {
      const j = await r.json();
      adminJwt = j.access_token;
      authMode = "jwt";
      console.log(`  ℹ️  admin 种子登录成功（${seed.account}）→ 真实 JWT 模式`);
      break;
    }
  } catch { /* try next */ }
}
if (authMode === "xforce") {
  console.log("  ℹ️  admin 种子不可用 → X-Force-Role: admin 路由注入模式（DEBUG 虚拟 admin）");
}

const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1500, height: 1000 } });

if (authMode === "jwt") {
  await pg.addInitScript(
    ({ tk }) => {
      localStorage.setItem("edu:auth:token", tk);
      localStorage.setItem("edu:auth:me", JSON.stringify({ id: 1, nickname: "联调管理员", email: "admin@edu.local", roles: ["admin"] }));
      localStorage.removeItem("edu:auth:tenant");
    },
    { tk: adminJwt },
  );
} else {
  // X-Force 模式：移除假 Authorization + 注入 X-Force-Role（verify-task04-ui.mjs L30-61 模式）
  await pg.addInitScript(() => {
    localStorage.setItem("edu:auth:token", "debug-force-token");
    localStorage.setItem("edu:auth:me", JSON.stringify({ id: 1, nickname: "调试管理员", email: "debug@edu.agent", roles: ["admin"] }));
  });
  await pg.route("http://127.0.0.1:8000/**", async (route) => {
    const req = route.request();
    const headers = {};
    for (const [k, v] of Object.entries(req.headers())) {
      if (/^content-length$/i.test(k) || /^authorization$/i.test(k)) continue;
      headers[k] = String(v);
    }
    headers["X-Force-Role"] = "admin";
    headers["X-Force-User-Id"] = "1";
    const method = req.method();
    const body = req.postDataBuffer();
    try {
      const resp = await fetch(req.url(), { method, headers, body: body ?? undefined });
      const buf = Buffer.from(await resp.arrayBuffer());
      const outHeaders = {};
      resp.headers.forEach((v, k) => {
        if (/^content-encoding$/i.test(k) || /^content-length$/i.test(k)) return;
        outHeaders[k] = v;
      });
      await route.fulfill({ status: resp.status, headers: outHeaders, body: buf });
    } catch (err) {
      console.error(`  [route.fetch] ${method} ${req.url().slice(20)} ERR: ${err instanceof Error ? err.message : String(err)}`);
      await route.abort();
    }
  });
}

const consoleErrors = [];
pg.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200)); });
pg.on("pageerror", (e) => console.error("  [pageerror]", e.message));

try {
  /* ============ 1. 打开课程管理页并等待水合 ============ */
  await pg.goto(`${BASE}/admin/courses`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.waitForTimeout(4000); // 等待水合 + 首屏查询（后端尚在，列表正常加载）
  const toasterMounted = await pg.evaluate(() => !!document.querySelector('[data-sonner-toaster]'));
  check("0. Toaster 已挂载（admin/courses）", toasterMounted);

  const createBtn = pg.locator("button:has-text('创建系列')").first();
  if ((await createBtn.count()) === 0) {
    const dump = await pg.evaluate(() => ({ url: location.href, bodyText: document.body.innerText.slice(0, 1000) }));
    check("0. 「创建系列」按钮存在", false, dump.bodyText.slice(0, 200));
    process.exitCode = 1;
  } else {
    check("0. 「创建系列」按钮存在", true);

    /* ============ 2. kill 后端 ============ */
    const killed = killBackend();
    console.log(`  ℹ️  后端已停止（${killed} 进程）—— 进入写失败场景`);
    await pg.waitForTimeout(600);

    /* ============ 3. 触发创建系列（写操作） ============ */
    await createBtn.click();
    await pg.waitForSelector("text=系列名称", { timeout: 10000 }).catch(() => undefined);
    const dialogOpen = await pg.evaluate(() => document.body.innerText.includes("系列名称"));
    check("1. 创建系列对话框打开", dialogOpen);

    if (dialogOpen) {
      const stamp = Date.now().toString(36);
      await pg.fill("[data-slot='dialog-content'] input[placeholder='2-64 字符']", `FAIL-${stamp}`).catch(() => undefined);
      await pg.fill("[data-slot='dialog-content'] input[placeholder='如：雅思基础入门系列']", `写失败补测${stamp.slice(-4)}`).catch(() => undefined);
      await pg.click("button:has-text('创建系列') >> nth=-1").catch(() => undefined);

      /* ============ 4. 断言：toast 可见 + 无 500 伪装成功 ============ */
      const toastShown = await waitFor(() => pg.locator('[data-sonner-toast]').count() > 0, 10000);
      const toasts = [];
      const n = await pg.locator('[data-sonner-toast]').count();
      for (let i = 0; i < n; i++) toasts.push(((await pg.locator('[data-sonner-toast]').nth(i).innerText().catch(() => "")) || "").replace(/\n/g, " | "));
      const joined = toasts.join(" || ").slice(0, 250);
      check("2. 创建系列失败弹出 toast（全局兜底）", toastShown, joined);

      // toast 文案含失败/网络错误语义（不得是成功文案）
      const failLike = /失败|网络错误|无法连接|请求失败|连接被拒绝|ERR_CONNECTION/i.test(joined);
      check("3. toast 含失败文案（非成功伪装）", failLike, joined.slice(0, 160));

      // 无 500 伪装成功：对话框仍打开 / 表单未提交；列表未回显新系列
      await pg.waitForTimeout(2000);
      const dialogStill = await pg.evaluate(() => document.body.innerText.includes("系列名称"));
      const listHasFake = (await pg.getByText(`写失败补测${stamp.slice(-4)}`, { exact: false }).count().catch(() => 0)) > 0;
      check("4. 无 500 伪装成功（对话框保持/无假数据回显）", dialogStill && !listHasFake, `dialog=${dialogStill} fakeList=${listHasFake}`);

      // console 有错误日志（不静默）
      check("5. 浏览器 console 有错误日志（不静默）", consoleErrors.some((t) => /series|admin|chat|network/i.test(t)), consoleErrors[0] ?? "无 console.error");
    }
  }
} catch (err) {
  console.error("脚本异常:", err instanceof Error ? err.message : String(err));
  try {
    const dump = await pg.evaluate(() => ({ url: location.href, bodyText: document.body.innerText.slice(0, 1200) }));
    const failPath = path.resolve(__dirname, "../../test-reports/task05-admin-writefail-fail.json");
    fs.mkdirSync(path.dirname(failPath), { recursive: true });
    fs.writeFileSync(failPath, JSON.stringify(dump, null, 2), "utf8");
  } catch { /* ignore */ }
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== 管理端写失败补测（task05-admin-write-fail-toast）：${results.length - failed.length}/${results.length} 通过 =====`);
console.log(`  ⚠️  后端已被 kill（${authMode} 模式）—— 请编排器在下一脚本前重启 uvicorn :8000`);
if (failed.length) process.exitCode = 1;
process.exit(process.exitCode ?? 0);
