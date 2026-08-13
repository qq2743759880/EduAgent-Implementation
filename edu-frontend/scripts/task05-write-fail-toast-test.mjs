/**
 * task05 验收5实测 v12（真实网络失败版）：
 *   写操作（删除会话 / 发帖）后端失败 → toast 错误提示 + console.error（R-7）
 *   方案：浏览器就绪并充分水合后，用 execSync taskkill 真实停止后端 → 操作 → 断言 toast。
 *   覆盖两条 toast 路径：
 *     A 删除会话失败：handleDelete catch toast.error("删除失败") + deleteMut onError toast.error("删除会话失败")
 *     B 发帖失败：PostEditor 无本地 onError → 全局 MutationCache onError → toast.error(网络错误文案)
 */
import { chromium } from "playwright";
import { execSync } from "node:child_process";

const BASE = "http://localhost:3000";
const API = "http://127.0.0.1:8000";

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

/* ---------- 0. 造数 ---------- */
const suffix = `${Date.now()}_${Math.floor(Math.random() * 9000 + 1000)}`;
const account = `p9toast_${suffix}`;
await fetch(`${API}/api/auth/register`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account, nickname: `Toast验证${suffix.slice(-4)}`, password: "P@ssw0rd123", mobile: `135${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}` }),
});
const login = await fetch(`${API}/api/auth/login`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account, password: "P@ssw0rd123" }),
});
const loginBody = await login.json();
const token = loginBody.access_token;
const user = loginBody.user;
const cs = await fetch(`${API}/api/chat/sessions`, {
  method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ title: "toast待删会话" }),
});
const sessId = (await cs.json()).session_id;
const qText = "请介绍雅思听力备考的三种有效方法";
await fetch(`${API}/api/chat`, {
  method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ query: qText, session_id: sessId, stream: false, model: "fast", use_mcp_tools: false }),
});
console.log(`  ℹ️  造数完成 uid=${user.user_id} session=${sessId}`);

/* ---------- 1. 浏览器注入 JWT ---------- */
const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1500, height: 1000 } });
await pg.addInitScript(
  ({ tk, me }) => {
    localStorage.setItem("edu:auth:token", tk);
    localStorage.setItem("edu:auth:me", JSON.stringify(me));
    localStorage.removeItem("edu:auth:tenant");
  },
  { tk: token, me: { id: user.user_id, nickname: user.nickname, email: user.email ?? null, username: account, avatar: null, roles: ["student"], tenantId: null } },
);

const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}
const errLogs = [];
pg.on("console", (m) => { if (m.type() === "error") errLogs.push(m.text().slice(0, 200)); });

async function readToasts() {
  const texts = [];
  const n = await pg.locator('[data-sonner-toast]').count();
  for (let i = 0; i < n; i++) texts.push((await pg.locator('[data-sonner-toast]').nth(i).innerText().catch(() => "")) || "");
  return texts;
}

try {
  /* ================= A. 删除会话失败 → toast + 回滚 ================= */
  await pg.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded", timeout: 30000 });
  const sb = pg.locator('aside[aria-label="历史会话"]:visible').first();
  await sb.getByText("toast待删会话").first().waitFor({ timeout: 20000 });
  await sb.getByText("toast待删会话").first().click();
  await pg.getByText(qText).first().waitFor({ timeout: 20000 });
  await pg.waitForTimeout(2500); // 充分等待水合
  check(true, "A0 历史已渲染 + 等待水合完成");

  const toasterInfo = await pg.evaluate(() => ({
    ol: !!document.querySelector('[data-sonner-toaster]'),
    section: !!document.querySelector('section[aria-label="Notifications alt+T"]'),
  }));
  check("A1 Toaster 已挂载", toasterInfo.ol, JSON.stringify(toasterInfo));

  // 真实停止后端
  const killed = killBackend();
  console.log(`  ℹ️  后端已停止（${killed} 进程）`);
  await pg.waitForTimeout(600);

  const row = sb.locator("li", { hasText: "toast待删会话" }).first();
  await row.hover();
  await sb.getByRole("button", { name: "删除对话 toast待删会话" }).click();
  await pg.getByRole("button", { name: "确认删除" }).waitFor({ timeout: 10000 });
  await pg.getByRole("button", { name: "确认删除" }).click();

  const delToastShown = await waitFor(() => pg.locator('[data-sonner-toast]').count() > 0, 8000);
  const delToasts = await readToasts();
  check("A2 删除会话失败弹出 toast", delToastShown, delToasts.join(" || ").replace(/\n/g, " | ").slice(0, 200));
  const delJoined = delToasts.join(" || ");
  check("A3 toast 含失败文案（删除失败/网络错误）", /删除失败|网络错误/.test(delJoined), delJoined.slice(0, 200));

  await pg.waitForTimeout(2000);
  const stillThere = (await pg.getByText("toast待删会话", { exact: true }).count()) > 0;
  check("A4 失败后乐观 UI 回滚（会话仍在列表）", stillThere, "");

  /* ================= B. 发帖失败 → toast + 不跳转 ================= */
  await pg.goto(`${BASE}/community`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.waitForTimeout(2500); // 等水合（后端已死，列表为空态也 OK）
  const toasterB = await pg.evaluate(() => !!document.querySelector('[data-sonner-toaster]'));
  check("B0 Toaster 已挂载（community）", toasterB);

  await pg.getByRole("button", { name: "发布帖子" }).first().click().catch(() => undefined);
  await pg.waitForTimeout(500);
  await pg.getByRole("heading", { name: "发布新帖" }).waitFor({ timeout: 10000 }).catch(() => undefined);
  const editorOpen = await pg.evaluate(() => document.body.innerText.includes("发布新帖"));
  check("B1 发帖编辑器打开", editorOpen);
  if (editorOpen) {
    await pg.getByLabel("标题").fill("发帖失败toast实测");
    await pg.locator(".w-md-editor-text-input").fill("这是一条用于验证写操作失败 toast 的测试帖子内容。");
    await pg.getByRole("button", { name: "发布", exact: true }).click();

    const postToastShown = await waitFor(() => pg.locator('[data-sonner-toast]').count() > 0, 8000);
    const postToasts = await readToasts();
    check("B2 发帖失败弹出 toast", postToastShown, postToasts.join(" || ").replace(/\n/g, " | ").slice(0, 200));
    const postJoined = postToasts.join(" || ");
    check("B3 toast 含失败文案（网络错误/无法连接）", /网络错误|无法连接/.test(postJoined), postJoined.slice(0, 200));

    const stillOnEditor = await pg.evaluate(() => document.body.innerText.includes("发布新帖"));
    check("B4 失败后不跳转、表单保持", stillOnEditor, "");
  }

  check("B5 浏览器 console 有错误日志（不静默）", errLogs.some((t) => t.includes("posts") || t.includes("sessions") || t.includes("chat")), errLogs[0] ?? "");
} catch (err) {
  console.error("脚本异常:", err.message);
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task05 写操作失败 toast 验证：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
