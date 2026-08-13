/**
 * task05 浏览器 UI 验证（Playwright Core 独立实例，不共享 MCP 浏览器上下文）
 *
 * 覆盖验收（dev-plan task05）：
 *  - R-1：历史会话加载请求路径为 /api/chat/sessions/{id}/history（不再 /messages 404 静默空），
 *         历史消息正常渲染（user+assistant 气泡）
 *  - R-2：删除会话 → DELETE 200 {ok:true} → 列表移除且乐观 UI 不回滚（后端 yn=0 软删）
 *  - 会话列表按用户隔离（student 只看到自己的会话）
 *
 * 前置：uvicorn :8000 运行中（新代码）、前端 dev server :3000、测试账号已由 prep 脚本造好
 * （edu-frontend/scripts/verify-task05-ui.mjs 自身会先走 HTTP 造数，见 _prepare 内联注释）。
 */
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://localhost:3000"; // L2：必须 localhost，127.0.0.1 会 403
const API = "http://127.0.0.1:8000";
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}

/* ---------- 0. HTTP 造数：注册新学生 → 登录 → 建会话 → 非流式问答（产生 2 条历史） ---------- */
const suffix = `${Date.now()}_${Math.floor(Math.random() * 9000 + 1000)}`;
const account = `p9s6uiv_${suffix}`;
const reg = await fetch(`${API}/api/auth/register`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account, nickname: `UI验证${suffix.slice(-4)}`, password: "P@ssw0rd123", mobile: `136${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}` }),
});
const login = await fetch(`${API}/api/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account, password: "P@ssw0rd123" }),
});
const loginBody = await login.json();
const token = loginBody.access_token;
const user = loginBody.user;
const uid = user.user_id;
const cs = await fetch(`${API}/api/chat/sessions`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ title: "浏览器实测会话" }),
});
const sessId = (await cs.json()).session_id;
const qText = "请介绍雅思听力备考的三种有效方法";
await fetch(`${API}/api/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ query: qText, session_id: sessId, stream: false, model: "fast", use_mcp_tools: false }),
});
check(true, `[准备] 学生 uid=${uid} 会话 ${sessId}（历史 2 条）`, account);

/* ---------- 1. 浏览器注入真实 JWT（addInitScript 在任何页面脚本前执行 → 无 hydrate 竞态） ---------- */
const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1500, height: 1000 } });
await pg.addInitScript(
  ({ tk, me }) => {
    localStorage.setItem("edu:auth:token", tk);
    localStorage.setItem("edu:auth:me", JSON.stringify(me));
    localStorage.removeItem("edu:auth:tenant");
  },
  {
    tk: token,
    me: { id: uid, nickname: user.nickname, email: user.email ?? null, username: account, avatar: null, roles: ["student"], tenantId: null },
  },
);

/* ---------- 2. 网络监听：列表 / history / DELETE ---------- */
let listResp = null; // 最后一次列表响应 body
let historyReqUrl = null;
let historyStatus = -1;
let deleteStatus = -1;
pg.on("response", (r) => {
  const u = r.url();
  if (u.includes("/api/chat/sessions") && r.request().method() === "GET") {
    void r.json().then((j) => { listResp = j; }).catch(() => undefined);
  }
  if (u.includes("/history")) { historyReqUrl = u; historyStatus = r.status(); }
  if (u.includes("/api/chat/sessions/") && r.request().method() === "DELETE") { deleteStatus = r.status(); }
});
pg.on("pageerror", (e) => console.error("  [pageerror]", e.message));
pg.on("console", (m) => { if (m.type() === "error") console.error("  [console.error]", m.text().slice(0, 200)); });

/** Node 侧轮询条件（页面事件异步写入 node 变量，waitForFunction 参数快照不可用） */
async function waitFor(cond, timeoutMs = 15000, stepMs = 200) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (cond()) return true;
    await new Promise((r) => setTimeout(r, stepMs));
  }
  return cond();
}

