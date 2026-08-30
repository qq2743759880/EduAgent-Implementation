/**
 * task69 · task42 批判① —— 登录态持久化/刷新/多标签/登出/受保护页守卫
 * 验收：3 用例全 PASS（登录→刷新仍登录；开新标签共享会话；登出→受保护页跳登录）
 */
import { test, expect } from "@playwright/test";
import { login, STUDENT } from "./helpers";

test.describe("登录态持久化（task42 批判①）", () => {
  test("登录 → 刷新仍保持登录", async ({ page }) => {
    await login(page, STUDENT.account, STUDENT.password);
    await expect(page).toHaveURL(/\/dashboard/);
    // 刷新后导航项仍在（登录态已持久化）。移动端主导航折叠进抽屉（不可见），
    // 故改用"URL 保持受保护页 + 正文标题可达"做断点无关断言
    await page.reload({ waitUntil: "networkidle" });
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator("main").first()).toContainText(/今日学习时长|进步|你好|学习仪表盘/);
  });

  test("开新标签共享会话（同一浏览器上下文 cookie/localStorage）", async ({ page, context }) => {
    await login(page, STUDENT.account, STUDENT.password);
    const second = await context.newPage();
    await second.goto("/dashboard", { waitUntil: "networkidle" });
    await expect(second).toHaveURL(/\/dashboard/);
    // 新标签无需二次登录即达受保护页（共享会话）；移动端同样用正文标题断言
    await expect(second.locator("main").first()).toContainText(/今日学习时长|进步|你好|学习仪表盘/);
    await second.close();
  });

  test("登出后受保护页跳转登录", async ({ page }) => {
    await login(page, STUDENT.account, STUDENT.password);
    // 通过用户下拉菜单「退出登录」
    await page.locator('button[aria-haspopup="menu"]').first().click();
    await page.getByRole("menuitem", { name: "退出登录" }).click();
    await page.waitForURL(/\/login/, { timeout: 15_000 });
    // 直接访问受保护页 → 被守卫拦回登录
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await expect(page).toHaveURL(/\/login/);
  });

  test("未登录访问用户页被守卫拦截", async ({ page }) => {
    await page.goto("/me", { waitUntil: "networkidle" });
    await expect(page).toHaveURL(/\/login/);
  });
});