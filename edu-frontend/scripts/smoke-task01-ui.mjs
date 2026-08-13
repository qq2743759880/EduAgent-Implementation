/**
 * task01 UI 冒烟验证（Playwright）：登录后真实数据渲染
 * 运行：node scripts/smoke-task01-ui.mjs
 * 前置：dev server :3000 + backend :8000 运行中
 *
 * 注意：BASE 必须用 localhost（而非 127.0.0.1）——Next.js dev 服务器对
 * 非 localhost Origin 的模块脚本请求返回 403（allowedDevOrigins 安全校验）。
 */
import { chromium } from "playwright";

const BASE = "http://localhost:3000";
const API = "http://127.0.0.1:8000";

async function loginToken() {
  const resp = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: "task01test", password: "Test@123456" }),
  });
  const data = await resp.json();
  return data.access_token;
}

const results = [];
const check = (name, cond, extra = "") => {
  results.push(!!cond);
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}${extra ? "  | " + extra : ""}`);
};

const browser = await chromium.launch();
try {
  const token = await loginToken();
  const user = {
    id: 846,
    nickname: "任务一测试",
    email: "task01test@gmail.com",
    roles: ["student"],
    username: "task01test",
  };

  const ctx = await browser.newContext();
  await ctx.addInitScript(
    ([t, u]) => {
      localStorage.setItem("edu:auth:token", t);
      localStorage.setItem("edu:auth:me", JSON.stringify(u));
    },
    [token, user],
  );
  const page = await ctx.newPage();

  /* ---- /community ---- */
  await page.goto(`${BASE}/community`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
  check("社区页标题可见", await page.getByRole("heading", { name: "学习社区" }).isVisible().catch(() => false));
  const boardTabs = await page.locator('[role="tablist"][aria-label="社区分版"] button').count();
  check("4 学科分版 + 全部 Tab（5 个）", boardTabs === 5, `tabs=${boardTabs}`);
  check("热门帖列表渲染（真实 API）", (await page.locator("article").count()) > 0, `posts=${await page.locator("article").count()}`);
  check("侧边栏出现「社区」入口", await page.locator('a[href="/community"]').first().isVisible().catch(() => false));
  check("侧边栏出现「成就中心」入口", await page.locator('a[href="/achievements"]').first().isVisible().catch(() => false));

  /* 打开发帖编辑器 */
  await page.getByRole("button", { name: "发布帖子" }).first().click();
  await page.waitForTimeout(1500);
  check("发帖编辑器出现（Markdown）", await page.locator(".w-md-editor").first().isVisible().catch(() => false));

  /* ---- 帖子详情 ---- */
  const firstPost = await page.locator("article a").first().getAttribute("href").catch(() => null);
  if (firstPost) {
    await page.goto(`${BASE}${firstPost}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);
    check("详情页标题渲染", (await page.locator("h1").count()) > 0);
    check("点赞按钮存在", await page.getByRole("button", { name: /点赞/ }).first().isVisible().catch(() => false));
    check("收藏按钮存在", await page.getByRole("button", { name: /收藏/ }).first().isVisible().catch(() => false));
    check("回帖表单存在", await page.getByPlaceholder(/写下你的看法/).isVisible().catch(() => false));
  }

  /* ---- /achievements ---- */
  await page.goto(`${BASE}/achievements`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  check("成就页徽章墙渲染（8 枚）", (await page.locator('[aria-label^="徽章"]').count()) === 8, `badges=${await page.locator('[aria-label^="徽章"]').count()}`);
  check("积分总览渲染", await page.getByText("当前积分").isVisible().catch(() => false));
  check("排行 Tab 渲染（日/周/月/总）", (await page.locator('[role="tablist"][aria-label="排行时间范围"] button').count()) === 4);
} finally {
  await browser.close();
}

console.log("\n==== 汇总 ====");
const failed = results.filter((r) => !r).length;
console.log(`共 ${results.length} 项，通过 ${results.length - failed}，失败 ${failed}`);
if (failed) process.exitCode = 1;
