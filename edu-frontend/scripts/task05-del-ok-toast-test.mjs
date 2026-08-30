/**
 * task05 对照实验：删除会话【成功】路径（后端在线）→ toast.success("对话已删除") 是否渲染
 * 复现 verify-task05-chat-ui.mjs 的删除成功检查，但显式检查 [data-sonner-toast]。
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
const account = `p9delok_${suffix}`;
await fetch(`${API}/api/auth/register`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account, nickname: `删除成功${suffix.slice(-4)}`, password: "P@ssw0rd123", mobile: `134${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}` }),
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
  body: JSON.stringify({ title: "删除成功对照会话" }),
});
const sessId = (await cs.json()).session_id;

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

try {
  await pg.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.getByText("删除成功对照会话").first().waitFor({ timeout: 20000 });

  const before = await pg.evaluate(() => {
    const s = document.querySelector('section[aria-label="Notifications alt+T"]');
    return { ol: !!document.querySelector('[data-sonner-toaster]'), sectionHTML: s ? s.outerHTML.slice(0, 400) : null };
  });
  check("加载后 Toaster 结构", before.ol, JSON.stringify(before).slice(0, 300));

  const sb = pg.locator('aside[aria-label="历史会话"]:visible').first();
  await sb.getByText("删除成功对照会话").first().click();
  const row = sb.locator("li", { hasText: "删除成功对照会话" }).first();
  await row.hover();
  await sb.getByRole("button", { name: "删除对话 删除成功对照会话" }).click();
  await pg.getByRole("button", { name: "确认删除" }).waitFor({ timeout: 10000 });
  await pg.getByRole("button", { name: "确认删除" }).click();

  const toastShown = await waitFor(() => pg.locator('[data-sonner-toast]').count() > 0, 8000);
  const n = await pg.locator('[data-sonner-toast]').count();
  const texts = [];
  for (let i = 0; i < n; i++) texts.push((await pg.locator('[data-sonner-toast]').nth(i).innerText().catch(() => "")) || "");
  check("删除成功 [data-sonner-toast] 渲染", toastShown, `count=${n} ${texts.join("||").replace(/\n/g, " | ").slice(0, 120)}`);

  const textMatch = (await pg.getByText("对话已删除").count()) > 0;
  check("删除成功 getByText 对话已删除（verify 同款检查）", textMatch, "");

  if (!toastShown) {
    const after = await pg.evaluate(() => {
      const s = document.querySelector('section[aria-label="Notifications alt+T"]');
      return { ol: !!document.querySelector('[data-sonner-toaster]'), sectionHTML: s ? s.outerHTML.slice(0, 500) : null, bodySnippet: document.body.innerText.includes("对话已删除") };
    });
    check("toast 未渲染时 section 结构", false, JSON.stringify(after).slice(0, 400));
  }
} catch (err) {
  console.error("脚本异常:", err.message);
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== 对照实验（删除成功 toast）：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
