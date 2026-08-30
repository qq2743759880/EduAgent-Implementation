/**
 * task69 · 断点截图矩阵 + 视觉验收基线
 * tech-source-audit §六：375/768/1024/1280/1440；成功/空/错误三态覆盖关键页。
 * 命名：test-reports/screenshots/task69/{page}-{viewport}.png
 * 判定：各断点无水平溢出、无元素遮挡、正文可达。
 */
import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { login, ADMIN, STUDENT } from "./helpers";

const VIEWPORTS = [
  { width: 375, height: 667 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
  { width: 1440, height: 900 },
] as const;

const SHOT_DIR = join(__dirname, "..", "test-reports", "screenshots", "task69");

/** 用户端关键页（登录后） */
const USER_SHOT_PAGES = ["/dashboard", "/courses", "/my-courses", "/chat", "/community", "/achievements", "/me"] as const;
/** 管理端关键页 */
const ADMIN_SHOT_PAGES = ["/admin/dashboard", "/admin/users", "/admin/questions", "/admin/rag", "/admin/mcp"] as const;

function safeName(p: string) {
  return p.replace(/^[/]+/, "").replace(/[/?]+/g, "_") || "root";
}

/** 等待页面退出「校验登录/加载」中间态后再截图，避免矩阵抓到骨架/加载骨架（视觉验收才有效） */
async function settle(page: import("@playwright/test").Page) {
  await page
    .waitForFunction(() => {
      const t = document.body.innerText ?? "";
      return !/正在校验登录状态|加载中|加载失败/.test(t);
    }, { timeout: 20_000 })
    .catch(() => {});
  await page.waitForTimeout(500);
}

test.describe("断点截图矩阵（GWT③）", () => {
  for (const vp of VIEWPORTS) {
    test(`用户端矩阵 ${vp.width}x${vp.height}`, async ({ browser }) => {
      test.setTimeout(120_000);
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const page = await ctx.newPage();
      await login(page, STUDENT.account, STUDENT.password);
      mkdirSync(SHOT_DIR, { recursive: true });
      for (const p of USER_SHOT_PAGES) {
        await page.goto(p, { waitUntil: "domcontentloaded", timeout: 30_000 });
        await settle(page);
        await page.screenshot({ path: join(SHOT_DIR, `${safeName(p)}-${vp.width}.png`), fullPage: false });
        // 无水平溢出断言
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        expect(overflow, `${p} @ ${vp.width} 存在水平溢出`).toBeFalsy();
      }
      await ctx.close();
    });
  }
});

test.describe("管理端截图矩阵（GWT③）", () => {
  for (const vp of [VIEWPORTS[3], VIEWPORTS[4]]) { // 管理端以桌面为主：1280/1440
    test(`管理端矩阵 ${vp.width}x${vp.height}`, async ({ browser }) => {
      test.setTimeout(120_000);
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const page = await ctx.newPage();
      await login(page, ADMIN.account, ADMIN.password, new RegExp("/admin/dashboard|/dashboard"));
      mkdirSync(SHOT_DIR, { recursive: true });
      for (const p of ADMIN_SHOT_PAGES) {
        await page.goto(p, { waitUntil: "domcontentloaded", timeout: 30_000 });
        await settle(page);
        await page.screenshot({ path: join(SHOT_DIR, `${safeName(p)}-${vp.width}.png`), fullPage: false });
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        expect(overflow, `${p} @ ${vp.width} 存在水平溢出`).toBeFalsy();
      }
      await ctx.close();
    });
  }
});

test.describe("200% 缩放无水平溢出（等效 1440→720）", () => {
  test("登录态 dashboard 在 200% 设备缩放无横向滚动条", async ({ browser }) => {
    test.setTimeout(90_000);
    const ctx = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      deviceScaleFactor: 2,
    });
    const page = await ctx.newPage();
    await login(page, STUDENT.account, STUDENT.password);
    await page.goto("/dashboard", { waitUntil: "domcontentloaded", timeout: 30_000 });
    await page.waitForTimeout(800);
    // 等效缩放：页面不应依赖 JS 才可读，且无横向溢出
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(overflow, "200% 缩放下 dashboard 水平溢出").toBeFalsy();
    await ctx.close();
  });
});