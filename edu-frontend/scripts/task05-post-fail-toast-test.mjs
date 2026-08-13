/**
 * task05 验收5实测：写操作（发帖）失败 → toast 错误提示（R-7）
 * v3：凭据由 prep 脚本写入临时 JSON（本脚本不再访问 API），后端生命周期由外部 bash 控制。
 * 前置：8000 已被外部停止（网络不可达）。
 */
import { chromium } from "playwright";
import fs from "node:fs";

const BASE = "http://localhost:3000";
const CRED = "C:/Users/Administrator/AppData/Local/Temp/opencode/task05_toast_cred.json";
const cred = JSON.parse(fs.readFileSync(CRED, "utf8"));
const { token, user } = cred;

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
  { tk: token, me: { id: user.user_id, nickname: user.nickname, email: user.email ?? null, username: user.account ?? user.username ?? cred.account, avatar: null, roles: ["student"], tenantId: null } },
);

const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  — " + extra : ""}`);
}

const errLogs = [];
pg.on("console", (m) => { if (m.type() === "error") errLogs.push(m.text().slice(0, 200)); });

try {
  await pg.goto(`${BASE}/community`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await pg.getByRole("button", { name: "发布帖子" }).first().waitFor({ timeout: 20000 });
  await pg.getByRole("button", { name: "发布帖子" }).first().click();
  await pg.getByRole("heading", { name: "发布新帖" }).waitFor({ timeout: 10000 });
  await pg.getByLabel("标题").fill("发帖失败toast实测");
  await pg.locator(".w-md-editor-text-input").fill("这是一条用于验证写操作失败 toast 的测试帖子内容。");
  check(true, "发帖编辑器打开并填写表单");

  const toasterMounted = await pg.evaluate(() => !!document.querySelector("[data-sonner-toaster]"));
  check("Toaster 组件已挂载", toasterMounted);

  // 后端已由外部停止 → 提交
  await pg.getByRole("button", { name: "发布", exact: true }).click();

  const toastShown = await waitFor(() => pg.locator('[data-sonner-toast]').count() > 0, 8000);
  let toastText = "";
  if (toastShown) {
    toastText = (await pg.locator('[data-sonner-toast]').first().innerText().catch(() => "")) || "";
  }
  check("发帖失败弹出 toast", toastShown, toastText.replace(/\n/g, " | ").slice(0, 120));
  const toastHasErrorMsg = /网络错误|无法连接|请求失败|失败/.test(toastText);
  check("toast 文案为错误提示", toastHasErrorMsg, toastText.replace(/\n/g, " | ").slice(0, 120));

  const stillOnEditor = await pg.evaluate(() => document.body.innerText.includes("发布新帖"));
  check("失败后不跳转、表单保持", stillOnEditor);

  await pg.waitForTimeout(500);
  check("浏览器 console 有错误日志（不静默）", errLogs.some((t) => t.includes("ERR_CONNECTION_REFUSED") || t.includes("posts")), errLogs[0] ?? "");
} catch (err) {
  console.error("脚本异常:", err.message);
  process.exitCode = 2;
} finally {
  await b.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== task05 发帖失败 toast 验证：${results.length - failed.length}/${results.length} 通过 =====`);
process.exit(failed.length > 0 ? 1 : 0);
