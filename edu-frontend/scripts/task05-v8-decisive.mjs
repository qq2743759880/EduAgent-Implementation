/**
 * task05 决定性实验 v8：完全复制 verify-task05-chat-ui.mjs 的删除流程（含历史加载等待），
 * 同时检查 [data-sonner-toast] + getByText("对话已删除") + dump 匹配元素结构。
 */
import { chromium } from "playwright";

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

const suffix = `${Date.now()}_${Math.floor(Math.random() * 9000 + 1000)}`;
const account = `p9v8_${suffix}`;
await fetch(`${API}/api/auth/register`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account, nickname: `V8验证${suffix.slice(-4)}`, password: "P@ssw0rd123", mobile: `133${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}` }),
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
  body: JSON.stringify({ title: "v8删除对照会话" }),
});
const sessId = (await cs.json()).session_id;
// 产生历史（同 verify）
const qText = "请介绍雅思听力备考的三种有效方法";
await fetch(`${API}/api/chat`, {
  method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ query: qText, session_id: sessId, stream: false, model: "fast", use_mcp_tools: false }),
});
console.log(`  ℹ️  session=${sessId} 历史已产生`);

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

let deleteStatus = -1;
pg.on("response", (r) => {
  if (r.url().includes("/api/chat/sessions/") && r.request().method() === "DELETE") deleteStatus = r.status();
});

try {
  // ===== 完全复制 verify 流程 =====
  await pg.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.getByText("v8删除对照会话").first().waitFor({ timeout: 20000 });
  await pg.waitForTimeout(800);
  const sb = pg.locator('aside[aria-label="历史会话"]:visible').first();
  await sb.getByText("v8删除对照会话").click();
  await pg.getByText(qText).first().waitFor({ timeout: 15000 }).catch(() => undefined);
  console.log("  ℹ️  历史已点击并等待渲染");

  const row = sb.locator("li", { hasText: "v8删除对照会话" }).first();
  await row.hover();
  await sb.getByRole("button", { name: "删除对话 v8删除对照会话" }).click();
  await pg.getByRole("button", { name: "确认删除" }).waitFor({ timeout: 10000 });
  await pg.getByRole("button", { name: "确认删除" }).click();
  const delOk = await waitFor(() => deleteStatus >= 0);
  check("DELETE 200", delOk && deleteStatus === 200, `status=${deleteStatus}`);

  // ===== 双重检查 =====
  await pg.getByText("对话已删除").first().waitFor({ timeout: 10000 }).catch(() => undefined);
  const textCount = await pg.getByText("对话已删除").count();
  check("getByText 对话已删除 > 0（verify 同款）", textCount > 0, `count=${textCount}`);

  const attrCount = await pg.locator('[data-sonner-toast]').count();
  check("[data-sonner-toast] > 0", attrCount > 0, `count=${attrCount}`);

  // dump 匹配元素
  const matched = await pg.evaluate(() => {
    const out = [];
    const all = document.querySelectorAll("body *");
    for (const el of all) {
      if ((el.textContent || "").includes("对话已删除")) {
        out.push({ tag: el.tagName, cls: (el.className || "").toString().slice(0, 80), attrs: Array.from(el.attributes).slice(0, 5).map((a) => `${a.name}=${a.value}`).join(" ") });
        if (out.length >= 5) break;
      }
    }
    return out;
  });
  console.log("  ℹ️  含「对话已删除」的元素：", JSON.stringify(matched).slice(0, 500));
} catch (err) {
  console.error("脚本异常:", err.message);
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== v8 决定性实验：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