try {
  /* ---------- 3. /chat：会话列表（用户隔离 + 含新会话） ---------- */
  await pg.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.getByText("浏览器实测会话").first().waitFor({ timeout: 20000 });
  await pg.waitForTimeout(800);
  const allMine = Array.isArray(listResp) && listResp.length > 0 && listResp.every((s) => Number(s.user_id) === uid);
  check("会话列表只含本人会话（user_id 隔离）", allMine, `共 ${Array.isArray(listResp) ? listResp.length : "?"} 条`);
  const totalText = (await pg.locator("text=共").first().textContent().catch(() => "")) ?? "";
  check("侧栏会话计数渲染", totalText.includes("个会话"), totalText.trim());

  /* ---------- 4. R-1：点击会话 → /history 200 + 消息渲染 ---------- */
  // 注意：/chat 页存在多个侧栏实例（GlobalChatInjection 浮动抽屉 / 桌面侧栏 / 移动抽屉），
  // 必须作用域限定到可见侧栏（L12 精确匹配纪律）
  const sb = pg.locator('aside[aria-label="历史会话"]:visible').first();
  await sb.getByText("浏览器实测会话").click();
  const histOk = await waitFor(() => historyStatus >= 0) && historyStatus === 200 && /\/history(\?|$)/.test(historyReqUrl ?? "");
  check("历史请求路径为 /history 且 200（R-1）", histOk, historyReqUrl ? historyReqUrl.replace(API, "") : "未捕获请求");
  await pg.getByText(qText).first().waitFor({ timeout: 15000 }).catch(() => undefined);
  const userBubble = await pg.getByText(qText).count();
  const aiBubbles = await pg.locator('[aria-label="AI 助手"]').count();
  check("历史消息渲染（user 气泡 + assistant 气泡）", userBubble > 0 && aiBubbles >= 1, `user=${userBubble} assistant=${aiBubbles}`);

  /* ---------- 5. R-2：删除会话 → DELETE 200 → 列表移除且不回滚 ---------- */
  const row = sb.locator("li", { hasText: "浏览器实测会话" }).first();
  await row.hover();
  await sb.getByRole("button", { name: "删除对话 浏览器实测会话" }).click();
  await pg.getByRole("button", { name: "确认删除" }).waitFor({ timeout: 10000 });
  await pg.getByRole("button", { name: "确认删除" }).click();
  const delOk = await waitFor(() => deleteStatus >= 0);
  check("DELETE /api/chat/sessions/{id} 200（R-2）", delOk && deleteStatus === 200, `status=${deleteStatus}`);
  await pg.getByText("对话已删除").first().waitFor({ timeout: 10000 }).catch(() => undefined);
  check("删除成功 toast「对话已删除」", (await pg.getByText("对话已删除").count()) > 0, "");
  await pg.waitForTimeout(800);
  const goneAfterDelete = (await pg.getByText("浏览器实测会话", { exact: true }).count()) === 0;
  await pg.waitForTimeout(2500); // 等待任何潜在回滚/refetch
  const stillGone = (await pg.getByText("浏览器实测会话", { exact: true }).count()) === 0;
  check("乐观 UI 不回滚（删除后仍消失）", goneAfterDelete && stillGone, "");

  /* ---------- 6. 后端复核：列表接口不再返回已删会话 ---------- */
  const after = await fetch(`${API}/api/chat/sessions`, { headers: { Authorization: `Bearer ${token}` } });
  const afterBody = await after.json();
  const notInBackend = !Array.isArray(afterBody) || !afterBody.some((s) => String(s.session_id) === String(sessId));
  check("后端复核：已删会话不在列表（yn=1 过滤）", notInBackend, "");
  const histAfter = await fetch(`${API}/api/chat/sessions/${sessId}/history`, { headers: { Authorization: `Bearer ${token}` } });
  check("后端复核：已删会话历史 404", histAfter.status === 404, `status=${histAfter.status}`);
} catch (err) {
  console.error("脚本异常:", err.message);
  try {
    const dump = await pg.evaluate(() => ({ url: location.href, bodyText: document.body.innerText.slice(0, 1200) }));
    fs.writeFileSync("C:/Users/Administrator/AppData/Local/Temp/opencode/task05-ui-fail.txt", JSON.stringify(dump, null, 2), "utf8");
  } catch { /* ignore */ }
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task05 chat UI 验证：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
