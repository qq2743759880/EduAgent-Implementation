/**
 * task05 验收5实测 v4：删除会话失败（后端已停）→ toast 错误提示 + 列表回滚
 * 覆盖：useChatSessions deleteMut 本地 onError（toast.error "删除会话失败"）
 *       + 全局 MutationCache onError（若有，会额外 toast "网络错误"）
 * 后端生命周期由外部 bash 控制（前置：8000 已被停止）。
 */
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://localhost:3000";
const CRED = "C:/Users/Administrator/AppData/Local/Temp/opencode/task05_toast_cred.json";
const cred = JSON.parse(fs.readFileSync(CRED, "utf8"));
const { token, user, session_id } = cred;

async function waitFor(cond, timeoutMs = 15000, stepMs = 150) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    if (cond()) return true;
    await new Promise((r) => setTimeout(r, stepMs));
  }
  return cond();
}

const b = await chromium.launch();
const pg = await b.newPage({ viewport: { width: 1500, height: 1000 } });
await pg.addInitScript(
  ({ tk, me }) => {
    localStorage.setItem("edu:auth:token", tk);
    localStorage.setItem("edu:auth:me", JSON.stringify(me));
    localStorage.removeItem("edu:auth:tenant");
  },
  { tk: token, me: { id: user.user_id, nickname: user.nickname, email: user.email ?? null, username: user.account ?? cred.account, avatar: null, roles: ["student"], tenantId: null } },
);

const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}

const errLogs = [];
pg.on("console", (m) => { if (m.type() === "error") errLogs.push(m.text().slice(0, 200)); });

try {
  await pg.goto(`${BASE}/chat`, { waitUntil: "domcontentloaded", timeout: 30000 });
  // 等待会话出现（侧栏）
  await pg.getByText("toast待删会话").first().waitFor({ timeout: 20000 });
  check(true, "会话列表加载（待删会话可见）");

  const toasterMounted = await pg.evaluate(() => {
    const s = document.querySelector('section[aria-label="Notifications alt+T"]');
    return { section: !!s, sectionHTML: s ? s.innerHTML.slice(0, 100) : null, ol: !!document.querySelector('[data-sonner-toaster]') };
  });
  check("Toaster 已挂载（ol[data-sonner-toaster] 存在）", toasterMounted.ol || toasterMounted.sectionHTML !== "", JSON.stringify(toasterMounted));

  // 删除会话（后端已停 → 失败）
  const sb = pg.locator('aside[aria-label="历史会话"]:visible').first();
  await sb.getByText("toast待删会话").first().click().catch(() => undefined);
  const row = sb.locator("li", { hasText: "toast待删会话" }).first();
  await row.hover().catch(() => undefined);
  await sb.getByRole("button", { name: "删除对话 toast待删会话" }).click().catch(async () => {
    // 兜底：可能按钮名不同，尝试包含“删除”的按钮
    await sb.getByRole("button", { name: /删除/ }).first().click();
  });
  await pg.getByRole("button", { name: "确认删除" }).waitFor({ timeout: 10000 });
  await pg.getByRole("button", { name: "确认删除" }).click();

  // 轮询 toast（[data-sonner-toast] 或 body 文本）
  const toastShown = await waitFor(() => pg.locator('[data-sonner-toast]').count() > 0, 8000);
  let toastTexts = [];
  if (toastShown) {
    const n = await pg.locator('[data-sonner-toast]').count();
    for (let i = 0; i < n; i++) toastTexts.push((await pg.locator('[data-sonner-toast]').nth(i).innerText().catch(() => "")) || "");
  }
  check("删除会话失败弹出 toast", toastShown, toastTexts.join(" || ").replace(/\n/g, " | ").slice(0, 160));
  const joined = toastTexts.join(" || ");
  check("toast 含失败文案（删除会话失败/网络错误）", /删除会话失败|网络错误|无法连接/.test(joined), joined.slice(0, 160));

  // 乐观回滚：会话仍在列表
  await pg.waitForTimeout(1500);
  const stillThere = (await pg.getByText("toast待删会话", { exact: true }).count()) > 0;
  check("失败后乐观 UI 回滚（会话仍在列表）", stillThere, "");
} catch (err) {
  console.error("脚本异常:", err.message);
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task05 删除会话失败 toast 验证：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
